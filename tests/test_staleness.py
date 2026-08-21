"""Tests for the staleness-ceiling guard's building blocks (see
GLOBAL_EXPANSION_PLAN.md Lane C): feed_deals' newest_item_at (recorded from
ALL parsed items, before the staleness/title_keywords filters), cn_llm_docs'
per-page ok_at carry-forward, and their persistence via state.py's
record_freshness/freshness.

The ceiling comparison itself (now - freshness > ceiling_days) is a one-line
check owned by main.py -- these tests cover the two signals it depends on.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from bargain_hunter.sources import cn_llm_docs as cn_mod
from bargain_hunter.sources.cn_llm_docs import CnLlmDocsSource
from bargain_hunter.sources.feed_deals import FeedDealsSource
from bargain_hunter.state import StateStore

NOW = datetime(2026, 8, 21, tzinfo=UTC)
FIXTURES = Path(__file__).parent / "fixtures"


def _rss(items: str) -> str:
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{items}</channel></rss>'


def _item(title: str, pub_date: str | None = None, guid: str | None = None) -> str:
    guid = guid or title
    date_tag = f"<pubDate>{pub_date}</pubDate>" if pub_date else ""
    return (
        f"<item><title>{title}</title><link>https://example.com/{guid}</link>"
        f"<description>d</description>{date_tag}<guid>{guid}</guid></item>"
    )


# ---------------------------------------------------------------------------
# feed_deals.newest_item_at
# ---------------------------------------------------------------------------


def test_newest_item_at_reflects_a_dead_feeds_stale_content():
    """God Save The Points case: HTTP 200, well-formed items, but every item
    is stale -- the ceiling guard's whole reason to exist."""
    xml = _rss(_item("Old deal", "Fri, 31 Jul 2025 00:00:00 +0000"))
    src = FeedDealsSource(name="aff", feed_urls=[], max_item_age_hours=None)

    src.parse(xml, now=NOW)

    assert src.newest_item_at == datetime(2025, 7, 31, tzinfo=UTC)
    age_days = (NOW - src.newest_item_at).days
    assert age_days > 300  # comfortably past any sane ceiling


def test_newest_item_at_stays_fresh_for_a_quiet_but_healthy_feed():
    """AFF subforum case: legitimately produces little most days, but the one
    item it does have is recent -- must NOT read as stale."""
    xml = _rss(_item("Quiet forum post", "Thu, 20 Aug 2026 12:00:00 +0000"))
    src = FeedDealsSource(name="aff", feed_urls=[], max_item_age_hours=None)

    src.parse(xml, now=NOW)

    age_hours = (NOW - src.newest_item_at).total_seconds() / 3600
    assert age_hours < 24


def test_newest_item_at_recorded_before_title_keyword_filter():
    """A feed where every item is dropped by title_keywords must still report
    itself as fresh -- newest_item_at reflects the feed's own health, not
    what survived our gates."""
    xml = _rss(_item("Bun 1.4 is now available", "Fri, 21 Aug 2026 06:00:00 +0000"))
    src = FeedDealsSource(
        name="vercel", feed_urls=[], max_item_age_hours=None, title_keywords=["free|discount"]
    )

    deals = src.parse(xml, now=NOW)

    assert deals == []  # filtered out, as intended
    assert src.newest_item_at == datetime(2026, 8, 21, 6, 0, tzinfo=UTC)


def test_newest_item_at_recorded_before_staleness_filter():
    """Same principle for the age filter: a stale item that gets dropped
    still counts toward newest_item_at."""
    xml = _rss(_item("Old", "Fri, 31 Jul 2025 00:00:00 +0000"))
    src = FeedDealsSource(name="aff", feed_urls=[], max_item_age_hours=24)

    deals = src.parse(xml, now=NOW)

    assert deals == []  # dropped as stale
    assert src.newest_item_at == datetime(2025, 7, 31, tzinfo=UTC)


def test_newest_item_at_none_when_no_item_has_a_parseable_date():
    xml = _rss(_item("No date"))
    src = FeedDealsSource(name="aff", feed_urls=[])

    src.parse(xml, now=NOW)

    assert src.newest_item_at is None


def test_newest_item_at_accumulates_across_multiple_parse_calls():
    """One `name` can share multiple feed_urls (e.g. aff = subforum + blog);
    newest_item_at must track the max across the whole fetch, not reset on
    each individual parse() call, and must not regress on a later call."""
    src = FeedDealsSource(name="aff", feed_urls=[], max_item_age_hours=None)

    src.parse(_rss(_item("Older", "Fri, 31 Jul 2025 00:00:00 +0000")), now=NOW)
    src.parse(_rss(_item("Newer", "Fri, 21 Aug 2026 00:00:00 +0000")), now=NOW)
    assert src.newest_item_at == datetime(2026, 8, 21, tzinfo=UTC)

    src.parse(_rss(_item("Old again", "Fri, 31 Jul 2025 00:00:00 +0000")), now=NOW)
    assert src.newest_item_at == datetime(2026, 8, 21, tzinfo=UTC)


# ---------------------------------------------------------------------------
# cn_llm_docs: ok_at is stamped on every successful fetch, and preserved
# (not refreshed) by the carry-forward path on a failed fetch.
# ---------------------------------------------------------------------------

CHAT_URL = "https://platform.kimi.com/docs/pricing/chat.md"
CHAT_PAGE = {"tag": "kimi", "slug": "chat", "label": "Kimi 定价说明", "url": CHAT_URL}


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _patch(monkeypatch, store: dict[str, str], dead: set[str] | None = None) -> None:
    dead = dead or set()

    def fake_get(url, **kwargs):
        if url in dead:
            return httpx.Response(500, request=httpx.Request("GET", url))
        return httpx.Response(200, text=store[url], request=httpx.Request("GET", url))

    monkeypatch.setattr(cn_mod.httpx, "get", fake_get)


def test_ok_at_stamped_on_successful_fetch(monkeypatch):
    store = {CHAT_URL: _fixture("cn_llm_docs_kimi_chat.md")}
    _patch(monkeypatch, store)
    src = CnLlmDocsSource(pages=[CHAT_PAGE])

    _, snapshot = src.check({}, now=NOW)

    assert snapshot["kimi:chat"]["ok_at"] == NOW.isoformat()


def test_carry_forward_preserves_the_old_ok_at_not_todays_date(monkeypatch):
    """The whole point: a permanently-dead page's ok_at must stop advancing,
    or it's indistinguishable from a page that's just unchanged."""
    chat_raw = _fixture("cn_llm_docs_kimi_chat.md")
    store = {CHAT_URL: chat_raw}
    _patch(monkeypatch, store)
    src = CnLlmDocsSource(pages=[CHAT_PAGE])
    _, snapshot = src.check({}, now=NOW)
    assert snapshot["kimi:chat"]["ok_at"] == NOW.isoformat()

    later = NOW + timedelta(days=30)
    _patch(monkeypatch, store, dead={CHAT_URL})  # page is now permanently dead
    _, snapshot2 = src.check(snapshot, now=later)

    assert snapshot2["kimi:chat"]["ok_at"] == NOW.isoformat()  # carried forward, not bumped
    assert snapshot2["kimi:chat"]["ok_at"] != later.isoformat()


# ---------------------------------------------------------------------------
# state.py: record_freshness / freshness persistence
# ---------------------------------------------------------------------------


def test_freshness_roundtrips_through_save_load(tmp_path):
    path = tmp_path / "deals_state.json"
    s = StateStore(path=path)
    s.load()
    when = datetime(2025, 7, 31, tzinfo=UTC)
    s.record_freshness("aff", when)
    s.save()

    s2 = StateStore(path=path)
    s2.load()
    assert s2.freshness("aff") == when
    assert s2.freshness("nodeseek") is None  # never recorded -> None, not KeyError


def test_freshness_naive_timestamp_coerced_to_aware_on_load(tmp_path):
    """A hand-edited (naive) timestamp in the committed state file must not
    crash a later subtraction against a tz-aware `now` (same guard as
    last_fetch's — see state.py's _aware())."""
    path = tmp_path / "deals_state.json"
    raw = {"cold_start": False, "freshness": {"aff": "2025-07-31T00:00:00"}}
    path.write_text(json.dumps(raw))
    s = StateStore(path=path)

    s.load()

    assert s.freshness("aff") == datetime(2025, 7, 31, tzinfo=UTC)
