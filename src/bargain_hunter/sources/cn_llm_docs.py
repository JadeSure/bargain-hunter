"""Chinese AI-platform doc differ: a CamelCamelCamel for DeepSeek/Kimi/Zhipu/
SiliconFlow 羊毛 (free quota grants, price cuts, time-limited promos).

None of these platforms' `/v1/models` APIs are readable without a key (401),
and the usual CN deal-aggregator routes are anti-bot walled. But several
publish their docs under the `llms.txt` convention (an explicit invitation
for programmatic reading) as plain Markdown/MDX, and DeepSeek's Docusaurus
site renders full static HTML server-side -- both are fetchable without auth
or scraping tricks. This module polls a configured set of those pages
(`config/settings.yaml` `sources.cn_llm_docs.pages`) and diffs each against
the previous run's snapshot.

Two diff tiers, tried per page in that order:

  1. Table diff (`_parse_doctable`). Kimi's pricing pages render a Mintlify
     `<DocTable columns={[...]} rows={[...]} />` JSX call with the actual
     price/limit figures as a JS array literal -- regex-extractable without
     a real JS parser since it's simple, stable, quote-delimited data (see
     `_parse_doctable`'s docstring for why the row-boundary regex is safe).
     When a row's cell changes, the deal title quotes the page's own column
     label (e.g. "输入价格（缓存未命中）"), so it never needs a hardcoded
     opinion on which column is "the price" -- this is what produces the
     "Kimi K3: 输入价格（缓存未命中） ¥20.00 → ¥12.00" style title.
  2. Whole-page text diff (`_diff_text`), for everything else: DeepSeek's
     HTML pages, Kimi's own index page (a CardGroup of links, not a price
     table), Zhipu's model-overview (its real pricing page is an SPA shell
     at open.bigmodel.cn/pricing -- this is the closest markdown route), and
     SiliconFlow's rate-limits policy page (no per-model price table was
     found in markdown form at all). A page-changed event only becomes a
     Deal if at least one *added* line (from a `difflib.unified_diff`
     against the previous run's normalised text) matches `_SIGNAL_RE` --
     free/promo keywords or a price-figure -- since a typo fix or unrelated
     prose edit is not 羊毛. The Deal title quotes that line verbatim, so it
     is never a vague "the page changed".

Honesty note: tier 2 cannot promise a clean "model: price" title the way
tier 1 can -- it reports whatever line of real page text tripped the
keyword gate, which is usually informative but occasionally just adjacent
context. That is the deliberate trade-off explained in the delegation brief:
concrete-but-imperfect beats a fabricated price-drop badge on data that was
never structured.

Cold start (a page never seen before) seeds silently -- same reasoning as
llm_prices.py's cold-start guard: without it, the very first run would
"diff" every page against nothing and alert on all of them at once.
"""

from __future__ import annotations

import difflib
import html as html_lib
import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from ..models import Deal

log = logging.getLogger(__name__)

USER_AGENT = (
    "bargain-hunter/0.1 (personal deal alerter; +https://github.com/versent-shawn/bargain-hunter)"
)
CATEGORIES = ["AI", "API"]

# Every page on platform.kimi.com/docs.bigmodel.cn/docs.siliconflow.cn (all
# three are Mintlify-hosted) carries this exact 3-line banner pointing back
# at the site's own llms.txt index. It's identical on every page of a given
# site and never itself constitutes a real change, so it's stripped before
# diffing rather than tripping every page's very first diff.
_DOC_INDEX_HEADER_RE = re.compile(
    r"^> ## Documentation Index\n> Fetch the complete documentation index at:.*\n"
    r"> Use this file to discover all available pages before exploring further\.\n*",
)
# The MDX component definition each Kimi pricing page inlines above its own
# <DocTable ... /> call -- identical boilerplate, not page content.
_MDX_EXPORT_RE = re.compile(r"export const \w+ = \(.*?\n\};\n", re.DOTALL)
_DOCTABLE_RE = re.compile(
    r"<DocTable\s+columns=\{(\[.*?\])\}\s*rows=\{(\[.*?\])\}\s*/>", re.DOTALL
)
_COL_TITLE_RE = re.compile(r'title:\s*"((?:[^"\\]|\\.)*)"')
_QUOTED_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_BLOCK_TAG_RE = re.compile(r"</(?:p|div|li|tr|h[1-6]|section|article)>|<br\s*/?>", re.IGNORECASE)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[\s\S]*?</\1>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
# What's worth an alert: 限时免费/免费/优惠/额度/赠送 (free/promo language), a
# model-list change (新增/下线/上线), or a price figure (¥/$ followed by a
# digit) -- a typo fix or copy-edit elsewhere on the page matches none of these.
_SIGNAL_RE = re.compile(r"限时免费|免费|优惠|额度|赠送|新增|下线|上线|[¥$]\s?\d")


def _sanitise(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-")


def _looks_like_html(raw: str) -> bool:
    return raw.lstrip()[:20].lower().startswith(("<!doctype", "<html"))


def _parse_doctable(raw: str) -> tuple[list[str], dict[str, list[str]]] | None:
    """Extract a Kimi pricing DocTable's column titles and rows (keyed by
    each row's first cell -- the model id or tier name), or None if this
    page doesn't have one.

    `rows={[...]}` is a JS array-of-arrays; `[^\\[\\]]+` (no nested brackets
    inside a row -- verified live, cells are plain quoted strings/numbers)
    correctly isolates one row at a time without a real JS parser: starting
    the match at the outer `[` always fails (nothing but whitespace before
    the next `[`, so no `]` can follow), so the engine only ever succeeds
    starting at each row's own `[`.
    """
    m = _DOCTABLE_RE.search(raw)
    if not m:
        return None
    columns_blob, rows_blob = m.groups()
    titles = _COL_TITLE_RE.findall(columns_blob)
    rows: dict[str, list[str]] = {}
    for row_blob in re.findall(r"\[([^\[\]]+)\]", rows_blob):
        cells = _QUOTED_RE.findall(row_blob)
        if cells:
            rows[cells[0]] = cells
    if not titles or not rows:
        return None
    return titles, rows


def _normalize_text(raw: str) -> str:
    """Plain-text, line-oriented form of a page used for tier-2 diffing.

    HTML pages (DeepSeek/Docusaurus) have block tags turned into newlines
    first so a table row survives as roughly one line, not flattened into
    one page-wide blob. MDX pages (Kimi/Zhipu/SiliconFlow) get the shared
    boilerplate stripped and any remaining JSX tags dropped.

    Both then have the surrounding Docusaurus/doc-site chrome trimmed: the
    left-nav sidebar and page footer are identical across every page on a
    site, so without this an unrelated sidebar edit would look like a
    change on every single page in the same run.
    """
    if _looks_like_html(raw):
        raw = _SCRIPT_STYLE_RE.sub(" ", raw)
        raw = _BLOCK_TAG_RE.sub("\n", raw)
        raw = _TAG_RE.sub(" ", raw)
        raw = html_lib.unescape(raw)
    else:
        raw = _DOC_INDEX_HEADER_RE.sub("", raw)
        raw = _MDX_EXPORT_RE.sub("", raw)
        raw = _TAG_RE.sub(" ", raw)

    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.splitlines()]
    text = "\n".join(ln for ln in lines if ln)

    idx = text.find("On this page")
    if idx != -1:
        text = text[idx + len("On this page") :]
    fidx = text.find("WeChat Official Account")
    if fidx != -1:
        text = text[:fidx]
    return text.strip()


class CnLlmDocsSource:
    name = "cn_llm_docs"

    def __init__(self, pages: list[dict[str, Any]], timeout: float = 20.0) -> None:
        self.pages = pages
        self.timeout = timeout

    def _fetch_one(self, url: str) -> str | None:
        """Network only, one page. Never raises -- one dead URL must not sink
        the whole run (see check()).

        `follow_redirects=True`: doc sites reorganise (verified live --
        DeepSeek permanently redirects both its pages to a trailing-slash
        URL), and depending on every configured URL staying canonical
        forever means a routine site tweak silently shrinks the snapshot --
        indistinguishable from a dead page unless someone reads the logs.
        Tolerating the hop keeps the page live; the `resp.history` check
        still logs it loudly, since a redirect landing somewhere unexpected
        (or a doc URL drifting long-term) is worth knowing about even when
        it isn't fatal.
        """
        try:
            resp = httpx.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=self.timeout,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            log.warning("cn_llm_docs: %s failed — %s", url, exc)
            return None
        if resp.history:
            log.warning("cn_llm_docs: %s redirected to %s", url, resp.url)
        if resp.status_code != 200:
            log.warning("cn_llm_docs: %s non-200 (%s)", url, resp.status_code)
            return None
        return resp.text

    def check(self, previous: dict, now: datetime | None = None) -> tuple[list[Deal], dict]:
        """Fetch every configured page, diff each against `previous`, and
        return (deals, current) -- current goes to
        `state.set_snapshot("cn_llm_docs", current)`.
        """
        now = now or datetime.now(UTC)
        current: dict[str, Any] = {}
        deals: list[Deal] = []
        for page in self.pages:
            url = page.get("url")
            if not url:
                continue
            tag = page.get("tag", "?")
            slug = page.get("slug", "?")
            label = page.get("label") or slug
            key = f"{tag}:{slug}"

            raw = self._fetch_one(url)
            if raw is None:
                # Carry the previous entry forward unchanged (bank_rates.py's
                # _carry_forward_brand reasoning): losing it would make the
                # next successful fetch look like a brand-new page (seed
                # only, never a diff) and silently swallow whatever changed
                # during this outage.
                prev_entry = previous.get(key)
                if prev_entry is not None:
                    current[key] = prev_entry
                continue

            prev_entry = previous.get(key)
            page_deals, entry = self._diff_page(url, tag, slug, label, raw, prev_entry, now)
            current[key] = entry
            deals.extend(page_deals)
        return deals, current

    def _diff_page(
        self,
        url: str,
        tag: str,
        slug: str,
        label: str,
        raw: str,
        prev_entry: dict | None,
        now: datetime,
    ) -> tuple[list[Deal], dict]:
        table = _parse_doctable(raw)
        if table is not None:
            titles, rows = table
            entry = {"kind": "table", "rows": rows}
            if prev_entry is None or prev_entry.get("kind") != "table":
                return [], entry  # cold start, or the page's rendering changed shape
            deals = self._diff_rows(url, tag, slug, label, titles, rows, prev_entry["rows"], now)
            return deals, entry

        text = _normalize_text(raw)
        entry = {"kind": "text", "text": text}
        if prev_entry is None or prev_entry.get("kind") != "text":
            return [], entry
        deals = self._diff_text(url, tag, slug, label, text, prev_entry["text"], now)
        return deals, entry

    def _diff_rows(
        self,
        url: str,
        tag: str,
        slug: str,
        label: str,
        titles: list[str],
        rows: dict[str, list[str]],
        prev_rows: dict[str, list[str]],
        now: datetime,
    ) -> list[Deal]:
        multi = len(rows) > 1
        deals: list[Deal] = []
        for row_key, cells in rows.items():
            prev_cells = prev_rows.get(row_key)
            if prev_cells is None:
                changes = [f"{t} {v}" for t, v in zip(titles[1:], cells[1:], strict=False) if v]
                if not changes:
                    continue
                title = f"{label}: 新增 {row_key} — " + ", ".join(changes)
            else:
                changes = [
                    f"{t} {old} → {new}"
                    for t, old, new in zip(titles[1:], prev_cells[1:], cells[1:], strict=False)
                    if old != new
                ]
                if not changes:
                    continue
                prefix = f"{row_key} " if multi else ""
                title = f"{label}: {prefix}" + ", ".join(changes)
            deals.append(
                Deal(
                    source=self.name,
                    deal_id=_sanitise(f"{tag}-{slug}-{row_key}"),
                    title=title,
                    url=url,
                    categories=CATEGORIES,
                    posted_at=now,
                    currency="CNY",
                )
            )
        return deals

    def _diff_text(
        self,
        url: str,
        tag: str,
        slug: str,
        label: str,
        text: str,
        prev_text: str,
        now: datetime,
    ) -> list[Deal]:
        if text == prev_text:
            return []
        added = [
            ln[1:].strip()
            for ln in difflib.unified_diff(prev_text.splitlines(), text.splitlines(), lineterm="")
            if ln.startswith("+") and not ln.startswith("+++")
        ]
        match = next((ln for ln in added if ln and _SIGNAL_RE.search(ln)), None)
        if match is None:
            return []  # page changed, but nothing that looks like real 羊毛 signal
        return [
            Deal(
                source=self.name,
                deal_id=_sanitise(f"{tag}-{slug}"),
                title=f"{label}: {match[:160]}",
                url=url,
                categories=CATEGORIES,
                posted_at=now,
                currency="CNY",
            )
        ]
