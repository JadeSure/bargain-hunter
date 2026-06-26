"""Corpus retention: drop raw posts older than the retention window.

The collector writes one JSON per post and never overwrites unchanged ones, so
the ``raw/`` tree grows without bound. Pruning keeps it to a rolling window —
old time-limited deal threads stop being useful once expired, and evergreen
playbooks are re-harvested while still live on the source.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)


def _post_timestamp(data: dict) -> datetime | None:
    """Best-effort age of a stored post: prefer fetched_at, fall back to created_at."""
    for key in ("fetched_at", "created_at"):
        raw = data.get(key)
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            continue
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return None


def prune_corpus(
    raw_dir: Path, retention_days: int, now: datetime | None = None
) -> list[Path]:
    """Delete raw post JSON older than ``retention_days``. Returns deleted paths.

    A non-positive ``retention_days`` disables pruning. Files we can't read or
    date are left in place rather than risking deletion of good data.
    """
    if retention_days <= 0 or not raw_dir.exists():
        return []
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=retention_days)
    deleted: list[Path] = []
    for path in sorted(raw_dir.glob("*/*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("prune: skipping unreadable %s: %s", path, exc)
            continue
        ts = _post_timestamp(data)
        if ts is None:
            log.warning("prune: no timestamp on %s, keeping it", path)
            continue
        if ts < cutoff:
            try:
                path.unlink()
                deleted.append(path)
            except OSError as exc:
                log.warning("prune: could not delete %s: %s", path, exc)
    if deleted:
        log.info("prune: removed %d posts older than %d days.", len(deleted), retention_days)
    return deleted
