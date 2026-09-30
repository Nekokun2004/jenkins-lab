# Taskflow CI/CD Architecture

Everything runs on one Debian host (Docker). Jenkins controller and the `linux-build` agent are containers; the
agent talks to the host Docker daemon through `docker.sock`. Install, Lint and Unit Test run as ephemeral pods on the
`kind` cluster (`k8s-node`); every other stage stays on `linux-build`.

## `taskflow-api` pipeline (`Jenkinsfile`, job `taskflow-pipeline`)

```mermaid
graph LR
    A[Push / Build Now] --> B[Install<br/>k8s pod]
    B --> C{{Fast Checks - parallel}}
    C --> C1[Lint<br/>k8s pod]
    C --> C2[Unit Test<br/>k8s pod]
    C --> C3[Secrets Detection<br/>gitleaks]
    C --> C4[SAST<br/>ESLint then Semgrep]
    C --> C5[SCA - npm audit]
    C1 & C2 & C3 & C4 & C5 --> D[Generate SBOM + sign]
    D --> E[Policy Gate<br/>OPA]
    E --> F[SonarQube Analysis]
    F --> G[Quality Gate<br/>webhook]
    G --> H[E2E<br/>Playwright]
    H --> I[Build Image<br/>localhost:5000]
    I --> J[Container Scan<br/>Trivy]
    J --> K[Blue/Green Deploy<br/>kind, auto rollback]
    K --> L[IaC: Lint, Security Scan,<br/>Terraform Plan]
    L --> M[/Approval - human/]
    M --> N[Terraform Apply<br/>LocalStack]
    N --> O[Ansible]
    O --> P[Deploy Staging<br/>branch develop]
    P --> Q[Pipeline Health Gate<br/>last 20 builds]
    Q --> R[Deploy Production<br/>branch main + input]
```

- **Parallel:** only the five Fast Checks lanes. The sequential chains are real dependencies: SBOM -> Policy Gate
  (needs `audit.json` from SCA), Sonar Analysis -> Quality Gate, Plan -> Approval -> Apply, Build Image -> Scan -> Deploy.
- **SAST** runs its two scanners one after the other: Declarative Pipeline rejects a `parallel` nested inside a
  `parallel` (checked with the Jenkins linter).
- **IaC stages** are skipped when the build parameter `SKIP_IAC` is true (test aid, default false).
- **Pipeline Health Gate** blocks `Deploy — Production` when the job's rolling build success rate over its **last 20
  completed builds** is below 90%. The rate comes from the job's own Jenkins build history (SUCCESS = success; FAILURE and
  UNSTABLE = not; ABORTED / running builds are skipped). With fewer than 20 builds it uses what exists and prints
  "N builds available out of 20"; with none it prints an explicit no-data warning (never a fake 100%). It runs on every
  branch; only `main` goes on to deploy.

## `taskflow-mobile` pipeline (Flutter, job `taskflow-mobile-pipeline`)

```mermaid
graph LR
    M1[Mobile push] --> M2[Flutter Analyze] --> M3[Flutter Test] --> M4[SCA<br/>osv-scanner]
    M4 --> M5[Build Debug APK] --> M6[Build Signed Release AAB] --> M7[Archive artifacts]
```

## Monitoring loop

```mermaid
graph LR
    J[Jenkins /prometheus] -->|scrape 15s| P[Prometheus :9090]
    P --> G[Grafana :3000<br/>Jenkins Pipeline SLO + alert]
    B[Jenkins build history<br/>last 20 builds] -->|results| H[Pipeline Health Gate]
    H -->|block or pass| Q[Deploy Production]
```

Components: Jenkins `:8080` (controller), agent `jenkins-agent-linux-build`, `kind` cluster `taskflow`
(Service `taskflow`, Deployments `taskflow-blue` / `taskflow-green`), registry `localhost:5000`, SonarQube `:9000`,
LocalStack `:4566` (Terraform state bucket `taskflow-tfstate`), Prometheus `:9090`, Grafana `:3000`.
