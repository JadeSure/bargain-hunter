"""Tests for price extraction and hot-score logic."""

from datetime import UTC, datetime, timedelta

import pytest

from bargain_hunter.config import ScoringConfig
from bargain_hunter.models import Deal, DealSnapshot
from bargain_hunter.scoring import (
    compute_hot_score,
    compute_vote_velocity,
    enrich_deal,
    extract_price_signals,
    is_hot,
    is_hot_candidate,
)

# ---------------------------------------------------------------------------
# Price / discount extraction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected_price,expected_was,expected_pct",
    [
        ("Acme Widget $49.99 (was $79.99)", 49.99, 79.99, pytest.approx(37.5, abs=0.2)),
        ("30% off all shoes $120", 120.0, pytest.approx(171.43, abs=0.2), 30.0),
        ("TV $1,299 RRP $1,999", 1299.0, 1999.0, pytest.approx(35.0, abs=0.2)),
        ("Free shipping on orders", None, None, None),
        ("iPhone $799 (was $999) 20% off", 799.0, 999.0, 20.0),
    ],
)
def test_extract_price_signals(text, expected_price, expected_was, expected_pct):
    price, was, pct = extract_price_signals(text)
    if expected_price is None:
        assert price is None
    else:
        assert price == expected_price
    if expected_was is None:
        assert was is None
    else:
        assert was == expected_was
    if expected_pct is None:
        assert pct is None
    else:
        assert pct == expected_pct


def _deal(**kwargs) -> Deal:
    defaults = dict(
        source="ozbargain",
        deal_id="1",
        title="Test deal",
        url="https://ozbargain.com.au/node/1",
        votes_pos=0,
        votes_neg=0,
        comment_count=0,
        posted_at=datetime.now(UTC) - timedelta(hours=1),
    )
    defaults.update(kwargs)
    return Deal(**defaults)


def test_enrich_deal_sets_price_signals():
    d = _deal(title="Widget $49.99 (was $79.99)")
    enriched = enrich_deal(d)
    assert enriched.price == pytest.approx(49.99)
    assert enriched.was_price == pytest.approx(79.99)
    assert enriched.discount_percent is not None


def test_enrich_deal_skips_if_already_set():
    d = _deal(title="Widget $49.99 (was $79.99)", price=10.0)
    enriched = enrich_deal(d)
    assert enriched.price == 10.0  # untouched


# ---------------------------------------------------------------------------
# Velocity
# ---------------------------------------------------------------------------


def _snaps(*votes_pos_list: int, spacing_minutes: int = 10) -> list[DealSnapshot]:
    base = datetime.now(UTC) - timedelta(minutes=spacing_minutes * len(votes_pos_list))
    return [
        DealSnapshot(
            ts=base + timedelta(minutes=i * spacing_minutes),
            votes_pos=v,
            votes_neg=0,
            comment_count=0,
        )
        for i, v in enumerate(votes_pos_list)
    ]


def test_velocity_zero_for_single_snapshot():
    snaps = _snaps(10)
    vel, lifetime = compute_vote_velocity(snaps, window_minutes=60)
    assert vel == 0.0
    assert lifetime == 0.0


def test_velocity_growing():
    # 3 snapshots, 10 min apart: 0→5→10 votes.  Over 20 min = 0.333 hr → 30 v/hr
    snaps = _snaps(0, 5, 10, spacing_minutes=10)
    vel, _ = compute_vote_velocity(snaps, window_minutes=60)
    assert vel > 0


# ---------------------------------------------------------------------------
# Hot candidacy and score
# ---------------------------------------------------------------------------


def _cfg() -> ScoringConfig:
    return ScoringConfig()


def test_early_burst_candidacy():
    d = _deal(
        votes_pos=30,
        posted_at=datetime.now(UTC) - timedelta(hours=1),
    )
    cfg = _cfg()
    # One snapshot is enough for early burst (no velocity needed)
    snaps = _snaps(30)
    assert is_hot_candidate(d, snaps, cfg)


def test_no_candidacy_for_old_low_vote_deal():
    d = _deal(
        votes_pos=3,
        posted_at=datetime.now(UTC) - timedelta(hours=48),
    )
    cfg = _cfg()
    snaps = _snaps(3)
    assert not is_hot_candidate(d, snaps, cfg)


def test_hot_score_decreases_with_age():
    cfg = _cfg()
    snaps = _snaps(0, 20, 40, spacing_minutes=20)
    young = _deal(votes_pos=40, posted_at=datetime.now(UTC) - timedelta(hours=1))
    old = _deal(votes_pos=40, posted_at=datetime.now(UTC) - timedelta(hours=24))
    score_young = compute_hot_score(young, snaps, cfg)
    score_old = compute_hot_score(old, snaps, cfg)
    assert score_young > score_old


def test_is_hot_end_to_end():
    cfg = _cfg()
    # Early burst: < 2h old, >= 25 votes, and score should pass threshold
    d = _deal(
        votes_pos=30,
        posted_at=datetime.now(UTC) - timedelta(minutes=30),
    )
    # Velocity: went from 0 to 30 in 30 min = 60 v/hr >> V1=15
    snaps = _snaps(0, 15, 30, spacing_minutes=15)
    assert is_hot(d, snaps, cfg)
