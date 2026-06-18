"""OzBargain source: parses the public RSS feed, including the custom ozb:meta block.

The feed exposes engagement metrics we need for the velocity ("hot") track as
attributes on <ozb:meta>: votes-pos, votes-neg, comment-count, click-count, plus
the merchant url, image and (optionally) expiry. No HTML scraping is required.
"""

import html
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from defusedxml import ElementTree as ET

from ..models import Deal
from .base import Source

OZB_NS = "https://www.ozbargain.com.au"
DEFAULT_FEED_URL = "https://www.ozbargain.com.au/deals/feed"
USER_AGENT = (
    "bargain-hunter/0.1 (personal deal alerter; +https://github.com/versent-shawn/bargain-hunter)"
)

_NODE_RE = re.compile(r"/node/(\d+)")
_TAG_RE = re.compile(r"<[^>]+>")


def _to_int(value: str | None) -> int:
    try:
        return int(value) if value is not None else 0
    except ValueError:
        return 0


def _clean_text(value: str | None) -> str | None:
    """Strip HTML tags and unescape entities so downstream matching/rendering see plain text."""
    if not value:
        return None
    text = html.unescape(_TAG_RE.sub(" ", value))
    text = " ".join(text.split())
    return text or None


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an RFC 2822 (pubDate) or ISO 8601 (ozb:meta expiry) timestamp.

    Always returns a timezone-aware datetime normalised to UTC, so downstream
    velocity / age / expiry maths never mixes naive and aware datetimes. A value
    that carries no offset (unexpected for this feed) is assumed to be UTC.
    """
    if not value:
        return None
    dt: datetime | None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class OzBargainSource(Source):
    name = "ozbargain"

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
        title = (item.findtext("title") or "").strip()
        if not link or not title:
            return None

        node_match = _NODE_RE.search(link)
        guid = (item.findtext("guid") or "").strip()
        if node_match:
            deal_id = node_match.group(1)
        elif guid:
            deal_id = guid.split(" ")[0]
        else:
            deal_id = link

        meta = item.find(f"{{{OZB_NS}}}meta")
        meta_attrs = meta.attrib if meta is not None else {}

        title_msg = item.find(f"{{{OZB_NS}}}title-msg")
        expired = title_msg is not None and title_msg.get("type") == "expired"

        categories = [c.text.strip() for c in item.findall("category") if c.text]

        return Deal(
            source=self.name,
            deal_id=deal_id,
            title=title,
            url=link,
            merchant_url=meta_attrs.get("url"),
            description=_clean_text(item.findtext("description")),
            image=meta_attrs.get("image"),
            categories=categories,
            posted_at=_parse_dt(item.findtext("pubDate")),
            expiry=_parse_dt(meta_attrs.get("expiry")),
            votes_pos=_to_int(meta_attrs.get("votes-pos")),
            votes_neg=_to_int(meta_attrs.get("votes-neg")),
            comment_count=_to_int(meta_attrs.get("comment-count")),
            click_count=_to_int(meta_attrs.get("click-count")),
            expired=expired,
        )
