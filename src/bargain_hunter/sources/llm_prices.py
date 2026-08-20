"""OpenRouter token-price differ: a CamelCamelCamel for LLM APIs.

Compares each model's current per-token price against the snapshot from the
previous run (an arbitrary dict handed in by the caller — meant to come from
``StateStore.snapshot("llm_prices")``, see state.py) and emits one Deal per
model that got either meaningfully cheaper or newly free.

Two branches, and the order matters (Correction C1,
docs/HIGH_VALUE_SOURCES_PLAN.md): a model id absent from the previous
snapshot is usually a new model launch, not a price cut, so it is skipped —
UNLESS it launched at US$0/M tokens, which is always worth knowing about and
would otherwise be silently swallowed by that same guard.

Unlike the other sources this is stateful across runs, so it does not
implement the plain ``Source.fetch() -> list[Deal]`` contract. ``check()`` is
the entry point: it fetches, diffs against ``previous``, and returns both the
deals to emit and the new snapshot the caller should persist via
``state.set_snapshot("llm_prices", current)``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from ..models import Deal

log = logging.getLogger(__name__)

API_URL = "https://openrouter.ai/api/v1/models"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
CATEGORIES = ["AI", "API", "Software"]

PriceMap = dict[str, tuple[float, float]]


def _sanitize(model_id: str) -> str:
    return model_id.replace("/", "-").replace("~", "-")


class LlmPriceSource:
    name = "openrouter"

    def __init__(
        self,
        min_drop_percent: float = 10.0,
        model_allowlist: list[str] | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.min_drop_percent = min_drop_percent
        self.model_allowlist = model_allowlist or []
        self.timeout = timeout

    def fetch(self) -> list[dict]:
        """Network only. Returns raw `data` entries, or [] on any failure.

        Never raises — this endpoint has no published rate limit or SLA and
        runs inside the 5-minute loop; one bad response must not sink the run.
        """
        try:
            resp = httpx.get(API_URL, headers={"User-Agent": BROWSER_UA}, timeout=self.timeout)
        except httpx.HTTPError as exc:
            log.warning("openrouter: request failed — %s", exc)
            return []
        if resp.status_code != 200:
            log.warning("openrouter: non-200 response (%s)", resp.status_code)
            return []
        try:
            return resp.json().get("data") or []
        except (ValueError, AttributeError) as exc:
            log.warning("openrouter: malformed response body — %s", exc)
            return []

    def check(self, previous: dict, now: datetime | None = None) -> tuple[list[Deal], PriceMap]:
        """Fetch, diff against `previous`, and return (deals, current).

        On fetch failure `current` is `previous` unchanged, so the caller's
        `state.set_snapshot("llm_prices", current)` is a safe no-op instead
        of wiping the snapshot to empty on a transient outage.
        """
        now = now or datetime.now(UTC)
        raw = self.fetch()
        if not raw:
            return [], previous

        current: PriceMap = {}
        deals: list[Deal] = []
        for model in raw:
            model_id = model.get("id")
            pricing = model.get("pricing") or {}
            prompt_raw = pricing.get("prompt")
            completion_raw = pricing.get("completion")
            if not model_id or prompt_raw is None or completion_raw is None:
                continue
            try:
                new_prompt = float(prompt_raw)
                new_completion = float(completion_raw)
            except (TypeError, ValueError):
                continue
            current[model_id] = (new_prompt, new_completion)

            if not previous:
                continue  # cold start / lost cache: no baseline yet, seed silently

            if self.model_allowlist and not any(s in model_id for s in self.model_allowlist):
                continue

            name = model.get("name") or model_id
            is_new = model_id not in previous
            is_free = new_prompt == 0.0 and new_completion == 0.0
            if is_new and is_free:
                deals.append(self._free_deal(model_id, name, now))
                continue
            if is_new:
                continue  # a new priced model is not a price cut

            try:
                old_prompt = float(previous[model_id][0])
            except (TypeError, ValueError, IndexError):
                continue
            if old_prompt <= 0:
                continue
            drop = (old_prompt - new_prompt) / old_prompt * 100
            if drop >= self.min_drop_percent:
                deals.append(self._drop_deal(model_id, name, new_prompt, old_prompt, drop, now))

        return deals, current

    @staticmethod
    def _free_deal(model_id: str, name: str, now: datetime) -> Deal:
        return Deal(
            source="openrouter",
            deal_id=_sanitize(model_id),
            title=f"{name}: now free on OpenRouter (US$0/M tokens)",
            url=f"https://openrouter.ai/{model_id}",
            categories=CATEGORIES,
            posted_at=now,
            price=0.0,
            discount_percent=100.0,
            price_confidence=None,
            currency="USD",
        )

    @staticmethod
    def _drop_deal(
        model_id: str,
        name: str,
        new_prompt: float,
        old_prompt: float,
        drop: float,
        now: datetime,
    ) -> Deal:
        return Deal(
            source="openrouter",
            deal_id=_sanitize(model_id),
            title=(
                f"{name}: input US${new_prompt * 1e6:.2f}/M tokens "
                f"(was US${old_prompt * 1e6:.2f}) — {drop:.0f}% cheaper"
            ),
            url=f"https://openrouter.ai/{model_id}",
            categories=CATEGORIES,
            posted_at=now,
            price=new_prompt * 1e6,
            was_price=old_prompt * 1e6,
            discount_percent=round(drop, 1),
            price_confidence=None,
            currency="USD",
        )
