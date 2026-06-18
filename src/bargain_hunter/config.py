"""Configuration: typed settings loaded from YAML, plus environment helpers."""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = REPO_ROOT / "config" / "settings.yaml"


class StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HotConfig(StrictConfigModel):
    min_votes_gain_per_window: int = 15
    early_burst_age_hours: float = 2.0
    early_burst_min_votes: int = 25
    velocity_top_percent: float = 10.0
    hot_threshold: float = 1.0
    neg_vote_penalty_weight: float = 0.5
    age_penalty_half_life_hours: float = 12.0
    min_votes_for_percentile: int = 5


class WatchConfig(StrictConfigModel):
    default_min_discount_percent: float = 15.0
    unpriced_min_votes: int = 5


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


class RunConfig(StrictConfigModel):
    dry_run: bool = False
    max_alerts_per_user_per_day: int = 10
    timezone: str = "Australia/Sydney"


class Settings(StrictConfigModel):
    run: RunConfig = Field(default_factory=RunConfig)
    sources: dict[str, SourceConfig] = Field(default_factory=dict)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    dedup: DedupConfig = Field(default_factory=DedupConfig)
    cold_start: ColdStartConfig = Field(default_factory=ColdStartConfig)


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
