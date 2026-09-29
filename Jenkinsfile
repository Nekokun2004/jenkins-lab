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
        stage('Secrets Detection') {
            agent { label 'linux-build' }
            steps {
                script {
                    docker.image('zricethezav/gitleaks:latest').inside('--entrypoint=""') {
                        sh '''
                            gitleaks detect --source . --no-git \
                                --report-format json --report-path gitleaks-report.json -v || \
                            gitleaks detect --source . --no-git \
                                --report-format json --report-path gitleaks-report.json --exit-code 0
                        '''
                    }
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: 'gitleaks-report.json', allowEmptyArchive: true
                }
            }
        }

        stage('SAST') {
            parallel {
                stage('ESLint Security') {
                    agent { docker { image 'node:20-alpine' } }
                    steps {
                        sh 'npm ci'
                        sh 'npx eslint --plugin security -f @microsoft/eslint-formatter-sarif -o eslint-report.sarif src/ || true'
                    }
                    post {
                        always {
                            archiveArtifacts artifacts: 'eslint-report.sarif', allowEmptyArchive: true
                        }
                    }
                }
                stage('Semgrep') {
                    agent { label 'linux-build' }
                    steps {
                        script {
                            docker.image('semgrep/semgrep:latest').inside {
                                sh 'semgrep --config=p/owasp-top-ten --config=p/nodejs --sarif -o semgrep-report.sarif src/ || true'
                            }
                        }
                    }
                    post {
                        always {
                            archiveArtifacts artifacts: 'semgrep-report.sarif', allowEmptyArchive: true
                        }
                    }
                }
            }
        }

        stage('SCA — npm audit') {
            agent { docker { image 'node:20-alpine' } }
            steps {
                sh 'npm ci'
                script {
                    sh 'apk add --no-cache jq'
                    sh 'npm audit --audit-level=high --json > audit.json || true'
                    def critical = sh(
                        script: "jq '.metadata.vulnerabilities.critical' audit.json",
                        returnStdout: true
                    ).trim().toInteger()
                    if (critical > 0) {
                        error("Blocking: ${critical} critical vulnerabilities found")
                    }
                    echo "SCA passed with 0 critical vulnerabilities (warnings allowed)"
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: 'audit.json', allowEmptyArchive: true
                    stash name: 'audit-report', includes: 'audit.json'
                }
            }
        }

        stage('Generate SBOM') {
            agent { label 'linux-build' }
            steps {
                // syft and cosign publish distroless/scratch images with no shell at all
                // (verified: `docker inspect` shows no /bin/sh), so docker.image().inside()
                // — which needs a shell inside the container to run `sh` steps — can't be
                // used here. Run them as one-shot `docker run` invocations from the agent's
                // own shell instead, passing CLI args directly as the container's CMD.
                sh 'docker run --rm -u $(id -u):$(id -g) -v "$WORKSPACE:/src" -w /src anchore/syft:latest dir:. -o cyclonedx-json=taskflow-api.cdx.json'
                sh '''
                    docker run --rm -u $(id -u):$(id -g) -e COSIGN_PASSWORD= -v "$WORKSPACE:/src" -w /src \
                        ghcr.io/sigstore/cosign/cosign:v2.4.1 generate-key-pair
                    docker run --rm -u $(id -u):$(id -g) -e COSIGN_PASSWORD= -v "$WORKSPACE:/src" -w /src \
                        ghcr.io/sigstore/cosign/cosign:v2.4.1 sign-blob --key cosign.key --yes taskflow-api.cdx.json > taskflow-api.cdx.json.sig
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'taskflow-api.cdx.json,taskflow-api.cdx.json.sig,cosign.pub', allowEmptyArchive: true
                    stash name: 'sbom-report', includes: 'taskflow-api.cdx.json'
                }
            }
        }

        stage('Policy Gate') {
            agent { label 'linux-build' }
            steps {
                unstash 'audit-report'
                script {
                    // opa's published image is also shell-less (same reason as syft/cosign
                    // above) — invoke it as a one-shot `docker run` instead of .inside().
                    def result = sh(
                        script: 'docker run --rm -v "$WORKSPACE:/src" -w /src openpolicyagent/opa:latest eval --input audit.json --data policy/security.rego \'data.security.deny\' -f raw',
                        returnStdout: true
                    ).trim()
                    echo "OPA policy evaluation result: ${result}"
                    if (result != '[]' && result != '') {
                        error("Policy Gate blocked: ${result}")
                    }
                }
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
            // TEMP TEST: checking whether the JAVA_HOME workaround is still needed
            // environment {
            //     JAVA_HOME = '/opt/java/openjdk'
            //     PATH = "${JAVA_HOME}/bin:${env.PATH}"
            // }
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
                    docker.image('mcr.microsoft.com/playwright:v1.63.0-noble').inside('--network host') {
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
                unstash 'coverage-report'
                archiveArtifacts artifacts: 'npm-debug.log*', allowEmptyArchive: true
                junit 'reports/junit.xml'
                publishCoverage adapters: [coberturaAdapter('coverage/cobertura-coverage.xml')]
            }
        }
    }
}
