"""Reddit source: parses subreddit Atom feeds (``/r/<sub>/<listing>.rss``).

Reddit's JSON API now returns 403 to non-OAuth clients, but the public Atom
feed is still served — to a *browser* User-Agent. We therefore use the RSS feed
and a browser UA. The feed carries the post title, selftext (as escaped HTML in
<content>), author, permalink and timestamps, which is plenty for Stage 1.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import httpx
from defusedxml import ElementTree as ET

from ..models import CapturedPost
from .base import BROWSER_UA, StrategySource, clean_html

_ATOM = "{http://www.w3.org/2005/Atom}"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class RedditSource(StrategySource):
    name = "reddit"

    def __init__(
        self,
        subreddits: list[str],
        listing: str = "hot",
        limit: int = 25,
        request_delay_seconds: float = 2.0,
        timeout: float = 20.0,
    ) -> None:
        self.subreddits = subreddits
        self.listing = listing
        self.limit = limit
        self.request_delay_seconds = request_delay_seconds
        self.timeout = timeout

    def fetch(self) -> list[CapturedPost]:
        posts: list[CapturedPost] = []
        now = datetime.now(UTC)
        for i, sub in enumerate(self.subreddits):
            if i:
                time.sleep(self.request_delay_seconds)  # avoid Reddit rate limiting
            url = f"https://www.reddit.com/r/{sub}/{self.listing}.rss?limit={self.limit}"
            resp = httpx.get(
                url,
                headers={"User-Agent": BROWSER_UA},
                timeout=self.timeout,
                follow_redirects=True,
            )
            resp.raise_for_status()
            posts.extend(self.parse(resp.text, subreddit=sub, now=now))
        return posts

    def parse(
        self, xml: str, subreddit: str, now: datetime | None = None
    ) -> list[CapturedPost]:
        now = now or datetime.now(UTC)
        root = ET.fromstring(xml)
        posts: list[CapturedPost] = []
        for entry in root.findall(f"{_ATOM}entry"):
            post = self._parse_entry(entry, subreddit, now)
            if post is not None:
                posts.append(post)
        return posts

    def _parse_entry(self, entry, subreddit: str, now: datetime) -> CapturedPost | None:
        title = (entry.findtext(f"{_ATOM}title") or "").strip()
        link_el = entry.find(f"{_ATOM}link")
        url = link_el.get("href") if link_el is not None else ""
        if not title or not url:
            return None

        raw_id = (entry.findtext(f"{_ATOM}id") or "").strip()
        post_id = raw_id.split("_", 1)[1] if "_" in raw_id else (raw_id or url)

        author_el = entry.find(f"{_ATOM}author")
        author = author_el.findtext(f"{_ATOM}name") if author_el is not None else None

        body = clean_html(entry.findtext(f"{_ATOM}content"))
        created = _parse_dt(entry.findtext(f"{_ATOM}published"))

        return CapturedPost(
            source=self.name,
            post_id=post_id,
            url=url,
            title=title,
            author=author,
            body=body,
            board=f"r/{subreddit}",
            created_at=created,
            fetched_at=now,
        )
