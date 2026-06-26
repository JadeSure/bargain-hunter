"""Whirlpool forums source: harvests threads from selected boards.

Whirlpool has no public API; we parse the board listing HTML for thread links
(``<a class="title" href="/thread/ID">``) and each thread page for the original
post body (``<div class="replytext bodytext">``, first occurrence = OP).
Boards default to Shopping / Finance / Travel, the richest in money-saving talk.
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

_THREAD_HREF_RE = re.compile(r"^/thread/([0-9a-z]+)$")


class WhirlpoolSource(StrategySource):
    name = "whirlpool"
    BASE = "https://forums.whirlpool.net.au"

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
            board_name, threads = self.parse_board(board_html)
            for thread_id, title, href in threads[: self.max_threads_per_board]:
                url = href if href.startswith("http") else self.BASE + href
                post = CapturedPost(
                    source=self.name,
                    post_id=thread_id,
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
        """Return (board_name, [(thread_id, title, href), ...]) for a board page."""
        soup = BeautifulSoup(html, "html.parser")
        board_name = None
        if soup.title and soup.title.string:
            # "<topic> - <Board> - Whirlpool Forums" → take the board segment
            parts = [p.strip() for p in soup.title.string.split(" - ") if p.strip()]
            board_name = parts[-2] if len(parts) >= 2 else (parts[0] if parts else None)

        threads: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for a in soup.find_all("a", class_="title", href=_THREAD_HREF_RE):
            href = a.get("href", "")
            m = _THREAD_HREF_RE.match(href)
            title = a.get_text(strip=True)
            if not m or not title or href in seen:
                continue
            seen.add(href)
            threads.append((m.group(1), title, href))
        return board_name, threads

    def parse_thread(self, html: str) -> str:
        """Return the original post body text (first post) from a thread page."""
        soup = BeautifulSoup(html, "html.parser")
        body = soup.find("div", class_="replytext")
        return clean_html(str(body)) if body else ""
