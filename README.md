# Bargain Hunter

Runs every 5 minutes on GitHub Actions. Fetches deals from OzBargain, scores
them for velocity ("爆款") and matches against personal watch lists ("盯货"),
then sends email digests to subscribers managed in Notion.

Full design: [`docs/PRD.md`](docs/PRD.md) · [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)

## Two tracks

- **Hot (爆款):** vote velocity + absolute votes + age. Passes a threshold → notifies all opt-in subscribers. Low frequency, high precision.
- **Watch (盯货):** keyword hits your Notion watch list and meets a discount / target price condition. Only notifies the subscriber who listed that keyword.

A deal that qualifies on both tracks is merged into one notification.

## Quick start (local dev)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest
```

Verify the OzBargain fetcher works:

```bash
python -m bargain_hunter --dry-run
# or the installed script:
bargain-hunter --dry-run
```

## First-time Notion setup

1. Create a Notion integration at <https://www.notion.so/my-integrations> with
   **Insert content** + **Read content** + **Update content** permissions.
2. Create or pick an existing Notion page and share it with the integration.
   Copy the page ID from its URL (32 hex chars after the last `/`).
3. Run the setup script — it creates both databases and prints the IDs:

   ```bash
   export NOTION_TOKEN=secret_xxx
   export NOTION_PARENT_PAGE_ID=<page-id>
   python scripts/setup_notion.py
   ```

4. Copy the printed DB IDs into your `.env` (local) and GitHub Secrets (Actions).

## Configuration

Copy `.env.example` → `.env` and fill in credentials. `.env` is git-ignored.

Tunable thresholds (velocity window, hot score, discount %, quiet hours, etc.)
are in `config/settings.yaml` — edit and redeploy, no code change needed.

## GitHub Actions setup

Add these Secrets to the repo (Settings → Secrets and variables → Actions):

| Secret | Description |
|---|---|
| `NOTION_TOKEN` | Integration token |
| `NOTION_SUBSCRIBERS_DB_ID` | From `setup_notion.py` output |
| `NOTION_SENT_LOG_DB_ID` | From `setup_notion.py` output |
| `SMTP_HOST` | e.g. `smtp.gmail.com` |
| `SMTP_PORT` | e.g. `587` |
| `SMTP_USERNAME` | Your Gmail address |
| `SMTP_PASSWORD` | Gmail app password (not your login password) |
| `EMAIL_FROM` | Display name + address, e.g. `Bargain Hunter <you@gmail.com>` |
| `MAINTAINER_EMAIL` | Where to send failure alerts |

Then trigger a manual run with `workflow_dispatch` and watch the logs.
The first run is always a cold start — it records a baseline but sends nothing.
From the second run onwards, hot deals and watch matches will generate notifications.

## Privacy

- `data/deals_state.json` stores vote snapshots only (no personal data). It is
  committed once per day (AET midnight) as a calibration seed; hot-path state
  travels via GitHub Actions Cache.
- Subscriber info, watch lists, and sent records live only in your private Notion.
- Public repo logs never print subscriber identifiers — only aggregate counts.

## Current state

All phases implemented. Ready for Phase 10 (connect real Notion + SMTP, calibrate thresholds).
