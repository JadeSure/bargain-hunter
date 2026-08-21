"""Tests for the smzdm (什么值得买) source, against frozen fixtures -- no network.

smzdm_home.json and smzdm_youhui.json are hand-built, structurally-trimmed
samples mirroring one live page response each, covering the measured traps:
an 原创 editorial row (home only, must be excluded), a ~5.2-year-old sentinel
row (youhui only, must be excluded), conditional/range article_price strings
that must not produce a bogus number, a row shared by both endpoints (must
de-dupe), and an http:// url (must upgrade to https://).
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from bargain_hunter.sources import smzdm as mod
from bargain_hunter.sources.smzdm import SmzdmSource

FIXTURE_HOME = json.loads(
    (Path(__file__).parent / "fixtures" / "smzdm_home.json").read_text(encoding="utf-8")
)
FIXTURE_YOUHUI = json.loads(
    (Path(__file__).parent / "fixtures" / "smzdm_youhui.json").read_text(encoding="utf-8")
)

# Matches the article_unix_date baked into both fixtures (1787310000 = 1h before
# this) so freshness assertions are deterministic regardless of when tests run.
NOW = datetime(2026, 8, 21, 12, 0, 0, tzinfo=UTC)


def _home_deals() -> dict[str, mod.Deal]:
    src = SmzdmSource()
    return {d.deal_id: d for d in src._parse_page("home", FIXTURE_HOME, True, NOW)}


def _youhui_deals() -> dict[str, mod.Deal]:
    src = SmzdmSource()
    return {d.deal_id: d for d in src._parse_page("youhui", FIXTURE_YOUHUI, False, NOW)}


def test_home_editorial_channel_excluded():
    deals = _home_deals()
    assert "180331000" not in deals  # 原创, not 优惠
    assert set(deals) == {"180330849", "180330900", "180331111"}


def test_youhui_no_channel_field_not_filtered():
    deals = _youhui_deals()
    # channel-based filter must not apply here -- only the age gate below does
    assert "180330222" in deals


def test_sentinel_5_year_old_row_excluded_by_max_age():
    deals = _youhui_deals()
    assert "170000001" not in deals


def test_bare_price_parsed_high_confidence():
    home = _home_deals()
    assert home["180330849"].price == 11.12
    assert home["180330849"].price_confidence == "high"

    youhui = _youhui_deals()
    assert youhui["180330222"].price == 99.0
    assert youhui["180330222"].price_confidence == "high"


def test_conditional_price_string_produces_no_bogus_number():
    deal = _home_deals()["180330900"]  # "10.96元（需买3件，需用券）"
    assert deal.price is None
    assert deal.price_confidence is None
    assert "10.96元（需买3件，需用券）" in (deal.description or "")


def test_range_price_string_produces_no_bogus_number():
    deal = _home_deals()["180331111"]  # "低至5折起"
    assert deal.price is None
    assert deal.price_confidence is None
    assert "低至5折起" in (deal.description or "")


def test_http_url_upgraded_to_https():
    deal = _home_deals()["180330849"]
    assert deal.url == "https://www.smzdm.com/p/180330849"


def test_votes_comments_currency_source():
    deal = _home_deals()["180330849"]
    assert deal.votes_pos == 10
    assert deal.comment_count == 3
    assert deal.currency == "CNY"
    assert deal.source == "smzdm"


def test_description_includes_mall():
    deal = _home_deals()["180330849"]
    assert "京东" in (deal.description or "")


def test_dedupe_across_endpoints_by_article_id():
    deals: dict[str, mod.Deal] = {}
    for deal in [*_home_deals().values(), *_youhui_deals().values()]:
        deals.setdefault(deal.key, deal)
    matching = [d for d in deals.values() if d.deal_id == "180330849"]
    assert len(matching) == 1


def test_error_code_failure_logged_and_returns_no_deals(caplog):
    bad = {"error_code": "-1", "error_msg": "Unknown method.", "data": {"rows": []}}
    src = SmzdmSource()
    with caplog.at_level("ERROR"):
        out = src._parse_page("home", bad, True, NOW)
    assert out == []
    assert any("smzdm" in r.message and "-1" in r.message for r in caplog.records)


# -- fetch(): pagination across both endpoints, pacing, per-page isolation ---


def _patch_get(monkeypatch, responses: dict[tuple[str, int], httpx.Response]) -> list:
    requested: list[tuple[str, int]] = []

    def fake_get(url, *, params=None, **kwargs):
        offset = (params or {}).get("offset", 0)
        key = (url, offset)
        requested.append(key)
        return responses[key]

    monkeypatch.setattr(mod.httpx, "get", fake_get)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    return requested


def test_fetch_paginates_both_endpoints_and_dedupes(monkeypatch):
    empty = httpx.Response(200, json={"error_code": "0", "error_msg": "data", "data": {"rows": []}})
    responses = {
        (mod.BASE_URL + mod._HOME_PATH, 0): httpx.Response(200, json=FIXTURE_HOME),
        (mod.BASE_URL + mod._HOME_PATH, 20): empty,
        (mod.BASE_URL + mod._YOUHUI_PATH, 0): httpx.Response(200, json=FIXTURE_YOUHUI),
        (mod.BASE_URL + mod._YOUHUI_PATH, 20): empty,
        (mod.BASE_URL + mod._FAXIAN_PATH, 0): empty,
        (mod.BASE_URL + mod._FAXIAN_PATH, 20): empty,
    }
    requested = _patch_get(monkeypatch, responses)

    deals = {d.key: d for d in SmzdmSource(max_pages=2).fetch()}

    assert set(requested) == set(responses)
    assert "smzdm:180330849" in deals  # shared row, deduped to one entry
    assert "smzdm:180330900" in deals  # home-only
    assert "smzdm:180330222" in deals  # youhui-only
    assert "smzdm:180331000" not in deals  # 原创, excluded
    assert "smzdm:170000001" not in deals  # sentinel, excluded


def test_fetch_one_bad_page_does_not_sink_the_others(monkeypatch, caplog):
    empty = httpx.Response(200, json={"error_code": "0", "error_msg": "data", "data": {"rows": []}})
    responses = {
        (mod.BASE_URL + mod._HOME_PATH, 0): httpx.Response(500, json={}),
        (mod.BASE_URL + mod._HOME_PATH, 20): empty,
        (mod.BASE_URL + mod._YOUHUI_PATH, 0): httpx.Response(200, json=FIXTURE_YOUHUI),
        (mod.BASE_URL + mod._YOUHUI_PATH, 20): empty,
        (mod.BASE_URL + mod._FAXIAN_PATH, 0): empty,
        (mod.BASE_URL + mod._FAXIAN_PATH, 20): empty,
    }
    _patch_get(monkeypatch, responses)

    with caplog.at_level("ERROR"):
        deals = {d.key: d for d in SmzdmSource(max_pages=2).fetch()}

    assert "smzdm:180330849" in deals  # came from youhui despite home page 0 failing
    assert any("smzdm" in r.message and "home" in r.message for r in caplog.records)


# -- faxian: article_date is naive Beijing time, not UTC -------------------------


def test_faxian_article_date_is_parsed_as_beijing_not_utc():
    """/v1/faxian/list has no article_unix_date; its timestamp is `article_date`,
    a naive "YYYY-MM-DD HH:MM:SS" string in Beijing time. Measured 2026-08-21:
    fetched at 06:16:16Z, newest article_date read "14:16:17" — exactly +8.
    Reading it as UTC would put every item 8 hours in the FUTURE, which makes
    the max-age filter silently never fire while the feed still looks healthy.
    """
    from bargain_hunter.sources.smzdm import _posted_at

    got = _posted_at({"article_date": "2026-08-21 14:16:17"})
    assert got is not None
    assert got.tzinfo is not None, "must be timezone-aware (ruff DTZ)"
    assert got == datetime(2026, 8, 21, 6, 16, 17, tzinfo=UTC)


def test_article_unix_date_wins_over_article_date_when_both_present():
    from bargain_hunter.sources.smzdm import _posted_at

    unix = 1755756977  # 2025-08-21T05:76:17Z-ish; exact value irrelevant
    got = _posted_at({"article_unix_date": unix, "article_date": "2026-08-21 14:16:17"})
    assert got == datetime.fromtimestamp(unix, UTC)


def test_posted_at_returns_none_when_neither_field_is_usable():
    from bargain_hunter.sources.smzdm import _posted_at

    for row in ({}, {"article_date": ""}, {"article_date": "not a date"},
                {"article_unix_date": None, "article_date": None}):
        assert _posted_at(row) is None
