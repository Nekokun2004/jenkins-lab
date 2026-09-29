# Lab 05 — Automated Testing & Quality Gates

**อ้างอิงจาก:** Deck 09 — Automated Testing in Jenkins
**ระยะเวลา:** 4 ชั่วโมง · **รูปแบบ:** ทำเป็นคู่ (ทำคนเดียวได้ตามความสะดวก)

---

## เป้าหมายของแล็บนี้

1. Publish ผลลัพธ์ JUnit และ coverage แบบ Cobertura จาก pipeline ให้ Jenkins กราฟ trend ได้
2. รัน Playwright E2E suite ยิงใส่ `taskflow-api` ที่รันอยู่ใน Docker จริง (ผ่าน docker compose)
3. บังคับใช้ SonarQube quality gate ที่บล็อก pipeline ถ้า coverage ต่ำกว่าเกณฑ์

## พื้นหลัง

Test ที่รันแล้วแต่ไม่มีใครเห็นผล ไม่ได้ทำให้ pipeline ปลอดภัยขึ้นจริง `junit` และ `publishCoverage` แปลงผลลัพธ์ test ดิบให้กลายเป็นกราฟ trend ที่ Jenkins มองเห็นและ gate ได้ ส่วน quality gate เปลี่ยนความหมายจาก "test ผ่านแล้ว" ให้กลายเป็น "test ผ่านแล้ว **และ** โค้ดได้มาตรฐานที่ตั้งไว้จริง"

---

## ⚠️ สิ่งที่ต้องเตรียมก่อนเริ่ม

### เตรียมที่ 1 — ตั้งค่าระบบให้ SonarQube รันได้ (สำคัญมาก มักพังถ้าข้าม)

SonarQube ใช้ Elasticsearch ข้างในตัวมันเอง ซึ่งต้องการค่า `vm.max_map_count` ของ Linux สูงกว่าค่า default — **ถ้าไม่ตั้งก่อน container จะ crash loop ทันทีตอน start**

```bash
sudo sysctl -w vm.max_map_count=262144
```

(ค่านี้จะหายไปตอน reboot เครื่อง ถ้าอยากให้ถาวรให้เพิ่มบรรทัด `vm.max_map_count=262144` ในไฟล์ `/etc/sysctl.conf` ด้วย — ไม่บังคับสำหรับแล็บนี้)

**รัน SonarQube container:**
```bash
docker run -d --name sonarqube \
  --network host \
  sonarqube:lts-community
```

**รอให้ boot เสร็จ** (ใช้เวลาประมาณ 1-2 นาที) เช็คสถานะด้วย:
```bash
curl -s http://localhost:9000/api/system/status
```
ต้องเห็น `{"status":"UP"}` ถึงจะพร้อมใช้งาน (ถ้าเห็น `STARTING` ให้รอแล้วลองใหม่)

---

### เตรียมที่ 2 — สร้าง SonarQube project + token

1. เปิด browser ไปที่ `http://localhost:9000`
2. Login ด้วย default: username `admin` / password `admin` → ระบบจะบังคับให้เปลี่ยนรหัสผ่านทันที ตั้งรหัสใหม่แล้วจำไว้
3. **Create a local project** → Project key: `taskflow-api`, Display name: `taskflow-api`
4. เลือก **"Locally"** สำหรับวิธี analyze
5. ตั้งชื่อ token เช่น `jenkins-token` → **Generate** → **คัดลอกค่า token ทันที** (เห็นครั้งเดียว)

---

### เตรียมที่ 3 — เพิ่ม `sonar-token` เป็น Jenkins Credential

Manage Jenkins → Credentials → Global → **Add Credentials**
- Kind: **Secret text**
- Secret: วาง token จากเตรียมที่ 2
- ID: `sonar-token`
- **Create**

---

### เตรียมที่ 4 — ตั้งค่า SonarQube server ใน Jenkins + Global Tool ของ sonar-scanner

**ตั้ง SonarQube server:**
Manage Jenkins → System → เลื่อนหา **SonarQube servers** → **Add SonarQube**
- Name: `SonarQube` (ต้องตรงกับที่ Jenkinsfile เรียก `withSonarQubeEnv('SonarQube')` เป๊ะ)
- Server URL: `http://localhost:9000`
- Server authentication token: เลือก credential `sonar-token`
- Save

**ตั้ง Global Tool auto-installer ของ sonar-scanner** (แบบเดียวกับที่ทำ NodeJS/JDK ใน Lab 02):
Manage Jenkins → Tools → เลื่อนหา **SonarQube Scanner installations** → **Add SonarQube Scanner**
- Name: `sonar-scanner-tool`
- ติ๊ก "Install automatically" (จะดาวน์โหลดเวอร์ชันล่าสุดให้เองตอน build)
- Save

**เช็ค plugin ที่จำเป็นก่อน** (ถ้าเคยติดตั้งจาก Lab 02 ไปแล้วข้ามได้เลย): Manage Jenkins → Plugins → Installed → ค้นหา `SonarQube Scanner` ต้องเจอ, ค้นหา `Code Coverage` และ `Cobertura` ต้องเจอทั้งคู่ — ถ้าไม่มี ไปติดตั้งที่ Available plugins ก่อน

---

### เตรียมที่ 5 — อัปเดต agent ให้มี `docker compose`

Unit Test/Lint ใช้ sibling container ปกติอยู่แล้ว แต่ E2E stage ต้องสั่ง `docker compose up -d` จากตัว agent เอง ซึ่ง **`docker-ce-cli` ที่ลงไว้ก่อนหน้านี้ไม่มีคำสั่ง `docker compose` ติดมาด้วย** ต้องเพิ่ม package แยก

แก้ `Dockerfile.agent` เพิ่มบรรทัด `docker-compose-plugin` ต่อจาก `docker-ce-cli`:

```dockerfile
FROM jenkins/inbound-agent:latest-jdk21

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && . /etc/os-release \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && npm --version \
    && node --version \
    && docker --version \
    && docker compose version \
    && rm -rf /var/lib/apt/lists/*

USER jenkins
```

(หมายเหตุ: ปรับให้ใช้ `${VERSION_CODENAME}` จาก `/etc/os-release` แทน hardcode `bookworm` ตามที่แก้ไว้ตอน Lab 03 — คงพฤติกรรมเดิมไว้)

**Build image ใหม่ + รัน agent ใหม่** (ใช้ pattern เดียวกับที่ทำมาตลอด — ลบ container เก่า, build image ใหม่, รันใหม่พร้อม secret ปัจจุบันจากหน้า Jenkins Nodes, อย่าลืม `-v /var/run/docker.sock:/var/run/docker.sock` และ `--group-add 123` ตามที่เจอปัญหาไปตอน Lab 03)

**ตรวจสอบ:**
```bash
docker exec jenkins-agent-linux-build docker compose version
```

---

### เตรียมที่ 6 — เพิ่ม Playwright เข้า repo (ยังไม่มีมาก่อน)

Repo `taskflow-api` ตอนนี้ยังไม่มี Playwright เลย ต้องเพิ่มเอง:

```bash
cd ~/Documents/selfproject/jenkins-lab
npm install --save-dev @playwright/test
```

สร้างไฟล์ `playwright.config.js` ที่ root:

```javascript
module.exports = {
  testDir: './e2e',
  reporter: [
    ['junit', { outputFile: 'playwright-report/junit.xml' }],
    ['html', { outputFolder: 'playwright-report/html', open: 'never' }],
  ],
  use: {
    baseURL: process.env.API_BASE_URL || 'http://localhost:8080',
  },
};
```

สร้างโฟลเดอร์ `e2e/` และไฟล์ `e2e/tasks.spec.js`:

```javascript
const { test, expect } = require('@playwright/test');

test('list tasks returns 200 and an array', async ({ request }) => {
  const res = await request.get('/api/tasks');
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(Array.isArray(body)).toBe(true);
});

test('create task returns 201 with the created task', async ({ request }) => {
  const res = await request.post('/api/tasks', { data: { title: 'E2E test task' } });
  expect(res.status()).toBe(201);
  const body = await res.json();
  expect(body.title).toBe('E2E test task');
  expect(body.done).toBe(false);
});

test('mark task done updates its status', async ({ request }) => {
  const created = await (await request.post('/api/tasks', { data: { title: 'to complete' } })).json();
  const res = await request.patch(`/api/tasks/${created.id}/done`);
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.done).toBe(true);
});
```

เพิ่ม script ใน `package.json` → `scripts`:
```json
"test:e2e": "playwright test"
```

Commit และ push:
```bash
git add package.json package-lock.json playwright.config.js e2e/
git commit -m "add: Playwright E2E specs for Lab 05"
git push origin main
```

---

## ขั้นตอนทั้งหมด — แก้ไข Jenkinsfile

เปิด `Jenkinsfile` แก้ stage `Unit Test` เดิม และเพิ่ม stage ใหม่ต่อจากมัน (ก่อนถึง `Deploy — Staging` ที่มีจาก Lab 04):

```groovy
        stage('Unit Test') {
            steps {
                sh 'npm test -- --coverage --reporters=jest-junit'
            }
        }

        stage('SonarQube Analysis') {
            agent { label 'linux-build' }
            steps {
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
                    docker.image('mcr.microsoft.com/playwright:v1.49.0-noble').inside('--network host') {
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
```

และแก้ `post.always` เดิมของทั้ง pipeline (ตอนท้ายไฟล์) เพิ่ม `junit` กับ `publishCoverage`:

```groovy
        always {
            archiveArtifacts artifacts: 'npm-debug.log*', allowEmptyArchive: true
            junit 'reports/junit.xml'
            publishCoverage adapters: [coberturaAdapter('coverage/cobertura-coverage.xml')]
        }
```

### 📖 อธิบายส่วนที่เพิ่มใหม่

**`sh 'npm test -- --coverage --reporters=jest-junit'`** — เพิ่ม flag `--coverage` (สั่งให้ Jest วัด code coverage ด้วย) และ `--reporters=jest-junit` (สั่งให้ output ผลเป็นไฟล์ XML ที่ Jenkins อ่านได้ แทนที่จะพิมพ์แค่ในเทอร์มินัล) — ทั้งสองอย่างนี้ package.json ของ repo ตั้งไว้ให้เขียนออกที่ `reports/junit.xml` และ `coverage/cobertura-coverage.xml` อยู่แล้วตั้งแต่ scaffold แรกเริ่ม (Lab 01)

**`def scannerHome = tool 'sonar-scanner-tool'`** — เรียก Global Tool auto-installer (เตรียมที่ 4) ให้ดาวน์โหลด/หา path ของ `sonar-scanner` ให้ เก็บ path ไว้ในตัวแปร (เหมือน `tools { nodejs 'node20' }` ใน Lab 02 แต่ต้องใช้ syntax แบบ `tool` ธรรมดาแทน เพราะปลั๊กอิน Sonar ไม่มี key พิเศษใน `tools { }` block)

**`withSonarQubeEnv('SonarQube') { ... }`** — ห่อคำสั่งข้างในด้วย environment variable พิเศษ (เช่น token, URL) ที่ตั้งค่าไว้ในเตรียมที่ 4 โดยอัตโนมัติ ไม่ต้องมาเขียน URL/token เองในคำสั่ง `sonar-scanner`

**`waitForQualityGate abortPipeline: true`** — หลังจากส่งผล scan ไปแล้ว ขั้นนี้จะ **รอ** ให้ SonarQube ประมวลผลเสร็จแล้วเทียบกับเกณฑ์ quality gate ที่ตั้งไว้ — `abortPipeline: true` หมายถึงถ้าผลไม่ผ่าน **ให้ทั้ง pipeline หยุดทันที** (ไม่ใช่แค่เตือนแล้วรันต่อ)

**`docker.image('mcr.microsoft.com/playwright:...').inside('--network host') { ... }`** — วิธีสั่งสร้าง sibling container ข้างในนี้ **ต่างจาก** `agent { docker { image ... } }` ตรงที่มันยืดหยุ่นกว่า: ใช้ได้ตรงกลาง stage ที่มี agent หลักเป็นคนละอย่างอยู่แล้ว (ในที่นี้คือ `linux-build` ที่ต้องสั่ง `docker compose` ก่อน) — `.inside('--network host')` คือส่ง flag เพิ่มเติมตอนสร้าง container ให้มันแชร์ network เดียวกับเครื่องจริง จะได้ยิง request เข้า `localhost:8080` (ที่ `docker compose up` เปิดไว้) ได้ตรง ๆ

**`post.always { sh 'docker compose down -v' ... }`** — ปิด container ที่ compose สร้างไว้ทุกครั้งไม่ว่า test จะผ่านหรือพัง (`-v` ลบ volume ของ Postgres ทิ้งด้วย กัน state ค้างข้ามรอบ) แล้วค่อย publish ผล JUnit/HTML ของ Playwright

---

## ขั้นตอนการทดสอบ (ตามโจทย์ข้อ 4-6)

### ขั้นที่ 4a — ตั้ง Quality Gate ให้ threshold เป็น 70% [UI]

SonarQube's built-in default gate ("Sonar way") is marked BUILT-IN and cannot be edited directly — it already has a "Coverage is less than 80.0%" condition, but you can't change that 80.0 value on the built-in gate itself. You must **copy** it first:

1. In SonarQube, go to **Quality Gates**.
2. Click **Copy** on "Sonar way".
3. Name the copy something like `taskflow-gate-70`.
4. In the copied gate, find the existing **Coverage is less than 80.0%** condition and edit its value down to **70**.
5. Either set this copied gate as the new **Default**, or go to the `taskflow-api` project's own settings and explicitly assign this gate to just that project (safer — doesn't affect other projects).
6. Save.

### ขั้นที่ 4b — จงใจทำให้ coverage ตกต่ำกว่า 70% เพื่อพิสูจน์ว่า gate บล็อกจริง [CLI]

จงใจลบ test ทิ้งบางไฟล์ชั่วคราวให้ coverage ตกต่ำกว่า 70% เช่น comment out เนื้อหาส่วนใหญ่ใน `tests/tasks.test.js` ไว้ก่อน (เก็บสำเนาไว้ ห้ามลบไฟล์จริง จะได้ revert ง่ายในขั้นที่ 6):
```bash
git add tests/tasks.test.js
git commit -m "test: temporarily strip tests to trigger quality gate failure"
git push origin main
```

รัน pipeline → **ควรเห็น pipeline หยุดที่ stage `Quality Gate` ไม่ใช่ที่ `Unit Test`** (เพราะ unit test เองยังผ่านอยู่ แค่ coverage ไม่พอ) — นี่คือสิ่งที่ต้องพิสูจน์ตามโจทย์ข้อ 4 เป๊ะ ๆ

**📸 deliverable:** เก็บ build นี้ไว้เป็น "one red at the gate"

### ขั้นที่ 6 — Revert กลับ ยืนยันทุก gate เขียวพร้อมกัน

```bash
git revert HEAD
git push origin main
```
(หรือ `git checkout` เอาไฟล์ test กลับมาแล้ว commit ใหม่ก็ได้ ผลเหมือนกัน)

รัน pipeline ใหม่ **ควรเห็นทุก stage เขียวในรอบเดียว**: Unit Test → SonarQube Analysis → Quality Gate → E2E — **เก็บ build นี้ไว้เป็น "one green"**

---

## สรุป Deliverables ที่ต้องส่ง

| # | รายการ | เก็บจากขั้นตอนไหน |
|---|---|---|
| 1 | Test-trend graph ที่เห็นอย่างน้อย 2 build (แดง 1 + เขียว 1) | ขั้นที่ 4, 6 |
| 2 | SonarQube quality gate report (export PDF/screenshot) ของ build ที่ผ่าน | ขั้นที่ 6 |
| 3 | Playwright HTML report artifact จาก Jenkins | ขั้นที่ 6 |

## เกณฑ์การให้คะแนน

| หัวข้อ | คะแนน |
|---|---|
| JUnit + coverage publish และ trend ถูกต้อง | 25 |
| Quality gate บล็อก regression จริง (ไม่ใช่แค่ทฤษฎี) | 30 |
| Playwright E2E รันแบบ headless ใน CI และรายงานผลถูกต้อง | 30 |
| Pipeline เขียวครบทุก gate ในรอบเดียวหลังแก้ | 15 |

---

## หมายเหตุ / ข้อควรระวัง

- SonarQube container กิน RAM ค่อนข้างเยอะ (~2GB ขึ้นไป) — ถ้าเครื่องเริ่มอืด เช็ค `docker stats` ดูว่า SonarQube กินไปเท่าไหร่
- `sonar.javascript.lcov.reportPaths=coverage/lcov.info` ใช้ path จาก `coverageReporters: ["text", "cobertura", "lcov"]` ที่ตั้งไว้ใน `package.json` ตั้งแต่ scaffold แรก — ถ้าเคยแก้ jest config ไปเอง ให้เช็คว่ายังมี `lcov` อยู่ในลิสต์ coverageReporters ด้วย ไม่งั้น Sonar จะไม่เห็น coverage เลย
- อย่าลืม `docker compose down -v` ทุกครั้งหลัง E2E ไม่งั้น container/volume ของ Postgres จะค้างสะสมทุก build จนกินพื้นที่ (บทเรียนจากวิกฤตดิสก์เต็มที่เจอมาแล้ว)
