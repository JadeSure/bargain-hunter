"""Per-subscriber quiet-hours override on top of the global run config.

`main.py` resolves quiet hours per subscriber with this helper: a subscriber
can set their own "HH:MM" start/end (e.g. because they're in a different
routine than the maintainer's default), and an unset field falls back to the
global `settings.run` window. During a subscriber's quiet window their
notifications are queued (see `queue_store`) and drained into their first
digest after the window ends.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .config import RunConfig
from .models import Subscriber


def _minutes(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":")[:2])
    return h * 60 + m


def is_in_quiet_hours(subscriber: Subscriber, now: datetime, global_config: RunConfig) -> bool:
    """Return True if `now` falls within this subscriber's quiet-hours window.

    Resolution order: the subscriber's own `quiet_hours_start`/`quiet_hours_end`
    (both must be set to take effect) override the global
    `global_config.quiet_hours_start`/`quiet_hours_end`; if neither pair is
    fully set, quiet hours are disabled (returns False).

    Handles wrap-around midnight (e.g. 22:00-07:00).
    """
    if subscriber.quiet_hours_start and subscriber.quiet_hours_end:
        start_str, end_str = subscriber.quiet_hours_start, subscriber.quiet_hours_end
    else:
        start_str, end_str = global_config.quiet_hours_start, global_config.quiet_hours_end
    if not start_str or not end_str:
        return False

    tz = ZoneInfo(global_config.timezone)
    local = now.astimezone(tz)
    current = local.hour * 60 + local.minute
    start = _minutes(start_str)
    end = _minutes(end_str)
    if start > end:  # window wraps midnight, e.g. 22:00-07:00
        return current >= start or current < end
    return start <= current < end
