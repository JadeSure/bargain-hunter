"""Watch-track keyword/price matching (PRD §6.3).

Keyword syntax (all parts optional, order matters):
  PHRASE [<=PRICE] [@HH:MM | @YYYY-MM-DDTHH:MM]

Examples:
  iPhone 17 Pro <=1800
  BWS @19:00                   (active today until 19:00 AET)
  Sony WH <=300 @2026-07-01T23:59
  Dyson                        (plain keyword, noise guard applies)

A deal matches when:
  - the keyword phrase appears in the title or description (case-insensitive), AND
  - the keyword has not expired, AND
  - at least one price condition is met:
      * discount_percent >= subscriber's min_discount_percent, OR
      * price <= target price (if specified), OR
      * noise guard: no discount/target → require min votes
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .config import WatchConfig
from .models import Deal, Subscriber

_AET = ZoneInfo("Australia/Sydney")

# "iPhone 17 Pro <=1800 @19:00"
# Groups: (phrase, target_price_or_empty, expiry_or_empty)
_KW_RE = re.compile(
    r"^(.*?)"
    r"(?:\s*<=\s*([\d,]+(?:\.\d+)?))?"  # optional <=PRICE
    r"(?:\s*@(\d{2}:\d{2}(?::\d{2})?|"  # optional @HH:MM[:SS]
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?))?"  # or @YYYY-MM-DDTHH:MM
    r"\s*$"
)


def _parse_keyword(
    raw: str,
) -> tuple[str, float | None, datetime | None]:
    """Return (phrase, target_price_or_None, expiry_or_None).

    expiry is always tz-aware (AET); a bare HH:MM is interpreted as today in AET.
    """
    m = _KW_RE.match(raw.strip())
    if not m:
        return raw.strip(), None, None

    phrase = (m.group(1) or "").strip()
    target = float(m.group(2).replace(",", "")) if m.group(2) else None
    expiry: datetime | None = None

    if m.group(3):
        raw_exp = m.group(3)
        if "T" in raw_exp:
            # Full datetime: assume AET
            dt = datetime.fromisoformat(raw_exp)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_AET)
            expiry = dt.astimezone(UTC)
        else:
            # HH:MM[:SS] — today in AET
            parts = raw_exp.split(":")
            h, mn = int(parts[0]), int(parts[1])
            ss = int(parts[2]) if len(parts) > 2 else 0
            today_aet = datetime.now(_AET).replace(hour=h, minute=mn, second=ss, microsecond=0)
            expiry = today_aet.astimezone(UTC)

    return phrase, target, expiry


def _keyword_hits(keyword: str, text: str) -> bool:
    return bool(re.search(re.escape(keyword), text, re.IGNORECASE))


def match_watch(
    deal: Deal,
    subscriber: Subscriber,
    cfg: WatchConfig,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Return (matched, reason_string).

    reason_string is a short human-readable note for notification text and logs.
    """
    now = now or datetime.now(UTC)
    search_text = deal.title + " " + (deal.description or "")
    min_discount = subscriber.min_discount_percent or cfg.default_min_discount_percent

    for raw_kw in subscriber.watch_keywords:
        keyword, target_price, expiry = _parse_keyword(raw_kw)
        if not keyword:
            continue

        # Skip expired keywords
        if expiry is not None and now >= expiry:
            continue

        if not _keyword_hits(keyword, search_text):
            continue

        # Keyword matched — evaluate price conditions.
        has_discount = deal.discount_percent is not None
        has_price = deal.price is not None

        # Condition 1: explicit % discount met
        if has_discount and deal.discount_percent >= min_discount:
            return True, f'"{keyword}" matched, {deal.discount_percent:.0f}% off'

        # Condition 2: price at or below target
        if target_price is not None and has_price and deal.price <= target_price:
            return True, f'"{keyword}" matched, ${deal.price:.2f} ≤ ${target_price:.2f}'

        # Condition 3: no price signal → noise guard (min votes required)
        no_price_verdict = not has_discount and target_price is None
        if no_price_verdict and deal.votes_pos >= cfg.unpriced_min_votes:
            return True, f'"{keyword}" matched ({deal.votes_pos} votes)'

    return False, ""


def filter_watch_matches(
    deals: list[Deal],
    subscriber: Subscriber,
    cfg: WatchConfig,
    now: datetime | None = None,
) -> list[tuple[Deal, str]]:
    """Return list of (deal, reason) that match this subscriber's watch list."""
    results = []
    for deal in deals:
        matched, reason = match_watch(deal, subscriber, cfg, now=now)
        if matched:
            results.append((deal, reason))
    return results
