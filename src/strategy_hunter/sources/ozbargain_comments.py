"""OzBargain deal-comments source: harvests stacking tips from deal discussions.

The community comment threads under OzBargain *deals* are where people share how
to combine techniques ("stack with the 10%-off gift cards + Cashrewards 3%").
That is exactly the raw material for guides, but the comment RSS feed returns
403, so we read the deals feed for busy deals, then scrape each deal's node page.

One ``CapturedPost`` is produced per deal (not per comment): its body is the
deal title plus the concatenated comments. Aggregating keeps the deal context
with its discussion, lets the relevance filter judge the whole thread, and makes
``content_hash`` dedup re-capture a deal naturally as new comments arrive.
"""

from __future__ import annotations

import contextlib
import re
import time
from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup
from defusedxml import ElementTree as ET

from ..models import CapturedPost
from .base import USER_AGENT, StrategySource, clean_html

_OZB_NS = "https://www.ozbargain.com.au"
_NODE_RE = re.compile(r"/node/(\d+)")
_COMMENT_ID_RE = re.compile(r"^comment-\d+")
_USER_HREF_RE = re.compile(r"^/user/\d+")
# A single comment that's too short is noise ("Bought. Thanks OP"); skip it.
_MIN_COMMENT_LEN = 40


class OzBargainCommentsSource(StrategySource):
    name = "ozbargain_comments"

    def __init__(
        self,
        feed_url: str = "https://www.ozbargain.com.au/deals/feed",
        min_comments: int = 10,
        max_deals: int = 15,
        request_delay_seconds: float = 1.0,
        timeout: float = 20.0,
    ) -> None:
        self.feed_url = feed_url
        self.min_comments = min_comments
        self.max_deals = max_deals
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
        deals = self.parse_deal_list(self._get(self.feed_url))
        # Busiest discussions first; these carry the most stacking talk.
        deals = sorted(deals, key=lambda d: d[2], reverse=True)
        posts: list[CapturedPost] = []
        for node_id, title, comment_count, url in deals:
            if comment_count < self.min_comments:
                continue
            if len(posts) >= self.max_deals:
                break
            time.sleep(self.request_delay_seconds)
            comments: list[tuple[str | None, datetime | None, str]] = []
            with contextlib.suppress(httpx.HTTPError):
                comments = self.parse_node_comments(self._get(url))
            body = self._build_body(title, comments)
            posts.append(
                CapturedPost(
                    source=self.name,
                    post_id=node_id,
                    url=url,
                    title=title,
                    body=body,
                    board="OzBargain Deals (comments)",
                    fetched_at=now,
                    num_comments=comment_count,
                )
            )
        return posts

    # -- Parsing (testable, no network) ---------------------------------------

    def parse_deal_list(self, xml: str) -> list[tuple[str, str, int, str]]:
        """Return [(node_id, title, comment_count, url), ...] from the deals feed."""
        root = ET.fromstring(xml)
        channel = root.find("channel")
        if channel is None:
            return []
        out: list[tuple[str, str, int, str]] = []
        for item in channel.findall("item"):
            link = (item.findtext("link") or "").strip()
            title = (item.findtext("title") or "").strip()
            m = _NODE_RE.search(link)
            if not m or not title:
                continue
            meta = item.find(f"{{{_OZB_NS}}}meta")
            cc = 0
            if meta is not None:
                with contextlib.suppress(TypeError, ValueError):
                    cc = int(meta.get("comment-count") or 0)
            out.append((m.group(1), title, cc, link))
        return out

    def parse_node_comments(
        self, html: str
    ) -> list[tuple[str | None, datetime | None, str]]:
        """Return [(author, posted_at, body), ...] for a deal node page."""
        soup = BeautifulSoup(html, "html.parser")
        results: list[tuple[str | None, datetime | None, str]] = []
        for wrap in soup.find_all("div", class_="comment-wrap", id=_COMMENT_ID_RE):
            content = wrap.find("div", class_="content")
            body = clean_html(str(content)) if content else ""
            if len(body) < _MIN_COMMENT_LEN:
                continue
            user_el = wrap.find("a", href=_USER_HREF_RE)
            author = user_el.get_text(strip=True) if user_el else None
            inner = wrap.find("div", class_="comment")
            posted_at = None
            if inner is not None and inner.get("data-ts"):
                with contextlib.suppress(ValueError, OverflowError):
                    posted_at = datetime.fromtimestamp(int(inner["data-ts"]), UTC)
            results.append((author, posted_at, body))
        return results

    @staticmethod
    def _build_body(
        title: str, comments: list[tuple[str | None, datetime | None, str]]
    ) -> str:
        """Concatenate comments into one body, each attributed to its author."""
        lines = [f"Deal: {title}", ""]
        for author, _ts, body in comments:
            who = author or "anon"
            lines.append(f"[{who}] {body}")
        return "\n".join(lines).strip()
