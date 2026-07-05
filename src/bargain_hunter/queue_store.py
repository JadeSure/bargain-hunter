"""Quiet-hours notification queue (deferral instead of silent drop).

During quiet hours the pipeline used to skip notifications entirely, so deals
that trended overnight were lost. Instead, would-be notifications are persisted
here (per subscriber: the deal payload, track, tier, reason, queue timestamp)
and drained into the first digest after quiet hours end.

Layout of queued_notifications.json:
  {
    "entries": [
      {"subscriber_email": "...", "deal": {...Deal fields...}, "track": "hot",
       "level": "great", "reason": "▲ 42 votes", "queued_at": "2026-07-06T13:00:00+00:00"},
      ...
    ]
  }

The file contains subscriber emails, so unlike deals_state.json it is
git-ignored and persisted only via the Actions hot cache (best-effort — a lost
cache just means a lost overnight queue, never a crash or a duplicate send:
drain re-checks the Sent Log).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from .models import Deal
from .state import _atomic_write_json

log = logging.getLogger(__name__)

DEFAULT_QUEUE_PATH = Path("data/queued_notifications.json")


class QueuedNotification(BaseModel):
    """One deferred notification for one subscriber."""

    subscriber_email: str
    deal: Deal
    track: str  # "hot" | "watch" | "mixed"
    level: str | None = None
    reason: str = ""
    queued_at: datetime

    def is_stale(self, now: datetime, max_age_hours: float) -> bool:
        """True if this entry should be dropped at drain time.

        Stale = queued longer ago than ``max_age_hours``, or the deal itself
        has expired in the meantime.
        """
        age_hours = (now - self.queued_at).total_seconds() / 3600
        if age_hours > max_age_hours:
            return True
        if self.deal.expired:
            return True
        return self.deal.expiry is not None and self.deal.expiry <= now


class NotificationQueue:
    """Disk-backed queue of notifications deferred during quiet hours."""

    def __init__(self, path: Path = DEFAULT_QUEUE_PATH) -> None:
        self.path = path
        # (subscriber_email, deal_key) -> QueuedNotification
        self._entries: dict[tuple[str, str], QueuedNotification] = {}

    def load(self) -> None:
        """Load the queue from disk; a missing or corrupt file is an empty queue."""
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Notification queue unreadable (%s) — starting empty.", exc)
            return
        for item in raw.get("entries", []):
            try:
                entry = QueuedNotification.model_validate(item)
            except ValidationError:
                continue
            self._entries[(entry.subscriber_email, entry.deal.key)] = entry
        if self._entries:
            log.info("Loaded %d queued notification(s).", len(self._entries))

    def save(self) -> None:
        payload = {
            "entries": [e.model_dump(mode="json") for e in self._entries.values()],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(self.path, payload)

    def add(
        self,
        subscriber_email: str,
        deal: Deal,
        track: str,
        level: str | None,
        reason: str,
        now: datetime | None = None,
    ) -> None:
        """Queue (or refresh) a deferred notification.

        Re-queuing the same (subscriber, deal) on a later quiet-hours run
        updates the deal payload / tier / reason but keeps the original
        ``queued_at``, so the staleness clock starts at first sighting.
        """
        now = now or datetime.now(UTC)
        key = (subscriber_email, deal.key)
        existing = self._entries.get(key)
        self._entries[key] = QueuedNotification(
            subscriber_email=subscriber_email,
            deal=deal,
            track=track,
            level=level,
            reason=reason,
            queued_at=existing.queued_at if existing else now,
        )

    def entries_for(self, subscriber_email: str) -> list[QueuedNotification]:
        return [e for e in self._entries.values() if e.subscriber_email == subscriber_email]

    def drain_for(
        self,
        subscriber_email: str,
        now: datetime,
        max_age_hours: float,
    ) -> list[QueuedNotification]:
        """Return this subscriber's queued entries that survive staleness filtering."""
        return [
            e
            for e in self.entries_for(subscriber_email)
            if not e.is_stale(now, max_age_hours)
        ]

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
