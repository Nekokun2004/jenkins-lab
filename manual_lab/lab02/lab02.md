# Lab 02 — Jenkins Plugins, Global Tools & RBAC

**อ้างอิงจาก:** Deck 04–05, 11 — Introduction to Jenkins / Best Practices
**ระยะเวลา:** 2 ชั่วโมง · **รูปแบบ:** ทำคนเดียว

---

## เป้าหมายของแล็บนี้ (Objectives)

1. ติดตั้ง plugin ชุดที่ pipeline จริงต้องใช้ (มากกว่าชุด "suggested" เริ่มต้น)
2. ตั้งค่า Global Tool auto-installer เพื่อให้ Jenkinsfile ไม่ต้องพึ่ง agent ที่ลง Node/JDK เองด้วยมือ
3. เปลี่ยนจาก security realm แบบเปิดของ Jenkins เป็น role-based access control แบบ least-privilege

## พื้นหลัง

Jenkins เริ่มต้นมาแบบ "เปลือย ๆ" แล้วโตขึ้นผ่าน ecosystem plugin กว่า 1800 ตัว — ชุด plugin ที่จำเป็น (Git, Docker Pipeline, Blue Ocean, SonarQube Scanner, Kubernetes, Credentials Binding) คือสิ่งที่เปลี่ยน controller เปล่า ๆ ให้กลายเป็นแพลตฟอร์มที่ทุกแล็บถัดไปคาดหวังว่ามีอยู่แล้ว

อีกเรื่องสำคัญ: ถ้าปล่อย Jenkins ไว้ตามค่า default **ผู้ใช้ที่ login ทุกคนจะมีสิทธิ์แอดมินเต็มทันที** — สิ่งแรกที่ควรทำก่อนเริ่มงาน pipeline จริงคือปิดช่องโหว่นี้

## สภาพแวดล้อมที่ต้องมี

- Jenkins ที่ทำ Lab 01 เสร็จแล้ว (มี node `linux-build` online, job `taskflow-smoke` เขียว)
- **หมายเหตุจากที่ทำมา:** ถ้าใช้เครื่องที่เพิ่ง restore `jenkins_home` มา ให้แน่ใจว่า controller + agent online ก่อนเริ่มแล็บนี้

---

## ขั้นตอนทั้งหมด

### ขั้นที่ 1 — ติดตั้ง plugin ชุดจำเป็น `[UI]`

ไปที่ **Manage Jenkins → Plugins → Available plugins** แล้วค้นหาทีละตัว ติ๊กเลือกทั้งหมดนี้ แล้วกด **Install**:

- `Docker Pipeline`
- `Blue Ocean`
- `SonarQube Scanner`
- `Kubernetes`
- `Credentials Binding`
- `Slack Notification`

หลังติดตั้งเสร็จ อาจมีให้เลือก **"Restart Jenkins when installation is complete and no jobs are running"** — ติ๊กได้เลย ปลอดภัย เพราะข้อมูลอยู่ใน `jenkins_home` volume อยู่แล้ว (เหมือนที่เราคุยกันไปตอน Lab 01 เรื่อง controller restart)

**📸 ต้องแคปหน้าจอตรงนี้ (deliverable ข้อ 1 บางส่วน):** หน้า **Manage Jenkins → Plugins → Installed plugins** ที่เห็น 6 ตัวนี้ติดตั้งสำเร็จ

---

### ขั้นที่ 2 — ตั้งค่า Global Tool auto-installer `[UI]`

ไปที่ **Manage Jenkins → Tools**

**NodeJS installations:**
- กด **Add NodeJS**
- Name: `node20`
- Version: เลือก `NodeJS 20.x.x` (ตัวล่าสุดในสาย 20)
- ปล่อย "Install automatically" ไว้ (ค่า default)

**JDK installations:**
- กด **Add JDK**
- Name: `temurin-21`
- ติ๊ก "Install automatically" → เลือก installer แบบ "Install from adoptium.net" → เลือกเวอร์ชัน 21

กด **Save**

> 💡 **จุดสำคัญที่เชื่อมกับปัญหาที่เราเจอใน Lab 01:** ตอน Lab 01 เราเจอปัญหา `npm: not found` เพราะ agent container ไม่มี Node.js ติดมา ต้อง `docker exec` ลงมือแพตช์เอง — **auto-installer ตัวนี้แก้ปัญหานั้นแบบถาวรกว่ามาก** เพราะ Jenkins จะดาวน์โหลด Node.js มาลงใน workspace ของ agent เองอัตโนมัติทุกครั้งที่ job สั่ง `tools { nodejs 'node20' }` โดยไม่ต้องพึ่ง image ที่เตรียม Node.js ไว้ล่วงหน้าเลย

---

### ขั้นที่ 3 — ทดสอบ auto-installer ด้วย scratch Jenkinsfile `[UI]`

สร้าง Pipeline jobใหม่ (ไม่ต้องผูกกับ SCM ก็ได้ แค่ scratch ทดสอบ):

**New Item → Pipeline → ชื่อ `node-tool-test`**

ในหน้า config เลื่อนไปที่ **Pipeline → Definition: Pipeline script** แล้ววางโค้ดนี้:

```groovy
pipeline {
    agent { label 'linux-build' }
    tools {
        nodejs 'node20'
    }
    stages {
        stage('Check Node') {
            steps {
                sh 'node -v'
                sh 'npm -v'
            }
        }
    }
}
```

Save → **Build Now** → เปิด Console Output

**ตัวอย่างผลลัพธ์ที่ควรเห็น:**
```
[Pipeline] tool
[Pipeline] sh
+ node -v
v20.18.1
[Pipeline] sh
+ npm -v
10.8.2
Finished: SUCCESS
```

ถ้าเห็นแบบนี้ แปลว่า auto-installer ทำงานจริง — agent ไม่จำเป็นต้องมี Node.js ติดตัวมาเองอีกต่อไป

---

### ขั้นที่ 4 — ติดตั้ง RBAC และปิด anonymous access `[UI]`

**4.1 ติดตั้ง plugin**
Manage Jenkins → Plugins → ค้นหา `Role-based Authorization Strategy` → Install

**4.2 เปลี่ยน Authorization Strategy**
Manage Jenkins → Security →
- **Authorization** → เลือก **"Role-Based Strategy"**
- Save

**4.3 ปิด anonymous read access**
ในหน้าเดียวกัน (หรือ Manage Jenkins → Security อีกครั้งหลัง save) ต้องแน่ใจว่า **ไม่มี** permission ใด ๆ ผูกกับ user/group ชื่อ `anonymous` เลย (จะไปตั้งในขั้นถัดไปตอนสร้าง role matrix)

**4.4 สร้าง roles**
Manage Jenkins → **Manage and Assign Roles → Manage Roles**

สร้าง 2 global/project role:
- **`developer`** → ติ๊กเฉพาะ permission: `Job/Build`, `Job/Read` และในช่อง Pattern ใส่ regex: `taskflow-.*` (จำกัดสิทธิ์แค่ job ที่ชื่อขึ้นต้นด้วย taskflow-)
- **`admin`** → ติ๊ก `Overall/Administer` (full control)

Save

**4.5 มอบหมาย role**
Manage Jenkins → **Manage and Assign Roles → Assign Roles**
- ใส่ user ของตัวเอง → assign role `admin`
- สร้าง user ใหม่ (Manage Jenkins → Users → Create User) ชื่อ เช่น `partner` → assign role `developer`

**📸 ต้องแคปหน้าจอตรงนี้ (deliverable ข้อ 2 บางส่วน):** หน้า roles matrix ที่เห็นทั้ง `developer` และ `admin` พร้อม permission ที่ตั้งไว้

---

### ขั้นที่ 5 — ทดสอบ credential ที่มองเห็นได้แค่โดยการอ้างอิง `[UI]`

**5.1 สร้าง folder-scoped credential**
Manage Jenkins → Credentials → เลือก scope ที่เป็น folder (หรือถ้ายังไม่มี folder ให้สร้าง folder ชื่อ `taskflow` ก่อนแล้วเข้าไปตั้ง credential ในนั้น)
- Kind: **Secret text**
- Secret: พิมพ์อะไรก็ได้ เช่น `dummy-secret-value-123`
- ID: `taskflow-test-secret`

**5.2 ทดสอบด้วย developer account**
- Logout จาก admin account
- Login ด้วย user `partner` (ที่มี role `developer`)
- ลองเข้า job ใน `taskflow-.*` แล้วดูว่าตอนเลือก credential ใน dropdown (เช่น ถ้าไปเพิ่ม step `withCredentials`) จะเห็น **ID** `taskflow-test-secret` ให้เลือกอ้างอิงได้
- แต่ถ้าลองเข้า Manage Jenkins → Credentials ด้วย account นี้ **ควรถูกบล็อกไม่ให้เห็นค่า secret จริง** (หรือเข้าหน้า Credentials ไม่ได้เลยถ้า role ไม่ได้ให้สิทธิ์ Credentials/View)

**📸 ต้องแคปหน้าจอตรงนี้ (deliverable ข้อ 2):** หลักฐานว่า developer account อ้างอิง credential ID ได้ แต่เห็นค่าจริงไม่ได้

---

### ขั้นที่ 6 — รัน `taskflow-smoke` ผ่าน Blue Ocean `[UI]`

กลับมา login ด้วย admin account → เปิด **Blue Ocean** (จากเมนูซ้าย หรือ URL `/blue`) → เลือก `taskflow-smoke` → กด run

ดู pipeline graph ที่ Blue Ocean แสดง ควรเห็น stage ตรงกับที่ตั้งไว้ใน job (แม้ Freestyle job อาจแสดงเป็น stage เดียวรวม ๆ ก็ได้ ไม่เหมือน Declarative Pipeline ที่มีหลาย stage ชัดเจน — สังเกตความต่างไว้เป็นข้อสังเกตในรายงานได้)

---

### ขั้นที่ 7 — Backup และเขียน/verify restore procedure `[CLI]`

**Backup:**
```bash
docker run --rm --volumes-from jenkins \
  -v $(pwd):/backup alpine \
  tar czf /backup/jenkins_home.tgz /var/jenkins_home
```

**Restore procedure (3 บรรทัด ตามที่โจทย์ขอ):**
```bash
docker volume create jenkins_home_restore_test
docker run --rm -v jenkins_home_restore_test:/var/jenkins_home -v $(pwd):/backup alpine sh -c "tar xzf /backup/jenkins_home.tgz -C /"
docker run -d --name jenkins-restore-test -p 8081:8080 -v jenkins_home_restore_test:/var/jenkins_home jenkins/jenkins:lts-jdk21
```

> หมายเหตุ: ใช้ **container/volume ชื่อใหม่ + port ใหม่ (8081)** เพื่อไม่ชนกับ Jenkins ตัวจริงที่รันอยู่แล้วที่ port 8080 — นี่คือ "second, throwaway Jenkins container" ตามที่โจทย์ต้องการ

**Verify:**
เปิด `http://localhost:8081` ควรเห็นหน้า dashboard เดียวกับตัวจริงทุกอย่าง (ไม่ใช่ setup wizard) plugin/job/role ที่เพิ่งตั้งไปครบ

ทดสอบเสร็จแล้ว **ลบ container/volume ทดสอบทิ้งได้เลย** (ไม่ต้องเก็บไว้ กินพื้นที่เปล่า ๆ):
```bash
docker rm -f jenkins-restore-test
docker volume rm jenkins_home_restore_test
```

**📸/📁 ต้องเก็บตรงนี้ (deliverable ข้อ 3):** ไฟล์ `jenkins_home.tgz` + สกรีนช็อตหน้า dashboard ของ container ทดสอบที่ port 8081 แสดงว่า restore สำเร็จ

---

## สรุป Deliverables ที่ต้องส่ง

| # | รายการ | เก็บจากขั้นตอนไหน |
|---|---|---|
| 1 | สกรีนช็อต plugin ที่ติดตั้ง + Global Tool auto-installer ทั้ง 2 ตัว | ขั้นที่ 1, 2 |
| 2 | สกรีนช็อต roles matrix + หลักฐานว่า developer เห็นค่า credential ไม่ได้ | ขั้นที่ 4, 5 |
| 3 | ไฟล์ `jenkins_home.tgz` + สกรีนช็อต restore สำเร็จบน container ที่สอง | ขั้นที่ 7 |

## เกณฑ์การให้คะแนน

| หัวข้อ | คะแนน |
|---|---|
| ติดตั้ง plugin ครบ + tool auto-installer ทำงานจริง | 25 |
| RBAC จำกัดสิทธิ์ developer ถูกต้อง, ปิด anonymous access | 30 |
| Credential ใช้อ้างอิงได้แต่ไม่เปิดเผยค่าให้ non-admin | 25 |
| Backup restore สำเร็จบน Jenkins instance ที่สอง | 20 |

---

## หมายเหตุ / ข้อควรระวัง

- ก่อนเริ่มแล็บนี้ เช็ค `df -h /` ก่อนเสมอ — บทเรียนจาก Lab 01: plugin + auto-installed tools (Node.js, JDK) กินพื้นที่เพิ่มพอสมควร
- Restore test container ใช้ port แยก (8081) และ volume แยกชื่อ เพื่อไม่ไปทับ Jenkins ตัวจริงที่กำลังใช้งานอยู่
- Role pattern `taskflow-.*` เป็น regex ต้องตรงกับชื่อ job จริง (`taskflow-smoke`, `node-tool-test` จะ**ไม่**เข้าเงื่อนไขนี้ เพราะไม่ได้ขึ้นต้นด้วย `taskflow-`)
