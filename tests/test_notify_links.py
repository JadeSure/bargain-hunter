"""Tests for the Amazon affiliate-tag URL wrapper."""

from bargain_hunter.notify.links import affiliate_url


def test_amazon_au_url_without_existing_query():
    url = affiliate_url("https://www.amazon.com.au/dp/B0ABCDEFG", "myaffid-20")
    assert url == "https://www.amazon.com.au/dp/B0ABCDEFG?tag=myaffid-20"


def test_amazon_url_with_existing_query_preserves_and_replaces_tag():
    url = affiliate_url(
        "https://www.amazon.com.au/dp/B0ABCDEFG?psc=1&tag=old-tag", "myaffid-20"
    )
    assert "psc=1" in url
    assert "tag=myaffid-20" in url
    assert "tag=old-tag" not in url
    # Only one tag param.
    assert url.count("tag=") == 1


def test_non_amazon_url_untouched():
    url = "https://ozbargain.com.au/node/12345"
    assert affiliate_url(url, "myaffid-20") == url


def test_unset_tag_is_identity():
    url = "https://www.amazon.com.au/dp/B0ABCDEFG"
    assert affiliate_url(url, None) == url
    assert affiliate_url(url, "") == url


def test_bare_amazon_com_host_also_tagged():
    url = affiliate_url("https://www.amazon.com/dp/B0ABCDEFG", "myaffid-20")
    assert url == "https://www.amazon.com/dp/B0ABCDEFG?tag=myaffid-20"


def test_empty_url_returns_empty():
    assert affiliate_url("", "myaffid-20") == ""
