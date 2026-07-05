"""Jinja2 template rendering for email digests."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..models import Deal, Subscriber
from .links import affiliate_url, get_amazon_affiliate_tag

log = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
_AET = ZoneInfo("Australia/Sydney")
SOURCE_LABELS = {
    "camelcamelcamel": "CamelCamelCamel",
    "ozbargain": "OzBargain",
}

_warned_missing_unsubscribe_config = False

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

    @property
    def affiliate_deal_url(self) -> str:
        """`deal.url` with an Amazon affiliate tag applied (env `AMAZON_AFFILIATE_TAG`)."""
        return affiliate_url(self.deal.url, get_amazon_affiliate_tag())

    @property
    def affiliate_merchant_url(self) -> str | None:
        """`deal.merchant_url` with an Amazon affiliate tag applied, if set."""
        if not self.deal.merchant_url:
            return None
        return affiliate_url(self.deal.merchant_url, get_amazon_affiliate_tag())


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


def build_unsubscribe_url(email: str) -> str | None:
    """Return the signed one-click unsubscribe URL for this email, or None.

    Reads UNSUBSCRIBE_BASE_URL / UNSUBSCRIBE_HMAC_SECRET from the environment.
    If either is unset, returns None (callers must degrade gracefully — omit
    the footer link and List-Unsubscribe headers) and logs a warning once per
    process so a missing config doesn't crash or spam logs every send.
    """
    global _warned_missing_unsubscribe_config
    base = (os.environ.get("UNSUBSCRIBE_BASE_URL") or "").strip()
    secret = (os.environ.get("UNSUBSCRIBE_HMAC_SECRET") or "").strip()
    if not base or not secret:
        if not _warned_missing_unsubscribe_config:
            log.warning(
                "UNSUBSCRIBE_BASE_URL / UNSUBSCRIBE_HMAC_SECRET not set — "
                "digests will be sent without unsubscribe links or headers."
            )
            _warned_missing_unsubscribe_config = True
        return None
    if not email:
        return None
    # Normalise casing before signing/encoding: the worker lowercases the `e=`
    # query param before reconstructing the HMAC, so a mixed-case address here
    # would otherwise produce a token that never verifies.
    email = email.strip().lower()
    token = _unsubscribe_token(secret, email)
    return f"{base}?e={quote(email)}&t={token}"


def render_email(
    subscriber: Subscriber,
    items: list[DealItem],
    cap_suppressed: int = 0,
) -> str:
    """Render the HTML email digest for one subscriber.

    If FEEDBACK_BASE_URL and FEEDBACK_HMAC_SECRET are set, the template renders
    per-deal 👍/👎 links with HMAC signatures; otherwise they are omitted.
    ``cap_suppressed`` > 0 adds a footer note that N more deals qualified today
    but were held back by the subscriber's daily cap.
    """
    tmpl = _env.get_template("email.html.j2")
    sent_at = datetime.now(UTC).astimezone(_AET).strftime("%d %b %Y %H:%M AEST")
    feedback_base = (os.environ.get("FEEDBACK_BASE_URL") or "").strip() or None
    hmac_secret = (os.environ.get("FEEDBACK_HMAC_SECRET") or "").strip() or None
    site_url = (
        os.environ.get("SITE_URL") or "https://bargain-hunter.sylvalume.online"
    ).strip().rstrip("/")

    if feedback_base and hmac_secret and subscriber.email:
        for item in items:
            item.feedback_up_url = _feedback_url(
                feedback_base, hmac_secret, item.deal.key, "up", subscriber.email, item.deal.title
            )
            item.feedback_down_url = _feedback_url(
                feedback_base, hmac_secret, item.deal.key, "down", subscriber.email, item.deal.title
            )

    unsubscribe_url = build_unsubscribe_url(subscriber.email) if subscriber.email else None

    return tmpl.render(
        subscriber=subscriber,
        deals=items,
        source_labels=SOURCE_LABELS,
        sent_at=sent_at,
        unsubscribe_url=unsubscribe_url,
        site_url=site_url,
        cap_suppressed=cap_suppressed,
    )
