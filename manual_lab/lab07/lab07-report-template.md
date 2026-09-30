# Lab 07 — Containers, Image Scanning & Deployment
## รายงานผลการทำแล็บ

**ชื่อผู้ทำ:** _______________________
**วันที่ทำ:** _______________________
**Repository:** https://github.com/Nekokun2004/jenkins-lab
**Branch:** `lab07`

> 📸 = **REQUIRED SCREENSHOT** (ภาพที่ต้องแนบเพื่อให้ได้คะแนน) · ข้อความที่ไม่มี 📸 เป็นข้อมูลให้กรอก

---

## 1. วัตถุประสงค์

1. Build และ push Docker image ที่มี version tag (Git SHA) จาก pipeline เข้า local registry
2. ไม่ใช้ tag `latest`
3. Scan image ด้วย Trivy
4. Block ช่องโหว่ระดับ HIGH / CRITICAL
5. Deploy บน local Kubernetes cluster (kind)
6. ทำ Blue/Green deployment
7. Smoke test สีใหม่ **ก่อน** สลับ Service
8. Rollback อัตโนมัติเมื่อ deploy ล้มเหลว

---

## 2. Architecture / Environment

| รายการ | ค่า |
|---|---|
| Jenkins job | ___________________ |
| Jenkins agent | `linux-build` (container `jenkins-agent-linux-build`) |
| Docker registry | `registry:2` ชื่อ container `kind-registry` ที่ `localhost:5000` |
| Kubernetes | kind (cluster `taskflow`) เวอร์ชัน ___________________ |
| Kubernetes namespace | ___________________ (default = `default`) |
| Image name | `localhost:5000/taskflow-api` |
| Image tag (build ที่ใช้เป็นหลักฐาน) | ___________________ |
| Active color เริ่มต้น | ___________________ |
| Active color หลัง deploy สำเร็จ | ___________________ |
| Trivy รันด้วย | `aquasec/trivy` เวอร์ชัน ___________________ |

**อธิบายสั้น ๆ ว่า kind node pull image จาก `localhost:5000` ได้อย่างไร (containerd mirror → `kind-registry:5000`):**

> _[เขียนอธิบาย]_

---

## 3. Image Build & Registry

**Git commit (เต็ม):** ___________________
**SHORT_SHA (7 ตัว):** ___________________
**Full image:** `localhost:5000/taskflow-api:___________________`
**Registry:** `localhost:5000` (`registry:2`)

**📸 REQUIRED SCREENSHOT — Jenkins console ของ stage `Build Image` (เห็น `docker push` และ `Verified in registry: ...`):**

> _[วางภาพตรงนี้]_

**Command/output — ยืนยัน tag ใน registry ด้วยคำสั่งอิสระ:**

```
$ curl -fsS http://localhost:5000/v2/taskflow-api/tags/list
```

> _[วางผลลัพธ์ — ต้องเห็น SHORT_SHA และไม่มี `latest`]_

**ตรวจว่าไม่มี `latest`:**

```
$ curl -s http://localhost:5000/v2/taskflow-api/tags/list | grep -c latest
```

> _[วางผลลัพธ์ — ต้องเป็น 0]_

**อธิบายสั้น ๆ: ทำไมใช้ immutable tag (Git SHA) แทน `latest`:**

> _[เขียนอธิบาย]_

---

## 4. Container Scan — Trivy

**Image ที่ scan:** ___________________
**Trivy severity:** ___________________
**Exit code policy:** ___________________ (`--exit-code 1` สำหรับ gate / `--exit-code 0` สำหรับสร้างรายงาน)
**SARIF artifact:** `trivy-report.sarif`

### 4.1 Scan ที่ผ่าน

**📸 REQUIRED SCREENSHOT — console ของ stage `Container Scan` ที่เขียว (ใช้ build เดียวกับหัวข้อ 3 และ 6):**

> _[วางภาพตรงนี้]_

### 4.2 พิสูจน์ว่า Trivy block image ที่มีช่องโหว่ได้จริง (25 คะแนน)

**วิธีทำให้ image มีช่องโหว่:** ___________________ (เช่น เปลี่ยน base เป็น `node:16-alpine`)
**Commit ที่จงใจทำให้พัง:** ___________________
**Exit code ที่ได้จากการรัน local ก่อน push:** ___ (ต้องเป็น 1)

**📸 REQUIRED SCREENSHOT — Jenkins console ของ stage `Container Scan` ที่ **แดง** (เห็นตาราง CVE HIGH/CRITICAL และ `exit code 1`):**

> _[วางภาพตรงนี้]_

**📸 REQUIRED SCREENSHOT — Stage View แสดง `Container Scan` แดง และ `Blue/Green Deploy` ถูกข้าม (ไม่ deploy image ที่ไม่ผ่าน scan):**

> _[วางภาพตรงนี้]_

**Revert แล้ว build กลับมาเขียว (Commit revert):** ___________________

### 4.3 SARIF Artifact

**📸 REQUIRED SCREENSHOT — หน้า Build Artifacts แสดง `trivy-report.sarif` (ควรมีทั้งของ build เขียว และของ build แดงที่ถูก block):**

> _[วางภาพตรงนี้]_

**ส่วนหนึ่งของไฟล์ SARIF (เช่น `tool.driver.name` และจำนวน `results`):**

> _[วางตัวอย่างสั้น ๆ หรือแนบไฟล์]_

**อธิบายสั้น ๆ: ทำไมต้อง block HIGH/CRITICAL และทำไม SARIF ยัง archive ได้แม้ build แดง (รันสองรอบ + `post.always`):**

> _[เขียนอธิบาย]_

---

## 5. Kubernetes Blue/Green Initial State

**Blue image:** ___________________
**Green image:** ___________________
**Current Service selector:** ___________________

**Screenshot/output — `kubectl get deployments -o wide`:**

> _[วางผลลัพธ์]_

**Screenshot/output — `kubectl get pods -l app=taskflow --show-labels`:**

> _[วางผลลัพธ์]_

**📸 REQUIRED SCREENSHOT/OUTPUT — `kubectl get svc taskflow -o yaml` (สถานะเริ่มต้น):**

> _[วางภาพหรือผลลัพธ์ตรงนี้]_

---

## 6. Successful Blue/Green Deployment

### BEFORE

**Current color:** ___________________
**Next color:** ___________________

**📸 REQUIRED SCREENSHOT — Service YAML ก่อนสลับ (`===== Service/taskflow BEFORE =====` ใน console, เห็น `selector.color`):**

> _[วางภาพตรงนี้]_

### Deployment

**New image:** `localhost:5000/taskflow-api:___________________`

**Rollout output (`kubectl rollout status`):**

> _[วาง Console Log]_

**📸 REQUIRED SCREENSHOT — Smoke test ผ่าน และ Service ยังชี้สีเดิมอยู่ตอนนั้น (`Smoke test PASSED on ... (Service still -> ...)`):**

> _[วางภาพตรงนี้]_

### AFTER

**New active color:** ___________________

**📸 REQUIRED SCREENSHOT — Service YAML หลังสลับ (`===== Service/taskflow AFTER =====`, เห็น `selector.color` เปลี่ยน):**

> _[วางภาพตรงนี้]_

**ตรวจอิสระนอก Jenkins:**

```
$ kubectl get svc taskflow -o jsonpath='{.spec.selector.color}'
$ kubectl get endpointslices -l kubernetes.io/service-name=taskflow -o jsonpath='{.items[*].endpoints[*].addresses[*]}'
$ kubectl get pods -l app=taskflow,color=<สีใหม่> -o jsonpath='{.items[*].status.podIP}'
```

> _[วางผลลัพธ์ — IP สองบรรทัดหลังต้องตรงกัน]_

**อธิบายสั้น ๆ: ทำไมต้อง smoke test ก่อนสลับ Service และ smoke test ยิงไปที่ Service ประจำสี (`taskflow-<color>`) ไม่ใช่ `taskflow`:**

> _[เขียนอธิบาย]_

---

## 7. Failed Deployment & Automatic Rollback

**Failure injection method:** ___________________ (เช่น `DEPLOY_FAULT=post-switch-fail`)
**Previous active color:** ___________________
**Target color:** ___________________
**Image/Commit ที่ใช้:** ___________________

**📸 REQUIRED SCREENSHOT — console แสดงความล้มเหลว (curl 404 / rollout timeout / smoke test fail):**

> _[วางภาพตรงนี้]_

**📸 REQUIRED SCREENSHOT — console ของ `post.failure` automatic rollback (เห็น `Rolling Service selector back to: ...`, `Rollback complete. Active color is now: ...`, `Active color remains: ...`):**

> _[วางภาพตรงนี้]_

**Verification หลัง build จบ:**

```
$ kubectl get svc taskflow -o jsonpath='{.spec.selector.color}'
```

> _[วางผลลัพธ์ — ต้องเท่ากับสีเดิมก่อน deploy]_

**Result:** สีเดิม (___________________) ยังรับ traffic อยู่ ☐ ยืนยันแล้ว

**(ถ้าทำเพิ่ม) ผลของโหมด `bad-image`:** ___________________

**อธิบายสั้น ๆ: rollback ทำงานอย่างไร (บันทึก `PREV_COLOR` ไว้ใน `env` ก่อนแก้อะไร, `post.failure` patch selector กลับ) และทำไมจึงใช้ `env.*` แทนตัวแปร `def`:**

> _[เขียนอธิบาย]_

---

## 8. Deliverables Summary

| # | Deliverable | Evidence | Status |
|---|---|---|---|
| 1 | `kubectl get svc taskflow -o yaml` ก่อนและหลัง successful blue/green switch | หัวข้อ 6 (BEFORE / AFTER) | ☐ แนบแล้ว |
| 2 | Trivy SARIF report ของ image build | หัวข้อ 4.3 | ☐ แนบแล้ว |
| 3 | Console log ของ deploy ที่ล้มเหลวและ automatic rollback | หัวข้อ 7 | ☐ แนบแล้ว |

---

## 9. ปัญหาที่พบระหว่างทำแล็บ (ถ้ามี)

> _[เขียนเฉพาะปัญหาที่เจอจริง พร้อมวิธีแก้]_

หัวข้อที่มักเจอ (ใช้เป็นแนวทาง — **ลบที่ไม่เจอจริงออก**):

| ปัญหา | เจอจริงไหม | วิธีแก้ที่ใช้ |
|---|---|---|
| kind node pull จาก `localhost:5000` ไม่ได้ (registry connectivity / hosts.toml / network `kind`) | ☐ เจอ ☐ ไม่เจอ | |
| Pod `ImagePullBackOff` / `ErrImagePull` | ☐ เจอ ☐ ไม่เจอ | |
| Jenkins workspace / Docker mount (phantom bind mount, SARIF ไม่ขึ้น) | ☐ เจอ ☐ ไม่เจอ | |
| Trivy gating (image จริงโดน CVE, DB download, exit code ก่อน archive) | ☐ เจอ ☐ ไม่เจอ | |
| Service selector / ตัวแปร rollback หายใน `post.failure` | ☐ เจอ ☐ ไม่เจอ | |
| อื่น ๆ: ___________________ | | |

---

## 10. ข้อจำกัดที่รู้ตัว (Known Limitations)

- _[เช่น registry เป็น HTTP local ไม่มี auth / tag ไม่ถูกบังคับ immutable ที่ registry]_
- _[เช่น kubectl ติดตั้งด้วย docker cp เข้า agent / kubeconfig เก็บในไฟล์ไม่ใช่ Jenkins Credentials]_
- _[เพิ่มเติมถ้ามี]_

---

## 11. Self-Assessment ตามเกณฑ์คะแนน

| Criterion | Full Score | Self Score | Evidence |
|---|---|---|---|
| Immutable image tag + push | 20 | ___ / 20 | |
| Trivy genuinely blocks vulnerable image | 25 | ___ / 25 | |
| Blue/green + smoke test before switch | 30 | ___ / 30 | |
| Automatic rollback demonstrated | 25 | ___ / 25 | |
| **TOTAL** | **100** | **___ / 100** | |
