"""CamelCamelCamel AU source: parses the top-drops RSS feed.

Feed URL: https://au.camelcamelcamel.com/top_drops/feed

Each item title encodes all price signals in a structured format:
  "Product Name - down 18.16% ($5.99) to $26.99 from $32.98"

CCC items have no vote/comment/click counts (price tracker, not community site).
Watch matching falls back to discount_percent as the noise gate (see WatchConfig).
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from defusedxml import ElementTree as ET

from ..models import Deal
from .base import Source

DEFAULT_FEED_URL = "https://au.camelcamelcamel.com/top_drops/feed"
USER_AGENT = (
    "bargain-hunter/0.1 (personal deal alerter; +https://github.com/versent-shawn/bargain-hunter)"
)

# "Product Name - down 18.16% ($5.99) to $26.99 from $32.98"
_TITLE_RE = re.compile(
    r"^(.*?)\s*-\s*down\s*([\d.]+)%\s*\(\$([\d,.]+)\)\s*to\s*\$([\d,.]+)\s*from\s*\$([\d,.]+)\s*$"
)
_PRODUCT_ID_RE = re.compile(r"/product/([^/?#]+)")


def _to_float(raw: str) -> float:
    return float(raw.replace(",", ""))


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class CamelCamelCamelSource(Source):
    name = "camelcamelcamel"

    def __init__(self, feed_url: str = DEFAULT_FEED_URL, timeout: float = 20.0) -> None:
        self.feed_url = feed_url
        self.timeout = timeout

    def fetch(self) -> list[Deal]:
        resp = httpx.get(
            self.feed_url,
            headers={"User-Agent": USER_AGENT},
            timeout=self.timeout,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return self.parse(resp.text)

    def parse(self, xml: str) -> list[Deal]:
        root = ET.fromstring(xml)
        channel = root.find("channel")
        if channel is None:
            return []
        deals: list[Deal] = []
        for item in channel.findall("item"):
            deal = self._parse_item(item)
            if deal is not None:
                deals.append(deal)
        return deals

    def _parse_item(self, item) -> Deal | None:
        link = (item.findtext("link") or "").strip()
        raw_title = (item.findtext("title") or "").strip()
        if not link or not raw_title:
            return None

        product_match = _PRODUCT_ID_RE.search(link)
        if not product_match:
            return None
        product_id = product_match.group(1)

        title_match = _TITLE_RE.match(html.unescape(raw_title))
        if not title_match:
            return None

        product_name = title_match.group(1).strip()
        discount_pct = float(title_match.group(2))
        price = _to_float(title_match.group(4))
        was_price = _to_float(title_match.group(5))

        return Deal(
            source=self.name,
            deal_id=product_id,
            title=product_name,
            url=link,
            merchant_url=f"https://www.amazon.com.au/dp/{product_id}",
            posted_at=_parse_dt(item.findtext("pubDate")),
            price=price,
            was_price=was_price,
            discount_percent=discount_pct,
            votes_pos=0,
            votes_neg=0,
            comment_count=0,
            click_count=0,
        )
