# Bargain Hunter

Runs every 5 minutes via GitHub Actions. Fetches deals from OzBargain and CamelCamelCamel AU, scores them for velocity (爆款/Hot) and matches against personal watch lists (盯货/Watch), then sends email digests to subscribers managed in Notion.

Full design: [`docs/PRD.md`](docs/PRD.md) · Implementation notes: [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)

## How it works

```mermaid
flowchart TD
    T1["⏱ GitHub Actions cron\nevery 5 min"] & T2["🌐 cron-job.org\nexternal trigger"] --> FETCH

    subgraph FETCH["Sources"]
        OZB[OzBargain RSS\nvotes · velocity]
        CCC[CamelCamelCamel AU\nprice drops · discount %]
    end

    FETCH --> ENRICH["Enrich + filter\nextract price · discount · drop expired deals"]
    CACHE[("Actions Cache\ndeals_state.json")] -->|restore| SNAP
    ENRICH --> SNAP["Record vote snapshots\n24 h rolling window"]
    SNAP -->|save| CACHE

    SNAP --> HOT["🔥 Hot score\nvote velocity × age decay · threshold 1.2"]
    SNAP --> WATCH["👀 Watch match\nkeyword · ≥ 15 votes · age ≤ 36 h"]

    HOT & WATCH --> QH{{"Quiet hours?\n22:00 – 07:00 AEST"}}
    QH -. skip .-> CACHE
    QH -- "07:00 – 22:00" --> NOTION

    NOTION[("Notion\nSubscribers · Sent Log")] --> DEDUP["Dedup\n7-day window · daily cap"]
    DEDUP --> EMAIL["📧 Email digest\nSMTP / Gmail"]
    EMAIL -->|log sent| NOTION

    EMAIL -- "👍/👎\nHMAC-signed links" --> CFW["Cloudflare Worker"]
    CFW --> FDB[("Notion\nFeedback DB")]
```

## Two tracks

- **Hot (爆款):** vote velocity + absolute votes + age decay. Passes a threshold → notifies all opt-in subscribers. Low frequency, high precision.
- **Watch (盯货):** keyword appears in a deal title → notifies the subscriber who listed that keyword. Noise guard: ≥5 votes (OzBargain) or ≥10% discount (CamelCamelCamel). Optional price ceiling to filter further.

A deal that qualifies on both tracks is merged into one notification.

## Sources

| Source | Type | Signal |
|---|---|---|
| OzBargain | Community deals | Vote velocity, comments |
| CamelCamelCamel AU | Amazon price drops | Discount % |

## Watch keyword syntax

Keywords are stored in the Notion Subscribers database, one per line in the **Watch Keywords** field:

```
PHRASE [<=PRICE] [@HH:MM | @YYYY-MM-DDTHH:MM]
```

Examples:

| Keyword | Meaning |
|---|---|
| `iPhone 17 Pro` | Any iPhone 17 Pro deal (noise guard applies) |
| `Dyson <=499` | Dyson deal at or under $499 |
| `Sony WH <=300 @2026-07-01T23:59` | Sony WH under $300, expires 1 July 2026 |
| `BWS @19:00` | BWS deal, expires today at 19:00 AEST |

Bare `@HH:MM` means today in `Australia/Sydney`. Expired keywords are silently skipped. Price ceiling is optional — bare keywords match on votes/discount alone.

## Quick start (local dev)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest
```

Dry-run (fetches real feed, prints what would be sent, no emails):

```bash
python -m bargain_hunter --dry-run
# or the installed script:
bargain-hunter --dry-run
```

## First-time Notion setup

1. Create a Notion integration at <https://www.notion.so/my-integrations> with
   **Insert content** + **Read content** + **Update content** permissions.
2. Share a Notion page with the integration. Copy the page ID from its URL (32 hex chars after the last `/`).
3. Run the setup script — it creates all databases and prints the IDs:

   ```bash
   export NOTION_TOKEN=ntn_xxx
   export NOTION_PARENT_PAGE_ID=<page-id>
   python scripts/setup_notion.py
   ```

4. Copy the printed IDs into `.env` (local) and GitHub Secrets (Actions).

## Adding subscribers

In Notion, open the **Bargain Hunter — Subscribers** database and create a new row:

| Field | Example |
|---|---|
| Name | Shawn Wang |
| Email | you@example.com |
| Active | ✓ |
| Channels | Email |
| Subscribe Hot Deals | ✓ |
| Watch Keywords | `BWS @19:00` |
| Max Alerts/Day | 10 |

## Configuration

Copy `.env.example` → `.env` and fill in credentials. `.env` is git-ignored.

Tunable thresholds (velocity window, hot score, vote gates, alerting cooldowns, etc.) are in `config/settings.yaml` — edit and push, no code change needed.

## GitHub Actions setup

### Secrets

Add these to Settings → Secrets and variables → Actions:

| Secret | Description |
|---|---|
| `NOTION_TOKEN` | Integration token (`ntn_...`) |
| `NOTION_SUBSCRIBERS_DB_ID` | From `setup_notion.py` output |
| `NOTION_SENT_LOG_DB_ID` | From `setup_notion.py` output |
| `SMTP_HOST` | e.g. `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USERNAME` | Your Gmail address |
| `SMTP_PASSWORD` | Gmail app password (not your login password) |
| `EMAIL_FROM` | e.g. `Bargain Hunter Bot <you@gmail.com>` |
| `MAINTAINER_EMAIL` | Where to send failure alerts |
| `FEEDBACK_HMAC_SECRET` | Random hex string; signs 👍/👎 links to prevent spam writes |
| `R2_ACCESS_KEY_ID` | Cloudflare R2 S3 API access key (for Terraform state) |
| `R2_SECRET_ACCESS_KEY` | Cloudflare R2 S3 API secret |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token scoped to Workers Scripts: Edit |

### Variables

| Variable | Description |
|---|---|
| `FEEDBACK_BASE_URL` | Public URL of the deployed feedback worker |
| `CLOUDFLARE_ACCOUNT_ID` | 32-char Cloudflare account ID |
| `NOTION_FEEDBACK_DB_ID` | From `setup_notion.py` output |
| `TF_STATE_BUCKET` | R2 bucket name for Terraform state |
| `TF_STATE_R2_ENDPOINT` | `https://<account-id>.r2.cloudflarestorage.com` |

### Scheduling

GitHub Actions cron is unreliable for high-frequency schedules (`*/5`) on low-activity repos — runs can be delayed 30–60 minutes or skipped. The recommended setup is an external scheduler triggering `workflow_dispatch` precisely.

**Setup with [cron-job.org](https://cron-job.org) (free):**

1. Generate a GitHub Fine-grained PAT with **Actions: Read and write** permission scoped to this repo.
2. In cron-job.org, create a new job using "Import from cURL":

   ```bash
   curl -X POST 'https://api.github.com/repos/JadeSure/bargain-hunter/actions/workflows/hunt.yml/dispatches' \
     -H 'Authorization: Bearer <your-PAT>' \
     -H 'Accept: application/vnd.github+json' \
     -H 'Content-Type: application/json' \
     -d '{"ref":"main"}'
   ```

3. Set the schedule to every 5 minutes.

The built-in `*/5` cron in the workflow file remains as a fallback.

### First run

The first run is always a **cold start** — it records a baseline but sends nothing. From the second run onwards, hot deals and watch matches generate notifications.

## Feedback worker (Cloudflare Workers)

Each digest email includes per-deal 👍/👎 links. Clicks hit a Cloudflare Worker that writes to a Notion Feedback database for calibration. Links are HMAC-signed — unsigned requests are rejected (403).

The worker is deployed automatically via Terraform on every push to `main` that touches `terraform/**` or `feedback-worker/src/**`. State is stored in a Cloudflare R2 bucket.

To deploy manually:
```bash
cd terraform
terraform init -backend-config=backend.hcl
terraform apply
```

## Alerting

Maintainer alert emails are throttled: only sent after 3 consecutive failures, then at most once per hour while failures persist. A clean run resets the counter.

## Current status (v1.1 — 2026-06-24)

Live and running. Highlights since v1.0:

- **CamelCamelCamel AU** added as a second source (Amazon price drops via RSS)
- **Watch matching simplified** — votes-only noise guard; no longer requires a discount signal from the deal title
- **Maintainer alert throttling** — alerts fire only after ≥3 consecutive failures, then at most once per hour
- **HMAC-signed feedback links** — 👍/👎 links in emails are signed; unsigned or replayed requests are rejected (403)
- **Cloudflare Worker deployed** at `https://bargain-feedback.jadesure17.workers.dev` — collects feedback into a Notion Feedback database
- **Terraform CI/CD** — pushing to `main` auto-deploys the Worker and its secrets via `terraform-feedback.yml`

### TODO (v1.2 direction)

| Priority | Item |
|---|---|
| High | Threshold calibration — after 1–2 weeks of data, tune `hot_threshold`, `min_votes`, `early_burst_*` against labelled Sent Log |
| Medium | Feedback data loop — use 👍/👎 counts to validate which deal types subscribers actually act on |
| Medium | Monitor feedback worker for mail-scanner pre-clicks (Safe Links / Proofpoint may trigger links before users do) |
| Low | Telegram channel — interface already modelled; needs bot /start onboarding |
| Low | Scheduling reliability — AWS Lambda + EventBridge for sub-5-min latency (v2) |

## Privacy

- `data/deals_state.json` stores vote snapshots only (no personal data). It is committed once per day (AET midnight) as a calibration seed; hot-path state travels via GitHub Actions Cache between runs.
- Subscriber info, watch lists, and sent records live only in your private Notion workspace.
- Public repo logs never print subscriber identifiers — only aggregate counts.
- Feedback links are HMAC-signed; the worker never returns subscriber data.
