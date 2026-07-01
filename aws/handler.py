"""AWS Lambda entry point — a serverless backup for the GitHub Actions `hunt.yml`.

This runs the *unmodified* ``bargain_hunter`` pipeline on an EventBridge 5-minute
schedule. Because Lambda's filesystem is read-only except ``/tmp`` (and ``/tmp``
is wiped on cold starts), the hot-path state that ``hunt.yml`` keeps in the
Actions Cache is instead synced to/from S3 around each run:

    S3  ──download──▶  /tmp/run/data/{deals_state,alert_state}.json
                       /tmp/run/data/observations/<AET-date>.jsonl
                            │
                            ▼  bargain_hunter.main.run() (relative `data/...` paths)
                            │
    S3  ◀──upload────  updated state + appended observations

The application code is untouched: it reads/writes ``data/...`` relative to the
current working directory, so the handler just ``chdir``s into a writable
``/tmp`` working dir whose ``data/`` we seed from S3. ``settings.yaml`` and the
Jinja templates resolve via package-relative absolute paths, so they are
unaffected by the ``chdir`` and are read straight from the deployment package.

Dedup / "don't email the same deal twice" lives in the Notion Sent Log, which is
shared with the Actions runner — so this backup will not double-send even if it
briefly overlaps a real Actions run. Velocity state (``deals_state.json``) is,
however, independent per runner, so this is intended as a *failover* (schedule
DISABLED by default) rather than a permanent second runner.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("aws.handler")
# boto3 is chatty at INFO during downloads/uploads.
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

_AET = ZoneInfo("Australia/Sydney")

STATE_BUCKET = os.environ["STATE_BUCKET"]
STATE_PREFIX = os.environ.get("STATE_PREFIX", "state").strip("/")
SETTINGS_PATH = os.environ.get("SETTINGS_PATH", "/var/task/config/settings.yaml")

WORK_DIR = Path("/tmp/run")
DATA_DIR = WORK_DIR / "data"
OBS_DIR = DATA_DIR / "observations"

# Single-file state objects mirrored verbatim between S3 and local disk.
STATE_FILES = ("deals_state.json", "alert_state.json")

_s3 = boto3.client("s3")


def _s3_key(*parts: str) -> str:
    return "/".join(p.strip("/") for p in (STATE_PREFIX, *parts) if p)


def _download(key: str, dest: Path) -> bool:
    """Best-effort download. Missing object => cold-start for that file."""
    try:
        _s3.download_file(STATE_BUCKET, key, str(dest))
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in ("404", "NoSuchKey", "403"):
            log.info("No existing s3://%s/%s (%s) — treating as cold.", STATE_BUCKET, key, code)
            return False
        raise


def _upload(src: Path, key: str) -> None:
    if not src.exists():
        return
    _s3.upload_file(str(src), STATE_BUCKET, key)
    log.info("Uploaded %s -> s3://%s/%s", src.name, STATE_BUCKET, key)


def _obs_filenames(now: datetime) -> list[str]:
    """Observation files we care about this run: today's and yesterday's (AET).

    Yesterday is fetched too so a run that fires just after the AET midnight
    rollover still appends to / does not clobber the prior day's file.
    """
    today = now.astimezone(_AET)
    from datetime import timedelta

    yesterday = today - timedelta(days=1)
    return [f"{yesterday:%Y-%m-%d}.jsonl", f"{today:%Y-%m-%d}.jsonl"]


def _seed_state(now: datetime) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OBS_DIR.mkdir(parents=True, exist_ok=True)
    for name in STATE_FILES:
        _download(_s3_key(name), DATA_DIR / name)
    for name in _obs_filenames(now):
        _download(_s3_key("observations", name), OBS_DIR / name)


def _persist_state(now: datetime) -> None:
    for name in STATE_FILES:
        _upload(DATA_DIR / name, _s3_key(name))
    # Upload only the observation files this run may have touched.
    for name in _obs_filenames(now):
        _upload(OBS_DIR / name, _s3_key("observations", name))


def handler(event: dict | None = None, context: object | None = None) -> dict:
    """Lambda entry point. Returns the run summary (counts only, no PII)."""
    # Imported here (not at module top) so import errors surface in the run logs
    # with a clear traceback rather than as an opaque init failure.
    from bargain_hunter.config import load_settings
    from bargain_hunter.main import _alert_if_needed, _heartbeat, run

    now = datetime.now(UTC)

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(WORK_DIR)  # make relative `data/...` writes land in /tmp/run/data
    _seed_state(now)

    settings = load_settings(Path(SETTINGS_PATH))
    dry_run = bool((event or {}).get("dry_run")) or settings.run.dry_run
    force = bool((event or {}).get("force"))

    if dry_run:
        log.info("=== DRY RUN: no emails sent, Notion not written ===")

    summary: dict = {}
    try:
        summary = run(settings, dry_run=dry_run, force=force)
        _alert_if_needed(summary, settings, now)
        if not dry_run:
            _heartbeat(summary)
    finally:
        # Always persist — mirrors hunt.yml's `if: always()` cache save so a
        # mid-run failure still keeps the snapshots/alert counter we gathered.
        try:
            _persist_state(now)
        except Exception:  # noqa: BLE001 - persistence must not mask a run error
            log.exception("Failed to persist state to S3")

    log.info("Run summary: %s", summary)
    return summary
