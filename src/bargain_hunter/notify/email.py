"""SMTP email delivery (v1: Gmail app password; pluggable for Resend later).

Sends one HTML digest per subscriber per run.  Each send is immediately followed
by a Sent Log write (handled by the caller via dedup.DedupStore.record_sent).
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..models import Subscriber
from .render import DealItem, render_email

log = logging.getLogger(__name__)


class SMTPConfig:
    def __init__(self) -> None:
        self.host: str = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        self.port: int = int(os.environ.get("SMTP_PORT", "587"))
        self.username: str = os.environ.get("SMTP_USERNAME", "")
        self.password: str = os.environ.get("SMTP_PASSWORD", "")
        self.from_addr: str = os.environ.get("EMAIL_FROM", self.username)

    def validate(self) -> None:
        missing = [
            k
            for k, v in [
                ("SMTP_USERNAME", self.username),
                ("SMTP_PASSWORD", self.password),
            ]
            if not v
        ]
        if missing:
            raise RuntimeError(f"Missing SMTP env vars: {', '.join(missing)}")


class EmailSender:
    def __init__(self, cfg: SMTPConfig | None = None, dry_run: bool = False) -> None:
        self.cfg = cfg or SMTPConfig()
        self.dry_run = dry_run

    def send_digest(
        self,
        subscriber: Subscriber,
        items: list[DealItem],
        subject: str | None = None,
    ) -> bool:
        """Render and send a deal digest.  Returns True on success."""
        if not subscriber.email:
            log.warning("Subscriber %s has no email; skipping.", subscriber.ref)
            return False

        html = render_email(subscriber, items)
        subject = subject or _build_subject(items)

        if self.dry_run:
            log.info(
                "[DRY RUN] Would email %s (%d deals): %s",
                subscriber.ref,
                len(items),
                subject,
            )
            return True

        try:
            self.cfg.validate()
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.cfg.from_addr
            msg["To"] = subscriber.email
            msg.attach(MIMEText(html, "html", "utf-8"))

            with smtplib.SMTP(self.cfg.host, self.cfg.port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.login(self.cfg.username, self.cfg.password)
                server.sendmail(self.cfg.from_addr, [subscriber.email], msg.as_string())

            log.info("Emailed %s: %d deals.", subscriber.ref, len(items))
            return True
        except Exception as exc:
            log.error("Failed to email %s: %s", subscriber.ref, exc)
            return False


def send_maintainer_alert(subject: str, body: str) -> None:
    """Send a plain-text failure / heartbeat alert to the maintainer."""
    maintainer = os.environ.get("MAINTAINER_EMAIL")
    if not maintainer:
        log.warning("MAINTAINER_EMAIL not set — cannot send alert: %s", subject)
        return
    cfg = SMTPConfig()
    try:
        cfg.validate()
        msg = MIMEMultipart()
        msg["Subject"] = f"[Bargain Hunter] {subject}"
        msg["From"] = cfg.from_addr
        msg["To"] = maintainer
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP(cfg.host, cfg.port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg.username, cfg.password)
            server.sendmail(cfg.from_addr, [maintainer], msg.as_string())
        log.info("Maintainer alert sent: %s", subject)
    except Exception as exc:
        log.error("Could not send maintainer alert (%s): %s", subject, exc)


def _build_subject(items: list[DealItem]) -> str:
    n = len(items)
    if n == 1:
        title = items[0].deal.title
        return f"[Bargain Hunter] {title[:60]}"
    return f"[Bargain Hunter] {n} deals for you"
