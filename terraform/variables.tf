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

# --- Portal API Worker ---

variable "portal_worker_name" {
  description = "Script name for the portal API Worker."
  type        = string
  default     = "bargain-portal-api"
}

variable "subscribers_db_id" {
  description = "Notion Subscribers database ID (printed by scripts/setup_notion.py)."
  type        = string
}

variable "waitlist_db_id" {
  description = "Notion Waitlist database ID for access requests."
  type        = string
  default     = "f5effc1618af4447abef61e3a8dc28ff"
}

variable "resend_api_key" {
  description = "Resend API key for sending magic link and access request emails."
  type        = string
  sensitive   = true
}

variable "frontend_url" {
  description = "Public URL of the Next.js frontend (Cloudflare Pages). Used for post-auth redirects and CORS."
  type        = string
}

variable "owner_email" {
  description = "Email address that receives access requests from the landing page."
  type        = string
}

variable "pages_project_name" {
  description = "Cloudflare Pages project name for the Next.js frontend."
  type        = string
  default     = "bargain-hunter"
}
