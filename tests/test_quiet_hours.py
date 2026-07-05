"""Tests for the per-subscriber quiet-hours override helper."""

from datetime import UTC, datetime

from bargain_hunter.config import RunConfig
from bargain_hunter.models import Subscriber
from bargain_hunter.quiet_hours import is_in_quiet_hours


def _sub(**kw) -> Subscriber:
    defaults = dict(name="Alice")
    defaults.update(kw)
    return Subscriber(**defaults)


def _global(**kw) -> RunConfig:
    return RunConfig(**kw)


# 2026-07-06T12:00 AEST == 2026-07-06T02:00 UTC (AEST = UTC+10, no DST in winter)
_NOON_AET_UTC = datetime(2026, 7, 6, 2, 0, tzinfo=UTC)
_LATE_NIGHT_AET_UTC = datetime(2026, 7, 6, 13, 0, tzinfo=UTC)  # 23:00 AEST


def test_no_quiet_hours_configured_anywhere():
    sub = _sub()
    cfg = _global()
    assert is_in_quiet_hours(sub, _LATE_NIGHT_AET_UTC, cfg) is False


def test_uses_global_default_when_subscriber_unset():
    sub = _sub()
    cfg = _global(quiet_hours_start="22:00", quiet_hours_end="07:00")
    assert is_in_quiet_hours(sub, _LATE_NIGHT_AET_UTC, cfg) is True
    assert is_in_quiet_hours(sub, _NOON_AET_UTC, cfg) is False


def test_subscriber_override_takes_precedence():
    # Subscriber wants a narrower midnight-4am window, ignoring the global 22:00-07:00.
    sub = _sub(quiet_hours_start="00:00", quiet_hours_end="04:00")
    cfg = _global(quiet_hours_start="22:00", quiet_hours_end="07:00")
    # 23:00 AEST, outside the subscriber's 00:00-04:00 override.
    assert is_in_quiet_hours(sub, _LATE_NIGHT_AET_UTC, cfg) is False


def test_subscriber_override_wraps_midnight():
    sub = _sub(quiet_hours_start="22:00", quiet_hours_end="02:00")
    cfg = _global()
    assert is_in_quiet_hours(sub, _LATE_NIGHT_AET_UTC, cfg) is True  # 23:00 AEST
    assert is_in_quiet_hours(sub, _NOON_AET_UTC, cfg) is False


def test_partial_subscriber_override_falls_back_to_global():
    # Only one of the two fields set on the subscriber -> falls back to global for both.
    sub = _sub(quiet_hours_start="00:00", quiet_hours_end=None)
    cfg = _global(quiet_hours_start="22:00", quiet_hours_end="07:00")
    assert is_in_quiet_hours(sub, _LATE_NIGHT_AET_UTC, cfg) is True
