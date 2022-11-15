terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"

  default_tags {
    tags = {
      ClusterName = var.cluster_name
      JobID       = var.job_id
    }
  }
}

data "aws_security_group" "ci_sg" {
  name = "ci-sg-${var.job_id}"
}

resource "aws_instance" "masters" {
  count = var.masters_count

  ami                    = var.ipxe_ami_us_east_1
  instance_type          = var.master_instance_type
  subnet_id              = var.aws_subnet
  vpc_security_group_ids = [data.aws_security_group.ci_sg.id]
  user_data              = var.ipxe_script

  tags = {
    Name     = "${var.cluster_name}-master-${count.index}"
    NodeType = "master"
  }

  root_block_device {
    volume_size = 100
    volume_type = "gp3"
  }
}

resource "aws_instance" "workers" {
  count = var.workers_count

  ami                    = var.ipxe_ami_us_east_1
  instance_type          = var.worker_instance_type
  subnet_id              = var.aws_subnet
  vpc_security_group_ids = [data.aws_security_group.ci_sg.id]
  user_data              = var.ipxe_script

  tags = {
    Name     = "${var.cluster_name}-worker-${count.index}"
    NodeType = "worker"
  }

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }
}

resource "aws_route53_zone" "private" {
  name = "${var.cluster_name}.redhat.com"

  vpc {
    vpc_id = var.aws_vpc
  }
}

resource "aws_route53_record" "app_wildcard" {
  zone_id = aws_route53_zone.private.zone_id
  name    = "*.apps.${var.cluster_name}.redhat.com"
  type    = "A"
  ttl     = 10
  records = aws_instance.workers[*].private_ip
}

resource "aws_route53_record" "api" {
  zone_id = aws_route53_zone.private.zone_id
  name    = "api.${var.cluster_name}.redhat.com"
  type    = "A"
  ttl     = 10
  records = aws_instance.masters[*].private_ip
}

resource "aws_route53_record" "api-int" {
  zone_id = aws_route53_zone.private.zone_id
  name    = "api-int.${var.cluster_name}.redhat.com"
  type    = "A"
  ttl     = 10
  records = aws_instance.masters[*].private_ip
}
