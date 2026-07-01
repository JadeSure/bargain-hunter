# Terraform state backend.
#
# Defaults to LOCAL state (terraform.tfstate in this dir) for a quick start.
# For CI / shared use, switch to an S3 backend by uncommenting below and running:
#
#   terraform init -backend-config=backend.hcl
#
# backend.hcl (git-ignored), e.g.:
#   bucket = "my-tf-state-bucket"
#   key    = "bargain-hunter/aws-backup.tfstate"
#   region = "ap-southeast-2"
#
# terraform {
#   backend "s3" {}
# }
