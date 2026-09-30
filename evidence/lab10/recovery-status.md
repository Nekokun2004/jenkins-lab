# Lab 10 recovery status (no secrets)

## Checkpoint 1 - 2026-10-01 ~02:55 +07 (after reboot audit)
- Runtime: all lab containers up; `sonarqube` was Exited(255) after reboot -> `docker start sonarqube` (not recreated).
- API repo `/home/nekup/Documents/selfproject/jenkins-lab`, branch `lab10`, commit `3ca7466` ("feat: integrate Lab 10 capstone pipeline"),
  already pushed (origin/lab10 == HEAD). Working tree clean except untracked `manual_lab/lab10/`.
- Step 1 VERIFIED (evidence/lab10/step1-secrets-check.txt, re-grep done, all matches safe).
- Step 2 structure VERIFIED (Fast Checks parallel: Lint, Unit Test, Secrets Detection, SAST[ESLint->Semgrep], SCA); verify-loop re-run in progress.
- Step 7 docs present (docs/architecture.md, docs/rollback-runbook.md; Service taskflow, Deployments taskflow-blue/green).
- Step 6 implemented (scripts/health_gate.py + 'Pipeline Health Gate' stage, SKIP_IAC default false); runtime block NOT yet proven.
- Temp repo `/home/nekup/Documents/selfproject/taskflow_mobile`: no git remote present; kept as reference.
- Real mobile repo cloned to `/home/nekup/Documents/selfproject/subscription_track` (read access OK). NOTE real paths are
  `apps/mobile` (Flutter) and `apps/server` (NestJS), not `app/...`. Branch `lab10-mobile-pipeline` created from develop (c19bfad).
- Ported: android signing (build.gradle.kts env-based), gradle.properties heap, `Jenkinsfile.mobile` (repo root, uses dir('apps/mobile')).
- Lab keystore: ~/.config/lab10/lab10-release.keystore valid (alias lab10key, CN=Lab10).
- Next action: finish local mobile build (evidence/lab10/mobile-local-build.log), verify APK/AAB, commit+push mobile branch.

## Checkpoint 2 - 2026-10-01 ~03:10 +07
- Mobile LOCAL build GREEN (evidence/lab10/mobile-local-build.log): pub get, analyze (no issues), 44 tests pass, osv-scanner clean,
  debug APK 150975150 B, release AAB 50852818 B; `keytool -printcert -jarfile` shows signer CN=Lab10 (signed with lab key).
- Mobile committed 55ad627 and pushed to origin/lab10-mobile-pipeline (nawaphonST1/subscription_track). Write access confirmed.
  Files: Jenkinsfile.mobile (Script Path), apps/mobile/android/app/build.gradle.kts, apps/mobile/android/gradle.properties.
  apps/mobile/pubspec.lock modified by pub get locally - intentionally NOT committed.
- BLOCKED: Claude-in-Chrome extension not connected (Chrome not running). Jenkins UI work pending.
- API verify-loop (2 passes) still running in background: log /tmp/claude-1000/verify-step2.log
- Next action: (1) connect Chrome, (2) create Jenkins creds android-keystore (file ~/.config/lab10/lab10-release.keystore),
  android-keystore-password, android-key-alias (=lab10key), (3) job taskflow-mobile-pipeline -> repo above, branch */lab10-mobile-pipeline,
  script path Jenkinsfile.mobile, run it; (4) taskflow-pipeline branch -> */lab10; (5) Step 6 block proof with SKIP_IAC=true.

## Checkpoint 3 - 2026-10-01 ~03:25 +07
- Step 2 verify-loop run 1 (log: evidence/lab10/step2-verify-loop-run1.log): 27/28. Pass 1 = 13/14 (E2E: verify-loop-db-1 unhealthy on cold
  start, overlapped with my Flutter build; E2E stage not changed by Lab 10). Pass 2 = 14/14. Clean re-run started -> /tmp/claude-1000/verify-step2-run2.log
- Browser: Claude extension (fcoeoabgfenejglbffodgkkbkcdhcgfn) is installed ONLY in the Flatpak Chrome (~/.var/app/com.google.Chrome);
  the regular /opt/google/chrome profiles (Default, Profile 1) do not have it, and the Flatpak native-messaging dir is empty. Not connected.
- Next action: install/enable the Claude extension in regular Chrome (signed into claude.ai), then Jenkins creds, mobile job, API job branch, Step 6 proof.

## Checkpoint 4 - 2026-10-01 ~03:40 +07 (final audit run)
- Step 2 VERIFIED: clean verify-loop re-run 28/28 (pass 1 14/14, pass 2 14/14) -> evidence/lab10/step2-verify-loop-run2-clean.log.
  (run 1 = 27/28, E2E postgres cold-start unhealthy while a Flutter build ran concurrently: step2-verify-loop-run1.log). git diff --check clean.
- Steps 1, 3, 7 re-verified from disk. Mobile artifacts re-checked (APK 150975150 B, AAB 50852818 B, signer CN=Lab10). No keystore tracked.
- apps/mobile/pubspec.lock drift (container SDK downgraded transitive deps) restored with `git restore` on that one file; mobile tree clean.
- Health Gate code reviewed: stage at Jenkinsfile:657, before Deploy — Production (:686); threshold 90; SKIP_IAC default false, guards only the 6 IaC stages.
- BLOCKED (manual): Claude-in-Chrome extension not installed in regular Chrome -> Step 4 (credentials), Step 5 (mobile job + green build), Step 6 (runtime block proof) NOT done.
- Next action: install Claude extension in regular Chrome, then run Steps 4 -> 5 -> job branch */lab10 -> Step 6 proof.

## Checkpoint 5 - 2026-10-01 ~04:25 +07
- Step 2 VERIFIED: clean verify-loop 28/28 (evidence/lab10/step2-verify-loop-run2-clean.log).
- Step 6 RUNTIME PROVEN: taskflow-pipeline now on */lab10. Build #60 (IaC failed: LocalStack bucket taskflow-tfstate missing after reboot; SKIP_IAC not yet
  registered on first run) = failed datapoint. Real-data bug found+fixed: missing success counter was read as nodata -> commit 8cebc6e (pushed to origin/lab10).
  Build #61 (SKIP_IAC=true): reached Pipeline Health Gate, measured 0.0% < 90%, BLOCKED; Deploy — Production not executed.
  Evidence: pipeline-health-gate-block.txt/.jpg, api-build-60-console.txt. Prometheus: total=2, success series absent.
- Step 4 PARTIAL: android-key-alias created. android-keystore (Secret file) and android-keystore-password (Secret text) MISSING - need the user:
  file upload tool cannot read ~/.config/lab10 (needs /add-dir), and a password is not typed into forms by the assistant.
- Step 5 PARTIAL: job taskflow-mobile-pipeline created (repo nawaphonST1/subscription_track, */lab10-mobile-pipeline, Jenkinsfile.mobile).
  Build #1 FAILURE as expected: Analyze PASS, Test PASS (44), SCA PASS, Debug APK PASS (150975878 B), Signed AAB stage: "Could not find credentials entry with ID 'android-keystore'".
  Evidence: mobile-pipeline-build1-missing-credentials-console.txt.
- Next action: user adds the 2 credentials -> assistant runs build #2, verifies artifacts (APK+AAB), saves mobile-pipeline-console.txt + mobile-pipeline-green.jpg.

## Checkpoint 6 - CLI-only mode (no browser, no Monitor)
- Step 6 evidence re-verified from disk (#61, success=0 total=1 rate=0.0, threshold 90%, BLOCKED, Deploy — Production not run). Step 6 stays PASS.
- Runtime: jenkins, agent, prometheus, sonarqube, kind, registry UP. grafana + localstack Exited(0) ~13 min before this checkpoint (not stopped by the assistant; left stopped, RAM tight).
  NOTE: LocalStack is only needed for the IaC stages (skipped with SKIP_IAC=true); Grafana state preserved in its volume.
- Jenkins CLI: host Java is 8 (CLI needs 17+) -> run the CLI inside the jenkins container (JDK 21); jar copied to jenkins:/tmp/jenkins-cli.jar (delete at the end).
  Anonymous CLI = HTTP 403. No JENKINS_* env vars, no ~/.config/jenkins-lab auth file.
- BLOCKED at the CLI-only auth checkpoint: need ~/.config/jenkins-lab/jenkins.auth (user:api-token) and ~/.config/jenkins-lab/keystore.pass (lab keystore password), created by the user with `read -s`.
- Next action: after the user says "continue": who-am-i, credential IDs check, create android-keystore (Secret file) + android-keystore-password (Secret text), run mobile build #2 via CLI, verify artifacts.

## Checkpoint 7 - auth file rejected
- ~/.config/jenkins-lab/jenkins.auth exists (600) but Jenkins returns 401 for CLI and REST (whoAmI). Username stored is not a Jenkins user
  (Jenkins users: nead, nedev, netiwut2004, aiagent); the same token also fails as nead/netiwut2004/nedev. Token shape is valid (34 chars).
- Temp copy of the auth file removed from the controller. keystore.pass exists (600), not yet used.
- Next action: user re-creates jenkins.auth with the correct username + a valid API token (see self-test command), then "continue".

## Checkpoint 8 - FINAL (CLI-only, 2026-10-01 ~05:15 +07)
- Jenkins auth fixed by user (authenticated as NeAd). Jenkins CLI run inside controller with `-http` (websocket mode rejected: "Unexpected request origin").
- Step 4 PASS: created android-keystore (Secret file) + android-keystore-password (Secret text) via CLI groovy; reused android-key-alias. No values printed;
  temp keystore/password/auth copies removed from the controller (verified 0 leftovers).
- Step 5 PASS: taskflow-mobile-pipeline #3 SUCCESS (console: evidence/lab10/mobile-pipeline-console.txt; #2 also SUCCESS - from an interrupted first attempt).
  Analyze PASS, Test 44 PASS, SCA clean, Debug APK PASS, Signed AAB PASS (signer CN=Lab10, re-verified on the AAB downloaded from Jenkins).
  Artifacts: apps/mobile/build/app/outputs/flutter-apk/app-debug.apk (150975878 B), .../bundle/release/app-release.aab (50852827 B), aab-signer.txt, coverage/lcov.info.
- Steps 1-7 COMPLETE. Git: API lab10 @ 8cebc6e pushed; mobile lab10-mobile-pipeline @ 55ad627 pushed; nothing tracked that shouldn't be.
- Manual: screenshot of taskflow-mobile-pipeline #3 (Stage View, green) still to be taken by the user.
- Grafana + localstack were stopped (not by the assistant) and left stopped; start them before Step 8 if needed (localstack is needed for IaC stages, Grafana for dashboards).
- Next action: Step 8 - Live Demo (NOT started).

## Checkpoint 9 - Health Gate changed to "last 20 builds" (2026-10-01 ~06:00 +07)
- Requirement: rolling success rate over the LAST 20 BUILDS < 90% aborts deploy. Old gate (1h Prometheus window, commit 8cebc6e) did not match.
- Prometheus cannot provide it (counters restart with Jenkins, no per-build data: total=2 vs 61 builds in history) -> gate now reads the job's own
  Jenkins build history (last 20 completed; ABORTED/running skipped; <20 -> "N builds available out of 20"; 0 -> explicit no-data warning). Threshold 90%.
  NOTE: deviates from the lab text example (Prometheus query) - must be explained in the report.
- Commit bb54b7f pushed to origin/lab10 (Jenkinsfile, scripts/health_gate.py, docs/architecture.md, docs/rollback-runbook.md). HEALTH_WINDOW param + PROM_URL removed.
- Verified: declarative linter OK, edge cases OK, real-history calc == Jenkinsfile's list.
- PROOF build taskflow-pipeline #62 (SKIP_IAC=true, DEPLOY_FAULT=none): 20 of 20 builds, 6 success, 30.0% < 90% -> Pipeline Health Gate BLOCKED; Deploy — Production did not run.
  Evidence: pipeline-health-gate-block.txt (new), api-build-62-console.txt. Superseded v1 (#61, 1h window) kept as *-v1-1h-window.txt/.jpg.
- Screenshot for #62 NOT taken (CLI-only mode): MANUAL SCREENSHOT REQUIRED - Jenkins -> taskflow-pipeline -> #62 -> Console Output (bottom) showing the BLOCKED line.
- Jenkins auth/CLI temp files removed from the controller. Queue empty. Step 8 not started.
