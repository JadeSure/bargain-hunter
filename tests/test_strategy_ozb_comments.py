"""Tests for the OzBargain deal-comments source (deals feed + comment HTML)."""

from pathlib import Path

from strategy_hunter.sources.ozbargain_comments import OzBargainCommentsSource

FIXTURES = Path(__file__).parent / "fixtures"


def _src(**kw):
    return OzBargainCommentsSource(**kw)


def test_parse_deal_list_extracts_nodes_and_counts():
    deals = _src().parse_deal_list(
        (FIXTURES / "ozb_deals_feed.xml").read_text(encoding="utf-8")
    )
    # The item without a /node/ link is skipped.
    assert [d[0] for d in deals] == ["111111", "222222"]
    assert deals[0][1] == "50% off Apple Gift Cards @ Coles"
    assert deals[0][2] == 42
    assert deals[0][3] == "https://www.ozbargain.com.au/node/111111"
    assert deals[1][2] == 2


def test_parse_node_comments_filters_short_noise():
    comments = _src().parse_node_comments(
        (FIXTURES / "ozb_deal_comments.html").read_text(encoding="utf-8")
    )
    # "Bought. Thanks OP." is below the min length and dropped.
    assert len(comments) == 2
    authors = [c[0] for c in comments]
    assert authors == ["stackmaster", "thrifty"]
    assert "Cashrewards" in comments[0][2]
    # data-ts is parsed into a tz-aware datetime.
    assert comments[0][1] is not None
    assert comments[0][1].tzinfo is not None


def test_build_body_attributes_each_comment():
    comments = [
        ("stackmaster", None, "stack gift cards + cashback"),
        (None, None, "anon tip"),
    ]
    body = OzBargainCommentsSource._build_body("Deal X", comments)
    assert body.startswith("Deal: Deal X")
    assert "[stackmaster] stack gift cards + cashback" in body
    assert "[anon] anon tip" in body
