# Bargain Hunter Product Requirements Document (PRD)

- Status: Draft v0.1, pending review
- Date: 2026-06-18
- Author: Shawn Wang
- Decision baseline: Python · Email (v1) + Telegram (later) · Deal history in repo / Subscribers and sent log in Notion · Sources: OzBargain + CamelCamelCamel (degradable)

---

## 1. Background and Goals

In Australia, deal-hunting mainly happens on OzBargain, but genuinely good deals move fast — stock runs out or listings expire within minutes, making it impossible to keep up manually.

**Goal:** Automatically and regularly discover deals that are "genuinely worth acting on" and push personalised alerts to each subscriber so they hear about deals first.

**Success metrics (v1):**
- System runs reliably on schedule and correctly parses OzBargain deals including vote counts.
- Can calculate vote velocity and select "hot" deals by threshold; can do targeted matching against each person's watchlist.
- Notifications are de-duplicated and merged into summaries, delivered by email (v1); Telegram as a later channel.
- Public repo does not leak any subscriber privacy.

**Non-goals (explicitly out of scope for v1):**
- No automated purchasing or auto-checkout.
- No full product price history database.
- No web frontend or admin dashboard (Notion serves as the backend).
- No aim to cover every platform; no machine learning scoring.

---

## 2. Users and Roles

- **Subscribers (~10 people):** Register email / Telegram in Notion, set watchlist and preferences, passively receive alerts.
- **Maintainer (you):** Manage Notion data, secrets, scoring thresholds, and operations.

---

## 3. Core Design: Two Independent Tracks

Treat "vote velocity" and "price discount" as two independent tracks rather than two variables in a single algorithm, because their **timeliness and precision are opposite**:

| Track | Signal | Nature | Audience | Frequency / Threshold |
|---|---|---|---|---|
| **Hot** | Vote velocity + absolute vote count + age | Lagging but accurate, low false-positive rate | All subscribers who have this enabled | Low frequency, high threshold — quality over quantity |
| **Watch** | Keyword match against personal watchlist + discount / low price | Leading but noisy, tolerates noise | Only users watching that item | Higher frequency, lower threshold — proactive |

**Why both:** Velocity is a lagging indicator — by the time the surge is confirmed, the hottest deals may already be nearly gone, but it reliably catches "objectively good deals". Price/discount is available the moment a deal is posted — fast but noisy. The two overlap (good prices usually get voted up quickly), but because their timeliness is opposite, each covering its own lane makes most sense: the Hot track casts a wide net for objectively good deals; the Watch track gets ahead on items you've specifically flagged.

**Overlap handling:** If a deal makes the Hot list AND matches someone's watchlist, that user receives **only one notification** (merged, labelled "you're watching + trending site-wide").

---

## 4. Data Sources

The source layer is a pluggable adapter interface with a unified `Deal` model output. Future sources (Catch, Amazon, social media, etc.) can be added.

### 4.1 OzBargain (primary source — verified)
- Feed: `https://www.ozbargain.com.au/deals/feed`
- Each item includes `<ozb:meta>` with `votes-pos`, `votes-neg`, `comment-count`, `click-count`, merchant direct `url`, `image`, `expiry` (some with `starting`).
- Supports both tracks: the main feed for velocity; keyword/tag search feeds (e.g. `.../cat/<category>/deals/feed`) for Watch.
- **Velocity works from RSS alone — no HTML scraping needed.**

### 4.2 CamelCamelCamel AU (secondary source — price/Watch track, degradable)
- Provides per-product price history RSS and an `https://au.camelcamelcamel.com/top_drops` drop page.
- Value: provides real price history context for "is this actually a low price?", filling OzBargain's gap on price history.
- ⚠️ Limitations: top_drops has no official feed — requires HTML scraping, vulnerable to ToS and page structure changes; keyword-to-ASIN mapping has overhead.
- **Degradation strategy:** Built as an adapter that can be disabled/replaced at any time. Watch track runs first on OzBargain keyword search feeds; CCC added incrementally as a price signal; system operates normally when CCC is unavailable.

---

## 5. Functional Requirements

- **FR1 Fetch:** Regularly pull from each source, normalise to a unified `Deal` model.
- **FR2 State snapshot:** Record each deal's `(votes_pos, votes_neg, comment_count, timestamp)` each run, for velocity calculation; persistence is described in §10.1.
- **FR3 Hot scoring:** Calculate hot score per §6 algorithm; must exceed threshold to enter the Hot track.
- **FR4 Watch matching:** Keyword + target price + minimum discount matching against personal watchlists.
- **FR5 De-duplication (with "re-alert on improvement"):** Same deal to same person defaults to one notification; **but if the deal materially improves (price drops a configured amount more, or vote count / heat crosses up a tier), it may be re-sent — max `max_realerts_per_deal` times per deal per person (default 1)**, to avoid spam. Sent log stored in Notion, with previous trigger state recorded to support re-alerting; access patterns and idempotency described in §10.2.
- **FR6 Notifications:** v1 implements email only; notification layer models "channels the subscriber owns" — Telegram as a later channel (see §14 Decision 4). Multiple deals in one run merged into a single digest; per-person daily frequency cap; optional quiet hours (both computed in AET — see §14 Decision 7). Daily cap counted by "deal × person × day", not by email count; same deal matching both Hot and Watch still counts as one.
- **FR7 Subscribers and preferences:** Read from Notion (schema in §7).
- **FR8 Cold start:** First run records baseline only, no notifications; subsequent runs only consider deals first seen after the system started — no backfilling history.
- **FR9 Expired/invalid filtering:** Do not alert on deals with a past `expiry`, or marked as expired / out of stock.
- **FR10 Observability and failure alerting:** Each run outputs a summary (aggregate counts, no subscriber identifiers); **failures must self-alert** — if the run crashes, a critical call errors, or 0 deals are parsed (almost certainly a feed format break rather than no deals that day), send an email to the maintainer; also set a heartbeat so that if no successful run completes for N hours, an alert fires. Silent failure is the worst failure mode for an alerting system.

---

## 6. "Good Deal" Scoring Algorithm (all parameters configurable)

### 6.1 Velocity definition
- Short-window rate: compare current snapshot with the nearest snapshot `window_minutes` ago to compute `Δvotes / Δt` (votes/hour); fall back to the two most recent snapshots if history is insufficient, but don't use the cold-start first round for notifications.
- All-time average: `votes_pos / age_hours` since posting.

### 6.2 Hot track
Any **one** of the following makes a deal a candidate:
1. Net votes gained in the most recent window ≥ `V1` (default example: +15 votes in 1 hour).
2. Early burst: `age < H` hours and `votes_pos ≥ V2` (default example: ≥25 votes within 2 hours).
3. Velocity in the top `P%` of currently active deals.

Candidates then compute a weighted hot score; must exceed `HOT_THRESHOLD` to be pushed:
- Positive: vote velocity, absolute vote count, comment velocity.
- Penalties: age (older = lower weight); high `votes_neg` ratio (controversial/negative) lowers score.
- Initial formula (tunable, calibrate after launch):
  `hot_score = age_factor * (vote_velocity / V1 + log1p(votes_pos) / log1p(V2) + 0.25 * comment_velocity) - neg_vote_penalty_weight * neg_ratio`
  - `age_factor = 0.5 ** (age_hours / age_penalty_half_life_hours)`
  - `neg_ratio = votes_neg / max(votes_pos + votes_neg, 1)`
  - Percentile candidates computed only among active, non-expired deals that meet `min_votes_for_percentile`, to avoid low-sample noise.

### 6.3 Watch track
- Keyword match against deal title/description (case-insensitive, optionally fuzzy), checking user watchlists.
- Trigger condition: keyword matched **AND** (discount ≥ user's `MIN_DISCOUNT` **OR** price ≤ user's target price **OR** CCC identifies it as a recent low).
- Discount parsing (best-effort, not conservatively rejecting): use regex to **best-effort** extract price and `was/RRP/% off` from the title (e.g. `$X (was $Y)`, `30% off`). When price/discount cannot be extracted, don't let everything through — apply noise protection: keyword must be an exact phrase match, OR the deal must have reached at least `watch.unpriced_min_votes`, OR the user has explicitly configured that keyword as "alert on any match". This prevents broad terms like `SSD`, `laptop`, `iPhone` from flooding notifications.

### 6.4 Default thresholds
> ⚠️ **The thresholds in `config/settings.yaml` are conservative starting guesses, not data-validated optimal values.** Calibrate against real data after launch: run for yourself only first, for 1–2 days, then adjust based on "should have sent / shouldn't have sent" observations (see Implementation Plan Phase 10).

All thresholds (`V1/V2/H/P/HOT_THRESHOLD/MIN_DISCOUNT/window length`) can be changed in `settings.yaml` and take effect immediately — no code change needed.

---

## 7. Notion Data Model

### DB: Subscribers
| Field | Type | Description |
|---|---|---|
| Name | Title | Full name |
| Email | Email | Email address |
| Telegram Chat ID | Text | For Telegram alerts |
| Active | Checkbox | Whether enabled |
| Channels | Multi-select | Email / Telegram |
| Subscribe Hot Deals | Checkbox | Whether to receive Hot track alerts |
| Watch Keywords | Text (multi-line) | One keyword per line, optional target price, e.g. `iPhone 17 Pro <=1800` |
| Min Discount % | Number | Minimum discount for Watch track |
| Categories | Multi-select | Optional category filter |
| Max Alerts/Day | Number | Daily cap, default 10 |
| Quiet Hours | Text | Optional quiet period (interpreted in AET; v1 does not store per-person timezone) |

### DB: Sent Log (private, for de-duplication)
| Field | Type | Description |
|---|---|---|
| Deal ID | Title | Unique deal identifier |
| Subscriber | Relation/Email | Recipient |
| Channel | Select | Email / Telegram |
| Track | Select | Hot / Watch |
| Sent At | Date | Time sent |
| Price | Number | Price identified at send time (nullable) |
| Discount % | Number | Discount identified at send time (nullable) |
| Votes Pos | Number | Positive vote count at send time |
| Heat Band | Select | Heat tier at send time, for cross-tier detection |
| Re-alert Count | Number | Number of re-alerts sent for this deal to this subscriber |
| Trigger Signature | Text | Rule version + trigger reason summary, for debugging and idempotency |

> This personal data lives **only in Notion (private)** — never in the public repo.

### (Optional) DB: Deals Observation Log
Records deals judged as hot and their scores, for retrospective analysis and threshold tuning. Optional in v1.

---

## 8. Notification Content (UX)

- **Email (HTML template):** Title, price/discount, vote count and velocity (e.g. "+28 votes in the past hour"), why it was sent (matching rules), direct links (OzBargain post + merchant URL), expiry time. Multiple deals in one run → one digest list. Footer explains how to manage subscriptions in Notion.
- **Telegram:** Concise text card + link, suited for instant reading.
- Copy is restrained and information-dense — no piling on adjectives.

---

## 9. Privacy / Security / Compliance

- **Public repo commits only non-personal data** (daily deal vote history snapshots — see §10.1); no subscriber information whatsoever.
- Secrets (`NOTION_TOKEN`, email API key, `TELEGRAM_BOT_TOKEN`, etc.) go through GitHub Actions Secrets — never committed; `.env.example` provided.
- Personal data (email, watchlist, sent history) lives only in Notion (private).
- Respect source ToS (polite scraping): prefer RSS, reasonable frequency; set a real, contactable User-Agent; conditional request caching (`If-Modified-Since`/`ETag`, 304 responses avoid re-downloading); exponential backoff on `429`/rate limits; notifications link to the OzBargain post page (`Deal.url`) rather than the merchant direct link, so the source gets the traffic; no aggressive scraping; CCC scraping is conservative and can be disabled at any time.
- No credentials, API keys, PII, or production data accepted or stored; public repo and logs contain no PII. Private Notion stores only minimum necessary PII (email, Telegram chat id, watchlist preferences, sent log).
- **Public repo Actions logs are visible to everyone:** Logs must never print any subscriber identifier (email, Telegram chat_id, name) — only aggregate counts or opaque Notion internal IDs. This is a more subtle PII exposure surface than "don't commit secrets".
- **Public repo + Secrets attack surface:** The scraping workflow only allows `schedule` and `workflow_dispatch` triggers — not `pull_request_target`; no secrets are exposed on any PR trigger path; `GITHUB_TOKEN` is configured with minimum permissions (only "daily state commit" requires `contents: write`); third-party actions are pinned to full commit SHAs to prevent supply chain hijacking.

---

## 10. Non-functional Requirements

- **Timeliness:** GitHub Actions scheduling runs as fast as every 5 minutes (`*/5`), but is commonly delayed 5–15 minutes during peak periods. v1 accepts this delay (frequency and state approach in §10.1); v2 evaluates migrating to AWS Lambda + EventBridge or a more reliable external scheduler for tighter polling.
- **Cost:** Fully covered by free tiers (public repo Actions standard runner with no minute limit, SMTP/Gmail, Telegram, Notion free tier, CCC free).
- **Reliability:** Use concurrency lock to prevent a new run triggering before the previous completes; retry critical calls; entire pipeline is idempotent.
- **Maintainability:** Parameterised config (strict block uses pydantic `extra="forbid"` — typos in `settings.yaml` keys raise errors immediately rather than silently ignoring, preventing "I changed it but it didn't take effect"; `SourceConfig` keeps `extra="allow"` to accommodate source-specific keys like `feed_url`); pluggable source adapters; clear logging.

### 10.1 Run frequency and state persistence (decided 2026-06-18)

**Run frequency:** cron `*/5 * * * *`, evenly distributed throughout the day. 5 minutes is the fastest interval GitHub Actions allows; actual trigger interval is roughly 5–15 minutes due to queue delays. Even spacing makes velocity snapshots a regular equidistant time series, convenient for computing `Δvotes/Δt` with no overnight gap. Use `concurrency` lock to prevent overlapping reruns caused by delays.

**Two types of "history" kept separately, each clean:**

1. **Hot state (velocity rolling snapshots) → GitHub Actions Cache, not in git, but only as best-effort hot cache.**
   - File `deals_state.json` structure: `{ deal_key: [ {ts, votes_pos, votes_neg, comment_count}, ... ] }`, keeping only snapshots within the most recent retention window (default 24 hours); older snapshots are pruned, keeping file size bounded.
   - Each run: restore from cache → append current snapshot → prune expired → save back to cache. **No git commits produced.**
   - Cache key uses `deals-state-<run_id>` + `restore-keys: deals-state-` to get the most recent copy. Note: GitHub Actions Cache is immutable and has capacity/eviction policies — it cannot be treated as a strongly consistent database; on cache miss, restore from the daily-committed history seed and treat that run as cold-start/low-confidence.

2. **Persistent history (for threshold tuning and disaster recovery seed) → committed to repo once per day.**
   - On the first run of each day (by AET), commit the cleaned-up snapshots to `data/` (~1 commit/day).
   - Dual purpose: (a) long-term data for threshold tuning; (b) recovery seed when cache is lost (evicted / first run), so velocity doesn't have to restart cold.

**Why this design:** Committing every run at 5-minute intervals would produce ~288 commits/day in a public repo, polluting git history. Decoupling "snapshot recording" (high-frequency, best-effort cache) from "history commits" (low-frequency, in git) means most runs maintain 5-minute resolution while the repo history grows by only 1 commit per day. Privacy boundary unchanged: both cache and commits contain only non-personal deal vote data. If cache eviction is found to affect hot detection, migrate hot state to an updatable external state store (e.g. private Notion table, Gist, S3/R2) as a priority.

### 10.2 De-duplication and idempotency (decided 2026-06-18)

**Where de-duplication data lives:** Sent Log remains in Notion (it's personal data, must stay in the private store).

**Access pattern (rate-limit prevention):** Each run **queries the Sent Log once for the most recent de-duplication window (default 7 days)**, loads results into memory for local comparison — **not per-(deal, person) point queries** — since Notion API is ~3 requests/second; point queries would hit rate limits and get slower as Sent Log grows. 7-day window is sufficient to cover a deal's lifespan; records beyond the window are archived/deleted periodically so Sent Log doesn't grow unboundedly.

**Idempotency (prevent re-sending on mid-run crash):** For each channel, **write one Sent Log entry immediately after each successful send** (not batched to the end of the run), with retries on the write. If SMTP succeeds but Notion write ultimately fails, a re-send may occur on the next run — so errors must be logged and the maintainer alerted; v1 targets at-least-once delivery + best-effort duplicate avoidance, not strict exactly-once. Combined with the `concurrency` lock in §10.1 to prevent concurrent overlap from delays.

**Re-alert on improvement (corresponds to FR5):** De-duplication is not "never send again". Record key state at the time of last send (price / discount / vote tier); if in a new run the deal materially improves (price drop meets configured threshold, or vote count crosses a tier), and re-alert count for this deal to this person hasn't exceeded `max_realerts_per_deal` (default 1), re-send and increment the count.

**Daily cap counting:** Reuse this recent-window Sent Log, count deals sent **on the current AET day** to determine if `max_alerts_per_day` has been exceeded (timezone — §14 Decision 7). During quiet hours, don't send non-urgent notifications by default; after quiet hours end, the next run re-evaluates deals still valid and within cap — expired or invalid deals are not resent.

---

## 11. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Velocity lags — the hottest deals are already gone | Watch track (leading signal) + early burst rule to compensate |
| Actions schedule delays | v1 accepts; v2 migrates to tighter scheduling |
| False positives / missed deals | Tunable thresholds + observation log retrospective iteration |
| CCC fragile / ToS | Adapter can be degraded; OzBargain search feed as fallback |
| Emails going to spam | v1 uses Gmail app password for low-cost validation; can add Telegram in parallel or switch to higher-reputation sending domain later |
| Keyword-to-ASIN friction | v1 has users paste Amazon links, or use OzBargain keyword feed |

---

## 12. v1 Acceptance Criteria

- Runs on schedule; correctly parses OzBargain deals including vote counts.
- Can calculate velocity and select hot deals by threshold; can do targeted matching against Notion watchlists.
- Can de-duplicate and send merged notifications by email; Telegram design retained but not in v1 acceptance scope.
- First run does not backfill history.
- Secrets not committed; public repo has no privacy leaks.

---

## 13. Roadmap

- **v1 (MVP, current):** Features above.
- **v1.1:** Threshold tuning + observation log + Amazon/CCC enhancements.
- **v2:** Tighter scheduling (Lambda), more sources, smarter scoring.

---

## 14. Confirmed Decisions (2026-06-18)

1. **Secondary source:** CamelCamelCamel AU (degradable, off by default, added incrementally).
2. **Thresholds:** Start with defaults from §6 and tune based on real data.
3. **Notion:** Script auto-creates both the Subscribers and Sent Log databases (requires an integration token with database creation permissions).
4. **Notification channels (revised 2026-06-18):** Channels are sent based on what the subscriber actually has — email if they have an email, Telegram if they have Telegram, both if they have both — **neither is required**. **v1 implements email only (SMTP, defaulting to Gmail app password — $0, no own domain needed)**; Telegram retained as a later channel (onboarding is more involved: users must /start the bot first and their chat id needs to be matched to their Notion entry). Email layer is built as pluggable — can switch to Resend with a custom domain later to improve deliverability. [Replaces previous "Telegram as primary" language.]
5. **Naming:** Project / package / public repo uniformly `bargain-hunter` (local folder rename deferred to last, to avoid breaking current session project associations).
6. **Run frequency and state storage:** cron fixed `*/5` (evenly distributed all day); velocity rolling snapshots primarily restored from best-effort GitHub Actions Cache (not in git), committed to repo once per day as tuning data and cache disaster-recovery seed. Details in §10.1.
7. **Timezone:** v1 assumes all subscribers are in Australia; entire system uniformly uses Australian Eastern Time (`Australia/Sydney`, same timezone as Melbourne and Sydney, `zoneinfo` handles DST automatically) for daily cap resets, quiet hours, and daily commit boundaries; no per-subscriber timezone handling (`Subscriber`'s Timezone field removed, unified timezone in `config/settings.yaml` under `run.timezone`).
