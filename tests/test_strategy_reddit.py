"""Tests for the Reddit Atom-feed parser, against a frozen sample feed."""

import json
from pathlib import Path

from strategy_hunter.sources.reddit import RedditSource

FIXTURE = Path(__file__).parent / "fixtures" / "reddit_atom_sample.xml"
COMMENTS_FIXTURE = Path(__file__).parent / "fixtures" / "reddit_comments_sample.json"


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
    src = RedditSource(
        subreddits=["AusFinance", "AusFrugal"], max_retries=0, request_delay_seconds=0
    )
    # No credentials -> RSS path; both subs 429 -> skipped, no raise, empty result.
    assert src.fetch() == []


def test_fetch_retries_then_succeeds(monkeypatch):
    import httpx

    from strategy_hunter.sources import reddit as reddit_mod

    xml = FIXTURE.read_text(encoding="utf-8")
    calls = {"n": 0}

    def fake_request(method, url, **kwargs):
        calls["n"] += 1
        req = httpx.Request(method, url)
        if calls["n"] == 1:                      # first hit is rate limited
            return httpx.Response(429, headers={"Retry-After": "0"}, request=req)
        return httpx.Response(200, text=xml, request=req)  # retry succeeds

    monkeypatch.setattr(reddit_mod.httpx, "request", fake_request)
    src = RedditSource(subreddits=["AusFinance"], max_retries=2, request_delay_seconds=0)
    posts = src.fetch()
    assert calls["n"] == 2                        # retried exactly once
    assert len(posts) == 2                        # parsed the fixture feed


# -- comment mining ------------------------------------------------------------


def _comments_data():
    return json.loads(COMMENTS_FIXTURE.read_text(encoding="utf-8"))


def test_parse_comments_json_filters_short_and_non_toplevel():
    src = RedditSource(subreddits=["AusFinance"])
    comments = src.parse_comments_json(_comments_data())
    # "same" (too short) and the "more" stub are excluded; 3 substantive left.
    assert len(comments) == 3
    assert all(len(body) >= 80 for _a, _s, body in comments)
    authors = [a for a, _s, _b in comments]
    assert "lurker" not in authors


def test_parse_comments_json_sorted_by_score_desc():
    src = RedditSource(subreddits=["AusFinance"])
    comments = src.parse_comments_json(_comments_data())
    scores = [s for _a, s, _b in comments]
    assert scores == sorted(scores, reverse=True)
    assert comments[0][0] == "saver2"  # highest score (35) first


def test_parse_comments_json_caps_at_max_comments_per_post():
    src = RedditSource(subreddits=["AusFinance"], max_comments_per_post=2)
    comments = src.parse_comments_json(_comments_data())
    assert len(comments) == 2


def test_parse_comments_json_handles_malformed_input():
    src = RedditSource(subreddits=["AusFinance"])
    assert src.parse_comments_json({}) == []
    assert src.parse_comments_json([{"data": {}}]) == []  # only one listing


def test_parse_comments_json_deterministic():
    src = RedditSource(subreddits=["AusFinance"])
    data = _comments_data()
    assert src.parse_comments_json(data) == src.parse_comments_json(data)


def test_append_comments_format():
    body = RedditSource._append_comments(
        "OP text", [("saver1", 10, "A long enough comment body to pass the filter easily.")]
    )
    assert body.startswith("OP text")
    assert "---- top comments ----" in body
    assert "[saver1] A long enough comment body" in body


def test_fetch_oauth_mines_comments_within_budget(monkeypatch):
    import httpx

    from strategy_hunter.sources import reddit as reddit_mod

    monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")

    listing_json = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": f"post{i}",
                        "title": f"Post {i}",
                        "selftext": "body",
                        "permalink": f"/r/AusFinance/comments/post{i}/x/",
                        "score": 100 - i,
                        "num_comments": 5,
                    }
                }
                for i in range(3)
            ]
        }
    }
    comments_json = _comments_data()
    calls = {"comments": 0}

    def fake_request(method, url, **kwargs):
        req = httpx.Request(method, url)
        if "access_token" in url:
            return httpx.Response(200, json={"access_token": "tok"}, request=req)
        if "/comments/" in url:
            calls["comments"] += 1
            return httpx.Response(200, json=comments_json, request=req)
        return httpx.Response(200, json=listing_json, request=req)

    monkeypatch.setattr(reddit_mod.httpx, "request", fake_request)
    src = RedditSource(
        subreddits=["AusFinance"],
        request_delay_seconds=0,
        max_posts_with_comments=2,
        comment_min_score=1,
    )
    posts = src.fetch()
    assert len(posts) == 3
    assert calls["comments"] == 2  # capped by max_posts_with_comments
    mined = [p for p in posts if "---- top comments ----" in p.body]
    assert len(mined) == 2
    # Highest-score posts (post0, post1) get mined; post2 does not.
    assert {p.post_id for p in mined} == {"post0", "post1"}


def test_fetch_rss_skips_comment_fetching(monkeypatch):
    import httpx

    from strategy_hunter.sources import reddit as reddit_mod

    xml = FIXTURE.read_text(encoding="utf-8")
    calls = {"n": 0}

    def fake_request(method, url, **kwargs):
        calls["n"] += 1
        assert "/comments/" not in url  # RSS fallback never mines comments
        return httpx.Response(200, text=xml, request=httpx.Request(method, url))

    monkeypatch.setattr(reddit_mod.httpx, "request", fake_request)
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    src = RedditSource(subreddits=["AusFinance"], request_delay_seconds=0)
    posts = src.fetch()
    assert len(posts) == 2
    assert calls["n"] == 1  # only the RSS feed request, no comment top-up
