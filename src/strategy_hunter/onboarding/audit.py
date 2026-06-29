"""Freshness audit for the onboarding program catalog.

Stage 2 (LLM extraction of programs) is manual, so the curated catalog can rot
silently — exactly how Cashrewards lingered after it shut down. This module scans
``data/strategies/onboarding/programs/*.json`` and flags entries that are likely
stale so the daily cron can open a GitHub issue for review. It never mutates the
catalog and degrades gracefully on unreadable files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from .models import Program


@dataclass
class StaleFlag:
    """One reason a program needs a refresh."""

    id: str
    name: str
    reason: str          # "expired" | "old" | "no_date"
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


def audit_programs(
    programs_dir: Path,
    *,
    now: datetime | None = None,
    max_age_days: int = 90,
) -> AuditResult:
    """Flag programs that are expired, undated, or older than ``max_age_days``."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=max_age_days)
    result = AuditResult()
    if not programs_dir.exists():
        return result

    for path in sorted(programs_dir.glob("*.json")):
        try:
            program = Program.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, json.JSONDecodeError) as exc:
            result.errors.append(f"{path.name}: cannot read/parse — {exc}")
            continue
        result.total += 1
        flag = _flag_for(program, now=now, cutoff=cutoff, max_age_days=max_age_days)
        if flag:
            result.flags.append(flag)
        else:
            result.fresh += 1

    result.flags.sort(key=lambda f: (f.reason, f.id))
    return result


def _flag_for(
    program: Program, *, now: datetime, cutoff: datetime, max_age_days: int
) -> StaleFlag | None:
    if program.valid_until and program.valid_until < now:
        return StaleFlag(
            program.id, program.name, "expired",
            f"valid_until {program.valid_until.date()} has passed",
        )
    if program.generated_at is None:
        return StaleFlag(program.id, program.name, "no_date", "no generated_at recorded")
    if program.generated_at < cutoff:
        age = (now - program.generated_at).days
        return StaleFlag(
            program.id, program.name, "old",
            f"reviewed {age}d ago (>{max_age_days}d)",
        )
    return None


def render_issue_body(result: AuditResult, *, max_age_days: int) -> str:
    """Markdown body for the review issue the cron opens when stale items exist."""
    lines = [
        "The onboarding program catalog has entries that need a freshness review "
        f"(threshold: {max_age_days} days). Confirm each is still accurate and bump "
        "`generated_at`, or remove/replace it.",
        "",
        f"**{len(result.flags)}** of {result.total} programs flagged:",
        "",
    ]
    reasons = {"expired": "⏰ expired", "old": "🕒 stale", "no_date": "❓ undated"}
    for f in result.flags:
        lines.append(f"- **{f.name}** (`{f.id}`) — {reasons.get(f.reason, f.reason)}: {f.detail}")
    if result.errors:
        lines += ["", "Unreadable files:", *[f"- {e}" for e in result.errors]]
    lines += ["", "_Opened automatically by the daily onboarding audit._"]
    return "\n".join(lines)
