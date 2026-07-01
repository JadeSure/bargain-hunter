# AWS serverless backup

A failover for the deal pipeline that normally runs on GitHub Actions
(`.github/workflows/hunt.yml`). GitHub's `*/5` cron is unreliable on
low-activity repos (runs delayed 30–60 min or skipped), so this deploys the
**same `bargain_hunter` pipeline** to AWS Lambda on a precise EventBridge
5-minute schedule.

It is a **backup**, not a second permanent runner: the schedule ships
**disabled** and you enable it when Actions is misbehaving (see
[Failover](#failover-enabledisable)).

```
EventBridge Scheduler ──rate(5 min)──▶ Lambda (handler.handler)
        (DISABLED by default)               │
                                            │  1. download state from S3 ─┐
                                            │  2. bargain_hunter.main.run()│  (unchanged)
                                            │  3. upload state to S3 ──────┘
                                            ▼
                                   CloudWatch Logs
```

## Why state lives in S3

Lambda's filesystem is read-only except `/tmp`, which is wiped on cold starts.
`hunt.yml` keeps the hot-path state (`deals_state.json`, `alert_state.json`,
`observations/*.jsonl`) in the Actions Cache between runs and commits a daily
seed to git. The Lambda handler (`handler.py`) reproduces that by syncing those
files to/from an S3 bucket around each run. The application code is untouched —
it still reads/writes `data/...` relative to the working directory, which the
handler points at `/tmp/run`.

**Dedup is shared.** "Don't email the same deal twice" is enforced via the
Notion Sent Log, which both runners read. So even if the Lambda briefly overlaps
a real Actions run it will **not** double-email. Velocity state
(`deals_state.json`) is per-runner, though, which is the main reason to run only
one at a time.

## Layout

```
aws/
  handler.py            Lambda entry: S3 state sync + run + alert + heartbeat
  build.sh              builds dist/lambda.zip (manylinux deps + src + config)
  terraform/            S3 bucket, IAM, Lambda, EventBridge schedule, log group
  README.md             this file
```

## Prerequisites

- AWS account + credentials (`aws configure`, or env vars).
- Terraform ≥ 1.6.
- Python 3.12 + `pip` (for `build.sh`).
- `zip` on PATH.

## Deploy

```bash
# 1. Build the Lambda zip (must run before terraform — it reads the zip's hash).
#    Build for the architecture you set in Terraform (default x86_64).
aws/build.sh                        # or: LAMBDA_ARCH=arm64 aws/build.sh

# 2. Configure secrets.
cd aws/terraform
cp terraform.tfvars.example terraform.tfvars   # fill in (git-ignored)
#    …or export TF_VAR_* env vars instead.

# 3. Apply.
terraform init      # local state by default; see backend.tf for S3 remote state
terraform plan
terraform apply
```

On every code change, re-run `aws/build.sh` then `terraform apply` — the
`source_code_hash` changes and Lambda is updated.

### CI

`.github/workflows/aws-backup.yml` does build + apply on pushes to `main` that
touch `aws/**`, `src/bargain_hunter/**`, or `config/settings.yaml`. It needs:

| Kind | Name | Notes |
|---|---|---|
| Secret | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | deploy credentials |
| Secret | `NOTION_TOKEN`, `NOTION_SUBSCRIBERS_DB_ID`, `NOTION_SENT_LOG_DB_ID` | same as hunt.yml |
| Secret | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM` | email |
| Secret | `MAINTAINER_EMAIL`, `FEEDBACK_HMAC_SECRET`, `HEALTHCHECK_URL` | alerts/feedback/heartbeat |
| Variable | `AWS_REGION` | default `ap-southeast-2` |
| Variable | `AWS_TF_STATE_BUCKET` | existing S3 bucket for Terraform remote state |
| Variable | `AWS_SCHEDULE_ENABLED` | `false` (default) / `true` to enable failover |
| Variable | `FEEDBACK_BASE_URL` | public feedback worker URL |

The CI job injects an S3 backend (`ci_backend_override.tf`); local runs keep the
default local state.

## Seed the state bucket (recommended before first real run)

Without seed state the first Lambda run is a cold start — it records a baseline
and sends nothing (same as Actions' first run). To carry over existing velocity
history, upload the daily git-committed snapshot:

```bash
BUCKET=$(terraform -chdir=aws/terraform output -raw state_bucket)
aws s3 cp data/deals_state.json   "s3://$BUCKET/state/deals_state.json"
aws s3 cp data/alert_state.json   "s3://$BUCKET/state/alert_state.json"   # optional
```

## Failover: enable/disable

The 5-minute schedule is **disabled by default**. Run only one scheduler at a
time to avoid divergent velocity state.

**Enable the AWS backup** (when Actions is down/unreliable):

```bash
# Quickest — flip the EventBridge schedule without a full apply:
aws scheduler update-schedule \
  --name "$(terraform -chdir=aws/terraform output -raw schedule_name)" \
  --state ENABLED \
  --schedule-expression 'rate(5 minutes)' \
  --schedule-expression-timezone 'Australia/Sydney' \
  --flexible-time-window '{"Mode":"OFF"}' \
  --target "$(aws scheduler get-schedule --name <name> --query 'Target' --output json)"

# Or, the declarative way (keeps Terraform state in sync):
terraform -chdir=aws/terraform apply -var schedule_enabled=true
```

Then **pause GitHub Actions** so the two don't fight over state: disable the
`bargain-hunter` workflow in the repo's Actions tab (or comment out the `cron`
in `hunt.yml`).

**Disable the AWS backup** (when Actions is healthy again):

```bash
terraform -chdir=aws/terraform apply -var schedule_enabled=false
```

## Manual / test invoke

```bash
FN=$(terraform -chdir=aws/terraform output -raw lambda_function_name)

# Real run:
aws lambda invoke --function-name "$FN" /dev/stdout

# Dry run (no emails, no Notion writes):
aws lambda invoke --function-name "$FN" \
  --payload '{"dry_run":true}' --cli-binary-format raw-in-base64-out /dev/stdout
```

Logs: `aws logs tail "$(terraform -chdir=aws/terraform output -raw log_group)" --follow`

## Cost

Negligible at this scale, and likely $0 within the AWS Always-Free allowances:

- **Lambda** — 5-min cadence ≈ 8,640 invocations/month. A ~512 MB run of a few
  seconds is well under the 1M requests + 400,000 GB-s/month always-free tier.
- **EventBridge Scheduler** — 8,640 invocations/month; the first 14M
  scheduler-invocations/month are free.
- **CloudWatch Logs** — a few MB/month at 14-day retention; first 5 GB free.
- **S3** — a handful of small objects, frequent PUT/GET. Storage is cents;
  request charges are a few cents/month. The largest item is `deals_state.json`
  (a few MB). Versioning + lifecycle keep it bounded.

Realistically a few cents/month at most if you exceed the free tier; effectively
free if you don't. Outbound email goes through your existing SMTP provider, not
AWS SES, so there's no AWS egress/email cost.

## Notes / limitations

- Keep `lambda_architecture` (Terraform) in sync with `LAMBDA_ARCH` (build.sh).
  `pydantic-core` ships native wheels per-arch; a mismatch fails at import.
- `boto3`/`botocore` are provided by the Lambda runtime and intentionally not
  bundled in the zip.
- This deploys only the **deal pipeline** (`bargain_hunter`), matching
  `hunt.yml`. The daily `strategy_hunter` collect job and the Cloudflare
  Workers/Pages stack are out of scope.
