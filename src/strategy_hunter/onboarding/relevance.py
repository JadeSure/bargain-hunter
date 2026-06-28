"""Relevance scoring for newcomer onboarding content.

Counts distinct signup/referral/newcomer signal phrases in a text. Cheap,
deterministic, no model required.
"""

from __future__ import annotations

import re

_SIGNAL_PHRASES = [
    "sign-up bonus",
    "signup bonus",
    "sign up bonus",
    "welcome bonus",
    "referral",
    "refer a friend",
    "refer-a-friend",
    "invite code",
    "referral code",
    "new customer",
    "new member",
    "new account",
    "bonus points",
    "cashback",
    "switch bank",
    "open an account",
    "join",
    "$ bonus",
    "points bonus",
    "promo code",
    "first purchase",
    "new user",
]

_PATTERNS = [re.compile(re.escape(p), re.IGNORECASE) for p in _SIGNAL_PHRASES]


def onboarding_relevance_score(text: str) -> int:
    """Count distinct newcomer signal phrases present in ``text``."""
    if not text:
        return 0
    return sum(1 for pat in _PATTERNS if pat.search(text))
