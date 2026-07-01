data "aws_caller_identity" "current" {}

locals {
  state_bucket_name = var.state_bucket_name != "" ? var.state_bucket_name : "${var.name_prefix}-state-${data.aws_caller_identity.current.account_id}"
  function_name     = var.name_prefix
}

# ---------------------------------------------------------------------------
# S3 — pipeline state (replaces the GitHub Actions Cache + daily git seed)
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "state" {
  bucket = local.state_bucket_name
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  # Expire old observation JSONL (calibration log) to keep the bucket small.
  dynamic "rule" {
    for_each = var.observations_retention_days > 0 ? [1] : []
    content {
      id     = "expire-observations"
      status = "Enabled"
      filter {
        prefix = "${var.state_prefix}/observations/"
      }
      expiration {
        days = var.observations_retention_days
      }
    }
  }

  # Reap non-current versions so versioning doesn't accumulate unbounded.
  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

# ---------------------------------------------------------------------------
# IAM — Lambda execution role
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.name_prefix}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  statement {
    sid       = "StateObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.state.arn}/${var.state_prefix}/*"]
  }

  statement {
    sid       = "StateList"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.state.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${var.state_prefix}/*"]
    }
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.name_prefix}-lambda"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

# ---------------------------------------------------------------------------
# CloudWatch Logs
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

# ---------------------------------------------------------------------------
# Lambda
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "hunt" {
  function_name = local.function_name
  role          = aws_iam_role.lambda.arn
  runtime       = "python3.12"
  handler       = "handler.handler"
  architectures = [var.lambda_architecture]
  timeout       = var.lambda_timeout_seconds
  memory_size   = var.lambda_memory_mb

  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  environment {
    variables = {
      STATE_BUCKET  = aws_s3_bucket.state.bucket
      STATE_PREFIX  = var.state_prefix
      SETTINGS_PATH = "/var/task/config/settings.yaml"

      # Mirrors hunt.yml's env block.
      NOTION_TOKEN             = var.notion_token
      NOTION_SUBSCRIBERS_DB_ID = var.notion_subscribers_db_id
      NOTION_SENT_LOG_DB_ID    = var.notion_sent_log_db_id
      SMTP_HOST                = var.smtp_host
      SMTP_PORT                = var.smtp_port
      SMTP_USERNAME            = var.smtp_username
      SMTP_PASSWORD            = var.smtp_password
      EMAIL_FROM               = var.email_from
      MAINTAINER_EMAIL         = var.maintainer_email
      FEEDBACK_BASE_URL        = var.feedback_base_url
      FEEDBACK_HMAC_SECRET     = var.feedback_hmac_secret
      HEALTHCHECK_URL          = var.healthcheck_url
    }
  }

  depends_on = [
    aws_iam_role_policy.lambda,
    aws_cloudwatch_log_group.lambda,
  ]
}

# ---------------------------------------------------------------------------
# EventBridge Scheduler — the */5 trigger (DISABLED by default; failover only)
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.name_prefix}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.hunt.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "${var.name_prefix}-scheduler"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "hunt" {
  name = var.name_prefix

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = "Australia/Sydney"
  state                        = var.schedule_enabled ? "ENABLED" : "DISABLED"

  target {
    arn      = aws_lambda_function.hunt.arn
    role_arn = aws_iam_role.scheduler.arn

    retry_policy {
      maximum_retry_attempts = 0 # next 5-min tick is the natural retry
    }
  }
}
