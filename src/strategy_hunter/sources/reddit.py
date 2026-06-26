"""Reddit source.

Two transports, chosen at runtime:

* **OAuth JSON API** (preferred, works from datacenter IPs like GitHub Actions):
  used when ``REDDIT_CLIENT_ID`` / ``REDDIT_CLIENT_SECRET`` are set. Reddit's
  app-only OAuth allows ~100 requests/min from cloud IPs, where the public feeds
  are blocked.
* **Public Atom RSS** (fallback, no credentials): ``/r/<sub>/<listing>.rss`` with
  a browser User-Agent. Works from residential IPs but Reddit reliably returns
  ``429`` to cloud/datacenter ranges.

Either way a single blocked/rate-limited subreddit is skipped (logged at
WARNING) rather than failing the whole run — Reddit availability is an external
condition, not a code error.
"""

from __future__ import annotations

import logging
import os
import random
import time
from datetime import UTC, datetime

import httpx
from defusedxml import ElementTree as ET

from ..models import CapturedPost
from .base import BROWSER_UA, StrategySource, clean_html

log = logging.getLogger(__name__)

_ATOM = "{http://www.w3.org/2005/Atom}"
_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_OAUTH_BASE = "https://oauth.reddit.com"


class RedditUnavailable(Exception):
    """A subreddit could not be fetched (rate-limited / blocked / network)."""


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
        max_retries: int = 2,
    ) -> None:
        self.subreddits = subreddits
        self.listing = listing
        self.limit = limit
        self.request_delay_seconds = request_delay_seconds
        self.timeout = timeout
        self.max_retries = max_retries
        self._token: str | None = None

    # -- transport ------------------------------------------------------------

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """One request with bounded 429 retries honouring Retry-After.

        Raises RedditUnavailable if still rate-limited after retries or on a
        network error, so the caller can skip just this subreddit.
        """
        for attempt in range(self.max_retries + 1):
            try:
                resp = httpx.request(
                    method, url, timeout=self.timeout, follow_redirects=True, **kwargs
                )
            except httpx.HTTPError as exc:
                raise RedditUnavailable(str(exc)) from exc
            if resp.status_code == 429:
                if attempt >= self.max_retries:
                    raise RedditUnavailable("429 Too Many Requests (rate limited)")
                time.sleep(min(self._retry_after(resp, attempt), 30.0))
                continue
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RedditUnavailable(str(exc)) from exc
            return resp
        raise RedditUnavailable("exhausted retries")

    @staticmethod
    def _retry_after(resp: httpx.Response, attempt: int) -> float:
        header = resp.headers.get("Retry-After")
        if header:
            try:
                return float(header)
            except ValueError:
                pass
        return 2.0**attempt + random.uniform(0, 1)  # exponential backoff + jitter

    def _get_token(self) -> str | None:
        """Fetch an app-only OAuth token if credentials are configured."""
        if self._token is not None:
            return self._token
        client_id = os.environ.get("REDDIT_CLIENT_ID")
        client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
        if not client_id or not client_secret:
            return None
        try:
            resp = self._request(
                "POST",
                _TOKEN_URL,
                auth=(client_id, client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": self._user_agent()},
            )
            self._token = resp.json().get("access_token")
        except (RedditUnavailable, ValueError) as exc:
            log.warning("reddit: OAuth token fetch failed, falling back to RSS: %s", exc)
            self._token = None
        return self._token

    @staticmethod
    def _user_agent() -> str:
        return os.environ.get(
            "REDDIT_USER_AGENT",
            "bargain-hunter/0.1 (+https://github.com/versent-shawn/bargain-hunter)",
        )

    # -- fetch ----------------------------------------------------------------

    def fetch(self) -> list[CapturedPost]:
        posts: list[CapturedPost] = []
        now = datetime.now(UTC)
        token = self._get_token()
        for i, sub in enumerate(self.subreddits):
            if i:
                time.sleep(self.request_delay_seconds)  # be polite between subs
            try:
                if token:
                    posts.extend(self._fetch_oauth(sub, token, now))
                else:
                    posts.extend(self._fetch_rss(sub, now))
            except RedditUnavailable as exc:
                log.warning("reddit: skipping r/%s — %s", sub, exc)
        return posts

    def _fetch_rss(self, sub: str, now: datetime) -> list[CapturedPost]:
        url = f"https://www.reddit.com/r/{sub}/{self.listing}.rss?limit={self.limit}"
        resp = self._request("GET", url, headers={"User-Agent": BROWSER_UA})
        return self.parse(resp.text, subreddit=sub, now=now)

    def _fetch_oauth(self, sub: str, token: str, now: datetime) -> list[CapturedPost]:
        url = f"{_OAUTH_BASE}/r/{sub}/{self.listing}?limit={self.limit}"
        resp = self._request(
            "GET",
            url,
            headers={"Authorization": f"bearer {token}", "User-Agent": self._user_agent()},
        )
        return self.parse_json(resp.json(), subreddit=sub, now=now)

    # -- parsing (testable, no network) ---------------------------------------

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

    def parse_json(
        self, data: dict, subreddit: str, now: datetime | None = None
    ) -> list[CapturedPost]:
        now = now or datetime.now(UTC)
        posts: list[CapturedPost] = []
        for child in data.get("data", {}).get("children", []):
            d = child.get("data", {})
            title = (d.get("title") or "").strip()
            post_id = d.get("id") or ""
            if not title or not post_id:
                continue
            permalink = d.get("permalink") or ""
            url = f"https://www.reddit.com{permalink}" if permalink else d.get("url", "")
            created = d.get("created_utc")
            posts.append(
                CapturedPost(
                    source=self.name,
                    post_id=post_id,
                    url=url,
                    title=title,
                    author=d.get("author"),
                    body=clean_html(d.get("selftext") or ""),
                    board=f"r/{subreddit}",
                    created_at=(datetime.fromtimestamp(created, UTC) if created else None),
                    fetched_at=now,
                    score=d.get("score"),
                    num_comments=d.get("num_comments"),
                )
            )
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
