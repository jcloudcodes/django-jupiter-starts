@Library('jcloudcodes-shared-library@main') _

pipeline {
  agent jslave-inbound

  options {
    timestamps()
    ansiColor('xterm')
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '30'))
    timeout(time: 45, unit: 'MINUTES')
  }

  parameters {
    choice(name: 'DEPLOY_ENV', choices: ['lab1', 'qa', 'prod'], description: 'Target environment (used for tagging/metadata)')
    booleanParam(name: 'PUSH_ARTIFACT', defaultValue: true, description: 'Upload build zip to Nexus raw repo')
    booleanParam(name: 'PUSH_DOCKER', defaultValue: true, description: 'Build & push Docker image to registry')
  }

  environment {
    APP_NAME          = 'nasa_world'
    PYTHON_VERSION    = '3.12'
    VENV_DIR          = '.venv'
    DJANGO_SETTINGS   = 'nasa_world.settings'

    //Sonar metadata
    SONAR_PROJECT_KEY   = 'django-juipiter-starts'
    SONAR_PROJECT_NAME  = 'django-juipiter-starts'
    //SonarQube server name configured in Jenkins
    SONAR_SERVER = 'jcloudcodes-sonarqube'

    // Artifact naming
    BUILD_TS = "${new Date().format('yyyyMMddHHmmss', TimeZone.getTimeZone('UTC'))}"

    // Nexus raw repo (zip artifacts)
    NEXUS_URL       = 'https://nexus.jcloudcodes.com'
    NEXUS_RAW_REPO  = 'django-artifacts'      // <-- create a RAW hosted repo with this name
    NEXUS_CRED_ID   = 'nexus-cred'            // <-- Jenkins credential (username/password)

    // Docker registry
    // - For JFrog Artifactory Docker registry example:
    //   REGISTRY_URL = 'https://your-artifactory.example.com'
    //   IMAGE_NAME   = 'your-docker-local/nasa-world'
    //
    // - For Nexus Docker repo example:
    //   REGISTRY_URL = 'https://nexus.jcloudcodes.com'
    //   IMAGE_NAME   = 'nasa-docker/nasa_world'
    //
    REGISTRY_URL    = 'https://nexus.jcloudcodes.com'
    IMAGE_NAME      = 'nasa-docker/nasa_world'
    DOCKER_CRED_ID  = 'docker-registry-cred'  // <-- Jenkins credential for docker registry
  }

  stages {
    stage('Checkout') {
      steps {
        cleanWs()
        checkout scm
        script {
          env.GIT_SHA = sh(script: "git rev-parse --short=12 HEAD", returnStdout: true).trim()
          env.BRANCH  = sh(script: "git rev-parse --abbrev-ref HEAD", returnStdout: true).trim()
          env.ARTIFACT_NAME = "${APP_NAME}-${BRANCH}-${GIT_SHA}-${BUILD_TS}.zip"
          env.DOCKER_TAG    = "${BRANCH}-${GIT_SHA}"
        }
      }
    }

    stage('Setup Python + Install Deps') {
      steps {
        djangoCi(
          pythonVersion: env.PYTHON_VERSION,
          venvDir: env.VENV_DIR,
          settingsMod: env.DJANGO_SETTINGS,
          requirements: 'requirements.txt'
        )
      }
    }

    stage('Lint + Unit Tests') {
      steps {
        sh """
          set -euxo pipefail
          ${VENV_DIR}/bin/python -V
          ${VENV_DIR}/bin/python -m pip show django || true

          # Optional: run migrations check (safe check)
          ${VENV_DIR}/bin/python manage.py check --settings=${DJANGO_SETTINGS}

          # If you use pytest:
          if [ -f "pytest.ini" ] || [ -d "tests" ]; then
            ${VENV_DIR}/bin/python -m pip install -U pytest pytest-django coverage
            ${VENV_DIR}/bin/python -m pytest -q --disable-warnings --maxfail=1
          else
            # Django default tests
            ${VENV_DIR}/bin/python manage.py test --settings=${DJANGO_SETTINGS} -v 2
          fi
        """
      }
    }

    stage('Package Build Artifact (zip)') {
      steps {
        sh """
          set -euxo pipefail
          rm -rf dist
          mkdir -p dist

          # Create a clean zip artifact without venv, git, caches, media/staticfiles
          zip -r "dist/${ARTIFACT_NAME}" . \
            -x ".git/*" ".venv/*" "venv/*" "__pycache__/*" "*.pyc" \
               "staticfiles/*" "media/*" "*.log" ".DS_Store" ".idea/*" ".vscode/*"
          ls -lh dist
        """
      }
    }

    stage('SonarQube Scan') {
      steps {
        // Requires sonar-scanner to exist on agent (or install via tool/containers)
        sonarScan(
          sonarServer: env.SONAR_SERVER,
          projectKey: env.SONAR_PROJECT_KEY,
          projectName: env.SONAR_PROJECT_NAME,
          sources: '.',
          pythonVersion: env.PYTHON_VERSION,
          // (optional) extra args:
          extraArgs: "-Dsonar.branch.name=${env.BRANCH}"
        )
      }
    }

//     stage('Quality Gate') {
//       steps {
//         timeout(time: 10, unit: 'MINUTES') {
//           // Fails the build if gate fails
//           waitForQualityGate abortPipeline: true
//         }
//       }
//     }

//     stage('Upload Artifact to Nexus (RAW)') {
//       when { expression { return params.PUSH_ARTIFACT } }
//       steps {
//         nexusUpload(
//           nexusUrl: env.NEXUS_URL,
//           rawRepo: env.NEXUS_RAW_REPO,
//           targetPath: "${APP_NAME}/${env.BRANCH}/${env.GIT_SHA}",
//           filePath: "dist/${env.ARTIFACT_NAME}",
//           credentialsId: env.NEXUS_CRED_ID
//         )
//       }
//     }

//     stage('Build & Push Docker Image') {
//       when { expression { return params.PUSH_DOCKER } }
//       steps {
//         dockerBuildPush(
//           registry: env.REGISTRY_URL,
//           credentialsId: env.DOCKER_CRED_ID,
//           image: env.IMAGE_NAME,
//           tag: env.DOCKER_TAG,
//           dockerfile: 'Dockerfile',
//           context: '.'
//         )
//       }
//     }
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