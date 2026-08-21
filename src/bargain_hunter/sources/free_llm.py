"""Free LLM API tier differ: a CamelCamelCamel for no-cost LLM API access.

Free tiers on inference-provider APIs (Groq, Google Gemini, OpenRouter,
Cloudflare Workers AI, ...) come and go, and their rate limits and context
windows move without announcement. `awesome-free-llm-apis`
(github.com/mnfst/awesome-free-llm-apis) tracks all of it in one
machine-readable `data.json`, refreshed roughly daily. This module polls that
file and diffs it against the previous run's snapshot.

Same shape as llm_prices.py (openrouter's price differ) and the same
cold-start hazard: on the very first run there is no baseline, so every one
of the ~120 free models would look "new" and flood the digest. `check()`
seeds silently on an empty `previous` for that reason -- see the guard below.

Unlike llm_prices.py (one number, price, to diff) each model here carries two
independently-interesting fields -- `rateLimit` and `context` -- so a single
model can produce at most one Deal per run with both changes folded into one
title (mirrors cn_llm_docs.py's `_diff_rows`, which folds multiple changed
table columns into one Deal per row rather than emitting one Deal per cell).

Models dropped from the upstream list are logged at INFO, not emitted as
Deals: a provider retiring a free tier is information, not an offer, and
removals also fire spuriously whenever the upstream repo restructures its
JSON (a source outside our control, unlike our own scoring pipeline).
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

import httpx

from ..models import Deal

log = logging.getLogger(__name__)

API_URL = "https://raw.githubusercontent.com/mnfst/awesome-free-llm-apis/main/data.json"
USER_AGENT = (
    "bargain-hunter/0.1 (personal deal alerter; +https://github.com/versent-shawn/bargain-hunter)"
)
CATEGORIES = ["AI", "API"]
# Snapshot key holding the payload's own "lastUpdated" date string (e.g.
# "2026-08-21"), carried through unparsed for the caller's staleness check.
LAST_UPDATED_KEY = "_lastUpdated"


def _sanitize(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-")


class FreeLlmSource:
    name = "free_llm"

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def fetch(self) -> dict | None:
        """Network only. Returns the parsed payload, or None on any failure.

        Never raises -- this is a third-party repo with no SLA; one bad
        response must not sink the run.
        """
        try:
            resp = httpx.get(
                API_URL,
                headers={"User-Agent": USER_AGENT},
                timeout=self.timeout,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            log.error("free_llm: request failed — %s", exc)
            return None
        if resp.history:
            log.warning("free_llm: redirected to %s", resp.url)
        if resp.status_code != 200:
            log.error("free_llm: non-200 response (%s)", resp.status_code)
            return None
        try:
            payload = resp.json()
        except ValueError as exc:
            log.error("free_llm: malformed response body — %s", exc)
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("providers"), list):
            log.error("free_llm: unexpected payload shape")
            return None
        return payload

    def check(self, previous: dict, now: datetime | None = None) -> tuple[list[Deal], dict]:
        """Fetch, diff against `previous`, and return (deals, current).

        On fetch failure `current` is `previous` unchanged, so the caller's
        `state.set_snapshot("free_llm", current)` is a safe no-op instead of
        wiping the snapshot on a transient outage.
        """
        now = now or datetime.now(UTC)
        payload = self.fetch()
        if payload is None:
            return [], previous

        # "Has a baseline" means "holds at least one model", not "is non-empty".
        # A snapshot can be non-empty and still have no models in it: fetch()
        # accepts `providers: []` as a well-formed payload, which would persist
        # a snapshot of just {_lastUpdated}. Testing `if not previous` there
        # would treat every one of the ~112 models as new on the following run
        # and flood the digest -- the same failure as the cold-start branch,
        # reached through a different door.
        had_baseline = any(k != LAST_UPDATED_KEY for k in previous)
        current: dict = {LAST_UPDATED_KEY: payload.get("lastUpdated")}
        deals: list[Deal] = []
        for provider in payload["providers"]:
            name = provider.get("name")
            url = provider.get("url") or ""
            if not name:
                continue
            for model in provider.get("models") or []:
                model_id = model.get("id")
                if not model_id:
                    continue
                key = f"{name}::{model_id}"
                entry = {"context": model.get("context"), "rateLimit": model.get("rateLimit")}
                current[key] = entry

                if not had_baseline:
                    continue  # cold start / lost cache: no baseline yet, seed silently

                prev_entry = previous.get(key)
                if prev_entry is None:
                    deals.append(self._new_model_deal(name, url, model_id, entry, now))
                    continue

                deal = self._diff_model(name, url, model_id, entry, prev_entry, now)
                if deal is not None:
                    deals.append(deal)

        if had_baseline:
            removed = {k for k in previous if k != LAST_UPDATED_KEY} - set(current)
            if removed:
                log.info(
                    "free_llm: %d model(s) dropped from the upstream list: %s",
                    len(removed),
                    sorted(removed),
                )

        return deals, current

    @staticmethod
    def _new_model_deal(
        provider: str, url: str, model_id: str, entry: dict, now: datetime
    ) -> Deal:
        detail = ", ".join(v for v in (entry.get("context"), entry.get("rateLimit")) if v)
        title = f"{provider}: 新增免费模型 {model_id}"
        if detail:
            title += f" ({detail})"
        return Deal(
            source="free_llm",
            deal_id=_sanitize(f"{provider}-{model_id}"),
            title=title,
            url=url,
            categories=CATEGORIES,
            posted_at=now,
            currency="USD",
        )

    @staticmethod
    def _diff_model(
        provider: str, url: str, model_id: str, entry: dict, prev_entry: dict, now: datetime
    ) -> Deal | None:
        changes = []
        rate_limit, old_rate_limit = entry.get("rateLimit"), (prev_entry or {}).get("rateLimit")
        if rate_limit and old_rate_limit and rate_limit != old_rate_limit:
            changes.append(f"限额 {old_rate_limit} → {rate_limit}")
        context, old_context = entry.get("context"), (prev_entry or {}).get("context")
        if context and old_context and context != old_context:
            changes.append(f"上下文 {old_context} → {context}")
        if not changes:
            return None
        return Deal(
            source="free_llm",
            deal_id=_sanitize(f"{provider}-{model_id}"),
            title=f"{provider}: {model_id} " + ", ".join(changes),
            url=url,
            categories=CATEGORIES,
            posted_at=now,
            currency="USD",
        )
