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
    fake = _fake_get({LIST_URL: (200, LIST_ONE_PRODUCT_UPDATED), DETAIL_URL: (200, detail_495)})
    monkeypatch.setattr(mod.httpx, "get", fake)
    previous = {
        "Macquarie:SV001MBLSAV001": {
            "rates": {"best_rate": 0.0490, "bonus_points": None},
            "lastUpdated": "x",
        }
    }
    src = BankRatesSource(brands=[BRAND], product_categories=CATEGORIES, previous_snapshot=previous)
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
    src = BankRatesSource(brands=[BRAND], product_categories=CATEGORIES, previous_snapshot=previous)
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


# -- leaderboard rows (frontend artifact, see leaderboard.py) -----------------


def test_leaderboard_row_written_for_freshly_detailed_product(monkeypatch):
    fake = _fake_get(
        {LIST_URL: (200, LIST_ONE_PRODUCT), DETAIL_URL: (200, _json("cds_product_detail_490.json"))}
    )
    monkeypatch.setattr(mod.httpx, "get", fake)
    src = BankRatesSource(brands=[BRAND], product_categories=CATEGORIES)
    src.fetch()

    row = src.next_leaderboard["Macquarie:SV001MBLSAV001"]
    assert row["brand"] == "Macquarie"
    assert row["name"] == "Macquarie Savings Account"
    assert row["category"] == "TRANS_AND_SAVINGS_ACCOUNTS"
    assert row["best_rate"] == 0.0490
    assert row["bonus_points"] is None


def test_leaderboard_row_carried_forward_when_unchanged(monkeypatch):
    # lastUpdated matches the snapshot -> no detail call this run, but the row
    # must still be present (carried from previous_leaderboard).
    fake = _fake_get({LIST_URL: (200, LIST_ONE_PRODUCT)})
    monkeypatch.setattr(mod.httpx, "get", fake)
    previous_snapshot = {
        "Macquarie:SV001MBLSAV001": {
            "rates": {"best_rate": 0.0490, "bonus_points": None},
            "lastUpdated": "2026-06-11T00:01:00.001Z",
        }
    }
    previous_leaderboard = {
        "Macquarie:SV001MBLSAV001": {
            "brand": "Macquarie",
            "name": "Macquarie Savings Account",
            "category": "TRANS_AND_SAVINGS_ACCOUNTS",
            "best_rate": 0.0490,
            "bonus_points": None,
            "url": BASE,
        }
    }
    src = BankRatesSource(
        brands=[BRAND],
        product_categories=CATEGORIES,
        previous_snapshot=previous_snapshot,
        previous_leaderboard=previous_leaderboard,
    )
    src.fetch()

    assert (
        src.next_leaderboard["Macquarie:SV001MBLSAV001"]
        == previous_leaderboard["Macquarie:SV001MBLSAV001"]
    )


def test_leaderboard_row_carried_forward_on_brand_failure(monkeypatch):
    def fake_get_blip(url, params=None, headers=None, timeout=None):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr(mod.httpx, "get", fake_get_blip)
    previous_leaderboard = {
        "Macquarie:SV001MBLSAV001": {
            "brand": "Macquarie",
            "name": "Macquarie Savings Account",
            "category": "TRANS_AND_SAVINGS_ACCOUNTS",
            "best_rate": 0.0490,
            "bonus_points": None,
            "url": BASE,
        }
    }
    src = BankRatesSource(
        brands=[BRAND],
        product_categories=CATEGORIES,
        previous_leaderboard=previous_leaderboard,
    )
    src.fetch()

    # Whole brand's list call failed -- row must stay exactly as seeded, not vanish.
    assert src.next_leaderboard == previous_leaderboard


def test_leaderboard_row_omitted_when_product_has_no_rate_or_bonus(monkeypatch):
    product = _list_body(
        [
            {
                "productId": "OD1",
                "lastUpdated": "x",
                "productCategory": "TRANS_AND_SAVINGS_ACCOUNTS",
                "name": "Plain",
            }
        ]
    )
    detail_url = LIST_URL + "/OD1"
    fake = _fake_get({LIST_URL: (200, product), detail_url: (200, {"data": {}})})
    monkeypatch.setattr(mod.httpx, "get", fake)
    src = BankRatesSource(brands=[BRAND], product_categories=CATEGORIES)
    src.fetch()

    assert src.next_leaderboard == {}


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


def test_transient_list_blip_does_not_lose_baseline_for_a_later_rate_rise(monkeypatch):
    # run1: first sighting -> seeds the snapshot at 4.90%.
    fake1 = _fake_get(
        {LIST_URL: (200, LIST_ONE_PRODUCT), DETAIL_URL: (200, _json("cds_product_detail_490.json"))}
    )
    monkeypatch.setattr(mod.httpx, "get", fake1)
    src1 = BankRatesSource(brands=[BRAND], product_categories=CATEGORIES)
    assert src1.fetch() == []
    snap1 = src1.next_snapshot
    assert snap1["Macquarie:SV001MBLSAV001"]["rates"]["best_rate"] == 0.0490

    # run2: transient network blip on the brand's LIST call -- must not wipe
    # the baseline down to nothing.
    def fake_get_blip(url, params=None, headers=None, timeout=None):
        if url == LIST_URL:
            raise httpx.ConnectError("boom", request=httpx.Request("GET", url))
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(mod.httpx, "get", fake_get_blip)
    src2 = BankRatesSource(brands=[BRAND], product_categories=CATEGORIES, previous_snapshot=snap1)
    assert src2.fetch() == []
    snap2 = src2.next_snapshot
    assert snap2["Macquarie:SV001MBLSAV001"] == snap1["Macquarie:SV001MBLSAV001"]  # carried forward

    # run3: rate genuinely rose to 5.35% -- must still be detected against the
    # run1 baseline (via run2's carry-forward), not treated as brand new.
    fake3 = _fake_get(
        {
            LIST_URL: (200, LIST_ONE_PRODUCT_UPDATED),
            DETAIL_URL: (200, _json("cds_product_detail_535.json")),
        }
    )
    monkeypatch.setattr(mod.httpx, "get", fake3)
    src3 = BankRatesSource(brands=[BRAND], product_categories=CATEGORIES, previous_snapshot=snap2)
    deals = src3.fetch()
    assert len(deals) == 1
    assert deals[0].title == "Macquarie Savings Account: 5.35% p.a. (was 4.90%)"


def test_detail_fetch_failure_carries_baseline_forward(monkeypatch):
    previous = {
        "Macquarie:SV001MBLSAV001": {
            "rates": {"best_rate": 0.0490, "bonus_points": None},
            "lastUpdated": "2026-06-11T00:01:00.001Z",
        }
    }

    def fake_get_detail_fails(url, params=None, headers=None, timeout=None):
        req = httpx.Request("GET", url)
        if url == LIST_URL:
            return httpx.Response(200, json=LIST_ONE_PRODUCT_UPDATED, request=req)
        if url == DETAIL_URL:
            raise httpx.ConnectError("boom", request=req)
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(mod.httpx, "get", fake_get_detail_fails)
    src = BankRatesSource(brands=[BRAND], product_categories=CATEGORIES, previous_snapshot=previous)
    assert src.fetch() == []
    assert src.next_snapshot["Macquarie:SV001MBLSAV001"] == previous["Macquarie:SV001MBLSAV001"]
    assert mod._SINCE_KEY not in src.next_snapshot  # held back: no prior cursor to hold


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


def test_bonus_points_takes_max_not_first_across_multiple_entries():
    # CDR doesn't guarantee array order; cards can carry multiple concurrent
    # BONUS_REWARDS entries. Verified live on a real CommBank card
    # (productId e15ed5da59354af78c9e8aa0f4f841cf): raw order was
    # [170000, 200000] -- the correct value is the max (200000), not the
    # first-seen (170000).
    detail = {
        "features": [
            {"featureType": "BONUS_REWARDS", "additionalValue": "170000"},
            {"featureType": "BONUS_REWARDS", "additionalValue": "200000"},
        ]
    }
    assert mod._bonus_points(detail) == 200000


def test_bonus_points_skips_malformed_entry_instead_of_aborting():
    detail = {
        "features": [
            {"featureType": "BONUS_REWARDS", "additionalValue": "not-a-number"},
            {"featureType": "BONUS_REWARDS", "additionalValue": "90000"},
        ]
    }
    assert mod._bonus_points(detail) == 90000


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
    src = BankRatesSource(brands=[BRAND], product_categories=CATEGORIES, previous_snapshot=previous)
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
    src = BankRatesSource(brands=[BRAND], product_categories=CATEGORIES, previous_snapshot=previous)
    assert src.fetch() == []


# -- detail-fetch cap --------------------------------------------------------


def _multi_product_list(n: int) -> dict:
    products = [
        {
            "productId": f"P{i}",
            "lastUpdated": f"2026-08-{10 + i:02d}T00:00:00Z",
            "productCategory": "TRANS_AND_SAVINGS_ACCOUNTS",
            "name": f"Account {i}",
        }
        for i in range(n)
    ]
    return _list_body(products)


def test_detail_fetch_cap_defers_excess_products(monkeypatch):
    list_body = _multi_product_list(3)
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        req = httpx.Request("GET", url)
        if url == LIST_URL:
            return httpx.Response(200, json=list_body, request=req)
        return httpx.Response(200, json=_json("cds_product_detail_490.json"), request=req)

    monkeypatch.setattr(mod.httpx, "get", fake_get)
    src = BankRatesSource(
        brands=[BRAND],
        product_categories=CATEGORIES,
        previous_snapshot={},
        max_detail_fetches_per_run=2,
    )
    src.fetch()

    detail_calls = [u for u in calls if u != LIST_URL]
    assert len(detail_calls) == 2  # capped, not 3
    seeded = [k for k in src.next_snapshot if k != mod._SINCE_KEY]
    assert len(seeded) == 2  # the 3rd product is left out entirely, to be retried later
    assert mod._SINCE_KEY not in src.next_snapshot  # no prior cursor to hold, so none written


def test_detail_fetch_cap_holds_since_cursor_instead_of_advancing(monkeypatch):
    list_body = _multi_product_list(2)
    old_since = "2026-08-01T00:00:00Z"

    def fake_get(url, params=None, headers=None, timeout=None):
        req = httpx.Request("GET", url)
        if url == LIST_URL:
            return httpx.Response(200, json=list_body, request=req)
        return httpx.Response(200, json=_json("cds_product_detail_490.json"), request=req)

    monkeypatch.setattr(mod.httpx, "get", fake_get)
    src = BankRatesSource(
        brands=[BRAND],
        product_categories=CATEGORIES,
        previous_snapshot={mod._SINCE_KEY: old_since},
        max_detail_fetches_per_run=1,
    )
    src.fetch()

    # Held back, not advanced to `now`: an advanced cursor could make the next
    # run's updated-since filter drop the still-pending product forever.
    assert src.next_snapshot[mod._SINCE_KEY] == old_since


def test_since_timestamp_is_exact_cds_shape_not_isoformat():
    # Verified live: 9 of 10 configured brands 400 on datetime.isoformat(),
    # with or without fractional seconds, "+00:00" or not -- only the exact
    # "yyyy-MM-ddTHH:mm:ssZ" shape is accepted by all ten. See module docstring
    # and _cdr_timestamp()'s comment: don't let this regress to .isoformat().
    from datetime import UTC, datetime, timedelta, timezone

    dt = datetime(2026, 8, 20, 14, 15, 9, 123456, tzinfo=UTC)
    result = mod._cdr_timestamp(dt)
    assert result == "2026-08-20T14:15:09Z"
    # Both real-world-rejected isoformat() shapes must differ from our output.
    assert result != dt.isoformat()  # "...T14:15:09.123456+00:00": fractional seconds
    no_micro = dt.replace(microsecond=0).isoformat()
    assert result != no_micro  # "...T14:15:09+00:00": "+00:00" instead of "Z"

    # Non-UTC input (e.g. AEST) must convert to UTC before formatting.
    aest = datetime(2026, 8, 21, 0, 15, 9, tzinfo=timezone(timedelta(hours=10)))
    assert mod._cdr_timestamp(aest) == "2026-08-20T14:15:09Z"


def test_card_without_bonus_rewards_feature_yields_no_deal(monkeypatch):
    loyalty_only = {
        "data": {
            **_json("cds_card_detail_velocity_black.json")["data"],
            "features": [{"featureType": "LOYALTY_PROGRAM", "additionalInfo": "0.5 points per $1"}],
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
    src = BankRatesSource(brands=[BRAND], product_categories=CATEGORIES, previous_snapshot=previous)
    assert src.fetch() == []
