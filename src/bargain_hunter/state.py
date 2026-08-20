"""Deal state persistence: rolling vote snapshots used to compute velocity.

Layout of deals_state.json:
  {
    "<source>:<deal_id>": [
      {"ts": "2026-06-19T00:00:00+00:00", "votes_pos": 10, "votes_neg": 0, "comment_count": 3},
      ...
    ],
    ...
  }

The hot-path (every 5-min run) reads from / writes to this file; the Actions
workflow additionally caches it between runs (best-effort) and commits it once
per day as a calibration seed (see PRD §10.1).

Snapshots older than `retention_hours` are pruned on every write to keep the
file size bounded.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import Deal, DealSnapshot
from .scoring import compute_vote_velocity

log = logging.getLogger(__name__)


def _aware(dt: datetime) -> datetime:
    """Coerce a possibly-naive datetime (e.g. hand-edited into the committed
    state file) to UTC-aware, so later arithmetic against `datetime.now(UTC)`
    can't raise `TypeError: can't subtract offset-naive and offset-aware
    datetimes`. Same treatment as strategy_hunter/sources/rss.py::_parse_pub_date."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON via a same-directory temp file + os.replace so a crash mid-write
    can't corrupt the target (a partial write would otherwise force cold-start)."""
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise

DEFAULT_STATE_PATH = Path("data/deals_state.json")
DEFAULT_RETENTION_HOURS = 24


class StateStore:
    def __init__(
        self,
        path: Path = DEFAULT_STATE_PATH,
        retention_hours: float = DEFAULT_RETENTION_HOURS,
    ) -> None:
        self.path = path
        self.retention_hours = retention_hours
        # key -> list[DealSnapshot] (oldest first)
        self._data: dict[str, list[DealSnapshot]] = {}
        self._first_seen: dict[str, datetime] = {}
        # Deals suppressed on first sighting for being stale (cold-start guard).
        # Kept "seeded" rather than dropped: on a later run they can still earn
        # a notification if they show renewed hot-candidacy-level velocity.
        self._seeded: dict[str, datetime] = {}
        self._cold_start = False
        # Event-day adaptive baseline: hour-of-day (Australia/Sydney, 0-23) ->
        # {"ewma": float, "updated_at": datetime}. Empty when never seeded.
        self._baseline_seeded_at: datetime | None = None
        self._baseline_hours: dict[int, dict] = {}
        # source -> last successful fetch time, for poll_interval_minutes gating
        # on sources slower-cadence than the 5-min hot-path loop.
        self._last_fetch: dict[str, datetime] = {}
        # Generic per-feature snapshot store (e.g. "llm_prices", "bank_rates") —
        # each feature keeps whatever JSON-able dict it needs between runs. Not
        # to be confused with `snapshots()` below (per-deal vote-velocity history).
        self._feature_snapshots: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load state from disk. If missing or corrupt, treat as cold start."""
        if not self.path.exists():
            log.info("State file not found — cold start.")
            self._cold_start = True
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("State file unreadable (%s) — cold start.", exc)
            self._cold_start = True
            return

        for key, snapshots in raw.get("snapshots", {}).items():
            parsed = []
            for s in snapshots:
                try:
                    parsed.append(
                        DealSnapshot(
                            ts=_aware(datetime.fromisoformat(s["ts"])),
                            votes_pos=s["votes_pos"],
                            votes_neg=s["votes_neg"],
                            comment_count=s["comment_count"],
                            click_count=s.get("click_count", 0),
                        )
                    )
                except (KeyError, ValueError):
                    continue
            if parsed:
                self._data[key] = parsed

        for key, ts_str in raw.get("first_seen", {}).items():
            with contextlib.suppress(ValueError):
                self._first_seen[key] = _aware(datetime.fromisoformat(ts_str))

        for key, ts_str in raw.get("seeded", {}).items():
            with contextlib.suppress(ValueError):
                self._seeded[key] = _aware(datetime.fromisoformat(ts_str))

        baseline = raw.get("site_baseline") or {}
        with contextlib.suppress(ValueError):
            seeded_at_str = baseline.get("seeded_at")
            if seeded_at_str:
                self._baseline_seeded_at = _aware(datetime.fromisoformat(seeded_at_str))
        for hour_str, bucket in (baseline.get("hours") or {}).items():
            try:
                hour = int(hour_str)
                self._baseline_hours[hour] = {
                    "ewma": float(bucket["ewma"]),
                    "updated_at": _aware(datetime.fromisoformat(bucket["updated_at"])),
                }
            except (KeyError, ValueError, TypeError):
                continue

        for src, ts_str in (raw.get("last_fetch") or {}).items():
            with contextlib.suppress(ValueError):
                self._last_fetch[src] = _aware(datetime.fromisoformat(ts_str))

        self._feature_snapshots = raw.get("feature_snapshots") or {}

        self._cold_start = raw.get("cold_start", False)
        log.info("Loaded state: %d deals, cold_start=%s", len(self._data), self._cold_start)

    def save(self) -> None:
        """Prune old snapshots and write state to disk."""
        self._prune()
        payload = {
            "cold_start": False,  # after the first successful save, cold start is done
            "snapshots": {
                key: [
                    {
                        "ts": s.ts.isoformat(),
                        "votes_pos": s.votes_pos,
                        "votes_neg": s.votes_neg,
                        "comment_count": s.comment_count,
                        "click_count": s.click_count,
                    }
                    for s in snaps
                ]
                for key, snaps in self._data.items()
            },
            "first_seen": {key: ts.isoformat() for key, ts in self._first_seen.items()},
            "seeded": {key: ts.isoformat() for key, ts in self._seeded.items()},
            "site_baseline": {
                "seeded_at": (
                    self._baseline_seeded_at.isoformat() if self._baseline_seeded_at else None
                ),
                "hours": {
                    str(hour): {
                        "ewma": bucket["ewma"],
                        "updated_at": bucket["updated_at"].isoformat(),
                    }
                    for hour, bucket in self._baseline_hours.items()
                },
            },
            "last_fetch": {src: ts.isoformat() for src, ts in self._last_fetch.items()},
            "feature_snapshots": self._feature_snapshots,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(self.path, payload)
        log.info("Saved state: %d deals.", len(self._data))

    # ------------------------------------------------------------------
    # Snapshot ingestion
    # ------------------------------------------------------------------

    def record(self, deal: Deal, now: datetime | None = None) -> None:
        """Append a snapshot for this deal and record first-seen time."""
        now = now or datetime.now(UTC)
        key = deal.key
        snap = DealSnapshot(
            ts=now,
            votes_pos=deal.votes_pos,
            votes_neg=deal.votes_neg,
            comment_count=deal.comment_count,
            click_count=deal.click_count,
        )
        self._data.setdefault(key, []).append(snap)
        self._first_seen.setdefault(key, now)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def snapshots(self, key: str) -> list[DealSnapshot]:
        return self._data.get(key, [])

    def first_seen(self, key: str) -> datetime | None:
        return self._first_seen.get(key)

    def is_cold_start(self) -> bool:
        return self._cold_start

    def is_new_to_system(self, key: str) -> bool:
        """True if we have seen this deal for the first time this run."""
        return key not in self._first_seen

    # ------------------------------------------------------------------
    # Poll-cadence gating (sources slower than the 5-min hot-path loop)
    # ------------------------------------------------------------------

    def due_for_fetch(self, source: str, interval_minutes: float, now: datetime) -> bool:
        """True if `source` has never been fetched, or its last fetch is older
        than `interval_minutes`."""
        last = self._last_fetch.get(source)
        if last is None:
            return True
        return (now - last).total_seconds() >= interval_minutes * 60

    def mark_fetched(self, source: str, now: datetime) -> None:
        self._last_fetch[source] = now

    # ------------------------------------------------------------------
    # Generic per-feature snapshots (e.g. LLM prices, bank rates)
    # ------------------------------------------------------------------

    def snapshot(self, key: str) -> dict:
        """Return the feature snapshot stored under `key`, or {} if never set.

        Distinct from `snapshots()` above (per-deal vote-velocity history) —
        this is an arbitrary JSON-able dict a source keeps between runs.
        """
        return self._feature_snapshots.get(key, {})

    def set_snapshot(self, key: str, value: dict) -> None:
        self._feature_snapshots[key] = value

    # ------------------------------------------------------------------
    # Event-day adaptive baseline (site-wide vote velocity)
    # ------------------------------------------------------------------

    def site_baseline(self, hour: int) -> tuple[float, datetime] | None:
        """Return (ewma, updated_at) for the given hour-of-day bucket, or None."""
        bucket = self._baseline_hours.get(hour)
        if bucket is None:
            return None
        return bucket["ewma"], bucket["updated_at"]

    def baseline_age_days(self, now: datetime | None = None) -> float:
        """Days since the baseline was first seeded; 0.0 if never seeded."""
        if self._baseline_seeded_at is None:
            return 0.0
        now = now or datetime.now(UTC)
        return max((now - self._baseline_seeded_at).total_seconds() / 86400, 0.0)

    def update_site_baseline(
        self,
        sample: float,
        hour: int,
        now: datetime,
        half_life_days: float,
        sample_clamp: float,
    ) -> None:
        """Update the hour-of-day bucket with a new site-velocity-index sample.

        First-ever update seeds `seeded_at`. An empty bucket is seeded directly
        with the sample; otherwise the sample is clamped to `sample_clamp *
        ewma` (only when ewma > 0, so an event-day spike can't poison the
        baseline in one run) before a time-aware EWMA update.
        """
        if self._baseline_seeded_at is None:
            self._baseline_seeded_at = now

        bucket = self._baseline_hours.get(hour)
        if bucket is None:
            self._baseline_hours[hour] = {"ewma": sample, "updated_at": now}
            return

        ewma = bucket["ewma"]
        clamped_sample = sample
        if ewma > 0:
            clamped_sample = min(sample, sample_clamp * ewma)

        dt_days = max((now - bucket["updated_at"]).total_seconds() / 86400, 0.0)
        alpha = 1 - 0.5 ** (dt_days / half_life_days) if half_life_days > 0 else 1.0
        new_ewma = ewma + alpha * (clamped_sample - ewma)
        self._baseline_hours[hour] = {"ewma": new_ewma, "updated_at": now}

    # ------------------------------------------------------------------
    # Cold-start / age guard (FR8)
    # ------------------------------------------------------------------

    def should_notify(
        self,
        deal: Deal,
        ignore_older_than_hours: float,
        is_first_sighting: bool,
        now: datetime | None = None,
        snapshots: list[DealSnapshot] | None = None,
        window_minutes: int | None = None,
        min_votes_gain_per_window: int | None = None,
    ) -> bool:
        """Return False during cold start, or if a newly-seen deal is stale.

        ``is_first_sighting`` MUST be captured *before* this run's snapshots are
        recorded (see ``main.run``). Otherwise ``record()`` would have already
        populated first-seen for every deal and the staleness guard below could
        never fire. On the first run we suppress everything (cold start). After
        that, a deal we are seeing for the first time is only eligible if it
        isn't already old inventory.

        A deal suppressed here for being stale on first sighting is not killed
        outright — it is marked "seeded". On later runs it stays suppressed
        unless it shows renewed, hot-candidacy-level window vote-gain (pass
        ``snapshots`` / ``window_minutes`` / ``min_votes_gain_per_window`` from
        the caller's scoring config to evaluate that gate); once it clears the
        gate once it graduates and is treated like any other known deal from
        then on. This keeps the cold-start spam guard without permanently
        burying a deal that later goes viral.
        """
        now = now or datetime.now(UTC)
        if self._cold_start:
            return False
        if is_first_sighting:
            if deal.posted_at is None:
                return True
            age = (now - deal.posted_at).total_seconds() / 3600
            if age <= ignore_older_than_hours:
                return True
            self._seeded[deal.key] = now
            return False
        if deal.key in self._seeded:
            if not snapshots or window_minutes is None or min_votes_gain_per_window is None:
                return False
            vote_vel, _ = compute_vote_velocity(snapshots, window_minutes, now)
            window_gain = vote_vel * (window_minutes / 60)
            if window_gain >= min_votes_gain_per_window:
                del self._seeded[deal.key]
                return True
            return False
        return True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(hours=self.retention_hours)
        for key in list(self._data):
            self._data[key] = [s for s in self._data[key] if s.ts >= cutoff]
            if not self._data[key]:
                del self._data[key]
        for key, first_seen in list(self._first_seen.items()):
            if key not in self._data and first_seen < cutoff:
                del self._first_seen[key]
        for key, seeded_at in list(self._seeded.items()):
            if key not in self._data and seeded_at < cutoff:
                del self._seeded[key]
