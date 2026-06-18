"""Core domain models shared across sources, scoring, matching and notifications."""

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
    expired: bool = False

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
    max_alerts_per_day: int = 10


class Notification(BaseModel):
    """A bundle of deals to send to one subscriber in one run."""

    subscriber: Subscriber
    deals: list[Deal] = Field(default_factory=list)
    track: Literal["hot", "watch", "mixed"] = "hot"
