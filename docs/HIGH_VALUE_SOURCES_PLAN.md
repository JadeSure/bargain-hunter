# High-value remote sources — execution plan (AU finance, travel, global digital)

Status: approved, not started. Written 2026-08-20.
Companion: [`GLOBAL_DEALS_PLAN.md`](GLOBAL_DEALS_PLAN.md) (NA/CN digital deals) —
this plan **extends** it and **corrects two things in it** (see "Corrections").

All endpoints below were fetched live on 2026-08-20 from a Melbourne IP.
Re-verify before trusting any of them. Where a probe failed, that is recorded
as a failure rather than smoothed over.

---

## 0. Why this exists

`GLOBAL_DEALS_PLAN.md` scoped itself to *digital goods* because the trigger
incident was a missed Grok subscription. That scope is correct for what it
covers, but it leaves the pipeline aimed at the **smallest** category of
remotely-capturable value for an Australian resident.

Rough annual order of magnitude, all fully online, all legitimate:

| Category | ~$/year | Covered today |
|---|---|---|
| Deposit-rate optimisation, mortgage refi cashback | 500–5000 | ✗ |
| Credit-card signup bonuses (80–150k points) | 800–1500 | ✗ |
| Energy / insurance / telco churn | 500–1500 | ✗ |
| Lost super, unclaimed money (one-off) | 0–thousands | ✗ |
| Airfare deals / error fares | 500–1500 per trip | ✗ |
| Gift-card stacking (≈15% off everyday spend) | 300–800 | partial (`cashback.py` covers the cashback layer only) |
| **Physical goods discounts** | 200–500 | ✓ (existing pipeline) |
| **LLM / SaaS discounts** | 50–300 | planned (`GLOBAL_DEALS_PLAN.md`) |

Orders of magnitude, not precise figures. The ordering is the point: the
pipeline currently covers the bottom two rows.

The headline finding is that the top row is reachable through a **free,
unauthenticated, legally-mandated API** — see Phase B3.

---

## Corrections to `GLOBAL_DEALS_PLAN.md`

Apply these to that file as part of Phase A. They are not new features; they
are defects in the existing approved plan.

### C1 — the OpenRouter spec silently drops every free model

`GLOBAL_DEALS_PLAN.md` §1b says:

> **Skip ids absent from `previous`** — dated variants mean a cheap *new* id is
> a new model, not a price cut.

Correct for price *cuts*, exactly backwards for the highest-value case. A model
that launches **at zero price** is always an absent id, so it is always skipped.

Verified 2026-08-20: `openrouter.ai/api/v1/models` returns **414 models, 20 of
them zero-priced**, including `z-ai/glm-5.2:free`,
`nvidia/nemotron-3.5-lightning:free`, `cohere/north-mini-code:free`,
`poolside/laguna-s-2.1:free`.

Fix — a second branch in `llm_prices.py`, roughly five lines:

```python
is_new = model_id not in previous
is_free = new_prompt == 0.0 and new_completion == 0.0
if is_new and is_free:
    emit(...)          # "now free" deal
    continue
if is_new:
    continue           # existing guard: new priced model is not a price cut
```

Title for the free case: `f"{name}: now free on OpenRouter (US$0/M tokens)"`,
`discount_percent=100.0`, `price=0.0`.

Note this is also the project's only **compliant** route to mainland-Chinese
models: GLM (Zhipu) via OpenRouter needs no +86 number, no 实名认证, no Alipay.

### C2 — the mainland-China rejection needs a stronger reason recorded

`GLOBAL_DEALS_PLAN.md` attributes thin CN coverage to payment gating. Verified
on 2026-08-20, the more durable reason is **content legality**, and it should be
recorded so nobody re-evaluates these sources in six months.

`nodeseek.com/rss.xml` → **HTTP 200, RSS 2.0, 20 items** — reachable, and
topically on-target for AI deals. Actual sampled titles:

| Sampled title | What it actually is |
|---|---|
| `GPT Plus 菲区实测` | Region-pricing arbitrage — ToS breach |
| `人找车，gpt-4 team，75` | 车队 / seat sharing — ToS breach |
| `sub2api 放了一个 pro20 账号上去` | Reselling a subscription as API access |
| `高价收购 SG-starhub1-Nano` | Account trading |

`linux.do` → **403 on every endpoint** tested (`/latest.json`, `/latest.rss`,
`/posts.json`), Cloudflare-gated, and `robots.txt` declares
`Content-Signal: search=yes, ai-train=no, use=reference`. Dead on both access
and policy grounds.

The consequence that matters: `/guides` is a **public website**, and Stage-2
Gemini extraction turns harvested discussion into published how-tos. Ingesting
NodeSeek would mean publishing account-fraud instructions under the project's
name. This is the same line `GLOBAL_DEALS_PLAN.md` already drew for app-store
country switching.

→ Add both to that file's "Rejected sources" with this evidence. **Do not add
NodeSeek or linux.do as sources.**

---

## Phase A — foundation + config (one agent, no new modules)

Every later phase depends on this, and it is the only phase that touches shared
files. It must land before Phase B merges.

### A1. `config/settings.yaml`

1. **`digital` category bucket** — this is `GLOBAL_DEALS_PLAN.md` Phase 0 and
   fixes a live bug: the `categories:` taxonomy has no software/digital bucket,
   so every software deal is permanently out-of-category for any subscriber with
   `Categories` set. Append exactly as specified there.

2. **New `sources:` blocks.** `SourceConfig` is `extra="allow"`
   (`config.py:154`), so arbitrary keys need no schema change:

```yaml
  # --- AU finance: CDR product reference data (see Phase B3) ---
  bank_rates:
    enabled: true
    poll_interval_minutes: 1440        # daily; rates do not move hourly
    currency: "AUD"
    min_rate_rise_bps: 10              # alert when a deposit rate rises >= 10bp
    min_bonus_points_rise: 10000       # alert when card signup points rise
    brands:                            # publicBaseUri verified 2026-08-20
      - {name: "ING",       base: "https://id.ob.ing.com.au",              x_v: 4}
      - {name: "UBank",     base: "https://public.cdr-api.86400.com.au",   x_v: 4}
      - {name: "Macquarie", base: "https://api.macquariebank.io",          x_v: 4}
      - {name: "Up",        base: "https://api.up.com.au",                 x_v: 4}
      - {name: "CommBank",  base: "https://api.commbank.com.au/public",    x_v: 4}
      - {name: "Westpac",   base: "https://digital-api.westpac.com.au",    x_v: 4}
      - {name: "NAB",       base: "https://openbank.api.nab.com.au",       x_v: 4}
      - {name: "ANZ",       base: "https://api.anz",                       x_v: 4}
      - {name: "Bendigo",   base: "https://api.cdr.bendigobank.com.au",    x_v: 4}
      - {name: "BOQ",       base: "https://api.cds.boq.com.au",            x_v: 5}
    product_categories:
      - "TRANS_AND_SAVINGS_ACCOUNTS"
      - "TERM_DEPOSITS"
      - "CRED_AND_CHRG_CARDS"

  # --- Travel: AU-departure airfare deals (see Phase B1) ---
  iknowthepilot:
    enabled: true
    poll_interval_minutes: 120
    currency: "AUD"
    feed_urls: ["https://www.iknowthepilot.com.au/feed/"]
```

3. **`voteless_sources` / `trusted_sources`** — extend the lists from
   `GLOBAL_DEALS_PLAN.md` §1d with `bank_rates` and `iknowthepilot`. Both carry
   no vote signal; both must stay out of the AU heat baseline (TRAP 1 there).

4. **`strategy:` block** — new `rss` source and widened config-only levers:

```yaml
  sources:
    rss:                               # see Phase B4
      enabled: true
      request_delay_seconds: 2.0
      feeds:
        - {url: "https://www.pointhacks.com.au/feed/",              board: "PointHacks"}
        - {url: "https://www.australianfrequentflyer.com.au/feed/", board: "AusFrequentFlyer"}
    reddit:
      subreddits: ["AusFinance", "AusFrugal", "fiaustralia", "churning", "LocalLLaMA"]
  onboarding:
    sources:
      ozbargain_tags:
        tags: ["referral", "cashback", "giftcard", "bonus"]
```

⚠️ **The two added subreddits and two added OzBargain tags are unverified.**
Reddit is fetched from CI under 429 pressure (the existing config carries
`max_retries: 5`, `max_backoff_seconds: 120`), and OzBargain tag names could not
be checked from this machine — the local IP is Cloudflare-challenged, so
`/tag/<t>/feed` returned 403 for *every* tag including the two already in
production use. **Verify tag existence from CI before trusting them**; a
non-existent tag must degrade to a logged skip, which `ozbargain_tags.py:58`
already does.

### A2. Shared Python edits

Mostly already specified in `GLOBAL_DEALS_PLAN.md` §1c — do them once, here:

| File | Change |
|---|---|
| `models.py` | `Deal`: add `currency: str = "AUD"` |
| `config.py` | `WatchConfig`: `trusted_sources: list[str] = Field(default_factory=list)` (it is `StrictConfigModel`, so the field must exist before the YAML key) |
| `matching.py` (~186) | the `passes_trusted` bypass — **the single most important line**; without it every keyword hit from a voteless source is silently dropped |
| `state.py` | `due_for_fetch` / `mark_fetched`, plus a **generic** snapshot pair `snapshot(key)` / `set_snapshot(key, value)` rather than the `llm_prices`-specific accessors — B2 and B3 both need one |
| `observations.py` | add `currency` to `build_observation` |
| `notify/render.py:23` | `SOURCE_LABELS` += `dealnews`/`slickdeals`/`v2ex`/`openrouter`/`bank_rates`→"AU Bank Rates"/`iknowthepilot`→"Flight Deals (AU)" |
| `templates/email.html.j2:56` | currency-aware price badge |
| `frontend/app/portal/settings/page.tsx` (~15) | add `digital` to `CATEGORY_OPTIONS` (id must equal the YAML key) |

`state.py` note: the generic accessors keep both snapshots inside
`data/deals_state.json`, which is already in both `actions/cache` path lists in
`hunt.yml` and committed once per AET day. **No workflow change is needed.**
Confirm the file stays sane afterwards — bank rates add ~30KB, LLM prices ~16KB.

### As-built (cross-phase ledger — corrections found after the plan was approved)

**Phase A**, landed as specified, plus two things the plan didn't anticipate:

- **`matching.py` `passes_trusted` bypass** — landed exactly as specified, but
  exposed a latent bug: the existing fallback reason string
  (`f'"{keyword}" matched, {deal.discount_percent:.0f}% off'`) ran whenever
  `passes_votes` was false, including the new trusted-only case where
  `discount_percent` is `None` — `.0f` on `None` raises `TypeError`. Fixed with
  a third branch (plain `'"{keyword}" matched'` when neither votes nor discount
  passed). Covered by `tests/test_matching.py::test_trusted_source_bypasses_*`.
- **`state.py` naive-datetime coercion** — `deals_state.json` is committed to
  `main`, so it's human-touchable, and every `datetime.fromisoformat(...)` call
  in `load()` (six sites: per-deal snapshot `ts`, `first_seen`, `seeded`,
  `site_baseline.seeded_at`, `site_baseline.hours[*].updated_at`, `last_fetch`)
  silently accepts a naive string and returns a naive `datetime` — no
  `ValueError`, so the existing `contextlib.suppress(ValueError)` guards don't
  catch it. A naive value then crashes the first time it's subtracted from a
  tz-aware `now` (e.g. inside `due_for_fetch`). Fixed with one `_aware()` helper
  (mirrors `strategy_hunter/sources/rss.py::_parse_pub_date`'s treatment)
  applied at all six sites, not just `last_fetch`. Covered by
  `tests/test_state.py::test_naive_last_fetch_timestamp_coerced_to_aware_on_load`.
- Everything else — `config/settings.yaml`, `models.py`, `config.py`,
  `observations.py`, `notify/render.py`, `templates/email.html.j2`,
  `frontend/app/portal/settings/page.tsx` — landed with no behavioural delta
  from this doc.

**Phase 3** (`frontend/lib/deals.ts`, GLOBAL_DEALS_PLAN.md), two more plan/code
mismatches found during reconciliation:

- Gate (b) ("still in the latest scan batch") was specified as per-*run* and in
  need of a per-source fix. As-built: `latestTsBySource` was already a
  `Map<string, string>` keyed by source — the batch was always resolved
  per-source. No fix needed, none made; GLOBAL_DEALS_PLAN.md Phase 3 corrected
  in place so it isn't re-implemented.
- **Event-emitting vs re-emitting sources**, a distinction neither plan drew.
  `dealnews`/`slickdeals`/`v2ex`/`iknowthepilot` re-emit every poll (the deal
  persists upstream) and live out the full 72h retention window under the
  batch gate. `openrouter`/`bank_rates` are differs — each emits a Deal exactly
  once, when its diff fires, then never again — so they skip the batch gate and
  rely on the 72h window alone; `frontend/lib/deals.ts` encodes this as
  `EVENT_EMITTING_SOURCES = new Set(['openrouter', 'bank_rates'])`. Recorded
  in GLOBAL_DEALS_PLAN.md Phase 3 as it also bears on `should_notify`, dedup,
  and observation retention for these two sources.

---

## Phase B — source modules (four parallel agents, strict file ownership)

Each agent owns only the files listed. No agent edits a file owned by another.
All four follow `sources/ozbargain.py:69`: `fetch()` does network only, `parse()`
is pure and takes text/dict.

### B1 — `bargain_hunter/sources/feed_deals.py`

Owns: that module, `tests/test_feed_deals.py`, its fixtures.

Implement `GLOBAL_DEALS_PLAN.md` §1a as written (the module body is given there
almost complete), with **one extension**: it serves a fifth instance,
`iknowthepilot`, using the same RSS 2.0 path. Verified 2026-08-20: HTTP 200,
25 items, WordPress RSS. Real sampled titles —

- `Tokyo Time? Jetstar Flights Have Dropped to just $576 return`
- `Newly Opened Beachfront Bali Bliss: 5 Nights + Flights + ... from $919pp`
- `Singapore, Sorted. Direct Flights on 5 Star Singapore Airlines from $609 return`

These are AUD and AU-departure, so `currency: "AUD"` and the normal `$` badge —
unlike the NA/CN feeds. `extract_price_signals` will pick up `$576` from the
title; `posted_at` from `pubDate`.

Confirm the `dealnews:` XML namespace URI against the live feed root before
trusting the constant — `GLOBAL_DEALS_PLAN.md` flags this as unverified.

### B2 — `bargain_hunter/sources/llm_prices.py`

Owns: that module, `tests/test_llm_prices.py`, its fixtures.

Implement `GLOBAL_DEALS_PLAN.md` §1b **plus correction C1 above**. Use the
generic `state.snapshot("llm_prices")` / `set_snapshot` from A2, not the
`llm_prices`-specific accessors written in that document.

Tests must include: ≥10% drop detected; <10% ignored; a new *priced* id ignored;
**a new *zero-priced* id emitted (C1)**; empty previous snapshot yields zero
deals but still seeds; malformed pricing skipped.

### B3 — `bargain_hunter/sources/bank_rates.py` ← the highest-value module

Owns: that module, `tests/test_bank_rates.py`, its fixtures.

**A CamelCamelCamel for every Australian bank product.** Australia's Consumer
Data Right obliges banks to publish product reference data through a public,
unauthenticated API. There is no scraping, no auth, no ToS exposure, and it is
legally required to stay available.

Everything below was verified live on 2026-08-20.

**Endpoints.**

```
list    {base}/cds-au/v1/banking/products
detail  {base}/cds-au/v1/banking/products/{productId}
```

Required headers: `Accept: application/json` **and** `x-v: <version>`.

**Version negotiation is mandatory and per-brand.** Omitting or guessing `x-v`
returns HTTP 406 with a machine-readable body naming the supported versions:

```json
{"errors":[{"code":406,"title":"Unsupported Version",
  "detail":"Value 3 is invalid for the x-v header. Versions available: 4 and 5"}]}
```

Most brands accept `4`; BOQ requires `5`. Start from the configured `x_v`, and
on 406 parse the highest integer out of `detail` and retry **once**. Never
retry-loop.

**Incremental fetch — use it.** `updated-since` works and collapses the daily
cost: on Macquarie, `?page-size=5` reported `totalRecords: 21`, while
`?updated-since=2026-08-01T00:00:00Z&page-size=5` reported `totalRecords: 2`.
`product-category=TRANS_AND_SAVINGS_ACCOUNTS` also filters server-side (21 → 7).
Pass the previous run's timestamp; on the first run omit it and seed silently.

**Detail payload** carries the actual money. Verified on Macquarie Savings:

```json
{"depositRateType": "INTRODUCTORY", "rate": "0.0535", "additionalValue": "P4M",
 "applicationFrequency": "P1M", "calculationFrequency": "P1D",
 "tiers": [{"name": "Variable Welcome rate", "unitOfMeasure": "DOLLAR",
   "minimumValue": 0.0, "applicabilityConditions": {"additionalInfo": "..."}}]}
```

`rate` is a **decimal string** (`"0.0535"` = 5.35%), same trap as OpenRouter's
per-token prices. `depositRateType` ∈ `{FIXED, BONUS, VARIABLE, INTRODUCTORY,
...}`. Products also carry `fees`, `eligibility`, `features`, and a
`lastUpdated` date.

**Behaviour.**

- For each enabled brand, if `state.due_for_fetch("bank_rates", ...)`: list
  products filtered to `product_categories`, then fetch detail **only** for
  products whose `lastUpdated` changed since the snapshot. This keeps a daily
  run to roughly 10 list calls plus a handful of detail calls.
- Snapshot shape: `{f"{brand}:{productId}": {"rates": {...}, "lastUpdated": ...}}`
  via the generic `state.snapshot("bank_rates")`.
- **Skip ids absent from the snapshot** — a newly listed product is not a rate
  rise. Same guard as OpenRouter, and here it is unambiguously right (there is
  no "new product launches at a great rate" case worth the false-positive flood;
  revisit only with observed data).
- Emit a `Deal` when the best rate for a product **rises** by
  `>= min_rate_rise_bps`, or a card's signup points rise by
  `>= min_bonus_points_rise`:
  - `source="bank_rates"`, `deal_id=f"{brand}-{productId}"` (sanitised)
  - `title=f"{brand} {product_name}: {new:.2f}% p.a. (was {old:.2f}%)"`
  - `url` from the product's `additionalInformation` URI when present, else the
    brand site
  - `categories=["Finance", "Banking", "Savings"]`, `currency="AUD"`,
    `price_confidence=None` (a rate is not a price — **must not** render a `$`
    badge), `posted_at=now`
- Always write the snapshot back, including on the first run.
- One brand failing (HTTP error, malformed JSON, unexpected 406) is logged and
  skipped. **Never raise** — this runs inside the 5-minute loop.

**Traps specific to B3.**

1. `price_confidence=None` and `price=None`. A 5.35% rate rendered as `$5.35`
   is worse than not sending it. Check the email template path.
2. `bank_rates` **must** be in `scoring.hot.voteless_sources`, or the AU heat
   baseline is corrupted permanently (`GLOBAL_DEALS_PLAN.md` TRAP 1).
3. `api.anz` is a real hostname with no TLD — do not "fix" it.
4. `CommBank`'s base already ends in `/public`; join paths without doubling.
5. Rates can also **fall**. Only rises are deals. A fall is not an alert.

### B4 — `strategy_hunter/sources/rss.py`

Owns: that module, its registration in `strategy_hunter/collect.py` +
`strategy_hunter/config.py`, `tests/test_strategy_rss.py`, its fixtures.

A generic RSS→`CapturedPost` source. `strategy_hunter` has no generic RSS
reader today — `ozbargain_comments.py` takes a `feed_url` but its parsing is
OzBargain-specific.

Follow `ozbargain_tags.py` closely: it is the nearest shape (config list of
targets → one `CapturedPost` per item, `board=` label, per-target failures
logged and skipped).

Verified feeds:

| Feed | Result | Why it matters |
|---|---|---|
| `pointhacks.com.au/feed/` | 200, RSS 2.0, 12KB | AU credit-card signup bonuses; sampled: `Westpac Altitude Black vs NAB Qantas Signature`, **`This week's gift card offers with Flybuys and Everyday Rewards`** |
| `australianfrequentflyer.com.au/feed/` | 200, 10 items | points redemption; sampled: `Airfare of the Week: Delta Premium Economy BNE–LAX from $2,987` |

That gift-card line is recurring and stackable with `cashback.py`, which is
exactly the unbuilt **P1.2 "stacking alerts — the differentiator"** in
[`IMPROVEMENT_PRD.md`](IMPROVEMENT_PRD.md). This module is the input that
unblocks it; P1.2 itself stays out of scope here.

`secretflying.com` returned **403** and is excluded.

---

## Phase C — integration (two parallel agents)

### C1 — pipeline wiring + digital quota

Owns: `main.py`, `dedup.py`, `subscribers.py`, `models.py` (`Notification.track`),
`tests/test_main.py`.

1. Fetch blocks for all new sources, gated on `state.due_for_fetch`, per
   `GLOBAL_DEALS_PLAN.md` §1c. Import source classes at module level — tests
   monkeypatch them there (`tests/test_main.py:116`).
2. Separate daily quota, per `GLOBAL_DEALS_PLAN.md` Phase 2, with the digital
   source set widened to include `bank_rates` and `iknowthepilot`.
   **Do not miss step 5 there** — the quiet-hours queue drain filters on
   `track in {"hot","mixed"}` and `track != "watch"`, so a third track is
   silently dropped without a third drain block.

### C2 — `/deals` region panels

Owns: `frontend/lib/deals.ts`, `frontend/app/deals/page.tsx`.

⚠️ **Read `frontend/AGENTS.md` and `node_modules/next/dist/docs/` first.** This
is a pre-release Next.js whose APIs differ from training data.

Implement `GLOBAL_DEALS_PLAN.md` Phase 3, with the region map extended:

```ts
const REGION_BY_SOURCE: Record<string, DealRegion> = {
  ozbargain: 'AU', camelcamelcamel: 'AU',
  bank_rates: 'AU', iknowthepilot: 'AU',
  dealnews: 'NA', slickdeals: 'NA',
  v2ex: 'CN', openrouter: 'GLOBAL',
}
```

Both `deals.ts` gates block the new sources and both need the fixes described
there — the `is_hot` requirement (these are watch-track, rarely hot) and the
"latest scan batch" check (these poll daily, so most runs emit no rows and
everything would silently vanish). Resolve the latest batch **per source**.

`bank_rates` and `iknowthepilot` belong in the **Australia** section, but the
existing AU tier logic must stay byte-identical for `ozbargain`/`camelcamelcamel`
— give the new AU sources their own subsection rather than merging them into the
tier ladder.

---

## Deferred, documented (not in this build)

Two lanes worth more than several of the sources above, both deliberately out of
scope here to keep the diff reviewable.

**Lane 3 — the renewal calendar — blocked on design, not merely deferred.**
Every existing lane is "the world changed → alert". The highest-dollar personal
羊毛 is "**my** clock ran out": a subscription auto-renewing at list price, a
VPS renewing at 3× the promo, a domain at 5×, a credit card's fee landing at
month 12 (the churn window), an energy discount period ending. Needs no new
source — but the original sketch (a dated `config/settings.yaml` list) is not
an acceptable home: renewal dates are per-subscriber personal data, this repo
is public, and `AGENTS.md` is explicit that subscriber info lives only in
Notion — public logs never carry subscriber identifiers. The correct home is
the Notion Subscribers DB, which means this lane touches `subscribers.py`
(schema + parsing), not a ~30-line config-driven cron check. Revisit as a
`subscribers.py` change.

**Lane 4 — the one-time sweep.** Money already owed, sitting unclaimed: ATO lost
super, ASIC and state unclaimed-money registers, class-action settlements,
state concession schemes. No feed should exist for this; it is a checklist page
under `/guides`, written once. Highest return per minute in this entire
document, and zero code. Scheme names and amounts change — verify current status
when writing, do not copy figures from here.

**Energy CDR** — the register works (84 retailers, `publicBaseUri` for AGL,
Origin, EnergyAustralia, Alinta, ActewAGL, Momentum), but
`/cds-au/v1/energy/plans` returned **nginx 404** on all three path variants
tried. The endpoint path needs discovery before this is worth specifying.
Do not assume it mirrors banking.

---

## Acceptance (whole plan)

```bash
ruff check . && pytest -q          # settings.yaml feeds BOTH packages — full suite, not a subset
bargain-hunter --dry-run           # per-source fetch counts, no email
strategy-hunter collect            # rss source appears in the corpus
cd frontend && npm run build
```

1. **Heat-baseline no-op proof.** Run `--dry-run` with the new sources disabled,
   note `heat_ratio` and `site_velocity_index`; enable them, re-run on the same
   state, confirm both are unchanged. If they move, a source is missing from
   `voteless_sources`.
2. **The acceptance test for B3** is a fixture-driven rate rise: a saved CDS
   detail payload at 4.90% and a second at 5.35% must produce exactly one Deal
   whose title reads `... 5.35% p.a. (was 4.90%)`, and a 5-basis-point rise must
   produce none.
3. **The acceptance test for C1** is `GLOBAL_DEALS_PLAN.md` Phase 2's: a digital
   deal sends when `remaining_hot == 0` and `remaining_watch == 0` but
   `remaining_digital > 0`, and survives a quiet-hours queue-and-drain round trip.
4. `data/deals_state.json` stays a sane size after both snapshots land.
5. No network in any test. Fixtures flat in `tests/fixtures/`, `httpx.get`
   monkeypatched at the module (`tests/test_strategy_reddit.py:74-88`).

## Rejected, with evidence (do not revisit without new data)

- **NodeSeek** — reachable (200/20 items) but content is predominantly seat
  sharing, region spoofing, and account resale. See C2.
- **linux.do** — 403 on all endpoints; `robots.txt` `ai-train=no`.
- **secretflying.com** — 403.
- **LowEndBox** — 200, but ~397KB/feed and roughly half editorial; only worth
  revisiting if the owner starts self-hosting.
- **Epic free games API** — works cleanly (200, AU pricing, `promotions`
  structure usable), but it is the most widely-publicised freebie in existence;
  near-zero marginal value over simply knowing it exists.
- **GitHub commit Atom for curated free-tier lists** — pattern works
  (`ripienaar/free-for-dev` 200, 20 entries) but `cheahjs/free-llm-api-resources`
  **404s** (renamed or rebranched). Low signal-to-noise; skip.

## Verification provenance

Probes run 2026-08-20 from a Melbourne residential IP. Two caveats recorded
honestly:

- **OzBargain returned 403 (Cloudflare "Just a moment...") to this machine** on
  `/deals/feed`, `/tag/*/feed` and `/cat/*/feed`. This is **not** a production
  outage — `data/observations/2026-08-20.jsonl` shows 8,090 `ozbargain` rows with
  the newest at `12:20:44Z`. Local-IP challenge only. It does mean no OzBargain
  sub-feed could be verified from here; do it from CI.
- Energy CDR plans endpoint unresolved, as noted above.
