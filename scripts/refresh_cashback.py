"""Refresh candidate cashback rates from ShopBack's public store list.

Semi-automatic: this fetches ShopBack's all-stores page, extracts a best-effort
merchant→rate map, and prints a YAML ``rates:`` block to paste into
``config/settings.yaml`` after review. It never writes settings itself — the
map in settings is the source of truth, kept robust to markup/ToS changes.

Usage:
  python scripts/refresh_cashback.py                 # print merchant → rate lines
  python scripts/refresh_cashback.py --known-only    # only merchants already in settings.yaml

Notes:
  * ShopBack renders rates client-side, so extraction is heuristic and will not
    map every store to a domain. Treat the output as a starting point: verify
    rates and fill in merchant domains that couldn't be resolved automatically.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from bargain_hunter.config import load_settings  # noqa: E402

STORES_URL = "https://www.shopback.com.au/all-stores"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Matches "<Name>Up to 5% Cashback" / "<Name>7% Cashback" fragments in the
# rendered store list. Group 1 = store name run, group 2 = headline percent.
_RATE_RE = re.compile(r"([A-Za-z0-9 .&'!-]{2,40}?)(?:Up to )?(\d+(?:\.\d+)?)% Cashback")


def extract_rates(text: str) -> dict[str, float]:
    """Return a best-effort {store_name: headline_percent} map from page text."""
    rates: dict[str, float] = {}
    for match in _RATE_RE.finditer(text):
        raw_name, pct = match.group(1), match.group(2)
        # The rendered text often doubles the store name (e.g. "AmazonAmazon");
        # collapse an exact doubling and take the trailing, cleaner run.
        name = raw_name.strip()
        half = len(name) // 2
        if half and name[:half] == name[half:]:
            name = name[half:]
        name = name.strip()
        if not name:
            continue
        try:
            value = float(pct)
        except ValueError:
            continue
        # Keep the highest headline rate seen for a store name.
        if name not in rates or value > rates[name]:
            rates[name] = value
    return rates


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--known-only",
        action="store_true",
        help="only print stores whose name loosely matches a domain already in settings.yaml",
    )
    args = ap.parse_args()

    resp = httpx.get(
        STORES_URL, headers={"User-Agent": USER_AGENT}, timeout=20.0, follow_redirects=True
    )
    resp.raise_for_status()
    rates = extract_rates(resp.text)
    if not rates:
        print(
            "No rates extracted — ShopBack markup likely changed; inspect the page manually.",
            file=sys.stderr,
        )
        return 1

    known_domains = list(load_settings().cashback.rates)

    print("# Candidate cashback rates from ShopBack (review before pasting into settings.yaml):")
    for name in sorted(rates):
        pct = rates[name]
        slug = re.sub(r"[^a-z0-9]", "", name.lower())
        matched = next(
            (d for d in known_domains if slug and slug in re.sub(r"[^a-z0-9]", "", d)), None
        )
        if args.known_only and not matched:
            continue
        domain_hint = matched or "<domain?>"
        print(f"  {domain_hint}: {pct}   # {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
