"""Generic digital-deal feed source (RSS 2.0 + Atom), config-driven.

Serves DealNews (NA software category), Slickdeals (keyword-scoped search),
V2EX (优惠信息) and iknowthepilot (AU-departure flight deals). Except for
iknowthepilot, these feeds carry no vote or comment signal, so they reach a
subscriber through the watch track (see scoring.hot.voteless_sources and
scoring.watch.trusted_sources) rather than the hot ladder.
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
