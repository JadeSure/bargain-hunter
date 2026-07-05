"""Tests for state persistence and the cold-start / staleness guard (FR8)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from bargain_hunter.models import Deal, DealSnapshot
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


def test_prune_removes_orphaned_first_seen_entries(tmp_path):
    s = StateStore(path=tmp_path / "deals_state.json", retention_hours=1)
    old = datetime.now(UTC) - timedelta(hours=2)
    s._first_seen["ozbargain:old"] = old

    s.save()

    s2 = StateStore(path=s.path)
    s2.load()
    assert s2.first_seen("ozbargain:old") is None


def test_prune_keeps_first_seen_for_deals_with_snapshots(tmp_path):
    s = StateStore(path=tmp_path / "deals_state.json", retention_hours=1)
    d = _deal()
    first_seen = datetime.now(UTC) - timedelta(hours=2)
    s._first_seen[d.key] = first_seen
    s.record(d, now=datetime.now(UTC))

    s.save()

    s2 = StateStore(path=s.path)
    s2.load()
    assert s2.first_seen(d.key) == first_seen


# ---------------------------------------------------------------------------
# Cold-start seeding: a stale first sighting is suppressed but not killed —
# it can graduate on a later run if it shows renewed, candidacy-level velocity.
# ---------------------------------------------------------------------------


def _snaps(*votes: int, spacing_minutes: int = 15) -> list[DealSnapshot]:
    base = datetime.now(UTC) - timedelta(minutes=spacing_minutes * len(votes))
    return [
        DealSnapshot(
            ts=base + timedelta(minutes=i * spacing_minutes),
            votes_pos=v,
            votes_neg=0,
            comment_count=0,
        )
        for i, v in enumerate(votes)
    ]


def test_stale_first_sighting_is_seeded_not_killed():
    s = StateStore(path=Path("/nonexistent/x.json"))
    s.load()
    s._cold_start = False
    old = _deal(posted_at=datetime.now(UTC) - timedelta(hours=48))
    assert not s.should_notify(old, 6.0, is_first_sighting=True)
    assert old.key in s._seeded


def test_seeded_deal_stays_suppressed_without_velocity_gate_args():
    """No snapshots/window info passed -> can't evaluate the velocity gate, so
    a seeded deal stays suppressed rather than defaulting to eligible."""
    s = StateStore(path=Path("/nonexistent/x.json"))
    s.load()
    s._cold_start = False
    old = _deal(posted_at=datetime.now(UTC) - timedelta(hours=48))
    assert not s.should_notify(old, 6.0, is_first_sighting=True)
    assert not s.should_notify(old, 6.0, is_first_sighting=False)


def test_seeded_deal_stays_suppressed_below_candidacy_velocity():
    s = StateStore(path=Path("/nonexistent/x.json"))
    s.load()
    s._cold_start = False
    old = _deal(posted_at=datetime.now(UTC) - timedelta(hours=48))
    assert not s.should_notify(old, 6.0, is_first_sighting=True)
    # Slow trickle: 10 -> 11 votes over 15 min = 4 votes/h -> 4-vote window
    # gain over a 60-min window, below the 5-vote candidacy bar.
    snaps = _snaps(10, 11)
    assert not s.should_notify(
        old,
        6.0,
        is_first_sighting=False,
        snapshots=snaps,
        window_minutes=60,
        min_votes_gain_per_window=5,
    )
    assert old.key in s._seeded


def test_seeded_deal_graduates_on_velocity_burst():
    """Cold-start-then-burst scenario: a stale deal suppressed on first sight
    later shows real hot-candidacy-level velocity and becomes eligible again."""
    s = StateStore(path=Path("/nonexistent/x.json"))
    s.load()
    s._cold_start = False
    old = _deal(posted_at=datetime.now(UTC) - timedelta(hours=48))
    assert not s.should_notify(old, 6.0, is_first_sighting=True)

    # Burst: 10 -> 40 votes in 15 min = 120 votes/h -> 120-vote window gain
    # over a 60-min window, comfortably over the 5-vote candidacy bar.
    snaps = _snaps(10, 40)
    assert s.should_notify(
        old,
        6.0,
        is_first_sighting=False,
        snapshots=snaps,
        window_minutes=60,
        min_votes_gain_per_window=5,
    )
    # Graduated: no longer seeded, and now eligible unconditionally like any
    # other known deal (regardless of velocity args on subsequent calls).
    assert old.key not in s._seeded
    assert s.should_notify(old, 6.0, is_first_sighting=False)


def test_seeded_state_persists_across_save_load(tmp_path):
    path = tmp_path / "deals_state.json"
    s = StateStore(path=path)
    s.load()
    s._cold_start = False
    old = _deal(posted_at=datetime.now(UTC) - timedelta(hours=48))
    assert not s.should_notify(old, 6.0, is_first_sighting=True)
    s.save()

    s2 = StateStore(path=path)
    s2.load()
    assert old.key in s2._seeded
    assert not s2.should_notify(old, 6.0, is_first_sighting=False)


def test_first_run_mass_send_regression_cold_start_then_normal_deals_unaffected():
    """A fresh (non-cold-start) run with a mix of brand-new fresh deals must
    not be affected by the seeding mechanism — only stale first-sightings get
    seeded; fresh new deals notify immediately as before."""
    s = StateStore(path=Path("/nonexistent/x.json"))
    s.load()
    s._cold_start = False
    fresh = _deal(deal_id="fresh", posted_at=datetime.now(UTC) - timedelta(minutes=30))
    assert s.should_notify(fresh, 6.0, is_first_sighting=True)
    assert fresh.key not in s._seeded
