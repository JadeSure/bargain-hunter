"""Tests for the onboarding program validator."""

import json
from pathlib import Path

from strategy_hunter.onboarding import validate_programs

VALID_PROGRAM = {
    "id": "cashrewards-au",
    "name": "Cashrewards",
    "category": "cashback_portal",
    "one_liner": "Australia's largest cashback portal.",
    "benefit": "Earn cashback at 2,000+ retailers.",
    "how_to_join": [
        {"order": 1, "action": "Sign up at cashrewards.com.au"},
    ],
    "sources": ["https://www.ozbargain.com.au/wiki/list_of_sign-up_bonuses"],
    "confidence": 0.8,
}


def _write(dir_: Path, name: str, data: dict) -> None:
    (dir_ / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_missing_dir_is_warning_not_error(tmp_path):
    result = validate_programs(tmp_path / "nope")
    assert result.ok
    assert result.warnings


def test_valid_program_passes(tmp_path):
    _write(tmp_path, "p1.json", VALID_PROGRAM)
    result = validate_programs(tmp_path)
    assert result.ok, result.errors
    assert result.valid_files == 1


def test_schema_violation_is_error(tmp_path):
    bad = {k: v for k, v in VALID_PROGRAM.items() if k != "name"}  # missing required
    _write(tmp_path, "bad.json", bad)
    result = validate_programs(tmp_path)
    assert not result.ok
    assert any("name" in e for e in result.errors)


def test_semantic_rules_flagged(tmp_path):
    p = dict(VALID_PROGRAM)
    p["id"] = "Not A Slug"
    p["how_to_join"] = []
    p["category"] = "nonsense"
    p["confidence"] = 1.5
    p["needs_referral"] = True
    p["referral_note"] = None
    _write(tmp_path, "x.json", p)
    result = validate_programs(tmp_path)
    joined = " ".join(result.errors)
    assert "kebab-case" in joined
    assert "how_to_join" in joined
    assert "category" in joined
    assert "confidence" in joined
    assert "referral_note" in joined


def test_duplicate_ids_flagged(tmp_path):
    _write(tmp_path, "a.json", VALID_PROGRAM)
    _write(tmp_path, "b.json", VALID_PROGRAM)
    result = validate_programs(tmp_path)
    assert any("duplicate id" in e for e in result.errors)
