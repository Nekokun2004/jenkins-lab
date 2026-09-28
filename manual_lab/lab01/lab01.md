# Lab 01 — ติดตั้ง Jenkins และสร้าง Job แรก

**อ้างอิงจาก:** Deck 04–05 — Introduction to Jenkins / Installing Jenkins
**ระยะเวลา:** 3 ชั่วโมง · **รูปแบบ:** ทำคนเดียว
**Repo ที่ใช้:** `taskflow-api`

---

## เป้าหมายของแล็บนี้ (Objectives)

1. ตั้งค่า Jenkins controller ให้รันบน Docker และผ่านขั้นตอน first-run setup ให้เสร็จ
2. เข้าใจสถาปัตยกรรม controller / agent / executor โดยการลงมือตั้งค่า agent ตัวที่สองจริง ๆ
3. สร้างและรัน Freestyle job ที่ checkout repo `taskflow-api` มา

## พื้นหลัง — ทำไมต้องแยก controller กับ agent

Jenkins แบ่งงานออกเป็น 2 ส่วน:
- **Controller** — ตัวจัดคิว build, เก็บ config, serve หน้าเว็บ UI
- **Agent** — ตัวที่ลงมือรันคำสั่ง build จริง ๆ (npm install, test, etc.)

เหตุผลที่แยกกันคือ ถ้า build หนัก ๆ ไปรันบน controller ตรง ๆ มันจะไปแย่ง resource กับตัว UI/scheduler เอง ทำให้ Jenkins ทั้งระบบอืด แนวคิดนี้จะเจอซ้ำในทุกแล็บถัดไป ผ่าน keyword `agent { ... }` ในทุก Jenkinsfile

## สภาพแวดล้อมที่ต้องมี

- Docker Desktop หรือ Docker Engine, RAM ว่างอย่างน้อย 2 GB
- GitHub account ที่มี repo `taskflow-api` อยู่แล้ว (fork หรือสร้างเอง)
- Jenkins image: `jenkins/jenkins:lts-jdk21` (**ห้ามเปลี่ยน tag** เพราะแล็บถัดไปอ้างอิง config ที่ผูกกับเวอร์ชันนี้)

---

## ขั้นตอนทั้งหมด

### ขั้นที่ 1 — Fork/เตรียม repo `[UI — เว็บ GitHub]`

เข้า GitHub แล้ว fork หรือ push repo `taskflow-api` ขึ้น account ตัวเอง ให้เป็น public หรือถ้าเป็น private ต้องตั้ง deploy key ให้ Jenkins อ่านได้ (จะตั้งตอน Lab 04 ก็ได้ ตอนนี้ public ไปก่อนง่ายสุด)

---

### ขั้นที่ 2 — รัน Jenkins controller `[CLI]`

```bash
docker run -d --name jenkins \
  -p 8080:8080 -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home \
  jenkins/jenkins:lts-jdk21
```

**อธิบายทีละส่วน:**
- `-v jenkins_home:/var/jenkins_home` → สร้าง **named volume** ชื่อ `jenkins_home` เก็บข้อมูลทั้งหมดไว้ (jobs, plugins, credentials) แม้ container จะถูกลบหรือ restart ข้อมูลก็ไม่หาย — **ห้ามลบ volume นี้จนกว่าจะทำครบ 10 แล็บ**
- `-p 8080:8080` → พอร์ตสำหรับเปิดหน้าเว็บ Jenkins
- `-p 50000:50000` → พอร์ตมาตรฐานที่ Jenkins ใช้รับการเชื่อมต่อจาก **inbound agent** (จะใช้ตอนขั้นที่ 4)

**ตัวอย่างผลลัพธ์ที่ควรเห็น:**
```bash
$ docker ps
CONTAINER ID   IMAGE                        STATUS          PORTS
a1b2c3d4e5f6   jenkins/jenkins:lts-jdk21    Up 10 seconds   0.0.0.0:8080->8080/tcp, 0.0.0.0:50000->50000/tcp
```

---

### ขั้นที่ 3 — ผ่านขั้นตอน first-run setup `[CLI → UI]`

**[CLI]** ดึงรหัสผ่านเริ่มต้น:
```bash
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```
ผลลัพธ์จะเป็นรหัสยาว ๆ ประมาณ `852b1f40b4bc484ea506c9aacd457736` — **เก็บไว้ใช้ครั้งเดียว ห้ามใส่ในรายงานหรือสกรีนช็อตที่ส่ง**

**[UI]** เปิดเบราว์เซอร์ไปที่ `http://localhost:8080`:
1. หน้า **Unlock Jenkins** → วางรหัสผ่านด้านบน → **Continue**
2. เลือก **Install suggested plugins** → รอจนติดตั้งเสร็จ
   > ถ้ามี plugin ไหน error ให้สกรีนช็อตข้อความ error ไว้ก่อน อย่าเพิ่งกด retry มั่ว ๆ
3. หน้า **Create First Admin User** → สร้าง account แอดมินของตัวเอง (เก็บรหัสผ่านไว้เอง ไม่ใส่ในรายงาน)
4. หน้า **Instance Configuration** → ปล่อย Jenkins URL เป็น `http://localhost:8080/` ตามเดิม
5. **Save and Finish** → **Start using Jenkins**

เมื่อเห็นหน้า Dashboard ของ Jenkins แปลว่าเสร็จขั้นนี้

---

### ขั้นที่ 4 — เพิ่ม agent ตัวที่สอง `linux-build` `[UI → CLI]`

**[UI]** ไปที่ **Manage Jenkins → Nodes → New Node**
- ตั้งชื่อ: `linux-build`
- ประเภท: **Permanent Agent**
- ตั้งค่า: Remote root directory เช่น `/home/jenkins/agent`, Labels: `linux-build`, Launch method: **Launch agent by connecting it to the controller** (inbound)
- กด Save → ระบบจะสร้าง **agent secret** ให้ พร้อมคำสั่ง docker ตัวอย่างมาให้เลย (คัดลอกมาใช้ได้)

**[CLI]** รัน agent container โดยใช้ secret ที่ได้ (ตัวอย่างรูปแบบคำสั่ง):
```bash
docker run -d --name jenkins-agent-linux-build \
  --network host \
  jenkinsci/inbound-agent:latest \
  -url http://localhost:8080/ \
  <AGENT_SECRET> \
  linux-build
```
> หมายเหตุ: ค่าที่แน่นอน (secret, url, ชื่อ agent) ให้คัดลอกจากปุ่ม "copy this command" ที่ Jenkins UI สร้างให้ในหน้า node นั้นตรง ๆ อย่าพิมพ์เองเพราะ secret ยาวและพิมพ์ผิดง่าย

**[UI]** กลับไปที่หน้า Manage Jenkins → Nodes ตรวจสอบว่า `linux-build` ขึ้นสถานะ **online** และมี **1 executor**

**📸 ต้องแคปหน้าจอตรงนี้ (deliverable ข้อ 1):** หน้า Nodes ที่เห็นทั้ง built-in node และ `linux-build` เป็นสีเขียว/online พร้อมกัน

---

### ขั้นที่ 5 — สร้าง Freestyle job `taskflow-smoke` `[UI]`

**New Item → Freestyle project → ชื่อ `taskflow-smoke`**

ตั้งค่าในหน้า config:
- **Source Code Management** → Git → ใส่ URL ของ repo fork เช่น `https://github.com/<username>/taskflow-api.git`
- **Restrict where this project can be run** → ติ๊กเลือก แล้วใส่ label expression: `linux-build` (บังคับให้รันบน agent ตัวที่สองเท่านั้น ไม่ใช่ built-in node)
- **Build Steps → Add build step → Execute shell:**
```bash
npm ci
echo "Node version: $(node -v)"
```

> ถ้า agent container ยังไม่มี Node.js ติดตั้งไว้ ให้ใช้ image ที่มี Node อยู่แล้ว หรือถ้าจะใช้ image `jenkins/inbound-agent` เปล่า ๆ ตามที่โจทย์บอก ("a plain Docker container running the jenkins/inbound-agent image is sufficient") ให้ตรวจสอบว่ามี node ติดตั้งอยู่ในนั้นก่อน ไม่งั้น `npm ci` จะ fail — ถ้า fail ให้แจ้งมา จะช่วย debug ต่อได้

---

### ขั้นที่ 6 — Trigger build และตรวจสอบผล `[UI]`

กด **Build Now** ที่ job `taskflow-smoke` แล้วเปิด **Console Output**

**ตัวอย่างผลลัพธ์ที่ควรเห็น (โดยประมาณ):**
```
Started by user admin
Running on linux-build in /home/jenkins/agent/workspace/taskflow-smoke
[taskflow-smoke] $ npm ci
added 445 packages in 12s
[taskflow-smoke] $ echo "Node version: $(node -v)"
Node version: v20.15.1
Finished: SUCCESS
```

จุดสำคัญที่ต้องดูคือบรรทัด `Running on linux-build in ...` — นี่คือหลักฐานว่า build รันบน agent ที่ถูกกำหนดไว้จริง ไม่ใช่ built-in node

**📸 ต้องแคปหน้าจอ/เก็บ log ตรงนี้ (deliverable ข้อ 2):** console output เต็ม ๆ ของ build ที่เขียว (SUCCESS)

---

### ขั้นที่ 7 — เขียนคำอธิบาย 1 ย่อหน้า (เขียนเอง ไม่มี UI/CLI)

**โจทย์ถามว่า:** ถ้า Jenkins controller container ถูก restart กลางที่ build กำลังรันอยู่ จะเกิดอะไรขึ้น?

**สิ่งที่ควรพูดถึงในย่อหน้า (ไม่ใช่แค่ตอบ "ไม่รู้" หรือพูดกว้าง ๆ):**
- controller คือตัวจัดการ UI/คิว/สถานะ build — พอ container ของ controller หยุดกลางคัน การเชื่อมต่อระหว่าง controller กับ agent ที่กำลังรันอยู่จะขาด
- build ที่ค้างอยู่มักจะจบลงด้วยสถานะ failed/aborted เพราะ controller ไม่สามารถรับ log หรือสั่งงานต่อได้ แม้ agent อาจจะยังรันคำสั่งของมันต่อไปเรื่อย ๆ ก็ตาม (เป็น process แยกกันคนละ container)
- เมื่อ controller กลับมาออนไลน์ (เพราะข้อมูลอยู่ใน `jenkins_home` volume) มันจะไม่รู้จัก state ของ build ที่ค้างอยู่ตอนนั้นอีกต่อไป และ agent จะต้อง reconnect เข้ามาใหม่
- ดังนั้นการดีไซน์ pipeline ที่ดีจึงต้องเผื่อเรื่อง idempotency/retry ไว้ ไม่ใช่สมมติว่า controller ไม่มีวันล่ม

**📝 นี่คือ deliverable ข้อ 3** — ต้องเป็นคำพูดของตัวเอง 1 ย่อหน้า

---

## สรุป Deliverables ที่ต้องส่ง (ตรงกับโจทย์)

| # | รายการ | เก็บจากขั้นตอนไหน |
|---|---|---|
| 1 | สกรีนช็อต Manage Jenkins → Nodes เห็นทั้ง 2 node online | ขั้นที่ 4 |
| 2 | Console output เต็มของ build ที่เขียว | ขั้นที่ 6 |
| 3 | คำอธิบาย 1 ย่อหน้า เรื่อง controller restart กลาง build | ขั้นที่ 7 |

## เกณฑ์การให้คะแนน (Assessment)

| หัวข้อ | คะแนน |
|---|---|
| Jenkins เข้าถึงได้ และมี 2 node ทำงานจริง | 35 |
| Freestyle job build ผ่าน (เขียว) บน agent ที่กำหนด | 35 |
| คำอธิบายพฤติกรรม controller/agent เมื่อ fail ถูกต้อง | 30 |

---

## หมายเหตุ / ข้อควรระวัง

- ห้ามลบ volume `jenkins_home` จนกว่าจะทำครบทั้ง 10 แล็บ เพราะทุกแล็บถัดไปสร้างต่อบน Jenkins ตัวเดียวกัน (plugin, credentials, jobs ที่ตั้งไว้จะคงอยู่)
- ห้ามใส่รหัสผ่าน initial admin password หรือรหัสผ่าน admin ส่วนตัวลงในรายงาน สกรีนช็อต หรือไฟล์ใด ๆ ที่จะส่ง
- พอร์ต `50000` ใช้เฉพาะสำหรับ agent เชื่อมต่อเข้ามา อย่าไปชนกับพอร์ตอื่นที่จะตั้งในแล็บถัดไป (เช่น NodePort ของ Kubernetes ใน Lab 09)
