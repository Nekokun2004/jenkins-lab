# Lab 03 — Your First Declarative Pipeline

**อ้างอิงจาก:** Deck 03, 06, 07 — Pipeline Stages / Jenkinsfile / Examples
**ระยะเวลา:** 3 ชั่วโมง · **รูปแบบ:** ทำคนเดียว

---

## เป้าหมายของแล็บนี้

1. เขียน Jenkinsfile แบบ Declarative Pipeline ที่มีครบ `agent`, `environment`, `stages`, `post`
2. รัน build ข้างใน Docker container (`agent { docker { ... } }`) แทนที่จะรันบน shell ของ controller ตรง ๆ
3. ใช้ `post` block ให้ทำงานต่างกันเมื่อ build สำเร็จ vs ล้มเหลว

## พื้นหลัง

Freestyle job (ที่ทำใน Lab 01) เก็บ config ไว้แค่ในฐานข้อมูลของ Jenkins เอง — ถ้า Jenkins หายไป config ก็หายไปด้วย ตรงข้ามกับ **Jenkinsfile** ที่เก็บอยู่ **ในตัว repo เอง** (เหมือนโค้ดแอปทั่วไป) ทำให้ review ผ่าน pull request ได้เหมือนไฟล์โค้ดอื่น ๆ — นี่คือแก่นของแนวคิด "Pipeline as Code"

---

## ⚠️ สิ่งที่ต้องเตรียมก่อนเริ่ม — อ่านก่อนลงมือ ไม่งั้นจะพังแน่นอน

Lab 03 ให้เขียน:
```groovy
agent { docker { image 'node:20-alpine' } }
```

บรรทัดนี้แปลว่า **"ให้ agent สร้าง Docker container ใหม่ขึ้นมาอีกตัวหนึ่ง (image `node:20-alpine`) แล้วรันทุก stage ข้างในนั้น"**

**ปัญหาคือ:** agent `linux-build` ของเรา **เป็น Docker container อยู่แล้ว** (สร้างจาก `jenkins-agent-node20` ที่เราต่อยอดจาก `jenkins/inbound-agent`) — พอมันต้องไป "สร้าง container ใหม่ซ้อนอีกที" (เรียกว่า **Docker-in-Docker / sibling containers**) มันต้องมี 2 อย่างเพิ่มเติมที่ container `linux-build` **ยังไม่มีตอนนี้**:

1. **Docker CLI** ติดตั้งอยู่ข้างใน container `linux-build` (ตอนนี้มีแค่ Java + Node.js ที่เราลงไปตอน Lab 01-02)
2. **สิทธิ์เข้าถึง Docker socket ของเครื่องจริง** (`/var/run/docker.sock`) ผ่าน mount เข้าไปตอนรัน container

ถ้าไม่แก้ก่อน พอรัน Pipeline job จะเจอ error ประมาณ `docker: not found` หรือ `permission denied` ตอนที่ Jenkinsfile พยายามสั่ง `docker run` ข้างใน agent

### วิธีแก้ — อัปเดต `Dockerfile.agent` แล้วรัน agent ใหม่

แก้ไฟล์ `Dockerfile.agent` (ไฟล์เดิมที่มี Node.js อยู่แล้ว) ให้เพิ่มการติดตั้ง Docker CLI เข้าไปด้วย:

```dockerfile
FROM jenkins/inbound-agent:latest-jdk21

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && npm --version \
    && node --version \
    && docker --version \
    && rm -rf /var/lib/apt/lists/*

USER jenkins
```

**อธิบายส่วนที่เพิ่มเข้ามา (Docker CLI installation):**
- `curl ... | gpg --dearmor -o ...` → ดาวน์โหลด public key ของ Docker มาเก็บไว้ เพื่อให้ `apt` เชื่อถือ package ที่จะติดตั้งจาก repository ของ Docker ได้ (ไม่งั้น apt จะปฏิเสธเพราะไม่รู้จักแหล่งที่มา)
- `echo "deb [...] https://download.docker.com/..." > /etc/apt/sources.list.d/docker.list` → เพิ่ม Docker's official apt repository เข้าไปในลิสต์แหล่งโหลด package ของระบบ (เพราะ Debian ปกติไม่มี `docker-ce-cli` ใน repository เริ่มต้น)
- `apt-get install -y docker-ce-cli` → ติดตั้ง**แค่ตัว CLI** (`docker` command) ไม่ได้ติดตั้ง Docker daemon เต็มรูปแบบ (เพราะเราจะยืมใช้ daemon ของเครื่องจริงผ่าน socket แทน ไม่ต้องรัน daemon ซ้อนอีกชั้น)
- `docker --version` → บรรทัดตรวจสอบตอน build ว่าติดตั้งสำเร็จจริง (จะเห็นเวอร์ชันขึ้นมาตอน build ถ้าไม่มี error)

**Build image ใหม่:**
```bash
docker build -t jenkins-agent-node20 -f Dockerfile.agent .
```

**ลบ agent container เดิมทิ้งก่อนสร้างใหม่:**
```bash
docker rm -f jenkins-agent-linux-build
```

**รัน agent ใหม่ — จุดสำคัญคือเพิ่ม `-v /var/run/docker.sock:/var/run/docker.sock`:**
```bash
docker run -d --name jenkins-agent-linux-build \
  --network host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  jenkins-agent-node20 \
  -url http://localhost:8080/ \
  -secret <ใส่ secret ปัจจุบันจากหน้า Jenkins Nodes> \
  -name "linux-build" \
  -workDir "/home/jenkins/agent"
```

**อธิบาย:** `-v /var/run/docker.sock:/var/run/docker.sock` คือการเอา "ท่อสื่อสาร" ที่ Docker daemon ของเครื่องจริงฟังอยู่ มา mount เข้าไปให้ container `linux-build` มองเห็นและคุยกับมันได้โดยตรง — พอ Jenkinsfile สั่ง `docker run node:20-alpine`, คำสั่งนั้นจะไปสั่ง Docker daemon ของ**เครื่องจริง**ให้สร้าง container ใหม่ (ซึ่งจะไปโผล่เป็น container "พี่น้อง" ข้าง ๆ `linux-build` เอง ไม่ใช่ container ซ้อนข้างในของมัน — นี่คือที่มาของคำว่า "sibling containers")

**ตรวจสอบว่าใช้งานได้จริง:**
```bash
docker exec jenkins-agent-linux-build docker ps
```
ถ้าเห็นลิสต์ container ของเครื่องจริงโผล่ขึ้นมา (รวมถึง container `jenkins`, `jenkins-agent-linux-build` เอง) แปลว่าเชื่อมต่อสำเร็จ พร้อมใช้งานแล้ว

---

## ขั้นตอนทั้งหมด

### ขั้นที่ 1 — เพิ่ม Jenkinsfile ในโฟลเดอร์ local clone ของ repo `[CLI]`

หา path ของ local clone repo (ที่ Jenkins job ดึงโค้ดจาก URL เดียวกัน) ถ้าจำ path ไม่ได้:
```bash
find ~ -maxdepth 5 -iname "jenkins-lab" -type d 2>/dev/null
```

เข้าไปที่โฟลเดอร์นั้น:
```bash
cd ~/<path-ที่เจอ>
```

สร้างไฟล์ `Jenkinsfile` (ไม่มีนามสกุล ตัว J ใหญ่ ตรงตามชื่อที่ Jenkins คาดหวัง):
```bash
nano Jenkinsfile
```
(หรือใช้ text editor ที่ถนัด — `code Jenkinsfile`, `vim Jenkinsfile` ก็ได้)

วางโค้ดนี้ทั้งหมด:

```groovy
pipeline {
    agent { docker { image 'node:20-alpine' } }

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
            steps {
                sh 'npm ci'
            }
        }
        stage('Lint') {
            steps {
                sh 'npm run lint'
            }
        }
        stage('Unit Test') {
            steps {
                sh 'npm test'
            }
        }
    }

    post {
        success {
            echo "✅ ${env.APP_NAME} passed on ${env.NODE_ENV}"
        }
        failure {
            echo "❌ Failed at stage: ${env.STAGE_NAME}"
        }
        always {
            archiveArtifacts artifacts: 'npm-debug.log*', allowEmptyArchive: true
        }
    }
}
```

บันทึกไฟล์ (ถ้าใช้ nano: `Ctrl+O` แล้ว `Enter` เพื่อ save, `Ctrl+X` เพื่อออก)

---

### 📖 อธิบายโค้ดทุกบรรทัดแบบละเอียด

```groovy
pipeline {
```
คำสั่งเปิดของ **Declarative Pipeline** ทุกอย่างข้างในวงเล็บปีกกานี้คือนิยามของ pipeline ทั้งตัว (ต่างจาก Scripted Pipeline ที่จะเริ่มด้วย `node {` และเขียนอิสระกว่า)

```groovy
    agent { docker { image 'node:20-alpine' } }
```
บอก Jenkins ว่า **ทุก stage** ข้างในนี้ (เว้นแต่จะไประบุ `agent` ใหม่ในระดับ stage) ให้รันข้างใน container ที่สร้างจาก image `node:20-alpine` — เพราะ image นี้มี Node.js 20 ติดตั้งมาให้แล้วในตัว (ไม่ต้องพึ่ง Global Tool auto-installer ของ Lab 02 ในไฟล์นี้เลย เป็นคนละวิธีแก้ปัญหาเดียวกัน)

```groovy
    environment {
        APP_NAME = 'taskflow-api'
        NODE_ENV = 'test'
    }
```
ประกาศตัวแปร environment 2 ตัว ที่จะมองเห็นได้จากทุก stage ผ่าน `env.APP_NAME` และ `env.NODE_ENV` — เหมือนตั้ง environment variable ใน shell ทั่วไป แต่ Jenkins จัดการ scope ให้อัตโนมัติ (มีผลแค่ใน pipeline นี้ ไม่หลุดไปกระทบ job อื่น)

```groovy
    options {
        timeout(time: 10, unit: 'MINUTES')
    }
```
`options` คือที่ตั้งค่าพฤติกรรมของทั้ง pipeline (ไม่ใช่ตัวงานจริง) — `timeout(time: 10, unit: 'MINUTES')` บอกว่า **ถ้า pipeline นี้รันเกิน 10 นาที ให้ Jenkins ฆ่าทิ้งอัตโนมัติ** ป้องกันเคสที่คำสั่งค้าง (เช่น `npm test` ค้างรอ input ที่ไม่มีวันมา) แล้วไปจับ executor ตัวเดียวไว้ตลอดกาล ทำให้ build อื่นที่รอคิวอยู่ไม่มีวันได้รันเลย

```groovy
    stages {
        stage('Install') {
            steps {
                sh 'npm ci'
            }
        }
```
`stages` คือกล่องรวม stage ทั้งหมด แต่ละ `stage('ชื่อ')` คือหนึ่งขั้นตอนที่แสดงเป็นกล่องแยกใน Blue Ocean/Stage View — `steps { sh '...' }` คือคำสั่งจริงที่รันข้างใน stage นั้น (`sh` แปลว่ารันเป็นคำสั่ง shell ธรรมดา)

`npm ci` (ต่างจาก `npm install`) คือคำสั่งติดตั้ง dependency แบบ**เป๊ะตรงตาม `package-lock.json` เท่านั้น** ไม่ปรับเวอร์ชันให้เอง — เหมาะกับ CI เพราะได้ผลลัพธ์เดิมทุกครั้งไม่ว่าจะรันกี่รอบ

```groovy
        stage('Lint') {
            steps {
                sh 'npm run lint'
            }
        }
        stage('Unit Test') {
            steps {
                sh 'npm test'
            }
        }
    }
```
สอง stage ถัดมาเรียก script ที่ตั้งไว้ใน `package.json` ของ `taskflow-api` อยู่แล้ว (`npm run lint` → เรียก eslint, `npm test` → เรียก jest) — ไม่ต้องแก้อะไรเพิ่มเพราะ repo scaffold เตรียม script พวกนี้ไว้ให้ครบตั้งแต่ Lab 01

```groovy
    post {
        success {
            echo "✅ ${env.APP_NAME} passed on ${env.NODE_ENV}"
        }
```
`post` คือ block ที่ทำงาน**หลัง**ทุก stage จบแล้ว (ไม่ว่าผลจะเป็นอะไร) — `success { }` มีผลแค่ตอน **ทุก stage ผ่านหมด** เท่านั้น ข้างในใช้ string interpolation แบบ Groovy (`"${...}"`) ดึงค่าตัวแปร environment ที่ตั้งไว้ด้านบนมาพิมพ์

```groovy
        failure {
            echo "❌ Failed at stage: ${env.STAGE_NAME}"
        }
```
`failure { }` มีผลเมื่อ**มี stage ไหนก็ตามล้มเหลว** — `env.STAGE_NAME` เป็นตัวแปรพิเศษที่ Jenkins set ให้อัตโนมัติ เก็บชื่อ stage ล่าสุดที่กำลังรันตอนที่เกิดความล้มเหลว (มีประโยชน์มากตอน debug ว่าพังที่ไหน โดยไม่ต้องไล่อ่าน log ทั้งหมด)

```groovy
        always {
            archiveArtifacts artifacts: 'npm-debug.log*', allowEmptyArchive: true
        }
    }
}
```
`always { }` ทำงาน**ทุกครั้งไม่ว่าผลจะเป็นอย่างไร** (สำเร็จ, ล้มเหลว, หรือถูก abort) — `archiveArtifacts` คือสั่งให้ Jenkins เก็บไฟล์ที่ตรงกับ pattern (`npm-debug.log*`) แนบไปกับผลลัพธ์ของ build นั้นให้ดาวน์โหลดย้อนหลังได้ `allowEmptyArchive: true` สำคัญมาก เพราะปกติแล้วจะไม่มีไฟล์ `npm-debug.log` เกิดขึ้นเลยถ้า build ผ่าน (npm สร้าง log ไฟล์นี้เฉพาะตอน error) — ถ้าไม่ใส่ flag นี้ Jenkins จะ mark build เป็น **unstable** ทุกครั้งที่หาไฟล์ตาม pattern ไม่เจอ ทั้งที่จริง ๆ คือเรื่องปกติ

---

### ขั้นที่ 2 — Commit และ push ขึ้น GitHub `[CLI]`

```bash
git add Jenkinsfile
git commit -m "add: Jenkinsfile for Lab 03 declarative pipeline"
git push origin main
```

(ถ้า branch หลักของ repo คุณชื่ออื่นที่ไม่ใช่ `main` ให้เปลี่ยนตรงคำสั่งสุดท้ายให้ตรง — เช็คด้วย `git branch` ถ้าไม่แน่ใจ)

---

### ขั้นที่ 3 — สร้าง Pipeline job ใหม่ใน Jenkins `[UI]`

**ห้ามใช้ job `taskflow-smoke` เดิม** (อันนั้นเป็น Freestyle) — ต้องสร้าง job ใหม่แยกต่างหาก:

1. หน้า Dashboard → **New Item**
2. ตั้งชื่อ เช่น `taskflow-pipeline`
3. เลือกประเภท **Pipeline** (ไม่ใช่ Freestyle project) → **OK**
4. เลื่อนหาส่วน **Pipeline** ด้านล่างของหน้า config
5. **Definition** → เปลี่ยนจาก "Pipeline script" (ค่า default ที่ให้พิมพ์โค้ดตรง ๆ ในกล่อง) เป็น **"Pipeline script from SCM"**
6. **SCM** → เลือก **Git**
7. **Repository URL** → ใส่ URL repo เดียวกับที่ `taskflow-smoke` ใช้ (เช่น `https://github.com/Nekokun2004/jenkins-lab.git`)
8. **Branches to build → Branch Specifier** → ใส่ `*/main` (แก้เป็น `*/master` ถ้า repo คุณใช้ branch นั้นแทน — จำจากบทเรียน Lab 01 ได้ว่าเคยเจอปัญหานี้มาแล้ว)
9. **Script Path** → ใส่ `Jenkinsfile` (ค่า default อยู่แล้ว ปกติไม่ต้องแก้ ถ้าไฟล์อยู่ที่ root ของ repo)
10. **Save**

---

### ขั้นที่ 4 — รันครั้งแรก `[UI]`

กด **Build Now** ที่ job `taskflow-pipeline`

**ผลลัพธ์ที่ควรเห็นถ้าทุกอย่างถูกต้อง (console log):**
```
[Pipeline] Start of Pipeline
[Pipeline] node
Running on linux-build in ...
[Pipeline] { (Install)
+ npm ci
added 445 packages
[Pipeline] { (Lint)
+ npm run lint
[Pipeline] { (Unit Test)
+ npm test
Tests: 7 passed, 7 total
[Pipeline] echo
✅ taskflow-api passed on test
Finished: SUCCESS
```

---

### ขั้นที่ 5 — จงใจทำให้ build แดง เพื่อพิสูจน์ `post.failure` `[CLI + UI]`

**[CLI]** แก้ไฟล์ test ตัวใดตัวหนึ่งในเครื่อง local ให้ fail โดยตั้งใจ เช่นแก้ `tests/health.test.js`:
```bash
nano tests/health.test.js
```
เปลี่ยนบรรทัด:
```javascript
expect(res.status).toBe(200);
```
เป็น:
```javascript
expect(res.status).toBe(999); // จงใจทำให้ fail สำหรับ Lab 03
```

Commit และ push:
```bash
git add tests/health.test.js
git commit -m "test: intentionally break health test for Lab 03 failure demo"
git push origin main
```

**[UI]** กลับไป Jenkins → กด **Build Now** ที่ `taskflow-pipeline` อีกครั้ง

**ควรเห็น:** build หยุดที่ stage **Unit Test** (สีแดง), console log มีบรรทัด `❌ Failed at stage: Unit Test` โผล่มาจาก `post.failure` — **นี่คือ deliverable ที่ต้องแคปเก็บไว้** (console log ของ build แดงพร้อมข้อความ post ที่ถูกต้อง)

---

### ขั้นที่ 6 — แก้กลับให้เขียว เพื่อพิสูจน์ `post.success` `[CLI + UI]`

**[CLI]** แก้กลับเป็นค่าเดิม:
```bash
nano tests/health.test.js
```
เปลี่ยน `toBe(999)` กลับเป็น `toBe(200)` แล้ว push:
```bash
git add tests/health.test.js
git commit -m "test: revert intentional break, restore passing health test"
git push origin main
```

**[UI]** กด **Build Now** อีกครั้ง

**ควรเห็น:** build ผ่านหมดทุก stage (เขียว), console log มีบรรทัด `✅ taskflow-api passed on test` — **นี่คือ deliverable อีกอันที่ต้องแคปเก็บไว้** (console log ของ build เขียว)

---

## สรุป Deliverables ที่ต้องส่ง

| # | รายการ | เก็บจากขั้นตอนไหน |
|---|---|---|
| 1 | Jenkinsfile ที่ merge เข้า branch main ของ repo แล้ว | ขั้นที่ 1-2 |
| 2 | Console log ของ build แดง พร้อมข้อความ post.failure ที่ถูกต้อง | ขั้นที่ 5 |
| 3 | Console log ของ build เขียว พร้อมข้อความ post.success ที่ถูกต้อง | ขั้นที่ 6 |

## เกณฑ์การให้คะแนน

| หัวข้อ | คะแนน |
|---|---|
| Jenkinsfile รันได้ถูกต้องข้างใน Docker agent | 30 |
| ใช้และ interpolate environment variable ถูกต้อง | 15 |
| post block แต่ละอันทำงานตรงเงื่อนไข | 35 |
| คำอธิบายเหตุผลของ timeout สมเหตุสมผล (คอมเมนต์ในโค้ด) | 20 |

---

## หมายเหตุ / ข้อควรระวัง

- **ปัญหา Docker-in-Docker ที่แก้ไว้ตอนต้นแล็บนี้ จะมีผลต่อเนื่องไปถึง Lab 07** (build/scan/deploy container image) เพราะฉะนั้น agent ที่อัปเดตแล้วตอนนี้จะใช้งานได้ยาว ๆ ไม่ต้องแก้ซ้ำอีก
- ถ้าย้ายเครื่องอีกรอบในอนาคต ต้องจำไว้ว่า `Dockerfile.agent` เวอร์ชันล่าสุด (ที่มีทั้ง Node.js + Docker CLI) คือตัวที่ต้องใช้ build ใหม่ ไม่ใช่เวอร์ชันแรกที่มีแค่ Node.js
- เวลาแก้ไฟล์ทดสอบให้ fail ตั้งใจ (ขั้นที่ 5) ห้ามลืม revert กลับ (ขั้นที่ 6) ไม่งั้น repo จะค้างอยู่ในสถานะ test พังไปเรื่อย ๆ กระทบแล็บถัดไป
