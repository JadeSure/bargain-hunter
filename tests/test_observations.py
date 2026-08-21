"""Tests for per-run feature logging used in threshold calibration."""

import gzip
import json
from datetime import UTC, datetime, timedelta

from bargain_hunter.config import ScoringConfig
from bargain_hunter.models import Deal, DealSnapshot
from bargain_hunter.observations import (
    ObservationLog,
    build_observation,
    compress_completed,
    file_date,
    maintain,
    prune_old,
)


def _deal(**kw) -> Deal:
    defaults = dict(
        source="ozbargain",
        deal_id="1",
        title="Widget $10",
        url="https://ozbargain.com.au/node/1",
        votes_pos=20,
        votes_neg=2,
        comment_count=4,
        click_count=15,
        posted_at=datetime.now(UTC) - timedelta(hours=1),
    )
    defaults.update(kw)
    return Deal(**defaults)


def _snaps(now: datetime) -> list[DealSnapshot]:
    base = now - timedelta(minutes=30)
    return [
        DealSnapshot(ts=base, votes_pos=0, votes_neg=0, comment_count=0, click_count=0),
        DealSnapshot(ts=now, votes_pos=20, votes_neg=2, comment_count=4, click_count=15),
    ]


def test_build_observation_has_expected_fields():
    now = datetime.now(UTC)
    row = build_observation(_deal(), _snaps(now), ScoringConfig(), is_hot=True, now=now)
    assert row["deal_key"] == "ozbargain:1"
    assert row["url"] == "https://ozbargain.com.au/node/1"
    assert row["votes_pos"] == 20
    assert row["click_count"] == 15
    assert row["is_hot"] is True
    assert row["vote_velocity"] > 0
    assert row["click_velocity"] > 0
    assert "hot_score" in row
    assert 0 <= row["neg_ratio"] <= 1


def test_build_observation_carries_description_through():
    now = datetime.now(UTC)
    row = build_observation(
        _deal(description="A widget that does things."),
        _snaps(now),
        ScoringConfig(),
        is_hot=True,
        now=now,
    )
    assert row["description"] == "A widget that does things."

    row_absent = build_observation(_deal(), _snaps(now), ScoringConfig(), is_hot=True, now=now)
    assert row_absent["description"] is None


def test_build_observation_caps_description_length():
    now = datetime.now(UTC)
    row = build_observation(
        _deal(description="x" * 1000), _snaps(now), ScoringConfig(), is_hot=True, now=now
    )
    assert len(row["description"]) == 300


def test_build_observation_records_hot_level():
    now = datetime.now(UTC)
    row = build_observation(
        _deal(), _snaps(now), ScoringConfig(), is_hot=True, level="great", now=now
    )
    assert row["hot_level"] == "great"
    # Level is optional; absent when not provided.
    row2 = build_observation(_deal(), _snaps(now), ScoringConfig(), is_hot=False, now=now)
    assert row2["hot_level"] is None


def test_build_observation_includes_adaptive_baseline_fields():
    now = datetime.now(UTC)
    row = build_observation(
        _deal(),
        _snaps(now),
        ScoringConfig(),
        is_hot=True,
        now=now,
        heat_ratio=1.5,
        site_velocity_index=12.3456,
    )
    assert row["heat_ratio"] == 1.5
    assert row["site_velocity_index"] == 12.3456

    # Defaults are behaviour-identical to pre-adaptive-baseline rows.
    row_default = build_observation(_deal(), _snaps(now), ScoringConfig(), is_hot=True, now=now)
    assert row_default["heat_ratio"] == 1.0
    assert row_default["site_velocity_index"] is None


def test_observation_log_writes_jsonl(tmp_path):
    now = datetime.now(UTC)
    obs = ObservationLog(obs_dir=tmp_path)
    obs.add(build_observation(_deal(), _snaps(now), ScoringConfig(), is_hot=False, now=now))
    obs.flush(now)

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    rows = [json.loads(line) for line in files[0].read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["deal_key"] == "ozbargain:1"


def test_file_date_handles_jsonl_and_gz(tmp_path):
    assert file_date(tmp_path / "2026-07-02.jsonl").isoformat() == "2026-07-02"
    assert file_date(tmp_path / "2026-07-02.jsonl.gz").isoformat() == "2026-07-02"
    assert file_date(tmp_path / "not-a-date.jsonl") is None


def test_compress_completed_gzips_past_days_only(tmp_path):
    # AET "today" for a fixed UTC now.
    now = datetime(2026, 7, 3, 2, 0, tzinfo=UTC)  # 12:00 AET on 2026-07-03
    (tmp_path / "2026-07-01.jsonl").write_text('{"a":1}\n', encoding="utf-8")
    (tmp_path / "2026-07-03.jsonl").write_text('{"b":2}\n', encoding="utf-8")

    created = compress_completed(tmp_path, now)

    assert [p.name for p in created] == ["2026-07-01.jsonl.gz"]
    assert not (tmp_path / "2026-07-01.jsonl").exists()  # original removed
    assert (tmp_path / "2026-07-03.jsonl").exists()  # today's kept as-is
    with gzip.open(tmp_path / "2026-07-01.jsonl.gz", "rt", encoding="utf-8") as f:
        assert f.read() == '{"a":1}\n'


def test_prune_old_removes_files_past_retention(tmp_path):
    now = datetime(2026, 7, 30, 2, 0, tzinfo=UTC)
    (tmp_path / "2026-06-01.jsonl.gz").write_bytes(b"old")
    (tmp_path / "2026-07-29.jsonl").write_text("recent\n", encoding="utf-8")

    removed = prune_old(tmp_path, now, retention_days=10)

    assert [p.name for p in removed] == ["2026-06-01.jsonl.gz"]
    assert (tmp_path / "2026-07-29.jsonl").exists()


def test_maintain_compresses_then_prunes(tmp_path):
    now = datetime(2026, 7, 30, 2, 0, tzinfo=UTC)
    (tmp_path / "2026-06-01.jsonl").write_text("ancient\n", encoding="utf-8")
    (tmp_path / "2026-07-29.jsonl").write_text("recent\n", encoding="utf-8")
    (tmp_path / "2026-07-30.jsonl").write_text("today\n", encoding="utf-8")

    maintain(tmp_path, now, retention_days=10)

    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["2026-07-29.jsonl.gz", "2026-07-30.jsonl"]
