# Rollback Runbook - taskflow-api deploy failure

Names used below come from `k8s/` and the `Jenkinsfile`: Service **`taskflow`** (port 8080, selector
`app=taskflow` + `color=blue|green`), Deployments **`taskflow-blue`** / **`taskflow-green`**, per-colour Services
`taskflow-blue` / `taskflow-green`, health endpoint **`/health`**. `kubectl` lives in the agent container with
`KUBECONFIG=/home/jenkins/.kube/config`, so run the commands like this (or `kubectl` directly on a machine with the kubeconfig):

```bash
K="docker exec jenkins-agent-linux-build kubectl"
```

## 1. Find the failed build and stage
Jenkins -> `taskflow-pipeline` -> the red build -> **Stages** (or *Console Output*, search for the last `[Pipeline] { (<stage>)`).
Note the build number and stage name; save the console log (*Console Output -> Download* or
`docker exec jenkins cat /var/jenkins_home/jobs/taskflow-pipeline/builds/<N>/log > build-<N>.log`).

| Failed stage | Traffic affected? | Action |
|---|---|---|
| anything before `Blue/Green Deploy` | No - Service was never touched | Fix and re-run; no rollback |
| `Blue/Green Deploy` | Possibly | Steps 2-5 |
| `Pipeline Health Gate` | No - it blocks *before* `Deploy — Production`; Blue/Green already succeeded | See step 7 |
| `Terraform Apply` / `Configure with Ansible` | No (infra only) | Do not re-approve blindly; `terraform show`, then fix |

## 2. Check which colour is live
```bash
$K get svc taskflow -o jsonpath='{.spec.selector.color}{"\n"}'
```

## 3. What the pipeline already does (automatic rollback)
`Blue/Green Deploy` records the live colour in `.lab07-previous-color` (and `env.PREV_COLOR`), deploys the image to the
**inactive** colour, smoke-tests it through `Service/taskflow-<color>`, and only then patches `Service/taskflow`.
If the stage fails (rollout timeout, failed smoke test, failed post-switch check) its `post { failure }` block patches the
selector back to the recorded colour, runs `kubectl rollout undo deployment/taskflow-<failed colour>`, and exits non-zero unless the
selector really equals the previous colour. Expect `Rollback complete. Active color: <previous>.` in the console.
If the failure happened *before* the colour was recorded it prints `Nothing to roll back` - the Service was never touched.

## 4. Manual rollback (auto-rollback did not run or did not restore the colour)
Pick the previously healthy colour (from `.lab07-previous-color` in the job workspace, or the build log line `Current active color:`):
```bash
docker exec jenkins-agent-linux-build cat /home/jenkins/agent/workspace/taskflow-pipeline/.lab07-previous-color   # may be stale - confirm with the log
PREV=blue      # <- the previously healthy colour
$K patch svc taskflow --type merge -p "{\"spec\":{\"selector\":{\"app\":\"taskflow\",\"color\":\"$PREV\"}}}"
```
(A merge patch on `color` alone also works; keeping `app` matches what the pipeline sends.)

## 5. Verify
```bash
$K get svc taskflow -o jsonpath='{.spec.selector.color}{"\n"}'          # == $PREV
$K rollout status deployment/taskflow-$PREV --timeout=60s               # successfully rolled out
$K get pods -l app=taskflow,color=$PREV                                  # all 1/1 Running
$K get endpointslices -l kubernetes.io/service-name=taskflow -o wide     # addresses are the $PREV pods
$K run verify-rb --rm -i --restart=Never --image=curlimages/curl:8.10.1 --command -- \
    curl -fsS --max-time 5 http://taskflow:8080/health                   # {"status":"ok",...}
```
If the failed colour is left on a bad revision: `$K rollout undo deployment/taskflow-<failed colour>` (it takes no traffic).

## 6. Preserve evidence and tell people
Keep: the build log, `$K get svc taskflow -o yaml`, `$K describe pods -l color=<failed colour>`, `$K logs deployment/taskflow-<failed colour>`,
the Grafana *Jenkins Pipeline SLO* dashboard. Post in the team channel (Slack/e-mail - not wired up in this lab, so do it by hand):
build link, failed stage, live colour now, who is investigating.

## 7. Before retrying a deployment
- Open an incident ticket with the evidence above; do not re-run until the root cause is named.
- Re-run only after the fix is merged; one build at a time (`disableConcurrentBuilds()` is on, never start two by hand).
- Never approve `Terraform Apply` just to "get further" - review the plan.
- If the `Pipeline Health Gate` blocked: its console shows the measured success rate. Fix the failing builds; the gate
  re-opens by itself once the failures age out of the window (`HEALTH_WINDOW`, default 1h) or enough successful builds
  lift the rate to 90%. It is not bypassed by editing the threshold.
