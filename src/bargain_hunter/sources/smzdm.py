"""SMZDM (什么值得买) source: two JSON app-API endpoints, offset-paginated.

什么值得买 is mainland China's largest deal-aggregation site. Its web frontend
sits behind a JS challenge, but the underlying app API (what the Android app
itself calls) does not -- no auth, no key, no CAPTCHA. The only requirement is
an app User-Agent; a browser UA gets HTTP 202 + a JS probe stub instead of
JSON. This is ordinary public-API use (the repo already sends browser UAs to
other sources by convention -- see AGENTS.md), not a challenge bypass: no
CAPTCHA solving, JS execution, or fingerprint spoofing is involved beyond this
one header. Verified live 2026-08-21.

Two endpoints, both under ``https://api.smzdm.com``, both returning
``{"error_code": "0"|"-1", "error_msg": ..., "data": {"rows": [...]}}``:

- ``/v1/home/list`` -- a mixed feed (~20 rows/page). Must be filtered to
  ``article_channel_name == "优惠"``: measured 17/20, the other 3 are ``原创``
  editorial posts (travel blogs, camera reviews) with empty prices.
- ``/v1/youhui/list`` -- all deals (~21 rows/page), no ``article_channel_name``
  field at all (always absent/None) -- do not filter on it here.

``error_code`` is the string ``"0"`` on success, ``"-1"`` with
``error_msg: "Unknown method."`` on a bad path. An HTTP 200 with a non-"0"
error_code is a failure and must not be read as an empty-but-fine page.

Pagination is ``?offset=N`` (``limit`` has no measured effect, so it isn't
sent). The same ``article_id`` can appear on both endpoints (measured, e.g.
"Arale 黑麦全麦面包吐司"), so results are de-duped across endpoints/pages by
``Deal.key``.

Two measured traps:
  - ``/v1/youhui/list`` returned one item ~5.2 years old (a pinned/sentinel
    entry) while every other sampled item was 0.0h old -- a max-age filter
    (default 72h; this is a same-day firehose, not an evergreen feed) drops it.
  - ``article_is_sold_out``/``article_is_timeout`` came back as empty strings,
    not booleans -- treated as advisory only, never as required logic (and
    unused here: ``Deal`` has no matching field).

``article_price`` is a display string with conditions baked in (e.g. "10.96元
（需买3件，需用券）", "低至5折起"), not a clean number.
``scoring.extract_price_signals`` is the repo's existing best-effort price
parser, but it is ``$``-anchored and never matches CNY "元" text, so it can't
be reused directly here. Its "parse only when unambiguous, else leave None"
stance is followed instead: only a bare "N元" with nothing else around it is
parsed as a numeric price; anything else leaves price as None (a wrong number
is worse than no number), with the original string kept visible via
``description``.
"""

import logging
import re
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx

from ..models import Deal
from .base import Source

log = logging.getLogger(__name__)

BASE_URL = "https://api.smzdm.com"
_HOME_PATH = "/v1/home/list"
_YOUHUI_PATH = "/v1/youhui/list"
_FAXIAN_PATH = "/v1/faxian/list"
APP_UA = "smzdm_android_V10.4.20 rv:864 (Redmi K30;Android10;zh)"
_PAGE_SIZE = 20  # offset step between pages -- verified live, `limit` has no effect
_HOME_CHANNEL = "优惠"

# /v1/faxian/list carries no article_unix_date at all -- its timestamp is
# `article_date`, a NAIVE "YYYY-MM-DD HH:MM:SS" string in Beijing time.
# Measured 2026-08-21: fetched at 06:16:16Z, newest article_date read
# "14:16:17" -- exactly +8. Reading it as UTC puts every item 8 hours in the
# FUTURE, which makes the max-age filter silently never fire: the feed looks
# perfectly healthy while the gate it is supposed to pass through does nothing.
_CN_TZ = ZoneInfo("Asia/Shanghai")

# Bare "12.34元" / "12元" only -- anything else (conditions, ranges like "低至
# 5折起") is left unparsed rather than guessed at.
_BARE_PRICE_RE = re.compile(r"^\s*([\d,]+(?:\.\d{1,2})?)\s*元\s*$")


def _to_int(value: object) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _parse_unix(value: object) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), UTC)
    except (TypeError, ValueError, OSError):
        return None


def _parse_cn_datetime(value: object) -> datetime | None:
    """Parse a naive Beijing-time "YYYY-MM-DD HH:MM:SS" string to aware UTC."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        aware = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=_CN_TZ)
    except ValueError:
        return None
    return aware.astimezone(UTC)


def _posted_at(row: dict) -> datetime | None:
    """article_unix_date where present (home/youhui), else article_date (faxian)."""
    return _parse_unix(row.get("article_unix_date")) or _parse_cn_datetime(row.get("article_date"))


def _parse_price(text: str | None) -> tuple[float | None, str | None]:
    if not text:
        return None, None
    match = _BARE_PRICE_RE.match(text)
    if not match:
        return None, None
    return float(match.group(1).replace(",", "")), "high"


def _describe(mall: str | None, price_text: str | None) -> str | None:
    parts = [part for part in (mall, price_text) if part]
    return " · ".join(parts) or None


class SmzdmSource(Source):
    name = "smzdm"

    def __init__(
        self,
        max_pages: int = 2,
        max_item_age_hours: float = 72.0,
        request_delay_seconds: float = 1.0,
        timeout: float = 20.0,
    ) -> None:
        self.max_pages = max_pages
        self.max_item_age_hours = max_item_age_hours
        self.request_delay_seconds = request_delay_seconds
        self.timeout = timeout

    def fetch(self) -> list[Deal]:
        now = datetime.now(UTC)
        deals: dict[str, Deal] = {}  # de-dupe across endpoints/pages by Deal.key
        endpoints = (
            ("home", _HOME_PATH, True),
            ("youhui", _YOUHUI_PATH, False),
            # 发现: 拼多多百亿补贴 / 天猫超市 / 天猫国际 — mainland retail the
            # other two endpoints barely surface. No article_channel_name here
            # either, so nothing to filter on.
            ("faxian", _FAXIAN_PATH, False),
        )
        first_request = True
        for label, path, filter_channel in endpoints:
            for page in range(self.max_pages):
                if not first_request:
                    time.sleep(self.request_delay_seconds)
                first_request = False
                offset = page * _PAGE_SIZE
                try:
                    resp = httpx.get(
                        BASE_URL + path,
                        params={"offset": offset},
                        headers={"User-Agent": APP_UA},
                        timeout=self.timeout,
                    )
                except httpx.HTTPError as exc:
                    log.error("smzdm: %s offset=%d request failed -- %s", label, offset, exc)
                    continue
                if resp.status_code != 200:
                    log.error(
                        "smzdm: %s offset=%d non-200 response (%s)",
                        label,
                        offset,
                        resp.status_code,
                    )
                    continue
                try:
                    data = resp.json()
                except ValueError as exc:
                    log.error(
                        "smzdm: %s offset=%d malformed response body -- %s", label, offset, exc
                    )
                    continue
                for deal in self._parse_page(label, data, filter_channel, now):
                    deals.setdefault(deal.key, deal)
        return list(deals.values())

    def _parse_page(
        self, label: str, data: dict, filter_channel: bool, now: datetime
    ) -> list[Deal]:
        if data.get("error_code") != "0":
            log.error(
                "smzdm: %s api error -- error_code=%s error_msg=%s",
                label,
                data.get("error_code"),
                data.get("error_msg"),
            )
            return []
        rows = (data.get("data") or {}).get("rows") or []
        out: list[Deal] = []
        for row in rows:
            if filter_channel and row.get("article_channel_name") != _HOME_CHANNEL:
                continue
            deal = self._to_deal(row, now)
            if deal is not None:
                out.append(deal)
        return out

    def _to_deal(self, row: dict, now: datetime) -> Deal | None:
        article_id = row.get("article_id")
        title = (row.get("article_title") or "").strip()
        if not article_id or not title:
            return None

        posted_at = _posted_at(row)
        if posted_at is not None:
            age_hours = (now - posted_at).total_seconds() / 3600
            if age_hours > self.max_item_age_hours:
                return None

        url = row.get("article_url") or (row.get("redirect_data") or {}).get("link") or ""
        if not url:
            return None
        if url.startswith("http://"):
            url = "https://" + url[len("http://") :]

        price, confidence = _parse_price(row.get("article_price"))

        return Deal(
            source=self.name,
            deal_id=str(article_id),
            title=title,
            url=url,
            description=_describe(row.get("article_mall"), row.get("article_price")),
            posted_at=posted_at,
            # faxian carries no article_worthy; article_favorite is its nearest
            # engagement counter.
            votes_pos=_to_int(row.get("article_worthy") or row.get("article_favorite")),
            comment_count=_to_int(row.get("article_comment")),
            price=price,
            price_confidence=confidence,
            currency="CNY",
        )
