"""Bargain Radar source: AU retail price drops, via the JSON API behind its SPA.

Endpoint: ``POST https://bargainradar.com.au/api/items`` ->
``{"count": <total matches>, "items": [...]}``. There is no feed: this is the
undocumented API the site's own Angular app calls, so it can change or vanish
without notice. The request-body keys in ``_body`` were read from that app's JS
bundle (2026-10-09). The server caps a page at ~120 items.

Payload traps:
  - ``updatedAt`` is a *naive* ISO string in Australia/Sydney local time.
  - ``newPrice``/``oldPrice`` are whole dollars, so the discount is taken from
    ``discount`` (a 0-1 fraction computed server-side from unrounded prices)
    rather than recomputed from the rounded ones.

The store / discount / updateType filters are sent in the body and then
re-applied client-side in ``_to_deal``: an undocumented API's parameters are
not guaranteed to be honoured (appsumo.py documents one that silently ignores
every parameter but ``page``).
"""

import logging
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx

from ..models import Deal
from .base import Source

log = logging.getLogger(__name__)

API_URL = "https://bargainradar.com.au/api/items"
ITEM_PAGE_URL = "https://bargainradar.com.au/item/{id}"
USER_AGENT = (
    "bargain-hunter/0.1 (personal deal alerter; +https://github.com/versent-shawn/bargain-hunter)"
)
# DISCOUNT_DOWN and DELETED are not deal events.
UPDATE_TYPES = ("NEW", "DISCOUNT_UP", "RETURNED")

_AET = ZoneInfo("Australia/Sydney")
# Display overrides; every other store name is just str.title() ("big w" -> "Big W").
_STORE_NAMES = {"jb hi-fi": "JB Hi-Fi"}


def _parse_sydney(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_AET)
    return dt.astimezone(UTC)


def _to_float(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


class BargainRadarSource(Source):
    name = "bargainradar"

    def __init__(
        self,
        stores: list[str],
        min_discount_percent: float = 20.0,
        lookback_minutes: int = 120,
        max_pages: int = 3,
        page_size: int = 100,
        request_delay_seconds: float = 2.0,
        timeout: float = 20.0,
    ) -> None:
        if not stores:
            # An empty `stores` body key means *all* stores server-side: pages
            # full of Amazon that the client-side store filter would then
            # silently drop to zero deals.
            raise ValueError("BargainRadarSource needs at least one store")
        self.stores = stores
        self.min_discount_percent = min_discount_percent
        self.lookback_minutes = lookback_minutes
        self.max_pages = max_pages
        self.page_size = page_size
        self.request_delay_seconds = request_delay_seconds
        self.timeout = timeout

    def _body(self, page: int) -> dict:
        return {
            "pageNumber": page,
            "itemsPerPage": self.page_size,
            "stores": list(self.stores),
            "discountRange": [self.min_discount_percent, 100],
            "dateRange": int(self.lookback_minutes * 60),  # seconds
            "includedUpdateTypes": list(UPDATE_TYPES),
            "sortBy": "date",
            "sortOrder": "desc",
            "discountChangeRate": 0,
        }

    def fetch(self) -> list[Deal]:
        # Errors propagate on purpose: main.py's per-source handler logs them to
        # summary["source_errors"], and the lookback window overlaps several
        # polls, so the next due run re-covers whatever this one missed.
        deals: dict[str, Deal] = {}  # de-dupe across pages by Deal.key
        total = 0
        for page in range(1, self.max_pages + 1):
            if page > 1:
                time.sleep(self.request_delay_seconds)
            resp = httpx.post(
                API_URL,
                json=self._body(page),
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=self.timeout,
                follow_redirects=True,
            )
            resp.raise_for_status()
            data = resp.json()
            for deal in self._parse(data):
                deals.setdefault(deal.key, deal)
            total = data["count"]
            if len(data.get("items") or []) < self.page_size or page * self.page_size >= total:
                return list(deals.values())
        log.warning(
            "bargainradar: truncated at %d pages (%d of %d items)",
            self.max_pages,
            self.max_pages * self.page_size,
            total,
        )
        return list(deals.values())

    def _parse(self, data: dict) -> list[Deal]:
        out: list[Deal] = []
        for item in data.get("items") or []:
            deal = self._to_deal(item)
            if deal is not None:
                out.append(deal)
        return out

    def _to_deal(self, item: dict) -> Deal | None:
        item_id = item.get("id")
        name = (item.get("name") or "").strip()
        merchant_url = item.get("url")
        store = item.get("store")
        if not item_id or not name or not merchant_url:
            return None
        if store not in self.stores or item.get("updateType") not in UPDATE_TYPES:
            return None

        discount = _to_float(item.get("discount"))
        price = _to_float(item.get("newPrice"))
        if discount is None or price is None or price <= 0:
            return None
        discount_percent = round(discount * 100, 1)
        if discount_percent < self.min_discount_percent:
            return None

        old_price = _to_float(item.get("oldPrice"))
        store_name = _STORE_NAMES.get(store, store.title())
        return Deal(
            source=self.name,
            deal_id=item_id,
            # The email template renders only the title, so the store goes in it.
            title=f"{name} ({store_name})",
            url=ITEM_PAGE_URL.format(id=item_id),
            merchant_url=merchant_url,
            image=item.get("imageUrl") or None,
            posted_at=_parse_sydney(item.get("updatedAt")),
            price=price,
            was_price=old_price if old_price is not None and old_price > price else None,
            discount_percent=discount_percent,
            price_confidence="high",
            currency="AUD",
            expired=bool(item.get("isReportedForSaleExpiry")),
        )
