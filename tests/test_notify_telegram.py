import json
from datetime import UTC, datetime

import httpx

from bargain_hunter.models import Deal, Subscriber
from bargain_hunter.notify import telegram as tg
from bargain_hunter.notify.render import DealItem
from bargain_hunter.notify.telegram import MAX_MESSAGE_CHARS, TelegramSender, render_messages

SUB = Subscriber(name="T", email="t@example.com", telegram_chat_id="12345", channels=["Telegram"])


def _item(deal_id="1", title="Sample <Deal> & Co", **kw) -> DealItem:
    deal = Deal(
        source="ozbargain",
        deal_id=deal_id,
        title=title,
        url=f"https://www.ozbargain.com.au/node/{deal_id}",
        posted_at=datetime.now(UTC),
        **kw,
    )
    return DealItem(deal=deal, track="hot", reason="Hot: 40 votes/h", level="top")


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_render_escapes_html_and_shows_price():
    item = _item(price=99.0, was_price=149.0, discount_percent=33.6, votes_pos=120)
    [msg] = render_messages(SUB, [item])
    assert "Sample &lt;Deal&gt; &amp; Co" in msg
    assert "$99.00 (was $149.00) · -34% · ▲ 120" in msg
    assert "<b>TOP · HOT</b>" in msg
    assert "1 deal for you" in msg


def test_render_includes_signed_feedback_links(monkeypatch):
    monkeypatch.setenv("FEEDBACK_BASE_URL", "https://fb.test/")
    monkeypatch.setenv("FEEDBACK_HMAC_SECRET", "s3cret")
    [msg] = render_messages(SUB, [_item()])
    assert 'href="https://fb.test/?d=ozbargain%3A1&amp;v=up&amp;e=t%40example.com&amp;t=' in msg


def test_render_splits_long_digest_at_deal_boundaries():
    items = [_item(deal_id=str(i), title="x" * 300) for i in range(30)]
    messages = render_messages(SUB, items, cap_suppressed=2)
    assert len(messages) > 1
    assert all(len(m) <= MAX_MESSAGE_CHARS for m in messages)
    assert sum(m.count("/node/") for m in messages) == 30 * 2  # title link + source link
    assert "2 more held back" in messages[-1]


def test_sender_disabled_without_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    sender = TelegramSender()
    assert not sender.enabled
    assert sender.send_digest(SUB, [_item()]) is False


def test_sender_posts_to_bot_api():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    sender = TelegramSender(token="abc", client=_client(handler))
    assert sender.send_digest(SUB, [_item()]) is True
    assert len(calls) == 1
    assert calls[0].url.path == "/botabc/sendMessage"
    body = json.loads(calls[0].content)
    assert body["chat_id"] == "12345"
    assert body["parse_mode"] == "HTML"


def test_sender_retries_once_on_429(monkeypatch):
    monkeypatch.setattr(tg.time, "sleep", lambda s: None)
    responses = iter(
        [
            httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 1}}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    sender = TelegramSender(token="abc", client=_client(lambda r: next(responses)))
    assert sender.send_digest(SUB, [_item()]) is True


def test_sender_fails_when_bot_blocked():
    def handler(request):
        return httpx.Response(403, json={"ok": False, "description": "bot was blocked"})

    sender = TelegramSender(token="abc", client=_client(handler))
    assert sender.send_digest(SUB, [_item()]) is False


def test_sender_requires_linked_chat():
    sender = TelegramSender(token="abc", client=_client(lambda r: httpx.Response(200)))
    unlinked = SUB.model_copy(update={"telegram_chat_id": None})
    assert sender.send_digest(unlinked, [_item()]) is False


def test_dry_run_sends_nothing():
    def handler(request):
        raise AssertionError("dry run must not hit the network")

    sender = TelegramSender(token="abc", dry_run=True, client=_client(handler))
    assert sender.send_digest(SUB, [_item()]) is True
