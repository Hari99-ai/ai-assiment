terraform {
  required_version = ">= 1.8, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.90"
    }
  }
  # Configure an encrypted remote S3 backend with locking during deployment.
}
provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "amrutam", Environment = var.environment }
  }
}
