# Terraform: feedback-worker deployment

## What this is

Terraform module that deploys the `feedback-worker` Cloudflare Worker. It creates two resources:

- `cloudflare_workers_script` — uploads `feedback-worker/src/index.js` directly as a single dependency-free ES module (no bundler or wrangler build step required).
- `cloudflare_workers_script_subdomain` — publishes the worker at `https://<worker_name>.<account-subdomain>.workers.dev`.

Remote state is stored in a Cloudflare R2 bucket (S3-compatible backend).

## Prerequisites

**a. Terraform >= 1.9**

```bash
terraform version
```

**b. Cloudflare API token** scoped to **Workers Scripts: Edit**. Create one at dash.cloudflare.com > My Profile > API Tokens.

**c. R2 bucket for state** — create a bucket (e.g. `bargain-hunter-tfstate`) in your Cloudflare account under R2 > Create bucket. Then create an **R2 S3 API token** (R2 > Manage R2 API tokens) with Object Read and Write permissions. You'll get an access key id and secret.

**d. Notion Feedback DB id** — printed at the end of:

```bash
python scripts/setup_notion.py
```

## One-time setup

Copy and fill in the backend config:

```bash
cp terraform/backend.hcl.example terraform/backend.hcl
# Edit backend.hcl: set bucket name and your R2 endpoint URL
```

`backend.hcl` must contain your account's R2 endpoint:

```hcl
bucket    = "bargain-hunter-tfstate"
endpoints = { s3 = "https://<YOUR_ACCOUNT_ID>.r2.cloudflarestorage.com" }
```

Export the four required environment variables before running any Terraform commands:

```bash
export AWS_ACCESS_KEY_ID=<r2-access-key-id>
export AWS_SECRET_ACCESS_KEY=<r2-secret-access-key>
export TF_VAR_cloudflare_api_token=<cf-api-token>
export TF_VAR_notion_token=<ntn-...>
```

Set `cloudflare_account_id` and `feedback_db_id` either via `terraform.tfvars` (gitignored — copy from `terraform.tfvars.example`) or as `TF_VAR_` environment variables:

```bash
export TF_VAR_cloudflare_account_id=<your-32-char-account-id>
export TF_VAR_feedback_db_id=<notion-feedback-db-id>
```

## Deploy

```bash
cd terraform
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

## After apply

The worker is live at `https://<worker_name>.<your-subdomain>.workers.dev`. The `worker_name` output prints the exact script name.

Set `FEEDBACK_BASE_URL` to that URL in two places:

- GitHub Actions: add it as a repo **variable** (not secret) under Settings > Secrets and variables > Actions > Variables.
- Local: add `FEEDBACK_BASE_URL=https://...` to your `.env` file.

The digest email template uses this variable to render 👍/👎 links per deal. If unset, the links are omitted.

## Caveats

**Secret in state.** `notion_token` is stored as a `secret_text` binding, which means its value is written into `terraform.tfstate`. This is why state lives in private R2 storage. Never use local committed state, and never commit `*.tfvars` or `backend.hcl` (both are gitignored).

**main_module.** The `cloudflare_workers_script` resource has `main_module = "index.js"`. This tells Cloudflare which file is the ES module entry point. If `apply` ever errors about the entrypoint or module name, this is the field to adjust.

**If the worker grows dependencies.** The direct-file upload approach works because `feedback-worker/src/index.js` has no imports or npm dependencies. If that changes, you would need to add an esbuild or wrangler bundle step that produces a single output file, then point `content_file` at that bundle instead.

## Local dev

Use `wrangler dev` to test the worker locally — Terraform is for deployment only:

```bash
cd feedback-worker
npx wrangler dev
```

The `feedback-worker/wrangler.jsonc` config controls local dev settings.

## Destroy

```bash
cd terraform
terraform destroy
```

## CI deployment (GitHub Actions)

`.github/workflows/terraform-feedback.yml` runs this module in CI:

- **push to `main`** touching `terraform/**` or `feedback-worker/src/**` → `init` + `fmt -check` + `validate` + `plan` + **`apply`**.
- **pull request** on those paths → same, but **plan only** (no apply).
- **manual** via *Actions → terraform-feedback-worker → Run workflow* → applies.

Runs are serialised by a `concurrency` group so two applies never touch state at once. Because that (not a remote lock) is our guard, avoid running `terraform apply` locally once CI owns deploys.

### Required GitHub config (Settings → Secrets and variables → Actions)

**Secrets**

| Name | Value |
|---|---|
| `R2_ACCESS_KEY_ID` | R2 S3 API token access key id |
| `R2_SECRET_ACCESS_KEY` | R2 S3 API token secret |
| `CLOUDFLARE_API_TOKEN` | Cloudflare token, Workers Scripts: Edit |
| `NOTION_TOKEN` | reuse the secret already set for the hunt workflow |

**Variables**

| Name | Value |
|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | your 32-char account id |
| `NOTION_FEEDBACK_DB_ID` | from `scripts/setup_notion.py` |
| `TF_STATE_BUCKET` | the R2 state bucket name |
| `TF_STATE_R2_ENDPOINT` | `https://<account-id>.r2.cloudflarestorage.com` |

### Optional hardening

- Split into separate `plan` and `apply` jobs and put `environment: production` on the apply job to require manual approval before each deploy.
- Enable true state locking with `use_lockfile = true` in `backend.tf` (Terraform >= 1.10; R2 supports the conditional writes it needs).
