"""Tests for the price-rank signal (rank a deal vs its own price history)."""

import json
from datetime import UTC, datetime

from bargain_hunter.config import PriceHistoryConfig
from bargain_hunter.models import Deal
from bargain_hunter.price_history import (
    classify_price_rank,
    enrich_price_ranks,
    load_price_history,
)

CFG = PriceHistoryConfig(enabled=True, lookback_days=30, min_history_points=3, near_fraction=0.05)


def test_classify_needs_enough_history():
    assert classify_price_rank(100.0, [110.0, 120.0], CFG) is None  # only 2 points
    assert classify_price_rank(100.0, [], CFG) is None


def test_classify_lowest_low_typical_high():
    hist = [100.0, 110.0, 120.0, 130.0]  # lo=100, hi=130
    assert classify_price_rank(95.0, hist, CFG) == "lowest"
    assert classify_price_rank(100.0, hist, CFG) == "lowest"
    assert classify_price_rank(104.0, hist, CFG) == "low"       # within 5% of lo
    assert classify_price_rank(115.0, hist, CFG) == "typical"
    assert classify_price_rank(129.0, hist, CFG) == "high"      # within 5% of hi


def test_classify_zero_price_unranked():
    assert classify_price_rank(0.0, [10.0, 20.0, 30.0], CFG) is None


def _write_obs(obs_dir, date, rows):
    obs_dir.mkdir(parents=True, exist_ok=True)
    with (obs_dir / f"{date}.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def test_load_price_history_only_high_confidence(tmp_path):
    now = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
    _write_obs(
        tmp_path,
        "2026-07-30",
        [
            {"deal_key": "ozbargain:1", "price": 100.0, "price_confidence": "high"},
            {"deal_key": "ozbargain:1", "price": 999.0, "price_confidence": "low"},  # ignored
            {"deal_key": "ozbargain:2", "price": 50.0, "price_confidence": "high"},
            {"deal_key": "ozbargain:1", "price": None, "price_confidence": "high"},  # ignored
        ],
    )
    hist = load_price_history({"ozbargain:1"}, 30, now, obs_dir=tmp_path)
    assert hist == {"ozbargain:1": [100.0]}


def _hi(key, price):
    return {"deal_key": key, "price": price, "price_confidence": "high"}


def test_load_price_history_respects_lookback(tmp_path):
    now = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
    _write_obs(tmp_path, "2026-07-30", [_hi("k", 10.0)])
    _write_obs(tmp_path, "2026-06-01", [_hi("k", 5.0)])
    hist = load_price_history({"k"}, 7, now, obs_dir=tmp_path)  # 7d window excludes June
    assert hist == {"k": [10.0]}

def _deal(price, conf="high", key_id="1"):
    return Deal(
        source="ozbargain", deal_id=key_id, title="x", url="https://x/node/" + key_id,
        price=price, price_confidence=conf,
    )


def test_enrich_sets_rank_from_history(tmp_path, monkeypatch):
    import bargain_hunter.price_history as ph

    now = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
    _write_obs(
        tmp_path,
        "2026-07-30",
        [_hi("ozbargain:1", p) for p in (200, 210, 220)],
    )
    monkeypatch.setattr(ph, "DEFAULT_OBS_DIR", tmp_path)
    deal = _deal(190.0)
    enrich_price_ranks([deal], CFG, now)
    assert deal.price_rank == "lowest"
    assert deal.price_history_days == 30


def test_enrich_disabled_and_low_confidence_noop(tmp_path, monkeypatch):
    import bargain_hunter.price_history as ph

    now = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(ph, "DEFAULT_OBS_DIR", tmp_path)
    d1 = _deal(100.0)
    enrich_price_ranks([d1], PriceHistoryConfig(enabled=False), now)
    assert d1.price_rank is None
    d2 = _deal(100.0, conf="low")
    enrich_price_ranks([d2], CFG, now)  # low confidence never ranked
    assert d2.price_rank is None
