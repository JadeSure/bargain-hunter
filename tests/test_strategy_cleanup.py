"""Tests for corpus retention pruning and the failure-alert decision."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from strategy_hunter.cleanup import prune_corpus
from strategy_hunter.main import _maybe_alert


def _post(raw_dir: Path, source: str, pid: str, fetched_at: datetime) -> Path:
    d = raw_dir / source
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{pid}.json"
    p.write_text(
        json.dumps(
            {
                "source": source,
                "post_id": pid,
                "url": "http://x",
                "title": "t",
                "fetched_at": fetched_at.isoformat(),
            }
        ),
        encoding="utf-8",
    )
    return p


def test_prune_removes_only_old_posts(tmp_path):
    now = datetime(2026, 6, 27, tzinfo=UTC)
    fresh = _post(tmp_path, "reddit", "new1", now - timedelta(days=5))
    old = _post(tmp_path, "reddit", "old1", now - timedelta(days=90))
    deleted = prune_corpus(tmp_path, retention_days=60, now=now)
    assert deleted == [old]
    assert fresh.exists()
    assert not old.exists()


def test_prune_disabled_with_nonpositive_retention(tmp_path):
    now = datetime(2026, 6, 27, tzinfo=UTC)
    old = _post(tmp_path, "reddit", "old1", now - timedelta(days=900))
    assert prune_corpus(tmp_path, retention_days=0, now=now) == []
    assert old.exists()


def test_prune_keeps_undated_posts(tmp_path):
    d = tmp_path / "reddit"
    d.mkdir(parents=True)
    p = d / "weird.json"
    p.write_text(json.dumps({"source": "reddit", "post_id": "x"}), encoding="utf-8")
    now = datetime(2026, 6, 27, tzinfo=UTC)
    assert prune_corpus(tmp_path, retention_days=1, now=now) == []
    assert p.exists()


def test_maybe_alert_silent_on_success(monkeypatch):
    called = {}

    def fake_send(subject, body):
        called["yes"] = True

    monkeypatch.setattr(
        "bargain_hunter.notify.email.send_maintainer_alert", fake_send, raising=False
    )
    _maybe_alert({"fetched": 10, "errors": []})
    assert "yes" not in called


def test_maybe_alert_fires_on_errors(monkeypatch):
    captured = {}

    def fake_send(subject, body):
        captured["subject"] = subject
        captured["body"] = body

    monkeypatch.setattr(
        "bargain_hunter.notify.email.send_maintainer_alert", fake_send, raising=False
    )
    _maybe_alert({"fetched": 0, "relevant": 0, "new": 0, "pruned": 0,
                  "errors": ["reddit fetch failed: boom"]})
    assert "FAILED" in captured["subject"]
    assert "boom" in captured["body"]
