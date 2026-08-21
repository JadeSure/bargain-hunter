"""Tests for the free-LLM-tier differ (free_llm.py), no network."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from bargain_hunter.sources import free_llm as mod
from bargain_hunter.sources.free_llm import FreeLlmSource

FIXTURE = Path(__file__).parent / "fixtures" / "free_llm_data.json"
NOW = datetime(2026, 8, 21, tzinfo=UTC)


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _patch(monkeypatch, payload: dict, status: int = 200) -> None:
    def fake_get(url, **kwargs):
        return httpx.Response(status, json=payload)

    monkeypatch.setattr(mod.httpx, "get", fake_get)


def test_cold_start_seeds_silently(monkeypatch):
    _patch(monkeypatch, _payload())

    deals, current = FreeLlmSource().check({}, now=NOW)

    assert deals == []
    assert current["Groq::openai/gpt-oss-120b"] == {
        "context": "131K",
        "rateLimit": "30 RPM, 1,000 RPD",
    }
    assert current[mod.LAST_UPDATED_KEY] == "2026-08-21"
    # malformed entries never make it into the snapshot
    assert not any("no id model" in k for k in current)
    assert "orphan-model" not in json.dumps(current)  # nameless provider is skipped entirely


def test_rate_limit_change_emits_one_deal_with_both_values(monkeypatch):
    _patch(monkeypatch, _payload())
    previous = {
        mod.LAST_UPDATED_KEY: "2026-08-20",
        "Groq::openai/gpt-oss-120b": {"context": "131K", "rateLimit": "15 RPM, 500 RPD"},
    }

    deals, current = FreeLlmSource().check(previous, now=NOW)

    matches = [d for d in deals if d.deal_id == "Groq-openai-gpt-oss-120b"]
    assert len(matches) == 1
    deal = matches[0]
    assert deal.source == "free_llm"
    assert "15 RPM, 500 RPD" in deal.title
    assert "30 RPM, 1,000 RPD" in deal.title
    assert deal.url == "https://console.groq.com/keys"
    assert deal.currency == "USD"
    assert deal.price is None
    assert deal.discount_percent is None
    assert deal.posted_at == NOW
    assert current["Groq::openai/gpt-oss-120b"]["rateLimit"] == "30 RPM, 1,000 RPD"


def test_context_change_emits_one_deal_with_both_values(monkeypatch):
    _patch(monkeypatch, _payload())
    previous = {
        mod.LAST_UPDATED_KEY: "2026-08-20",
        "Groq::openai/gpt-oss-120b": {"context": "64K", "rateLimit": "30 RPM, 1,000 RPD"},
        "Groq::llama-3.3-70b-versatile": {"context": "128K", "rateLimit": "30 RPM, 14,400 RPD"},
        "Google Gemini::gemini-2.5-flash": {
            "context": "1M",
            "rateLimit": "10 RPM, 250,000 TPM, 250 RPD",
        },
    }

    deals, _ = FreeLlmSource().check(previous, now=NOW)

    assert len(deals) == 1
    assert "64K" in deals[0].title
    assert "131K" in deals[0].title


def test_both_rate_limit_and_context_change_fold_into_one_deal(monkeypatch):
    _patch(monkeypatch, _payload())
    previous = {
        mod.LAST_UPDATED_KEY: "2026-08-20",
        "Groq::openai/gpt-oss-120b": {"context": "64K", "rateLimit": "15 RPM, 500 RPD"},
    }

    deals, _ = FreeLlmSource().check(previous, now=NOW)

    matches = [d for d in deals if d.deal_id == "Groq-openai-gpt-oss-120b"]
    assert len(matches) == 1
    assert "限额" in matches[0].title
    assert "上下文" in matches[0].title


def test_newly_added_model_emits_one_deal(monkeypatch):
    _patch(monkeypatch, _payload())
    previous = {
        mod.LAST_UPDATED_KEY: "2026-08-20",
        "Groq::llama-3.3-70b-versatile": {"context": "128K", "rateLimit": "30 RPM, 14,400 RPD"},
        "Google Gemini::gemini-2.5-flash": {
            "context": "1M",
            "rateLimit": "10 RPM, 250,000 TPM, 250 RPD",
        },
    }

    deals, current = FreeLlmSource().check(previous, now=NOW)

    matches = [d for d in deals if d.deal_id == "Groq-openai-gpt-oss-120b"]
    assert len(matches) == 1
    assert "新增免费模型" in matches[0].title
    assert "openai/gpt-oss-120b" in matches[0].title
    assert "131K" in matches[0].title
    assert "30 RPM, 1,000 RPD" in matches[0].title
    assert current["Groq::openai/gpt-oss-120b"]["rateLimit"] == "30 RPM, 1,000 RPD"


def test_removed_model_emits_no_deal_but_is_logged(monkeypatch, caplog):
    _patch(monkeypatch, _payload())
    previous = {
        mod.LAST_UPDATED_KEY: "2026-08-20",
        "Groq::openai/gpt-oss-120b": {"context": "131K", "rateLimit": "30 RPM, 1,000 RPD"},
        "Groq::llama-3.3-70b-versatile": {"context": "128K", "rateLimit": "30 RPM, 14,400 RPD"},
        "Google Gemini::gemini-2.5-flash": {
            "context": "1M",
            "rateLimit": "10 RPM, 250,000 TPM, 250 RPD",
        },
        "Retired Provider::some-model": {"context": "8K", "rateLimit": "5 RPM"},
    }

    with caplog.at_level("INFO", logger="bargain_hunter.sources.free_llm"):
        deals, current = FreeLlmSource().check(previous, now=NOW)

    assert deals == []
    assert "Retired Provider::some-model" not in current
    assert any("dropped from the upstream list" in r.message for r in caplog.records)


def test_unchanged_payload_emits_nothing(monkeypatch):
    payload = _payload()
    _patch(monkeypatch, payload)
    _, snapshot = FreeLlmSource().check({}, now=NOW)

    deals, _ = FreeLlmSource().check(snapshot, now=NOW)

    assert deals == []


def test_last_updated_round_trips_into_the_snapshot(monkeypatch):
    _patch(monkeypatch, _payload())

    _, current = FreeLlmSource().check({}, now=NOW)

    assert current[mod.LAST_UPDATED_KEY] == "2026-08-21"


def test_fetch_failure_returns_previous_unchanged(monkeypatch, caplog):
    _patch(monkeypatch, {}, status=503)
    previous = {
        mod.LAST_UPDATED_KEY: "2026-08-20",
        "Groq::openai/gpt-oss-120b": {"context": "131K", "rateLimit": "30 RPM, 1,000 RPD"},
    }

    with caplog.at_level("ERROR", logger="bargain_hunter.sources.free_llm"):
        deals, current = FreeLlmSource().check(previous, now=NOW)

    assert deals == []
    assert current is previous
    assert any("non-200" in r.message for r in caplog.records)


def test_malformed_json_body_returns_previous_unchanged(monkeypatch, caplog):
    def fake_get(url, **kwargs):
        return httpx.Response(200, text="not json")

    monkeypatch.setattr(mod.httpx, "get", fake_get)
    previous = {mod.LAST_UPDATED_KEY: "2026-08-20"}

    with caplog.at_level("ERROR", logger="bargain_hunter.sources.free_llm"):
        deals, current = FreeLlmSource().check(previous, now=NOW)

    assert deals == []
    assert current is previous
    assert any("malformed response body" in r.message for r in caplog.records)


def test_unexpected_shape_returns_previous_unchanged(monkeypatch):
    _patch(monkeypatch, {"nope": "not the expected shape"})
    previous = {mod.LAST_UPDATED_KEY: "2026-08-20"}

    deals, current = FreeLlmSource().check(previous, now=NOW)

    assert deals == []
    assert current is previous


def test_redirect_is_followed_and_logged(monkeypatch):
    payload = _payload()

    def fake_get(url, **kwargs):
        redirect = httpx.Response(302, request=httpx.Request("GET", url))
        return httpx.Response(
            200, json=payload, request=httpx.Request("GET", url), history=[redirect]
        )

    monkeypatch.setattr(mod.httpx, "get", fake_get)

    deals, current = FreeLlmSource().check({}, now=NOW)

    assert deals == []
    assert current[mod.LAST_UPDATED_KEY] == "2026-08-21"


def test_snapshot_with_only_lastupdated_is_treated_as_cold_start(monkeypatch):
    """A non-empty snapshot holding no models is NOT a baseline.

    fetch() accepts `providers: []` as well-formed, which persists a snapshot of
    just {_lastUpdated}. Testing `if not previous` there would make every model
    look new on the next run and flood the digest — the cold-start flood reached
    through a different door.
    """
    src = FreeLlmSource()
    monkeypatch.setattr(src, "fetch", lambda: json.loads(FIXTURE.read_text(encoding="utf-8")))
    deals, current = src.check({mod.LAST_UPDATED_KEY: "2026-08-20"}, now=NOW)
    assert deals == []
    assert len([k for k in current if k != mod.LAST_UPDATED_KEY]) > 0
