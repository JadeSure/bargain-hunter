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
    """Common monkeypatching for run(): fake source/Notion/email, warm state.

    ``sub`` may be a single Subscriber or a list. ``quiet`` may be None to keep
    the real per-subscriber ``is_in_quiet_hours`` resolution (for tests that
    exercise subscriber-level quiet-hours overrides).
    """
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
    subs = sub if isinstance(sub, list) else [sub]
    monkeypatch.setattr(main_mod, "fetch_subscribers", lambda *a, **kw: list(subs))
    monkeypatch.setattr(main_mod, "DedupStore", lambda cfg: dedup)
    monkeypatch.setattr(main_mod.EmailSender, "send_digest", fake_send_digest)
    if quiet is not None:
        monkeypatch.setattr(main_mod, "is_in_quiet_hours", lambda sub, now, cfg: quiet)
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


def test_per_subscriber_quiet_hours_override(monkeypatch, tmp_path):
    """One subscriber's own quiet window queues while another's sends, same run."""
    from zoneinfo import ZoneInfo

    now = datetime.now(UTC)
    deals = [
        _deal(
            deal_id="n1",
            title="Nintendo Switch OLED",
            votes_pos=20,
            posted_at=now - timedelta(hours=1),
        )
    ]
    settings = _watch_settings()
    local = now.astimezone(ZoneInfo(settings.run.timezone))

    def hhmm(offset_hours: int) -> str:
        shifted = local + timedelta(hours=offset_hours)
        return f"{shifted.hour:02d}:{shifted.minute:02d}"

    night = Subscriber(
        name="Night", email="night@example.com",
        subscribe_hot=False, watch_keywords=["Nintendo"],
        quiet_hours_start=hhmm(-1), quiet_hours_end=hhmm(1),  # covers now
    )
    day = Subscriber(
        name="Day", email="day@example.com",
        subscribe_hot=False, watch_keywords=["Nintendo"],
        quiet_hours_start=hhmm(1), quiet_hours_end=hhmm(2),  # excludes now
    )
    dedup = _FakeDedup()
    sent = _wire_run(monkeypatch, tmp_path, deals, [night, day], dedup, quiet=None)

    summary = main_mod.run(settings, dry_run=True)

    assert [email for email, _items, _cap in sent] == ["day@example.com"]
    assert summary["queued"] == 1
    queued_raw = json.loads(Path("data/queued_notifications.json").read_text(encoding="utf-8"))
    assert [e["subscriber_email"] for e in queued_raw["entries"]] == ["night@example.com"]


def test_drain_only_removes_draining_subscribers_queue_entries(monkeypatch, tmp_path):
    """A draining subscriber must not wipe entries owed to a still-quiet one."""
    from bargain_hunter.queue_store import NotificationQueue

    now = datetime.now(UTC)
    queue = NotificationQueue()
    deal = _deal(deal_id="q1", title="Queued deal", votes_pos=20, posted_at=now)
    queue.add("still-quiet@example.com", deal, "watch", None, "kept", now=now)
    queue.add("draining@example.com", deal, "watch", None, "drained", now=now)
    queue.remove_for("draining@example.com")
    assert [e.subscriber_email for e in queue.entries_for("still-quiet@example.com")] == [
        "still-quiet@example.com"
    ]
    assert queue.entries_for("draining@example.com") == []


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


# ---------------------------------------------------------------------------
# Digital track: separate daily quota (HIGH_VALUE_SOURCES_PLAN.md Phase C1 /
# GLOBAL_DEALS_PLAN.md Phase 2). DIGITAL_SOURCES deals must not share the
# hot/watch caps, and must survive a quiet-hours queue-and-drain round trip.
# ---------------------------------------------------------------------------


def test_digital_track_uses_independent_daily_cap(monkeypatch, tmp_path):
    """A digital-source deal still sends when hot and watch are both at their
    daily cap, because it draws from remaining_digital, not theirs — this also
    covers the "at daily caps, skipping" early-continue needing to check
    remaining_digital too."""
    now = datetime.now(UTC)
    deal = _deal(
        source="dealnews",
        deal_id="d1",
        title="SuperGrok now free",
        votes_pos=20,
        posted_at=now - timedelta(hours=1),
    )
    sub = Subscriber(
        name="Digital", email="digital@example.com",
        subscribe_hot=False, watch_keywords=["SuperGrok"],
        max_alerts_per_day=0, max_watch_alerts_per_day=0,
    )
    dedup = _FakeDedup()
    sent = _wire_run(monkeypatch, tmp_path, [deal], sub, dedup, quiet=False)

    summary = main_mod.run(_watch_settings(), dry_run=True)

    assert summary["notifications_sent"] == 1
    assert len(sent) == 1
    email, items, _cap = sent[0]
    assert email == "digital@example.com"
    assert [i.track for i in items] == ["digital"]


def test_digital_entry_survives_quiet_hours_queue_and_drain(monkeypatch, tmp_path):
    """A queued digital-track entry must not be silently dropped at drain
    time — main.py's queue drain used to only recognise {'hot','mixed'} and
    'watch', which would swallow a 'digital' entry without a third block."""
    now = datetime.now(UTC)
    deal = _deal(
        source="dealnews",
        deal_id="d1",
        title="SuperGrok now free",
        votes_pos=20,
        posted_at=now - timedelta(hours=2),
    )
    sub = Subscriber(
        name="Night", email="night@example.com",
        subscribe_hot=False, watch_keywords=["SuperGrok"],
    )
    dedup = _FakeDedup()

    # Quiet run: deal is queued with track="digital".
    _wire_run(monkeypatch, tmp_path, [deal], sub, dedup, quiet=True)
    summary1 = main_mod.run(_watch_settings(), dry_run=True)
    assert summary1["queued"] == 1
    q_raw = json.loads(Path("data/queued_notifications.json").read_text(encoding="utf-8"))
    assert [e["track"] for e in q_raw["entries"]] == ["digital"]

    # Morning run: feed no longer carries the deal, but the queue does.
    sent = _wire_run(monkeypatch, tmp_path, [], sub, dedup, quiet=False)
    summary2 = main_mod.run(_watch_settings(), dry_run=True)

    assert len(sent) == 1
    email, items, _cap = sent[0]
    assert email == "night@example.com"
    assert [i.deal.key for i in items] == ["dealnews:d1"]
    assert [i.track for i in items] == ["digital"]
    assert summary2["notifications_sent"] == 1
    q_raw2 = json.loads(Path("data/queued_notifications.json").read_text(encoding="utf-8"))
    assert q_raw2["entries"] == []


def test_digital_source_deal_that_is_also_watch_matched_arrives_mixed(monkeypatch, tmp_path):
    """A digital-source deal that both clears the hot ladder (on discount) and
    matches the subscriber's own watch keyword must not lose the watch reason.

    Regression: the digital split (main.py's _split_digital) peels DIGITAL_SOURCES
    deals out of hot_candidates into digital_from_hot *before* the watch loop's
    mixed-annotation pass, which only searched hot_items — so the annotation was
    a silent no-op for digital-source deals and the specific watch-keyword reason
    was dropped."""
    now = datetime.now(UTC)
    deal = _deal(
        source="dealnews",
        deal_id="d1",
        title="NordVPN 40% off annual plan",
        votes_pos=0,
        posted_at=now - timedelta(hours=1),
    )
    sub = Subscriber(
        name="Mixed", email="mixed@example.com",
        subscribe_hot=True, watch_keywords=["NordVPN"],
    )
    dedup = _FakeDedup()
    sent = _wire_run(monkeypatch, tmp_path, [deal], sub, dedup, quiet=False)

    settings = Settings.model_validate(
        {
            "sources": {"ozbargain": {"enabled": True}},
            "scoring": {
                "watch": {
                    "min_votes": 5,
                    "min_discount_percent": 10,
                    "trusted_sources": ["dealnews"],
                },
                "hot": {"voteless_sources": ["dealnews"], "discount_tiers": {"hot": 40.0}},
            },
        }
    )
    summary = main_mod.run(settings, dry_run=True)

    assert summary["notifications_sent"] == 1
    email, items, _cap = sent[0]
    assert email == "mixed@example.com"
    assert len(items) == 1
    item = items[0]
    assert item.track == "mixed"
    assert item.reason == '40% off · "NordVPN" matched, 40% off'


def test_new_source_poll_interval_gating_skips_when_not_due(monkeypatch, tmp_path):
    """dealnews (and the other slow-cadence sources) must respect
    poll_interval_minutes via state.due_for_fetch, not refetch every run.

    Uses dry_run=False: this test needs state.due_for_fetch persisted across
    the two run() calls, and no Notion/email path is exercised either way
    (env vars are deleted below), so a live run is safe here."""
    monkeypatch.chdir(tmp_path)
    Path("data").mkdir()
    Path("data/deals_state.json").write_text(
        json.dumps({"cold_start": False, "snapshots": {}, "first_seen": {}}),
        encoding="utf-8",
    )
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_SUBSCRIBERS_DB_ID", raising=False)
    monkeypatch.delenv("NOTION_SENT_LOG_DB_ID", raising=False)

    fetch_calls = []

    class _EmptyOzb:
        def __init__(self, *a, **kw):
            pass

        def fetch(self):
            return []

    class FakeFeedDealsSource:
        def __init__(self, *a, **kw):
            pass

        def fetch(self):
            fetch_calls.append(1)
            return []

    monkeypatch.setattr(main_mod, "OzBargainSource", _EmptyOzb)
    monkeypatch.setattr(main_mod, "FeedDealsSource", FakeFeedDealsSource)

    settings = Settings.model_validate(
        {
            "sources": {
                "ozbargain": {"enabled": True},
                "dealnews": {
                    "enabled": True,
                    "poll_interval_minutes": 60,
                    "feed_urls": ["https://example.com/feed"],
                },
            },
        }
    )

    main_mod.run(settings, dry_run=False)
    assert len(fetch_calls) == 1

    main_mod.run(settings, dry_run=False)
    assert len(fetch_calls) == 1  # second run, interval not elapsed — skipped


# ---------------------------------------------------------------------------
# --dry-run must not touch tracked calibration data (regression: a local
# dry run once overwrote data/deals_state.json and appended to the committed
# observation log).
# ---------------------------------------------------------------------------


def _dry_run_settings() -> Settings:
    return Settings.model_validate({"sources": {"ozbargain": {"enabled": True}}})


def test_dry_run_does_not_persist_state_or_observations(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_SUBSCRIBERS_DB_ID", raising=False)
    monkeypatch.delenv("NOTION_SENT_LOG_DB_ID", raising=False)

    class FakeSource:
        def __init__(self, *a, **kw):
            pass

        def fetch(self):
            return [_deal()]

    monkeypatch.setattr(main_mod, "OzBargainSource", FakeSource)

    main_mod.run(_dry_run_settings(), dry_run=True)

    assert not Path("data/deals_state.json").exists()
    assert not Path("data/observations").exists()


def test_live_run_persists_state_and_observations(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_SUBSCRIBERS_DB_ID", raising=False)
    monkeypatch.delenv("NOTION_SENT_LOG_DB_ID", raising=False)

    class FakeSource:
        def __init__(self, *a, **kw):
            pass

        def fetch(self):
            return [_deal()]

    monkeypatch.setattr(main_mod, "OzBargainSource", FakeSource)

    main_mod.run(_dry_run_settings(), dry_run=False)

    assert Path("data/deals_state.json").exists()
    assert list(Path("data/observations").glob("*.jsonl"))
