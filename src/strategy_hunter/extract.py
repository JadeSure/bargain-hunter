"""Automated Stage 2 guide extraction via the Gemini API.

Stage 2 used to be 100% manual: a human pasted ``digest/<date>.md`` and
``prompts/extract_guide.md`` into an LLM and hand-saved the JSON output to
``data/strategies/guides/``. This module does the same thing over HTTP
(``httpx``, no ``google-genai`` SDK dependency) so it can run unattended from
CI — every candidate guide is still run through the same schema + semantic
checks as ``validate_guides`` before anything touches disk, and a human reviews
the diff via a pull request rather than a straight commit to ``main``.

Degrades gracefully: with no ``GEMINI_API_KEY`` (e.g. the secret isn't
configured yet), no digest to extract from, or a free-tier 429 that survives
retries, this is a clean, non-crashing skip.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .config import StrategyConfig
from .models import Guide
from .validate import validate_guide_data

log = logging.getLogger(__name__)

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "extract_guide.md"
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_TEMPERATURE = 0.2
_DEFAULT_RETRY_DELAY_SECONDS = 5.0


class GeminiRateLimited(Exception):
    """429 persisted after retries — caller should skip this run, not crash."""


@dataclass
class ExtractResult:
    written: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors


def latest_digest_path(digest_dir: Path, date: str | None = None) -> Path | None:
    """The digest to extract from: ``date`` (YYYY-MM-DD) if given, else the newest."""
    if date:
        path = digest_dir / f"{date}.md"
        return path if path.exists() else None
    if not digest_dir.exists():
        return None
    paths = sorted(digest_dir.glob("*.md"))
    return paths[-1] if paths else None


def parse_guide_candidates(raw_text: str) -> list[dict]:
    """Pull guide JSON object(s) out of a raw model response.

    Tolerates a fenced ```json code block, a bare JSON list of guides, a single
    guide object, or ``{"guides": [...]}``.
    """
    text = raw_text.strip()
    fences = _JSON_FENCE_RE.findall(text)
    payload = fences[0].strip() if fences else text
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"model response is not valid JSON: {exc}") from exc

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("guides"), list):
            return data["guides"]
        return [data]
    raise ValueError(f"unexpected JSON top-level type: {type(data).__name__}")


def _retry_delay_seconds(response: httpx.Response) -> float:
    """Best-effort wait hint from a 429: Retry-After header, else Gemini's RetryInfo."""
    header = response.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    try:
        details = response.json().get("error", {}).get("details", [])
    except (json.JSONDecodeError, ValueError):
        details = []
    for detail in details:
        if str(detail.get("@type", "")).endswith("RetryInfo"):
            delay = str(detail.get("retryDelay", ""))
            if delay.endswith("s"):
                try:
                    return float(delay[:-1])
                except ValueError:
                    pass
    return _DEFAULT_RETRY_DELAY_SECONDS


def call_gemini(
    system_prompt: str,
    user_message: str,
    *,
    model: str,
    max_tokens: int,
    api_key: str,
    timeout: float = 300.0,
    max_retries: int = 2,
) -> str:
    """Call the Gemini generateContent API and return the concatenated text content.

    Gemini's free tier rate-limits aggressively; a 429 is retried a modest
    number of times honouring any retry hint, then raises ``GeminiRateLimited``
    so the caller can skip this run cleanly rather than crash it.
    """
    url = f"{_API_BASE}/{model}:generateContent"
    headers = {"x-goog-api-key": api_key, "content-type": "application/json"}
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_message}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": _TEMPERATURE},
    }

    attempt = 0
    while True:
        response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        if response.status_code == 429:
            if attempt >= max_retries:
                raise GeminiRateLimited(f"Gemini rate-limited after {max_retries} retries")
            delay = _retry_delay_seconds(response)
            log.warning(
                "Gemini rate-limited (attempt %d/%d) — waiting %.1fs.",
                attempt + 1, max_retries, delay,
            )
            time.sleep(delay)
            attempt += 1
            continue
        response.raise_for_status()
        break

    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise ValueError(f"Gemini response contained no candidates: {data}")
    parts = candidates[0].get("content", {}).get("parts", [])
    return "\n".join(part.get("text", "") for part in parts if part.get("text"))


def extract_guides(
    cfg: StrategyConfig,
    *,
    date: str | None = None,
    now: datetime | None = None,
) -> ExtractResult:
    """Run Stage 2 extraction against the latest (or ``date``) digest.

    Validates every candidate guide with the same rules as ``validate_guides``
    and only writes files that pass. An existing guide with the same id is
    overwritten only if its content actually changed; ``generated_at`` is
    refreshed whenever a file is (re)written.
    """
    now = now or datetime.now(UTC)
    result = ExtractResult()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        result.skipped = True
        result.skip_reason = "GEMINI_API_KEY is not set"
        log.info("%s — skipping automated guide extraction.", result.skip_reason)
        return result

    digest_dir = Path(cfg.digest_dir)
    digest_path = latest_digest_path(digest_dir, date)
    if digest_path is None:
        result.skipped = True
        result.skip_reason = f"no digest found (date={date or 'latest'})"
        log.info("%s — nothing to extract.", result.skip_reason)
        return result

    system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    digest_text = digest_path.read_text(encoding="utf-8")

    try:
        raw_text = call_gemini(
            system_prompt,
            digest_text,
            model=cfg.extract.model,
            max_tokens=cfg.extract.max_tokens,
            api_key=api_key,
        )
    except GeminiRateLimited as exc:
        result.skipped = True
        result.skip_reason = str(exc)
        log.warning("%s — skipping this run.", exc)
        return result
    except httpx.HTTPError as exc:
        result.errors.append(f"Gemini API request failed: {exc}")
        return result

    try:
        candidates = parse_guide_candidates(raw_text)
    except ValueError as exc:
        result.errors.append(str(exc))
        return result

    guides_dir = Path(cfg.guides_dir)
    guides_dir.mkdir(parents=True, exist_ok=True)
    _write_candidates(candidates, guides_dir, now, result)
    return result


def _write_candidates(
    candidates: list[dict], guides_dir: Path, now: datetime, result: ExtractResult
) -> None:
    disk_ids = {path.stem for path in guides_dir.glob("*.json")}
    batch_ids: set[str] = set()

    for candidate in candidates:
        if not isinstance(candidate, dict):
            result.errors.append(f"skipping non-object candidate: {candidate!r}")
            continue
        candidate = dict(candidate)
        candidate.setdefault("generated_at", now.isoformat())
        guide_id = candidate.get("id")
        rel = f"{guide_id or '?'}.json"

        if guide_id in batch_ids:
            result.errors.append(f"{rel}: duplicate id '{guide_id}' within this extraction batch")
            continue

        # A guide reappearing for the same id is a legitimate refresh, not a
        # duplicate — exclude it from the on-disk id set passed to the validator.
        seen_ids = {i: f"{i}.json" for i in disk_ids if i != guide_id}
        guide, errors, warnings = validate_guide_data(rel, candidate, seen_ids)
        for warning in warnings:
            log.warning("extract warning: %s", warning)
        if errors or guide is None:
            result.errors.extend(errors or [f"{rel}: failed validation"])
            continue

        batch_ids.add(guide.id)
        _write_guide_if_changed(guides_dir, guide, now, result)


def _write_guide_if_changed(
    guides_dir: Path, guide: Guide, now: datetime, result: ExtractResult
) -> None:
    path = guides_dir / f"{guide.id}.json"
    new_payload = guide.model_dump(mode="json", exclude={"generated_at"})

    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        existing_payload = {k: v for k, v in existing.items() if k != "generated_at"}
        if existing_payload == new_payload:
            result.unchanged.append(guide.id)
            return

    guide.generated_at = now
    path.write_text(
        json.dumps(guide.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    result.written.append(guide.id)
