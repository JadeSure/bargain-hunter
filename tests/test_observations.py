"""Tests for per-run feature logging used in threshold calibration."""

import json
from datetime import UTC, datetime, timedelta

from bargain_hunter.config import ScoringConfig
from bargain_hunter.models import Deal, DealSnapshot
from bargain_hunter.observations import ObservationLog, build_observation


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
    assert row["votes_pos"] == 20
    assert row["click_count"] == 15
    assert row["is_hot"] is True
    assert row["vote_velocity"] > 0
    assert row["click_velocity"] > 0
    assert "hot_score" in row
    assert 0 <= row["neg_ratio"] <= 1


def test_build_observation_records_hot_level():
    now = datetime.now(UTC)
    row = build_observation(
        _deal(), _snaps(now), ScoringConfig(), is_hot=True, level="great", now=now
    )
    assert row["hot_level"] == "great"
    # Level is optional; absent when not provided.
    row2 = build_observation(_deal(), _snaps(now), ScoringConfig(), is_hot=False, now=now)
    assert row2["hot_level"] is None


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
