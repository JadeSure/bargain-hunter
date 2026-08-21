"""AppSumo source: paginates the deals API and filters client-side.

Endpoint: ``GET https://appsumo.com/api/v2/deals/?page=N`` ->
``{"deals": [...], "meta": {...}}``. ``per_page`` is fixed at 10 server-side
and not adjustable, so covering ~40 recent deals means several sequential
page requests (paced by ``request_delay_seconds``, bounded by ``max_pages``).

Verified live 2026-08-21: **every query parameter except ``page`` is
ignored** by this API -- ``?page=1`` and ``?page=1&browse_deal_status=current
&ordering=-dates__start_date&limit=50`` return identical slug lists, order,
and ``meta``. Any filter expressed as a query string is a silent no-op, so
filtering happens entirely client-side in ``_is_current``.

Three measured traps in the raw payload:
  - ``original_price`` can be the sentinel ``0.0`` on an item with a real,
    non-zero ``price`` (e.g. "Crowdflow") -- computing a discount without
    guarding ``original_price > price > 0`` produces a bogus/negative percent.
  - ``dates.start_date`` carries a *future* sentinel on some expired items
    (e.g. ``vectera-2019``: ``browse_deal_status: expired, has_ended: True,
    start_date: 2030-10-03``). It correlates with ``has_ended`` so the
    boolean filter below removes it, but the field must never be used on its
    own to judge freshness.
  - ``product_url`` is the *vendor's* own site and ``clickthrough_url`` is
    always ``None`` -- neither is the deal page. The deal page is
    ``"https://appsumo.com" + get_absolute_url``.

``description`` is composed in ``_describe`` from three optional signals:
``core_features``/``common_features`` (dicts, text under ``feature`` vs
``text`` respectively -- either list can be empty), ``deal_review``
(``average_rating`` is a *string* and can be ``None`` alongside
``review_count: 0`` on a brand-new deal), and ``refundable_days``.
"""

import contextlib
import logging
import time
from datetime import UTC, datetime

import httpx

from ..models import Deal
from .base import Source

log = logging.getLogger(__name__)

BASE_URL = "https://appsumo.com/api/v2/deals/"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _parse_ts(text: str | None) -> datetime | None:
    if not text:
        return None
    with contextlib.suppress(ValueError):
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return None


_MAX_FEATURES = 4  # card display, not a product page -- a handful, not the full list


def _feature_texts(items: object, key: str) -> list[str]:
    """Extract non-empty feature strings from a `core_features`/`common_features` list.

    Both lists hold dicts, but the text lives under a different key in each
    (`feature` vs `text`) -- measured live 2026-08-21. Either list can also be
    empty on a given deal.
    """
    texts = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        text = (item.get(key) or "").strip()
        if text:
            texts.append(text)
    return texts


def _describe(item: dict) -> str | None:
    """Compose a short "what is this / should I care" card description.

    Features answer "what is this", the rating is the quality signal, and the
    refund window is the risk signal -- in that order. Any of the three can be
    absent (empty feature lists, a brand-new deal with no reviews yet, no
    refund window), so parts are collected and joined only where present.
    """
    features = _feature_texts(item.get("core_features"), "feature") or _feature_texts(
        item.get("common_features"), "text"
    )
    parts = features[:_MAX_FEATURES]

    review = item.get("deal_review") or {}
    review_count = review.get("review_count") or 0
    rating = review.get("average_rating")
    if rating is not None and review_count:
        with contextlib.suppress(TypeError, ValueError):
            parts.append(f"{float(rating):.1f}★ ({review_count} reviews)")

    refundable_days = item.get("refundable_days")
    is_number = isinstance(refundable_days, int | float) and not isinstance(refundable_days, bool)
    if is_number and refundable_days > 0:
        parts.append(f"{int(refundable_days)}-day refund")

    return " · ".join(parts) or None


class AppSumoSource(Source):
    name = "appsumo"

    def __init__(
        self,
        max_pages: int = 4,
        request_delay_seconds: float = 2.0,
        timeout: float = 20.0,
    ) -> None:
        self.max_pages = max_pages
        self.request_delay_seconds = request_delay_seconds
        self.timeout = timeout

    def fetch(self) -> list[Deal]:
        deals: dict[str, Deal] = {}  # de-dupe across pages by Deal.key
        for page in range(1, self.max_pages + 1):
            if page > 1:
                time.sleep(self.request_delay_seconds)
            try:
                resp = httpx.get(
                    BASE_URL,
                    params={"page": page},
                    headers={"User-Agent": BROWSER_UA},
                    timeout=self.timeout,
                    follow_redirects=True,
                )
            except httpx.HTTPError as exc:
                # One bad page must not sink the run -- but a silent skip is
                # exactly the bug class this repo has shipped five times, so
                # this stays at ERROR, not a swallowed warning.
                log.error("appsumo: page %d failed -- %s", page, exc)
                continue
            if resp.status_code != 200:
                log.error("appsumo: page %d non-200 response (%s)", page, resp.status_code)
                continue
            try:
                data = resp.json()
            except ValueError as exc:
                log.error("appsumo: page %d malformed response body -- %s", page, exc)
                continue
            for deal in self._parse_page(data):
                deals.setdefault(deal.key, deal)
        return list(deals.values())

    def _parse_page(self, data: dict) -> list[Deal]:
        out: list[Deal] = []
        for item in data.get("deals") or []:
            if not self._is_current(item):
                continue
            deal = self._to_deal(item)
            if deal is not None:
                out.append(deal)
        return out

    @staticmethod
    def _is_current(item: dict) -> bool:
        return (
            item.get("browse_deal_status") == "current"
            and not item.get("has_ended")
            and bool(item.get("has_started"))
            and not item.get("is_addon")
            and bool(item.get("display_on_browse"))
        )

    def _to_deal(self, item: dict) -> Deal | None:
        slug = item.get("slug")
        title = (item.get("public_name") or "").strip()
        abs_url = item.get("get_absolute_url") or ""
        if not slug or not title or not abs_url:
            return None
        url = "https://appsumo.com" + abs_url

        price = self._to_float(item.get("price"))
        was_price = self._to_float(item.get("original_price"))
        discount_percent = None
        if price is not None and was_price is not None and was_price > price > 0:
            discount_percent = round((was_price - price) / was_price * 100, 1)
        else:
            # 0.0-sentinel (or any non-discounting) original_price is not a
            # real "was" price -- surfacing it would render as "was $0.00".
            was_price = None

        return Deal(
            source=self.name,
            deal_id=slug,
            title=title,
            url=url,
            description=_describe(item),
            posted_at=_parse_ts((item.get("dates") or {}).get("start_date")),
            price=price,
            was_price=was_price,
            discount_percent=discount_percent,
            price_confidence="high" if price is not None else None,
            currency="USD",
        )

    @staticmethod
    def _to_float(value: object) -> float | None:
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        return None
