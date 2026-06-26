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

# --- Portal API ---

# KV namespace for sessions and magic link tokens.
resource "cloudflare_workers_kv_namespace" "portal_sessions" {
  account_id = var.cloudflare_account_id
  title      = "bargain-portal-sessions"
}

# Portal API Worker — built via wrangler in CI, uploaded here as a bundled script.
# The source path points to the compiled output; wrangler build runs before terraform apply.
resource "cloudflare_workers_script" "portal" {
  account_id         = var.cloudflare_account_id
  script_name        = var.portal_worker_name
  content_file       = "${path.module}/../portal-worker/dist/index.js"
  content_sha256     = filesha256("${path.module}/../portal-worker/dist/index.js")
  main_module        = "index.js"
  compatibility_date = "2026-01-01"

  bindings = [
    {
      name         = "PORTAL_KV"
      type         = "kv_namespace"
      namespace_id = cloudflare_workers_kv_namespace.portal_sessions.id
    },
    {
      name = "NOTION_TOKEN"
      type = "secret_text"
      text = var.notion_token
    },
    {
      name = "SUBSCRIBERS_DB_ID"
      type = "plain_text"
      text = var.subscribers_db_id
    },
    {
      name = "RESEND_API_KEY"
      type = "secret_text"
      text = var.resend_api_key
    },
    {
      name = "WORKER_URL"
      type = "plain_text"
      text = "https://${var.portal_worker_name}.${var.cloudflare_account_id}.workers.dev"
    },
    {
      name = "FRONTEND_URL"
      type = "plain_text"
      text = var.frontend_url
    },
    {
      name = "OWNER_EMAIL"
      type = "plain_text"
      text = var.owner_email
    },
  ]
}

resource "cloudflare_workers_script_subdomain" "portal" {
  account_id       = var.cloudflare_account_id
  script_name      = cloudflare_workers_script.portal.script_name
  enabled          = true
  previews_enabled = false
}
