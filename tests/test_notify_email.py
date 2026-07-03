import hashlib
import hmac
from datetime import UTC, datetime
from urllib.parse import quote

from bargain_hunter.models import Deal, Subscriber
from bargain_hunter.notify.email import EmailSender
from bargain_hunter.notify.render import DealItem, build_unsubscribe_url


def _sample_item() -> DealItem:
    deal = Deal(
        source="ozbargain",
        deal_id="1",
        title="Sample Deal",
        url="https://www.ozbargain.com.au/node/1",
        posted_at=datetime.now(UTC),
    )
    return DealItem(deal=deal, track="hot")


def test_build_unsubscribe_url_is_deterministic(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://worker.test/auth/unsubscribe")
    monkeypatch.setenv("UNSUBSCRIBE_HMAC_SECRET", "s3cret")

    url_a = build_unsubscribe_url("user@example.com")
    url_b = build_unsubscribe_url("user@example.com")

    assert url_a == url_b
    assert url_a is not None
    assert url_a.startswith("https://worker.test/auth/unsubscribe?e=user%40example.com&t=")


def test_build_unsubscribe_url_changes_per_email(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://worker.test/auth/unsubscribe")
    monkeypatch.setenv("UNSUBSCRIBE_HMAC_SECRET", "s3cret")

    url_a = build_unsubscribe_url("a@example.com")
    url_b = build_unsubscribe_url("b@example.com")

    assert url_a != url_b


def test_build_unsubscribe_url_none_when_unset(monkeypatch):
    monkeypatch.delenv("UNSUBSCRIBE_BASE_URL", raising=False)
    monkeypatch.delenv("UNSUBSCRIBE_HMAC_SECRET", raising=False)

    assert build_unsubscribe_url("user@example.com") is None


def test_build_unsubscribe_url_normalises_email_case(monkeypatch):
    # portal-worker's unsubscribe.ts lowercases the `e=` query param before
    # recomputing the HMAC over "unsubscribe|<email>", so the token we embed
    # must be signed over the same lowercased form or verification fails for
    # any subscriber whose Notion email contains uppercase letters.
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://worker.test/auth/unsubscribe")
    monkeypatch.setenv("UNSUBSCRIBE_HMAC_SECRET", "s3cret")

    mixed_case_url = build_unsubscribe_url("User@Example.com")
    lowercase_url = build_unsubscribe_url("user@example.com")

    assert mixed_case_url == lowercase_url
    assert mixed_case_url == (
        "https://worker.test/auth/unsubscribe?e="
        + quote("user@example.com")
        + "&t="
        + hmac.new(b"s3cret", b"unsubscribe|user@example.com", hashlib.sha256).hexdigest()[:32]
    )


def test_send_digest_adds_list_unsubscribe_headers(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_BASE_URL", "https://worker.test/auth/unsubscribe")
    monkeypatch.setenv("UNSUBSCRIBE_HMAC_SECRET", "s3cret")
    monkeypatch.setenv("SMTP_USERNAME", "bot@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")

    sent_messages = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, *args, **kwargs):
            pass

        def sendmail(self, from_addr, to_addrs, msg_string):
            sent_messages.append(msg_string)

    monkeypatch.setattr("bargain_hunter.notify.email.smtplib.SMTP", FakeSMTP)

    subscriber = Subscriber(name="Test", email="user@example.com")
    sender = EmailSender()
    ok = sender.send_digest(subscriber, [_sample_item()])

    assert ok
    assert len(sent_messages) == 1
    expected_prefix = "List-Unsubscribe: <https://worker.test/auth/unsubscribe?e=user%40example.com&t="
    assert expected_prefix in sent_messages[0]
    assert "List-Unsubscribe-Post: List-Unsubscribe=One-Click" in sent_messages[0]


def test_send_digest_omits_headers_without_unsubscribe_config(monkeypatch):
    monkeypatch.delenv("UNSUBSCRIBE_BASE_URL", raising=False)
    monkeypatch.delenv("UNSUBSCRIBE_HMAC_SECRET", raising=False)
    monkeypatch.setenv("SMTP_USERNAME", "bot@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")

    sent_messages = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, *args, **kwargs):
            pass

        def sendmail(self, from_addr, to_addrs, msg_string):
            sent_messages.append(msg_string)

    monkeypatch.setattr("bargain_hunter.notify.email.smtplib.SMTP", FakeSMTP)

    subscriber = Subscriber(name="Test", email="user@example.com")
    sender = EmailSender()
    ok = sender.send_digest(subscriber, [_sample_item()])

    assert ok
    assert len(sent_messages) == 1
    assert "List-Unsubscribe" not in sent_messages[0]
