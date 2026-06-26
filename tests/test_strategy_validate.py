"""Tests for the Stage 2 guide validator."""

import json
from pathlib import Path

from strategy_hunter.validate import validate_guides

VALID_GUIDE = {
    "id": "buy-macbook-au-cheap",
    "goal": "Buy a MacBook cheaply in Australia",
    "summary": "Stack discounted gift cards + cashback to save on a MacBook.",
    "techniques": ["discounted_giftcard", "cashback"],
    "steps": [
        {"order": 1, "action": "Buy discounted Apple gift cards", "technique": "discounted_giftcard"},
        {"order": 2, "action": "Place the order via a cashback portal", "technique": "cashback"},
    ],
    "sources": ["https://www.ozbargain.com.au/node/111111"],
    "confidence": 0.8,
}


def _write(dir_: Path, name: str, data: dict) -> None:
    (dir_ / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_missing_dir_is_warning_not_error(tmp_path):
    result = validate_guides(tmp_path / "nope")
    assert result.ok
    assert result.warnings


def test_valid_guide_passes(tmp_path):
    _write(tmp_path, "g1.json", VALID_GUIDE)
    result = validate_guides(tmp_path)
    assert result.ok, result.errors
    assert result.valid_files == 1


def test_schema_violation_is_error(tmp_path):
    bad = {k: v for k, v in VALID_GUIDE.items() if k != "goal"}  # missing required
    _write(tmp_path, "bad.json", bad)
    result = validate_guides(tmp_path)
    assert not result.ok
    assert any("goal" in e for e in result.errors)


def test_semantic_rules_flagged(tmp_path):
    g = dict(VALID_GUIDE)
    g["id"] = "Not A Slug"
    g["steps"] = []
    g["sources"] = []
    g["confidence"] = 1.5
    _write(tmp_path, "x.json", g)
    result = validate_guides(tmp_path)
    joined = " ".join(result.errors)
    assert "kebab-case" in joined
    assert "no steps" in joined
    assert "no sources" in joined or "cites no sources" in joined
    assert "confidence" in joined


def test_duplicate_ids_flagged(tmp_path):
    _write(tmp_path, "a.json", VALID_GUIDE)
    _write(tmp_path, "b.json", VALID_GUIDE)
    result = validate_guides(tmp_path)
    assert any("duplicate id" in e for e in result.errors)
