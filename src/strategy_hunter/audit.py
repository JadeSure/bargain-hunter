"""Freshness audit for Stage 2 guide JSON (``data/strategies/guides/*.json``).

Extraction can now run automatically (see ``extract.py``), but guides can still
rot silently between refreshes — a time-limited promo expires, or every raw post
a guide cites gets pruned by ``cleanup.prune_corpus`` (60-day retention) so there
is nothing left to re-verify the claim against. This module scans the guides
directory and flags entries needing review, mirroring
``onboarding.audit.audit_programs``. It never mutates guide files and degrades
gracefully on unreadable JSON.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from .models import Guide


@dataclass
class StaleFlag:
    """One reason a guide needs a refresh."""

    id: str
    goal: str
    reason: str          # "expired" | "old" | "no_date" | "sources_pruned"
    detail: str


@dataclass
class AuditResult:
    flags: list[StaleFlag] = field(default_factory=list)
    fresh: int = 0
    total: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def stale(self) -> bool:
        return bool(self.flags)


def _raw_urls(raw_dir: Path) -> set[str]:
    """Every source URL still present in the (pruned) raw corpus."""
    urls: set[str] = set()
    if not raw_dir.exists():
        return urls
    for path in raw_dir.glob("*/*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        url = data.get("url")
        if url:
            urls.add(url)
    return urls


def audit_guides(
    guides_dir: Path,
    raw_dir: Path,
    *,
    now: datetime | None = None,
    staleness_days: int = 30,
) -> AuditResult:
    """Flag guides that are expired, undated, stale, or fully source-pruned."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=staleness_days)
    result = AuditResult()
    if not guides_dir.exists():
        return result

    live_urls = _raw_urls(raw_dir)

    for path in sorted(guides_dir.glob("*.json")):
        try:
            guide = Guide.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, json.JSONDecodeError) as exc:
            result.errors.append(f"{path.name}: cannot read/parse — {exc}")
            continue
        result.total += 1
        flag = _flag_for(guide, now=now, cutoff=cutoff, staleness_days=staleness_days,
                          live_urls=live_urls)
        if flag:
            result.flags.append(flag)
        else:
            result.fresh += 1

    result.flags.sort(key=lambda f: (f.reason, f.id))
    return result


def _flag_for(
    guide: Guide,
    *,
    now: datetime,
    cutoff: datetime,
    staleness_days: int,
    live_urls: set[str],
) -> StaleFlag | None:
    if guide.valid_until and guide.valid_until < now:
        return StaleFlag(
            guide.id, guide.goal, "expired",
            f"valid_until {guide.valid_until.date()} has passed",
        )
    if guide.generated_at is None:
        return StaleFlag(guide.id, guide.goal, "no_date", "no generated_at recorded")
    if guide.generated_at < cutoff:
        age = (now - guide.generated_at).days
        return StaleFlag(
            guide.id, guide.goal, "old",
            f"reviewed {age}d ago (>{staleness_days}d)",
        )
    if guide.sources and live_urls and not any(s in live_urls for s in guide.sources):
        return StaleFlag(
            guide.id, guide.goal, "sources_pruned",
            "all cited sources have been pruned from the raw corpus",
        )
    return None


def render_issue_body(result: AuditResult, *, staleness_days: int) -> str:
    """Markdown body for the review issue the cron opens when stale guides exist."""
    lines = [
        "The Stage 2 guide catalog has entries that need a freshness review "
        f"(threshold: {staleness_days} days). Confirm each is still accurate, "
        "re-run `strategy-hunter extract`, or remove/replace it.",
        "",
        f"**{len(result.flags)}** of {result.total} guides flagged:",
        "",
    ]
    reasons = {
        "expired": "⏰ expired",
        "old": "🕒 stale",
        "no_date": "❓ undated",
        "sources_pruned": "🗑️ sources pruned",
    }
    for f in result.flags:
        lines.append(f"- **{f.goal}** (`{f.id}`) — {reasons.get(f.reason, f.reason)}: {f.detail}")
    if result.errors:
        lines += ["", "Unreadable files:", *[f"- {e}" for e in result.errors]]
    lines += ["", "_Opened automatically by the nightly strategy guide audit._"]
    return "\n".join(lines)
