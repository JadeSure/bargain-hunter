"""Tests for category taxonomy routing (categories.py)."""

from bargain_hunter.categories import buckets_for_deal, deal_matches_categories
from bargain_hunter.models import Deal

TAXONOMY = {
    "electronics": ["Computing", "Monitor", "Phone", "Mouse"],
    "home": ["Home & Garden", "Vacuum"],
    "food": ["Wine", "Groceries"],
}


def _deal(**kwargs) -> Deal:
    defaults = dict(source="ozbargain", deal_id="1", title="Test", url="https://x")
    defaults.update(kwargs)
    return Deal(**defaults)


def test_buckets_from_categories_field():
    d = _deal(categories=["LCD Monitor", "Dell", "Computing"])
    assert buckets_for_deal(d, TAXONOMY) == {"electronics"}


def test_word_boundary_avoids_false_positive():
    # "Monitored" must NOT match the term "Monitor".
    d = _deal(categories=["Monitored Alarm Service"])
    assert buckets_for_deal(d, TAXONOMY) == set()


def test_multi_word_term_with_ampersand():
    d = _deal(categories=["Home & Garden"])
    assert buckets_for_deal(d, TAXONOMY) == {"home"}


def test_title_fallback_when_no_categories():
    # CamelCamelCamel deals carry no categories — fall back to the title.
    d = _deal(title="Logitech Wireless Mouse", categories=[])
    assert buckets_for_deal(d, TAXONOMY) == {"electronics"}


def test_categories_field_takes_precedence_over_title():
    # When categories exist, the title is NOT searched (avoids title noise).
    d = _deal(title="Great in your kitchen with wine", categories=["Computing"])
    assert buckets_for_deal(d, TAXONOMY) == {"electronics"}


def test_deal_matches_categories_true_on_overlap():
    d = _deal(categories=["Computing"])
    assert deal_matches_categories(d, ["electronics", "food"], TAXONOMY) is True


def test_deal_matches_categories_false_on_no_overlap():
    d = _deal(categories=["Computing"])
    assert deal_matches_categories(d, ["food"], TAXONOMY) is False


def test_empty_subscriber_categories_matches_everything():
    d = _deal(categories=["Computing"])
    assert deal_matches_categories(d, [], TAXONOMY) is True


def test_no_taxonomy_means_no_buckets():
    d = _deal(categories=["Computing"])
    assert buckets_for_deal(d, None) == set()
    # With categories selected but no taxonomy, nothing can match.
    assert deal_matches_categories(d, ["electronics"], None) is False
