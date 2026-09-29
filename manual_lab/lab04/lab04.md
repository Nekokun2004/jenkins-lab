# Lab 04 — Git, GitHub & Multibranch Pipelines

**อ้างอิงจาก:** Deck 08 — Integrating with Git & GitHub
**ระยะเวลา:** 3 ชั่วโมง · **รูปแบบ:** ทำคนเดียว

---

## เป้าหมายของแล็บนี้

1. ตั้ง GitHub webhook ให้ push โค้ดแล้ว trigger Jenkins build เองอัตโนมัติ (ไม่ต้องกด Build Now)
2. ตั้ง Multibranch Pipeline ที่ scan repo แล้วสร้าง pipeline แยกให้ทุก branch และทุก PR โดยอัตโนมัติ
3. ใช้ `when { branch }` gate stage Deploy ให้ทำงานตาม branch strategy จริง (feature → develop → main)

## พื้นหลัง

ทีมงานจริงไม่นั่งกด "Build Now" เอง — push โค้ดแล้ว Jenkins ต้องรู้เองทันที Multibranch Pipeline job จะ scan repo แล้วสร้าง pipeline ของตัวเองให้ทุก branch/PR โดยอัตโนมัติ ทุกอันใช้ Jenkinsfile เดียวกัน แต่พฤติกรรมต่างกันไปตาม `when` condition

---

## ⚠️ สิ่งที่ต้องเตรียมก่อนเริ่ม

### เตรียมที่ 1 — รวม branch `lab03` เข้า `main` ก่อน

ตอนนี้ Jenkinsfile มีอยู่แค่ใน branch `lab03` เท่านั้น (จาก Lab 03) แต่ Lab 04 ต้องการให้ **`main` เป็น branch หลักที่มี Jenkinsfile อยู่แล้ว** เพื่อให้ Multibranch Pipeline discover เจอ และให้ `develop`/`feature/*` แตกออกมาจาก `main` ได้ถูกต้อง

```bash
cd ~/Documents/selfproject/jenkins-lab
git checkout main
git pull origin main
git merge lab03
git push origin main
```

**ถ้าเจอ merge conflict:** เกิดได้เพราะ `main` อาจมีอะไรบางอย่างที่ `lab03` ไม่มี (หรือกลับกัน) — ส่ง error ที่เจอมาดูได้เลย ไม่ต้องแก้เดา

**ตรวจสอบว่า `main` มี Jenkinsfile แล้วจริง:**
```bash
git show main:Jenkinsfile | head -5
```
ควรเห็นบรรทัด `pipeline {` โผล่มา ไม่ error ว่าไฟล์ไม่มี

---

### เตรียมที่ 2 — สร้าง GitHub Personal Access Token (PAT)

Multibranch Pipeline ที่จะ discover PR ต้องเรียก GitHub API ซึ่งต้องมี token ถึงจะไม่โดน rate limit และเห็น PR ได้

1. ไปที่ GitHub → คลิกรูปโปรไฟล์มุมขวาบน → **Settings**
2. เลื่อนลงซ้ายมือ หา **Developer settings** (อยู่ล่างสุด)
3. **Personal access tokens → Tokens (classic)** → **Generate new token (classic)**
4. ตั้งชื่อ เช่น `jenkins-multibranch`
5. เลือก scope: ติ๊ก **`repo`** (ทั้งกลุ่ม) กับ **`admin:repo_hook`** (ให้ Jenkins จัดการ webhook ให้อัตโนมัติได้ในขั้นถัดไป)
6. **Generate token** → **คัดลอกค่า token ทันที** (เห็นครั้งเดียว)

---

### เตรียมที่ 3 — ติดตั้ง ngrok เพื่อ expose Jenkins ออกอินเทอร์เน็ต

Jenkins รันอยู่ที่ `localhost:8080` ซึ่ง GitHub (อยู่บนอินเทอร์เน็ต) เรียกเข้ามาไม่ได้เลย ต้องมี tunnel เจาะออกไป

**ติดตั้ง ngrok (Debian):**
```bash
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
  | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
  | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok
```

**สมัครบัญชี ngrok ฟรี** ที่ https://ngrok.com แล้วเอา authtoken จากหน้า dashboard มาผูก:
```bash
ngrok config add-authtoken <YOUR_AUTHTOKEN>
```

**รัน tunnel ชี้ไปที่ port 8080:**
```bash
ngrok http 8080
```

จะเห็นหน้าจอค้างอยู่แบบนี้ (**ห้ามปิด terminal นี้** ต้องปล่อยรันค้างไว้ตลอดที่ทำแล็บ):
```
Forwarding    https://xxxx-xxx-xxx-xxx-xxx.ngrok-free.app -> http://localhost:8080
```

**คัดลอก URL ที่ขึ้นต้นด้วย `https://` นั้นเก็บไว้** — จะใช้ทั้งตอนตั้ง webhook และตอนตั้งค่า Jenkins URL

**อัปเดต Jenkins URL ให้ตรงกับ ngrok:**
Manage Jenkins → System → **Jenkins Location** → Jenkins URL → เปลี่ยนจาก `http://localhost:8080/` เป็น URL ngrok ที่ได้มา (ต่อท้ายด้วย `/`) → Save

---

### เตรียมที่ 4 — ติดตั้ง plugin GitHub Branch Source

Multibranch Pipeline แบบธรรมดา (Git source) จะเห็นแค่ branch ไม่เห็น PR — ต้องใช้ **GitHub Branch Source** เพื่อ discover ทั้งคู่

Manage Jenkins → Plugins → Available plugins → ค้นหา **`GitHub Branch Source`** → ติ๊ก → Install (ถ้าเจอในลิสต์ Installed อยู่แล้วจากการติดตั้งพวก plugin dependency ของ Blue Ocean ตอน Lab 02 ก็ข้ามได้เลย เช็คใน Installed plugins ก่อน)

---

### เตรียมที่ 5 — เพิ่ม GitHub token เป็น Jenkins Credential

Manage Jenkins → Credentials → System → Global credentials → **Add Credentials**
- Kind: **Username with password**
- Username: username GitHub ของคุณ (เช่น `Nekokun2004`)
- Password: วาง PAT ที่คัดลอกมาจากเตรียมที่ 2
- ID: `github-pat`
- **Create**

---

## ขั้นตอนทั้งหมด

### ขั้นที่ 1 — ตั้ง GitHub Webhook `[UI]`

ไปที่หน้า repo บน GitHub → **Settings → Webhooks → Add webhook**
- **Payload URL:** `<ngrok-url>/github-webhook/` (เช่น `https://xxxx.ngrok-free.app/github-webhook/` — **ต้องมี `/` ปิดท้าย**)
- **Content type:** `application/json`
- **Which events:** เลือก **"Let me select individual events"** → ติ๊ก **Pushes** และ **Pull requests**
- **Add webhook**

GitHub จะยิง ping ทดสอบทันที — เลื่อนลงมาดูใน **Recent Deliveries** ควรเห็น response **200**

**📸 deliverable ข้อ 1:** สกรีนช็อตหน้า Recent Deliveries ที่เห็น response 200

---

### ขั้นที่ 2 — สร้าง Multibranch Pipeline `[UI]`

หน้า Dashboard → **New Item** → ตั้งชื่อ `taskflow-multibranch` → เลือกประเภท **Multibranch Pipeline** → **OK**

ในหน้า config:
- **Branch Sources → Add source → GitHub**
- **Credentials** → เลือก `github-pat` ที่สร้างไว้
- **Repository HTTPS URL** → ใส่ URL repo (`https://github.com/Nekokun2004/jenkins-lab.git` หรือของคุณ)
- **Behaviours** → ค่า default มักมี "Discover branches" กับ "Discover pull requests from origin" อยู่แล้ว ปล่อยไว้ตามเดิม
- **Scan Multibranch Pipeline Triggers** → ติ๊ก **"Periodically if not otherwise run"** ตั้งเป็น 1 minute (กันเหนียวเผื่อ webhook มาไม่ทัน)
- **Save**

Jenkins จะเริ่ม scan ทันที — รอสักครู่แล้วดูว่าเจอ branch `main` (และ `lab03` ถ้ายังไม่ลบ) ขึ้นมาเป็น pipeline ย่อยในลิสต์

---

### ขั้นที่ 3 — สร้าง branch `develop`, `feature/health-endpoint` + แก้ Jenkinsfile `[CLI]`

```bash
cd ~/Documents/selfproject/jenkins-lab
git checkout main
git checkout -b develop
git push origin develop

git checkout main
git checkout -b feature/health-endpoint
```

แก้ไฟล์ `Jenkinsfile` เพิ่ม 2 stage ใหม่ต่อจาก `stage('Unit Test')` (ก่อนปิด `stages {`):

```groovy
        stage('Deploy — Staging') {
            when { branch 'develop' }
            steps {
                sh 'echo deploying to staging...'
            }
        }
        stage('Deploy — Production') {
            when { branch 'main' }
            input {
                message 'Deploy to production?'
            }
            steps {
                sh 'echo deploying to production...'
            }
        }
```

### 📖 อธิบายโค้ดส่วนที่เพิ่มใหม่

```groovy
stage('Deploy — Staging') {
    when { branch 'develop' }
```
`when { branch 'develop' }` คือเงื่อนไขที่ทำให้ **stage นี้รันก็ต่อเมื่อ pipeline run นี้มาจาก branch ชื่อ `develop` เท่านั้น** — ถ้า Multibranch Pipeline กำลังรัน pipeline ของ branch `feature/health-endpoint` หรือ `main` มันจะ**ข้าม stage นี้ไปเลย** (ไม่ error ไม่ fail แค่ข้ามไปเฉย ๆ เห็นเป็นกล่องสีเทาใน Blue Ocean)

```groovy
stage('Deploy — Production') {
    when { branch 'main' }
    input {
        message 'Deploy to production?'
    }
```
เหมือนกันแต่ผูกกับ `main` แทน — จุดต่างคือมี `input { message '...' }` เพิ่มมา ซึ่งจะทำให้ pipeline **หยุดรอ** ตรงนี้ ขึ้นข้อความถามใน UI ว่า "Deploy to production?" พร้อมปุ่ม **Proceed / Abort** ให้กดยืนยัน — pipeline จะไม่รันคำสั่งจริง (`sh 'echo deploying...'`) จนกว่าจะมีคนกด Proceed ก่อน (นี่คือ **manual approval gate** ที่โจทย์ต้องการให้พิสูจน์ในขั้นที่ 6)

Commit และ push branch `feature/health-endpoint`:
```bash
git add Jenkinsfile
git commit -m "add: deploy staging/production stages with branch gates"
git push origin feature/health-endpoint
```

---

### ขั้นที่ 4 — Push ไป `feature/health-endpoint` แล้วเช็คว่า webhook trigger เอง `[UI]`

เนื่องจากเพิ่ง push ไปแล้วในขั้นที่ 3 — กลับไปที่หน้า Jenkins **โดยไม่ต้องกด Build Now เอง**

รอสัก 10-30 วินาที (หรือน้อยกว่านั้นถ้า webhook ทำงานทันที) แล้ว refresh หน้า job `taskflow-multibranch`

**ควรเห็น:**
- มี pipeline ย่อยใหม่ชื่อ `feature%2Fhealth-endpoint` (หรือแสดงเป็น `feature/health-endpoint`) ขึ้นมาเอง พร้อม build #1 กำลังรัน/รันเสร็จแล้ว **โดยที่คุณไม่ได้กด Build Now เลย**
- เปิดดู console log ของ build นั้น ต้องเห็นว่า stage `Deploy — Staging` และ `Deploy — Production` **ถูกข้าม** (แสดงเป็นสีเทา ไม่ใช่เขียว) เพราะ branch ปัจจุบันไม่ใช่ทั้ง `develop` และ `main`

**📸 deliverable:** เก็บภาพนี้ไว้เป็นหลักฐาน "webhook trigger เอง"

---

### ขั้นที่ 5 — เปิด Pull Request จาก `feature/health-endpoint` เข้า `develop` `[UI]`

ไปที่ GitHub → repo → จะเห็นแบนเนอร์เสนอให้สร้าง PR จาก branch ที่เพิ่ง push ไป (`feature/health-endpoint`) → คลิก **Compare & pull request**
- **base:** `develop` (เปลี่ยนจาก default `main`)
- **compare:** `feature/health-endpoint`
- **Create pull request**

กลับไปที่ Jenkins → `taskflow-multibranch` — ควรเห็น pipeline ย่อยใหม่ประเภท **PR** โผล่ขึ้นมาแยกต่างหาก (มักจะแสดงชื่อเป็น `PR-1` หรือคล้ายกัน) ซึ่งเป็นคนละอันกับ pipeline ของ branch `feature/health-endpoint` เอง — นี่คือสิ่งที่ GitHub Branch Source plugin ทำให้พิเศษกว่า Git source ธรรมดา

---

### ขั้นที่ 6 — Merge เข้า `develop` แล้ว `main` เพื่อพิสูจน์ deploy gate `[CLI + UI]`

**Merge PR เข้า develop** (ทำผ่าน GitHub UI: กด **Merge pull request** ในหน้า PR ที่เปิดไว้)

กลับไป Jenkins รอ webhook trigger build ของ branch `develop` เอง → เปิด console log

**ควรเห็น:** stage `Deploy — Staging` **รันจริง** (เขียว, มีบรรทัด `deploying to staging...`) โดย**ไม่มีการหยุดรอ approve ใด ๆ** เพราะไม่มี `input` block ผูกกับ stage นี้

**Merge `develop` เข้า `main`:**
```bash
git checkout main
git pull origin main
git merge develop
git push origin main
```

กลับไป Jenkins รอ webhook trigger build ของ branch `main` → เปิด console log

**ควรเห็น:** pipeline วิ่งมาถึง stage `Deploy — Production` แล้ว **ค้างรอ** ขึ้นข้อความ "Deploy to production?" พร้อมปุ่ม **Proceed** ให้กด (build จะค้างอยู่ตรงนี้จนกว่าจะกด) — กด **Proceed** แล้วดู console log ต่อว่าโผล่บรรทัด `deploying to production...` ตามมา

**📸 deliverable:** เก็บภาพตอนที่ build ค้างรอ input (ก่อนกด Proceed) ไว้เป็นหลักฐานว่า production gate ทำงานจริง

---

## สรุป Deliverables ที่ต้องส่ง

| # | รายการ | เก็บจากขั้นตอนไหน |
|---|---|---|
| 1 | สกรีนช็อต GitHub webhook delivery log แสดง response 200 | ขั้นที่ 1 |
| 2 | Diagram 1 หน้า แสดง branch strategy (feature → develop → main) พร้อม annotate ว่า stage ไหนรันที่ branch ไหน | สรุปจากทั้งแล็บ (ดูโครงร่างใน `lab04-report-template.md`) |

## เกณฑ์การให้คะแนน

| หัวข้อ | คะแนน |
|---|---|
| Webhook trigger build เองโดยไม่ต้องกด Build Now | 25 |
| Multibranch job discover branch และ PR ถูกต้อง | 25 |
| `when` condition gate แต่ละ deploy stage ถูกต้อง | 30 |
| Production input gate ทำงานตามที่ออกแบบไว้ | 20 |

---

## หมายเหตุ / ข้อควรระวัง

- **ngrok free tier เปลี่ยน URL ทุกครั้งที่รันใหม่** — ถ้าปิด terminal ที่รัน `ngrok http 8080` ไปแล้วเปิดใหม่ จะได้ URL ใหม่ ต้องกลับไปแก้ทั้ง GitHub webhook payload URL และ Jenkins Location ใหม่ทั้งคู่
- ถ้า webhook ไม่ trigger อัตโนมัติ ให้เช็คที่ GitHub → Settings → Webhooks → คลิกเข้า webhook นั้น → ดู Recent Deliveries ว่า response เป็น 200 จริงไหม (ถ้าเป็น timeout/refused แปลว่า ngrok tunnel หลุดหรือ URL เปลี่ยนไปแล้ว)
- `input` step จะทำให้ executor ของ agent ถูกจับค้างไว้ตลอดเวลาที่รอคนกด Proceed — ถ้าลืมกด อาจไปบล็อก build อื่นที่ต้องการ executor เดียวกัน (ย้อนกลับไปแนวคิดเรื่อง `timeout` ที่เรียนใน Lab 03)
