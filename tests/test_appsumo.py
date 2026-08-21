"""Tests for the AppSumo source, against a frozen fixture -- no network.

appsumo_deals.json is a hand-built, structurally-trimmed sample mirroring one
live page response, covering the three measured traps: an expired item with a
future start_date sentinel (vectera-2019), an is_addon item, and an item with
an original_price: 0.0 sentinel (Crowdflow).
"""

import json
from pathlib import Path

import httpx

from bargain_hunter.sources import appsumo as mod
from bargain_hunter.sources.appsumo import AppSumoSource

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "appsumo_deals.json").read_text(encoding="utf-8")
)


def _deals() -> dict[str, "mod.Deal"]:
    return {d.deal_id: d for d in AppSumoSource()._parse_page(FIXTURE)}


def test_only_current_started_non_addon_visible_items_kept():
    deals = _deals()
    assert set(deals) == {"cleanvoice-ai", "tidycal", "crowdflow", "worklm", "timetuna"}


def test_expired_item_with_future_start_date_excluded():
    deals = _deals()
    assert "vectera-2019" not in deals


def test_addon_item_excluded():
    deals = _deals()
    assert "cleanvoice-ai-penetration-testing" not in deals


def test_url_is_absolute_deal_page_not_product_or_clickthrough():
    deals = _deals()
    assert deals["cleanvoice-ai"].url == "https://appsumo.com/products/cleanvoice-ai"
    assert deals["tidycal"].url == "https://appsumo.com/products/tidycal"


def test_prices_and_discount_computed_from_structured_fields():
    deals = _deals()
    cleanvoice = deals["cleanvoice-ai"]
    assert cleanvoice.price == 29.0
    assert cleanvoice.was_price == 299.0
    assert cleanvoice.discount_percent == 90.3
    assert cleanvoice.price_confidence == "high"
    assert cleanvoice.currency == "USD"
    assert cleanvoice.source == "appsumo"

    tidycal = deals["tidycal"]
    assert tidycal.price == 59.0
    assert tidycal.was_price == 708.0
    assert tidycal.discount_percent == 91.7


def test_zero_original_price_sentinel_does_not_produce_bogus_discount():
    crowdflow = _deals()["crowdflow"]
    assert crowdflow.price == 29.0
    assert crowdflow.was_price is None
    assert crowdflow.discount_percent is None


def test_posted_at_parsed_from_dates_start_date():
    cleanvoice = _deals()["cleanvoice-ai"]
    assert cleanvoice.posted_at is not None
    assert cleanvoice.posted_at.isoformat() == "2026-06-01T00:00:00+00:00"


# -- description composition ---------------------------------------------


def test_description_composed_from_features_rating_and_refund():
    worklm = _deals()["worklm"]
    assert worklm.description == (
        "AI chat · Multi-LLM access · BYOK · Team AI · 4.9★ (20 reviews) · 60-day refund"
    )


def test_description_none_when_no_features_rating_or_refund_present():
    # cleanvoice-ai's fixture row has no core_features/common_features/
    # deal_review/refundable_days at all.
    cleanvoice = _deals()["cleanvoice-ai"]
    assert cleanvoice.description is None


def test_description_empty_feature_lists_and_no_rating_yet_still_clean():
    # timetuna: both feature lists are [], review_count is 0 with
    # average_rating None -- only the refund signal should survive, no
    # dangling separators or a bare "·".
    timetuna = _deals()["timetuna"]
    assert timetuna.description == "60-day refund"
    assert "·" not in timetuna.description  # no other parts to join


# -- fetch(): pagination, pacing, and per-page failure isolation --------------


def _patch_pages(monkeypatch, pages: dict[int, httpx.Response]) -> list[int]:
    requested: list[int] = []

    def fake_get(url, *, params=None, **kwargs):
        page = (params or {}).get("page")
        requested.append(page)
        return pages[page]

    monkeypatch.setattr(mod.httpx, "get", fake_get)
    return requested


def test_fetch_paginates_up_to_max_pages_and_dedupes(monkeypatch):
    page1 = httpx.Response(200, json={"deals": FIXTURE["deals"][:2], "meta": {}})
    page2 = httpx.Response(200, json={"deals": FIXTURE["deals"][:2], "meta": {}})  # duplicate slugs
    requested = _patch_pages(monkeypatch, {1: page1, 2: page2})
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)

    src = AppSumoSource(max_pages=2)
    deals = src.fetch()

    assert requested == [1, 2]
    assert {d.deal_id for d in deals} == {"cleanvoice-ai", "tidycal"}  # deduped across pages


def test_fetch_one_bad_page_does_not_sink_the_others(monkeypatch, caplog):
    good = httpx.Response(200, json={"deals": FIXTURE["deals"][:1], "meta": {}})
    bad = httpx.Response(500, json={})
    requested = _patch_pages(monkeypatch, {1: bad, 2: good})
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)

    with caplog.at_level("ERROR"):
        deals = AppSumoSource(max_pages=2).fetch()

    assert requested == [1, 2]
    assert {d.deal_id for d in deals} == {"cleanvoice-ai"}
    assert any("appsumo" in r.message and "page 1" in r.message for r in caplog.records)
