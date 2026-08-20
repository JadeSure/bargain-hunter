"""Tests for the OpenRouter token-price differ (llm_prices.py), no network."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from bargain_hunter.sources import llm_prices as mod
from bargain_hunter.sources.llm_prices import LlmPriceSource

FIXTURE = Path(__file__).parent / "fixtures" / "openrouter_models_sample.json"
NOW = datetime(2026, 8, 20, tzinfo=UTC)


def _raw_models() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["data"]


def _patch(monkeypatch, payload: dict, status: int = 200) -> None:
    def fake_get(url, **kwargs):
        return httpx.Response(status, json=payload)

    monkeypatch.setattr(mod.httpx, "get", fake_get)


def test_drop_at_or_above_threshold_detected(monkeypatch):
    _patch(monkeypatch, {"data": _raw_models()})
    previous = {"qwen/qwen3.8-27b": [0.0000006, 0.0000032]}

    deals, current = LlmPriceSource().check(previous, now=NOW)

    deal = next(d for d in deals if d.deal_id == "qwen-qwen3.8-27b")
    assert deal.source == "openrouter"
    assert deal.discount_percent == 25.0
    assert deal.price == pytest.approx(0.45)
    assert deal.was_price == pytest.approx(0.6)
    assert deal.currency == "USD"
    assert deal.price_confidence is None
    assert deal.posted_at == NOW
    assert "25% cheaper" in deal.title
    assert current["qwen/qwen3.8-27b"][0] == pytest.approx(0.00000045)


def test_drop_below_threshold_ignored(monkeypatch):
    priced_only = [m for m in _raw_models() if m["id"] != "nvidia/nemotron-3.5-lightning:free"]
    _patch(monkeypatch, {"data": priced_only})
    # (0.00000047 - 0.00000045) / 0.00000047 * 100 ~= 4.3%, below the 10% default
    previous = {"qwen/qwen3.8-27b": [0.00000047, 0.0000032]}

    deals, _ = LlmPriceSource().check(previous, now=NOW)

    assert deals == []


def test_new_priced_model_ignored(monkeypatch):
    """The anti-flood guard: an id absent from `previous` is a new model
    launch, not a price cut, unless it launched free (see the C1 test below)."""
    _patch(monkeypatch, {"data": _raw_models()})
    previous = {"qwen/qwen3.8-27b": [0.0000006, 0.0000032]}

    deals, current = LlmPriceSource().check(previous, now=NOW)

    assert "z-ai-glm-5.3" not in {d.deal_id for d in deals}
    assert "z-ai/glm-5.3" in current  # still tracked, so a future run can diff it


def test_new_free_model_emitted(monkeypatch):
    """Correction C1: a model launching at zero price is always an id absent
    from `previous`, so it must be caught before the absent-id guard above
    swallows it."""
    _patch(monkeypatch, {"data": _raw_models()})
    previous = {"qwen/qwen3.8-27b": [0.0000006, 0.0000032]}  # glm-5.3 & free model both "new"

    deals, _ = LlmPriceSource().check(previous, now=NOW)

    # sanitize() only replaces "/" and "~" — the ":free" suffix's colon stays.
    free = next(d for d in deals if d.deal_id == "nvidia-nemotron-3.5-lightning:free")
    assert "now free" in free.title
    assert free.discount_percent == 100.0
    assert free.price == 0.0
    assert free.currency == "USD"
    assert free.price_confidence is None


def test_empty_previous_snapshot_yields_zero_deals_but_seeds(monkeypatch):
    """Cold start (or a lost Actions cache) must seed silently — including for
    the zero-priced models the C1 free-branch would otherwise flag as "new"."""
    _patch(monkeypatch, {"data": _raw_models()})  # includes the zero-priced model

    deals, current = LlmPriceSource().check({}, now=NOW)

    assert deals == []
    assert "qwen/qwen3.8-27b" in current
    assert "z-ai/glm-5.3" in current
    assert current["nvidia/nemotron-3.5-lightning:free"] == (0.0, 0.0)


def test_malformed_pricing_skipped(monkeypatch):
    _patch(monkeypatch, {"data": _raw_models()})

    deals, current = LlmPriceSource().check({}, now=NOW)

    assert "test/malformed-pricing" not in current
    assert "test/missing-pricing" not in current
    assert not any(d.deal_id.startswith("test-") for d in deals)


def test_non_200_response_returns_empty_and_does_not_raise(monkeypatch):
    _patch(monkeypatch, {"data": _raw_models()}, status=503)
    previous = {"qwen/qwen3.8-27b": [0.0000006, 0.0000032]}

    deals, current = LlmPriceSource().check(previous, now=NOW)

    assert deals == []
    assert current is previous  # unchanged, not clobbered by a transient outage


def test_model_allowlist_filters_and_empty_allowlist_means_all(monkeypatch):
    _patch(monkeypatch, {"data": _raw_models()})
    previous = {
        "qwen/qwen3.8-27b": [0.0000006, 0.0000032],   # 25% drop
        "z-ai/glm-5.3": [0.0000020, 0.0000044],       # 30% drop
    }

    scoped, _ = LlmPriceSource(model_allowlist=["qwen/"]).check(previous, now=NOW)
    assert {d.deal_id for d in scoped} == {"qwen-qwen3.8-27b"}

    unscoped, _ = LlmPriceSource().check(previous, now=NOW)
    assert {"qwen-qwen3.8-27b", "z-ai-glm-5.3"} <= {d.deal_id for d in unscoped}
