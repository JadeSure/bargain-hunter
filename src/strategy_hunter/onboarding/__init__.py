"""Newcomer onboarding catalog for strategy_hunter.

Public API for the curated catalog of AU money-saving programs.
"""

from __future__ import annotations

from .collect import collect_onboarding, load_all_onboarding_posts
from .models import PROGRAM_CATEGORIES, Program, ProgramStep
from .relevance import onboarding_relevance_score
from .validate import ProgramValidationResult, validate_programs

__all__ = [
    "PROGRAM_CATEGORIES",
    "Program",
    "ProgramStep",
    "ProgramValidationResult",
    "collect_onboarding",
    "load_all_onboarding_posts",
    "onboarding_relevance_score",
    "validate_programs",
]
