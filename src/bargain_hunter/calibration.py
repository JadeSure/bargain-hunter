"""Weekly calibration report (Improvement PRD P2.2) — human-in-the-loop only.

Joins the Notion Sent Log + Feedback DBs against an observation replay (reusing
``backtest.py``'s replay machinery) to answer: are the tiers/tracks/sources we
actually send performing well, and would nudging a tier's score threshold have
helped? This module **never writes to config/settings.yaml or Notion** — it
only produces a markdown report for a human to read and decide on.

Usage::

    bargain-hunter-calibrate
    bargain-hunter-calibrate --lookback-days 21 --settings candidate.yaml

Degrades gracefully (prints a clear message, exits 0, writes nothing) when
``NOTION_TOKEN`` / ``NOTION_SENT_LOG_DB_ID`` / ``NOTION_FEEDBACK_DB_ID`` are not
all set — see AGENTS.md's "optional integrations degrade gracefully" convention.

## Design notes

- **Join key is the deal, not the (deal, subscriber) pair.** The Feedback DB
  (written by ``feedback-worker``) does not carry a Sent Log row id, only a
  deal id + optional subscriber email, so feedback is pooled per deal exactly
  like ``backtest._join_sent_log`` already does for its own sent-log join —
  this keeps the two joins conceptually consistent.
- **Tier ground truth comes from replaying observations under the *current*
  settings**, not from the Sent Log (which has no tier column) — this reuses
  ``backtest.replay``/``classify_row`` rather than duplicating the
  score/candidacy logic.
- **Source** (``ozbargain`` / ``camelcamelcamel``) is parsed from the
  ``source:deal_id`` shape of ``Deal.key`` (see ``models.Deal.key``) since
  neither the Sent Log nor the Feedback DB stores it directly.
- **Threshold suggestions are asymmetric by construction.** Raising a tier's
  ``min_score`` can only *exclude* deals we already sent (and therefore have
  feedback for), so its effect on 👍-rate is directly measurable. Lowering a
  threshold *includes* deals that were never sent — we have no feedback for
  them, so only a volume estimate is reported, never a rate. Every cell below
  ``min_n`` samples is flagged "insufficient data" rather than guessed at.
"""

from __future__ import annotations

import argparse
import logging
import os
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from notion_client import Client

from .backtest import (
    DEFAULT_OBS_DIR,
    ObservationRow,
    classify_row,
    group_by_run,
    load_observations,
    replay,
)
from .config import (
    HotConfig,
    ScoringConfig,
    Settings,
    effective_tiers,
    load_dotenv,
    load_settings,
)

log = logging.getLogger(__name__)

_AET = ZoneInfo("Australia/Sydney")
DEFAULT_REPORT_DIR = Path("data/calibration")
DEFAULT_LOOKBACK_DAYS = 14
DEFAULT_MIN_CELL_N = 20
GRID_DELTAS: tuple[float, ...] = (-1.0, -0.5, 0.5, 1.0)

# Sent Log property names — must match dedup.py's schema (see that module).
_P_SENT_DEAL_ID = "Deal ID"
_P_SENT_SUBSCRIBER = "Subscriber Email"
_P_SENT_TRACK = "Track"
_P_SENT_AT = "Sent At"
_P_SENT_PRICE = "Price"
_P_SENT_DISCOUNT = "Discount %"
_P_SENT_VOTES = "Votes Pos"

# Feedback DB property names — must match feedback-worker/src/index.js.
_P_FB_DEAL_ID = "Deal ID"
_P_FB_VERDICT = "Verdict"
_P_FB_EMAIL = "Subscriber Email"
_P_FB_AT = "At"


# ---------------------------------------------------------------------------
# Notion I/O
# ---------------------------------------------------------------------------


def make_notion_client() -> Client:
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise RuntimeError("NOTION_TOKEN environment variable not set.")
    return Client(auth=token, notion_version="2022-06-28")


def _query_all(notion: Client, db_id: str, filter_payload: dict) -> list[dict]:
    results: list[dict] = []
    cursor: str | None = None
    while True:
        body: dict = {"page_size": 100, "filter": filter_payload}
        if cursor:
            body["start_cursor"] = cursor
        resp = notion.request(path=f"databases/{db_id}/query", method="POST", body=body)
        results.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return results


def _prop_text(props: dict, key: str) -> str:
    prop = props.get(key, {})
    items = prop.get("rich_text") or prop.get("title") or []
    return "".join(t.get("plain_text", "") for t in items).strip()


@dataclass(frozen=True)
class SentRecord:
    deal_key: str
    subscriber_email: str
    track: str
    sent_at: datetime
    price: float | None
    discount_pct: float | None
    votes_pos: int


@dataclass(frozen=True)
class FeedbackRecord:
    deal_key: str
    subscriber_email: str
    positive: bool
    at: datetime


def parse_sent_record(props: dict) -> SentRecord | None:
    deal_key = _prop_text(props, _P_SENT_DEAL_ID)
    sent_at_raw = (props.get(_P_SENT_AT, {}).get("date") or {}).get("start")
    if not deal_key or not sent_at_raw:
        return None
    sent_at = datetime.fromisoformat(sent_at_raw)
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=UTC)
    email = props.get(_P_SENT_SUBSCRIBER, {}).get("email") or ""
    track = (props.get(_P_SENT_TRACK, {}).get("select") or {}).get("name", "hot")
    price = props.get(_P_SENT_PRICE, {}).get("number")
    discount = props.get(_P_SENT_DISCOUNT, {}).get("number")
    votes = props.get(_P_SENT_VOTES, {}).get("number")
    return SentRecord(
        deal_key=deal_key,
        subscriber_email=email,
        track=track,
        sent_at=sent_at,
        price=float(price) if price is not None else None,
        discount_pct=float(discount) if discount is not None else None,
        votes_pos=int(votes or 0),
    )


def parse_feedback_record(props: dict) -> FeedbackRecord | None:
    deal_key = _prop_text(props, _P_FB_DEAL_ID)
    verdict = (props.get(_P_FB_VERDICT, {}).get("select") or {}).get("name")
    at_raw = (props.get(_P_FB_AT, {}).get("date") or {}).get("start")
    if not deal_key or verdict not in ("up", "down") or not at_raw:
        return None
    at = datetime.fromisoformat(at_raw)
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    email = props.get(_P_FB_EMAIL, {}).get("email") or ""
    return FeedbackRecord(
        deal_key=deal_key, subscriber_email=email, positive=verdict == "up", at=at
    )


def fetch_sent_log(notion: Client, db_id: str, since: datetime) -> list[SentRecord]:
    filter_payload = {"property": _P_SENT_AT, "date": {"after": since.isoformat()}}
    records = []
    for page in _query_all(notion, db_id, filter_payload):
        rec = parse_sent_record(page.get("properties", {}))
        if rec:
            records.append(rec)
    return records


def fetch_feedback(notion: Client, db_id: str, since: datetime) -> list[FeedbackRecord]:
    filter_payload = {"property": _P_FB_AT, "date": {"after": since.isoformat()}}
    records = []
    for page in _query_all(notion, db_id, filter_payload):
        rec = parse_feedback_record(page.get("properties", {}))
        if rec:
            records.append(rec)
    return records


# ---------------------------------------------------------------------------
# Pure join/aggregation logic — no network, unit-testable with synthetic data.
# ---------------------------------------------------------------------------


def deal_source(deal_key: str) -> str:
    """Parse the source prefix from a ``source:deal_id`` key (see models.Deal.key)."""
    return deal_key.split(":", 1)[0] if ":" in deal_key else "unknown"


def latest_sent_by_deal(sent_records: list[SentRecord]) -> dict[str, SentRecord]:
    latest: dict[str, SentRecord] = {}
    for rec in sent_records:
        cur = latest.get(rec.deal_key)
        if cur is None or rec.sent_at > cur.sent_at:
            latest[rec.deal_key] = rec
    return latest


def latest_observation_by_deal(rows: list[ObservationRow]) -> dict[str, ObservationRow]:
    latest: dict[str, ObservationRow] = {}
    for row in rows:
        cur = latest.get(row.deal_key)
        if cur is None or row.ts > cur.ts:
            latest[row.deal_key] = row
    return latest


@dataclass(frozen=True)
class JoinedFeedback:
    deal_key: str
    source: str
    track: str
    tier: str | None
    positive: bool
    price: float | None
    discount_pct: float | None
    votes_pos: int
    vote_velocity: float | None
    comment_velocity: float | None


def join_feedback(
    sent_records: list[SentRecord],
    feedback_records: list[FeedbackRecord],
    tier_by_deal_key: dict[str, str],
    obs_by_deal_key: dict[str, ObservationRow] | None = None,
) -> list[JoinedFeedback]:
    """Join each feedback row to the (most recent) Sent Log entry for its deal.

    Pooled at deal-key level, not (deal, subscriber) — see module docstring.
    Feedback rows whose deal was never sent (or predates the lookback window)
    are dropped.
    """
    obs_by_deal_key = obs_by_deal_key or {}
    sent_by_deal = latest_sent_by_deal(sent_records)
    joined: list[JoinedFeedback] = []
    for fb in feedback_records:
        sent = sent_by_deal.get(fb.deal_key)
        if sent is None:
            continue
        obs = obs_by_deal_key.get(fb.deal_key)
        joined.append(
            JoinedFeedback(
                deal_key=fb.deal_key,
                source=deal_source(fb.deal_key),
                track=sent.track,
                tier=tier_by_deal_key.get(fb.deal_key),
                positive=fb.positive,
                price=sent.price,
                discount_pct=(
                    sent.discount_pct
                    if sent.discount_pct is not None
                    else (obs.discount_percent if obs else None)
                ),
                votes_pos=sent.votes_pos,
                vote_velocity=obs.vote_velocity if obs else None,
                comment_velocity=obs.comment_velocity if obs else None,
            )
        )
    return joined


@dataclass(frozen=True)
class RateCell:
    n: int
    positive: int

    @property
    def rate(self) -> float | None:
        return round(self.positive / self.n, 4) if self.n else None


def _rate_by(joined: list[JoinedFeedback], key_fn) -> dict[str, RateCell]:
    totals: Counter[str] = Counter()
    positives: Counter[str] = Counter()
    for j in joined:
        k = key_fn(j)
        totals[k] += 1
        if j.positive:
            positives[k] += 1
    return {k: RateCell(n=totals[k], positive=positives[k]) for k in totals}


def rate_by_tier(joined: list[JoinedFeedback]) -> dict[str, RateCell]:
    return _rate_by(joined, lambda j: j.tier or "untiered")


def rate_by_track(joined: list[JoinedFeedback]) -> dict[str, RateCell]:
    return _rate_by(joined, lambda j: j.track)


def rate_by_source(joined: list[JoinedFeedback]) -> dict[str, RateCell]:
    return _rate_by(joined, lambda j: j.source)


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 3) if values else None


def distribution_comparison(joined: list[JoinedFeedback]) -> dict[str, dict[str, float | None]]:
    """Mean votes/velocity/discount for 👍 vs 👎 deals, side by side."""
    groups = {
        "positive": [j for j in joined if j.positive],
        "negative": [j for j in joined if not j.positive],
    }
    out: dict[str, dict[str, float | None]] = {}
    for label, items in groups.items():
        out[label] = {
            "n": len(items),
            "mean_votes_pos": _mean([float(j.votes_pos) for j in items]),
            "mean_vote_velocity": _mean(
                [j.vote_velocity for j in items if j.vote_velocity is not None]
            ),
            "mean_discount_pct": _mean(
                [j.discount_pct for j in items if j.discount_pct is not None]
            ),
        }
    return out


# ---------------------------------------------------------------------------
# Threshold grid search
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThresholdSuggestion:
    tier: str
    delta: float
    direction: str  # "raise" | "lower"
    n: int
    baseline_positive_rate: float | None
    candidate_positive_rate: float | None
    note: str


def _adjust_tier_min_score(hot: HotConfig, tier_name: str, delta: float) -> HotConfig:
    tiers = effective_tiers(hot)
    new_tiers = [
        t.model_copy(update={"min_score": round(t.min_score + delta, 4)})
        if t.name == tier_name
        else t
        for t in tiers
    ]
    return hot.model_copy(update={"tiers": new_tiers})


def grid_search_thresholds(
    rows: list[ObservationRow],
    cfg: ScoringConfig,
    joined: list[JoinedFeedback],
    deltas: tuple[float, ...] = GRID_DELTAS,
    min_n: int = DEFAULT_MIN_CELL_N,
) -> list[ThresholdSuggestion]:
    """For each tier x delta, replay observations under the adjusted config and
    report the effect on the 👍-rate of *currently-sent* deals in that tier.

    See the module docstring for why raising and lowering are handled
    asymmetrically. Never mutates ``cfg`` or any settings file.
    """
    baseline_by_tier = rate_by_tier(joined)
    tiers = effective_tiers(cfg.hot)
    runs = group_by_run(rows)
    suggestions: list[ThresholdSuggestion] = []

    for tier in tiers:
        baseline = baseline_by_tier.get(tier.name)
        baseline_rate = baseline.rate if baseline else None
        tier_joined = [j for j in joined if j.tier == tier.name]
        tier_deal_keys = {j.deal_key for j in tier_joined}

        for delta in deltas:
            direction = "raise" if delta > 0 else "lower"
            candidate_hot = _adjust_tier_min_score(cfg.hot, tier.name, delta)
            candidate_cfg = cfg.model_copy(update={"hot": candidate_hot})
            new_tier_by_key = {
                row.deal_key: classify_row(row, runs[row.ts], candidate_cfg) for row in rows
            }

            if direction == "raise":
                remaining = [j for j in tier_joined if new_tier_by_key.get(j.deal_key) == tier.name]
                n = len(remaining)
                if n < min_n or baseline is None or baseline.n < min_n:
                    suggestions.append(
                        ThresholdSuggestion(
                            tier=tier.name,
                            delta=delta,
                            direction=direction,
                            n=n,
                            baseline_positive_rate=baseline_rate,
                            candidate_positive_rate=None,
                            note=f"insufficient data (n<{min_n})",
                        )
                    )
                    continue
                positive = sum(1 for j in remaining if j.positive)
                candidate_rate = round(positive / n, 4)
                improved = candidate_rate > (baseline_rate or 0)
                verdict = "would improve" if improved else "would not improve"
                suggestions.append(
                    ThresholdSuggestion(
                        tier=tier.name,
                        delta=delta,
                        direction=direction,
                        n=n,
                        baseline_positive_rate=baseline_rate,
                        candidate_positive_rate=candidate_rate,
                        note=f"{verdict} the 👍-rate among currently-sent {tier.name} deals",
                    )
                )
            else:
                newly_qualifying = {
                    key
                    for key, t in new_tier_by_key.items()
                    if t == tier.name and key not in tier_deal_keys
                }
                n = len(newly_qualifying)
                note = (
                    f"insufficient data (n<{min_n})"
                    if n < min_n
                    else (
                        f"would newly qualify ~{n} deals never sent at this tier — "
                        "no feedback exists for them, so 👍-rate cannot be estimated"
                    )
                )
                suggestions.append(
                    ThresholdSuggestion(
                        tier=tier.name,
                        delta=delta,
                        direction=direction,
                        n=n,
                        baseline_positive_rate=baseline_rate,
                        candidate_positive_rate=None,
                        note=note,
                    )
                )
    return suggestions


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class CalibrationReport:
    generated_at: datetime
    lookback_days: int
    sent_count: int
    feedback_count: int
    joined_count: int
    rate_by_tier: dict[str, RateCell]
    rate_by_track: dict[str, RateCell]
    rate_by_source: dict[str, RateCell]
    distribution: dict[str, dict[str, float | None]]
    suggestions: list[ThresholdSuggestion]
    report_path: Path | None = field(default=None)


def _fmt_rate(cell: RateCell | None) -> str:
    if cell is None or cell.rate is None:
        return "n/a"
    return f"{cell.rate:.1%}"


def _fmt_val(value: float | None, suffix: str = "") -> str:
    return "n/a" if value is None else f"{value:g}{suffix}"


def _fmt_signed_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _rate_table_rows(cells: dict[str, RateCell]) -> list[str]:
    return [
        f"| {name} | {cell.n} | {_fmt_rate(cell)} |"
        for name, cell in sorted(cells.items(), key=lambda kv: -kv[1].n)
    ]


def _rate_summary_lines(cells: dict[str, RateCell], width: int) -> list[str]:
    return [f"  {name:{width}s} n={cell.n:<5d} {_fmt_rate(cell)}" for name, cell in cells.items()]


def render_markdown_report(report: CalibrationReport) -> str:
    aet_date = report.generated_at.astimezone(_AET).date().isoformat()
    lines = [
        f"# Bargain Hunter calibration report — {aet_date}",
        "",
        f"Lookback: {report.lookback_days} days. "
        f"Sent Log rows: {report.sent_count}. Feedback rows: {report.feedback_count}. "
        f"Joined (feedback on a sent deal): {report.joined_count}.",
        "",
        "**This report is advisory only. No thresholds are changed automatically — "
        "a human must edit `config/settings.yaml`, sanity-check with "
        "`bargain-hunter-backtest`, then commit.**",
        "",
        "## 👍-rate by hot tier",
        "",
        "| Tier | n | 👍 rate |",
        "|---|---|---|",
        *(_rate_table_rows(report.rate_by_tier) or ["| (no joined feedback) | | |"]),
        "",
        "## 👍-rate by track",
        "",
        "| Track | n | 👍 rate |",
        "|---|---|---|",
        *(_rate_table_rows(report.rate_by_track) or ["| (no joined feedback) | | |"]),
        "",
        "## 👍-rate by source",
        "",
        "| Source | n | 👍 rate |",
        "|---|---|---|",
        *(_rate_table_rows(report.rate_by_source) or ["| (no joined feedback) | | |"]),
        "",
        "## Distribution: 👍 vs 👎 deals",
        "",
        "| Metric | 👍 deals | 👎 deals |",
        "|---|---|---|",
    ]
    pos = report.distribution.get("positive", {})
    neg = report.distribution.get("negative", {})
    pos_votes = _fmt_val(pos.get("mean_votes_pos"))
    neg_votes = _fmt_val(neg.get("mean_votes_pos"))
    pos_vel = _fmt_val(pos.get("mean_vote_velocity"))
    neg_vel = _fmt_val(neg.get("mean_vote_velocity"))
    pos_disc = _fmt_val(pos.get("mean_discount_pct"), "%")
    neg_disc = _fmt_val(neg.get("mean_discount_pct"), "%")
    lines += [
        f"| n | {pos.get('n', 0)} | {neg.get('n', 0)} |",
        f"| mean votes | {pos_votes} | {neg_votes} |",
        f"| mean vote velocity | {pos_vel} | {neg_vel} |",
        f"| mean discount % | {pos_disc} | {neg_disc} |",
        "",
        "## Suggested threshold adjustments",
        "",
        "Grid replay over `scoring.hot.tiers[].min_score` ± the deltas below. "
        "Raising a threshold only ever removes already-sent (and therefore "
        "feedback-labelled) deals, so its 👍-rate effect is measurable. "
        "Lowering a threshold pulls in deals nobody has rated — those cells "
        "report a volume estimate only, never a rate.",
        "",
        "| Tier | Δ score | n | baseline 👍 rate | candidate 👍 rate | note |",
        "|---|---|---|---|---|---|",
    ]
    if report.suggestions:
        for s in report.suggestions:
            baseline_str = _fmt_signed_rate(s.baseline_positive_rate)
            candidate_str = _fmt_signed_rate(s.candidate_positive_rate)
            sign = "+" if s.delta > 0 else ""
            row = (
                f"| {s.tier} | {sign}{s.delta:g} | {s.n} | {baseline_str} | "
                f"{candidate_str} | {s.note} |"
            )
            lines.append(row)
    else:
        lines.append("| (no tiers configured) | | | | | |")

    lines.append("")
    return "\n".join(lines)


def render_summary(report: CalibrationReport) -> str:
    """One-screen plain-text summary for stdout / the calibration GitHub issue."""
    aet_date = report.generated_at.astimezone(_AET).date().isoformat()
    lines = [
        f"Bargain Hunter calibration summary — {aet_date}",
        "=" * 48,
        f"Lookback: {report.lookback_days}d  Sent: {report.sent_count}  "
        f"Feedback: {report.feedback_count}  Joined: {report.joined_count}",
        "",
        "👍-rate by tier:",
    ]
    lines += _rate_summary_lines(report.rate_by_tier, 10) or ["  (none)"]
    lines += ["", "👍-rate by track:"]
    lines += _rate_summary_lines(report.rate_by_track, 10) or ["  (none)"]
    lines += ["", "👍-rate by source:"]
    lines += _rate_summary_lines(report.rate_by_source, 16) or ["  (none)"]
    lines += ["", "Suggested threshold adjustments (advisory only — never auto-applied):"]
    if report.suggestions:
        for s in report.suggestions:
            sign = "+" if s.delta > 0 else ""
            candidate_str = _fmt_signed_rate(s.candidate_positive_rate)
            summary_line = (
                f"  {s.tier} {sign}{s.delta:g}: n={s.n} candidate={candidate_str} — {s.note}"
            )
            lines.append(summary_line)
    else:
        lines.append("  (none)")
    if report.report_path:
        lines += ["", f"Full report: {report.report_path}"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestration + CLI
# ---------------------------------------------------------------------------


def run_calibration(
    settings_path: Path | None = None,
    obs_dir: Path = DEFAULT_OBS_DIR,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    report_dir: Path = DEFAULT_REPORT_DIR,
    min_n: int = DEFAULT_MIN_CELL_N,
    now: datetime | None = None,
) -> CalibrationReport | None:
    """Pull Sent Log + Feedback from Notion, join against an observation
    replay, and write a markdown report to ``report_dir/YYYY-MM-DD.md``
    (AET date). Returns ``None`` (after logging a clear reason) when Notion
    credentials for either database are unset.
    """
    notion_token = os.environ.get("NOTION_TOKEN")
    sent_log_db = os.environ.get("NOTION_SENT_LOG_DB_ID")
    feedback_db = os.environ.get("NOTION_FEEDBACK_DB_ID")
    missing = [
        name
        for name, val in (
            ("NOTION_TOKEN", notion_token),
            ("NOTION_SENT_LOG_DB_ID", sent_log_db),
            ("NOTION_FEEDBACK_DB_ID", feedback_db),
        )
        if not val
    ]
    if missing:
        log.warning(
            "Calibration skipped: missing environment variable(s): %s. "
            "Set these to enable the weekly calibration report.",
            ", ".join(missing),
        )
        return None

    now = now or datetime.now(UTC)
    since = now - timedelta(days=lookback_days)
    notion = make_notion_client()
    sent_records = fetch_sent_log(notion, sent_log_db, since)  # type: ignore[arg-type]
    feedback_records = fetch_feedback(notion, feedback_db, since)  # type: ignore[arg-type]

    settings: Settings = load_settings(settings_path)
    rows = load_observations(obs_dir, date_from=since.date(), date_to=now.date())
    replayed = replay(rows, settings.scoring)
    tier_by_key = {row.deal_key: level for row, level in replayed if level is not None}
    obs_by_deal = latest_observation_by_deal(rows)

    joined = join_feedback(sent_records, feedback_records, tier_by_key, obs_by_deal)

    report = CalibrationReport(
        generated_at=now,
        lookback_days=lookback_days,
        sent_count=len(sent_records),
        feedback_count=len(feedback_records),
        joined_count=len(joined),
        rate_by_tier=rate_by_tier(joined),
        rate_by_track=rate_by_track(joined),
        rate_by_source=rate_by_source(joined),
        distribution=distribution_comparison(joined),
        suggestions=grid_search_thresholds(rows, settings.scoring, joined, min_n=min_n),
    )

    report_dir.mkdir(parents=True, exist_ok=True)
    aet_date = now.astimezone(_AET).date().isoformat()
    out_path = report_dir / f"{aet_date}.md"
    out_path.write_text(render_markdown_report(report), encoding="utf-8")
    report.report_path = out_path
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bargain-hunter-calibrate",
        description=(
            "Join the Notion Sent Log + Feedback DBs against an observation "
            "replay and write a weekly calibration report. Advisory only — "
            "never edits config/settings.yaml."
        ),
    )
    parser.add_argument(
        "--settings", type=Path, default=None, help="Settings YAML (default: config/settings.yaml)."
    )
    parser.add_argument(
        "--obs-dir", type=Path, default=DEFAULT_OBS_DIR, help="Observation log directory."
    )
    parser.add_argument(
        "--report-dir", type=Path, default=DEFAULT_REPORT_DIR, help="Where to write the report."
    )
    parser.add_argument(
        "--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS, help="Days of history to join."
    )
    parser.add_argument(
        "--min-n",
        type=int,
        default=DEFAULT_MIN_CELL_N,
        help="Minimum sample size per grid-search cell before reporting a rate.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_dotenv()
    args = build_arg_parser().parse_args(argv)
    report = run_calibration(
        settings_path=args.settings,
        obs_dir=args.obs_dir,
        lookback_days=args.lookback_days,
        report_dir=args.report_dir,
        min_n=args.min_n,
    )
    if report is None:
        print("Calibration skipped — see warning above.")
        return 0
    print(render_summary(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
