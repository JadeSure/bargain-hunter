"""Newcomer onboarding catalog for strategy_hunter.

Public API for the curated catalog of AU money-saving programs.
"""

from __future__ import annotations

from .audit import AuditResult, StaleFlag, audit_programs, render_issue_body
from .collect import collect_onboarding, load_all_onboarding_posts
from .models import PROGRAM_CATEGORIES, Program, ProgramStep
from .relevance import onboarding_relevance_score
from .validate import ProgramValidationResult, validate_programs

__all__ = [
    "PROGRAM_CATEGORIES",
    "AuditResult",
    "Program",
    "ProgramStep",
    "ProgramValidationResult",
    "StaleFlag",
    "audit_programs",
    "collect_onboarding",
    "load_all_onboarding_posts",
    "onboarding_relevance_score",
    "render_issue_body",
    "validate_programs",
]
