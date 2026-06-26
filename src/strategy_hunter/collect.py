"""Orchestrates one collection run: fetch all enabled sources, filter by
relevance, persist new/changed posts to the raw corpus, and write the digest.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from .cleanup import prune_corpus
from .config import StrategyConfig
from .digest import write_digest
from .models import CapturedPost
from .relevance import relevance_score
from .sources import (
    OzBargainCommentsSource,
    OzBargainForumSource,
    RedditSource,
    StrategySource,
    WhirlpoolSource,
)
from .store import PostStore

log = logging.getLogger(__name__)


def build_sources(cfg: StrategyConfig) -> list[StrategySource]:
    """Instantiate the enabled sources from config."""
    sources: list[StrategySource] = []
    s = cfg.sources
    if s.reddit.enabled:
        sources.append(
            RedditSource(
                subreddits=s.reddit.subreddits,
                listing=s.reddit.listing,
                limit=s.reddit.limit,
                request_delay_seconds=max(cfg.request_delay_seconds, 2.0),
            )
        )
    if s.ozbargain_forum.enabled:
        sources.append(
            OzBargainForumSource(
                board_urls=s.ozbargain_forum.board_urls,
                max_threads_per_board=s.ozbargain_forum.max_threads_per_board,
                fetch_body=s.ozbargain_forum.fetch_body,
                request_delay_seconds=cfg.request_delay_seconds,
            )
        )
    if s.ozbargain_comments.enabled:
        sources.append(
            OzBargainCommentsSource(
                feed_url=s.ozbargain_comments.feed_url,
                min_comments=s.ozbargain_comments.min_comments,
                max_deals=s.ozbargain_comments.max_deals,
                request_delay_seconds=cfg.request_delay_seconds,
            )
        )
    if s.whirlpool.enabled:
        sources.append(
            WhirlpoolSource(
                board_urls=s.whirlpool.board_urls,
                max_threads_per_board=s.whirlpool.max_threads_per_board,
                fetch_body=s.whirlpool.fetch_body,
                request_delay_seconds=cfg.request_delay_seconds,
            )
        )
    return sources


def collect(cfg: StrategyConfig, now: datetime | None = None) -> dict:
    """Run one full collection pass. Returns a summary dict (counts only)."""
    now = now or datetime.now(UTC)
    summary: dict = {
        "fetched": 0,
        "relevant": 0,
        "new": 0,
        "pruned": 0,
        "errors": [],
        "digest": None,
    }

    store = PostStore(Path(cfg.raw_dir))
    new_posts: list[CapturedPost] = []

    for src in build_sources(cfg):
        try:
            posts = src.fetch()
        except Exception as exc:  # one bad source must not sink the run
            msg = f"{src.name} fetch failed: {exc}"
            log.error(msg)
            summary["errors"].append(msg)
            continue
        log.info("%s: fetched %d posts.", src.name, len(posts))
        summary["fetched"] += len(posts)

        for post in posts:
            post.relevance = relevance_score(f"{post.title}\n{post.body}")
            if post.relevance < cfg.min_relevance:
                continue
            summary["relevant"] += 1
            if store.save(post):
                new_posts.append(post)

    summary["new"] = len(new_posts)
    digest_path = write_digest(new_posts, Path(cfg.digest_dir), now)
    if digest_path is not None:
        summary["digest"] = str(digest_path)

    pruned = prune_corpus(Path(cfg.raw_dir), cfg.retention_days, now)
    summary["pruned"] = len(pruned)

    log.info(
        "Collection complete. fetched=%d relevant=%d new=%d pruned=%d errors=%d",
        summary["fetched"], summary["relevant"], summary["new"],
        summary["pruned"], len(summary["errors"]),
    )
    return summary


def load_all_posts(raw_dir: Path) -> list[CapturedPost]:
    """Load every stored post from the raw corpus (used to rebuild a digest)."""
    posts: list[CapturedPost] = []
    if not raw_dir.exists():
        return posts
    for path in sorted(raw_dir.glob("*/*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            posts.append(CapturedPost.model_validate(data))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            log.warning("Skipping unreadable %s: %s", path, exc)
    return posts
