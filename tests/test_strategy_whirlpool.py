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
    # First reply (OP) only; the second reply must not leak in.
    assert "Amazon usually" not in body
