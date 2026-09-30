# Jenkins Lab — คำสั่งสำคัญ (Cheat Sheet)

รวมคำสั่งที่ใช้จริงระหว่างย้าย Jenkins มาเครื่องใหม่ (`wasugree`) + แก้ปัญหา agent
`linux-build` — ไว้อ้างอิงตอนต้องทำซ้ำ หรือย้ายเครื่องอีกรอบ

---

## 0. Restart เครื่อง / Restart container

### 0.1 Restart เครื่อง (reboot) แล้วต้องทำอะไร

Docker daemon เปิดเองตอน boot (`systemctl is-enabled docker` = enabled) แต่ container จะกลับมาเองหรือไม่ขึ้นกับ restart policy:

| Container | Restart policy | หลัง reboot |
|---|---|---|
| `jenkins` | `unless-stopped` | ขึ้นเอง |
| `kind-registry` | `always` | ขึ้นเอง |
| `localstack` | `unless-stopped` | ขึ้นเอง **แต่ข้อมูลหาย** (ดูล่าง) |
| `taskflow-control-plane` (kind) | `on-failure` | **ไม่ขึ้นเอง** ต้อง `docker start` |
| `sonarqube` | `no` | **ไม่ขึ้นเอง** ต้อง `docker start` |
| `jenkins-agent-linux-build` | `no` | **ไม่ขึ้นเอง** ต้อง `docker start` |

**ห้ามลบ/สร้าง container ใหม่ตอน reboot** — แค่ `docker start` ของเดิม: `sonarqube` ไม่มี volume (ข้อมูลและ webhook อยู่ใน container นั้น), agent มี `kubectl`/`kind`/kubeconfig อยู่ใน container/image เดิม, kind cluster อยู่ใน `taskflow-control-plane`

ทำตามลำดับ:

```bash
# 1) ดูสถานะ — jenkins, kind-registry, localstack ควรขึ้นเองแล้ว
docker ps -a --format 'table {{.Names}}\t{{.Status}}'

# 2) kind cluster (รอ Ready ประมาณ 1-2 นาที)
docker start taskflow-control-plane
until docker exec taskflow-control-plane kubectl --kubeconfig /etc/kubernetes/admin.conf get nodes 2>/dev/null | grep -q ' Ready'; do sleep 5; done

# 3) SonarQube (รอ status = UP ประมาณ 1-2 นาที)
docker start sonarqube
until curl -s localhost:9000/api/system/status | grep -q '"UP"'; do sleep 5; done

# 4) Jenkins agent (เริ่มหลัง jenkins ขึ้นแล้ว — ใช้ WebSocket จึงต่อกลับเองได้)
docker start jenkins-agent-linux-build

# 5) LocalStack: ขึ้นเองแต่ว่างเปล่า (Community ไม่เก็บข้อมูลข้าม restart)
#    bucket taskflow-tfstate และ EC2/security group ที่เคย apply หายทั้งหมด → สร้าง bucket ใหม่
docker exec -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test -e AWS_DEFAULT_REGION=us-east-1 \
  jenkins-agent-linux-build aws --endpoint-url=http://localhost:4566 s3 mb s3://taskflow-tfstate
```

ถ้ายังไม่ได้ `terraform destroy` ก่อน reboot ไม่ต้องกังวล: state กับ resource หายพร้อมกัน จึงไม่ขัดกัน (Lab 08 เริ่ม plan ใหม่ได้เลย)

**ตรวจว่าทุกอย่างกลับมาปกติ:**

```bash
docker exec jenkins-agent-linux-build kubectl get nodes                 # taskflow-control-plane Ready
docker exec jenkins-agent-linux-build kubectl get svc taskflow -o jsonpath='{.spec.selector.color}{"\n"}'   # สี blue/green เดิม ไม่เปลี่ยน
docker exec jenkins-agent-linux-build curl -fsS http://localhost:5000/v2/   # {}
curl -s localhost:9000/api/system/status                                # "status":"UP"
curl -s localhost:4566/_localstack/health | grep -E '"(ec2|s3)"'         # available/running
# Jenkins UI: Manage Jenkins -> Nodes -> linux-build ต้อง online (ถ้า offline รอ 1 นาที หรือ docker restart jenkins-agent-linux-build)
```

**ถ้า kind ขึ้นแล้ว pod ค้าง:** รอสักพักก่อน (kubelet/containerd ต้อง sync) — ถ้าผ่านไป 3-5 นาทีแล้ว `kubectl get pods -A` ยังไม่ Running ค่อย `docker restart taskflow-control-plane` (อย่าลบ cluster)

**อยากให้ 3 ตัวที่ไม่ขึ้นเองกลับมาเองด้วย** (ทำครั้งเดียว ไม่ต้อง recreate container):

```bash
docker update --restart unless-stopped taskflow-control-plane sonarqube jenkins-agent-linux-build
```

หมายเหตุ: limit RAM ที่ตั้งไว้ (`docker update --memory ...`) อยู่กับ container เดิม ไม่หายตอน reboot/restart แต่จะหายถ้า `docker rm` แล้วสร้างใหม่

### 0.2 Restart container หลัก 2 ตัวที่ใช้อยู่ (`jenkins` + agent)

ใช้บ่อยสุด เวลา container ค้าง/ดับ หรือแก้ config แล้วอยากให้ Jenkins โหลดใหม่:

```bash
# Jenkins controller
docker restart jenkins

# Jenkins agent (linux-build)
docker restart jenkins-agent-linux-build
```

**ถ้า `docker restart` ไม่ขึ้น** (เช่น container โดน exit ค้างจาก Jenkins สั่ง restart ตัวเองข้างใน UI แล้วไม่มีใครสั่งเปิดกลับ) ให้เช็คสถานะก่อนแล้วค่อย `docker start`:

```bash
docker ps -a --filter "name=jenkins"
docker start jenkins
docker start jenkins-agent-linux-build
```

`jenkins` container ตั้ง restart policy เป็น `unless-stopped` ไว้แล้ว (กันเคส Jenkins สั่ง restart ตัวเองจากในหน้า UI แล้ว container ค้างดับ) เช็คได้ด้วย:

```bash
docker inspect jenkins --format '{{.HostConfig.RestartPolicy.Name}}'
```

⚠️ agent (`jenkins-agent-linux-build`) **ไม่มี** restart policy นี้ — ถ้า container ตัวนี้ดับ ต้อง `docker start` เอง ไม่ auto กลับมาเอง

---

## 1. Backup `jenkins_home` (จากเครื่อง/container เดิม)

```bash
docker run --rm --volumes-from jenkins \
  -v $(pwd):/backup alpine \
  tar czf /backup/jenkins_home.tgz /var/jenkins_home
```

ก่อน extract เสมอ เช็คพื้นที่ว่างก่อน (บทเรียนจากรอบก่อนที่พื้นที่เต็ม):

```bash
df -h /
```

---

## 2. Restore `jenkins_home` เข้า volume ใหม่ + สตาร์ท container

```bash
docker volume create jenkins_home
docker run --rm -v jenkins_home:/var/jenkins_home -v $(pwd):/backup alpine \
  sh -c "tar xzf /backup/jenkins_home.tgz -C /"
docker run -d --name jenkins -p 8080:8080 -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home jenkins/jenkins:lts-jdk21
```

**เช็คว่า restore สำเร็จ (ไม่ต้อง setup wizard ใหม่):**

```bash
docker exec jenkins test -f /var/jenkins_home/secrets/initialAdminPassword \
  && echo "wizard ยังไม่เสร็จ" || echo "restore แล้วผ่าน wizard ไปแล้ว"
```

---

## 3. Build agent image (มี Node.js 20 ฝังมาด้วย)

`Dockerfile.agent`:

```dockerfile
FROM jenkins/inbound-agent:latest-jdk21
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm --version \
    && node --version \
    && rm -rf /var/lib/apt/lists/*
USER jenkins
```

```bash
docker build -t jenkins-agent-node20 -f Dockerfile.agent .
```

---

## 4. รัน agent container ต่อกับ Jenkins (`linux-build`)

⚠️ **จุดสำคัญที่พลาดมาก่อน:** ต้องใส่ `-webSocket` ด้วย ไม่งั้นจะเจอ error
`The server rejected the connection: None of the protocols were accepted`
เพราะ controller เครื่องนี้ใช้ WebSocket ไม่ใช่ raw TCP JNLP4 — ตัวเลข secret
ที่ผิดไม่ใช่สาเหตุ ให้เอา `-secret` ตรงจากหน้า **Manage Jenkins → Nodes → linux-build**
เท่านั้น (มันคำนวณจาก instance key ข้างในเครื่อง หา/เดาเองจากไฟล์ใน `jenkins_home` ไม่ได้)

```bash
# ถ้ามี container เก่าค้างอยู่ ลบก่อน
docker rm -f jenkins-agent-linux-build

docker run -d --name jenkins-agent-linux-build \
  --network host \
  jenkins-agent-node20 \
  -url http://localhost:8080/ \
  -secret <SECRET_จากหน้า_Manage_Jenkins_Nodes> \
  -name "linux-build" \
  -webSocket \
  -workDir "/home/jenkins/agent"
```

**เช็คว่าต่อติดจริง (ต้องเห็น 2 บรรทัดนี้ใน log ไม่ใช่แค่ container running):**

```bash
docker logs jenkins-agent-linux-build --tail 20
# ต้องเห็น: "WebSocket connection open" แล้วตามด้วย "Connected"

docker exec jenkins-agent-linux-build node -v
docker exec jenkins-agent-linux-build npm -v
```

จากนั้นไปเช็คที่ **[UI] Manage Jenkins → Nodes → linux-build** ว่าขึ้นสถานะ online จริง
(container รันอยู่ ไม่ได้แปลว่า controller เห็นว่า online เสมอไป ต้องดู UI ยืนยันอีกที)

---

## 5. รันแอป `taskflow-api` ทดสอบเอง (ไม่พึ่ง Jenkins)

```bash
cd jenkins-lab
npm ci
npm test          # ใช้ in-memory store ไม่ต้องมี DB
npm start         # http://localhost:8080/health
```

หรือรันเต็มคู่กับ Postgres:

```bash
docker compose up -d --build
curl http://localhost:8080/health
```

---

## 6. Restore ทดสอบ (throwaway instance แยก port ไม่ชนของจริง)

```bash
docker volume create jenkins_home_restore_test
docker run --rm -v jenkins_home_restore_test:/var/jenkins_home -v $(pwd):/backup alpine \
  sh -c "tar xzf /backup/jenkins_home.tgz -C /"
docker run -d --name jenkins-restore-test -p 8081:8080 \
  -v jenkins_home_restore_test:/var/jenkins_home jenkins/jenkins:lts-jdk21

# ทดสอบเสร็จแล้วลบทิ้ง
docker rm -f jenkins-restore-test
docker volume rm jenkins_home_restore_test
```

---

## สรุปสิ่งที่ต้องเช็คทุกครั้งหลังย้ายเครื่อง

1. `df -h /` — พื้นที่พอก่อน extract/build เสมอ
2. `docker ps` — container `jenkins` ขึ้น และ mount volume `jenkins_home` ถูกต้อง
3. secret ของ agent เอาจากหน้า UI สดๆ เท่านั้น อย่าจำจากเครื่องเก่ามาใช้เดา
4. ใส่ `-webSocket` ในคำสั่งรัน agent เสมอ (คอนโทรลเลอร์นี้ปิด raw TCP inbound)
5. เช็คสถานะ node ที่ UI จริง ไม่เชื่อแค่ `docker ps` ว่า container รันอยู่
