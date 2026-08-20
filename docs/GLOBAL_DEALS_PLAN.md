# Global digital deals — execution plan (NA + mainland China)

Status: approved, not started. Written 2026-08-18.
Companion research: all endpoints below were fetched and verified live on
2026-08-18 from an AU IP. Re-verify before trusting any of them.

Execute phases in order. Each phase is independently shippable and has its own
acceptance check. Do not start Phase 1 before finishing Phase 0.

---

## 0. Why this exists, and why the trigger deal was missed

The pipeline only watches AU sources (`ozbargain`, `camelcamelcamel`). The owner
missed a discounted Grok/xAI plan offered in North America. Goal: add NA +
mainland-CN coverage restricted to **virtual/digital goods purchasable from
Melbourne** (AI subscriptions, LLM token/API price cuts, SaaS, cloud credits, dev
tools, VPN, storage). Not physical retail. Scope chosen: **all digital goods**.
Also wanted: NA / China panels on the `/deals` web UI, and a **separate daily
alert quota** for these deals.

### The awkward part: it was already in reach

`ozbargain.com.au/node/963354` — "SuperGrok US$9.90/Month (~A$14, Was US$30),
SuperGrok Heavy US$99/Month (~A$141, Was US$300) for First 3 Months @ xAI Grok",
posted **13/06/2026 15:26 AEST**, **16,536 votes**. The existing OzBargain feed
carried it. On a 2-minute poll it should have been classified `top` within
minutes. So the miss is a **routing/config failure, not a sourcing failure**.

Cannot be proven post-hoc: `data/observations/` only starts 2026-07-04, so
13 June is out of range.

The three candidate root causes, in likelihood order — **check all three before
writing code**:

1. **No matching watch keyword.** Watch is the only track that fires on
   "something I specifically care about". If the Notion `Watch Keywords` cell had
   no AI term, the watch track could not fire.
2. **Category routing suppressed the hot track.** `main.py::_hot_level_eligible`
   drops an out-of-category deal unless it is tier `top` and
   `scoring.hot.universal_top` is true. A subscriber with `Categories` set to
   e.g. `electronics, home` receives *nothing* software-related below `top`,
   because there is **no `digital`/software bucket in the `categories:` taxonomy
   at all** (`config/settings.yaml:141-160` — electronics/home/fashion/sports/
   toys/beauty/food/travel only). A software deal matches no bucket, so it is
   permanently out-of-category for every category-restricted subscriber. **This
   is a real, present bug affecting all software deals, not just Grok.**
3. **`min_hot_level` floor**, or the pipeline was not yet running/subscribed on
   13 June.

Diagnostic commands (run these first, they are cheap):

```bash
# Was 963354 ever observed at all? (only proves 2026-07-04 onward)
grep -rl "ozbargain:963354" data/observations/ | head
grep -rh "ozbargain:963354" data/observations/ | python3 -c "
import sys,json
for l in sys.stdin:
    r=json.loads(l); print(r['ts'], r.get('is_hot'), r.get('level'), r.get('votes_pos'), r.get('hot_score'))
" | head -20

# What do software-ish deals look like in the log, and do they carry categories?
grep -rh -i "grok\|subscription\|vpn\|software" data/observations/ | python3 -c "
import sys,json
for l in sys.stdin:
    r=json.loads(l)
    print(r['deal_key'], '|', r['title'][:70], '| hot=', r.get('is_hot'), r.get('level'))
" | sort -u | head -30
```

Then, in Notion Subscribers, read the row and record: `Watch Keywords`,
`Categories`, `Hot Level`, `Subscribe Hot Deals`, `Max Alerts/Day`. Write the
answer into this file under "Findings" before proceeding.

---

## Phase 0 — config only, zero code

Fixes root cause #2 for every software deal, not just AI ones.

1. `config/settings.yaml`, append to the `categories:` map (currently ends at the
   `travel:` bucket, ~line 159). `Settings.categories` is
   `dict[str, list[str]] | None` (`src/bargain_hunter/config.py:238`) so no code
   change is needed. `categories.py` matches these terms word-boundary,
   case-insensitively, against `Deal.categories` first and falls back to
   title+description. OzBargain's feed already emits `<category>` tags that the
   parser stores (`sources/ozbargain.py:119,129`).

```yaml
  digital:     ["Software", "Internet", "Subscription", "Streaming", "Cloud",
                "VPN", "Antivirus", "Domain", "Web Hosting", "Mobile Plan",
                "Steam", "PC Game", "eBook", "Online Course", "AI", "SaaS",
                "Credit", "API"]
```

2. `frontend/app/portal/settings/page.tsx` — add `digital` to `CATEGORY_OPTIONS`
   (~line 15, ids must match the YAML keys exactly) so it is selectable.

3. Notion Subscribers row — add `digital` to `Categories`, and add these
   `Watch Keywords` (newline-separated):
   `SuperGrok`, `Grok Heavy`, `xAI`, `OpenRouter`, `Claude Max`, `ChatGPT Pro`,
   `Perplexity Pro`, `Cursor`.
   **Do not add bare `grok`.** The pipeline already logged
   `camelcamelcamel:1617296201` "Grokking Simplicity: Taming Complex Software
   with Functional Thinking" — the exact false positive a bare keyword produces.

**Acceptance:** `pytest tests/test_categories.py tests/test_hot_routing.py -q`
passes, and a hand-built `Deal(categories=["Software"])` returns True from
`categories.deal_matches_categories(deal, ["digital"], taxonomy)`.

**Commit:** `feat(config): add digital category bucket for software/AI deals`

---

## Phase 1 — the four new sources

| name | endpoint | region | mechanism |
|---|---|---|---|
| `dealnews` | `https://www.dealnews.com/c124/Computers/Software/?rss=1` | NA | watch |
| `slickdeals` | `https://slickdeals.net/newsearch.php?rss=1&q=<term>&searcharea=deals&searchin=first` | NA | watch |
| `v2ex` | `https://www.v2ex.com/feed/deals.xml` | CN | watch |
| `openrouter` | `https://openrouter.ai/api/v1/models` | GLOBAL | price diff |

Verified field inventories:
- **dealnews**: RSS 2.0 + namespaced `dealnews:price` (has a currency attribute),
  `dealnews:expires`, `dealnews:category`, `dealnews:retailer`,
  `dealnews:dealType`, `dealnews:staffPick`, `media:content`, `pubDate`.
  **No votes, no comments, no was-price, no discount percent.** 7 of 8 sampled
  items were genuinely VPN / cloud storage / security / lifetime SaaS / Office.
  robots.txt: 2s crawl-delay, nothing relevant disallowed.
- **slickdeals**: RSS 2.0, only `title`, `link`, `description`,
  `content:encoded`, `pubDate`, `category`, `dc:creator`, `guid`. `ttl=5`.
  Thumb Score exists **only as plain text inside the `content:encoded` HTML
  blob** — do not try to parse it as a field. `q=grok` returned "SuperGrok Annual
  Plan bundled with X Premium+ $197.5" (29 Dec 2025) — the NA-exclusive variant
  that never reached OzBargain. This is the single source that justifies the
  feature. `q=grok` also returns noise ("List of FREE Kindle Books",
  "Grokit VR digital download $3"), so keyword collision is real.
  Use `searchin=first`. **Never** use `mode=frontpage` (90-95% physical retail).
- **v2ex**: Atom (`entry`/`title`/`link href`/`published`/`content`). 50 entries
  spanning 2026-06-02..2026-08-08, ~0.7 items/day, newest sample 10 days old.
  Content is largely 羊毛 requiring 支付宝. Thin but it is the only mainland
  source that survived verification.
- **openrouter**: `{"data":[{"id","name","pricing":{"prompt","completion",
  "request","image","input_cache_read"},...}]}`. 413 models, ~678KB, prices are
  per-token USD **decimal strings**. Multiply by 1e6 for per-million display.

### 1a. `src/bargain_hunter/sources/feed_deals.py` (new)

One class serving `dealnews`, `slickdeals`, `v2ex`. Instance-level `name`
overrides the class attribute so one module yields three distinct `Deal.source`
values. Follow `sources/ozbargain.py:69` exactly: `fetch()` does network only,
`parse()` is pure and takes text.

```python
"""Generic digital-deal feed source (RSS 2.0 + Atom), config-driven.

Serves DealNews (NA software category), Slickdeals (keyword-scoped search) and
V2EX (优惠信息). These feeds carry no vote or comment signal, so they reach a
subscriber through the watch track (see scoring.hot.voteless_sources and
scoring.watch.trusted_sources) rather than the hot ladder.
"""
from __future__ import annotations

import contextlib
import hashlib
import html
import logging
import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from defusedxml import ElementTree as ET

from ..models import Deal
from ..scoring import extract_price_signals
from .base import Source

log = logging.getLogger(__name__)

_ATOM = "http://www.w3.org/2005/Atom"
_DEALNEWS = "http://dealnews.com/rss/"      # CONFIRM against the live feed's xmlns
_TAG_RE = re.compile(r"<[^>]+>")
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _strip_html(raw: str, max_len: int = 2000) -> str:
    return html.unescape(_TAG_RE.sub(" ", raw or "")).strip()[:max_len]


class FeedDealsSource(Source):
    def __init__(
        self,
        name: str,
        feed_urls: list[str],
        *,
        currency: str = "USD",
        block_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        request_delay_seconds: float = 2.0,
        timeout: float = 20.0,
    ) -> None:
        self.name = name
        self.feed_urls = feed_urls
        self.currency = currency
        self._block = [re.compile(p, re.IGNORECASE) for p in (block_patterns or [])]
        self._allow = [re.compile(p, re.IGNORECASE) for p in (allow_patterns or [])]
        self.request_delay_seconds = request_delay_seconds
        self.timeout = timeout

    def fetch(self) -> list[Deal]:
        deals: dict[str, Deal] = {}          # de-dupe across queries by Deal.key
        for i, url in enumerate(self.feed_urls):
            if i:
                time.sleep(self.request_delay_seconds)
            try:
                resp = httpx.get(
                    url,
                    headers={"User-Agent": BROWSER_UA},
                    timeout=self.timeout,
                    follow_redirects=True,
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                # One dead feed (Slickdeals 403s readily) must not sink the run.
                log.warning("%s: skipping feed %s — %s", self.name, url, exc)
                continue
            for deal in self.parse(resp.text):
                deals.setdefault(deal.key, deal)
        return list(deals.values())

    def parse(self, xml: str, now: datetime | None = None) -> list[Deal]:
        now = now or datetime.now(UTC)
        root = ET.fromstring(xml)
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else root.findall(f"{{{_ATOM}}}entry")
        out: list[Deal] = []
        for item in items:
            deal = self._parse_item(item, now)
            if deal is not None:
                out.append(deal)
        return out

    def _parse_item(self, item, now: datetime) -> Deal | None:
        atom = item.tag.endswith("entry")
        if atom:
            title = (item.findtext(f"{{{_ATOM}}}title") or "").strip()
            link_el = item.find(f"{{{_ATOM}}}link")
            url = (link_el.get("href") if link_el is not None else "") or ""
            raw_body = item.findtext(f"{{{_ATOM}}}content") or item.findtext(f"{{{_ATOM}}}summary") or ""
            ts_text = item.findtext(f"{{{_ATOM}}}published") or item.findtext(f"{{{_ATOM}}}updated")
            guid = item.findtext(f"{{{_ATOM}}}id") or url
        else:
            title = (item.findtext("title") or "").strip()
            url = (item.findtext("link") or "").strip()
            raw_body = item.findtext("description") or ""
            ts_text = item.findtext("pubDate")
            guid = item.findtext("guid") or url

        if not title or not url:
            return None
        description = _strip_html(raw_body)
        if self._region_locked(f"{title}\n{description}"):
            # Logged, not silent — the pattern list needs tuning against misfires.
            log.info("%s: dropped region-locked item: %s", self.name, title[:90])
            return None

        posted_at = self._parse_ts(ts_text)
        price, was_price, discount_pct = extract_price_signals(title)
        currency = self.currency
        # DealNews gives a structured price; prefer it over the title regex.
        dn_price = item.find(f"{{{_DEALNEWS}}}price")
        if dn_price is not None and (dn_price.text or "").strip():
            with contextlib.suppress(TypeError, ValueError):
                price = float(dn_price.text.strip().lstrip("$"))
                currency = dn_price.get("currency") or currency
        expiry = self._parse_ts((item.findtext(f"{{{_DEALNEWS}}}expires") or "").strip() or None)
        categories = [
            (c.text or "").strip()
            for c in item.findall("category") + item.findall(f"{{{_DEALNEWS}}}category")
            if (c.text or "").strip()
        ]

        return Deal(
            source=self.name,
            deal_id=hashlib.sha1(guid.encode()).hexdigest()[:16],
            title=title,
            url=url,
            description=description or None,
            categories=categories,
            posted_at=posted_at,
            expiry=expiry,
            # price MUST be set here or scoring.enrich_deal overwrites
            # discount_percent — see TRAP 2.
            price=price,
            was_price=was_price,
            discount_percent=discount_pct,
            price_confidence=None,      # suppresses the "$" badge; currency is not AUD
            currency=currency,
        )

    def _region_locked(self, text: str) -> bool:
        if any(p.search(text) for p in self._allow):
            return False
        return any(p.search(text) for p in self._block)

    @staticmethod
    def _parse_ts(text: str | None) -> datetime | None:
        if not text:
            return None
        with contextlib.suppress(Exception):
            return parsedate_to_datetime(text).astimezone(UTC)     # RFC 822 (RSS)
        with contextlib.suppress(Exception):
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
        return None
```

Notes for the implementer:
- **Confirm the `dealnews:` namespace URI** from the live feed's root element
  before trusting `_DEALNEWS`. `curl -s '<dealnews url>' | head -5`.
- `price_confidence=None` is deliberate: `Deal` has no per-currency rendering in
  the email until Phase 1c, and a bare `$` on a USD price misleads an AU reader.
- Return `Deal` objects even when `price is None`; the watch track does not need
  a price once `trusted_sources` is in place.
- Ruff `DTZ` forbids naive datetimes. Every datetime above is tz-aware.

### 1b. `src/bargain_hunter/sources/llm_prices.py` (new)

```python
"""OpenRouter token-price differ: a CamelCamelCamel for LLM APIs.

Compares the current per-token price of every model against the snapshot from the
previous run (stored in the existing StateStore, so it rides the Actions cache and
the daily deals_state.json commit for free) and emits one Deal per model whose
price fell by at least `min_drop_percent`.
"""
```

Behaviour, exactly:
- `GET https://openrouter.ai/api/v1/models`, browser UA, 20s timeout. Non-200 →
  log and return `[]`. Never raise; the endpoint is an unsanctioned convenience
  with no published rate limit or SLA.
- Build `current = {id: (float(prompt), float(completion))}` from
  `pricing.prompt` / `pricing.completion`. Skip entries whose pricing is missing
  or unparseable.
- Compare against `previous = state.llm_prices()`. For each id:
  - **Skip ids absent from `previous`** — dated variants
    (`deepseek/deepseek-v4-pro-0813`) mean a cheap *new* id is a new model, not a
    price cut. Getting this wrong produces a flood on every model launch.
  - Compute `drop = (old_prompt - new_prompt) / old_prompt * 100` on the prompt
    price; require `>= min_drop_percent` (config, default 10.0) and `old > 0`.
  - Optional `model_allowlist` (config, list of substrings). Empty = all.
    `~`-prefixed floating aliases (`~x-ai/grok-latest`) are the best targets
    because they track what a user actually pays — put them in the allowlist first.
- Emit one `Deal` per drop:
  - `source="openrouter"`, `deal_id=<model id with "/" and "~" replaced by "-">`
  - `title=f"{name}: input US${new*1e6:.2f}/M tokens (was US${old*1e6:.2f}) — {drop:.0f}% cheaper"`
  - `url=f"https://openrouter.ai/{model_id}"`
  - `price=new*1e6`, `was_price=old*1e6`, `discount_percent=round(drop,1)`,
    `currency="USD"`, `price_confidence=None`, `posted_at=now`
  - `categories=["AI", "API", "Software"]` so the `digital` bucket matches
- Always write `current` back via `state.set_llm_prices(current)`, including on
  the first run (no snapshot → zero alerts, snapshot seeded).

### 1c. Edits to existing files

| File | Change |
|---|---|
| `src/bargain_hunter/config.py` | `WatchConfig`: add `trusted_sources: list[str] = Field(default_factory=list)`. `WatchConfig` is `StrictConfigModel` (`extra="forbid"`) so the field must exist before the YAML key. |
| `src/bargain_hunter/models.py` | `Deal`: add `currency: str = "AUD"` (keeps every existing source and every persisted row valid). |
| `src/bargain_hunter/matching.py` (~line 186) | see below — **not optional** |
| `src/bargain_hunter/state.py` | add `last_fetch` + `llm_prices` accessors — see below |
| `src/bargain_hunter/main.py` (~86-110) | two fetch blocks — see below |
| `src/bargain_hunter/notify/render.py:23` | `SOURCE_LABELS` += `{"dealnews": "DealNews (US)", "slickdeals": "Slickdeals (US)", "v2ex": "V2EX (CN)", "openrouter": "OpenRouter"}` — without this the email prints a title-cased raw slug. |
| `src/bargain_hunter/templates/email.html.j2:56` | price badge currently `${{ "%.2f"|format(deal.price) }}`. Make it `{{ "US$" if deal.currency != "AUD" else "$" }}{{ ... }}`. |
| `config/settings.yaml` | new `sources:` blocks, `voteless_sources`, `watch.trusted_sources` |
| `README.md`, `AGENTS.md` | add the four sources to the source list / repo map |

**`matching.py` noise guard.** Current code inside
`_match_watch_with_target` (~line 186):

```python
passes_votes = deal.votes_pos >= cfg.min_votes
passes_discount = (
    cfg.min_discount_percent is not None
    and deal.discount_percent is not None
    and deal.discount_percent >= cfg.min_discount_percent
)
if not (passes_votes or passes_discount):
    continue
```

Becomes:

```python
passes_votes = deal.votes_pos >= cfg.min_votes
passes_discount = (
    cfg.min_discount_percent is not None
    and deal.discount_percent is not None
    and deal.discount_percent >= cfg.min_discount_percent
)
# Editorially curated / keyword-scoped feeds carry neither votes nor a parseable
# discount; for those the keyword match is itself the quality guard.
passes_trusted = deal.source in cfg.trusted_sources
if not (passes_votes or passes_discount or passes_trusted):
    continue
```

Without this **every keyword hit from the new feeds is silently dropped** —
they have zero votes and usually no parseable percentage. This is the single
most important line in Phase 1.

**`state.py`.** Add to the `StateStore` dict (it currently holds `cold_start`,
`snapshots`, `first_seen`, `seeded`, `site_baseline`; `_prune()` only touches
`snapshots`, so new keys are safe):

```python
def due_for_fetch(self, source: str, interval_minutes: float, now: datetime) -> bool:
    last = self._data.get("last_fetch", {}).get(source)
    if not last:
        return True
    return (now - datetime.fromisoformat(last)).total_seconds() >= interval_minutes * 60

def mark_fetched(self, source: str, now: datetime) -> None:
    self._data.setdefault("last_fetch", {})[source] = now.isoformat()

def llm_prices(self) -> dict[str, list[float]]:
    return self._data.get("llm_prices", {})

def set_llm_prices(self, prices: dict[str, tuple[float, float]]) -> None:
    self._data["llm_prices"] = {k: [v[0], v[1]] for k, v in prices.items()}
```

Storing the price snapshot here (rather than a new `data/llm_prices.json`) means
**no `.github/workflows/hunt.yml` change**: `data/deals_state.json` is already in
both `actions/cache` path lists (lines ~39-42 and ~74-77) and is git-committed
once per AET day as a recovery seed (~line 108). Verify the file stays a sane
size: `python3 -c "import json;print(len(json.dumps(json.load(open('data/deals_state.json')))))"`.

**`main.py` fetch blocks**, after the existing camelcamelcamel block (~line 110):

```python
for src_name in ("dealnews", "slickdeals", "v2ex"):
    cfg = settings.sources.get(src_name)
    if not (cfg and cfg.enabled):
        continue
    interval = getattr(cfg, "poll_interval_minutes", 60)
    if not state.due_for_fetch(src_name, interval, now):
        continue
    try:
        src = FeedDealsSource(
            name=src_name,
            feed_urls=list(getattr(cfg, "feed_urls", [])),
            currency=getattr(cfg, "currency", "USD"),
            block_patterns=list(getattr(cfg, "region_block_patterns", [])),
            allow_patterns=list(getattr(cfg, "region_allow_patterns", [])),
        )
        all_deals.extend(src.fetch())
        state.mark_fetched(src_name, now)
    except Exception as exc:
        summary["errors"].append(f"{src_name} fetch failed: {exc}")

or_cfg = settings.sources.get("openrouter")
if or_cfg and or_cfg.enabled and state.due_for_fetch(
    "openrouter", getattr(or_cfg, "poll_interval_minutes", 1440), now
):
    try:
        src = LlmPriceSource(
            min_drop_percent=getattr(or_cfg, "min_drop_percent", 10.0),
            model_allowlist=list(getattr(or_cfg, "model_allowlist", [])),
        )
        all_deals.extend(src.fetch(previous=state.llm_prices(), setter=state.set_llm_prices, now=now))
        state.mark_fetched("openrouter", now)
    except Exception as exc:
        summary["errors"].append(f"openrouter fetch failed: {exc}")
```

`SourceConfig` is `extra="allow"` (`config.py:154`) so `feed_urls`,
`poll_interval_minutes`, `region_block_patterns` etc. need **no schema change**.
Import both classes at `main.py` module level (tests monkeypatch them there, see
`tests/test_main.py:116`).

Note the consequence of interval gating: on runs where a source is not fetched,
its deals are absent from `active_deals`. That is fine — dedup and
`should_notify` handle re-sightings — but it is why Phase 3 needs a per-source
"latest batch" fix.

### 1d. `config/settings.yaml`

```yaml
sources:
  # ... existing ozbargain + camelcamelcamel unchanged ...

  # --- Global digital deals. All four are voteless (see scoring.hot.voteless_sources)
  # and reach subscribers via watch keywords (scoring.watch.trusted_sources).
  dealnews:
    enabled: true
    poll_interval_minutes: 60
    currency: "USD"
    feed_urls:
      - "https://www.dealnews.com/c124/Computers/Software/?rss=1"
  slickdeals:
    enabled: true
    poll_interval_minutes: 60
    currency: "USD"
    # The query string IS the filter. Keep terms specific; bare "grok" collides
    # with "Grokking Simplicity" and "Grokit VR".
    feed_urls:
      - "https://slickdeals.net/newsearch.php?rss=1&q=supergrok&searcharea=deals&searchin=first"
      - "https://slickdeals.net/newsearch.php?rss=1&q=chatgpt&searcharea=deals&searchin=first"
      - "https://slickdeals.net/newsearch.php?rss=1&q=claude+ai&searcharea=deals&searchin=first"
      - "https://slickdeals.net/newsearch.php?rss=1&q=perplexity&searcharea=deals&searchin=first"
      - "https://slickdeals.net/newsearch.php?rss=1&q=vpn&searcharea=deals&searchin=first"
      - "https://slickdeals.net/newsearch.php?rss=1&q=cloud+storage&searcharea=deals&searchin=first"
  v2ex:
    enabled: true
    poll_interval_minutes: 180
    currency: "CNY"
    feed_urls:
      - "https://www.v2ex.com/feed/deals.xml"
  openrouter:
    enabled: true
    poll_interval_minutes: 1440
    min_drop_percent: 10.0
    model_allowlist: []          # e.g. ["x-ai/", "anthropic/", "deepseek/"]

scoring:
  hot:
    # dealnews/slickdeals/v2ex/openrouter carry no vote signal. Listing them here
    # keeps them out of the OzBargain-calibrated site velocity index (TRAP 1).
    voteless_sources: ["camelcamelcamel", "dealnews", "slickdeals", "v2ex", "openrouter"]
  watch:
    # These feeds have no votes and often no parseable discount; the keyword
    # match is the quality guard (see matching.py noise guard).
    trusted_sources: ["dealnews", "slickdeals", "v2ex", "openrouter"]
```

Region-lock patterns — put them under each NA/CN source as
`region_block_patterns` / `region_allow_patterns`. Allow list is checked first
and wins:

```yaml
    region_allow_patterns: ["global", "worldwide", "any region",
                            "international card", "全球可用", "支持国际信用卡"]
    region_block_patterns:
      - "US only"
      - "USA only"
      - "U\\.S\\. residents"
      - "US/CA residents"
      - "United States and Canada only"
      - "requires US billing"
      - "US billing (address|zip)"
      - "not available outside the US"
      - "US App Store"
      - "\\.edu email"
      - "(T-Mobile|Verizon|AT&T|Xfinity|Spectrum) customers"
      - "US (PayPal|Venmo)"
      - "region-locked"
      - "EU key"
      - "ROW excluded"
      - "仅限中国大陆"
      - "仅限大陆用户"
      - "大陆不发"
      - "中国大陆手机号"
      - "\\+86"
      - "实名认证"
      - "仅支持支付宝"
      - "仅支持微信"
      - "不支持境外"
      - "海外用户不可用"
```

**Do not block on soft signals like "USD pricing" or "no AUD option".** Most
global Stripe checkouts price in USD and take AU cards happily; blocking there
would kill the highest-value category. This list has no prior art (the research
looked specifically and found none), so expect a month of tuning against the
`dropped region-locked item` log lines.

**No LLM classifier.** Candidate volume is ~5/day, already digital by source
selection, so a classifier would change perhaps one alert a week while adding a
network call and a failure mode inside a loop that runs every 2 minutes. If the
regex misfires badly after a month, run the classifier in the daily
`strategy_hunter` job (it already has `GEMINI_API_KEY` and `extract.call_gemini`
as a reusable helper), never in the deal loop.

### 1e. Measured noise budget

| source | new items/day | alerts/day after filters |
|---|---|---|
| dealnews | 1-2 with a pubDate inside 48h | <1 |
| slickdeals × 6 | 0-2 fresh across all queries | <1 |
| v2ex | ~0.7 | ≪1 |
| openrouter | 1 diff | 1-3 per week |

`scoring.watch.max_deal_age_hours: 36` already discards DealNews's evergreen
entries (several sampled items date to February).

### Phase 1 acceptance

```bash
ruff check . && pytest -q
bargain-hunter --dry-run          # per-source fetch counts in the log, no email
grep -c dealnews data/observations/$(TZ=Australia/Sydney date +%F).jsonl
```
Plus the heat-baseline no-op check under "Verification" below.

**Commits:** `feat(sources): add DealNews/Slickdeals/V2EX digital deal feeds`,
`feat(sources): detect OpenRouter token price cuts`,
`fix(matching): let trusted voteless sources bypass the noise guard`

---

## Phase 2 — separate daily quota

Daily caps are counted from the Notion Sent Log `Track` **select** property via
`dedup.daily_count(sub, now=now, tracks={...})` (`dedup.py:179`). So the cheapest
correct design is a **third track value, `"digital"`**: any deal whose source is
in the digital set is tagged `digital` regardless of whether it qualified via hot
or watch, and counted against its own cap.

1. `models.py` — `Subscriber.max_digital_alerts_per_day: int = 10`;
   `Notification.track` literal `+= "digital"`.
2. `subscribers.py` — `_P_MAX_DIGITAL = "Max Digital Alerts/Day"` (~line 24) plus
   one parse line, copying the existing `_P_MAX_WATCH_ALERTS` handling
   (`_parse_subscriber`, ~lines 98-136).
3. `main.py` (~line 330) — alongside `remaining_hot` / `remaining_watch`:
   ```python
   digital_daily = dedup.daily_count(sub, now=now, tracks={"digital"})
   remaining_digital = sub.max_digital_alerts_per_day - digital_daily
   ```
   Also extend the "at daily caps, skipping" early-continue below it to require
   `remaining_digital <= 0` as well, or subscribers at their AU caps will never
   receive digital deals.
4. After `hot_candidates` and `watch_candidates` are built and before the cap
   slices, partition items whose `deal.source` is in the digital set out into
   `digital_candidates`, set `item.track = "digital"`, sort by tier then discount,
   slice to `max(remaining_digital, 0)`, add the overflow to `cap_suppressed`,
   and append to `items`.
5. **Queue drain** — `main.py` filters queued entries with
   `if q.track not in {"hot", "mixed"}` (~line 409) and `if q.track != "watch"`
   (~line 470). A `digital` entry queued during quiet hours would be **silently
   dropped**. Add the third drain block.
6. Notion — add a `Max Digital Alerts/Day` number property to the Subscribers DB.
   The Sent Log `Track` select gets the new option created on first write by the
   API; confirm on the first real send rather than assuming.
7. `templates/email.html.j2:71` already renders `{{ item.track }}` generically;
   a `.badge.digital` CSS rule is optional polish.

**Deliberately skipped:** the portal round-trip for this number
(`portal-worker/src/lib/notion.ts`, `portal-worker/src/types.ts`,
`frontend/app/portal/settings/page.tsx`). Edit it in Notion; add the UI only if
it changes often.

**Acceptance:** a new case in `tests/test_main.py` proving a digital deal is sent
when `remaining_hot == 0` and `remaining_watch == 0` but
`remaining_digital > 0`, and that a `digital` entry survives a quiet-hours
queue-and-drain round trip.

**Commit:** `feat(notify): separate daily alert quota for digital deals`

---

## Phase 3 — North America / China panels on `/deals`

⚠️ **Read `frontend/AGENTS.md` and the bundled docs under
`node_modules/next/dist/docs/` before writing any frontend code.** This is a
pre-release Next.js whose APIs differ from training data.

`frontend/lib/deals.ts` reads `data/observations/<AET-date>.jsonl`, walks back
`RETENTION_HOURS = 72` (line ~89), and keeps a deal only if **both**:
(a) `is_hot === true` at least once in the window (`agg.lastHotTs`), and
(b) it still appears in the source's latest scan batch
(`isStillInLatestSourceBatch`, ~line 184).

Both gates exclude the new sources, and each needs a fix:

1. **(a)** the new sources are watch-track and rarely hot, so `lastHotTs` is
   never set. Fix: define `const DIGITAL_SOURCES = new Set(['dealnews',
   'slickdeals', 'v2ex', 'openrouter'])` and, for those sources, keep the deal on
   recency inside the existing 72h window instead of requiring `is_hot`. Volume
   is ~1-2 items/day so the board will not flood.
2. **(b)** they poll hourly/daily, so most runs emit no rows for them and the
   "latest batch" is empty → **everything would silently disappear**. Fix:
   resolve the latest batch **per source** (the most recent `ts` at which that
   source appeared at all), not per run.
3. The live OzBargain expiry re-check (`isOzbargainInactive`, ~lines 39-52) is
   already source-gated; leave it alone.

Region lives **only in the frontend** — a literal map beside the existing
`sourceLabel()` (~line 248). Python never needs it, because filtering is already
per-source config, so do **not** add a field to `Deal` or to the observation row:

```ts
export type DealRegion = 'AU' | 'NA' | 'CN' | 'GLOBAL'
const REGION_BY_SOURCE: Record<string, DealRegion> = {
  ozbargain: 'AU', camelcamelcamel: 'AU',
  dealnews: 'NA', slickdeals: 'NA',
  v2ex: 'CN', openrouter: 'GLOBAL',
}
export function dealRegion(source: string): DealRegion {
  return REGION_BY_SOURCE[source] ?? 'AU'
}
```

Add `currency: string` to the `LiveDeal` interface (~line 6), read from the
observation row (add `currency` to `observations.build_observation` in Phase 1 —
one line) and default to `'AUD'` when absent so historical rows stay valid.

`frontend/app/deals/page.tsx` renders one flat `.deals-grid` (line ~78). Change
to stacked sections, reusing the existing card markup and `HotLevelBadge` /
`SourceBadge` (lines 18-42), one section per region, each rendering nothing when
empty:

1. **Australia** — existing tier logic (`topCandidates`/`greatCandidates`,
   `MIN_DISPLAY_COUNT`, `FALLBACK_GREAT_LIMIT`) completely unchanged.
2. **North America**
3. **中国 / China**
4. **LLM token prices** — `openrouter`. Given its own section rather than being
   filed under NA because token price cuts are not regional and are arguably the
   most interesting content. Move it under NA if the owner prefers.

The card's hardcoded `$` (line ~108) becomes `US$` / `¥` when
`deal.currency !== 'AUD'`.

**Acceptance:** `cd frontend && npm run build`, then the dev server; confirm each
region section populates from real observation rows and empty sections render
nothing. Confirm the Australia section is byte-identical in content to before.

**Commit:** `feat(frontend): region panels for NA/CN/global digital deals`

---

## Verification (whole feature)

1. **Endpoints, from this machine and again from CI** (Slickdeals was verified
   from an AU IP; Actions runs from US IPs and Slickdeals 403s even its own
   robots.txt — treat 403 as skip-and-log, never a pipeline failure):
   ```bash
   curl -sI "https://www.dealnews.com/c124/Computers/Software/?rss=1" | head -1
   curl -s "https://slickdeals.net/newsearch.php?rss=1&q=supergrok&searcharea=deals&searchin=first" | head -40
   curl -s "https://www.v2ex.com/feed/deals.xml" | head -20
   curl -s "https://openrouter.ai/api/v1/models" | python3 -c "import json,sys;print(len(json.load(sys.stdin)['data']))"
   ```
2. **Acceptance test = the deal that was missed.** Save the Slickdeals `q=grok`
   feed containing "SuperGrok Annual Plan bundled with X Premium+ $197.5" as
   `tests/fixtures/slickdeals_grok.xml`, then assert a subscriber whose watch
   keywords include `SuperGrok` gets a match through
   `matching.filter_watch_matches`. This is the one test that proves the feature
   does what it was built for.
3. **Unit tests** — fixture-parse style, no network, following
   `tests/test_ozbargain.py`; for fetch paths use
   `monkeypatch.setattr(mod.httpx, "get", fake)` as in
   `tests/test_strategy_reddit.py:74-88`. Fixtures go flat in `tests/fixtures/`.
   - `tests/test_feed_deals.py`: RSS 2.0 parse; Atom parse (V2EX);
     `dealnews:price` + currency attribute preferred over the title regex;
     tz-aware timestamps; region block drops an item; a positive override keeps
     one; a 403 on one feed does not lose the others; cross-query de-dupe by key.
   - `tests/test_llm_prices.py`: ≥10% drop detected; <10% ignored; an id absent
     from the previous snapshot ignored; empty previous snapshot yields zero
     deals but still seeds; malformed pricing skipped.
   - `tests/test_matching.py`: `trusted_sources` bypass fires with 0 votes and
     `discount_percent=None`; a non-trusted source with the same shape still does
     not fire.
   - `tests/test_main.py`: digital cap independent of hot/watch caps; poll
     interval gating skips a fetch.
   - `tests/test_state.py`: `due_for_fetch` / `mark_fetched` / `llm_prices`
     round-trip and survive `save()`/`load()` and `_prune()`.
4. **Regression:** full `pytest` and `ruff check .`. `config/settings.yaml` is
   read by **both** packages — `bargain_hunter.config.Settings` is
   `extra="forbid"` at the top level, and `strategy_hunter.load_strategy_config`
   reads the same file — so run the whole suite, not a subset.
5. **Heat-baseline no-op proof (TRAP 1).** Run `bargain-hunter --dry-run` with
   the new sources disabled, note `heat_ratio` and `site_velocity_index` from the
   summary, enable them, run again on the same state, and confirm both are
   unchanged. If they move, a new source is missing from `voteless_sources`.
6. **State size:** confirm `data/deals_state.json` stays reasonable after the
   `llm_prices` snapshot lands (~16KB added).

## The four traps (do not lose these)

1. **Foreign votes poison the AU baseline.** `main.py:159-170` builds
   `vote_based_pairs` = every active deal whose source is **not** in
   `scoring.hot.voteless_sources`, feeds `compute_site_velocity_index`, and the
   resulting `heat_ratio` both scales OzBargain's absolute vote gates *and* is
   persisted into the per-hour EWMA `site_baseline` inside the committed
   `data/deals_state.json`. A foreign vote scale would inflate the index, raise
   OzBargain's gates, suppress genuine AU deals, and permanently corrupt the
   baseline. → all four new sources go in `voteless_sources`. None has usable
   vote data anyway.
2. **`enrich_deal` clobbers `discount_percent`.** `scoring.py:184` early-returns
   **only** `if deal.price is not None`; otherwise it unconditionally overwrites
   price/was_price/discount_percent/price_confidence from a title regex. → new
   sources set `price` themselves, reusing `scoring.extract_price_signals`.
3. **Poll cadence.** The pipeline runs every ~2 min; six Slickdeals queries at
   that rate is ~4,300 requests/day against a WAF that 403s readily. Gate on
   `poll_interval_minutes`. DealNews robots.txt asks for a 2s crawl-delay.
4. **The voteless hot bar is 40% off.** `discount_candidate_min = 40.0` and
   `discount_tiers = {good: 40, great: 55, top: 70}` (`config.py:113-122`, not
   overridden in YAML). New-source deals therefore reach the owner mainly via
   **watch keywords**, which is correct — hot scoring is calibrated on observed
   OzBargain data and there is no observed data for these sources yet. Revisit
   after a few weeks of `data/observations/` rows. Note `universal_top: true`
   means a ≥70%-off item bypasses category routing and reaches every hot
   subscriber.

## Open questions to settle during implementation

- `state.should_notify` also takes `min_votes_gain_per_window`. CamelCamelCamel
  passes through it today so voteless sources are presumably fine, but cover it
  with a test rather than assuming.
- Confirm the `dealnews:` XML namespace URI from the live feed.
- CN payment gating is documentation-derived and untested: SiliconFlow / Zhipu /
  Volcano appear Alipay+WeChat only; DeepSeek routes foreign cards via PayPal
  with bank-dependent success; Kimi runs separate `platform.moonshot.ai` and
  `.cn` consoles with non-interchangeable keys. Nobody has put an AU card
  through any of them. This is why mainland China gets one thin source.

## Explicitly not doing

- No Gemini/LLM classifier in the deal loop.
- No Reddit source. Owner declined adding `REDDIT_CLIENT_ID`/`SECRET`; also
  unproven from CI datacenter IPs, and Reddit's `.rss` carries no score or
  comment count so it could not do velocity even if reachable. If this is ever
  revisited: register an OAuth script app and confirm
  `oauth.reddit.com/r/grok/hot.json` returns `score` and `num_comments` from an
  Actions runner *before* writing code.
- No GST line on USD deals. Australia does apply GST to inbound digital
  supplies, but many global checkouts already price GST-inclusive for AU
  customers, so a blanket "+10%" would often be wrong.
- No app-store country switching. It breaches Apple/Google terms and Google
  enforces a 365-day country lock; surface such deals as region-locked, never as
  actionable.
- No portal UI for the digital alert cap.

## Rejected sources (do not revisit without new evidence)

什么值得买 smzdm (403, WAF-gated, mostly Taobao/JD physical) · 线报 sites
(xianbao.fun etc: no syndication) · Telegram-to-RSS via public RSSHub (403;
needs a self-hosted instance) · 小众软件 appinn / 反斗软件 apprcn / 少数派 sspai
(software *news* firehoses, zero deal items in sample) · AppSumo (sitemap +
per-product scrape only) · StackSocial (robots.txt disallows product feeds for
non-Google bots) · DealFuel, Kinguin, Product Hunt (auth/partner-gated or 404
unauthenticated) · X / @grok (402 Payment Required — the fastest first-party
channel is paywalled) · `x.ai/news` (10 recent posts, all model/feature
launches, never subscription pricing) · `x.ai/api` (API token prices only, no
consumer subscription tiers) · Artificial Analysis, Perplexity changelog (401) ·
Slickdeals `mode=frontpage` (90-95% physical retail).

Tier 2, with triggers: **HN Algolia**
(`https://hn.algolia.com/api/v1/search_by_date?tags=story&numericFilters=points>30`)
— the only velocity-capable new source (`points`, `num_comments`, `created_at`);
add if the OpenRouter diff proves to be missing consumer-subscription news, but
note it is largely redundant with OpenRouter for token prices. **DeepSeek /
OpenAI changelog diffs** (`https://api-docs.deepseek.com/updates`,
`https://developers.openai.com/api/docs/changelog` — the old
platform.openai.com URL now 301s); add only for provider-native confirmation of
what OpenRouter already told you.

## Findings

_Fill this in from the Phase 0 diagnostics before writing code._

- Notion `Watch Keywords` at time of the miss:
- Notion `Categories` at time of the miss:
- `Hot Level` floor:
- Verdict on why node/963354 never arrived:
