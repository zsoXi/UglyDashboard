"""Independent OpenCode usage reconciliation on a WAL-safe DB copy.

Purpose (V6 Etap B): prove where the reported OpenCode token difference comes
from, without trusting either dashboard. The script:

  1. copies the live OpenCode SQLite database with the SQLite backup API, so
     the copy includes everything a plain file copy would miss (WAL),
  2. reads that consistent copy directly (stdlib sqlite3 only),
  3. computes uncapped usage sums per session from usage-carrying parts and
     from assistant messages, using the SAME field semantics as the product
     adapter (mission_control.core.oc_usage), plus an emulation of the
     reader's per-session part cap,
  4. runs the real product reader (mission_control.sources.read_opencode) on
     the same copy,
  5. reports totals, per-session deltas (top offenders) and diagnostics.

Privacy: the output contains hashed session ids only. No titles, prompts,
directories, model names or file paths are written. The DB copy lives in a
temporary directory that is removed on exit and is never committed.

Usage:
  python -X utf8 scripts/reconcile_usage.py --db <opencode.db> --output <path>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mission_control.core import (  # noqa: E402
    MAX_OC_PARTS_PER_SESSION,
    MAX_OC_PARTS_TOTAL,
    Diagnostics,
    oc_usage,
    zero_usage,
)
from mission_control.sources import read_opencode  # noqa: E402

FIELDS = ("input", "output", "reasoning", "cache_read", "cache_write", "total")


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def backup_copy(src: Path, dest: Path) -> None:
    """Copy a live SQLite database consistently, WAL included."""
    if not src.exists():
        raise SystemExit(f"source database not found: {src.name}")
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def add_usage(acc, usage):
    for key in FIELDS:
        acc[key] += usage.get(key, 0)


def stream_json_rows(con: sqlite3.Connection, query: str):
    cur = con.execute(query)
    while True:
        row = cur.fetchone()
        if row is None:
            break
        yield row


def parse_payload(raw):
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def collect_usage(con: sqlite3.Connection, diag: Diagnostics):
    """Uncapped per-session usage from parts and from assistant messages.

    ``uncapped`` sums every usage-carrying part. ``window`` keeps, per
    session, the newest ``MAX_OC_PARTS_PER_SESSION`` part slots (a slot is a
    usage dict for step-finish parts, otherwise None) so the reader's
    per-session part cap can be emulated exactly: the cap counts ALL parts,
    not only the usage-carrying ones.
    """
    uncapped = {}
    window = {}
    messages = {}
    part_counts = {}
    usage_events = {}
    for row in stream_json_rows(con, "SELECT session_id, data FROM part ORDER BY rowid"):
        sid = row[0]
        if sid is None:
            continue
        part_counts[sid] = part_counts.get(sid, 0) + 1
        usage = None
        payload = parse_payload(row[1])
        if payload is None:
            diag.record("reconcile.part_payload", None, "unparsable")
        elif payload.get("type") == "step-finish" and payload.get("tokens"):
            usage = oc_usage(payload["tokens"], diag)
            add_usage(uncapped.setdefault(sid, zero_usage()), usage)
            usage_events[sid] = usage_events.get(sid, 0) + 1
        window.setdefault(sid, deque(maxlen=MAX_OC_PARTS_PER_SESSION)).append(usage)
    for row in stream_json_rows(con, "SELECT session_id, data FROM message"):
        sid = row[0]
        if sid is None:
            continue
        payload = parse_payload(row[1])
        if payload is None or payload.get("role") != "assistant" or not payload.get("tokens"):
            continue
        add_usage(messages.setdefault(sid, zero_usage()), oc_usage(payload["tokens"], diag))
    return uncapped, window, messages, part_counts, usage_events


def window_usage(entries) -> dict:
    """Sum the usage found in the newest-N-parts window."""
    acc = zero_usage()
    for usage in entries or ():
        if usage is not None:
            add_usage(acc, usage)
    return acc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", required=True, help="Path to the OpenCode SQLite database.")
    parser.add_argument("--limit", type=int, default=1000, help="Product history limit.")
    parser.add_argument("--output", default="", help="Optional sanitized JSON output path.")
    parser.add_argument("--top", type=int, default=10, help="How many sessions to list.")
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="mc-reconcile-"))
    copy = tmp / "opencode-copy.db"
    try:
        backup_copy(Path(args.db), copy)
        diag = Diagnostics()
        con = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
        try:
            parts_uncapped, part_window, messages, part_counts, usage_events = collect_usage(
                con, diag
            )
        finally:
            con.close()

        rows, _dirs, coverage = read_opencode(str(copy), args.limit)
        adapter = {}
        for session in rows:
            adapter[session["native_id"]] = dict(session["usage"])

        totals = {
            "uncapped_parts": zero_usage(),
            "capped_parts_emulation": zero_usage(),
            "message_level": zero_usage(),
            "adapter": zero_usage(),
        }
        per_session = []
        all_ids = set(parts_uncapped) | set(part_window) | set(messages) | set(adapter)
        for sid in all_ids:
            uncapped = parts_uncapped.get(sid, zero_usage())
            capped = window_usage(part_window.get(sid))
            message = messages.get(sid, zero_usage())
            adapter_usage = adapter.get(sid, zero_usage())
            for name, usage in (
                ("uncapped_parts", uncapped),
                ("capped_parts_emulation", capped),
                ("message_level", message),
                ("adapter", adapter_usage),
            ):
                add_usage(totals[name], usage)
            per_session.append(
                {
                    "session": short_hash(sid),
                    "parts": part_counts.get(sid, 0),
                    "parts_window": min(part_counts.get(sid, 0), MAX_OC_PARTS_PER_SESSION),
                    "usage_events": usage_events.get(sid, 0),
                    "uncapped_total": uncapped["total"],
                    "capped_total": capped["total"],
                    "message_total": message["total"],
                    "adapter_total": adapter_usage["total"],
                    "delta_uncapped_minus_adapter": uncapped["total"] - adapter_usage["total"],
                }
            )
        per_session.sort(key=lambda item: item["delta_uncapped_minus_adapter"], reverse=True)

        result = {
            "source": {
                "database": "opencode.db (consistent copy)",
                "sessions": len(all_ids),
                "parts_total": sum(part_counts.values()),
                "usage_events_total": sum(usage_events.values()),
            },
            "product_reader_coverage": {
                key: coverage.get(key)
                for key in (
                    "total_sessions",
                    "loaded_sessions",
                    "parts_loaded",
                    "truncated_sessions",
                    "deadline_exceeded",
                    "truncated",
                )
            },
            "limits": {
                "max_oc_parts_per_session": MAX_OC_PARTS_PER_SESSION,
                "max_oc_parts_total": MAX_OC_PARTS_TOTAL,
            },
            "totals": totals,
            "delta": {
                "uncapped_minus_adapter": totals["uncapped_parts"]["total"]
                - totals["adapter"]["total"],
                "capped_minus_adapter": totals["capped_parts_emulation"]["total"]
                - totals["adapter"]["total"],
                "uncapped_minus_message": totals["uncapped_parts"]["total"]
                - totals["message_level"]["total"],
            },
            "top_sessions": per_session[: args.top],
            "diagnostics": diag.snapshot(),
            "field_semantics": (
                "Components use the product adapter semantics (mission_control.core.oc_usage); "
                "OpenCode components are treated as disjoint, and an explicit provider total "
                "is preserved when present. The capped emulation keeps the newest "
                "MAX_OC_PARTS_PER_SESSION parts per session, counting every part row."
            ),
        }
        payload = json.dumps(result, ensure_ascii=True, indent=2)
        print(payload)
        if args.output:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(payload + "\n", encoding="utf-8")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
