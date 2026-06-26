"""Domain models for the strategy-collection pipeline.

``CapturedPost`` is the raw harvested unit (one forum thread / Reddit post).
``Guide`` is the structured output the local LLM must emit in Stage 2 — it is
defined here so the (future) publish step can validate guide JSON against it.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel, Field


class CapturedPost(BaseModel):
    """A single harvested piece of discussion (forum thread or Reddit post)."""

    source: str                       # "ozbargain_forum" | "reddit" | "whirlpool"
    post_id: str
    url: str
    title: str
    author: str | None = None
    body: str = ""                    # plain text (HTML stripped)
    board: str | None = None          # forum board name / subreddit
    created_at: datetime | None = None
    fetched_at: datetime
    score: int | None = None          # upvotes / replies, when available
    num_comments: int | None = None
    tags: list[str] = Field(default_factory=list)
    relevance: int = 0                # count of money-saving keyword hits

    @property
    def key(self) -> str:
        """Stable cross-run identity for dedup."""
        return f"{self.source}:{self.post_id}"

    @property
    def content_hash(self) -> str:
        """Hash of title+body, so edited threads are re-captured but stable ones aren't."""
        h = hashlib.sha256()
        h.update((self.title + "\n" + self.body).encode("utf-8"))
        return h.hexdigest()[:16]


class GuideStep(BaseModel):
    """One ordered step in a money-saving playbook."""

    order: int
    action: str
    detail: str | None = None
    est_saving: str | None = None     # free-text, e.g. "~9%" or "$50"
    technique: str | None = None      # e.g. "cashback", "discounted_giftcard"


class Guide(BaseModel):
    """A structured money-saving playbook — the Stage 2 LLM output schema."""

    id: str                           # kebab-case slug, e.g. "buy-macbook-au-cheap"
    goal: str                         # e.g. "在澳洲低价购买 MacBook"
    category: str | None = None
    region: str = "AU"
    summary: str
    techniques: list[str] = Field(default_factory=list)
    steps: list[GuideStep] = Field(default_factory=list)
    total_est_saving: str | None = None
    difficulty: str | None = None     # 易 | 中 | 难
    risks: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)   # source URLs
    valid_until: datetime | None = None
    confidence: float | None = None   # 0..1, model self-rated
    generated_at: datetime | None = None
