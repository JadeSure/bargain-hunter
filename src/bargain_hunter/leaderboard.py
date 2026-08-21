"""Rates & prices leaderboard artifact: a small, purpose-built JSON snapshot
for the frontend's /rates page.

`data/deals_state.json` (feature_snapshots, see state.py) only ever stores
enough to detect a *change* -- a product UUID and two numbers -- because it
rides the pipeline's hot path and the Actions cache. It is not a leaderboard
row and must not be widened into one. This module owns a separate file
(`data/leaderboard.json`) with exactly what a leaderboard row needs: name,
brand, category, link.

bank_rates and openrouter poll on independent daily cadences (state.py's
due_for_fetch) and rarely land in the same pipeline run, so `update()` merges:
it only touches the section(s) passed in, leaving the other section (and its
own `_updated_at`) exactly as the last run that refreshed it left them. A
single shared timestamp would misrepresent whichever section didn't just run.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_PATH = Path("data/leaderboard.json")


def load(path: Path = DEFAULT_PATH) -> dict[str, Any]:
    """Read the artifact, or {} if missing/corrupt (cold start)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _llm_rows(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for model in models:
        model_id = model.get("id")
        pricing = model.get("pricing") or {}
        try:
            prompt = float(pricing.get("prompt"))
            completion = float(pricing.get("completion"))
        except (TypeError, ValueError):
            continue
        # OpenRouter's "-1" sentinel means variable/routed pricing, not a real
        # price (see llm_prices.check()) -- exclude it, but keep genuine free
        # (0.0) models so the board can show them.
        if not model_id or prompt < 0 or completion < 0:
            continue
        rows.append(
            {
                "id": model_id,
                "name": model.get("name") or model_id,
                "prompt_usd_per_token": prompt,
                "completion_usd_per_token": completion,
                "url": f"https://openrouter.ai/{model_id}",
            }
        )
    return rows


def update(
    *,
    bank_products: dict[str, dict[str, Any]] | None = None,
    llm_models: list[dict[str, Any]] | None = None,
    path: Path = DEFAULT_PATH,
    now: datetime | None = None,
) -> None:
    """Merge freshly-fetched section(s) into the committed leaderboard artifact.

    Pass `bank_products=src.next_leaderboard` and/or `llm_models=src.last_models`
    only for a source that actually ran this cycle; omitting a section (None)
    leaves it and its timestamp untouched.
    """
    if bank_products is None and llm_models is None:
        return
    now = now or datetime.now(UTC)
    payload = load(path)
    if bank_products is not None:
        payload["bank_products"] = bank_products
        payload["bank_products_updated_at"] = now.isoformat()
    if llm_models is not None:
        payload["llm_models"] = _llm_rows(llm_models)
        payload["llm_models_updated_at"] = now.isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Compact, not pretty-printed: ~600 rows/day committed to git, and repo
    # growth is a known problem here (same reasoning as observations' gzip).
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    log.info("leaderboard: wrote %s", path)
