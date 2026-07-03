"""Tests for word-boundary block-keyword matching in main.py."""

from bargain_hunter.main import _is_blocked
from bargain_hunter.models import Deal


def _deal(**kw) -> Deal:
    defaults = dict(
        source="ozbargain",
        deal_id="1",
        title="Test",
        url="https://ozbargain.com.au/node/1",
        votes_pos=10,
        votes_neg=0,
        comment_count=0,
    )
    defaults.update(kw)
    return Deal(**defaults)


def test_block_keyword_does_not_match_substring():
    """Block keyword "pro" must not suppress "projector"."""
    deal = _deal(title="Epson Projector $299")
    assert not _is_blocked(deal, ["pro"])


def test_block_keyword_matches_whole_word():
    deal = _deal(title="Pro subscription discount")
    assert _is_blocked(deal, ["pro"])


def test_block_keyword_no_hits_returns_false():
    deal = _deal(title="Random deal")
    assert not _is_blocked(deal, [])
