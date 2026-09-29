# Lab 06 — Shift-Left Security Pipeline
## รายงานผลการทำแล็บ

**ชื่อผู้ทำ:** _______________________
**วันที่ทำ:** _______________________
**Repository:** https://github.com/Nekokun2004/jenkins-lab

---

## 1. วัตถุประสงค์

1. รัน secrets detection, SAST, SCA ก่อน stage build ตามลำดับ Secrets → SAST → SCA
2. สร้างและเก็บ SBOM ที่ลงลายเซ็นแล้ว
3. ใช้ fail/warn threshold policy แทนการ gate แบบ all-or-nothing

---

## 2. ลำดับ Stage ที่ implement

| ลำดับ | Stage | เครื่องมือ |
|---|---|---|
| 1 | Secrets Detection | Gitleaks |
| 2 | SAST | ESLint (security plugin) + Semgrep |
| 3 | SCA — npm audit | npm audit + jq (fail/warn threshold) |
| 4 | Generate SBOM | Syft + Cosign |
| 5 | Policy Gate | Open Policy Agent (OPA) |

---

## 3. ผลการทดสอบ

### 3.1 Secrets Detection — พิสูจน์ว่า Gitleaks จับ fake secret ได้

**Branch ที่ใช้ทดสอบ (scratch, ไม่ merge):** `lab06-secrets-test`

**สกรีนช็อต/ไฟล์ — Gitleaks report แสดงผลจับ fake AWS key ได้:**

> _[วางภาพหรือแนบไฟล์ gitleaks-report.json ตรงนี้]_

---

### 3.2 SAST Reports

**สกรีนช็อต — ESLint SARIF report เป็น artifact:**

> _[วางภาพตรงนี้]_

**สกรีนช็อต — Semgrep SARIF report เป็น artifact:**

> _[วางภาพตรงนี้]_

---

### 3.3 SCA — Fail/Warn Threshold Logic

**สกรีนช็อต — Console log แสดง SCA stage ผ่าน (0 critical, warning อนุญาตให้ผ่าน):**

> _[วางภาพตรงนี้]_

**คำอธิบายสั้น ๆ ว่า logic ทำงานอย่างไร (ไม่ใช่แค่ exit-code):**

> _[เขียนอธิบาย]_

---

### 3.4 Signed SBOM

**สกรีนช็อต — Jenkins artifacts แสดง `.cdx.json`, `.sig`, `cosign.pub`:**

> _[วางภาพตรงนี้]_

**เนื้อหาบางส่วนของ SBOM (ตัวอย่าง component ที่พบ):**

> _[วางตัวอย่างเนื้อหาโดยย่อ]_

---

### 3.5 Policy Gate — Block และ Un-block

**ไฟล์ `policy/security.rego`:**
```rego
package security

deny[msg] {
    input.metadata.vulnerabilities.critical > 0
    msg := sprintf("Blocked: %d CRITICAL vulnerabilities found", [input.metadata.vulnerabilities.critical])
}

default allow = false

allow {
    count(deny) == 0
}
```

**Dependency ที่ downgrade เพื่อทดสอบ:** _______________________ (ระบุชื่อ + เวอร์ชัน)

**สกรีนช็อต — Console log แสดง Policy Gate บล็อก (มี CVE):**

> _[วางภาพตรงนี้]_

**สกรีนช็อต — Console log แสดง Policy Gate ผ่าน (หลัง revert):**

> _[วางภาพตรงนี้]_

---

## 4. สรุปผลตาม Deliverables

| # | รายการ | สถานะ |
|---|---|---|
| 1 | Gitleaks report ที่จับ fake secret ได้ | ☐ แนบแล้ว |
| 2 | Signed SBOM (.cdx.json + .sig) เป็น build artifact | ☐ แนบแล้ว |
| 3 | ไฟล์ policy/security.rego + log block + log ผ่าน | ☐ แนบแล้ว |

---

## 5. ปัญหาที่พบระหว่างทำแล็บ (ถ้ามี)

> _[เขียนสรุปปัญหาที่เจอ และวิธีแก้]_

---

## 6. ข้อจำกัดที่รู้ตัว (Known Limitations)

- Cosign key generate ใหม่ทุก build (ไม่ persist ข้าม build) — ในระบบจริงควรเก็บ private key ไว้ใน credential store ถาวร
- _[เพิ่มเติมถ้ามี]_

---

## 7. Self-Assessment ตามเกณฑ์คะแนน

| หัวข้อ | คะแนนเต็ม | ประเมินตนเอง | หมายเหตุ |
|---|---|---|---|
| ลำดับ stage ถูกต้อง: secrets → SAST → SCA → SBOM → policy | 25 | ___ / 25 | |
| Fail/warn threshold logic ถูกต้อง | 25 | ___ / 25 | |
| SBOM สร้าง, sign, archive ครบ | 25 | ___ / 25 | |
| Policy gate บล็อกและปลดบล็อกได้จริง | 25 | ___ / 25 | |
| **รวม** | **100** | **___ / 100** | |
