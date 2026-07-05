"""Tests for the weekly calibration report (Improvement PRD P2.2).

All tests operate on synthetic in-memory records — no Notion network calls,
following the frozen-fixture convention (AGENTS.md) by avoiding the network
entirely rather than mocking it.
"""

from datetime import UTC, datetime

from bargain_hunter.backtest import ObservationRow
from bargain_hunter.calibration import (
    CalibrationReport,
    FeedbackRecord,
    JoinedFeedback,
    RateCell,
    SentRecord,
    deal_source,
    distribution_comparison,
    grid_search_thresholds,
    join_feedback,
    latest_observation_by_deal,
    latest_sent_by_deal,
    rate_by_source,
    rate_by_tier,
    rate_by_track,
    render_markdown_report,
    render_summary,
    run_calibration,
)
from bargain_hunter.config import HotConfig, HotTier, ScoringConfig


def _sent(deal_key: str, sent_at: datetime, **kw) -> SentRecord:
    defaults = dict(
        subscriber_email="a@example.com",
        track="hot",
        price=None,
        discount_pct=None,
        votes_pos=10,
    )
    defaults.update(kw)
    return SentRecord(deal_key=deal_key, sent_at=sent_at, **defaults)


def _fb(deal_key: str, positive: bool, at: datetime, **kw) -> FeedbackRecord:
    defaults = dict(subscriber_email="a@example.com")
    defaults.update(kw)
    return FeedbackRecord(deal_key=deal_key, positive=positive, at=at, **defaults)


def _row(**kw) -> ObservationRow:
    defaults = dict(
        ts="2026-01-01T00:00:00+00:00",
        deal_key="ozbargain:x",
        title="t",
        votes_pos=20,
        n_snapshots=2,
        vote_velocity=0.0,
    )
    defaults.update(kw)
    return ObservationRow(**defaults)


# ---------------------------------------------------------------------------
# deal_source / join
# ---------------------------------------------------------------------------


def test_deal_source_parses_prefix():
    assert deal_source("ozbargain:123") == "ozbargain"
    assert deal_source("camelcamelcamel:B0AB") == "camelcamelcamel"
    assert deal_source("no-colon-here") == "unknown"


def test_latest_sent_by_deal_picks_most_recent():
    older = _sent("ozbargain:A", datetime(2026, 1, 1, tzinfo=UTC), votes_pos=5)
    newer = _sent("ozbargain:A", datetime(2026, 1, 2, tzinfo=UTC), votes_pos=50)
    latest = latest_sent_by_deal([older, newer])
    assert latest["ozbargain:A"].votes_pos == 50


def test_latest_observation_by_deal_picks_most_recent_ts():
    early = _row(deal_key="ozbargain:A", ts="2026-01-01T00:00:00+00:00", vote_velocity=1.0)
    late = _row(deal_key="ozbargain:A", ts="2026-01-02T00:00:00+00:00", vote_velocity=9.0)
    latest = latest_observation_by_deal([early, late])
    assert latest["ozbargain:A"].vote_velocity == 9.0


def test_join_feedback_pools_by_deal_key_and_drops_unmatched():
    sent = [
        _sent(
            "ozbargain:A",
            datetime(2026, 1, 1, tzinfo=UTC),
            track="hot",
            votes_pos=30,
            discount_pct=25.0,
        )
    ]
    feedback = [
        _fb("ozbargain:A", True, datetime(2026, 1, 1, 1, tzinfo=UTC)),
        _fb("ozbargain:A", False, datetime(2026, 1, 1, 2, tzinfo=UTC)),
        _fb("ozbargain:never-sent", True, datetime(2026, 1, 1, tzinfo=UTC)),
    ]
    joined = join_feedback(sent, feedback, tier_by_deal_key={"ozbargain:A": "good"})
    assert len(joined) == 2
    assert {j.positive for j in joined} == {True, False}
    assert all(j.tier == "good" and j.source == "ozbargain" and j.track == "hot" for j in joined)


def test_join_feedback_falls_back_to_observation_fields_when_sent_log_missing_them():
    sent = [_sent("ozbargain:A", datetime(2026, 1, 1, tzinfo=UTC), discount_pct=None)]
    feedback = [_fb("ozbargain:A", True, datetime(2026, 1, 1, 1, tzinfo=UTC))]
    obs = {"ozbargain:A": _row(deal_key="ozbargain:A", discount_percent=42.0, vote_velocity=3.5)}
    joined = join_feedback(sent, feedback, {}, obs_by_deal_key=obs)
    assert joined[0].discount_pct == 42.0
    assert joined[0].vote_velocity == 3.5
    assert joined[0].tier is None  # no tier map entry for this deal


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------


def _joined(deal_key, source, track, tier, positive, **kw) -> JoinedFeedback:
    defaults = dict(
        price=None, discount_pct=None, votes_pos=10, vote_velocity=None, comment_velocity=None
    )
    defaults.update(kw)
    return JoinedFeedback(
        deal_key=deal_key, source=source, track=track, tier=tier, positive=positive, **defaults
    )


def test_rate_by_tier_track_source():
    joined = [
        _joined("ozbargain:A", "ozbargain", "hot", "good", True),
        _joined("ozbargain:B", "ozbargain", "hot", "good", False),
        _joined("camelcamelcamel:C", "camelcamelcamel", "watch", "great", True),
    ]

    by_tier = rate_by_tier(joined)
    assert by_tier["good"].n == 2
    assert by_tier["good"].rate == 0.5
    assert by_tier["great"].rate == 1.0

    by_track = rate_by_track(joined)
    assert by_track["hot"].n == 2
    assert by_track["watch"].n == 1

    by_source = rate_by_source(joined)
    assert by_source["ozbargain"].n == 2
    assert by_source["camelcamelcamel"].n == 1


def test_rate_cell_handles_zero_n():
    cell = RateCell(n=0, positive=0)
    assert cell.rate is None


def test_distribution_comparison_means_and_missing_values():
    joined = [
        _joined(
            "k1", "ozbargain", "hot", "good", True,
            discount_pct=30.0, vote_velocity=5.0, votes_pos=20,
        ),
        _joined(
            "k2", "ozbargain", "hot", "good", True,
            discount_pct=None, vote_velocity=3.0, votes_pos=10,
        ),
        _joined(
            "k3", "ozbargain", "hot", "good", False,
            discount_pct=10.0, vote_velocity=None, votes_pos=5,
        ),
    ]
    dist = distribution_comparison(joined)
    assert dist["positive"]["n"] == 2
    assert dist["positive"]["mean_votes_pos"] == 15.0
    assert dist["positive"]["mean_vote_velocity"] == 4.0
    assert dist["positive"]["mean_discount_pct"] == 30.0  # only k1 has a value
    assert dist["negative"]["n"] == 1
    assert dist["negative"]["mean_vote_velocity"] is None


# ---------------------------------------------------------------------------
# grid search
# ---------------------------------------------------------------------------


def _hot_cfg() -> ScoringConfig:
    hot = HotConfig(
        min_votes_gain_per_window=15,
        early_burst_min_votes=25,
        neg_vote_penalty_weight=0.5,
        age_penalty_half_life_hours=12.0,
        comment_velocity_weight=0.0,
        tiers=[HotTier(name="good", min_score=1.5), HotTier(name="great", min_score=4.0)],
    )
    return ScoringConfig(hot=hot)


def test_grid_search_raising_threshold_can_exclude_a_negative_and_improve_rate():
    cfg = _hot_cfg()
    ts = "2026-01-01T00:00:00+00:00"
    # score ~= vote_velocity/15 + log1p(votes_pos)/log1p(25); both fire "good"
    # under the unmodified config (score >= 1.5, < 4.0).
    # weak scores ~1.934, strong ~2.601
    weak = _row(deal_key="ozbargain:weak", ts=ts, votes_pos=20, vote_velocity=15.0)
    strong = _row(deal_key="ozbargain:strong", ts=ts, votes_pos=20, vote_velocity=25.0)
    rows = [weak, strong]

    sent = [
        _sent("ozbargain:weak", datetime(2026, 1, 1, tzinfo=UTC)),
        _sent("ozbargain:strong", datetime(2026, 1, 1, tzinfo=UTC)),
    ]
    feedback = [
        _fb("ozbargain:weak", False, datetime(2026, 1, 1, 1, tzinfo=UTC)),
        _fb("ozbargain:strong", True, datetime(2026, 1, 1, 1, tzinfo=UTC)),
    ]
    tier_by_key = {"ozbargain:weak": "good", "ozbargain:strong": "good"}
    joined = join_feedback(sent, feedback, tier_by_key)
    assert rate_by_tier(joined)["good"].rate == 0.5

    suggestions = grid_search_thresholds(rows, cfg, joined, deltas=(0.5,), min_n=1)
    good_raise = next(s for s in suggestions if s.tier == "good" and s.delta == 0.5)
    # Raising good's min_score by 0.5 (to 2.0) excludes "weak" (score ~1.93,
    # now below threshold) but keeps "strong" (score ~2.60) — so the
    # candidate 👍-rate among the single remaining deal is 100%.
    assert good_raise.n == 1
    assert good_raise.candidate_positive_rate == 1.0
    assert good_raise.baseline_positive_rate == 0.5
    assert "would improve" in good_raise.note


def test_grid_search_flags_insufficient_data_below_min_n():
    cfg = _hot_cfg()
    ts = "2026-01-01T00:00:00+00:00"
    row = _row(deal_key="ozbargain:only", ts=ts, votes_pos=20, vote_velocity=25.0)
    sent = [_sent("ozbargain:only", datetime(2026, 1, 1, tzinfo=UTC))]
    feedback = [_fb("ozbargain:only", True, datetime(2026, 1, 1, 1, tzinfo=UTC))]
    joined = join_feedback(sent, feedback, {"ozbargain:only": "good"})

    suggestions = grid_search_thresholds([row], cfg, joined, deltas=(0.5,), min_n=20)
    good_raise = next(s for s in suggestions if s.tier == "good" and s.delta == 0.5)
    assert good_raise.candidate_positive_rate is None
    assert "insufficient data" in good_raise.note


def test_grid_search_lowering_threshold_reports_volume_only_never_a_rate():
    cfg = _hot_cfg()
    ts = "2026-01-01T00:00:00+00:00"
    # A deal that currently falls just short of "good" (score < 1.5) — lowering
    # the threshold by 0.5 (to 1.0) should pull it in, but with no feedback.
    below_threshold = _row(deal_key="ozbargain:below", ts=ts, votes_pos=20, vote_velocity=8.0)
    rows = [below_threshold]
    suggestions = grid_search_thresholds(rows, cfg, joined=[], deltas=(-0.5,), min_n=1)
    good_lower = next(s for s in suggestions if s.tier == "good" and s.delta == -0.5)
    assert good_lower.direction == "lower"
    assert good_lower.candidate_positive_rate is None
    assert good_lower.n == 1
    assert "cannot be estimated" in good_lower.note


# ---------------------------------------------------------------------------
# rendering (smoke tests)
# ---------------------------------------------------------------------------


def _sample_report() -> CalibrationReport:
    return CalibrationReport(
        generated_at=datetime(2026, 7, 6, 0, 0, tzinfo=UTC),
        lookback_days=14,
        sent_count=10,
        feedback_count=4,
        joined_count=4,
        rate_by_tier=rate_by_tier(
            [
                _joined("k1", "ozbargain", "hot", "good", True),
                _joined("k2", "ozbargain", "hot", "good", False),
            ]
        ),
        rate_by_track={"hot": RateCell(n=2, positive=1)},
        rate_by_source={"ozbargain": RateCell(n=2, positive=1)},
        distribution=distribution_comparison(
            [
                _joined("k1", "ozbargain", "hot", "good", True, votes_pos=10, vote_velocity=2.0),
                _joined("k2", "ozbargain", "hot", "good", False, votes_pos=5, vote_velocity=1.0),
            ]
        ),
        suggestions=[],
    )


def test_render_markdown_report_smoke():
    output = render_markdown_report(_sample_report())
    assert "# Bargain Hunter calibration report" in output
    assert "## 👍-rate by hot tier" in output
    assert "## 👍-rate by track" in output
    assert "## 👍-rate by source" in output
    assert "## Distribution: 👍 vs 👎 deals" in output
    assert "## Suggested threshold adjustments" in output
    assert "never" in output.lower()  # advisory-only caveat present


def test_render_summary_smoke():
    output = render_summary(_sample_report())
    assert "calibration summary" in output
    assert "👍-rate by tier" in output


# ---------------------------------------------------------------------------
# graceful degradation without Notion credentials
# ---------------------------------------------------------------------------


def test_run_calibration_skips_gracefully_without_notion_credentials(monkeypatch, tmp_path, caplog):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_SENT_LOG_DB_ID", raising=False)
    monkeypatch.delenv("NOTION_FEEDBACK_DB_ID", raising=False)

    with caplog.at_level("WARNING"):
        report = run_calibration(obs_dir=tmp_path, report_dir=tmp_path / "calibration")

    assert report is None
    assert not (tmp_path / "calibration").exists()
    assert "NOTION_TOKEN" in caplog.text


def test_run_calibration_writes_dated_report_with_stubbed_notion(monkeypatch, tmp_path):
    """End-to-end through run_calibration with the Notion fetchers stubbed out
    (no network) — verifies the join, report write, and AET-dated filename."""
    import bargain_hunter.calibration as calibration

    monkeypatch.setenv("NOTION_TOKEN", "test-token")
    monkeypatch.setenv("NOTION_SENT_LOG_DB_ID", "sent-db")
    monkeypatch.setenv("NOTION_FEEDBACK_DB_ID", "fb-db")
    monkeypatch.setattr(calibration, "make_notion_client", lambda: object())

    now = datetime(2026, 7, 6, 2, 0, tzinfo=UTC)  # 12:00 AET on 2026-07-06
    sent = [_sent("ozbargain:A", datetime(2026, 7, 1, tzinfo=UTC), votes_pos=30)]
    feedback = [_fb("ozbargain:A", True, datetime(2026, 7, 2, tzinfo=UTC))]
    monkeypatch.setattr(calibration, "fetch_sent_log", lambda *a, **kw: sent)
    monkeypatch.setattr(calibration, "fetch_feedback", lambda *a, **kw: feedback)

    obs_dir = tmp_path / "observations"
    obs_dir.mkdir()
    row = _row(deal_key="ozbargain:A", ts="2026-07-01T00:00:00+00:00", vote_velocity=25.0)
    (obs_dir / "2026-07-01.jsonl").write_text(row.model_dump_json() + "\n", encoding="utf-8")

    report_dir = tmp_path / "calibration"
    report = run_calibration(obs_dir=obs_dir, report_dir=report_dir, now=now)

    assert report is not None
    assert report.joined_count == 1
    assert report.report_path == report_dir / "2026-07-06.md"
    content = report.report_path.read_text(encoding="utf-8")
    assert "# Bargain Hunter calibration report — 2026-07-06" in content
    assert "ozbargain" in content
