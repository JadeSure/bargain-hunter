from datetime import UTC, datetime

from bargain_hunter.models import Deal, Subscriber
from bargain_hunter.notify.render import DealItem, render_email


def test_render_email_uses_source_label():
    deal = Deal(
        source="camelcamelcamel",
        deal_id="B000123",
        title="Test Product",
        url="https://au.camelcamelcamel.com/product/B000123",
        merchant_url="https://www.amazon.com.au/dp/B000123",
        posted_at=datetime.now(UTC),
        price=19.99,
        price_confidence="high",
    )
    subscriber = Subscriber(name="Test", email="test@example.com")

    html = render_email(subscriber, [DealItem(deal=deal, track="watch")])

    assert "CamelCamelCamel" in html
    assert "OzBargain" not in html


def test_render_email_shows_high_confidence_price():
    deal = Deal(
        source="ozbargain",
        deal_id="1",
        title="Simple Product $49.99 @ Store",
        url="https://www.ozbargain.com.au/node/1",
        posted_at=datetime.now(UTC),
        price=49.99,
        price_confidence="high",
    )
    subscriber = Subscriber(name="Test", email="test@example.com")

    html = render_email(subscriber, [DealItem(deal=deal, track="hot")])

    assert "$49.99" in html


def test_render_email_hides_low_confidence_price():
    deal = Deal(
        source="ozbargain",
        deal_id="2",
        title="Everyday Market: 30% Cashback (Capped at $150, Min Spend $50)",
        url="https://www.ozbargain.com.au/node/2",
        posted_at=datetime.now(UTC),
        price=150.0,
        price_confidence="low",
    )
    subscriber = Subscriber(name="Test", email="test@example.com")

    html = render_email(subscriber, [DealItem(deal=deal, track="hot")])

    assert "$150.00" not in html
