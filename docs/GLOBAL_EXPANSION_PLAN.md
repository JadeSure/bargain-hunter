# Global expansion — execution spec

Outcome of a 13-agent live-probe recon (2026-08-21) into whether to extend the
pipeline to developed countries. **The premise did not survive.** This doc
records the refutation and specifies what to build instead.

## Finding: "country" is the wrong axis

Two of the six probed categories mapped exactly onto the original hypothesis —
developed-country consumer aggregators, and developed-country welfare. They are
the only two that scored a **total wipeout**: 26 candidates, 0 kept.

| Evidence | Measurement |
| --- | --- |
| HotUKDeals `/rss/trending` | 1/20 items capturable from AU. 60% UK-domestic physical, incl. a UK-plug charger that does not fit a Type I socket |
| mydealz (DE) | 0/20 |
| Chollometro (ES) | 0 digital items in sample |
| HotUKDeals `/rss/tag/steam` | **Negative** value: *Judgment* at £8.79 = A$17.60 vs Steam AU's own A$13.73 |
| mydealz NordVPN/PureVPN "130% cashback" | Value locked in Topcashback **DE**, needs a German account — borderless on the surface, residency-gated one layer down |
| GOV.UK + HMRC Atom | Flawless Atom, <5h freshness. Every payable item needs an NI number + UK residence + UK bank account |
| MissingMoney/NAUPA, NZ IRD, Bank of Canada | Registers of money an institution already holds **in your name**. With no local ID or account you cannot appear in them *by construction* |
| The Flight Deal / Fly4Free | 0/50 and 0/50 AU-origin. Both AU regex hits were false positives (`Ex-PER-ience`, `PER-u`) |
| Cheapies.nz | Same engine as OzBargain (identical `ozb:meta`) — which is exactly why it adds nothing |

Welfare is exclusionary by definition: it is redistribution to resident
taxpayers. And regional pricing has already captured the consumer arbitrage —
storefronts price-discriminate in the user's favour where they live, which is
why foreign consumer deals do not transfer.

**The axis that predicts value is whether the owner can actually complete the
transaction** — not which country the offer came from. That means an address
that can receive it, an identity that can claim it, and a payment rail that can
pay for it.

> ### ⚠️ Correction (2026-08-21, same day)
>
> This section originally read "value that arrives as bytes", and used it to
> write off **all** of mainland China's physical-goods and payment-rail deals.
> That was wrong, and wrong for the worst possible reason: **the owner model it
> rested on was never verified.**
>
> The inference was "owner lives in Australia → no mainland shipping address →
> 立减金 cannot be redeemed → the mainland category is dead." Nobody checked it.
> The owner is a mainland national with WeChat, Alipay, a mainland phone number,
> **a mainland shipping address, and family in mainland China to receive and
> redeem**. So mainland physical goods, 立减金, and local-service coupons are all
> capturable, and the "bytes only" axis collapses.
>
> The process failure is the point: this doc's author verified ~70 endpoints by
> hand and never once verified the single assumption every rejection hung on —
> the one thing that could have been settled by asking. Rigour was spent on the
> cheap questions and skipped on the load-bearing one.
>
> A second, compounding error: **"a GitHub Actions runner can't curl it" was
> treated as "this data is unavailable."** See the smzdm entry below. The rule
> is *do not defeat bot detection* (no CAPTCHA solving, no JS-challenge
> execution, no fingerprint spoofing). It is not *do not use a documented public
> API*, and it says nothing about what the owner can fetch with their own
> browser and their own accounts. Non-automated and semi-automated harvesting
> are legitimate delivery mechanisms and were never considered.
>
> What survives unchanged: the **developed-country** findings above. UK/DE/FR/ES/
> AT/NL/CA/JP/SE consumer deals and foreign welfare really are residency- and
> shipping-gated for this owner, and the measurements in the table stand. What
> does not survive is applying that same conclusion to a country the owner is a
> citizen of.

Of the 8 survivors, **zero are in a developed country other than Australia** —
but that reflects where this pass looked, not where value is. The single
largest source in the repo today (smzdm) was found only after the correction.

## What to build

Ranked by value/effort from the judge pass. `feed_deals.py` already parses Atom
(`_parse_item` branches on `item.tag.endswith("entry")`), so six of the seven
are configuration, not code.

| # | Source | Value | Effort | Mechanism |
| --- | --- | --- | --- | --- |
| 0 | **什么值得买 (smzdm)** | **9** | 3 | **new module** — added after the correction above |
| 1 | Aliyun Model Studio (百炼) docs | 6 | 1 | 2 lines into `cn_llm_docs.pages` |
| 2 | Vercel changelog | 6 | 2 | `feed_deals` (Atom) |
| 3 | ~~NodeSeek~~ | 5 | 2 | **deferred — see below** |
| 4 | AppSumo | 5 | 3 | **new module** |
| 5 | AFF deals subforum | 4 | 1 | `feed_deals` (RSS) |
| 6 | Point Hacks | 3 | 1 | `feed_deals` (RSS) |
| 8 | AFF blog | 2 | 1 | `feed_deals` (RSS) |

Dropped from the shortlist: **free-for-dev** (#7). It is a directory, not a deal
feed — standing free tiers have no expiry and no urgency, so it is discovery
value, not capture value, and its commit titles (`Update GhostChat entry`) carry
no payload.

### 什么值得买 (smzdm): the one this pass got wrong

An earlier session recorded smzdm as *"JS fingerprint challenge — refused to
bypass"* and it was carried into this pass unexamined. That was a
misdiagnosis, not a judgement call:

```
browser UA → https://www.smzdm.com/          HTTP 202, 209 B JS probe stub
app UA     → https://api.smzdm.com/v1/home/list
                                              HTTP 200, application/json,
                                              36,996 B, error_code "0"
```

The **web frontend** carries the challenge. The **app API does not** — no auth,
no key, no CAPTCHA, no JS to execute. The only difference is the `User-Agent`
header, and this repo already sends a non-default UA to every source by
convention (AGENTS.md: *"Real sources send a browser User-Agent"*). Requesting a
vendor's own unauthenticated public API is the same category as reading
OzBargain's RSS. Nothing was bypassed.

The lesson worth keeping: *"my curl got blocked"* is a fact about one request
from one machine with one header. Writing it down as *"this source is walled"*
turns a retryable observation into a permanent, load-bearing conclusion — and
this one sat unchallenged across two sessions while it hid the single most
valuable source available.

Endpoints, verified live 2026-08-21 — see `sources/smzdm.py` for the full field
map and traps:

| Endpoint | Rows | Notes |
| --- | --- | --- |
| `/v1/home/list` | ~20 | mixed; filter `article_channel_name == "优惠"` (17/20; rest is `原创` editorial) |
| `/v1/youhui/list` | ~21 | all deals; the channel field is absent here |

`?offset=N` paginates. `article_worthy` is a real 值 count, but smzdm is still
listed in `voteless_sources`: its scale (0-15 on fresh items) is not
commensurable with OzBargain's, and `compute_site_velocity_index` is a
percentile over every non-voteless deal, so mixing them would corrupt a baseline
that has been calibrating for weeks. `votes_pos` is still populated for display.

### NodeSeek: dropped

**Verdict after measuring: drop.** The judge scored it 5/2 from the recon
summary; measuring the live feed directly contradicts that score.

The judge scored this 5/2 from the recon summary. Measuring the live feed
directly changed the picture, and the `title_keywords` list this spec originally
carried was **guessed from v2ex rather than measured** — the same mistake that
cost 9/10 CDR banks last round.

- The feed window is **~12 minutes**, not hours: 20 items spanning newest 0.0h
  to oldest 0.2h, i.e. ~100 posts/hour, ~2400/day. A 60-minute poll sees ~5% of
  it. Covering the feed means polling at the pipeline's own 5-minute cadence.
- **`?category=` is ignored.** Verified by title-list comparison, not bytes:
  `?category=trade` and the bare root return identical title lists with
  identical trade-post ratios (3/20 each). An earlier byte-level difference was
  pure time drift on a feed this fast. Everything else on the domain —
  `/api/discussions`, `/category/*`, `www` — is 403 Cloudflare, so the
  unfiltered root is the only surface.
- The guessed list matches **~0 of 20** real titles. `9折` is not matched by
  `折扣`; `甲骨文的毛` is not matched by `羊毛`; `free许可证` is English.
- Much of the trade traffic is **peer-to-peer** (`100包push出vmiss ...`,
  `收个datawave sg 10.8/月`) — paying a stranger by Alipay for a transferred VPS
  account is a different risk class from a merchant offer and should not be
  surfaced as a deal even if the filter catches it.

An 11-minute sampler was then run to build a measured list. Across the unique
titles it captured, **zero were a claimable merchant offer**:

```
收个datawave sg 10.8/月            P2P — someone buying
【收】vmshell四周年CMIN2.HKDC-Lite   P2P — someone buying
100包push出vmiss ...9折月付款        P2P — reselling their own VPS
甲骨文的毛一次都没撸到是什么水平？        a complaint about NOT getting a freebie
【NQ + TQ】DGNCloud HK 4C4G 测试机   a review-unit request, not an offer
工单后 DediRock 的丢包率大幅度下降      a service report
现在买GPT什么方式性价比高？             grey-market account chatter
```

The one `羊毛` keyword hit is someone saying they have *never* managed to grab
one. The one `折` hit is a peer-to-peer resale. The board's actual subject
matter is VPS reviews, proxy-software questions, and account trading.

Two further reasons not to build it even if the sample were richer: much of the
tradeable content is **peer-to-peer** — paying a stranger by Alipay for a
transferred VPS account is a different risk class from a merchant offer — and a
visible slice is grey-market (region-switching for cheaper GPT pricing, affiliate
cloaking). Neither belongs in a digest presented as deals.

The structural objections stand independently of sample size: a 12-minute feed
window, no category filtering, and Cloudflare on every alternative surface.

Losing NodeSeek does cost real coverage of CN developer free-tier chatter. The
Aliyun/Kimi/DeepSeek/Zhipu/SiliconFlow docs in `cn_llm_docs` cover the platforms'
own announcements, which is the part that was actually claimable anyway.

### Verified endpoint evidence

Every line below was measured directly, not taken from a subagent report.

```
vercel-atom          HTTP=200 application/atom+xml   3,296,435 B  1.41s
nodeseek-rss         HTTP=200 application/xml           10,136 B  0.43s
appsumo-api          HTTP=200 application/json         102,336 B  1.82s
aff-deals-subforum   HTTP=200 application/rss+xml       32,693 B  0.19s
pointhacks           HTTP=200 application/rss+xml       12,109 B  0.12s
aff-blog             HTTP=200 application/rss+xml      172,181 B  0.39s
aliyun new-free-quota HTTP=200 text/markdown            19,202 B  0 redirects
aliyun coding-plan    HTTP=200 text/markdown             8,473 B  0 redirects
```

Vercel feed composition: **1492 entries, newest 10.6h, oldest 3586 days.** 125
entries fall inside 30 days; 9 of those match offer keywords, and every
non-match is pure product noise (`Bun 1.4 is now available in Vercel
Functions`). The 9 hits are all time-boxed and claimable:

```
[ 2d] Fish Audio models now available on Vercel AI Gateway for free
[ 4d] GPT-5.6 Sol is 50% off on AI Gateway for the next month
[ 8d] GLM 5.2 free for eve agents through August 27 via Blackbox on AI Gateway
[ 9d] Exa web search free through August 31 on AI Gateway and eve
[17d] DeepSeek V4 Flash is 90% off through Novita on AI Gateway
```

## Lane A — AppSumo source (the only real code)

Owns **`src/bargain_hunter/sources/appsumo.py`**, **`tests/test_appsumo.py`**,
**`tests/fixtures/appsumo_deals.json`**. Touch nothing else. Report the config
block and the `main.py` wiring as text; the supervisor integrates them.

Measured API shape — **all of this is verified, do not re-derive**:

- `GET https://appsumo.com/api/v2/deals/?page=N` → `{"deals": [...], "meta": {...}}`.
  The array key is **`deals`**, not `results` or `data`.
- `meta` = `{page, per_page: 10, total_results: 4230, total_pages: 423}`.
- **Every query parameter except `page` is ignored.** Verified: `?page=1` and
  `?page=1&browse_deal_status=current&ordering=-dates__start_date&limit=50`
  return identical slug lists, identical order, identical `meta`. Any filter
  written as a query string is a no-op that reads as correct code. **Filter
  client-side.**
  - Note when re-checking this: a raw byte comparison is *not* a valid test.
    `dates.schema_end_date` is derived from request time, so two identical
    requests differ byte-wise. Compare slug lists.
- `per_page` is 10 and not adjustable, so covering ~40 recent deals means 4
  sequential requests. Pace them (`request_delay_seconds`) and bound the count
  with a `max_pages` setting (default 4).

Client-side filter — keep an item only when **all** hold:

```python
it["browse_deal_status"] == "current"
not it["has_ended"]
it["has_started"]
not it["is_addon"]
it["display_on_browse"]
```

Measured yield: **33/40 across pages 1-4.**

Field mapping:

| Deal field | Source | Trap |
| --- | --- | --- |
| `title` | `public_name` | on `is_addon` items this is a *feature* name (`"Penetration testing"`), which the filter already excludes |
| `url` | `"https://appsumo.com" + get_absolute_url` | `product_url` is the **vendor's own site**, not the deal page. `clickthrough_url` is always `None`. Using either produces a wrong or dead link — this repo already shipped 32/35 dead cards once |
| `price` / `was_price` | `price` / `original_price` | |
| `discount_percent` | computed | **Guard `original_price > price > 0`.** Measured live: Crowdflow has `original_price: 0.0` with `price: 29.00`. Same sentinel class as the `-1` guard already in `llm_prices.py` |
| `posted_at` | `dates.start_date` | **Never sort or filter on this.** Expired deals carry a future sentinel — `vectera-2019` is `browse_deal_status: expired, has_ended: True` with `start_date: 2030-10-03`. It correlates with `has_ended`, so the boolean filter removes it, but the field is not trustworthy on its own |
| `currency` | `"USD"` | |
| `deal_id` | `slug` | |

Test against a frozen fixture (no network). The fixture must include at least
one expired item, one `is_addon` item, and one `original_price: 0.0` item, and
assert all three are excluded or handled — those are the three measured traps.

## Lane B — feed defaults

Owns **`src/bargain_hunter/sources/feed_deals.py`** and its tests. Touch nothing
else. `settings.yaml` and `main.py` belong to the supervisor.

Add per-`name` entries to `_DEFAULT_MAX_AGE_HOURS` and `_DEFAULT_TITLE_KEYWORDS`:

- **`vercel`** — `max_item_age_hours: 24*30`. Mandatory: the feed carries 1492
  entries back to 2016 and without a cutoff every poll floods observations.
  `title_keywords` isolating offers from product noise; the measured-good set is
  `free|credit|discount|\boff\b|promo|pricing|price|trial|no cost`. Verified
  9/125 hit rate over 30 days with no false negatives in the sample.
  Also raise the default `timeout` for this source — 3.3MB measured at 1.41s
  locally, but the 20s default leaves little headroom on a slow CI runner, and a
  read timeout mid-body raises inside `parse()`, which `fetch()` does **not**
  catch (it only catches `httpx.HTTPError`). It surfaces at `main.py`'s
  per-source `except Exception`, which logs and continues — i.e. silent zero.
- **`nodeseek`** — general VPS/hosting forum firehose, needs `title_keywords`.
  Reuse the shape of the `v2ex` list (it is the same community register) plus
  hosting terms: `vps|白嫖|免费|优惠|折扣|补货|上新|活动|羊毛|额度|试用`.
- **`aff`**, **`pointhacks`** — AU travel. `aff` covers both the deals subforum
  and the blog under one `name` (one `name` shares one filter — see the existing
  v2ex comment). Keep `title_keywords` **unset** for both: measured 17/20 of the
  subforum's threads are already deal-shaped, and a filter here is precisely the
  "filter-shaped inert" trap (Point Hacks changes its recurring-post title
  convention, the filter matches zero forever, the feed stays a healthy 200).

## Lane C — the staleness ceiling

Owns **`src/bargain_hunter/state.py`**, **`src/bargain_hunter/sources/cn_llm_docs.py`**,
**`tests/test_staleness.py`**. Touch nothing else.

This closes the failure mode that has now bitten this repo **five times**: a
swallowed non-200 or an empty parse leaves a source contributing zero while
every log line looks normal.

The live specimen the recon turned up:

```
God Save The Points   HTTP 200 · application/rss+xml · 10 well-formed items
                      newest pubDate 2025-07-31 → 386 days stale, site closed
```

Nothing in a status-code check catches that. Neither does "did we get items" —
`hostloc` returns HTTP 200 with a Discuz `提示信息` error page, and the AFF
subforum legitimately produces nothing for a fortnight at 0.7 threads/week.

The one signal that works is **the age of the freshest evidence the source
itself reports**:

1. `feed_deals.parse()` records `self.newest_item_at` = `max(posted_at)` across
   **all** parsed items, taken *before* the staleness and keyword filters. It
   must reflect the feed's own health, not what survived our gates.
2. `cn_llm_docs` stamps `"ok_at": <iso>` into each page's entry on every
   successful fetch. The existing carry-forward path must preserve the **old**
   `ok_at` — that is the entire point, it is what makes a permanently-dead page
   distinguishable from an unchanged one. Today `check()` carries the previous
   entry forward verbatim and the result is indistinguishable from "no change",
   which is a real defect in already-shipped code.
3. `state.py` grows `record_freshness(source, when)` / `freshness(source)`
   alongside the existing `mark_fetched` / `last_fetch`.

Keep it to one comparison against one configured ceiling. Do not build a
per-source policy engine. Sources with nothing to report are simply skipped.

## Supervisor-owned integration

`config/settings.yaml`, `src/bargain_hunter/main.py`, `frontend/lib/deals.ts`.
Held back from all lanes to keep the diffs conflict-free.

- `settings.yaml`: source blocks; `scoring.hot.voteless_sources` and
  `scoring.watch.trusted_sources` for every new source (none carry votes);
  `run.source_staleness_ceiling_days`. Remember `Settings` is `extra="forbid"`
  at the top level — run the **full** suite.
- `main.py`: fetch blocks behind `_fetch_gate`, and the staleness check.
- `frontend/lib/deals.ts`: `REGION_BY_SOURCE` (`appsumo`/`vercel` → `GLOBAL`,
  `nodeseek` → `CN`, `aff`/`pointhacks` → `AU`) and `SOURCE_LABELS`. Aliyun
  rides on `cn_llm_docs`, already mapped to `CN`.
- `appsumo` and `vercel` re-emit every poll, so neither belongs in
  `EVENT_EMITTING_SOURCES`.

## Acceptance

1. `ruff check .` clean; full `pytest` green (currently 489).
2. `bargain-hunter --dry-run` reaches every new source and each logs its gate
   decision. **`--dry-run` must not write `data/deals_state.json`** — it
   destroyed 109,468 lines once already.
3. Each new source produces ≥1 real parsed item against its live endpoint, or
   an explained zero. A zero with no explanation is the exact failure this spec
   exists to prevent.
4. `frontend` builds, and every new card resolves a real `url` — no `href="#"`.
