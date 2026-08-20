"""Bank rates source: Australia's Consumer Data Right (CDR) banking product
reference data — a public, unauthenticated API every AU bank must publish.

No scraping, no auth, no ToS exposure. The caller decides cadence (via
StateStore.due_for_fetch); this module always fetches when called.

Endpoints (per brand `base`):
  list    {base}/cds-au/v1/banking/products
  detail  {base}/cds-au/v1/banking/products/{productId}

Version *selection* is not negotiated: every request sends a high `x-v` plus
`x-min-v: 1`, and the CDS server picks whichever version it supports and
echoes the choice back in its response `x-v` header. Parsing supported
versions out of a 406 body was tried first and abandoned — brands don't agree
on a machine-readable format (some error bodies name no version at all), so
`x-min-v` is what actually works across all of them.

Incremental fetch: an `updated-since` query param (the previous run's
timestamp) shrinks the list response, but the per-product `lastUpdated`
comparison against the snapshot is what actually decides whether a detail
call happens — `updated-since` is a perf optimisation only, not a
correctness gate.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from ..models import Deal
from .base import Source

log = logging.getLogger(__name__)

USER_AGENT = (
    "bargain-hunter/0.1 (personal deal alerter; +https://github.com/versent-shawn/bargain-hunter)"
)

_PRODUCTS_PATH = "/cds-au/v1/banking/products"
_SINCE_KEY = "_since"  # meta key in the feature snapshot dict, alongside "brand:productId" keys
_ID_SANITISE_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_NETWORK_ERRORS = (httpx.HTTPError, ValueError, KeyError, TypeError)
# ponytail: upper bound sent as x-v; raise when CDS publishes past v7. A 406
# despite x-min-v: 1 means the endpoint genuinely can't serve anything <= this,
# not that this bound is stale — the log line at the call site says which.
_MAX_VERSION = 7


def _sanitise_id(raw: str) -> str:
    return _ID_SANITISE_RE.sub("-", raw)


def _display_name(brand_name: str, product_name: str) -> str:
    """Brand-prefixed title text, without doubling the brand when the product
    name already carries it (e.g. "Macquarie Term Deposit")."""
    if product_name.lower().startswith(brand_name.lower()):
        return product_name
    return f"{brand_name} {product_name}"


def _best_deposit_rate(detail: dict) -> float | None:
    """Highest `rate` across a product's depositRates, as a fraction (0.0535 = 5.35%).
    Missing/malformed entries are skipped rather than failing the whole product."""
    rates: list[float] = []
    for entry in detail.get("depositRates") or []:
        try:
            rates.append(float(entry["rate"]))
        except (KeyError, TypeError, ValueError):
            continue
    return max(rates) if rates else None


def _bonus_points(detail: dict) -> int | None:
    """Signup-bonus points from a card's BONUS_REWARDS feature (`additionalValue`,
    a plain integer string — verified live on Westpac Altitude Velocity Black:
    additionalValue="150000"). LOYALTY_PROGRAM entries are ongoing earn rates
    (e.g. "0.5 points per $1"), not the signup bonus — do not scan those."""
    for feature in detail.get("features") or []:
        if feature.get("featureType") != "BONUS_REWARDS":
            continue
        try:
            return int(feature["additionalValue"])
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _extract_rate_signals(detail: dict) -> dict[str, float | int | None]:
    return {"best_rate": _best_deposit_rate(detail), "bonus_points": _bonus_points(detail)}


def _product_url(detail: dict, brand_base: str) -> str:
    info = detail.get("additionalInformation") or {}
    return (
        info.get("overviewUri")
        or info.get("eligibilityUri")
        or detail.get("applicationUri")
        or brand_base
    )


class BankRatesSource(Source):
    name = "bank_rates"

    def __init__(
        self,
        brands: list[dict[str, Any]],
        product_categories: list[str],
        min_rate_rise_bps: int = 10,
        min_bonus_points_rise: int = 10000,
        previous_snapshot: dict[str, Any] | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.brands = brands
        self.product_categories = set(product_categories)
        self.min_rate_rise_bps = min_rate_rise_bps
        self.min_bonus_points_rise = min_bonus_points_rise
        self.previous_snapshot = previous_snapshot or {}
        self.timeout = timeout
        # Populated by fetch(); the caller persists this via state.set_snapshot("bank_rates", ...).
        self.next_snapshot: dict[str, Any] = {}

    def fetch(self) -> list[Deal]:
        now = datetime.now(UTC)
        since = self.previous_snapshot.get(_SINCE_KEY)
        # Written unconditionally so the snapshot round-trips even if every brand fails.
        self.next_snapshot = {_SINCE_KEY: now.isoformat()}
        deals: list[Deal] = []
        for brand in self.brands:
            brand_name = brand.get("name", "?")
            try:
                deals.extend(self._fetch_brand(brand, since, now))
            except _NETWORK_ERRORS as exc:
                log.warning("bank_rates: %s failed, skipping: %s", brand_name, exc)
        return deals

    def _fetch_brand(self, brand: dict[str, Any], since: str | None, now: datetime) -> list[Deal]:
        # brand["x_v"] is no longer read: version selection is server-side (see _get_json).
        brand_name = brand["name"]
        base = brand["base"]

        params: dict[str, Any] = {"page-size": 1000}
        if since:
            params["updated-since"] = since
        list_body = self._get_json(base, _PRODUCTS_PATH, params)
        products = (list_body.get("data") or {}).get("products") or []

        deals: list[Deal] = []
        for product in products:
            if product.get("productCategory") not in self.product_categories:
                continue
            product_id = product.get("productId")
            if not product_id:
                continue
            last_updated = product.get("lastUpdated")

            key = f"{brand_name}:{product_id}"
            prev = self.previous_snapshot.get(key)
            if prev is not None and prev.get("lastUpdated") == last_updated:
                self.next_snapshot[key] = prev  # unchanged since last run, carry forward untouched
                continue

            try:
                detail_body = self._get_json(base, f"{_PRODUCTS_PATH}/{product_id}")
            except _NETWORK_ERRORS as exc:
                log.warning("bank_rates: %s detail %s failed: %s", brand_name, product_id, exc)
                continue
            detail = detail_body.get("data") or {}
            signals = _extract_rate_signals(detail)
            self.next_snapshot[key] = {"rates": signals, "lastUpdated": last_updated}

            if prev is None:
                continue  # newly listed product: seed only, not a rate rise

            deal = self._maybe_deal(
                brand_name, base, product, detail, prev.get("rates") or {}, signals, now
            )
            if deal is not None:
                deals.append(deal)
        return deals

    def _maybe_deal(
        self,
        brand_name: str,
        base: str,
        product: dict[str, Any],
        detail: dict[str, Any],
        old: dict[str, Any],
        new: dict[str, Any],
        now: datetime,
    ) -> Deal | None:
        name = _display_name(brand_name, product.get("name") or product.get("productId", "?"))

        old_rate, new_rate = old.get("best_rate"), new.get("best_rate")
        if old_rate is not None and new_rate is not None:
            bps = (new_rate - old_rate) * 10_000
            if bps >= self.min_rate_rise_bps:
                title = f"{name}: {new_rate * 100:.2f}% p.a. (was {old_rate * 100:.2f}%)"
                return self._build_deal(brand_name, base, product, detail, title, now)

        old_pts, new_pts = old.get("bonus_points"), new.get("bonus_points")
        if (
            old_pts is not None
            and new_pts is not None
            and new_pts - old_pts >= self.min_bonus_points_rise
        ):
            title = f"{name}: {new_pts:,} bonus points (was {old_pts:,})"
            return self._build_deal(brand_name, base, product, detail, title, now)
        return None

    def _build_deal(
        self,
        brand_name: str,
        base: str,
        product: dict[str, Any],
        detail: dict[str, Any],
        title: str,
        now: datetime,
    ) -> Deal:
        return Deal(
            source=self.name,
            deal_id=f"{brand_name}-{_sanitise_id(product['productId'])}",
            title=title,
            url=_product_url(detail, base),
            categories=["Finance", "Banking", "Savings"],
            currency="AUD",
            price=None,
            price_confidence=None,
            posted_at=now,
        )

    def _get_json(self, base: str, path: str, params: dict[str, Any] | None = None) -> dict:
        """GET with CDS content negotiation: send x-v=_MAX_VERSION plus x-min-v: 1
        and let the server pick a version it supports, echoed back in its response
        x-v header. A 406 here means the endpoint can't serve anything in that
        range — logged and skipped by the caller, never raised out of fetch()."""
        # String concatenation, not urljoin: a leading "/" in `path` would make urljoin
        # treat it as an absolute path and drop a base path like CommBank's "/public".
        url = base.rstrip("/") + path
        headers = {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "x-v": str(_MAX_VERSION),
            "x-min-v": "1",
        }
        resp = httpx.get(url, params=params, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
