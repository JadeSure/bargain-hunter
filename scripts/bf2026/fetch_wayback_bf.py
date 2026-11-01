#!/usr/bin/env python3
"""Harvest OzBargain Black Friday 2021-2023 deals from Wayback Machine snapshots into
data/bf2026 `points` rows (the live /event/black-friday listing only reaches back to 2024-11).

The snapshots are single pages holding hundreds of cards, not 20-card paginated listings. Card
parsing, field mapping and the `event` window are fetch_ozbargain.py's; this script adds the
Wayback fetch, injection/URL-rewrite stripping and the 2022 `/pages/black-friday` card markup.
`source` is the live /node/<id> URL; the snapshot URL goes in `note`. Rows get a `wb-` id; node
ids already in a sibling points/*.json are skipped.

The 2022 page's cards carry no posted date, so for each priced 2022 card the live /node/<id> page
is read once for its posted date (cached in DIR/node-dates.json, so --from-html stays offline).
Cards without a date are skipped, never dated by guesswork.

    python3 scripts/bf2026/fetch_wayback_bf.py --save-html DIR   # reuses pages already in DIR
    python3 scripts/bf2026/fetch_wayback_bf.py --from-html DIR   # re-parse saved HTML, no network
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import fetch_ozbargain as ozb
import httpx
from bs4 import BeautifulSoup

SNAPSHOT_URL = "https://web.archive.org/web/{ts}/https://www.ozbargain.com.au{path}"
NODE_URL = "https://www.ozbargain.com.au/node/{node_id}"
# (timestamp, path): CDX-verified 2026-11-01. 2022 has no in-season /event/ capture.
SNAPSHOTS = (
    ("20211124173124", "/event/black-friday"),
    ("20221124134806", "/pages/black-friday"),
    ("20221125130910", "/pages/black-friday"),
    ("20231125180519", "/event/black-friday"),
    ("20231128032255", "/event/black-friday"),
    ("20231204230414", "/event/black-friday"),
)
TIMEOUT = 60  # Wayback is slow and these pages are 0.4-2.4 MB
ATTEMPTS = 3  # for timeouts / connection errors only; 403/429 never retry
NODE_BLOCK_LIMIT = 3  # consecutive 403s on node pages before we treat it as rate limiting

# Wayback's injected scripts/styles/trailing comment, and the /web/<ts><flag>/ prefix it puts on
# every URL (absolute or root-relative) -- removed so /node/<id> hrefs come out as on the live site.
INJECTED_RE = re.compile(
    r"<script\b(?:(?!</script>).)*?(?:web-static\.archive\.org|__wm\.|RufflePlayer)"
    r"(?:(?!</script>).)*</script>"
    r"|<link\b[^>]*web-static\.archive\.org[^>]*>"
    r"|<!--\s*FILE ARCHIVED.*",
    re.S,
)
REWRITE_RE = re.compile(
    r"(?:https?:)?(?://web\.archive\.org)?/web/\d{14}[a-z]{0,3}_?/(?=https?:|//)"
)
OZB_HOST_RE = re.compile(r"(?:https?:)?//(?:www\.)?ozbargain\.com\.au(?=/)")


def strip_wayback(html: str) -> str:
    return OZB_HOST_RE.sub("", REWRITE_RE.sub("", INJECTED_RE.sub("", html)))


def parse_page_cards(html: str) -> list[dict]:
    """`/pages/black-friday` cards: `ul.ng2 > li#node<id>[title]` with store, votes, no date."""
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for li in soup.select("ul.ng2 > li"):
        node_id = (li.get("id") or "").removeprefix("node")
        link = li.select_one(f'.ng2-dealinfo a[href="/node/{node_id}"]')
        if not (node_id.isdigit() and link):
            continue
        store = li.select_one(".ng2-dealstore")
        cards.append(
            {
                "node_id": node_id,
                "title": ozb.collapse(li.get("title") or link.get_text()),
                "posted": None,
                "up": ozb._vote_count(li, ".n-vote .voteup span"),
                "down": ozb._vote_count(li, ".n-vote .votedown span"),
                "domain": ozb.collapse(store.get_text()) if store else None,
            }
        )
    return cards


def parse_cards(html: str, path: str) -> list[dict]:
    html = strip_wayback(html)
    return parse_page_cards(html) if path.startswith("/pages/") else ozb.parse_cards(html)


def parse_node_posted(html: str) -> tuple[str, str, str] | None:
    """(DD, MM, YYYY) of the deal on a live /node/<id> page: the first date in its card."""
    card = BeautifulSoup(html, "html.parser").select_one("div.node-ozbdeal .submitted")
    posted = ozb.POSTED_RE.search(card.get_text(" ")) if card else None
    return posted.groups() if posted else None


def is_priced(card: dict) -> bool:
    return ozb.parse_price(ozb.split_title(card["title"])[0]) is not None


def fetch(client: httpx.Client, url: str) -> tuple[str | None, str]:
    """Return (html, "") or (None, problem). A 403/429 problem starts with 'BLOCKED'."""
    problem = ""
    for attempt in range(ATTEMPTS):
        if attempt:
            time.sleep(ozb.MIN_DELAY)
        try:
            resp = client.get(url)
        except httpx.HTTPError as exc:
            problem = f"request failed ({exc!r})"
            continue
        if resp.status_code in (403, 429):
            return None, f"BLOCKED: HTTP {resp.status_code}"
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}"
        return resp.text, ""
    return None, f"{problem} after {ATTEMPTS} attempts"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--delay", type=float, default=ozb.MIN_DELAY, help=f"seconds, >= {ozb.MIN_DELAY}"
    )
    ap.add_argument("--out", type=Path, default=ozb.DATA / "points" / "wayback-bf.json")
    ap.add_argument("--save-html", type=Path, default=None, help="default: a new temp dir")
    ap.add_argument("--from-html", type=Path, default=None, help="re-parse saved pages offline")
    args = ap.parse_args()
    if args.delay < ozb.MIN_DELAY:
        ap.error(f"--delay must be >= {ozb.MIN_DELAY} (PRD 5.2)")

    known, watch_keys = ozb.load_known_categories()
    offline = args.from_html is not None
    html_dir = args.from_html or args.save_html or Path(tempfile.mkdtemp(prefix="wayback-bf-"))
    html_dir.mkdir(parents=True, exist_ok=True)
    files = [html_dir / f"{ts}.html" for ts, _ in SNAPSHOTS]
    dates_file = html_dir / "node-dates.json"
    node_dates: dict[str, list[str]] = (
        json.loads(dates_file.read_text(encoding="utf-8")) if dates_file.exists() else {}
    )
    if offline:
        mtimes = [f.stat().st_mtime for f in files if f.exists()]
        fetched = datetime.fromtimestamp(min(mtimes), ozb.SYDNEY) if mtimes else None
    else:
        fetched = datetime.now(ozb.SYDNEY)
    retrieved_at = (fetched or datetime.now(ozb.SYDNEY)).date().isoformat()

    # check.py wants ids unique across every points/*.json; skip node ids already held there.
    other_ids = {
        row["id"]
        for path in args.out.parent.glob("*.json")
        if path.resolve() != args.out.resolve()
        for row in json.loads(path.read_text(encoding="utf-8"))
    }
    skips: Counter[str] = Counter()
    per_snapshot: dict[str, str] = {}
    problems: list[str] = []
    cards_by_node: dict[str, tuple[dict, str]] = {}  # first-seen snapshot wins
    last_request = 0.0

    def get(client: httpx.Client, url: str) -> tuple[str | None, str]:
        nonlocal last_request
        time.sleep(max(0.0, args.delay - (time.monotonic() - last_request)))
        try:
            return fetch(client, url)
        finally:
            last_request = time.monotonic()

    with httpx.Client(
        headers={"User-Agent": ozb.USER_AGENT}, follow_redirects=True, timeout=TIMEOUT
    ) as client:
        blocked = False
        for (ts, path), file in zip(SNAPSHOTS, files, strict=True):
            url = SNAPSHOT_URL.format(ts=ts, path=path)
            if file.exists():  # saved pages are reused: they are expensive to re-fetch
                html = file.read_text(encoding="utf-8")
            elif offline:
                problems.append(f"{ts}: no saved HTML")
                continue
            else:
                html, problem = get(client, url)
                if html is None:
                    problems.append(f"{ts}: {problem}")
                    if problem.startswith("BLOCKED"):
                        blocked = True
                        break
                    continue
                file.write_text(html, encoding="utf-8")
            cards = parse_cards(html, path)
            per_snapshot[ts] = f"{ts} {path}: {len(html):,} B, {len(cards)} cards"
            if not cards:
                problems.append(f"{ts}: parsed zero cards (layout change or block page?)")
            for card in cards:
                node_id = card["node_id"]
                if f"ozb-{node_id}" in other_ids or f"wb-{node_id}" in other_ids:
                    skips["in_other_points_file"] += 1
                elif node_id in cards_by_node:
                    skips["duplicate_node"] += 1
                else:
                    cards_by_node[node_id] = (card, SNAPSHOT_URL.format(ts=ts, path=path))

        # Cards with no date (2022 page): read the posted date off the live node page, priced only.
        undated = [
            node_id
            for node_id, (card, _) in cards_by_node.items()
            if card["posted"] is None and is_priced(card)
        ]
        todo = [node_id for node_id in undated if node_id not in node_dates]
        print(
            f"undated priced cards: {len(undated)}; node pages to read: {len(todo)}",
            file=sys.stderr,
        )
        # A 403 on one node means that deal was removed or restricted — skip it. Only a run
        # of them back to back means the site is rate-limiting us, and that is when we stop.
        consecutive_blocks = 0
        for i, node_id in enumerate(todo):
            if offline or blocked:
                break
            html, problem = get(client, NODE_URL.format(node_id=node_id))
            if html is None:
                skips[f"node_page_{problem.split(':')[0].replace(' ', '_')}"] += 1
                if problem.startswith("BLOCKED"):
                    consecutive_blocks += 1
                    problems.append(f"node {node_id}: {problem}")
                    if consecutive_blocks >= NODE_BLOCK_LIMIT:
                        blocked = True
                        break
                continue
            consecutive_blocks = 0
            posted = parse_node_posted(html)
            if posted:
                node_dates[node_id] = list(posted)
                dates_file.write_text(json.dumps(node_dates, indent=1) + "\n", encoding="utf-8")
            else:
                skips["node_page_no_date"] += 1
            if (i + 1) % 25 == 0:
                print(f"  node pages read: {i + 1}/{len(todo)}", file=sys.stderr)

    rows: dict[str, dict] = {}
    for node_id, (card, snapshot_url) in cards_by_node.items():
        note = f"Wayback snapshot {snapshot_url}"
        if card["posted"] is None and node_id in node_dates:
            card["posted"] = tuple(node_dates[node_id])
            note += "; posted date read from the live node page"
        row, reason = ozb.build_row(card, retrieved_at, known)
        if row is None:
            skips[reason] += 1
            continue
        row.update(id=f"wb-{node_id}", note=note)
        rows[row["id"]] = row

    event_label, window_start, window_end = ozb.EVENT_SEASONS["black-friday"]
    out_rows = sorted(rows.values(), key=lambda r: (r["date"], r["id"]))
    print(f"HTML: {html_dir}")
    print("per snapshot:")
    kept_by_snapshot = Counter(r["note"].split()[2].rstrip(";") for r in out_rows)
    for ts, path in SNAPSHOTS:
        if ts in per_snapshot:
            kept = kept_by_snapshot[SNAPSHOT_URL.format(ts=ts, path=path)]
            print(f"  {per_snapshot[ts]}, {kept} rows kept")
    print(f"rows kept: {len(out_rows)}")
    print(f"rows skipped: {sum(skips.values())} {dict(skips)}")
    if out_rows:
        seasons = Counter(
            ozb.season_year(date.fromisoformat(r["date"]), window_start, window_end)
            for r in out_rows
            if r["event"] == event_label
        )
        print(f"{event_label} rows per season year:", dict(sorted(seasons.items())))
        print(
            "rows per posted year:", dict(sorted(Counter(r["date"][:4] for r in out_rows).items()))
        )
        print("rows per event:", dict(Counter(r["event"] for r in out_rows)))
        print("rows per category:", dict(Counter(r["category"] for r in out_rows).most_common()))
        n = len(out_rows)
        print(f"with was_price: {sum(r['was_price'] is not None for r in out_rows)}/{n}")
        print(f"with votes: {sum(r['votes'] is not None for r in out_rows)}/{n}")
        print(f"with conditions: {sum(bool(r['conditions']) for r in out_rows)}/{n}")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(out_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.out}")
    if skips["no_date"]:
        problems.append(
            f"{skips['no_date']} priced cards have no posted date (node pages not read)"
        )
    for problem in problems:
        print(f"ERROR: {problem}", file=sys.stderr)
    if not out_rows:
        print("ERROR: no rows produced; nothing written", file=sys.stderr)
    return 1 if problems or not out_rows else 0


if __name__ == "__main__":
    sys.exit(main())
