#!/usr/bin/env python3
"""Validate data/bf2026 JSON. Usage: check.py [--root DIR]  (default: this file's directory)."""

import json
import math
import re
import sys
from datetime import date
from pathlib import Path

CATEGORIES = {"数码电子", "家电厨房", "美妆个护", "户外运动", "保健食品", "礼品", "其他"}
EVENTS = {"黑五季", "Click Frenzy", "Prime Day", "EOFY", "双11", "节礼日", "平日", "其他促销"}
KINDS = {"全场折扣", "品类折扣", "返现加码", "礼品卡折扣", "积分加倍", "会员价"}
KEY_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}(-[0-9]{2})?")
DAY_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

NUM = (int, float)
# field -> (allowed types, nullable)
POINT = {
    "id": (str, False),
    "key": (str, False),
    "item": (str, False),
    "model": (str, True),
    "category": (str, False),
    "retailer": (str, False),
    "date": (str, False),
    "event": (str, False),
    "price": (NUM, False),
    "was_price": (NUM, True),
    "was_suspect": (bool, False),
    "conditions": (str, False),
    "votes": (int, True),
    "history_low": (bool, False),
    "source": (str, False),
    "evidence": (str, False),
    "retrieved_at": (str, False),
    "note": (str, False),
}
PROMO = {
    "id": (str, False),
    "year": (int, False),
    "retailer": (str, False),
    "kind": (str, False),
    "value": (str, False),
    "start": (str, True),
    "end": (str, True),
    "scope": (str, False),
    "conditions": (str, False),
    "votes": (int, True),
    "source": (str, False),
    "evidence": (str, False),
    "retrieved_at": (str, False),
    "note": (str, False),
}

errors: list[str] = []


def err(where: str, msg: str) -> None:
    errors.append(f"{where}: {msg}")


def real_date(s: str) -> bool:
    if not isinstance(s, str) or not DATE_RE.fullmatch(s):
        return False
    try:
        y, m, *d = (int(x) for x in s.split("-"))
        date(y, m, d[0] if d else 1)
    except ValueError:
        return False
    return True


def real_day(s) -> bool:
    return isinstance(s, str) and bool(DAY_RE.fullmatch(s)) and real_date(s)


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        err(path.name, f"cannot read JSON: {e}")
        return None


def check_fields(where: str, row: dict, schema: dict) -> bool:
    missing, extra = schema.keys() - row.keys(), row.keys() - schema.keys()
    if missing:
        err(where, f"missing fields {sorted(missing)}")
    if extra:
        err(where, f"unexpected fields {sorted(extra)}")
    ok = not missing and not extra
    for f, (types, nullable) in schema.items():
        if f not in row:
            continue
        v = row[f]
        if v is None:
            if not nullable:
                err(where, f"{f} must not be null")
                ok = False
        elif isinstance(v, bool) != (types is bool) or not isinstance(v, types):
            err(where, f"{f} has wrong type {type(v).__name__}")
            ok = False
        elif isinstance(v, float) and not math.isfinite(v):
            err(where, f"{f} must be finite")
            ok = False
    return ok


def check_common(where: str, row: dict) -> None:
    if not str(row["source"]).startswith("http"):
        err(where, "source must start with http")
    ev = row["evidence"]
    if len(ev) > 200:
        err(where, "evidence longer than 200 chars")
    if not ev.strip() and not row["id"].startswith("cur-"):
        err(where, "evidence required unless id starts with cur-")
    if not real_day(row["retrieved_at"]):
        err(where, f"retrieved_at not a real YYYY-MM-DD: {row['retrieved_at']!r}")


def check_points(root: Path) -> int:
    ids: set[str] = set()
    n = 0
    for path in sorted((root / "points").glob("*.json")):
        rows = load(path)
        if not isinstance(rows, list):
            if rows is not None:
                err(path.name, "must be a JSON array")
            continue
        for i, row in enumerate(rows):
            where = f"{path.name}[{i}]"
            if not isinstance(row, dict):
                err(where, "must be an object")
                continue
            n += 1
            schema_ok = check_fields(where, row, POINT)
            if isinstance(row.get("id"), str):
                where = f"{path.name}:{row['id']}"
                if row["id"] in ids:
                    err(where, "duplicate id")
                ids.add(row["id"])
            if not schema_ok:
                continue
            check_common(where, row)
            if row["category"] not in CATEGORIES:
                err(where, f"bad category {row['category']!r}")
            if row["event"] not in EVENTS:
                err(where, f"bad event {row['event']!r}")
            if not KEY_RE.fullmatch(row["key"]):
                err(where, f"bad key {row['key']!r}")
            if not real_date(row["date"]):
                err(where, f"date not a real YYYY-MM[-DD]: {row['date']!r}")
            if row["price"] <= 0:
                err(where, "price must be > 0")
            elif row["was_price"] is not None and row["was_price"] <= row["price"]:
                err(where, "was_price must be > price")
    return n


def check_promos(root: Path) -> int:
    ids: set[str] = set()
    n = 0
    for path in sorted((root / "promos").glob("*.json")):
        rows = load(path)
        if not isinstance(rows, list):
            if rows is not None:
                err(path.name, "must be a JSON array")
            continue
        for i, row in enumerate(rows):
            where = f"{path.name}[{i}]"
            if not isinstance(row, dict):
                err(where, "must be an object")
                continue
            n += 1
            schema_ok = check_fields(where, row, PROMO)
            if isinstance(row.get("id"), str):
                where = f"{path.name}:{row['id']}"
                if row["id"] in ids:
                    err(where, "duplicate id")
                ids.add(row["id"])
            if not schema_ok:
                continue
            check_common(where, row)
            if row["kind"] not in KINDS:
                err(where, f"bad kind {row['kind']!r}")
            for f in ("start", "end"):
                if row[f] is not None and not real_day(row[f]):
                    err(where, f"{f} not a real YYYY-MM-DD: {row[f]!r}")
    return n


def check_objects(
    root: Path, name: str, string_fields: tuple[str, ...] = (), int_fields: tuple[str, ...] = ()
) -> None:
    rows = load(root / name)
    if rows is None:
        return
    if not isinstance(rows, list):
        err(name, "must be a JSON array")
        return
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            err(f"{name}[{i}]", "must be an object")
            continue
        for f in string_fields:
            if not isinstance(row.get(f), str):
                err(f"{name}[{i}]", f"{f} must be a string")
        for f in int_fields:
            v = row.get(f)
            if not isinstance(v, int) or isinstance(v, bool):
                err(f"{name}[{i}]", f"{f} must be an integer")


def check_unique(root: Path, name: str, field: str) -> None:
    rows = load(root / name)
    if rows is None:
        return
    if not isinstance(rows, list):
        err(name, "must be a JSON array")
        return
    seen: set[str] = set()
    for i, row in enumerate(rows):
        v = row.get(field) if isinstance(row, dict) else None
        if not isinstance(row, dict):
            err(f"{name}[{i}]", "must be an object")
        elif not isinstance(v, str) or not v:
            err(f"{name}[{i}]", f"{field} must be a non-empty string")
        elif v in seen:
            err(f"{name}[{i}]", f"duplicate {field} {v!r}")
        else:
            seen.add(v)


def main() -> int:
    root = Path(__file__).resolve().parent
    if "--root" in sys.argv:
        i = sys.argv.index("--root")
        if i + 1 >= len(sys.argv):
            print("usage: check.py [--root DIR]", file=sys.stderr)
            return 2
        root = Path(sys.argv[i + 1])
    n_points = check_points(root)
    n_promos = check_promos(root)
    check_unique(root, "watch.json", "key")
    check_unique(root, "calendar.json", "id")
    check_objects(
        root,
        "calendar.json",
        ("id", "event", "start", "end", "date_label", "status", "note", "source"),
    )
    check_objects(
        root, "prep.json", ("phase", "by", "task", "detail", "source"), int_fields=("step",)
    )
    check_objects(root, "facts.json", ("id", "label", "value", "source"))
    check_objects(root, "rules.json", ("id", "topic", "value", "status", "note", "source"))
    if errors:
        print(f"{len(errors)} error(s):")
        for e in errors:
            print(f"  {e}")
        return 1
    print(f"ok: {n_points} points, {n_promos} promos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
