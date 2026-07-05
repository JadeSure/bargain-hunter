"""Tests for Sent Log dedup + re-alert logic (spam control core).

No Notion network calls: DedupStore is built directly and its in-memory
`_log` is populated with synthetic SentEntry rows, following the frozen-
fixture ethos used elsewhere in this test suite.
"""

from datetime import UTC, datetime, timedelta

from bargain_hunter.config import DedupConfig
from bargain_hunter.dedup import DedupStore, SentEntry
from bargain_hunter.models import Deal, Subscriber


def _cfg(**kw) -> DedupConfig:
    return DedupConfig(**kw)


def _sub(**kw) -> Subscriber:
    defaults = dict(name="Alice", email="alice@example.com")
    defaults.update(kw)
    return Subscriber(**defaults)


def _deal(**kw) -> Deal:
    defaults = dict(
        source="ozbargain",
        deal_id="1",
        title="Test deal",
        url="https://ozbargain.com.au/node/1",
        votes_pos=10,
        votes_neg=0,
        comment_count=0,
    )
    defaults.update(kw)
    return Deal(**defaults)


def _entry(**kw) -> SentEntry:
    defaults = dict(
        deal_key="ozbargain:1",
        subscriber_email="alice@example.com",
        channel="Email",
        track="hot",
        sent_at=datetime.now(UTC) - timedelta(hours=1),
        price=100.0,
        discount_pct=10.0,
        votes_pos=10,
        heat_band=0,
        realert_count=0,
        trigger_sig="hot",
    )
    defaults.update(kw)
    return SentEntry(**defaults)


def _store_with(entries: list[SentEntry], cfg: DedupConfig | None = None) -> DedupStore:
    store = DedupStore(cfg or _cfg())
    for e in entries:
        store._log.setdefault((e.deal_key, e.subscriber_email), []).append(e)
    return store


# ---------------------------------------------------------------------------
# already_sent — plain dedup, hot track. Never grants a re-alert (PRD P0.3 FR2:
# re-alerts are watch-track-only), regardless of price drop, ceiling, or vote
# growth.
# ---------------------------------------------------------------------------


def test_never_sent_is_not_deduped():
    store = _store_with([])
    deal = _deal()
    sub = _sub()
    assert not store.already_sent(deal, sub)


def test_already_sent_with_no_realerts_allowed_is_always_deduped():
    """max_realerts_per_deal=0 means a single prior send blocks forever,
    regardless of price drop or vote-band jump."""
    entry = _entry(realert_count=0, price=100.0, heat_band=0)
    store = _store_with([entry], cfg=_cfg(max_realerts_per_deal=0))
    deal = _deal(price=10.0, votes_pos=1000)  # huge drop + huge vote jump
    sub = _sub()
    assert store.already_sent(deal, sub)


def test_already_sent_ignores_price_drop_hot_track_never_realerts():
    """Regression: the hot track must not re-alert on price drops even though
    `realert_check` (watch-only) would. `already_sent` always blocks a second
    send once one exists."""
    entry = _entry(realert_count=0, price=100.0, heat_band=0, votes_pos=10)
    store = _store_with(
        [entry], cfg=_cfg(max_realerts_per_deal=1, significant_price_drop_percent=5.0)
    )
    deal = _deal(price=50.0, votes_pos=10)  # 50% drop — would fire via realert_check
    sub = _sub()
    assert store.already_sent(deal, sub)
    skip, label = store.realert_check(deal, sub)
    assert not skip
    assert label == "Price drop: $100 → $50"


def test_already_sent_ignores_heat_band_jump():
    entry = _entry(realert_count=0, heat_band=0, votes_pos=10, price=None)
    store = _store_with([entry], cfg=_cfg(max_realerts_per_deal=1, heat_band_size_votes=50))
    deal = _deal(votes_pos=1000, price=None)  # huge band jump
    sub = _sub()
    assert store.already_sent(deal, sub)


# ---------------------------------------------------------------------------
# realert_check — watch-track-only re-alerts (PRD P0.3 FR1/FR2).
# ---------------------------------------------------------------------------


def test_heat_band_jump_no_longer_triggers_realert():
    """Retired per IMPROVEMENT_PRD P0.3 review: a vote-band jump used to
    re-trigger, but that fires on ordinary hot-deal vote growth (e.g. 45 -> 60
    votes) far too often to justify a re-email. `_heat_band` is still computed
    and recorded in the Sent Log for calibration, it just no longer gates a
    re-alert — only a watch ceiling or a significant price drop does."""
    entry = _entry(realert_count=0, heat_band=0, votes_pos=10, price=None)
    store = _store_with([entry], cfg=_cfg(max_realerts_per_deal=1, heat_band_size_votes=50))
    deal = _deal(votes_pos=60, price=None)  # band 60//50=1 > 0 — no longer matters
    sub = _sub()
    skip, label = store.realert_check(deal, sub)
    assert skip
    assert label is None


def test_no_heat_band_jump_stays_deduped():
    entry = _entry(realert_count=0, heat_band=0, votes_pos=10, price=None)
    store = _store_with([entry], cfg=_cfg(max_realerts_per_deal=1, heat_band_size_votes=50))
    deal = _deal(votes_pos=20, price=None)  # still band 0
    sub = _sub()
    skip, _ = store.realert_check(deal, sub)
    assert skip


def test_significant_price_drop_triggers_realert():
    entry = _entry(realert_count=0, price=100.0, heat_band=0, votes_pos=10)
    store = _store_with(
        [entry], cfg=_cfg(max_realerts_per_deal=1, significant_price_drop_percent=5.0)
    )
    deal = _deal(price=90.0, votes_pos=10)  # 10% drop >= 5%
    sub = _sub()
    skip, _ = store.realert_check(deal, sub)
    assert not skip


def test_insignificant_price_drop_stays_deduped():
    entry = _entry(realert_count=0, price=100.0, heat_band=0, votes_pos=10)
    store = _store_with(
        [entry], cfg=_cfg(max_realerts_per_deal=1, significant_price_drop_percent=5.0)
    )
    deal = _deal(price=98.0, votes_pos=10)  # 2% drop < 5%
    sub = _sub()
    skip, _ = store.realert_check(deal, sub)
    assert skip


def test_newly_satisfied_watch_ceiling_triggers_realert():
    """Acceptance scenario: sent at $350 with watch `Sony <=300`; price drops to
    $290 (at/below the ceiling for the first time) → exactly one re-alert."""
    entry = _entry(realert_count=0, price=350.0, heat_band=0, votes_pos=10)
    store = _store_with([entry], cfg=_cfg(max_realerts_per_deal=1))
    deal = _deal(price=290.0, votes_pos=10)
    sub = _sub()
    skip, _ = store.realert_check(deal, sub, watch_target_price=300.0)
    assert not skip


def test_ceiling_already_satisfied_at_last_send_is_not_newly_satisfied():
    """If the ceiling was already met at the last send, a further small drop that
    stays under `significant_price_drop_percent` is not a *new* ceiling event."""
    entry = _entry(realert_count=0, price=290.0, heat_band=0, votes_pos=10)
    store = _store_with(
        [entry], cfg=_cfg(max_realerts_per_deal=1, significant_price_drop_percent=5.0)
    )
    deal = _deal(price=285.0, votes_pos=10)  # already <=300 at last send; ~1.7% drop
    sub = _sub()
    skip, _ = store.realert_check(deal, sub, watch_target_price=300.0)
    assert skip


def test_ceiling_realert_never_fires_when_last_sent_price_unknown():
    entry = _entry(realert_count=0, price=None, heat_band=0, votes_pos=10)
    store = _store_with([entry], cfg=_cfg(max_realerts_per_deal=1))
    deal = _deal(price=290.0, votes_pos=10)
    sub = _sub()
    skip, _ = store.realert_check(deal, sub, watch_target_price=300.0)
    assert skip


def test_ceiling_realert_never_fires_when_current_price_unknown():
    entry = _entry(realert_count=0, price=350.0, heat_band=0, votes_pos=10)
    store = _store_with([entry], cfg=_cfg(max_realerts_per_deal=1))
    deal = _deal(price=None, votes_pos=10)
    sub = _sub()
    skip, _ = store.realert_check(deal, sub, watch_target_price=300.0)
    assert skip


def test_realert_check_labels_ceiling_price_drop():
    entry = _entry(realert_count=0, price=350.0, heat_band=0, votes_pos=10)
    store = _store_with([entry], cfg=_cfg(max_realerts_per_deal=1))
    deal = _deal(price=290.0, votes_pos=10)
    sub = _sub()
    skip, label = store.realert_check(deal, sub, watch_target_price=300.0)
    assert not skip
    assert label == "Price drop: $350 → $290"


def test_realert_check_labels_significant_price_drop_without_ceiling():
    entry = _entry(realert_count=0, price=100.0, heat_band=0, votes_pos=10)
    store = _store_with(
        [entry], cfg=_cfg(max_realerts_per_deal=1, significant_price_drop_percent=5.0)
    )
    deal = _deal(price=90.0, votes_pos=10)
    sub = _sub()
    skip, label = store.realert_check(deal, sub)
    assert not skip
    assert label == "Price drop: $100 → $90"


def test_significant_price_drop_fires_exactly_one_realert():
    """End-to-end re-alert lifecycle with the production config values
    (max_realerts_per_deal=1, significant_price_drop_percent=5.0, matching
    config/settings.yaml): a >=5% drop on a previously-sent watch deal fires
    exactly one re-alert; a further big drop after that re-alert does not."""
    first_send = _entry(realert_count=0, price=100.0, track="watch", votes_pos=10)
    store = _store_with(
        [first_send],
        cfg=_cfg(max_realerts_per_deal=1, significant_price_drop_percent=5.0),
    )
    sub = _sub()

    # 1st re-check after a 10% drop -> re-alert due.
    dropped = _deal(price=90.0, votes_pos=10)
    skip, label = store.realert_check(dropped, sub)
    assert not skip
    assert label == "Price drop: $100 → $90"

    # Simulate the re-alert having been sent (mirrors record_sent's cache write:
    # realert_count = number of prior entries for this pair).
    store._log[(first_send.deal_key, first_send.subscriber_email)].append(
        _entry(realert_count=1, price=90.0, track="watch", votes_pos=10)
    )

    # 2nd re-check after another huge drop -> cap exhausted, no second re-alert.
    dropped_again = _deal(price=50.0, votes_pos=10)
    skip, label = store.realert_check(dropped_again, sub)
    assert skip
    assert label is None


def test_production_config_enables_price_drop_realert():
    """Guard against the IMPROVEMENT_PRD-reported regression: the shipped
    settings.yaml must keep max_realerts_per_deal >= 1, otherwise the
    significant_price_drop_percent re-alert path is dead code."""
    from bargain_hunter.config import load_settings

    settings = load_settings()
    assert settings.dedup.max_realerts_per_deal >= 1


def test_realert_cap_exhausted_forces_dedup():
    """Once max_realerts_per_deal re-alerts have already fired, further
    price drops no longer matter."""
    entries = [
        _entry(realert_count=0, price=100.0, heat_band=0, votes_pos=10),
        _entry(realert_count=1, price=50.0, heat_band=1, votes_pos=60),
    ]
    store = _store_with(entries, cfg=_cfg(max_realerts_per_deal=1))
    deal = _deal(price=1.0, votes_pos=1000)  # would otherwise qualify for another re-alert
    sub = _sub()
    skip, _ = store.realert_check(deal, sub)
    assert skip


# ---------------------------------------------------------------------------
# daily_count
# ---------------------------------------------------------------------------


def test_daily_count_counts_only_today_aet():
    now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)  # 2026-07-03 20:00 AEST
    yesterday_utc = now - timedelta(days=1)
    entries = [
        _entry(deal_key="ozbargain:1", sent_at=now, track="hot"),
        _entry(deal_key="ozbargain:2", sent_at=yesterday_utc, track="hot"),
    ]
    store = _store_with(entries)
    sub = _sub()
    assert store.daily_count(sub, now=now) == 1


def test_daily_count_dedupes_multiple_entries_for_same_deal():
    now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
    entries = [
        _entry(deal_key="ozbargain:1", sent_at=now, realert_count=0, track="hot"),
        _entry(deal_key="ozbargain:1", sent_at=now, realert_count=1, track="hot"),
    ]
    store = _store_with(entries)
    sub = _sub()
    assert store.daily_count(sub, now=now) == 1


def test_daily_count_filters_by_track_hot_vs_watch():
    now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
    entries = [
        _entry(deal_key="ozbargain:1", sent_at=now, track="hot"),
        _entry(deal_key="ozbargain:2", sent_at=now, track="mixed"),
        _entry(deal_key="ozbargain:3", sent_at=now, track="watch"),
    ]
    store = _store_with(entries)
    sub = _sub()
    assert store.daily_count(sub, now=now, tracks={"hot", "mixed"}) == 2
    assert store.daily_count(sub, now=now, tracks={"watch"}) == 1
    assert store.daily_count(sub, now=now) == 3


def test_daily_count_ignores_other_subscribers():
    now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
    entries = [
        _entry(subscriber_email="alice@example.com", sent_at=now),
        _entry(subscriber_email="bob@example.com", sent_at=now),
    ]
    store = _store_with(entries)
    sub = _sub(email="alice@example.com")
    assert store.daily_count(sub, now=now) == 1
