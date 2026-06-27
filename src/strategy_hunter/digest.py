"""Builds the LLM-ready digest from newly captured posts.

The digest is a single Markdown file the maintainer feeds to a local model
(alongside ``prompts/extract_guide.md``) in Stage 2. Posts are grouped by board
and sorted by relevance so the highest-signal material is read first. Bodies are
truncated to keep the whole digest within a comfortable context window.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import CapturedPost

log = logging.getLogger(__name__)

_AET = ZoneInfo("Australia/Sydney")
_BODY_EXCERPT = 1500


def build_digest_markdown(posts: list[CapturedPost], date_label: str) -> str:
    """Render captured posts into a single Markdown digest string."""
    lines: list[str] = [
        f"# Strategy guide material digest — {date_label}",
        "",
        (
            f"{len(posts)} new posts. Use the schema in `prompts/extract_guide.md` "
            "to extract structured guides."
        ),
        "",
    ]

    by_board: dict[str, list[CapturedPost]] = {}
    for p in posts:
        by_board.setdefault(p.board or p.source, []).append(p)

    for board in sorted(by_board):
        items = sorted(by_board[board], key=lambda p: p.relevance, reverse=True)
        lines.append(f"## {board} ({len(items)})")
        lines.append("")
        for p in items:
            lines.append(f"### {p.title}")
            meta = f"- source: {p.source} · relevance {p.relevance} · <{p.url}>"
            if p.created_at:
                meta += f" · {p.created_at.date()}"
            lines.append(meta)
            body = p.body.strip()
            if len(body) > _BODY_EXCERPT:
                body = body[:_BODY_EXCERPT].rstrip() + " …"
            if body:
                lines.append("")
                lines.append(body)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_digest(
    posts: list[CapturedPost], digest_dir: Path, now: datetime
) -> Path | None:
    """Write today's digest Markdown. Returns the path, or None if no posts."""
    if not posts:
        return None
    date_label = now.astimezone(_AET).strftime("%Y-%m-%d")
    digest_dir.mkdir(parents=True, exist_ok=True)
    path = digest_dir / f"{date_label}.md"
    path.write_text(build_digest_markdown(posts, date_label), encoding="utf-8")
    log.info("Wrote digest with %d posts to %s", len(posts), path)
    return path
