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

import json
import logging
from datetime import datetime
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
) -> dict:
    """Build one feature row for a deal at decision time."""
    vote_vel, lifetime_vel = compute_vote_velocity(snapshots, cfg.window_minutes, now)
    comment_vel = compute_comment_velocity(snapshots, cfg.window_minutes, now)
    click_vel = compute_click_velocity(snapshots, cfg.window_minutes, now)
    score = compute_hot_score(deal, snapshots, cfg, now)

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
        "discount_percent": deal.discount_percent,
        "hot_score": score,
        "is_hot": is_hot,
        "hot_level": level,
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
