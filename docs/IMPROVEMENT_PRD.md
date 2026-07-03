# Improvement PRD — Bargain Hunter v2 features

Status: draft, agreed in principle 2026-07-03.
Owner: Shawn. Companion docs: `PRD.md` (original product), `STRATEGY_PLAN.md`, `WEB_PLAN.md`.

This PRD captures the agreed improvement roadmap after the 2026-07-03 bug-fix
sweep (commits `44b5ea64`..`22c26ca5`). It is written so that any workstream can
be picked up independently by a future session without re-deriving context.

## Context / current state

- The deal pipeline is triggered **externally by cron-job.org every 5 minutes**
  (not by GitHub Actions' own unreliable cron; briefly ran at 2-minute cadence
  until 2026-07-03). Scheduling is NOT a problem and needs no redesign.
- Scoring thresholds in `config/settings.yaml` were hand-calibrated on early
  observation data. Observation rows (every active deal, every run) accumulate
  in `data/observations/*.jsonl`; Sent Log and 👍/👎 feedback accumulate in
  Notion. None of this data currently feeds back into anything.
- Known business-logic gaps (documented in this file, P0): deals that trend
  during quiet hours are lost; CamelCamelCamel deals can never be "hot"
  (all candidacy gates are vote-based); price-drop re-alerts are configured
  (`significant_price_drop_percent`) but dead (`max_realerts_per_deal: 0`).

## Non-goals

- Replacing GitHub Actions or Notion. Both are fine at current scale.
- Paid growth, multi-region, non-AU sources.
- Real-time (<2 min) alerting.

---

## P0 — Business-logic gaps (fix what users already expect to work)

### P0.1 Overnight queue ("while you slept" digest)

**Problem.** During quiet hours (22:00–07:00 AET) `run()` returns before the
notify loop. A deal that spikes at 23:00 has decayed velocity by 07:00 and no
longer classifies hot — it is silently lost. ~9h/day of coverage gap.

**Requirements.**
- FR1: During quiet hours, still classify hot deals and evaluate watch matches;
  persist qualifying (deal, level/reason) pairs to state
  (`data/deals_state.json`, new `overnight_queue` section) instead of sending.
- FR2: On the first non-quiet run, drain the queue into the normal
  per-subscriber flow: same dedup, caps, category routing, block keywords.
  Queued items count against that day's caps.
- FR3: Queue entries carry the deal snapshot at queue time; if the deal has
  expired or gone out of stock by morning, drop it.
- FR4: A deal that re-qualifies in the morning on its own must not be sent
  twice (dedup by deal key already guarantees this — add a test).

**Acceptance.** Unit test: deal classifies hot at 23:00 → queued, not sent;
07:05 run sends it once; second 07:07 run sends nothing.

### P0.2 Discount-based hot candidacy for price-tracker sources

**Problem.** All three hot gates are vote-based; CCC deals have zero votes, so
CCC's biggest price drops only ever reach watch-keyword users.

**Requirements.**
- FR1: New gate in `is_hot_candidate`: a deal from a voteless source qualifies
  when `discount_percent >= hot.tracker_min_discount_pct` (new setting,
  suggested initial 30) AND `price_confidence == "high"`.
- FR2: Tier assignment for these deals: map discount depth to tiers (e.g.
  ≥50% → great, ≥30% → good) via config, since the vote-based score is
  meaningless for them. `top` stays vote-gated (universal_top unaffected).
- FR3: Settings additions must keep `Settings` (`extra="forbid"`) valid — add
  fields to `ScoringConfig.hot`, run full pytest (shared-config warning in
  AGENTS.md).

**Acceptance.** CCC fixture deal at 40% off, high confidence → classified
`good`, appears in digest; same deal at low confidence → not hot.

### P0.3 Price-drop re-alerts

**Problem.** `max_realerts_per_deal: 0` means a subscriber who saw a deal at
$350 never hears that it later hit their $300 watch ceiling. Defeats the point
of price-ceiling watches.

**Requirements.**
- FR1: Set `max_realerts_per_deal: 1`. Re-alert fires only when (a) a watch
  price ceiling is *newly* satisfied (was above, now at/below), or (b) price
  dropped ≥ `significant_price_drop_percent` from the price recorded in the
  Sent Log entry.
- FR2: Re-alert emails are visibly labelled ("Price drop: …") and count
  against the watch daily cap.
- FR3: `tests/test_dedup.py` (added 2026-07-03) already covers the re-alert
  machinery — extend it for the "newly satisfied ceiling" path before touching
  `dedup.py` logic.

**Acceptance.** Deal sent at $350 with watch `Sony <=300`; next run price $290
→ one re-alert; further runs at $285 → nothing.

### P0.4 Watch semantics polish (small)

- Document in README that `@HH:MM` expiry re-arms **daily** (current behaviour;
  keep it, it suits daily specials) — or add `@once HH:MM` if one-shot is wanted.
- When a `<=PRICE` keyword matches but the deal price could not be parsed,
  notify with a "price unverified" note instead of silently dropping
  (config-gated, default on).

---

## P1 — Flagship improvements

### P1.1 Backtest harness (build first — it de-risks everything else)

**Problem.** Every threshold change today needs a week of live observation to
evaluate. The observation log already contains everything needed to replay.

**Requirements.**
- FR1: New CLI `bargain-hunter backtest --settings <candidate.yaml>
  [--from DATE --to DATE]` that replays `data/observations/*.jsonl` through
  `classify_hot`/quality-gate logic with the candidate config.
- FR2: Output: per-tier fire counts, fire rate, list of deals that would newly
  fire / no longer fire vs. the current config, daily volume distribution.
- FR3: Join against Sent Log export (CSV/JSON dump; no live Notion dependency)
  and feedback data when available → precision proxy (👍 rate) per tier.
- FR4: Pure offline; no network, no state mutation. Fast (<10s on months of
  data).

**Acceptance.** Running backtest with the *current* settings over a period
reproduces the hot classifications recorded in that period's observations
(sanity check), modulo documented differences.

**Dependency for:** threshold auto-tuning (P2.2), P0.2 tier mapping choice.

### P1.2 Stacking alerts (bargain × strategy crossover — the differentiator)

**Problem.** strategy_hunter knows techniques (cashback rates, gift-card
discounts); bargain_hunter knows live deals. Nobody combines them.

**Requirements.**
- FR1: New collector: ShopBack + Cashrewards current rates (and rate *boosts*)
  per merchant → `data/strategies/rates.json`, refreshed by the daily strategy
  run. Graceful degradation if scraping fails (stale file + timestamp).
- FR2: Merchant matcher: map a deal's merchant (OzBargain provides it; CCC =
  Amazon) to a rates entry.
- FR3: When a hot/watch deal's merchant has an active cashback rate ≥ a
  threshold (or a boost event), append a "Stack it" section to the deal item:
  effective price arithmetic (deal price × (1 − cashback) [× gift-card discount
  when a guide documents one]).
- FR4: Never present stacking as guaranteed — copy must say "typically
  excludes gift cards / check store terms".
- FR5: Frontend `/guides` gains a merchant page section showing current rate +
  applicable guides (render from `rates.json`, static rebuild like `/deals`).

**Acceptance.** Fixture: hot deal from a merchant with a 10% boost → digest
item shows effective-price line; merchant without rates → no section.

### P1.3 LLM title normalisation

**Problem.** Regex price extraction, keyword category taxonomy, and the lack of
cross-source dedup are all symptoms of unstructured titles.

**Requirements.**
- FR1: Batch step after fetch: send new-to-system titles (only first sighting;
  cache by deal key in state) to Claude Haiku → strict JSON: `{brand, model,
  product_type, category, price, was_price, discount_pct, merchant,
  is_service_or_promo}`. Pydantic-validated; on failure fall back to current
  regex path (never block the run).
- FR2: Regex extraction remains the fallback and the comparison baseline; log
  disagreements to observations for a few weeks before trusting LLM values for
  display.
- FR3: Category routing prefers LLM `category` (mapped to the existing bucket
  ids) over keyword taxonomy when present.
- FR4: Cross-source fingerprint: `brand+model` normalised → dedupe OzB/CCC
  duplicates within a run and in Sent-Log dedup (same product = same alert).
- FR5: Cost guard: cap LLM calls per run (config), skip silently when
  `ANTHROPIC_API_KEY` unset (AGENTS.md graceful-degradation convention).

**Acceptance.** Fixture titles (the gnarly ones from `test_scoring.py`) parse
to correct structured fields; pipeline runs unchanged with no API key.

---

## P2 — Next wave

### P2.1 Telegram channel
Per-subscriber `channels` already validated in portal (`Email`/`Telegram`).
Bot sends the same rendered digest (compact format) via Bot API; subscriber
stores chat id via a `/start` deep-link flow through portal-worker. Email
remains the fallback. Faster than email for time-sensitive deals.

### P2.2 Calibration report + threshold tuning loop
Weekly GH Action: run backtest (P1.1) over the trailing 2 weeks, join 👍/👎,
email maintainer a report (fire rate per tier, 👍 rate, top misses). Later:
grid-search candidate thresholds offline and propose a settings diff (existing
plan: train a simple classifier on labelled Sent Log once enough data).

### P2.3 Semantic watch matching
Exact phrase match stays primary. Add embedding fallback ("noise cancelling
headphones" → Sony WH-1000XM6) with a clearly-labelled "semantic match" reason
and a higher noise-guard bar. Needs an embeddings dependency + cache; keep
optional/config-gated.

### P2.4 Compliance + deliverability (small, do early)
`List-Unsubscribe` (+ `List-Unsubscribe-Post`) headers on all digests and a
one-click deactivate endpoint (signed link, feedback-worker pattern). Required
posture under the AU Spam Act and improves inbox placement.

## P3 — Backlog (unordered)

- Per-subscriber cadence tiers: instant / daily digest / weekly best-of.
- One-click mute merchant/category from the email (signed link → Notion block
  keywords).
- Per-subscriber private RSS feed (cheap; served by portal-worker).
- Combo calculator on `/guides` (price × cashback × gift-card stacking,
  interactive).
- More sources: Amazon AU lightning deals, eBay Plus, merchant RSS feeds —
  one module + frozen fixture each.
- Metrics page (private route): sends/day, fire rate per tier, error rate,
  rendered from observations + Sent Log.
- Repo bloat: archive `data/observations/` monthly to R2 (or squash data
  commits); git history is growing unboundedly.
- Magic-link POST-confirm page (true single-use tokens; see comment in
  `portal-worker/src/lib/kv.ts`).
- Security headers on Pages (`public/_headers`: `Referrer-Policy: no-referrer`,
  `X-Content-Type-Options: nosniff`, frame-ancestors baseline).
- Watch UX: structured builder form in portal (keyword + ceiling + expiry
  fields) that serialises to the existing syntax — zero pipeline change.
- Consolidate duplicated `make_notion_client` (subscribers.py / dedup.py).
- Precompute deal-side watch-match signals once per run (perf; matters as
  subscriber count grows).

## Suggested sequencing

| Phase | Items | Rationale |
|---|---|---|
| 1 | P1.1 backtest, P0.3 re-alerts, P2.4 unsubscribe | Backtest de-risks all tuning; re-alerts has tests ready; compliance is small |
| 2 | P0.1 overnight queue, P0.2 CCC hot path (tiers chosen via backtest), P0.4 | Closes the user-facing coverage gaps |
| 3 | P1.3 LLM normalisation | Unblocks better categories, dedup, price accuracy |
| 4 | P1.2 stacking alerts, P2.1 Telegram | Differentiation + speed |
| 5 | P2.2 calibration loop, P2.3 semantic match, P3 picks | Compounding polish |

Effort feel (single-session-sized unless noted): P0.3, P0.4, P2.4 small;
P0.1, P0.2, P1.1 medium; P1.3, P2.1 medium-large; P1.2 large (two sessions:
rates collector, then matcher+render).
