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

import httpx

from .alert_throttle import AlertThrottle
from .config import Settings, load_dotenv, load_settings
from .dedup import DedupStore
from .matching import filter_watch_matches
from .models import Deal
from .notify.email import EmailSender, send_maintainer_alert
from .notify.render import DealItem
from .observations import ObservationLog, build_observation
from .scoring import compute_vote_velocity, enrich_deal, is_hot
from .sources.camelcamelcamel import CamelCamelCamelSource
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


def run(settings: Settings, dry_run: bool = False, force: bool = False) -> dict:
    """Execute one full run.  Returns a summary dict (counts only, no PII)."""
    summary: dict = {
        "deals_fetched": 0,
        "hot_deals": 0,
        "watch_matches": 0,
        "notifications_sent": 0,
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

    if not all_deals and not summary["errors"]:
        # Feed returned 0 deals without error — likely a format change.
        msg = "0 deals fetched — possible feed format change."
        log.error(msg)
        summary["errors"].append(msg)

    summary["deals_fetched"] = len(all_deals)

    # Enrich with price/discount signals
    all_deals = [enrich_deal(d) for d in all_deals]

    # Filter expired/out-of-stock (including deals whose expiry timestamp has passed).
    active_deals = [
        d for d in all_deals
        if not d.expired and (d.expiry is None or d.expiry > now)
    ]
    if d := len(all_deals) - len(active_deals):
        log.info("Filtered %d expired deals.", d)

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

    hot_deals: list[Deal] = []
    if not state.is_cold_start():
        for deal in active_deals:
            if not state.should_notify(
                deal,
                settings.cold_start.ignore_deals_older_than_hours,
                deal.key in first_sighting,
                now=now,
            ):
                continue
            if is_hot(deal, snaps_map[deal.key], settings.scoring, active_pairs, now=now):
                hot_deals.append(deal)
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
                now=now,
            )
        )
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
        state.save()
        return summary

    notion = make_notion_client()
    try:
        subscribers = fetch_subscribers(notion, subscribers_db)
    except Exception as exc:
        msg = f"Subscriber fetch failed: {exc}"
        log.error(msg)
        summary["errors"].append(msg)
        state.save()
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
        state.save()
        return summary

    # ------------------------------------------------------------------
    # 6. Match + notify each subscriber
    # ------------------------------------------------------------------
    if _is_quiet_hours(settings, now):
        if force:
            log.info("Quiet hours active but --force set; proceeding with notifications.")
        else:
            log.info("Quiet hours — skipping notifications for this run.")
            state.save()
            return summary

    sender = EmailSender(dry_run=dry_run)

    for sub in subscribers:
        if not sub.active:
            continue

        # Daily caps — hot and watch are independent quotas.
        # "mixed" deals (hot-qualified + watch keyword hit) count against hot cap only.
        hot_daily = dedup.daily_count(sub, now=now, tracks={"hot", "mixed"})
        watch_daily = dedup.daily_count(sub, now=now, tracks={"watch"})
        remaining_hot = sub.max_alerts_per_day - hot_daily
        remaining_watch = sub.max_watch_alerts_per_day - watch_daily

        if remaining_hot <= 0 and remaining_watch <= 0:
            log.info(
                "Subscriber %s at daily caps (hot=%d/%d watch=%d/%d); skipping.",
                sub.ref, hot_daily, sub.max_alerts_per_day,
                watch_daily, sub.max_watch_alerts_per_day,
            )
            continue

        hot_items: list[DealItem] = []
        watch_items: list[DealItem] = []
        notified_keys: set[str] = set()

        # Hot track
        if sub.subscribe_hot and hot_deals and remaining_hot > 0:
            for deal in hot_deals:
                if len(hot_items) >= remaining_hot:
                    log.info("[%s] hot skip %s: daily cap", sub.ref, deal.key)
                    break
                if dedup.already_sent(deal, sub):
                    log.info("[%s] hot skip %s: already sent", sub.ref, deal.key)
                    continue
                vel, _ = compute_vote_velocity(
                    snaps_map.get(deal.key, []), settings.scoring.window_minutes, now
                )
                if not _passes_quality_gate(deal, settings.scoring.hot, vote_velocity=vel):
                    log.info(
                        "[%s] hot skip %s: quality gate (votes=%d disc=%s vel=%.1f)",
                        sub.ref, deal.key, deal.votes_pos, deal.discount_percent, vel,
                    )
                    continue
                hot_items.append(DealItem(deal, track="hot", reason=_hot_reason(deal)))
                notified_keys.add(deal.key)

        # Watch track (independent cap — does not share quota with hot)
        watch_hits = filter_watch_matches(active_deals, sub, settings.scoring.watch, now=now)
        for deal, reason in watch_hits:
            if deal.key in notified_keys:
                # Already queued via hot — annotate as mixed (no watch cap cost)
                for item in hot_items:
                    if item.deal.key == deal.key:
                        item.track = "mixed"
                        item.reason = f"{item.reason} · {reason}"
                continue
            if len(watch_items) >= remaining_watch:
                break
            if not state.should_notify(
                deal,
                settings.cold_start.ignore_deals_older_than_hours,
                deal.key in first_sighting,
                now=now,
            ):
                continue
            if dedup.already_sent(deal, sub):
                continue
            watch_items.append(DealItem(deal, track="watch", reason=reason))
            notified_keys.add(deal.key)

        items = hot_items + watch_items
        if not items:
            continue

        summary["watch_matches"] += len(watch_items)

        # Send
        ok = sender.send_digest(sub, items)
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
    # 7. Save state
    # ------------------------------------------------------------------
    state.save()

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
    parts = [f"▲ {deal.votes_pos} votes"]
    if deal.discount_percent:
        parts.append(f"{deal.discount_percent:.0f}% off")
    return " · ".join(parts)


def _is_quiet_hours(settings: Settings, now: datetime) -> bool:
    """Return True if current local time falls within the configured quiet window.

    Handles wrap-around midnight (e.g. 22:00–07:00).
    Returns False when quiet hours are not configured.
    """
    start_str = settings.run.quiet_hours_start
    end_str = settings.run.quiet_hours_end
    if not start_str or not end_str:
        return False
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(settings.run.timezone)
    local = now.astimezone(tz)
    current = local.hour * 60 + local.minute
    sh, sm = map(int, start_str.split(":"))
    eh, em = map(int, end_str.split(":"))
    start = sh * 60 + sm
    end = eh * 60 + em
    if start > end:  # window wraps midnight, e.g. 22:00–07:00
        return current >= start or current < end
    return start <= current < end


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
        _alert_if_needed(summary, settings, now)
        if not dry_run:
            _heartbeat(summary)
    except Exception:
        tb = traceback.format_exc()
        log.critical("Unhandled exception:\n%s", tb)
        send_maintainer_alert("Unhandled exception", tb)
        sys.exit(1)


if __name__ == "__main__":
    main()
