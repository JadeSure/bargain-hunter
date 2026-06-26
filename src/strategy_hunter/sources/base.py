"""Source adapter interface for the strategy pipeline.

Each source harvests free-text discussion and normalises it into
``CapturedPost`` objects. Parsing is split from fetching (a ``parse_*`` method
on plain text) so it can be unit-tested against frozen fixtures without network.
"""

from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod

from ..models import CapturedPost

USER_AGENT = (
    "bargain-hunter/0.1 (personal money-saving guide collector; "
    "+https://github.com/versent-shawn/bargain-hunter)"
)
# Reddit blocks the bot UA above on its JSON/RSS endpoints; a browser UA is
# required there (RSS is allowed, JSON is not).
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u00a0]+")


def clean_html(value: str | None, *, max_len: int = 8000) -> str:
    """Strip HTML tags + entities and collapse whitespace into plain text.

    Newlines are preserved (paragraph structure helps the LLM); runs of spaces
    are collapsed. Output is truncated to ``max_len`` chars to bound corpus size.
    """
    if not value:
        return ""
    text = _TAG_RE.sub(" ", value)
    text = html.unescape(text)
    lines = [_WS_RE.sub(" ", ln).strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rstrip() + " …"
    return text


class StrategySource(ABC):
    """A pluggable source of money-saving discussion."""

    name: str

    @abstractmethod
    def fetch(self) -> list[CapturedPost]:
        """Return posts currently visible from this source."""
        ...
