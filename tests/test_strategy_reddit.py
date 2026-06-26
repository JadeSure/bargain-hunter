"""Tests for the Reddit Atom-feed parser, against a frozen sample feed."""

from pathlib import Path

from strategy_hunter.sources.reddit import RedditSource

FIXTURE = Path(__file__).parent / "fixtures" / "reddit_atom_sample.xml"


def _parse():
    return RedditSource(subreddits=["AusFinance"]).parse(
        FIXTURE.read_text(encoding="utf-8"), subreddit="AusFinance"
    )


def test_parses_entries():
    posts = _parse()
    assert len(posts) == 2
    assert all(p.source == "reddit" for p in posts)
    assert all(p.board == "r/AusFinance" for p in posts)


def test_known_entry_fields():
    posts = {p.post_id: p for p in _parse()}
    p = posts["abc123"]            # "t3_" prefix stripped
    assert p.title == "Cheapest way to buy a MacBook?"
    assert "student discount" in p.body
    assert p.url.endswith("/cheapest_macbook/")
    assert p.author == "/u/saver"
    assert p.key == "reddit:abc123"


def test_timestamps_are_timezone_aware():
    for p in _parse():
        assert p.created_at is not None
        assert p.created_at.tzinfo is not None
        assert p.created_at.utcoffset().total_seconds() == 0
