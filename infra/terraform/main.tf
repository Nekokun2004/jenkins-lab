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
    description = "taskflow-api port"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # deliberately too open: proves the tfsec/Checkov gate (Lab 08 step 12)
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "taskflow_host" {
  ami           = "ami-0c02fb55956c7d316" # dummy AMI: LocalStack does not validate it
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
