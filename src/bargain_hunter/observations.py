"""Per-run feature logging for threshold calibration (Step 1 of the tuning plan).

Writes one JSONL row per active deal per run to
``data/observations/<AET-date>.jsonl`` — non-personal deal features only, the
same privacy class as ``deals_state.json``.

These rows are the *features*.  The *labels* (manual review, or 👍/👎 customer
feedback collected via the Cloudflare worker) are joined back later by
``(deal_key, date)`` to find the hot-score "sweet spot" and, eventually, to
train a classifier.  Capturing every active deal (not just hot candidates) is
deliberate: it lets calibration see the deals we *failed* to flag, not only the
ones we did.
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import ScoringConfig
from .models import Deal, DealSnapshot
from .scoring import (
    compute_click_velocity,
    compute_comment_velocity,
    compute_hot_score,
    compute_vote_velocity,
)

log = logging.getLogger(__name__)

_AET = ZoneInfo("Australia/Sydney")
DEFAULT_OBS_DIR = Path("data/observations")


def build_observation(
    deal: Deal,
    snapshots: list[DealSnapshot],
    cfg: ScoringConfig,
    *,
    is_hot: bool,
    level: str | None = None,
    now: datetime,
    heat_ratio: float = 1.0,
    site_velocity_index: float | None = None,
) -> dict:
    """Build one feature row for a deal at decision time.

    `heat_ratio` / `site_velocity_index` are the event-day adaptive baseline
    inputs for this run (see `scoring.compute_heat_ratio`) — logged so the
    backtest replay can reproduce the live decision.
    """
    vote_vel, lifetime_vel = compute_vote_velocity(snapshots, cfg.window_minutes, now)
    comment_vel = compute_comment_velocity(snapshots, cfg.window_minutes, now)
    click_vel = compute_click_velocity(snapshots, cfg.window_minutes, now)
    score = compute_hot_score(deal, snapshots, cfg, now, heat_ratio=heat_ratio)

    age_hours: float | None = None
    if deal.posted_at:
        age_hours = round(max((now - deal.posted_at).total_seconds() / 3600, 0.0), 3)

    total_votes = deal.votes_pos + deal.votes_neg
    return {
        "ts": now.isoformat(),
        "deal_key": deal.key,
        "title": deal.title,
        "votes_pos": deal.votes_pos,
        "votes_neg": deal.votes_neg,
        "neg_ratio": round(deal.votes_neg / total_votes, 4) if total_votes else 0.0,
        "comment_count": deal.comment_count,
        "click_count": deal.click_count,
        "n_snapshots": len(snapshots),
        "vote_velocity": round(vote_vel, 4),
        "lifetime_velocity": round(lifetime_vel, 4),
        "comment_velocity": round(comment_vel, 4),
        "click_velocity": round(click_vel, 4),
        "age_hours": age_hours,
        "price": deal.price,
        "price_confidence": deal.price_confidence,
        "discount_percent": deal.discount_percent,
        "cashback_percent": deal.cashback_percent,
        "price_rank": deal.price_rank,
        "hot_score": score,
        "is_hot": is_hot,
        "hot_level": level,
        "heat_ratio": round(heat_ratio, 4),
        "site_velocity_index": (
            round(site_velocity_index, 4) if site_velocity_index is not None else None
        ),
    }


class ObservationLog:
    """Accumulates feature rows for one run, then appends them to today's JSONL."""

    def __init__(self, obs_dir: Path = DEFAULT_OBS_DIR) -> None:
        self.obs_dir = obs_dir
        self._rows: list[dict] = []

    def add(self, row: dict) -> None:
        self._rows.append(row)

    def flush(self, now: datetime) -> None:
        """Append accumulated rows to data/observations/<AET-date>.jsonl."""
        if not self._rows:
            return
        self.obs_dir.mkdir(parents=True, exist_ok=True)
        date = now.astimezone(_AET).strftime("%Y-%m-%d")
        path = self.obs_dir / f"{date}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            for row in self._rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        log.info("Logged %d observations to %s", len(self._rows), path.name)
        self._rows = []


# ---------------------------------------------------------------------------
# Maintenance: keep the committed observation log small and bounded.
#
# The feature log is what makes `.git` grow without limit — 15-18 MB of JSONL is
# appended and committed every ~5 min. Calibration/backtest only look back a few
# weeks, so we (1) gzip completed (immutable, past-day) files ~8-10x and
# (2) prune anything older than the retention window. The live pipeline only
# ever appends to *today's* uncompressed file, so compressing past days is safe.
# ---------------------------------------------------------------------------

DEFAULT_RETENTION_DAYS = 45


def file_date(path: Path) -> date | None:
    """AET date encoded in an observation filename (`.jsonl` or `.jsonl.gz`)."""
    name = path.name
    if name.endswith(".jsonl.gz"):
        name = name[: -len(".gz")]
    stem = name[: -len(".jsonl")] if name.endswith(".jsonl") else name
    try:
        return date.fromisoformat(stem)
    except ValueError:
        return None


def compress_completed(obs_dir: Path, now: datetime) -> list[Path]:
    """Gzip every completed (before-today, AET) ``*.jsonl`` file in ``obs_dir``.

    Today's file is left uncompressed because the pipeline keeps appending to it.
    Returns the list of newly created ``.jsonl.gz`` paths.
    """
    if not obs_dir.exists():
        return []
    today = now.astimezone(_AET).date()
    created: list[Path] = []
    for path in sorted(obs_dir.glob("*.jsonl")):
        fdate = file_date(path)
        if fdate is None or fdate >= today:
            continue
        gz_path = path.with_suffix(path.suffix + ".gz")
        with path.open("rb") as src, gzip.open(gz_path, "wb") as dst:
            dst.write(src.read())
        path.unlink()
        created.append(gz_path)
        log.info("Compressed %s -> %s", path.name, gz_path.name)
    return created


def prune_old(obs_dir: Path, now: datetime, retention_days: int) -> list[Path]:
    """Delete observation files older than ``retention_days`` (by filename date).

    Returns the list of removed paths.
    """
    if not obs_dir.exists() or retention_days <= 0:
        return []
    cutoff = now.astimezone(_AET).date() - timedelta(days=retention_days)
    removed: list[Path] = []
    for path in sorted([*obs_dir.glob("*.jsonl"), *obs_dir.glob("*.jsonl.gz")]):
        fdate = file_date(path)
        if fdate is not None and fdate < cutoff:
            path.unlink()
            removed.append(path)
            log.info("Pruned %s (older than %d days)", path.name, retention_days)
    return removed


def maintain(obs_dir: Path, now: datetime, retention_days: int) -> None:
    """Compress completed daily files, then prune anything past the window."""
    compress_completed(obs_dir, now)
    prune_old(obs_dir, now, retention_days)


def main(argv: list[str] | None = None) -> int:
    """CLI: compress completed observation files and prune old ones.

    Usage::

        bargain-hunter-maintain-obs [--obs-dir data/observations] [--retention-days 45]
    """
    import argparse
    from datetime import UTC

    parser = argparse.ArgumentParser(description="Compress + prune the observation log.")
    parser.add_argument("--obs-dir", type=Path, default=DEFAULT_OBS_DIR)
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    maintain(args.obs_dir, datetime.now(UTC), args.retention_days)
    return 0
