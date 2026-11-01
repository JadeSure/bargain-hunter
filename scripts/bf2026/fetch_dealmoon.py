#!/usr/bin/env python3
"""Harvest Dealmoon AU (www.dealmoon.com.au) listing pages into data/bf2026 points + promos.

Dealmoon is a source of *2026 current prices* only: the listings show what is on sale now, there
is no history. Nothing is fetched except the listing pages in PAGES: `/product/<id>` is a
JS-challenge stub (HTTP 202, 0 bytes), `go.dealmoon.com.au/exec/` is the affiliate redirector, and
`/www/.../ajax-load` (the only pagination) is Disallowed in robots.txt, so none of them is touched.
Every request is checked against the live robots.txt (Disallow wildcards included).

Two kinds of product record sit in the HTML of each listing page:
  * carousel card (`div.spDeal`, 20 per page): price, original price, name, merchant, 人感兴趣.
    It has NO timestamp of its own, so `date` is the retrieval date.
  * deal-embedded item (`div.js-sp-item` inside a `div.mlist` deal post): price (+ original price),
    name; merchant is the deal's store; `date` is the deal post's own `t=` (unix seconds).
Items priced in ¥/£/€, or on a deal whose text says the page shows USD/GBP/EUR, are skipped.
Promos come from deal posts whose lead sentence is "<store> 现有 <offer>" with a store-level offer.

    .venv/bin/python scripts/bf2026/fetch_dealmoon.py
    .venv/bin/python scripts/bf2026/fetch_dealmoon.py --from-html DIR   # offline re-parse

Reuses match_known_key/classify from the sibling fetch_ozbargain.py. Deps are the main project's
(httpx, beautifulsoup4); not wired into any workflow.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
import unicodedata
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup
from fetch_ozbargain import classify, match_known_key

DATA = Path(__file__).resolve().parents[2] / "data" / "bf2026"
SITE = "https://www.dealmoon.com.au"
# Same literal as src/strategy_hunter/sources/base.py USER_AGENT; keep in sync.
USER_AGENT = (
    "bargain-hunter/0.1 (personal money-saving guide collector; "
    "+https://github.com/versent-shawn/bargain-hunter)"
)
SYDNEY = ZoneInfo("Australia/Sydney")
MIN_DELAY = 2.0  # PRD 5.2

# Canonical listing paths (the /cn/ and trailing-slash forms 301 to these) -> category of the page,
# or None for a mixed listing. A carousel card seen on exactly one category page gets that category.
# /at-home is deliberately mixed: 15 of its 20 carousel cards are bedding, rugs, cups, luggage and
# concert tickets, not 家电厨房. Set it to "家电厨房" to follow the page name instead.
PAGES: dict[str, str | None] = {
    "/latest": None,
    "/hot-picks": None,
    "/beauty": "美妆个护",
    "/electronics-computers": "数码电子",
    "/at-home": None,
    "/health": "保健食品",
    "/clothing-jewelry-bags": "其他",
    "/sports-outdoors": "户外运动",
}

# Dealmoon's own per-item taxonomy on deal-embedded items: data-dmt-d-category="sp-大类|小类[:..]".
# (大类, 小类) first, then 大类; the first of several ":"-joined tags decides.
SP_CATEGORY: dict[tuple[str, str | None], str] = {
    ("护肤", None): "美妆个护",
    ("彩妆", None): "美妆个护",
    ("个人护理", None): "美妆个护",
    ("男士", "男士个人护理"): "美妆个护",
    ("保健品", None): "保健食品",
    ("家电数码", "个护电器"): "美妆个护",
    ("家电数码", None): "数码电子",
    ("家居", "厨房电器"): "家电厨房",
    ("家居", "厨房用品"): "家电厨房",
    ("家居", "吸尘清洁"): "家电厨房",
    ("家居", "家用电器"): "家电厨房",
    ("运动户外", None): "户外运动",
    ("家居", None): "其他",
    ("服饰", None): "其他",
    ("配饰", None): "其他",
    ("包包", None): "其他",
    ("女鞋", None): "其他",
    ("男士", None): "其他",
    ("母婴儿童", None): "其他",
    ("美食", None): "其他",
    ("旅游", None): "其他",
}

# Explicit markers in the card's name/description only (no inference).
CONDITION_MARKERS = (
    ("需优惠码", re.compile(r"折扣码|优惠码|用码")),
    ("仅新客", re.compile(r"新用户|新客")),
    ("仅会员", re.compile(r"会员")),
    ("套装", re.compile(r"套装|件套|礼盒|倒数日历")),
    ("二手", re.compile(r"二手|中古")),
)
FOREIGN_PAGE_RE = re.compile(r"页面[^。；\n]{0,15}?(?:美元|美金|英镑|欧元)")
EDITORIAL_STORE = "Dealmoon澳新省钱快报"  # Dealmoon's own account, not a merchant
# Different SKU / accessory that a watch-key rule would otherwise swallow
KNOWN_KEY_VETO = re.compile(r"旅行|travel|supersonic\s*r\b|充电器|保护壳|保护套", re.I)
STORE_WIDE_RE = re.compile(r"全场|全站|全店")
DEPARTMENT_RE = re.compile(r"折扣区|清仓区|奥莱区|特惠|专场")  # "全场" after one of these is scoped
SECTION_RE = re.compile(r"折扣区|清仓区|奥莱区|大促|闪促|专场")
GIFT_CARD_RE = re.compile(r"礼卡|礼品卡")
EMOJI_RE = re.compile(r"[\U0001F000-\U0001FFFF\u2600-\u27BF\uFE0F]")
NO_CODE_RE = re.compile(r"无需[^，。；,]{0,10}(?:折扣码|优惠码|用码)")


def collapse(text: str) -> str:
    return " ".join(text.split())


def to_number(text: str) -> float | int:
    value = float(text.replace(",", ""))
    return int(value) if value.is_integer() else round(value, 2)


def aud(text: str) -> float | int | None:
    """'$1,234.50' -> number; anything else (¥, £, empty) -> None."""
    m = re.fullmatch(r"\$\s?(\d[\d,]*(?:\.\d+)?)", text)
    return to_number(m.group(1)) if m else None


def price_problem(text: str) -> str:
    if not text:
        return "no_price"
    return "non_aud_currency" if text[0] in "¥￥£€" else "unreadable_price"


def sydney_day(unix_seconds: int) -> str:
    return datetime.fromtimestamp(unix_seconds, SYDNEY).date().isoformat()


def event_for(day: str) -> str:
    md = (int(day[5:7]), int(day[8:10]))
    if (11, 10) <= md <= (12, 2):
        return "黑五季"
    if md >= (12, 24) or md <= (1, 15):
        return "节礼日"
    return "其他促销"


def conditions_of(text: str, labels: tuple[str, ...] | None = None) -> str:
    text = NO_CODE_RE.sub("", text)  # "无需使用折扣码" means no code is needed
    return "、".join(
        label
        for label, pattern in CONDITION_MARKERS
        if (labels is None or label in labels) and pattern.search(text)
    )


# ---------------------------------------------------------------------------
# robots.txt (urllib.robotparser has no wildcard support, so match Disallow lines ourselves)
# ---------------------------------------------------------------------------
def disallow_rules(robots_txt: str) -> list[re.Pattern[str]]:
    rules = []
    for line in robots_txt.splitlines():
        field, _, value = line.split("#")[0].partition(":")
        if field.strip().lower() == "disallow" and value.strip():
            pattern = re.escape(value.strip()).replace(r"\*", ".*").replace(r"\$", "$")
            rules.append(re.compile(pattern))
    return rules


# ---------------------------------------------------------------------------
# HTML -> raw records
# ---------------------------------------------------------------------------
def parse_listing(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for div in soup.select("div.spDeal"):
        link = div.select_one('a[href^="/product/"]')
        pid = re.fullmatch(r"/product/(\d+)", link["href"]) if link else None
        title, price = div.select_one("p.title"), div.select_one("p.price")
        if not (pid and title and price):
            cards.append({"pid": None})
            continue
        bottom = [collapse(s.get_text()) for s in div.select("div.bottom span")]
        cards.append(
            {
                "pid": pid.group(1),
                "prices": [collapse(s.get_text()) for s in price.select("span")],
                "title": collapse(title.get_text()),
                "retailer": bottom[0] if bottom else "",
                "popularity": bottom[1] if len(bottom) > 1 else "",
            }
        )
    deals = []
    for deal in soup.select('div.mlist[data-type="deal"]'):
        heading, brief = deal.select_one("h2.title"), deal.select_one("p.brief")
        permalink = deal.select_one("a.zoom-title")
        items = []
        for it in deal.select("div.js-sp-item"):
            tw, name = it.select_one("p.tw_text"), it.select_one("p.deal_text")
            desc = it.select_one("p.deal_text_desc")
            tag = it.select_one("a[data-dmt-d-category]")
            items.append(
                {
                    "pid": it.get("data-id", ""),
                    "price_text": collapse(tw.get_text()) if tw else "",
                    "name": collapse(name.get_text()) if name else "",
                    "desc": collapse(desc.get_text()) if desc else "",
                    "taxonomy": tag["data-dmt-d-category"] if tag else "",
                }
            )
        deals.append(
            {
                "id": deal.get("data-id", ""),
                "t": deal.get("t", ""),
                "store": deal.get("data-dmt-d-store-name", ""),
                "title": collapse(heading.get_text()) if heading else "",
                "url": permalink["href"] if permalink else "",
                "brief": collapse(brief.get_text()) if brief else "",
                "foreign_currency": bool(FOREIGN_PAGE_RE.search(deal.get_text(" "))),
                "items": items,
            }
        )
    return {"cards": cards, "deals": deals}


# ---------------------------------------------------------------------------
# Points
# ---------------------------------------------------------------------------
def derive_key(item: str, pid: str, known: dict[str, str]) -> str:
    """Lowercase-kebab slug of the item's ASCII tokens. CJK-only names, and slugs that would
    collide with a watch/curated key without having matched it, fall back to dm-<id>."""
    ascii_item = unicodedata.normalize("NFKD", item).encode("ascii", "ignore").decode().lower()
    slug = "-".join(re.findall(r"[a-z0-9]+", ascii_item.replace("'", ""))[:6])
    return slug if re.search(r"[a-z]{3}", slug) and slug not in known else f"dm-{pid}"


def taxonomy_category(tag: str) -> str | None:
    first = tag.removeprefix("sp-").split(":")[0]
    top, _, sub = first.partition("|")
    return SP_CATEGORY.get((top, sub)) or SP_CATEGORY.get((top, None))


def collect_products(pages: dict[str, dict], retrieved_at: str) -> tuple[dict, dict]:
    """pid -> merged product record, and pid -> skip reason for the ones that never made it."""
    products: dict[str, dict] = {}
    skipped: dict[str, str] = {}
    deals = {d["id"]: d for p in pages.values() for d in p["deals"]}
    for deal in sorted(deals.values(), key=lambda d: d["t"], reverse=True):  # newest post wins
        for it in deal["items"]:
            pid = it["pid"]
            if pid in products:
                continue
            prices = it["price_text"].split()
            price = aud(prices[0]) if prices else None
            if not (pid and it["name"] and deal["t"].isdigit()):
                skipped.setdefault(pid, "unreadable_item")
            elif price is None:
                skipped.setdefault(pid, price_problem(prices[0] if prices else ""))
            elif price <= 0:
                skipped.setdefault(pid, "zero_price")
            elif deal["foreign_currency"]:
                skipped.setdefault(pid, "page_not_aud")
            else:
                was = aud(prices[1]) if len(prices) > 1 else None
                name = re.sub(r"^(.+?)\s+\1(?=\s|$)", r"\1", it["name"])  # "Arc'teryx Arc'teryx .."
                products[pid] = {
                    "item": name,
                    "retailer": deal["store"],
                    "price": price,
                    "was": was if was is not None and was > price else None,
                    "date": sydney_day(int(deal["t"])),
                    "evidence": collapse(f"{it['price_text']} {name} {it['desc']} {deal['store']}"),
                    "votes": None,
                    "taxonomy": taxonomy_category(it["taxonomy"]),
                    "conditions": conditions_of(f"{name} {it['desc']}"),
                    "pages": set(),
                }
    carousel: dict[str, dict] = {}
    for path, page in pages.items():
        for card in page["cards"]:
            if not card["pid"]:
                skipped.setdefault(f"card@{path}", "unreadable_card")
                continue
            entry = carousel.setdefault(card["pid"], {"card": card, "pages": set()})
            entry["pages"].add(PAGES.get(path))
    for pid, entry in carousel.items():
        card = entry["card"]
        price = aud(card["prices"][0]) if card["prices"] else None
        if price is None or price <= 0 or not (card["title"] and card["retailer"]):
            skipped.setdefault(pid, price_problem(card["prices"][0] if card["prices"] else ""))
            continue
        was = aud(card["prices"][1]) if len(card["prices"]) > 1 else None
        was = was if was is not None and was > price else None
        pop = re.fullmatch(r"(\d+)人感兴趣", card["popularity"])
        text = collapse(" ".join([*card["prices"], card["title"], card["retailer"]]))
        text = collapse(f"{text} {card['popularity']}")
        if pid in products:
            products[pid]["votes"] = int(pop.group(1)) if pop else None
            if (products[pid]["price"], products[pid]["was"]) == (price, was):
                products[pid]["evidence"] = text
            else:  # same product, different price: the card is "now", the deal's date is not
                products[pid].update(price=price, was=was, date=retrieved_at, evidence=text)
        else:
            products[pid] = {
                "item": card["title"],
                "retailer": card["retailer"],
                "price": price,
                "was": was,
                "date": retrieved_at,
                "evidence": text,
                "votes": int(pop.group(1)) if pop else None,
                "taxonomy": None,
                "conditions": conditions_of(card["title"]),
                "pages": set(),
            }
        products[pid]["pages"] = entry["pages"]
    return products, {k: v for k, v in skipped.items() if k not in products}


def load_known_categories() -> dict[str, str]:
    """key -> category from curated.json then watch.json (watch wins)."""
    known = {r["key"]: r["category"] for r in _load(DATA / "points" / "curated.json")}
    known.update({w["key"]: w["category"] for w in _load(DATA / "watch.json")})
    return known


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_points(
    products: dict, known: dict[str, str], retrieved_at: str
) -> tuple[list[dict], Counter]:
    rows, routes = [], Counter()
    for pid in sorted(products, key=int):
        p = products[pid]
        # Python's \b treats CJK as word chars ("M5芯片" has no boundary), so match on ASCII only
        ascii_item = re.sub(r"[^\x00-\x7f]", " ", p["item"])
        key = None if KNOWN_KEY_VETO.search(p["item"]) else match_known_key(ascii_item)
        key = key if key in known else None
        page_cats = p["pages"] - {None}
        if key:
            category, route = known[key], "known-key"
        elif p["taxonomy"]:
            category, route = p["taxonomy"], "item-taxonomy"
        elif len(page_cats) == 1:
            category, route = next(iter(page_cats)), "category-page"
        else:
            category, route = classify(p["item"], p["retailer"]), "keyword/default"
        routes[route] += 1
        rows.append(
            {
                "id": f"dm-{pid}",
                "key": key or derive_key(p["item"], pid, known),
                "item": p["item"],
                "model": None,
                "category": category,
                "retailer": p["retailer"],
                "date": p["date"],
                "event": event_for(p["date"]),
                "price": p["price"],
                "was_price": p["was"],
                "was_suspect": False,
                "conditions": p["conditions"],
                "votes": p["votes"],
                "history_low": False,
                "source": f"{SITE}/product/{pid}",
                "evidence": p["evidence"][:200],
                "retrieved_at": retrieved_at,
                "note": "",
            }
        )
    return rows, routes


# ---------------------------------------------------------------------------
# Promos: deal posts whose lead sentence is "<store> 现有 <offer>"
# ---------------------------------------------------------------------------
def promo_value(offer: str) -> str | None:
    if m := re.search(r"满\s*\$?(\d+)\s*[减返]\s*\$?(\d+)", offer):
        return f"${m[2]} off ${m[1]}"
    folds = re.findall(r"(?<![-~\d.])(\d+(?:\.\d+)?)\s*折", offer)  # "8-9折" is a range: skip
    if len(folds) == 1:  # "8折" = pay 80% = 20% off; "5折起" / "低至5折" = up to 50% off
        up_to = re.search(rf"低至[^\d]{{0,3}}{folds[0]}|{folds[0]}\s*折\s*起", offer)
        return f"{'最高 ' if up_to else ''}{round((10 - float(folds[0])) * 10, 1):g}%"
    return offer.split("，")[0][:80] if folds else None


def promo_dates(brief: str, posted: date) -> tuple[str | None, str | None]:
    def day(month: str, d: str, after: date) -> str | None:
        try:
            found = date(posted.year, int(month), int(d))
            return (found if found >= after else found.replace(year=found.year + 1)).isoformat()
        except ValueError:
            return None

    window = r"活动时间[：:]\s*(\d{1,2})月(\d{1,2})日\s*[-–~至到]\s*(\d{1,2})月(\d{1,2})日"
    if m := re.search(window, brief):
        return day(m[1], m[2], date(posted.year - 1, 1, 1)), day(m[3], m[4], posted)
    if m := re.search(r"截止日期为\s*(\d{1,2})月(\d{1,2})[日号]", brief):
        return None, day(m[1], m[2], posted)
    return None, None


def promo_kind(offer: str) -> str | None:
    if GIFT_CARD_RE.search(offer):
        return "礼品卡折扣"
    if "会员" in offer:
        return "会员价"
    store_wide = STORE_WIDE_RE.search(offer)
    if store_wide and not DEPARTMENT_RE.search(offer[: store_wide.start()]):
        return "全场折扣"
    if store_wide or SECTION_RE.search(offer):
        return "品类折扣"
    return None  # a single brand / product line, not a store-level offer


def build_promos(pages: dict[str, dict], retrieved_at: str) -> tuple[list[dict], Counter]:
    rows, skips = [], Counter()
    deals = {d["id"]: d for p in pages.values() for d in p["deals"]}
    for deal in sorted(deals.values(), key=lambda d: d["t"], reverse=True):
        brief = deal["brief"]
        if "现有" not in brief or not deal["t"].isdigit():
            continue  # not an offer post (roundup, guide, single-product write-up)
        offer = collapse(EMOJI_RE.sub("", re.split(r"[。！]", brief.split("现有", 1)[1])[0]))
        kind, value = promo_kind(offer), promo_value(offer)
        if deal["store"] == EDITORIAL_STORE or re.search(r"[¥￥£€]", offer) or not deal["url"]:
            skips["editorial_store_or_non_aud"] += 1
        elif kind is None:
            skips["brand_or_product_level"] += 1
        elif value is None:
            skips["no_discount_value (gift-with-purchase etc.)"] += 1
        else:
            posted = datetime.fromtimestamp(int(deal["t"]), SYDNEY).date()
            start, end = promo_dates(brief, posted)
            rows.append(
                {
                    "id": f"dm-promo-{deal['id']}",
                    "year": posted.year,
                    "retailer": deal["store"],
                    "kind": kind,
                    "value": value,
                    "start": start,
                    "end": end,
                    "scope": offer[:120],
                    "conditions": conditions_of(offer, ("需优惠码", "仅新客", "仅会员")),
                    "votes": None,
                    "source": deal["url"],
                    "evidence": brief[:200],
                    "retrieved_at": retrieved_at,
                    "note": "",
                }
            )
    return rows, skips


# ---------------------------------------------------------------------------
# Crawl + CLI
# ---------------------------------------------------------------------------
def write_json(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(rows)} rows)")


def fetch_pages(html_dir: Path, delay: float) -> tuple[dict[str, dict], str]:
    """Fetch every PAGES listing politely. Returns (parsed pages so far, problem or "")."""
    pages: dict[str, dict] = {}
    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, follow_redirects=False, timeout=30
    ) as client:
        robots = client.get(f"{SITE}/robots.txt")
        if robots.status_code != 200:
            return pages, f"robots.txt returned HTTP {robots.status_code}; not fetching anything"
        (html_dir / "robots.txt").write_text(robots.text, encoding="utf-8")
        rules = disallow_rules(robots.text)
        for path in PAGES:
            if any(rule.match(path) for rule in rules):
                return pages, f"robots.txt disallows {path}; stopping"
            time.sleep(delay)
            try:
                resp = client.get(f"{SITE}{path}")
            except httpx.HTTPError as exc:
                return pages, f"request for {path} failed ({exc!r}); stopping, no retry"
            if resp.status_code != 200 or not resp.text.strip():
                # 403/429 = blocked; 202/0 bytes = JS-challenge stub; 3xx = page moved
                return pages, f"HTTP {resp.status_code} ({len(resp.content)}B) on {path}: stopping"
            (html_dir / page_name(path)).write_text(resp.text, encoding="utf-8")
            pages[path] = parse_listing(resp.text)
            print(f"{path}: {summarise(pages[path])}", file=sys.stderr)
            if broken(pages[path]):
                return pages, f"{path} parsed zero cards (layout change or block page?)"
    return pages, ""


def page_name(path: str) -> str:
    return path.strip("/") + ".html"


def summarise(page: dict) -> str:
    items = sum(len(d["items"]) for d in page["deals"])
    return f"{len(page['cards'])} carousel cards, {len(page['deals'])} deals, {items} deal items"


def broken(page: dict) -> bool:
    """A normal listing has both the 20-card carousel and deal-embedded items."""
    return not page["cards"] or not any(d["items"] for d in page["deals"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--delay", type=float, default=MIN_DELAY, help=f"seconds, >= {MIN_DELAY}")
    ap.add_argument("--out-dir", type=Path, default=DATA, help="holds points/ and promos/")
    ap.add_argument("--save-html", type=Path, default=None, help="default: a new temp dir")
    ap.add_argument("--from-html", type=Path, default=None, help="re-parse saved pages offline")
    args = ap.parse_args()
    if args.delay < MIN_DELAY:
        ap.error(f"--delay must be >= {MIN_DELAY} (PRD 5.2)")

    html_dir = args.from_html or args.save_html or Path(tempfile.mkdtemp(prefix="dealmoon-bf2026-"))
    html_dir.mkdir(parents=True, exist_ok=True)
    if args.from_html:
        files = {p: html_dir / page_name(p) for p in PAGES if (html_dir / page_name(p)).exists()}
        pages = {p: parse_listing(f.read_text(encoding="utf-8")) for p, f in files.items()}
        problem = "" if pages else f"no saved HTML for any of {list(PAGES)} in {html_dir}"
        if empty := [p for p, page in pages.items() if broken(page)]:
            problem = f"{empty} parsed zero cards (layout change or block page?)"
        stamp = min((f.stat().st_mtime for f in files.values()), default=time.time())
        retrieved_at = datetime.fromtimestamp(stamp, SYDNEY).date().isoformat()
    else:
        pages, problem = fetch_pages(html_dir, args.delay)
        retrieved_at = datetime.now(SYDNEY).date().isoformat()

    known = load_known_categories()
    products, skipped = collect_products(pages, retrieved_at)
    points, routes = build_points(products, known, retrieved_at)
    promos, promo_skips = build_promos(pages, retrieved_at)

    print(f"\nHTML: {html_dir}")
    print(f"pages {'parsed' if args.from_html else 'fetched'}: {len(pages)}/{len(PAGES)}")
    for path, page in pages.items():
        print(f"  {path}: {summarise(page)}")
    print(f"points kept: {len(points)}; skipped: {len(skipped)} {dict(Counter(skipped.values()))}")
    if points:
        print("category route:", dict(routes))
        print("rows per category:", dict(Counter(r["category"] for r in points).most_common()))
        print("rows per event:", dict(Counter(r["event"] for r in points)))
        print("rows per date:", dict(sorted(Counter(r["date"] for r in points).items())))
        print("with was_price:", sum(r["was_price"] is not None for r in points))
        print("with votes:", sum(r["votes"] is not None for r in points))
        print("with conditions:", sum(bool(r["conditions"]) for r in points))
        print("key from watch/curated:", sum(r["key"] in known for r in points))
        print("key fallback dm-<id>:", sum(r["key"].startswith("dm-") for r in points))
        print("editorial retailer:", sum(r["retailer"] == EDITORIAL_STORE for r in points))
    print(f"promos kept: {len(promos)} {dict(Counter(r['kind'] for r in promos))}")
    print(f"promo-shaped posts skipped: {dict(promo_skips)}")

    if points:
        write_json(args.out_dir / "points" / "dealmoon.json", points)
    if promos:
        write_json(args.out_dir / "promos" / "dealmoon.json", promos)
    if problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    if not points:
        print("ERROR: no rows produced; nothing written", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
