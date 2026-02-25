pipeline {
  agent none

  stages {
    stage('Checkout') {
      agent { label 'jslave-inbound' }
      steps { checkout scm }
    }

    stage('Sanity') {
      agent { label 'jslave-inbound' }
      steps { sh 'echo SH_WORKS && hostname && whoami && pwd' }
    }

    stage('Python Build in Container') {
      agent { label 'jslave-inbound' }
      steps {
        sh '''
          set -euxo pipefail
          docker run --rm -u 0:0 -v "$PWD:/app" -w /app python:3.12-slim \
            bash -lc "python --version"
        '''
      }
    }
  }
}