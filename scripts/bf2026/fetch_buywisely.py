#!/usr/bin/env python3
"""Harvest BuyWisely AU (buywisely.com.au) product pages into data/bf2026 points.

BuyWisely is a source of *2026 current multi-retailer prices* for the 25 watch.json items (PRD
P0 #4): one `平日` points row per seller offer on a product page. It provides NO dated price
series. The chart behind "Price history" loads `/api/product/<slug>?timeRange=..`, which
robots.txt allows but which answers a Cloudflare "Just a moment" challenge (HTTP 403) to a plain
client; we do not work around that. The `created_at` dates inside the page payload are
seller-record timestamps, not price points. What the page does give: current offers (price,
stock, seller), the product's lowest/highest current price, and one sentence "The all-time low
was $X on <date>".

Discovery (the sanctioned path, no /search and no /api/): sitemap.xml -> ~40 sitemap shards of
`/au/product/<slug>` (1.7M slugs) -> keep slugs that `match_known_key` ties to a watch key, rank
them (freshest sitemap lastmod first), and try at most --per-key pages per key. Each key keeps the
rows of ONE product page (one SKU, so a key's prices are comparable): the first page with
MIN_SELLERS clean sellers, else the page with the most. A page is used only if its title ties to
the key, its prices are <= MAX_AGE_DAYS old and >= 2 sellers survive; each offer's own listing
title must tie too. Prices come from the page's server-rendered RSC payload
(`"offers":[{"pid":..,"base_price":..}]`); a row is kept only if the seller name and price also
appear in the page's visible text.

Seller country: the payload's `country_code` is "au" on every offer of every /au/ page (2161 of
2161 measured, desertcart.com.sa and Desertcart.ae included), so it cannot filter. Foreign sellers
are dropped by their own domain's country TLD plus a name list (NON_AU_SELLER); `.com` sellers not
on the list stay. AU storefronts that ship from overseas (Ubuy Australia, desertcart.com.au) stay,
labelled 海外直邮 (PRD 9). `history_low` is true only when the page's own sentence "The all-time
low was $X" has price <= X and the offer has no conditions label: the payload's `lowest_price` is
just the cheapest *current* offer (== min of the offers on 144 of 144 pages), not a historical
low. `was_price` is always null: the offer objects carry no RRP/original price. Cashback rates
sit in the payload (ShopBack / Cashrewards) but are not visible on the page and carry 2023-24
updated_at stamps, so promos are only written with --promos.

The one dated fact a page gives is its sentence "The all-time low was $X on <date>". Each saved
page that ties to a watch key yields one extra `bwlow-<pid>` row (history_low true, event by the
PRD calendar window of the stated date, retailer only when the same page's "right now is $X at
SELLER" sentence names the seller of that very price). Guard: the low must be >= LOW_MIN_RATIO of
the median current price of >= LOW_MIN_OFFERS ordinary AU offers on the page (a junk or mispriced
listing otherwise becomes a permanent "all-time low"). "All-time" only reaches back to when
BuyWisely started tracking that record, which for most pages is 2026.

    .venv/bin/python scripts/bf2026/fetch_buywisely.py --save-html DIR
    .venv/bin/python scripts/bf2026/fetch_buywisely.py --from-html DIR   # offline re-parse

--save-html DIR also acts as a cache: sitemap shards and product pages already in DIR are
reused (resume after a 403, or re-rank offline). `date`/`retrieved_at` follow each file's mtime,
so a reused page keeps its true fetch date; use a new empty DIR for a fully fresh run. Reuses
match_known_key from the sibling fetch_ozbargain.py. Deps are the main project's (httpx,
beautifulsoup4); not wired into any workflow. robots.txt says `ai-train=no`: this corpus is
reference input only.
"""

from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import statistics
import sys
import tempfile
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup
from fetch_ozbargain import match_known_key

DATA = Path(__file__).resolve().parents[2] / "data" / "bf2026"
SITE = "https://buywisely.com.au"
PRODUCT_PATH = "/au/product/"
# Same literal as src/strategy_hunter/sources/base.py USER_AGENT; keep in sync.
USER_AGENT = (
    "bargain-hunter/0.1 (personal money-saving guide collector; "
    "+https://github.com/versent-shawn/bargain-hunter)"
)
SYDNEY = ZoneInfo("Australia/Sydney")
MIN_DELAY = 2.0  # PRD 5.2
MIN_SELLERS = 3  # stop trying more pages for a key once one page gave this many clean rows
PER_KEY = 6  # default cap on product pages tried per key
MAX_AGE_DAYS = 7  # skip a page whose "Prices last updated" is older than this
# All-time-low guard: BuyWisely pages mix in junk/mispriced/used listings, and one of them becomes
# a permanent "all-time low" (seen: PS5 $11.90, Pandora bracelet $22.95). Keep a stated low only
# if it is >= this share of the median current price of the page's qualifying AU offers.
LOW_MIN_RATIO = 0.6
LOW_MIN_OFFERS = 2  # ...and judged against at least this many such offers

# Words that make a title an accessory/part/toy of a watch product rather than the product itself.
NOT_THE_PRODUCT = re.compile(
    r"attachments?|nozzles?|diffusers?|accessor(?:y|ies)|replacement|compatible|filters?"
    r"|\bbrush(?:es)?\b|\bcomb\b|\btoys?\b|play[\s-]?set|styling[\s-]set|\bcases?\b|\bcovers?\b"
    r"|\bstraps?\b|\bbands?\b|charger|\bcables?\b|protector|\bskins?\b|\bsleeve|\bdocks?\b"
    r"|\bmounts?\b|pouch|\bbattery\b|microphone|user[\s-]guide|recipe[\s-]book|\btubs?\b"
    r"|pints[\s-]and[\s-]lids|\bpaddle|\bgames?\b|joy[\s-]?con|\bbarrels?\b|\bliner"
    r"|\bstands?\b(?![\s-]*mixer)|\bvelcro\b|\bfor\b|\btools?\b|crevice|light[\s-]pipe|jacket|wallet"
    r"|\bcreations\b|cook[\s-]?book",
    re.I,
)
# key -> (title must match, title must not match); "" = no constraint. Only where the watch.json
# item is narrower than the shared KEY_RULES in fetch_ozbargain.py.
NARROW: dict[str, tuple[str, str]] = {
    "sonos": (r"\b(?:beam|era)(?:\b|\d)", ""),  # watch item is "Sonos 音箱（Beam / Era）"
    # the shared rule is just "airwrap" (matches cot liners); 100V/110V = Japan/US-spec units
    "dyson-airwrap": (r"dyson", r"\b1[01]0\s?v\b"),
    # watch note is the Artisan 4.8L ("$1,149 -> $699"), not the 7.6L commercial / Pro Line mixers
    "kitchenaid": (
        r"(?=.*\bartisan\b)(?=.*(?:stand\s*mixer|\bksm\d|5ksm))",
        r"bowl(?![\s-]*lift)|beater|hook|whisk|spare|\bmini\b|kettle|hand",
    ),
    "oralb-io": ("", r"\bmanual\b"),  # a mislabelled "iO 3 Manual Toothbrush" listing
    "sony-xm6": (r"wh-?1000\s?xm6", ""),  # the shared rule also matches "Boya BY-XM6" microphones
    "comvita": (r"umf[\s-]*15", ""),  # watch item is UMF15+ 250g
    "dyson-supersonic": ("", r"supersonic\s*r\b|travel|hd0[1-6]\b"),  # HD17/travel/old gens
    "roborock-curv": ("", r"curv\s?(?:x|2)|\bflow\b"),  # CurvX and Curv 2 Flow are other models
    "ps5": ("", r"\bdrive\b"),  # the detachable disc drive accessory
    # Current models only: a discontinued 2015 Kindle or Series 8 would set a bogus "lowest price".
    "kindle-pw": (r"2024|12th|16\s?gb", ""),
    "apple-watch": (r"series\s?(?:10|11|12)\b|ultra\s?[23]\b|\bse\s?(?:3|\(?3rd)", ""),
}
# watch.json's oralb-io note is about the iO3 ("iO3 标原价 $199"), which the shared rules keep
# under their own key. Airwrap i.d. / Origin stay separate products: not in the 25, so not emitted.
ALIASES = {"oralb-io3": "oralb-io"}
HASHED_SLUG = re.compile(r"-\d{8}(?:-au)?$")  # auto-imported single-seller records: rank last
RSC_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
OFFERS_KEY = '"offers":'
OFFERS_START = OFFERS_KEY + '[{"pid":'  # the per-seller list (the JSON-LD one starts [{"@type")
ALL_TIME_LOW = re.compile(
    r"The all-time low was \$([\d,]+\.\d{2}) on (\d{1,2}) ([A-Za-z]+) (\d{4})(?: — [^.]*\.)?"
)
HEADLINE = re.compile(r"right now is \$([\d,]+\.\d{2}) at (.+?) ?(?:, compared across|\.|$)")
LAST_UPDATED = re.compile(r"Prices last updated (\d{1,2}) ([A-Za-z]+) (\d{4})")
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
STOCK_CONDITIONS = (  # stock_status marker -> conditions label
    (re.compile(r"out of stock|sold out", re.I), "缺货"),
    (re.compile(r"pre-?order", re.I), "预购"),
    (re.compile(r"back-?order", re.I), "缺货可订"),
    (re.compile(r"see merchant", re.I), "库存待确认"),
)
STOCK_LABELS = {label for _, label in STOCK_CONDITIONS}
UNKNOWN_SELLER = "BuyWisely 历史最低价（商家未注明）"
# Markers in the seller's own listing title (the offer is tagged "new" even if the title says not).
LISTING_CONDITIONS = (
    (re.compile(r"pre-?owned|\bused\b|second[\s-]?hand"), "二手"),
    (re.compile(r"refurb|renewed|reconditioned"), "翻新"),
    (re.compile(r"open[\s-]box|box damage|damaged box"), "箱损"),
    (re.compile(r"\bbundle\b"), "套装"),
    (
        re.compile(r"uae version|international (?:version|model)|japan(?:ese)? model|grey import"),
        "水货",
    ),
)
# Sellers outside Australia (the payload's country_code cannot tell: it is "au" everywhere).
# Matched on name + domain; a 2-letter country TLD other than .au is foreign too. Partial.
NON_AU_SELLER = re.compile(
    r"gosupps|playthek|smartyez|mr ?porter|fwrd|mcgrocer|tradeinn|techinn|dizzle|hkairport"
    r"|shoppers-?kart|modesens|herbkart|play-asia|selfridges|snapklik|yoho|kapruka|igeekjo"
    r"|aliexpress|microless|dokodemo|swiftronics|\bshop\.com|\b(?:usa|uae|uk|cyprus|japan)\b"
)
# Seller markers (name + seller domain) that make a "new" listing not an ordinary AU price. The
# listing's own condition says "new" for all of these, so without a label they would pass as
# plain prices and set the alert price. Partial: only sellers recognisable as such.
SELLER_CONDITIONS = (
    (re.compile(r"^ebay"), "eBay 卖家未注明"),
    (
        re.compile(
            r"cash ?converters|webuy\.com|depop|luxury ?closet|culture-?circle|pre-?owned|refurb"
            r"|stockx|reebelo"
        ),
        "二手/转售",
    ),
    (re.compile(r"u-?buy|desertcart"), "海外直邮"),  # AU storefronts that ship from overseas
)


class Stop(Exception):
    """Blocked, robots-disallowed or unexpected response: stop crawling, keep what we have."""


def collapse(text: str) -> str:
    return " ".join(text.split())


def sydney_day(stamp: float) -> str:
    return datetime.fromtimestamp(stamp, SYDNEY).date().isoformat()


def money(value: float) -> str:
    return f"${value:,.2f}"


# ---------------------------------------------------------------------------
# robots.txt + polite GET
# ---------------------------------------------------------------------------
def robots_allows(robots_txt: str, path: str) -> bool:
    """Longest matching Allow/Disallow wins, Allow on a tie. No wildcards: this robots.txt has none.
    ponytail: ignores User-agent groups (one `*` group today); add them if the file grows more."""
    best = (-1, True)
    for line in robots_txt.splitlines():
        field, _, value = line.split("#")[0].partition(":")
        field, value = field.strip().lower(), value.strip()
        if field in ("allow", "disallow") and value and path.startswith(value):
            best = max(best, (len(value), field == "allow"))
    return best[1]


class Crawler:
    """GET with >= delay between requests; stops on anything unexpected, never retries."""

    def __init__(self, client: httpx.Client, delay: float):
        self.client, self.delay, self.requests = client, delay, 0
        self._last = 0.0
        self.robots = ""

    def get(self, path: str, *, ok_missing: bool = False) -> bytes | None:
        if self.robots and not robots_allows(self.robots, path):
            raise Stop(f"robots.txt disallows {path}")
        time.sleep(max(0.0, self._last + self.delay - time.monotonic()))
        try:
            resp = self.client.get(f"{SITE}{path}")
        except httpx.HTTPError as exc:
            raise Stop(f"request for {path} failed ({exc!r}); no retry") from exc
        finally:
            self._last = time.monotonic()
            self.requests += 1
        if resp.status_code in (404, 410) and ok_missing:
            return None
        if resp.status_code != 200 or not resp.content.strip():
            raise Stop(f"HTTP {resp.status_code} ({len(resp.content)}B) on {path}: stopping")
        return resp.content


# ---------------------------------------------------------------------------
# Matching titles / slugs to the watch keys
# ---------------------------------------------------------------------------
def tie(title: str, watch_keys: set[str]) -> str | None:
    """The watch key a product title/slug belongs to, or None. Slugs have hyphens where titles
    have spaces, so try both spellings (`oral-b` needs the hyphen, `airpods pro 3` the spaces)."""
    if NOT_THE_PRODUCT.search(title):
        return None
    key = match_known_key(title) or match_known_key(title.replace("-", " "))
    key = ALIASES.get(key, key)
    if key not in watch_keys:
        return None
    need, veto = NARROW.get(key, ("", ""))
    spellings = {title.lower(), title.lower().replace("-", " ")}
    if need and not any(re.search(need, t) for t in spellings):
        return None
    if veto and any(re.search(veto, t) for t in spellings):
        return None
    return key


def shard_slugs(shard_xml: str) -> list[tuple[str, str]]:
    """(slug, lastmod month 'YYYY-MM' or '') for every product URL in one sitemap shard."""
    url = re.escape(SITE + PRODUCT_PATH)
    pattern = rf"<loc>{url}([^<]+)</loc>\s*(?:<lastmod>([\d-]{{7}})\S*</lastmod>)?"
    return [(html.unescape(slug), month) for slug, month in re.findall(pattern, shard_xml)]


def rank(entries: list[tuple[str, str]]) -> list[str]:
    """Most recently updated month first (sitemap lastmod tracks how fresh the page's prices are:
    26 of 31 pages stamped 2026-10 were <= 7 days old, 0 of 22 stamped 2026-06/07); within a
    month, hand-curated multi-seller records before auto-imported ones, shorter = more generic."""
    by_shape = sorted(set(entries), key=lambda e: (bool(HASHED_SLUG.search(e[0])), len(e[0]), e[0]))
    return [slug for slug, _ in sorted(by_shape, key=lambda e: e[1], reverse=True)]


def page_file(html_dir: Path, slug: str) -> Path:
    return html_dir / "product" / (quote(slug, safe="")[:200] + ".html")


# ---------------------------------------------------------------------------
# Product page -> raw record
# ---------------------------------------------------------------------------
def parse_day(day: str, month: str, year: str) -> date | None:
    """'25', 'Sept', '2026' -> date (month by its first three letters); None if not a real day."""
    try:
        return date(int(year), MONTHS.index(month[:3].lower()) + 1, int(day))
    except ValueError:
        return None


def parse_product(page_html: str) -> dict | None:
    """Parsed product page, or None. Keys: name, url (canonical), pid, offers, lines (visible
    text), all_time_low / low_date / low_text (the page's "The all-time low was ..." sentence)
    and last_updated."""
    rsc = "".join(json.loads(m) for m in RSC_CHUNK.findall(page_html))
    at = rsc.find(OFFERS_START)
    if at < 0:
        return None
    try:
        offers, _ = json.JSONDecoder().raw_decode(rsc[at + len(OFFERS_KEY) :])
    except ValueError:
        return None
    soup = BeautifulSoup(page_html, "html.parser")
    name = url = ""
    for block in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(block.string or "")
        except ValueError:
            continue
        for node in data if isinstance(data, list) else [data]:
            if isinstance(node, dict) and node.get("@type") == "Product":
                name = collapse(html.unescape(str(node.get("name", ""))))
                url = str(node.get("url", ""))
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = [collapse(s) for s in soup.get_text("\n", strip=True).split("\n")]
    text = " ".join(lines)
    low, updated = ALL_TIME_LOW.search(text), LAST_UPDATED.search(text)
    headline = HEADLINE.search(text)
    return {
        "name": name,
        "url": url,
        "pid": offers[0].get("pid") if offers else None,
        "offers": offers,
        "lines": lines,
        "all_time_low": float(low[1].replace(",", "")) if low else None,
        "low_date": parse_day(low[2], low[3], low[4]) if low else None,
        "low_text": collapse(low[0]) if low else "",
        "last_updated": parse_day(*updated.groups()) if updated else None,
        # "The lowest price for X right now is $P at SELLER": (P, SELLER)
        "headline": (float(headline[1].replace(",", "")), collapse(headline[2]))
        if headline
        else None,
    }


def visible(lines: list[str], seller: str, price: float) -> bool:
    """Seller name immediately followed by its price, as in the rendered offer list."""
    shown = money(price)
    return any(a == seller and b == shown for a, b in zip(lines, lines[1:], strict=False))


def foreign_seller(seller: dict) -> bool:
    who = f"{seller.get('name', '')} {seller.get('url', '')}".lower()
    tld = str(seller.get("url", "")).rsplit(".", 1)[-1]
    return (len(tld) == 2 and tld != "au") or bool(NON_AU_SELLER.search(who))


def conditions_of(stock_status: str | None, seller: dict, listing: str) -> str:
    status = collapse(stock_status or "")
    who = f"{seller.get('name', '')} {seller.get('url', '')}".lower()
    labels = [label for pattern, label in STOCK_CONDITIONS if pattern.search(status)]
    labels += [label for pattern, label in SELLER_CONDITIONS if pattern.search(who)]
    labels += [label for pattern, label in LISTING_CONDITIONS if pattern.search(listing.lower())]
    return "、".join(dict.fromkeys(labels))


def cashback_of(seller: dict) -> list[tuple[str, str, str]]:
    """(provider, commission text, record updated_at) the seller object carries."""
    found = []
    for provider in ("shopback", "cashrewards"):
        record = seller.get(provider) or {}
        text = record.get("commission_string") or record.get("commission")
        if isinstance(text, str) and "unavailable" not in text.lower():
            stamp = re.search(r"\d{4}-\d{2}-\d{2}", str(record.get("updated_at")))
            found.append((provider, collapse(text), stamp[0] if stamp else ""))
    return found


def offer_skip(offer: dict, key: str, watch_keys: set[str]) -> str | None:
    """Why this offer is not an ordinary AU price for `key` (None = it qualifies)."""
    seller, price = offer.get("seller") or {}, offer.get("base_price")
    if offer.get("country_code") != "au":
        return "non_au"
    if foreign_seller(seller):
        return "non_au_seller"
    if offer.get("condition") != "new":
        return "not_new"
    if not (collapse(str(seller.get("name", ""))) and isinstance(price, int | float) and price > 0):
        return "no_seller_or_price"
    if not urlparse(str(offer.get("seller_product_url"))).path.strip("/"):
        return "listing_url_is_site_root"  # not a product page: cannot be verified
    if tie(str(offer.get("product_title", "")), watch_keys) != key:
        return "offer_title_not_key"
    return None


def build_page_rows(
    slug: str, page: dict, key: str, category: str, day: str, watch_keys: set[str]
) -> tuple[list[dict], Counter, list[tuple]]:
    """(points, skip reasons, cashback seen) for one product page already tied to `key`."""
    source = f"{SITE}{PRODUCT_PATH}{quote(slug, safe='%-_.~')}"
    prices = [
        o["base_price"] for o in page["offers"] if isinstance(o.get("base_price"), int | float)
    ]
    cheapest = min(prices, default=None)
    best: dict[tuple[int, int], dict] = {}
    cashback: list[tuple] = []
    skips: Counter = Counter()
    for offer in page["offers"]:
        seller, price = offer.get("seller") or {}, offer.get("base_price")
        name = collapse(str(seller.get("name", "")))
        if reason := offer_skip(offer, key, watch_keys):
            skips[reason] += 1
        elif not visible(page["lines"], name, price):
            skips["price_not_in_visible_text"] += 1
        else:
            pid_seller = (int(offer["pid"]), int(offer["seller_id"]))
            if pid_seller in best:  # same seller listed twice on one product: keep the cheaper
                skips["duplicate_seller_listing"] += 1
            if pid_seller not in best or price < best[pid_seller]["price"]:
                listing = collapse(str(offer.get("product_title", "")))
                delivery = collapse(str(offer.get("delivery_info") or ""))
                low = page["all_time_low"]
                conditions = conditions_of(offer.get("stock_status"), seller, listing)
                best[pid_seller] = {
                    "id": f"bw-{pid_seller[0]}-{pid_seller[1]}",
                    "key": key,
                    "item": page["name"],
                    "model": None,
                    "category": category,
                    "retailer": name,
                    "date": day,
                    "event": "平日",
                    "price": price,
                    "was_price": None,
                    "was_suspect": False,
                    "conditions": conditions,
                    "votes": None,
                    # lowest_price is only the cheapest *current* offer, and the page itself says
                    # when that is far above the all-time low: trust the all-time-low sentence,
                    # and only for a plain buyable price (not out of stock / eBay / overseas).
                    "history_low": low is not None and price <= low and not conditions,
                    "source": source,
                    "evidence": collapse(f"{name} {money(price)} {listing} {delivery}")[:200],
                    "retrieved_at": day,
                    "note": "",
                    "_cheapest_now": price == cheapest,
                }
            cashback += [
                (name, offer["seller_id"], source, day, *seen) for seen in cashback_of(seller)
            ]
    return sorted(best.values(), key=lambda r: (r["price"], r["retailer"])), skips, cashback


def event_for(day: date) -> str:
    """The PRD's calendar-window rule: Black Friday 11/10-12/02, Boxing Day 12/24-01/15."""
    md = (day.month, day.day)
    if (11, 10) <= md <= (12, 2):
        return "黑五季"
    if md >= (12, 24) or md <= (1, 15):
        return "节礼日"
    return "平日"


def offer_labels(offer: dict) -> list[str]:
    listing = collapse(str(offer.get("product_title", "")))
    labels = conditions_of(offer.get("stock_status"), offer.get("seller") or {}, listing)
    return [label for label in labels.split("、") if label]


def build_low_row(
    page: dict, key: str, category: str, day: date, watch_keys: set[str]
) -> tuple[dict | None, str]:
    """(row, "") for the page's stated all-time low, else (None, why it was dropped)."""
    low, low_day = page["all_time_low"], page["low_date"]
    if low is None or low_day is None:
        return None, "no_all_time_low_sentence"
    if not page["url"] or page["pid"] is None:
        return None, "no_url_or_pid"
    if not date(2020, 1, 1) <= low_day <= day:
        return None, "low_date_implausible"
    offers = [o for o in page["offers"] if offer_skip(o, key, watch_keys) is None]
    plain = [o for o in offers if not (set(offer_labels(o)) - STOCK_LABELS)]
    if len(plain) < LOW_MIN_OFFERS:  # too few ordinary AU offers to judge the low by
        return None, "under_2_ordinary_offers_on_page"
    if low < LOW_MIN_RATIO * statistics.median(o["base_price"] for o in plain):
        return None, "low_under_60pct_of_median_current_price"
    retailer, note = UNKNOWN_SELLER, "页面标示的历史最低价；商家与成色未注明"
    headline = page["headline"]  # the page names the seller of the lowest *current* price
    if headline and abs(headline[0] - low) < 0.005:
        for offer in page["offers"]:
            seller = offer.get("seller") or {}
            if collapse(str(seller.get("name", ""))) == headline[1] and offer["base_price"] == low:
                if offer_skip(offer, key, watch_keys):
                    return None, "low_is_an_unqualified_offer"
                if set(offer_labels(offer)) - STOCK_LABELS:
                    return None, "low_is_a_flagged_seller"
                retailer, note = (
                    headline[1],
                    "页面标示的历史最低价（现价即历史最低）；商家取自同页现价句；成色未注明",
                )
                break
    return {
        "id": f"bwlow-{page['pid']}",
        "key": key,
        "item": page["name"],
        "model": None,
        "category": category,
        "retailer": retailer,
        "date": low_day.isoformat(),
        "event": event_for(low_day),
        "price": low,
        "was_price": None,
        "was_suspect": False,
        "conditions": "",
        "votes": None,
        "history_low": True,
        "source": page["url"],
        "evidence": page["low_text"][:200],
        "retrieved_at": day.isoformat(),
        "note": note,
    }, ""


def harvest_lows(
    html_dir: Path, watch: list[dict], watch_keys: set[str]
) -> tuple[list[dict], Counter]:
    """One all-time-low row per saved product page that ties to a watch key and passes the guard."""
    category = {w["key"]: w["category"] for w in watch}
    order = {w["key"]: i for i, w in enumerate(watch)}
    rows: dict[str, dict] = {}
    drops: Counter = Counter()
    for path in sorted((html_dir / "product").glob("*.html")):
        page = parse_product(path.read_text(encoding="utf-8"))
        key = tie(page["name"], watch_keys) if page else None
        if page is None or key is None:
            drops["page_not_tied_to_a_watch_key"] += 1
            continue
        day = date.fromisoformat(sydney_day(path.stat().st_mtime))
        row, reason = build_low_row(page, key, category[key], day, watch_keys)
        if row is None:
            drops[reason] += 1
        else:
            rows[row["id"]] = row
    return sorted(rows.values(), key=lambda r: (order[r["key"]], r["date"], r["id"])), drops


PROVIDER_LABELS = {"shopback": "ShopBack", "cashrewards": "Cashrewards"}


def promo_rows(cashback: list[tuple]) -> list[dict]:
    """One 返现加码 row per (seller, provider) from the cashback records of the kept pages."""
    rows: dict[str, dict] = {}
    for name, seller_id, source, day, provider, text, stamp in cashback:
        label = PROVIDER_LABELS[provider]
        rows.setdefault(
            f"bw-promo-{seller_id}-{provider}",
            {
                "id": f"bw-promo-{seller_id}-{provider}",
                "year": int(day[:4]),
                "retailer": name,
                "kind": "返现加码",
                "value": text,
                "start": None,
                "end": None,
                "scope": f"{label} 上 {name} 的返现（BuyWisely 商家数据）",
                "conditions": "",
                "votes": None,
                "source": source,
                "evidence": collapse(f"{name} {label} {text}")[:200],
                "retrieved_at": day,
                "note": f"费率记录 updated_at {stamp or '未知'}；页面可见文字中看不到此费率",
            },
        )
    return list(rows.values())


# ---------------------------------------------------------------------------
# Crawl + CLI
# ---------------------------------------------------------------------------
def write_json(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(rows)} rows)")


def discover(html_dir: Path, crawler: Crawler | None, watch_keys: set[str]) -> dict[str, list[str]]:
    """key -> ranked candidate slugs, from the sitemap shards (cached under html_dir/sitemaps)."""
    shard_dir = html_dir / "sitemaps"
    shard_dir.mkdir(parents=True, exist_ok=True)
    if crawler:
        index = html_dir / "sitemap.xml"
        if not index.exists():
            body = crawler.get("/sitemap.xml")
            index.write_bytes(body or b"")
        names = re.findall(r"/sitemaps/(sitemap-\d+\.xml)", index.read_text(encoding="utf-8"))
        for name in names:
            if not (shard_dir / f"{name}.gz").exists():
                body = crawler.get(f"/sitemaps/{name}")
                (shard_dir / f"{name}.gz").write_bytes(gzip.compress(body or b""))
    found: dict[str, list[tuple[str, str]]] = {}
    total = 0
    for shard in sorted(shard_dir.glob("*.gz"), key=lambda p: int(re.search(r"-(\d+)", p.name)[1])):
        entries = shard_slugs(gzip.decompress(shard.read_bytes()).decode("utf-8"))
        total += len(entries)
        for slug, month in entries:
            if key := tie(slug, watch_keys):
                found.setdefault(key, []).append((slug, month))
    print(f"sitemap: {total} product slugs, {sum(map(len, found.values()))} tied to a watch key")
    return {key: rank(slugs) for key, slugs in found.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--delay", type=float, default=MIN_DELAY, help=f"seconds, >= {MIN_DELAY}")
    ap.add_argument("--per-key", type=int, default=PER_KEY, help="max product pages tried per key")
    ap.add_argument("--out-dir", type=Path, default=DATA, help="holds points/ (and promos/)")
    ap.add_argument("--promos", action="store_true", help="also write promos/buywisely.json")
    ap.add_argument("--save-html", type=Path, default=None, help="default: a new temp dir")
    ap.add_argument("--from-html", type=Path, default=None, help="re-parse saved pages offline")
    args = ap.parse_args()
    if args.delay < MIN_DELAY:
        ap.error(f"--delay must be >= {MIN_DELAY} (PRD 5.2)")

    watch = json.loads((DATA / "watch.json").read_text(encoding="utf-8"))
    watch_keys = {w["key"] for w in watch}
    html_dir = (
        args.from_html or args.save_html or Path(tempfile.mkdtemp(prefix="buywisely-bf2026-"))
    )
    html_dir.mkdir(parents=True, exist_ok=True)

    points: list[dict] = []
    cashback: list[tuple] = []
    skips: Counter = Counter()  # offers skipped on the pages that were kept
    tried: dict[str, int] = {w["key"]: 0 for w in watch}
    stats: Counter = Counter()
    problem = ""
    crawler = None
    try:
        if not args.from_html:
            client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60)
            crawler = Crawler(client, args.delay)
            (html_dir / "robots.txt").write_bytes(robots := crawler.get("/robots.txt") or b"")
            crawler.robots = robots.decode("utf-8")
        candidates = discover(html_dir, crawler, watch_keys)
        for w in watch:
            key = w["key"]
            best = None  # (clean rows, rows) score, rows, skips, cashback of the best page so far
            for slug in candidates.get(key, [])[: args.per_key]:
                path = page_file(html_dir, slug)
                if not path.exists():
                    if crawler is None:
                        stats["not_saved_offline"] += 1
                        continue
                    body = crawler.get(
                        f"{PRODUCT_PATH}{quote(slug, safe='%-_.~')}", ok_missing=True
                    )
                    if body is None:
                        stats["http_404"] += 1
                        continue
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(body)
                else:
                    stats["cached_page"] += 1
                tried[key] += 1
                page = parse_product(path.read_text(encoding="utf-8"))
                if page is None:
                    stats["unparseable_page"] += 1
                    continue
                if tie(page["name"], watch_keys) != key:
                    stats["page_title_not_key"] += 1
                    continue
                day = sydney_day(path.stat().st_mtime)
                updated = page["last_updated"]
                age = (date.fromisoformat(day) - updated).days if updated else None
                if age is None or age > MAX_AGE_DAYS:
                    stats["stale_or_undated_page"] += 1
                    continue
                rows, page_skips, page_cashback = build_page_rows(
                    slug, page, key, w["category"], day, watch_keys
                )
                if len(rows) < 2:  # a lone listing cannot be cross-checked against anyone
                    stats["page_under_2_sellers"] += 1
                    continue
                clean = sum(not r["conditions"] for r in rows)
                if best is None or (clean, len(rows)) > best[0]:
                    best = ((clean, len(rows)), rows, page_skips, page_cashback)
                if clean >= MIN_SELLERS:
                    break  # this page already compares enough clean sellers
            if best:
                points.extend(best[1])
                skips.update(best[2])
                cashback += best[3]
                stats["pages_used"] += 1
    except Stop as stop:
        problem = str(stop)

    lows, low_drops = harvest_lows(html_dir, watch, watch_keys)
    cheapest_now = sum(r.pop("_cheapest_now") for r in points)
    sellers = {r["retailer"] for r in points}
    cashback = [c for c in cashback if c[0] in sellers]
    promos = promo_rows(cashback)

    print(f"\nHTML: {html_dir}")
    print(f"requests this run: {crawler.requests if crawler else 0}; {dict(stats)}")
    print("per key (pages tried -> rows, clean rows | sellers | price range of clean rows):")
    for w in watch:
        rows = [r for r in points if r["key"] == w["key"]]
        clean = [r["price"] for r in rows if not r["conditions"]]
        span = f"{min(clean)}-{max(clean)}" if clean else "-"
        n_sellers = len({r["retailer"] for r in rows})
        print(
            f"  {w['key']:18} {tried[w['key']]} -> {len(rows):2}, {len(clean):2} | {n_sellers:2}"
            f" | {span}"
        )
    print(f"points kept: {len(points)}; offers skipped on kept pages: {dict(skips)}")
    print("with was_price:", sum(r["was_price"] is not None for r in points))
    print(
        f"history_low=true: {sum(r['history_low'] for r in points)}"
        f" (rows equal to the page's current lowest_price: {cheapest_now})"
    )
    print("conditions:", dict(Counter(r["conditions"] for r in points)))
    print(f"\nall-time-low rows kept: {len(lows)}; dropped: {dict(low_drops)}")
    print("  event:", dict(Counter(r["event"] for r in lows)))
    print("  year:", dict(sorted(Counter(r["date"][:4] for r in lows).items())))
    print(f"  seller unknown: {sum(r['retailer'] == UNKNOWN_SELLER for r in lows)}")
    first = [w["key"] for w in watch if any(r["key"] == w["key"] for r in lows)]
    print("  keys with an all-time-low row:", len(first))
    print(
        "  keys whose ONLY rows are lows:",
        [k for k in first if not any(r["key"] == k for r in points)],
    )
    stamps = sorted(c[6] for c in cashback if c[6])
    print(f"cashback rows available: {len(promos)}, record updated_at {stamps[:1]}..{stamps[-1:]}")

    if points:
        write_json(args.out_dir / "points" / "buywisely.json", points + lows)
    if promos and args.promos:
        write_json(args.out_dir / "promos" / "buywisely.json", promos)
    if problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    if not points:
        print("ERROR: no watch item matched a BuyWisely page; nothing written", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
