"""Domain models for the newcomer onboarding catalog.

``ProgramStep`` is one ordered join step. ``Program`` is a curated money-saving
program (cashback portal, bank, loyalty scheme, app) that newcomers to AU should join.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

PROGRAM_CATEGORIES: frozenset[str] = frozenset({
    "cashback_portal",
    "bank",
    "loyalty",
    "food_app",
    "fuel_app",
    "travel",
    "telco",
    "survey",
    "shopping_app",
    "other",
})


class ProgramStep(BaseModel):
    """One ordered step for joining or activating a program."""

    order: int
    action: str
    detail: str | None = None


class Program(BaseModel):
    """A curated money-saving program for newcomers to Australia."""

    id: str                            # kebab-case slug, e.g. "cashrewards-au"
    name: str                          # e.g. "TopCashback AU"
    category: str                      # one of PROGRAM_CATEGORIES
    one_liner: str                     # why a newcomer wants it (short)
    benefit: str                       # what you get (ongoing value / mechanics)
    signup_bonus: str | None = None    # free text, e.g. "$25 after first $25 cashback"
    needs_referral: bool = False       # bonus requires an existing member's invite/code
    referral_note: str | None = None
    how_to_join: list[ProgramStep] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    region: str = "AU"
    recommended_for_newcomer: bool = True
    priority: int = 100                # lower = do earlier on the checklist
    est_value: str | None = None       # e.g. "~$50 one-off + ongoing 2-8% cashback"
    official_url: str | None = None
    sources: list[str] = Field(default_factory=list)
    valid_until: datetime | None = None
    confidence: float | None = None    # 0..1, self-rated
    generated_at: datetime | None = None
