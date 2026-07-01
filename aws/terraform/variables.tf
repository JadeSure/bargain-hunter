variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "ap-southeast-2" # Sydney — closest to the AET audience/sources
}

variable "name_prefix" {
  description = "Prefix for all resource names."
  type        = string
  default     = "bargain-hunter-backup"
}

variable "state_bucket_name" {
  description = "Globally-unique S3 bucket name for pipeline state. Empty = auto-generate from name_prefix + account id."
  type        = string
  default     = ""
}

variable "lambda_zip_path" {
  description = "Path to the built Lambda zip (produced by aws/build.sh)."
  type        = string
  default     = "../dist/lambda.zip"
}

variable "lambda_architecture" {
  description = "Lambda CPU architecture. Must match the arch used by aws/build.sh."
  type        = string
  default     = "x86_64"
  validation {
    condition     = contains(["x86_64", "arm64"], var.lambda_architecture)
    error_message = "lambda_architecture must be x86_64 or arm64."
  }
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout. hunt.yml allows 8 min; the pipeline itself is far quicker."
  type        = number
  default     = 300
}

variable "lambda_memory_mb" {
  description = "Lambda memory (also scales CPU). 512MB is comfortable for the I/O-bound run."
  type        = number
  default     = 512
}

variable "schedule_expression" {
  description = "EventBridge Scheduler rate/cron. Mirrors hunt.yml's */5."
  type        = string
  default     = "rate(5 minutes)"
}

variable "schedule_enabled" {
  description = "Whether the 5-minute schedule is active. DISABLED by default — this is a failover; enable it only when GitHub Actions is unreliable/down."
  type        = bool
  default     = false
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for the Lambda."
  type        = number
  default     = 14
}

variable "state_prefix" {
  description = "Key prefix under which state objects live in the bucket."
  type        = string
  default     = "state"
}

variable "observations_retention_days" {
  description = "Days after which observation JSONL objects in S3 expire (0 = never). Calibration log; keep modest."
  type        = number
  default     = 30
}

# ---------------------------------------------------------------------------
# Pipeline secrets / config — injected as encrypted Lambda environment vars.
# Provide via TF_VAR_* env vars or a (git-ignored) *.auto.tfvars; never commit.
# Mirrors the env block of .github/workflows/hunt.yml.
# ---------------------------------------------------------------------------
variable "notion_token" {
  type      = string
  sensitive = true
}

variable "notion_subscribers_db_id" {
  type = string
}

variable "notion_sent_log_db_id" {
  type = string
}

variable "smtp_host" {
  type    = string
  default = "smtp.gmail.com"
}

variable "smtp_port" {
  type    = string
  default = "587"
}

variable "smtp_username" {
  type      = string
  sensitive = true
}

variable "smtp_password" {
  type      = string
  sensitive = true
}

variable "email_from" {
  type = string
}

variable "maintainer_email" {
  type = string
}

variable "feedback_base_url" {
  description = "Public URL of the deployed feedback worker (repo variable in Actions)."
  type        = string
  default     = ""
}

variable "feedback_hmac_secret" {
  type      = string
  sensitive = true
  default   = ""
}

variable "healthcheck_url" {
  description = "Dead-man's-switch ping URL (e.g. healthchecks.io). Pinged on clean runs."
  type        = string
  sensitive   = true
  default     = ""
}
