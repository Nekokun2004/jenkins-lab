---
name: cicd-verify-loop
description: Use whenever you change the Jenkinsfile, a stage command, a scanner image, docker-compose.yml or anything a Jenkins build executes. Reproduce every stage locally on the real agent (jenkins-agent-linux-build) and verify independently BEFORE pushing, so one Build Now goes green instead of push -> fail -> fix -> push loops.
---

# CI/CD local verification loop

Goal: exactly **one** real Jenkins build per change set. Every bug found by a Jenkins build that a local
reproduction could have caught is a process failure. Work autonomously; report only when the whole local
run is green or when a step is risky/irreversible (needs `sudo`, deletes user data, force-push, etc.).

## The loop

1. **Read the checklist below first.** Check every stage's commands against it *before* running anything.
   Sweep the whole Jenkinsfile (`grep`) for a bug class once you know it; never fix it one stage at a time.
2. **Reproduce each stage locally, in Jenkins order, on the real agent.** Same image, same `-u`, same
   mounts, same working directory, same shared state (stash/unstash = copy files between steps; the agent
   workspace is persistent across builds). Extract the shell snippets from the Jenkinsfile programmatically
   so you test the text Jenkins will run, not a retyped copy: `python3 .claude/skills/cicd-verify-loop/verify-loop.py`.
3. **Per stage:** run it, capture output + exit code. On failure: state a hypothesis, apply the *minimal*
   fix, re-run the **same** command (not a new one).
4. **Verify from outside the command's own session.** A separate `docker exec jenkins-agent-linux-build ls/stat/cat`
   (existence, owner, size, content). Never accept exit code 0 alone: Docker reported success while writing
   to a phantom host directory, and `archiveArtifacts allowEmptyArchive: true` hides missing files.
5. **Run the whole sequence twice.** Pass 2 runs in the *same* workspace and catches stale-state bugs
   (files left by pass 1, root-owned leftovers, "already exists" prompts). Real Jenkins reuses workspaces.
6. **Only when every stage passes in full sequence:** one commit, one push, then ask the user to press
   Build Now **once**.
7. **If the real build still fails** for something the local run missed: diagnose it yourself with this same
   procedure, add a new entry to the checklist below (same terse format), improve `verify-loop.py` so it
   would have caught it, and resume from step 1 for that stage. Do not wait for the user to diagnose.
8. Things that cannot be reproduced locally (say so explicitly in the report, do not claim green):
   `withSonarQubeEnv`/`waitForQualityGate` (would publish a real analysis), `junit`/`publishCoverage`/
   `archiveArtifacts` plugin steps, `when { branch }` (multibranch only), `input`. Verify their prerequisites
   (tool present, server UP, input files exist) instead.

## Known Docker / Jenkins-agent quirks (check BEFORE a stage fails)

Add a new entry every time you discover one. Terse: symptom -> cause -> rule.

- **`apk add` in `node:20-alpine`** -> `Unable to open log: Permission denied` -> Jenkins runs the container as
  `-u 1000:1000`; apk needs root. Use `args '-u root'` on that stage's agent.
- **`anchore/syft:latest` has no `/etc/passwd`** -> `-u root` fails (`unable to find user root`), and uid 1000
  has no HOME (Go falls back to `/`, unwritable: `unable to create report file`). Use numeric `-u 0:0`.
- **syft, cosign, opa images are shell-less (distroless/scratch)** -> `docker.image().inside { sh }` cannot work
  (no `/bin/sh`). Use a raw `docker run ... <image> <args>` from the agent's own shell instead.
- **Raw `docker run` needing the real workspace** -> MUST be `--volumes-from jenkins-agent-linux-build -w "$WORKSPACE"`.
  NEVER `-v $WORKSPACE:/x` or `-v /home/jenkins/agent/workspace/...:/x`: the agent talks to the *host* dockerd via
  docker.sock (Docker-outside-of-Docker), the path only exists in the agent's named volume, and Docker silently
  creates an empty phantom directory on the host. Symptom: exit 0, output missing, `stash` fails, `archiveArtifacts` doesn't.
  Same class as the Lab 05 `schema.sql` bind mount (bake files into the image instead).
- **`$(hostname)` in the agent is not the container id** (it is `wasugree`). Use the stable container name
  `jenkins-agent-linux-build`. (Agent label `linux-build` != Docker container name.)
- **Files created as root** (any `-u 0:0` / `-u root` stage) -> hand them back before the stage ends. Inside a root
  Jenkins container: `chown "$(stat -c '%u:%g' .)" <file>`. From the agent's own (non-root) shell a bare
  `sh 'chown ...'` FAILS (`Operation not permitted`): run it in a root container:
  `docker run --rm -u 0:0 --volumes-from jenkins-agent-linux-build -w "$WORKSPACE" node:20-alpine chown -R "$(id -u):$(id -g)" .`
- **Persistent workspace** -> commands that refuse to overwrite (`cosign generate-key-pair`: `File cosign.key already
  exists. Overwrite?` -> `user declined the prompt`) hit last build's files. Make every producer idempotent:
  `rm -f` its outputs first.
- **`docker run -u A -u B`: the last `-u` wins.** Jenkins injects `-u 1000:1000` first, so extra args like
  `.inside('-u 0:0')` correctly override it.
- **`agent none` at pipeline level** -> every leaf stage (including leaves inside `parallel`) needs its own `agent`;
  a parent stage that contains `parallel` must not have one. Same family as JENKINS-30600.
- **`unstash` of a missing stash** throws a raw `AbortException` that masks the real upstream failure. Wrap in
  try/catch and let the next step that needs the file fail with the accurate error.
- **`openpolicyagent/opa:latest` is OPA 1.x (Rego v1)**: rules need `import rego.v1`, `contains`, `if`. Classic
  `deny[msg] { ... }` does not parse. `opa eval -f raw` prints `[]` when nothing is denied.
- **Playwright**: the docker image tag must equal the installed `@playwright/test` version (check `package-lock.json`).
- **docker-compose host ports** (`ports: "5432:5432"`) collide between concurrent builds on this 2-executor agent.
  Publish only what the test client needs (`8081`), never the db.
- **SonarQube `coverage` gate is blended** (lines + branches), not Jest's line %. Exclude bootstrap/DB-only files via
  `collectCoverageFrom` negations and document why in README.
- **`npm audit`** needs only `package.json` + `package-lock.json`; no `npm ci` (which would also create node_modules).
- **cosign `sign-blob`** uploads to the public Rekor log unless `--tlog-upload=false` (needs internet, public record).
- **`sudo` needs a password** in this environment: never try; ask the user to run it with the `!` prefix.
- **Local `docker compose` reads `./.env`**: a malformed line breaks every compose command. `.env` is git-ignored and
  holds real tokens: never commit or print it; never `git add .` (generated `cosign.key`, reports are in `.gitignore`).
- **Generated secrets left in the persistent workspace get flagged by the next build's Secrets Detection**
  (found only on pass 2: gitleaks `private-key` on the leftover `cosign.key`). Delete throwaway key material at
  the end of the stage that made it (`post { always { sh 'rm -f cosign.key' } }`), and archive only the public half.
- **Two Jenkins jobs build the same branch** (`taskflow-pipeline` and multibranch `taskflow-multibranch`, lab06
  workspaces exist for both). Overlapping runs collide on host port 8081 (E2E) and starve the 2 executors. Let one
  build finish before starting another; never press Build Now on both.
- **`sh(returnStdout: true)` captures stdout only**, so tools that print notices to stderr (`npm notice`) are safe in
  the pipeline; the harness must not merge stderr when it parses such a value (use an `echo KEY=...` marker).
- **Pipeline `timeout(10 min)` covers the whole run** including image pulls, 12 per-stage checkouts and Semgrep rule
  downloads. Measured (images cached): ~150 s of stage commands per full run, ~4-5 min expected in Jenkins. Re-measure
  with `verify-loop.py` when adding stages; raise the timeout if the estimate passes ~5 min.
- **Never `pkill -f <name>` from a shell whose own command line contains `<name>`** (it kills itself): kill by PID.

## Files

- `verify-loop.py`: the harness (extracts snippets from `Jenkinsfile`, runs them on the agent, verifies independently,
  two passes). Usage: `python3 .claude/skills/cicd-verify-loop/verify-loop.py [passes]`. Extend it when you add a stage.
