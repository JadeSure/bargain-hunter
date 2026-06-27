"""Configuration: typed settings loaded from YAML, plus environment helpers."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = REPO_ROOT / "config" / "settings.yaml"


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ (no extra deps).

    Only sets keys that are not already present — real env vars always win
    (so GitHub Actions Secrets override .env transparently).
    """
    env_path = path or REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


class StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HotTier(StrictConfigModel):
    """One rung of the hot ladder.

    A deal earns the highest tier whose ``min_score`` it meets and whose optional
    value gates (``min_votes`` / ``min_discount_percent``) it passes. ``min_score``
    is the weighted hot velocity score; the value gates let a tier (e.g. ``top``)
    demand genuine savings rather than velocity alone.
    """

    name: str
    min_score: float
    min_discount_percent: float | None = None
    min_votes: int | None = None


class HotConfig(StrictConfigModel):
    min_votes_gain_per_window: int = 15
    early_burst_age_hours: float = 2.0
    early_burst_min_votes: int = 25
    velocity_top_percent: float = 10.0
    hot_threshold: float = 1.0
    neg_vote_penalty_weight: float = 0.5
    age_penalty_half_life_hours: float = 12.0
    min_votes_for_percentile: int = 5
    # Absolute minimum votes before a deal is even considered for hot candidacy.
    min_votes_to_candidate: int = 10
    # Weight applied to comment velocity in the hot score formula.
    comment_velocity_weight: float = 0.25
    # Quality gate: deals with fewer votes than quality_high_votes_threshold must have
    # a discount_percent >= quality_min_discount_pct to be sent.
    # Data-backed: promo/food/membership deals (~22-38 votes, no discount) are filtered
    # while genuine discounted products (8+ votes, 20%+ off) still get through.
    # Set to None to disable.
    quality_min_discount_pct: float | None = None
    quality_high_votes_threshold: int = 40
    # Hot ladder: ordered tiers (sorted best-first by effective_tiers()). When
    # empty, a single "hot" tier is synthesised from hot_threshold so existing
    # single-threshold behaviour is preserved.
    tiers: list[HotTier] = Field(default_factory=list)
    # When True, the top tier bypasses category filtering and reaches every hot
    # subscriber (the universal best-of-best). When False, every tier — including
    # top — is restricted to a subscriber's chosen categories.
    universal_top: bool = True


def effective_tiers(hot: HotConfig) -> list[HotTier]:
    """Return the hot ladder sorted best-first (highest ``min_score`` first).

    Falls back to a single ``"hot"`` tier derived from ``hot_threshold`` when no
    tiers are configured, so callers can treat the ladder uniformly.
    """
    if hot.tiers:
        return sorted(hot.tiers, key=lambda t: t.min_score, reverse=True)
    return [HotTier(name="hot", min_score=hot.hot_threshold)]


class WatchConfig(StrictConfigModel):
    min_votes: int = 5
    # Fallback gate for sources with no vote system (e.g. CamelCamelCamel).
    # When set, a deal with discount_percent >= this value passes even with 0 votes.
    min_discount_percent: float | None = None
    # Skip watch matches for deals older than this (hours from posted_at).
    # Prevents stale deals from consuming the daily cap. Deals with no posted_at are exempt.
    max_deal_age_hours: float = 48.0


class ScoringConfig(StrictConfigModel):
    window_minutes: int = 60
    hot: HotConfig = Field(default_factory=HotConfig)
    watch: WatchConfig = Field(default_factory=WatchConfig)


class SourceConfig(BaseModel):
    """Per-source config. Extra keys (e.g. feed_url) are preserved."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = False


class DedupConfig(StrictConfigModel):
    lookback_days: int = 7
    max_realerts_per_deal: int = 1
    significant_price_drop_percent: float = 5.0
    heat_band_size_votes: int = 50


class ColdStartConfig(StrictConfigModel):
    ignore_deals_older_than_hours: float = 6.0


class AlertConfig(StrictConfigModel):
    min_consecutive_failures: int = 3
    cooldown_hours: float = 1.0


class RunConfig(StrictConfigModel):
    dry_run: bool = False
    max_alerts_per_user_per_day: int = 10
    timezone: str = "Australia/Sydney"
    # Quiet hours: no sends outside this window (both in "HH:MM" local time).
    # If start > end, the window wraps midnight (e.g. 22:00–07:00).
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None


class Settings(StrictConfigModel):
    run: RunConfig = Field(default_factory=RunConfig)
    sources: dict[str, SourceConfig] = Field(default_factory=dict)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    dedup: DedupConfig = Field(default_factory=DedupConfig)
    cold_start: ColdStartConfig = Field(default_factory=ColdStartConfig)
    alerting: AlertConfig = Field(default_factory=AlertConfig)
    # Consumed by the separate strategy_hunter pipeline (it has its own loader);
    # accepted here so the shared settings.yaml validates under this strict model.
    strategy: dict[str, Any] | None = None
    # Category taxonomy: bucket id -> match terms. Routes hot deals to subscribers
    # by their chosen interest buckets. Optional; absent = no category routing.
    categories: dict[str, list[str]] | None = None


def load_settings(path: Path | None = None) -> Settings:
    """Load settings.yaml into a typed Settings object (falls back to defaults)."""
    path = path or DEFAULT_SETTINGS_PATH
    if not path.exists():
        return Settings()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Settings.model_validate(data)


def env(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    """Read an environment variable, optionally raising if missing."""
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
