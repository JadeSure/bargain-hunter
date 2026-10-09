"""Tests for the Bargain Radar source, against a frozen fixture -- no network.

bargainradar_items.json is real /api/items output captured 2026-10-09, with two
hand edits: the Good Guys item (2145c201-...) has isReportedForSaleExpiry set
true, and the second Myer item (5d3f9dab-...) has discount lowered to 0.12 to
sit below the floor. The David Jones RETURNED item sits exactly on the 20% floor
and the Amazon item is outside the store allowlist.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from bargain_hunter.config import HotConfig, ScoringConfig, load_settings
from bargain_hunter.models import Deal
from bargain_hunter.scoring import classify_hot, is_hot_candidate
from bargain_hunter.sources import bargainradar as mod
from bargain_hunter.sources.bargainradar import BargainRadarSource, _parse_sydney

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "bargainradar_items.json").read_text(encoding="utf-8")
)

MYER_SUITCASE = "fcfa2bec-775b-4d41-bf1e-a2ffc7cb6d38"
DJ_VACUUM = "4ff43134-a3fc-458c-8bd8-d5479e4c8fab"
DJ_AT_FLOOR = "6ae194f8-0821-4e0a-955b-be701badf126"
BIGW_HEADPHONES = "7b08a8b9-f622-4f53-8a2f-0fad970bd8a4"
GOODGUYS_EXPIRED = "2145c201-b00b-42c0-9f77-c57a48408df5"
DJ_VACUUM_URL = "https://www.davidjones.com/product/dreame-aqua10-roller-robot-vacuum-cleaner-27989136"

# Same stores as sources.bargainradar in config/settings.yaml (no amazon).
STORES = [
    "jb hi-fi", "the good guys", "bing lee", "big w", "target", "myer",
    "david jones", "bunnings", "officeworks", "costco", "total tools", "sydney tools",
]


def _source(**kwargs) -> BargainRadarSource:
    return BargainRadarSource(stores=STORES, min_discount_percent=20, **kwargs)


def _deals() -> dict[str, Deal]:
    return {d.deal_id: d for d in _source()._parse(FIXTURE)}


def _item(item_id: str, store: str = "myer") -> dict:
    return {
        "id": item_id,
        "name": "Widget",
        "store": store,
        "url": f"https://example.com/{item_id}",
        "updateType": "NEW",
        "discount": 0.5,
        "newPrice": 10,
        "oldPrice": 20,
        "updatedAt": "2026-10-09T20:19:24",
    }


# -- parsing -------------------------------------------------------------------


def test_parse_keeps_in_store_items_at_or_above_floor():
    # The at-floor item is kept; the Amazon and 12%-off items are dropped.
    assert set(_deals()) == {
        MYER_SUITCASE,
        DJ_VACUUM,
        DJ_AT_FLOOR,
        BIGW_HEADPHONES,
        GOODGUYS_EXPIRED,
    }


def test_deal_mapping():
    deal = _deals()[DJ_VACUUM]
    assert deal.source == "bargainradar"
    assert deal.url == f"https://bargainradar.com.au/item/{DJ_VACUUM}"
    assert deal.merchant_url == DJ_VACUUM_URL
    assert deal.title.startswith("Dreame - Aqua10")
    assert deal.title.endswith("(David Jones)")
    assert deal.price == 1299.0
    assert deal.was_price == 2499.0
    assert deal.discount_percent == 48.0
    assert deal.price_confidence == "high"
    assert deal.currency == "AUD"
    # 20:19:24 Sydney on 2026-10-09 is AEDT (+11).
    assert deal.posted_at == datetime(2026, 10, 9, 9, 19, 24, tzinfo=UTC)
    assert deal.expired is False


def test_sale_expiry_report_marks_deal_expired():
    assert _deals()[GOODGUYS_EXPIRED].expired is True


def test_was_price_only_when_above_price():
    # newPrice is 10: an oldPrice that isn't higher is not a usable "was" price.
    assert _source()._to_deal({**_item("a"), "oldPrice": 20}).was_price == 20.0
    assert _source()._to_deal({**_item("a"), "oldPrice": 10}).was_price is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2026-07-01T12:00:00", datetime(2026, 7, 1, 2, 0, tzinfo=UTC)),  # AEST, +10
        ("2026-01-15T12:00:00", datetime(2026, 1, 15, 1, 0, tzinfo=UTC)),  # AEDT, +11
        ("garbage", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_sydney(text, expected):
    assert _parse_sydney(text) == expected


def test_store_display_names():
    jb = _source()._to_deal(_item("a", store="jb hi-fi"))
    assert jb.title.endswith("(JB Hi-Fi)")  # not str.title()'s "Jb Hi-Fi"
    assert _deals()[BIGW_HEADPHONES].title.endswith("(Big W)")


@pytest.mark.parametrize(
    "change",
    [
        {"updateType": "DISCOUNT_DOWN"},
        {"updateType": "DELETED"},
        {"newPrice": 0},
        {"discount": True},  # bools are not numbers
        {"url": ""},
    ],
)
def test_non_deal_or_malformed_items_dropped(change):
    assert _source()._to_deal({**_item("a"), **change}) is None


# -- fetch(): request shape, pagination, errors ---------------------------------


def _response(payload: dict, status: int = 200) -> httpx.Response:
    # raise_for_status() needs the request attached, as on a real response.
    return httpx.Response(status, json=payload, request=httpx.Request("POST", mod.API_URL))


def _page(page: int, size: int, count: int) -> httpx.Response:
    items = [_item(f"page{page}-{i}") for i in range(size)]
    return _response({"count": count, "items": items})


def _patch_post(monkeypatch, respond) -> list[dict]:
    """Replace httpx.post with ``respond(page_number)``; return each call's kwargs."""
    calls: list[dict] = []

    def fake_post(url, **kwargs):
        calls.append(kwargs)
        return respond(kwargs["json"]["pageNumber"])

    monkeypatch.setattr(mod.httpx, "post", fake_post)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    return calls


def test_request_body_and_headers(monkeypatch):
    calls = _patch_post(monkeypatch, lambda _n: _response({"count": 0, "items": []}))

    assert _source().fetch() == []

    assert len(calls) == 1
    assert calls[0]["json"] == {
        "pageNumber": 1,
        "itemsPerPage": 100,
        "stores": STORES,
        "discountRange": [20, 100],
        "dateRange": 7200,
        "includedUpdateTypes": ["NEW", "DISCOUNT_UP", "RETURNED"],
        "sortBy": "date",
        "sortOrder": "desc",
        "discountChangeRate": 0,
    }
    assert "bargain-hunter" in calls[0]["headers"]["User-Agent"]


@pytest.mark.parametrize("count", [250, 300])  # 300: max_pages * page_size exactly covers it
def test_fetch_pages_until_count_is_covered(monkeypatch, caplog, count):
    calls = _patch_post(monkeypatch, lambda page: _page(page, 100, count))

    with caplog.at_level(logging.WARNING):
        deals = _source(max_pages=3).fetch()

    assert [c["json"]["pageNumber"] for c in calls] == [1, 2, 3]
    assert len(deals) == 300
    assert "truncated" not in caplog.text


def test_fetch_dedupes_items_repeated_across_pages(monkeypatch):
    # Sorted newest-first, so activity between requests can shift an item onto the next page.
    same_items = _response({"count": 150, "items": [_item(f"x{i}") for i in range(100)]})
    calls = _patch_post(monkeypatch, lambda _n: same_items)

    assert len(_source(max_pages=2).fetch()) == 100
    assert len(calls) == 2


@pytest.mark.parametrize("count", [50, 250])  # 250: the server claims more than it served
def test_fetch_stops_on_short_page(monkeypatch, count):
    calls = _patch_post(monkeypatch, lambda page: _page(page, 50, count))

    assert len(_source(max_pages=3).fetch()) == 50
    assert len(calls) == 1


def test_fetch_paces_requests_after_the_first(monkeypatch):
    sleeps: list[float] = []
    _patch_post(monkeypatch, lambda page: _page(page, 100, 250))
    monkeypatch.setattr(mod.time, "sleep", sleeps.append)

    _source(max_pages=3, request_delay_seconds=1.5).fetch()

    assert sleeps == [1.5, 1.5]


def test_fetch_warns_when_max_pages_truncates(monkeypatch, caplog):
    calls = _patch_post(monkeypatch, lambda page: _page(page, 100, 250))

    with caplog.at_level(logging.WARNING):
        _source(max_pages=2).fetch()

    assert len(calls) == 2
    assert any("truncated" in r.message for r in caplog.records)


def test_fetch_does_not_swallow_http_errors(monkeypatch):
    _patch_post(monkeypatch, lambda _n: _response({}, status=500))

    with pytest.raises(httpx.HTTPStatusError):
        _source().fetch()


def test_empty_store_list_rejected():
    with pytest.raises(ValueError):
        BargainRadarSource(stores=[])


# -- watch-only: never enters the hot ladder ------------------------------------


def _radar_deal() -> Deal:
    return Deal(
        source="bargainradar",
        deal_id="x",
        title="Widget (Myer)",
        url="https://bargainradar.com.au/item/x",
        discount_percent=80.0,
        posted_at=datetime.now(UTC) - timedelta(hours=1),
    )


def test_excluded_source_is_not_a_hot_candidate():
    # Same fresh 80%-off deal: the voteless discount path would make it hot, so
    # the exclusion (not some other gate) is what keeps it out.
    voteless = ["bargainradar"]
    open_cfg = ScoringConfig(hot=HotConfig(voteless_sources=voteless))
    excluded_cfg = ScoringConfig(
        hot=HotConfig(voteless_sources=voteless, excluded_sources=["bargainradar"])
    )

    assert is_hot_candidate(_radar_deal(), [], open_cfg)
    assert not is_hot_candidate(_radar_deal(), [], excluded_cfg)


def test_production_config_is_watch_only():
    settings = load_settings()
    hot, watch = settings.scoring.hot, settings.scoring.watch

    assert "bargainradar" in hot.voteless_sources
    assert "bargainradar" in hot.excluded_sources
    assert "bargainradar" not in watch.trusted_sources
    assert classify_hot(_radar_deal(), [], settings.scoring) is None
