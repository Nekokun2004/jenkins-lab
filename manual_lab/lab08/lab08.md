# Lab 08 — Infrastructure as Code in the Pipeline

**อ้างอิงจาก:** Deck 00d — Infrastructure as Code
**ระยะเวลา:** 4 ชั่วโมง · **รูปแบบ:** ทำเป็นคู่ (ทำคนเดียวได้ตามความสะดวก)

---

## เป้าหมายของแล็บนี้

1. เขียน Terraform provision environment ให้ `taskflow-api` พร้อม remote state
2. Lint + security-scan IaC ก่อน `plan` ทุกครั้ง, gate `apply` ด้วย human approval
3. ใช้ Ansible ตั้งค่า host ที่ Terraform สร้างไว้

## พื้นหลัง

Lab 07 สมมติว่ามี Kubernetes cluster อยู่แล้ว แล็บนี้สร้าง**ตัวโครงสร้างพื้นฐานเอง**แบบ version-controlled — ต่างจากการคลิกในหน้าเว็บ console ตรงที่ทุกการเปลี่ยนแปลง environment กลายเป็น diff ที่ review ได้

---

## ⚠️ การตัดสินใจออกแบบที่สำคัญ — อ่านก่อนเขียนโค้ด

โจทย์บอกว่า "against LocalStack or a real free-tier cloud account — instructor's choice" — เลือก **LocalStack** (ฟรี, local, ไม่ต้องสมัคร cloud account) แต่มีข้อจำกัดสำคัญที่ต้องรู้ก่อน:

### ข้อจำกัดของ LocalStack Community Edition

**`aws_instance` ใน LocalStack Community ไม่ใช่เครื่องจริงที่ SSH เข้าได้** — มันแค่จำลอง metadata (สร้าง/ลบ/describe ได้ แต่ไม่มี process จริงรันอยู่ให้ต่อเข้าไปได้) Pro edition ถึงจะมี container จริงให้ต่อ SSH ได้ ซึ่งต้องเสียเงิน

**ทางแก้ที่ใช้ในแล็บนี้:** Terraform ยัง provision `aws_instance` + `aws_security_group` ผ่าน LocalStack จริง (ได้ output address, ได้ remote state, ได้ทุกอย่างที่โจทย์ข้อ 1 ต้องการ) — แต่ตอนที่ Ansible ต้อง "ไปตั้งค่า host" จริง ๆ **ให้ Ansible ต่อเข้า `localhost` (agent เอง) ผ่าน `ansible_connection=local` แทน** โดยยังคง**อ่านค่า address จาก `terraform output` มาใส่ใน inventory จริง** (แค่ไม่ได้ใช้ address นั้นเชื่อมต่อจริง เพราะ LocalStack ต่อไม่ได้อยู่ดี)

**ทำไมถึงยอมรับได้:** agent (`jenkins-agent-linux-build`) มี Docker CLI ต่อ socket เดียวกับ host อยู่แล้ว (ตั้งมาตั้งแต่ Lab 03) — สั่ง `docker pull localhost:5000/taskflow-api:<sha>` จาก agent ตรง ๆ จึงเป็นการทดสอบจริง ไม่ใช่ของปลอม แค่ "host ที่ configure" คือ agent เอง ไม่ใช่ EC2 instance จริงเท่านั้น — **เขียนข้อจำกัดนี้ไว้ในรายงานตรง ๆ** เป็นเรื่องที่ยอมรับได้และมีเหตุผลรองรับชัดเจน (โจทย์เองก็บอกว่า "instructor's choice" อยู่แล้ว)

### เลือกใช้เครื่องมือแบบ binary ไม่ใช่ Docker sidecar

ต่างจาก Lab 06 (Gitleaks/Syft/Cosign ที่ใช้ sidecar container) — แล็บนี้เลือก**ติดตั้ง Terraform, Ansible, tfsec, checkov เป็น binary ลงใน `Dockerfile.agent` ตรง ๆ** เพราะเครื่องมือกลุ่มนี้ถูกเรียกซ้ำหลาย stage ติดกัน (`terraform init` ต้องรันซ้ำในหลาย stage) — ถ้าใช้ sidecar จะต้องกลับไปเจอปัญหา phantom mount/uid/entrypoint แบบ Lab 06 ซ้ำอีก การ bake เข้า agent image ตัดปัญหาทั้งกลุ่มทิ้งไปเลย

### เรื่อง workspace แยกกันข้าม stage (บทเรียนจาก Lab 05/06)

Pipeline ยังเป็น `agent none` — ทุก stage ที่มี `agent { label 'linux-build' }` ของตัวเอง **จะได้ workspace แยกกัน** (`@2`, `@3`, ...) เหมือนที่เจอมาตลอด — ไฟล์ `tfplan` ที่สร้างใน stage `Terraform Plan` จะไม่มีอยู่ใน stage `Approval`/`Terraform Apply` ถ้าไม่ `stash`/`unstash` — จัดการเรื่องนี้ไว้ในโค้ดแล้ว (ดูขั้นที่ 10)

---

## สิ่งที่ต้องรู้ก่อนเริ่ม (สืบทอดจาก Lab 01-07)

| ข้อเท็จจริง | ผลกับ Lab 08 |
|---|---|
| agent ใช้ `--network host` | เข้า LocalStack ที่ `localhost:4566` ได้ตรง ๆ |
| agent mount `docker.sock` ของ host | `docker pull` ใน Ansible playbook คุยกับ dockerd ของ host จริง เห็น registry จาก Lab 07 |
| `pipeline { agent none }` | ทุก stage ใหม่ต้องมี `agent { label 'linux-build' }` |
| stage แยก agent = workspace แยกกัน | ต้อง `stash`/`unstash` ไฟล์ `tfplan` ข้าม stage |
| Registry `localhost:5000` จาก Lab 07 ยังใช้อยู่ | Ansible playbook pull image จากตรงนี้ |
| ห้ามแก้ stage เดิม (Lab 01-07) | เพิ่ม stage ใหม่ต่อท้าย `Blue/Green Deploy` เท่านั้น |

---

## ไฟล์ที่ต้องเพิ่ม

```
jenkins-lab/
├── Jenkinsfile                              # แก้: +6 stage ใหม่
├── infra/
│   ├── terraform/
│   │   ├── main.tf                          # ใหม่
│   │   └── .gitignore                       # ใหม่: กัน .terraform/, *.tfstate, tfplan หลุดเข้า git
│   └── ansible/
│       ├── playbook.yml                     # ใหม่
│       └── inventory/
│           └── dynamic_inventory.sh         # ใหม่
```

---

## ขั้นที่ 1 — อัปเดต `Dockerfile.agent` เพิ่มเครื่องมือ IaC ทั้งหมด `[CLI]`

```dockerfile
FROM jenkins/inbound-agent:latest-jdk21

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg unzip python3 python3-pip awscli \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && . /etc/os-release \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && curl -fsSL "https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_linux_amd64.zip" -o /tmp/terraform.zip \
    && unzip /tmp/terraform.zip -d /usr/local/bin \
    && rm /tmp/terraform.zip \
    && curl -fsSL https://github.com/aquasecurity/tfsec/releases/latest/download/tfsec-linux-amd64 -o /usr/local/bin/tfsec \
    && chmod +x /usr/local/bin/tfsec \
    && pip3 install --break-system-packages ansible ansible-lint checkov \
    && mkdir -p /home/jenkins/.terraform.d/plugin-cache && chown -R jenkins:jenkins /home/jenkins/.terraform.d \
    && npm --version && node --version && docker --version && docker compose version \
    && terraform --version && ansible --version && ansible-lint --version && tfsec --version && checkov --version && aws --version \
    && rm -rf /var/lib/apt/lists/*

USER jenkins
```

> **หมายเหตุ:** เวอร์ชัน Terraform `1.9.8` ที่ pin ไว้ อาจไม่มีอยู่แล้วถ้าเวลาผ่านไปนาน — ถ้าดาวน์โหลดไม่ได้ ให้เช็คเวอร์ชันล่าสุดที่ `https://releases.hashicorp.com/terraform/` แล้วแก้เลขในบรรทัดนั้น

**Build image ใหม่ + รัน agent ใหม่** (pattern เดิมที่ทำมาตลอด — ลบ container เก่า, build ใหม่, รันด้วย secret ปัจจุบันจากหน้า Jenkins Nodes):
```bash
docker build -t jenkins-agent-node20 -f Dockerfile.agent .
docker rm -f jenkins-agent-linux-build
docker run -d --name jenkins-agent-linux-build \
  --network host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --group-add 123 \
  -e TF_PLUGIN_CACHE_DIR=/home/jenkins/.terraform.d/plugin-cache \
  jenkins-agent-node20 \
  -url http://localhost:8080/ \
  -secret <SECRET_ปัจจุบันจากหน้า Jenkins> \
  -name "linux-build" \
  -workDir "/home/jenkins/agent"
```
`-e TF_PLUGIN_CACHE_DIR=...` ทำให้ provider binary (aws provider ~200MB) โหลดครั้งเดียว แล้วใช้ซ้ำได้ทุก stage/build แม้ workspace จะแยกกัน (path นี้อยู่นอก workspace ของ Jenkins เลยไม่ถูกล้าง)

---

## ขั้นที่ 2 — รัน LocalStack `[CLI]`

```bash
docker run -d --name localstack \
  --network host \
  -e SERVICES=ec2,s3,sts \
  localstack/localstack:latest
```

**รอสัก 10-15 วิ แล้วตรวจสอบ:**
```bash
curl -s http://localhost:4566/_localstack/health | python3 -m json.tool
```
ต้องเห็น `ec2`, `s3` เป็น `"available"` หรือ `"running"`

---

## ขั้นที่ 3 — สร้าง S3 bucket สำหรับ remote state `[CLI]`

```bash
aws --endpoint-url=http://localhost:4566 --region us-east-1 \
  s3 mb s3://taskflow-tfstate
aws --endpoint-url=http://localhost:4566 --region us-east-1 \
  s3 ls
```
ต้องเห็น `taskflow-tfstate` ในลิสต์

---

## ขั้นที่ 4 — สร้าง branch `lab08` `[CLI]`

```bash
git checkout lab07
git pull origin lab07
git checkout -b lab08
```

---

## ขั้นที่ 5 — เขียน Terraform `[CLI]`

`infra/terraform/main.tf`:
```hcl
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket                      = "taskflow-tfstate"
    key                         = "taskflow-api/terraform.tfstate"
    region                      = "us-east-1"
    access_key                  = "test"
    secret_key                  = "test"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_requesting_account_id  = true
    use_path_style              = true
    endpoints = {
      s3 = "http://localhost:4566"
    }
  }
}

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    ec2 = "http://localhost:4566"
    s3  = "http://localhost:4566"
  }
}

resource "aws_security_group" "taskflow_sg" {
  name        = "taskflow-sg"
  description = "Allow inbound traffic to taskflow-api"

  ingress {
    description = "taskflow-api port"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # จงใจเปิดกว้างเกินไป — ใช้พิสูจน์ tfsec/checkov ในขั้นที่ 13
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "taskflow_host" {
  ami           = "ami-0c02fb55956c7d316" # dummy AMI — LocalStack ไม่ validate ค่านี้
  instance_type = "t3.micro"

  vpc_security_group_ids = [aws_security_group.taskflow_sg.id]

  tags = {
    Name = "taskflow-host"
  }
}

output "instance_id" {
  value = aws_instance.taskflow_host.id
}

output "instance_address" {
  value = aws_instance.taskflow_host.private_ip
}

output "security_group_id" {
  value = aws_security_group.taskflow_sg.id
}
```

`infra/terraform/.gitignore`:
```
.terraform/
.terraform.lock.hcl
*.tfstate
*.tfstate.backup
tfplan
tfplan.txt
tf-outputs.json
```

---

## ขั้นที่ 6 — ทดสอบ Terraform บนเครื่องก่อน push `[CLI]`

```bash
cd infra/terraform
terraform init
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
terraform output
```

**ตรวจอิสระ:**
```bash
aws --endpoint-url=http://localhost:4566 --region us-east-1 ec2 describe-instances \
  --query 'Reservations[].Instances[].{ID:InstanceId,State:State.Name}'
```
ต้องเห็น instance สถานะ `running`

**ยังไม่ลบทิ้ง** — จะใช้ทดสอบ Ansible ต่อในขั้นที่ 8 แล้วค่อย `terraform destroy` ท้ายสุด (ขั้นที่ 18)

---

## ขั้นที่ 7 — เขียน Ansible playbook `[CLI]`

`infra/ansible/inventory/dynamic_inventory.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../terraform"
ADDRESS=$(terraform output -raw instance_address 2>/dev/null || echo "unavailable")
mkdir -p "$(dirname "$0")"
{
  echo "[taskflow]"
  echo "localhost ansible_connection=local terraform_reported_address=${ADDRESS}"
} > "$(dirname "$0")/hosts.ini"
echo "Generated inventory — Terraform reported instance_address=${ADDRESS}"
echo "(LocalStack Community instances aren't reachable — targeting localhost, see Known Limitations)"
cat "$(dirname "$0")/hosts.ini"
```
```bash
chmod +x infra/ansible/inventory/dynamic_inventory.sh
```

`infra/ansible/playbook.yml`:
```yaml
---
- name: Configure taskflow-api host
  hosts: taskflow
  gather_facts: false
  vars:
    image_name: "localhost:5000/taskflow-api:{{ image_tag }}"

  tasks:
    - name: Confirm Node.js is present on the host
      ansible.builtin.command: node --version
      register: node_version
      changed_when: false

    - name: Confirm Docker CLI is present on the host
      ansible.builtin.command: docker --version
      register: docker_version
      changed_when: false

    - name: Pull taskflow-api image from the local registry
      ansible.builtin.command: "docker pull {{ image_name }}"
      register: pull_result
      changed_when: "'Image is up to date' not in pull_result.stdout"

    - name: Show pulled image digest
      ansible.builtin.command: "docker image inspect {{ image_name }} --format '{{ '{{' }}.RepoDigests{{ '}}' }}'"
      register: image_digest
      changed_when: false

    - name: Report results
      ansible.builtin.debug:
        msg:
          - "Node.js: {{ node_version.stdout }}"
          - "Docker: {{ docker_version.stdout }}"
          - "Image digest: {{ image_digest.stdout }}"
```

**อธิบายจุดสำคัญ:**
- ไม่ใช้ `become: true`/`apt` install จริง — เพราะ agent รันเป็น user `jenkins` (ไม่ใช่ root) และไม่ได้ตั้ง passwordless sudo ไว้ ใช้ `command: node --version`/`docker --version` เป็นการ**ยืนยันว่ามีอยู่แล้ว** แทน (Node.js/Docker CLI ถูกติดตั้งไว้ใน agent ตั้งแต่ Lab 01/03 อยู่แล้ว)
- **`docker pull`** คือ task ที่ทำงานจริง ไม่ใช่แค่ verify — ดึง image จาก registry ที่สร้างไว้ตอน Lab 07 จริง ๆ
- `changed_when` กำหนดเองเพราะ `ansible.builtin.command` ไม่รู้เองว่า "เปลี่ยนแปลงอะไรไหม" (ต่างจาก module อย่าง `apt`/`copy` ที่ตรวจสอบให้อัตโนมัติ)

---

## ขั้นที่ 8 — ทดสอบ Ansible บนเครื่องก่อน push `[CLI]`

```bash
cd infra/ansible
./inventory/dynamic_inventory.sh
ansible-lint playbook.yml
ansible-playbook -i inventory/hosts.ini playbook.yml -e image_tag=<SHORT_SHA จาก Lab 07>
```

**รันซ้ำรอบสอง** (พิสูจน์ idempotency — รอบสองควรขึ้น `changed=0` สำหรับ 3 task แรก):
```bash
ansible-playbook -i inventory/hosts.ini playbook.yml -e image_tag=<SHORT_SHA เดิม>
```

---

## ขั้นที่ 9 — เขียน stage `IaC Lint & Validate` `[CLI]`

เพิ่มต่อจาก stage สุดท้ายของ Lab 07 (`Blue/Green Deploy`):

```groovy
        stage('IaC Lint & Validate') {
            parallel {
                stage('Terraform Validate') {
                    agent { label 'linux-build' }
                    steps {
                        dir('infra/terraform') {
                            sh '''
                                terraform init -backend=false
                                terraform validate
                                terraform fmt -check -recursive
                            '''
                        }
                    }
                }
                stage('Ansible Lint') {
                    agent { label 'linux-build' }
                    steps {
                        sh 'ansible-lint infra/ansible/playbook.yml'
                    }
                }
            }
        }
```

---

## ขั้นที่ 10 — เขียน stage ที่เหลือ (Security Scan, Plan, Approval, Apply, Ansible) `[CLI]`

```groovy
        stage('IaC Security Scan') {
            agent { label 'linux-build' }
            steps {
                dir('infra/terraform') {
                    sh 'tfsec .'
                    sh 'checkov -d .'
                }
            }
        }

        stage('Terraform Plan') {
            agent { label 'linux-build' }
            steps {
                dir('infra/terraform') {
                    sh '''
                        terraform init
                        terraform plan -out=tfplan
                        terraform show -no-color tfplan > tfplan.txt
                    '''
                }
                stash name: 'tfplan-artifact', includes: 'infra/terraform/tfplan,infra/terraform/tfplan.txt'
                archiveArtifacts artifacts: 'infra/terraform/tfplan.txt', allowEmptyArchive: true
            }
        }

        stage('Approval') {
            agent { label 'linux-build' }
            steps {
                unstash 'tfplan-artifact'
                script {
                    def planSummary = readFile('infra/terraform/tfplan.txt')
                    input message: 'Review the Terraform plan. Apply?', ok: 'Apply',
                          parameters: [text(name: 'PlanSummary', defaultValue: planSummary, description: 'Terraform plan (read-only, for review)')]
                }
                stash name: 'tfplan-artifact-2', includes: 'infra/terraform/tfplan,infra/terraform/tfplan.txt'
            }
        }

        stage('Terraform Apply') {
            agent { label 'linux-build' }
            steps {
                unstash 'tfplan-artifact-2'
                dir('infra/terraform') {
                    sh '''
                        terraform init
                        terraform apply tfplan
                        terraform output -json > tf-outputs.json
                    '''
                }
                archiveArtifacts artifacts: 'infra/terraform/tf-outputs.json'
            }
        }

        stage('Configure with Ansible') {
            agent { label 'linux-build' }
            steps {
                sh 'chmod +x infra/ansible/inventory/dynamic_inventory.sh && infra/ansible/inventory/dynamic_inventory.sh'
                dir('infra/ansible') {
                    sh "ansible-playbook -i inventory/hosts.ini playbook.yml -e image_tag=${env.SHORT_SHA}"
                }
            }
        }
```

**อธิบายจุดสำคัญ:**
- **`stash`/`unstash` ต่อกันเป็นทอด ๆ** (`tfplan-artifact` → `tfplan-artifact-2`) เพราะแต่ละ stage คนละ workspace — `Approval` รับมาแล้วต้อง stash ส่งต่อให้ `Terraform Apply` อีกที (unstash ครั้งเดียวใช้ได้ครั้งเดียวต่อ 1 ชื่อในทางปฏิบัติที่ปลอดภัยที่สุด จึงตั้งชื่อใหม่ก่อนส่งต่อ)
- **`input` พร้อม `parameters: [text(...)]`** ทำให้ผู้ approve เห็นเนื้อหา plan จริงในหน้า approve เลย ไม่ต้องเปิดดู console log แยก
- `env.SHORT_SHA` มาจาก stage `Build Image` ของ Lab 07 ที่ตั้งไว้แล้ว (`env.SHORT_SHA = env.GIT_COMMIT.take(7)`)

---

## ขั้นที่ 11 — Commit, push, ชี้ Jenkins job ไป `lab08` `[CLI + UI]`

```bash
git add Jenkinsfile Dockerfile.agent infra/
git commit -m "add: Terraform IaC pipeline with LocalStack, tfsec/checkov gate, Ansible configuration"
git push origin lab08
```

**[UI]** เข้า job `taskflow-pipeline` → Configure → Branch Specifier → `*/lab08` → Save

---

## ขั้นที่ 12 — Build Now รอบแรก (คาดว่าแดงที่ `IaC Security Scan`) `[UI]`

เพราะ security group เปิด `0.0.0.0/0` ไว้ตั้งใจ — **เก็บ log ตรงนี้ไว้เป็นหลักฐาน "before" ของ tfsec/checkov**

---

## ขั้นที่ 13 — แก้ finding ให้แคบลง, commit, build ใหม่ (คาดว่าเขียว) `[CLI + UI]`

แก้ `infra/terraform/main.tf`:
```hcl
  ingress {
    description = "taskflow-api port (restricted to Docker bridge network)"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["172.16.0.0/12"] # แคบลงจาก 0.0.0.0/0
  }
```
```bash
git add infra/terraform/main.tf
git commit -m "fix: restrict security group ingress CIDR per tfsec/checkov finding"
git push origin lab08
```
กด Build Now ใหม่ — **เก็บ log ตรงนี้เป็นหลักฐาน "after"**

### ผลจริงที่เกิดขึ้น (Build #56 → แก้ตามนี้) — ต่างจากตัวอย่างข้างบน

Build #56 แดงที่ `IaC Security Scan` ตามที่ตั้งใจ. output จริงของ scanner:

| Tool | Rule | Finding | Action |
|---|---|---|---|
| tfsec | `aws-ec2-no-public-ingress-sgr` (CRITICAL, main.tf:50) | ingress 8080 จาก `0.0.0.0/0` | **แก้**: `172.17.0.0/16` |
| tfsec | `aws-ec2-no-public-egress-sgr` (CRITICAL, main.tf:57) | egress ไป `0.0.0.0/0` | **แก้**: `172.17.0.0/16` |
| tfsec | `aws-ec2-enforce-http-token-imds` (HIGH) | ไม่บังคับ IMDSv2 | **แก้**: `metadata_options { http_tokens = "required" }` |
| tfsec | `aws-ec2-add-description-to-security-group-rule` (LOW) | egress ไม่มี description | **แก้**: เพิ่ม `description` |
| tfsec | `aws-ec2-enable-at-rest-encryption` (HIGH) | root volume ไม่เข้ารหัส | **suppress** (ดูล่าง) |
| Checkov | `CKV_AWS_382`, `CKV_AWS_23`, `CKV_AWS_79`, `CKV_AWS_135` | egress เปิด / ไม่มี description / IMDSv1 / ไม่ EBS optimized | **แก้**: egress แคบลง, description, IMDSv2, `ebs_optimized = true` |
| Checkov | `CKV_AWS_8` | root volume ไม่เข้ารหัส | **suppress** |
| Checkov | `CKV_AWS_126` | ไม่เปิด detailed monitoring | **suppress** |
| Checkov | `CKV2_AWS_41` | ไม่มี IAM role | **suppress** |

**CIDR ที่ใช้จริง: `172.17.0.0/16`** (docker bridge — ที่ Jenkins/kind อยู่) แคบกว่า `172.16.0.0/12` ในตัวอย่าง และผ่านทั้ง tfsec และ Checkov.

**Suppress เฉพาะที่ LocalStack Community ทำไม่ได้จริง (ทดสอบแล้ว ไม่ใช่เดา)** — ใช้ inline ต่อ resource เท่านั้น ไม่มี global exclusion:
- root volume encryption: `root_block_device { encrypted = true }` ทำให้ `terraform apply` ล้มเหลว `collecting instance settings: couldn't find resource` (LocalStack ไม่มี root EBS volume จริง) → `#tfsec:ignore:aws-ec2-enable-at-rest-encryption` + `#checkov:skip=CKV_AWS_8`
- detailed monitoring: `monitoring = true` ล้มเหลว `MonitorInstances ... 501 not yet implemented` → `#checkov:skip=CKV_AWS_126`
- IAM role: host ไม่เรียก AWS API และ LocalStack รันแค่ `ec2,s3,sts` → `#checkov:skip=CKV2_AWS_41`

บน AWS จริงควรเปิดทั้งสามอย่าง — เขียนไว้ในรายงานหัวข้อ Known Limitations.

**ข้อเท็จจริงของการติดตั้งจริงที่ต่างจากขั้นที่ 1–2:**
- `localstack/localstack:latest` ตอนนี้ต้องมี auth token (ไม่รันถ้าไม่มี) → pin `localstack/localstack:4.9.2` (ยังรันได้โดยไม่ต้องมี token)
- Terraform `1.9.8` ยังดาวน์โหลดได้ จึงใช้ตามเดิม (tfsec `v1.28.14`)
- SonarQube ต้องมี webhook `http://172.17.0.1:8080/sonarqube-webhook/` ไม่งั้น `waitForQualityGate` ค้างที่ `IN_PROGRESS` จน timeout (พบใน build #55)

---

## ขั้นที่ 14 — กด Approve ที่ `Approval` stage `[UI]`

เข้า build ที่กำลังรอ (มีไอคอนหยุดรออยู่) → กด **Apply** → เก็บภาพหน้า approve ที่เห็นเนื้อหา plan

---

## ขั้นที่ 15 — ตรวจสอบผล `Terraform Apply` + `Configure with Ansible` `[UI]`

เก็บภาพ console log ของทั้งสอง stage (ต้องเห็น `instance_address` ใน output และเห็น Ansible task `Pull taskflow-api image` สำเร็จ)

---

## ขั้นที่ 16 — ตรวจอิสระนอก Jenkins `[CLI]`

```bash
aws --endpoint-url=http://localhost:4566 --region us-east-1 ec2 describe-instances \
  --query 'Reservations[].Instances[].{ID:InstanceId,State:State.Name}'
docker exec jenkins-agent-linux-build docker images | grep taskflow-api
```

---

## ขั้นที่ 17 — `terraform destroy` ท้ายสุด `[CLI]`

**⚠️ ทำหลังเก็บ screenshot/deliverable ครบแล้วเท่านั้น**

```bash
cd infra/terraform
terraform destroy -auto-approve
terraform show
```
`terraform show` ต้องว่าง (ไม่มี resource เหลือ) — เก็บผลลัพธ์นี้ไว้เป็นหลักฐานข้อ 6

---

## สรุป Deliverables

| # | รายการ | เก็บจากขั้นตอนไหน |
|---|---|---|
| 1 | Terraform + Ansible source files, `tfplan` artifact | ขั้นที่ 10-11 |
| 2 | Before/after tfsec หรือ Checkov output | ขั้นที่ 12-13 |
| 3 | Screenshot approval prompt + applied output (instance address) | ขั้นที่ 14-15 |

## เกณฑ์การให้คะแนน

| หัวข้อ | คะแนน |
|---|---|
| Remote state ตั้งถูกต้อง, ไม่มี local state หลุดเข้า git | 20 |
| tfsec/Checkov findings ถูก triage และแก้จริง | 25 |
| Apply ถูก gate ด้วย human approval จริง | 20 |
| Ansible playbook ตั้งค่า host สำเร็จ | 25 |
| Destroy สะอาด ไม่มี resource ค้าง | 10 |

---

## ข้อจำกัดที่รู้ตัว (Known Limitations)

- **LocalStack Community's `aws_instance` ไม่ใช่เครื่องจริงที่ SSH เข้าได้** — Ansible จึงต่อผ่าน `ansible_connection=local` (target agent เอง) แทน โดยยังอ่าน address จาก `terraform output` มาบันทึกไว้ใน inventory จริง ในระบบจริง (real cloud) จะใช้ address นั้นต่อ SSH ตรง ๆ
- Ansible playbook ไม่ได้ใช้ `become`/apt install จริง เพราะ agent รันเป็น non-root user — ใช้การยืนยันว่ามีเครื่องมืออยู่แล้วแทน
- LocalStack ไม่มี auth/TLS จริง — เหมาะสำหรับแล็บเท่านั้น
- Terraform provider plugin cache ใช้ path ร่วมข้าม workspace (`TF_PLUGIN_CACHE_DIR`) เพื่อประหยัดเวลาดาวน์โหลด แต่ state/lock file ยังต้อง `terraform init` ใหม่ทุก stage เพราะ workspace แยกกัน (`agent none` + `agent label` per stage)

## หมายเหตุ / ข้อควรระวัง

- ถ้าสร้าง agent container ใหม่ (`docker rm -f` แล้ว `docker run`) ต้อง build image ใหม่จาก `Dockerfile.agent` ที่มีเครื่องมือ IaC ครบ ไม่ใช่ image เวอร์ชันเก่า
- LocalStack container ต้องรันอยู่ตลอดเวลาที่ทำ Terraform stage ใด ๆ (เหมือน SonarQube ที่ต้องรันตลอด Lab 05)
- อย่าลืม `terraform destroy` ก่อนจบ session จริง ๆ (ไม่ใช่แค่ทำ mental note) — ตรวจด้วย `terraform show` ให้ว่างจริง
