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


def test_parse_json_listing():
    data = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "xyz789",
                        "title": "Stacking cashback + gift cards on Apple",
                        "selftext": "Use a discounted gift card then Cashrewards.",
                        "author": "dealhunter",
                        "permalink": "/r/AusFinance/comments/xyz789/stacking/",
                        "created_utc": 1700000000,
                        "score": 42,
                        "num_comments": 7,
                    }
                },
                {"data": {"id": "", "title": "no id, skipped"}},
            ]
        }
    }
    posts = RedditSource(subreddits=["AusFinance"]).parse_json(data, subreddit="AusFinance")
    assert len(posts) == 1
    p = posts[0]
    assert p.post_id == "xyz789"
    assert p.board == "r/AusFinance"
    assert p.url == "https://www.reddit.com/r/AusFinance/comments/xyz789/stacking/"
    assert p.score == 42
    assert p.num_comments == 7
    assert p.created_at is not None and p.created_at.tzinfo is not None
    assert "Cashrewards" in p.body


def test_fetch_skips_rate_limited_subreddit(monkeypatch):
    import httpx

    from strategy_hunter.sources import reddit as reddit_mod

    def fake_request(method, url, **kwargs):
        return httpx.Response(429)

    monkeypatch.setattr(reddit_mod.httpx, "request", fake_request)
    src = RedditSource(subreddits=["AusFinance", "AusFrugal"], max_retries=0)
    # No credentials -> RSS path; both subs 429 -> skipped, no raise, empty result.
    assert src.fetch() == []
