"""CLI entry point for the strategy-collection pipeline.

Usage::

    python -m strategy_hunter collect          # fetch sources, store, write digest
    python -m strategy_hunter digest           # rebuild digest from the stored corpus
    python -m strategy_hunter validate-guides  # validate Stage 2 guide JSON
    python -m strategy_hunter --help
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from .collect import collect, load_all_posts
from .config import load_strategy_config
from .digest import write_digest
from .onboarding import audit_programs, render_issue_body, validate_programs
from .onboarding.collect import collect_onboarding, load_all_onboarding_posts
from .validate import validate_guides

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)


def _maybe_alert(summary: dict) -> None:
    """Email the maintainer if the run errored or harvested nothing."""
    errors = summary.get("errors") or []
    fetched = summary.get("fetched", 0)
    if not errors and fetched > 0:
        return
    if errors and fetched == 0:
        subject = "Strategy collection FAILED — no posts fetched"
    elif errors:
        subject = f"Strategy collection had {len(errors)} source error(s)"
    else:
        subject = "Strategy collection fetched 0 posts"
    error_lines = [f"  - {e}" for e in errors] or ["  (none)"]
    body_lines = [
        f"fetched={fetched} relevant={summary.get('relevant', 0)} "
        f"new={summary.get('new', 0)} pruned={summary.get('pruned', 0)}",
        "",
        "Errors:",
        *error_lines,
    ]
    try:
        from bargain_hunter.notify.email import send_maintainer_alert

        send_maintainer_alert(subject, "\n".join(body_lines))
    except Exception as exc:  # alerting must never crash the run
        log.error("Could not send strategy collection alert: %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Strategy guide collector.")
    parser.add_argument(
        "command",
        nargs="?",
        default="collect",
        choices=[
            "collect",
            "digest",
            "validate-guides",
            "onboarding-validate",
            "onboarding-collect",
            "onboarding-digest",
            "onboarding-audit",
        ],
        help=(
            "collect: fetch + store + digest; digest: rebuild digest from corpus; "
            "validate-guides: validate Stage 2 guide JSON; "
            "onboarding-validate: validate onboarding program JSON; "
            "onboarding-collect: fetch + store + digest onboarding material; "
            "onboarding-digest: rebuild onboarding digest from corpus; "
            "onboarding-audit: flag stale catalog programs for review."
        ),
    )
    parser.add_argument(
        "--settings", type=Path, default=None, help="Path to settings.yaml."
    )
    parser.add_argument(
        "--report", type=Path, default=None,
        help="onboarding-audit: write issue-body markdown here when stale items exist.",
    )
    args = parser.parse_args()

    cfg = load_strategy_config(args.settings)
    if not cfg.enabled:
        log.info("strategy.enabled is false — nothing to do.")
        return

    now = datetime.now(UTC)
    if args.command == "collect":
        summary = collect(cfg, now=now)
        log.info("Summary: %s", summary)
        if cfg.alert_on_failure:
            _maybe_alert(summary)
    elif args.command == "digest":
        posts = load_all_posts(Path(cfg.raw_dir))
        path = write_digest(posts, Path(cfg.digest_dir), now)
        log.info("Rebuilt digest from %d posts: %s", len(posts), path)
    elif args.command == "validate-guides":
        result = validate_guides(Path(cfg.guides_dir))
        for warn in result.warnings:
            log.warning("guide warning: %s", warn)
        for err in result.errors:
            log.error("guide error: %s", err)
        log.info(
            "Validated %d/%d guide files OK.",
            result.valid_files, result.total_files,
        )
        if not result.ok:
            sys.exit(1)
    elif args.command == "onboarding-validate":
        result = validate_programs(Path(cfg.onboarding.programs_dir))
        for warn in result.warnings:
            log.warning("program warning: %s", warn)
        for err in result.errors:
            log.error("program error: %s", err)
        log.info(
            "Validated %d/%d program files OK.",
            result.valid_files, result.total_files,
        )
        if not result.ok:
            sys.exit(1)
    elif args.command == "onboarding-collect":
        summary = collect_onboarding(cfg, now=now)
        log.info("Summary: %s", summary)
        if cfg.alert_on_failure:
            _maybe_alert(summary)
    elif args.command == "onboarding-digest":
        posts = load_all_onboarding_posts(Path(cfg.onboarding.raw_dir))
        path = write_digest(
            posts,
            Path(cfg.onboarding.digest_dir),
            now,
            title="Newcomer onboarding material digest",
            prompt_ref="prompts/extract_onboarding.md",
        )
        log.info("Rebuilt onboarding digest from %d posts: %s", len(posts), path)
    elif args.command == "onboarding-audit":
        result = audit_programs(
            Path(cfg.onboarding.programs_dir),
            now=now,
            max_age_days=cfg.onboarding.staleness_days,
        )
        for err in result.errors:
            log.error("audit error: %s", err)
        for f in result.flags:
            log.warning("stale program: %s (%s) — %s", f.id, f.reason, f.detail)
        log.info(
            "Audited %d programs: %d fresh, %d flagged.",
            result.total, result.fresh, len(result.flags),
        )
        if args.report and result.stale:
            body = render_issue_body(result, max_age_days=cfg.onboarding.staleness_days)
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(body, encoding="utf-8")
            log.info("Wrote audit report: %s", args.report)


if __name__ == "__main__":
    main()
