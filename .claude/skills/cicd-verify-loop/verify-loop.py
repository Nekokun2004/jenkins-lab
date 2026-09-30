#!/usr/bin/env python3
"""Local reproduction of the Jenkinsfile on the real agent (jenkins-agent-linux-build).

Shell snippets are extracted verbatim from the Jenkinsfile; each stage runs in the same
container context Jenkins would give it; every result is verified by a SEPARATE docker exec.
Runs the whole sequence N times (default 2) in ONE persistent workspace, so pass 2 catches
stale-state bugs exactly like a second real build would.

Usage (from anywhere in the repo):  python3 .claude/skills/cicd-verify-loop/verify-loop.py [passes] [--keep] [--lab07|--lab08|--lab10]
--lab08 runs only the IaC stages against LocalStack, using a throwaway state key (never the real one).
Not reproducible locally (verify prerequisites only): withSonarQubeEnv/waitForQualityGate,
junit/publishCoverage/archiveArtifacts, `when { branch }`, `input`.
When you add or change a stage, extend the matching @stage function below.
"""
import json, os, re, subprocess, sys, time

AGENT = "jenkins-agent-linux-build"
WS = "/home/jenkins/agent/workspace/verify-loop"
ROOT = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
JF = os.path.join(ROOT, "Jenkinsfile")
results = []


def sh(cmd, inp=None, timeout=900):
    p = subprocess.run(cmd, input=inp, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)


def agent_exec(script, env=None, cwd=None):
    """Run a shell script in the agent's own shell (what a plain `sh` step does).
    `env` = extra environment a Jenkins `env.X = ...` / `environment {}` block would export.
    `cwd` = subdirectory of the workspace, like a `dir('...')` block."""
    cmd = ["docker", "exec", "-i", "-e", f"WORKSPACE={WS}"]
    for k, v in (env or {}).items():
        cmd += ["-e", f"{k}={v}"]
    cmd += ["-w", f"{WS}/{cwd}" if cwd else WS, AGENT, "sh", "-s"]
    return sh(cmd, inp=script)


def agent_check(script):
    """Independent verification: a separate docker exec, unrelated to the tested command."""
    return sh(["docker", "exec", AGENT, "sh", "-c", script])


def container_run(image, user, snippet, entrypoint_empty=False, extra=()):
    """Jenkins docker.inside()/agent{docker{}} equivalent: -u <agent uid> then user args, --volumes-from agent."""
    cmd = ["docker", "run", "--rm", "-i", "-u", "1000:1000", "--volumes-from", AGENT, "-w", WS]
    cmd += ["-u", user] if user != "1000:1000" else []
    cmd += list(extra)
    if entrypoint_empty:
        cmd += ["--entrypoint", ""]
    cmd += [image, "sh", "-s"]
    return sh(cmd, inp=snippet)


# ---------------------------------------------------------------- Jenkinsfile extraction
def strip_comments(t):
    return "\n".join(l for l in t.split("\n") if not l.strip().startswith("//"))


def stage_body(name):
    t = strip_comments(open(JF).read())
    i = t.index(f"stage('{name}')")
    j = t.index("{", i)
    d, k = 0, j
    while True:
        if t[k] == "{": d += 1
        elif t[k] == "}":
            d -= 1
            if d == 0: break
        k += 1
    return t[j:k + 1]


SNIP = re.compile(
    r"\bsh\s*'''(?P<blk>.*?)'''"
    r"|\bsh\s*'(?P<one>(?:[^'\\]|\\.)*)'"
    r"|script:\s*'(?P<scr>(?:[^'\\]|\\.)*)'"
    r"|script:\s*\"(?P<dq>(?:[^\"\\]|\\.)*)\""
    r"|\bsh\s*\"(?P<gs>(?:[^\"\\]|\\.)*)\"", re.S)


def snippets(name):
    body = stage_body(name)
    out = []
    for m in SNIP.finditer(body):
        if m.group("blk") is not None:
            import textwrap
            out.append(textwrap.dedent(m.group("blk")).strip("\n"))
        else:
            s = next(m.group(g) for g in ("one", "scr", "dq", "gs") if m.group(g) is not None)
            s = s.replace("\\'", "'")
            # Groovy GString ${env.X} -> shell $X (the harness exports the same variable)
            out.append(re.sub(r"\$\{env\.(\w+)\}", r"$\1", s))
    return out


# ---------------------------------------------------------------- reporting
def record(stage, ok, detail, secs):
    results.append((stage, ok, secs))
    flag = "PASS" if ok else "FAIL"
    print(f"[{flag}] {stage:<28} {secs:6.1f}s  {detail}", flush=True)
    return ok


def must(cond, msg):
    if not cond:
        raise AssertionError(msg)


def stage(name):
    def deco(fn):
        def run():
            t0 = time.time()
            try:
                detail = fn() or ""
                return record(name, True, detail, time.time() - t0)
            except Exception as e:  # noqa
                return record(name, False, f"{type(e).__name__}: {e}", time.time() - t0)
        return run
    return deco


def owner_ok(path):
    rc, o = agent_check(f"stat -c '%u:%g' {WS}/{path}")
    must(rc == 0, f"{path} missing (independent check): {o.strip()}")
    must(o.strip() == "1000:1000", f"{path} owned by {o.strip()}, expected 1000:1000")


def json_ok(path):
    rc, o = agent_check(f"cat {WS}/{path}")
    must(rc == 0, f"cannot read {path}: {o.strip()}")
    return json.loads(o)


# ---------------------------------------------------------------- stages
@stage("Install")
def st_install():
    for s in snippets("Install"):
        rc, o = container_run("node:20-alpine", "1000:1000", s)
        must(rc == 0, o[-400:])
    rc, o = agent_check(f"test -x {WS}/node_modules/.bin/eslint && stat -c '%u:%g' {WS}/node_modules")
    must(rc == 0 and "1000:1000" in o, f"node_modules check: {o.strip()}")
    return "node_modules present, uid 1000"


@stage("Secrets Detection")
def st_secrets():
    ss = snippets("Secrets Detection")
    must(len(ss) == 1, f"expected 1 snippet, got {len(ss)}")
    rc, o = container_run("zricethezav/gitleaks:latest", "0:0", ss[0], entrypoint_empty=True)
    must(rc == 0, o[-400:])
    owner_ok("gitleaks-report.json")
    rep = json_ok("gitleaks-report.json")
    must(isinstance(rep, list), "report is not a JSON list")
    return f"report ok ({len(rep)} findings), owner 1000:1000"


@stage("SAST / ESLint Security")
def st_eslint():
    for s in snippets("ESLint Security"):
        rc, o = container_run("node:20-alpine", "1000:1000", s)
        must(rc == 0, o[-400:])
    owner_ok("eslint-report.sarif")
    rep = json_ok("eslint-report.sarif")
    must("runs" in rep, "no SARIF runs")
    return "sarif ok, owner 1000:1000"


@stage("SAST / Semgrep")
def st_semgrep():
    ss = snippets("Semgrep")
    must(len(ss) == 1, f"expected 1 snippet, got {len(ss)}")
    rc, o = container_run("semgrep/semgrep:latest", "0:0", ss[0])
    must(rc == 0, o[-400:])
    owner_ok("semgrep-report.sarif")
    rep = json_ok("semgrep-report.sarif")
    must("runs" in rep, "no SARIF runs")
    return "sarif ok, owner 1000:1000"


@stage("SCA — npm audit")
def st_sca():
    ss = snippets("SCA — npm audit")
    # snippets: apk add, npm audit, chown, jq(critical)
    must(len(ss) == 4, f"expected 4 snippets, got {len(ss)}: {ss}")
    # each `sh` step is its own shell in the same root container; run them in one container
    # to keep apk's install (as Jenkins' long-lived sidecar does), joined as separate steps
    script = "\n".join(ss[:3])
    rc, o = container_run("node:20-alpine", "root", script + "\n" + ss[3] + " > /tmp/critical.txt\necho CRITICAL=$(cat /tmp/critical.txt)")
    must(rc == 0, o[-400:])
    mm = re.search(r"CRITICAL=(\d+)", o)  # Groovy: sh(returnStdout).trim().toInteger() sees stdout only
    must(mm, "jq output not an integer: " + o[-200:])
    critical = int(mm.group(1))
    owner_ok("audit.json")
    a = json_ok("audit.json")
    must(a["metadata"]["vulnerabilities"]["critical"] == critical, "jq value != audit.json")
    agent_check(f"cp {WS}/audit.json /tmp/stash-audit-report.json")  # stash simulation
    return f"critical={critical} (SCA {'passes' if critical == 0 else 'BLOCKS'}), owner 1000:1000"


@stage("Generate SBOM")
def st_sbom():
    ss = snippets("Generate SBOM")
    for s in ss:
        rc, o = agent_exec(s)
        must(rc == 0, f"snippet failed: {s[:80]!r}\n{o[-400:]}")
    for f in ("taskflow-api.cdx.json", "taskflow-api.cdx.json.sig", "cosign.pub"):
        owner_ok(f)
    rc, o = agent_check(f"test ! -e {WS}/cosign.key && echo gone")
    must("gone" in o, "cosign.key still in workspace after post cleanup")
    sbom = json_ok("taskflow-api.cdx.json")
    must(len(sbom.get("components", [])) > 50, "SBOM has too few components")
    rc, o = agent_check(f"wc -c < {WS}/taskflow-api.cdx.json.sig")
    must(int(o.strip()) > 20, "signature empty")
    # verify the signature really validates against the SBOM with the generated public key
    rc, o = sh(["docker", "run", "--rm", "-u", "0:0", "--volumes-from", AGENT, "-w", WS,
                "ghcr.io/sigstore/cosign/cosign:v2.4.1", "verify-blob", "--key", "cosign.pub",
                "--signature", "taskflow-api.cdx.json.sig", "--insecure-ignore-tlog=true",
                "taskflow-api.cdx.json"])
    must(rc == 0 and "Verified OK" in o, f"verify-blob: {o[-300:]}")
    agent_check(f"cp {WS}/taskflow-api.cdx.json /tmp/stash-sbom-report.json")
    return f"{len(sbom['components'])} components, signature verified, sbom/sig/pub owner 1000:1000, cosign.key removed"


@stage("Policy Gate")
def st_policy():
    ss = snippets("Policy Gate")
    must(len(ss) == 1, f"expected 1 snippet, got {len(ss)}: {ss}")
    # unstash simulation as uid 1000 over whatever is in the workspace (collision test)
    rc, o = agent_check(f"cp /tmp/stash-audit-report.json {WS}/audit.json")
    must(rc == 0, f"unstash simulation failed (stale file collision?): {o.strip()}")
    rc, o = agent_exec(ss[0])
    must(rc == 0, o[-300:])
    result = o.strip()
    must(result == "[]", f"expected '[]' for a clean audit, got {result!r}")
    # blocking path: fake audit.json with critical=1 (Fix 5 format)
    agent_check(f"echo '{{\"metadata\":{{\"vulnerabilities\":{{\"critical\":1}}}}}}' > {WS}/audit.json")
    rc, o = agent_exec(ss[0])
    blocked = o.strip()
    must(rc == 0 and blocked not in ("[]", "") and "Blocked: 1 CRITICAL" in blocked, f"block path: {blocked!r}")
    agent_check(f"cp /tmp/stash-audit-report.json {WS}/audit.json")  # restore
    return f"clean -> '[]' (pass); critical=1 -> {blocked}"


@stage("Checks / Lint")
def st_lint():
    for s in snippets("Lint"):
        rc, o = container_run("node:20-alpine", "1000:1000", s)
        must(rc == 0, o[-400:])
    return "eslint clean"


@stage("Checks / Unit Test")
def st_unit():
    for s in snippets("Unit Test"):
        rc, o = container_run("node:20-alpine", "1000:1000", s)
        must(rc == 0, o[-400:])
    for f in ("coverage/lcov.info", "coverage/cobertura-coverage.xml", "reports/junit.xml"):
        owner_ok(f)
    rc, o = agent_check(f"grep -o 'tests=\"[0-9]*\"' {WS}/reports/junit.xml | head -1")
    must("tests=" in o, "junit has no tests attr")
    return f"coverage + junit present, {o.strip()}"


@stage("SonarQube prerequisites")
def st_sonar():
    rc, o = agent_check("ls /home/jenkins/agent/tools/hudson.plugins.sonar.SonarRunnerInstallation/sonar-scanner-tool/bin/sonar-scanner")
    must(rc == 0, "sonar-scanner tool missing: " + o.strip())
    rc, o = agent_check("java -version 2>&1 | head -1")
    must("openjdk" in o.lower() or "version" in o.lower(), "java not on PATH without JAVA_HOME block: " + o)
    rc, o = agent_check("/home/jenkins/agent/tools/hudson.plugins.sonar.SonarRunnerInstallation/sonar-scanner-tool/bin/sonar-scanner --version 2>&1 | grep -i 'SonarScanner CLI'")
    must(rc == 0, "sonar-scanner cannot start without JAVA_HOME env block: " + o)
    rc, o = agent_check("curl -s http://172.17.0.1:9000/api/system/status")
    must('"status":"UP"' in o, "SonarQube not UP at 172.17.0.1:9000: " + o)
    return "scanner starts w/o JAVA_HOME block, server UP at 172.17.0.1:9000 (analysis NOT published)"


@stage("E2E")
def st_e2e():
    ss = snippets("E2E")
    # snippets: compose up, npm ci, test:e2e, compose down
    must(len(ss) == 4, f"expected 4 snippets, got {len(ss)}: {ss}")
    up, npm_ci, e2e, down = ss
    try:
        rc, o = agent_exec(up)
        must(rc == 0, "compose up: " + o[-500:])
        rc, o = container_run("mcr.microsoft.com/playwright:v1.63.0-noble", "1000:1000",
                              npm_ci + "\n" + e2e, extra=("--network", "host"))
        must(rc == 0, "playwright: " + o[-900:])
    finally:
        agent_exec(down)
    owner_ok("playwright-report/junit.xml")
    rc, o = agent_check(f"grep -o 'tests=\"[0-9]*\" failures=\"[0-9]*\"' {WS}/playwright-report/junit.xml | head -1; ls {WS}/playwright-report/html | head -3")
    must("tests=" in o and 'failures="0"' in o, "junit: " + o)
    summary = o.strip().split("\n")[0]
    rc, o = agent_check("docker ps -a --format '{{.Names}}' | grep verify-loop || echo none")
    must("none" in o, "compose leftovers: " + o)
    return "playwright " + summary + ", compose torn down"



# ---------------------------------------------------------------- Lab 07
def lab07_env():
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()[:7]
    e = {"REGISTRY": "localhost:5000", "APP_NAME": "taskflow-api", "SHORT_SHA": sha,
         "IMAGE": f"localhost:5000/taskflow-api:{sha}", "BUILD_NUMBER": "9001",
         "KUBECONFIG": "/home/jenkins/.kube/config"}
    return e


def real_snippets(name):
    """Drop the Groovy-side `sh(script: 'git rev-parse ...')`, which is not a shell step we can replay verbatim."""
    return [x for x in snippets(name) if not x.startswith("git rev-parse")]


@stage("Build Image")
def st_build_image():
    env = lab07_env()
    ss = real_snippets("Build Image")
    must(len(ss) == 1, f"expected 1 snippet, got {len(ss)}")
    must(":latest" not in ss[0] and "latest" not in env["IMAGE"], "latest tag found")
    rc, o = agent_exec(ss[0], env)
    must(rc == 0, o[-600:])
    must(f"Verified in registry: {env['IMAGE']}" in o, "no registry verification line")
    rc, o = sh(["curl", "-fsS", "http://localhost:5000/v2/taskflow-api/tags/list"])
    must(env["SHORT_SHA"] in o and "latest" not in o, "host-side tag list: " + o)
    rc, o = sh(["docker", "exec", "taskflow-control-plane", "crictl", "pull", env["IMAGE"]])
    must(rc == 0, "kind node cannot pull from registry: " + o[-300:])
    return f"{env['IMAGE']} pushed, in registry, kind node pulls it"


def trivy_snippets():
    ss = real_snippets("Container Scan")
    must(len(ss) == 4, f"expected 4 snippets (rm, sarif, chown, gate), got {len(ss)}")
    return ss


@stage("Container Scan")
def st_trivy():
    env = lab07_env()
    rm, sarif, chown, gate = trivy_snippets()
    for x in (rm, sarif, chown):
        rc, o = agent_exec(x, env)
        must(rc == 0, o[-500:])
    owner_ok("trivy-report.sarif")
    rep = json_ok("trivy-report.sarif")
    must(rep["runs"][0]["tool"]["driver"]["name"] == "Trivy", "not a Trivy SARIF")
    rc, o = agent_exec(gate, env)
    must(rc == 0, "gate failed on the real image: " + o[-500:])
    # blocking path: a known-vulnerable image must fail the gate, yet pass 1 must still leave a SARIF behind
    bad = "node:16-alpine"
    sh(["docker", "pull", "-q", bad])
    badenv = dict(env, IMAGE=bad)
    agent_exec(rm, badenv)
    rc, o = agent_exec(sarif, badenv)
    must(rc == 0, "pass 1 must not fail on findings: " + o[-300:])
    agent_exec(chown, badenv)
    owner_ok("trivy-report.sarif")
    n = len(json_ok("trivy-report.sarif")["runs"][0]["results"])
    must(n > 0, "vulnerable image produced an empty SARIF")
    rc, o = agent_exec(gate, badenv)
    must(rc != 0, "GATE DID NOT BLOCK a vulnerable image")
    agent_exec(rm, env)
    return f"clean image passes gate; {bad} -> SARIF with {n} results written, gate blocked (rc={rc}); SARIF owner 1000:1000"


def kget(jsonpath, what="svc/taskflow"):
    rc, o = sh(["kubectl", "get"] + what.split() + ["-o", f"jsonpath={jsonpath}"])
    must(rc == 0, o)
    return o.strip()


def bg_blocks():
    ss = snippets("Blue/Green Deploy")
    # rm -f, script: kubectl get (current), deploy block, rollback block
    must(len(ss) == 4, f"expected 4 snippets, got {len(ss)}: {[x[:40] for x in ss]}")
    return ss


def bg_env(env, fault):
    cur = kget("{.spec.selector.color}")
    nxt = "green" if cur == "blue" else "blue"
    e = dict(env, PREV_COLOR=cur, NEXT_COLOR=nxt, DEPLOY_IMAGE=env["IMAGE"], VERIFY_PATH="/health")
    if fault == "bad-image":
        e["DEPLOY_IMAGE"] = f"{env['REGISTRY']}/{env['APP_NAME']}:0000000-does-not-exist"
    if fault == "post-switch-fail":
        e["VERIFY_PATH"] = "/health-broken"
    return cur, nxt, e


def sync_color_ep(color):
    time.sleep(3)
    ep = sorted(kget('{range .items[*].endpoints[*]}{.addresses[0]}{"\\n"}{end}', "endpointslices -l kubernetes.io/service-name=taskflow").split())
    pods = sorted(kget('{range .items[*]}{.status.podIP}{"\\n"}{end}', f"pods -l app=taskflow,color={color} --field-selector=status.phase=Running").split())
    must(ep == pods, f"endpoints {ep} != {color} pods {pods}")


@stage("Blue/Green Deploy")
def st_bluegreen():
    env = lab07_env()
    rm, _cur, deploy, rollback = bg_blocks()
    notes = []
    # ---- success path
    agent_exec(rm, env)
    cur, nxt, e = bg_env(env, "none")
    agent_exec(f"printf %s {cur} > .lab07-previous-color", env)  # Groovy writeFile
    rc, o = agent_exec(deploy, e)
    must(rc == 0, "deploy failed: " + o[-900:])
    order = [o.index(x) for x in ("Rollout complete for", "Smoke test passed for", "Switching traffic", "Active color is now")]
    must(order == sorted(order), "log order wrong (smoke test must precede the switch)")
    must(f"Smoke test passed for {nxt} (Service/taskflow still -> {cur})" in o, "traffic moved before smoke test passed")
    must(kget("{.spec.selector.color}") == nxt, "selector not switched")
    sync_color_ep(nxt)
    notes.append(f"success {cur}->{nxt}")
    # ---- failure path 1: fails AFTER the switch; rollback must flip the selector back
    for fault in ("post-switch-fail", "bad-image"):
        agent_exec(rm, env)
        cur, nxt, e = bg_env(env, fault)
        agent_exec(f"printf %s {cur} > .lab07-previous-color", env)
        rc, o = agent_exec(deploy, e)
        must(rc != 0, f"{fault}: deploy unexpectedly succeeded")
        if fault == "post-switch-fail":
            must(kget("{.spec.selector.color}") == nxt, "fault mode never switched traffic, so it would not exercise rollback")
        rc, o = agent_exec(rollback, e)
        must(rc == 0, f"{fault}: rollback block failed: " + o[-500:])
        must(f"Rolling back Service selector to {cur}." in o and f"Rollback complete. Active color: {cur}." in o, "rollback log lines missing: " + o[-400:])
        must(kget("{.spec.selector.color}") == cur, f"{fault}: selector not restored to {cur}")
        sync_color_ep(cur)
        notes.append(f"{fault}: rolled back to {cur}")
    # ---- rollback with no recorded color must not touch the Service
    agent_exec(rm, env)
    before = kget("{.spec.selector}")
    rc, o = agent_exec(rollback, {k: v for k, v in env.items()})
    must(rc == 0 and "Nothing to roll back" in o, "no-context rollback: " + o[-300:])
    must(kget("{.spec.selector}") == before, "no-context rollback changed the Service")
    # leave both colors on the real image (failed rollouts above were undone by the rollback block)
    agent_exec(rm, env)
    return "; ".join(notes) + "; no-context rollback is a no-op"


# ---------------------------------------------------------------- Lab 08 (IaC)
TF_DIR = "infra/terraform"
HARNESS_KEY = "taskflow-api/verify-loop.tfstate"     # NEVER the real state key
AWS_ENV = "AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1"


def lab08_env():
    e = lab07_env()
    e.update({"TF_IN_AUTOMATION": "1", "TF_INPUT": "0",  # the Jenkinsfile environment {} block
              # snippets stay verbatim; only the state key is redirected (init appends this)
              "TF_CLI_ARGS_init": f"-backend-config=key={HARNESS_KEY}",
              "SHORT_SHA": lab08_tag()})
    return e


def lab08_tag():
    rc, o = sh(["curl", "-fsS", "http://localhost:5000/v2/taskflow-api/tags/list"])
    must(rc == 0, "registry unreachable: " + o)
    tags = json.loads(o)["tags"]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()[:7]
    return head if head in tags else sorted(tags)[-1]


def l8(script, env=None, cwd=None):
    """Like agent_exec, but with Jenkins' `sh -e` semantics (first failing command aborts the step)."""
    return agent_exec("set -e\n" + script, env, cwd)


def aws_cli(args):
    return sh(["docker", "exec", "-e", "AWS_ACCESS_KEY_ID=test", "-e", "AWS_SECRET_ACCESS_KEY=test",
               "-e", "AWS_DEFAULT_REGION=us-east-1", AGENT, "aws", "--endpoint-url=http://localhost:4566"] + args)


def ingress_is_open():
    src = "\n".join(l.split("#")[0] for l in open(os.path.join(ROOT, TF_DIR, "main.tf")).read().split("\n"))  # ignore comments
    m = re.search(r'ingress\s*\{(.*?)\n  \}', src, re.S)
    return bool(m and "0.0.0.0/0" in m.group(1))


@stage("IaC / Terraform Validate")
def st_tf_validate():
    ss = snippets("Terraform Validate")
    must(len(ss) == 1, f"expected 1 snippet, got {len(ss)}")
    rc, o = l8(ss[0], lab08_env(), cwd=TF_DIR)
    must(rc == 0, o[-600:])
    return "init -backend=false + validate + fmt -check ok"


@stage("IaC / Ansible Lint")
def st_ansible_lint():
    ss = snippets("Ansible Lint")
    must(len(ss) == 1, f"expected 1 snippet, got {len(ss)}")
    rc, o = l8(ss[0], lab08_env())
    must(rc == 0, o[-600:])
    must("0 failure(s)" in o, "lint summary missing: " + o[-300:])
    return "ansible-lint clean"


@stage("IaC / Security Scan")
def st_iac_scan():
    ss = snippets("IaC Security Scan")
    must(len(ss) == 1, f"expected 1 snippet, got {len(ss)}")
    rc, o = l8(ss[0], lab08_env(), cwd=TF_DIR)
    must("===== tfsec =====" in o and "===== Checkov =====" in o, "one of the scanners did not run: " + o[-400:])
    if ingress_is_open():
        must(rc != 0, "stage stayed GREEN although ingress is 0.0.0.0/0")
        must("aws-ec2-no-public-ingress-sgr" in o, "tfsec did not report the open ingress")
        must("CKV_AWS_382" in o or "CKV_AWS_260" in o or "FAILED" in o, "checkov reported nothing")
        return "ingress open => stage RED as intended (tfsec aws-ec2-no-public-ingress-sgr; checkov failed too)"
    must(rc == 0, "clean config must pass both scanners: " + o[-900:])
    return "config clean => both scanners pass, stage GREEN"


@stage("IaC / Terraform Plan")
def st_tf_plan():
    ss = snippets("Terraform Plan")
    must(len(ss) == 2, f"expected 2 snippets (rm, plan), got {len(ss)}")
    env = lab08_env()
    rc, o = l8(ss[0], env)
    must(rc == 0, o[-300:])
    rc, o = l8(ss[1], env, cwd=TF_DIR)
    must(rc == 0, o[-900:])
    owner_ok(f"{TF_DIR}/tfplan")
    owner_ok(f"{TF_DIR}/tfplan.txt")
    rc, txt = agent_check(f"cat {WS}/{TF_DIR}/tfplan.txt")
    must("Plan:" in txt or "No changes" in txt, "tfplan.txt has no plan summary")
    # stash simulation: the same file set the Jenkinsfile stashes
    rc, o = agent_check(f"cd {WS} && tar -cf /tmp/stash-tfplan.tar {TF_DIR}/tfplan {TF_DIR}/tfplan.txt {TF_DIR}/.terraform.lock.hcl")
    must(rc == 0, "stash contents missing (lock file?): " + o)
    return re.search(r"(Plan: [^\n]*|No changes[^\n]*)", txt).group(1)


@stage("IaC / Approval handoff")
def st_approval():
    # Jenkins: Approval and Apply run in DIFFERENT workspaces. Simulate with a second, empty workspace.
    ws2 = WS + "@2"
    files = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True).stdout
    tar = subprocess.run(["tar", "--null", "-T", "-", "-cf", "-"], cwd=ROOT, input=files, capture_output=True).stdout
    agent_check(f"rm -rf {ws2} && mkdir -p {ws2}")
    subprocess.run(["docker", "exec", "-i", AGENT, "tar", "-x", "-C", ws2], input=tar, capture_output=True)  # SCM checkout of the stage
    rc, o = agent_check(f"tar -xf /tmp/stash-tfplan.tar -C {ws2} && ls {ws2}/{TF_DIR}")     # unstash overlay
    must(rc == 0 and "tfplan" in o, "unstash into a fresh workspace failed: " + o)
    rc, o = agent_check(f"wc -c < {ws2}/{TF_DIR}/tfplan.txt")
    must(int(o.strip()) > 0, "empty plan text for the input prompt")
    return f"plan text {o.strip()} chars (prompt drops 'known after apply' lines, caps at 12000); input itself is UI-only"


@stage("IaC / Terraform Apply")
def st_tf_apply():
    ss = snippets("Terraform Apply")
    must(len(ss) == 2, f"expected 2 snippets (rm, apply), got {len(ss)}")
    env = lab08_env()
    ws2 = WS + "@2"
    # run in the "@2" workspace that only has the unstashed plan (like the real second agent context)
    rc, o = sh(["docker", "exec", "-i", "-e", f"WORKSPACE={ws2}"] + sum([["-e", f"{k}={v}"] for k, v in env.items()], []) +
               ["-w", f"{ws2}/{TF_DIR}", AGENT, "sh", "-s"], inp="set -e\n" + ss[1])
    must(rc == 0, "apply failed: " + o[-900:])
    must("Apply complete!" in o, "no 'Apply complete!' line: " + o[-300:])
    rc, o = agent_check(f"cat {ws2}/{TF_DIR}/tf-outputs.json")
    outs = json.loads(o)
    iid = outs["instance_id"]["value"]
    addr = outs["instance_address"]["value"]
    # independent checks (separate process, LocalStack + S3, not Terraform)
    rc, o = aws_cli(["ec2", "describe-instances", "--instance-ids", iid, "--query", "Reservations[].Instances[].State.Name", "--output", "text"])
    must(rc == 0 and "running" in o, f"instance {iid} not running in LocalStack: {o.strip()}")
    rc, o = aws_cli(["s3", "ls", "s3://taskflow-tfstate/taskflow-api/"])
    must("verify-loop.tfstate" in o, "harness state object missing in S3: " + o)
    # carry the applied state's view back to the main workspace for the inventory stage
    return f"instance {iid} running, address {addr}, state in S3"


@stage("IaC / Configure with Ansible")
def st_ansible():
    ss = snippets("Configure with Ansible")
    must(len(ss) == 3, f"expected 3 snippets (init, inventory, playbook), got {len(ss)}: {ss}")
    env = lab08_env()
    rc, o = l8(ss[0], env, cwd=TF_DIR)
    must(rc == 0, "terraform init: " + o[-400:])
    rc, o = l8(ss[1], env)
    must(rc == 0, "inventory: " + o[-400:])
    rc, o = l8(ss[2], env, cwd="infra/ansible")
    must(rc == 0, "ansible-playbook: " + o[-900:])
    must("failed=0" in o and "unreachable=0" in o, "recap: " + o[-300:])
    rc, ini = agent_check(f"cat {WS}/infra/ansible/inventory/hosts.ini")
    rc2, out = agent_check(f"cd {WS}/{TF_DIR} && terraform output -raw instance_address")
    addr = out.strip().splitlines()[-1] if out.strip() else ""
    must("ansible_connection=local" in ini and "localhost" in ini, "inventory: " + ini)
    must(addr and f"terraform_reported_address={addr}" in ini, f"inventory lacks Terraform address {addr!r}: {ini}")
    must("Pull taskflow-api image" in o and "Image digest: [localhost:5000/taskflow-api@sha256:" in o, "pull/digest missing")
    rc, o = agent_check(f"docker image inspect localhost:5000/taskflow-api:{env['SHORT_SHA']} --format '{{{{.Id}}}}'")
    must(rc == 0, "image not present after playbook: " + o)
    rc, o = l8(ss[2], env, cwd="infra/ansible")     # second run: idempotency
    must(rc == 0 and "changed=0" in o and "failed=0" in o, "second playbook run not idempotent: " + o[-300:])
    return f"inventory has localhost+local+address {addr}; playbook rc=0, 2nd run changed=0"


def lab08_cleanup():
    """Destroy ONLY what the harness created (throwaway state key), then drop that state object."""
    env = lab08_env()
    rc, o = sh(["docker", "exec", "-i", "-e", "TF_IN_AUTOMATION=1", "-e", f"TF_CLI_ARGS_init={env['TF_CLI_ARGS_init']}",
                "-w", f"{WS}/{TF_DIR}", AGENT, "sh", "-c",
                "terraform init -no-color >/dev/null && terraform destroy -auto-approve -no-color | tail -2 && terraform show -no-color"])
    print("[cleanup] harness terraform destroy:", o.strip().replace("\n", " | ")[-200:])
    aws_cli(["s3", "rm", f"s3://taskflow-tfstate/{HARNESS_KEY}"])
    sh(["docker", "exec", AGENT, "sh", "-c", f"rm -rf {WS}@2"])


LAB08_STAGES = [st_tf_validate, st_ansible_lint, st_iac_scan, st_tf_plan, st_approval, st_tf_apply, st_ansible]


# ---------------------------------------------------------------- Lab 10
@stage("Pipeline Health Gate (script)")
def st_health_gate():
    ss = snippets("Pipeline Health Gate")
    must(any("scripts/health_gate.py" in s for s in ss), f"gate no longer calls scripts/health_gate.py: {ss}")
    env = {"PROM_URL": "http://localhost:9090", "JOB_NAME": "taskflow-pipeline", "HEALTH_WINDOW": "1h"}
    rc, o = l8("python3 scripts/health_gate.py", env)
    must(rc == 0 and re.search(r"^HEALTH status=(ok|nodata) ", o, re.M), "unexpected gate output: " + o[-300:])
    # Prometheus down => the stage must FAIL, never read as healthy
    rc, o = agent_exec("python3 scripts/health_gate.py", dict(env, PROM_URL="http://localhost:1"))
    must(rc != 0 and "HEALTH" not in o, "unreachable Prometheus must fail the gate, got: " + o[-200:])
    rc, o = agent_exec("python3 scripts/health_gate.py", dict(env, HEALTH_WINDOW="bogus"))
    must(rc != 0, "bad window must fail the gate")
    rc, o = agent_exec("python3 scripts/health_gate.py", dict(env, JOB_NAME="no-such-job"))
    must(rc == 0 and "status=nodata" in o, "unknown job must report nodata (not a rate): " + o[-200:])
    return "live query ok; unreachable / bad-window -> non-zero; unknown job -> nodata"


LAB10_STAGES = None  # filled in below (needs the Lab 05-07 stage functions)


STAGES = [st_install, st_secrets, st_eslint, st_semgrep, st_sca, st_sbom, st_policy,
          st_lint, st_unit, st_sonar, st_e2e, st_build_image, st_trivy, st_bluegreen]

def seed_workspace():
    """Fresh Jenkins-style checkout: tracked files (working-tree state), owned by the agent user."""
    sh(["docker", "exec", AGENT, "sh", "-c", f"rm -rf {WS} /tmp/stash-*; mkdir -p {WS}"])
    # tracked + new-but-not-ignored files (a Jenkins checkout of the commit about to be made)
    files = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True).stdout
    tar = subprocess.run(["tar", "--null", "-T", "-", "-cf", "-"], cwd=ROOT, input=files, capture_output=True).stdout
    p = subprocess.run(["docker", "exec", "-i", AGENT, "tar", "-x", "-C", WS], input=tar, capture_output=True)
    if p.returncode != 0:
        sys.exit("could not seed workspace: " + p.stderr.decode())


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    passes = int(args[0]) if args else 2
    if "--lab07" in sys.argv:
        STAGES = STAGES[-3:]  # Build Image, Container Scan, Blue/Green Deploy only
    if "--lab08" in sys.argv:
        STAGES = LAB08_STAGES
    if "--lab10" in sys.argv:  # Fast Checks lanes + SBOM/Policy chain + health gate; no deploys, colour untouched
        STAGES = [st_install, st_secrets, st_eslint, st_semgrep, st_sca, st_lint, st_unit, st_sbom, st_policy, st_health_gate]
    seed_workspace()
    for n in range(1, passes + 1):
        print(f"\n===== PASS {n} ({'fresh checkout' if n == 1 else 'PERSISTENT workspace, stale state from pass ' + str(n-1)}) =====", flush=True)
        t0 = time.time()
        for st in STAGES:
            st()
        print(f"----- pass {n} wall time (sequential, no image-pull time excluded): {time.time()-t0:.0f}s", flush=True)
    if "--lab08" in sys.argv:
        lab08_cleanup()
    if "--keep" not in sys.argv:
        sh(["docker", "exec", AGENT, "sh", "-c", f"rm -rf {WS} /tmp/stash-*"])
    bad = [r for r in results if not r[1]]
    print(f"\nSUMMARY: {len(results)-len(bad)}/{len(results)} stage runs passed")
    sys.exit(1 if bad else 0)
