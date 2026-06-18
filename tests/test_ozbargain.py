"""Tests for the OzBargain RSS parser, against a frozen real-feed snapshot."""

from pathlib import Path

from bargain_hunter.sources.ozbargain import OzBargainSource, _clean_text

FIXTURE = Path(__file__).parent / "fixtures" / "ozbargain_sample.xml"


def _parse():
    return OzBargainSource().parse(FIXTURE.read_text(encoding="utf-8"))


def test_parses_many_deals():
    deals = _parse()
    assert len(deals) >= 10
    assert all(d.source == "ozbargain" for d in deals)
    assert all(d.deal_id and d.title and d.url for d in deals)


def test_known_deal_fields():
    deals = {d.deal_id: d for d in _parse()}
    d = deals["964067"]
    assert d.title.startswith("Brother Colour DCP Laser Printer")
    assert "C&C" in d.title  # XML entity (&amp;) decoded
    assert d.votes_pos == 2
    assert d.votes_neg == 0
    assert d.comment_count == 2
    assert d.click_count == 42
    assert d.url == "https://www.ozbargain.com.au/node/964067"
    assert d.merchant_url and "thegoodguys" in d.merchant_url
    assert "Computing" in d.categories
    assert d.posted_at is not None and d.posted_at.year == 2026
    assert d.key == "ozbargain:964067"


def test_expiry_parsed():
    deals = {d.deal_id: d for d in _parse()}
    d = deals["964066"]  # Autobarn deal carries expiry + starting
    assert d.expiry is not None
    assert d.expiry.year == 2026 and d.expiry.month == 6


def test_datetimes_are_timezone_aware():
    # Every parsed timestamp must be tz-aware (normalised to UTC) so downstream
    # velocity/age/expiry maths never mixes naive and aware datetimes.
    for d in _parse():
        if d.posted_at is not None:
            assert d.posted_at.tzinfo is not None
            assert d.posted_at.utcoffset().total_seconds() == 0
        if d.expiry is not None:
            assert d.expiry.tzinfo is not None


def test_clean_text_strips_html_and_entities():
    assert _clean_text("<p>Save&nbsp;30% <b>off</b></p>") == "Save 30% off"
    assert _clean_text("") is None
    assert _clean_text(None) is None
    assert _clean_text("   ") is None
