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
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import Deal, DealSnapshot

log = logging.getLogger(__name__)

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
        self._cold_start = False

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
                            ts=datetime.fromisoformat(s["ts"]),
                            votes_pos=s["votes_pos"],
                            votes_neg=s["votes_neg"],
                            comment_count=s["comment_count"],
                        )
                    )
                except (KeyError, ValueError):
                    continue
            if parsed:
                self._data[key] = parsed

        for key, ts_str in raw.get("first_seen", {}).items():
            with contextlib.suppress(ValueError):
                self._first_seen[key] = datetime.fromisoformat(ts_str)

        self._cold_start = raw.get("cold_start", False)
        log.info(
            "Loaded state: %d deals, cold_start=%s", len(self._data), self._cold_start
        )

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
                    }
                    for s in snaps
                ]
                for key, snaps in self._data.items()
            },
            "first_seen": {
                key: ts.isoformat() for key, ts in self._first_seen.items()
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
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
    # Cold-start / age guard (FR8)
    # ------------------------------------------------------------------

    def should_notify(self, deal: Deal, ignore_older_than_hours: float) -> bool:
        """Return False during cold start, or if the deal pre-dates the system.

        On cold start we record snapshots but suppress notifications entirely.
        After cold start, deals whose posted_at pre-dates our first-seen window
        are treated as old inventory and not pushed.
        """
        if self._cold_start:
            return False
        key = deal.key
        first = self._first_seen.get(key)
        if first is None:
            # Seen for the first time this run — not cold start, so allow it
            # only if the deal itself isn't stale.
            if deal.posted_at is None:
                return True
            age = (datetime.now(UTC) - deal.posted_at).total_seconds() / 3600
            return age <= ignore_older_than_hours
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
