"""Amazon affiliate-tag wrapping for outbound deal links.

Graceful degradation: `AMAZON_AFFILIATE_TAG` is optional; when unset,
`affiliate_url` is the identity function.
"""

from __future__ import annotations

import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_AMAZON_HOSTS = {
    "amazon.com.au",
    "www.amazon.com.au",
    "amazon.com",
    "www.amazon.com",
}


def affiliate_url(url: str, amazon_tag: str | None) -> str:
    """Append `?tag=<amazon_tag>` to Amazon AU/US product URLs; pass everything else through.

    Preserves any existing query params (a pre-existing `tag` param is replaced,
    not duplicated). Returns `url` unchanged if `amazon_tag` is falsy or `url`
    isn't an amazon.com(.au) URL.
    """
    if not amazon_tag or not url:
        return url

    parts = urlsplit(url)
    if parts.netloc.lower() not in _AMAZON_HOSTS:
        return url

    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["tag"] = amazon_tag
    new_query = urlencode(query)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def get_amazon_affiliate_tag() -> str | None:
    """Read the affiliate tag from the environment (unset -> None)."""
    return os.environ.get("AMAZON_AFFILIATE_TAG") or None
