"""Validation for onboarding program JSON (``data/strategies/onboarding/programs/*.json``).

Checks each file against the ``Program`` pydantic schema, then applies semantic rules:
kebab-case slug, unique ids across the corpus, valid category, non-empty how_to_join,
unique step orders, confidence in 0..1, priority >= 1, and needs_referral/referral_note
consistency.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from .models import PROGRAM_CATEGORIES, Program

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass
class ProgramValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    valid_files: int = 0
    total_files: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_programs(programs_dir: Path) -> ProgramValidationResult:
    """Validate every ``*.json`` in ``programs_dir`` against the Program schema + rules."""
    result = ProgramValidationResult()
    if not programs_dir.exists():
        result.warnings.append(f"programs dir does not exist yet: {programs_dir}")
        return result

    paths = sorted(programs_dir.glob("*.json"))
    result.total_files = len(paths)
    seen_ids: dict[str, str] = {}

    for path in paths:
        rel = path.name
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result.errors.append(f"{rel}: cannot read/parse JSON — {exc}")
            continue

        try:
            program = Program.model_validate(data)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"]) or "(root)"
                result.errors.append(f"{rel}: {loc}: {err['msg']}")
            continue

        file_errors = _check_semantics(rel, program, seen_ids, result.warnings)
        if file_errors:
            result.errors.extend(file_errors)
        else:
            result.valid_files += 1

    return result


def _check_semantics(
    rel: str,
    program: Program,
    seen_ids: dict[str, str],
    warnings: list[str],
) -> list[str]:
    errors: list[str] = []

    if not _SLUG_RE.match(program.id):
        errors.append(f"{rel}: id '{program.id}' is not a kebab-case slug")
    elif program.id in seen_ids:
        errors.append(
            f"{rel}: duplicate id '{program.id}' (also in {seen_ids[program.id]})"
        )
    else:
        seen_ids[program.id] = rel

    if program.category not in PROGRAM_CATEGORIES:
        errors.append(f"{rel}: category '{program.category}' is not in PROGRAM_CATEGORIES")

    if not program.how_to_join:
        errors.append(f"{rel}: how_to_join is empty")
    else:
        orders = [s.order for s in program.how_to_join]
        if len(set(orders)) != len(orders):
            errors.append(f"{rel}: step 'order' values are not unique: {orders}")

    if program.confidence is not None and not 0.0 <= program.confidence <= 1.0:
        errors.append(f"{rel}: confidence {program.confidence} outside 0..1")

    if program.priority < 1:
        errors.append(f"{rel}: priority {program.priority} must be >= 1")

    if program.needs_referral and not program.referral_note:
        errors.append(f"{rel}: needs_referral is True but referral_note is empty")

    # Warnings — non-fatal but worth reviewing.
    if not program.one_liner.strip():
        warnings.append(f"{rel}: one_liner is empty")
    if not program.benefit.strip():
        warnings.append(f"{rel}: benefit is empty")
    if not program.sources:
        warnings.append(f"{rel}: no sources listed")
    if not program.official_url:
        warnings.append(f"{rel}: no official_url set")

    return errors
