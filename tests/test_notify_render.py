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
    )
    subscriber = Subscriber(name="Test", email="test@example.com")

    html = render_email(subscriber, [DealItem(deal=deal, track="watch")])

    assert "CamelCamelCamel" in html
    assert "OzBargain" not in html
