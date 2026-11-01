#!/usr/bin/env python3
"""Harvest OzBargain's /event/<slug> listing pages into data/bf2026 `points` rows.

Everything comes from the listing HTML (title, net votes, posted date, merchant); no /node/<id>
pages are fetched. Titles without an explicit single AUD `$` price are skipped (promo-shaped
posts belong in promos/, per docs/BF2026_DATA_PRD.md). Nothing is invented: unparseable
optional fields are null/"" and unparseable required fields skip the row.

    python3 scripts/bf2026/fetch_ozbargain.py --pages 0-219
    python3 scripts/bf2026/fetch_ozbargain.py --event boxing-day
    python3 scripts/bf2026/fetch_ozbargain.py --from-html DIR   # re-parse saved HTML, no network

Deps are the main project's (httpx, beautifulsoup4); not wired into any workflow.
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

DATA = Path(__file__).resolve().parents[2] / "data" / "bf2026"
EVENT_URL = "https://www.ozbargain.com.au/event/{slug}"
# Same literal as src/strategy_hunter/sources/base.py USER_AGENT; keep in sync.
USER_AGENT = (
    "bargain-hunter/0.1 (personal money-saving guide collector; "
    "+https://github.com/versent-shawn/bargain-hunter)"
)
SYDNEY = ZoneInfo("Australia/Sydney")
MIN_DELAY = 2.0  # PRD 5.2
# slug -> (`event` value in the window, window start, window end), inclusive (month, day).
# A window with start > end crosses the new year: Jan 8 2026 is in the 2025 Boxing Day season.
# label -> one or more (start, end) windows. Several events run twice a year, so a single
# window would mislabel half their deals; the windows below were set from the measured
# month histogram of each event's own listing, not guessed.
EVENT_SEASONS = {
    "black-friday": ("黑五季", [((11, 10), (12, 2))]),
    "boxing-day": ("节礼日", [((12, 24), (1, 15))]),
    # Cyber Monday sits inside the Black Friday window and check.py has no separate value
    # for it, so its deals carry 黑五季.
    "cyber-monday": ("黑五季", [((11, 10), (12, 2))]),
    # Two seasons: Click Frenzy Mayhem in May, the main event Oct/Nov. Measured 328 rows
    # in May against 356 in November, so one window would drop half the source.
    "click-frenzy": ("Click Frenzy", [((5, 1), (5, 31)), ((10, 20), (11, 25))]),
    "singles-day": ("双11", [((11, 1), (11, 15))]),
    # July Prime Day (2,436 rows, with a June lead-in) plus October "Prime Big Deal Days"
    # (475 rows) — both measured on the live listing.
    "amazon-prime-day": ("Prime Day", [((6, 20), (7, 31)), ((10, 1), (10, 20))]),
}

# ---------------------------------------------------------------------------
# Title parsing
# ---------------------------------------------------------------------------
_NUM = r"(\d[\d,]*(?:\.\d+)?)"
# `$` not glued to a currency prefix (US$, NZ$, A$ ...) and not an approximation (~$).
PRICE_RE = re.compile(r"(?<![A-Za-z~])\$\s?" + _NUM)
WAS_RE = re.compile(r"\b(?:RRP|Was|Don['’]?t Pay)\s*:?\s*\$\s?" + _NUM, re.I)
AT_RE = re.compile(r"\s@\s*")
# "+ Delivery (...)" / "+ $9.99 Shipping": what follows describes shipping, not the price.
DELIVERY_RE = re.compile(
    r"\s\+\s*(?:\$[\d.,]+\s*)?(?:[A-Za-z]+\s+){0,2}?(?:Del\b|Delivery|Shipping|Ship\b|Postage|P&P)",
    re.I,
)
# Price shapes that are not one product's price.
NOT_PRICE_AFTER_RE = re.compile(
    r"\s*(?:(?:-|–|to)\s*\$|off\b|spend\b|min(?:imum)?\b|orders?\b|or more"
    r"|cash\s?back|rebate|bonus|credit\b|voucher|e?gift)",
    re.I,
)
NOT_PRICE_BEFORE_RE = re.compile(
    r"(?:\bfrom|\bstarting(?: at| from)?|\bup to|\bsave|\bmin(?:imum)?|\bover|\bspend"
    r"|\bcapped at|\d\s*for|cash\s?back\s*:)\s*$",
    re.I,
)

CONDITIONS = (  # (label, pattern) in output order; matched on the pre-delivery title text
    ("仅新客", r"\bnew (?:members?|customers?|users?)\b"),
    ("仅会员", r"\bmember(?:s|ship)?\b"),
    ("仅学生", r"\bstudents?\b"),
    (
        "需优惠码",
        r"\b(?:with|w/|via|using)\s+(?:\S+\s+){0,3}?(?:code|coupon)s?\b"
        r"|\bcoupons?\b|\bpromo code\b",
    ),
    ("仅 eBay Plus", r"\bebay plus\b"),
    ("需到店自提", r"\bclick\s*(?:&|and)\s*collect\b|\bc&c\b"),
)

CANONICAL_RETAILERS = (  # matched against the lowercased merchant text or domain
    ("Amazon AU", r"\bamazon au(?:stralia)?\b|amazon\.com\.au|^amazon$"),
    ("JB Hi-Fi", r"\bjb hi-?fi\b|jbhifi\.com\.au"),
    ("The Good Guys", r"\bgood guys\b|thegoodguys\.com\.au"),
    ("Big W", r"\bbig w\b|bigw\.com\.au"),
    ("Kogan", r"\bkogan\b"),
    ("Chemist Warehouse", r"chemist ?warehouse"),
    ("David Jones", r"david jones|davidjones\.com"),
    ("Costco", r"\bcostco\b"),
)


def to_number(text: str) -> float | int:
    value = float(text.replace(",", ""))
    return int(value) if value.is_integer() else value


def collapse(text: str) -> str:
    return " ".join(text.split())


def split_title(title: str) -> tuple[str, str | None]:
    """Return (title before the trailing `@ Merchant`, merchant or None).

    The merchant is introduced by the last `@` outside parentheses, so "(Price Beat @ Bunnings)"
    doesn't count; with several merchants ("@ Amazon, Officeworks") only the first is kept."""
    top_level = [
        m
        for m in AT_RE.finditer(title)
        if title[: m.start()].count("(") <= title[: m.start()].count(")")
    ]
    if not top_level:
        return title, None
    m = top_level[-1]
    first = re.split(r",\s*(?![^()]*\))", title[m.end() :])[0]
    return title[: m.start()], collapse(first)


def parse_price(body: str) -> tuple[float | int, int, int] | None:
    """First explicit single AUD price in `body` as (amount, start, end), else None."""
    cut = DELIVERY_RE.search(body)
    core = body[: cut.start()] if cut else body
    if re.match(r"\s*\d+\s*x\s", core, re.I):  # "2x Sonos Era 100 $414": a multi-unit price
        return None
    masked = WAS_RE.sub(lambda m: " " * len(m.group()), core)  # RRP/Was amounts aren't the price
    candidates = []
    for m in PRICE_RE.finditer(masked):
        before = masked[: m.start()]
        if to_number(m.group(1)) == 0 or before.count("(") > before.count(")"):
            continue  # $0 delivery, or a "(Min $80 Spend)" qualifier
        candidates.append(m)
    if len(candidates) != 1:  # none, or several products/tiers in one title
        return None
    m = candidates[0]
    if NOT_PRICE_AFTER_RE.match(masked[m.end() :]) or NOT_PRICE_BEFORE_RE.search(
        masked[: m.start()]
    ):
        return None
    return to_number(m.group(1)), m.start(), m.end()


def parse_was_price(body: str, price: float | int) -> float | int | None:
    m = WAS_RE.search(body)
    if not m:
        return None
    was = to_number(m.group(1))
    return was if was > price else None


def parse_conditions(body: str, merchant: str | None) -> str:
    cut = DELIVERY_RE.search(body)
    # "@ Costco (Membership Required)": a merchant-side parenthetical is part of the marker text.
    notes = " ".join(re.findall(r"\(([^)]*)\)", merchant or ""))
    text = f"{body[: cut.start()] if cut else body} {notes}".lower()
    found = []
    for label, pattern in CONDITIONS:
        # "Delivered / NSW C&C" offers both ways, so C&C after "Delivered" isn't a requirement.
        scope = re.split(r"\bdeliver(?:y|ed)\b", text)[0] if label == "需到店自提" else text
        if re.search(pattern, scope):
            found.append(label)
            if label == "仅新客":  # don't also count its "members" as 仅会员
                text = re.sub(pattern, " ", text)
    return "、".join(found)


def clean_retailer(merchant: str | None, domain: str | None) -> str:
    raw = re.sub(r"\s*\([^)]*\)\s*$", "", merchant or "").strip() or (domain or "")
    for name, pattern in CANONICAL_RETAILERS:
        if re.search(pattern, raw.lower()):
            return name
    return raw


def make_item(body: str, price_start: int, price_end: int) -> str:
    """Title minus price fragment (and everything after it, unless the price leads) and merchant."""

    def strip_lead(text: str) -> str:  # [PS5, eBay Plus] / [NSW] tags and "50% off " openers
        text = re.sub(r"^(?:\s*\[[^\]]*\])+", "", text)
        return re.sub(r"^\s*(?:up to\s+)?\d+%\s*off\s+", "", text, flags=re.I)

    text = strip_lead(body[:price_start])
    if len(collapse(text)) < 3:  # price leads the title: keep what follows it
        text = strip_lead(body[:price_start] + body[price_end:])
    text = re.sub(
        r"(?:\s+(?:from|for|only|at|just|now|eg|via|delivered|shipped))+\s*$", "", text, flags=re.I
    )
    if text.count("(") > text.count(")"):
        text = text[: text.rindex("(")]
    return collapse(re.sub(r"[\s\-–:,(+/~]+$", "", text))


# ---------------------------------------------------------------------------
# Keys (weakest field): explicit token rules, then a derived slug
# ---------------------------------------------------------------------------
_PS5 = r"\b(?:ps5|playstation\s?5)\b"
_PS5_CONSOLE = r"\bconsole\b|digital edition|\bslim\b"
_PS5_VETO = (r"\bpro\b|controller|dualsense|headset|pulse|camera|remote|charging|vr2|portal",)
_ACCESSORY = (r"\b(?:case|cover|strap|band|charger|cable|protector|stand|dock|mount|bracket)s?\b",)
_CONSUMABLE = (r"\b(?:replacement|brush heads?|refills?)\b",)
_SWITCH_VETO = _ACCESSORY + (
    r"\b(?:game|edition|controller|joy-?con|camera|adapter|card|bag|grip|carry)s?\b",
)

# (key, all patterns must match the lowercased title, none of the veto patterns may).
# Most specific first. Keys are all from data/bf2026/watch.json or points/curated.json
# (checked at startup); the 25 watch keys are marked.
KEY_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("dyson-airwrap-id", (r"airwrap", r"\bi\.?d\b"), ()),
    ("dyson-airwrap-origin", (r"airwrap", r"\borigin\b"), ()),
    ("dyson-airwrap", (r"airwrap",), ()),  # watch
    ("dyson-nural", (r"\bnural\b",), ()),
    ("dyson-supersonic", (r"dyson", r"supersonic"), ()),  # watch
    ("dyson-gen5", (r"gen\s?5", r"dyson|detect"), (r"outsize",)),  # watch
    ("dyson-v15", (r"\bv15\b", r"dyson|detect"), ()),  # watch
    ("dyson-v10", (r"\bv10\b", r"dyson"), ()),
    ("dyson-v7", (r"\bv7\b", r"dyson"), ()),
    ("roborock-curv", (r"q\s?revo\s*curv",), ()),  # watch
    ("roborock-edgec", (r"q\s?revo\s*edge\s?c",), ()),
    ("roborock-s8", (r"roborock", r"\bs8\b"), ()),
    ("ecovacs-t50", (r"ecovacs|deebot", r"\bt50\b"), ()),
    ("breville-impress", (r"barista express impress|bes876",), ()),
    ("breville-bes870", (r"barista express|bes870",), (r"impress",)),  # watch
    ("breville-bambino", (r"bambino",), ()),
    ("ninja-creami", (r"\bcreami\b",), (r"deluxe|swirl|slushi|nc501",)),  # watch
    ("vertuo-pop", (r"vertuo\s*pop",), ()),  # watch
    ("kitchenaid", (r"kitchenaid", r"mixer|artisan|stand"), ()),  # watch
    ("kindle-pw", (r"paperwhite",), _ACCESSORY),  # watch
    ("sony-xm6", (r"wh-?1000xm6|\bxm6\b",), ()),  # watch
    ("airpods-pro-3", (r"airpods pro\s*(?:3\b|\(?3rd)",), ()),  # watch
    ("airpods-pro-2", (r"airpods pro\s*(?:2\b|\(?2nd)",), ()),
    ("apple-watch", (r"apple watch",), _ACCESSORY),  # watch
    ("macbook-air", (r"macbook air", r"\bm5\b"), ()),  # watch
    ("mba-m2", (r"macbook air", r"\bm2\b"), ()),
    ("ps5-bundle", (_PS5, _PS5_CONSOLE, r"bundle|\+"), _PS5_VETO),
    ("ps5", (_PS5, _PS5_CONSOLE), _PS5_VETO),  # watch
    ("switch-2", (r"nintendo switch 2\b",), _SWITCH_VETO),  # watch
    ("switch-oled", (r"switch oled",), _SWITCH_VETO),
    ("sonos", (r"\bsonos\b",), _ACCESSORY),  # watch
    ("garmin-fr265", (r"forerunner\s*265",), ()),  # watch
    ("garmin-instinct2", (r"garmin", r"instinct\s*2"), ()),
    ("garmin-vivoactive5", (r"vivoactive\s*5",), ()),
    ("lululemon", (r"lululemon",), ()),  # watch
    ("comvita", (r"comvita", r"manuka|honey|umf"), ()),  # watch
    ("blackmores-cal", (r"blackmores", r"calcium|\bcal\b"), ()),
    ("swisse-blackmores", (r"swisse|blackmores",), ()),  # watch
    ("oralb-io3", (r"oral-?b", r"\bio\s?(?:series\s?)?3\b"), _CONSUMABLE),
    ("oralb-io7", (r"oral-?b", r"\bio\s?(?:series\s?)?7\b"), _CONSUMABLE),
    ("oralb-io", (r"oral-?b", r"\bio\b"), _CONSUMABLE),  # watch
    ("t2-tea-books", (r"\bt2\b", r"tea\s*(?:&|and)\s*books?"), ()),  # watch
    ("boody-socks", (r"boody", r"socks?"), ()),  # watch
    ("pandora-bracelet", (r"pandora", r"bracelet|bangle"), ()),  # watch
    ("pixel-9a", (r"pixel\s*9a",), ()),
    ("samsung-990pro", (r"990\s*pro",), ()),
    ("moto-edge60", (r"edge\s*60", r"motorola|moto"), (r"\bpro\b",)),
    ("shark-stain", (r"stain\s*striker",), ()),
    ("trusens", (r"trusens",), ()),
)

SLUG_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "for", "with", "of", "to", "in", "on", "at", "by", "from",
        "only", "new", "free", "off", "up", "plus", "pack", "bundle", "delivered", "delivery",
        "shipped", "buy", "get", "save", "sale", "deal", "deals", "now", "just", "via", "inc",
        "incl", "e", "g", "eg",
    }
)
SLUG_UNIT_RE = re.compile(r"^\d+(?:gb|tb|mb|w|v|l|ml|g|kg|cm|mm|hz|mah|pk|pcs?|pack)$")
SLUG_MAX_TOKENS = 4


def derive_slug(item: str) -> str | None:
    ascii_item = unicodedata.normalize("NFKD", item).encode("ascii", "ignore").decode().lower()
    tokens = [
        t
        for t in re.findall(r"[a-z0-9]+", ascii_item.replace("'", ""))
        if t not in SLUG_STOPWORDS and not SLUG_UNIT_RE.match(t)
    ]
    return "-".join(tokens[:SLUG_MAX_TOKENS]) or None


def match_known_key(item: str) -> str | None:
    text = item.lower()
    for key, needs, vetoes in KEY_RULES:
        if all(re.search(p, text) for p in needs) and not any(re.search(p, text) for p in vetoes):
            return key
    return None


# ---------------------------------------------------------------------------
# Categories: first matching list wins; default 其他
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "保健食品",
        (
            "vitamin", "multivitamin", "supplement", "protein", "whey", "collagen", "omega",
            "fish oil", "probiotic", "creatine", "pre-workout", "gummies", "manuka", "umf",
            "comvita", "blackmores", "swisse", "bio island", "nature's way", "centrum",
            "elevit", "ostelin", "cenovis", "musashi", "optimum nutrition", "bulk nutrients",
            "myprotein", "berocca", "magnesium", "zinc", "electrolyte", "wpi", "isolate", "bcaa",
            "ehplabs",
        ),
    ),
    (
        "美妆个护",
        (
            "skincare", "skin care", "moisturiser", "moisturizer", "serum", "cleanser",
            "sunscreen", "spf", "lipstick", "mascara", "foundation", "makeup", "make-up",
            "perfume", "fragrance", "cologne", "eau de", "edp", "edt", "shampoo",
            "conditioner", "hair dryer", "hairdryer", "hair straightener", "straightener",
            "hair clipper", "curling", "airwrap", "supersonic", "toothbrush", "toothpaste",
            "oral-b", "razor", "shaver", "trimmer", "epilator", "ipl", "body wash",
            "deodorant", "lotion", "face cream", "hand cream", "night cream", "aesop", "mecca",
            "sephora", "sukin", "cetaphil", "cerave", "neutrogena", "la roche", "olay",
            "clinique", "estee lauder", "lancome", "l'oreal", "ghd", "gillette", "oneblade",
            "water flosser", "waterpik", "nail polish", "hair removal", "theragun", "massager",
            "exfoliant", "bha", "retinol", "niacinamide", "paula's choice", "the ordinary",
        ),
    ),
    (
        "礼品",
        (
            "gift card", "egift", "gift voucher", "gift set", "gift pack", "gift box",
            "gift hamper", "hamper", "advent calendar", "stocking filler", "secret santa",
            "pandora", "boody", "t2 tea", "jewellery", "jewelry", "necklace", "bracelet",
            "earrings", "candle", "chocolate", "tea set",
        ),
    ),
    (
        "家电厨房",
        (
            "vacuum", "robovac", "air fryer", "airfryer", "coffee machine", "coffee maker",
            "coffee grinder", "grinder", "espresso", "nespresso", "circulator",
            "blender", "mixer", "fridge", "freezer", "refrigerator", "washing machine",
            "washer", "dryer", "dishwasher", "microwave", "oven", "cooktop", "rangehood",
            "kettle", "toaster", "rice cooker", "slow cooker", "pressure cooker",
            "multicooker", "thermomix", "air purifier", "purifier", "humidifier",
            "dehumidifier", "heater", "fan", "air conditioner", "split system", "steam mop",
            "mop", "iron", "juicer", "food processor", "waffle", "frypan", "cookware",
            "saucepan", "knife", "kitchen", "sodastream", "water filter", "dyson", "roborock",
            "ecovacs", "shark", "kitchenaid", "breville", "ninja", "delonghi", "de'longhi",
            "sunbeam", "tefal", "miele", "bosch", "karcher", "pressure washer", "creami",
        ),
    ),
    (
        "户外运动",
        (
            "tent", "camping", "camp", "hiking", "sleeping bag", "kayak", "paddle", "bike",
            "bicycle", "e-bike", "ebike", "scooter", "skateboard", "helmet", "treadmill",
            "dumbbell", "kettlebell", "barbell", "weights", "gym", "yoga", "pilates",
            "fitness", "running", "runners", "trail running", "sneakers", "nike", "adidas", "asics",
            "brooks", "hoka", "new balance", "salomon", "merrell", "lululemon", "patagonia",
            "north face", "macpac", "kathmandu", "rip curl", "wetsuit", "surf", "snorkel",
            "golf", "fishing", "cricket", "tennis", "racquet", "soccer", "basketball",
            "swim", "goggles", "esky", "cooler", "yeti", "hydro flask", "water bottle",
            "trampoline", "bbq", "barbecue", "weber", "garmin forerunner", "garmin fenix",
            "garmin instinct", "garmin venu", "garmin vivoactive", "garmin epix",
            "garmin enduro", "athletic", "activewear", "workout", "reebok", "mizuno", "puma",
            "under armour", "saucony", "skechers", "netball", "gymshark",
        ),
    ),
    (
        "数码电子",
        (
            "tv", "television", "oled", "qled", "mini-led", "monitor", "laptop", "notebook",
            "macbook", "imac", "mac mini", "ipad", "tablet", "tab", "iphone", "galaxy",
            "pixel", "smartphone", "phone", "headphones", "earbuds", "earphones", "airpods",
            "buds", "headset", "speaker", "soundbar", "sonos", "bose", "jbl", "sony", "ssd",
            "hdd", "nvme", "microsd", "sd card", "usb", "flash drive", "hard drive", "nas",
            "router", "wi-fi", "wifi", "mesh", "modem", "gpu", "graphics card", "rtx",
            "radeon", "ryzen", "intel", "cpu", "qhd", "uhd", "4k", "ips", "evnia", "ultrawide",
            "microsdxc", "sdxc", "sdhc", "micro sd", "audio", "processor", "motherboard", "ram",
            "ddr4", "ddr5", "keyboard", "mouse", "webcam", "camera", "gopro", "dji", "drone",
            "lens",
            "printer", "projector", "ps5", "ps4", "playstation", "xbox", "nintendo",
            "switch 2", "steam deck", "gaming", "smartwatch", "apple watch", "galaxy watch",
            "fitbit", "garmin", "kindle", "kobo", "e-reader", "charger", "power bank",
            "powerbank", "usb-c", "adapter", "smart plug", "smart home", "tp-link",
            "doorbell", "cctv", "dash cam", "dashcam", "airtag", "chromebook", "thinkpad",
            "lenovo", "asus", "acer", "msi", "logitech", "razer", "anker", "ugreen", "motorola",
            "moto", "elgato", "bluetooth", "hue", "nanoleaf", "insta360", "console", "thunderbolt",
            "dock", "hisense", "tcl", "lg", "xiaomi", "oppo", "oneplus", "realme", "laser",
            "multi-function", "dab+", "bitdefender", "synology", "qnap", "seagate", "sandisk",
            "corsair", "kingston", "gigabyte", "nvidia", "netgear", "ubiquiti",
        ),
    ),
)


# Fallback when the title has no keyword: specialist retailers whose whole range is one category.
RETAILER_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "数码电子",
        (
            "umart", "scorptec", "pc case gear", "centre com", "centrecom", "mwave", "evatech",
            "msy", "ple computers", "computer alliance", "digidirect", "bambu lab", "eb games",
            "camera house", "samsung", "lenovo", "hp", "dell", "asus", "acer", "apple", "google",
            "sony", "logitech",
        ),
    ),
    ("户外运动", ("kathmandu", "macpac", "bcf", "anaconda", "rebel sport", "decathlon")),
    ("美妆个护", ("mecca", "sephora", "aesop", "lookfantastic", "adore beauty")),
    ("保健食品", ("vitacost", "iherb", "bulk nutrients", "myprotein")),
)


def compile_keywords(words: tuple[str, ...]) -> re.Pattern[str]:
    alternatives = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9])(?:{alternatives})(?:s|es)?(?![a-z0-9])", re.I)


CATEGORY_PATTERNS = tuple((cat, compile_keywords(words)) for cat, words in CATEGORY_KEYWORDS)


RETAILER_PATTERNS = tuple((cat, compile_keywords(words)) for cat, words in RETAILER_KEYWORDS)


def classify(title: str, retailer: str) -> str:
    for patterns, text in ((CATEGORY_PATTERNS, title), (RETAILER_PATTERNS, retailer)):
        for category, pattern in patterns:
            if pattern.search(text):
                return category
    return "其他"


# ---------------------------------------------------------------------------
# Listing-page cards -> rows
# ---------------------------------------------------------------------------
POSTED_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s*-\s*\d{1,2}:\d{2}")


def parse_cards(html: str) -> list[dict]:
    """Deal cards on one listing page. `node-teaser` is the normal card; page 0 also pins
    `node-page` cards (store-rep posts) that carry the same title/votes/date. Forum/poll nodes
    are not `node-ozbdeal` and are ignored."""
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for div in soup.select("div.node-ozbdeal"):
        node_id = (div.get("id") or "").removeprefix("node")
        heading = div.select_one("h2.title")
        link = div.select_one(f'h2.title a[href="/node/{node_id}"]')
        if not (node_id.isdigit() and heading and link):
            continue
        title = collapse(heading.get("data-title") or link.get_text())
        submitted = div.select_one(".submitted")
        posted = POSTED_RE.search(submitted.get_text(" ")) if submitted else None
        via = div.select_one(".submitted .via a") or div.select_one(
            "ul.submitted li:has(i.fa-link)"
        )
        cards.append(
            {
                "node_id": node_id,
                "title": title,
                "posted": posted.groups() if posted else None,
                "up": _vote_count(div, ".n-vote .voteup span"),
                "down": _vote_count(div, ".n-vote .votedown span"),
                "domain": collapse(via.get_text()) if via else None,
            }
        )
    return cards


def _vote_count(div, selector: str) -> int | None:
    el = div.select_one(selector)
    try:
        return int(el.get_text(strip=True).replace(",", "")) if el else None
    except ValueError:
        return None


def season_year(d: date, start: tuple[int, int], end: tuple[int, int]) -> int | None:
    """The season a date falls in (the year the window opens), or None outside the window."""
    md = (d.month, d.day)
    if start <= end:
        return d.year if start <= md <= end else None
    if md >= start:
        return d.year
    return d.year - 1 if md <= end else None


def build_row(
    card: dict, retrieved_at: str, known: dict[str, str], event_slug: str = "black-friday"
) -> tuple[dict | None, str]:
    """Return (row, "") or (None, skip_reason)."""
    title = card["title"]
    body, merchant = split_title(title)
    priced = parse_price(body)
    if priced is None:
        return None, "no_price" if "$" not in body else "unusable_price"
    price, start, end = priced
    if not card["posted"]:
        return None, "no_date"
    day, month, year = (int(x) for x in card["posted"])
    try:
        posted = date(year, month, day)
    except ValueError:
        return None, "no_date"
    item = make_item(body, start, end)
    retailer = clean_retailer(merchant, card["domain"])
    key = match_known_key(item) or derive_slug(item)
    if not (item and retailer and key):
        return None, "unparsed_name"
    up, down = card["up"], card["down"]
    event_label, windows = EVENT_SEASONS[event_slug]
    in_season = any(season_year(posted, ws, we) is not None for ws, we in windows)
    return {
        "id": f"ozb-{card['node_id']}",
        "key": key,
        "item": item,
        "model": None,
        "category": known.get(key) or classify(body, retailer),
        "retailer": retailer,
        "date": posted.isoformat(),
        "event": event_label if in_season else "其他促销",
        "price": price,
        "was_price": parse_was_price(body, price),
        "was_suspect": False,
        "conditions": parse_conditions(body, merchant),
        "votes": up - down if up is not None and down is not None else None,
        "history_low": False,
        "source": f"https://www.ozbargain.com.au/node/{card['node_id']}",
        "evidence": title[:200],
        "retrieved_at": retrieved_at,
        "note": "",
    }, ""


def load_known_categories() -> tuple[dict[str, str], set[str]]:
    """key -> category from curated.json + watch.json (watch wins), and the watch key set."""
    known: dict[str, str] = {}
    for row in json.loads((DATA / "points" / "curated.json").read_text(encoding="utf-8")):
        known[row["key"]] = row["category"]
    watch = json.loads((DATA / "watch.json").read_text(encoding="utf-8"))
    watch_keys = {w["key"] for w in watch}
    known.update({w["key"]: w["category"] for w in watch})
    rule_keys = {key for key, _, _ in KEY_RULES}
    if unknown := rule_keys - known.keys():
        sys.exit(f"KEY_RULES keys not in watch.json/curated.json: {sorted(unknown)}")
    if uncovered := watch_keys - rule_keys:
        sys.exit(f"watch.json keys without a KEY_RULES entry: {sorted(uncovered)}")
    return known, watch_keys


# ---------------------------------------------------------------------------
# Crawl + CLI
# ---------------------------------------------------------------------------
def parse_page_range(text: str) -> range:
    first, _, last = text.partition("-")
    try:
        a, b = int(first), int(last or first)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--pages must be N or A-B, got {text!r}") from None
    if a < 0 or b < a:
        raise argparse.ArgumentTypeError(f"--pages range is invalid: {text!r}")
    return range(a, b + 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pages", type=parse_page_range, default="0-219", help="inclusive, e.g. 0-219")
    ap.add_argument("--max-pages", type=int, default=None, help="stop after this many pages")
    ap.add_argument("--delay", type=float, default=MIN_DELAY, help=f"seconds, >= {MIN_DELAY}")
    ap.add_argument("--event", choices=sorted(EVENT_SEASONS), default="black-friday")
    ap.add_argument("--out", type=Path, default=None, help="default: points/ozbargain[-EVENT].json")
    ap.add_argument("--save-html", type=Path, default=None, help="default: a new temp dir")
    ap.add_argument("--from-html", type=Path, default=None, help="re-parse saved pages offline")
    args = ap.parse_args()
    if args.delay < MIN_DELAY:
        ap.error(f"--delay must be >= {MIN_DELAY} (PRD 5.2)")
    if args.out is None:
        suffix = "" if args.event == "black-friday" else f"-{args.event}"
        args.out = DATA / "points" / f"ozbargain{suffix}.json"
    url = EVENT_URL.format(slug=args.event)
    event_label, windows = EVENT_SEASONS[args.event]

    known, watch_keys = load_known_categories()
    offline = args.from_html is not None
    html_dir = args.from_html or args.save_html or Path(tempfile.mkdtemp(prefix="ozb-bf2026-"))
    html_dir.mkdir(parents=True, exist_ok=True)

    def page_file(n: int) -> Path:
        return html_dir / f"page-{n:03d}.html"

    pages = list(args.pages)[: args.max_pages]
    if offline:
        mtimes = [page_file(n).stat().st_mtime for n in pages if page_file(n).exists()]
        fetched = datetime.fromtimestamp(min(mtimes), SYDNEY) if mtimes else datetime.now(SYDNEY)
    else:
        fetched = datetime.now(SYDNEY)
    retrieved_at = fetched.date().isoformat()

    # check.py wants ids unique across every points/*.json; a node tagged with two events
    # lives in whichever file was written first, so skip ids already in the sibling files.
    other_ids = {
        row["id"]
        for path in args.out.parent.glob("*.json")
        if path.resolve() != args.out.resolve()
        for row in json.loads(path.read_text(encoding="utf-8"))
    }
    rows: dict[str, dict] = {}
    skips: Counter[str] = Counter()
    pages_fetched = cards_seen = 0
    last_page_with_cards = None
    stop = f"page range exhausted at {pages[-1]}" if pages else "no pages requested"
    problem = ""
    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30
    ) as client:
        for i, page in enumerate(pages):
            if offline:
                if not page_file(page).exists():
                    stop = f"no saved HTML for page={page}"
                    break
                html = page_file(page).read_text(encoding="utf-8")
            else:
                if i:
                    time.sleep(args.delay)
                try:
                    resp = client.get(url, params={"page": page})
                except httpx.HTTPError as exc:
                    problem = f"request for page={page} failed ({exc!r}); stopping, no retry"
                    break
                if resp.status_code in (403, 429):
                    problem = f"HTTP {resp.status_code} on page={page}: blocked; stopping, no retry"
                    break
                if resp.status_code == 404 and page > 0:  # site caps listings at 200 pages
                    stop = f"HTTP 404 at page={page} (past the site's last page)"
                    break
                if resp.status_code != 200:
                    problem = f"HTTP {resp.status_code} on page={page}; stopping, no retry"
                    break
                html = resp.text
                page_file(page).write_text(html, encoding="utf-8")
            pages_fetched += 1
            cards = parse_cards(html)
            print(f"page={page}: {len(cards)} cards", file=sys.stderr)
            if not cards:
                if page == 0:
                    problem = "page=0 parsed zero cards (layout change or block page?)"
                else:
                    stop = f"zero cards at page={page}"
                break
            cards_seen += len(cards)
            last_page_with_cards = page
            for card in cards:
                if f"ozb-{card['node_id']}" in other_ids:
                    skips["in_other_points_file"] += 1
                    continue
                row, reason = build_row(card, retrieved_at, known, args.event)
                if row is None:
                    skips[reason] += 1
                elif row["id"] not in rows:
                    rows[row["id"]] = row

    out_rows = list(rows.values())
    print(f"\nevent: {args.event} ({url})")
    print(f"HTML: {html_dir}")
    print(f"pages {'parsed' if offline else 'fetched'}: {pages_fetched}")
    print(f"last page with cards: {last_page_with_cards}; stopped: {stop}")
    print(f"cards seen: {cards_seen}")
    print(f"rows kept: {len(out_rows)}")
    print(f"rows skipped: {sum(skips.values())} {dict(skips)}")
    print("  no_price = no '$' in title; unusable_price = '$' present but foreign/range/from/spend")
    if out_rows:
        hits = Counter(
            "watch" if r["key"] in watch_keys else "curated" if r["key"] in known else "derived"
            for r in out_rows
        )
        print(f"keys: watch={hits['watch']} curated-variant={hits['curated']} "
              f"derived={hits['derived']}")
        posted_years = Counter(r["date"][:4] for r in out_rows)
        print("rows per posted year:", dict(sorted(posted_years.items())))
        in_season = [r for r in out_rows if r["event"] == event_label]
        seasons = Counter(
            next(
                (
                    y
                    for ws, we in windows
                    if (y := season_year(date.fromisoformat(r["date"]), ws, we)) is not None
                ),
                None,
            )
            for r in in_season
        )
        print(f"{event_label} rows per season year:", dict(sorted(seasons.items())))
        print("rows per category:", dict(Counter(r["category"] for r in out_rows).most_common()))
        print("rows per event:", dict(Counter(r["event"] for r in out_rows)))
        print("with was_price:", sum(r["was_price"] is not None for r in out_rows))
        print("with votes:", sum(r["votes"] is not None for r in out_rows))
        print("with conditions:", sum(bool(r["conditions"]) for r in out_rows))

    if out_rows:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(out_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.out}")
    if problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    if not out_rows:
        print("ERROR: no rows produced; nothing written", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
