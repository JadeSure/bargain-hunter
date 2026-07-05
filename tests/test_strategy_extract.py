"""Tests for automated Stage 2 guide extraction (Gemini transport, JSON parsing,
validation-before-write, and overwrite-only-if-changed semantics). No network."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from strategy_hunter import extract as extract_mod
from strategy_hunter.config import StrategyConfig
from strategy_hunter.extract import (
    GeminiRateLimited,
    call_gemini,
    extract_guides,
    parse_guide_candidates,
)

VALID_GUIDE = {
    "id": "buy-macbook-au-cheap",
    "goal": "Buy a MacBook cheaply in Australia",
    "summary": "Stack discounted gift cards + cashback to save on a MacBook.",
    "techniques": ["discounted_giftcard", "cashback"],
    "steps": [
        {
            "order": 1,
            "action": "Buy discounted Apple gift cards",
            "technique": "discounted_giftcard",
        },
        {"order": 2, "action": "Place the order via a cashback portal", "technique": "cashback"},
    ],
    "sources": ["https://www.ozbargain.com.au/node/111111"],
    "confidence": 0.8,
}


class FakeResponse:
    def __init__(self, status_code: int, payload: dict, headers: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)  # type: ignore[arg-type]


# -- parse_guide_candidates ----------------------------------------------------


def test_parse_bare_list():
    assert parse_guide_candidates(json.dumps([VALID_GUIDE])) == [VALID_GUIDE]


def test_parse_single_object():
    assert parse_guide_candidates(json.dumps(VALID_GUIDE)) == [VALID_GUIDE]


def test_parse_wrapped_guides_key():
    assert parse_guide_candidates(json.dumps({"guides": [VALID_GUIDE]})) == [VALID_GUIDE]


def test_parse_fenced_json():
    text = f"Here you go:\n```json\n{json.dumps([VALID_GUIDE])}\n```\nDone."
    assert parse_guide_candidates(text) == [VALID_GUIDE]


def test_parse_invalid_json_raises():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_guide_candidates("not json at all")


def test_parse_unexpected_top_level_raises():
    with pytest.raises(ValueError, match="unexpected JSON top-level type"):
        parse_guide_candidates("42")


# -- call_gemini ----------------------------------------------------------------


def test_call_gemini_parses_response(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse(
            200,
            {"candidates": [{"content": {"parts": [{"text": "hello "}, {"text": "world"}]}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    text = call_gemini(
        "system prompt", "user message", model="gemini-2.5-flash", max_tokens=100, api_key="key123"
    )
    assert text == "hello \nworld"
    assert captured["headers"]["x-goog-api-key"] == "key123"
    assert "gemini-2.5-flash:generateContent" in captured["url"]
    assert captured["json"]["system_instruction"]["parts"][0]["text"] == "system prompt"


def test_call_gemini_no_candidates_raises(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: FakeResponse(200, {"candidates": []}))
    with pytest.raises(ValueError, match="no candidates"):
        call_gemini("s", "u", model="m", max_tokens=10, api_key="k")


def test_call_gemini_retries_on_429_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(
                429,
                {
                    "error": {
                        "details": [
                            {
                                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                                "retryDelay": "0.01s",
                            }
                        ]
                    }
                },
            )
        return FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(extract_mod.time, "sleep", lambda s: None)
    text = call_gemini("s", "u", model="m", max_tokens=10, api_key="k", max_retries=2)
    assert text == "ok"
    assert calls["n"] == 2


def test_call_gemini_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: FakeResponse(429, {"error": {}}))
    monkeypatch.setattr(extract_mod.time, "sleep", lambda s: None)
    with pytest.raises(GeminiRateLimited):
        call_gemini("s", "u", model="m", max_tokens=10, api_key="k", max_retries=1)


# -- extract_guides ---------------------------------------------------------------


def _cfg(tmp_path: Path) -> StrategyConfig:
    return StrategyConfig(
        digest_dir=str(tmp_path / "digest"),
        guides_dir=str(tmp_path / "guides"),
        raw_dir=str(tmp_path / "raw"),
    )


def _write_digest(cfg: StrategyConfig, name: str = "2026-07-06.md") -> None:
    digest_dir = Path(cfg.digest_dir)
    digest_dir.mkdir(parents=True, exist_ok=True)
    (digest_dir / name).write_text(f"# digest\nsome content for {name}", encoding="utf-8")


def test_skips_without_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cfg = _cfg(tmp_path)
    _write_digest(cfg)
    result = extract_guides(cfg)
    assert result.skipped
    assert "GEMINI_API_KEY" in result.skip_reason


def test_skips_without_digest(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "key123")
    cfg = _cfg(tmp_path)
    result = extract_guides(cfg)
    assert result.skipped
    assert "no digest" in result.skip_reason


def test_skips_on_rate_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "key123")
    cfg = _cfg(tmp_path)
    _write_digest(cfg)
    monkeypatch.setattr(
        extract_mod, "call_gemini", lambda *a, **kw: (_ for _ in ()).throw(GeminiRateLimited("x"))
    )
    result = extract_guides(cfg)
    assert result.skipped
    assert not result.errors


def test_writes_valid_guide(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "key123")
    cfg = _cfg(tmp_path)
    _write_digest(cfg)
    monkeypatch.setattr(extract_mod, "call_gemini", lambda *a, **kw: json.dumps([VALID_GUIDE]))
    result = extract_guides(cfg)
    assert result.written == ["buy-macbook-au-cheap"]
    assert not result.errors
    out = json.loads((Path(cfg.guides_dir) / "buy-macbook-au-cheap.json").read_text())
    assert out["goal"] == VALID_GUIDE["goal"]
    assert out["generated_at"]


def test_invalid_candidate_not_written(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "key123")
    cfg = _cfg(tmp_path)
    _write_digest(cfg)
    bad = {k: v for k, v in VALID_GUIDE.items() if k != "goal"}
    monkeypatch.setattr(extract_mod, "call_gemini", lambda *a, **kw: json.dumps([bad]))
    result = extract_guides(cfg)
    assert not result.written
    assert result.errors
    assert not list(Path(cfg.guides_dir).glob("*.json"))


def test_duplicate_id_in_batch_flagged(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "key123")
    cfg = _cfg(tmp_path)
    _write_digest(cfg)
    monkeypatch.setattr(
        extract_mod, "call_gemini", lambda *a, **kw: json.dumps([VALID_GUIDE, VALID_GUIDE])
    )
    result = extract_guides(cfg)
    assert result.written == ["buy-macbook-au-cheap"]
    assert any("duplicate id" in e for e in result.errors)


def test_unchanged_guide_not_rewritten(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "key123")
    cfg = _cfg(tmp_path)
    _write_digest(cfg)
    monkeypatch.setattr(extract_mod, "call_gemini", lambda *a, **kw: json.dumps([VALID_GUIDE]))

    first = extract_guides(cfg)
    assert first.written == ["buy-macbook-au-cheap"]
    path = Path(cfg.guides_dir) / "buy-macbook-au-cheap.json"
    first_generated_at = json.loads(path.read_text())["generated_at"]

    second = extract_guides(cfg)
    assert second.unchanged == ["buy-macbook-au-cheap"]
    assert not second.written
    assert json.loads(path.read_text())["generated_at"] == first_generated_at


def test_changed_guide_overwritten_with_new_generated_at(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "key123")
    cfg = _cfg(tmp_path)
    _write_digest(cfg)
    monkeypatch.setattr(extract_mod, "call_gemini", lambda *a, **kw: json.dumps([VALID_GUIDE]))
    first = extract_guides(cfg)
    assert first.written == ["buy-macbook-au-cheap"]

    changed = dict(VALID_GUIDE)
    changed["summary"] = "A brand-new, different summary."
    monkeypatch.setattr(extract_mod, "call_gemini", lambda *a, **kw: json.dumps([changed]))
    second = extract_guides(cfg)
    assert second.written == ["buy-macbook-au-cheap"]
    out = json.loads((Path(cfg.guides_dir) / "buy-macbook-au-cheap.json").read_text())
    assert out["summary"] == changed["summary"]


def test_date_argument_selects_specific_digest(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "key123")
    cfg = _cfg(tmp_path)
    _write_digest(cfg, "2026-07-01.md")
    _write_digest(cfg, "2026-07-06.md")
    seen = {}

    def fake_call(system_prompt, user_message, **kw):
        seen["user_message"] = user_message
        return json.dumps([])

    monkeypatch.setattr(extract_mod, "call_gemini", fake_call)
    extract_guides(cfg, date="2026-07-01")
    assert "2026-07-01.md" in seen["user_message"]
