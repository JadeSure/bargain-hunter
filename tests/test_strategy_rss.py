"""Tests for the generic RSS 2.0 source, against frozen sample feeds.

Fixtures are trimmed real payloads fetched live from both feeds on 2026-08-20
(not hand-written) — real titles, entities, and description/content:encoded
shape. Only exception: one AFF item's pubDate is deliberately corrupted to
exercise the malformed-date path.
"""

from pathlib import Path

from strategy_hunter.sources.rss import RssFeedSource

POINTHACKS_FIXTURE = Path(__file__).parent / "fixtures" / "rss_pointhacks_sample.xml"
AFF_FIXTURE = Path(__file__).parent / "fixtures" / "rss_frequentflyer_sample.xml"


def _parse(fixture: Path, board: str):
    return RssFeedSource(feeds=[]).parse(fixture.read_text(encoding="utf-8"), board=board)


def test_parses_rss2_items():
    posts = _parse(POINTHACKS_FIXTURE, board="PointHacks")
    assert len(posts) == 2
    assert all(p.source == "rss" for p in posts)
    assert all(p.board == "PointHacks" for p in posts)


def test_known_entry_fields():
    posts = {p.title: p for p in _parse(POINTHACKS_FIXTURE, board="PointHacks")}
    p = posts["Westpac Altitude Black vs NAB Qantas Signature"]
    assert p.url == "https://www.pointhacks.com.au/westpac-altitude-black-vs-nab-qantas-signature/"
    assert p.post_id == "https://www.pointhacks.com.au/?p=230953"  # guid, not link


def test_numeric_entities_resolved_in_titles():
    posts = {p.title: p for p in _parse(POINTHACKS_FIXTURE, board="PointHacks")}
    assert "This week’s gift card offers with Flybuys and Everyday Rewards" in posts
    aff = {p.title: p for p in _parse(AFF_FIXTURE, board="AusFrequentFlyer")}
    assert any("Brisbane – Los Angeles" in t for t in aff)  # &#8211; -> en dash


def test_falls_back_to_description_when_no_content_encoded():
    # The real PointHacks feed carries no content:encoded at all.
    posts = {p.title: p for p in _parse(POINTHACKS_FIXTURE, board="PointHacks")}
    p = posts["Westpac Altitude Black vs NAB Qantas Signature"]
    assert "help you decide which might be the better choice" in p.body
    assert "<p>" not in p.body


def test_content_encoded_preferred_over_description():
    posts = {p.title: p for p in _parse(AFF_FIXTURE, board="AusFrequentFlyer")}
    p = posts["How to Buy Qatar Airways Privilege Club Avios"]
    assert "one of seven loyalty programs" in p.body   # only in content:encoded
    assert "50% bonus" not in p.body                   # description's wording, not used


def test_html_stripped_from_body():
    posts = _parse(POINTHACKS_FIXTURE, board="PointHacks") + _parse(
        AFF_FIXTURE, board="AusFrequentFlyer"
    )
    for p in posts:
        assert "<p" not in p.body
        assert "class=" not in p.body


def test_timestamps_are_timezone_aware_and_utc():
    posts = {p.title: p for p in _parse(POINTHACKS_FIXTURE, board="PointHacks")}
    p = posts["Westpac Altitude Black vs NAB Qantas Signature"]
    assert p.created_at is not None
    assert p.created_at.tzinfo is not None
    assert p.created_at.utcoffset().total_seconds() == 0
    assert p.created_at.hour == 5


def test_malformed_pub_date_does_not_crash_and_yields_none():
    posts = {p.title: p for p in _parse(AFF_FIXTURE, board="AusFrequentFlyer")}
    good = posts["How to Buy Qatar Airways Privilege Club Avios"]
    bad = next(t for t in posts if t.startswith("Airfare of the Week"))
    assert good.created_at is not None
    assert posts[bad].created_at is None


def test_fetch_skips_dead_feed_but_keeps_other_feed(monkeypatch):
    import httpx

    from strategy_hunter.sources import rss as rss_mod

    def fake_get(url, **kwargs):
        if "pointhacks" in url:
            return httpx.Response(403, request=httpx.Request("GET", url))
        return httpx.Response(
            200,
            text=AFF_FIXTURE.read_text(encoding="utf-8"),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(rss_mod.httpx, "get", fake_get)
    src = RssFeedSource(
        feeds=[
            {"url": "https://www.pointhacks.com.au/feed/", "board": "PointHacks"},
            {
                "url": "https://www.australianfrequentflyer.com.au/feed/",
                "board": "AusFrequentFlyer",
            },
        ],
        request_delay_seconds=0,
    )
    posts = src.fetch()
    assert len(posts) == 2  # both items from the surviving feed
    assert all(p.board == "AusFrequentFlyer" for p in posts)
