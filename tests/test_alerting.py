"""Maintainer alert policy: one failing source never mails; real failures mail at most daily."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bargain_hunter import main as mod
from bargain_hunter.config import load_settings

SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.yaml"
T0 = datetime(2026, 10, 3, 2, 0, tzinfo=UTC)


@pytest.fixture
def sent(monkeypatch, tmp_path):
    """Run each test against a fresh data/alert_state.json and capture alerts."""
    monkeypatch.chdir(tmp_path)
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        mod, "send_maintainer_alert", lambda subject, body: calls.append((subject, body))
    )
    return calls


@pytest.fixture
def settings():
    return load_settings(SETTINGS_PATH)


def _summary(deals: int = 110, errors=(), source_errors=()) -> dict:
    return {
        "deals_fetched": deals, "hot_deals": 1, "notifications_sent": 0, "cold_start": False,
        "errors": list(errors), "source_errors": list(source_errors),
    }


def _runs(n: int, summary: dict, settings, start: datetime = T0) -> None:
    for i in range(n):
        mod._alert_if_needed(summary, settings, start + timedelta(minutes=5 * i))


def test_configured_policy_is_one_hour_then_daily(settings):
    alerting = settings.alerting
    assert (alerting.min_consecutive_failures, alerting.cooldown_hours) == (12, 24.0)


def test_one_source_failing_every_run_never_mails(sent, settings):
    # The 2026-10-01..03 shape: ~110 deals per run, v2ex failing each time.
    v2ex = "v2ex fetch failed: could not convert string to float: ''"
    _runs(500, _summary(source_errors=[v2ex]), settings)
    assert sent == []


def test_every_source_failing_still_mails_once_a_day(sent, settings):
    dead = _summary(deals=0, errors=["0 deals fetched — 9 source(s) failed."],
                    source_errors=["OzBargain fetch failed: timeout"])
    _runs(11, dead, settings)
    assert sent == []  # under an hour of failures: could be a blip
    _runs(1, dead, settings, start=T0 + timedelta(minutes=55))
    assert len(sent) == 1
    assert "OzBargain fetch failed" in sent[0][1]  # source detail rides along
    _runs(280, dead, settings, start=T0 + timedelta(hours=1))  # rest of the day
    assert len(sent) == 1
    _runs(1, dead, settings, start=T0 + timedelta(hours=25))
    assert len(sent) == 2


def test_a_clean_run_resets_the_count(sent, settings):
    bad = _summary(errors=["Dedup load failed: boom"])
    _runs(11, bad, settings)
    _runs(1, _summary(), settings, start=T0 + timedelta(minutes=55))
    _runs(11, bad, settings, start=T0 + timedelta(hours=1))
    assert sent == []


def test_a_crash_loop_mails_once_per_cooldown(sent, settings):
    for i in range(280):  # ~23h of crashing every 5 minutes
        mod._alert_on_crash(settings, T0 + timedelta(minutes=5 * i), "Traceback ...")
    assert [s for s, _ in sent] == ["Unhandled exception (12 consecutive)"]
