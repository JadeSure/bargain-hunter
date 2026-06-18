# Bargain Hunter

Runs every 5 minutes via an external cron trigger → GitHub Actions. Fetches deals from OzBargain, scores them for velocity (爆款/Hot) and matches against personal watch lists (盯货/Watch), then sends email digests to subscribers managed in Notion.

Full design: [`docs/PRD.md`](docs/PRD.md)

## Two tracks

- **Hot (爆款):** vote velocity + absolute votes + age decay. Passes a threshold → notifies all opt-in subscribers. Low frequency, high precision.
- **Watch (盯货):** keyword hits your Notion watch list and meets a discount or target price condition. Only notifies the subscriber who listed that keyword.

A deal that qualifies on both tracks is merged into one notification.

## Watch keyword syntax

Keywords are stored in the Notion Subscribers database, one per line in the **Watch Keywords** field:

```
PHRASE [<=PRICE] [@HH:MM | @YYYY-MM-DDTHH:MM]
```

Examples:

| Keyword | Meaning |
|---|---|
| `iPhone 17 Pro` | Any iPhone 17 Pro deal (noise guard: ≥5 votes required) |
| `Dyson <=499` | Dyson deal at or under $499 |
| `Sony WH <=300 @2026-07-01T23:59` | Sony WH under $300, expires 1 July 2026 |
| `BWS @19:00` | BWS deal, expires today at 19:00 AEST |

Bare `@HH:MM` means today in `Australia/Sydney`. Expired keywords are silently skipped.

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
3. Run the setup script — it creates both databases and prints the IDs:

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

Tunable thresholds (velocity window, hot score, discount %, quiet hours, etc.) are in `config/settings.yaml` — edit and push, no code change needed.

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

### Reliable scheduling via external trigger

GitHub Actions cron is unreliable for high-frequency schedules (`*/5`) on low-activity repos — runs can be delayed 30-60 minutes or skipped entirely. The recommended setup is to use an external scheduler to trigger `workflow_dispatch` precisely.

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

## Privacy

- `data/deals_state.json` stores vote snapshots only (no personal data). It is committed once per day (AET midnight) as a calibration seed; hot-path state travels via GitHub Actions Cache between runs.
- Subscriber info, watch lists, and sent records live only in your private Notion workspace.
- Public repo logs never print subscriber identifiers — only aggregate counts.
