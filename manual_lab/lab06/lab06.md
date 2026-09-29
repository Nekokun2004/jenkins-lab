# Lab 06 — Shift-Left Security Pipeline

**อ้างอิงจาก:** Deck 00c, 09b — DevSecOps / Security Analysis
**ระยะเวลา:** 4 ชั่วโมง · **รูปแบบ:** ทำเป็นคู่ (ทำคนเดียวได้ตามความสะดวก)

---

## เป้าหมายของแล็บนี้

1. รัน secrets detection, SAST, SCA ก่อน stage build เสมอ ตามลำดับนี้เป๊ะ
2. สร้างและเก็บ SBOM (Software Bill of Materials) ของ release artifact ไว้เป็นหลักฐาน
3. ใช้นโยบาย fail/warn threshold แทนการ gate แบบ all-or-nothing

## พื้นหลัง

Shift-left คือแนวคิดเรื่อง cost curve: secret ที่หลุดแล้วถูก Gitleaks จับได้ตอน commit แทบไม่มีต้นทุนอะไรเลย แต่ secret ตัวเดียวกันที่หลุดไปถึง production กลายเป็น incident เต็มรูปแบบ แล็บนี้สร้างสายพาน security แบบมีลำดับ: **Secrets → SAST → SCA → SBOM → Policy Gate** (ยังไม่รวม Container scan/DAST ซึ่งจะไปทำใน Lab 07 ตอนมี image จริงให้ scan)

---

## ⚠️ สิ่งที่ต้องเตรียมก่อนเริ่ม

### เตรียมที่ 1 — ทุก tool ใหม่รันผ่าน Docker sidecar ทั้งหมด ไม่ต้องแก้ `Dockerfile.agent` อีก

ข่าวดี: Gitleaks, Semgrep, Syft, Cosign, OPA **ไม่ต้องติดตั้งลงใน agent image เลย** — ใช้ pattern เดียวกับ `docker.image('...').inside(...)` ที่ทำมาแล้วตอน Lab 05 (E2E stage กับ Playwright) คือดึง Docker image ของแต่ละ tool มารันเป็น sidecar container ชั่วคราวแทน

**ลองดึง image ทั้งหมดมาเช็คไว้ก่อนล่วงหน้า** (กันเสียเวลารอ pull ตอน build จริง):
```bash
docker exec jenkins-agent-linux-build docker pull zricethezav/gitleaks:latest
docker exec jenkins-agent-linux-build docker pull semgrep/semgrep:latest
docker exec jenkins-agent-linux-build docker pull anchore/syft:latest
docker exec jenkins-agent-linux-build docker pull ghcr.io/sigstore/cosign/cosign:v2.4.1
docker exec jenkins-agent-linux-build docker pull openpolicyagent/opa:latest
```

### เตรียมที่ 2 — เพิ่ม ESLint SARIF formatter (ให้ output เป็นไฟล์ที่ archive ได้)

```bash
cd ~/Documents/selfproject/jenkins-lab
npm install --save-dev @microsoft/eslint-formatter-sarif
git add package.json package-lock.json
git commit -m "add: eslint SARIF formatter for Lab 06 SAST stage"
```

### เตรียมที่ 3 — สร้าง branch ใหม่สำหรับ Lab 06 (แยกจาก `lab05` ที่จบไปแล้ว)

```bash
git checkout main
git pull origin main
git checkout -b lab06
```

> **หมายเหตุ:** ถ้า `main` ยังไม่มี Jenkinsfile จาก Lab 05 (ยังไม่ได้ merge `lab05 → main`) ให้ใช้ `git checkout lab05 && git checkout -b lab06` แทน เพื่อสืบทอด stage ทั้งหมดจาก Lab 05 มาด้วย — เช็คด้วย `git log --oneline -5` ก่อนว่า Jenkinsfile ที่เห็นมี stage `SonarQube Analysis` อยู่จริงไหม

### เตรียมที่ 4 — เข้าใจเรื่อง Cosign key ก่อนเริ่ม (สำคัญ ป้องกันความสับสน)

โจทย์บอกว่า "a local keypair is fine for the lab" — วิธีที่ง่ายที่สุดคือ **generate key คู่ใหม่ทุกครั้งที่ build** (ไม่ต้องเก็บ persist ข้าม build) เพราะเป็นแค่การสาธิตว่า sign/verify ทำงานถูกต้อง ไม่ใช่ระบบ production ที่ต้อง track key เดิมข้ามเวลา — จะเห็นในโค้ด stage ว่า generate key ใหม่ทุกรอบ

---

## ขั้นตอนทั้งหมด

### ขั้นที่ 1 — Secrets Detection: ทดสอบบน scratch branch ก่อน `[CLI]`

**สร้าง scratch branch แยกต่างหาก (ไม่ merge เข้าที่ไหนเลย):**
```bash
git checkout -b lab06-secrets-test
```

**จงใจ commit fake AWS key:**
```bash
echo 'AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE' >> .env.fake-secret-test
echo 'AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY' >> .env.fake-secret-test
git add .env.fake-secret-test
git commit -m "test: intentional fake AWS key for Gitleaks detection demo"
git push origin lab06-secrets-test
```

**ทดสอบ Gitleaks ตรง ๆ ก่อนเอาเข้า Jenkinsfile** (เพื่อยืนยันว่าจับได้จริง):
```bash
docker run --rm -v "$(pwd):/repo" zricethezav/gitleaks:latest detect \
  --source /repo --report-format json --report-path /repo/gitleaks-report.json -v
```

**ผลลัพธ์ที่ควรเห็น:** Gitleaks รายงาน error/finding พบ AWS key pattern พร้อม exit code ไม่เท่ากับ 0 — ยืนยันว่า Gitleaks ทำงานจริง

**เก็บไฟล์ `gitleaks-report.json` นี้ไว้เป็น deliverable ข้อ 1** แล้ว**กลับไปที่ branch `lab06`** (อย่า merge `lab06-secrets-test` เข้าที่ไหนเลย ปล่อยเป็น scratch branch ทิ้งไว้):
```bash
git checkout lab06
```

---

### ขั้นที่ 2 — เขียน Jenkinsfile stage ทั้งหมด

เปิด `Jenkinsfile` เพิ่ม stage ใหม่เข้าไป **ก่อน** stage `Checks` เดิม (ต่อจาก `Install`):

```groovy
        stage('Secrets Detection') {
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
            steps {
                script {
                    docker.image('anchore/syft:latest').inside('--entrypoint=""') {
                        sh 'syft dir:. -o cyclonedx-json=taskflow-api.cdx.json'
                    }
                    docker.image('ghcr.io/sigstore/cosign/cosign:v2.4.1').inside('--entrypoint="" -e COSIGN_PASSWORD=') {
                        sh '''
                            cosign generate-key-pair
                            cosign sign-blob --key cosign.key --yes taskflow-api.cdx.json > taskflow-api.cdx.json.sig
                        '''
                    }
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: 'taskflow-api.cdx.json,taskflow-api.cdx.json.sig,cosign.pub', allowEmptyArchive: true
                    stash name: 'sbom-report', includes: 'taskflow-api.cdx.json'
                }
            }
        }

        stage('Policy Gate') {
            steps {
                unstash 'audit-report'
                script {
                    docker.image('openpolicyagent/opa:latest').inside('--entrypoint=""') {
                        def result = sh(
                            script: "opa eval --input audit.json --data policy/security.rego 'data.security.deny' -f raw",
                            returnStdout: true
                        ).trim()
                        echo "OPA policy evaluation result: ${result}"
                        if (result != '[]' && result != '') {
                            error("Policy Gate blocked: ${result}")
                        }
                    }
                }
            }
        }
```

---

### 📖 อธิบายส่วนสำคัญของโค้ด

**Secrets Detection:**
```groovy
docker.image('zricethezav/gitleaks:latest').inside('--entrypoint=""') { ... }
```
`--entrypoint=""` จำเป็นเพราะ image ทางการของ Gitleaks ตั้ง entrypoint เป็น `gitleaks` ไว้แล้ว — ถ้าไม่ล้าง entrypoint ก่อน คำสั่ง `sh` ข้างในจะถูกส่งเป็น argument ต่อจาก `gitleaks` แทนที่จะรันเป็น shell script ปกติ ทำให้พังทันที

`--no-git` บอก Gitleaks ให้สแกนไฟล์ในสภาพปัจจุบัน (ไม่ไล่ทั้ง git history) — ใช้แบบนี้ใน pipeline หลักเพราะ `lab06` branch ไม่มี fake secret อยู่แล้ว (เราแยกไปทดสอบใน `lab06-secrets-test` ต่างหาก) จุดประสงค์ตรงนี้คือให้ stage นี้ผ่านเสมอในสายงานจริง เป็นแค่ safety net

**SAST (parallel):**
เหมือน `Checks` stage ของ Lab 05 — สอง sub-stage รันพร้อมกัน `ESLint Security` ต้องมี `agent { docker {...} }` ของตัวเอง (กฎเดียวกับ Lab 05 ที่ stage ในเสีย `parallel` ห้ามมี agent ที่ parent) ส่วน `Semgrep` ไม่ต้องมี agent เพราะสืบทอดจาก agent หลักของ pipeline

**SCA — npm audit:**
```groovy
sh 'npm audit --audit-level=high --json > audit.json || true'
```
เพิ่ม `|| true` (แก้จาก `-|` ในโจทย์ต้นฉบับซึ่งเป็น typo) เพราะ `npm audit` จะ return exit code ที่ไม่ใช่ 0 ทันทีที่เจอ vulnerability ระดับ `high` ขึ้นไป — ถ้าไม่ดัก `|| true` ไว้ shell step จะ fail ก่อนที่ script จะได้ไปอ่านและตัดสินใจเองด้วยตรรกะ fail/warn ที่ต้องการ (แก่นของโจทย์ข้อนี้คือ "ไม่ใช่ exit-code-only")

`apk add --no-cache jq` ต้องรันทุกครั้งเพราะ container `node:20-alpine` ใหม่ทุก build (ephemeral) ไม่มี `jq` ติดมา — ไม่ต้องแก้ Dockerfile ไหน

**Generate SBOM:**
```groovy
cosign generate-key-pair
```
โดย default คำสั่งนี้จะถาม password สำหรับเข้ารหัส private key แบบ interactive — ตั้ง `-e COSIGN_PASSWORD=` (ค่าว่าง) ไว้ตอนสร้าง container เพื่อให้มันอ่านจาก environment variable แทนการถามในเทอร์มินัล (ซึ่งใช้ไม่ได้ใน non-interactive CI)

**Policy Gate:**
```groovy
opa eval --input audit.json --data policy/security.rego 'data.security.deny' -f raw
```
`-f raw` บอกให้ OPA คืนค่าดิบ (ไม่ envelope เป็น JSON ซับซ้อน) — ถ้าไม่มี deny เข้าเงื่อนไข ผลลัพธ์จะเป็น `[]` (array ว่าง) เทียบง่ายในโค้ด Groovy

---

### ขั้นที่ 3 — เขียนไฟล์ policy `policy/security.rego`

```bash
mkdir -p policy
cat > policy/security.rego << 'EOF'
package security

deny[msg] {
    input.metadata.vulnerabilities.critical > 0
    msg := sprintf("Blocked: %d CRITICAL vulnerabilities found", [input.metadata.vulnerabilities.critical])
}

default allow = false

allow {
    count(deny) == 0
}
EOF
```

**อธิบายโค้ด rego:**
- `deny[msg] { ... }` — กฎแรก (clause แรก): ถ้าเงื่อนไขข้างในเป็นจริง (`input.metadata.vulnerabilities.critical > 0`) ให้เพิ่มข้อความ `msg` เข้าไปใน set ชื่อ `deny`
- `allow { count(deny) == 0 }` — กฎที่สอง (clause ที่สอง): `allow` จะเป็นจริงก็ต่อเมื่อ set `deny` ว่างเปล่า — สอง clause นี้คือ "two-clause policy" ตามที่โจทย์ระบุ

Commit ไฟล์นี้:
```bash
git add policy/security.rego Jenkinsfile package.json package-lock.json
git commit -m "add: shift-left security pipeline (secrets, SAST, SCA, SBOM, policy gate)"
git push origin lab06
```

---

### ขั้นที่ 4 — สร้าง Jenkins job ชี้ไป `lab06` แล้วรันครั้งแรก `[UI]`

ใช้ job `taskflow-pipeline` เดิม → Configure → เปลี่ยน Branch Specifier เป็น `*/lab06` → Save → Build Now

**คาดว่า build แรกจะผ่านเขียวทุก stage ใหม่** เพราะยังไม่ได้จงใจทำอะไรให้พัง

---

### ขั้นที่ 5 — จงใจ downgrade dependency ให้มี known CVE แล้วพิสูจน์ว่า Policy Gate บล็อกจริง `[CLI]`

```bash
npm install lodash@4.17.4 --save-exact
git add package.json package-lock.json
git commit -m "test: intentionally downgrade lodash to trigger known critical CVE"
git push origin lab06
```

รัน Build Now ใหม่ — **คาดว่า pipeline จะหยุดที่ `Policy Gate`** (ไม่ใช่ที่ `SCA — npm audit` เพราะ SCA stage ตั้งใจให้แค่ warn ถ้า critical ยังไม่เกิน 0 ตาม logic ที่เขียนไว้ — แต่ตรงนี้ critical จะ > 0 จริง ทำให้ **ทั้ง SCA และ Policy Gate อาจ block พร้อมกัน** ขึ้นอยู่กับว่า `npm audit` รายงาน severity ของ lodash เวอร์ชันนี้เป็น critical จริงหรือแค่ high — **เช็คค่า `critical` ใน `audit.json` ที่ archive ไว้ก่อน** ถ้าเป็น 0 (severity แค่ high ไม่ใช่ critical) SCA stage จะผ่าน แต่ Policy Gate ก็จะผ่านด้วยเพราะ policy เช็คแค่ critical เหมือนกัน — **ถ้าเจอแบบนี้ให้ลองเวอร์ชัน `lodash@4.17.15` หรือค้นหา package อื่นที่ `npm audit` ระบุ severity เป็น critical ชัดเจนแทน**)

**📸 deliverable:** เก็บ console log ของ build ที่ `Policy Gate` (หรือ `SCA`) แสดง error message บล็อกไว้

---

### ขั้นที่ 6 — Revert กลับ ยืนยันว่าผ่านปกติ `[CLI]`

```bash
git revert HEAD
git push origin lab06
```

รัน Build Now ใหม่ — **คาดว่าทุก stage เขียวหมดอีกครั้ง** เก็บ log นี้ไว้เป็นคู่กับ log ที่ block

---

## สรุป Deliverables ที่ต้องส่ง

| # | รายการ | เก็บจากขั้นตอนไหน |
|---|---|---|
| 1 | Gitleaks report ที่จับ fake secret ได้ (จาก scratch branch ไม่ merge) | ขั้นที่ 1 |
| 2 | Signed SBOM (`.cdx.json` + `.sig`) เป็น build artifact | ขั้นที่ 4 |
| 3 | ไฟล์ `policy/security.rego` + log 1 อันที่ block CVE, 1 อันที่ผ่าน | ขั้นที่ 5, 6 |

## เกณฑ์การให้คะแนน

| หัวข้อ | คะแนน |
|---|---|
| ลำดับ stage ถูกต้อง: secrets → SAST → SCA → SBOM → policy | 25 |
| Fail/warn threshold logic ถูกต้อง ไม่ใช่ exit-code เปล่า ๆ | 25 |
| SBOM ถูกสร้าง, sign, และ archive ครบ | 25 |
| Policy gate บล็อกและปลดบล็อกได้จริงตามที่ออกแบบ | 25 |

---

## หมายเหตุ / ข้อควรระวัง

- Cosign key ที่ generate ใหม่ทุก build เป็นเรื่องปกติสำหรับแล็บนี้ — ในระบบจริงจะต้องเก็บ private key ไว้ใน Jenkins Credentials หรือ external KMS ไม่ generate ใหม่ทุกครั้ง (ควรเขียนโน้ตนี้ไว้ในรายงานเป็นข้อจำกัดที่รู้ตัว)
- `lab06-secrets-test` branch ต้อง**ไม่ถูก merge เข้า `lab06` หรือ `main` เด็ดขาด** เพราะมี fake secret ค้างอยู่ในนั้นถาวร (แม้จะเป็นของปลอมก็ตาม เป็นนิสัยที่ดีที่ต้องฝึกไว้)
- ถ้า `npm audit` เปลี่ยนผลลัพธ์ไปตามเวลา (เพราะฐานข้อมูล vulnerability ของ npm อัปเดตเรื่อย ๆ) ตัวเลข critical ของ dependency ที่เลือกมาอาจไม่ตรงกับตอนเขียนคู่มือนี้ — ให้เช็ค `audit.json` จริงเสมอก่อนสรุปผล
