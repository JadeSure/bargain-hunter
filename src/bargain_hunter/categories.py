"""Category routing: map a deal to subscriber interest buckets.

Subscribers pick broad category buckets (e.g. ``electronics``, ``home``) in the
portal. OzBargain emits granular free-text categories (brands, models, types),
and CamelCamelCamel emits none at all. A config-driven taxonomy
(``settings.yaml`` -> ``categories``) maps each bucket id to a list of match
terms; a deal belongs to a bucket when any term matches.

Matching uses word boundaries (so ``Monitor`` matches "LCD Monitor" but not
"Monitored"). The OzBargain ``categories`` list is the primary signal; when a
deal carries no categories (e.g. CamelCamelCamel) we fall back to the title and
description so those deals can still be routed.
"""

from __future__ import annotations

import re
from functools import lru_cache

from .models import Deal

Taxonomy = dict[str, list[str]]


@lru_cache(maxsize=512)
def _term_pattern(term: str) -> re.Pattern[str]:
    """Compile a case-insensitive, boundary-anchored matcher for one term.

    ``(?<!\\w)``/``(?!\\w)`` are used instead of ``\\b`` so terms containing
    non-word characters (e.g. "Health & Beauty") still anchor correctly.
    """
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)


def _match_text(deal: Deal) -> str:
    """Primary signal = the deal's own categories; fall back to title/desc."""
    if deal.categories:
        return " | ".join(deal.categories)
    return deal.title + " " + (deal.description or "")


def buckets_for_deal(deal: Deal, taxonomy: Taxonomy | None) -> set[str]:
    """Return the set of bucket ids this deal matches under the taxonomy."""
    if not taxonomy:
        return set()
    text = _match_text(deal)
    matched: set[str] = set()
    for bucket, terms in taxonomy.items():
        if any(_term_pattern(term).search(text) for term in terms if term):
            matched.add(bucket)
    return matched


def deal_matches_categories(
    deal: Deal,
    sub_categories: list[str],
    taxonomy: Taxonomy | None,
) -> bool:
    """Return True if the deal is relevant to a subscriber's chosen categories.

    A subscriber with no categories selected matches everything (their alerts are
    not category-restricted).
    """
    if not sub_categories:
        return True
    return bool(buckets_for_deal(deal, taxonomy) & set(sub_categories))
