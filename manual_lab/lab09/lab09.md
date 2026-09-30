# Lab 09 — Jenkins on Kubernetes: Dynamic Agents & Pipeline Metrics

**อ้างอิงจาก:** Deck 04, 00e — Jenkins Architecture / Site Reliability Engineering
**ระยะเวลา:** 4 ชั่วโมง (ทำแบบย่อ ตามแผน checkpoint ที่ตกลงกันไว้)

---

## เป้าหมายของแล็บนี้

1. ให้ Jenkins สร้าง build agent เป็น Kubernetes pod ชั่วคราวแทน container ที่ตั้งค้างไว้
2. เปิด metrics ของ Jenkins เองให้ Prometheus scrape ได้ และมี dashboard ดู
3. ตั้ง SLO ของ pipeline เอง แล้วพิสูจน์ว่า alert ทำงานจริงตอนโหลดหนัก

## ⚠️ แผนย่อสำหรับเวลาที่จำกัด (ตกลงกันไว้แล้ว)

| งาน | ระดับที่ทำ | เหตุผล |
|---|---|---|
| K8s dynamic agent | **เต็มรูปแบบ** | Lab 10 ต้องใช้ต่อ, พิสูจน์ยากถ้าไม่ทำจริง |
| Prometheus + Grafana | **เบา** — 2 container docker-compose, 3 panel ง่าย ๆ, ไม่ใช้ Alertmanager แยก | ใช้ **Grafana's built-in alerting** แทน (Grafana 8+ มี alert engine ในตัว ไม่ต้องตั้ง Alertmanager) |
| SLO/Saturation demo | **สเกลเล็ก** — concurrency=1, trigger 2-3 build พร้อมกัน (ไม่ใช่ 10) | ยังคง "แสดงผลจริง" ตามที่โจทย์ต้องการ แค่ตัวเลขเล็กลง |

---

## ⚠️ การตัดสินใจสำคัญ — Jenkins Controller ↔ kind Cluster เชื่อมกันยังไง

**ปัญหาเดียวกับที่เจอตอน SonarQube (Lab 05)** — Jenkins **controller** อยู่ bridge network ส่วน kind cluster (`taskflow-control-plane`) อยู่ใน Docker network ชื่อ `kind` (คนละ network กัน) การตั้งค่า **Kubernetes Cloud** ทำที่ระดับ controller (Manage Jenkins → Clouds) ไม่ใช่ agent — controller เลยต้อง**เข้าถึง API server ของ kind ให้ได้ก่อน**

**ทางแก้ที่ง่ายและตรงที่สุด:** เอา container `jenkins` เข้าไปอยู่ใน network `kind` เพิ่มอีกอัน (ไม่ลบ network เดิม แค่เพิ่ม):
```bash
docker network connect kind jenkins
```
พอทำแบบนี้ Jenkins controller จะคุยกับ `taskflow-control-plane:6443` ได้ตรง ๆ ด้วยชื่อ container เลย (Docker จัดการ DNS ให้อัตโนมัติในเครือข่ายเดียวกัน) — ไม่ต้องเดา IP อะไรทั้งนั้น

**เรื่อง TLS certificate:** kind ใช้ self-signed cert — แทนที่จะเสียเวลา import CA cert เข้า Jenkins credential ให้ติ๊ก **"Disable https certificate check"** ในหน้า Kubernetes Cloud config ไปเลย (bypass ตามหลักที่ตกลงกันไว้ ไม่กระทบความถูกต้องของแล็บ)

**เรื่อง pod เรียกกลับหา Jenkins (JNLP):** pod ที่เกิดขึ้นชั่วคราวต้องต่อกลับมาที่ Jenkins controller — ใช้ **`http://172.17.0.1:8080/`** (bridge gateway IP แบบเดียวกับที่ใช้แก้ปัญหา SonarQube) เป็นค่า "Jenkins URL" ใน Kubernetes Cloud config

> **[ยังไม่ได้ทดสอบบนเครื่องนี้]** ค่า `172.17.0.1` น่าจะใช้ได้เพราะ pattern เดียวกับที่ยืนยันแล้วตอน SonarQube แต่เป็นคนละ network path (ผ่าน nested container ของ kind) — ถ้า pod ขึ้นมาแล้วแต่ **ไม่ต่อกลับ Jenkins** (ดูจาก build ค้างที่ "Still waiting to schedule task" ทั้งที่ pod มีอยู่จริงใน `kubectl get pods`) ให้เช็ค gateway ที่แท้จริงของ network `kind` แทน:
> ```bash
> docker network inspect kind --format '{{(index .IPAM.Config 0).Gateway}}'
> ```
> แล้วเอาค่านั้นมาใส่แทน `172.17.0.1`

---

## สิ่งที่ต้องรู้ก่อนเริ่ม

| ข้อเท็จจริง | ผลกับ Lab 09 |
|---|---|
| kind cluster ถูก `docker stop` ไว้หลัง Lab 08 | ต้อง `docker start` ก่อน |
| SonarQube ก็ถูก stop ไว้เหมือนกัน | ไม่จำเป็นสำหรับ Lab 09 ปล่อยหยุดไว้ต่อ ประหยัด RAM |
| agent (`jenkins-agent-linux-build`) ใช้ `--network host` | ใช้ทดสอบ `kubectl` แบบเดิมได้เหมือน Lab 07 |
| Jenkinsfile ปัจจุบันมีหลาย stage `agent { docker {...} }` | **แผนย่อ: แก้แค่ stage ที่เป็น `node:20-alpine` ล้วน ๆ** (Install, Lint, Unit Test) ให้เป็น K8s pod — stage อื่นที่ซับซ้อน (SonarQube, E2E, Terraform ฯลฯ) **ปล่อยไว้บน `linux-build` เหมือนเดิม** เขียนเป็น known limitation |

---

## ขั้นที่ 1 — รี Start kind cluster `[CLI]`

```bash
docker start taskflow-control-plane
sleep 10
docker exec jenkins-agent-linux-build kubectl get nodes
```
ต้องเห็นสถานะ `Ready`

---

## ขั้นที่ 2 — เชื่อม Jenkins controller เข้า network `kind` `[CLI]`

```bash
docker network connect kind jenkins
docker exec jenkins getent hosts taskflow-control-plane
```
ควรเห็น IP ตอบกลับมา (ยืนยันว่า resolve ชื่อ container ได้แล้ว)

---

## ขั้นที่ 3 — สร้าง branch `lab09` `[CLI]`

```bash
git checkout lab08
git pull origin lab08
git checkout -b lab09
```

---

## ขั้นที่ 4 — ติดตั้ง plugin `[UI]`

Manage Jenkins → Plugins → Available → ติ๊กเลือกทั้งคู่:
- **Kubernetes** (ถ้ายังไม่มีจาก Lab 02)
- **Prometheus metrics**

Install → restart ถ้าถาม

---

## ขั้นที่ 5 — ตั้งค่า Kubernetes Cloud `[UI]`

Manage Jenkins → Clouds → **Add a new cloud** → **Kubernetes**
- **Kubernetes URL:** `https://taskflow-control-plane:6443`
- ติ๊ก **Disable https certificate check**
- **Jenkins URL:** `http://172.17.0.1:8080/` (หรือ gateway IP จริงถ้าค่านี้ใช้ไม่ได้)
- กด **Test Connection** — ต้องขึ้น "Connection test successful"

เลื่อนลง **Pod Templates → Add Pod Template**
- **Name:** `k8s-node`
- **Labels:** `k8s-node`
- **Containers → Add Container:**
  - Name: `node`
  - Image: `node:20-alpine`
  - Command to run: `cat`
  - Allocate pseudo-TTY: ✅ (ติ๊ก)
- Save

---

## ขั้นที่ 6 — แก้ Jenkinsfile ให้ 3 stage แรกใช้ K8s pod `[CLI]`

แก้เฉพาะ `Install` และ 2 sub-stage ใน `Checks` (`Lint`, `Unit Test`) จาก:
```groovy
agent { docker { image 'node:20-alpine' } }
```
เป็น:
```groovy
agent {
    kubernetes {
        yaml '''
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: node
    image: node:20-alpine
    command: ['cat']
    tty: true
'''
    }
}
```
(3 จุดในไฟล์ — ทำเหมือนกันทุกจุด)

**สิ่งที่ต้องคงไว้เหมือนเดิม:** stage อื่นทั้งหมด (`SonarQube Analysis`, `Quality Gate`, `E2E`, `Deploy —`, IaC ทั้งชุดจาก Lab 08) **ยังใช้ `agent { label 'linux-build' }` เหมือนเดิม** — เขียนไว้ใน Known Limitations ว่าไม่ได้ย้ายทุก stage เพราะเวลาจำกัด (stage ที่เหลือต้องใช้ Docker-in-Docker ซ้อนในพอด K8s ซึ่งซับซ้อนกว่ามาก)

---

## ขั้นที่ 7 — Push, ชี้ Jenkins job ไป `lab09`, Build Now, ดู pod เกิดจริง `[CLI + UI]`

```bash
git add Jenkinsfile
git commit -m "feat: move Install/Checks stages to Kubernetes dynamic agents"
git push origin lab09
```
**[UI]** Configure job → Branch Specifier → `*/lab09` → Save → Build Now

**[CLI]** เปิด terminal อีกหน้าต่างคู่ขนาน รันค้างไว้ตอนกด Build Now:
```bash
docker exec jenkins-agent-linux-build kubectl get pods -w
```
**ต้องเห็น pod ใหม่ขึ้นมา (`Pending` → `Running`) แล้วหายไปหลัง build เสร็จ** — นี่คือ deliverable ข้อ 1 (diff Jenkinsfile) + หลักฐาน "genuinely run on ephemeral pods"

---

## ขั้นที่ 8 — ตรวจสอบ Prometheus metrics endpoint `[UI]`

เปิด `http://localhost:8080/prometheus` — ต้องเห็น metrics text จริง (ไม่ error) มองหาชื่อ metric ที่จะใช้ในขั้นถัดไป (ชื่อจริงอาจต่างกันไปตามเวอร์ชัน plugin — **เช็คจาก output จริงหน้านี้ก่อนไปเขียน Prometheus config** อย่าเชื่อชื่อ metric ที่เขียนในคู่มือนี้เป๊ะ ๆ)

---

## ขั้นที่ 9 — ตั้ง Prometheus + Grafana (แบบเบา) `[CLI]`

`infra/monitoring/prometheus.yml`:
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'jenkins'
    metrics_path: '/prometheus'
    static_configs:
      - targets: ['localhost:8080']
```

`infra/monitoring/docker-compose.yml`:
```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    network_mode: host
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro

  grafana:
    image: grafana/grafana:latest
    network_mode: host
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
```
(ใช้ `network_mode: host` ทั้งคู่ — pattern เดียวกับ SonarQube/LocalStack ที่ทำมาตลอด ตัด cross-network complexity ทิ้งไปเลย: Grafana คุย Prometheus ผ่าน `localhost:9090`, Prometheus คุย Jenkins ผ่าน `localhost:8080` ตรง ๆ)

```bash
cd infra/monitoring
docker compose up -d
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep health
```
ต้องเห็น `"health": "up"` สำหรับ target `jenkins`

---

## ขั้นที่ 10 — สร้าง Grafana Dashboard 3 panel `[UI]`

เปิด `http://localhost:3000` (login `admin`/`admin`, เปลี่ยนรหัสถ้าถาม)

**Connections → Data sources → Add data source → Prometheus** → URL: `http://localhost:9090` → Save & Test

**สร้าง Dashboard ใหม่ → Add visualization** เลือก Prometheus datasource แล้วใส่ query 3 panel (ปรับชื่อ metric ตามที่เห็นจริงในขั้นที่ 8):
1. **Build success rate:** ประมาณ `sum(rate(default_jenkins_builds_success_build_count[1h])) / sum(rate(default_jenkins_builds_last_build_result_ordinal[1h]))` (หรือ metric คู่ success/total ที่เห็นจริง)
2. **p95 build duration:** `histogram_quantile(0.95, jenkins_builds_duration_milliseconds_summary)`
3. **Queue length:** `jenkins_queue_size_value`

Save dashboard → **Dashboard settings → JSON Model** → copy เก็บไว้เป็น deliverable

---

## ขั้นที่ 11 — ตั้ง Grafana Alert (แทน Prometheus Alertmanager) `[UI]`

ที่ panel "Queue length" → **Edit → Alert → Create alert rule**
- Condition: `WHEN last() OF query(A) IS ABOVE 0`
- Evaluate every `10s` for `30s` (ย่อจาก 5 นาทีในโจทย์เดิม — สเกลเล็กให้เห็นผลเร็ว)
- Labels: `severity: warning`
- Summary: `Jenkins build queue backlog`
- Save

---

## ขั้นที่ 12 — Saturation Demo สเกลเล็ก `[UI]`

**ลด concurrency:** Manage Jenkins → Clouds → Kubernetes → Pod Template `k8s-node` → **Instance Cap: 1**

**Trigger 2-3 build พร้อมกัน:** เปิด job หลายแท็บ กด Build Now รัว ๆ 2-3 ครั้งติดกัน

**สังเกต:** Grafana panel "Queue length" ควรขยับขึ้น, alert เปลี่ยนสถานะ `Normal` → `Pending` → `Firing` — **เก็บภาพตอน Firing ไว้**

**แก้กลับ:** Instance Cap → 2 (หรือมากกว่า) → รอ queue ระบาย → เก็บภาพตอน alert กลับเป็น `Normal`

---

## สรุป Deliverables

| # | รายการ | เก็บจากขั้นตอนไหน |
|---|---|---|
| 1 | Diff Jenkinsfile (Docker agent → K8s pod template) | ขั้นที่ 6 |
| 2 | Grafana dashboard JSON (3 panel) | ขั้นที่ 10 |
| 3 | Screenshot alert Firing ตอนโหลดหนัก + กลับ Normal ตอนแก้ | ขั้นที่ 12 |

## เกณฑ์การให้คะแนน

| หัวข้อ | คะแนน |
|---|---|
| Build รันบน K8s pod จริง ยืนยันสด ๆ | 30 |
| Prometheus metrics scrape + dashboard ถูกต้อง | 25 |
| SLO/Alert ตั้งตาม symptom (queue time) ถูกต้อง | 20 |
| Saturation + recovery แสดงผลจริง | 25 |

## ข้อจำกัดที่รู้ตัว (Known Limitations)

- ย้ายแค่ 3 stage (Install/Lint/Unit Test) ไป K8s pod — stage ที่เหลือยังอยู่บน `linux-build` static agent เพราะเวลาจำกัด (Docker-in-Docker ซ้อนในพอด K8s ซับซ้อนกว่ามาก)
- ใช้ Grafana built-in alerting แทน Prometheus Alertmanager แยก (ผลลัพธ์เทียบเท่ากันในแง่ demo สด แต่สถาปัตยกรรมต่างจาก production ทั่วไปที่มักแยก Alertmanager)
- Saturation demo สเกลเล็ก (concurrency 1, build 2-3 อัน) แทน 10 build ตามโจทย์เดิม — ยังพิสูจน์ mechanism เดียวกันได้
- TLS certificate check ปิดไว้ (`Disable https certificate check`) — ใช้ได้เฉพาะ local lab ไม่ใช่ production practice
