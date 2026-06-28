"""Tests for the OzBargain tag-feed source, against a frozen fixture."""

from datetime import UTC, datetime
from pathlib import Path

from strategy_hunter.onboarding.relevance import onboarding_relevance_score
from strategy_hunter.sources.ozbargain_tags import OzBargainTagSource

FIXTURES = Path(__file__).parent / "fixtures"
_FIXED_NOW = datetime(2026, 6, 29, 0, 0, 0, tzinfo=UTC)


def _parse():
    xml = (FIXTURES / "ozb_tag_feed.xml").read_text(encoding="utf-8")
    return OzBargainTagSource(tags=["cashback"]).parse(xml, tag="cashback", now=_FIXED_NOW)


def test_returns_at_least_one_post():
    posts = _parse()
    assert len(posts) >= 1


def test_post_ids_are_numeric():
    for post in _parse():
        assert post.post_id.isdigit(), f"post_id not numeric: {post.post_id!r}"


def test_urls_contain_node():
    for post in _parse():
        assert "/node/" in post.url, f"url missing /node/: {post.url!r}"


def test_board_and_source():
    for post in _parse():
        assert post.board == "OzBargain #cashback"
        assert post.source == "ozbargain_tag"


def test_at_least_one_non_empty_body():
    assert any(post.body for post in _parse())


def test_fetched_at_matches_fixed_now():
    for post in _parse():
        assert post.fetched_at == _FIXED_NOW


def test_first_post_relevance_score_positive():
    posts = _parse()
    first = posts[0]
    score = onboarding_relevance_score(f"{first.title}\n{first.body}")
    assert score > 0, f"expected >0 relevance for: {first.title!r}"
