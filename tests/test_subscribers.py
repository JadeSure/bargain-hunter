"""Tests for Notion subscriber parsing."""

from bargain_hunter.subscribers import _parse_subscriber


def _props(**overrides) -> dict:
    base = {
        "Name": {"title": [{"plain_text": "Alice"}]},
        "Email": {"email": "alice@example.com"},
        "Telegram Chat ID": {"rich_text": []},
        "Active": {"checkbox": True},
        "Channels": {"multi_select": [{"name": "Email"}]},
        "Subscribe Hot Deals": {"checkbox": True},
        "Watch Keywords": {"rich_text": []},
        "Min Discount %": {"number": None},
        "Categories": {"multi_select": []},
        "Hot Level": {"select": None},
        "Max Alerts/Day": {"number": None},
        "Max Watch Alerts/Day": {"number": None},
        "Block Keywords": {"rich_text": []},
    }
    base.update(overrides)
    return base


def test_max_alerts_falls_back_to_settings_default_when_unset():
    """An empty "Max Alerts/Day" field should take the settings.yaml default."""
    sub = _parse_subscriber(_props(), default_max_alerts_per_day=25)
    assert sub.max_alerts_per_day == 25


def test_max_alerts_explicit_notion_value_overrides_default():
    sub = _parse_subscriber(
        _props(**{"Max Alerts/Day": {"number": 3}}), default_max_alerts_per_day=25
    )
    assert sub.max_alerts_per_day == 3


def test_max_alerts_uses_builtin_default_when_not_passed():
    sub = _parse_subscriber(_props())
    assert sub.max_alerts_per_day == 10


def test_quiet_hours_unset_by_default():
    sub = _parse_subscriber(_props())
    assert sub.quiet_hours_start is None
    assert sub.quiet_hours_end is None


def test_quiet_hours_parsed_when_present():
    sub = _parse_subscriber(
        _props(
            **{
                "Quiet Hours Start": {"rich_text": [{"plain_text": "22:00"}]},
                "Quiet Hours End": {"rich_text": [{"plain_text": "07:00"}]},
            }
        )
    )
    assert sub.quiet_hours_start == "22:00"
    assert sub.quiet_hours_end == "07:00"
