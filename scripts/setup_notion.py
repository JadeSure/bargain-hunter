"""Create the Subscribers and Sent Log databases in Notion.

Usage:
  python scripts/setup_notion.py

Requires:
  NOTION_TOKEN          — integration token with "Insert content" capability
  NOTION_PARENT_PAGE_ID — ID of the Notion page to create the DBs under
                          (the page must be shared with your integration)

On success, prints the two DB IDs.  Copy them into GitHub Secrets:
  NOTION_SUBSCRIBERS_DB_ID
  NOTION_SENT_LOG_DB_ID
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

# Allow running the script directly without `pip install -e .`
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from bargain_hunter.config import load_dotenv

load_dotenv()

NOTION_VERSION = "2022-06-28"
BASE = "https://api.notion.com/v1"


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        print(f"ERROR: {name} is not set.", file=sys.stderr)
        sys.exit(1)
    return val


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Subscribers DB schema  (PRD §7)
# ---------------------------------------------------------------------------

SUBSCRIBERS_TITLE = "Bargain Hunter — Subscribers"

SUBSCRIBERS_PROPS: dict = {
    "Name": {"title": {}},
    "Email": {"email": {}},
    "Telegram Chat ID": {"rich_text": {}},
    "Active": {"checkbox": {}},
    "Channels": {
        "multi_select": {
            "options": [
                {"name": "Email", "color": "blue"},
                {"name": "Telegram", "color": "green"},
            ]
        }
    },
    "Subscribe Hot Deals": {"checkbox": {}},
    "Watch Keywords": {"rich_text": {}},
    "Min Discount %": {"number": {"format": "number"}},
    "Categories": {
        "multi_select": {
            "options": [
                {"name": "Computing", "color": "gray"},
                {"name": "Gaming", "color": "purple"},
                {"name": "Home & Garden", "color": "yellow"},
                {"name": "Automotive", "color": "orange"},
                {"name": "Travel", "color": "pink"},
                {"name": "Clothing", "color": "red"},
                {"name": "Health & Beauty", "color": "green"},
            ]
        }
    },
    "Max Alerts/Day": {"number": {"format": "number"}},
    "Quiet Hours": {"rich_text": {}},
}

# ---------------------------------------------------------------------------
# Sent Log DB schema  (PRD §7)
# ---------------------------------------------------------------------------

SENT_LOG_TITLE = "Bargain Hunter — Sent Log"

SENT_LOG_PROPS: dict = {
    "Deal ID": {"title": {}},
    "Subscriber Email": {"email": {}},
    "Channel": {
        "select": {
            "options": [
                {"name": "Email", "color": "blue"},
                {"name": "Telegram", "color": "green"},
            ]
        }
    },
    "Track": {
        "select": {
            "options": [
                {"name": "hot", "color": "orange"},
                {"name": "watch", "color": "blue"},
                {"name": "mixed", "color": "purple"},
            ]
        }
    },
    "Sent At": {"date": {}},
    "Price": {"number": {"format": "dollar"}},
    "Discount %": {"number": {"format": "number"}},
    "Votes Pos": {"number": {"format": "number"}},
    "Heat Band": {"number": {"format": "number"}},
    "Re-alert Count": {"number": {"format": "number"}},
    "Trigger Signature": {"rich_text": {}},
}

# ---------------------------------------------------------------------------
# Feedback DB schema  (labels for calibration: 👍/👎 from customers + manual)
# ---------------------------------------------------------------------------

FEEDBACK_TITLE = "Bargain Hunter — Feedback"

FEEDBACK_PROPS: dict = {
    "Deal ID": {"title": {}},
    "Deal Title": {"rich_text": {}},
    "Subscriber Email": {"email": {}},
    "Verdict": {
        "select": {
            "options": [
                {"name": "up", "color": "green"},
                {"name": "down", "color": "red"},
            ]
        }
    },
    "At": {"date": {}},
    "Source": {
        "select": {
            "options": [
                {"name": "customer", "color": "blue"},
                {"name": "manual", "color": "gray"},
            ]
        }
    },
    # Filled in by you (or derived from Verdict) — the calibration label.
    "Label": {
        "select": {
            "options": [
                {"name": "Good", "color": "green"},
                {"name": "Meh", "color": "yellow"},
                {"name": "Bad", "color": "red"},
            ]
        }
    },
}


def create_db(token: str, parent_page_id: str, title: str, props: dict) -> str:
    r = httpx.post(
        f"{BASE}/databases",
        headers=_headers(token),
        json={
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": props,
        },
    )
    if r.status_code != 200:
        print(f"ERROR creating '{title}': {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    return r.json()["id"].replace("-", "")


def main() -> None:
    token = _require_env("NOTION_TOKEN")
    parent_page_id = _require_env("NOTION_PARENT_PAGE_ID")

    print("Creating Subscribers database...")
    subs_id = create_db(token, parent_page_id, SUBSCRIBERS_TITLE, SUBSCRIBERS_PROPS)
    print(f"  ✓ NOTION_SUBSCRIBERS_DB_ID={subs_id}")

    print("Creating Sent Log database...")
    log_id = create_db(token, parent_page_id, SENT_LOG_TITLE, SENT_LOG_PROPS)
    print(f"  ✓ NOTION_SENT_LOG_DB_ID={log_id}")

    print("Creating Feedback database...")
    feedback_id = create_db(token, parent_page_id, FEEDBACK_TITLE, FEEDBACK_PROPS)
    print(f"  ✓ NOTION_FEEDBACK_DB_ID={feedback_id}")

    print()
    print("Add these to your GitHub Secrets (Settings → Secrets → Actions):")
    print(f"  NOTION_SUBSCRIBERS_DB_ID = {subs_id}")
    print(f"  NOTION_SENT_LOG_DB_ID    = {log_id}")
    print()
    print("Also update your .env for local testing:")
    print(f"  NOTION_SUBSCRIBERS_DB_ID={subs_id}")
    print(f"  NOTION_SENT_LOG_DB_ID={log_id}")
    print()
    print("The Feedback DB id goes into the Cloudflare worker (not the app):")
    print(f"  feedback-worker/wrangler.jsonc  ->  FEEDBACK_DB_ID = {feedback_id}")


if __name__ == "__main__":
    main()
