"""Read subscribers and their preferences from Notion (PRD §7)."""

from __future__ import annotations

import logging
import os

from notion_client import Client

from .models import Subscriber

log = logging.getLogger(__name__)

# Notion property names — must match the DB schema defined in PRD §7.
_P_NAME = "Name"
_P_EMAIL = "Email"
_P_TELEGRAM = "Telegram Chat ID"
_P_ACTIVE = "Active"
_P_CHANNELS = "Channels"
_P_HOT = "Subscribe Hot Deals"
_P_KEYWORDS = "Watch Keywords"
_P_MIN_DISCOUNT = "Min Discount %"
_P_CATEGORIES = "Categories"
_P_MAX_ALERTS = "Max Alerts/Day"
_P_MAX_WATCH_ALERTS = "Max Watch Alerts/Day"
_P_BLOCK_KEYWORDS = "Block Keywords"


def _text(prop: dict) -> str:
    """Extract plain text from a Notion rich_text or title property."""
    items = prop.get("rich_text") or prop.get("title") or []
    return "".join(t.get("plain_text", "") for t in items).strip()


def _email(prop: dict) -> str | None:
    return prop.get("email") or None


def _checkbox(prop: dict) -> bool:
    return bool(prop.get("checkbox", False))


def _multiselect(prop: dict) -> list[str]:
    return [o["name"] for o in prop.get("multi_select", [])]


def _number(prop: dict, default: float | None = None) -> float | None:
    v = prop.get("number")
    return float(v) if v is not None else default


def _parse_keywords(raw: str) -> list[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


def fetch_subscribers(
    notion: Client,
    db_id: str,
) -> list[Subscriber]:
    """Query the Subscribers DB and return active subscribers."""
    results: list[Subscriber] = []
    cursor = None
    while True:
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        resp = notion.request(path=f"databases/{db_id}/query", method="POST", body=body)
        for page in resp.get("results", []):
            props = page.get("properties", {})
            try:
                sub = _parse_subscriber(props)
            except Exception as exc:
                log.warning("Skipping malformed subscriber page %s: %s", page.get("id"), exc)
                continue
            if sub.active and (sub.email or sub.telegram_chat_id):
                results.append(sub)
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    log.info("Fetched %d active subscribers from Notion.", len(results))
    return results


def _parse_subscriber(props: dict) -> Subscriber:
    name = _text(props.get(_P_NAME, {}))
    email = _email(props.get(_P_EMAIL, {}))
    telegram = _text(props.get(_P_TELEGRAM, {})) or None
    active = _checkbox(props.get(_P_ACTIVE, {}))
    channels = _multiselect(props.get(_P_CHANNELS, {}))
    subscribe_hot = _checkbox(props.get(_P_HOT, {}))
    keywords_raw = _text(props.get(_P_KEYWORDS, {}))
    watch_keywords = _parse_keywords(keywords_raw)
    min_discount = _number(props.get(_P_MIN_DISCOUNT, {}))
    categories = _multiselect(props.get(_P_CATEGORIES, {}))
    max_alerts = int(_number(props.get(_P_MAX_ALERTS, {}), default=10) or 10)
    max_watch_alerts = int(_number(props.get(_P_MAX_WATCH_ALERTS, {}), default=10) or 10)
    block_keywords_raw = _text(props.get(_P_BLOCK_KEYWORDS, {}))
    block_keywords = _parse_keywords(block_keywords_raw)

    return Subscriber(
        name=name or "Unknown",
        email=email,
        telegram_chat_id=telegram,
        active=active,
        channels=channels,
        subscribe_hot=subscribe_hot,
        watch_keywords=watch_keywords,
        block_keywords=block_keywords,
        min_discount_percent=min_discount,
        categories=categories,
        max_alerts_per_day=max_alerts,
        max_watch_alerts_per_day=max_watch_alerts,
    )


def make_notion_client() -> Client:
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise RuntimeError("NOTION_TOKEN environment variable not set.")
    return Client(auth=token, notion_version="2022-06-28")
