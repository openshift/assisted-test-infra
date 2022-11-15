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
      JobID = var.job_id
    }
  }
}

resource "aws_security_group" "ci_sg" {
  name        = "ci-sg-${var.job_id}"
  description = "Security group that allows every instances from the CI job to talk together"
  vpc_id      = var.aws_vpc

  ingress {
    description = 0
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }
}

// This profile allows the connection to the machine using ssm
// https://docs.aws.amazon.com/systems-manager/latest/userguide/setup-instance-profile.html
resource "aws_iam_instance_profile" "ci_instance_profile" {
  name = "ci-instance-profile-${var.job_id}"
  role = aws_iam_role.ci_instance_role.name
}

resource "aws_iam_role" "ci_instance_role" {
  name = "ci-instance-role-${var.job_id}"
  path = "/"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
}

resource "aws_iam_role_policy_attachment" "attach_ssm_policy_to_ci_instance_role" {
  role       = aws_iam_role.ci_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_instance" "ci_instance" {
  ami                    = var.rocky_8_ami_us_east_1
  instance_type          = "t3.medium"
  subnet_id              = var.aws_subnet
  user_data              = file("user_data.yml")
  vpc_security_group_ids = [aws_security_group.ci_sg.id]
  iam_instance_profile   = aws_iam_instance_profile.ci_instance_profile.name

  tags = {
    Name = "ci-instance"
  }

  root_block_device {
    volume_size = 64
    volume_type = "gp3"
  }
}
