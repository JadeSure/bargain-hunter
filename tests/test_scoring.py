"""Tests for price extraction and hot-score logic."""

from datetime import UTC, datetime, timedelta

import pytest

from bargain_hunter.config import AdaptiveConfig, HotConfig, HotTier, ScoringConfig, effective_tiers
from bargain_hunter.models import Deal, DealSnapshot
from bargain_hunter.scoring import (
    classify_hot,
    compute_click_velocity,
    compute_heat_ratio,
    compute_hot_score,
    compute_site_velocity_index,
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
        ("1more Hq31 Bluetooth Headphones $55.97 Delivered @ Amazon AU", 55.97, None, None),
        (
            "Motorola Moto G86 Power 5G $272, Edge 60 Pro $620 + Del ($0 C&C)",
            272.0,
            None,
            None,
        ),
        (
            "Motorola Moto G86 with $40 cashback ($232) and bonus software valued at $178",
            232.0,
            None,
            None,
        ),
        (
            "Upsized Referral Bonus: $50 for Referrer & $50 for Referee "
            "($10 Earned Cashback Required)",
            None,
            None,
            None,
        ),
        (
            "Everyday Market: 30% Cashback (Capped at $150 per Member, "
            "Min Spend $50, Max Spend $1000)",
            None,
            None,
            None,
        ),
        ("Join Amazon Prime Get $10 Credit for Eligible $59+ Order", None, None, None),
        (
            "$2 off $15, $4 off $30, $9 off $65 Spend (in USD) @ AliExpress",
            None,
            None,
            None,
        ),
        ("$50 off Big essentials Collection @ Baby Village", None, None, None),
        (
            "Apple iPhone 17 256GB $1299 Delivered ($100 off RRP) @ Costco",
            1299.0,
            None,
            None,
        ),
        (
            "Seasonal Farm Direct Whole Australian Black Truffle 15g $28.50 / "
            "30g $57 / 45g $85.50 + $20 Postage",
            28.5,
            None,
            None,
        ),
        (
            "Men's Suit Jacket from $39.20, Wool Trousers 3 for $84 + "
            "$10 Delivery ($75 Order) @ Oxford",
            39.2,
            None,
            None,
        ),
        (
            "Omo Professional Active Clean Laundry Powder 6kg $21 + Delivery ($0 C&C)",
            21.0,
            None,
            None,
        ),
        (
            "Cygnett 100W Laptop Power Bank 25K + Stand $43.12 + Delivery ($0 C&C) @ Bing Lee",
            43.12,
            None,
            None,
        ),
        (
            "Apple Magsafe Charger (2m) $67 (RRP $89) Delivered ($0 Prime/ $59 Spend)",
            67.0,
            89.0,
            pytest.approx(24.7, abs=0.2),
        ),
        (
            "Under Armour Curry Series 7 Men’s Basketball Shoes $99.95 + "
            "Delivery / Free over $150 @ Foot Locker",
            99.95,
            None,
            None,
        ),
        (
            "Save $100 on $1000 Minimum Spend, e.g. Palit GeForce RTX 5080 GPU $1499, "
            "RTX 5070 Ti GPU $1199 + Delivery @ Shopping Express",
            1199.0,
            None,
            None,
        ),
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
    assert enriched.price_confidence == "high"
    assert enriched.was_price == pytest.approx(79.99)
    assert enriched.discount_percent is not None


def test_enrich_deal_skips_if_already_set():
    d = _deal(title="Widget $49.99 (was $79.99)", price=10.0)
    enriched = enrich_deal(d)
    assert enriched.price == 10.0  # untouched


def test_enrich_deal_prefers_title_price_over_description_noise():
    d = _deal(
        title="Mitsubishi Electric 442L Refrigerator $1,865 @ Appliances Online",
        description="Includes a 2 year warranty and occasional $2 off accessory references.",
    )
    enriched = enrich_deal(d)
    assert enriched.price == pytest.approx(1865.0)


def test_enrich_deal_ignores_coupon_discount_amount_in_description():
    d = _deal(
        title=(
            "Apple MacBook Pro 14-Inch - M5 Chip 16GB 512GB (Silver) - "
            '$2059 with Code "Y2K220" - Free Delivery - Direct Debit @ MWAVE'
        ),
        description="Apply coupon code Y2K220 for $220 off the regular price.",
    )
    enriched = enrich_deal(d)
    assert enriched.price == pytest.approx(2059.0)
    assert enriched.price_confidence == "high"


def test_enrich_deal_does_not_use_description_when_title_has_only_promo_amounts():
    d = _deal(
        title="Everyday Market: 30% Cashback (Capped at $150, Min Spend $50)",
        description="New users can also get a $10 welcome bonus after their first purchase.",
    )
    enriched = enrich_deal(d)
    assert enriched.price is None
    assert enriched.price_confidence is None


@pytest.mark.parametrize(
    "title,price",
    [
        ("Logitech MX Keys S Wireless Keyboard $139 + Delivery ($0 C&C) @ Umart", 139.0),
        (
            "Cygnett 100W Laptop Power Bank 25K + Stand $43.12 + Delivery ($0 C&C) "
            "@ Bing Lee",
            43.12,
        ),
    ],
)
def test_enrich_deal_marks_single_price_with_fulfilment_noise_high_confidence(title, price):
    d = _deal(title=title)
    enriched = enrich_deal(d)
    assert enriched.price == pytest.approx(price)
    assert enriched.price_confidence == "high"


def test_enrich_deal_marks_multi_variant_price_low_confidence():
    d = _deal(
        title=(
            "Save $100 on $1000 Minimum Spend, e.g. Palit GeForce RTX 5080 GPU $1499, "
            "RTX 5070 Ti GPU $1199 + Delivery @ Shopping Express"
        ),
    )
    enriched = enrich_deal(d)
    assert enriched.price == pytest.approx(1199.0)
    assert enriched.price_confidence == "low"


def test_enrich_deal_falls_back_to_description_when_title_has_no_price():
    d = _deal(
        title="Special member deal @ Example Store",
        description="Now $49.99, was $79.99 for members only.",
    )
    enriched = enrich_deal(d)
    assert enriched.price == pytest.approx(49.99)
    assert enriched.price_confidence == "low"


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


def test_percentile_gate_rejects_zero_velocity_on_quiet_night():
    """Gate 3 must not pass when every active deal (including this one) has zero
    vote velocity — a flat 0 >= 0 comparison must not grant candidacy."""
    cfg = _cfg()
    # Old enough to miss early burst, below early_burst_min_votes, flat votes
    # across snapshots so velocity is 0.
    d = _deal(votes_pos=10, posted_at=datetime.now(UTC) - timedelta(hours=6))
    snaps = _snaps(10, 10, spacing_minutes=10)
    other = _deal(deal_id="2", votes_pos=10, posted_at=datetime.now(UTC) - timedelta(hours=6))
    other_snaps = _snaps(10, 10, spacing_minutes=10)
    assert not is_hot_candidate(d, snaps, cfg, all_active_deals=[(other, other_snaps)])


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


# ---------------------------------------------------------------------------
# Hot ladder (tiers) and classify_hot
# ---------------------------------------------------------------------------


def test_effective_tiers_sorted_best_first():
    cfg = HotConfig(
        tiers=[
            HotTier(name="good", min_score=1.5),
            HotTier(name="top", min_score=7.0),
            HotTier(name="great", min_score=4.0),
        ]
    )
    assert [t.name for t in effective_tiers(cfg)] == ["top", "great", "good"]


def test_effective_tiers_fallback_to_single_hot():
    tiers = effective_tiers(HotConfig(hot_threshold=2.0))
    assert len(tiers) == 1
    assert tiers[0].name == "hot"
    assert tiers[0].min_score == 2.0


def test_classify_hot_none_for_non_candidate():
    d = _deal(votes_pos=3, posted_at=datetime.now(UTC) - timedelta(hours=48))
    assert classify_hot(d, _snaps(3), _cfg()) is None


def test_classify_hot_value_gate_demotes_to_lower_tier():
    # Both tiers clear on score; top's min_votes gate (1000) fails → demoted to good.
    cfg = ScoringConfig(
        hot=HotConfig(
            tiers=[
                HotTier(name="top", min_score=0.0, min_votes=1000),
                HotTier(name="good", min_score=0.0),
            ]
        )
    )
    d = _deal(votes_pos=30, posted_at=datetime.now(UTC) - timedelta(minutes=30))
    snaps = _snaps(0, 15, 30, spacing_minutes=15)
    assert classify_hot(d, snaps, cfg) == "good"


def test_classify_hot_top_when_value_gate_met():
    cfg = ScoringConfig(
        hot=HotConfig(
            tiers=[
                HotTier(name="top", min_score=0.0, min_votes=10),
                HotTier(name="good", min_score=0.0),
            ]
        )
    )
    d = _deal(votes_pos=30, posted_at=datetime.now(UTC) - timedelta(minutes=30))
    snaps = _snaps(0, 15, 30, spacing_minutes=15)
    assert classify_hot(d, snaps, cfg) == "top"


# ---------------------------------------------------------------------------
# Click velocity
# ---------------------------------------------------------------------------


def _click_snaps(*clicks: int, spacing_minutes: int = 15) -> list[DealSnapshot]:
    base = datetime.now(UTC) - timedelta(minutes=spacing_minutes * len(clicks))
    return [
        DealSnapshot(
            ts=base + timedelta(minutes=i * spacing_minutes),
            votes_pos=0,
            votes_neg=0,
            comment_count=0,
            click_count=c,
        )
        for i, c in enumerate(clicks)
    ]


def test_click_velocity_zero_for_single_snapshot():
    assert compute_click_velocity(_click_snaps(5), window_minutes=60) == 0.0


def test_click_velocity_growing():
    # 0 -> 10 -> 30 clicks: positive rate
    assert compute_click_velocity(_click_snaps(0, 10, 30), window_minutes=60) > 0


# ---------------------------------------------------------------------------
# Discount-based hot candidacy for voteless sources (e.g. CamelCamelCamel)
# ---------------------------------------------------------------------------


def _ccc_deal(**kwargs) -> Deal:
    defaults = dict(
        source="camelcamelcamel",
        deal_id="ccc-1",
        title="Widget",
        url="https://au.camelcamelcamel.com/product/1",
        votes_pos=0,
        votes_neg=0,
        comment_count=0,
        posted_at=datetime.now(UTC) - timedelta(hours=1),
    )
    defaults.update(kwargs)
    return Deal(**defaults)


def test_voteless_deal_never_candidate_via_vote_gates():
    """A CCC-style deal with 0 votes and no discount never qualifies — the
    vote-based gates are untouched and votes_pos=0 always fails them anyway."""
    d = _ccc_deal(discount_percent=None)
    assert not is_hot_candidate(d, [], _cfg())


def test_voteless_deal_below_discount_floor_not_candidate():
    d = _ccc_deal(discount_percent=39.9)
    assert not is_hot_candidate(d, [], _cfg())


def test_voteless_deal_at_discount_floor_is_candidate():
    d = _ccc_deal(discount_percent=40.0)
    assert is_hot_candidate(d, [], _cfg())


def test_vote_based_source_ignores_discount_candidacy_path():
    """A vote-based deal (e.g. OzBargain) with a huge discount but 0 votes must
    still fail candidacy — the discount path is voteless-sources-only."""
    d = _deal(source="ozbargain", votes_pos=0, discount_percent=90.0)
    assert not is_hot_candidate(d, [], _cfg())


def _ladder_cfg() -> ScoringConfig:
    """A hot ladder shaped like production settings.yaml (good/great/top),
    needed because classify_discount_tier maps discount % to *named* tiers —
    the default single synthesised "hot" tier has no discount mapping."""
    return ScoringConfig(
        hot=HotConfig(
            tiers=[
                HotTier(name="top", min_score=7.0, min_votes=40),
                HotTier(name="great", min_score=4.0),
                HotTier(name="good", min_score=1.5),
            ]
        )
    )


def test_voteless_deal_classifies_good_tier():
    d = _ccc_deal(discount_percent=42.0)
    assert classify_hot(d, [], _ladder_cfg()) == "good"


def test_voteless_deal_classifies_great_tier():
    d = _ccc_deal(discount_percent=60.0)
    assert classify_hot(d, [], _ladder_cfg()) == "great"


def test_voteless_deal_classifies_top_tier():
    d = _ccc_deal(discount_percent=75.0)
    assert classify_hot(d, [], _ladder_cfg()) == "top"


def test_voteless_deal_discount_candidate_min_disabled():
    cfg = ScoringConfig(hot=HotConfig(discount_candidate_min=None))
    d = _ccc_deal(discount_percent=99.0)
    assert not is_hot_candidate(d, [], cfg)


# ---------------------------------------------------------------------------
# Event-day adaptive baseline
# ---------------------------------------------------------------------------


def test_site_velocity_index_excludes_single_snapshot_pairs():
    now = datetime.now(UTC)
    pairs = [
        (_deal(deal_id="1"), _snaps(10)),  # single snapshot — excluded
        (_deal(deal_id="2"), _snaps(0, 20, spacing_minutes=30)),
        (_deal(deal_id="3"), _snaps(0, 40, spacing_minutes=30)),
    ]
    index = compute_site_velocity_index(pairs, window_minutes=60, percentile=50, now=now)
    assert index is not None
    assert index > 0


def test_site_velocity_index_none_when_no_samples():
    now = datetime.now(UTC)
    pairs = [(_deal(deal_id="1"), _snaps(10))]  # single snapshot only
    assert compute_site_velocity_index(pairs, window_minutes=60, percentile=75, now=now) is None


def test_site_velocity_index_percentile_maths():
    now = datetime.now(UTC)
    # Velocities: 0->10 over 30min=20v/h, 0->20=40v/h, 0->30=60v/h, 0->40=80v/h
    pairs = [
        (_deal(deal_id=str(i)), _snaps(0, v, spacing_minutes=30))
        for i, v in enumerate([10, 20, 30, 40])
    ]
    index = compute_site_velocity_index(pairs, window_minutes=60, percentile=50, now=now)
    assert index == pytest.approx(50.0, abs=1.0)


def test_compute_heat_ratio_disabled_returns_one():
    cfg = AdaptiveConfig(enabled=False)
    assert compute_heat_ratio(2.0, 1.0, cfg, baseline_age_days=100) == 1.0


def test_compute_heat_ratio_none_index_returns_one():
    cfg = AdaptiveConfig(enabled=True)
    assert compute_heat_ratio(None, 1.0, cfg, baseline_age_days=100) == 1.0


def test_compute_heat_ratio_none_baseline_returns_one():
    cfg = AdaptiveConfig(enabled=True)
    assert compute_heat_ratio(2.0, None, cfg, baseline_age_days=100) == 1.0


def test_compute_heat_ratio_tiny_baseline_returns_one():
    cfg = AdaptiveConfig(enabled=True, min_baseline_velocity=0.5)
    assert compute_heat_ratio(2.0, 0.2, cfg, baseline_age_days=100) == 1.0


def test_compute_heat_ratio_warmup_returns_one():
    cfg = AdaptiveConfig(enabled=True, warmup_days=3.0)
    assert compute_heat_ratio(2.0, 1.0, cfg, baseline_age_days=1.0) == 1.0


def test_compute_heat_ratio_clamps_high():
    cfg = AdaptiveConfig(enabled=True, warmup_days=3.0, ratio_clamp_max=3.0)
    assert compute_heat_ratio(100.0, 1.0, cfg, baseline_age_days=100) == 3.0


def test_compute_heat_ratio_clamps_low():
    cfg = AdaptiveConfig(enabled=True, warmup_days=3.0, ratio_clamp_min=0.5)
    assert compute_heat_ratio(0.01, 1.0, cfg, baseline_age_days=100) == 0.5


def test_compute_heat_ratio_computed_value():
    cfg = AdaptiveConfig(enabled=True, warmup_days=3.0, ratio_clamp_min=0.5, ratio_clamp_max=3.0)
    assert compute_heat_ratio(2.0, 1.0, cfg, baseline_age_days=100) == 2.0


def test_is_hot_candidate_gate1_scales_with_heat_ratio():
    # Window vote gain of 20 votes/h (5 votes over 15 min) with default
    # min_votes_gain_per_window=15: passes at ratio 1.0, fails at ratio 2.0.
    d = _deal(votes_pos=15, posted_at=datetime.now(UTC) - timedelta(hours=6))
    snaps = _snaps(10, 15, spacing_minutes=15)
    cfg = _cfg()
    assert is_hot_candidate(d, snaps, cfg, heat_ratio=1.0)
    assert not is_hot_candidate(d, snaps, cfg, heat_ratio=2.0)


def test_is_hot_candidate_gate1_fails_at_1_passes_at_lower_ratio():
    d = _deal(votes_pos=13, posted_at=datetime.now(UTC) - timedelta(hours=6))
    snaps = _snaps(10, 13, spacing_minutes=15)
    cfg = _cfg()
    assert not is_hot_candidate(d, snaps, cfg, heat_ratio=1.0)
    assert is_hot_candidate(d, snaps, cfg, heat_ratio=0.5)


def test_is_hot_candidate_gate2_scales_with_heat_ratio():
    # early_burst_min_votes default 25; deal has 25 votes, fresh.
    d = _deal(votes_pos=25, posted_at=datetime.now(UTC) - timedelta(minutes=30))
    snaps = _snaps(25)
    cfg = _cfg()
    assert is_hot_candidate(d, snaps, cfg, heat_ratio=1.0)
    assert not is_hot_candidate(d, snaps, cfg, heat_ratio=2.0)


def test_compute_hot_score_scales_with_heat_ratio():
    cfg = _cfg()
    d = _deal(votes_pos=40, posted_at=datetime.now(UTC) - timedelta(minutes=30))
    snaps = _snaps(0, 20, 40, spacing_minutes=20)
    score_ratio_1 = compute_hot_score(d, snaps, cfg, heat_ratio=1.0)
    score_ratio_low = compute_hot_score(d, snaps, cfg, heat_ratio=0.5)
    assert score_ratio_low > score_ratio_1
