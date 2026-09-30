# Lab 10 — Capstone: End-to-End Pipeline
## รายงานผลการทำแล็บ

**ชื่อผู้ทำ:** _______________________
**วันที่ทำ:** _______________________
**Repository (API):** https://github.com/Nekokun2004/jenkins-lab
**Repository (Mobile):** https://github.com/Nekokun2004/taskflow-mobile
**Branch:** `lab10`

---

## 1. วัตถุประสงค์

1. รวมทุก stage จาก Lab 03-09 เป็น Jenkinsfile เดียว จัด parallel ตรงจุด
2. เพิ่ม pipeline สำหรับ `taskflow-mobile` (Flutter)
3. Live demo — push จริง เดินอธิบายทุก gate

---

## 2. Parallelize + Secrets Check

**สกรีนช็อต — Stage View แสดง stage ที่ parallel กันจริง:**

> _[วางภาพตรงนี้]_

**ผล `grep -R "password\|secret\|token" Jenkinsfile`:**
```
[วางผลลัพธ์ — ต้องไม่มีค่าจริงหลุดออกมา]
```

---

## 3. Mobile Pipeline

**สกรีนช็อต — Jenkins console ของ `taskflow-mobile-pipeline` เขียว:**

> _[วางภาพตรงนี้]_

**Artifact ที่ได้:** ☐ Debug APK ☐ Signed Release AAB (ติ๊กที่ทำได้จริง)

**ถ้า signed AAB ไม่สำเร็จ อธิบายว่าติดตรงไหน:**

> _[เขียนอธิบาย]_

---

## 4. Pipeline Health Gate

**Metric/threshold ที่ใช้:** _______________________

**สกรีนช็อต — console log แสดง gate บล็อก deploy จริง (success rate ต่ำกว่าเกณฑ์):**

> _[วางภาพตรงนี้]_

---

## 5. Architecture & Runbook

**แนบไฟล์ `docs/architecture.md` และ `docs/rollback-runbook.md`:** ☐ แนบแล้ว

---

## 6. Live Demo

**ลิงก์วิดีโอ/บันทึกการ demo:** _______________________
**Gate ที่ block สดในเดโม:** _______________________

---

## 7. สรุป Deliverables

| # | Deliverable | สถานะ |
|---|---|---|
| 1 | Jenkinsfile ทั้งคู่ (API + mobile) build เขียว | ☐ แนบแล้ว |
| 2 | Architecture diagram + rollback runbook | ☐ แนบแล้ว |
| 3 | วิดีโอ/live demo 10 นาที + gate บล็อกสด | ☐ แนบแล้ว |

---

## 8. ปัญหาที่พบระหว่างทำแล็บ (ถ้ามี)

> _[เขียนเฉพาะปัญหาที่เจอจริง พร้อมวิธีแก้]_

---

## 9. ข้อจำกัดที่รู้ตัว (Known Limitations)

- _[เช่น Mobile app เป็น default scaffold, signed AAB ไม่ครบ, notification ไม่ได้ต่อจริง]_
- _[เพิ่มเติมถ้ามี]_

---

## 10. Self-Assessment ตามเกณฑ์คะแนน

| หัวข้อ | คะแนนเต็ม | ประเมินตนเอง | หมายเหตุ |
|---|---|---|---|
| Gate ครบ จัดลำดับถูก parallelize ตรงจุด | 30 | ___ / 30 | |
| ไม่มี secret ฝังในโค้ด | 15 | ___ / 15 | |
| Mobile pipeline build และ sign ถูกต้อง | 20 | ___ / 20 | |
| Pipeline health gate บล็อกจริงสด ๆ | 15 | ___ / 15 | |
| Runbook เจาะจงใช้งานได้จริง | 10 | ___ / 10 | |
| Live walkthrough ชัดเจน | 10 | ___ / 10 | |
| **รวม** | **100** | **___ / 100** | |
