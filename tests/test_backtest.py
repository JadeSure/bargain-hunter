"""Tests for the offline backtest harness (P1.1)."""

from datetime import date
from pathlib import Path

from bargain_hunter.backtest import (
    ObservationRow,
    _replay_is_candidate,
    load_observations,
    load_sent_log,
    render_report,
    replay,
    run_backtest,
)
from bargain_hunter.config import HotConfig, ScoringConfig

FIXTURES = Path(__file__).parent / "fixtures" / "backtest"


def _row(**kw) -> ObservationRow:
    defaults = dict(
        ts="2026-01-01T00:00:00+00:00",
        deal_key="ozbargain:x",
        title="Test deal",
        votes_pos=0,
        n_snapshots=2,
        vote_velocity=0.0,
    )
    defaults.update(kw)
    return ObservationRow(**defaults)


def test_load_observations_date_filtering():
    all_rows = load_observations(FIXTURES)
    expected = {"ozbargain:A", "ozbargain:B", "ozbargain:D", "ozbargain:E"}
    assert {r.deal_key for r in all_rows} == expected

    only_day_one = load_observations(FIXTURES, date_from=date(2026, 1, 1), date_to=date(2026, 1, 1))
    assert {r.deal_key for r in only_day_one} == {"ozbargain:A", "ozbargain:B"}


def test_replay_sanity_matches_recorded_current_config():
    """Acceptance criterion: replaying the config that produced the observations
    reproduces the same hot classifications (see backtest.py module docstring)."""
    rows = load_observations(FIXTURES)
    from bargain_hunter.config import load_settings

    settings = load_settings(FIXTURES / "current.yaml")
    replayed = replay(rows, settings.scoring)
    levels = {row.deal_key: level for row, level in replayed}

    assert levels["ozbargain:A"] == "good"
    assert levels["ozbargain:B"] is None
    assert levels["ozbargain:D"] == "good"
    assert levels["ozbargain:E"] == "good"
    # Matches what was actually recorded at write time (classify_hot only —
    # see the module docstring's "Quality gate" section for why the quality
    # gate itself is deliberately excluded from this comparison).
    for row, level in replayed:
        assert level == row.hot_level


def test_fire_count_aggregation():
    report = run_backtest(settings_path=FIXTURES / "current.yaml", obs_dir=FIXTURES)
    assert report.total_rows == 4
    assert report.fire_counts_by_tier == {"good": 3}
    assert report.fire_rate == round(3 / 4, 4)
    assert report.daily_volume == {"2026-01-01": 1, "2026-01-02": 2}


def test_quality_gate_suppresses_sendable_count_without_affecting_classification():
    """ozbargain:E classifies as "good" (matching recorded ground truth) but has
    no discount signal, so it fails current.yaml's quality gate — it should be
    counted in fire_counts_by_tier but excluded from sendable_fire_counts_by_tier,
    and it must NOT appear as a no-longer-fire diff (ground truth has no concept
    of the quality gate — see module docstring)."""
    report = run_backtest(settings_path=FIXTURES / "current.yaml", obs_dir=FIXTURES)
    assert report.sendable_fire_counts_by_tier == {"good": 2}  # A and D only, not E
    assert "ozbargain:E" not in report.no_longer_fire


def test_no_longer_fire_under_stricter_config():
    report = run_backtest(settings_path=FIXTURES / "stricter.yaml", obs_dir=FIXTURES)
    assert report.fire_counts_by_tier == {}
    assert set(report.no_longer_fire) == {"ozbargain:A", "ozbargain:D", "ozbargain:E"}
    assert report.newly_fire == []


def test_newly_fire_under_looser_config():
    report = run_backtest(settings_path=FIXTURES / "looser.yaml", obs_dir=FIXTURES)
    assert report.newly_fire == ["ozbargain:B"]
    # A and D were already recorded hot — not "newly" firing.
    assert report.no_longer_fire == []


def test_no_sent_log_graceful_path():
    report = run_backtest(settings_path=FIXTURES / "current.yaml", obs_dir=FIXTURES)
    assert report.sent_log_stats is None
    output = render_report(report)
    assert "Sent-log" not in output


def test_sent_log_join_computes_positive_rate():
    sent_log = load_sent_log(FIXTURES / "sent_log.json")
    report = run_backtest(
        settings_path=FIXTURES / "looser.yaml",
        obs_dir=FIXTURES,
        sent_log_path=FIXTURES / "sent_log.json",
    )
    assert sent_log[0]["deal_key"] == "ozbargain:A"
    assert report.sent_log_stats is not None
    # A (up), B (down), D (up) all fire under looser.yaml as "good".
    assert report.sent_log_stats["good"]["n"] == 3
    assert report.sent_log_stats["good"]["positive_rate"] == round(2 / 3, 4)


def test_render_report_smoke():
    report = run_backtest(settings_path=FIXTURES / "current.yaml", obs_dir=FIXTURES)
    output = render_report(report)
    assert "Fire counts by tier" in output
    assert "sendable after quality gate" in output
    assert "Newly fires under candidate config" in output
    assert "No longer fires under candidate config" in output


def test_gate3_percentile_requires_top_velocity_in_cohort():
    cfg = ScoringConfig(hot=HotConfig(min_votes_gain_per_window=999, early_burst_min_votes=999))
    leader = _row(deal_key="ozbargain:leader", votes_pos=20, vote_velocity=50.0, n_snapshots=2)
    laggard = _row(deal_key="ozbargain:laggard", votes_pos=20, vote_velocity=1.0, n_snapshots=2)
    cohort = [leader, laggard]

    assert _replay_is_candidate(leader, cohort, cfg) is True
    assert _replay_is_candidate(laggard, cohort, cfg) is False


def test_candidacy_requires_minimum_snapshots_for_percentile_gate():
    cfg = ScoringConfig(hot=HotConfig(min_votes_gain_per_window=999, early_burst_min_votes=999))
    lone_but_thin = _row(votes_pos=20, vote_velocity=50.0, n_snapshots=1)
    assert _replay_is_candidate(lone_but_thin, [lone_but_thin], cfg) is False
