"""Orchestrates one onboarding collection run: fetch enabled sources, filter by
relevance, persist new posts to the raw corpus, and write the digest.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from ..cleanup import prune_corpus
from ..config import StrategyConfig
from ..digest import write_digest
from ..models import CapturedPost
from ..sources import RedditSource, StrategySource
from ..sources.ozbargain_tags import OzBargainTagSource
from ..store import PostStore
from .relevance import onboarding_relevance_score

log = logging.getLogger(__name__)


def build_onboarding_sources(cfg: StrategyConfig) -> list[StrategySource]:
    """Instantiate the enabled onboarding sources from config."""
    sources: list[StrategySource] = []
    s = cfg.onboarding.sources
    if s.ozbargain_tags.enabled:
        sources.append(
            OzBargainTagSource(
                tags=s.ozbargain_tags.tags,
                request_delay_seconds=cfg.onboarding.request_delay_seconds,
            )
        )
    if s.reddit.enabled:
        sources.append(
            RedditSource(
                subreddits=s.reddit.subreddits,
                listing=s.reddit.listing,
                limit=s.reddit.limit,
                request_delay_seconds=max(
                    s.reddit.request_delay_seconds, cfg.onboarding.request_delay_seconds
                ),
                max_retries=s.reddit.max_retries,
                max_backoff_seconds=s.reddit.max_backoff_seconds,
            )
        )
    return sources


def collect_onboarding(cfg: StrategyConfig, now: datetime | None = None) -> dict:
    """Run one full onboarding collection pass. Returns a summary dict."""
    now = now or datetime.now(UTC)
    summary: dict = {
        "fetched": 0,
        "relevant": 0,
        "new": 0,
        "pruned": 0,
        "errors": [],
        "digest": None,
    }

    store = PostStore(Path(cfg.onboarding.raw_dir))
    new_posts: list[CapturedPost] = []

    for src in build_onboarding_sources(cfg):
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
            post.relevance = onboarding_relevance_score(f"{post.title}\n{post.body}")
            if post.relevance < cfg.onboarding.min_relevance:
                continue
            summary["relevant"] += 1
            if store.save(post):
                new_posts.append(post)

    summary["new"] = len(new_posts)
    digest_path = write_digest(
        new_posts,
        Path(cfg.onboarding.digest_dir),
        now,
        title="Newcomer onboarding material digest",
        prompt_ref="prompts/extract_onboarding.md",
    )
    if digest_path is not None:
        summary["digest"] = str(digest_path)

    pruned = prune_corpus(Path(cfg.onboarding.raw_dir), cfg.onboarding.retention_days, now)
    summary["pruned"] = len(pruned)

    log.info(
        "Onboarding collection complete. fetched=%d relevant=%d new=%d pruned=%d errors=%d",
        summary["fetched"],
        summary["relevant"],
        summary["new"],
        summary["pruned"],
        len(summary["errors"]),
    )
    return summary


def load_all_onboarding_posts(raw_dir: Path) -> list[CapturedPost]:
    """Load every stored onboarding post from the raw corpus."""
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
