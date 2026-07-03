"""Offline backtest CLI — replay observation logs through hot-classification logic.

Usage::

    bargain-hunter-backtest --settings candidate.yaml
    bargain-hunter-backtest --settings candidate.yaml --from 2026-06-24 --to 2026-06-30
    bargain-hunter-backtest --settings candidate.yaml --sent-log sent_log.json

Purpose (PRD P1.1): every threshold change today needs a week of live
observation to evaluate. ``data/observations/*.jsonl`` (written by
``observations.build_observation`` on every run) already has, for every
active deal on every run, the *inputs* to ``classify_hot`` — this module
replays those inputs through candidate ``scoring.hot`` settings without
touching the network or any state file.

## Why this is a *replay*, not a re-run of ``scoring.py``

Observation rows do **not** store the raw ``DealSnapshot`` history — only the
aggregate features (``vote_velocity``, ``comment_velocity``, ``n_snapshots``,
``age_hours``, ...) computed *once*, at write time, using whatever
``scoring.window_minutes`` was live that run. ``compute_hot_score`` and
``is_hot_candidate`` in ``scoring.py`` take a snapshot list and recompute
velocity from scratch, so they cannot be called directly here.

Instead, ``_replay_score`` / ``_replay_is_candidate`` below are algebraic
reimplementations of ``compute_hot_score`` / ``is_hot_candidate`` that take
the *stored* velocity numbers as given. This makes the replay **exact** for
candidate settings that change score weights, tier floors, or vote-count
gates (the overwhelming majority of tuning knobs) — but it means a candidate
settings file that changes ``scoring.window_minutes`` cannot be backtested
accurately: the stored ``vote_velocity``/``comment_velocity`` figures are
frozen at the *original* window and cannot be recomputed for a different one.
The report does not special-case this; if you change ``window_minutes`` in a
candidate file, treat the output as indicative only.

The "top-P%-velocity" candidacy gate (gate 3 in ``is_hot_candidate``) compares
a deal's velocity against every other deal active in the *same run*. Rows are
grouped by their shared ``ts`` (every deal observed in one run is logged with
one common timestamp) to reconstruct that per-run cohort.

## Quality gate: classification vs. what's actually sent

``main.py`` computes two different things at two different points in a run:
``classify_hot`` (step 4) decides a deal's *tier*, and that tier is what gets
logged to observations as ``is_hot``/``hot_level`` (step 4b) — **before**
``_passes_quality_gate`` (step 6) additionally filters the lowest tier at
send time. So the ground truth in observations reflects classification only,
never the quality gate.

This module mirrors that split: ``classify_row``/``replay`` reproduce
``classify_hot`` and are what's compared against recorded ``is_hot``/
``hot_level`` in the report's fire counts and newly-fire/no-longer-fire diff
(this is also why the sanity check — replaying the config that produced the
data — reproduces the recorded classifications almost exactly, see
``tests/test_backtest.py::test_replay_sanity_matches_recorded_current_config``).
``would_send`` separately reimplements ``main._passes_quality_gate`` (not
imported — importing ``main`` would trigger its module-level
``logging.basicConfig`` as a side effect) to report a *second*,
unvalidated-against-ground-truth number: ``sendable_fire_counts_by_tier``,
i.e. what would actually reach an inbox after the quality gate.

## Sent-log join format (``--sent-log``)

Optional, minimal, and intentionally decoupled from the live Notion Sent Log
schema (no network dependency). Accepts either:

- a JSON file containing a list of objects, or
- a CSV file with a header row,

each row/object needs at least ``deal_key`` and a feedback indicator. Accepted
column names (first match wins): ``feedback`` (``"up"``/``"down"``,
``"1"``/``"0"``, or truthy/falsy), or separate ``thumbs_up`` / ``thumbs_down``
count columns. A ``tier`` column is optional; when absent, feedback is pooled
across all fired tiers rather than broken out per tier. Rows with a
``deal_key`` that never fired in the replay are ignored. When ``--sent-log``
is omitted, this section of the report is skipped entirely (FR3).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from .config import HotConfig, ScoringConfig, Settings, effective_tiers, load_settings

_AET = ZoneInfo("Australia/Sydney")
DEFAULT_OBS_DIR = Path("data/observations")


# ---------------------------------------------------------------------------
# Observation row model — tolerant of schema growth across the corpus.
# ---------------------------------------------------------------------------


class ObservationRow(BaseModel):
    """One line from data/observations/*.jsonl.

    ``extra="ignore"`` plus optional/defaulted fields because the schema has
    grown over time (``hot_level`` and ``price_confidence`` are absent from
    the earliest files) — see ``observations.py``.
    """

    model_config = ConfigDict(extra="ignore")

    ts: str
    deal_key: str
    title: str
    votes_pos: int = 0
    votes_neg: int = 0
    neg_ratio: float = 0.0
    comment_count: int = 0
    click_count: int = 0
    n_snapshots: int = 0
    vote_velocity: float = 0.0
    lifetime_velocity: float = 0.0
    comment_velocity: float = 0.0
    click_velocity: float = 0.0
    age_hours: float | None = None
    price: float | None = None
    price_confidence: str | None = None
    discount_percent: float | None = None
    hot_score: float = 0.0
    is_hot: bool = False
    hot_level: str | None = None


def _file_date(path: Path) -> date | None:
    try:
        return date.fromisoformat(path.stem)
    except ValueError:
        return None


def load_observations(
    obs_dir: Path,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[ObservationRow]:
    """Load observation rows from ``obs_dir``, filtered by AET filename date.

    Files are named ``<AET-date>.jsonl`` (see ``observations.ObservationLog``),
    so filtering by filename avoids parsing files entirely outside the range —
    this is what keeps a months-long backtest fast (FR4).
    """
    rows: list[ObservationRow] = []
    for path in sorted(obs_dir.glob("*.jsonl")):
        file_date = _file_date(path)
        if file_date is not None:
            if date_from and file_date < date_from:
                continue
            if date_to and file_date > date_to:
                continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(ObservationRow.model_validate_json(line))
    return rows


def group_by_run(rows: list[ObservationRow]) -> dict[str, list[ObservationRow]]:
    """Group rows by their shared ``ts`` — one group per pipeline run."""
    runs: dict[str, list[ObservationRow]] = defaultdict(list)
    for row in rows:
        runs[row.ts].append(row)
    return runs


# ---------------------------------------------------------------------------
# Replay: algebraic reimplementations of scoring.py / main.py, operating on
# the stored aggregate features rather than raw snapshots (see module docstring).
# ---------------------------------------------------------------------------


def _replay_score(row: ObservationRow, hot: HotConfig) -> float:
    """Reimplementation of scoring.compute_hot_score using stored aggregates."""
    age_hours = row.age_hours or 0.0
    age_factor = 0.5 ** (age_hours / hot.age_penalty_half_life_hours)
    total_votes = row.votes_pos + row.votes_neg
    neg_ratio = row.votes_neg / total_votes if total_votes else 0.0

    v1 = hot.min_votes_gain_per_window or 1
    v2 = hot.early_burst_min_votes or 1
    vote_term = row.vote_velocity / v1 + math.log1p(row.votes_pos) / math.log1p(v2)
    comment_term = hot.comment_velocity_weight * row.comment_velocity
    score = age_factor * (vote_term + comment_term) - hot.neg_vote_penalty_weight * neg_ratio
    return round(max(score, 0.0), 4)


def _replay_is_candidate(
    row: ObservationRow, run_rows: list[ObservationRow], cfg: ScoringConfig
) -> bool:
    """Reimplementation of scoring.is_hot_candidate using stored aggregates."""
    hot = cfg.hot
    if row.votes_pos < hot.min_votes_to_candidate:
        return False

    # Gate 1: window vote gain. Uses the *stored* vote_velocity, which was
    # computed against the window_minutes live at write time — see the module
    # docstring's caveat about changing scoring.window_minutes in candidates.
    if row.n_snapshots >= 2:
        window_gain = row.vote_velocity * (cfg.window_minutes / 60)
        if window_gain >= hot.min_votes_gain_per_window:
            return True

    # Gate 2: early burst.
    age_hours = row.age_hours if row.age_hours is not None else 0.0
    if age_hours <= hot.early_burst_age_hours and row.votes_pos >= hot.early_burst_min_votes:
        return True

    # Gate 3: top-P% velocity among deals active in the same run.
    if run_rows and row.n_snapshots >= 2 and row.votes_pos >= hot.min_votes_for_percentile:
        my_vel = row.vote_velocity
        velocities = [
            r.vote_velocity
            for r in run_rows
            if r.votes_pos >= hot.min_votes_for_percentile and r.n_snapshots >= 2
        ]
        if velocities:
            velocities.sort(reverse=True)
            cutoff_idx = max(0, int(len(velocities) * hot.velocity_top_percent / 100) - 1)
            if my_vel > 0 and my_vel >= velocities[cutoff_idx]:
                return True

    return False


def _replay_passes_quality_gate(row: ObservationRow, hot: HotConfig) -> bool:
    """Reimplementation of main._passes_quality_gate.

    Not imported from ``main`` because importing that module triggers its
    module-level ``logging.basicConfig`` call, which would clobber this CLI's
    own log/stdout formatting as a side effect.
    """
    min_disc = hot.quality_min_discount_pct
    if min_disc is None:
        return True
    if row.vote_velocity >= 20.0:
        return True
    if row.votes_pos >= hot.quality_high_votes_threshold:
        return True
    return row.discount_percent is not None and row.discount_percent >= min_disc


def classify_row(
    row: ObservationRow, run_rows: list[ObservationRow], cfg: ScoringConfig
) -> str | None:
    """Return the hot tier ``classify_hot`` would assign, or None.

    This is what ``main.py`` logs as ``is_hot``/``hot_level`` in the
    observation row (step 4b, *before* the per-subscriber quality gate in
    step 6) — so it is the quantity to compare against recorded ground truth.
    See ``would_send`` for the quality-gate-filtered variant.
    """
    if not _replay_is_candidate(row, run_rows, cfg):
        return None
    score = _replay_score(row, cfg.hot)
    tiers = effective_tiers(cfg.hot)

    for tier in tiers:
        if score < tier.min_score:
            continue
        if tier.min_votes is not None and row.votes_pos < tier.min_votes:
            continue
        min_disc = tier.min_discount_percent
        if min_disc is not None and (row.discount_percent or 0) < min_disc:
            continue
        return tier.name
    return None


def would_send(level: str, row: ObservationRow, cfg: ScoringConfig) -> bool:
    """Whether ``level`` would survive main.py's quality gate (step 6).

    The quality gate only guards the *lowest* configured tier (see
    ``main._passes_quality_gate``'s docstring) — a deal that already earned a
    higher tier isn't double-filtered.
    """
    tiers = effective_tiers(cfg.hot)
    lowest_tier_name = tiers[-1].name
    tier_rank = {t.name: i for i, t in enumerate(reversed(tiers))}
    is_elevated = tier_rank.get(level, 0) > tier_rank.get(lowest_tier_name, 0)
    return is_elevated or _replay_passes_quality_gate(row, cfg.hot)


def replay(
    rows: list[ObservationRow], cfg: ScoringConfig
) -> list[tuple[ObservationRow, str | None]]:
    """Replay every row through the candidate config's ``classify_hot`` logic.

    Returns the classification tier (matching what's recorded in
    observations), not the quality-gate-filtered send decision — see
    ``classify_row``'s docstring and the module docstring's "Quality gate"
    section.
    """
    runs = group_by_run(rows)
    return [(row, classify_row(row, runs[row.ts], cfg)) for row in rows]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class BacktestReport:
    total_rows: int
    fire_counts_by_tier: dict[str, int]
    fire_rate: float
    daily_volume: dict[str, int]
    newly_fire: list[str]
    no_longer_fire: list[str]
    sendable_fire_counts_by_tier: dict[str, int]
    sent_log_stats: dict[str, dict] | None = field(default=None)


def _aet_date(ts: str) -> str:
    return datetime.fromisoformat(ts).astimezone(_AET).strftime("%Y-%m-%d")


def build_report(
    replayed: list[tuple[ObservationRow, str | None]],
    cfg: ScoringConfig,
    sent_log: list[dict] | None = None,
) -> BacktestReport:
    """Aggregate a replay into a report.

    ``fire_counts_by_tier`` / ``newly_fire`` / ``no_longer_fire`` compare the
    ``classify_hot``-only tier (see ``classify_row``) against the recorded
    ``is_hot``/``hot_level`` ground truth. ``sendable_fire_counts_by_tier``
    additionally applies the quality gate (``would_send``) to show what would
    actually reach a subscriber's inbox — there is no recorded ground truth
    for that quantity (see the module docstring), so it is not used in the diff.
    """
    total = len(replayed)
    fire_counts: Counter[str] = Counter()
    sendable_fire_counts: Counter[str] = Counter()
    daily_volume: Counter[str] = Counter()
    newly_fire: set[str] = set()
    no_longer_fire: set[str] = set()
    fired_tier_by_key: dict[str, str] = {}

    for row, level in replayed:
        if level is not None:
            fire_counts[level] += 1
            daily_volume[_aet_date(row.ts)] += 1
            fired_tier_by_key[row.deal_key] = level
            if would_send(level, row, cfg):
                sendable_fire_counts[level] += 1
            if not row.is_hot:
                newly_fire.add(row.deal_key)
        elif row.is_hot:
            no_longer_fire.add(row.deal_key)

    fire_rate = sum(fire_counts.values()) / total if total else 0.0

    sent_log_stats: dict[str, dict] | None = None
    if sent_log is not None:
        sent_log_stats = _join_sent_log(sent_log, fired_tier_by_key)

    return BacktestReport(
        total_rows=total,
        fire_counts_by_tier=dict(fire_counts),
        fire_rate=round(fire_rate, 4),
        daily_volume=dict(sorted(daily_volume.items())),
        newly_fire=sorted(newly_fire),
        no_longer_fire=sorted(no_longer_fire),
        sendable_fire_counts_by_tier=dict(sendable_fire_counts),
        sent_log_stats=sent_log_stats,
    )


def _feedback_is_positive(row: dict) -> bool | None:
    if "feedback" in row and row["feedback"] not in (None, ""):
        val = str(row["feedback"]).strip().lower()
        if val in ("up", "1", "true", "yes", "positive", "thumbs_up"):
            return True
        if val in ("down", "0", "false", "no", "negative", "thumbs_down"):
            return False
    up = row.get("thumbs_up")
    down = row.get("thumbs_down")
    if up is not None or down is not None:
        return int(up or 0) >= int(down or 0)
    return None


def _join_sent_log(sent_log: list[dict], fired_tier_by_key: dict[str, str]) -> dict[str, dict]:
    """Join sent-log feedback rows against replay fires, pooled per tier."""
    positives: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    for entry in sent_log:
        deal_key = entry.get("deal_key")
        if not deal_key or deal_key not in fired_tier_by_key:
            continue
        is_pos = _feedback_is_positive(entry)
        if is_pos is None:
            continue
        tier = entry.get("tier") or fired_tier_by_key[deal_key]
        totals[tier] += 1
        if is_pos:
            positives[tier] += 1

    return {
        tier: {
            "n": totals[tier],
            "positive_rate": round(positives[tier] / totals[tier], 4) if totals[tier] else None,
        }
        for tier in totals
    }


def load_sent_log(path: Path) -> list[dict]:
    """Load a minimal sent-log export — see module docstring for the format."""
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON list of objects")
    return data


def render_report(report: BacktestReport) -> str:
    lines = [
        "Bargain Hunter backtest report",
        "==============================",
        f"Total observation rows: {report.total_rows}",
        f"Overall fire rate: {report.fire_rate:.2%}",
        "",
        "Fire counts by tier:",
    ]
    if report.fire_counts_by_tier:
        for tier, count in sorted(report.fire_counts_by_tier.items(), key=lambda kv: -kv[1]):
            sendable = report.sendable_fire_counts_by_tier.get(tier, 0)
            lines.append(f"  {tier:10s} {count:6d}  ({sendable} sendable after quality gate)")
    else:
        lines.append("  (none)")

    lines += ["", "Daily volume (fires per AET date):"]
    if report.daily_volume:
        for day, count in report.daily_volume.items():
            lines.append(f"  {day}  {count}")
    else:
        lines.append("  (none)")

    lines += ["", f"Newly fires under candidate config ({len(report.newly_fire)} deals):"]
    lines += [f"  + {key}" for key in report.newly_fire] or ["  (none)"]

    lines += ["", f"No longer fires under candidate config ({len(report.no_longer_fire)} deals):"]
    lines += [f"  - {key}" for key in report.no_longer_fire] or ["  (none)"]

    if report.sent_log_stats is not None:
        lines += ["", "Sent-log 👍-rate proxy by tier:"]
        if report.sent_log_stats:
            for tier, stats in sorted(report.sent_log_stats.items()):
                rate = stats["positive_rate"]
                rate_str = f"{rate:.2%}" if rate is not None else "n/a"
                lines.append(f"  {tier:10s} n={stats['n']:<5d} 👍 rate={rate_str}")
        else:
            lines.append("  (no matching sent-log rows for fired deals)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run_backtest(
    settings_path: Path,
    obs_dir: Path = DEFAULT_OBS_DIR,
    date_from: date | None = None,
    date_to: date | None = None,
    sent_log_path: Path | None = None,
) -> BacktestReport:
    settings: Settings = load_settings(settings_path)
    rows = load_observations(obs_dir, date_from, date_to)
    replayed = replay(rows, settings.scoring)
    sent_log = load_sent_log(sent_log_path) if sent_log_path else None
    return build_report(replayed, settings.scoring, sent_log)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bargain-hunter-backtest",
        description="Replay data/observations/*.jsonl through candidate scoring settings.",
    )
    parser.add_argument("--settings", required=True, type=Path, help="Candidate settings YAML.")
    parser.add_argument(
        "--from", dest="date_from", type=_parse_date, default=None, help="AET date, inclusive."
    )
    parser.add_argument(
        "--to", dest="date_to", type=_parse_date, default=None, help="AET date, inclusive."
    )
    parser.add_argument(
        "--obs-dir", type=Path, default=DEFAULT_OBS_DIR, help="Observation log directory."
    )
    parser.add_argument(
        "--sent-log", type=Path, default=None, help="Optional Sent Log export (.json or .csv)."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = run_backtest(
        settings_path=args.settings,
        obs_dir=args.obs_dir,
        date_from=args.date_from,
        date_to=args.date_to,
        sent_log_path=args.sent_log,
    )
    print(render_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
