"""Jinja2 template rendering for email digests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..models import Deal, Subscriber

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
_AET = ZoneInfo("Australia/Sydney")

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


class DealItem:
    """Bundles a deal with its track + reason string for template rendering."""

    def __init__(self, deal: Deal, track: str, reason: str = "") -> None:
        self.deal = deal
        self.track = track
        self.reason = reason


def render_email(
    subscriber: Subscriber,
    items: list[DealItem],
) -> str:
    """Render the HTML email digest for one subscriber."""
    tmpl = _env.get_template("email.html.j2")
    sent_at = datetime.now(UTC).astimezone(_AET).strftime("%d %b %Y %H:%M AEST")
    return tmpl.render(subscriber=subscriber, deals=items, sent_at=sent_at)
