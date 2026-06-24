"""Throttle maintainer alert emails to avoid spam on repeated failures.

State is persisted in data/alert_state.json (included in Actions Cache) so
consecutive-failure counting survives across the 5-minute runs.

Policy:
  - Only alert after `min_consecutive_failures` failures in a row.
  - After an alert is sent, suppress further alerts for `cooldown_hours`.
  - A clean run resets the consecutive-failure counter (but not the cooldown,
    so a flapping service doesn't fire again immediately after one good run).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_PATH = Path("data/alert_state.json")


class AlertThrottle:
    def __init__(
        self,
        path: Path = DEFAULT_PATH,
        min_consecutive_failures: int = 3,
        cooldown_hours: float = 2.0,
    ) -> None:
        self.path = path
        self.min_consecutive = min_consecutive_failures
        self.cooldown_hours = cooldown_hours
        self._failures = 0
        self._last_sent: datetime | None = None

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._failures = int(raw.get("consecutive_failures", 0))
            ts = raw.get("last_sent")
            self._last_sent = datetime.fromisoformat(ts) if ts else None
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            log.warning("Alert state unreadable (%s) — starting fresh.", exc)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "consecutive_failures": self._failures,
            "last_sent": self._last_sent.isoformat() if self._last_sent else None,
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def record_success(self) -> None:
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1
        log.info("Consecutive failures: %d / %d", self._failures, self.min_consecutive)

    def record_sent(self, now: datetime) -> None:
        self._last_sent = now

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------

    def should_alert(self, now: datetime | None = None) -> bool:
        """Return True if an alert should be sent right now."""
        now = now or datetime.now(UTC)
        if self._failures < self.min_consecutive:
            return False
        if self._last_sent is not None:
            elapsed_hours = (now - self._last_sent).total_seconds() / 3600
            if elapsed_hours < self.cooldown_hours:
                log.info(
                    "Alert suppressed — cooldown active (%.1fh / %.1fh elapsed).",
                    elapsed_hours,
                    self.cooldown_hours,
                )
                return False
        return True
