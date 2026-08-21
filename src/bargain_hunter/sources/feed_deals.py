"""Generic digital-deal feed source (RSS 2.0 + Atom), config-driven.

Serves DealNews (NA software category), Slickdeals (keyword-scoped search),
V2EX (优惠信息), iknowthepilot (AU-departure flight deals), Vercel's changelog
(Atom), and the AFF/Point Hacks AU-travel feeds. Except for iknowthepilot,
these feeds carry no vote or comment signal, so they
reach a subscriber through the watch track (see scoring.hot.voteless_sources
and scoring.watch.trusted_sources) rather than the hot ladder.

These feeds also re-emit months-to-years-old items on every poll (no window
param on the query side), so parse() drops anything older than
max_item_age_hours before it ever reaches observations/dedup/scoring.

V2EX's deals.xml is a slow, purpose-built node (~0.7 posts/day) that rarely has
anything inside the watch track's freshness window; index.xml (全站最新) and its
per-node feeds (e.g. openai.xml) are much fresher firehoses of mostly-unrelated
discussion, kept on-topic via title_keywords rather than by loosening any age
gate (see _DEFAULT_TITLE_KEYWORDS below).
"""

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
from ..scoring import extract_price_signals, price_display_confidence
from .base import Source

log = logging.getLogger(__name__)

_ATOM = "http://www.w3.org/2005/Atom"
# Confirmed live 2026-08-20 against https://www.dealnews.com/c124/Computers/Software/?rss=1
# root element: <rss ... xmlns:dealnews="https://www.dealnews.com/ns/rss/1.0.htm">
_DEALNEWS = "https://www.dealnews.com/ns/rss/1.0.htm"
_TAG_RE = re.compile(r"<[^>]+>")
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _strip_html(raw: str, max_len: int = 2000) -> str:
    return html.unescape(_TAG_RE.sub(" ", raw or "")).strip()[:max_len]


_UNSET = object()  # distinguishes "use the per-source default" from an explicit None/[]


class FeedDealsSource(Source):
    # Default parse-time staleness cutoffs (hours since posted_at), by source
    # `name`; sources not listed fall back to _FALLBACK_MAX_AGE_HOURS. Measured
    # live 2026-08-21: dealnews's own item ages top out around 73h*24=1751h
    # (~10 weeks) with no multi-year tail — it's a single evergreen software
    # category with no fixed end dates, not reposted cruft — so it gets more
    # headroom to avoid cutting a still-valid several-week-old software offer.
    # slickdeals and v2ex return genuine years-old reposts (slickdeals max
    # ~24000h / 2.7 years, v2ex max ~3200h / 4.4 months) and get the tighter
    # fallback.
    #
    # vercel is a mandatory override, not just documentation of what the
    # fallback already computes to: measured live 2026-08-21, the feed carries
    # 1492 entries back to 2016 (newest 10.6h, oldest 3586 days), so without a
    # cutoff every poll floods observations with a decade of changelog noise.
    # Pinned explicitly so it can't silently drift if _FALLBACK_MAX_AGE_HOURS
    # ever changes for unrelated reasons (see GLOBAL_EXPANSION_PLAN.md).
    _DEFAULT_MAX_AGE_HOURS = {"dealnews": 24 * 60, "vercel": 24 * 30}  # 60 / 30 days
    _FALLBACK_MAX_AGE_HOURS = 24 * 30.0  # 30 days

    # V2EX's deals.xml is purpose-built (every post is already deal-shaped) but
    # its index.xml (全站最新) and per-node feeds are general firehoses — most
    # items are unrelated discussion. Measured live 2026-08-21: unfiltered, the
    # openai node's "money" keywords hit mostly on bare 额度 (quota) complaints
    # ("额度用的很快", "账号额度明显缩水") — 18/50 hits, ~2 genuinely deal-shaped.
    # [推广] is V2EX's own "promotion" node tag — a post tagged with it is
    # commercial by definition, so it's included as a standalone strong signal.
    # Dropping bare 额度/码 (码 alone matches inside 密码/代码/编码 etc.) took
    # openai's hits from 18 to 3 with zero loss of the genuinely deal-shaped
    # ones. Applied to all of v2ex's feed_urls, including deals.xml, since one
    # `name` shares one filter (see main.py's per-source-name construction) —
    # measured no loss there (its own titles already say 羊毛/优惠/免费 etc.).
    #
    # Vercel's changelog Atom feed mixes real time-boxed offers ("free",
    # "50% off") with routine product-shipped noise ("Bun 1.4 is now available
    # in Vercel Functions"). Measured live 2026-08-21 over the 125 entries
    # inside the 30-day cutoff above: this set hits 9/125 with zero false
    # negatives in the sample (see GLOBAL_EXPANSION_PLAN.md for the title
    # list). \boff\b is bounded so it doesn't fire on "Toolbar"/"Functions"
    # etc. — also checked against "offers"/"official"/"offering": the \b right
    # after "off" needs a non-word char, and the following letter in each of
    # those is a word char, so none of them false-fire either. Re-measured over
    # the feed's full 365-day window (816 entries, 25 hits, ~3%): \boff\b
    # produced zero false positives there, and the residual noise is "price"
    # matching feature news ("price sorting", "price per token flattens") —
    # kept anyway because the same token catches real cuts ("Reduced prices for
    # TLDs"). "promo" was dropped: over those 816 entries it scored zero real
    # offers and one false positive, "Block Vercel deployment promotions with
    # GitHub Actions" (deployment promotion, not a discount). A promo-code
    # offer's title would still be caught by free/off/discount/credit.
    _DEFAULT_TITLE_KEYWORDS = {
        "v2ex": [
            r"\[推广\]",
            r"羊毛", r"薅", r"优惠", r"折扣", r"免费", r"白嫖", r"领取", r"首月",
            r"福利", r"活动", r"促销", r"特价", r"减免", r"返现", r"试用", r"赠送",
            r"券", r"限时", r"0 ?元", r"几折", r"打折", r"便宜",
        ],
        "vercel": [
            "free", "credit", "discount", r"\boff\b", "pricing", "price",
            "trial", "no cost",
        ],
    }
    _FALLBACK_TITLE_KEYWORDS: list[str] | None = None  # no filtering — aff/pointhacks included:
    # measured 17/20 of AFF's deals subforum is already deal-shaped, and a filter here is the
    # "filter-shaped inert" trap — a title-convention change on their end would make it match
    # zero forever while the feed still reads healthy (HTTP 200, well-formed). See
    # GLOBAL_EXPANSION_PLAN.md Lane B.

    # HTTP request timeout (seconds), by source `name`; same per-name-default
    # mechanism as the two dicts above, reused here rather than plumbing a new
    # config field through main.py. vercel's feed is 3.3MB (measured 1.41s
    # locally) — thin under the 20s fallback on a slow CI runner, and a read
    # timeout mid-body raises inside parse(), which fetch() does not catch
    # (it only catches httpx.HTTPError) — it would escape to main.py's
    # per-source `except Exception` as a silent zero-deal fetch.
    _DEFAULT_TIMEOUT_SECONDS = {"vercel": 60.0}
    _FALLBACK_TIMEOUT_SECONDS = 20.0

    # Titles to reject even when they matched title_keywords, by source `name`.
    # The keyword list answers "is this on topic"; this answers "is it actually
    # an offer". V2EX's 优惠-adjacent register is full of posts that use the
    # vocabulary without offering anything: questions about a deal, complaints
    # that one died, warnings about a scam, and — the reason this exists —
    # 中转站 ads reselling someone else's LLM API quota, which is grey-market
    # account resale, not a merchant offer, and must not reach a digest.
    # Measured live 2026-08-21 against a full v2ex poll: 14 items in, 9 rejected
    # and 5 kept, matching a by-hand classification of the same 14 exactly.
    # Deliberately per-`name`, NOT global: 中转 means "transit" in an airfare
    # title, so a shared list would silently kill aff/iknowthepilot's real
    # connecting-flight deals.
    _DEFAULT_TITLE_BLOCK = {
        "v2ex": [
            # grey market: reselling or sharing someone else's account/quota
            r"中转", r"逆向", r"车位", r"合租", r"成品号", r"镜像站", r"独享号",
            # 代充/代付 is the same trade in a different wrapper: someone tops up
            # your vendor account with their own payment rail, which is an
            # account-terms violation and leaves you with no recourse. Measured
            # live: "[推广] ChatGPT Codex Claude 官方订阅代充值 v2 优惠码 …"
            # slipped through a list that only knew the word 中转.
            r"代充", r"代付", r"代开", r"拼车", r"共享号",
            # questions — used the vocabulary, offering nothing
            r"哪里有", r"有没有", r"^求", r"求购", r"求推荐", r"是什么", r"怎么样",
            r"如何评价",
            # complaints and post-mortems ("the freebie is dead", "got banned")
            r"封号", r"被封", r"炸了", r"跑路", r"翻车", r"缩水", r"没了",
            # scam warnings
            r"警惕", r"小心", r"谨慎", r"别急", r"避雷", r"骗",
            # on-topic vocabulary, off-topic subject
            r"公益", r"心理咨询",
        ],
    }
    _FALLBACK_TITLE_BLOCK: list[str] | None = None  # no rejection

    def __init__(
        self,
        name: str,
        feed_urls: list[str],
        *,
        currency: str = "USD",
        block_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        request_delay_seconds: float = 2.0,
        # HTTP request timeout in seconds. Defaults per `name` via
        # _DEFAULT_TIMEOUT_SECONDS above when not passed explicitly.
        timeout: float = _UNSET,  # type: ignore[assignment]
        # Drop items older than this at parse time. None disables the filter.
        # Items with no parseable posted_at are always kept — an unknown age
        # is not evidence of staleness (see _is_stale). Defaults per `name`
        # via _DEFAULT_MAX_AGE_HOURS above when not passed explicitly.
        max_item_age_hours: float | None = _UNSET,  # type: ignore[assignment]
        # Reject items whose title matches one of these, even if they passed
        # title_keywords. None/[] disables. Defaults per `name` via
        # _DEFAULT_TITLE_BLOCK above when not passed explicitly.
        title_block: list[str] | None = _UNSET,  # type: ignore[assignment]
        # Keep only items whose title matches one of these patterns (any-of).
        # None/[] disables the filter (kept for every existing call site).
        # Defaults per `name` via _DEFAULT_TITLE_KEYWORDS when not passed
        # explicitly — needed for firehose feeds (e.g. V2EX's index.xml) that
        # mix a source's real content with unrelated discussion.
        title_keywords: list[str] | None = _UNSET,  # type: ignore[assignment]
    ) -> None:
        self.name = name
        self.feed_urls = feed_urls
        self.currency = currency
        self._block = [re.compile(p, re.IGNORECASE) for p in (block_patterns or [])]
        self._allow = [re.compile(p, re.IGNORECASE) for p in (allow_patterns or [])]
        self.request_delay_seconds = request_delay_seconds
        if timeout is _UNSET:
            timeout = self._DEFAULT_TIMEOUT_SECONDS.get(name, self._FALLBACK_TIMEOUT_SECONDS)
        self.timeout = timeout
        if max_item_age_hours is _UNSET:
            max_item_age_hours = self._DEFAULT_MAX_AGE_HOURS.get(name, self._FALLBACK_MAX_AGE_HOURS)
        self.max_item_age_hours = max_item_age_hours
        if title_keywords is _UNSET:
            title_keywords = self._DEFAULT_TITLE_KEYWORDS.get(name, self._FALLBACK_TITLE_KEYWORDS)
        self._title_keywords = [re.compile(p, re.IGNORECASE) for p in (title_keywords or [])]
        if title_block is _UNSET:
            title_block = self._DEFAULT_TITLE_BLOCK.get(name, self._FALLBACK_TITLE_BLOCK)
        self._title_block = [re.compile(p, re.IGNORECASE) for p in (title_block or [])]
        # Newest posted_at across ALL parsed items this source has seen, taken
        # before the staleness/title_keywords filters below -- the staleness
        # ceiling guard's signal of the feed's own health, not what survived
        # our gates (see GLOBAL_EXPANSION_PLAN.md Lane C).
        self.newest_item_at: datetime | None = None

    def fetch(self) -> list[Deal]:
        deals: dict[str, Deal] = {}  # de-dupe across queries by Deal.key
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
        items = (
            channel.findall("item") if channel is not None else root.findall(f"{{{_ATOM}}}entry")
        )
        out: list[Deal] = []
        dropped_stale = 0
        dropped_no_keyword = 0
        dropped_blocked = 0
        for item in items:
            deal = self._parse_item(item, now)
            if deal is None:
                continue
            if deal.posted_at and (
                self.newest_item_at is None or deal.posted_at > self.newest_item_at
            ):
                self.newest_item_at = deal.posted_at
            if self._is_stale(deal, now):
                dropped_stale += 1
                continue
            if self._title_keywords and not any(p.search(deal.title) for p in self._title_keywords):
                dropped_no_keyword += 1
                continue
            if any(p.search(deal.title) for p in self._title_block):
                dropped_blocked += 1
                continue
            out.append(deal)
        # Aggregate, not per-item — these feeds can carry 100+ dropped items per
        # poll (firehose nodes especially) and a line each would flood the log.
        if dropped_stale:
            log.info(
                "%s: dropped %d stale item(s) older than %gh",
                self.name,
                dropped_stale,
                self.max_item_age_hours,
            )
        if dropped_blocked:
            log.info(
                "%s: dropped %d item(s) matching title_block (not an offer)",
                self.name,
                dropped_blocked,
            )
        if dropped_no_keyword:
            log.info(
                "%s: dropped %d item(s) not matching title_keywords", self.name, dropped_no_keyword
            )
        return out

    def _is_stale(self, deal: Deal, now: datetime) -> bool:
        if self.max_item_age_hours is None or deal.posted_at is None:
            return False  # no cutoff configured, or age unknown — don't guess stale
        age_hours = (now - deal.posted_at).total_seconds() / 3600
        return age_hours > self.max_item_age_hours

    def _parse_item(self, item, now: datetime) -> Deal | None:
        atom = item.tag.endswith("entry")
        if atom:
            title = (item.findtext(f"{{{_ATOM}}}title") or "").strip()
            link_el = item.find(f"{{{_ATOM}}}link")
            url = (link_el.get("href") if link_el is not None else "") or ""
            raw_body = (
                item.findtext(f"{{{_ATOM}}}content") or item.findtext(f"{{{_ATOM}}}summary") or ""
            )
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
        price_confidence = None
        # DealNews gives a structured price; prefer it over the title regex.
        dn_price = item.find(f"{{{_DEALNEWS}}}price")
        if dn_price is not None and (dn_price.text or "").strip():
            with contextlib.suppress(TypeError, ValueError):
                price = float(dn_price.text.strip().lstrip("$"))
                currency = dn_price.get("currency") or currency
                price_confidence = "high"
        # AUD (iknowthepilot) gets the same title-derived confidence check
        # scoring.enrich_deal already applies elsewhere; a "$" on a foreign
        # (USD/CNY) price would misread as AUD, so those stay unconfirmed.
        if price_confidence is None and currency == "AUD":
            price_confidence = price_display_confidence(title, price, was_price)
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
            # discount_percent — see GLOBAL_DEALS_PLAN.md TRAP 2.
            price=price,
            was_price=was_price,
            discount_percent=discount_pct,
            price_confidence=price_confidence,
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
        dt: datetime | None = None
        with contextlib.suppress(Exception):
            dt = parsedate_to_datetime(text)  # RFC 822 (RSS)
        if dt is None:
            with contextlib.suppress(Exception):
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt is None:
            return None
        # RFC 822 without a numeric offset (seen on iknowthepilot's pubDate)
        # parses as naive — treat as UTC rather than let it leak downstream.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
