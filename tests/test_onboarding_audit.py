"""Tests for the onboarding catalog freshness audit."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from strategy_hunter.onboarding import audit_programs, render_issue_body

NOW = datetime(2026, 6, 1, tzinfo=UTC)

BASE = {
    "id": "shopback-au",
    "name": "ShopBack",
    "category": "cashback_portal",
    "one_liner": "Top AU cashback portal.",
    "benefit": "Cashback at thousands of retailers.",
    "how_to_join": [{"order": 1, "action": "Sign up"}],
}


def _write(dir_: Path, name: str, **over) -> None:
    (dir_ / name).write_text(json.dumps({**BASE, **over}, ensure_ascii=False), "utf-8")


def test_fresh_program_not_flagged(tmp_path):
    _write(tmp_path, "fresh.json", generated_at=(NOW - timedelta(days=10)).isoformat())
    r = audit_programs(tmp_path, now=NOW, max_age_days=90)
    assert r.total == 1 and r.fresh == 1 and not r.stale


def test_old_program_flagged(tmp_path):
    _write(tmp_path, "old.json", generated_at=(NOW - timedelta(days=120)).isoformat())
    r = audit_programs(tmp_path, now=NOW, max_age_days=90)
    assert len(r.flags) == 1 and r.flags[0].reason == "old"


def test_expired_program_flagged(tmp_path):
    _write(tmp_path, "exp.json",
           generated_at=NOW.isoformat(), valid_until=(NOW - timedelta(days=1)).isoformat())
    r = audit_programs(tmp_path, now=NOW, max_age_days=90)
    assert r.flags[0].reason == "expired"


def test_undated_program_flagged(tmp_path):
    _write(tmp_path, "nodate.json")
    r = audit_programs(tmp_path, now=NOW, max_age_days=90)
    assert r.flags[0].reason == "no_date"


def test_unreadable_file_reported_not_crash(tmp_path):
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    r = audit_programs(tmp_path, now=NOW, max_age_days=90)
    assert r.errors and r.total == 0


def test_missing_dir_is_clean(tmp_path):
    assert not audit_programs(tmp_path / "nope", now=NOW).stale


def test_issue_body_lists_flags(tmp_path):
    _write(tmp_path, "old.json", generated_at=(NOW - timedelta(days=200)).isoformat())
    r = audit_programs(tmp_path, now=NOW, max_age_days=90)
    body = render_issue_body(r, max_age_days=90)
    assert "shopback-au" in body and "1" in body
