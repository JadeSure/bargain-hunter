"""Tests for the generic RSS/Atom digital-deal feed source, against frozen fixtures.

dealnews_sample.xml, v2ex_sample.xml and iknowthepilot_sample.xml are trimmed
from real live fetches (2026-08-20). slickdeals_sample.xml is hand-written from
the documented field inventory in docs/GLOBAL_DEALS_PLAN.md — the live feed
403s from this machine (Cloudflare challenge), consistent with that document's
note that Slickdeals 403s readily even from CI.
"""

from datetime import UTC, datetime
from pathlib import Path

import httpx

from bargain_hunter.sources import feed_deals as mod
from bargain_hunter.sources.feed_deals import FeedDealsSource

FIXTURES = Path(__file__).parent / "fixtures"

RSS_ITEM = (
    '<?xml version="1.0"?><rss version="2.0"><channel>'
    "<item><title>{title}</title><link>{link}</link><description>{desc}</description>"
    "<pubDate>Mon, 01 Jun 2026 10:00:00 +0000</pubDate><guid>{guid}</guid></item>"
    "</channel></rss>"
)


def _dealnews():
    return FeedDealsSource(name="dealnews", feed_urls=[], currency="USD").parse(
        (FIXTURES / "dealnews_sample.xml").read_text(encoding="utf-8")
    )


def _slickdeals():
    return FeedDealsSource(name="slickdeals", feed_urls=[], currency="USD").parse(
        (FIXTURES / "slickdeals_sample.xml").read_text(encoding="utf-8")
    )


def _v2ex():
    return FeedDealsSource(name="v2ex", feed_urls=[], currency="CNY").parse(
        (FIXTURES / "v2ex_sample.xml").read_text(encoding="utf-8")
    )


def _iknowthepilot():
    return FeedDealsSource(name="iknowthepilot", feed_urls=[], currency="AUD").parse(
        (FIXTURES / "iknowthepilot_sample.xml").read_text(encoding="utf-8")
    )


# -- RSS 2.0 parse -------------------------------------------------------------


def test_parses_rss_items():
    deals = _dealnews()
    assert len(deals) == 4
    assert all(d.source == "dealnews" for d in deals)
    assert all(d.deal_id and d.title and d.url for d in deals)


def test_rss_categories_and_currency():
    # Fixture has 2 items; the SuperGrok one is dated Dec 2025 (~8 months old)
    # and is dropped by the default staleness filter — see
    # test_stale_item_dropped_and_logged below. Only NordVPN (Aug 2026) survives.
    deals = _slickdeals()
    assert len(deals) == 1
    assert all(d.categories == ["Software"] for d in deals)
    assert all(d.currency == "USD" for d in deals)


# -- Atom parse (V2EX) ----------------------------------------------------------


def test_parses_atom_entries():
    # 2 of the fixture's 3 keyword-matching items, not 3: the third is
    # "别急着薅羊毛，先看看 mirasim 的隐私协议", a scam warning that uses the
    # 羊毛 vocabulary while offering nothing, and _DEFAULT_TITLE_BLOCK now
    # rejects it. See test_v2ex_title_block_matches_the_hand_classified_live_sample.
    deals = _v2ex()
    assert len(deals) == 2
    assert all(d.source == "v2ex" for d in deals)
    assert all(d.currency == "CNY" for d in deals)
    boc = {d.title: d for d in deals}["中银香港 boc + 10 元羊毛"]
    assert boc.url == "https://www.v2ex.com/t/1235521#reply0"


# -- dealnews:price + currency attribute preferred over the title regex --------


def test_structured_price_preferred_over_title_regex():
    deals = {d.title: d for d in _dealnews()}
    # Title says "$10", the structured dealnews:price element says 9.97.
    windows = deals["Microsoft Windows 11 Pro Lifetime License for $10 + digital delivery"]
    assert windows.price == 9.97
    assert windows.currency == "USD"
    assert windows.price_confidence == "high"  # structured field, not the title regex


def test_structured_price_used_when_it_matches_title_too():
    deals = {d.title: d for d in _dealnews()}
    malwarebytes = deals[
        "Malwarebytes Standard Premium Security 3-Device 1-Year"
        " Antivirus Software for $13 + download"
    ]
    assert malwarebytes.price == 13.0
    assert malwarebytes.price_confidence == "high"


def test_item_with_no_structured_price_falls_back_to_none():
    deals = {d.title: d for d in _dealnews()}
    sale = deals["StackSocial Deal Days Sale: Up to 96% off + shipping varies"]
    assert sale.price is None
    assert sale.discount_percent == 96.0
    assert sale.price_confidence is None  # no dealnews:price element on this item


# -- tz-aware timestamps throughout ---------------------------------------------


def test_timestamps_are_timezone_aware():
    for deals in (_dealnews(), _slickdeals(), _v2ex(), _iknowthepilot()):
        for d in deals:
            assert d.posted_at is not None
            assert d.posted_at.tzinfo is not None
            assert d.posted_at.utcoffset().total_seconds() == 0


def test_dealnews_expiry_parsed_and_tz_aware():
    deals = {d.title: d for d in _dealnews()}
    sale = deals["StackSocial Deal Days Sale: Up to 96% off + shipping varies"]
    assert sale.expiry is not None
    assert sale.expiry.tzinfo is not None


# -- region locking --------------------------------------------------------------


def test_region_block_pattern_drops_item():
    xml = RSS_ITEM.format(
        title="VPN 2-year plan", link="https://x.example/1", desc="US only, sorry.", guid="g1"
    )
    src = FeedDealsSource(name="dealnews", feed_urls=[], block_patterns=["US only"])
    assert src.parse(xml) == []


def test_region_allow_pattern_overrides_block():
    xml = RSS_ITEM.format(
        title="VPN 2-year plan",
        link="https://x.example/1",
        desc="US only, but also available worldwide.",
        guid="g1",
    )
    # RSS_ITEM's fixed pubDate predates the default staleness cutoff — disable
    # it here since this test is about region-pattern precedence, not age.
    src = FeedDealsSource(
        name="dealnews",
        feed_urls=[],
        block_patterns=["US only"],
        allow_patterns=["worldwide"],
        max_item_age_hours=None,
    )
    deals = src.parse(xml)
    assert len(deals) == 1


# -- fetch: one dead feed does not lose the others' items -----------------------


def test_403_on_one_feed_does_not_lose_others(monkeypatch):
    dealnews_xml = (FIXTURES / "dealnews_sample.xml").read_text(encoding="utf-8")

    def fake_get(url, **kwargs):
        req = httpx.Request("GET", url)
        if "dead" in url:
            return httpx.Response(403, request=req)
        return httpx.Response(200, text=dealnews_xml, request=req)

    monkeypatch.setattr(mod.httpx, "get", fake_get)
    src = FeedDealsSource(
        name="dealnews",
        feed_urls=["https://example.com/dead-feed", "https://example.com/ok-feed"],
        request_delay_seconds=0,
    )
    deals = src.fetch()
    assert len(deals) == 4  # only the working feed's items, none lost


# -- fetch: cross-query de-dupe by Deal.key --------------------------------------


def test_cross_query_dedupe_by_key(monkeypatch):
    xml = RSS_ITEM.format(
        title="Same deal every query", link="https://x.example/1", desc="", guid="same-guid"
    )

    def fake_get(url, **kwargs):
        return httpx.Response(200, text=xml, request=httpx.Request("GET", url))

    monkeypatch.setattr(mod.httpx, "get", fake_get)
    # RSS_ITEM's fixed pubDate predates the default staleness cutoff — disable
    # it here since this test is about cross-query dedupe, not age.
    src = FeedDealsSource(
        name="slickdeals",
        feed_urls=["https://example.com/q=a", "https://example.com/q=b"],
        request_delay_seconds=0,
        max_item_age_hours=None,
    )
    deals = src.fetch()
    assert len(deals) == 1


# -- iknowthepilot: AUD currency, but still title-regex priced -------------------


def test_iknowthepilot_is_aud_with_real_price_confidence():
    deals = _iknowthepilot()
    assert len(deals) == 5
    assert all(d.currency == "AUD" for d in deals)
    tokyo_title = "Tokyo Time? Jetstar Flights Have Dropped to just $576 return"
    tokyo = {d.title: d for d in deals}[tokyo_title]
    assert tokyo.price == 576.0
    # AUD title-regex price -> real price_display_confidence check, not a
    # blanket None: an unambiguous single-price title reads "high".
    assert tokyo.price_confidence == "high"


def test_foreign_currency_title_regex_prices_stay_unconfirmed():
    # A "$" on a USD/CNY price would misread as AUD, so price_confidence
    # stays None for these even when a price was extracted from the title.
    for deals in (_slickdeals(), _v2ex()):
        assert all(d.price_confidence is None for d in deals)


# -- staleness filter: drop months/years-old items at parse time -----------------


def test_stale_item_dropped_and_logged(caplog):
    # SuperGrok (pubDate Dec 2025, ~8 months old) is older than the 30-day
    # default cutoff and is dropped; NordVPN (Aug 2026) survives.
    with caplog.at_level("INFO"):
        deals = _slickdeals()
    assert [d.title for d in deals] == ["NordVPN 2-Year Plan for $2.99/mo + 3 months free"]
    assert "dropped 1 stale item" in caplog.text


def test_item_older_than_cutoff_is_dropped():
    xml = RSS_ITEM.format(title="Old deal", link="https://x.example/1", desc="", guid="g1")
    src = FeedDealsSource(name="dealnews", feed_urls=[], max_item_age_hours=48)
    # RSS_ITEM's fixed pubDate is 2026-06-01T10:00Z; anchor "now" 49h later
    # (just past the 48h cutoff) for a deterministic, non-flaky assertion.
    now = datetime(2026, 6, 3, 11, 0, 0, tzinfo=UTC)
    assert src.parse(xml, now=now) == []


def test_item_within_cutoff_is_kept():
    xml = RSS_ITEM.format(title="Fresh deal", link="https://x.example/1", desc="", guid="g1")
    src = FeedDealsSource(name="dealnews", feed_urls=[], max_item_age_hours=48)
    now = datetime(2026, 6, 3, 9, 0, 0, tzinfo=UTC)  # 47h after pubDate
    assert len(src.parse(xml, now=now)) == 1


def test_max_item_age_hours_none_disables_filter():
    xml = RSS_ITEM.format(title="Ancient deal", link="https://x.example/1", desc="", guid="g1")
    src = FeedDealsSource(name="dealnews", feed_urls=[], max_item_age_hours=None)
    assert len(src.parse(xml)) == 1  # real "now" — item is months old but kept


def test_item_with_unparseable_posted_at_is_kept_not_dropped():
    """Missing/unparseable posted_at must never be silently treated as stale —
    the source can't tell an untimestamped item apart from a fresh one."""
    xml = (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        "<item><title>No date deal</title><link>https://x.example/2</link>"
        "<description>desc</description><guid>g2</guid></item>"
        "</channel></rss>"
    )
    src = FeedDealsSource(name="dealnews", feed_urls=[], max_item_age_hours=48)
    deals = src.parse(xml)
    assert len(deals) == 1
    assert deals[0].posted_at is None


# -- title_keywords filter: keep only on-topic items in a firehose feed ----------


def test_title_keywords_drops_non_matching_and_keeps_matching(caplog):
    xml = (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        "<item><title>羊毛党薅羊毛攻略</title><link>https://x.example/1</link>"
        "<description></description><guid>g1</guid></item>"
        "<item><title>今天天气怎么样</title><link>https://x.example/2</link>"
        "<description></description><guid>g2</guid></item>"
        "</channel></rss>"
    )
    src = FeedDealsSource(
        name="dealnews", feed_urls=[], max_item_age_hours=None, title_keywords=["羊毛"]
    )
    with caplog.at_level("INFO"):
        deals = src.parse(xml)
    assert [d.title for d in deals] == ["羊毛党薅羊毛攻略"]
    assert "dropped 1 item(s) not matching title_keywords" in caplog.text


def test_title_keywords_none_disables_filter():
    xml = RSS_ITEM.format(title="Anything goes", link="https://x.example/1", desc="", guid="g1")
    src = FeedDealsSource(
        name="dealnews", feed_urls=[], max_item_age_hours=None, title_keywords=None
    )
    assert len(src.parse(xml)) == 1


def test_v2ex_default_title_keywords_filters_firehose():
    """V2EX's index.xml/openai node mix real 羊毛 posts with unrelated discussion
    (measured live 2026-08-21) — the default keyword filter keeps only the former."""
    xml = (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        "<item><title>[推广] 超值机场羊毛，速度冲</title><link>https://x.example/1</link>"
        "<description></description><guid>g1</guid></item>"
        "<item><title>Codex 额度越来越不经用，没怎么做事</title><link>https://x.example/2</link>"
        "<description></description><guid>g2</guid></item>"
        "</channel></rss>"
    )
    src = FeedDealsSource(name="v2ex", feed_urls=[], currency="CNY", max_item_age_hours=None)
    deals = src.parse(xml)
    assert [d.title for d in deals] == ["[推广] 超值机场羊毛，速度冲"]


def test_dealnews_and_slickdeals_unaffected_by_v2ex_default_keywords():
    """The per-name default only applies to name="v2ex" — other sources keep
    their existing no-filter behaviour."""
    xml = RSS_ITEM.format(
        title="No Chinese keywords here", link="https://x.example/1", desc="", guid="g1"
    )
    for name in ("dealnews", "slickdeals", "iknowthepilot"):
        src = FeedDealsSource(name=name, feed_urls=[], max_item_age_hours=None)
        assert len(src.parse(xml)) == 1


# -- vercel: mandatory 30-day age cutoff + offer-vs-noise title_keywords ---------


def _rss_with_titles(titles: list[str]) -> str:
    items = "".join(
        f"<item><title>{t}</title><link>https://x.example/{i}</link>"
        f"<description></description><guid>g{i}</guid></item>"
        for i, t in enumerate(titles)
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{items}</channel></rss>'


VERCEL_OFFER_TITLES = [
    "Fish Audio models now available on Vercel AI Gateway for free",
    "GPT-5.6 Sol is 50% off on AI Gateway for the next month",
    "GLM 5.2 free for eve agents through August 27 via Blackbox on AI Gateway",
    "Exa web search free through August 31 on AI Gateway and eve",
    "DeepSeek V4 Flash is 90% off through Novita on AI Gateway",
]
VERCEL_NOISE_TITLES = [
    "Manage Vercel Toolbar comments from the CLI",
    "Bun 1.4 is now available in Vercel Functions",
    "Algolia joins the Vercel Marketplace",
]


def test_vercel_default_title_keywords_keep_offers_drop_noise():
    xml = _rss_with_titles(VERCEL_OFFER_TITLES + VERCEL_NOISE_TITLES)
    src = FeedDealsSource(name="vercel", feed_urls=[], max_item_age_hours=None)
    kept = {d.title for d in src.parse(xml)}
    assert kept == set(VERCEL_OFFER_TITLES)


def test_vercel_default_max_item_age_is_30_days():
    src = FeedDealsSource(name="vercel", feed_urls=[])
    assert src.max_item_age_hours == 24 * 30


def test_vercel_default_timeout_is_raised():
    # 20s default is thin for the measured 3.3MB feed on a slow CI runner.
    assert FeedDealsSource(name="vercel", feed_urls=[]).timeout == 60.0


def test_other_sources_keep_default_timeout():
    for name in ("dealnews", "slickdeals", "v2ex", "iknowthepilot", "aff", "pointhacks"):
        assert FeedDealsSource(name=name, feed_urls=[]).timeout == 20.0


# -- aff / pointhacks: title_keywords deliberately unset (no filtering) ---------


def test_aff_and_pointhacks_have_no_default_title_keywords():
    """Unlike vercel, these get no filter at all: measured 17/20 of
    AFF's subforum is already deal-shaped, and a filter here risks going
    filter-shaped-inert (silently matching zero forever) — see
    GLOBAL_EXPANSION_PLAN.md Lane B."""
    for name in ("aff", "pointhacks"):
        src = FeedDealsSource(name=name, feed_urls=[])
        assert src._title_keywords == []
        assert src.max_item_age_hours == FeedDealsSource._FALLBACK_MAX_AGE_HOURS

    xml = RSS_ITEM.format(
        title="Nothing deal-shaped about this title",
        link="https://x.example/1",
        desc="",
        guid="g1",
    )
    for name in ("aff", "pointhacks"):
        src = FeedDealsSource(name=name, feed_urls=[], max_item_age_hours=None)
        assert len(src.parse(xml)) == 1


# -- v2ex title_block: on-topic vocabulary, but not an offer ---------------------

# The exact 14 items one live v2ex poll produced on 2026-08-21 *after*
# title_keywords, with the by-hand verdict that _DEFAULT_TITLE_BLOCK was tuned
# to reproduce. Kept verbatim rather than paraphrased: the filter's whole job is
# to separate these specific registers, and a cleaned-up sample would stop
# testing the thing that actually broke (中转站 quota resale reaching a digest).
_V2EX_LIVE_SAMPLE = [
    ("中银香港 boc + 10 元羊毛", True),
    ("别急着 羊毛了，先看看 mirasim 的隐私协议", False),
    ("支付宝免费领无糖可乐，亲测一次即中", True),
    ("免费领取 100 刀 Fable 5 的使用额度", True),
    ("Kimi K3 羊毛", True),
    ("求大豆包 seed-2.0 官方渠道 折扣 有量", False),
    ("[推广] 最有性价比的 Cursor 插件中转 模型保真 注册免费体验", False),
    ("[程序员] 为程序员朋友提供免费公益心理咨询服务", False),
    ("[Oracle] Oracle 刚开免费服务器就被封号", False),
    ("[分享创造] 这两天晚上把 LaunchX 的股票面板又优化了一下，有没有试用给我点建议", False),
    ("[推广] [中转站] plus 炸了你们用什么？来我这 0.03 opus4.6，无敌平替", False),
    ("[跟一下] Chatgpt 客户端 1000 Credit 邀请，需要的来（老号或免费账号也可）", True),
    ("哪里有便宜的 Luna 可以用？", False),
    ("Codex 重置是什么力度的活动？可能没有想象的那么多", False),
]


def _v2ex_blocks(title: str) -> bool:
    src = FeedDealsSource(name="v2ex", feed_urls=[])
    return any(p.search(title) for p in src._title_block)


def test_v2ex_title_block_matches_the_hand_classified_live_sample():
    for title, should_keep in _V2EX_LIVE_SAMPLE:
        assert _v2ex_blocks(title) is not should_keep, title


def test_v2ex_title_block_rejects_grey_market_quota_resale():
    """The reason this filter exists: reselling someone else's LLM API quota is
    account resale, not a merchant offer, and must never reach a digest."""
    for title in (
        "[推广] [中转站] plus 炸了你们用什么？来我这 0.03 opus4.6",
        "[推广] Cursor 插件中转 模型保真",
        "出 ChatGPT plus 车位，长期稳定",
        "GPT 合租，一个月 15",
        # Measured live 2026-08-21: this one slipped through a block list that
        # only knew the word 中转. 代充 is the same trade in a different
        # wrapper — a stranger tops up your vendor account with their payment
        # rail, which violates the vendor's terms and leaves you no recourse.
        "[推广] ChatGPT Codex Claude 官方订阅代充值 v2 优惠码 SSASASAV10",
        "代付 ChatGPT Plus，安全快速",
    ):
        assert _v2ex_blocks(title), title


def test_title_block_is_scoped_to_v2ex_not_shared():
    """中转 means 'transit' in an airfare title -- a global block list would
    silently kill aff/iknowthepilot's real connecting-flight deals."""
    transit_fare = "SYD-BKK 中转曼谷 商务舱 $2700"
    assert _v2ex_blocks(transit_fare)  # would be dropped *if* v2ex saw it
    for name in ("aff", "iknowthepilot", "pointhacks", "dealnews", "vercel"):
        src = FeedDealsSource(name=name, feed_urls=[])
        assert src._title_block == [], name
        assert not any(p.search(transit_fare) for p in src._title_block)
