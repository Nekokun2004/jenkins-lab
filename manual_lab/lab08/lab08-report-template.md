# Lab 08 — Infrastructure as Code in the Pipeline
## รายงานผลการทำแล็บ

**ชื่อผู้ทำ:** _______________________
**วันที่ทำ:** _______________________
**Repository:** https://github.com/Nekokun2004/jenkins-lab
**Branch:** `lab08`

---

## 1. วัตถุประสงค์

1. เขียน Terraform provision environment ให้ `taskflow-api` พร้อม remote state
2. Lint + security-scan IaC ก่อน `plan`, gate `apply` ด้วย human approval
3. ใช้ Ansible ตั้งค่า host ที่ Terraform สร้างไว้

**Cloud provider ที่ใช้:** LocalStack (local) / _______________________ (ถ้าใช้ cloud จริง ระบุ)

---

## 2. Remote State

**Backend ที่ใช้:** S3-compatible (LocalStack) / _______________________
**Bucket name:** _______________________

**ยืนยันว่าไม่มี local state หลุดเข้า git:**
```bash
git ls-files | grep -i tfstate
```
> _[วางผลลัพธ์ — ต้องไม่มี output อะไรเลย]_

---

## 3. tfsec / Checkov — Before/After

**Finding ที่เจอ (ก่อนแก้):** _______________________ (เช่น security group เปิด 0.0.0.0/0)

**สกรีนช็อต — console/output แสดง finding ก่อนแก้ (แดง):**

> _[วางภาพตรงนี้]_

**วิธีแก้:** _______________________

**สกรีนช็อต — console/output แสดงว่าผ่านหลังแก้ (เขียว):**

> _[วางภาพตรงนี้]_

---

## 4. Approval Gate

**สกรีนช็อต — หน้า input prompt แสดงเนื้อหา Terraform plan ก่อนกด Apply:**

> _[วางภาพตรงนี้]_

**สกรีนช็อต — console log ของ `Terraform Apply` แสดง instance address ที่ output:**

> _[วางภาพตรงนี้]_

**Instance address ที่ได้:** _______________________

---

## 5. Ansible Configuration

**Host ที่ Ansible ตั้งค่า:** _______________________ (ระบุถ้าใช้ localhost แทน เพราะข้อจำกัดของ LocalStack/cloud — อธิบายสั้น ๆ)

**สกรีนช็อต — console log ของ stage `Configure with Ansible` แสดง task ที่ผ่านหมด (โดยเฉพาะ `docker pull`):**

> _[วางภาพตรงนี้]_

**พิสูจน์ idempotency (รันซ้ำรอบสอง `changed=0`):** ☐ ทำแล้ว

---

## 6. Destroy

**ผลลัพธ์ `terraform show` หลัง destroy (ต้องว่าง):**

> _[วางผลลัพธ์ตรงนี้]_

---

## 7. สรุป Deliverables

| # | Deliverable | สถานะ |
|---|---|---|
| 1 | Terraform + Ansible source files, `tfplan` artifact | ☐ แนบแล้ว |
| 2 | Before/after tfsec หรือ Checkov output | ☐ แนบแล้ว |
| 3 | Screenshot approval prompt + applied output (instance address) | ☐ แนบแล้ว |

---

## 8. ปัญหาที่พบระหว่างทำแล็บ (ถ้ามี)

> _[เขียนเฉพาะปัญหาที่เจอจริง พร้อมวิธีแก้]_

---

## 9. ข้อจำกัดที่รู้ตัว (Known Limitations)

- _[เช่น LocalStack ไม่มี instance จริงให้ SSH เข้า — ใช้ ansible_connection=local แทน]_
- _[เพิ่มเติมถ้ามี]_

---

## 10. Self-Assessment ตามเกณฑ์คะแนน

| หัวข้อ | คะแนนเต็ม | ประเมินตนเอง | หมายเหตุ |
|---|---|---|---|
| Remote state ตั้งถูกต้อง ไม่มี local state หลุดเข้า git | 20 | ___ / 20 | |
| tfsec/Checkov findings ถูก triage และแก้จริง | 25 | ___ / 25 | |
| Apply ถูก gate ด้วย human approval จริง | 20 | ___ / 20 | |
| Ansible playbook ตั้งค่า host สำเร็จ | 25 | ___ / 25 | |
| Destroy สะอาด ไม่มี resource ค้าง | 10 | ___ / 10 | |
| **รวม** | **100** | **___ / 100** | |
