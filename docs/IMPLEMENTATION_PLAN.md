# Bargain Hunter Implementation Plan

- Status: **v1.1 live** (2026-06-24)
- Related doc: `docs/PRD.md`

---

## 1. Tech Stack

| Area | Choice | Notes |
|---|---|---|
| Language | Python 3.13 | venv at `.venv/` |
| Scheduling | GitHub Actions cron `*/5` + cron-job.org external trigger | GH cron is unreliable; external trigger as backstop |
| RSS parsing | `defusedxml` | XXE-safe, supports `ozb:meta` namespace |
| HTTP | `httpx` | Synchronous, for direct Notion API calls |
| Data models | `pydantic` v2, `extra="forbid"` | Strict mode |
| Notion | `notion-client` + direct `httpx` | notion-client lacks `databases.query()`; direct calls needed; API version locked to `2022-06-28` |
| Email | SMTP (Gmail app password) | Email layer is pluggable — can switch to Resend |
| Templates | `Jinja2` | Responsive HTML email |
| Testing/quality | `pytest` + `ruff` (lint + format) | 36 tests, all passing |
| Feedback Worker | Cloudflare Workers (JS) | HMAC signature, writes to Notion Feedback DB |
| Infrastructure | Terraform + Cloudflare R2 state | Auto-applies on push to main |
| Telegram | Later channel — not implemented in v1 | |

---

## 2. Repository Structure

```
bargain-hunter/
  README.md
  docs/
    PRD.md
    IMPLEMENTATION_PLAN.md
  pyproject.toml
  .env.example
  .github/workflows/
    hunt.yml                   # Main scraping + notification workflow
    terraform-feedback.yml     # Cloudflare Worker auto-deploy
  config/
    settings.yaml              # Tunable parameters (thresholds, alerting, sources)
  data/
    deals_state.json           # Vote rolling snapshots (hot state via Actions Cache, daily commit)
    alert_state.json           # Maintainer alert throttle state (gitignored)
  feedback-worker/
    src/index.js               # Cloudflare Worker: receive thumbs up/down, HMAC verify, write Notion
  terraform/
    main.tf                    # Worker + subdomain resources
    variables.tf               # Includes feedback_hmac_secret (sensitive)
    backend.hcl                # R2 state backend (gitignored, CI writes dynamically)
    terraform.tfvars           # Non-sensitive variables (gitignored)
  scripts/
    setup_notion.py            # Auto-create Subscribers / Sent Log / Feedback databases
  src/bargain_hunter/
    __init__.py
    __main__.py
    main.py                    # Orchestration entry point
    models.py                  # Deal / Subscriber / Notification (pydantic)
    config.py                  # settings.yaml + env loading, load_dotenv()
    state.py                   # Vote snapshot read/write + cold-start detection
    alert_throttle.py          # Maintainer alert throttling (data/alert_state.json)
    matching.py                # Watch keyword matching (including expiry time parsing)
    observations.py            # Observation recording (optional)
    sources/
      base.py
      ozbargain.py             # RSS + ozb:meta parsing, HTML cleanup
      camelcamelcamel.py       # CCC AU top_drops RSS parsing
    scoring.py                 # velocity + hot score + discount parsing
    subscribers.py             # Read subscribers from Notion
    dedup.py                   # Sent log (Notion read/write)
    notify/
      email.py                 # SMTP sending
      render.py                # Jinja2 rendering + HMAC-signed feedback URLs
    templates/
      email.html.j2
  tests/
    test_ozbargain.py
    test_scoring.py
    test_matching.py
    test_observations.py
    test_state.py
```

---

## 3. Implementation Phases

| Phase | Content | Status |
|---|---|---|
| Phase 0 | Scaffold: repo, pyproject.toml, ruff, directory skeleton | ✅ |
| Phase 1 | Data models + config: Deal/Subscriber/Notification; settings.yaml | ✅ |
| Phase 2 | OzBargain adapter: RSS fetch, ozb:meta parsing, HTML cleanup, timezone normalisation | ✅ |
| Phase 3 | State snapshots + cold start: deals_state.json, Actions Cache, daily commit | ✅ |
| Phase 4 | Scoring + discount parsing: velocity, hot score, title price regex | ✅ |
| Phase 5 | Watch matching: keywords / target price / expiry time (`@HH:MM` / `@YYYY-MM-DDTHH:MM`) | ✅ |
| Phase 6 | Notion integration: setup_notion.py to create databases; read Subscribers; write Sent Log | ✅ |
| Phase 7 | Notifications: Jinja2 HTML email, SMTP, digest merging, frequency caps | ✅ |
| Phase 8 | Orchestrate main.py: full pipeline integration, idempotency, dry-run, maintainer alert | ✅ |
| Phase 9 | GitHub Actions: cron, concurrency lock, cache, secrets injection | ✅ |
| Phase 10 | Go live: Notion + SMTP with real environment, cron-job.org external trigger, subscribers added | ✅ |
| Phase 11 | v1.1: CCC source, Watch simplification, alert throttling, HMAC feedback, Cloudflare Worker + Terraform CI | ✅ |

---

## 4. v1.1 New Features (2026-06-24)

### CamelCamelCamel AU
- `sources/camelcamelcamel.py` parses `au.camelcamelcamel.com/top_drops/feed`
- Title regex: `"Product Name - down 18.16% ($5.99) to $26.99 from $32.98"`
- votes=0 (no community votes); noise gate changed to `discount_percent >= min_discount_percent`
- Merchant URL points to `amazon.com.au/dp/{ASIN}`

### Watch matching simplification
- Removed "must have discount" requirement; vote count alone is the noise gate (`min_votes=5`)
- CCC source fallback: either votes OR discount passing is sufficient (CCC has no vote counts)
- Optional price cap (`<=PRICE`) still supported

### Maintainer alert throttling
- `alert_throttle.py`: state persisted to `data/alert_state.json` (retained alongside Actions Cache)
- Policy: trigger only when consecutive failures ≥3 **AND** last alert was sent ≥1 hour ago
- A successful run automatically resets the counter

### HMAC-signed feedback links
- `notify/render.py`: `HMAC-SHA256(secret, "{deal_key}|{verdict}|{email}")` → 32-char hex
- Email template uses pre-signed `item.feedback_up_url` / `item.feedback_down_url`
- Worker validates the `?t=` parameter using the Web Crypto API; invalid signatures return 403

### Cloudflare Worker + Terraform CI/CD
- `feedback-worker/src/index.js`: dependency-free ES module, uploaded directly as content_file
- `terraform/main.tf`: `cloudflare_workers_script` + `cloudflare_workers_script_subdomain`
- R2 bucket stores Terraform state (S3-compatible backend)
- `terraform-feedback.yml`: push to main (touching `terraform/**` or `feedback-worker/src/**`) automatically runs `init → fmt → validate → plan → apply`; PRs run plan only

---

## 5. Key Implementation Decisions

**Notion API compatibility**
All versions of `notion-client` lack `databases.query()`; `databases.update()` silently drops `properties`.
Solution: switched entirely to direct `httpx` calls, API version locked to `2022-06-28`.

**GitHub Actions cron unreliability**
`*/5` is skipped or delayed 30–60 minutes on low-activity public repos.
Solution: cron-job.org triggers `workflow_dispatch` every 5 minutes; GH cron is the backstop.
Required permissions: GitHub Fine-grained PAT, `Actions: Read and write`.

**Keyword expiry time**
`@HH:MM` parsed as that day's AET time; `@YYYY-MM-DDTHH:MM` as an absolute time (both converted to UTC for storage).
`now >= expiry` skips that keyword (boundary is expired).

**Timezone**
All internal timestamps are UTC tz-aware. User-facing display uses `Australia/Sydney`.

**`.env` loading**
`load_dotenv()` in `config.py` does not override existing environment variables — GitHub Secrets always take precedence.

**Terraform state on R2 vs S3**
Free, no cross-region egress fees, tied to the Cloudflare account. R2 endpoint uses the S3-compatible backend; `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` are R2 API tokens using the fixed naming convention that Terraform's S3 backend requires.

**Non-sensitive Terraform variables hardcoded in the workflow**
`cloudflare_account_id`, `feedback_db_id`, and R2 endpoint are non-sensitive fixed values written directly into the YAML; avoids occasional GitHub Variables query failures and reduces operational overhead.

---

## 6. Test Coverage

| File | Tests | Coverage |
|---|---|---|
| `test_ozbargain.py` | 5 | RSS parsing, timezone, HTML cleanup |
| `test_scoring.py` | 13 | Discount parsing, velocity, hot score edge cases |
| `test_matching.py` | 18 | Keyword matching, target price, noise gate, keyword expiry |
| `test_observations.py` | — | Observation recording |
| `test_state.py` | — | Snapshot read/write |
| **Total** | **36+** | All passing |

---

## 7. Backlog (v1.2 direction)

| Priority | Item | Notes |
|---|---|---|
| High | Threshold calibration | After 1–2 weeks of data, label Sent Log entries as "should/shouldn't have sent" and use data to tune `hot_threshold`, `min_votes`, `early_burst_*` |
| Medium | Feedback data loop | Aggregate thumbs up/down data to validate which deal types subscribers actually care about, feeding back into threshold tuning |
| Medium | Email scanner false-click monitoring | Safe Links / Proofpoint and similar security proxies may pre-click feedback links; HMAC already prevents spam writes, but monitor Notion Feedback DB for records that appear before expected user click times |
| Low | Telegram channel | Interface already in place; users need to /start the bot to get their chat_id |
| Low | More reliable scheduling | AWS Lambda + EventBridge (v2); current GH cron has occasional delays |
| Low | Observations cache path | Confirm whether `data/observations/` is included in the Actions Cache paths (hunt.yml) |
