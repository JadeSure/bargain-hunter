provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

locals {
  worker_source = "${path.module}/../feedback-worker/src/index.js"
}

# The feedback collector Worker (HMAC-signed). Single dependency-free ES module, so the source
# file is uploaded directly via content_file — no bundler/wrangler build step.
# Using content_file (not inline content) keeps the JS out of Terraform state.
resource "cloudflare_workers_script" "feedback" {
  account_id         = var.cloudflare_account_id
  script_name        = var.worker_name
  content_file       = local.worker_source
  content_sha256     = filesha256(local.worker_source)
  main_module        = "index.js"
  compatibility_date = "2026-01-01"

  bindings = [
    {
      name = "FEEDBACK_DB_ID"
      type = "plain_text"
      text = var.feedback_db_id
    },
    {
      name = "NOTION_TOKEN"
      type = "secret_text"
      text = var.notion_token
    },
    {
      name = "FEEDBACK_HMAC_SECRET"
      type = "secret_text"
      text = var.feedback_hmac_secret
    },
  ]
}

# Publish on https://<worker_name>.<account-subdomain>.workers.dev
resource "cloudflare_workers_script_subdomain" "feedback" {
  account_id       = var.cloudflare_account_id
  script_name      = cloudflare_workers_script.feedback.script_name
  enabled          = true
  previews_enabled = false
}
