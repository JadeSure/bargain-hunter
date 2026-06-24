variable "cloudflare_api_token" {
  description = "Cloudflare API token scoped to Workers Scripts:Edit."
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID (from `wrangler whoami` or the dashboard URL)."
  type        = string
}

variable "worker_name" {
  description = "Worker script name; also the workers.dev subdomain host."
  type        = string
  default     = "bargain-feedback"
}

variable "feedback_db_id" {
  description = "Notion Feedback database id (printed by scripts/setup_notion.py)."
  type        = string
}

variable "notion_token" {
  description = "Notion integration token. Stored as a secret_text binding, so it lands in Terraform state — keep the R2 backend private."
  type        = string
  sensitive   = true
}

variable "feedback_hmac_secret" {
  description = "Shared HMAC-SHA256 secret for signing feedback links. Must match FEEDBACK_HMAC_SECRET in the Python app."
  type        = string
  sensitive   = true
}
