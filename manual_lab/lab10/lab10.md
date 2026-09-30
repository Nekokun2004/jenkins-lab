# Lab 10 — Capstone: End-to-End Pipeline

**อ้างอิงจาก:** Deck 11–13 — Best Practices / Summary / Mobile
**ระยะเวลา:** 4 ชั่วโมง + take-home (ทำแบบย่อ ตามแผน checkpoint) · **ออกแบบมาให้ทำเป็นทีม 3-4 คน — ทำคนเดียวใช้แผนย่อนี้**

---

## เป้าหมายของแล็บนี้

1. รวมทุก stage จาก Lab 03-09 เป็น Jenkinsfile เดียว จัด parallel ให้ตรงจุด
2. เพิ่ม pipeline สำหรับ `taskflow-mobile` (Flutter)
3. Demo สด — push การเปลี่ยนแปลงจริง เดินอธิบายทุก gate

## ⚠️ แผนย่อสำหรับเวลาที่จำกัด (ตกลงกันไว้แล้ว)

| งาน | ระดับที่ทำ | เหตุผล |
|---|---|---|
| Parallelize Jenkinsfile เดิม | **เต็มรูปแบบ** | ทำง่าย ใช้ pattern เดิมจาก Lab 05 |
| No hardcoded secrets (grep check) | **เต็มรูปแบบ** | เร็วมาก แทบไม่เสียเวลา |
| Mobile pipeline (Flutter) | **บายพาส** — ใช้ `flutter create` scaffold ของ Flutter เอง (ไม่เขียน UI เอง), keystore ปลอมสำหรับทดสอบ | โจทย์เช็คว่า pipeline build/sign ได้ ไม่ได้เช็คว่า UI สวยแค่ไหน |
| ย้ายทุก stage ไป K8s dynamic agent | **บางส่วน** — เฉพาะที่ Lab 09 ย้ายไปแล้ว | ย้ายทุก stage ต้องแก้ Docker-in-Docker ในพอด K8s ซึ่งซับซ้อนเกินเวลา |
| Pipeline Health Gate | **เต็มรูปแบบ** — query Prometheus จาก Lab 09 ตรง ๆ | มี endpoint พร้อมใช้อยู่แล้ว ไม่ยาก |
| Slack/email notification | **บายพาส** — ใส่โค้ดไว้ในไฟล์ ไม่ต่อ service จริง | ไม่มีคะแนนแยกในเกณฑ์ |
| Architecture diagram + Runbook | **เต็มรูปแบบแต่สั้น** | จำเป็นสำหรับคะแนน เขียนเร็วได้ |
| Live demo | **เต็มรูปแบบ** | จำเป็น แต่ไม่ต้องซ้อมเยอะ |

---

## สิ่งที่ต้องรู้ก่อนเริ่ม

| ข้อเท็จจริง | ผลกับ Lab 10 |
|---|---|
| `taskflow-mobile` repo ยังไม่เคยสร้าง | ต้องสร้างใหม่ตอนนี้ (fork ตั้งแต่ Lab 01 ไว้เฉย ๆ ไม่เคยใช้จริง) |
| agent มี Docker CLI + compose อยู่แล้ว | ใช้ sidecar `cirruslabs/flutter:stable` แบบเดียวกับที่ทำ Playwright ได้เลย |
| Registry `localhost:5000` จาก Lab 07 | ไม่เกี่ยวกับ mobile (APK/AAB ไม่ต้อง push เข้า registry) |
| Prometheus endpoint จาก Lab 09 ที่ `localhost:9090` | ใช้ query โดยตรงใน Pipeline Health Gate |

---

## ขั้นที่ 1 — Grep เช็คว่าไม่มี secret ฝังในโค้ด `[CLI]`

```bash
grep -R "password\|secret\|token" Jenkinsfile
```
ถ้าเจอบรรทัดไหนที่เป็น**ค่าจริง** (ไม่ใช่แค่ชื่อ credential id เช่น `sonar-token`, `github-pat`) ให้แก้เป็น `withCredentials`/`credentials()` — ถ้าทำมาถูกทางตลอด (ใช้ Jenkins Credentials มาตั้งแต่ Lab 05) **ควรจะผ่านอยู่แล้วโดยไม่ต้องแก้อะไรเลย**

---

## ขั้นที่ 2 — Parallelize stage อิสระใน Jenkinsfile เดิม `[CLI]`

รวม stage ที่ไม่พึ่งกัน (`Secrets Detection`, `SAST`, `SCA — npm audit` จาก Lab 06) เข้าไปอยู่ใน `parallel {}` เดียวกับ `Checks` (Lint/Unit Test) — ทั้งหมดนี้ไม่ต้องรอกันเลย:

```groovy
        stage('Fast Checks') {
            parallel {
                stage('Lint') {
                    agent { kubernetes { yaml '''...node:20-alpine...''' } }
                    steps { sh 'npm ci && npm run lint' }
                }
                stage('Unit Test') {
                    agent { kubernetes { yaml '''...node:20-alpine...''' } }
                    steps {
                        sh 'npm ci && npm test -- --coverage --reporters=default --reporters=jest-junit'
                        stash name: 'coverage-report', includes: 'coverage/**, reports/**'
                    }
                }
                stage('Secrets Detection') {
                    agent { label 'linux-build' }
                    steps { /* เนื้อหาเดิมจาก Lab 06 */ }
                }
                stage('SAST') {
                    agent { label 'linux-build' }
                    steps { /* รวม ESLint+Semgrep เดิมจาก Lab 06 เป็น sequential ในนี้ หรือ parallel ซ้อนก็ได้ */ }
                }
                stage('SCA — npm audit') {
                    agent { docker { image 'node:20-alpine'; args '-u root' } }
                    steps { /* เนื้อหาเดิมจาก Lab 06 */ }
                }
            }
        }
```

**stage ที่ยังต้อง sequential** (พึ่งพากันจริง ไม่แตะ): `Generate SBOM → Policy Gate` (ต้องมี audit.json ก่อน), `SonarQube Analysis → Quality Gate` (ต้องมี coverage ก่อน), `Terraform Plan → Approval → Apply` (ลำดับตายตัว), `Build Image → Container Scan → Blue/Green Deploy` (ต้องมี image ก่อน)

---

## ขั้นที่ 3 — สร้าง `taskflow-mobile` แบบเร็ว `[CLI]`

```bash
cd ~/Documents/selfproject
flutter create taskflow_mobile
cd taskflow_mobile
git init
git add .
git commit -m "init: default Flutter scaffold app for Lab 10"
git remote add origin https://github.com/Nekokun2004/taskflow-mobile.git
git branch -M main
git push -u origin main
git checkout -b lab10
```
(ถ้าเครื่องไม่มี Flutter SDK ติดตั้งไว้ ข้ามขั้นนี้ได้ — ใช้ `cirruslabs/flutter:stable` container รัน `flutter create` แทนก็ได้เหมือนกัน แค่ mount โฟลเดอร์เข้าไป)

---

## ขั้นที่ 4 — สร้าง keystore ปลอมสำหรับ local testing `[CLI]`

```bash
keytool -genkey -v -keystore lab10-release.keystore \
  -alias lab10key -keyalg RSA -keysize 2048 -validity 10000 \
  -storepass lab10pass -keypass lab10pass \
  -dname "CN=Lab10, OU=Test, O=JenkinsLab, L=Bangkok, S=Bangkok, C=TH"
```
**เขียนในรายงานตรง ๆ:** นี่คือ local testing key ไม่ใช่ production signing key

เก็บ keystore เป็น Jenkins Credential (Secret file):
Manage Jenkins → Credentials → Add → **Secret file** → upload `lab10-release.keystore` → ID: `android-keystore`
เพิ่ม Secret text อีก 2 อัน: `android-keystore-password` = `lab10pass`, `android-key-alias` = `lab10key`

---

## ขั้นที่ 5 — เขียน `Jenkinsfile` สำหรับ `taskflow-mobile` `[CLI]`

```groovy
pipeline {
    agent { docker { image 'cirruslabs/flutter:stable' } }

    stages {
        stage('Flutter Analyze') {
            steps { sh 'flutter analyze' }
        }
        stage('Flutter Test') {
            steps { sh 'flutter test --coverage' }
        }
        stage('SCA — osv-scanner') {
            steps {
                sh '''
                    curl -fsSL https://github.com/google/osv-scanner/releases/latest/download/osv-scanner_linux_amd64 -o osv-scanner
                    chmod +x osv-scanner
                    ./osv-scanner --lockfile=pubspec.lock || true
                '''
            }
        }
        stage('Build Debug APK') {
            steps { sh 'flutter build apk --debug' }
        }
        stage('Build Signed Release AAB') {
            when { branch 'main' }
            steps {
                withCredentials([
                    file(credentialsId: 'android-keystore', variable: 'KEYSTORE_FILE'),
                    string(credentialsId: 'android-keystore-password', variable: 'KEYSTORE_PASSWORD'),
                    string(credentialsId: 'android-key-alias', variable: 'KEY_ALIAS')
                ]) {
                    sh '''
                        cp "$KEYSTORE_FILE" android/app/lab10-release.keystore
                        flutter build appbundle --release \
                          --build-name=1.0.0 \
                          --build-number=${BUILD_NUMBER}
                    '''
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'build/app/outputs/**/*.apk,build/app/outputs/**/*.aab', allowEmptyArchive: true
        }
    }
}
```

> **หมายเหตุ:** การเซ็น AAB จริงต้องแก้ `android/app/build.gradle` ให้อ่าน keystore path/password จาก environment variable ด้วย — ถ้าเวลาไม่พอให้ **บายพาสส่วนนี้**: build แค่ debug APK ให้ผ่าน แล้วเขียนใน Known Limitations ว่า "signed release AAB ยังไม่ครบ เพราะการตั้งค่า Gradle signing config ต้องใช้เวลาเพิ่ม" — ยังได้คะแนนบางส่วนจาก stage ที่เหลือ

สร้าง Jenkins Pipeline job ใหม่ชื่อ `taskflow-mobile-pipeline` ชี้ไปที่ repo/branch นี้

---

## ขั้นที่ 6 — Pipeline Health Gate (เพิ่มใน Jenkinsfile ของ `taskflow-api`) `[CLI]`

เพิ่มก่อน stage `Deploy — Production`:
```groovy
        stage('Pipeline Health Gate') {
            agent { label 'linux-build' }
            steps {
                script {
                    def successRate = sh(
                        script: '''
                            curl -s http://localhost:9090/api/v1/query \
                              --data-urlencode 'query=sum(rate(default_jenkins_builds_success_build_count[1h])) / sum(rate(default_jenkins_builds_last_build_result_ordinal[1h])) * 100' \
                              | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['result'][0]['value'][1] if d['data']['result'] else '100')"
                        ''',
                        returnStdout: true
                    ).trim().toFloat()
                    echo "Rolling build success rate: ${successRate}%"
                    if (successRate < 90) {
                        error("Pipeline Health Gate blocked: success rate ${successRate}% is below 90% threshold")
                    }
                }
            }
        }
```
> **หมายเหตุ:** query PromQL ข้างต้นเป็นตัวอย่าง — **เช็คชื่อ metric จริงจาก `/prometheus` endpoint ก่อน** (ทำไว้แล้วตอน Lab 09 ขั้นที่ 8) แล้วปรับ query ให้ตรงกับชื่อจริงที่เห็น

**พิสูจน์ว่า gate บล็อกจริง:** ลอง fail build 2-3 ครั้งติดกันโดยตั้งใจ (เช่น comment test ออกชั่วคราวแบบที่ทำใน Lab 05) ให้ success rate ตกต่ำกว่า 90% แล้วดูว่า Pipeline Health Gate หยุด deploy จริง — เก็บ log ไว้

---

## ขั้นที่ 7 — Architecture Diagram + Runbook `[CLI]`

เขียนไฟล์ `docs/architecture.md` (1 หน้า, ใช้ Mermaid diagram ง่าย ๆ พอ):

```markdown
# Taskflow CI/CD Architecture

\`\`\`mermaid
graph LR
    A[Push] --> B[Fast Checks: Lint/Test/Secrets/SAST/SCA parallel]
    B --> C[SonarQube Analysis]
    C --> D[Quality Gate]
    D --> E[Generate SBOM]
    E --> F[Policy Gate]
    F --> G[Build Image]
    G --> H[Container Scan]
    H --> I[Blue/Green Deploy]
    I --> J[Pipeline Health Gate]
    J --> K[Deploy Production]

    M[Mobile: Analyze/Test/SCA] --> N[Build APK/AAB]
\`\`\`
```

`docs/rollback-runbook.md`:
```markdown
# Rollback Runbook — Production Deploy Failure

1. เช็ค Jenkins console log ของ build ที่ล้มเหลว หา stage ที่พัง
2. ถ้าพังที่ `Blue/Green Deploy` หรือหลังจากนั้น — `post.failure` จะ auto-rollback Service selector กลับสีเดิมให้เองแล้ว
   ยืนยันด้วย: `kubectl get svc taskflow -o jsonpath='{.spec.selector.color}'`
3. ถ้า auto-rollback ไม่ทำงาน (bug ใน pipeline เอง) ทำ manual:
   `kubectl patch svc taskflow -p '{"spec":{"selector":{"color":"<สีเดิม>"}}}'`
4. เช็คว่า traffic กลับมาที่สีเดิมจริง: `curl http://<service-ip>:8080/health`
5. แจ้งทีมใน Slack/email ว่า rollback แล้ว พร้อมลิงก์ build ที่ fail
6. เปิด incident ticket พร้อม log ที่เกี่ยวข้อง ก่อนจะ retry deploy ใหม่
```

---

## ขั้นที่ 8 — Live Demo `[UI]`

1. Push commit เล็ก ๆ 1 อัน (เช่น เพิ่ม field ใหม่ใน `/api/tasks` response)
2. เปิด Stage View ให้เห็นจอ ไล่อธิบายทีละ stage ตามที่รันจริง
3. **จงใจทำ 1 gate ให้ block สด ๆ** (แนะนำ: comment test ออกให้ Quality Gate หรือ Pipeline Health Gate บล็อก — ทำซ้ำแบบเดียวกับที่พิสูจน์มาแล้วใน Lab 05/06/09)
4. อัดวิดีโอหรือถ่ายทอดสด 10 นาที ตามที่โจทย์ต้องการ

---

## สรุป Deliverables

| # | รายการ | เก็บจากขั้นตอนไหน |
|---|---|---|
| 1 | Jenkinsfile ทั้งคู่ (API + mobile) build เขียว | ขั้นที่ 2, 5 |
| 2 | Architecture diagram + rollback runbook | ขั้นที่ 7 |
| 3 | วิดีโอ/live demo 10 นาที พร้อม gate บล็อกสด | ขั้นที่ 8 |

## เกณฑ์การให้คะแนน

| หัวข้อ | คะแนน |
|---|---|
| Gate ครบทุกแล็บก่อนหน้า จัดลำดับถูก parallelize ตรงจุด | 30 |
| ไม่มี secret ฝังในโค้ดทั้งสอง Jenkinsfile | 15 |
| Mobile pipeline build และ sign ถูกต้อง | 20 |
| Pipeline health gate บล็อก deploy จริงสด ๆ | 15 |
| Runbook เจาะจงใช้งานได้จริง | 10 |
| Live walkthrough ชัดเจนตรงกับพฤติกรรมจริง | 10 |

## ข้อจำกัดที่รู้ตัว (Known Limitations)

- Mobile app เป็น default Flutter scaffold (`flutter create`) ไม่ใช่ UI ของ taskflow จริง — เวลาจำกัดจึงเน้นพิสูจน์ pipeline mechanism แทนการพัฒนา UI
- Signed release AAB อาจไม่ครบ (ต้องแก้ Gradle signing config เพิ่ม) — ถ้าไม่ทันระบุไว้ตรงนี้ว่าทำแค่ debug APK
- ไม่ได้ย้ายทุก stage ไป K8s dynamic agent (สืบทอดข้อจำกัดจาก Lab 09)
- Slack/email notification มีโค้ดเตรียมไว้แต่ไม่ได้ต่อ service จริง (ไม่มี Slack workspace/SMTP server ให้ทดสอบ)
- Keystore เป็น local testing key ไม่ใช่ production signing key
