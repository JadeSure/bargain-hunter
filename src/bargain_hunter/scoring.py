"""Velocity, hot-score computation, and price/discount extraction from deal titles.

Algorithm details match PRD §6.  All thresholds come from Settings so they can
be tuned in settings.yaml without touching code.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from .config import ScoringConfig, effective_tiers
from .models import Deal, DealSnapshot

# ---------------------------------------------------------------------------
# Price / discount extraction (best-effort; see PRD §6.3)
# ---------------------------------------------------------------------------

# Matches: $49.99, $1,299, $49
_PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")
# Matches: "30% off", "30%off"
_PCT_OFF_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*off", re.IGNORECASE)
# Matches: "was $X", "RRP $X", "RRP: $X"
_WAS_RE = re.compile(r"(?:was|rrp):?\s*\$\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
_NON_PRICE_AFTER_RE = re.compile(
    r"^\W*(?:"
    r"c&c\b|click\s*(?:and|&)\s*collect\b|"
    r"cash\s*back\b|cashback\b|bonus\b|coupon\b|voucher\b|"
    r"off\b|discount\b|saving\b|savings\b|credit\b|total\b|"
    r"cap\b|capped\b|"
    r"minimum\s+spend\b|min\s+spend\b|max\s+spend\b|"
    r"(?:for\s+)?referrer\b|(?:for\s+)?referee\b|earned\b|order\b|spend\b|required\b|"
    r"for\s+free\s+(?:del\b|delivery\b|shipping\b|post(?:age)?\b)|"
    r"gift\s*card\b|gc\b"
    r")",
    re.IGNORECASE,
)
_NON_PRICE_BEFORE_RE = re.compile(
    r"(?:"
    r"cash\s*back|cashback|bonus|coupon|voucher|"
    r"save|saving|savings|credit|referrer|referee|earned|"
    r"orders?\s+over|free\s+over|over|minimum\s+spend|min\s+spend|max\s+spend|"
    r"spend|orders?|refer\s+a\s+friend\s+for|"
    r"cap|capped|capped\s+at|valued\s+at|worth|"
    r"delivery(?:\s+from)?|shipping(?:\s+from)?|post(?:age)?(?:\s+from)?"
    r")\W*$",
    re.IGNORECASE,
)
_NON_PRICE_TITLE_RE = re.compile(r"^\s*\$[\d,.]+\s*(?:off|bonus)\b", re.IGNORECASE)
_LOW_CONFIDENCE_CONTEXT_RE = re.compile(
    r"\b(?:"
    r"cash\s*back|cashback|bonus|"
    r"cap|capped|min(?:imum)?\s+spend|max(?:imum)?\s+spend|"
    r"gift\s*card|gc|credit|referrer|referee"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _PriceCandidate:
    value: float
    start: int
    end: int


def _to_float(raw: str) -> float:
    return float(raw.replace(",", ""))


def _price_candidates(text: str) -> list[_PriceCandidate]:
    return [
        _PriceCandidate(_to_float(match.group(1)), match.start(), match.end())
        for match in _PRICE_RE.finditer(text)
    ]


def _is_non_price_amount(text: str, candidate: _PriceCandidate) -> bool:
    if candidate.value == 0:
        return True
    before = text[max(0, candidate.start - 32) : candidate.start]
    after = text[candidate.end : candidate.end + 40]
    before_tail = before.strip()
    before_is_parenthesis = candidate.start > 0 and text[candidate.start - 1] == "("
    is_additive_fee = before_tail.endswith(("+", "/", "&")) and re.match(
        r"^\W*(?:del\b|delivery\b|shipping\b|post(?:age)?\b)",
        after,
        re.IGNORECASE,
    )
    return bool(
        is_additive_fee
        or
        _NON_PRICE_AFTER_RE.match(after)
        or (not before_is_parenthesis and _NON_PRICE_BEFORE_RE.search(before))
    )


def _select_current_price(
    text: str,
    candidates: list[_PriceCandidate],
    was_price: float | None,
) -> float | None:
    current_candidates = [
        candidate
        for candidate in candidates
        if (was_price is None or candidate.value != was_price)
        and not _is_non_price_amount(text, candidate)
    ]
    if not current_candidates:
        return None
    return min(candidate.value for candidate in current_candidates)


def _current_price_candidates(
    text: str,
    candidates: list[_PriceCandidate],
    was_price: float | None,
) -> list[_PriceCandidate]:
    return [
        candidate
        for candidate in candidates
        if (was_price is None or candidate.value != was_price)
        and not _is_non_price_amount(text, candidate)
    ]


def _has_any_price(text: str) -> bool:
    return _PRICE_RE.search(text) is not None


def price_display_confidence(text: str, price: float | None, was_price: float | None) -> str | None:
    """Return display confidence for a parsed title price.

    Low-confidence prices can still feed matching/dedup, but should not be shown
    as a factual badge in notifications.
    """
    if price is None:
        return None
    candidates = _current_price_candidates(text, _price_candidates(text), was_price)
    matching = [candidate for candidate in candidates if candidate.value == price]
    if len(candidates) == 1 and matching and not _LOW_CONFIDENCE_CONTEXT_RE.search(text):
        return "high"
    return "low"


def extract_price_signals(text: str) -> tuple[float | None, float | None, float | None]:
    """Return (price, was_price, discount_percent) extracted from a deal title/description.

    Uses a lenient cascade: explicit % off → was/RRP pair → first two prices.
    Returns None for any signal we can't confidently extract.
    """
    if _NON_PRICE_TITLE_RE.match(text):
        return None, None, None

    # 1. Explicit "X% off"
    pct_match = _PCT_OFF_RE.search(text)
    discount_pct: float | None = float(pct_match.group(1)) if pct_match else None

    # 2. "was $X" / "RRP $X"
    was_match = _WAS_RE.search(text)
    was_price: float | None = _to_float(was_match.group(1)) if was_match else None

    # 3. All dollar amounts
    candidates = _price_candidates(text)

    price = _select_current_price(text, candidates, was_price)

    # Derive missing signals
    if discount_pct is None and price and was_price and was_price > price:
        discount_pct = round((was_price - price) / was_price * 100, 1)
    if was_price is None and price and discount_pct:
        was_price = round(price / (1 - discount_pct / 100), 2)

    return price, was_price, discount_pct


def enrich_deal(deal: Deal) -> Deal:
    """Populate Deal.price/was_price/discount_percent from title (in-place copy)."""
    if deal.price is not None:
        return deal  # already enriched
    text = deal.title
    price, was_price, discount_pct = extract_price_signals(text)
    confidence = price_display_confidence(text, price, was_price)
    if price is None and deal.description and not _has_any_price(text):
        price, was_price, discount_pct = extract_price_signals(deal.description)
        confidence = "low" if price is not None else None
    return deal.model_copy(
        update={
            "price": price,
            "was_price": was_price,
            "discount_percent": discount_pct,
            "price_confidence": confidence,
        }
    )


# ---------------------------------------------------------------------------
# Velocity
# ---------------------------------------------------------------------------


def compute_vote_velocity(
    snapshots: list[DealSnapshot],
    window_minutes: int,
    now: datetime | None = None,
) -> tuple[float, float]:
    """Return (window_velocity, lifetime_velocity) in votes/hour.

    window_velocity: net positive votes gained over the last `window_minutes`.
    lifetime_velocity: total votes / age since oldest snapshot (fallback signal).

    Returns (0.0, 0.0) when fewer than 2 snapshots exist.
    """
    if len(snapshots) < 2:
        return 0.0, 0.0

    now = now or datetime.now(UTC)
    window_start = now.timestamp() - window_minutes * 60

    # Most recent snapshot is the "current" reference
    latest = snapshots[-1]
    latest_ts = latest.ts.timestamp()

    # Find the snapshot closest to (but not newer than) window_start
    baseline = snapshots[0]
    for snap in snapshots:
        if snap.ts.timestamp() <= window_start:
            baseline = snap

    delta_votes = latest.votes_pos - baseline.votes_pos
    delta_hours = (latest_ts - baseline.ts.timestamp()) / 3600
    window_vel = delta_votes / delta_hours if delta_hours > 0 else 0.0

    # Lifetime: oldest to latest
    oldest = snapshots[0]
    total_hours = (latest_ts - oldest.ts.timestamp()) / 3600
    lifetime_vel = latest.votes_pos / total_hours if total_hours > 0 else 0.0

    return max(window_vel, 0.0), max(lifetime_vel, 0.0)


def compute_comment_velocity(
    snapshots: list[DealSnapshot],
    window_minutes: int,
    now: datetime | None = None,
) -> float:
    """Return comment growth rate (comments/hour) over the window."""
    if len(snapshots) < 2:
        return 0.0
    now = now or datetime.now(UTC)
    window_start = now.timestamp() - window_minutes * 60
    latest = snapshots[-1]
    baseline = snapshots[0]
    for snap in snapshots:
        if snap.ts.timestamp() <= window_start:
            baseline = snap
    delta = latest.comment_count - baseline.comment_count
    delta_hours = (latest.ts.timestamp() - baseline.ts.timestamp()) / 3600
    return max(delta / delta_hours, 0.0) if delta_hours > 0 else 0.0


def compute_click_velocity(
    snapshots: list[DealSnapshot],
    window_minutes: int,
    now: datetime | None = None,
) -> float:
    """Return outbound-click growth rate (clicks/hour) over the window.

    Clicks are a direct "people are acting on this" signal and often move
    earlier than votes settle.  Logged for calibration; not yet scored.
    """
    if len(snapshots) < 2:
        return 0.0
    now = now or datetime.now(UTC)
    window_start = now.timestamp() - window_minutes * 60
    latest = snapshots[-1]
    baseline = snapshots[0]
    for snap in snapshots:
        if snap.ts.timestamp() <= window_start:
            baseline = snap
    delta = latest.click_count - baseline.click_count
    delta_hours = (latest.ts.timestamp() - baseline.ts.timestamp()) / 3600
    return max(delta / delta_hours, 0.0) if delta_hours > 0 else 0.0


# ---------------------------------------------------------------------------
# Hot score (PRD §6.2)
# ---------------------------------------------------------------------------


def compute_hot_score(
    deal: Deal,
    snapshots: list[DealSnapshot],
    cfg: ScoringConfig,
    now: datetime | None = None,
) -> float:
    """Compute the weighted hot score for a single deal.

    Returns 0.0 if there are insufficient snapshots for a meaningful score.
    """
    now = now or datetime.now(UTC)
    hot = cfg.hot

    vote_vel, _ = compute_vote_velocity(snapshots, cfg.window_minutes, now)
    comment_vel = compute_comment_velocity(snapshots, cfg.window_minutes, now)

    age_hours = 0.0
    if deal.posted_at:
        age_hours = max((now - deal.posted_at).total_seconds() / 3600, 0.0)

    age_factor = 0.5 ** (age_hours / hot.age_penalty_half_life_hours)
    neg_ratio = deal.votes_neg / max(deal.votes_pos + deal.votes_neg, 1)

    v1 = hot.min_votes_gain_per_window or 1
    v2 = hot.early_burst_min_votes or 1

    vote_term = vote_vel / v1 + math.log1p(deal.votes_pos) / math.log1p(v2)
    comment_term = hot.comment_velocity_weight * comment_vel
    score = age_factor * (vote_term + comment_term) - hot.neg_vote_penalty_weight * neg_ratio

    return round(max(score, 0.0), 4)


# ---------------------------------------------------------------------------
# Hot candidacy (PRD §6.2 — any-one-of-three gates)
# ---------------------------------------------------------------------------


def is_hot_candidate(
    deal: Deal,
    snapshots: list[DealSnapshot],
    cfg: ScoringConfig,
    all_active_deals: list[tuple[Deal, list[DealSnapshot]]] | None = None,
    now: datetime | None = None,
) -> bool:
    """Return True if deal passes at least one of the three hot candidacy gates."""
    now = now or datetime.now(UTC)
    hot = cfg.hot

    # Absolute floor: no deal with fewer votes than this can be a hot candidate.
    # Data-backed: prevents 2-3 vote posts with high comment velocity from scoring high.
    if deal.votes_pos < hot.min_votes_to_candidate:
        return False

    # Gate 1: window vote gain
    if len(snapshots) >= 2:
        vote_vel, _ = compute_vote_velocity(snapshots, cfg.window_minutes, now)
        window_gain = vote_vel * (cfg.window_minutes / 60)
        if window_gain >= hot.min_votes_gain_per_window:
            return True

    # Gate 2: early burst
    age_hours = 0.0
    if deal.posted_at:
        age_hours = (now - deal.posted_at).total_seconds() / 3600
    if age_hours <= hot.early_burst_age_hours and deal.votes_pos >= hot.early_burst_min_votes:
        return True

    # Gate 3: top-P% velocity among active deals
    if all_active_deals and len(snapshots) >= 2 and deal.votes_pos >= hot.min_votes_for_percentile:
        my_vel, _ = compute_vote_velocity(snapshots, cfg.window_minutes, now)
        velocities = []
        for other_deal, other_snaps in all_active_deals:
            if other_deal.votes_pos >= hot.min_votes_for_percentile and len(other_snaps) >= 2:
                v, _ = compute_vote_velocity(other_snaps, cfg.window_minutes, now)
                velocities.append(v)
        if velocities:
            velocities.sort(reverse=True)
            cutoff_idx = max(0, int(len(velocities) * hot.velocity_top_percent / 100) - 1)
            if my_vel >= velocities[cutoff_idx]:
                return True

    return False


def classify_hot(
    deal: Deal,
    snapshots: list[DealSnapshot],
    cfg: ScoringConfig,
    all_active_deals: list[tuple[Deal, list[DealSnapshot]]] | None = None,
    now: datetime | None = None,
) -> str | None:
    """Return the name of the highest hot tier the deal earns, or None.

    The deal must first pass hot candidacy; then it earns the best tier whose
    ``min_score`` is met and whose optional value gates (``min_votes`` /
    ``min_discount_percent``) pass. A deal that clears a tier's score but fails
    its value gate falls through to the next-best tier rather than being dropped.
    """
    if not is_hot_candidate(deal, snapshots, cfg, all_active_deals, now):
        return None
    score = compute_hot_score(deal, snapshots, cfg, now)
    for tier in effective_tiers(cfg.hot):
        if score < tier.min_score:
            continue
        if tier.min_votes is not None and deal.votes_pos < tier.min_votes:
            continue
        if (
            tier.min_discount_percent is not None
            and (deal.discount_percent or 0) < tier.min_discount_percent
        ):
            continue
        return tier.name
    return None


def is_hot(
    deal: Deal,
    snapshots: list[DealSnapshot],
    cfg: ScoringConfig,
    all_active_deals: list[tuple[Deal, list[DealSnapshot]]] | None = None,
    now: datetime | None = None,
) -> bool:
    """Backward-compatible boolean: True if the deal earns any hot tier."""
    return classify_hot(deal, snapshots, cfg, all_active_deals, now) is not None
