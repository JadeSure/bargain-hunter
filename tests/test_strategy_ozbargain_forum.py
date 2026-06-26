"""Tests for the OzBargain forum board/thread HTML parsers."""

from pathlib import Path

from strategy_hunter.sources.ozbargain_forum import OzBargainForumSource

FIXTURES = Path(__file__).parent / "fixtures"


def _src():
    return OzBargainForumSource(board_urls=[])


def test_parse_board_extracts_topics():
    name, topics = _src().parse_board(
        (FIXTURES / "ozb_forum_board.html").read_text(encoding="utf-8")
    )
    assert name == "Find Me A Bargain"
    # 3 real topics; the "#comment" anchor must be excluded, no duplicates.
    assert len(topics) == 3
    ids = [t[0] for t in topics]
    assert ids == ["965128", "964962", "962435"]
    assert topics[0][1] == "Cheapest Way to Get Adobe Creative Cloud?"
    assert topics[0][2] == "/node/965128"


def test_parse_thread_returns_op_body():
    body = _src().parse_thread(
        (FIXTURES / "ozb_forum_thread.html").read_text(encoding="utf-8")
    )
    assert "cheapest way to get Adobe" in body
    # Only the OP (first .content), not the comment, is returned.
    assert "student plan" not in body
