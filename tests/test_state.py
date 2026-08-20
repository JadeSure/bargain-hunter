"""Tests for state persistence and the cold-start / staleness guard (FR8)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

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


# ---------------------------------------------------------------------------
# Event-day adaptive baseline
# ---------------------------------------------------------------------------


def test_site_baseline_missing_returns_none():
    s = StateStore(path=Path("/nonexistent/x.json"))
    s.load()
    assert s.site_baseline(9) is None
    assert s.baseline_age_days() == 0.0


def test_site_baseline_first_update_seeds_bucket():
    s = StateStore(path=Path("/nonexistent/x.json"))
    s.load()
    now = datetime.now(UTC)
    s.update_site_baseline(2.0, hour=9, now=now, half_life_days=14.0, sample_clamp=3.0)
    result = s.site_baseline(9)
    assert result is not None
    ewma, updated_at = result
    assert ewma == 2.0
    assert updated_at == now
    assert s.baseline_age_days(now) == 0.0


def test_site_baseline_roundtrips_through_save_load(tmp_path):
    path = tmp_path / "deals_state.json"
    s = StateStore(path=path)
    s.load()
    now = datetime.now(UTC)
    s.update_site_baseline(2.0, hour=9, now=now, half_life_days=14.0, sample_clamp=3.0)
    s.save()

    s2 = StateStore(path=path)
    s2.load()
    result = s2.site_baseline(9)
    assert result is not None
    assert result[0] == pytest.approx(2.0)
    assert s2.baseline_age_days(now) == pytest.approx(0.0, abs=1e-6)


def test_loading_old_format_state_without_site_baseline_works(tmp_path):
    path = tmp_path / "deals_state.json"
    path.write_text(json.dumps({"cold_start": False, "snapshots": {}}))
    s = StateStore(path=path)
    s.load()
    assert s.site_baseline(9) is None
    assert s.baseline_age_days() == 0.0


def test_site_baseline_ewma_time_aware_decay():
    s = StateStore(path=Path("/nonexistent/x.json"))
    s.load()
    t0 = datetime.now(UTC)
    s.update_site_baseline(10.0, hour=9, now=t0, half_life_days=14.0, sample_clamp=3.0)
    # Exactly one half-life later, a sample of 0 should pull the EWMA halfway down.
    t1 = t0 + timedelta(days=14.0)
    s.update_site_baseline(0.0, hour=9, now=t1, half_life_days=14.0, sample_clamp=3.0)
    ewma, _ = s.site_baseline(9)
    assert ewma == pytest.approx(5.0, abs=0.01)


def test_site_baseline_sample_clamp_caps_event_day_spike():
    s = StateStore(path=Path("/nonexistent/x.json"))
    s.load()
    t0 = datetime.now(UTC)
    s.update_site_baseline(10.0, hour=9, now=t0, half_life_days=14.0, sample_clamp=3.0)
    # Event-day spike of 1000 should be clamped to 3x the existing EWMA (30)
    # before the EWMA update — not allowed to poison the baseline in one run.
    t1 = t0 + timedelta(days=14.0)
    s.update_site_baseline(1000.0, hour=9, now=t1, half_life_days=14.0, sample_clamp=3.0)
    ewma, _ = s.site_baseline(9)
    # alpha=0.5, clamped_sample=30 -> ewma = 10 + 0.5*(30-10) = 20
    assert ewma == pytest.approx(20.0, abs=0.01)


def test_site_baseline_hour_buckets_are_independent():
    s = StateStore(path=Path("/nonexistent/x.json"))
    s.load()
    now = datetime.now(UTC)
    s.update_site_baseline(5.0, hour=9, now=now, half_life_days=14.0, sample_clamp=3.0)
    s.update_site_baseline(50.0, hour=20, now=now, half_life_days=14.0, sample_clamp=3.0)
    assert s.site_baseline(9)[0] == pytest.approx(5.0)
    assert s.site_baseline(20)[0] == pytest.approx(50.0)


def test_site_baseline_seeded_at_set_once():
    s = StateStore(path=Path("/nonexistent/x.json"))
    s.load()
    t0 = datetime.now(UTC)
    s.update_site_baseline(5.0, hour=9, now=t0, half_life_days=14.0, sample_clamp=3.0)
    assert s.baseline_age_days(t0) == pytest.approx(0.0, abs=1e-6)
    t1 = t0 + timedelta(days=5)
    s.update_site_baseline(6.0, hour=10, now=t1, half_life_days=14.0, sample_clamp=3.0)
    # seeded_at is set on the FIRST ever update across all buckets, not per-bucket.
    assert s.baseline_age_days(t1) == pytest.approx(5.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Poll-cadence gating + generic feature snapshots
# ---------------------------------------------------------------------------


def test_due_for_fetch_true_when_never_fetched():
    s = StateStore(path=Path("/nonexistent/x.json"))
    s.load()
    assert s.due_for_fetch("openrouter", 1440, datetime.now(UTC))


def test_due_for_fetch_respects_interval():
    s = StateStore(path=Path("/nonexistent/x.json"))
    s.load()
    now = datetime.now(UTC)
    s.mark_fetched("openrouter", now)
    assert not s.due_for_fetch("openrouter", 60, now + timedelta(minutes=30))
    assert s.due_for_fetch("openrouter", 60, now + timedelta(minutes=61))


def test_last_fetch_and_snapshot_roundtrip_through_save_load(tmp_path):
    path = tmp_path / "deals_state.json"
    s = StateStore(path=path)
    s.load()
    now = datetime.now(UTC)
    s.mark_fetched("bank_rates", now)
    s.set_snapshot("bank_rates", {"ING:123": {"rates": {"BONUS": 5.35}}})
    s.save()

    s2 = StateStore(path=path)
    s2.load()
    assert not s2.due_for_fetch("bank_rates", 1440, now + timedelta(hours=1))
    assert s2.snapshot("bank_rates") == {"ING:123": {"rates": {"BONUS": 5.35}}}
    assert s2.snapshot("llm_prices") == {}  # never set -> empty, not KeyError


def test_naive_last_fetch_timestamp_coerced_to_aware_on_load(tmp_path):
    """A hand-edited (naive) timestamp in the committed state file must not
    crash `due_for_fetch`'s subtraction against a tz-aware `now`."""
    path = tmp_path / "deals_state.json"
    raw = {"cold_start": False, "last_fetch": {"bank_rates": "2026-08-20T00:00:00"}}
    path.write_text(json.dumps(raw))
    s = StateStore(path=path)
    s.load()
    assert not s.due_for_fetch("bank_rates", 1440, datetime(2026, 8, 20, 1, 0, tzinfo=UTC))


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
