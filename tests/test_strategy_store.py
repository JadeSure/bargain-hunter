"""Tests for relevance scoring and the raw-corpus store."""

from datetime import UTC, datetime
from pathlib import Path

from strategy_hunter.models import CapturedPost
from strategy_hunter.relevance import relevance_score
from strategy_hunter.store import PostStore


def test_relevance_counts_signal_phrases():
    assert relevance_score("Cheapest way to buy a MacBook with cashback") >= 2
    # Off-topic news with no money-saving signal scores zero.
    assert relevance_score("Reserve bank holds interest rates steady") == 0
    assert relevance_score("") == 0


def _post(body: str = "body") -> CapturedPost:
    return CapturedPost(
        source="reddit",
        post_id="abc",
        url="https://example.com/abc",
        title="Cheapest MacBook",
        body=body,
        fetched_at=datetime.now(UTC),
    )


def test_store_save_is_idempotent_until_content_changes(tmp_path: Path):
    store = PostStore(raw_dir=tmp_path)
    post = _post()

    assert store.save(post) is True                      # new
    assert (tmp_path / "reddit" / "abc.json").exists()
    assert store.save(post) is False                     # unchanged

    post.body = "an edited body with new detail"
    assert store.save(post) is True                      # content changed
