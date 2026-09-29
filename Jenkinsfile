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
            agent {
                docker {
                    image 'node:20-alpine'
                    // apk add needs root to write /var/cache/apk and /lib/apk/db; Jenkins'
                    // Docker Pipeline plugin otherwise runs the container as uid 1000 (matching
                    // the agent's jenkins user), which fails with "Unable to open log:
                    // Permission denied" before jq is even installed — confirmed by reproducing
                    // the exact error with `docker run -u 1000:1000`.
                    args '-u root'
                }
            }
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
                // Running this container as root means `npm ci` above wrote root-owned
                // node_modules. Only audit.json is stashed forward, so clean node_modules
                // up now rather than leave root-owned files behind — Jenkins reuses this
                // physical workspace directory across future builds, and a later stage
                // running as uid 1000 (the normal case) would otherwise hit the same
                // permission wall we just fixed here.
                sh 'rm -rf node_modules'
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
                //
                // anchore/syft:latest has NO /etc/passwd at all (confirmed via `docker cp`),
                // so uid 1000 has no home directory entry and Go's home-dir resolution falls
                // back to '/', which is root-owned. syft then fails trying to write both its
                // cache dir (/.cache/syft) and — fatally — the output report itself, relative
                // to that broken HOME. Root isn't needed here (unlike apk in SCA, which needs
                // real root-owned system directories); pointing HOME at an always-writable
                // directory fixes the actual cause without escalating privileges or producing
                // root-owned output files.
                sh 'docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v "$WORKSPACE:/src" -w /src anchore/syft:latest dir:. -o cyclonedx-json=taskflow-api.cdx.json'
                sh '''
                    docker run --rm -u $(id -u):$(id -g) -e COSIGN_PASSWORD= -v "$WORKSPACE:/src" -w /src \
                        ghcr.io/sigstore/cosign/cosign:v2.4.1 generate-key-pair
                    docker run --rm -u $(id -u):$(id -g) -e COSIGN_PASSWORD= -v "$WORKSPACE:/src" -w /src \
                        ghcr.io/sigstore/cosign/cosign:v2.4.1 sign-blob --key cosign.key --tlog-upload=false --yes taskflow-api.cdx.json > taskflow-api.cdx.json.sig
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
                script {
                    // If 'SCA — npm audit' never reached its post.always (e.g. it was itself
                    // skipped or crashed before stashing), unstash throws a raw AbortException
                    // that masks the real upstream failure behind a confusing "no such saved
                    // stash" error. Catch just that and let the real problem surface naturally
                    // below instead: the opa eval step will fail on its own, loudly, because
                    // audit.json genuinely won't exist — this doesn't hide a real failure, it
                    // just replaces a misleading one with an accurate one.
                    try {
                        unstash 'audit-report'
                    } catch (Exception e) {
                        echo "No 'audit-report' stash found, skipping: ${e.message}"
                    }
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
                script {
                    // Same reasoning as Policy Gate: if 'Unit Test' never ran (e.g. an earlier
                    // stage failed first), unstash throws a raw AbortException that masks the
                    // real upstream failure. Catch just that; junit/publishCoverage below will
                    // still fail loudly on their own if reports/coverage genuinely don't exist,
                    // so a real problem still surfaces — just without the confusing extra error.
                    try {
                        unstash 'coverage-report'
                    } catch (Exception e) {
                        echo "No 'coverage-report' stash found, skipping: ${e.message}"
                    }
                }
                archiveArtifacts artifacts: 'npm-debug.log*', allowEmptyArchive: true
                junit 'reports/junit.xml'
                publishCoverage adapters: [coberturaAdapter('coverage/cobertura-coverage.xml')]
            }
        }
    }
}
