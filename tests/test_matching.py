"""Tests for the watch-track keyword matching logic."""


from bargain_hunter.config import WatchConfig
from bargain_hunter.matching import filter_watch_matches, match_watch
from bargain_hunter.models import Deal, Subscriber


def _cfg(**kw) -> WatchConfig:
    return WatchConfig(**kw)


def _sub(**kw) -> Subscriber:
    defaults = dict(name="Alice", watch_keywords=[], min_discount_percent=None)
    defaults.update(kw)
    return Subscriber(**defaults)


def _deal(**kw) -> Deal:
    defaults = dict(
        source="ozbargain", deal_id="1", title="Test", url="https://ozbargain.com.au/node/1",
        votes_pos=10, votes_neg=0, comment_count=0,
    )
    defaults.update(kw)
    return Deal(**defaults)


# ---------------------------------------------------------------------------
# Basic keyword matching
# ---------------------------------------------------------------------------

def test_keyword_match_case_insensitive():
    deal = _deal(title="Apple iPhone 17 Pro Max 256GB $1,599")
    sub = _sub(watch_keywords=["iphone 17 pro"])
    matched, reason = match_watch(deal, sub, _cfg())
    # No price condition met (no discount / target price) — falls to noise guard
    # votes_pos=10 >= unpriced_min_votes=5 → should match
    assert matched
    assert "iphone 17 pro" in reason.lower()


def test_keyword_no_match():
    deal = _deal(title="Samsung TV 55inch $799")
    sub = _sub(watch_keywords=["iPhone 17 Pro"])
    matched, _ = match_watch(deal, sub, _cfg())
    assert not matched


def test_keyword_with_discount():
    deal = _deal(
        title="Sony WH-1000XM5 $249 (was $449) 44% off", discount_percent=44.0, price=249.0
    )
    sub = _sub(watch_keywords=["Sony WH"], min_discount_percent=20.0)
    matched, reason = match_watch(deal, sub, _cfg())
    assert matched
    assert "44" in reason


def test_keyword_with_target_price():
    deal = _deal(title="Dyson V15 $499", price=499.0)
    sub = _sub(watch_keywords=["Dyson V15 <=600"])
    matched, reason = match_watch(deal, sub, _cfg())
    assert matched
    assert "499" in reason


def test_target_price_not_met():
    deal = _deal(title="Dyson V15 $750", price=750.0)
    sub = _sub(watch_keywords=["Dyson V15 <=600"])
    matched, _ = match_watch(deal, sub, _cfg())
    assert not matched


# ---------------------------------------------------------------------------
# Unpriced noise guard
# ---------------------------------------------------------------------------

def test_unpriced_passes_with_enough_votes():
    deal = _deal(title="SSD deal", votes_pos=10)
    sub = _sub(watch_keywords=["SSD"])
    matched, _ = match_watch(deal, sub, _cfg(unpriced_min_votes=5))
    assert matched


def test_unpriced_blocked_by_low_votes():
    deal = _deal(title="SSD deal", votes_pos=2)
    sub = _sub(watch_keywords=["SSD"])
    matched, _ = match_watch(deal, sub, _cfg(unpriced_min_votes=5))
    assert not matched


# ---------------------------------------------------------------------------
# filter_watch_matches
# ---------------------------------------------------------------------------

def test_filter_returns_matching_deals():
    deals = [
        _deal(deal_id="1", title="iPhone 17 Pro $1,599", price=1599.0),
        _deal(deal_id="2", title="Macbook Air M4 $1,299", price=1299.0),
        _deal(deal_id="3", title="Samsung TV $799", price=799.0),
    ]
    sub = _sub(watch_keywords=["iPhone 17 Pro <=2000", "Macbook Air"])
    results = filter_watch_matches(deals, sub, _cfg())
    keys = {d.deal_id for d, _ in results}
    assert "1" in keys
    assert "2" in keys
    assert "3" not in keys
