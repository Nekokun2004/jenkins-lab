# Lab 07 — Containers, Image Scanning & Deployment

**อ้างอิงจาก:** Deck 07, 09b, 10 — Jenkinsfile Examples / Security / Deploying
**ระยะเวลา:** 4 ชั่วโมง · **รูปแบบ:** ทำเป็นคู่ (ทำคนเดียวได้ตามความสะดวก)
**Deliverable:** Running blue/green service

> **สถานะเอกสารนี้:** เขียนจากการอ่าน `Jenkinsfile`, `Dockerfile`, `src/app.js`, Lab 01–06 และสถานะ Docker จริงของเครื่อง (ดูตารางสถานะเครื่อง) **ยังไม่ได้ implement/รัน Lab 07** — คำสั่งที่ยังไม่เคยรันบนเครื่องนี้ถูกทำเครื่องหมาย `[ยังไม่ได้ทดสอบบนเครื่องนี้]` ให้ทำตาม Step 0 (verify local ก่อน Jenkins) เสมอ
> ไฟล์ `PROJECT_CONTEXT.md` ที่โจทย์พูดถึง **ไม่มีอยู่ใน repo** — ใช้ `Jenkinsfile`, `manual_lab/README.md`, `.claude/skills/cicd-verify-loop/SKILL.md` และ Lab 06 เป็นแหล่งข้อมูลแทน


---
> **วิธีอ่านเอกสารนี้:** ส่วน **“อ่านเป็นบริบท”** (เป้าหมาย, Architecture, สิ่งที่ต้องรู้, สถานะเครื่อง, โครงสร้างไฟล์, หลักการ verify) อยู่ **ก่อน** ขั้นที่ 1 · ส่วน **“ขั้นตอนทั้งหมด”** คือสิ่งที่ต้อง **ลงมือทำตามลำดับ** ขั้นที่ 1–23 · ส่วน **“Reference”** (Troubleshooting, Known Limitations, Cleanup) อยู่ **หลัง** ขั้นสุดท้าย
---
> **📝 บันทึกการทำจริง (Lab 07 implementation, 2026-09-30) — สิ่งที่ต่างจากที่เขียนไว้ในเอกสารนี้:**
> - เวอร์ชันที่ติดตั้งจริง: kubectl v1.37.1, kind v0.33.0 (node image `kindest/node:v1.37.0`), Trivy 0.74.0; agent ต้องลง `jq` เพิ่มด้วย `apt-get install jq` (ไม่มีมาใน image)
> - **Trivy กับ image เดิมไม่ผ่าน gate (กรณี B ในขั้นที่ 13):** พบ 22 รายการใน npm ที่ bundle มากับ node image (tar, glob, minimatch ...) + 4 รายการ OpenSSL (libssl3/libcrypto3) — แก้ที่ `Dockerfile` (stage runtime): `apk upgrade libssl3 libcrypto3` และลบ `npm`/`corepack` ออก แล้วผ่าน gate โดยไม่ต้องใช้ `--ignore-unfixed`
> - Jenkinsfile เก็บสีเดิมไว้ทั้งใน `env.PREV_COLOR` **และไฟล์ `.lab07-previous-color`** (ลบทิ้งต้น stage กัน stale; อยู่ใน `.gitignore`); Smoke test มี retry 3 ครั้ง เพราะ `kubectl run -i` บางครั้งขึ้น `couldn't attach to pod` (ไม่กระทบผล)
> - ตรวจ endpoint หลังสลับต้องเทียบแบบ **เรียงลำดับ/เป็นชุด** ไม่ใช่ string ตรง ๆ เพราะ pod เก่าที่กำลัง terminate ยังอยู่ใน EndpointSlice ชั่วครู่
> - `verify-loop.py` ขยายให้ครอบ Build Image / Container Scan / Blue/Green Deploy (รวมเส้นทาง block ของ Trivy และ rollback ทั้ง `post-switch-fail` / `bad-image`) — ผ่าน 28/28 stage-run ใน 2 รอบ

# ส่วนที่ A — อ่านเป็นบริบท (ยังไม่ต้องรันอะไร)
## เป้าหมายของ Lab
1. Build Docker image จาก pipeline แล้ว push เข้า **local registry** (`registry:2`)
2. **ห้ามใช้ tag `latest`** — tag ต้องเป็น `taskflow-api:<7 ตัวแรกของ Git SHA>`
3. Scan image ที่ build เสร็จด้วย **Trivy** และ **block** เมื่อเจอ HIGH / CRITICAL
4. Deploy บน Kubernetes ในเครื่อง (**kind**)
5. ทำ **Blue/Green**: มี Deployment 2 ชุด (`taskflow-blue`, `taskflow-green`) และ Service เดียว (`taskflow`) ที่ชี้สีเดียวผ่าน label `color`
6. **Smoke test สีที่ยังไม่ live ก่อน** สลับ Service เสมอ
7. ถ้า deploy พัง ต้อง **rollback อัตโนมัติ** (Service กลับไปสีเดิม) — เป็นโค้ดที่รันจริงใน `post { failure }` ไม่ใช่แค่ขั้นตอนที่เขียนไว้

#### แนวคิดสั้น ๆ

| แนวคิด | ใจความ |
|---|---|
| **Immutable image** | tag ผูกกับ Git SHA = ชี้ commit เดียวตลอดกาล ย้อนรอยได้ rollback ไม่กำกวม. `latest` เปลี่ยนความหมายได้ทุก push, ไม่รู้ว่าคือ commit ไหน, และ "rollback ไป latest" ไม่มีความหมาย |
| **Local registry** | `registry:2` รันเป็น container บนเครื่อง ให้ทั้ง Docker daemon (push) และ kind node (pull) เข้าถึง |
| **Trivy** | scan CVE ใน OS package + library ของ image จริง (ต่างจาก npm audit ที่ดูแค่ `package-lock.json`) |
| **Blue/Green** | deploy เวอร์ชันใหม่ลงสี "ที่ไม่ได้รับ traffic" ทดสอบให้เรียบร้อย แล้วค่อยย้าย traffic ทีเดียวด้วยการแก้ selector ของ Service |
| **Smoke test ก่อนสลับ** | ถ้าทดสอบหลังสลับ ผู้ใช้จะเจอเวอร์ชันพังก่อนเรารู้ — จุดนี้คือ 30 คะแนน |
| **Rollback** | จำสีเดิมไว้ *ก่อนแตะอะไร* ถ้าพังให้ patch selector กลับ |

---
## ภาพรวม Architecture
```
                           Jenkins Controller (container `jenkins`)
                                        |
                                        v
                      Agent `linux-build` (container `jenkins-agent-linux-build`)
                      --network host · docker.sock mounted · + kubectl · + kubeconfig
                                        |
                                /var/run/docker.sock
                                        |
                                        v
                          Host Docker Daemon  (dockerd ของเครื่อง)
                            /                          \
                           /                            \
         container `kind-registry` (registry:2)      kind cluster `taskflow`
         host: localhost:5000  ──────────┐           (node container `taskflow-control-plane`)
         kind net: kind-registry:5000 ◄──┘  containerd mirror:
                                            localhost:5000 → http://kind-registry:5000
                                                          |
                          +-------------------------------+------------------------------+
                          |                                                              |
                          v                                                              v
                 Deployment/taskflow-blue                                      Deployment/taskflow-green
                 pod labels: app=taskflow, color=blue                          pod labels: app=taskflow, color=green
                          ^          ^                                                   ^          ^
                          |          |  Service/taskflow-blue  (smoke test)              |          |
                          |          +-----------------------------  Service/taskflow-green (smoke test)
                          |                                                              |
                          +-------------------- Service/taskflow ------------------------+
                                           selector: app=taskflow, color=<active>
```

**จุดที่ต้องเข้าใจ (สำคัญที่สุดของ Lab นี้):**

- `localhost:5000` **บนเครื่อง host / ใน agent** (agent ใช้ `--network host`) = registry container ที่ publish port 5000 — `docker push localhost:5000/...` ใช้ได้ (Docker daemon ยอม HTTP สำหรับ `127.0.0.0/8` อยู่แล้ว)
- `localhost:5000` **ใน kind node** = ตัว node เอง ไม่ใช่ host → ต้องมี containerd mirror ที่แปลง `localhost:5000` เป็น `http://kind-registry:5000` และต้องต่อ `kind-registry` เข้า Docker network ชื่อ `kind`
- ทำให้ image reference เดียว `localhost:5000/taskflow-api:<sha>` ใช้ได้ทั้งตอน push (จาก host) และตอน pull (จาก kind node)
- **Logical image** = `taskflow-api:<sha>` (ชื่อแอป + SHA) ส่วน **registry-qualified image** = `localhost:5000/taskflow-api:<sha>` (มี registry host นำหน้า). ใน Jenkinsfile ใช้ตัวหลังตลอดเพราะ `docker push` ต้องการ registry host ใน tag

#### ลำดับ Blue/Green (ลำดับนี้คือหัวใจของคะแนน)

```
Service ──► BLUE (live อยู่)            current = blue, next = green    ← บันทึก PREV_COLOR ก่อนแตะอะไร
              |
   build + push + scan image <sha>      (ต้องผ่าน Trivy ก่อนถึงตรงนี้)
              |
              v
   kubectl set image  taskflow-green    (BLUE ยังรับ traffic 100%)
              |
              v
   kubectl rollout status taskflow-green
              |
              v
   smoke test  http://taskflow-green:8080/health    (ผ่าน Service taskflow-green ไม่ใช่ taskflow)
            /          \
         PASS          FAIL / rollout timeout
          |               |
          v               v
  patch Service          Service ไม่ถูกแตะ (ยังเป็น BLUE)
  BLUE → GREEN           post.failure: patch กลับ PREV_COLOR=blue (+ verify + log)
          |
          v
  verify ผ่าน Service taskflow (post-switch check)
          |
        FAIL → post.failure: patch Service GREEN → BLUE   ← rollback ที่ "ทำงานจริง" (selector เปลี่ยนสองครั้ง)
```

---
## สิ่งที่ต้องรู้ก่อนเริ่ม (สืบทอดจาก Lab 01–06)
| ข้อเท็จจริงจากโปรเจกต์ | ผลกับ Lab 07 |
|---|---|
| Jenkins controller + agent `linux-build` รันเป็น Docker container; agent ใช้ `--network host` | agent เรียก `localhost:5000` (registry) และ API server ของ kind (`127.0.0.1:<port>`) ได้ตรง ๆ |
| agent mount `/var/run/docker.sock` ของ host (Docker-outside-of-Docker) | `docker build/push` ใน pipeline คุยกับ **dockerd ของ host** — image อยู่ใน image store ของ host, registry/kind ที่ host สร้างก็เห็น |
| workspace ของ agent (`/home/jenkins/agent`) อยู่ใน anonymous Docker volume ไม่ใช่ path จริงบน host | **ห้าม** `-v "$WORKSPACE:/x"` กับ `docker run` ใน Jenkins (เกิด phantom bind mount ตามที่เจอใน Lab 06) — ใช้ `--volumes-from jenkins-agent-linux-build -w "$WORKSPACE"` เหมือน Syft/Cosign/OPA |
| `docker build .` ส่ง build context ผ่าน socket | **ไม่มีปัญหา phantom mount** — ใช้ได้ตามปกติ (ต่างจาก `docker run -v`) |
| `pipeline { agent none }` | ทุก stage ใหม่ต้องมี `agent { label 'linux-build' }` ของตัวเอง |
| Tool ใหม่ต้องไม่บังคับแก้ `Dockerfile.agent` ถ้าเลี่ยงได้ | Trivy รันเป็น sidecar `aquasec/trivy`; ส่วน `kubectl` ต้องอยู่ในเครื่อง agent (ดูขั้นที่ 2 — ติดตั้งด้วย `docker cp` ไม่ต้อง rebuild image) |
| `sudo` ต้องใช้รหัสผ่าน | ติดตั้ง binary ไว้ที่ `~/.local/bin` (อยู่ใน `PATH` แล้ว) ไม่ต้อง sudo |
| Pipeline มี `timeout(time: 10, unit: 'MINUTES')` ทั้งงาน | Lab 07 เพิ่ม build+scan+rollout → **ต้องเพิ่มเป็น 20 นาที** (อยู่ในโค้ดขั้นที่ 16) |
| Stage Lab 05/06 (`E2E`, SAST, SBOM, Policy Gate ...) | **ห้ามแตะ** — Lab 07 เพิ่ม 3 stage ต่อท้าย E2E |
| แอปฟังที่พอร์ต **8080** (`ENV PORT=8080`, `EXPOSE 8080`) และมี `GET /health` → `200 {"status":"ok"}` (`src/app.js`) | ใช้เป็น readiness probe + smoke test. ไม่มี `DATABASE_URL` แอปใช้ in-memory repository จึง **ไม่ต้องมี Postgres** บน k8s |
| Dockerfile เป็น multi-stage, `USER node` | รันเป็น non-root ได้ ไม่ต้องตั้ง `securityContext` เพิ่ม |

---
## ⚠️ สิ่งที่ต้องเตรียมก่อนเริ่ม — สถานะเครื่องที่ตรวจไว้จริง
คำสั่งตรวจ/ติดตั้งเครื่องมืออยู่ในขั้นที่ 1–4 ข้างล่าง ส่วนตารางนี้คือผลที่ตรวจไว้แล้วตอนเขียนเอกสาร
### สถานะเครื่องที่ตรวจไว้ตอนเขียนเอกสาร (read-only check)
| เครื่องมือ | สถานะ | หมายเหตุ |
|---|---|---|
| `docker` | ✅ Docker 29.7.2 (host), 29.8.1 (client ใน agent) | agent เข้า socket ได้ (`jenkins` อยู่ group 123) |
| `kubectl` | ❌ ยังไม่มี (ทั้ง host และ agent) | ติดตั้งตามขั้นที่ 2 |
| `kind` | ❌ ยังไม่มี | ติดตั้งตามขั้นที่ 2 |
| `trivy` | ❌ ยังไม่มีบน host | **ไม่ต้องติดตั้ง** — รันผ่าน `docker run aquasec/trivy` (ขั้นที่ 3) |
| port `5000` | ✅ ว่าง | registry ใช้พอร์ตนี้ |
| RAM | ~15 GB (ว่างจริงไม่มาก) | kind control-plane node เดียวกินราว 1–2 GB |

---
## Files / Directory Structure to Add
```
jenkins-lab/
├── Jenkinsfile                     # แก้: timeout 20 นาที, disableConcurrentBuilds, parameters, environment, +3 stage
├── .gitignore                      # แก้: เพิ่ม trivy-report.sarif
├── kind/
│   └── kind-config.yaml            # ใหม่: cluster config + containerd registry config_path
└── k8s/
    ├── deployment-blue.yaml        # ใหม่
    ├── deployment-green.yaml       # ใหม่
    ├── service.yaml                # ใหม่: Service/taskflow (live) — selector color=<active>
    └── service-colors.yaml         # ใหม่: Service/taskflow-blue + taskflow-green (ไว้ smoke test)
```

- **สร้างใหม่เฉพาะที่จำเป็น** — ไม่มี helm/kustomize (ตามหลัก "ทางสั้นที่สุดที่ defend ได้")
- `Dockerfile` **ไม่ต้องแก้** (ยกเว้นตอนจงใจทำ image ให้มีช่องโหว่ในขั้นที่ 13 ซึ่งแก้ชั่วคราวแล้ว revert)

---
## หลักการ Step 0 — Local Verification First
ตามข้อตกลงของโปรเจกต์ (`.claude/skills/cicd-verify-loop`): **ห้ามไล่ push → รอ Jenkins → แก้ทีละ bug**

```
สร้าง/รันทุกคำสั่งบนเครื่องก่อน  ──►  ตรวจซ้ำด้วยคำสั่ง "อิสระ"  ──►  จึงค่อยใส่ Jenkinsfile  ──►  Build Now ครั้งเดียว
```

| คำสั่งที่รัน | เช็คอิสระ (exit code 0 อย่างเดียวไม่พอ) |
|---|---|
| `docker run ... registry:2` | `curl http://localhost:5000/v2/` ได้ `{}` |
| `kind create cluster` | `kubectl get nodes` เป็น `Ready` |
| `docker push localhost:5000/taskflow-api:<sha>` | `curl .../v2/taskflow-api/tags/list` มี `<sha>` **และ** `docker exec taskflow-control-plane crictl pull ...` สำเร็จ |
| `trivy ... -o trivy-report.sarif` | `test -s trivy-report.sarif` + `jq '.runs[0].tool.driver.name'` |
| `kubectl apply` | `kubectl get deploy,svc` + `kubectl rollout status` |
| `kubectl patch svc` | `kubectl get svc taskflow -o jsonpath='{.spec.selector.color}'` + endpoint IP ตรงกับ pod สีนั้น |

ต้องรันทุกอย่าง **จากใน agent** (`docker exec jenkins-agent-linux-build ...`) อย่างน้อยหนึ่งรอบ เพราะ Jenkins รันที่นั่น (kubeconfig, `kubectl`, สิทธิ์ docker.sock ต้องพร้อมจริง) และรัน **ซ้ำ 2 รอบ** (workspace ของ agent ถาวรข้าม build)

---
# ส่วนที่ B — ขั้นตอนทั้งหมด (ทำตามลำดับ)
| ขั้นที่ | ทำอะไร |
|---|---|
| 1–4 | เตรียมเครื่องมือ (ตรวจ, ติดตั้ง kubectl/kind, Trivy ผ่าน Docker, pre-pull) |
| 5 | สร้าง branch `lab07` |
| 6–9 | registry + kind cluster + เชื่อม registry↔kind + kubeconfig ให้ agent |
| 10 | เขียน Kubernetes manifests |
| 11–13 | build/push image, Trivy local, พิสูจน์ gate |
| 14–15 | deploy Blue/Green เริ่มต้น + ซ้อมสลับด้วยมือ |
| 16–20 | แก้ Jenkinsfile (ส่วนบนสุด, Build Image, Container Scan, Blue/Green Deploy, Rollback) |
| 21 | commit/push แล้วรัน Jenkins |
| 22–23 | Demo สำเร็จ / Demo ล้มเหลว + rollback |

---
## ขั้นตอนทั้งหมด
### ขั้นที่ 1 — ตรวจเครื่องมือที่ต้องใช้ (รันซ้ำก่อนเริ่มทุกครั้ง) `[CLI]`
```bash
docker --version
kubectl version --client
kind version
docker exec jenkins-agent-linux-build docker ps --format '{{.Names}}'     # agent เข้า Docker socket ได้
docker exec jenkins-agent-linux-build kubectl version --client            # kubectl ใน agent
docker exec jenkins-agent-linux-build curl -sS -o /dev/null -w '%{http_code}\n' http://localhost:5000/v2/   # 200 = registry ถึงได้จาก agent
```

---
### ขั้นที่ 2 — ติดตั้ง kubectl + kind (ทำตอน implement ไม่ใช่ตอนนี้) — [ยังไม่ได้ทดสอบบนเครื่องนี้] `[CLI]`
```bash
mkdir -p ~/.local/bin
# kubectl (latest stable)
curl -fsSLo ~/.local/bin/kubectl "https://dl.k8s.io/release/$(curl -fsSL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x ~/.local/bin/kubectl
# kind (pin เวอร์ชันไว้ — เปลี่ยนเป็นรุ่นใหม่กว่านี้ได้)
curl -fsSLo ~/.local/bin/kind https://kind.sigs.k8s.io/dl/v0.30.0/kind-linux-amd64
chmod +x ~/.local/bin/kind
kubectl version --client && kind version
```

**ใส่ `kubectl` เข้า agent (ไม่ต้อง rebuild `Dockerfile.agent`)** — binary เป็น static ใช้ข้ามเครื่องได้:

```bash
docker cp "$(command -v kubectl)" jenkins-agent-linux-build:/usr/local/bin/kubectl
docker exec -u root jenkins-agent-linux-build chmod 755 /usr/local/bin/kubectl
docker exec jenkins-agent-linux-build kubectl version --client        # ต้องเห็นเวอร์ชัน
```

> ⚠️ ถ้า **สร้าง container agent ใหม่** (`docker rm -f` แล้ว `docker run`) ไฟล์นี้หาย ต้อง `docker cp` ซ้ำ. (ทางถาวร = เติม `kubectl` ใน `Dockerfile.agent` — ดูส่วน Reference 2 (Known Limitations))

---
### ขั้นที่ 3 — เตรียม Trivy ผ่าน Docker (ไม่ต้องติดตั้ง) `[CLI]`
```bash
docker pull aquasec/trivy:latest                        # pre-pull กันรอตอน build จริง
docker run --rm aquasec/trivy:latest --version
```

ฐานข้อมูล CVE (~ร้อย MB) จะถูกโหลดครั้งแรกแล้ว cache ใน named volume `trivy-cache` (named volume ใช้ได้ปกติ — ที่ห้ามคือ *bind mount path ของ workspace*)

---
### ขั้นที่ 4 — Pre-pull image ที่จะใช้ (กันเสียเวลาและกัน Docker Hub rate limit) `[CLI]`
```bash
docker pull registry:2
# (kind node image ~1 GB จะถูกดึงอัตโนมัติตอน `kind create cluster` ครั้งแรก — ต่อเน็ตไว้)
docker pull curlimages/curl:8.10.1                       # ใช้ทำ smoke test pod
```

---
### ขั้นที่ 5 — สร้าง branch `lab07` (แยกจาก `lab06`) `[CLI]`
สืบทอด stage ทั้งหมดจาก Lab 06 — เช็ค `git log --oneline -5` ว่ามี stage `E2E` ก่อน

```bash
git checkout lab06 && git checkout -b lab07
git branch --show-current        # ต้องเป็น lab07
grep -n "stage('E2E')" Jenkinsfile   # ต้องเจอ
```

---
### ขั้นที่ 6 — ตั้ง Local Registry (`registry:2`) `[CLI]`
```bash
docker run -d --restart=always --name kind-registry \
  -p 127.0.0.1:5000:5000 \
  registry:2
```

- `-p 127.0.0.1:5000:5000` = publish เฉพาะ loopback ของ host (ไม่เปิดให้เครื่องอื่นในเครือข่ายเห็น)
- `--restart=always` = ไม่ต้องสตาร์ทเองหลัง reboot

**ตรวจอิสระ:**

```bash
curl -fsS http://localhost:5000/v2/                           # → {}
curl -fsS http://localhost:5000/v2/_catalog                   # → {"repositories":[]}
docker exec jenkins-agent-linux-build curl -fsS http://localhost:5000/v2/   # agent ก็ต้องเห็น (host network)
```

> การต่อ registry เข้า network `kind` ทำหลังสร้าง cluster (ขั้นที่ 8) เพราะ network `kind` ถูกสร้างโดย `kind create cluster`

---
### ขั้นที่ 7 — สร้าง kind cluster (config + create) `[CLI]`
```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
containerdConfigPatches:
- |-
  [plugins."io.containerd.grpc.v1.cri".registry]
    config_path = "/etc/containerd/certs.d"
nodes:
- role: control-plane
```

`config_path` บอก containerd ให้อ่าน mirror config จากโฟลเดอร์ `/etc/containerd/certs.d/<registry-host>/hosts.toml` (โฟลเดอร์นี้อ่านสด ไม่ต้อง restart containerd)


**สร้าง cluster**

```bash
kind create cluster --name taskflow --config kind/kind-config.yaml
kubectl cluster-info --context kind-taskflow
kubectl get nodes
```

ต้องเห็น node `taskflow-control-plane` สถานะ `Ready`

---
### ขั้นที่ 8 — ต่อ registry เข้ากับ kind node (containerd mirror) `[CLI]`
```bash
# (1) ต่อ registry container เข้า network `kind` (kind สร้างให้ตอน create cluster)
docker network connect kind kind-registry 2>/dev/null || true

# (2) บอก containerd ในทุก node ว่า localhost:5000 = http://kind-registry:5000
REGISTRY_DIR="/etc/containerd/certs.d/localhost:5000"
for node in $(kind get nodes --name taskflow); do
  docker exec "$node" mkdir -p "$REGISTRY_DIR"
  cat <<'EOF' | docker exec -i "$node" sh -c "cat > $REGISTRY_DIR/hosts.toml"
[host."http://kind-registry:5000"]
EOF
done
```

**ตรวจอิสระ (ทำหลัง push image ครั้งแรกในขั้นที่ 11 ก็ได้):**

```bash
docker inspect -f '{{json .NetworkSettings.Networks}}' kind-registry | grep -o '"kind"'     # ต้องพิมพ์ "kind"
docker exec taskflow-control-plane cat "/etc/containerd/certs.d/localhost:5000/hosts.toml"
docker exec taskflow-control-plane getent hosts kind-registry || docker exec taskflow-control-plane ping -c1 kind-registry
docker exec taskflow-control-plane crictl pull localhost:5000/taskflow-api:<SHA>            # พิสูจน์ว่า node pull ได้จริง
```

`crictl pull` สำเร็จ = การเชื่อม kind ↔ registry ถูกต้อง. นี่คือจุดที่พังบ่อยที่สุด อย่าข้าม

> `kind load docker-image` ใช้ได้เป็น **ทางหนีไฟฉุกเฉิน** ตอน debug เท่านั้น — หลักฐานหลักของ Lab ต้องเป็น image ที่ **push เข้า registry แล้ว pull ผ่าน registry**

---
### ขั้นที่ 9 — ทำ kubeconfig ให้ agent `[CLI]`
kind ออก kubeconfig ที่ชี้ `https://127.0.0.1:<random-port>` — agent ใช้ `--network host` จึงเข้าถึงได้เหมือน host

```bash
kind get kubeconfig --name taskflow > /tmp/kubeconfig-taskflow
docker exec jenkins-agent-linux-build mkdir -p /home/jenkins/.kube
docker cp /tmp/kubeconfig-taskflow jenkins-agent-linux-build:/home/jenkins/.kube/config
docker exec -u root jenkins-agent-linux-build chown -R jenkins:jenkins /home/jenkins/.kube
rm /tmp/kubeconfig-taskflow
docker exec jenkins-agent-linux-build kubectl get nodes          # ← เช็คจาก agent จริง ต้อง Ready
```

> ⚠️ ถ้า `kind delete cluster` แล้วสร้างใหม่ port/cert เปลี่ยน → ต้องทำขั้นนี้ซ้ำ (อาการ: `Unable to connect to the server` / `x509` ใน Jenkins)

---
### ขั้นที่ 10 — เขียน Kubernetes Blue/Green Manifests `[CLI]`
**`k8s/deployment-blue.yaml`**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: taskflow-blue
  labels:
    app: taskflow
    color: blue
spec:
  replicas: 1
  selector:
    matchLabels:
      app: taskflow
      color: blue
  template:
    metadata:
      labels:
        app: taskflow
        color: blue
    spec:
      containers:
      - name: taskflow
        image: __IMAGE__
        ports:
        - containerPort: 8080
        env:
        - name: PORT
          value: "8080"
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 2
          periodSeconds: 3
        resources:
          requests:
            cpu: 50m
            memory: 64Mi
```

**`k8s/deployment-green.yaml`**

เหมือน blue ทุกบรรทัด แต่คำว่า `blue` ทุกที่ต้องเป็น `green` (`metadata.name`, `metadata.labels.color`, `selector.matchLabels.color`, `template.metadata.labels.color`) — สร้างด้วย `sed`:

```bash
sed 's/blue/green/g' k8s/deployment-blue.yaml > k8s/deployment-green.yaml
grep -n 'blue\|green' k8s/deployment-green.yaml      # ต้องไม่เหลือคำว่า blue
```

**`k8s/service.yaml` — Service ที่รับ traffic จริง**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: taskflow
spec:
  selector:
    app: taskflow
    color: blue
  ports:
  - port: 8080
    targetPort: 8080
```

**`k8s/service-colors.yaml` — Service ประจำสี (ไว้ smoke test)**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: taskflow-blue
spec:
  selector:
    app: taskflow
    color: blue
  ports:
  - port: 8080
    targetPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: taskflow-green
spec:
  selector:
    app: taskflow
    color: green
  ports:
  - port: 8080
    targetPort: 8080
```

**อธิบายจุดสำคัญ**

| บรรทัด | ทำไมสำคัญ |
|---|---|
| `selector.matchLabels` = `template.metadata.labels` | Deployment หา pod ของตัวเองจาก label นี้ — ถ้าไม่ตรงกัน `kubectl apply` ถูกปฏิเสธ (`selector does not match template labels`) |
| `color` label ต่างกันระหว่าง 2 Deployment | ถ้า selector ซ้ำกัน ReplicaSet สองชุดจะแย่ง pod กัน |
| `Service/taskflow` selector `app=taskflow,color=<active>` | **นี่คือ "สวิตช์" ของ Blue/Green** — pipeline แก้แค่ค่า `color` |
| `image: __IMAGE__` | placeholder — ตอน bootstrap แทนด้วย image จริงด้วย `sed` (ขั้นที่ 14). หลังจากนั้น Jenkins เปลี่ยน image ด้วย `kubectl set image` ไม่ใช้ `apply` ซ้ำ |
| `readinessProbe /health` | pod ยังไม่ Ready ก็ไม่เข้า Endpoints → `rollout status` รอจน `/health` ตอบ 200 จริง |
| **`Service/taskflow-blue`, `taskflow-green`** | **Deployment name ไม่ใช่ DNS name** — `http://taskflow-green:8080` ใช้ได้ก็เพราะเรา *สร้าง Service* ชื่อนั้น (kube-dns แปลงชื่อ Service เป็น ClusterIP). ตัวอย่างใน PDF ที่ curl `http://taskflow-<color>:8080/health` จะใช้ได้จริงก็ต่อเมื่อมี Service ชื่อนี้อยู่ |

---
### ขั้นที่ 11 — Build และ Push Image (Local) `[CLI]`
```bash
cd ~/Documents/selfproject/jenkins-lab
export SHORT_SHA=$(git rev-parse HEAD | cut -c1-7)
export IMAGE=localhost:5000/taskflow-api:${SHORT_SHA}
echo "$IMAGE"

docker build -t "$IMAGE" .
docker push "$IMAGE"
```

**ตรวจอิสระ (เลือกทำทั้งสามข้อ):**

```bash
# (1) image อยู่ใน local daemon จริง
docker image inspect "$IMAGE" --format '{{.Id}}'

# (2) registry รู้จัก tag นี้ (ถามผ่าน HTTP API ไม่ใช่ผ่าน docker)
curl -fsS http://localhost:5000/v2/taskflow-api/tags/list          # → {"name":"taskflow-api","tags":["<sha>"]}

# (3) ลบ local แล้ว pull กลับจาก registry — พิสูจน์ว่า push สำเร็จจริง
docker rmi "$IMAGE" && docker pull "$IMAGE"
```

**ห้าม** `docker tag ... :latest` / `docker push ...:latest` ทุกกรณี — ตรวจว่าไม่มีหลุดด้วย:

```bash
curl -s http://localhost:5000/v2/taskflow-api/tags/list | grep -c latest    # ต้องได้ 0
grep -n ':latest' Jenkinsfile k8s/*.yaml                                    # ต้องเห็นเฉพาะ image ของ *เครื่องมือ* (gitleaks/semgrep/syft ฯลฯ) ไม่มี taskflow-api
```

---
### ขั้นที่ 12 — Trivy Scan Local (สร้าง SARIF + บังคับ gate) `[CLI]`
**สร้าง SARIF (ต้องได้ไฟล์เสมอ แม้เจอช่องโหว่)**

```bash
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v trivy-cache:/root/.cache \
  -v "$PWD":/out -w /out \
  aquasec/trivy:latest image \
    --format sarif -o trivy-report.sarif \
    --severity HIGH,CRITICAL --exit-code 0 \
    "$IMAGE"
test -s trivy-report.sarif && echo "SARIF OK ($(wc -c < trivy-report.sarif) bytes)"
```

(ตอนทดสอบ local บน host ใช้ `-v "$PWD":/out` ได้ เพราะ host path จริง — **ใน Jenkins ห้ามใช้** ดูขั้นที่ 18)

`--exit-code 0` = รอบนี้เก็บรายงานอย่างเดียว ไม่ fail


**บังคับ gate**

```bash
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v trivy-cache:/root/.cache \
  aquasec/trivy:latest image \
    --severity HIGH,CRITICAL --exit-code 1 \
    "$IMAGE"
echo "trivy exit code = $?"
```

| ผลลัพธ์ | ความหมาย |
|---|---|
| exit `0` + ตารางว่าง/`Total: 0` | ไม่พบ HIGH/CRITICAL → image ผ่าน |
| exit `1` + ตาราง CVE | พบ HIGH/CRITICAL → **gate block** |

---
### ขั้นที่ 13 — วัดผล Trivy กับ image จริง และพิสูจน์ว่า gate block ได้จริง `[CLI + UI]`
> ส่วน commit/push/Build Now ในขั้นนี้ให้ทำหลังจากเขียน Jenkinsfile เสร็จ (ขั้นที่ 16–21) ส่วนการวัดด้วยคำสั่ง `docker run` ทำได้ทันที


ยังไม่เคยรัน Trivy กับ `taskflow-api` มาก่อน. ผลลัพธ์ของ `node:20-alpine` ขึ้นกับวันที่ (CVE ใหม่ออกทุกวัน) — มี 2 กรณี:

**กรณี A: image จริงผ่าน gate (exit 0)** → ต้อง **พิสูจน์ว่า gate block ได้จริง** ด้วย image ที่มีช่องโหว่แน่ ๆ:

```bash
# ทางเร็วสุด (ตรวจ gate เฉย ๆ): scan image เก่าที่มี CVE แน่นอน
docker pull node:16-alpine
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache \
  aquasec/trivy:latest image --severity HIGH,CRITICAL --exit-code 1 node:16-alpine
echo "exit = $?"        # คาดว่า 1
```

แล้วพิสูจน์ **ใน Jenkins** แบบเดียวกับ Lab 06 (commit ของเสีย → แดง → revert → เขียว):

```bash
sed -i 's#^FROM node:20-alpine#FROM node:16-alpine#' Dockerfile     # แก้ทั้ง 2 FROM
grep -n '^FROM' Dockerfile                                          # ต้องเป็น node:16-alpine ทั้งคู่
git commit -am "test: intentionally build from EOL node:16 base to trigger Trivy gate"
git push origin lab07
# Build Now → คาดว่าแดงที่ 'Container Scan' และ stage 'Blue/Green Deploy' ถูกข้าม (skipped)
git revert HEAD && git push origin lab07                            # แล้ว Build Now อีกรอบ ต้องกลับมาเขียว
```

> Node 16 รันแอปนี้ได้ (`engines >=20` เป็นแค่ warning) — ถ้า `npm ci` ใน image บ่นจนล้ม ให้ใช้ base อื่นที่เก่าและ build ได้ เช่น `node:18-alpine`. ต้อง **ตรวจ `docker run ... --exit-code 1` ให้ได้ exit 1 ก่อน** ค่อย push

**กรณี B: image จริงโดน HIGH/CRITICAL (exit 1)** → pipeline จริงจะแดงตั้งแต่ build แรก ตัดสินใจ (เรียงจากเร็วไปช้า):

1. เพิ่ม `--ignore-unfixed` (ซ่อน CVE ที่ยังไม่มี patch — เป็นแนวปฏิบัติทั่วไป ระบุในรายงานเป็น policy)
2. ตัด npm ออกจาก runtime image (เป็นต้นเหตุ CVE ของ node image บ่อยมาก และ runtime ไม่ใช้ `npm`): เพิ่มใน stage สุดท้ายของ Dockerfile `RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx` (ก่อน `USER node`)
3. เปลี่ยน base เป็น tag ที่ patch แล้ว (`docker pull node:20-alpine` ใหม่)
4. `.trivyignore` สำหรับ CVE เดี่ยวที่รับความเสี่ยงได้ (ต้องเขียนเหตุผลในรายงาน)

ตัดสินใจแล้วให้ **แก้ทั้งคำสั่ง local และ Jenkinsfile ให้ flag ตรงกันเป๊ะ**

---
### ขั้นที่ 14 — Deploy Blue/Green เริ่มต้น `[CLI]`
Bootstrap ครั้งแรก ใช้ image ที่ push แล้วในขั้นที่ 11 ทั้งสองสี (สีที่ไม่ live ก็รัน SHA เดียวกันไปก่อน):

```bash
sed "s#__IMAGE__#${IMAGE}#" k8s/deployment-blue.yaml  | kubectl apply -f -
sed "s#__IMAGE__#${IMAGE}#" k8s/deployment-green.yaml | kubectl apply -f -
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/service-colors.yaml

kubectl rollout status deployment/taskflow-blue  --timeout=120s
kubectl rollout status deployment/taskflow-green --timeout=120s
```

**ตรวจอิสระ:**

```bash
kubectl get deployments -o wide
kubectl get pods -l app=taskflow -o wide --show-labels          # ต้องมี pod blue 1 + green 1 สถานะ Running 1/1
kubectl get svc
kubectl get svc taskflow -o jsonpath='{.spec.selector}{"\n"}'   # {"app":"taskflow","color":"blue"}

# Service taskflow ชี้ pod สีไหนจริง: IP ใน EndpointSlice ต้องตรงกับ IP ของ pod สีนั้น
kubectl get endpointslices -l kubernetes.io/service-name=taskflow -o jsonpath='{.items[*].endpoints[*].addresses[*]}{"\n"}'
kubectl get pods -l app=taskflow,color=blue  -o jsonpath='{.items[*].status.podIP}{"\n"}'
```

**จด "สีเริ่มต้น" ไว้** (ควรเป็น `blue`) — เก็บ `kubectl get svc taskflow -o yaml` ไว้เป็นภาพประกอบ

**ตรวจว่า kind pull จาก registry จริง (ไม่ได้ใช้ของที่ `kind load`):**

```bash
kubectl describe pod -l app=taskflow,color=blue | grep -E 'Image:|Pulled|Pulling'
```

---
### ขั้นที่ 15 — ซ้อม Blue/Green Switch ด้วยมือ 1 รอบสำเร็จ (ก่อนเขียน Jenkinsfile) `[CLI]`
ทำ **หนึ่งรอบสำเร็จด้วยมือ** ก่อนเขียน Jenkinsfile. ต้องมี image ใหม่ (commit เล็ก ๆ ให้ SHA เปลี่ยน เช่นแก้ comment ใน `README.md`):

```bash
git commit -am "chore: bump for blue/green manual test"
export SHORT_SHA=$(git rev-parse HEAD | cut -c1-7)
export IMAGE=localhost:5000/taskflow-api:${SHORT_SHA}
docker build -t "$IMAGE" . && docker push "$IMAGE"
curl -fsS http://localhost:5000/v2/taskflow-api/tags/list | grep -q "$SHORT_SHA" && echo "tag in registry"

# --- BEFORE ---
kubectl get svc taskflow -o yaml > /tmp/svc-before.yaml

# --- current / next ---
current=$(kubectl get svc taskflow -o jsonpath='{.spec.selector.color}')
if [ "$current" = "blue" ]; then next=green; else next=blue; fi
echo "current=$current next=$next"

# --- set image ลงสีที่ไม่ live ---
kubectl set image deployment/taskflow-$next taskflow="$IMAGE"
kubectl rollout status deployment/taskflow-$next --timeout=90s

# --- smoke test สี next ผ่าน Service ประจำสี (Service taskflow ยังชี้ $current อยู่) ---
kubectl run smoke-manual --rm -i --restart=Never --image=curlimages/curl:8.10.1 --command -- \
  curl -fsS --max-time 5 "http://taskflow-$next:8080/health"
# ต้องเห็น {"status":"ok"}

# --- ยืนยันก่อนสลับว่า traffic ยังอยู่สีเดิม ---
kubectl get svc taskflow -o jsonpath='{.spec.selector.color}{"\n"}'     # ต้องเท่ากับ $current

# --- สลับ ---
kubectl patch svc taskflow --type merge -p "{\"spec\":{\"selector\":{\"color\":\"$next\"}}}"

# --- AFTER + ตรวจอิสระ ---
kubectl get svc taskflow -o yaml > /tmp/svc-after.yaml
diff /tmp/svc-before.yaml /tmp/svc-after.yaml        # ต่างกันที่ selector.color อย่างเดียว (+ resourceVersion)
kubectl get svc taskflow -o jsonpath='{.spec.selector.color}{"\n"}'     # = $next
kubectl get endpointslices -l kubernetes.io/service-name=taskflow -o jsonpath='{.items[*].endpoints[*].addresses[*]}{"\n"}'
kubectl get pods -l app=taskflow,color=$next -o jsonpath='{.items[*].status.podIP}{"\n"}'   # สองบรรทัดต้องเป็น IP เดียวกัน
kubectl get deployment taskflow-$next -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'  # = $IMAGE (ไม่ใช่ latest)
```

**ทำไม `kubectl patch --type merge` ถึงแก้แค่ `color`:** merge patch รวม key ของ map — `app: taskflow` ที่มีอยู่ไม่ถูกแตะ

> ถ้า `kubectl run` ตอบ `already exists` จากรอบก่อนที่ค้าง: `kubectl delete pod smoke-manual --ignore-not-found`
> **ซ้อมย้อนกลับด้วยมือ** ด้วยคำสั่ง patch เดิมแต่ใส่ `$current` เพื่อดูว่า Service กลับได้จริง แล้วสลับไป `$next` อีกครั้งก่อนเริ่มรอบ Jenkins (หรือจะเริ่ม Jenkins จากสีไหนก็ได้ เพราะ pipeline หา current เอง)

---
### ขั้นที่ 16 — แก้ Jenkinsfile ส่วนบนสุด (environment / parameters / options) `[CLI]`
Lab 07 **เพิ่ม** ไม่แทนที่ของเดิม. ส่วนที่แก้ที่ระดับบนสุดของ `Jenkinsfile`:

```groovy
pipeline {
    agent none

    environment {
        APP_NAME = 'taskflow-api'
        NODE_ENV = 'test'
        REGISTRY = 'localhost:5000'
    }

    parameters {
        choice(name: 'DEPLOY_FAULT', choices: ['none', 'bad-image', 'post-switch-fail'],
               description: 'Lab 07 failure injection: none = normal deploy; bad-image = deploy a nonexistent tag; post-switch-fail = fail the verification AFTER the Service switch')
    }

    options {
        timeout(time: 20, unit: 'MINUTES')
        disableConcurrentBuilds()
    }
    // ... stages เดิมทั้งหมด (Install ... E2E) ไม่เปลี่ยน ...
```

---
### ขั้นที่ 17 — Jenkinsfile — stage `Build Image` `[CLI]`
Stage ใหม่ (วางต่อจาก `E2E` และก่อน `Deploy — Staging`):

```groovy
        stage('Build Image') {
            agent { label 'linux-build' }
            steps {
                script {
                    env.SHORT_SHA = env.GIT_COMMIT ? env.GIT_COMMIT.take(7) :
                        sh(script: 'git rev-parse HEAD', returnStdout: true).trim().take(7)
                    env.IMAGE = "${env.REGISTRY}/${env.APP_NAME}:${env.SHORT_SHA}"
                }
                sh '''
                    set -eu
                    echo "Building immutable image: $IMAGE"
                    docker build -t "$IMAGE" .
                    docker image inspect "$IMAGE" --format 'Local image id: {{.Id}}'
                    docker push "$IMAGE"
                    curl -fsS "http://$REGISTRY/v2/$APP_NAME/tags/list"
                    echo
                    curl -fsS "http://$REGISTRY/v2/$APP_NAME/tags/list" | grep -q "$SHORT_SHA"
                    echo "Verified in registry: $IMAGE"
                '''
            }
        }
```

#### อธิบายทีละบรรทัด

| โค้ด | อธิบาย |
|---|---|
| `agent { label 'linux-build' }` | pipeline เป็น `agent none` จึงต้องระบุ agent เอง; ที่นี่มี docker.sock |
| `env.GIT_COMMIT ? env.GIT_COMMIT.take(7) : ...` | ใช้ `env.GIT_COMMIT.take(7)` ตามโจทย์. `GIT_COMMIT` ถูกตั้งโดย Git plugin ตอน checkout ของ stage; ถ้าไม่มี (null) ใช้ `git rev-parse HEAD` แทน — ได้ SHA เดียวกัน. `take(7)` คือ 7 ตัวแรก |
| `env.SHORT_SHA = ...`, `env.IMAGE = ...` | กำหนดผ่าน `env.` เพื่อให้ **stage ถัดไปเห็น** (ตัวแปร `def` ในสคริปต์หายทันทีที่จบ `script {}`) และ export เป็น env ให้ `sh` ใช้ `$IMAGE` ได้ |
| `"${env.REGISTRY}/${env.APP_NAME}:${env.SHORT_SHA}"` | ได้ `localhost:5000/taskflow-api:1a2b3c4` — ไม่มี `latest` ที่ไหนเลย |
| `set -eu` | fail ทันทีถ้าคำสั่งไหนพัง/ตัวแปรไม่ถูกตั้ง (กัน `$IMAGE` ว่างแล้ว build tag ผิด) |
| `docker build -t "$IMAGE" .` | ส่ง context ผ่าน socket — **ไม่ใช่ bind mount** จึงไม่ติด phantom-mount |
| `docker image inspect ... {{.Id}}` | หลักฐานว่า image อยู่ใน daemon จริง |
| `docker push "$IMAGE"` | dockerd ของ host push ไป `localhost:5000` (host loopback → container registry) |
| `curl .../tags/list` | เช็คอิสระผ่าน Registry HTTP API (agent ใช้ host network จึงเห็น `localhost:5000`) |
| `grep -q "$SHORT_SHA"` | ถ้า tag ไม่อยู่ใน registry → stage แดง ทันที (ไม่ปล่อยให้ stage หลังไปเจอ `ImagePullBackOff`) |

> **ข้อจำกัด:** re-run commit เดิมจะ push tag เดิมซ้ำ (เนื้อหาเดิมจาก layer cache) — registry ไม่ได้ห้ามเขียนทับ tag. ตอน demo ให้ใช้ commit ใหม่ทุกรอบเพื่อให้ SHA ใหม่ชัดเจน

และเพิ่มใน `.gitignore`: `trivy-report.sarif`

---
### ขั้นที่ 18 — Jenkinsfile — stage `Container Scan` `[CLI]`
```groovy
        stage('Container Scan') {
            agent { label 'linux-build' }
            steps {
                // trivy image เป็น root (-u 0:0) เพราะต้องอ่าน docker.sock ที่ได้มาจาก --volumes-from;
                // ห้าม -v "$WORKSPACE:..." (phantom bind mount) — ใช้ --volumes-from เหมือน Syft/OPA
                sh 'rm -f trivy-report.sarif'
                sh '''
                    docker run --rm -u 0:0 \
                        -v trivy-cache:/root/.cache \
                        --volumes-from jenkins-agent-linux-build -w "$WORKSPACE" \
                        aquasec/trivy:latest image \
                            --format sarif -o trivy-report.sarif \
                            --severity HIGH,CRITICAL --exit-code 0 \
                            "$IMAGE"
                '''
                sh '''
                    docker run --rm -u 0:0 --volumes-from jenkins-agent-linux-build -w "$WORKSPACE" \
                        node:20-alpine chown "$(id -u):$(id -g)" trivy-report.sarif
                    test -s trivy-report.sarif
                '''
                sh '''
                    docker run --rm -u 0:0 \
                        -v trivy-cache:/root/.cache \
                        --volumes-from jenkins-agent-linux-build \
                        aquasec/trivy:latest image \
                            --severity HIGH,CRITICAL --exit-code 1 \
                            "$IMAGE"
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'trivy-report.sarif', allowEmptyArchive: true
                }
            }
        }
```

#### อธิบายทีละบรรทัด

| โค้ด | อธิบาย |
|---|---|
| `rm -f trivy-report.sarif` | workspace ถาวรข้าม build — เริ่มสะอาดทุกรอบ (idempotent ตามกฎ Lab 06) |
| รอบที่ 1 `--exit-code 0 --format sarif -o trivy-report.sarif` | **สร้างรายงานเสมอ** ไม่ว่าเจออะไร → ไฟล์มีแน่นอนก่อนถึง gate |
| `--severity HIGH,CRITICAL` | รายงานและ gate ใช้ระดับเดียวกัน |
| `--volumes-from jenkins-agent-linux-build` | ได้ทั้ง workspace จริง **และ** `/var/run/docker.sock` (mount ของ agent ถูกคัดลอกมาด้วย) → Trivy เห็น image ที่เพิ่ง build ใน daemon โดยไม่ต้อง pull |
| `-w "$WORKSPACE"` | เขียนไฟล์ลง workspace จริงของ Jenkins |
| `-v trivy-cache:/root/.cache` | named volume เก็บ DB ของ Trivy (ไม่ใช่ path ของ workspace) — รอบสองไม่ต้องโหลด DB ใหม่ |
| `-u 0:0` | ไฟล์ที่ได้เป็นของ root → step `chown` (ใช้ pattern เดียวกับ SBOM) คืนสิทธิ์ให้ uid 1000 ก่อนถึง gate |
| `test -s trivy-report.sarif` | เช็คอิสระว่าไฟล์มีเนื้อหาจริง (ไม่ใช่ phantom) |
| รอบที่ 2 `--exit-code 1` | **gate**: เจอ HIGH/CRITICAL → exit 1 → stage แดง → `Blue/Green Deploy` ไม่ถูกรันเพราะ stage ต่อกันตามลำดับ. แสดงตาราง CVE ใน console เป็นหลักฐาน. (ไม่เขียนไฟล์ จึงไม่มีไฟล์ root ค้าง) |
| `post.always.archiveArtifacts` | รันแม้ stage แดง → SARIF ของ build ที่ถูก block ยังดาวน์โหลดได้ (`allowEmptyArchive` กัน step ล้มซ้ำซ้อนถ้า scan ยังไม่ทันสร้างไฟล์) |

**ตรวจ local ตามที่ Jenkins จะรันจริง** (รันบน agent): `docker exec -e IMAGE="$IMAGE" -e WORKSPACE=/home/jenkins/agent/workspace/<job> jenkins-agent-linux-build sh -c '...'` — หรือใช้ `.claude/skills/cicd-verify-loop/verify-loop.py` ตาม Step 0.

> ถ้า DB ดาวน์โหลดไม่ได้ (`TOOMANYREQUESTS` จาก ghcr.io) ให้เพิ่ม `--db-repository public.ecr.aws/aquasecurity/trivy-db` ทั้งสองคำสั่ง

---
### ขั้นที่ 19 — Jenkinsfile — stage `Blue/Green Deploy` `[CLI]`
```groovy
        stage('Blue/Green Deploy') {
            agent { label 'linux-build' }
            environment {
                KUBECONFIG = '/home/jenkins/.kube/config'
            }
            steps {
                script {
                    sh 'kubectl version --client'

                    // 1) สีที่ live อยู่ตอนนี้ — บันทึกก่อนแตะอะไรทั้งหมด
                    def current = sh(
                        script: "kubectl get svc taskflow -o jsonpath='{.spec.selector.color}'",
                        returnStdout: true
                    ).trim()
                    if (current != 'blue' && current != 'green') {
                        error("Service/taskflow has unexpected color selector: '${current}'")
                    }
                    // 2) สีที่จะ deploy (สีตรงข้าม)
                    def next = current == 'blue' ? 'green' : 'blue'

                    // 3) เก็บลง env เพื่อให้ post.failure มองเห็น (ตัวแปร def หายนอก script)
                    env.PREV_COLOR = current
                    env.NEXT_COLOR = next
                    env.DEPLOY_IMAGE = (params.DEPLOY_FAULT == 'bad-image')
                        ? "${env.REGISTRY}/${env.APP_NAME}:0000000-does-not-exist"
                        : env.IMAGE
                    env.VERIFY_PATH = (params.DEPLOY_FAULT == 'post-switch-fail') ? '/health-broken' : '/health'

                    echo "Current active color: ${current}"
                    echo "Deploying new image to: ${next}  (image: ${env.DEPLOY_IMAGE}, fault mode: ${params.DEPLOY_FAULT})"
                }
                sh '''
                    set -eu
                    echo "===== Service/taskflow BEFORE ====="
                    kubectl get svc taskflow -o yaml

                    # 4) deploy ลงสีที่ไม่ live — Service ยังชี้ $PREV_COLOR ตลอดช่วงนี้
                    kubectl set image deployment/taskflow-$NEXT_COLOR taskflow="$DEPLOY_IMAGE"
                    kubectl rollout status deployment/taskflow-$NEXT_COLOR --timeout=90s

                    # 5) smoke test สีใหม่ "ก่อน" สลับ — ยิงผ่าน Service ประจำสี taskflow-<color>
                    kubectl delete pod smoke-$BUILD_NUMBER --ignore-not-found
                    out=$(kubectl run smoke-$BUILD_NUMBER --rm -i --restart=Never \
                        --image=curlimages/curl:8.10.1 --command -- \
                        curl -fsS --max-time 5 "http://taskflow-$NEXT_COLOR:8080/health")
                    echo "Smoke test response: $out"
                    echo "$out" | grep -q '"status":"ok"'
                    echo "Smoke test PASSED on $NEXT_COLOR (Service still -> $(kubectl get svc taskflow -o jsonpath='{.spec.selector.color}'))"

                    # 6) สลับ traffic
                    PATCH=$(printf '{"spec":{"selector":{"color":"%s"}}}' "$NEXT_COLOR")
                    kubectl patch svc taskflow --type merge -p "$PATCH"
                    echo "Service switched: $PREV_COLOR -> $(kubectl get svc taskflow -o jsonpath='{.spec.selector.color}')"

                    # 7) post-switch verification ผ่าน Service จริง (ถ้าพัง → post.failure rollback)
                    kubectl delete pod verify-$BUILD_NUMBER --ignore-not-found
                    vout=$(kubectl run verify-$BUILD_NUMBER --rm -i --restart=Never \
                        --image=curlimages/curl:8.10.1 --command -- \
                        curl -fsS --max-time 5 "http://taskflow:8080$VERIFY_PATH")
                    echo "Post-switch verification response: $vout"
                    echo "$vout" | grep -q '"status":"ok"'

                    echo "===== Service/taskflow AFTER ====="
                    kubectl get svc taskflow -o yaml
                    echo "Blue/Green deploy SUCCESS: active color is now $NEXT_COLOR"
                '''
            }
            post {
                failure { /* ดูขั้นที่ 20 */ }
            }
        }
```

> **หมายเหตุการ normalize:** ตัวอย่างในคู่มือ PDF ที่สกัดมาเสียรูป (เช่น `def next = current -= 'blue' ? 'green' : 'blue'` และ `kubectl run`/`curl` ที่ quote/ขึ้นบรรทัดผิด) ไม่ได้ถูกคัดลอกตรง ๆ — ถูกเขียนใหม่เป็น Groovy/shell ที่ถูกต้องข้างต้น: `def next = current == 'blue' ? 'green' : 'blue'` และ `kubectl run ... --command -- curl -fsS ...`. นอกจากนี้ URL `http://taskflow-<color>:8080` ในตัวอย่างเดิมใช้ได้จริงเพราะเราสร้าง `Service/taskflow-<color>` (ขั้นที่ 10) ไม่ใช่เพราะชื่อ Deployment

#### อธิบายทีละส่วน

| ส่วน | อธิบาย |
|---|---|
| `environment { KUBECONFIG ... }` (ระดับ stage) | ชี้ kubeconfig ที่ทำไว้ในขั้นที่ 9 ไม่พึ่ง `$HOME` |
| `jsonpath='{.spec.selector.color}'` | อ่านสี live จากของจริงใน cluster ไม่เก็บสถานะไว้ที่อื่น (pipeline ไม่มี state ข้าม build) |
| ตรวจ `current` เป็น blue/green | ถ้า Service ถูกแก้ผิดมือ ให้แดงทันทีแทนที่จะเดาเอา |
| `def next = current == 'blue' ? 'green' : 'blue'` | ตรรกะสลับสี; `==` เปรียบเทียบ ไม่ใช่ `-=` |
| `env.PREV_COLOR/NEXT_COLOR/DEPLOY_IMAGE/VERIFY_PATH` | ค่า `env.*` ใช้ได้ทั้งใน `sh` (เป็น `$PREV_COLOR`) และใน `post {}` ของ stage — **นี่คือกลไกที่ทำให้ rollback จำสีเดิมได้** ดูขั้นที่ 20 |
| `sh '''...'''` (single-quote) | Groovy ไม่ interpolate — ตัวแปร `$...` ถูกขยายโดย shell จาก env ที่ export; หลีกเลี่ยง quote/escape ซ้อนกับ JSON ด้วย `printf` |
| `kubectl set image deployment/taskflow-$NEXT_COLOR taskflow="$DEPLOY_IMAGE"` | `taskflow=` คือชื่อ container ใน manifest (`name: taskflow`) — ถ้าชื่อไม่ตรงได้ `unable to find container` |
| `rollout status --timeout=90s` | รอ pod ใหม่ Ready (readiness probe `/health` ผ่าน). เกินเวลา → exit ≠ 0 → stage แดง |
| `kubectl run smoke-$BUILD_NUMBER --rm -i --restart=Never --command -- curl ...` | pod ชั่วคราวใน cluster ใช้ CoreDNS หา `taskflow-green` → ClusterIP ของ `Service/taskflow-green` → pod สีเขียวเท่านั้น. **ไม่ผ่าน `Service/taskflow`** จึงทดสอบสีใหม่ได้ทั้งที่ traffic จริงยังอยู่สีเก่า |
| `out=$(...)` + `grep -q '"status":"ok"'` | ตัดสินผลจากเนื้อ response ไม่พึ่งการ propagate exit code ของ `kubectl run` อย่างเดียว (เวอร์ชันต่าง ๆ ต่างกัน); ถ้า curl ล้ม `set -e` หยุดที่บรรทัด assign |
| `kubectl delete pod smoke-... --ignore-not-found` | กัน `AlreadyExists` จาก pod ค้างของรอบก่อน |
| `kubectl patch svc ... --type merge` | **จุดสลับ traffic จุดเดียว** อยู่หลัง smoke test ผ่านเท่านั้น (ลำดับบรรทัดคือหลักฐานให้กรรมการ) |
| post-switch verification ผ่าน `taskflow:8080` | เช็คว่า traffic จริงหลังสลับใช้ได้; ในโหมด `post-switch-fail` ยิง `/health-broken` (404 → `curl -f` ล้ม) เพื่อจำลอง "หลังสลับแล้วเพิ่งพบว่าพัง" |
| `echo "===== Service/taskflow BEFORE/AFTER ====="` + `-o yaml` | ได้ deliverable ข้อ 1 ใน console log ตรง ๆ (แคปหน้านี้ได้เลย) |

---
### ขั้นที่ 20 — Jenkinsfile — Automatic Rollback (`post.failure`) `[CLI]`
แทน `post { failure { /* ... */ } }` ข้างบนด้วย:

```groovy
            post {
                failure {
                    script {
                        if (!env.PREV_COLOR) {
                            echo 'Blue/Green deploy failed BEFORE the current color was recorded - Service untouched, nothing to roll back.'
                        } else {
                            echo "❌ Blue/Green deploy FAILED (target color: ${env.NEXT_COLOR}, fault mode: ${params.DEPLOY_FAULT})"
                            sh '''
                                echo "Active color BEFORE rollback: $(kubectl get svc taskflow -o jsonpath='{.spec.selector.color}')"
                                echo "Rolling Service selector back to: $PREV_COLOR"
                                PATCH=$(printf '{"spec":{"selector":{"color":"%s"}}}' "$PREV_COLOR")
                                kubectl patch svc taskflow --type merge -p "$PATCH"
                                ACTIVE=$(kubectl get svc taskflow -o jsonpath='{.spec.selector.color}')
                                echo "Rollback complete. Active color is now: $ACTIVE"
                                # ทำให้ inactive color ที่พังกลับไป revision ก่อนหน้า (ไม่กระทบ traffic)
                                kubectl rollout undo deployment/taskflow-$NEXT_COLOR || true
                                echo "===== Service/taskflow AFTER ROLLBACK ====="
                                kubectl get svc taskflow -o yaml
                                [ "$ACTIVE" = "$PREV_COLOR" ]
                                echo "Active color remains: $PREV_COLOR"
                            '''
                        }
                    }
                }
            }
```

#### ตัวแปรและ scope (จุดที่ทำให้ rollback "ดูถูกแต่ไม่ทำงาน")

| ปัญหา | ทำไม | วิธีแก้ในโค้ดนี้ |
|---|---|---|
| `def current` ที่ประกาศใน `script {}` ของ `steps` | เป็น local variable — **มองไม่เห็นใน `post {}`** (scope คนละบล็อก) ถ้าอ้าง `current` ใน post จะได้ `MissingPropertyException` หรือค่าว่าง → rollback ไม่ทำงานเงียบ ๆ | กำหนด `env.PREV_COLOR = current` ใน `steps` ก่อนเปลี่ยนอะไรทั้งหมด. `env.*` เป็นของทั้ง build จึงอ่านได้ใน `post.failure` |
| พังก่อนถึงบรรทัดที่บันทึก `env.PREV_COLOR` | เช่น `kubectl` ติดต่อ cluster ไม่ได้ | `if (!env.PREV_COLOR)` พิมพ์ข้อความชัดเจนแทน patch ด้วยค่าว่าง (ซึ่งจะทำลาย Service) |
| `post.failure` ระดับ **stage** | รันบน agent + workspace เดิมของ stage → มี `kubectl`/`KUBECONFIG` (environment ระดับ stage ใช้ใน post ของ stage เดียวกันได้) | ไม่ต้อง `node {}` ซ้อน |
| Rollback patch ล้มเอง | ถ้า cluster ล่มหมด rollback ก็ทำไม่ได้ | บรรทัด `[ "$ACTIVE" = "$PREV_COLOR" ]` ทำให้ post แดงเสียงดัง ไม่เงียบ |

(ทางเลือกอื่นที่ valid: `writeFile file: 'prev_color.txt', text: current` แล้ว `readFile` ใน post — ใช้ `env.*` เพราะสั้นกว่าและไม่ทิ้งไฟล์ใน workspace)

#### Log ที่ควรเห็นเมื่อ rollback ทำงาน (ตัวอย่างโหมด `post-switch-fail`)

```
Current active color: blue
Deploying new image to: green  (image: localhost:5000/taskflow-api:abc1234, fault mode: post-switch-fail)
...
Smoke test PASSED on green (Service still -> blue)
Service switched: blue -> green
curl: (22) The requested URL returned error: 404
...
❌ Blue/Green deploy FAILED (target color: green, fault mode: post-switch-fail)
Active color BEFORE rollback: green
Rolling Service selector back to: blue
service/taskflow patched
Rollback complete. Active color is now: blue
Active color remains: blue
```

---
### ขั้นที่ 21 — Commit, push แล้วรัน Jenkins ครั้งแรก `[CLI + UI]`
ทำ Step 0 (รันทุก stage ซ้ำ 2 รอบบน agent จริง) ให้เขียวก่อน จึง commit — เพิ่มเฉพาะไฟล์ของ Lab 07 (ห้าม `git add .`)

```bash
git add Jenkinsfile k8s/ kind/ .gitignore
git commit -m "add: Lab 07 build/scan/blue-green pipeline with automatic rollback"
git push origin lab07
```

ใช้ job `taskflow-pipeline` เดิม → Configure → Branch Specifier เป็น `*/lab07` → Save → Build Now **ครั้งเดียว**

---
### ขั้นที่ 22 — Successful Demonstration `[CLI + UI]`
**ก่อนเริ่ม:** `git commit` การเปลี่ยนแปลงใหม่ (SHA ต้องไม่ซ้ำ), `DEPLOY_FAULT=none`, จด `kubectl get svc taskflow -o jsonpath='{.spec.selector.color}'` ไว้ (สมมติ `blue`)

1. **Build with Parameters** → `DEPLOY_FAULT = none` *(Build Now ครั้งแรกหลังเพิ่ม `parameters {}` จะรันด้วยค่า default — ครั้งถัดไปจึงเห็นปุ่ม Build with Parameters)*
2. รอจนเขียวทั้ง `Build Image → Container Scan → Blue/Green Deploy`
3. **เก็บหลักฐาน:**
   - 📸 Console ของ `Build Image` (เห็น `Verified in registry: localhost:5000/taskflow-api:<sha>`)
   - 📸 Console ของ `Blue/Green Deploy` ช่วง `Service/taskflow BEFORE` (selector `color: blue`)
   - 📸 Console ช่วง rollout + `Smoke test PASSED on green (Service still -> blue)` + `Service switched: blue -> green`
   - 📸 Console ช่วง `Service/taskflow AFTER` (selector `color: green`)
4. **ตรวจนอก Jenkins:**
   ```bash
   kubectl get svc taskflow -o yaml
   kubectl get svc taskflow -o jsonpath='{.spec.selector.color}{"\n"}'        # green
   kubectl get deployment taskflow-green -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
   curl -fsS http://localhost:5000/v2/taskflow-api/tags/list
   ```

---
### ขั้นที่ 23 — Failed Deployment / Rollback Demonstration `[CLI + UI]`
#### วิธี inject ความล้มเหลวที่แนะนำ: `DEPLOY_FAULT = post-switch-fail` (เร็ว ~1 นาที และ rollback เห็นชัดที่สุด)

| โหมด | เกิดอะไร | พิสูจน์อะไร | เวลา |
|---|---|---|---|
| **`post-switch-fail` (แนะนำ)** | rollout ผ่าน, smoke test ผ่าน, Service **สลับแล้ว** → verification หลังสลับ (`/health-broken` → 404) ล้ม → `post.failure` patch กลับ | selector เปลี่ยน blue→green→blue จริง, rollback step "ทำงานจริงและเปลี่ยนสถานะ" | ~1 นาที |
| `bad-image` | `set image` ไปที่ tag ที่ไม่มี → pod `ErrImagePull/ImagePullBackOff` → `rollout status` timeout 90 วิ → ล้ม **ก่อนสลับ** | Service ไม่เคยถูกแตะ (ความปลอดภัย) และ `post.failure` ยังรันพร้อม log rollback | ~2 นาที |

> เหตุผล: ใน `bad-image` Service ไม่เคยเปลี่ยน การ patch กลับเป็น no-op — พิสูจน์ความปลอดภัยได้ แต่ **ไม่เห็นว่ากลไก rollback เปลี่ยนสถานะ**. กรรมการให้คะแนน "rollback demonstrated" จึงใช้ `post-switch-fail` เป็นหลักฐานหลัก และ `bad-image` เป็นหลักฐานเสริม (ถ้ามีเวลา)
> `post-switch-fail` คือ fault-injection hook (ตัวตรวจหลังสลับตั้งใจยิง path ที่ไม่มี) — ระบุไว้ตรง ๆ ในรายงาน ไม่ใช่การแก้แอปให้พัง

**ขั้นตอน:**

1. จด `kubectl get svc taskflow -o jsonpath='{.spec.selector.color}'` (สมมติ `green` หลังรอบสำเร็จ → target จะเป็น `blue`)
2. commit ใหม่ (SHA ใหม่) → **Build with Parameters** → `DEPLOY_FAULT = post-switch-fail`
3. คาดว่า: `Build Image`, `Container Scan` เขียว; `Blue/Green Deploy` **แดง**; pipeline แดง
4. 📸 **ต้องแคป:**
   - Console ช่วง `Smoke test PASSED on blue` → `Service switched: green -> blue` → `curl: (22) ... 404`
   - Console ช่วง `❌ Blue/Green deploy FAILED` → `Rolling Service selector back to: green` → `Rollback complete. Active color is now: green` → `Active color remains: green`
   - Stage View ที่ `Blue/Green Deploy` เป็นสีแดง
5. **ตรวจนอก Jenkins:**
   ```bash
   kubectl get svc taskflow -o jsonpath='{.spec.selector.color}{"\n"}'     # ต้องเป็น green (สีเดิม)
   kubectl get endpointslices -l kubernetes.io/service-name=taskflow -o jsonpath='{.items[*].endpoints[*].addresses[*]}{"\n"}'
   kubectl get pods -l app=taskflow,color=green -o jsonpath='{.items[*].status.podIP}{"\n"}'   # IP ตรงกัน
   ```
6. (เสริม) ทำซ้ำกับ `DEPLOY_FAULT = bad-image` และแคป `kubectl get pods` ที่เห็น `ImagePullBackOff` + log rollback
7. กลับสู่ปกติ: Build ใหม่ด้วย `none` ยืนยันว่า pipeline ยังสลับได้

---
# ส่วนที่ C — สรุปและ Reference (หลังทำครบขั้นที่ 23)
## สรุป Deliverables ที่ต้องส่ง
| # | Deliverable ทางการ | หลักฐานที่ต้องเก็บ | มาจากขั้นที่ |
|---|---|---|---|
| 1 | `kubectl get svc taskflow -o yaml` **ก่อนและหลัง** blue/green switch สำเร็จ | console log `Service/taskflow BEFORE` และ `AFTER` จาก build `none` + (แนะนำ) `kubectl get svc taskflow -o yaml` รันเองนอก Jenkins | 22 |
| 2 | Trivy SARIF ของ image build | artifact `trivy-report.sarif` (screenshot หน้า Artifacts + ไฟล์ที่ดาวน์โหลด) — ถ้ามี ให้มีของ build ที่ถูก block ด้วย (พิสูจน์ว่า archive ได้แม้แดง) | 13, 18 |
| 3 | Console log ของ deploy ที่ล้มและ rollback อัตโนมัติ | console ช่วง `❌ Blue/Green deploy FAILED` … `Rollback complete` + `kubectl get svc ... jsonpath` หลังจบ | 23 |

---
## เกณฑ์การให้คะแนน (100 คะแนน)
| หัวข้อ | คะแนน | เช็คตัวเอง |
|---|---|---|
| Image tag ไม่เปลี่ยนแปลงได้ (immutable) และ push ถูกต้อง | 20 | ☐ tag = `taskflow-api:<7-char SHA>` ☐ `tags/list` มี SHA ☐ ไม่มี `latest` ทั้ง registry/Jenkinsfile/manifest ☐ `docker pull` กลับมาได้ |
| Trivy gate block image ที่มีช่องโหว่ได้จริง | 25 | ☐ `--exit-code 1 --severity HIGH,CRITICAL` ☐ มี build แดงที่ `Container Scan` จาก image ที่มีช่องโหว่จริง ☐ `Blue/Green Deploy` ถูกข้าม ☐ SARIF archive แม้แดง |
| Blue/green switch ใช้ได้ และ smoke test ก่อนสลับ | 30 | ☐ log เรียง: set image → rollout → smoke test → patch ☐ Service YAML ก่อน/หลังต่างที่ `color` ☐ smoke test ยิง Service ประจำสี ไม่ใช่ `taskflow` |
| Automatic rollback แสดงผลจริง | 25 | ☐ log `Rolling Service selector back to: <สีเดิม>` จาก `post.failure` ☐ `jsonpath` หลังจบ = สีเดิม ☐ พิสูจน์ด้วย `post-switch-fail` |

---
## Reference 1 — Troubleshooting
| # | Symptom | Root cause | Fastest fix |
|---|---|---|---|
| 1 | `kind: command not found` | ยังไม่ติดตั้ง | ขั้นที่ 2 (`~/.local/bin`, ไม่ต้อง sudo) |
| 2 | `kubectl: command not found` (ใน Jenkins, host มีแล้ว) | binary อยู่บน host ไม่ได้อยู่ใน agent (หรือ agent ถูกสร้างใหม่) | `docker cp "$(command -v kubectl)" jenkins-agent-linux-build:/usr/local/bin/kubectl` + `chmod 755` ด้วย `-u root` |
| 3 | `trivy: command not found` | ไม่ได้ติดตั้ง (ตั้งใจ) | ใช้ `docker run aquasec/trivy` ตามขั้นที่ 12 / 18 |
| 4 | `docker push`: `connection refused` / `dial tcp 127.0.0.1:5000` | registry container ไม่ได้รัน | `docker ps -a --filter name=kind-registry`; `docker start kind-registry`; `curl localhost:5000/v2/` |
| 5 | Pod `ErrImagePull`: `dial tcp 127.0.0.1:5000: connect: connection refused` (Events ของ pod) | kind node resolve `localhost:5000` เป็นตัวมันเอง — ไม่มี containerd mirror | ทำขั้นที่ 8 ข้อ (2) (`hosts.toml`) แล้วเช็ค `crictl pull` |
| 6 | Pod `ImagePullBackOff`: `no such host kind-registry` | registry ไม่ได้ต่อ network `kind` (หรือ cluster สร้างใหม่หลังต่อ) | `docker network connect kind kind-registry` |
| 7 | `ErrImagePull` / `manifest unknown` | tag ไม่มีใน registry (พิมพ์ผิด, push ไม่สำเร็จ, หรือใช้ `bad-image` โดยตั้งใจ) | `curl localhost:5000/v2/taskflow-api/tags/list`; เทียบกับ `kubectl get deploy -o jsonpath` |
| 8 | `kubectl apply`: `selector does not match template labels` / Deployment สองชุดแย่ง pod | `matchLabels` ≠ pod labels, หรือ sed สร้าง green ไม่ครบ | `grep -n 'color' k8s/deployment-*.yaml`; ต้อง `blue` ล้วน / `green` ล้วนต่อไฟล์ |
| 9 | Service ไม่มี endpoints (`kubectl get endpointslices` ว่าง), curl timeout | Service selector ไม่ตรง pod label, หรือ pod ยังไม่ Ready | `kubectl get pods --show-labels`; `kubectl describe svc taskflow` |
| 10 | smoke test: `Could not resolve host: taskflow-green` | ไม่มี `Service/taskflow-green` (ชื่อ Deployment ไม่ใช่ DNS name) หรือ apply `service-colors.yaml` ไม่ครบ | `kubectl apply -f k8s/service-colors.yaml`; `kubectl get svc` |
| 11 | `permission denied ... /var/run/docker.sock` ใน agent | user `jenkins` ไม่อยู่ group ของ socket (ปกติอยู่: group 123) หรือ sidecar ไม่ได้ root | `docker exec jenkins-agent-linux-build id`; Trivy ต้อง `-u 0:0` |
| 12 | `trivy-report.sarif` ไม่เจอ/ว่าง ทั้งที่ exit 0 (phantom workspace mount) | ใช้ `-v "$WORKSPACE:..."` แทน `--volumes-from` | ใช้ `--volumes-from jenkins-agent-linux-build -w "$WORKSPACE"`; `docker exec jenkins-agent-linux-build ls -l $WORKSPACE` เช็คซ้ำ |
| 13 | Trivy แดงแล้ว artifact ไม่มี SARIF | รวม `--exit-code 1` กับ `-o` ไว้ในคำสั่งเดียวก่อนสร้างรายงาน หรือไม่มี `post.always` | ใช้สองรอบตามขั้นที่ 18 + `post { always { archiveArtifacts ... } }` |
| 14 | Trivy: `TOOMANYREQUESTS` / DB download fail | rate limit ghcr.io / ไม่มีเน็ต | `--db-repository public.ecr.aws/aquasecurity/trivy-db` หรือรอแล้วรันซ้ำ (cache ใน `trivy-cache`) |
| 15 | Trivy แดงตั้งแต่ image จริง (ไม่ได้ตั้งใจ) | CVE ใน base/npm ของ `node:20-alpine` | ขั้นที่ 13 กรณี B |
| 16 | Rollback ไม่ทำงาน / ข้อความ `MissingPropertyException: current` | ใช้ตัวแปร `def` ใน `post.failure` (scope ไม่ข้าม) | ใช้ `env.PREV_COLOR` (ขั้นที่ 20) |
| 17 | สอง build รันพร้อมกัน สลับสีชนกัน | ไม่มี `disableConcurrentBuilds()` (agent มี 2 executor) | ใส่ใน `options` (ขั้นที่ 16) |
| 22 | `error: timed out waiting for the condition` จาก `rollout status` | pod ไม่ Ready (image pull, `/health` ไม่ตอบ, resource ไม่พอ) | `kubectl describe pod -l color=<next>`, `kubectl logs ...`; ตรวจ events; เพิ่ม `--timeout` ถ้าแค่ช้า |
| 23 | Deploy สำเร็จแต่ยังเห็นของเก่า | `set image` tag เดิม (commit เดิม) → ไม่มี rollout ใหม่ / cache | ใช้ commit ใหม่ทุกรอบ; `kubectl get deploy -o jsonpath=...image` ดู SHA จริง |
| 20 | `Unable to connect to the server` / x509 | cluster ถูกสร้างใหม่ (stale kubeconfig ใน agent) | ทำขั้นที่ 9 ซ้ำ |
| 21 | `kind create cluster`: ชื่อซ้ำ / `node(s) already exist` | cluster เก่าค้าง | `kind delete cluster --name taskflow` แล้วสร้างใหม่ + ทำ 8.3, 8.4 ซ้ำ |
| 22 | registry ต่อ network ผิด: `docker push` ได้แต่ node pull ไม่ได้ (หรือกลับกัน) | publish port ที่ `127.0.0.1` ถูกต้องสำหรับ host แต่ node ต้องไปทาง network `kind` | host/agent ใช้ `localhost:5000`; node ใช้ `kind-registry:5000` (ผ่าน hosts.toml) — เช็คทั้งสองทางตามขั้นที่ 8 |
| 23 | `kubectl run ... AlreadyExists` | pod smoke ค้างจากรอบที่ถูก abort | `kubectl delete pod -l run --ignore-not-found` หรือลบตามชื่อ; โค้ดมี `delete --ignore-not-found` อยู่แล้ว |
| 24 | `docker exec taskflow-control-plane crictl pull` ไม่ทำงาน แม้ตั้ง hosts.toml ถูก | containerd config key ไม่ตรงเวอร์ชัน (containerd 2.x) | `docker exec taskflow-control-plane cat /etc/containerd/config.toml \| grep -n config_path`; ถ้าไม่มี ให้หา key ของ registry plugin ตามเวอร์ชัน (เช่น `io.containerd.cri.v1.images`) หรือใช้ fallback `kind load docker-image` เพื่อ debug และระบุเป็น deviation |

---
## Reference 2 — Known Limitations / Lab Shortcuts
- **kind + registry:2 บนเครื่องเดียว** แทน cloud registry/cluster — เพียงพอตาม deliverable (พิสูจน์ flow push → scan → deploy → switch → rollback)
- Registry เป็น HTTP ไม่มี auth/TLS; image tag **ไม่ถูกบังคับ immutable ที่ registry** (เขียนทับ tag เดิมได้) — immutability มาจากวินัย "tag = Git SHA" ของ pipeline ในระบบจริงใช้ registry ที่รองรับ tag immutability และ pin ด้วย digest
- `kubectl` ติดตั้งด้วย `docker cp` เข้า container agent (หายถ้าสร้าง agent ใหม่); ถาวรควรเติมใน `Dockerfile.agent` ภายหลัง
- kubeconfig อยู่ในไฟล์บน agent ไม่ได้เก็บใน Jenkins Credentials — ระบบจริงใช้ credential + RBAC ของ service account เฉพาะ
- Trivy ใช้ tag `latest` ของ **เครื่องมือ** (สอดคล้อง Lab 06); กฎ "ห้าม latest" ใช้กับ image ของ *แอป* ที่ deploy
- Blue/Green ใช้ Deployment 1 replica ต่อสี; ไม่ได้ทำ traffic shifting แบบค่อยเป็นค่อยไป (Service selector สลับทีเดียว)
- `post-switch-fail` เป็น fault-injection hook ที่อยู่ใน Jenkinsfile (ควรเอาออกหรือปกป้องใน production)
- ไม่มีการ `kubectl apply` manifest ใน pipeline (Jenkins ใช้ `set image` เท่านั้น): manifest ใน `k8s/` เป็น bootstrap — อย่า re-apply ทับหลัง deploy เพราะ `__IMAGE__` จะรีเซ็ต image
- ค่า CVE เปลี่ยนตามเวลา: ผลของ Trivy กับ `node:20-alpine` ที่ผ่าน/ไม่ผ่านวันนี้อาจต่างจากวันส่งงาน — เก็บ SARIF จริงเสมอ

---
## Reference 3 — Cleanup
### 3.1 ⛔ ห้ามทำก่อนเก็บ screenshot/deliverable ครบ

- `kind delete cluster --name taskflow` (ลบ Service/Deployment — หลักฐาน `kubectl get svc -o yaml` ที่ต้องรันสดหายหมด)
- `docker rm -f kind-registry` (ลบ tag/ภาพ registry ที่ใช้ยืนยัน)
- ลบ build ของ Jenkins ที่เก็บ artifact (`trivy-report.sarif`) และ console log

### 3.2 ✅ Reset เพื่อทำ Lab ซ้ำ / เก็บกวาดหลังส่งงาน

```bash
# ลบเฉพาะ workload (เก็บ cluster ไว้) — ใช้ตอนอยากเริ่ม bootstrap ใหม่
kubectl delete -f k8s/service.yaml -f k8s/service-colors.yaml -f k8s/deployment-blue.yaml -f k8s/deployment-green.yaml --ignore-not-found
kubectl delete pod -l run --ignore-not-found 2>/dev/null; kubectl get pods       # เช็ค smoke pod ไม่ค้าง

# ลบ cluster ทั้งก้อน (หลังส่งงานแล้ว)
kind delete cluster --name taskflow

# ลบ registry (หลังส่งงานแล้ว)
docker rm -f kind-registry

# (ออปชัน) ล้าง volume cache ของ Trivy และ image ที่ build ไว้
docker volume rm trivy-cache
docker rmi $(docker images --format '{{.Repository}}:{{.Tag}}' | grep '^localhost:5000/taskflow-api:') 2>/dev/null

# ถ้าสร้าง cluster ใหม่: ต้องทำขั้นที่ 8 (registry ↔ kind) และ 8.4 (kubeconfig ใน agent) ซ้ำ
```

**ตรวจหลัง cleanup:** `kind get clusters`, `docker ps -a --filter name=kind`, `docker volume ls | grep trivy`
