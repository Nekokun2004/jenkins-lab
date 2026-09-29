# Lab 05 — Automated Testing & Quality Gates
## รายงานผลการทำแล็บ

**ชื่อผู้ทำ:** _______________________
**วันที่ทำ:** _______________________
**Repository:** https://github.com/Nekokun2004/jenkins-lab

---

## 1. วัตถุประสงค์

1. Publish ผลลัพธ์ JUnit และ coverage (Cobertura) จาก pipeline
2. รัน Playwright E2E suite ยิงใส่ instance ของ `taskflow-api` ที่รันบน Docker จริง
3. บังคับใช้ SonarQube quality gate บล็อก pipeline เมื่อ coverage ต่ำกว่าเกณฑ์

---

## 2. การตั้งค่าเบื้องต้น

**SonarQube URL:** http://localhost:9000
**SonarQube Project Key:** taskflow-api
**Quality Gate coverage threshold ที่ตั้งไว้:** ต่ำกว่า 70% → Fail

---

## 3. ผลการทดสอบ

### 3.1 Test-Trend Graph

**สกรีนช็อต — Test-trend graph แสดงอย่างน้อย 2 build (1 แดงที่ gate, 1 เขียว):**

> _[วางภาพตรงนี้]_

---

### 3.2 Build ที่ Quality Gate บล็อก (coverage ต่ำกว่าเกณฑ์)

**สกรีนช็อต — Console log แสดง pipeline หยุดที่ stage `Quality Gate` (ไม่ใช่ที่ Unit Test):**

> _[วางภาพตรงนี้]_

**สกรีนช็อต — หน้า SonarQube แสดงผล Coverage ที่ต่ำกว่า 70%:**

> _[วางภาพตรงนี้]_

---

### 3.3 SonarQube Quality Gate Report (Build ที่ผ่าน)

**Export/สกรีนช็อต — SonarQube Quality Gate report ของ build ที่ผ่านเกณฑ์:**

> _[วางภาพหรือไฟล์ PDF ตรงนี้]_

---

### 3.4 Playwright E2E Report

**สกรีนช็อต — Jenkins build page แสดง Playwright HTML report เป็น artifact:**

> _[วางภาพตรงนี้]_

**สกรีนช็อต — เปิด Playwright HTML report แสดงผล 3 test (list/create/mark-done) ผ่านหมด:**

> _[วางภาพตรงนี้]_

---

### 3.5 Pipeline เขียวครบทุก Gate ในรอบเดียว

**สกรีนช็อต — Console log / Stage View แสดงทุก stage เขียว (Unit Test → SonarQube Analysis → Quality Gate → E2E):**

> _[วางภาพตรงนี้]_

---

## 4. สรุปผลตาม Deliverables

| # | รายการ | สถานะ |
|---|---|---|
| 1 | Test-trend graph (แดง 1 + เขียว 1) | ☐ แนบแล้ว |
| 2 | SonarQube quality gate report ของ build ที่ผ่าน | ☐ แนบแล้ว |
| 3 | Playwright HTML report artifact | ☐ แนบแล้ว |

---

## 5. ปัญหาที่พบระหว่างทำแล็บ (ถ้ามี)

> _[เขียนสรุปปัญหาที่เจอ และวิธีแก้ — เช่น SonarQube ไม่ยอม start, docker compose network ไม่เจอ API, coverage ไม่ขึ้นใน Sonar ฯลฯ]_

---

## 6. Self-Assessment ตามเกณฑ์คะแนน

| หัวข้อ | คะแนนเต็ม | ประเมินตนเอง | หมายเหตุ |
|---|---|---|---|
| JUnit + coverage publish และ trend ถูกต้อง | 25 | ___ / 25 | |
| Quality gate บล็อก regression จริง | 30 | ___ / 30 | |
| Playwright E2E รันแบบ headless และรายงานถูกต้อง | 30 | ___ / 30 | |
| Pipeline เขียวครบทุก gate ในรอบเดียวหลังแก้ | 15 | ___ / 15 | |
| **รวม** | **100** | **___ / 100** | |
