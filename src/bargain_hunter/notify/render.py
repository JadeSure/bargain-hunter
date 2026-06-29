"""Jinja2 template rendering for email digests."""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..models import Deal, Subscriber

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
_AET = ZoneInfo("Australia/Sydney")
SOURCE_LABELS = {
    "camelcamelcamel": "CamelCamelCamel",
    "ozbargain": "OzBargain",
}

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


class DealItem:
    """Bundles a deal with its track + reason string for template rendering."""

    def __init__(self, deal: Deal, track: str, reason: str = "", level: str | None = None) -> None:
        self.deal = deal
        self.track = track
        self.reason = reason
        self.level = level
        self.feedback_up_url: str | None = None
        self.feedback_down_url: str | None = None


def _sign(secret: str, deal_key: str, verdict: str, email: str) -> str:
    """Return a 32-char hex HMAC-SHA256 token covering deal+verdict+email."""
    msg = f"{deal_key}|{verdict}|{email}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:32]


def _unsubscribe_token(secret: str, email: str) -> str:
    """Return a 32-char hex HMAC-SHA256 token covering just the email."""
    msg = f"unsubscribe|{email}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:32]


def _feedback_url(
    base: str, secret: str, deal_key: str, verdict: str, email: str, title: str = ""
) -> str:
    token = _sign(secret, deal_key, verdict, email)
    url = f"{base}?d={quote(deal_key)}&v={verdict}&e={quote(email)}&t={token}"
    if title:
        url += f"&n={quote(title[:120])}"
    return url


def render_email(
    subscriber: Subscriber,
    items: list[DealItem],
) -> str:
    """Render the HTML email digest for one subscriber.

    If FEEDBACK_BASE_URL and FEEDBACK_HMAC_SECRET are set, the template renders
    per-deal 👍/👎 links with HMAC signatures; otherwise they are omitted.
    """
    tmpl = _env.get_template("email.html.j2")
    sent_at = datetime.now(UTC).astimezone(_AET).strftime("%d %b %Y %H:%M AEST")
    feedback_base = (os.environ.get("FEEDBACK_BASE_URL") or "").strip() or None
    hmac_secret = (os.environ.get("FEEDBACK_HMAC_SECRET") or "").strip() or None
    unsubscribe_base = (os.environ.get("UNSUBSCRIBE_BASE_URL") or "").strip() or None
    unsubscribe_secret = (os.environ.get("UNSUBSCRIBE_HMAC_SECRET") or "").strip() or None

    if feedback_base and hmac_secret and subscriber.email:
        for item in items:
            item.feedback_up_url = _feedback_url(
                feedback_base, hmac_secret, item.deal.key, "up", subscriber.email, item.deal.title
            )
            item.feedback_down_url = _feedback_url(
                feedback_base, hmac_secret, item.deal.key, "down", subscriber.email, item.deal.title
            )

    unsubscribe_url: str | None = None
    if unsubscribe_base and unsubscribe_secret and subscriber.email:
        token = _unsubscribe_token(unsubscribe_secret, subscriber.email)
        unsubscribe_url = (
            f"{unsubscribe_base}?e={quote(subscriber.email)}&t={token}"
        )

    return tmpl.render(
        subscriber=subscriber,
        deals=items,
        source_labels=SOURCE_LABELS,
        sent_at=sent_at,
        unsubscribe_url=unsubscribe_url,
    )
