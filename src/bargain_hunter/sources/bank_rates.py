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
correctness gate. The value must be `yyyy-MM-ddTHH:mm:ssZ` — verified live,
9 of 10 configured brands 400 on Python's default `datetime.isoformat()`
(only UBank tolerates it), whether fractional seconds are present or not and
regardless of `+00:00` vs no offset. Only the strict `Z`-suffixed, no-fractional
form is accepted by all ten. Without it, run 2 onward would 400 on every list
call for those 9 brands — swallowed as an ordinary per-brand skip (`fetch()`),
so bank_rates would silently collapse to UBank's ~3 products and stay there,
indistinguishable from routine network noise in the logs.

Detail-fetch budget: on an empty/lost snapshot every product looks changed,
which without a cap means several hundred serial detail calls in one run —
confirmed in production (a cold run over several minutes on a `*/5` cron
causes queueing). `max_detail_fetches_per_run` bounds that.

Deferral (cap or fetch failure): whenever a product's or a whole brand's fresh
data can't be obtained this run — over budget, or a network/HTTP error on
either the list or the detail call — its *previous* snapshot entry is carried
forward unchanged rather than dropped. Losing an entry instead would make the
next successful run see the product as brand new (`prev is None`), which is
seed-only and never emits a deal — so a transient blip could silently erase a
real rate change that happened during it. The `_since` cursor is also held
back (not advanced) whenever anything was deferred, so a deferred product's
older `lastUpdated` can't fall outside the next run's `updated-since` window
and get silently dropped forever. See `fetch()`, `_carry_forward_brand()`,
`_defer_product()`.
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


def _cdr_timestamp(dt: datetime) -> str:
    """CDS `DateTimeString` format: `yyyy-MM-ddTHH:mm:ssZ`, and only this exact
    shape. Verified live: 9 of the 10 configured brands 400 on
    `datetime.isoformat()` (fractional seconds and/or `+00:00` instead of `Z`;
    only UBank is lenient), and that 400 is swallowed by the per-brand
    `except _NETWORK_ERRORS` in `fetch()` as an ordinary skip — no crash, no
    alert, just that brand silently missing every run after the first. Do not
    "simplify" this back to `.isoformat()`."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    """Highest signup-bonus points across a card's BONUS_REWARDS features
    (`additionalValue`, a plain integer string — verified live on Westpac
    Altitude Velocity Black: additionalValue="150000"). Cards can carry
    multiple concurrent BONUS_REWARDS entries (verified live on a real
    CommBank card: 170000 and 200000 both present) and CDR doesn't guarantee
    array order, so — like _best_deposit_rate above — take the max, not the
    first; otherwise the offer is under-reported and can manufacture phantom
    rises/falls if the API's array order shifts between polls with nothing
    material changed. LOYALTY_PROGRAM entries are ongoing earn rates (e.g.
    "0.5 points per $1"), not the signup bonus — do not scan those."""
    points: list[int] = []
    for feature in detail.get("features") or []:
        if feature.get("featureType") != "BONUS_REWARDS":
            continue
        try:
            points.append(int(feature["additionalValue"]))
        except (KeyError, TypeError, ValueError):
            continue
    return max(points) if points else None


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
        # Sensible default derived from a real cold-start production run: ~3s/detail
        # call observed end-to-end (network + occasional retries), so 40 keeps one
        # run's added time to ~2 min, well inside the */5 cron window. Config wiring
        # (config/settings.yaml `bank_rates.max_detail_fetches_per_run`, read via
        # getattr in main.py) is not part of this change; this default applies until
        # that lands.
        max_detail_fetches_per_run: int = 40,
    ) -> None:
        self.brands = brands
        self.product_categories = set(product_categories)
        self.min_rate_rise_bps = min_rate_rise_bps
        self.min_bonus_points_rise = min_bonus_points_rise
        self.previous_snapshot = previous_snapshot or {}
        self.timeout = timeout
        self.max_detail_fetches_per_run = max_detail_fetches_per_run
        # Populated by fetch(); the caller persists this via state.set_snapshot("bank_rates", ...).
        self.next_snapshot: dict[str, Any] = {}
        self._detail_budget = 0
        self._deferred_brands: list[str] = []

    def fetch(self) -> list[Deal]:
        now = datetime.now(UTC)
        since = self.previous_snapshot.get(_SINCE_KEY)
        self.next_snapshot = {}
        self._detail_budget = self.max_detail_fetches_per_run
        self._deferred_brands = []
        deals: list[Deal] = []
        for brand in self.brands:
            brand_name = brand.get("name", "?")
            try:
                deals.extend(self._fetch_brand(brand, since, now))
            except _NETWORK_ERRORS as exc:
                log.warning("bank_rates: %s failed, skipping: %s", brand_name, exc)
                self._carry_forward_brand(brand_name)

        if self._deferred_brands:
            # Hold the `since` cursor back rather than advancing it: a deferred
            # product's `lastUpdated` predates `now`, so an advanced cursor could
            # make the *next* run's list call filter it out before we ever detail-
            # fetch it — silently dropping it instead of retrying it.
            if since:
                self.next_snapshot[_SINCE_KEY] = since
            log.warning(
                "bank_rates: deferring product(s) in %s to a later run "
                "(detail-fetch cap or fetch failure)",
                ", ".join(self._deferred_brands),
            )
        else:
            self.next_snapshot[_SINCE_KEY] = _cdr_timestamp(now)
        return deals

    def _carry_forward_brand(self, brand_name: str) -> None:
        """The brand's list call itself failed -- no fresh product data at all
        this run. Keep its previous baseline intact rather than losing every
        product's snapshot entry, so a transient blip can't make the next
        successful run treat every product as brand new (and silently miss a
        rate change that happened during the blip, since a "new" product is
        seed-only, never a diff)."""
        prefix = f"{brand_name}:"
        for key, value in self.previous_snapshot.items():
            if key.startswith(prefix):
                self.next_snapshot.setdefault(key, value)
        if brand_name not in self._deferred_brands:
            self._deferred_brands.append(brand_name)

    def _defer_product(self, brand_name: str, key: str, prev: dict[str, Any] | None) -> None:
        """Couldn't get fresh detail data for `key` this run (cap or a fetch
        failure). Carry its old baseline forward (if any) instead of dropping
        it, so a later run's before/after comparison is against the real
        previous value, not nothing -- same reasoning as _carry_forward_brand,
        just at product granularity."""
        if prev is not None:
            self.next_snapshot[key] = prev
        if brand_name not in self._deferred_brands:
            self._deferred_brands.append(brand_name)

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

            if self._detail_budget <= 0:
                # Over budget this run -- carry the old baseline (if any) forward
                # and retry the detail call on a later run instead of losing it.
                self._defer_product(brand_name, key, prev)
                continue
            self._detail_budget -= 1

            try:
                detail_body = self._get_json(base, f"{_PRODUCTS_PATH}/{product_id}")
            except _NETWORK_ERRORS as exc:
                log.warning("bank_rates: %s detail %s failed: %s", brand_name, product_id, exc)
                self._defer_product(brand_name, key, prev)
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
