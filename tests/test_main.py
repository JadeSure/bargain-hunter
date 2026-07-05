"""Tests for word-boundary block-keyword matching and cap counting in main.py."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bargain_hunter import main as main_mod
from bargain_hunter.config import Settings
from bargain_hunter.main import _is_blocked
from bargain_hunter.models import Deal, Subscriber


def _deal(**kw) -> Deal:
    defaults = dict(
        source="ozbargain",
        deal_id="1",
        title="Test",
        url="https://ozbargain.com.au/node/1",
        votes_pos=10,
        votes_neg=0,
        comment_count=0,
    )
    defaults.update(kw)
    return Deal(**defaults)


def test_block_keyword_does_not_match_substring():
    """Block keyword "pro" must not suppress "projector"."""
    deal = _deal(title="Epson Projector $299")
    assert not _is_blocked(deal, ["pro"])


def test_block_keyword_matches_whole_word():
    deal = _deal(title="Pro subscription discount")
    assert _is_blocked(deal, ["pro"])


def test_block_keyword_no_hits_returns_false():
    deal = _deal(title="Random deal")
    assert not _is_blocked(deal, [])


# ---------------------------------------------------------------------------
# Daily-cap suppression counter (integration-style: run() with all network
# boundaries monkeypatched; only the selection loop is real).
# ---------------------------------------------------------------------------


def test_run_counts_cap_suppressed_and_passes_to_digest(monkeypatch, tmp_path):
    """Two fresh watch-matching deals, max_watch_alerts_per_day=1: one is sent
    and the other is counted as cap-suppressed and passed to send_digest for
    the footer note."""
    monkeypatch.chdir(tmp_path)
    # Warm state (not cold start), so the watch track's should_notify can pass.
    Path("data").mkdir()
    Path("data/deals_state.json").write_text(
        json.dumps({"cold_start": False, "snapshots": {}, "first_seen": {}}),
        encoding="utf-8",
    )

    now = datetime.now(UTC)
    deals = [
        _deal(
            deal_id=str(i),
            title=f"Nintendo Switch bundle {i}",
            votes_pos=20,
            posted_at=now - timedelta(hours=1),
        )
        for i in (1, 2)
    ]

    class FakeSource:
        def __init__(self, *a, **kw):
            pass

        def fetch(self):
            return deals

    sub = Subscriber(
        name="Capped",
        email="capped@example.com",
        subscribe_hot=False,
        watch_keywords=["Nintendo"],
        max_watch_alerts_per_day=1,
    )

    sent = {}

    def fake_send_digest(self, subscriber, items, subject=None, cap_suppressed=0):
        sent["items"] = items
        sent["cap_suppressed"] = cap_suppressed
        return True

    class FakeDedup:
        def __init__(self, cfg):
            pass

        def load(self, notion, db_id):
            pass

        def daily_count(self, sub, now=None, tracks=None):
            return 0

        def already_sent(self, deal, sub):
            return False

        def realert_check(self, deal, sub, watch_target_price=None):
            return False, None

        def record_sent(self, *a, **kw):
            pass

    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_SUBSCRIBERS_DB_ID", "s")
    monkeypatch.setenv("NOTION_SENT_LOG_DB_ID", "l")
    monkeypatch.setattr(main_mod, "OzBargainSource", FakeSource)
    monkeypatch.setattr(main_mod, "make_notion_client", lambda: object())
    monkeypatch.setattr(main_mod, "fetch_subscribers", lambda *a, **kw: [sub])
    monkeypatch.setattr(main_mod, "DedupStore", FakeDedup)
    monkeypatch.setattr(main_mod.EmailSender, "send_digest", fake_send_digest)

    settings = Settings.model_validate(
        {
            "sources": {"ozbargain": {"enabled": True}},
            "scoring": {"watch": {"min_votes": 5}},
        }
    )
    summary = main_mod.run(settings, dry_run=True)

    assert summary["watch_matches"] == 1
    assert len(sent["items"]) == 1
    assert sent["cap_suppressed"] == 1
