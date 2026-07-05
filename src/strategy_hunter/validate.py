"""Validation for Stage 2 guide JSON (``data/strategies/guides/*.json``).

The local LLM (Sonnet 4.6) emits guides; this is the gate that catches malformed
output before it can reach the website. It checks each file against the ``Guide``
pydantic schema, then applies a few semantic rules the schema alone can't express
(kebab-case slug, unique ids across the corpus, non-empty steps/sources, sane
confidence). Used both from the CLI and as the reviewer's correctness check.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from .models import Guide

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass
class GuideValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    valid_files: int = 0
    total_files: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_guides(guides_dir: Path) -> GuideValidationResult:
    """Validate every ``*.json`` in ``guides_dir`` against the Guide schema + rules."""
    result = GuideValidationResult()
    if not guides_dir.exists():
        result.warnings.append(f"guides dir does not exist yet: {guides_dir}")
        return result

    paths = sorted(guides_dir.glob("*.json"))
    result.total_files = len(paths)
    seen_ids: dict[str, str] = {}

    for path in paths:
        rel = path.name
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result.errors.append(f"{rel}: cannot read/parse JSON — {exc}")
            continue

        guide, errors, warnings = validate_guide_data(rel, data, seen_ids)
        result.warnings.extend(warnings)
        if errors:
            result.errors.extend(errors)
        else:
            result.valid_files += 1

    return result


def validate_guide_data(
    rel: str, data: dict, seen_ids: dict[str, str]
) -> tuple[Guide | None, list[str], list[str]]:
    """Validate one guide payload (schema + semantics).

    ``seen_ids`` maps id -> filename of guides already accepted in this run; it is
    consulted (but not mutated) to flag duplicates. Returns ``(guide, errors,
    warnings)`` — ``guide`` is ``None`` whenever ``errors`` is non-empty. Shared by
    the CLI validator and the automated Stage 2 extractor, so both apply the same
    rules to guide JSON before it can reach disk.
    """
    warnings: list[str] = []
    try:
        guide = Guide.model_validate(data)
    except ValidationError as exc:
        errors = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "(root)"
            errors.append(f"{rel}: {loc}: {err['msg']}")
        return None, errors, warnings

    errors = _check_semantics(rel, guide, seen_ids, warnings)
    return (None if errors else guide), errors, warnings


def _check_semantics(
    rel: str,
    guide: Guide,
    seen_ids: dict[str, str],
    warnings: list[str],
) -> list[str]:
    errors: list[str] = []

    if not _SLUG_RE.match(guide.id):
        errors.append(f"{rel}: id '{guide.id}' is not a kebab-case slug")
    elif guide.id in seen_ids:
        errors.append(
            f"{rel}: duplicate id '{guide.id}' (also in {seen_ids[guide.id]})"
        )
    else:
        seen_ids[guide.id] = rel

    if not guide.steps:
        errors.append(f"{rel}: guide has no steps")
    else:
        orders = [s.order for s in guide.steps]
        if len(set(orders)) != len(orders):
            errors.append(f"{rel}: step 'order' values are not unique: {orders}")

    if not guide.sources:
        errors.append(f"{rel}: guide cites no sources")

    if guide.confidence is not None and not 0.0 <= guide.confidence <= 1.0:
        errors.append(
            f"{rel}: confidence {guide.confidence} outside 0..1"
        )

    # Warnings — not fatal, but worth the reviewer's attention.
    if not guide.summary.strip():
        warnings.append(f"{rel}: summary is empty")
    if not guide.techniques:
        warnings.append(f"{rel}: no techniques listed")

    return errors
