# Lab 07 — Containers, Image Scanning & Deployment
## รายงานผลการทำแล็บ

**ชื่อผู้ทำ:** _______________________
**วันที่ทำ:** _______________________
**Repository:** https://github.com/Nekokun2004/jenkins-lab
**Branch:** `lab07`

> 📸 = ภาพที่ต้องแคป · ช่อง `____` = ข้อมูลที่ต้องกรอกเอง

---

## 1. วัตถุประสงค์

1. Build และ push Docker image ที่มี version tag (Git SHA) จาก pipeline — ไม่ใช้ `latest`
2. Scan image ด้วย Trivy และ block เมื่อเจอช่องโหว่ระดับ HIGH/CRITICAL
3. Deploy แบบ Blue/Green บน local Kubernetes (kind) โดยสลับ traffic ผ่าน Service selector
4. Rollback อัตโนมัติเมื่อ deploy ล้มเหลว

**สภาพแวดล้อม:** Jenkins job `taskflow-pipeline` (branch `lab07`) · agent `linux-build` · registry `registry:2` ที่ `localhost:5000` · kind v0.33.0 (Kubernetes v1.37.0, cluster `taskflow`, namespace `default`) · Trivy 0.74.0 รันผ่าน Docker

---

## 2. Image Build & Push (ไม่ใช้ `latest`)

**Image tag ที่ใช้เป็นหลักฐาน:** `localhost:5000/taskflow-api:_______________` (SHA 7 ตัว)

📸 **Console ของ stage `Build Image`** (เห็น `docker push` และ `Verified in registry: ...`):

> _[วางภาพตรงนี้]_

**ยืนยันว่าไม่มี `latest` ใน registry:**
```bash
curl -s http://localhost:5000/v2/taskflow-api/tags/list
```
> _[วางผลลัพธ์ — ต้องเห็น SHA และไม่มีคำว่า latest]_

**ทำไมใช้ SHA แทน `latest`:** _[เขียน 1–2 บรรทัด]_

---

## 3. Trivy Container Scan

### 3.1 Scan ที่ผ่าน (เขียว)

📸 **Console ของ stage `Container Scan` ที่เขียว:**

> _[วางภาพตรงนี้]_

📸 **หน้า Artifacts แสดง `trivy-report.sarif`:**

> _[วางภาพตรงนี้]_

### 3.2 พิสูจน์ว่า Trivy บล็อกได้จริง (25 คะแนน)

**วิธีทำให้ image มีช่องโหว่:** _______________________ (เช่น เปลี่ยน base image เป็น `node:16-alpine`)

📸 **Console ของ `Container Scan` ที่แดง** (เห็น exit code 1 และตาราง CVE HIGH/CRITICAL):

> _[วางภาพตรงนี้]_

📸 **Stage View** — `Container Scan` แดง และ `Blue/Green Deploy` ถูกข้าม:

> _[วางภาพตรงนี้]_

☐ revert กลับแล้ว build เขียวตามปกติ

---

## 4. Blue/Green Deployment

**สีก่อน deploy:** _______ → **สีหลัง deploy:** _______

📸 **`kubectl get svc taskflow -o yaml` ก่อนสลับ** (เห็น `selector.color`):

> _[วางภาพหรือผลลัพธ์ตรงนี้]_

📸 **Console log** แสดงลำดับ `set image` → `rollout status` → smoke test ผ่าน → สลับ Service:

> _[วางภาพตรงนี้]_

📸 **`kubectl get svc taskflow -o yaml` หลังสลับ** (`selector.color` เปลี่ยนเป็นสีใหม่):

> _[วางภาพหรือผลลัพธ์ตรงนี้]_

**ทำไม smoke test ต้องทำก่อนสลับ Service:** _[เขียน 1–2 บรรทัด]_

---

## 5. Automatic Rollback เมื่อ Deploy ล้มเหลว

**วิธี inject ความล้มเหลว:** _______________________ (เช่น `DEPLOY_FAULT=post-switch-fail`)

📸 **Console จุดที่ deploy ล้มเหลว** (smoke test fail / rollout timeout):

> _[วางภาพตรงนี้]_

📸 **Console ของ `post.failure`** (เห็น `Rolling back Service selector to ...` และ `Rollback complete. Active color: ...`):

> _[วางภาพตรงนี้]_

**ยืนยันหลัง build จบ — สีเดิมยังรับ traffic:**
```bash
kubectl get svc taskflow -o jsonpath='{.spec.selector.color}'
```
> _[วางผลลัพธ์ — ต้องเท่ากับสีก่อน deploy]_

---

## 6. สรุป Deliverables

| # | Deliverable | สถานะ |
|---|---|---|
| 1 | `kubectl get svc taskflow -o yaml` ก่อนและหลัง switch สำเร็จ | ☐ แนบแล้ว |
| 2 | Trivy SARIF report ของ image build | ☐ แนบแล้ว |
| 3 | Console log ของ deploy ที่ล้มเหลว + automatic rollback | ☐ แนบแล้ว |

---

## 7. ปัญหาที่พบระหว่างทำแล็บ (ถ้ามี)

> _[เขียนเฉพาะปัญหาที่เจอจริง พร้อมวิธีแก้]_

---

## 8. Self-Assessment

| หัวข้อ | เต็ม | ประเมินตนเอง | หมายเหตุ |
|---|---|---|---|
| Image tag แบบ immutable และ push ถูกต้อง | 20 | ___ / 20 | |
| Trivy gate บล็อก image ที่มีช่องโหว่ได้จริง | 25 | ___ / 25 | |
| Blue/green switch + smoke test ก่อนสลับ | 30 | ___ / 30 | |
| Automatic rollback แสดงผลจริง | 25 | ___ / 25 | |
| **รวม** | **100** | **___ / 100** | |
