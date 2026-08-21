"""Tests for the rates & prices leaderboard artifact writer (no network)."""

import json
from datetime import UTC, datetime
from pathlib import Path

from bargain_hunter import leaderboard as mod

NOW = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)


def test_load_missing_file_returns_empty_dict(tmp_path: Path):
    assert mod.load(tmp_path / "nope.json") == {}


def test_update_writes_bank_products_and_timestamp(tmp_path: Path):
    path = tmp_path / "leaderboard.json"
    rows = {
        "ING:abc": {
            "brand": "ING",
            "name": "ING Savings",
            "category": "TRANS_AND_SAVINGS_ACCOUNTS",
            "best_rate": 0.0535,
            "bonus_points": None,
            "url": "https://ing.com.au",
        }
    }

    mod.update(bank_products=rows, path=path, now=NOW)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["bank_products"] == rows
    assert payload["bank_products_updated_at"] == NOW.isoformat()
    assert "llm_models" not in payload


def test_update_only_touches_the_section_passed(tmp_path: Path):
    """bank_rates and openrouter poll independently -- writing one section must
    not blank out or re-stamp the other."""
    path = tmp_path / "leaderboard.json"
    mod.update(bank_products={"a": {"name": "A"}}, path=path, now=NOW)
    later = datetime(2026, 8, 21, 15, 0, tzinfo=UTC)

    mod.update(
        llm_models=[
            {
                "id": "x/y",
                "name": "X Y",
                "pricing": {"prompt": "0.000001", "completion": "0.000002"},
            }
        ],
        path=path,
        now=later,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["bank_products"] == {"a": {"name": "A"}}
    assert payload["bank_products_updated_at"] == NOW.isoformat()  # untouched
    assert payload["llm_models_updated_at"] == later.isoformat()
    assert payload["llm_models"][0]["id"] == "x/y"


def test_update_with_no_sections_is_a_noop(tmp_path: Path):
    path = tmp_path / "leaderboard.json"
    mod.update(path=path, now=NOW)
    assert not path.exists()


def test_llm_rows_excludes_variable_pricing_sentinel_but_keeps_free_models():
    models = [
        {"id": "openrouter/auto", "name": "Auto", "pricing": {"prompt": "-1", "completion": "-1"}},
        {
            "id": "vendor/free-model",
            "name": "Free Model",
            "pricing": {"prompt": "0", "completion": "0"},
        },
        {
            "id": "vendor/priced",
            "name": "Priced",
            "pricing": {"prompt": "0.000001", "completion": "0.000002"},
        },
        {"id": "vendor/malformed", "name": "Bad", "pricing": {"prompt": "nope", "completion": "0"}},
    ]

    rows = mod._llm_rows(models)

    ids = {r["id"] for r in rows}
    assert ids == {"vendor/free-model", "vendor/priced"}
    free = next(r for r in rows if r["id"] == "vendor/free-model")
    assert free["prompt_usd_per_token"] == 0.0
    assert free["url"] == "https://openrouter.ai/vendor/free-model"
    priced = next(r for r in rows if r["id"] == "vendor/priced")
    assert priced["prompt_usd_per_token"] == 0.000001
    assert priced["completion_usd_per_token"] == 0.000002
