variable "aws_vpc" {
  type        = string
  description = "VPC"
  default     = "vpc-0cfce97ee90c54fb1"
}

variable "aws_subnet" {
  type        = string
  description = "private subnet"
  default     = "subnet-08a826b57afed75ee"
}

variable "rocky_8_ami_us_east_1" {
  type        = string
  description = "Rocky Linux 8 AMI in us-east-1"
  default     = "ami-004b161a1cceb1ceb"
}

variable "job_id" {
  type        = string
  description = "Identifier used to tag all and suffix all the ressource names related to the current job"
}
