"""Tests for per-subscriber hot-deal routing (_hot_level_eligible)."""

from bargain_hunter.main import _hot_level_eligible
from bargain_hunter.models import Deal, Subscriber

# good=0, great=1, top=2 (higher = more valuable)
TIER_RANK = {"good": 0, "great": 1, "top": 2}
TOP = "top"
TAXONOMY = {"electronics": ["Computing", "Monitor"], "food": ["Wine"]}


def _deal(categories=None) -> Deal:
    return Deal(
        source="ozbargain",
        deal_id="1",
        title="Thing",
        url="https://x",
        categories=categories or [],
    )


def _sub(**kw) -> Subscriber:
    return Subscriber(name="t", email="t@e.com", **kw)


def _eligible(deal, level, sub, universal_top=True) -> bool:
    return _hot_level_eligible(
        deal,
        level,
        sub,
        tier_rank=TIER_RANK,
        top_name=TOP,
        taxonomy=TAXONOMY,
        universal_top=universal_top,
    )


def test_no_categories_no_floor_receives_all_levels():
    sub = _sub()
    d = _deal(["Computing"])
    assert _eligible(d, "good", sub)
    assert _eligible(d, "great", sub)
    assert _eligible(d, "top", sub)


def test_min_level_floor_blocks_lower_tiers():
    sub = _sub(min_hot_level="great")
    d = _deal()
    assert not _eligible(d, "good", sub)
    assert _eligible(d, "great", sub)
    assert _eligible(d, "top", sub)


def test_category_restricted_gets_in_category_at_floor():
    # "computer only, great & up" → great computing deal is eligible.
    sub = _sub(categories=["electronics"], min_hot_level="great")
    assert _eligible(_deal(["Computing"]), "great", sub)


def test_category_restricted_blocks_out_of_category_lower_tier():
    # great non-computer deal must NOT reach a computer-only subscriber.
    sub = _sub(categories=["electronics"])
    assert not _eligible(_deal(["Wine"]), "great", sub)


def test_universal_top_reaches_out_of_category():
    # top non-computer deal still reaches a computer-only subscriber (universal_top).
    sub = _sub(categories=["electronics"])
    assert _eligible(_deal(["Wine"]), "top", sub, universal_top=True)


def test_hard_mode_blocks_out_of_category_top():
    # With universal_top off, even top deals are filtered to the chosen categories.
    sub = _sub(categories=["electronics"])
    assert not _eligible(_deal(["Wine"]), "top", sub, universal_top=False)


def test_in_category_top_always_eligible():
    sub = _sub(categories=["electronics"], min_hot_level="good")
    assert _eligible(_deal(["Monitor"]), "top", sub)


def test_floor_applies_even_in_category():
    # A "top only" computer fan should not get a great-tier computer deal.
    sub = _sub(categories=["electronics"], min_hot_level="top")
    assert not _eligible(_deal(["Computing"]), "great", sub)
    assert _eligible(_deal(["Computing"]), "top", sub)
