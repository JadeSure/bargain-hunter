"""Add 'Deal Title' rich_text property to the existing Feedback DB.

Run once:
  python scripts/migrate_feedback_db.py

Requires NOTION_TOKEN in environment or .env.
The Feedback DB ID is read from NOTION_FEEDBACK_DB_ID env var, falling back to
the hardcoded value in wrangler.jsonc.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from bargain_hunter.config import load_dotenv

load_dotenv()

NOTION_VERSION = "2022-06-28"
BASE = "https://api.notion.com/v1"

# Fallback to the value in wrangler.jsonc
_WRANGLER_FEEDBACK_DB_ID = "389a2a0bfd0481328e01c06175dae735"


def main() -> None:
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        print("ERROR: NOTION_TOKEN not set.", file=sys.stderr)
        sys.exit(1)

    db_id = os.environ.get("NOTION_FEEDBACK_DB_ID") or _WRANGLER_FEEDBACK_DB_ID
    print(f"Patching Feedback DB {db_id} …")

    r = httpx.patch(
        f"{BASE}/databases/{db_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        json={
            "properties": {
                "Deal Title": {"rich_text": {}},
            }
        },
    )

    if r.status_code == 200:
        print("  ✓ 'Deal Title' property added.")
    else:
        print(f"ERROR {r.status_code}: {r.text}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
