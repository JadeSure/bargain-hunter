#!/usr/bin/env python3
"""Build data/bf2026/points/chemistwarehouse.json from Chemist Warehouse product pages.

Why this source: 保健食品 and 礼品 were the two thinnest categories in the dataset, and
almost no row anywhere had a `was_price`. Chemist Warehouse server-renders both the
selling price and its "Don't Pay RRP" figure into the product page, so each row arrives
with a reference price a reviewer can see at `source`.

Two things to know about the numbers this produces:

  * RRP is a manufacturer list price, not a price Chemist Warehouse previously charged.
    It is the inflated-reference-price case `was_suspect` exists for, so every row with
    a `was_price` here sets `was_suspect = True`. These rows are a baseline to measure a
    Black Friday price against, not evidence of a 50%-off sale.
  * `date` is the day the page was read, and `event` is whatever season that day falls
    in. Run this outside 11-10..12-02 and you get 平日 baselines; run it during the
    season and you get 黑五季 rows.

Product URLs come from the sitemap the site publishes
(https://static.chemistwarehouse.com.au/AMS/sitemap/cwh_sitemap.xml). robots.txt
disallows /search, /native-search and the ?category=/?brand= filter URLs, so the
sitemap is the only listing this script reads.

Usage: fetch_chemistwarehouse.py [--supplements 450] [--gifts 350] [--out-dir data/bf2026]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

UA = (
    "bargain-hunter/0.1 (personal money-saving guide collector; "
    "+https://github.com/versent-shawn/bargain-hunter)"
)
SITEMAP = "https://static.chemistwarehouse.com.au/AMS/sitemap/cwh/products.xml"
# These are Australian shelf prices, so the day they belong to is the Australian day,
# not UTC — matching the sibling fetch_ozbargain.py.
SYDNEY = ZoneInfo("Australia/Sydney")
DELAY = 2.2

# Slug fragments that identify the two categories we are short of. Supplement brands are
# listed by name because the slugs carry no category marker.
SUPPLEMENT = (
    "swisse",
    "blackmores",
    "bioglan",
    "ostelin",
    "nature-s-own",
    "natures-own",
    "caruso",
    "cenovis",
    "ethical-nutrients",
    "fusion-health",
    "thompson",
    "nature-s-way",
    "natures-way",
    "herbs-of-gold",
    "inner-health",
    "bio-island",
    "life-space",
    "go-healthy",
    "vitamin",
    "fish-oil",
    "krill",
    "magnesium",
    "collagen",
    "probiotic",
    "multivitamin",
    "coq10",
    "glucosamine",
    "turmeric",
    "melatonin",
)
GIFT = ("gift-set", "gift-pack", "giftset", "gift-box", "piece-set", "-gift-")

PRICE_RE = re.compile(r'<h2 class="display-l[^"]*">\$([0-9][0-9,]*\.?[0-9]*)</h2>')
RRP_RE = re.compile(r"Pay RRP \$([0-9][0-9,]*\.?[0-9]*)")
OFF_RE = re.compile(r"\$([0-9][0-9,]*\.?[0-9]*) Off RRP")
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:  # noqa: S310 - fixed https host
        return r.read().decode("utf-8", "replace")


def money(s: str) -> float:
    return float(s.replace(",", ""))


def text_of(fragment: str) -> str:
    plain = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return unicodedata.normalize("NFKC", plain).strip()


def slug_of(url: str) -> str:
    raw = url.rstrip("/").rsplit("/", 1)[-1].lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return cleaned or "unknown"


def spread(urls: list[str], want: int) -> list[str]:
    """Take `want` urls spaced evenly through the sorted list, so one brand can't fill it."""
    urls = sorted(urls)
    if want >= len(urls):
        return urls
    step = len(urls) / want
    return [urls[int(i * step)] for i in range(want)]


def event_for(day: datetime) -> str:
    md = (day.month, day.day)
    if (11, 10) <= md <= (12, 2):
        return "黑五季"
    if md >= (12, 24) or md <= (1, 15):
        return "节礼日"
    return "平日"


def parse(url: str, page: str) -> dict | None:
    prices = PRICE_RE.findall(page)
    if not prices:
        return None
    price = money(prices[0])
    if price <= 0:
        return None
    titles = H1_RE.findall(page)
    item = text_of(titles[0]) if titles else ""
    if not item:
        return None

    rrp = RRP_RE.findall(page)
    was = money(rrp[0]) if rrp else None
    if was is not None and was <= price:
        was = None

    bits = [f"${price:.2f}"]
    off = OFF_RE.findall(page)
    if off:
        bits.append(f"${money(off[0]):.2f} Off RRP")
    if was is not None:
        bits.append(f"Don't Pay RRP ${was:.2f}")
    return {
        "item": item,
        "price": price,
        "was_price": was,
        "evidence": " | ".join(bits)[:200],
        "key": slug_of(url),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--supplements", type=int, default=450)
    ap.add_argument("--gifts", type=int, default=350)
    ap.add_argument("--out-dir", default="data/bf2026")
    args = ap.parse_args(argv)

    now = datetime.now(SYDNEY)
    today = now.strftime("%Y-%m-%d")
    event = event_for(now)

    print(f"sitemap: {SITEMAP}", file=sys.stderr)
    locs = re.findall(r"<loc>([^<]+)</loc>", get(SITEMAP))
    gifts = [u for u in locs if any(k in u for k in GIFT)]
    gift_set = set(gifts)
    supps = [u for u in locs if u not in gift_set and any(k in u for k in SUPPLEMENT)]
    picked = [("保健食品", u) for u in spread(supps, args.supplements)]
    picked += [("礼品", u) for u in spread(gifts, args.gifts)]
    print(
        f"sitemap has {len(locs)} products; {len(supps)} supplement / {len(gifts)} gift "
        f"candidates; fetching {len(picked)}",
        file=sys.stderr,
    )

    rows, skipped, failed, gone = [], 0, 0, 0
    for n, (category, url) in enumerate(picked, 1):
        if n > 1:
            time.sleep(DELAY)
        try:
            page = get(url)
        except urllib.error.HTTPError as exc:
            # The sitemap keeps delisted products, so a 404 is routine; anything else
            # (403, 429, 5xx) means the site is pushing back and the run should stop.
            if exc.code == 404:
                gone += 1
                continue
            print(f"  [{n}/{len(picked)}] HTTP {exc.code} on {url}, stopping", file=sys.stderr)
            break
        except (urllib.error.URLError, OSError) as exc:
            failed += 1
            print(f"  [{n}/{len(picked)}] fetch failed {url}: {exc}", file=sys.stderr)
            if failed > 20:
                print("too many connection failures, stopping", file=sys.stderr)
                break
            continue
        got = parse(url, page)
        if got is None:
            skipped += 1
            continue
        rows.append(
            {
                "id": f"cur-cw-{len(rows) + 1:03d}",
                "key": got["key"],
                "item": got["item"],
                "model": None,
                "category": category,
                "retailer": "Chemist Warehouse",
                "date": today,
                "event": event,
                "price": got["price"],
                "was_price": got["was_price"],
                # RRP is a manufacturer list price, never a price CW itself charged.
                "was_suspect": got["was_price"] is not None,
                "conditions": "",
                "votes": None,
                "history_low": False,
                "source": url,
                "evidence": got["evidence"],
                "retrieved_at": today,
                "note": (
                    "Chemist Warehouse 商品页当日在线价；was_price 取页面的 "
                    "Don't Pay RRP，是厂商建议零售价而非该店此前售价，故 was_suspect 为 true"
                    if got["was_price"] is not None
                    else "Chemist Warehouse 商品页当日在线价；页面未印 RRP"
                ),
            }
        )
        if n % 50 == 0:
            print(f"  [{n}/{len(picked)}] {len(rows)} rows, {skipped} skipped", file=sys.stderr)

    out = Path(args.out_dir) / "points" / "chemistwarehouse.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with_was = sum(1 for r in rows if r["was_price"] is not None)
    print(
        f"wrote {out}: {len(rows)} rows ({with_was} with RRP), "
        f"{skipped} pages had no price, {gone} delisted (404), {failed} connection failures",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
