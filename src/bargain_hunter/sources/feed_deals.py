"""Generic digital-deal feed source (RSS 2.0 + Atom), config-driven.

Serves DealNews (NA software category), Slickdeals (keyword-scoped search),
V2EX (优惠信息) and iknowthepilot (AU-departure flight deals). Except for
iknowthepilot, these feeds carry no vote or comment signal, so they reach a
subscriber through the watch track (see scoring.hot.voteless_sources and
scoring.watch.trusted_sources) rather than the hot ladder.

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
    _DEFAULT_MAX_AGE_HOURS = {"dealnews": 24 * 60}  # 60 days
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
    _DEFAULT_TITLE_KEYWORDS = {
        "v2ex": [
            r"\[推广\]",
            r"羊毛", r"薅", r"优惠", r"折扣", r"免费", r"白嫖", r"领取", r"首月",
            r"福利", r"活动", r"促销", r"特价", r"减免", r"返现", r"试用", r"赠送",
            r"券", r"限时", r"0 ?元", r"几折", r"打折", r"便宜",
        ],
    }
    _FALLBACK_TITLE_KEYWORDS: list[str] | None = None  # no filtering

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
        # Drop items older than this at parse time. None disables the filter.
        # Items with no parseable posted_at are always kept — an unknown age
        # is not evidence of staleness (see _is_stale). Defaults per `name`
        # via _DEFAULT_MAX_AGE_HOURS above when not passed explicitly.
        max_item_age_hours: float | None = _UNSET,  # type: ignore[assignment]
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
        self.timeout = timeout
        if max_item_age_hours is _UNSET:
            max_item_age_hours = self._DEFAULT_MAX_AGE_HOURS.get(name, self._FALLBACK_MAX_AGE_HOURS)
        self.max_item_age_hours = max_item_age_hours
        if title_keywords is _UNSET:
            title_keywords = self._DEFAULT_TITLE_KEYWORDS.get(name, self._FALLBACK_TITLE_KEYWORDS)
        self._title_keywords = [re.compile(p, re.IGNORECASE) for p in (title_keywords or [])]

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
        for item in items:
            deal = self._parse_item(item, now)
            if deal is None:
                continue
            if self._is_stale(deal, now):
                dropped_stale += 1
                continue
            if self._title_keywords and not any(p.search(deal.title) for p in self._title_keywords):
                dropped_no_keyword += 1
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
