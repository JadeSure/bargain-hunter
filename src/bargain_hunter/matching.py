"""Watch-track keyword/price matching (PRD §6.3).

Each subscriber has a list of watch keywords, each optionally annotated with a
target price:  "iPhone 17 Pro <=1800".  A deal matches when:
  - the keyword phrase appears in the title or description (case-insensitive), AND
  - at least one price condition is met:
      * discount_percent >= subscriber's min_discount_percent, OR
      * price <= subscriber's target price (if specified), OR
      * noise guard passes for unpriced deals (min votes reached, or keyword is
        an exact phrase on an "alert_always" keyword)

When none of the above price conditions can be evaluated (no price extracted,
no target price, no discount), the unpriced noise guard applies.
"""

from __future__ import annotations

import re

from .config import WatchConfig
from .models import Deal, Subscriber

# "iPhone 17 Pro <=1800"  →  keyword="iPhone 17 Pro", target=1800.0
_TARGET_RE = re.compile(r"^(.*?)\s*<=\s*([\d,]+(?:\.\d+)?)$")


def _parse_keyword(raw: str) -> tuple[str, float | None]:
    """Return (phrase, target_price_or_None)."""
    m = _TARGET_RE.match(raw.strip())
    if m:
        return m.group(1).strip(), float(m.group(2).replace(",", ""))
    return raw.strip(), None


def _keyword_hits(keyword: str, text: str) -> bool:
    return bool(re.search(re.escape(keyword), text, re.IGNORECASE))


def match_watch(
    deal: Deal,
    subscriber: Subscriber,
    cfg: WatchConfig,
) -> tuple[bool, str]:
    """Return (matched, reason_string).

    reason_string is a short human-readable note for notification text and logs.
    """
    search_text = deal.title + " " + (deal.description or "")
    min_discount = subscriber.min_discount_percent or cfg.default_min_discount_percent

    for raw_kw in subscriber.watch_keywords:
        keyword, target_price = _parse_keyword(raw_kw)
        if not keyword:
            continue
        if not _keyword_hits(keyword, search_text):
            continue

        # Keyword matched — now evaluate price conditions.
        has_discount = deal.discount_percent is not None
        has_price = deal.price is not None

        # Condition 1: explicit % discount met
        if has_discount and deal.discount_percent >= min_discount:
            return True, f'"{keyword}" matched, {deal.discount_percent:.0f}% off'

        # Condition 2: price at or below target
        if target_price is not None and has_price and deal.price <= target_price:
            return True, f'"{keyword}" matched, ${deal.price:.2f} ≤ ${target_price:.2f}'

        # Condition 3: no price signal to evaluate → noise guard (min votes required).
        # Applies when: no discount extracted AND no target price to compare against.
        no_price_verdict = not has_discount and target_price is None
        if no_price_verdict and deal.votes_pos >= cfg.unpriced_min_votes:
            return True, f'"{keyword}" matched ({deal.votes_pos} votes)'

    return False, ""


def filter_watch_matches(
    deals: list[Deal],
    subscriber: Subscriber,
    cfg: WatchConfig,
) -> list[tuple[Deal, str]]:
    """Return list of (deal, reason) that match this subscriber's watch list."""
    results = []
    for deal in deals:
        matched, reason = match_watch(deal, subscriber, cfg)
        if matched:
            results.append((deal, reason))
    return results
