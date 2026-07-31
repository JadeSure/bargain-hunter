"""Tests for cashback enrichment (config-maintained merchant→rate stacking)."""

from bargain_hunter.cashback import enrich_cashback, match_cashback_rate
from bargain_hunter.config import CashbackConfig
from bargain_hunter.models import Deal

RATES = {"amazon.com.au": 5.0, "jbhifi.com.au": 10.0, "shop.example.com": 8.0, "example.com": 2.0}


def _deal(**kw) -> Deal:
    base = {"source": "ozbargain", "deal_id": "1", "title": "x", "url": "https://x/node/1"}
    base.update(kw)
    return Deal(**base)


def test_exact_host_match():
    assert match_cashback_rate("https://amazon.com.au/dp/B0", RATES) == ("amazon.com.au", 5.0)


def test_www_and_subdomain_match():
    assert match_cashback_rate("https://www.amazon.com.au/dp/B0", RATES) == ("amazon.com.au", 5.0)
    assert match_cashback_rate("https://smile.amazon.com.au/x", RATES) == ("amazon.com.au", 5.0)


def test_longest_key_wins():
    # shop.example.com is more specific than example.com.
    assert match_cashback_rate("https://shop.example.com/x", RATES) == ("shop.example.com", 8.0)
    assert match_cashback_rate("https://blog.example.com/x", RATES) == ("example.com", 2.0)


def test_no_match_and_empty():
    assert match_cashback_rate("https://kmart.com.au/x", RATES) is None
    assert match_cashback_rate(None, RATES) is None
    assert match_cashback_rate("https://amazon.com.au/x", {}) is None


def test_enrich_prefers_merchant_url():
    deal = _deal(url="https://www.ozbargain.com.au/node/1", merchant_url="https://www.amazon.com.au/dp/B0")
    enrich_cashback(deal, CashbackConfig(enabled=True, provider_label="ShopBack", rates=RATES))
    assert deal.cashback_percent == 5.0
    assert deal.cashback_provider == "ShopBack"


def test_enrich_falls_back_to_url():
    deal = _deal(url="https://www.jbhifi.com.au/products/x", merchant_url=None)
    enrich_cashback(deal, CashbackConfig(enabled=True, rates=RATES))
    assert deal.cashback_percent == 10.0


def test_enrich_disabled_is_noop():
    deal = _deal(merchant_url="https://www.amazon.com.au/dp/B0")
    enrich_cashback(deal, CashbackConfig(enabled=False, rates=RATES))
    assert deal.cashback_percent is None
    assert deal.cashback_provider is None


def test_enrich_no_match_leaves_none():
    deal = _deal(merchant_url="https://www.kmart.com.au/x")
    enrich_cashback(deal, CashbackConfig(enabled=True, rates=RATES))
    assert deal.cashback_percent is None
