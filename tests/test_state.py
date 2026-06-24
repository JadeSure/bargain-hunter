"""Tests for state persistence and the cold-start / staleness guard (FR8)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from bargain_hunter.models import Deal
from bargain_hunter.state import StateStore


def _deal(**kw) -> Deal:
    defaults = dict(
        source="ozbargain",
        deal_id="1",
        title="Test",
        url="https://ozbargain.com.au/node/1",
        posted_at=datetime.now(UTC) - timedelta(hours=1),
    )
    defaults.update(kw)
    return Deal(**defaults)


def test_should_notify_false_on_cold_start():
    s = StateStore(path=Path("/nonexistent/deals_state.json"))
    s.load()  # missing file -> cold start
    assert s.is_cold_start()
    assert not s.should_notify(_deal(), 6.0, is_first_sighting=True)


def test_should_notify_blocks_stale_first_sighting():
    s = StateStore(path=Path("/nonexistent/x.json"))
    s.load()
    s._cold_start = False  # simulate being past cold start
    old = _deal(posted_at=datetime.now(UTC) - timedelta(hours=48))
    fresh = _deal(posted_at=datetime.now(UTC) - timedelta(hours=1))
    assert not s.should_notify(old, 6.0, is_first_sighting=True)
    assert s.should_notify(fresh, 6.0, is_first_sighting=True)


def test_should_notify_allows_known_deal_regardless_of_age():
    s = StateStore(path=Path("/nonexistent/x.json"))
    s.load()
    s._cold_start = False
    old = _deal(posted_at=datetime.now(UTC) - timedelta(hours=48))
    # Already known (not a first sighting) -> staleness guard does not apply.
    assert s.should_notify(old, 6.0, is_first_sighting=False)


def test_click_count_roundtrip(tmp_path):
    path = tmp_path / "deals_state.json"
    s = StateStore(path=path)
    s.load()
    d = _deal(votes_pos=5, comment_count=2, click_count=42)
    s.record(d)
    s.save()

    s2 = StateStore(path=path)
    s2.load()
    snaps = s2.snapshots(d.key)
    assert snaps
    assert snaps[-1].click_count == 42
