"""OzBargain forum source: harvests discussion threads from forum boards.

OzBargain's *deal* feed is consumed by ``bargain_hunter``; here we target the
*forum* boards (e.g. "Find Me A Bargain", "Financial") where members ask and
answer "what's the cheapest way to buy X" — the raw material for stacking
guides. There is no forum RSS and the comment feed is blocked, so we parse the
board listing HTML for thread links, then each thread page for the OP body.
"""

from __future__ import annotations

import contextlib
import re
import time
from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup

from ..models import CapturedPost
from .base import USER_AGENT, StrategySource, clean_html

_NODE_HREF_RE = re.compile(r"^/node/(\d+)$")


class OzBargainForumSource(StrategySource):
    name = "ozbargain_forum"
    BASE = "https://www.ozbargain.com.au"

    def __init__(
        self,
        board_urls: list[str],
        max_threads_per_board: int = 25,
        fetch_body: bool = True,
        request_delay_seconds: float = 1.0,
        timeout: float = 20.0,
    ) -> None:
        self.board_urls = board_urls
        self.max_threads_per_board = max_threads_per_board
        self.fetch_body = fetch_body
        self.request_delay_seconds = request_delay_seconds
        self.timeout = timeout

    # -- HTTP -----------------------------------------------------------------

    def _get(self, url: str) -> str:
        resp = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=self.timeout,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text

    def fetch(self) -> list[CapturedPost]:
        now = datetime.now(UTC)
        posts: list[CapturedPost] = []
        for board_url in self.board_urls:
            board_html = self._get(board_url)
            board_name, topics = self.parse_board(board_html)
            for post_id, title, href in topics[: self.max_threads_per_board]:
                url = href if href.startswith("http") else self.BASE + href
                post = CapturedPost(
                    source=self.name,
                    post_id=post_id,
                    url=url,
                    title=title,
                    board=board_name,
                    fetched_at=now,
                )
                if self.fetch_body:
                    time.sleep(self.request_delay_seconds)
                    with contextlib.suppress(httpx.HTTPError):
                        post.body = self.parse_thread(self._get(url))
                posts.append(post)
        return posts

    # -- Parsing (testable, no network) ---------------------------------------

    def parse_board(self, html: str) -> tuple[str | None, list[tuple[str, str, str]]]:
        """Return (board_name, [(post_id, title, href), ...]) for a board page."""
        soup = BeautifulSoup(html, "html.parser")
        board_name = None
        if soup.title and soup.title.string:
            board_name = soup.title.string.split(":", 1)[0].strip() or None

        topics: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=_NODE_HREF_RE):
            href = a.get("href", "")
            m = _NODE_HREF_RE.match(href)
            title = a.get_text(strip=True)
            if not m or not title or href in seen:
                continue
            seen.add(href)
            topics.append((m.group(1), title, href))
        return board_name, topics

    def parse_thread(self, html: str) -> str:
        """Return the original post body text from a thread page."""
        soup = BeautifulSoup(html, "html.parser")
        content = soup.find("div", class_="content")
        return clean_html(str(content)) if content else ""
