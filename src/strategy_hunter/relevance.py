"""Lightweight relevance scoring: how likely a post is a money-saving guide.

Stage 1 must keep the corpus focused so the (token-limited) local model in
Stage 2 isn't fed off-topic noise (tax questions, news, chit-chat). We score by
counting hits of money-saving signal phrases in the title + body. Cheap,
deterministic, no model needed.
"""

from __future__ import annotations

import re

# Phrases that signal deal-stacking / money-saving discussion. Lowercased match.
_SIGNAL_PHRASES = [
    # techniques
    "cashback", "cash back", "cashrewards", "shopback", "topcashback",
    "gift card", "giftcard", "discounted gift", "egift",
    "discount", "% off", "percent off", "coupon", "promo code", "promo",
    "voucher", "clearance", "price match", "price beat", "pricebeat",
    "trade-in", "trade in", "student discount", "edu discount", "education store",
    "sign-up bonus", "signup bonus", "bonus points", "rewards points", "churn",
    "frequent flyer", "qantas points", "velocity points", "credit card points",
    "stack", "stacking", "loophole", "hack",
    # intent patterns
    "cheapest way", "cheapest place", "how to get", "best way to", "best card",
    "under $", "save money", "save on", "deal on", "get it cheaper",
    "good deal", "worth it", "recommend", "alternative to",
    # Chinese (sources are mostly EN, but keep a few)
    "薅羊毛", "优惠", "折扣", "返现", "礼品卡", "攻略",
]

_PATTERNS = [re.compile(re.escape(p), re.IGNORECASE) for p in _SIGNAL_PHRASES]


def relevance_score(text: str) -> int:
    """Count distinct money-saving signal phrases present in ``text``."""
    if not text:
        return 0
    return sum(1 for pat in _PATTERNS if pat.search(text))
