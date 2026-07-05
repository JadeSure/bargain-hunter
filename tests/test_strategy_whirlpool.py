"""Tests for the Whirlpool board/thread HTML parsers."""

from pathlib import Path

from strategy_hunter.sources.whirlpool import WhirlpoolSource

FIXTURES = Path(__file__).parent / "fixtures"


def _src():
    return WhirlpoolSource(board_urls=[])


def test_parse_board_extracts_threads():
    name, threads = _src().parse_board(
        (FIXTURES / "whirlpool_board.html").read_text(encoding="utf-8")
    )
    assert name == "Shopping"
    assert len(threads) == 2
    assert threads[0] == ("3n110q7p", "Cheapest place to buy AirPods Pro?", "/thread/3n110q7p")
    assert threads[1][0] == "3271rv29"


def test_parse_thread_returns_op_body():
    body = _src().parse_thread(
        (FIXTURES / "whirlpool_thread.html").read_text(encoding="utf-8")
    )
    assert "cheapest place to buy AirPods Pro" in body
    # Too-short reply ("Amazon usually...", <80 chars) is filtered as noise.
    assert "Amazon usually" not in body


def test_parse_thread_appends_substantive_replies():
    body = _src().parse_thread(
        (FIXTURES / "whirlpool_thread.html").read_text(encoding="utf-8")
    )
    assert "---- replies ----" in body
    assert "[dealhunter]" in body
    assert "Stack a 5% discounted JB Hi-Fi gift card" in body
    # OP body still comes first, replies appended after it.
    assert body.index("cheapest place to buy AirPods Pro") < body.index("---- replies ----")


def test_parse_thread_caps_replies_at_fifteen():
    body = _src().parse_thread(
        (FIXTURES / "whirlpool_thread_many_replies.html").read_text(encoding="utf-8")
    )
    assert body.count("[user") == 15
    for i in range(1, 16):
        assert f"[user{i}]" in body
    for i in range(16, 21):
        assert f"[user{i}]" not in body


def test_parse_thread_no_replies_returns_bare_op_body():
    html = (
        '<html><body><div class="reply">'
        '<div class="replytext bodytext">Just the original post, no replies.</div>'
        "</div></body></html>"
    )
    body = _src().parse_thread(html)
    assert body == "Just the original post, no replies."
    assert "----" not in body


def test_parse_thread_is_deterministic_across_runs():
    html = (FIXTURES / "whirlpool_thread.html").read_text(encoding="utf-8")
    src = _src()
    assert src.parse_thread(html) == src.parse_thread(html)
