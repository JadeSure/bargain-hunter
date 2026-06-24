# Remote state in Cloudflare R2 (S3-compatible). Account-specific values
# (bucket + endpoint) are supplied at init time via a gitignored backend.hcl:
#
#   terraform init -backend-config=backend.hcl
#
# R2 credentials are an R2 "S3 API" token, passed as standard AWS env vars:
#   export AWS_ACCESS_KEY_ID=...      # R2 access key id
#   export AWS_SECRET_ACCESS_KEY=...  # R2 secret access key
terraform {
  backend "s3" {
    key    = "feedback-worker/terraform.tfstate"
    region = "auto"

    # R2 is S3-compatible but not AWS S3 — disable AWS-only behaviours.
    # skip_s3_checksum is REQUIRED for recent Terraform versions or uploads fail.
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_s3_checksum            = true
    use_path_style              = true
  }
}
