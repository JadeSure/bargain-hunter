"""Telegram delivery via the Bot API (optional channel; email stays the default).

Enabled only when ``TELEGRAM_BOT_TOKEN`` is set. Subscribers link their chat
through the portal (``/start <token>`` deep link handled by portal-worker), which
writes their chat id into the Notion "Telegram Chat ID" property.

Messages use Telegram's HTML parse mode and a compact one-block-per-deal layout.
Digests longer than Telegram's 4096-char limit are split across messages.
"""

from __future__ import annotations

import html
import logging
import os
import time

import httpx

from ..models import Deal, Subscriber
from .render import SOURCE_LABELS, DealItem, attach_feedback_urls, get_site_url

log = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
MAX_MESSAGE_CHARS = 4096
MAX_RETRY_AFTER_S = 10


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _link(url: str, label: str) -> str:
    return f'<a href="{_esc(url)}">{_esc(label)}</a>'


def _price_line(deal: Deal) -> str:
    symbol = "$" if deal.currency == "AUD" else f"{deal.currency} "
    parts: list[str] = []
    if deal.price is not None:
        price = f"{symbol}{deal.price:,.2f}"
        if deal.was_price:
            price += f" (was {symbol}{deal.was_price:,.2f})"
        parts.append(price)
    if deal.discount_percent:
        parts.append(f"-{deal.discount_percent:.0f}%")
    if deal.cashback_percent:
        parts.append(f"+{deal.cashback_percent:g}% cashback")
    if deal.votes_pos:
        parts.append(f"▲ {deal.votes_pos}")
    return " · ".join(parts)


def format_item(item: DealItem) -> str:
    """Render one deal as a Telegram-HTML block."""
    deal = item.deal
    badge = item.track.upper()
    if item.level:
        badge = f"{item.level.upper()} · {badge}"
    lines = [f"<b>{_esc(badge)}</b>", _link(item.affiliate_deal_url, deal.title)]
    price = _price_line(deal)
    if price:
        lines.append(_esc(price))
    if item.reason:
        lines.append(f"<i>{_esc(item.reason)}</i>")

    actions = [_link(item.affiliate_deal_url, SOURCE_LABELS.get(deal.source, deal.source))]
    if item.affiliate_merchant_url:
        actions.append(_link(item.affiliate_merchant_url, "Go to deal"))
    if item.feedback_up_url and item.feedback_down_url:
        actions.append(f"{_link(item.feedback_up_url, '👍')} {_link(item.feedback_down_url, '👎')}")
    lines.append(" · ".join(actions))
    return "\n".join(lines)


def render_messages(
    subscriber: Subscriber, items: list[DealItem], cap_suppressed: int = 0
) -> list[str]:
    """Render a digest as one or more Telegram messages, each ≤ MAX_MESSAGE_CHARS.

    Deals are never split mid-block: a typical digest of ≤10 deals is a single
    message; a long one rolls over to a new message at a deal boundary.
    """
    attach_feedback_urls(subscriber, items)
    n = len(items)
    header = f"🛒 <b>Bargain Hunter</b> — {n} deal{'s' if n != 1 else ''} for you"
    footer_parts = [_link(f"{get_site_url()}/deals", "Browse all live deals")]
    if cap_suppressed > 0:
        footer_parts.append(
            f"{cap_suppressed} more held back by your daily cap "
            f"({_link(f'{get_site_url()}/portal', 'settings')})"
        )
    footer = "\n".join(footer_parts)

    blocks = [format_item(item)[:MAX_MESSAGE_CHARS] for item in items]
    messages: list[str] = []
    current = header
    for block in blocks:
        candidate = f"{current}\n\n{block}"
        if len(candidate) > MAX_MESSAGE_CHARS:
            messages.append(current)
            current = block
        else:
            current = candidate
    candidate = f"{current}\n\n{footer}"
    if len(candidate) > MAX_MESSAGE_CHARS:
        messages.extend([current, footer])
    else:
        messages.append(candidate)
    return messages


class TelegramSender:
    def __init__(
        self,
        token: str | None = None,
        dry_run: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        if token is None:
            token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.token = token.strip()
        self.dry_run = dry_run
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def send_digest(
        self,
        subscriber: Subscriber,
        items: list[DealItem],
        cap_suppressed: int = 0,
    ) -> bool:
        """Send a digest to the subscriber's linked chat. Returns True on success."""
        if not self.enabled or not subscriber.telegram_chat_id:
            return False

        messages = render_messages(subscriber, items, cap_suppressed=cap_suppressed)
        if self.dry_run:
            log.info(
                "[DRY RUN] Would Telegram %s (%d deals, %d message(s)).",
                subscriber.ref,
                len(items),
                len(messages),
            )
            return True

        client = self._client or httpx.Client(timeout=20)
        try:
            for text in messages:
                if not self._send(client, subscriber, text):
                    return False
        finally:
            if self._client is None:
                client.close()
        log.info("Telegrammed %s: %d deals.", subscriber.ref, len(items))
        return True

    def _send(self, client: httpx.Client, subscriber: Subscriber, text: str) -> bool:
        payload = {
            "chat_id": subscriber.telegram_chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        url = f"{API_BASE}/bot{self.token}/sendMessage"
        for attempt in range(2):
            try:
                resp = client.post(url, json=payload)
            except httpx.HTTPError as exc:
                # The exception text can embed the request URL, which carries the token.
                log.error("Telegram send to %s failed: %s", subscriber.ref, type(exc).__name__)
                return False
            if resp.status_code == 200:
                return True
            retry_after = _retry_after(resp)
            if resp.status_code == 429 and attempt == 0 and retry_after <= MAX_RETRY_AFTER_S:
                time.sleep(retry_after)
                continue
            # 403 = the user blocked the bot / never pressed Start; 400 = bad chat id.
            log.error(
                "Telegram send to %s failed: HTTP %d %s",
                subscriber.ref,
                resp.status_code,
                _description(resp),
            )
            return False
        return False


def _retry_after(resp: httpx.Response) -> int:
    try:
        return int(resp.json().get("parameters", {}).get("retry_after", MAX_RETRY_AFTER_S + 1))
    except (ValueError, AttributeError):
        return MAX_RETRY_AFTER_S + 1


def _description(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("description", ""))[:200]
    except ValueError:
        return ""
