pipeline {
    agent none

    environment {
        APP_NAME = 'taskflow-api'
        NODE_ENV = 'test'
        REGISTRY = 'localhost:5000'
        // Lab 08: no interactive prompts / hints from Terraform in the console
        TF_IN_AUTOMATION = '1'
        TF_INPUT = '0'
        // Lab 10 Pipeline Health Gate
        PROM_URL = 'http://localhost:9090'
        HEALTH_THRESHOLD = '90'
        HEALTH_WINDOW = "${params.HEALTH_WINDOW}"
    }

    parameters {
        string(name: 'HEALTH_WINDOW', defaultValue: '1h',
               description: 'Lab 10 Pipeline Health Gate: look-back window for the build success rate (Prometheus duration, e.g. 1h, 6h)')
        booleanParam(name: 'SKIP_IAC', defaultValue: false,
                     description: 'Lab 10 test aid: skip the Lab 08 IaC stages (Terraform plan/approval/apply, Ansible) so a run can reach the Pipeline Health Gate without a human Terraform approval. Default false = full pipeline.')
        choice(name: 'DEPLOY_FAULT', choices: ['none', 'bad-image', 'post-switch-fail'],
               description: 'Lab 07 failure injection. none = normal deploy; bad-image = deploy a nonexistent tag (rollout times out before the switch); post-switch-fail = fail the verification AFTER the Service switch (rollback flips the selector back)')
    }

    options {
        timeout(time: 45, unit: 'MINUTES')
        // A hung npm install or test run must not hold the executor forever —
        // an executor stuck on one dead build blocks every other queued build
        // from ever running on this agent. Raised from 10 for Lab 07: Build Image + Trivy
        // (first run downloads its DB) + kubectl rollout add several minutes. Raised again
        // for Lab 08: the whole run now includes IaC stages AND the (up to 15 min) human approval wait.
        disableConcurrentBuilds()
        // Two builds flipping Service/taskflow at once would corrupt the recorded previous color.
    }

    stages {
        stage('Install') {
            agent {
                kubernetes {
                    // The plugin always adds a `jnlp` container; without this, `sh` would run in it (no node/npm).
                    defaultContainer 'node'
                    yaml '''
                        apiVersion: v1
                        kind: Pod
                        spec:
                          containers:
                          - name: node
                            image: node:20-alpine
                            command: ['cat']
                            tty: true
                        '''
                }
            }
            steps {
                sh 'npm ci'
            }
        }
        stage('Fast Checks') {
            parallel {
                stage('Lint') {
                    agent {
                        kubernetes {
                            // The plugin always adds a `jnlp` container; without this, `sh` would run in it (no node/npm).
                            defaultContainer 'node'
                            yaml '''
                                apiVersion: v1
                                kind: Pod
                                spec:
                                  containers:
                                  - name: node
                                    image: node:20-alpine
                                    command: ['cat']
                                    tty: true
                                '''
                        }
                    }
                    steps {
                        sh 'npm ci'
                        sh 'npm run lint'
                    }
                }
                stage('Unit Test') {
                    agent {
                        kubernetes {
                            // The plugin always adds a `jnlp` container; without this, `sh` would run in it (no node/npm).
                            defaultContainer 'node'
                            yaml '''
                                apiVersion: v1
                                kind: Pod
                                spec:
                                  containers:
                                  - name: node
                                    image: node:20-alpine
                                    command: ['cat']
                                    tty: true
                                '''
                        }
                    }
                    steps {
                        sh 'npm ci'
                        sh 'npm test -- --coverage --reporters=default --reporters=jest-junit'
                        stash name: 'coverage-report', includes: 'coverage/**, reports/**'
                    }
                }
                stage('Secrets Detection') {
                    agent { label 'linux-build' }
                    steps {
                        script {
                            // -u 0:0 (numeric root, not the name 'root'): forced preemptively so a
                            // future scanner-image swap can't silently reintroduce a uid-mismatch bug
                            // like the ones already hit in SCA and Generate SBOM.
                            docker.image('zricethezav/gitleaks:latest').inside('--entrypoint="" -u 0:0') {
                                sh '''
                                    gitleaks detect --source . --no-git \
                                        --report-format json --report-path gitleaks-report.json -v || \
                                    gitleaks detect --source . --no-git \
                                        --report-format json --report-path gitleaks-report.json --exit-code 0
                                    # ran as root: hand the report back to the workspace owner
                                    chown "$(stat -c '%u:%g' .)" gitleaks-report.json
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
                    // Declarative Pipeline does not allow a parallel nested inside this parallel (validated by the
                    // Jenkins linter), so the two scanners run one after the other inside this Fast Checks lane.
                    stages {
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
                                    docker.image('semgrep/semgrep:latest').inside('-u 0:0') {
                                        sh '''
                                            semgrep --config=p/owasp-top-ten --config=p/nodejs --sarif -o semgrep-report.sarif src/ || true
                                            # ran as root: hand the report back to the workspace owner
                                            chown "$(stat -c '%u:%g' .)" semgrep-report.sarif
                                        '''
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
                        script {
                            // npm audit resolves entirely from package.json/package-lock.json — it
                            // does not need node_modules installed. Skipping npm ci here means this
                            // stage never creates node_modules at all, so there's nothing for the
                            // root-owned-file residue problem (that we hit and fixed once already)
                            // to even apply to. Verified locally: audit.json comes out identical
                            // with or without a prior npm ci.
                            sh 'apk add --no-cache jq'
                            sh 'npm audit --audit-level=high --json > audit.json || true'
                            // container runs as root (needed for apk): hand audit.json back to the
                            // workspace owner so the later unstash/overwrite as uid 1000 can't collide
                            sh 'chown "$(stat -c \'%u:%g\' .)" audit.json'
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
                // Run as root (-u 0:0, numeric — anchore/syft:latest has no /etc/passwd at
                // all, so '-u root' by NAME fails outright with "unable to find user root:
                // no matching entries in passwd file"; numeric uids bypass that lookup and
                // work regardless of whether the image has a user database). Root sidesteps
                // syft's broken HOME resolution entirely. This leaves cosign.key/cosign.pub/
                // taskflow-api.cdx.json root-owned, so the chown step below reclaims them —
                // same pattern as SCA's fix, applied consistently here too.
                //
                // '-v "$WORKSPACE:/src"' was a raw HOST bind mount, but this agent container
                // talks to the real host's dockerd over the shared docker.sock (Docker-
                // outside-of-Docker) — $WORKSPACE is a path inside the agent's own named-
                // volume filesystem, NOT a real path on the actual host. Docker silently
                // auto-created an empty directory at that literal path on the real host and
                // wrote output there instead, completely disconnected from the real
                // workspace — confirmed by reproducing it and checking both locations
                // independently. '--volumes-from jenkins-agent-linux-build' shares the
                // agent's own filesystem view instead (the same mechanism Jenkins' own
                // docker.image().inside() already uses correctly for Gitleaks/Semgrep, just
                // spelled out explicitly here since a raw docker run doesn't get it for
                // free). Hardcoding this container's name is a known coupling specific to
                // this single-agent lab setup — Jenkins' NODE_NAME ('linux-build', the
                // agent's logical label) and the underlying Docker container's actual name
                // ('jenkins-agent-linux-build') are two separate identifiers with no
                // automatic mapping between them.
                // The agent workspace persists across builds, and `cosign generate-key-pair`
                // refuses to overwrite an existing cosign.key (interactive "Overwrite?" prompt
                // -> "user declined the prompt" in CI). Start from a clean slate every run.
                sh 'rm -f cosign.key cosign.pub taskflow-api.cdx.json taskflow-api.cdx.json.sig'
                sh 'docker run --rm -u 0:0 --volumes-from jenkins-agent-linux-build -w "$WORKSPACE" anchore/syft:latest dir:. -o cyclonedx-json=taskflow-api.cdx.json'
                sh '''
                    docker run --rm -u 0:0 -e COSIGN_PASSWORD= --volumes-from jenkins-agent-linux-build -w "$WORKSPACE" \
                        ghcr.io/sigstore/cosign/cosign:v2.4.1 generate-key-pair
                    docker run --rm -u 0:0 -e COSIGN_PASSWORD= --volumes-from jenkins-agent-linux-build -w "$WORKSPACE" \
                        ghcr.io/sigstore/cosign/cosign:v2.4.1 sign-blob --key cosign.key --tlog-upload=false --yes taskflow-api.cdx.json > taskflow-api.cdx.json.sig
                '''
                // A plain `chown` here would run as the agent's own uid (1000, non-root),
                // which cannot reclaim files it doesn't own — confirmed: 'Operation not
                // permitted'. Root only exists *inside* a container relative to the bind
                // mount, so the chown itself has to run the same way the scanners did.
                sh '''
                    TARGET_UID=$(id -u); TARGET_GID=$(id -g)
                    docker run --rm -u 0:0 --volumes-from jenkins-agent-linux-build -w "$WORKSPACE" node:20-alpine chown -R "${TARGET_UID}:${TARGET_GID}" .
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'taskflow-api.cdx.json,taskflow-api.cdx.json.sig,cosign.pub', allowEmptyArchive: true
                    stash name: 'sbom-report', includes: 'taskflow-api.cdx.json'
                    // The signing key is a throwaway generated per build and never archived. Leaving
                    // it in the persistent workspace makes the NEXT build's Secrets Detection flag
                    // it as a leaked private key (found by a second local pass), so remove it.
                    sh 'rm -f cosign.key'
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
                        script: 'docker run --rm -u 0:0 --volumes-from jenkins-agent-linux-build -w "$WORKSPACE" openpolicyagent/opa:latest eval --input audit.json --data policy/security.rego \'data.security.deny\' -f raw',
                        returnStdout: true
                    ).trim()
                    echo "OPA policy evaluation result: ${result}"
                    if (result != '[]' && result != '') {
                        error("Policy Gate blocked: ${result}")
                    }
                }
            }
        }
        stage('SonarQube Analysis') {
            agent { label 'linux-build' }
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
        stage('Build Image') {
            agent { label 'linux-build' }
            steps {
                script {
                    // Immutable tag = first 7 chars of the Git SHA. Never 'latest'.
                    env.SHORT_SHA = env.GIT_COMMIT ? env.GIT_COMMIT.take(7) :
                        sh(script: 'git rev-parse HEAD', returnStdout: true).trim().take(7)
                    // env.* (not `def`) so the next stages — which run on a fresh agent context — still see it.
                    env.IMAGE = "${env.REGISTRY}/${env.APP_NAME}:${env.SHORT_SHA}"
                }
                // docker build streams its context over docker.sock (no bind mount), so the
                // phantom-workspace-mount quirk does not apply here.
                sh '''
                    set -eu
                    echo "Building immutable image: $IMAGE"
                    docker build -t "$IMAGE" .
                    docker image inspect "$IMAGE" --format 'Local image id: {{.Id}}'
                    docker push "$IMAGE"
                    curl -fsS "http://$REGISTRY/v2/$APP_NAME/tags/list"
                    echo
                    curl -fsS "http://$REGISTRY/v2/$APP_NAME/tags/list" | grep -q "$SHORT_SHA"
                    echo "Verified in registry: $IMAGE"
                '''
            }
        }
        stage('Container Scan') {
            agent { label 'linux-build' }
            steps {
                // Trivy's image is distroless-ish and needs root for docker.sock. As with Syft/OPA, the
                // workspace comes from --volumes-from (NEVER -v "$WORKSPACE:..."): that also carries the
                // agent's /var/run/docker.sock, so Trivy sees the image just built without pulling it.
                // Workspace persists across builds: start from a clean slate.
                sh 'rm -f trivy-report.sarif'
                // PASS 1: write the SARIF report no matter what is found (--exit-code 0).
                sh '''
                    docker run --rm -u 0:0 -v trivy-cache:/root/.cache \
                        --volumes-from jenkins-agent-linux-build -w "$WORKSPACE" \
                        aquasec/trivy:latest image \
                            --format sarif -o trivy-report.sarif \
                            --severity HIGH,CRITICAL --exit-code 0 \
                            "$IMAGE"
                '''
                // Root wrote the report: hand it back (a bare chown from the agent shell is not permitted).
                sh '''
                    docker run --rm -u 0:0 --volumes-from jenkins-agent-linux-build -w "$WORKSPACE" \
                        node:20-alpine chown "$(id -u):$(id -g)" trivy-report.sarif
                    test -s trivy-report.sarif
                '''
                // PASS 2: the gate. HIGH/CRITICAL => exit 1 => stage red => Blue/Green Deploy never runs.
                sh '''
                    docker run --rm -u 0:0 -v trivy-cache:/root/.cache \
                        --volumes-from jenkins-agent-linux-build \
                        aquasec/trivy:latest image \
                            --quiet --severity HIGH,CRITICAL --exit-code 1 \
                            "$IMAGE"
                '''
            }
            post {
                always {
                    // runs on a red scan too, so the SARIF of a blocked image stays downloadable
                    archiveArtifacts artifacts: 'trivy-report.sarif', allowEmptyArchive: true
                }
            }
        }
        stage('Blue/Green Deploy') {
            agent { label 'linux-build' }
            environment {
                KUBECONFIG = '/home/jenkins/.kube/config'
            }
            steps {
                // Stale state from a previous build must never drive this build's rollback.
                sh 'rm -f .lab07-previous-color'
                script {
                    // 1) live color, recorded BEFORE anything is touched
                    def current = sh(
                        script: "kubectl get svc taskflow -o jsonpath='{.spec.selector.color}'",
                        returnStdout: true
                    ).trim()
                    if (current != 'blue' && current != 'green') {
                        error("Service/taskflow has unexpected color selector: '${current}'")
                    }
                    // 2) candidate = the other color (valid Groovy: == compares, -= would assign)
                    def next = current == 'blue' ? 'green' : 'blue'
                    // 3) `def` locals die with this script block and are invisible to post.failure:
                    //    keep the rollback context in env.* AND a workspace file.
                    env.PREV_COLOR = current
                    env.NEXT_COLOR = next
                    writeFile file: '.lab07-previous-color', text: current
                    env.DEPLOY_IMAGE = (params.DEPLOY_FAULT == 'bad-image') ?
                        "${env.REGISTRY}/${env.APP_NAME}:0000000-does-not-exist" :
                        env.IMAGE
                    env.VERIFY_PATH = (params.DEPLOY_FAULT == 'post-switch-fail') ? '/health-broken' : '/health'
                    echo "Current active color: ${current}"
                    echo "Candidate color: ${next}"
                    echo "Deploying image: ${env.DEPLOY_IMAGE} (fault mode: ${params.DEPLOY_FAULT})"
                }
                sh '''
                    set -eu
                    # curl pod inside the cluster; url -> pod name. Retries absorb kubectl-attach races.
                    smoke() {
                        url="$1"; pod="$2"; n=0
                        while [ "$n" -lt 3 ]; do
                            n=$((n+1))
                            kubectl delete pod "$pod" --ignore-not-found >/dev/null
                            if out=$(kubectl run "$pod" --rm -i --restart=Never \
                                    --image=curlimages/curl:8.10.1 --command -- \
                                    curl -fsS --max-time 5 "$url") && echo "$out" | grep -q '"status":"ok"'; then
                                echo "Response from $url: $out"
                                return 0
                            fi
                            echo "attempt $n failed for $url"; sleep 2
                        done
                        return 1
                    }

                    echo "===== Service/taskflow BEFORE ====="
                    kubectl get svc taskflow -o yaml

                    # Deploy to the INACTIVE color. Service/taskflow keeps pointing at $PREV_COLOR throughout.
                    kubectl set image deployment/taskflow-$NEXT_COLOR taskflow="$DEPLOY_IMAGE"
                    kubectl rollout status deployment/taskflow-$NEXT_COLOR --timeout=90s
                    echo "Rollout complete for $NEXT_COLOR"

                    # Smoke test via Service/taskflow-<color> (a Deployment name alone is not a DNS name).
                    smoke "http://taskflow-$NEXT_COLOR:8080/health" "smoke-$BUILD_NUMBER"
                    echo "Smoke test passed for $NEXT_COLOR (Service/taskflow still -> $(kubectl get svc taskflow -o jsonpath='{.spec.selector.color}'))"

                    # Only now: switch traffic.
                    echo "Switching traffic $PREV_COLOR -> $NEXT_COLOR"
                    kubectl patch svc taskflow --type merge -p "$(printf '{"spec":{"selector":{"app":"taskflow","color":"%s"}}}' "$NEXT_COLOR")"
                    echo "Active color is now $(kubectl get svc taskflow -o jsonpath='{.spec.selector.color}')"

                    # Post-switch verification through the live Service; failure => post.failure rollback.
                    smoke "http://taskflow:8080$VERIFY_PATH" "verify-$BUILD_NUMBER"

                    echo "===== Service/taskflow AFTER ====="
                    kubectl get svc taskflow -o yaml
                    echo "Blue/Green deploy SUCCESS: active color is $NEXT_COLOR"
                '''
            }
            post {
                failure {
                    sh '''
                        set -u
                        PREV=$(cat .lab07-previous-color 2>/dev/null || true)
                        [ -n "$PREV" ] || PREV="${PREV_COLOR:-}"
                        if [ -z "$PREV" ]; then
                            echo "Deployment failed before the previous color was recorded; Service/taskflow was never touched. Nothing to roll back."
                            exit 0
                        fi
                        echo "Deployment failed."
                        echo "Active color BEFORE rollback: $(kubectl get svc taskflow -o jsonpath='{.spec.selector.color}')"
                        echo "Rolling back Service selector to $PREV."
                        kubectl patch svc taskflow --type merge -p "$(printf '{"spec":{"selector":{"app":"taskflow","color":"%s"}}}' "$PREV")"
                        ACTIVE=$(kubectl get svc taskflow -o jsonpath='{.spec.selector.color}')
                        echo "Rollback complete. Active color: $ACTIVE."
                        # put the failed (inactive) color back on its previous revision; never affects traffic
                        kubectl rollout undo deployment/taskflow-${NEXT_COLOR:-none} || true
                        echo "===== Service/taskflow AFTER ROLLBACK ====="
                        kubectl get svc taskflow -o yaml
                        [ "$ACTIVE" = "$PREV" ]
                    '''
                }
            }
        }
        stage('IaC Lint & Validate') {
            when {
                beforeAgent true
                expression { !params.SKIP_IAC }
            }
            parallel {
                stage('Terraform Validate') {
                    agent { label 'linux-build' }
                    steps {
                        dir('infra/terraform') {
                            sh '''
                                terraform init -backend=false -no-color
                                terraform validate -no-color
                                terraform fmt -check -recursive
                            '''
                        }
                    }
                }
                stage('Ansible Lint') {
                    agent { label 'linux-build' }
                    steps {
                        sh 'ansible-lint infra/ansible/playbook.yml'
                    }
                }
            }
        }
        stage('IaC Security Scan') {
            when {
                beforeAgent true
                expression { !params.SKIP_IAC }
            }
            agent { label 'linux-build' }
            steps {
                dir('infra/terraform') {
                    // Run BOTH scanners so the console shows every finding, then fail if either
                    // one failed. No `|| true`: a finding must turn this stage red before any plan exists.
                    sh '''
                        set +e
                        echo "===== tfsec ====="
                        tfsec . --no-colour
                        TFSEC_RC=$?
                        echo "===== Checkov ====="
                        checkov -d . --compact
                        CHECKOV_RC=$?
                        echo "tfsec exit=$TFSEC_RC checkov exit=$CHECKOV_RC"
                        [ "$TFSEC_RC" -eq 0 ] && [ "$CHECKOV_RC" -eq 0 ]
                    '''
                }
            }
        }
        stage('Terraform Plan') {
            when {
                beforeAgent true
                expression { !params.SKIP_IAC }
            }
            agent { label 'linux-build' }
            steps {
                // Persistent workspace: never let a previous build's plan be re-used.
                sh 'rm -f infra/terraform/tfplan infra/terraform/tfplan.txt infra/terraform/tf-outputs.json'
                dir('infra/terraform') {
                    sh '''
                        terraform init -no-color
                        terraform plan -no-color -out=tfplan
                        terraform show -no-color tfplan > tfplan.txt
                    '''
                }
                // agent-per-stage = separate workspaces: the plan (and the provider lock it was made
                // with) must travel by stash. This exact plan file is what Apply will consume.
                stash name: 'tfplan-artifact', includes: 'infra/terraform/tfplan,infra/terraform/tfplan.txt,infra/terraform/.terraform.lock.hcl'
                archiveArtifacts artifacts: 'infra/terraform/tfplan.txt', allowEmptyArchive: true
            }
        }
        stage('Approval') {
            when {
                beforeAgent true
                expression { !params.SKIP_IAC }
            }
            agent { label 'linux-build' }
            steps {
                unstash 'tfplan-artifact'
                script {
                    def plan = readFile('infra/terraform/tfplan.txt')
                    echo plan
                    // The prompt shows the plan WITHOUT the "(known after apply)" noise, capped so the
                    // text box stays usable; the untouched full plan is in this console log and in the
                    // tfplan.txt artifact.
                    def summary = plan.readLines().findAll { !it.contains('(known after apply)') }.join('\n')
                    def limit = 12000
                    def shown = summary.length() > limit ?
                        summary.take(limit) + "\n... [truncated: full plan in the console log and tfplan.txt artifact]" : summary
                    timeout(time: 15, unit: 'MINUTES') {
                        input message: 'Review the Terraform plan below. Apply exactly this plan?', ok: 'Apply',
                              parameters: [text(name: 'PlanSummary', defaultValue: shown,
                                                description: 'Terraform plan (read-only, for review). Changing this text does NOT change what is applied.')]
                    }
                }
                stash name: 'tfplan-artifact-2', includes: 'infra/terraform/tfplan,infra/terraform/tfplan.txt,infra/terraform/.terraform.lock.hcl'
            }
        }
        stage('Terraform Apply') {
            when {
                beforeAgent true
                expression { !params.SKIP_IAC }
            }
            agent { label 'linux-build' }
            steps {
                sh 'rm -f infra/terraform/tfplan infra/terraform/tf-outputs.json'
                unstash 'tfplan-artifact-2'
                dir('infra/terraform') {
                    // apply consumes the reviewed plan file: no new plan is computed after approval
                    sh '''
                        terraform init -no-color
                        terraform apply -no-color tfplan
                        terraform output -json > tf-outputs.json
                        echo "===== terraform output ====="
                        terraform output -no-color
                    '''
                }
                archiveArtifacts artifacts: 'infra/terraform/tf-outputs.json'
            }
        }
        stage('Configure with Ansible') {
            when {
                beforeAgent true
                expression { !params.SKIP_IAC }
            }
            agent { label 'linux-build' }
            steps {
                // dynamic_inventory.sh reads `terraform output`, which needs an initialised backend in THIS workspace
                dir('infra/terraform') {
                    sh 'terraform init -no-color'
                }
                sh 'bash infra/ansible/inventory/dynamic_inventory.sh'
                dir('infra/ansible') {
                    sh "ansible-playbook -i inventory/hosts.ini playbook.yml -e image_tag=${env.SHORT_SHA}"
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
        stage('Pipeline Health Gate') {
            agent { label 'linux-build' }
            steps {
                script {
                    // Builds that succeeded / finished in the last HEALTH_WINDOW, from Prometheus (Lab 09);
                    // the query and why it is not rate()/increase() are documented in scripts/health_gate.py.
                    // A Prometheus outage makes that script exit non-zero, which fails this stage (never a silent pass).
                    def result = sh(returnStdout: true, script: 'python3 scripts/health_gate.py').trim()
                    def line = result.readLines().find { it.startsWith('HEALTH ') }
                    if (line == null) {
                        error("Pipeline Health Gate: could not read the success rate from Prometheus. Output: ${result}")
                    }
                    echo "Prometheus: ${env.PROM_URL}  job: ${env.JOB_NAME}  window: ${env.HEALTH_WINDOW}  threshold: ${env.HEALTH_THRESHOLD}%"
                    echo line
                    if (line.contains('status=nodata')) {
                        // Not treated as 100%: there is simply nothing to measure. Blocking here would deadlock the
                        // pipeline once the window has emptied (every blocked build adds a failure, nothing can recover).
                        echo "WARNING: no completed builds in the last ${env.HEALTH_WINDOW}; success rate unknown -> gate PASSES without health evidence"
                    } else {
                        def rate = line.split('rate=')[1].trim() as BigDecimal
                        echo "Rolling build success rate: ${rate}%  (threshold ${env.HEALTH_THRESHOLD}%)"
                        if (rate < (env.HEALTH_THRESHOLD as BigDecimal)) {
                            error("Pipeline Health Gate BLOCKED: success rate ${rate}% is below the ${env.HEALTH_THRESHOLD}% threshold - Deploy — Production will not run")
                        }
                        echo "Pipeline Health Gate PASSED: ${rate}% >= ${env.HEALTH_THRESHOLD}%"
                    }
                }
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
