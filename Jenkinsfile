pipeline {
    agent none

    environment {
        APP_NAME = 'taskflow-api'
        NODE_ENV = 'test'
    }

    options {
        timeout(time: 10, unit: 'MINUTES')
        // A hung npm install or test run must not hold the executor forever —
        // an executor stuck on one dead build blocks every other queued build
        // from ever running on this agent.
    }

    stages {
        stage('Install') {
            agent { docker { image 'node:20-alpine' } }
            steps {
                sh 'npm ci'
            }
        }
        stage('Checks') {
            parallel {
                stage('Lint') {
                    agent { docker { image 'node:20-alpine' } }
                    steps {
                        sh 'npm ci'
                        sh 'npm run lint'
                    }
                }
                stage('Unit Test') {
                    agent { docker { image 'node:20-alpine' } }
                    steps {
                        sh 'npm ci'
                        sh 'npm test -- --coverage --reporters=default --reporters=jest-junit'
                        stash name: 'coverage-report', includes: 'coverage/**, reports/**'
                    }
                }
            }
        }
        stage('SonarQube Analysis') {
            agent { label 'linux-build' }
            environment {
                JAVA_HOME = '/opt/java/openjdk'
                PATH = "${JAVA_HOME}/bin:${env.PATH}"
            }
            steps {
                unstash 'coverage-report'
                script {
                    def scannerHome = tool 'sonar-scanner-tool'
                    withSonarQubeEnv('SonarQube') {
                        sh "${scannerHome}/bin/sonar-scanner -Dsonar.projectKey=taskflow-api -Dsonar.sources=src -Dsonar.javascript.lcov.reportPaths=coverage/lcov.info"
                    }
                }
            }
        }
        stage('Quality Gate') {
            agent { label 'linux-build' }
            steps {
                timeout(time: 5, unit: 'MINUTES') {
                    waitForQualityGate abortPipeline: true
                }
            }
        }
        stage('E2E') {
            agent { label 'linux-build' }
            steps {
                sh 'docker compose up -d --build'
                script {
                    docker.image('mcr.microsoft.com/playwright:v1.49.0-noble').inside('--network host') {
                        sh 'npm ci'
                        sh 'npm run test:e2e'
                    }
                }
            }
            post {
                always {
                    sh 'docker compose down -v'
                    junit 'playwright-report/junit.xml'
                    archiveArtifacts artifacts: 'playwright-report/html/**', allowEmptyArchive: true
                }
            }
        }
        stage('Deploy — Staging') {
            agent { label 'linux-build' }
            when {
                beforeInput true
                branch 'develop'
            }
            steps {
                sh 'echo deploying to staging...'
            }
        }
        stage('Deploy — Production') {
            agent { label 'linux-build' }
            when {
                beforeInput true
                branch 'main'
            }
            input {
                message 'Deploy to production?'
            }
            steps {
                sh 'echo deploying to production...'
            }
        }
    }

    post {
        success {
            node('linux-build') {
                echo "✅ ${env.APP_NAME} passed on ${env.NODE_ENV}"
            }
        }
        failure {
            node('linux-build') {
                echo "❌ Failed at stage: ${env.STAGE_NAME}"
            }
        }
        always {
            node('linux-build') {
                archiveArtifacts artifacts: 'npm-debug.log*', allowEmptyArchive: true
                junit 'reports/junit.xml'
                publishCoverage adapters: [coberturaAdapter('coverage/cobertura-coverage.xml')]
            }
        }
    }
}
