"""Entry point: orchestrates one complete Bargain Hunter run.

Usage:
  python -m bargain_hunter.main          # live run
  python -m bargain_hunter.main --dry-run
  python -m bargain_hunter.main --help
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from . import leaderboard
from .alert_throttle import AlertThrottle
from .cashback import enrich_cashback
from .categories import deal_matches_categories
from .config import Settings, effective_tiers, load_dotenv, load_settings
from .dedup import DedupStore
from .matching import _keyword_pattern, filter_watch_matches
from .models import Deal, Subscriber
from .notify.email import EmailSender, send_maintainer_alert
from .notify.render import DealItem
from .observations import ObservationLog, build_observation
from .price_history import enrich_price_ranks
from .queue_store import NotificationQueue
from .quiet_hours import is_in_quiet_hours
from .scoring import (
    classify_hot,
    compute_heat_ratio,
    compute_site_velocity_index,
    compute_vote_velocity,
    enrich_deal,
    is_voteless_source,
)
from .sources.bank_rates import BankRatesSource
from .sources.camelcamelcamel import CamelCamelCamelSource
from .sources.feed_deals import FeedDealsSource
from .sources.llm_prices import LlmPriceSource
from .sources.ozbargain import OzBargainSource
from .state import StateStore
from .subscribers import fetch_subscribers, make_notion_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

# Hour-of-day baseline buckets are keyed in Australia/Sydney time so an event
# day's dilution isn't misread as (or masked by) the normal 3am lull.
_AET = ZoneInfo("Australia/Sydney")

# Non-physical, voteless, watch-track sources that share one separate daily
# quota (Subscriber.max_digital_alerts_per_day) instead of the AU hot/watch
# caps — each is too thin to justify its own quota, but too easily crowded
# out if it shared the OzBargain/CamelCamelCamel caps.
DIGITAL_SOURCES = {
    "dealnews",
    "slickdeals",
    "v2ex",
    "openrouter",
    "bank_rates",
    "iknowthepilot",
}


def _save_state(state: StateStore, dry_run: bool) -> None:
    """Persist state, unless this is a dry run.

    ``data/deals_state.json`` is committed to `main` as a calibration seed —
    a local ``--dry-run`` must never overwrite it.
    """
    if not dry_run:
        state.save()


def run(settings: Settings, dry_run: bool = False, force: bool = False) -> dict:
    """Execute one full run.  Returns a summary dict (counts only, no PII)."""
    summary: dict = {
        "deals_fetched": 0,
        "hot_deals": 0,
        "watch_matches": 0,
        "notifications_sent": 0,
        "queued": 0,
        "errors": [],
        "cold_start": False,
    }

    now = datetime.now(UTC)

    # ------------------------------------------------------------------
    # 1. Load state
    # ------------------------------------------------------------------
    state = StateStore(path=Path("data/deals_state.json"))
    state.load()
    summary["cold_start"] = state.is_cold_start()

    # ------------------------------------------------------------------
    # 2. Fetch deals from enabled sources
    # ------------------------------------------------------------------
    all_deals: list[Deal] = []
    ozb_cfg = settings.sources.get("ozbargain")
    if ozb_cfg and ozb_cfg.enabled:
        feed_url = getattr(ozb_cfg, "feed_url", None)
        try:
            src = OzBargainSource(feed_url=feed_url) if feed_url else OzBargainSource()
            raw_deals = src.fetch()
            log.info("OzBargain: fetched %d deals.", len(raw_deals))
            all_deals.extend(raw_deals)
        except Exception as exc:
            msg = f"OzBargain fetch failed: {exc}"
            log.error(msg)
            summary["errors"].append(msg)

    ccc_cfg = settings.sources.get("camelcamelcamel")
    if ccc_cfg and ccc_cfg.enabled:
        feed_url = getattr(ccc_cfg, "feed_url", None)
        try:
            src = CamelCamelCamelSource(feed_url=feed_url) if feed_url else CamelCamelCamelSource()
            raw_deals = src.fetch()
            log.info("CamelCamelCamel: fetched %d deals.", len(raw_deals))
            all_deals.extend(raw_deals)
        except Exception as exc:
            msg = f"CamelCamelCamel fetch failed: {exc}"
            log.error(msg)
            summary["errors"].append(msg)

    # Slower-cadence sources (hourly/daily), gated on state.due_for_fetch so
    # the 5-min hot-path loop doesn't hammer them every run.
    for src_name in ("dealnews", "slickdeals", "v2ex", "iknowthepilot"):
        cfg = settings.sources.get(src_name)
        if not (cfg and cfg.enabled):
            continue
        interval = getattr(cfg, "poll_interval_minutes", 60)
        if not state.due_for_fetch(src_name, interval, now):
            continue
        try:
            src = FeedDealsSource(
                name=src_name,
                feed_urls=list(getattr(cfg, "feed_urls", [])),
                currency=getattr(cfg, "currency", "USD"),
                block_patterns=list(getattr(cfg, "region_block_patterns", [])),
                allow_patterns=list(getattr(cfg, "region_allow_patterns", [])),
            )
            raw_deals = src.fetch()
            log.info("%s: fetched %d deals.", src_name, len(raw_deals))
            all_deals.extend(raw_deals)
            state.mark_fetched(src_name, now)
        except Exception as exc:
            msg = f"{src_name} fetch failed: {exc}"
            log.error(msg)
            summary["errors"].append(msg)

    or_cfg = settings.sources.get("openrouter")
    if (
        or_cfg
        and or_cfg.enabled
        and state.due_for_fetch("openrouter", getattr(or_cfg, "poll_interval_minutes", 1440), now)
    ):
        try:
            src = LlmPriceSource(
                min_drop_percent=getattr(or_cfg, "min_drop_percent", 10.0),
                model_allowlist=list(getattr(or_cfg, "model_allowlist", [])),
            )
            or_deals, or_snapshot = src.check(state.snapshot("llm_prices"), now=now)
            log.info("openrouter: %d price-change deal(s).", len(or_deals))
            all_deals.extend(or_deals)
            state.set_snapshot("llm_prices", or_snapshot)
            state.mark_fetched("openrouter", now)
            # src.last_models is [] when this run's fetch failed -- leave the
            # leaderboard's llm_models section untouched rather than blanking it.
            if not dry_run and src.last_models:
                leaderboard.update(llm_models=src.last_models, now=now)
        except Exception as exc:
            msg = f"openrouter fetch failed: {exc}"
            log.error(msg)
            summary["errors"].append(msg)

    br_cfg = settings.sources.get("bank_rates")
    if (
        br_cfg
        and br_cfg.enabled
        and state.due_for_fetch("bank_rates", getattr(br_cfg, "poll_interval_minutes", 1440), now)
    ):
        try:
            src = BankRatesSource(
                brands=list(getattr(br_cfg, "brands", [])),
                product_categories=list(getattr(br_cfg, "product_categories", [])),
                min_rate_rise_bps=getattr(br_cfg, "min_rate_rise_bps", 10),
                min_bonus_points_rise=getattr(br_cfg, "min_bonus_points_rise", 10000),
                max_detail_fetches_per_run=getattr(br_cfg, "max_detail_fetches_per_run", 40),
                previous_snapshot=state.snapshot("bank_rates"),
                previous_leaderboard=leaderboard.load().get("bank_products") or {},
            )
            br_deals = src.fetch()
            log.info("bank_rates: %d rate-change deal(s).", len(br_deals))
            all_deals.extend(br_deals)
            state.set_snapshot("bank_rates", src.next_snapshot)
            state.mark_fetched("bank_rates", now)
            if not dry_run:
                leaderboard.update(bank_products=src.next_leaderboard, now=now)
        except Exception as exc:
            msg = f"bank_rates fetch failed: {exc}"
            log.error(msg)
            summary["errors"].append(msg)

    if not all_deals and not summary["errors"]:
        # Feed returned 0 deals without error — likely a format change.
        msg = "0 deals fetched — possible feed format change."
        log.error(msg)
        summary["errors"].append(msg)

    summary["deals_fetched"] = len(all_deals)

    # Enrich with price/discount signals
    all_deals = [enrich_deal(d) for d in all_deals]

    # Stack any known cashback rate on top (config-maintained merchant→rate map).
    if settings.cashback.enabled:
        for deal in all_deals:
            enrich_cashback(deal, settings.cashback)

    # Filter expired/out-of-stock (including deals whose expiry timestamp has passed).
    active_deals = [d for d in all_deals if not d.expired and (d.expiry is None or d.expiry > now)]
    if d := len(all_deals) - len(active_deals):
        log.info("Filtered %d expired deals.", d)

    # Rank each priced deal against its own recent price history (from the
    # observation log) so "hot" is qualified by whether it's genuinely cheap.
    enrich_price_ranks(active_deals, settings.price_history, now)

    # ------------------------------------------------------------------
    # 3. Record snapshots (always, even on cold start)
    # ------------------------------------------------------------------
    # Capture first-sightings BEFORE recording: record() populates first-seen for
    # every deal, which would otherwise defeat the staleness guard in should_notify.
    first_sighting = {d.key for d in active_deals if state.is_new_to_system(d.key)}
    for deal in active_deals:
        state.record(deal, now=now)

    # ------------------------------------------------------------------
    # 4. Score hot deals
    # ------------------------------------------------------------------
    snaps_map = {d.key: state.snapshots(d.key) for d in active_deals}
    active_pairs = [(d, snaps_map[d.key]) for d in active_deals]

    # ------------------------------------------------------------------
    # 4a. Event-day adaptive baseline: compute this run's site heat ratio
    #     against the PRE-update baseline, classify with it, then update the
    #     baseline. Voteless sources (e.g. CCC) are excluded from the index —
    #     they carry no vote signal and would only drag it down.
    # ------------------------------------------------------------------
    adaptive_cfg = settings.scoring.hot.adaptive
    heat_ratio = 1.0
    site_velocity_index: float | None = None
    if not state.is_cold_start():
        vote_based_pairs = [
            (d, snaps)
            for d, snaps in active_pairs
            if not is_voteless_source(d, settings.scoring.hot)
        ]
        site_velocity_index = compute_site_velocity_index(
            vote_based_pairs,
            settings.scoring.window_minutes,
            adaptive_cfg.index_percentile,
            now=now,
        )
        n_index_samples = sum(1 for _d, snaps in vote_based_pairs if len(snaps) >= 2)
        if n_index_samples < adaptive_cfg.min_deals_for_index:
            site_velocity_index = None

        hour = now.astimezone(_AET).hour
        baseline_entry = state.site_baseline(hour)
        baseline_value = baseline_entry[0] if baseline_entry else None
        heat_ratio = compute_heat_ratio(
            site_velocity_index, baseline_value, adaptive_cfg, state.baseline_age_days(now)
        )
        if site_velocity_index is not None and adaptive_cfg.enabled:
            state.update_site_baseline(
                site_velocity_index,
                hour,
                now,
                adaptive_cfg.ewma_half_life_days,
                adaptive_cfg.baseline_sample_clamp,
            )
    log.info(
        "Adaptive baseline: heat_ratio=%.3f site_velocity_index=%s",
        heat_ratio,
        site_velocity_index,
    )
    summary["heat_ratio"] = round(heat_ratio, 3)
    summary["site_velocity_index"] = site_velocity_index

    hot_deals: list[Deal] = []
    # Hot ladder + routing inputs, computed once for the whole run.
    tiers = effective_tiers(settings.scoring.hot)
    top_name = tiers[0].name
    # Rank tiers so a higher rank = a more valuable deal (e.g. good=0, great=1, top=2).
    tier_rank = {tier.name: i for i, tier in enumerate(reversed(tiers))}
    taxonomy = settings.categories
    hot_levels: dict[str, str] = {}
    if not state.is_cold_start():
        for deal in active_deals:
            if not state.should_notify(
                deal,
                settings.cold_start.ignore_deals_older_than_hours,
                deal.key in first_sighting,
                now=now,
                snapshots=snaps_map[deal.key],
                window_minutes=settings.scoring.window_minutes,
                min_votes_gain_per_window=settings.scoring.hot.min_votes_gain_per_window,
                hot_cfg=settings.scoring.hot,
            ):
                continue
            level = classify_hot(
                deal,
                snaps_map[deal.key],
                settings.scoring,
                active_pairs,
                now=now,
                heat_ratio=heat_ratio,
            )
            if level is not None:
                hot_levels[deal.key] = level
        # Best tiers first so the per-subscriber daily cap favours the top deals.
        hot_deals = sorted(
            (d for d in active_deals if d.key in hot_levels),
            key=lambda d: tier_rank.get(hot_levels[d.key], 0),
            reverse=True,
        )
        summary["hot_deals"] = len(hot_deals)
        log.info("Hot deals this run: %d", len(hot_deals))

    # ------------------------------------------------------------------
    # 4b. Log per-deal features for calibration (runs regardless of Notion).
    #     Every active deal, not just hot ones, so tuning can see what we missed.
    # ------------------------------------------------------------------
    hot_keys = {d.key for d in hot_deals}
    obs = ObservationLog()
    for deal in active_deals:
        obs.add(
            build_observation(
                deal,
                snaps_map[deal.key],
                settings.scoring,
                is_hot=deal.key in hot_keys,
                level=hot_levels.get(deal.key),
                now=now,
                heat_ratio=heat_ratio,
                site_velocity_index=site_velocity_index,
            )
        )
    if dry_run:
        log.info("Dry run: state and observations were not persisted to disk.")
    else:
        obs.flush(now)

    # ------------------------------------------------------------------
    # 5. Notion: subscribers + dedup (skip if no token / dry-run mock)
    # ------------------------------------------------------------------
    notion_token = os.environ.get("NOTION_TOKEN")
    subscribers_db = os.environ.get("NOTION_SUBSCRIBERS_DB_ID")
    sent_log_db = os.environ.get("NOTION_SENT_LOG_DB_ID")

    has_notion = bool(notion_token and subscribers_db and sent_log_db)

    if not has_notion:
        if not dry_run:
            log.warning("NOTION_TOKEN / DB IDs not set — skipping subscriber fetch and dedup.")
        _save_state(state, dry_run)
        return summary

    notion = make_notion_client()
    try:
        subscribers = fetch_subscribers(
            notion,
            subscribers_db,
            settings.run.max_alerts_per_user_per_day,
            settings.run.max_digital_alerts_per_day,
        )
    except Exception as exc:
        msg = f"Subscriber fetch failed: {exc}"
        log.error(msg)
        summary["errors"].append(msg)
        _save_state(state, dry_run)
        return summary

    dedup = DedupStore(cfg=settings.dedup)
    try:
        dedup.load(notion, sent_log_db)
    except Exception as exc:
        # Fail CLOSED: without the sent-log we cannot dedup, and daily caps also
        # read from it — proceeding would re-send every qualifying deal to everyone
        # (up to each cap) on every run. Skipping sends is far cheaper than spam.
        msg = f"Dedup load failed: {exc} — skipping all sends this run (fail-closed)."
        log.error(msg)
        summary["errors"].append(msg)
        _save_state(state, dry_run)
        return summary

    # ------------------------------------------------------------------
    # 6. Match + notify each subscriber
    # ------------------------------------------------------------------
    # During quiet hours we don't drop notifications — we queue them (per
    # subscriber) and drain the queue into the first digest after quiet hours
    # end, re-checking staleness and Sent Log dedup at drain time. Quiet hours
    # are resolved per subscriber (their own window overrides the global one),
    # so on any given run some subscribers may be queueing while others drain.
    if force:
        log.info("--force set; quiet hours are bypassed for all subscribers.")

    queue = NotificationQueue()
    queue.load()
    max_age = settings.run.quiet_hours_queue_max_age_hours

    sender = EmailSender(dry_run=dry_run)

    for sub in subscribers:
        if not sub.active:
            continue

        # This subscriber's effective quiet window (own override, else global).
        sub_quiet = not force and is_in_quiet_hours(sub, now, settings.run)

        # Daily caps — hot and watch are independent quotas.
        # "mixed" deals (hot-qualified + watch keyword hit) count against hot cap only.
        # While a subscriber is quiet, caps are NOT applied: the drain (usually
        # the next AET day, when caps have reset) applies them instead.
        hot_daily = dedup.daily_count(sub, now=now, tracks={"hot", "mixed"})
        watch_daily = dedup.daily_count(sub, now=now, tracks={"watch"})
        digital_daily = dedup.daily_count(sub, now=now, tracks={"digital"})
        remaining_hot = sub.max_alerts_per_day - hot_daily
        remaining_watch = sub.max_watch_alerts_per_day - watch_daily
        remaining_digital = sub.max_digital_alerts_per_day - digital_daily

        if not sub_quiet and remaining_hot <= 0 and remaining_watch <= 0 and remaining_digital <= 0:
            log.info(
                "Subscriber %s at daily caps (hot=%d/%d watch=%d/%d digital=%d/%d); skipping.",
                sub.ref,
                hot_daily,
                sub.max_alerts_per_day,
                watch_daily,
                sub.max_watch_alerts_per_day,
                digital_daily,
                sub.max_digital_alerts_per_day,
            )
            continue

        if sub_quiet:
            queued = []
        else:
            queued = queue.drain_for(sub.email or "", now=now, max_age_hours=max_age)
            # Survivors are merged into this digest; anything stale is dropped.
            # Only this subscriber's entries — others may still be in their own
            # quiet window and are owed theirs later.
            queue.remove_for(sub.email or "")

        # Candidates = passed every filter except the daily cap (applied after
        # the queued-entry merge so tier sorting decides who wins cap slots).
        hot_candidates: list[DealItem] = []
        watch_candidates: list[DealItem] = []
        # Digital-source deals (DIGITAL_SOURCES) are peeled out of hot/watch
        # candidates below and compete for their own cap instead.
        digital_candidates: list[DealItem] = []
        # Deals that passed every filter except a daily cap. Surfaced in the
        # digest footer so cap truncation is visible instead of silent.
        cap_suppressed = 0

        # Hot track
        if sub.subscribe_hot and hot_deals:
            for deal in hot_deals:
                if _is_blocked(deal, sub.block_keywords):
                    log.info("[%s] hot skip %s: blocked keyword", sub.ref, deal.key)
                    continue
                if dedup.already_sent(deal, sub):
                    log.info("[%s] hot skip %s: already sent", sub.ref, deal.key)
                    continue
                level = hot_levels.get(deal.key, top_name)
                if not _hot_level_eligible(
                    deal,
                    level,
                    sub,
                    tier_rank=tier_rank,
                    top_name=top_name,
                    taxonomy=taxonomy,
                    universal_top=settings.scoring.hot.universal_top,
                ):
                    log.info("[%s] hot skip %s: level/category (%s)", sub.ref, deal.key, level)
                    continue
                vel, _ = compute_vote_velocity(
                    snaps_map.get(deal.key, []), settings.scoring.window_minutes, now
                )
                # Quality gate guards the lowest tier only. Deals at "great"/"top" already
                # earned a higher score threshold via classify_hot; don't double-filter.
                # It is also vote-velocity based, so it doesn't apply to voteless-source
                # deals (e.g. CamelCamelCamel) — those already earned their tier purely
                # on discount depth (see scoring.classify_discount_tier), which is a
                # sufficient quality bar on its own.
                is_elevated = tier_rank.get(level, 0) > tier_rank.get(tiers[-1].name, 0)
                passes_qg = (
                    is_elevated
                    or is_voteless_source(deal, settings.scoring.hot)
                    or _passes_quality_gate(deal, settings.scoring.hot, vote_velocity=vel)
                )
                if not passes_qg:
                    log.info(
                        "[%s] hot skip %s: quality gate (votes=%d disc=%s vel=%.1f)",
                        sub.ref,
                        deal.key,
                        deal.votes_pos,
                        deal.discount_percent,
                        vel,
                    )
                    continue
                hot_candidates.append(
                    DealItem(deal, track="hot", reason=_hot_reason(deal), level=level)
                )

        # Merge queued (overnight) hot/mixed entries: staleness was already
        # filtered by drain_for; re-check dedup and blocks at drain time.
        hot_candidate_keys = {item.deal.key for item in hot_candidates}
        for q in queued:
            if q.track not in {"hot", "mixed"} or q.deal.key in hot_candidate_keys:
                continue
            if dedup.already_sent(q.deal, sub):
                continue
            if _is_blocked(q.deal, sub.block_keywords):
                continue
            hot_candidates.append(DealItem(q.deal, track=q.track, reason=q.reason, level=q.level))
            hot_candidate_keys.add(q.deal.key)

        # Digital-source deals get their own quota, not the hot cap.
        hot_candidates, digital_from_hot = _split_digital(hot_candidates)
        digital_candidates.extend(digital_from_hot)

        # Best tiers first, then apply the daily cap (skipped in queue mode —
        # the drain applies caps instead).
        hot_candidates.sort(key=lambda item: tier_rank.get(item.level or "", 0), reverse=True)
        if sub_quiet:
            hot_items = hot_candidates
        else:
            hot_items = hot_candidates[: max(remaining_hot, 0)]
            if len(hot_candidates) > len(hot_items):
                log.info(
                    "[%s] hot: %d deal(s) held back by daily cap",
                    sub.ref,
                    len(hot_candidates) - len(hot_items),
                )
                cap_suppressed += len(hot_candidates) - len(hot_items)
        notified_keys = {item.deal.key for item in hot_items} | {
            item.deal.key for item in digital_from_hot
        }

        # Watch track (independent cap — does not share quota with hot)
        watch_hits = filter_watch_matches(active_deals, sub, settings.scoring.watch, now=now)
        for deal, reason, watch_target_price in watch_hits:
            if deal.key in notified_keys:
                # Already queued via hot — annotate as mixed (no watch cap cost).
                # Digital-source deals were already peeled into digital_from_hot
                # above, so they must be searched too or the annotation is a
                # silent no-op and the watch-specific reason is lost.
                for item in hot_items + digital_from_hot:
                    if item.deal.key == deal.key:
                        item.track = "mixed"
                        item.reason = f"{item.reason} · {reason}"
                continue
            if _is_blocked(deal, sub.block_keywords):
                continue
            if not state.should_notify(
                deal,
                settings.cold_start.ignore_deals_older_than_hours,
                deal.key in first_sighting,
                now=now,
                snapshots=snaps_map.get(deal.key, []),
                window_minutes=settings.scoring.window_minutes,
                min_votes_gain_per_window=settings.scoring.hot.min_votes_gain_per_window,
                hot_cfg=settings.scoring.hot,
            ):
                continue
            skip, realert_label = dedup.realert_check(
                deal, sub, watch_target_price=watch_target_price
            )
            if skip:
                continue
            if realert_label:
                reason = f"{reason} · {realert_label}"
            watch_candidates.append(DealItem(deal, track="watch", reason=reason))
            notified_keys.add(deal.key)

        # Merge queued (overnight) watch entries, then apply the watch cap.
        for q in queued:
            if q.track != "watch" or q.deal.key in notified_keys:
                continue
            if dedup.already_sent(q.deal, sub):
                continue
            if _is_blocked(q.deal, sub.block_keywords):
                continue
            watch_candidates.append(DealItem(q.deal, track="watch", reason=q.reason))
            notified_keys.add(q.deal.key)

        # Digital-source deals get their own quota, not the watch cap.
        watch_candidates, digital_from_watch = _split_digital(watch_candidates)
        digital_candidates.extend(digital_from_watch)

        # Merge queued (overnight) digital entries. A third drain block is
        # required here — the hot/mixed and watch drains above filter this
        # track out, so without it a queued digital entry is silently lost.
        for q in queued:
            if q.track != "digital" or q.deal.key in notified_keys:
                continue
            if dedup.already_sent(q.deal, sub):
                continue
            if _is_blocked(q.deal, sub.block_keywords):
                continue
            digital_candidates.append(
                DealItem(q.deal, track="digital", reason=q.reason, level=q.level)
            )
            notified_keys.add(q.deal.key)

        if sub_quiet:
            watch_items = watch_candidates
        else:
            watch_items = watch_candidates[: max(remaining_watch, 0)]
            if len(watch_candidates) > len(watch_items):
                log.info(
                    "[%s] watch: %d deal(s) held back by daily cap",
                    sub.ref,
                    len(watch_candidates) - len(watch_items),
                )
                cap_suppressed += len(watch_candidates) - len(watch_items)

        # Best tiers first (mirrors hot), discount depth as a tiebreak — most
        # digital deals arrive via watch and carry no tier, so discount decides.
        digital_candidates.sort(
            key=lambda item: (tier_rank.get(item.level or "", 0), item.deal.discount_percent or 0),
            reverse=True,
        )
        if sub_quiet:
            digital_items = digital_candidates
        else:
            digital_items = digital_candidates[: max(remaining_digital, 0)]
            if len(digital_candidates) > len(digital_items):
                log.info(
                    "[%s] digital: %d deal(s) held back by daily cap",
                    sub.ref,
                    len(digital_candidates) - len(digital_items),
                )
                cap_suppressed += len(digital_candidates) - len(digital_items)

        items = hot_items + watch_items + digital_items
        if not items:
            continue

        if sub_quiet:
            email = sub.email or ""
            for item in items:
                queue.add(email, item.deal, item.track, item.level, item.reason, now=now)
            summary["queued"] += len(items)
            log.info("[%s] quiet hours — %d notification(s) queued.", sub.ref, len(items))
            continue

        summary["watch_matches"] += len(watch_items)

        # Send
        ok = sender.send_digest(sub, items, cap_suppressed=cap_suppressed)
        if ok:
            summary["notifications_sent"] += len(items)
            for item in items:
                trigger_sig = f"{item.track}:{item.reason[:200]}"
                try:
                    dedup.record_sent(
                        notion,
                        sent_log_db,
                        item.deal,
                        sub,
                        channel="Email",
                        track=item.track,
                        trigger_sig=trigger_sig,
                    )
                except Exception as exc:
                    log.error(
                        "Sent Log write failed for %s / %s: %s",
                        item.deal.key,
                        sub.ref,
                        exc,
                    )
                    summary["errors"].append(f"Sent log write error: {exc}")

    # ------------------------------------------------------------------
    # 7. Save state (and the quiet-hours queue)
    # ------------------------------------------------------------------
    # Persist queue additions (quiet subscribers) and removals (drained ones).
    queue.save()
    if summary["queued"]:
        log.info("Quiet hours: %d notification(s) queued for later delivery.", summary["queued"])

    _save_state(state, dry_run)

    log.info(
        "Run complete. fetched=%d hot=%d watch_hits=%d sent=%d errors=%d cold_start=%s",
        summary["deals_fetched"],
        summary["hot_deals"],
        summary["watch_matches"],
        summary["notifications_sent"],
        len(summary["errors"]),
        summary["cold_start"],
    )
    return summary


def _hot_level_eligible(
    deal: Deal,
    level: str,
    sub: Subscriber,
    *,
    tier_rank: dict[str, int],
    top_name: str,
    taxonomy: dict[str, list[str]] | None,
    universal_top: bool,
) -> bool:
    """Whether a classified hot deal should reach this subscriber.

    Two gates, both must pass:
      1. Level floor — the deal's tier must rank at or above the subscriber's
         chosen minimum hot level (no choice = no floor).
      2. Category — subscribers with no categories receive everything; otherwise
         in-category deals pass, and out-of-category deals pass only when the deal
         is ``top`` and ``universal_top`` is enabled (the universal best-of-best).
    """
    floor = sub.min_hot_level
    if floor in tier_rank and tier_rank.get(level, -1) < tier_rank[floor]:
        return False

    if not sub.categories:
        return True
    if deal_matches_categories(deal, sub.categories, taxonomy):
        return True
    return universal_top and level == top_name


def _split_digital(items: list[DealItem]) -> tuple[list[DealItem], list[DealItem]]:
    """Peel deals from DIGITAL_SOURCES out of a candidate list, retagging
    their track so they compete for the digital cap instead of hot/watch's."""
    kept: list[DealItem] = []
    digital: list[DealItem] = []
    for item in items:
        if item.deal.source in DIGITAL_SOURCES:
            item.track = "digital"
            digital.append(item)
        else:
            kept.append(item)
    return kept, digital


def _is_blocked(deal: Deal, block_keywords: list[str]) -> bool:
    """Return True if any block keyword appears in the deal title or description."""
    if not block_keywords:
        return False
    import re

    text = deal.title + " " + (deal.description or "")
    return any(re.search(_keyword_pattern(kw), text, re.IGNORECASE) for kw in block_keywords)


def _passes_quality_gate(deal: Deal, hot_cfg, vote_velocity: float = 0.0) -> bool:
    """Data-backed quality filter for hot deals.

    High velocity (>=20 votes/h) is itself a quality signal — data shows these
    deals reach 50-120 votes regardless of extractable discount. Bypass the
    discount check so fast-moving deals (GTA VI, Dell monitors, etc.) aren't
    delayed until they accumulate 40+ votes.

    For lower-velocity deals: promo/food/membership deals cluster at 18-38 votes
    with no discount signal, so require discount >= quality_min_discount_pct unless
    they've already accumulated quality_high_votes_threshold votes.
    """
    min_disc = hot_cfg.quality_min_discount_pct
    if min_disc is None:
        return True
    if vote_velocity >= 20.0:
        return True
    if deal.votes_pos >= hot_cfg.quality_high_votes_threshold:
        return True
    return deal.discount_percent is not None and deal.discount_percent >= min_disc


def _hot_reason(deal: Deal) -> str:
    parts = []
    if deal.votes_pos or deal.votes_neg:
        parts.append(f"▲ {deal.votes_pos} votes")
    if deal.discount_percent:
        parts.append(f"{deal.discount_percent:.0f}% off")
    return " · ".join(parts) or "Hot deal"


def _alert_if_needed(summary: dict, settings: Settings, now: datetime) -> None:
    """Send maintainer alert on failure or zero-deal anomaly, with throttling."""
    throttle = AlertThrottle(
        min_consecutive_failures=settings.alerting.min_consecutive_failures,
        cooldown_hours=settings.alerting.cooldown_hours,
    )
    throttle.load()

    has_error = bool(summary["errors"]) or (
        summary["deals_fetched"] == 0 and not summary["cold_start"]
    )

    if has_error:
        throttle.record_failure()
    else:
        throttle.record_success()

    if has_error and throttle.should_alert(now):
        subject = f"Run failed or 0 deals fetched ({throttle._failures} consecutive)"
        body = (
            f"Bargain Hunter has failed {throttle._failures} run(s) in a row.\n\n"
            f"  deals_fetched : {summary['deals_fetched']}\n"
            f"  hot_deals     : {summary['hot_deals']}\n"
            f"  sent          : {summary['notifications_sent']}\n"
            f"  cold_start    : {summary['cold_start']}\n"
            f"  errors:\n" + "\n".join(f"    - {e}" for e in summary["errors"])
        )
        send_maintainer_alert(subject, body)
        throttle.record_sent(now)

    throttle.save()


def _heartbeat(summary: dict) -> None:
    """Ping a dead-man's-switch URL on a clean run (FR10).

    An external monitor (e.g. healthchecks.io) raises an alert if these pings
    stop — the only way to catch the whole pipeline going silent (cron-job.org
    down, Actions disabled, PAT expired), which in-process alerting cannot.
    """
    url = os.environ.get("HEALTHCHECK_URL")
    if not url or summary["errors"]:
        return
    try:
        httpx.get(url, timeout=10)
    except Exception as exc:  # a failed heartbeat must never break the run
        log.warning("Heartbeat ping failed: %s", exc)


def main() -> None:
    load_dotenv()  # load .env if present; real env vars (Actions Secrets) always win
    parser = argparse.ArgumentParser(description="Bargain Hunter deal alerter.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without sending.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass quiet hours and send immediately (still writes Sent Log).",
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=None,
        help="Path to settings.yaml (default: config/settings.yaml).",
    )
    args = parser.parse_args()

    settings = load_settings(args.settings)
    dry_run = args.dry_run or settings.run.dry_run

    if dry_run:
        log.info("=== DRY RUN MODE: no emails will be sent, Notion not written ===")

    try:
        now = datetime.now(UTC)
        summary = run(settings, dry_run=dry_run, force=getattr(args, "force", False))
        if not dry_run:
            _alert_if_needed(summary, settings, now)
            _heartbeat(summary)
    except Exception:
        tb = traceback.format_exc()
        log.critical("Unhandled exception:\n%s", tb)
        send_maintainer_alert("Unhandled exception", tb)
        sys.exit(1)


if __name__ == "__main__":
    main()
