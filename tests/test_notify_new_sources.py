"""Digest rendering for the six new digital-deal sources (dealnews, slickdeals,
v2ex, openrouter, bank_rates, iknowthepilot).

Covers the defects an actual render caught: a missing `.badge.digital` CSS
rule and a "▲ 0" votes badge shown for every voteless source (both fixed in
templates/email.html.j2), plus the currency/price-badge/link cases these
sources are most likely to get wrong.
"""

from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote, urlsplit

from bargain_hunter.models import Deal, Subscriber
from bargain_hunter.notify.links import affiliate_url
from bargain_hunter.notify.render import SOURCE_LABELS, DealItem, _sign, render_email

SUBSCRIBER = Subscriber(name="Test", email="test@example.com")
NOW = datetime.now(UTC)


def _render(deal: Deal, track: str = "digital") -> str:
    return render_email(SUBSCRIBER, [DealItem(deal=deal, track=track)])


def test_bank_rates_no_price_badge_and_no_none_leak():
    deal = Deal(
        source="bank_rates",
        deal_id="ING-SAVMAX001",
        title="ING Savings Maximiser: 5.35% p.a. (was 4.90%)",
        url="https://www.ing.com.au/savings/savings-maximiser.html",
        currency="AUD",
        price=None,
        price_confidence=None,
        posted_at=NOW,
    )
    html = _render(deal)
    assert "None" not in html
    assert "badge price" not in html
    assert "5.35% p.a." in html


def test_bank_rates_bonus_points_title():
    deal = Deal(
        source="bank_rates",
        deal_id="Westpac-ALTVELBLK",
        title="Westpac Altitude Velocity Black: 150,000 bonus points (was 60,000)",
        url="https://www.westpac.com.au/credit-cards/altitude/velocity-black/",
        currency="AUD",
        price=None,
        price_confidence=None,
        posted_at=NOW,
    )
    html = _render(deal)
    assert "None" not in html
    assert "150,000 bonus points" in html


def test_dealnews_usd_price_gets_us_dollar_prefix():
    deal = Deal(
        source="dealnews",
        deal_id="dn1",
        title="Adobe Creative Cloud for $29.99/mo",
        url="https://www.dealnews.com/some-deal",
        price=29.99,
        was_price=59.99,
        price_confidence="high",
        currency="USD",
        posted_at=NOW,
    )
    html = _render(deal, track="watch")
    assert '<span class="badge price">US$29.99</span>' in html
    # The badge itself must not be a bare AUD-style "$29.99" (an AU reader
    # would misread that as dollars, not USD). The deal title is unaffected
    # and legitimately still says "$29.99" — only the badge is checked here.
    assert '<span class="badge price">$29.99</span>' not in html


def test_slickdeals_low_confidence_hides_price_badge():
    deal = Deal(
        source="slickdeals",
        deal_id="sd1",
        title="ChatGPT Plus 3 Months Free",
        url="https://slickdeals.net/f/thread",
        price=None,
        price_confidence=None,
        currency="USD",
        posted_at=NOW,
    )
    html = _render(deal, track="watch")
    assert "badge price" not in html


def test_v2ex_chinese_title_renders_without_mangling():
    deal = Deal(
        source="v2ex",
        deal_id="v1",
        title="【优惠】阿里云新用户三年 99 元套餐限时开抢",
        url="https://www.v2ex.com/t/999999",
        price=None,
        price_confidence=None,
        currency="CNY",
        posted_at=NOW,
    )
    html = _render(deal, track="watch")
    assert "badge price" not in html
    assert "【优惠】阿里云新用户三年 99 元套餐限时开抢" in html
    assert SOURCE_LABELS["v2ex"] in html


def test_openrouter_inline_us_dollar_not_doubled():
    deal = Deal(
        source="openrouter",
        deal_id="openai-gpt-5-mini",
        title="GPT-5 Mini: input US$0.15/M tokens (was US$0.30) — 50% cheaper",
        url="https://openrouter.ai/openai/gpt-5-mini",
        price=0.15,
        was_price=0.30,
        discount_percent=50.0,
        price_confidence=None,  # openrouter never sets this -> no separate price badge
        currency="USD",
        posted_at=NOW,
    )
    html = _render(deal)
    assert "US$US$" not in html
    assert "badge price" not in html
    assert "US$0.15/M tokens" in html


def test_iknowthepilot_aud_high_confidence_shows_plain_dollar():
    deal = Deal(
        source="iknowthepilot",
        deal_id="iktp1",
        title="Sydney to Tokyo Return from $649 (was $1,199)",
        url="https://www.iknowthepilot.com.au/deals/syd-tokyo",
        price=649.0,
        was_price=1199.0,
        price_confidence="high",
        currency="AUD",
        posted_at=NOW,
    )
    html = _render(deal, track="watch")
    assert "$649.00" in html
    assert "US$649.00" not in html


def test_digital_track_badge_has_matching_css_rule():
    deal = Deal(
        source="openrouter",
        deal_id="m1",
        title="Some model now free",
        url="https://openrouter.ai/x/y",
        posted_at=NOW,
    )
    html = _render(deal, track="digital")
    assert '<span class="badge digital">DIGITAL</span>' in html
    # The template embeds its own <style>; the class it uses must be defined there.
    assert ".badge.digital" in html


def test_voteless_source_hides_zero_votes_badge():
    deal = Deal(
        source="bank_rates",
        deal_id="x",
        title="Some Bank: 5% p.a.",
        url="https://bank.example/product",
        posted_at=NOW,
    )
    html = _render(deal)
    assert "▲ 0" not in html
    assert "▲" not in html


def test_all_six_new_sources_have_labels_not_raw_slugs():
    for source in (
        "dealnews",
        "slickdeals",
        "v2ex",
        "openrouter",
        "bank_rates",
        "iknowthepilot",
    ):
        deal = Deal(
            source=source,
            deal_id="id1",
            title="Some deal title",
            url="https://example.com/deal",
            posted_at=NOW,
        )
        html = _render(deal)
        assert SOURCE_LABELS[source] in html
        assert f">{source}<" not in html


def test_affiliate_url_leaves_non_amazon_domains_untouched():
    urls = [
        "https://openrouter.ai/nvidia/nemotron-3.5-lightning:free",
        "https://www.ing.com.au/savings/savings-maximiser.html",
        "https://www.dealnews.com/some-deal",
    ]
    for url in urls:
        assert affiliate_url(url, "bargainhunter-22") == url


def test_openrouter_colon_deal_key_survives_feedback_link_round_trip(monkeypatch):
    monkeypatch.setenv("FEEDBACK_BASE_URL", "https://feedback.example.workers.dev")
    monkeypatch.setenv("FEEDBACK_HMAC_SECRET", "s3cret")
    deal = Deal(
        source="openrouter",
        deal_id="nvidia-nemotron-3.5-lightning:free",  # "/" and "~" sanitised, ":" kept
        title="Nemotron 3.5 Lightning: now free on OpenRouter (US$0/M tokens)",
        url="https://openrouter.ai/nvidia/nemotron-3.5-lightning:free",
        posted_at=NOW,
    )
    item = DealItem(deal=deal, track="digital")
    render_email(SUBSCRIBER, [item])

    assert item.feedback_up_url is not None
    query = parse_qs(urlsplit(item.feedback_up_url).query)
    decoded_key = unquote(query["d"][0])
    assert decoded_key == deal.key == "openrouter:nvidia-nemotron-3.5-lightning:free"
    # The token must verify against the key exactly as decoded off the URL.
    expected = _sign("s3cret", decoded_key, "up", SUBSCRIBER.email)
    assert query["t"][0] == expected
