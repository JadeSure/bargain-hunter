"""OzBargain tag-feed source: harvests tag-filtered deals for onboarding signals.

Each OzBargain tag has an RSS feed at /tag/<tag>/feed. One CapturedPost is
produced per item: useful for signup-bonus and referral deals tagged "cashback",
"referral", etc.
"""

from __future__ import annotations

import contextlib
import logging
import random
import re
import time
from datetime import UTC, datetime

import httpx
from defusedxml import ElementTree as ET

from ..models import CapturedPost
from .base import USER_AGENT, StrategySource, clean_html

log = logging.getLogger(__name__)

_OZB_NS = "https://www.ozbargain.com.au"
_NODE_RE = re.compile(r"/node/(\d+)")


class OzBargainTagSource(StrategySource):
    name = "ozbargain_tag"

    def __init__(
        self,
        tags: list[str],
        request_delay_seconds: float = 2.0,
        timeout: float = 20.0,
    ) -> None:
        self.tags = tags
        self.request_delay_seconds = request_delay_seconds
        self.timeout = timeout

    def fetch(self) -> list[CapturedPost]:
        now = datetime.now(UTC)
        posts: list[CapturedPost] = []
        for i, tag in enumerate(self.tags):
            if i:
                time.sleep(self.request_delay_seconds + random.uniform(0, 1))
            url = f"https://www.ozbargain.com.au/tag/{tag}/feed"
            try:
                resp = httpx.get(
                    url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=self.timeout,
                    follow_redirects=True,
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("ozbargain_tag: skipping tag '%s' — %s", tag, exc)
                continue
            posts.extend(self.parse(resp.text, tag=tag, now=now))
        return posts

    def parse(
        self, xml: str, tag: str, now: datetime | None = None
    ) -> list[CapturedPost]:
        """Parse an OzBargain tag RSS feed into CapturedPosts (no network)."""
        now = now or datetime.now(UTC)
        root = ET.fromstring(xml)
        channel = root.find("channel")
        if channel is None:
            return []
        posts: list[CapturedPost] = []
        for item in channel.findall("item"):
            link = (item.findtext("link") or "").strip()
            title = (item.findtext("title") or "").strip()
            m = _NODE_RE.search(link)
            if not m or not title:
                continue
            body = clean_html(item.findtext("description") or "")
            meta = item.find(f"{{{_OZB_NS}}}meta")
            num_comments: int | None = None
            score: int | None = None
            if meta is not None:
                with contextlib.suppress(TypeError, ValueError):
                    num_comments = int(meta.get("comment-count") or 0)
                with contextlib.suppress(TypeError, ValueError):
                    score = int(meta.get("votes-pos") or 0)
            posts.append(
                CapturedPost(
                    source=self.name,
                    post_id=m.group(1),
                    url=link,
                    title=title,
                    body=body,
                    board=f"OzBargain #{tag}",
                    fetched_at=now,
                    num_comments=num_comments,
                    score=score,
                )
            )
        return posts
