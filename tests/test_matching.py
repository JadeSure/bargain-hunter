"""Tests for the watch-track keyword matching logic."""

from datetime import UTC, datetime, timedelta

from bargain_hunter.config import WatchConfig
from bargain_hunter.matching import _parse_keyword, filter_watch_matches, match_watch
from bargain_hunter.models import Deal, Subscriber


def _cfg(**kw) -> WatchConfig:
    return WatchConfig(**kw)


def _sub(**kw) -> Subscriber:
    defaults = dict(name="Alice", watch_keywords=[], min_discount_percent=None)
    defaults.update(kw)
    return Subscriber(**defaults)


def _deal(**kw) -> Deal:
    defaults = dict(
        source="ozbargain",
        deal_id="1",
        title="Test",
        url="https://ozbargain.com.au/node/1",
        votes_pos=10,
        votes_neg=0,
        comment_count=0,
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


# ---------------------------------------------------------------------------
# _parse_keyword: expiry parsing
# ---------------------------------------------------------------------------


def test_parse_keyword_bare():
    phrase, price, expiry = _parse_keyword("BWS")
    assert phrase == "BWS"
    assert price is None
    assert expiry is None


def test_parse_keyword_with_price():
    phrase, price, expiry = _parse_keyword("Dyson <=499")
    assert phrase == "Dyson"
    assert price == 499.0
    assert expiry is None


def test_parse_keyword_absolute_expiry():
    phrase, price, expiry = _parse_keyword("BWS @2030-01-15T19:00")
    assert phrase == "BWS"
    assert price is None
    assert expiry is not None
    assert expiry.tzinfo is not None  # always UTC-aware


def test_parse_keyword_all_parts():
    phrase, price, expiry = _parse_keyword("Sony WH <=300 @2030-06-01T23:59")
    assert phrase == "Sony WH"
    assert price == 300.0
    assert expiry is not None


def test_parse_keyword_hhmm_returns_aware():
    phrase, price, expiry = _parse_keyword("BWS @19:00")
    assert phrase == "BWS"
    assert expiry is not None
    assert expiry.tzinfo is not None


# ---------------------------------------------------------------------------
# Keyword expiry: match_watch with explicit `now`
# ---------------------------------------------------------------------------


def _future_utc(minutes: int = 60) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=minutes)


def _past_utc(minutes: int = 60) -> datetime:
    return datetime.now(UTC) - timedelta(minutes=minutes)


def test_expired_keyword_skipped():
    """A keyword whose expiry has already passed should never match."""
    # Use absolute datetime format so the test is deterministic
    expired_kw = "BWS @2020-01-01T00:00"
    deal = _deal(title="BWS 10% off selected wines", price=20.0, discount_percent=10.0)
    sub = _sub(watch_keywords=[expired_kw])
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=UTC)
    matched, _ = match_watch(deal, sub, _cfg(), now=now)
    assert not matched


def test_not_yet_expired_keyword_matches():
    """A keyword with a future expiry should still match normally."""
    future_kw = "BWS @2099-12-31T23:59"
    deal = _deal(title="BWS 20% off beer", price=15.0, discount_percent=20.0)
    sub = _sub(watch_keywords=[future_kw], min_discount_percent=10.0)
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=UTC)
    matched, reason = match_watch(deal, sub, _cfg(), now=now)
    assert matched
    assert "BWS" in reason


def test_expired_keyword_with_price_target_skipped():
    """Even if price target is met, expired keyword must not match."""
    kw = "Dyson <=600 @2020-01-01T00:00"
    deal = _deal(title="Dyson V15 $499", price=499.0)
    sub = _sub(watch_keywords=[kw])
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=UTC)
    matched, _ = match_watch(deal, sub, _cfg(), now=now)
    assert not matched


def test_expiry_at_exact_boundary_is_expired():
    """now == expiry means the keyword has expired (boundary is exclusive)."""
    kw = "BWS @2026-06-18T09:00"  # 19:00 AEST = 09:00 UTC
    deal = _deal(title="BWS wine deal", votes_pos=20)
    sub = _sub(watch_keywords=[kw])
    # now == expiry exactly
    expiry_utc = datetime(2026, 6, 18, 9, 0, 0, tzinfo=UTC)
    matched, _ = match_watch(deal, sub, _cfg(unpriced_min_votes=5), now=expiry_utc)
    assert not matched


def test_one_expired_one_valid_keyword():
    """Only the valid (non-expired) keyword triggers a match."""
    deal = _deal(title="BWS and Dan Murphy wines", votes_pos=20)
    sub = _sub(
        watch_keywords=[
            "BWS @2020-01-01T00:00",  # expired
            "Dan Murphy @2099-12-31T23:59",  # valid
        ]
    )
    now = datetime(2026, 6, 18, 12, 0, 0, tzinfo=UTC)
    matched, reason = match_watch(deal, sub, _cfg(unpriced_min_votes=5), now=now)
    assert matched
    assert "Dan Murphy" in reason
