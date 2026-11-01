#!/usr/bin/env python3
"""Build data/bf2026/promos/ozbargain.json from OzBargain's gift-card and reward-points tags.

Why this source: of the six `kind` values check.py allows, 礼品卡折扣 had one row and
积分加倍 had none, so the two levers Australian shoppers actually stack ahead of a sale —
buy the gift card at a discount, then earn multiplied points on it — were missing
entirely. OzBargain tags both: /tag/gift-card and /tag/reward-points.

Each row's `evidence` is the deal title, which is where the discount is stated, and
`source` is the deal node, so the figure is visible at the link. Titles that announce a
giveaway or a competition rather than a standing discount are dropped; the run prints
how many and why.

`start` is the day the deal was posted, which is when the offer appeared; OzBargain
listing titles rarely carry an end date, so `end` stays null unless the title states one.

Deps and pacing are the sibling fetch_ozbargain.py's; not wired into any workflow.

Usage: fetch_ozbargain_promos.py [--pages 0-14] [--delay 2.0] [--out ...]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_ozbargain import (  # noqa: E402 - sibling script, path set above
    MIN_DELAY,
    SYDNEY,
    USER_AGENT,
    collapse,
    parse_cards,
    split_title,
)

DATA = Path(__file__).resolve().parents[2] / "data" / "bf2026"
TAGS = ("gift-card", "reward-points")
TAG_URL = "https://www.ozbargain.com.au/tag/{tag}"
NODE_URL = "https://www.ozbargain.com.au/node/{node_id}"

# Checked in order: a title like "20x Flybuys Points on Apple Gift Cards" is a points
# multiplier first and a gift-card deal second.
# \d[\d,]* rather than \d+ so a thousands separator ("10,000 Flybuys Points") is part of
# the number instead of leaving "000" behind as the match.
_COUNT = r"\d[\d,]*(?:\.\d+)?"
POINTS_RE = re.compile(
    rf"\b{_COUNT}x\s*(?:\w+\s+){{0,2}}points?\b|\bbonus\s+(?:\w+\s+){{0,2}}points?\b"
    rf"|\bpoints?\s+bonus\b|\bdouble\s+points?\b|\b{_COUNT}\s*(?:bonus\s+)?"
    rf"(?:flybuys|velocity|qantas)\s+points?\b",
    re.I,
)
CASHBACK_RE = re.compile(r"\bupsized\b|\bcash\s?back\b", re.I)
# "Sitewide", "storewide", "everything" — a discount on the whole shop rather than a line.
SITEWIDE_RE = re.compile(
    r"\bsite\s?wide\b|\bstore\s?wide\b|\bentire\s+(?:store|site|range|order)\b"
    r"|\beverything\b|\ball\s+(?:full[-\s]priced?|orders?)\b",
    re.I,
)
PERCENT_OFF_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*off", re.I)
DOLLAR_OFF_RE = re.compile(r"\$(\d+(?:\.\d+)?)\s*off", re.I)
CREDIT_RE = re.compile(r"\$(\d+(?:\.\d+)?)\s*(?:\w+\s+){0,2}(?:promo\s+)?credit\b", re.I)
# Both orders appear: "3% Cashback" and "Cashback: 2% Upsized".
CASHBACK_VALUE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*%\s*(?:upsized\s*)?cash\s?back"
    r"|cash\s?back[^.]{0,20}?(\d+(?:\.\d+)?)\s*%\s*upsized"
    r"|(\d+(?:\.\d+)?)\s*%\s*upsized",
    re.I,
)
POINTS_VALUE_RE = re.compile(
    rf"\b({_COUNT}x)\s*((?:\w+\s+){{0,2}}points?)\b"
    rf"|\b({_COUNT})\s*((?:bonus\s+)?(?:\w+\s+){{0,2}}points?)\b",
    re.I,
)

# A giveaway, a competition or a resale listing is not a standing discount.
EXCLUDE_RE = re.compile(
    r"\bfor\s+(?:the\s+)?(?:1st|first)\s+\d+\b|\bgiveaway\b|\bcompetition\b|\bwin\s+a\b"
    r"|\bfree\s+entry\b|\braffle\b|\bselling\b|\bswap\b",
    re.I,
)
GIFT_CARD_RE = re.compile(r"\bgift\s?cards?\b|\be-?gift\b|\bgc\b|\bvoucher\b", re.I)
END_RE = re.compile(r"\b(?:ends?|until|expires?)\s+(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", re.I)

CONDITION_RULES = (
    (re.compile(r"\bEDR\b|\bEveryday\s+Rewards\b", re.I), "需 Everyday Rewards 会员"),
    (re.compile(r"\bflybuys\b", re.I), "需 Flybuys 会员"),
    (re.compile(r"\bin[-\s]?store\s+only\b", re.I), "仅限门店"),
    (re.compile(r"\bonline\s+only\b", re.I), "仅限线上"),
    (re.compile(r"\bactivation\s+required\b", re.I), "需先激活"),
    (re.compile(r"\bapp\s+only\b", re.I), "仅限 App"),
    (re.compile(r"\bmembers?\s+only\b|\bmembership\s+required\b", re.I), "仅会员"),
    (re.compile(r"\bnew\s+customers?\b", re.I), "仅新客"),
    (re.compile(r"\bselected\b|\bspecific\b", re.I), "仅限指定商品"),
)
STATE_RE = re.compile(r"^\[(NSW|VIC|QLD|WA|SA|TAS|ACT|NT)[^\]]*\]\s*", re.I)


def classify(title: str) -> str | None:
    if POINTS_RE.search(title):
        return "积分加倍"
    if CASHBACK_RE.search(title):
        return "返现加码"
    has_discount = (
        PERCENT_OFF_RE.search(title) or DOLLAR_OFF_RE.search(title) or CREDIT_RE.search(title)
    )
    if not has_discount:
        return None
    # A sitewide sale is a different lever from a discounted gift card, so it only counts as
    # 全场折扣 when the title says the whole shop is included.
    if SITEWIDE_RE.search(title):
        return "全场折扣"
    if GIFT_CARD_RE.search(title):
        return "礼品卡折扣"
    return "品类折扣"


def value_of(title: str, kind: str) -> str:
    """The discount as the title states it, so `value` and `evidence` can't disagree."""
    if kind == "积分加倍":
        m = POINTS_VALUE_RE.search(title)
        if m:
            count, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            return collapse(f"{count} {unit}")
        m = POINTS_RE.search(title)
        return collapse(m.group(0)) if m else "积分加倍"
    if kind == "返现加码":
        m = CASHBACK_VALUE_RE.search(title)
        if m:
            pct = next(g for g in m.groups() if g)
            return f"{pct}% cashback"
        m = CASHBACK_RE.search(title)
        return collapse(m.group(0)) if m else "返现加码"
    m = PERCENT_OFF_RE.search(title)
    if m:
        return f"{m.group(1)}% off"
    m = DOLLAR_OFF_RE.search(title)
    if m:
        return f"${m.group(1)} off"
    m = CREDIT_RE.search(title)
    return f"${m.group(1)} credit" if m else "折扣"


def conditions_of(title: str) -> str:
    found = [label for pattern, label in CONDITION_RULES if pattern.search(title)]
    state = STATE_RE.match(title)
    if state:
        found.insert(0, f"仅 {state.group(1).upper()}")
    # dict.fromkeys keeps CONDITION_RULES order while dropping repeats
    return "；".join(dict.fromkeys(found))


def end_of(title: str, posted: date) -> str | None:
    m = END_RE.search(title)
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
    if year:
        y = int(year)
        y += 2000 if y < 100 else 0
    else:
        # No year printed: the nearest one that puts the end on or after the posting day.
        y = posted.year if (month, day) >= (posted.month, posted.day) else posted.year + 1
    try:
        return date(y, month, day).isoformat()
    except ValueError:
        return None


def scope_of(title_body: str) -> str:
    return collapse(STATE_RE.sub("", title_body)).strip(" -–,:")


# Titles that have broken the regexes above, kept so a change that breaks them again fails
# loudly: run with --self-check.
SELF_CHECK = (
    (
        "Earn 20x Flybuys Points on Apple Gift Cards (In-Store Only) @ Coles",
        "积分加倍",
        "20x Flybuys Points",
        "需 Flybuys 会员；仅限门店",
    ),
    (
        "Activate & Spend $X (Min. $50) in 1 Transaction for 4 Consecutive Weeks at Coles, "
        "Get 10,000 Flybuys Points or $50 off @ Flybuys",
        "积分加倍",
        "10,000 Flybuys Points",
        "需 Flybuys 会员",
    ),
    (
        "Amazon Gift Card Cashback: 2% Upsized, [Bank] 2% Bonus, $5 Bonus Amazon GC on $250 "
        "GC Spend (Activation Required) @ ShopBack",
        "返现加码",
        "2% cashback",
        "需先激活",
    ),
    ("SuperSwap Gift Card: 3% Cashback @ ShopBack", "返现加码", "3% cashback", ""),
    ("10% off $30 and $50 Ultimate Birthday Gift Cards @ Officeworks", "礼品卡折扣", "10% off", ""),
    (
        "10% off Nintendo eShop Gift Cards (EDR Required, in-Store Only) @ Woolworths",
        "礼品卡折扣",
        "10% off",
        "需 Everyday Rewards 会员；仅限门店",
    ),
    (
        "$20 Amazon Promo Credit on $200 Apple eGift Card Spend @ Amazon AU",
        "礼品卡折扣",
        "$20 credit",
        "",
    ),
    ("30% off Sitewide @ Cotton On", "全场折扣", "30% off", ""),
    ("20% off Storewide (Excludes Sale Items) @ Myer", "全场折扣", "20% off", ""),
    # A discount that names neither the whole shop nor a gift card is a category deal.
    ("25% off All Nike Footwear @ Rebel", "品类折扣", "25% off", ""),
    # A giveaway is not a standing discount, so it must not classify at all.
    ("[NSW] $100 Gift Cards for 1st 50 Customers fr. 9am Sat. @ Sports Direct", None, "", ""),
)


def self_check() -> int:
    for title, kind, value, conditions in SELF_CHECK:
        if kind is None:
            assert EXCLUDE_RE.search(title), f"should be excluded: {title}"
            continue
        assert not EXCLUDE_RE.search(title), f"wrongly excluded: {title}"
        got = classify(title)
        assert got == kind, f"{title}\n  kind {got!r} != {kind!r}"
        got = value_of(title, kind)
        assert got == value, f"{title}\n  value {got!r} != {value!r}"
        got = conditions_of(title)
        assert got == conditions, f"{title}\n  conditions {got!r} != {conditions!r}"
    # end_of has no year in the title, so it must land on the next occurrence after posting.
    assert end_of("20% off, ends 3/12 @ JB Hi-Fi", date(2026, 11, 20)) == "2026-12-03"
    assert end_of("20% off, ends 3/1 @ JB Hi-Fi", date(2026, 12, 28)) == "2027-01-03"
    assert end_of("20% off @ JB Hi-Fi", date(2026, 11, 20)) is None
    print(f"self-check: {len(SELF_CHECK)} titles ok", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pages", type=int, default=15, help="listing pages per tag")
    ap.add_argument(
        "--tags",
        default=",".join(TAGS),
        help=f"comma-separated OzBargain tags (default: {','.join(TAGS)})",
    )
    ap.add_argument("--delay", type=float, default=MIN_DELAY, help=f"seconds, >= {MIN_DELAY}")
    ap.add_argument("--out", type=Path, default=DATA / "promos" / "ozbargain.json")
    ap.add_argument("--self-check", action="store_true", help="assert the pinned titles, exit")
    args = ap.parse_args()
    if args.self_check:
        return self_check()
    if args.delay < MIN_DELAY:
        ap.error(f"--delay must be >= {MIN_DELAY} (PRD 5.2)")

    retrieved_at = datetime.now(SYDNEY).date().isoformat()
    rows: dict[str, dict] = {}
    dropped_kind = dropped_excluded = dropped_nodate = 0
    requests = 0

    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30
    ) as client:
        for tag in [t.strip() for t in args.tags.split(",") if t.strip()]:
            for page in range(args.pages):
                if requests:
                    time.sleep(args.delay)
                requests += 1
                try:
                    resp = client.get(TAG_URL.format(tag=tag), params={"page": page})
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        print(f"{tag}: no such tag (404), skipping", file=sys.stderr)
                    else:
                        code = exc.response.status_code
                        print(f"{tag} page={page}: HTTP {code}, stopping this tag", file=sys.stderr)
                    break
                except httpx.HTTPError as exc:
                    print(f"{tag} page={page} failed ({exc!r}); stopping this tag", file=sys.stderr)
                    break
                cards = parse_cards(resp.text)
                if not cards:
                    print(f"{tag} page={page}: no cards, stopping this tag", file=sys.stderr)
                    break
                for card in cards:
                    title = card["title"]
                    if card["node_id"] in rows:
                        continue
                    if EXCLUDE_RE.search(title):
                        dropped_excluded += 1
                        continue
                    kind = classify(title)
                    if kind is None:
                        dropped_kind += 1
                        continue
                    if not card["posted"]:
                        dropped_nodate += 1
                        continue
                    d, m, y = (int(x) for x in card["posted"])
                    posted = date(y, m, d)
                    body, merchant = split_title(title)
                    up, down = card["up"], card["down"]
                    rows[card["node_id"]] = {
                        "id": f"ozbp-{card['node_id']}",
                        "year": posted.year,
                        "retailer": merchant or (card["domain"] or "未注明"),
                        "kind": kind,
                        "value": value_of(title, kind),
                        "start": posted.isoformat(),
                        "end": end_of(title, posted),
                        "scope": scope_of(body)[:200],
                        "conditions": conditions_of(title),
                        "votes": up - down if up is not None and down is not None else None,
                        "source": NODE_URL.format(node_id=card["node_id"]),
                        "evidence": title[:200],
                        "retrieved_at": retrieved_at,
                        "note": f"OzBargain /tag/{tag} 列表页标题；start 为发帖日",
                    }
                print(
                    f"{tag} page={page}: {len(cards)} cards, {len(rows)} kept so far",
                    file=sys.stderr,
                )

    out_rows = sorted(rows.values(), key=lambda r: (r["start"], r["id"]), reverse=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    by_kind: dict[str, int] = {}
    for row in out_rows:
        by_kind[row["kind"]] = by_kind.get(row["kind"], 0) + 1
    print(f"wrote {args.out}: {len(out_rows)} promos from {requests} requests", file=sys.stderr)
    print(f"  by kind: {by_kind}", file=sys.stderr)
    print(
        f"  dropped: {dropped_kind} no discount stated, {dropped_excluded} giveaway/competition, "
        f"{dropped_nodate} no posting date",
        file=sys.stderr,
    )
    if out_rows:
        print(f"  date span: {out_rows[-1]['start']} .. {out_rows[0]['start']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
