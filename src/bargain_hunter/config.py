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


class AdaptiveConfig(StrictConfigModel):
    """Event-day adaptive scoring baseline (site-wide vote velocity index).

    Normalises the fixed absolute vote-velocity gates in `HotConfig` against a
    rolling per-hour site heat baseline so genuinely good deals aren't
    misclassified on event days (Boxing Day, Prime Day) when site-wide
    velocity shifts. Disabled by default; see `heat_ratio` plumbing in
    `scoring.py` / `main.py`.
    """

    enabled: bool = False
    ewma_half_life_days: float = 14.0
    # Percentile of active-deal vote velocities used as the per-run site heat index.
    index_percentile: float = 75.0
    # Minimum sampled deals to compute an index this run.
    min_deals_for_index: int = 5
    # Until the baseline is this old, heat_ratio is forced to 1.0.
    warmup_days: float = 3.0
    ratio_clamp_min: float = 0.5
    ratio_clamp_max: float = 3.0
    # Each run's index sample is clamped to <= this x current bucket EWMA before
    # updating, so an event day can't poison the baseline (only when the bucket
    # already has a value).
    baseline_sample_clamp: float = 3.0
    # Votes/h; below this the bucket baseline is treated as unreliable -> ratio 1.0.
    min_baseline_velocity: float = 0.1


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
    # Sources with no vote signal at all (e.g. CamelCamelCamel, which is a pure
    # price tracker) can never clear the vote-based candidacy gates below, so they
    # get a second, discount-only candidacy path instead. Vote-based sources are
    # untouched by this path.
    voteless_sources: list[str] = Field(default_factory=lambda: ["camelcamelcamel"])
    # Minimum discount % for a voteless-source deal to become a hot candidate.
    # None disables the discount candidacy path entirely.
    discount_candidate_min: float | None = 40.0
    # Age cap for the voteless discount-only candidacy path (hours since
    # posted_at). This is the *only* staleness gate on that path — a deal
    # with no vote signal never ages out via score decay the way vote-based
    # deals do. Global feed sources (dealnews/slickdeals/v2ex/...) return
    # months-to-years-old reposts, and `top` bypasses category routing to
    # every hot subscriber (universal_top), so an ungated old deal at high
    # discount would reach everyone. 48h mirrors early_burst freshness intent
    # while giving global-feed poll cadences (up to 3h) headroom.
    max_voteless_age_hours: float = 48.0
    # Discount % thresholds mapped to hot-ladder tier names, used to classify a
    # voteless-source candidate directly (no hot score is computed for these —
    # there is no velocity signal to score). A tier absent from this mapping is
    # simply unreachable via the discount path.
    discount_tiers: dict[str, float] = Field(
        default_factory=lambda: {"good": 40.0, "great": 55.0, "top": 70.0}
    )
    adaptive: AdaptiveConfig = Field(default_factory=AdaptiveConfig)


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
    # Sources trusted to bypass the votes/discount noise guard entirely (their
    # keyword match is itself the quality guard) — editorially curated or
    # keyword-scoped feeds with no vote system and often no parseable discount.
    trusted_sources: list[str] = Field(default_factory=list)


class ScoringConfig(StrictConfigModel):
    window_minutes: int = 60
    hot: HotConfig = Field(default_factory=HotConfig)
    watch: WatchConfig = Field(default_factory=WatchConfig)


class SourceConfig(BaseModel):
    """Per-source config. Extra keys (e.g. feed_url) are preserved."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = False


class CashbackConfig(StrictConfigModel):
    """Merchant→cashback-rate map, stacked on top of matching deals.

    ``rates`` is keyed by merchant domain (e.g. ``amazon.com.au``) → headline
    "up to" cashback percent. A deal matches when its merchant host equals a key
    or is a subdomain of it. Maintained by hand in ``settings.yaml``; refresh
    candidate rates with ``scripts/refresh_cashback.py`` (semi-automatic, from
    ShopBack's public store list) then paste the reviewed values back.
    """

    enabled: bool = False
    provider_label: str = "ShopBack"
    rates: dict[str, float] = Field(default_factory=dict)


class PriceHistoryConfig(StrictConfigModel):
    """Price-rank signal: is a deal's price genuinely low, or just popular?

    Ranks a deal's current price against its own history of high-confidence
    prices from prior runs (read back from ``data/observations/*.jsonl`` — no
    new storage). Turns "hot" (social proof) into "hot *and* cheap" (real value).
    """

    enabled: bool = False
    lookback_days: int = 30
    # Minimum prior high-confidence price points before a deal is ranked at all
    # (below this the signal is unreliable and no badge is shown).
    min_history_points: int = 3
    # Within this fraction of the historical low counts as "near the low"; within
    # this fraction of the historical high counts as "above typical".
    near_fraction: float = 0.05


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
    # Default for Subscriber.max_digital_alerts_per_day when the Notion
    # "Max Digital Alerts/Day" property is absent (the DB schema is not
    # expected to gain that property — see subscribers.py).
    max_digital_alerts_per_day: int = 10
    timezone: str = "Australia/Sydney"
    # Quiet hours: no sends outside this window (both in "HH:MM" local time).
    # If start > end, the window wraps midnight (e.g. 22:00–07:00).
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    # Notifications matched during quiet hours are queued rather than dropped
    # (see queue_store.py). A queued entry older than this many hours is treated
    # as stale and discarded when the queue is drained after quiet hours end.
    quiet_hours_queue_max_age_hours: float = 12.0
    # Staleness ceiling: warn when a source's own freshest item is older than
    # this. Catches the failure this repo has hit repeatedly — a feed that
    # still returns HTTP 200 with well-formed content but has gone dark (the
    # measured specimen: God Save The Points, 10 valid items, newest 386 days
    # old, site closed). Neither a status check nor an item-count check sees
    # it. Set to None to disable.
    source_staleness_ceiling_days: float | None = 45.0


class Settings(StrictConfigModel):
    run: RunConfig = Field(default_factory=RunConfig)
    sources: dict[str, SourceConfig] = Field(default_factory=dict)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    dedup: DedupConfig = Field(default_factory=DedupConfig)
    cold_start: ColdStartConfig = Field(default_factory=ColdStartConfig)
    alerting: AlertConfig = Field(default_factory=AlertConfig)
    cashback: CashbackConfig = Field(default_factory=CashbackConfig)
    price_history: PriceHistoryConfig = Field(default_factory=PriceHistoryConfig)
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
