# Lab 04 — Git, GitHub & Multibranch Pipelines
## รายงานผลการทำแล็บ

**ชื่อผู้ทำ:** _______________________
**วันที่ทำ:** _______________________
**Repository:** https://github.com/Nekokun2004/jenkins-lab

---

## 1. วัตถุประสงค์

แล็บนี้มีเป้าหมาย 3 ข้อ:
1. ตั้งค่า GitHub webhook ให้ Jenkins build อัตโนมัติทุกครั้งที่มีการ push โค้ด
2. ตั้งค่า Multibranch Pipeline ให้ discover branch และ pull request โดยอัตโนมัติ
3. ใช้ `when { branch }` gate stage การ deploy ให้ตรงกับ branch strategy จริง

---

## 2. ขั้นตอนการดำเนินงาน

### 2.1 ตั้งค่า GitHub Webhook

**Payload URL ที่ใช้:** _______________________ (URL จาก ngrok)

**สกรีนช็อต — GitHub Webhook Recent Deliveries (ต้องเห็น response 200):**

> _[วางภาพตรงนี้]_

---

### 2.2 สร้าง Multibranch Pipeline Job

**ชื่อ job:** `taskflow-multibranch`

**สกรีนช็อต — หน้า Multibranch Pipeline แสดง branch ที่ discover เจอ (main, develop, feature/health-endpoint):**

> _[วางภาพตรงนี้]_

---

### 2.3 การแก้ไข Jenkinsfile — เพิ่ม Deploy Stages

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

---

### 2.4 Push ไปยัง `feature/health-endpoint` — พิสูจน์ Webhook Trigger อัตโนมัติ

**สกรีนช็อต — Build ที่ถูก trigger เองจาก webhook (ไม่ได้กด Build Now):**

> _[วางภาพตรงนี้]_

**สกรีนช็อต — Console log แสดงว่า Deploy stages ทั้งสองถูกข้าม (สีเทา):**

> _[วางภาพตรงนี้]_

---

### 2.5 เปิด Pull Request (`feature/health-endpoint` → `develop`)

**สกรีนช็อต — Jenkins แสดง pipeline แยกสำหรับ PR:**

> _[วางภาพตรงนี้]_

---

### 2.6 Merge เข้า `develop` — พิสูจน์ Deploy — Staging ทำงานโดยไม่ต้อง Approve

**สกรีนช็อต — Console log stage `Deploy — Staging` รันสำเร็จ (เขียว):**

> _[วางภาพตรงนี้]_

---

### 2.7 Merge เข้า `main` — พิสูจน์ Production Input Gate

**สกรีนช็อต — Build ค้างรอที่ input step "Deploy to production?" (ก่อนกด Proceed):**

> _[วางภาพตรงนี้]_

**สกรีนช็อต — Console log หลังกด Proceed แสดง `deploying to production...`:**

> _[วางภาพตรงนี้]_

---

## 3. Branch Strategy Diagram

**Diagram 1 หน้า แสดง feature → develop → main พร้อม annotate ว่า stage ใดรันที่ branch ใด:**

> _[วางภาพ diagram ตรงนี้ — หรือวาดด้วยมือ/เครื่องมือ diagram แล้ว export เป็นรูป]_

**คำอธิบาย diagram (เขียนสรุปสั้น ๆ ประกอบภาพ):**

| Branch | Stage ที่รัน | ต้อง Approve หรือไม่ |
|---|---|---|
| `feature/*` | Install, Lint, Unit Test เท่านั้น | ไม่มี deploy stage ให้ approve |
| `develop` | Install, Lint, Unit Test, **Deploy — Staging** | ไม่ต้อง approve |
| `main` | Install, Lint, Unit Test, **Deploy — Production** | **ต้อง approve** (input gate) |

---

## 4. สรุปผลตาม Deliverables

| # | รายการ | สถานะ |
|---|---|---|
| 1 | สกรีนช็อต webhook delivery แสดง response 200 | ☐ แนบแล้ว |
| 2 | Diagram branch strategy พร้อม annotation | ☐ แนบแล้ว |

---

## 5. ปัญหาที่พบระหว่างทำแล็บ (ถ้ามี)

> _[เขียนสรุปปัญหาที่เจอ และวิธีแก้ — เช่น ngrok URL เปลี่ยน, webhook ไม่ trigger, merge conflict ฯลฯ]_

---

## 6. Self-Assessment ตามเกณฑ์คะแนน

| หัวข้อ | คะแนนเต็ม | ประเมินตนเอง | หมายเหตุ |
|---|---|---|---|
| Webhook trigger build เองโดยไม่ต้องกด Build Now | 25 | ___ / 25 | |
| Multibranch job discover branch และ PR ถูกต้อง | 25 | ___ / 25 | |
| `when` condition gate แต่ละ deploy stage ถูกต้อง | 30 | ___ / 30 | |
| Production input gate ทำงานตามที่ออกแบบไว้ | 20 | ___ / 20 | |
| **รวม** | **100** | **___ / 100** | |
