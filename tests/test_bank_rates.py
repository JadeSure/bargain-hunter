"""Tests for the CDR bank-rates source. No network — httpx.get is monkeypatched
per tests/test_strategy_reddit.py:74-88, keyed by exact URL (params are sent
separately by httpx.get and never appear in the URL the fake receives)."""

import json
from pathlib import Path

import httpx

from bargain_hunter.sources import bank_rates as mod
from bargain_hunter.sources.bank_rates import BankRatesSource

FIXTURES = Path(__file__).parent / "fixtures"

BASE = "https://api.macquariebank.io"
LIST_URL = BASE + mod._PRODUCTS_PATH
DETAIL_URL = LIST_URL + "/SV001MBLSAV001"
BRAND = {"name": "Macquarie", "base": BASE, "x_v": 4}
CATEGORIES = ["TRANS_AND_SAVINGS_ACCOUNTS", "TERM_DEPOSITS", "CRED_AND_CHRG_CARDS"]


def _json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _fake_get(url_to_response, calls=None):
    """url_to_response: url -> (status, body_dict) | list of those, consumed in order."""

    def fake_get(url, params=None, headers=None, timeout=None):
        if calls is not None:
            calls.append((url, dict(headers or {})))
        entry = url_to_response.get(url)
        if entry is None:
            raise AssertionError(f"unexpected URL requested: {url}")
        item = entry.pop(0) if isinstance(entry, list) else entry
        status, body = item
        return httpx.Response(status, json=body, request=httpx.Request("GET", url))

    return fake_get


def _list_body(products):
    return {"data": {"products": products}, "meta": {"totalRecords": len(products)}}


def _product(last_updated: str) -> dict:
    return {
        "productId": "SV001MBLSAV001",
        "lastUpdated": last_updated,
        "productCategory": "TRANS_AND_SAVINGS_ACCOUNTS",
        "name": "Savings Account",
    }


LIST_ONE_PRODUCT = _list_body([_product("2026-06-11T00:01:00.001Z")])
LIST_ONE_PRODUCT_UPDATED = _list_body([_product("2026-08-18T00:01:00.001Z")])


# -- acceptance test -----------------------------------------------------------


def test_rate_rise_490_to_535_emits_one_deal(monkeypatch):
    # Run 1: first sighting -> seeds the snapshot, no deal.
    fake1 = _fake_get(
        {
            LIST_URL: (200, LIST_ONE_PRODUCT),
            DETAIL_URL: (200, _json("cds_product_detail_490.json")),
        }
    )
    monkeypatch.setattr(mod.httpx, "get", fake1)
    src1 = BankRatesSource(brands=[BRAND], product_categories=CATEGORIES)
    assert src1.fetch() == []
    snapshot = src1.next_snapshot
    assert snapshot["Macquarie:SV001MBLSAV001"]["rates"]["best_rate"] == 0.0490

    # Run 2: lastUpdated changed, rate rose from 4.90% to 5.35% -> exactly one deal.
    fake2 = _fake_get(
        {
            LIST_URL: (200, LIST_ONE_PRODUCT_UPDATED),
            DETAIL_URL: (200, _json("cds_product_detail_535.json")),
        }
    )
    monkeypatch.setattr(mod.httpx, "get", fake2)
    src2 = BankRatesSource(
        brands=[BRAND], product_categories=CATEGORIES, previous_snapshot=snapshot
    )
    deals = src2.fetch()

    assert len(deals) == 1
    deal = deals[0]
    assert deal.title == "Macquarie Savings Account: 5.35% p.a. (was 4.90%)"
    assert deal.source == "bank_rates"
    assert deal.deal_id == "Macquarie-SV001MBLSAV001"
    assert deal.currency == "AUD"
    assert deal.price is None
    assert deal.price_confidence is None


def test_5bp_rise_produces_no_deal(monkeypatch):
    detail_495 = {
        "data": {
            **_json("cds_product_detail_490.json")["data"],
            "depositRates": [{"rate": "0.0495"}],
        }
    }
    fake = _fake_get(
        {LIST_URL: (200, LIST_ONE_PRODUCT_UPDATED), DETAIL_URL: (200, detail_495)}
    )
    monkeypatch.setattr(mod.httpx, "get", fake)
    previous = {
        "Macquarie:SV001MBLSAV001": {
            "rates": {"best_rate": 0.0490, "bonus_points": None},
            "lastUpdated": "x",
        }
    }
    src = BankRatesSource(
        brands=[BRAND], product_categories=CATEGORIES, previous_snapshot=previous
    )
    assert src.fetch() == []


def test_rate_fall_produces_no_deal(monkeypatch):
    fake = _fake_get(
        {
            LIST_URL: (200, LIST_ONE_PRODUCT_UPDATED),
            DETAIL_URL: (200, _json("cds_product_detail_490.json")),
        }
    )
    monkeypatch.setattr(mod.httpx, "get", fake)
    previous = {
        "Macquarie:SV001MBLSAV001": {
            "rates": {"best_rate": 0.0535, "bonus_points": None},
            "lastUpdated": "x",
        }
    }
    src = BankRatesSource(
        brands=[BRAND], product_categories=CATEGORIES, previous_snapshot=previous
    )
    assert src.fetch() == []


def test_new_product_absent_from_snapshot_seeds_without_deal(monkeypatch):
    fake = _fake_get(
        {
            LIST_URL: (200, LIST_ONE_PRODUCT),
            DETAIL_URL: (200, _json("cds_product_detail_490.json")),
        }
    )
    monkeypatch.setattr(mod.httpx, "get", fake)
    src = BankRatesSource(brands=[BRAND], product_categories=CATEGORIES, previous_snapshot={})
    assert src.fetch() == []
    assert "Macquarie:SV001MBLSAV001" in src.next_snapshot


def test_empty_previous_snapshot_zero_deals_but_snapshot_written(monkeypatch):
    fake = _fake_get(
        {
            LIST_URL: (200, LIST_ONE_PRODUCT),
            DETAIL_URL: (200, _json("cds_product_detail_490.json")),
        }
    )
    monkeypatch.setattr(mod.httpx, "get", fake)
    src = BankRatesSource(brands=[BRAND], product_categories=CATEGORIES, previous_snapshot={})
    assert src.fetch() == []
    assert src.next_snapshot  # non-empty: at least the "_since" marker + seeded product
    assert mod._SINCE_KEY in src.next_snapshot


def test_category_filter_excludes_other_categories(monkeypatch):
    # A sibling RESIDENTIAL_MORTGAGES product in the same list response must never
    # trigger a detail call — it's outside the configured product_categories.
    other = {
        "productId": "LN1",
        "lastUpdated": "x",
        "productCategory": "RESIDENTIAL_MORTGAGES",
        "name": "Loan",
    }
    list_body = _list_body(LIST_ONE_PRODUCT["data"]["products"] + [other])
    calls = []
    fake = _fake_get(
        {
            LIST_URL: (200, list_body),
            DETAIL_URL: (200, _json("cds_product_detail_490.json")),
        },
        calls,
    )
    monkeypatch.setattr(mod.httpx, "get", fake)
    src = BankRatesSource(brands=[BRAND], product_categories=CATEGORIES, previous_snapshot={})
    src.fetch()
    assert not any("LN1" in url for url, _ in calls)


# -- version negotiation --------------------------------------------------------


# Real ING 406 body (verified live) — no digits at all, so any regex-based version
# parsing fails silently on it. This is the exact shape that made every ING/UBank
# detail call 406 and left the module a silent no-op in production.
ING_406_BODY = {
    "errors": [
        {
            "code": "urn:au-cds:error:cds-all:Header/UnsupportedVersion",
            "title": "Unsupported Version",
            "detail": "Not acceptable value in headers x-v or x-min-v",
        }
    ]
}


def test_sends_x_v_and_x_min_v_on_every_request(monkeypatch):
    calls = []
    fake = _fake_get(
        {
            LIST_URL: (200, LIST_ONE_PRODUCT_UPDATED),
            DETAIL_URL: (200, _json("cds_product_detail_535.json")),
        },
        calls,
    )
    monkeypatch.setattr(mod.httpx, "get", fake)
    previous = {
        "Macquarie:SV001MBLSAV001": {
            "rates": {"best_rate": 0.0490, "bonus_points": None},
            "lastUpdated": "x",
        }
    }
    BankRatesSource(
        brands=[BRAND], product_categories=CATEGORIES, previous_snapshot=previous
    ).fetch()
    assert len(calls) == 2  # list + detail
    for _url, headers in calls:
        assert headers["x-v"] == str(mod._MAX_VERSION)
        assert headers["x-min-v"] == "1"


def test_version_less_406_body_degrades_to_skip_without_losing_other_brands(monkeypatch):
    ing_base = "https://id.ob.ing.com.au"
    ing_list_url = ing_base + mod._PRODUCTS_PATH
    ing_brand = {"name": "ING", "base": ing_base}

    def fake_get(url, params=None, headers=None, timeout=None):
        req = httpx.Request("GET", url)
        if url == ing_list_url:
            return httpx.Response(406, json=ING_406_BODY, request=req)
        if url == LIST_URL:
            return httpx.Response(200, json=LIST_ONE_PRODUCT_UPDATED, request=req)
        if url == DETAIL_URL:
            return httpx.Response(200, json=_json("cds_product_detail_535.json"), request=req)
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(mod.httpx, "get", fake_get)
    previous = {
        "Macquarie:SV001MBLSAV001": {
            "rates": {"best_rate": 0.0490, "bonus_points": None},
            "lastUpdated": "x",
        }
    }
    src = BankRatesSource(
        brands=[ing_brand, BRAND], product_categories=CATEGORIES, previous_snapshot=previous
    )
    deals = src.fetch()  # does not raise
    assert len(deals) == 1
    assert deals[0].deal_id == "Macquarie-SV001MBLSAV001"


# -- resilience -------------------------------------------------------------


def test_one_brand_http_error_does_not_lose_others(monkeypatch):
    other_base = "https://api.up.com.au"
    other_list_url = other_base + mod._PRODUCTS_PATH
    other_detail_url = other_list_url + "/SV001MBLSAV001"
    other_brand = {"name": "Up", "base": other_base, "x_v": 4}

    def fake_get(url, params=None, headers=None, timeout=None):
        req = httpx.Request("GET", url)
        if url == LIST_URL:
            raise httpx.ConnectError("boom", request=req)
        if url == other_list_url:
            return httpx.Response(200, json=LIST_ONE_PRODUCT_UPDATED, request=req)
        if url == other_detail_url:
            return httpx.Response(200, json=_json("cds_product_detail_535.json"), request=req)
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(mod.httpx, "get", fake_get)
    previous = {
        "Up:SV001MBLSAV001": {
            "rates": {"best_rate": 0.0490, "bonus_points": None},
            "lastUpdated": "x",
        }
    }
    src = BankRatesSource(
        brands=[BRAND, other_brand],
        product_categories=CATEGORIES,
        previous_snapshot=previous,
    )
    deals = src.fetch()
    assert len(deals) == 1
    assert deals[0].deal_id == "Up-SV001MBLSAV001"


# -- pure parsing helpers -----------------------------------------------------


def test_display_name_skips_prefix_when_product_name_already_carries_brand():
    # Real Macquarie CDR product names already start with the brand.
    assert mod._display_name("Macquarie", "Macquarie Term Deposit") == "Macquarie Term Deposit"


def test_display_name_prefixes_brand_when_product_name_omits_it():
    # Real Westpac CDR product names (e.g. "Altitude Velocity Black") don't.
    expected = "Westpac Altitude Velocity Black"
    assert mod._display_name("Westpac", "Altitude Velocity Black") == expected


def test_decimal_rate_string_parsed():
    assert mod._best_deposit_rate({"depositRates": [{"rate": "0.0535"}]}) == 0.0535


def test_malformed_rate_skipped_without_crashing():
    assert mod._best_deposit_rate({"depositRates": [{"rate": "not-a-number"}, {}]}) is None
    assert mod._best_deposit_rate({}) is None


def test_bonus_rewards_value_parsed_from_real_fixture():
    detail = _json("cds_card_detail_velocity_black.json")["data"]
    assert mod._bonus_points(detail) == 150000


def test_loyalty_program_entries_are_not_mistaken_for_bonus_points():
    # Only LOYALTY_PROGRAM (earn-rate) entries, no BONUS_REWARDS -> None, not a
    # regex hit on "0.5"/"10,000" from the earn-rate free text.
    detail = {
        "features": [
            {"featureType": "LOYALTY_PROGRAM", "additionalInfo": "0.5 points per $1, up to 10,000"}
        ]
    }
    assert mod._bonus_points(detail) is None


# -- credit-card signup bonus (BONUS_REWARDS) --------------------------------


CARD_DETAIL_URL = LIST_URL + "/CCAltBlackVelocity"
LIST_ONE_CARD = _list_body(
    [
        {
            "productId": "CCAltBlackVelocity",
            "lastUpdated": "2026-07-13T00:41:32Z",
            "productCategory": "CRED_AND_CHRG_CARDS",
            "name": "Altitude Velocity Black",
        }
    ]
)


def test_bonus_points_rise_emits_deal(monkeypatch):
    fake = _fake_get(
        {
            LIST_URL: (200, LIST_ONE_CARD),
            CARD_DETAIL_URL: (200, _json("cds_card_detail_velocity_black.json")),
        }
    )
    monkeypatch.setattr(mod.httpx, "get", fake)
    previous = {
        "Macquarie:CCAltBlackVelocity": {
            "rates": {"best_rate": None, "bonus_points": 90000},
            "lastUpdated": "x",
        }
    }
    src = BankRatesSource(
        brands=[BRAND], product_categories=CATEGORIES, previous_snapshot=previous
    )
    deals = src.fetch()
    assert len(deals) == 1
    assert deals[0].title == "Macquarie Altitude Velocity Black: 150,000 bonus points (was 90,000)"


def test_bonus_points_rise_below_threshold_no_deal(monkeypatch):
    fake = _fake_get(
        {
            LIST_URL: (200, LIST_ONE_CARD),
            CARD_DETAIL_URL: (200, _json("cds_card_detail_velocity_black.json")),
        }
    )
    monkeypatch.setattr(mod.httpx, "get", fake)
    previous = {
        "Macquarie:CCAltBlackVelocity": {
            "rates": {"best_rate": None, "bonus_points": 145000},  # rise of 5000 < default 10000
            "lastUpdated": "x",
        }
    }
    src = BankRatesSource(
        brands=[BRAND], product_categories=CATEGORIES, previous_snapshot=previous
    )
    assert src.fetch() == []


def test_card_without_bonus_rewards_feature_yields_no_deal(monkeypatch):
    loyalty_only = {
        "data": {
            **_json("cds_card_detail_velocity_black.json")["data"],
            "features": [
                {"featureType": "LOYALTY_PROGRAM", "additionalInfo": "0.5 points per $1"}
            ],
        }
    }
    fake = _fake_get({LIST_URL: (200, LIST_ONE_CARD), CARD_DETAIL_URL: (200, loyalty_only)})
    monkeypatch.setattr(mod.httpx, "get", fake)
    previous = {
        "Macquarie:CCAltBlackVelocity": {
            "rates": {"best_rate": None, "bonus_points": 90000},
            "lastUpdated": "x",
        }
    }
    src = BankRatesSource(
        brands=[BRAND], product_categories=CATEGORIES, previous_snapshot=previous
    )
    assert src.fetch() == []
