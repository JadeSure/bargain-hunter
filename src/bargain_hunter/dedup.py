"""Sent-log dedup + re-alert logic (PRD §5, §10.2).

One-shot batch load: at the start of each run we pull all Sent Log entries
for the last `lookback_days` into memory, then do all dedup checks locally
without further Notion API calls.  After a successful notification send, we
immediately write a Sent Log entry (per-send, not batched at end of run).
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

from notion_client import Client

from .config import DedupConfig
from .models import Deal, Subscriber

log = logging.getLogger(__name__)

_P_DEAL_ID = "Deal ID"
_P_SUBSCRIBER = "Subscriber Email"
_P_CHANNEL = "Channel"
_P_TRACK = "Track"
_P_SENT_AT = "Sent At"
_P_PRICE = "Price"
_P_DISCOUNT = "Discount %"
_P_VOTES_POS = "Votes Pos"
_P_HEAT_BAND = "Heat Band"
_P_REALERT_COUNT = "Re-alert Count"
_P_TRIGGER_SIG = "Trigger Signature"


class SentEntry:
    __slots__ = (
        "deal_key",
        "subscriber_email",
        "channel",
        "track",
        "sent_at",
        "price",
        "discount_pct",
        "votes_pos",
        "heat_band",
        "realert_count",
        "trigger_sig",
    )

    def __init__(  # noqa: PLR0913
        self,
        deal_key: str,
        subscriber_email: str,
        channel: str,
        track: str,
        sent_at: datetime,
        price: float | None,
        discount_pct: float | None,
        votes_pos: int,
        heat_band: int,
        realert_count: int,
        trigger_sig: str,
    ) -> None:
        self.deal_key = deal_key
        self.subscriber_email = subscriber_email
        self.channel = channel
        self.track = track
        self.sent_at = sent_at
        self.price = price
        self.discount_pct = discount_pct
        self.votes_pos = votes_pos
        self.heat_band = heat_band
        self.realert_count = realert_count
        self.trigger_sig = trigger_sig


def _heat_band(votes_pos: int, band_size: int) -> int:
    return votes_pos // band_size


class DedupStore:
    """In-memory Sent Log loaded once per run from Notion."""

    def __init__(self, cfg: DedupConfig) -> None:
        self.cfg = cfg
        # (deal_key, subscriber_email) -> list[SentEntry]
        self._log: dict[tuple[str, str], list[SentEntry]] = {}

    def load(self, notion: Client, db_id: str) -> None:
        """Bulk-load recent Sent Log from Notion (one-shot per run)."""
        cutoff = (datetime.now(UTC) - timedelta(days=self.cfg.lookback_days)).isoformat()
        filter_payload = {
            "property": _P_SENT_AT,
            "date": {"after": cutoff},
        }
        cursor = None
        count = 0
        while True:
            kwargs: dict = {
                "database_id": db_id,
                "filter": filter_payload,
                "page_size": 100,
            }
            if cursor:
                kwargs["start_cursor"] = cursor
            resp = notion.databases.query(**kwargs)
            for page in resp.get("results", []):
                entry = _parse_sent_entry(page.get("properties", {}))
                if entry:
                    key = (entry.deal_key, entry.subscriber_email)
                    self._log.setdefault(key, []).append(entry)
                    count += 1
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
        log.info("Loaded %d Sent Log entries (last %d days).", count, self.cfg.lookback_days)

    def already_sent(self, deal: Deal, subscriber: Subscriber) -> bool:
        """Return True if deal was already sent to this subscriber and no re-alert is due."""
        email = subscriber.email or ""
        entries = self._log.get((deal.key, email), [])
        if not entries:
            return False
        # Check re-alert eligibility
        latest = max(entries, key=lambda e: e.sent_at)
        realert_count = sum(1 for e in entries if e.realert_count > 0)
        if realert_count >= self.cfg.max_realerts_per_deal:
            return True
        # Substantial price drop?
        if deal.price and latest.price:
            drop_pct = (latest.price - deal.price) / latest.price * 100
            if drop_pct >= self.cfg.significant_price_drop_percent:
                return False
        # Vote band jump?
        current_band = _heat_band(deal.votes_pos, self.cfg.heat_band_size_votes)
        return not current_band > latest.heat_band

    def daily_count(self, subscriber: Subscriber, now: datetime | None = None) -> int:
        """Count deals already sent to this subscriber today (AET calendar day)."""
        from zoneinfo import ZoneInfo

        now = now or datetime.now(UTC)
        tz = ZoneInfo("Australia/Sydney")
        today = now.astimezone(tz).date()
        email = subscriber.email or ""
        count = 0
        seen_deals: set[str] = set()
        for (deal_key, sub_email), entries in self._log.items():
            if sub_email != email:
                continue
            for e in entries:
                if e.sent_at.astimezone(tz).date() == today and deal_key not in seen_deals:
                    seen_deals.add(deal_key)
                    count += 1
        return count

    def record_sent(
        self,
        notion: Client,
        db_id: str,
        deal: Deal,
        subscriber: Subscriber,
        channel: str,
        track: str,
        trigger_sig: str,
    ) -> None:
        """Write a Sent Log entry to Notion immediately after sending."""
        email = subscriber.email or ""
        existing = self._log.get((deal.key, email), [])
        realert_count = len(existing)
        now = datetime.now(UTC)
        band = _heat_band(deal.votes_pos, self.cfg.heat_band_size_votes)

        props: dict = {
            _P_DEAL_ID: {"title": [{"text": {"content": deal.key}}]},
            _P_SUBSCRIBER: {"email": email},
            _P_CHANNEL: {"select": {"name": channel}},
            _P_TRACK: {"select": {"name": track}},
            _P_SENT_AT: {"date": {"start": now.isoformat()}},
            _P_VOTES_POS: {"number": deal.votes_pos},
            _P_HEAT_BAND: {"number": band},
            _P_REALERT_COUNT: {"number": realert_count},
            _P_TRIGGER_SIG: {"rich_text": [{"text": {"content": trigger_sig[:2000]}}]},
        }
        if deal.price is not None:
            props[_P_PRICE] = {"number": deal.price}
        if deal.discount_percent is not None:
            props[_P_DISCOUNT] = {"number": deal.discount_percent}

        notion.pages.create(parent={"database_id": db_id}, properties=props)

        # Mirror into local cache to keep daily_count accurate within this run
        entry = SentEntry(
            deal_key=deal.key,
            subscriber_email=email,
            channel=channel,
            track=track,
            sent_at=now,
            price=deal.price,
            discount_pct=deal.discount_percent,
            votes_pos=deal.votes_pos,
            heat_band=band,
            realert_count=realert_count,
            trigger_sig=trigger_sig,
        )
        self._log.setdefault((deal.key, email), []).append(entry)


def _prop_text(props: dict, key: str) -> str:
    prop = props.get(key, {})
    items = prop.get("rich_text") or prop.get("title") or []
    return "".join(t.get("plain_text", "") for t in items).strip()


def _parse_sent_entry(props: dict) -> SentEntry | None:
    try:
        deal_key = _prop_text(props, _P_DEAL_ID)
        email = props.get(_P_SUBSCRIBER, {}).get("email", "") or ""
        channel = (props.get(_P_CHANNEL, {}).get("select") or {}).get("name", "Email")
        track = (props.get(_P_TRACK, {}).get("select") or {}).get("name", "hot")
        sent_at_raw = (props.get(_P_SENT_AT, {}).get("date") or {}).get("start")
        if not deal_key or not email or not sent_at_raw:
            return None
        sent_at = datetime.fromisoformat(sent_at_raw)
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=UTC)
        price_num = props.get(_P_PRICE, {}).get("number")
        discount_num = props.get(_P_DISCOUNT, {}).get("number")
        votes_pos = int(props.get(_P_VOTES_POS, {}).get("number") or 0)
        heat_band = int(props.get(_P_HEAT_BAND, {}).get("number") or 0)
        realert_count = int(props.get(_P_REALERT_COUNT, {}).get("number") or 0)
        trigger_sig = _prop_text(props, _P_TRIGGER_SIG)
        return SentEntry(
            deal_key=deal_key,
            subscriber_email=email,
            channel=channel,
            track=track,
            sent_at=sent_at,
            price=float(price_num) if price_num is not None else None,
            discount_pct=float(discount_num) if discount_num is not None else None,
            votes_pos=votes_pos,
            heat_band=heat_band,
            realert_count=realert_count,
            trigger_sig=trigger_sig,
        )
    except Exception:
        return None


def make_notion_client() -> Client:
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise RuntimeError("NOTION_TOKEN environment variable not set.")
    return Client(auth=token)
