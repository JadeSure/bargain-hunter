"""Tests for the CN AI-platform doc differ (cn_llm_docs.py), no network.

Fixtures are real captures (2026-08-21) of platform.kimi.com's pricing docs
and api-docs.deepseek.com's changelog -- see the module docstring for why
these specific pages were chosen. A "changed" run is simulated by editing
the fixture text in-place, mirroring how llm_prices/bank_rates tests work.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx

from bargain_hunter.sources import cn_llm_docs as mod
from bargain_hunter.sources.cn_llm_docs import CnLlmDocsSource, _normalize_text, _parse_doctable

FIXTURES = Path(__file__).parent / "fixtures"
K3_URL = "https://platform.kimi.com/docs/pricing/chat-k3.md"
CHAT_URL = "https://platform.kimi.com/docs/pricing/chat.md"
DEEPSEEK_URL = "https://api-docs.deepseek.com/updates"
NOW = datetime(2026, 8, 21, tzinfo=UTC)


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _patch(monkeypatch, store: dict[str, str], dead: set[str] | None = None) -> None:
    dead = dead or set()

    def fake_get(url, **kwargs):
        if url in dead:
            return httpx.Response(500, request=httpx.Request("GET", url))
        return httpx.Response(200, text=store[url], request=httpx.Request("GET", url))

    monkeypatch.setattr(mod.httpx, "get", fake_get)


K3_PAGE = {"tag": "kimi", "slug": "chat-k3", "label": "Kimi K3", "url": K3_URL}
CHAT_PAGE = {"tag": "kimi", "slug": "chat", "label": "Kimi 定价说明", "url": CHAT_URL}
DEEPSEEK_PAGE = {
    "tag": "deepseek",
    "slug": "updates",
    "label": "DeepSeek Change Log",
    "url": DEEPSEEK_URL,
}


# ---------------------------------------------------------------------------
# Parsing / normalisation building blocks
# ---------------------------------------------------------------------------


def test_parse_doctable_extracts_columns_and_the_single_row():
    titles, rows = _parse_doctable(_fixture("cn_llm_docs_kimi_chat_k3.md"))

    assert titles[0] == "模型"
    assert "输入价格（缓存未命中）" in titles
    assert rows["kimi-k3"][titles.index("输入价格（缓存未命中）")] == "¥20.00"


def test_parse_doctable_returns_none_for_a_page_without_one():
    """chat.md is a CardGroup of links, not a DocTable -- must fall through
    to the tier-2 text differ, not silently produce an empty table."""
    assert _parse_doctable(_fixture("cn_llm_docs_kimi_chat.md")) is None


def test_normalize_text_strips_mintlify_boilerplate_and_keeps_signal_lines():
    text = _normalize_text(_fixture("cn_llm_docs_kimi_chat.md"))

    assert "Documentation Index" not in text  # shared site banner, not page content
    assert "export const DocTable" not in text  # MDX component definition
    assert "限时免费" in text  # the actual free-quota line survives
    assert "8 月 31 日全平台下线" in text  # V1 deprecation notice survives


def test_normalize_text_strips_docusaurus_nav_and_footer_chrome():
    text = _normalize_text(_fixture("cn_llm_docs_deepseek_updates.html"))

    assert "Rate Limit & Isolation" not in text  # left-nav sidebar item
    assert "WeChat Official Account" not in text  # footer
    assert "Change Log" in text
    assert "DeepSeek-V4-Pro Update" in text


# ---------------------------------------------------------------------------
# check(): cold start, table diff, text diff, failure handling
# ---------------------------------------------------------------------------


def test_cold_start_seeds_every_page_silently(monkeypatch):
    store = {
        K3_URL: _fixture("cn_llm_docs_kimi_chat_k3.md"),
        CHAT_URL: _fixture("cn_llm_docs_kimi_chat.md"),
    }
    _patch(monkeypatch, store)

    deals, snapshot = CnLlmDocsSource(pages=[K3_PAGE, CHAT_PAGE]).check({}, now=NOW)

    assert deals == []
    assert snapshot["kimi:chat-k3"]["kind"] == "table"
    assert snapshot["kimi:chat"]["kind"] == "text"


def test_table_price_change_produces_the_exact_row_and_column_in_the_title(monkeypatch):
    k3_raw = _fixture("cn_llm_docs_kimi_chat_k3.md")
    store = {K3_URL: k3_raw}
    _patch(monkeypatch, store)
    src = CnLlmDocsSource(pages=[K3_PAGE])
    _, snapshot = src.check({}, now=NOW)

    store[K3_URL] = k3_raw.replace("¥20.00", "¥12.00")
    deals, _ = src.check(snapshot, now=NOW)

    assert len(deals) == 1
    deal = deals[0]
    assert deal.source == "cn_llm_docs"
    assert deal.deal_id == "kimi-chat-k3-kimi-k3"
    assert deal.title == "Kimi K3: 输入价格（缓存未命中） ¥20.00 → ¥12.00"
    assert deal.currency == "CNY"
    assert deal.price is None  # no fabricated $ badge on a per-column CNY table cell
    assert deal.posted_at == NOW


def test_table_unrelated_column_unchanged_emits_nothing(monkeypatch):
    k3_raw = _fixture("cn_llm_docs_kimi_chat_k3.md")
    store = {K3_URL: k3_raw}
    _patch(monkeypatch, store)
    src = CnLlmDocsSource(pages=[K3_PAGE])
    _, snapshot = src.check({}, now=NOW)

    deals, _ = src.check(snapshot, now=NOW)  # re-fetch identical content

    assert deals == []


def test_new_model_row_is_reported_as_an_addition(monkeypatch):
    k3_raw = _fixture("cn_llm_docs_kimi_chat_k3.md")
    store = {K3_URL: k3_raw}
    _patch(monkeypatch, store)
    src = CnLlmDocsSource(pages=[K3_PAGE])
    _, snapshot = src.check({}, now=NOW)

    new_row = (
        '["kimi-k3-turbo", "1M tokens", "¥1.50", "¥15.00", "¥75.00", "1,048,576 tokens"],\n'
    )
    store[K3_URL] = k3_raw.replace(
        'rows={[\n["kimi-k3"', "rows={[\n" + new_row + '["kimi-k3"'
    )
    deals, _ = src.check(snapshot, now=NOW)

    assert len(deals) == 1
    assert "新增 kimi-k3-turbo" in deals[0].title
    assert "¥1.50" in deals[0].title


def test_text_diff_gates_on_signal_keywords_not_any_change(monkeypatch):
    chat_raw = _fixture("cn_llm_docs_kimi_chat.md")
    store = {CHAT_URL: chat_raw}
    _patch(monkeypatch, store)
    src = CnLlmDocsSource(pages=[CHAT_PAGE])
    _, snapshot = src.check({}, now=NOW)

    # A copy-edit with no price/promo keyword must not fire.
    store[CHAT_URL] = chat_raw.replace("大致来说", "大体来说")
    deals, _ = src.check(snapshot, now=NOW)
    assert deals == []

    # A real promo line appearing must fire, quoting that line.
    promo = "\n\n## 新活动\n\n新用户注册即赠送 ¥50 免费额度，限时优惠至月底。\n"
    store[CHAT_URL] = chat_raw + promo
    deals, _ = src.check(snapshot, now=NOW)
    assert len(deals) == 1
    assert deals[0].deal_id == "kimi-chat"
    assert "¥50 免费额度" in deals[0].title


def test_one_dead_url_does_not_sink_the_others(monkeypatch, caplog):
    chat_raw = _fixture("cn_llm_docs_kimi_chat.md")
    store = {CHAT_URL: chat_raw}
    dead_page = {"tag": "dead", "slug": "gone", "label": "Dead Page", "url": "https://x/dead.md"}
    _patch(monkeypatch, store, dead={"https://x/dead.md"})
    src = CnLlmDocsSource(pages=[CHAT_PAGE, dead_page])

    deals, snapshot = src.check({}, now=NOW)

    assert deals == []
    assert "kimi:chat" in snapshot
    assert "dead:gone" not in snapshot  # never seen before, nothing to carry forward


def test_redirect_is_followed_not_treated_as_a_dead_page(monkeypatch):
    """Regression: DeepSeek's real pages 302 to a trailing-slash URL and
    httpx.get does not follow redirects by default (verified live) -- a
    redirect must not look identical to a dead page and silently keep a
    page out of the snapshot forever."""
    chat_raw = _fixture("cn_llm_docs_kimi_chat.md")
    calls: list[dict] = []

    def fake_get(url, **kwargs):
        calls.append(kwargs)
        redirect = httpx.Response(302, request=httpx.Request("GET", url))
        return httpx.Response(
            200, text=chat_raw, request=httpx.Request("GET", url), history=[redirect]
        )

    monkeypatch.setattr(mod.httpx, "get", fake_get)

    deals, snapshot = CnLlmDocsSource(pages=[CHAT_PAGE]).check({}, now=NOW)

    assert calls[0]["follow_redirects"] is True
    assert "kimi:chat" in snapshot  # fetched and seeded despite the redirect
    assert deals == []  # cold start, not a swallowed failure


def test_fetch_failure_carries_the_previous_snapshot_entry_forward(monkeypatch):
    chat_raw = _fixture("cn_llm_docs_kimi_chat.md")
    store = {CHAT_URL: chat_raw}
    _patch(monkeypatch, store)
    src = CnLlmDocsSource(pages=[CHAT_PAGE])
    _, snapshot = src.check({}, now=NOW)

    _patch(monkeypatch, store, dead={CHAT_URL})  # this run's fetch fails
    deals, snapshot2 = src.check(snapshot, now=NOW)

    assert deals == []
    assert snapshot2["kimi:chat"] == snapshot["kimi:chat"]  # carried forward, not dropped


def test_deepseek_html_change_log_diff_quotes_the_added_line(monkeypatch):
    deepseek_raw = _fixture("cn_llm_docs_deepseek_updates.html")
    store = {DEEPSEEK_URL: deepseek_raw}
    _patch(monkeypatch, store)
    src = CnLlmDocsSource(pages=[DEEPSEEK_PAGE])
    _, snapshot = src.check({}, now=NOW)

    new_entry = (
        "<h1>Change Log</h1><p>Date: 2026-08-22</p>"
        "<p>deepseek-v5 launches at $0.10/M input, 限时免费 first month.</p>"
    )
    store[DEEPSEEK_URL] = deepseek_raw.replace("<h1>Change Log</h1>", new_entry)
    deals, _ = src.check(snapshot, now=NOW)

    assert len(deals) == 1
    assert "$0.10" in deals[0].title or "限时免费" in deals[0].title
