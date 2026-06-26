"""Raw corpus persistence: one JSON file per captured post, committed to the repo.

Layout::

    data/strategies/raw/<source>/<post_id>.json

A post is re-written only when its content hash changes (edited thread), so git
diffs stay meaningful and unchanged threads don't churn. ``save`` returns whether
the post was new or updated, which ``collect`` uses to build the day's digest.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .models import CapturedPost

log = logging.getLogger(__name__)


class PostStore:
    def __init__(self, raw_dir: Path) -> None:
        self.raw_dir = raw_dir

    def _path(self, post: CapturedPost) -> Path:
        return self.raw_dir / post.source / f"{post.post_id}.json"

    def existing_hash(self, post: CapturedPost) -> str | None:
        path = self._path(post)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("content_hash")
        except (OSError, json.JSONDecodeError):
            return None

    def save(self, post: CapturedPost) -> bool:
        """Write the post to disk. Return True if it was new or changed."""
        if self.existing_hash(post) == post.content_hash:
            return False
        path = self._path(post)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = post.model_dump(mode="json")
        payload["content_hash"] = post.content_hash
        payload["key"] = post.key
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True
