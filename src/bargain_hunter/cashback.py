"""Cashback enrichment: stack a known cashback rate on top of a matching deal.

The core value lever — a "hot" deal is only half the saving; most AU purchases
can also earn cashback (ShopBack/Cashrewards/etc.). We keep a hand-maintained
merchant→rate map in ``config/settings.yaml`` (``cashback.rates``) rather than
scraping live: a config map is robust to markup changes and ToS-friendly, and
``scripts/refresh_cashback.py`` produces refreshed candidate rates for review.

Matching is by merchant host: a deal earns a rate when the host of its
``merchant_url`` (falling back to ``url``) equals a rate key or is a subdomain
of it (``www.amazon.com.au`` and ``amazon.com.au`` both match key
``amazon.com.au``). Longest matching key wins so a specific subdomain rate can
override a broader one.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from .config import CashbackConfig
from .models import Deal


def _host(url: str | None) -> str | None:
    """Return the lowercased hostname of ``url`` with a leading ``www.`` stripped."""
    if not url:
        return None
    netloc = urlsplit(url).netloc.lower()
    # Drop any userinfo/port.
    host = netloc.rsplit("@", 1)[-1].split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host or None


def match_cashback_rate(url: str | None, rates: dict[str, float]) -> tuple[str, float] | None:
    """Return ``(matched_domain, percent)`` for ``url`` against ``rates``, or None.

    A rate key matches when the URL host equals it or is a subdomain of it.
    The longest (most specific) matching key wins.
    """
    host = _host(url)
    if not host or not rates:
        return None
    best: tuple[str, float] | None = None
    for domain, percent in rates.items():
        key = domain.lower().lstrip(".")
        if (host == key or host.endswith("." + key)) and (best is None or len(key) > len(best[0])):
            best = (key, percent)
    return best


def enrich_cashback(deal: Deal, cfg: CashbackConfig) -> Deal:
    """Populate ``deal.cashback_percent`` / ``cashback_provider`` in place.

    No-op when cashback is disabled or no rate matches. Prefers the merchant
    destination (``merchant_url``) over the deal-page ``url`` so an OzBargain
    node link doesn't shadow the real merchant.
    """
    if not cfg.enabled or not cfg.rates:
        return deal
    match = match_cashback_rate(deal.merchant_url, cfg.rates) or match_cashback_rate(
        deal.url, cfg.rates
    )
    if match:
        deal.cashback_percent = match[1]
        deal.cashback_provider = cfg.provider_label
    return deal
