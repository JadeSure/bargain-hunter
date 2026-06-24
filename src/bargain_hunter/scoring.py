"""Velocity, hot-score computation, and price/discount extraction from deal titles.

Algorithm details match PRD §6.  All thresholds come from Settings so they can
be tuned in settings.yaml without touching code.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime

from .config import ScoringConfig
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


def _to_float(raw: str) -> float:
    return float(raw.replace(",", ""))


def extract_price_signals(text: str) -> tuple[float | None, float | None, float | None]:
    """Return (price, was_price, discount_percent) extracted from a deal title/description.

    Uses a lenient cascade: explicit % off → was/RRP pair → first two prices.
    Returns None for any signal we can't confidently extract.
    """
    # 1. Explicit "X% off"
    pct_match = _PCT_OFF_RE.search(text)
    discount_pct: float | None = float(pct_match.group(1)) if pct_match else None

    # 2. "was $X" / "RRP $X"
    was_match = _WAS_RE.search(text)
    was_price: float | None = _to_float(was_match.group(1)) if was_match else None

    # 3. All dollar amounts
    all_prices = [_to_float(m) for m in _PRICE_RE.findall(text)]

    # Current price: smallest dollar amount (filters the "was" anchor if both present)
    price: float | None = None
    if all_prices:
        candidates = [p for p in all_prices if was_price is None or p != was_price]
        if candidates:
            price = min(candidates)
        elif all_prices:
            price = min(all_prices)

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
    text = deal.title + " " + (deal.description or "")
    price, was_price, discount_pct = extract_price_signals(text)
    return deal.model_copy(
        update={
            "price": price,
            "was_price": was_price,
            "discount_percent": discount_pct,
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

    score = (
        age_factor
        * (vote_vel / v1 + math.log1p(deal.votes_pos) / math.log1p(v2) + 0.25 * comment_vel)
        - hot.neg_vote_penalty_weight * neg_ratio
    )

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


def is_hot(
    deal: Deal,
    snapshots: list[DealSnapshot],
    cfg: ScoringConfig,
    all_active_deals: list[tuple[Deal, list[DealSnapshot]]] | None = None,
    now: datetime | None = None,
) -> bool:
    """Full hot check: must pass candidacy AND score threshold."""
    if not is_hot_candidate(deal, snapshots, cfg, all_active_deals, now):
        return False
    score = compute_hot_score(deal, snapshots, cfg, now)
    return score >= cfg.hot.hot_threshold
