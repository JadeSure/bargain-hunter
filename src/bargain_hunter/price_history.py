"""Price-rank signal — is a deal genuinely cheap, or just popular?

A "hot" verdict is social proof (lots of upvotes), not a value judgement: a deal
can trend while still being priced above its own recent norm (retailers inflate
then "discount"). This module ranks a deal's current price against its *own*
history of high-confidence prices, read back from the observation JSONL files the
pipeline already writes (``data/observations/<AET-date>.jsonl``) — so it needs no
new storage and improves as history accrues.

Only high-confidence prices are considered (heuristic OzBargain title prices at
low confidence would poison the history). A deal is left unranked until it has at
least ``min_history_points`` prior points, so we never assert "lowest in 30d" on
a single sighting.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import PriceHistoryConfig
from .models import Deal
from .observations import DEFAULT_OBS_DIR

log = logging.getLogger(__name__)

_AET = ZoneInfo("Australia/Sydney")


def load_price_history(
    keys: Iterable[str],
    lookback_days: int,
    now: datetime,
    obs_dir: Path | None = None,
) -> dict[str, list[float]]:
    """Return {deal_key: [high-confidence prices]} from recent observation files.

    Reads the last ``lookback_days`` AET-dated observation files and collects
    every ``price`` recorded at ``price_confidence == "high"`` for the requested
    keys. Missing/corrupt files and malformed rows are skipped, never fatal.
    """
    obs_dir = obs_dir or DEFAULT_OBS_DIR
    wanted = set(keys)
    history: dict[str, list[float]] = {}
    if not wanted or not obs_dir.exists():
        return history
    today = now.astimezone(_AET).date()
    for offset in range(lookback_days + 1):
        date = today - timedelta(days=offset)
        path = obs_dir / f"{date.isoformat()}.jsonl"
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            key = row.get("deal_key")
            if key not in wanted or row.get("price_confidence") != "high":
                continue
            price = row.get("price")
            if isinstance(price, int | float) and price > 0:
                history.setdefault(key, []).append(float(price))
    return history


def classify_price_rank(
    current: float, history: list[float], cfg: PriceHistoryConfig
) -> str | None:
    """Rank ``current`` against prior ``history`` prices.

    Returns ``"lowest"`` / ``"low"`` / ``"typical"`` / ``"high"``, or ``None`` when
    there isn't enough history (``< min_history_points``) to judge.
    """
    if current <= 0 or len(history) < cfg.min_history_points:
        return None
    lo, hi = min(history), max(history)
    near = cfg.near_fraction
    if current <= lo:
        return "lowest"
    if current <= lo * (1 + near):
        return "low"
    if hi > lo and current >= hi * (1 - near):
        return "high"
    return "typical"


def enrich_price_ranks(deals: list[Deal], cfg: PriceHistoryConfig, now: datetime) -> None:
    """Populate ``price_rank`` / ``price_history_days`` in place for ranked deals.

    No-op when disabled. Only deals carrying a high-confidence price are ranked.
    """
    if not cfg.enabled:
        return
    rankable = [d for d in deals if d.price and d.price > 0 and d.price_confidence == "high"]
    if not rankable:
        return
    history = load_price_history((d.key for d in rankable), cfg.lookback_days, now)
    for deal in rankable:
        past = history.get(deal.key, [])
        rank = classify_price_rank(deal.price, past, cfg)
        if rank is not None:
            deal.price_rank = rank
            deal.price_history_days = cfg.lookback_days
