"""Generic RSS 2.0 source: harvests configured feeds into CapturedPosts.

Unlike ozbargain_comments.py (feed shape is OzBargain-specific), this parses
any standard RSS 2.0 <channel>/<item> feed. Used for AU finance/travel blogs
(PointHacks, Australian Frequent Flyer) that publish plain RSS.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from defusedxml import ElementTree as ET

from ..models import CapturedPost
from .base import BROWSER_UA, StrategySource, clean_html

log = logging.getLogger(__name__)

_CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"


class RssFeedSource(StrategySource):
    name = "rss"

    def __init__(
        self,
        feeds: list[dict[str, str]],
        request_delay_seconds: float = 2.0,
        timeout: float = 20.0,
    ) -> None:
        self.feeds = feeds
        self.request_delay_seconds = request_delay_seconds
        self.timeout = timeout

    def fetch(self) -> list[CapturedPost]:
        now = datetime.now(UTC)
        posts: list[CapturedPost] = []
        for i, feed in enumerate(self.feeds):
            if i:
                time.sleep(self.request_delay_seconds)
            url = feed["url"]
            board = feed.get("board") or url
            try:
                resp = httpx.get(
                    url,
                    headers={"User-Agent": BROWSER_UA},
                    timeout=self.timeout,
                    follow_redirects=True,
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("rss: skipping feed '%s' — %s", board, exc)
                continue
            posts.extend(self.parse(resp.text, board=board, now=now))
        return posts

    def parse(self, xml: str, board: str, now: datetime | None = None) -> list[CapturedPost]:
        """Parse an RSS 2.0 feed into CapturedPosts (no network)."""
        now = now or datetime.now(UTC)
        root = ET.fromstring(xml)
        channel = root.find("channel")
        if channel is None:
            return []
        posts: list[CapturedPost] = []
        for item in channel.findall("item"):
            link = (item.findtext("link") or "").strip()
            title = (item.findtext("title") or "").strip()
            if not link or not title:
                continue
            guid = (item.findtext("guid") or "").strip()
            encoded_el = item.find(f"{{{_CONTENT_NS}}}encoded")
            raw_body = (encoded_el.text if encoded_el is not None else None) or (
                item.findtext("description") or ""
            )
            posts.append(
                CapturedPost(
                    source=self.name,
                    post_id=guid or link,
                    url=link,
                    title=title,
                    body=clean_html(raw_body),
                    board=board,
                    created_at=_parse_pub_date(item.findtext("pubDate")),
                    fetched_at=now,
                )
            )
        return posts


def _parse_pub_date(value: str | None) -> datetime | None:
    """Parse an RFC 822 pubDate into a tz-aware UTC datetime, or None if malformed."""
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
