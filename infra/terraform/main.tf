terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state: S3 bucket served by LocalStack (bucket created once by hand: taskflow-tfstate)
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
    description = "taskflow-api port (restricted to the Docker bridge network 172.17.0.0/16)"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["172.17.0.0/16"] # narrowed from 0.0.0.0/0 (tfsec aws-ec2-no-public-ingress-sgr)
  }

  egress {
    description = "outbound only inside the Docker bridge network 172.17.0.0/16"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["172.17.0.0/16"] # was 0.0.0.0/0 (aws-ec2-no-public-egress-sgr, CKV_AWS_382)
  }
}

# Triaged, NOT fixable on LocalStack Community (documented in manual_lab/lab08/lab08.md; enable in real cloud):
#   - root volume encryption: LocalStack has no root EBS volume, so `root_block_device { encrypted = true }`
#     fails on apply with "collecting instance settings: couldn't find resource"
#   - detailed monitoring: LocalStack answers MonitorInstances with 501 "not yet implemented"
#   - IAM role: the host makes no AWS API calls, and this LocalStack runs only ec2,s3,sts
#tfsec:ignore:aws-ec2-enable-at-rest-encryption
resource "aws_instance" "taskflow_host" {
  #checkov:skip=CKV_AWS_8: LocalStack has no root EBS volume to encrypt (apply fails); enable encrypted root_block_device on real AWS
  #checkov:skip=CKV_AWS_126: LocalStack does not implement MonitorInstances (501); enable monitoring on real AWS
  #checkov:skip=CKV2_AWS_41: host makes no AWS API calls, so it needs no IAM role (LocalStack runs only ec2,s3,sts)
  ami           = "ami-0c02fb55956c7d316" # dummy AMI: LocalStack does not validate it
  instance_type = "t3.micro"
  ebs_optimized = true # CKV_AWS_135

  metadata_options {
    http_tokens   = "required" # IMDSv2 only (aws-ec2-enforce-http-token-imds, CKV_AWS_79)
    http_endpoint = "enabled"
  }

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
