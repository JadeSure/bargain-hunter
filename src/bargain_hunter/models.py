"""Core domain models shared across sources, scoring, matching and notifications."""

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Deal(BaseModel):
    """A normalised deal from any source."""

    source: str
    deal_id: str
    title: str
    url: str
    merchant_url: str | None = None
    description: str | None = None
    image: str | None = None
    categories: list[str] = Field(default_factory=list)
    posted_at: datetime | None = None
    expiry: datetime | None = None
    votes_pos: int = 0
    votes_neg: int = 0
    comment_count: int = 0
    click_count: int = 0
    # Price signals, populated later by scoring (may be absent).
    price: float | None = None
    was_price: float | None = None
    discount_percent: float | None = None
    price_confidence: Literal["high", "low"] | None = None
    # ISO 4217 code for `price`/`was_price`. Defaults to AUD so every existing
    # source and persisted row stays valid without a backfill.
    currency: str = "AUD"
    expired: bool = False
    # Cashback that can be stacked on top of this deal (populated by cashback.py
    # from the config-maintained merchant→rate map). None = no known rate.
    cashback_percent: float | None = None
    cashback_provider: str | None = None
    # Price-rank signal vs this deal's own recent price history (price_history.py).
    # None = not enough history to judge. price_history_days = span the rank covers.
    price_rank: Literal["lowest", "low", "typical", "high"] | None = None
    price_history_days: int | None = None

    @property
    def key(self) -> str:
        """Stable cross-run identity, used for state and dedup."""
        return f"{self.source}:{self.deal_id}"


class DealSnapshot(BaseModel):
    """A point-in-time observation of a deal's engagement, used to compute velocity."""

    ts: datetime
    votes_pos: int
    votes_neg: int
    comment_count: int
    click_count: int = 0


class Subscriber(BaseModel):
    """A person who receives alerts, sourced from Notion."""

    name: str
    email: str | None = None
    telegram_chat_id: str | None = None
    active: bool = True
    channels: list[str] = Field(default_factory=list)  # "Email" | "Telegram"
    subscribe_hot: bool = True
    watch_keywords: list[str] = Field(default_factory=list)
    min_discount_percent: float | None = None
    categories: list[str] = Field(default_factory=list)
    # Minimum hot tier the subscriber wants (e.g. "top" | "great" | "good").
    # None = no floor (receive every tier). Compared via the configured tier rank.
    min_hot_level: str | None = None
    max_alerts_per_day: int = 10        # hot track daily cap
    max_watch_alerts_per_day: int = 10  # watch track daily cap (independent)
    # digital track daily cap (independent) — dealnews/slickdeals/v2ex/openrouter/
    # bank_rates/iknowthepilot (see main.DIGITAL_SOURCES)
    max_digital_alerts_per_day: int = 10
    block_keywords: list[str] = Field(default_factory=list)
    # Per-subscriber quiet-hours override, "HH:MM" local time (run.timezone).
    # None/empty = fall back to the global run.quiet_hours_start/end config.
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None

    @property
    def ref(self) -> str:
        """Non-PII, stable handle for logs.

        Public-repo Actions logs must never print subscriber identifiers
        (email / name / telegram id). This hashed reference stays correlatable
        across log lines without leaking who the person is.
        """
        seed = self.email or self.telegram_chat_id or self.name or "?"
        return "sub-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]


class Notification(BaseModel):
    """A bundle of deals to send to one subscriber in one run."""

    subscriber: Subscriber
    deals: list[Deal] = Field(default_factory=list)
    track: Literal["hot", "watch", "mixed", "digital"] = "hot"
