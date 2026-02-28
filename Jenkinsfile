@Library('jcloudcodes-shared-library@main') _

pipeline {
  agent { label 'jslave-inbound' }

  options {
    timestamps()
    disableConcurrentBuilds()
    timeout(time: 45, unit: 'MINUTES')
    skipDefaultCheckout(true)

    buildDiscarder(logRotator(
      daysToKeepStr: '2',
      numToKeepStr: '2',
      artifactDaysToKeepStr: '2',
      artifactNumToKeepStr: '2'
    ))
  }

  parameters {
    choice(name: 'DEPLOY_ENV', choices: ['lab1', 'qa', 'prod'], description: 'Target environment')
    booleanParam(name: 'PUSH_ARTIFACT', defaultValue: true, description: 'Upload build zip to Nexus raw repo')
    booleanParam(name: 'PUSH_DOCKER', defaultValue: true, description: 'Build & push Docker image to registry')

    // ✅ GitOps deploy (ArgoCD trigger)
    booleanParam(name: 'GITOPS_DEPLOY', defaultValue: true, description: 'Update Helm repo values to trigger ArgoCD deploy')
    booleanParam(name: 'REQUIRE_APPROVAL_FOR_PROD', defaultValue: true, description: 'Manual approval gate for prod')
    booleanParam(name: 'ARGO_WAIT', defaultValue: true, description: 'Wait for ArgoCD app to become Synced/Healthy')
  }

  environment {
    VENV_DIR        = '.venv'
    DJANGO_SETTINGS = 'nasa_world.settings'

    // ✅ Helm GitOps repo (ArgoCD watches this repo)
    HELM_REPO_URL    = 'https://github.com/jcloudcodes/jcloud_argocd.git'
    HELM_REPO_BRANCH = 'main'
    HELM_REPO_DIR    = 'helm-gitops'

    // Sonar
    SONAR_PROJECT_KEY  = 'django-jupiter-starts'
    SONAR_PROJECT_NAME = 'django-jupiter-starts'
    SONAR_SERVER       = 'jcloudcodes-sonarqube'

    // Nexus raw (zip artifacts)
    NEXUS_URL       = 'http://nexus.jcloudcodes.com'
    NEXUS_RAW_REPO  = 'django-starts-jupiters'
    NEXUS_CRED_ID   = 'jcloudcodes-nexus-cred'

    // App / image
    APP_NAME    = 'nasa-app'
    IMAGE_NAME  = 'django-starts-jupiters-ig'

    // Nexus Docker registry
    NEXUS_DOCKER_REGISTRY = 'nexus.jcloudcodes.com:20080'
    NEXUS_DOCKER_REPO     = 'django-starts-jupiters-ig'
    NEXUS_DOCKER_CRED     = 'jcloudcodes-nexus-cred'

    // Docker Hub
    DOCKERHUB_NAMESPACE   = 'jcloudcodes'
    DOCKERHUB_CRED        = 'jcloudcodes-dockerhub-cred'

    // ✅ Argo CD
    ARGOCD_SERVER   = 'argocd.jcloudcodes.com'  // change if using LB / ingress / port-forward
    ARGOCD_APP_DEV  = 'django-app-dev'
    ARGOCD_APP_QA   = 'django-app-qa'
    ARGOCD_APP_PROD = 'django-app-prod'
  }

  stages {

    stage('Checkout') {
      steps {
        cleanWs()
        checkout scm
        script {
          env.GIT_SHA  = sh(script: "git rev-parse --short=12 HEAD", returnStdout: true).trim()
          env.BRANCH   = sh(script: "git rev-parse --abbrev-ref HEAD", returnStdout: true).trim()
          env.BUILD_TS = sh(script: "date -u +%Y%m%d%H%M%S", returnStdout: true).trim()

          env.ARTIFACT_NAME = "${APP_NAME}-${BRANCH}-${GIT_SHA}-${BUILD_TS}.zip"
          env.DOCKER_TAG    = "${BRANCH}-${GIT_SHA}"
        }
      }
    }

    stage('Sanity') {
      steps {
        sh '''
          set -euxo pipefail
          echo "NODE_NAME=$NODE_NAME"
          echo "WORKSPACE=$WORKSPACE"
          hostname
          whoami
          docker --version
        '''
      }
    }

    stage('Setup Python + Install Deps (Py3.12 container)') {
      steps {
        sh '''
          set -euxo pipefail
          docker pull python:3.12-slim

          docker run --rm -u 0:0 \
            -v "$PWD:/app" -w /app \
            python:3.12-slim bash -lc "
              apt-get update
              apt-get install -y --no-install-recommends gcc build-essential python3-dev libffi-dev
              rm -rf /var/lib/apt/lists/*

              python --version
              rm -rf .venv
              python -m venv .venv
              .venv/bin/pip install -U pip wheel setuptools
              .venv/bin/pip install -r requirements.txt
            "
        '''
      }
    }

    stage('Lint + Unit Tests (Py3.12 container)') {
      steps {
        sh """
          set -euxo pipefail
          docker run --rm -u 0:0 \
            -v "\$PWD:/app" -w /app \
            python:3.12-slim bash -lc "
              . .venv/bin/activate
              python manage.py check --settings=nasa_world.settings_ci
              if [ -f pytest.ini ] || [ -d tests ]; then
                pip install -U pytest pytest-django coverage
                pytest -q --disable-warnings --maxfail=1
              else
                python manage.py test --settings=nasa_world.settings_ci -v 2
              fi
            "
        """
      }
    }

    stage('Package Build Artifact (zip)') {
      steps {
        sh """
          set -euxo pipefail
          rm -rf dist
          mkdir -p dist

          zip -r "dist/${ARTIFACT_NAME}" . \
            -x ".git/*" ".venv/*" "venv/*" "__pycache__/*" "*.pyc" \
               "staticfiles/*" "media/*" "*.log" ".DS_Store" ".idea/*" ".vscode/*"

          ls -lh dist
        """
      }
    }

    stage('SonarQube Scan') {
      steps {
        withSonarQubeEnv('jcloudcodes-sonarqube') {
          sh """
            set -euxo pipefail
            ${tool 'jcloudcodes-sonarqube-scanner'}/bin/sonar-scanner \
              -Dsonar.projectKey=${SONAR_PROJECT_KEY} \
              -Dsonar.projectName=${SONAR_PROJECT_NAME} \
              -Dsonar.sources=. \
              -Dsonar.python.version=3.12 \
              -Dsonar.exclusions=**/migrations/**,**/static/**,**/staticfiles/**,**/media/**,**/.venv/**,**/venv/**,**/__pycache__/**
          """
        }
      }
    }

    stage('Upload Artifact to Nexus (RAW)') {
      when { expression { return params.PUSH_ARTIFACT } }
      steps {
        nexusUpload(
          nexusUrl: env.NEXUS_URL,
          rawRepo: env.NEXUS_RAW_REPO,
          targetPath: "${APP_NAME}/${env.BRANCH}/${env.GIT_SHA}",
          filePath: "dist/${env.ARTIFACT_NAME}",
          credentialsId: env.NEXUS_CRED_ID
        )
      }
    }

    stage('Build Docker Image') {
      when { expression { return params.PUSH_DOCKER } }
      steps {
        script {
          env.TAG = "${env.BUILD_NUMBER}"                 // final pushed tag
          env.LOCAL_IMAGE = "${env.IMAGE_NAME}:${env.TAG}"
        }
        sh """
          set -euxo pipefail
          docker build -t ${env.LOCAL_IMAGE} -f Dockerfile .
        """
      }
    }

    stage('Push Docker Images (Parallel)') {
      when { expression { return params.PUSH_DOCKER } }
      steps {
        script {
          def tag = env.TAG

          def nexusRepoImage = "${env.NEXUS_DOCKER_REGISTRY}/${env.NEXUS_DOCKER_REPO}/${env.IMAGE_NAME}"
          def hubRepoImage   = "${env.DOCKERHUB_NAMESPACE}/${env.IMAGE_NAME}"

          echo "NEXUS IMAGE: ${nexusRepoImage}:${tag}"
          echo "HUB   IMAGE: ${hubRepoImage}:${tag}"

          parallel(
            'Push Nexus': {
              dockerBuildPush(
                build: false,
                sourceImage: env.LOCAL_IMAGE,
                registry: "http://${env.NEXUS_DOCKER_REGISTRY}",
                credentialsId: env.NEXUS_DOCKER_CRED,
                image: nexusRepoImage,
                tag: tag
              )
            },
            'Push Docker Hub': {
              dockerBuildPush(
                build: false,
                sourceImage: env.LOCAL_IMAGE,
                registry: "https://index.docker.io/v1/",
                credentialsId: env.DOCKERHUB_CRED,
                image: hubRepoImage,
                tag: tag,
                alsoLatest: (params.DEPLOY_ENV == 'prod')
              )
            }
          )
        }
      }
    }

    // ✅ Approval gate for PROD (before GitOps change)
    stage('Approval: PROD Deploy') {
      when { expression { return params.GITOPS_DEPLOY && params.DEPLOY_ENV == 'prod' && params.REQUIRE_APPROVAL_FOR_PROD } }
      steps {
        timeout(time: 15, unit: 'MINUTES') {
          input message: "Approve PROD GitOps deploy to ArgoCD?", ok: "Deploy PROD"
        }
      }
    }

    stage('Set Image Tag (always)') {
      steps {
        script {
          // If docker build ran, TAG already set.
          // If not, fallback to BUILD_NUMBER so GitOps still works.
          env.TAG = env.TAG?.trim() ? env.TAG : "${env.BUILD_NUMBER}"
          echo "Using image tag: ${env.TAG}"
        }
      }
    }

    // ✅ GitOps update (ArgoCD trigger) - updates Helm repo, not app repo
    stage('GitOps: Update Helm repo values (trigger ArgoCD)') {
      when { expression { return params.GITOPS_DEPLOY } }
      steps {
        script {
          def envFolder = (params.DEPLOY_ENV == 'lab1') ? 'dev' : params.DEPLOY_ENV

          def argoApp = (params.DEPLOY_ENV == 'lab1') ? env.ARGOCD_APP_DEV :
                        (params.DEPLOY_ENV == 'qa')   ? env.ARGOCD_APP_QA  : env.ARGOCD_APP_PROD

          env.ARGO_APP = argoApp
          env.GITOPS_ENV_FOLDER = envFolder

          dir(env.HELM_REPO_DIR) {
            deleteDir()

            // ✅ Proper branch checkout (no detached HEAD)
            git url: env.HELM_REPO_URL,
                branch: env.HELM_REPO_BRANCH,
                credentialsId: 'github-cred'

            sh 'git status -sb'


            def valuesFile = "environments/${envFolder}/values.yaml"
            if (!fileExists(valuesFile)) {
              error("Missing Helm values file: ${env.HELM_REPO_DIR}/${valuesFile}")
            }

            gitopsUpdate(
              deployEnv: envFolder,
              valuesFile: valuesFile,
              imageTag: env.TAG,
              argoAppName: argoApp
            )

            env.GITOPS_VALUES_FILE = valuesFile
          }
        }
      }
    }

    stage('GitOps: Commit & Push Helm repo') {
     when { expression { return params.GITOPS_DEPLOY && params.PUSH_DOCKER } }
     steps {
       dir(env.HELM_REPO_DIR) {
         gitopsCommitPush(
           repoUrl: env.HELM_REPO_URL,
           branch: env.HELM_REPO_BRANCH,
           credentialsId: 'github-cred',
           commitMessage: "gitops(${env.GITOPS_ENV_FOLDER}): deploy ${env.IMAGE_NAME}:${env.TAG}",
           pathsToCommit: [ env.GITOPS_VALUES_FILE ]
         )
       }
     }
    }

    stage('ArgoCD: Wait for Sync/Healthy') {
        when { expression { return params.GITOPS_DEPLOY && params.ARGO_WAIT } }
        steps {
          script {
            // Basic sanity (fast fail with clear message)
            if (!env.ARGOCD_SERVER?.trim()) { error("ARGOCD_SERVER is empty") }
            if (!env.ARGO_APP?.trim())      { error("ARGO_APP is empty") }

            echo "ArgoCD server: ${env.ARGOCD_SERVER}"
            echo "ArgoCD app: ${env.ARGO_APP}"
          }

          // 1) Connectivity check (catches DNS / routing / TLS issues)
          sh '''
            set -e
            echo "Checking ArgoCD reachability..."
            curl -ksS --connect-timeout 5 --max-time 10 "${ARGOCD_SERVER}/api/version" | head -c 200 || true
            echo
          '''

          // 2) App existence check (catches wrong app name / RBAC token issues)
          // Uses ArgoCD CLI (recommended). If you don't have argocd CLI installed on the agent,
          // skip this block and go straight to argocdWait below.
          withCredentials([string(credentialsId: 'argocd-token', variable: 'ARGO_TOKEN')]) {
            sh '''
              set -e
              if command -v argocd >/dev/null 2>&1; then
                echo "argocd CLI found. Verifying login + app access..."
                argocd version --server "${ARGOCD_SERVER}" --insecure --auth-token "${ARGO_TOKEN}" || true
                argocd app get "${ARGO_APP}" --server "${ARGOCD_SERVER}" --insecure --auth-token "${ARGO_TOKEN}" >/dev/null
                echo "App exists and token has access ✅"
              else
                echo "argocd CLI not found on this Jenkins agent; skipping CLI checks."
              fi
            '''
          }

          // 3) Wait for Sync/Healthy
          argocdWait(
            server: env.ARGOCD_SERVER,
            appName: env.ARGO_APP,
            credentialsId: 'argocd-token',
            timeoutSeconds: 600,
            insecure: true
          )
        }
      }
    // ✅ Wait for Argo CD to sync + become healthy (prod ready)
    // stage('ArgoCD: Wait for Sync/Healthy') {
    //   when { expression { return params.GITOPS_DEPLOY && params.ARGO_WAIT } }
    //   steps {
    //     argocdWait(
    //       server: env.ARGOCD_SERVER,
    //       appName: env.ARGO_APP,
    //       credentialsId: 'argocd-token',
    //       timeoutSeconds: 600,
    //       insecure: true
    //     )
    //   }
    // }

  }
  post {
    always {
      sh '''
        set +e
        echo "Docker cleanup: remove images matching django-starts-jupiters-ig"
        docker images --format "{{.Repository}}:{{.Tag}} {{.ID}}" | \
          awk '/django-starts-jupiters-ig/ {print $2}' | sort -u | \
          xargs -r docker rmi -f || true
        docker image prune -f || true
        true
      '''
      archiveArtifacts artifacts: 'dist/*.zip', fingerprint: true, onlyIfSuccessful: false
      junit allowEmptyResults: true, testResults: '**/test-results/**/*.xml, **/pytest-report.xml'
      cleanWs(deleteDirs: true, notFailBuild: true)
    }

    success {
      echo "SUCCESS: ${APP_NAME} artifact=${ARTIFACT_NAME} docker=${IMAGE_NAME}:${TAG} env=${DEPLOY_ENV} argoApp=${ARGO_APP}"
    }

    failure {
      echo "FAILED: Check logs above for the stage that failed (GitOps/ArgoCD/Tests/Nexus/Docker)."
    }
  }
}
