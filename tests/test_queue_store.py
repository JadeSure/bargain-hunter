"""Tests for the quiet-hours notification queue (persistence, staleness, drain)."""

from datetime import UTC, datetime, timedelta

from bargain_hunter.models import Deal
from bargain_hunter.queue_store import NotificationQueue, QueuedNotification


def _deal(**kw) -> Deal:
    defaults = dict(
        source="ozbargain",
        deal_id="1",
        title="Test deal",
        url="https://ozbargain.com.au/node/1",
        votes_pos=20,
        posted_at=datetime.now(UTC) - timedelta(hours=1),
    )
    defaults.update(kw)
    return Deal(**defaults)


def _queue(tmp_path) -> NotificationQueue:
    return NotificationQueue(path=tmp_path / "queued_notifications.json")


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_queue_roundtrip(tmp_path):
    now = datetime.now(UTC)
    q = _queue(tmp_path)
    q.add("alice@example.com", _deal(), "watch", None, '"Sony" matched (20 votes)', now=now)
    q.add("alice@example.com", _deal(deal_id="2"), "hot", "great", "▲ 40 votes", now=now)
    q.save()

    q2 = _queue(tmp_path)
    q2.load()
    assert len(q2) == 2
    entries = q2.entries_for("alice@example.com")
    by_key = {e.deal.key: e for e in entries}
    assert by_key["ozbargain:2"].level == "great"
    assert by_key["ozbargain:2"].queued_at == now
    assert by_key["ozbargain:1"].track == "watch"


def test_queue_missing_file_is_empty(tmp_path):
    q = _queue(tmp_path)
    q.load()
    assert len(q) == 0


def test_queue_corrupt_file_is_empty(tmp_path):
    path = tmp_path / "queued_notifications.json"
    path.write_text("{not json", encoding="utf-8")
    q = NotificationQueue(path=path)
    q.load()
    assert len(q) == 0


def test_queue_requeue_same_deal_keeps_original_queued_at(tmp_path):
    first = datetime.now(UTC) - timedelta(hours=3)
    later = datetime.now(UTC)
    q = _queue(tmp_path)
    q.add("alice@example.com", _deal(votes_pos=10), "hot", "good", "▲ 10 votes", now=first)
    q.add("alice@example.com", _deal(votes_pos=50), "hot", "great", "▲ 50 votes", now=later)
    assert len(q) == 1
    entry = q.entries_for("alice@example.com")[0]
    assert entry.queued_at == first  # staleness clock starts at first queueing
    assert entry.level == "great"  # payload refreshed to the latest observation
    assert entry.deal.votes_pos == 50


def test_queue_clear(tmp_path):
    q = _queue(tmp_path)
    q.add("alice@example.com", _deal(), "hot", "good", "", now=datetime.now(UTC))
    q.clear()
    q.save()
    q2 = _queue(tmp_path)
    q2.load()
    assert len(q2) == 0


# ---------------------------------------------------------------------------
# Staleness filtering (drain_for)
# ---------------------------------------------------------------------------


def _entry(queued_at: datetime, **deal_kw) -> QueuedNotification:
    return QueuedNotification(
        subscriber_email="alice@example.com",
        deal=_deal(**deal_kw),
        track="watch",
        reason="",
        queued_at=queued_at,
    )


def test_is_stale_when_older_than_max_age():
    now = datetime.now(UTC)
    assert _entry(now - timedelta(hours=13)).is_stale(now, max_age_hours=12.0)
    assert not _entry(now - timedelta(hours=11)).is_stale(now, max_age_hours=12.0)


def test_is_stale_when_deal_expired_flag():
    now = datetime.now(UTC)
    assert _entry(now - timedelta(hours=1), expired=True).is_stale(now, 12.0)


def test_is_stale_when_deal_expiry_passed():
    now = datetime.now(UTC)
    assert _entry(now - timedelta(hours=1), expiry=now - timedelta(minutes=5)).is_stale(now, 12.0)
    assert not _entry(now - timedelta(hours=1), expiry=now + timedelta(hours=1)).is_stale(now, 12.0)


def test_drain_for_filters_stale_and_other_subscribers(tmp_path):
    now = datetime.now(UTC)
    q = _queue(tmp_path)
    q.add("alice@example.com", _deal(deal_id="fresh"), "watch", None, "", now=now)
    q.add(
        "alice@example.com",
        _deal(deal_id="old"),
        "watch",
        None,
        "",
        now=now - timedelta(hours=13),
    )
    q.add(
        "alice@example.com",
        _deal(deal_id="expired", expired=True),
        "watch",
        None,
        "",
        now=now,
    )
    q.add("bob@example.com", _deal(deal_id="bobs"), "watch", None, "", now=now)

    survivors = q.drain_for("alice@example.com", now=now, max_age_hours=12.0)
    assert [e.deal.deal_id for e in survivors] == ["fresh"]
