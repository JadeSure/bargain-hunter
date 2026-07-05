"""Tests for the Stage 2 guide freshness audit."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from strategy_hunter.audit import audit_guides, render_issue_body

NOW = datetime(2026, 7, 6, tzinfo=UTC)

BASE = {
    "id": "buy-macbook-au-cheap",
    "goal": "Buy a MacBook cheaply in Australia",
    "summary": "Stack discounted gift cards + cashback to save on a MacBook.",
    "techniques": ["discounted_giftcard"],
    "steps": [{"order": 1, "action": "Buy discounted gift cards"}],
    "sources": ["https://www.ozbargain.com.au/node/111111"],
}


def _write_guide(dir_: Path, name: str, **over) -> None:
    (dir_ / name).write_text(json.dumps({**BASE, **over}, ensure_ascii=False), "utf-8")


def _write_raw(dir_: Path, source: str, post_id: str, url: str) -> None:
    (dir_ / source).mkdir(parents=True, exist_ok=True)
    (dir_ / source / f"{post_id}.json").write_text(json.dumps({"url": url}), "utf-8")


def test_fresh_guide_not_flagged(tmp_path):
    guides = tmp_path / "guides"
    guides.mkdir()
    raw = tmp_path / "raw"
    _write_raw(raw, "ozbargain_forum", "111111", "https://www.ozbargain.com.au/node/111111")
    _write_guide(guides, "g.json", generated_at=(NOW - timedelta(days=5)).isoformat())
    result = audit_guides(guides, raw, now=NOW, staleness_days=30)
    assert result.total == 1 and result.fresh == 1 and not result.stale


def test_old_guide_flagged(tmp_path):
    guides = tmp_path / "guides"
    guides.mkdir()
    _write_guide(guides, "g.json", generated_at=(NOW - timedelta(days=45)).isoformat())
    result = audit_guides(guides, tmp_path / "raw", now=NOW, staleness_days=30)
    assert len(result.flags) == 1
    assert result.flags[0].reason == "old"


def test_expired_guide_flagged(tmp_path):
    guides = tmp_path / "guides"
    guides.mkdir()
    _write_guide(
        guides, "g.json",
        generated_at=NOW.isoformat(),
        valid_until=(NOW - timedelta(days=1)).isoformat(),
    )
    result = audit_guides(guides, tmp_path / "raw", now=NOW, staleness_days=30)
    assert result.flags[0].reason == "expired"


def test_undated_guide_flagged(tmp_path):
    guides = tmp_path / "guides"
    guides.mkdir()
    _write_guide(guides, "g.json")
    result = audit_guides(guides, tmp_path / "raw", now=NOW, staleness_days=30)
    assert result.flags[0].reason == "no_date"


def test_all_sources_pruned_flagged(tmp_path):
    guides = tmp_path / "guides"
    guides.mkdir()
    raw = tmp_path / "raw"
    # a raw corpus that exists but doesn't contain this guide's cited source
    _write_raw(raw, "ozbargain_forum", "999999", "https://www.ozbargain.com.au/node/999999")
    _write_guide(guides, "g.json", generated_at=(NOW - timedelta(days=1)).isoformat())
    result = audit_guides(guides, raw, now=NOW, staleness_days=30)
    assert result.flags[0].reason == "sources_pruned"


def test_missing_raw_dir_does_not_flag_pruned(tmp_path):
    guides = tmp_path / "guides"
    guides.mkdir()
    _write_guide(guides, "g.json", generated_at=(NOW - timedelta(days=1)).isoformat())
    result = audit_guides(guides, tmp_path / "nope", now=NOW, staleness_days=30)
    assert not result.stale


def test_unreadable_file_reported_not_crash(tmp_path):
    guides = tmp_path / "guides"
    guides.mkdir()
    (guides / "bad.json").write_text("{not json", encoding="utf-8")
    result = audit_guides(guides, tmp_path / "raw", now=NOW, staleness_days=30)
    assert result.errors and result.total == 0


def test_missing_guides_dir_is_clean(tmp_path):
    assert not audit_guides(tmp_path / "nope", tmp_path / "raw", now=NOW).stale


def test_issue_body_lists_flags(tmp_path):
    guides = tmp_path / "guides"
    guides.mkdir()
    _write_guide(guides, "g.json", generated_at=(NOW - timedelta(days=200)).isoformat())
    result = audit_guides(guides, tmp_path / "raw", now=NOW, staleness_days=30)
    body = render_issue_body(result, staleness_days=30)
    assert "buy-macbook-au-cheap" in body
    assert "1" in body
