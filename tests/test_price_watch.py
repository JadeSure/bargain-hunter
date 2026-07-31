"""Tests for Amazon target-price watches (ASIN matching against the CCC feed)."""

from datetime import UTC, datetime

from bargain_hunter.config import WatchConfig
from bargain_hunter.matching import _extract_asin, filter_watch_matches, match_watch
from bargain_hunter.models import Deal, Subscriber

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
CFG = WatchConfig(min_votes=15, min_discount_percent=15, max_deal_age_hours=48)


def _ccc(asin, price, discount=20.0):
    return Deal(
        source="camelcamelcamel",
        deal_id=asin,
        title="Some Product",
        url=f"https://au.camelcamelcamel.com/product/{asin}",
        merchant_url=f"https://www.amazon.com.au/dp/{asin}",
        price=price,
        discount_percent=discount,
        price_confidence="high",
        posted_at=NOW,
    )


def _sub(keywords):
    return Subscriber(name="t", email="t@example.com", watch_keywords=keywords)


def test_extract_asin_url_and_bare():
    assert _extract_asin("https://www.amazon.com.au/dp/B08166SLDF") == "B08166SLDF"
    assert _extract_asin("https://www.amazon.com.au/gp/product/B08166SLDF?ref=x") == "B08166SLDF"
    assert _extract_asin("B08166SLDF") == "B08166SLDF"
    assert _extract_asin("b08166sldf") == "B08166SLDF"


def test_extract_asin_rejects_ordinary_keywords():
    assert _extract_asin("iPhone 17 Pro") is None
    assert _extract_asin("Nintendo12") is None  # not a B0-ASIN
    assert _extract_asin("Sony WH1000") is None


def test_asin_watch_fires_below_target():
    deal = _ccc("B08166SLDF", price=1400.0)
    matched, reason = match_watch(deal, _sub(["B08166SLDF <=1500"]), CFG, now=NOW)
    assert matched
    assert "B08166SLDF" in reason and "1400" in reason


def test_asin_watch_url_form_fires():
    deal = _ccc("B08166SLDF", price=1400.0)
    kw = "https://www.amazon.com.au/dp/B08166SLDF <=1500"
    matched, _ = match_watch(deal, _sub([kw]), CFG, now=NOW)
    assert matched


def test_asin_watch_above_target_no_match():
    deal = _ccc("B08166SLDF", price=1600.0)
    matched, _ = match_watch(deal, _sub(["B08166SLDF <=1500"]), CFG, now=NOW)
    assert not matched


def test_asin_watch_bypasses_noise_guard():
    # 0 votes and low discount would fail the normal guard; ASIN+target overrides.
    deal = _ccc("B08166SLDF", price=1400.0, discount=1.0)
    deal.votes_pos = 0
    matched, _ = match_watch(deal, _sub(["B08166SLDF <=1500"]), CFG, now=NOW)
    assert matched


def test_asin_watch_wrong_product_no_match():
    deal = _ccc("B000000000", price=10.0)
    matched, _ = match_watch(deal, _sub(["B08166SLDF <=1500"]), CFG, now=NOW)
    assert not matched


def test_asin_watch_ignores_non_ccc_source():
    ozb = Deal(
        source="ozbargain", deal_id="B08166SLDF", title="x",
        url="https://www.ozbargain.com.au/node/1", votes_pos=100,
    )
    matched, _ = match_watch(ozb, _sub(["B08166SLDF <=1500"]), CFG, now=NOW)
    assert not matched


def test_asin_watch_no_target_alerts_on_any_drop():
    deal = _ccc("B08166SLDF", price=99.0)
    matched, reason = match_watch(deal, _sub(["B08166SLDF"]), CFG, now=NOW)
    assert matched
    assert "price drop" in reason


def test_asin_watch_returns_target_for_dedup():
    deal = _ccc("B08166SLDF", price=1400.0)
    results = filter_watch_matches([deal], _sub(["B08166SLDF <=1500"]), CFG, now=NOW)
    assert len(results) == 1
    _, _, target = results[0]
    assert target == 1500.0
