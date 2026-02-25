@Library('jcloudcodes-shared-library@main') _

pipeline {
  // ✅ Run on your real agent (NO pipeline-level docker agent)
  agent { label 'jslave-inbound' }

  options {
    timestamps()
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '30'))
    timeout(time: 45, unit: 'MINUTES')
    skipDefaultCheckout(true)   // ✅ stop Jenkins doing extra auto-checkouts
  }

  parameters {
    choice(name: 'DEPLOY_ENV', choices: ['lab1', 'qa', 'prod'], description: 'Target environment (used for tagging/metadata)')
    booleanParam(name: 'PUSH_ARTIFACT', defaultValue: true, description: 'Upload build zip to Nexus raw repo')
    booleanParam(name: 'PUSH_DOCKER', defaultValue: true, description: 'Build & push Docker image to registry')
  }

  environment {
    APP_NAME        = 'nasa_world'
    VENV_DIR        = '.venv'
    DJANGO_SETTINGS = 'nasa_world.settings'

    // Sonar
    SONAR_PROJECT_KEY  = 'django-jupiter-starts'
    SONAR_PROJECT_NAME = 'django-jupiter-starts'
    SONAR_SERVER       = 'jcloudcodes-sonarqube'

    // Nexus raw (zip artifacts)
    NEXUS_URL      = 'https://nexus.jcloudcodes.com'
    NEXUS_RAW_REPO = 'django-artifacts'
    NEXUS_CRED_ID  = 'nexus-cred'

    // Docker registry
    REGISTRY_URL   = 'https://nexus.jcloudcodes.com'
    IMAGE_NAME     = 'nasa-docker/nasa_world'
    DOCKER_CRED_ID = 'docker-registry-cred'
  }

  stages {
    stage('Checkout') {
      steps {
        cleanWs()
        checkout scm
        script {
          env.GIT_SHA = sh(script: "git rev-parse --short=12 HEAD", returnStdout: true).trim()
          env.BRANCH  = sh(script: "git rev-parse --abbrev-ref HEAD", returnStdout: true).trim()
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

    // ✅ Python build/test inside a container (avoids Python 3.9 on host)
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

    // ✅ Use your shared library sonar step (requires sonar-scanner on node)
    stage('SonarQube Scan') {
        steps {
            withSonarQubeEnv('jcloudcodes-sonarqube') {
            sh """
                set -euxo pipefail
                docker run --rm \
                -e SONAR_HOST_URL="\$SONAR_HOST_URL" \
                -e SONAR_TOKEN="\$SONAR_AUTH_TOKEN" \
                -v "\$PWD:/usr/src" -w /usr/src \
                sonarsource/sonar-scanner-cli:latest \
                -Dsonar.projectKey=${SONAR_PROJECT_KEY} \
                -Dsonar.projectName=${SONAR_PROJECT_NAME} \
                -Dsonar.sources=. \
                -Dsonar.python.version=3.12 \
                -Dsonar.exclusions=**/migrations/**,**/static/**,**/staticfiles/**,**/media/**,**/.venv/**,**/venv/**,**/__pycache__/** \
                -Dsonar.branch.name=${BRANCH}
            """
            }
        }
        }

    stage('Quality Gate') {
      steps {
        timeout(time: 10, unit: 'MINUTES') {
          waitForQualityGate abortPipeline: true
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

    stage('Build & Push Docker Image') {
      when { expression { return params.PUSH_DOCKER } }
      steps {
        dockerBuildPush(
          registry: env.REGISTRY_URL,
          credentialsId: env.DOCKER_CRED_ID,
          image: env.IMAGE_NAME,
          tag: env.DOCKER_TAG,
          dockerfile: 'Dockerfile',
          context: '.'
        )
      }
    }
  }

  post {
    always {
      archiveArtifacts artifacts: 'dist/*.zip', fingerprint: true, onlyIfSuccessful: false
      junit allowEmptyResults: true, testResults: '**/test-results/**/*.xml, **/pytest-report.xml'
      cleanWs(deleteDirs: true, notFailBuild: true)
    }

    success {
      echo "SUCCESS: ${APP_NAME} artifact=${ARTIFACT_NAME} docker=${IMAGE_NAME}:${DOCKER_TAG}"
    }

    failure {
      echo "FAILED: Check Sonar gate, tests, and Nexus/Docker auth"
    }
  }
}