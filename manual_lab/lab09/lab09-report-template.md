# Lab 09 — Jenkins on Kubernetes: Dynamic Agents & Pipeline Metrics
## รายงานผลการทำแล็บ

**ชื่อผู้ทำ:** _______________________
**วันที่ทำ:** _______________________
**Repository:** https://github.com/Nekokun2004/jenkins-lab
**Branch:** `lab09`

---

## 1. วัตถุประสงค์

1. ให้ Jenkins agent รันเป็น Kubernetes pod ชั่วคราวแทน container ที่ตั้งค้างไว้
2. เปิด metrics ของ Jenkins ให้ Prometheus scrape ได้ + มี dashboard
3. ตั้ง SLO + alert แล้วพิสูจน์ว่าทำงานจริงตอนโหลดหนัก

---

## 2. Kubernetes Dynamic Agent

**Kubernetes URL ที่ตั้งไว้:** _______________________
**Stage ที่ย้ายไปใช้ K8s pod:** _______________________ (เช่น Install, Lint, Unit Test)

**Diff Jenkinsfile (agent เดิม → agent ใหม่):**

> _[วางโค้ด before/after ตรงนี้]_

**สกรีนช็อต/Terminal output — `kubectl get pods -w` แสดง pod เกิดและหายไปจริงตอน build:**

> _[วางภาพหรือ log ตรงนี้]_

---

## 3. Prometheus + Grafana

**สกรีนช็อต — `/prometheus` endpoint แสดง metrics จริง:**

> _[วางภาพตรงนี้]_

**Grafana Dashboard JSON (3 panel):**

> _[แนบไฟล์ .json หรือวางเนื้อหาโดยย่อ]_

**สกรีนช็อต — หน้า Dashboard ที่เห็นทั้ง 3 panel:**

> _[วางภาพตรงนี้]_

---

## 4. SLO / Alert

**SLO ที่ตั้ง:** _______________________ (เช่น 95% ของ build เสร็จภายใน 6 นาที)
**Alert condition:** _______________________

**สกรีนช็อต — Alert สถานะ Firing ตอนโหลดหนัก (saturation):**

> _[วางภาพตรงนี้]_

**สกรีนช็อต — Alert กลับเป็น Normal หลังแก้ capacity:**

> _[วางภาพตรงนี้]_

**วิธี saturate ที่ใช้:** _______________________ (เช่น concurrency=1, trigger 2-3 build พร้อมกัน)

---

## 5. สรุป Deliverables

| # | Deliverable | สถานะ |
|---|---|---|
| 1 | Diff Jenkinsfile (Docker agent → K8s pod template) | ☐ แนบแล้ว |
| 2 | Grafana dashboard JSON (3 panel) | ☐ แนบแล้ว |
| 3 | Screenshot alert Firing + กลับ Normal | ☐ แนบแล้ว |

---

## 6. ปัญหาที่พบระหว่างทำแล็บ (ถ้ามี)

> _[เขียนเฉพาะปัญหาที่เจอจริง พร้อมวิธีแก้]_

---

## 7. ข้อจำกัดที่รู้ตัว (Known Limitations)

- _[เช่น ย้ายแค่บาง stage ไป K8s pod, ใช้ Grafana alerting แทน Alertmanager, saturation สเกลเล็ก]_
- _[เพิ่มเติมถ้ามี]_

---

## 8. Self-Assessment ตามเกณฑ์คะแนน

| หัวข้อ | คะแนนเต็ม | ประเมินตนเอง | หมายเหตุ |
|---|---|---|---|
| Build รันบน K8s pod จริง ยืนยันสด ๆ | 30 | ___ / 30 | |
| Prometheus metrics scrape + dashboard ถูกต้อง | 25 | ___ / 25 | |
| SLO/Alert ตั้งตาม symptom ถูกต้อง | 20 | ___ / 20 | |
| Saturation + recovery แสดงผลจริง | 25 | ___ / 25 | |
| **รวม** | **100** | **___ / 100** | |
