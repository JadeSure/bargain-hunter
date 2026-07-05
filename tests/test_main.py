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


# ---------------------------------------------------------------------------
# Quiet-hours deferral queue: quiet run queues, next run drains + merges.
# ---------------------------------------------------------------------------


class _FakeDedup:
    def __init__(self, cfg=None):
        self.sent: list[tuple[str, str]] = []

    def load(self, notion, db_id):
        pass

    def daily_count(self, sub, now=None, tracks=None):
        return 0

    def already_sent(self, deal, sub):
        return (deal.key, sub.email) in self.sent

    def realert_check(self, deal, sub, watch_target_price=None):
        return (deal.key, sub.email) in self.sent, None

    def record_sent(self, notion, db_id, deal, sub, channel, track, trigger_sig):
        self.sent.append((deal.key, sub.email))


def _wire_run(monkeypatch, tmp_path, deals, sub, dedup, quiet):
    """Common monkeypatching for run(): fake source/Notion/email, warm state."""
    monkeypatch.chdir(tmp_path)
    state_path = Path("data/deals_state.json")
    if not state_path.exists():
        Path("data").mkdir(exist_ok=True)
        state_path.write_text(
            json.dumps({"cold_start": False, "snapshots": {}, "first_seen": {}}),
            encoding="utf-8",
        )

    class FakeSource:
        def __init__(self, *a, **kw):
            pass

        def fetch(self):
            return list(deals)

    sent_digests = []

    def fake_send_digest(self, subscriber, items, subject=None, cap_suppressed=0):
        sent_digests.append((subscriber.email, list(items), cap_suppressed))
        return True

    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_SUBSCRIBERS_DB_ID", "s")
    monkeypatch.setenv("NOTION_SENT_LOG_DB_ID", "l")
    monkeypatch.setattr(main_mod, "OzBargainSource", FakeSource)
    monkeypatch.setattr(main_mod, "make_notion_client", lambda: object())
    monkeypatch.setattr(main_mod, "fetch_subscribers", lambda *a, **kw: [sub])
    monkeypatch.setattr(main_mod, "DedupStore", lambda cfg: dedup)
    monkeypatch.setattr(main_mod.EmailSender, "send_digest", fake_send_digest)
    monkeypatch.setattr(main_mod, "_is_quiet_hours", lambda settings, now: quiet)
    return sent_digests


def _watch_settings() -> Settings:
    return Settings.model_validate(
        {
            "sources": {"ozbargain": {"enabled": True}},
            "scoring": {"watch": {"min_votes": 5}},
        }
    )


def test_quiet_hours_queues_instead_of_sending(monkeypatch, tmp_path):
    now = datetime.now(UTC)
    deals = [
        _deal(
            deal_id="n1",
            title="Nintendo Switch OLED",
            votes_pos=20,
            posted_at=now - timedelta(hours=1),
        )
    ]
    sub = Subscriber(
        name="Night", email="night@example.com",
        subscribe_hot=False, watch_keywords=["Nintendo"],
    )
    dedup = _FakeDedup()
    sent = _wire_run(monkeypatch, tmp_path, deals, sub, dedup, quiet=True)

    summary = main_mod.run(_watch_settings(), dry_run=True)

    assert sent == []  # nothing emailed during quiet hours
    assert summary["notifications_sent"] == 0
    assert summary["queued"] == 1
    assert Path("data/queued_notifications.json").exists()


def test_drain_merges_queued_into_next_digest_and_clears_queue(monkeypatch, tmp_path):
    now = datetime.now(UTC)
    overnight = _deal(
        deal_id="n1",
        title="Nintendo Switch OLED",
        votes_pos=20,
        posted_at=now - timedelta(hours=2),
    )
    sub = Subscriber(
        name="Night", email="night@example.com",
        subscribe_hot=False, watch_keywords=["Nintendo"],
    )
    dedup = _FakeDedup()

    # Quiet run: deal is queued.
    _wire_run(monkeypatch, tmp_path, [overnight], sub, dedup, quiet=True)
    main_mod.run(_watch_settings(), dry_run=True)

    # Morning run: feed no longer carries the deal, but the queue does.
    sent = _wire_run(monkeypatch, tmp_path, [], sub, dedup, quiet=False)
    summary = main_mod.run(_watch_settings(), dry_run=True)

    assert len(sent) == 1
    email, items, _ = sent[0]
    assert email == "night@example.com"
    assert [i.deal.key for i in items] == ["ozbargain:n1"]
    assert summary["notifications_sent"] == 1
    # Queue cleared after drain.
    q_raw = json.loads(Path("data/queued_notifications.json").read_text(encoding="utf-8"))
    assert q_raw["entries"] == []


def test_drain_drops_stale_and_already_sent_entries(monkeypatch, tmp_path):
    now = datetime.now(UTC)
    fresh = _deal(
        deal_id="fresh", title="Nintendo fresh", votes_pos=20,
        posted_at=now - timedelta(hours=2),
    )
    sub = Subscriber(
        name="Night", email="night@example.com",
        subscribe_hot=False, watch_keywords=["Nintendo"],
    )
    dedup = _FakeDedup()

    _wire_run(monkeypatch, tmp_path, [fresh], sub, dedup, quiet=True)
    main_mod.run(_watch_settings(), dry_run=True)

    # Rewrite the queue to add a stale entry and an already-sent entry.
    qpath = Path("data/queued_notifications.json")
    q_raw = json.loads(qpath.read_text(encoding="utf-8"))
    fresh_entry = q_raw["entries"][0]
    stale_entry = json.loads(json.dumps(fresh_entry))
    stale_entry["deal"]["deal_id"] = "stale"
    stale_entry["queued_at"] = (now - timedelta(hours=13)).isoformat()
    sent_entry = json.loads(json.dumps(fresh_entry))
    sent_entry["deal"]["deal_id"] = "sentalready"
    q_raw["entries"] += [stale_entry, sent_entry]
    qpath.write_text(json.dumps(q_raw), encoding="utf-8")
    dedup.sent.append(("ozbargain:sentalready", "night@example.com"))

    sent = _wire_run(monkeypatch, tmp_path, [], sub, dedup, quiet=False)
    main_mod.run(_watch_settings(), dry_run=True)

    assert len(sent) == 1
    _, items, _ = sent[0]
    assert [i.deal.deal_id for i in items] == ["fresh"]
