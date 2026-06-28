"""Typed configuration for the strategy pipeline, read from the ``strategy:``
section of ``config/settings.yaml`` (same file as bargain_hunter)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = REPO_ROOT / "config" / "settings.yaml"


class StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OzbForumConfig(StrictConfigModel):
    enabled: bool = True
    # Forum board listing pages to harvest. Defaults target the boards richest in
    # "how to buy X cheaply" / stacking discussion.
    board_urls: list[str] = Field(
        default_factory=lambda: [
            "https://www.ozbargain.com.au/forum/1341",   # Find Me A Bargain
            "https://www.ozbargain.com.au/forum/38183",  # Financial
        ]
    )
    max_threads_per_board: int = 25
    fetch_body: bool = True           # fetch each relevant thread's OP body


class OzbCommentsConfig(StrictConfigModel):
    enabled: bool = True
    feed_url: str = "https://www.ozbargain.com.au/deals/feed"
    min_comments: int = 10            # only mine deals with at least this many comments
    max_deals: int = 15               # cap node-page fetches per run


class RedditConfig(StrictConfigModel):
    enabled: bool = True
    subreddits: list[str] = Field(
        default_factory=lambda: ["AusFinance", "AusFrugal", "fiaustralia"]
    )
    listing: str = "hot"              # hot | new | top
    limit: int = 25
    # Reddit rate-limits unauthenticated feed requests from datacenter IPs (CI).
    # Pace requests and back off patiently so subsequent subreddits still get
    # through. Tune these up if you still see 429s in Actions logs.
    request_delay_seconds: float = 6.0   # gap between subreddit requests
    max_retries: int = 4                 # retries on a 429 before giving up
    max_backoff_seconds: float = 90.0    # cap on any single backoff/Retry-After wait


class WhirlpoolConfig(StrictConfigModel):
    enabled: bool = True
    board_urls: list[str] = Field(
        default_factory=lambda: [
            "https://forums.whirlpool.net.au/forum/153",  # Shopping
            "https://forums.whirlpool.net.au/forum/150",  # Finance
            "https://forums.whirlpool.net.au/forum/149",  # Travel
        ]
    )
    max_threads_per_board: int = 25
    fetch_body: bool = True


class StrategySourcesConfig(StrictConfigModel):
    ozbargain_forum: OzbForumConfig = Field(default_factory=OzbForumConfig)
    ozbargain_comments: OzbCommentsConfig = Field(default_factory=OzbCommentsConfig)
    reddit: RedditConfig = Field(default_factory=RedditConfig)
    whirlpool: WhirlpoolConfig = Field(default_factory=WhirlpoolConfig)


class OzbTagConfig(StrictConfigModel):
    enabled: bool = True
    tags: list[str] = Field(default_factory=lambda: ["referral", "cashback"])


class OnboardingSourcesConfig(StrictConfigModel):
    ozbargain_tags: OzbTagConfig = Field(default_factory=OzbTagConfig)
    reddit: RedditConfig = Field(
        default_factory=lambda: RedditConfig(subreddits=["AusFinance", "AusFrugal"])
    )


class OnboardingConfig(StrictConfigModel):
    enabled: bool = True
    programs_dir: str = "data/strategies/onboarding/programs"
    digest_dir: str = "data/strategies/onboarding/digest"
    raw_dir: str = "data/strategies/onboarding/raw"
    min_relevance: int = 1
    request_delay_seconds: float = 2.0
    retention_days: int = 90
    sources: OnboardingSourcesConfig = Field(default_factory=OnboardingSourcesConfig)


class StrategyConfig(StrictConfigModel):
    enabled: bool = True
    # Minimum money-saving keyword hits for a post to be kept (filters off-topic news).
    min_relevance: int = 1
    # Politeness delay between HTTP requests when fetching thread bodies.
    request_delay_seconds: float = 1.0
    # Drop raw posts older than this many days (0 disables pruning) to bound the corpus.
    retention_days: int = 60
    # Email the maintainer when a collection run errors or harvests nothing.
    alert_on_failure: bool = True
    raw_dir: str = "data/strategies/raw"
    digest_dir: str = "data/strategies/digest"
    guides_dir: str = "data/strategies/guides"
    sources: StrategySourcesConfig = Field(default_factory=StrategySourcesConfig)
    onboarding: OnboardingConfig = Field(default_factory=OnboardingConfig)


def load_strategy_config(path: Path | None = None) -> StrategyConfig:
    """Load the ``strategy:`` section of settings.yaml into a typed object."""
    path = path or DEFAULT_SETTINGS_PATH
    if not path.exists():
        return StrategyConfig()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return StrategyConfig.model_validate(data.get("strategy", {}))
