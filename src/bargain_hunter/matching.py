"""Watch-track keyword/price matching (PRD §6.3).

Keyword syntax (all parts optional, order matters):
  PHRASE [<=PRICE] [@HH:MM | @YYYY-MM-DDTHH:MM]

Examples:
  iPhone 17 Pro
  BWS @19:00                   (active today until 19:00 AET)
  Sony WH <=300 @2026-07-01T23:59
  Dyson <=499

If PHRASE is an Amazon product URL (…/dp/<ASIN>) or a bare ASIN (B0……), it is a
**target-price watch**: it matches the exact product in the CamelCamelCamel feed
(by ASIN) rather than by title text, and the vote/discount noise guard is skipped
because the `<=PRICE` target is the gate. Examples:
  https://www.amazon.com.au/dp/B08166SLDF <=1500
  B08166SLDF <=1500

A (text) deal matches when:
  - the keyword phrase appears in the title or description (case-insensitive), AND
  - the keyword has not expired, AND
  - votes_pos >= cfg.min_votes (noise guard — confirms it's a real deal), AND
  - if <=PRICE is specified: deal.price is known and at or below that target
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .config import WatchConfig
from .models import Deal, Subscriber

_AET = ZoneInfo("Australia/Sydney")

# Amazon product URL (…/dp/<ASIN>, …/gp/product/<ASIN>, …/product/<ASIN>).
_AMAZON_ASIN_RE = re.compile(r"/(?:dp|gp/product|product)/([A-Z0-9]{10})(?:[/?#]|$)", re.IGNORECASE)
# Bare modern ASIN. Restricted to the "B0…" form so ordinary 10-char keywords
# aren't hijacked; paste the full Amazon URL for older ISBN-style ASINs.
_BARE_ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$", re.IGNORECASE)


def _extract_asin(phrase: str) -> str | None:
    """Return the uppercased ASIN if ``phrase`` is an Amazon URL or bare ASIN, else None."""
    p = phrase.strip()
    m = _AMAZON_ASIN_RE.search(p)
    if m:
        return m.group(1).upper()
    if _BARE_ASIN_RE.match(p):
        return p.upper()
    return None


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


def _keyword_pattern(keyword: str) -> str:
    """Build a word-boundary-aware regex for `keyword`.

    `\\b` only anchors correctly next to a word character, so it's only added on
    the side(s) where the phrase actually starts/ends with one (e.g. "C&C" gets
    no trailing boundary, but still matches as a whole phrase via the escaping).
    """
    pattern = re.escape(keyword)
    if keyword[:1].isalnum() or keyword[:1] == "_":
        pattern = r"\b" + pattern
    if keyword[-1:].isalnum() or keyword[-1:] == "_":
        pattern = pattern + r"\b"
    return pattern


def _keyword_hits(keyword: str, text: str) -> bool:
    return bool(re.search(_keyword_pattern(keyword), text, re.IGNORECASE))


def match_watch(
    deal: Deal,
    subscriber: Subscriber,
    cfg: WatchConfig,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Return (matched, reason_string).

    reason_string is a short human-readable note for notification text and logs.
    """
    matched, reason, _ = _match_watch_with_target(deal, subscriber, cfg, now=now)
    return matched, reason


def _match_watch_with_target(
    deal: Deal,
    subscriber: Subscriber,
    cfg: WatchConfig,
    now: datetime | None = None,
) -> tuple[bool, str, float | None]:
    """Like `match_watch`, but also returns the matching keyword's `<=PRICE` target
    (None if the matched keyword has no price ceiling), so callers can tell dedup
    whether a re-alert is due to a *newly* satisfied ceiling.
    """
    now = now or datetime.now(UTC)

    # Reject stale deals up-front — prevents old tracked deals from filling the daily cap.
    if deal.posted_at is not None:
        age_hours = (now - deal.posted_at).total_seconds() / 3600
        if age_hours > cfg.max_deal_age_hours:
            return False, "", None

    search_text = deal.title + " " + (deal.description or "")

    for raw_kw in subscriber.watch_keywords:
        keyword, target_price, expiry = _parse_keyword(raw_kw)
        if not keyword:
            continue

        if expiry is not None and now >= expiry:
            continue

        # Amazon target-price watch: match the exact product by ASIN in the CCC
        # feed, gated by the price target rather than the vote/discount guard.
        asin = _extract_asin(keyword)
        if asin is not None:
            if deal.source != "camelcamelcamel" or deal.deal_id.upper() != asin:
                continue
            if target_price is not None:
                if deal.price is None or deal.price > target_price:
                    continue
                reason = f"Amazon {asin} dropped to ${deal.price:.2f} ≤ ${target_price:.2f}"
                return True, reason, target_price
            note = f", {deal.discount_percent:.0f}% off" if deal.discount_percent else ""
            price_note = f" to ${deal.price:.2f}" if deal.price is not None else ""
            return True, f"Amazon {asin} price drop{price_note}{note}", None

        if not _keyword_hits(keyword, search_text):
            continue

        # Noise guard: votes (community deals) OR discount (price-tracker deals like CCC).
        passes_votes = deal.votes_pos >= cfg.min_votes
        passes_discount = (
            cfg.min_discount_percent is not None
            and deal.discount_percent is not None
            and deal.discount_percent >= cfg.min_discount_percent
        )
        # Editorially curated / keyword-scoped feeds carry neither votes nor a
        # parseable discount; for those the keyword match is itself the quality guard.
        passes_trusted = deal.source in cfg.trusted_sources
        if not (passes_votes or passes_discount or passes_trusted):
            continue

        # Optional price ceiling — if specified, deal price must be known and within target.
        if target_price is not None:
            if deal.price is None or deal.price > target_price:
                continue
            reason = f'"{keyword}" matched, ${deal.price:.2f} ≤ ${target_price:.2f}'
            return True, reason, target_price

        if passes_votes:
            return True, f'"{keyword}" matched ({deal.votes_pos} votes)', None
        if passes_discount:
            return True, f'"{keyword}" matched, {deal.discount_percent:.0f}% off', None
        return True, f'"{keyword}" matched', None

    return False, "", None


def filter_watch_matches(
    deals: list[Deal],
    subscriber: Subscriber,
    cfg: WatchConfig,
    now: datetime | None = None,
) -> list[tuple[Deal, str, float | None]]:
    """Return list of (deal, reason, watch_target_price) for this subscriber's watch list.

    `watch_target_price` is the `<=PRICE` ceiling of the matching keyword (or None if
    the keyword has no ceiling) — dedup needs it to detect a *newly* satisfied ceiling.
    """
    results = []
    for deal in deals:
        matched, reason, target_price = _match_watch_with_target(deal, subscriber, cfg, now=now)
        if matched:
            results.append((deal, reason, target_price))
    return results
