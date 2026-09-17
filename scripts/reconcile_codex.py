"""Read-only Codex rollout-log reconciliation for V6.

Answers a narrow, checkable question: how much token usage do the real local
Codex files contain when counted per *logical session* instead of per file,
and how much of the difference between the two dashboards is explained by
file scope (``~/.codex`` vs ``~/.codex/browser``), duplicate/aliased files,
and cumulative-counter semantics.

Properties:

* source files are opened read-only; nothing is written next to them;
* the report contains only aggregated numbers and hashed session ids -- no
  prompts, no titles, no absolute user paths;
* the delta logic reproduces ``mission_control.core.codex_usage`` and the
  cumulative handling of ``mission_control.sources.codex_apply`` (reset
  detection and out-of-order skipping), so the result is comparable with the
  product adapter.

Usage::

    python -X utf8 scripts/reconcile_codex.py --output docs/benchmarks/codex.json
    python -X utf8 scripts/reconcile_codex.py --home ~/.codex --home ~/.codex/browser
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mission_control.core import (  # noqa: E402
    add_usage,
    codex_usage,
    zero_usage,
)

DEFAULT_HOMES = ("~/.codex", "~/.codex/browser")
MAX_FILES = 20000


def as_obj(value):
    """Return a dict for JSON object payloads, else an empty dict."""
    return value if isinstance(value, dict) else {}


def home_label(path, home):
    """Short, non-identifying label for a home directory."""
    try:
        rel = path.resolve().relative_to(home.resolve())
    except (OSError, ValueError):
        return "home"
    first = rel.parts[0] if rel.parts else "."
    return "home" if first == "." else "home/" + first


def walk_files(home):
    """Yield candidate rollout JSONL files under one Codex home."""
    for sub in ("sessions", "archived_sessions"):
        root = home / sub
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = [d for d in dirnames if not (Path(dirpath) / d).is_symlink()]
            for name in filenames:
                if name.endswith(".jsonl"):
                    p = Path(dirpath) / name
                    if not p.is_symlink():
                        yield p
                    if len(filenames) > MAX_FILES:
                        break


def scan_file(path):
    """Per-file scan: cumulative delta sum, session ids, counters."""
    out = {
        "records": 0,
        "token_records": 0,
        "out_of_order": 0,
        "resets": 0,
        "total": zero_usage(),
        "session_ids": [],
        "first_ts": None,
        "last_ts": None,
        "bytes": 0,
        "sha256": "",
    }
    try:
        data = path.read_bytes()
    except OSError:
        return None
    out["bytes"] = len(data)
    out["sha256"] = hashlib.sha256(data).hexdigest()
    cumulative = zero_usage()
    usage_ts = None
    seen_ids = set()
    text = data.decode("utf-8", "replace")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        out["records"] += 1
        ts = rec.get("timestamp")
        if isinstance(ts, (int, float)):
            out["last_ts"] = ts if out["last_ts"] is None else max(out["last_ts"], ts)
            out["first_ts"] = ts if out["first_ts"] is None else min(out["first_ts"], ts)
        typ = rec.get("type")
        payload = as_obj(rec.get("payload"))
        if typ == "session_meta":
            sid = payload.get("id") or payload.get("session_id")
            if isinstance(sid, str) and sid and sid not in seen_ids:
                seen_ids.add(sid)
                out["session_ids"].append(sid)
            continue
        if typ != "event_msg" or payload.get("type") != "token_count":
            continue
        info = as_obj(payload.get("info"))
        total = as_obj(info.get("total_token_usage"))
        if not total:
            continue
        out["token_records"] += 1
        if usage_ts is not None and isinstance(ts, (int, float)) and ts < usage_ts:
            out["out_of_order"] += 1
            continue
        if isinstance(ts, (int, float)):
            usage_ts = ts
        u = codex_usage(total, None)
        if u["total"] < cumulative["total"]:
            out["resets"] += 1
            delta = u
        else:
            delta = {k: max(0, u[k] - cumulative.get(k, 0)) for k in u}
        add_usage(out["total"], delta)
        cumulative = u
    return out


def fallback_id(path):
    return "file:" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:24]


def short_id(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--home", action="append", default=None, help="Codex home (repeatable)")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    parser.add_argument("--top", type=int, default=12, help="How many sessions to list")
    args = parser.parse_args()

    homes = [Path(os.path.expanduser(h)).resolve() for h in (args.home or DEFAULT_HOMES)]
    started = time.time()

    files = []
    per_home = {}
    for home in homes:
        label = home_label(home, home)
        found = list(walk_files(home))
        per_home[label] = {"files": len(found)}
        for path in found:
            files.append((label, path))

    scans = {}
    per_file_session = {}
    for label, path in files:
        scan = scan_file(path)
        if scan is None:
            continue
        scans[(label, str(path))] = scan
        ids = scan["session_ids"] or [fallback_id(path)]
        per_file_session[(label, str(path))] = ids

    # Logical sessions: a session can legitimately span several files
    # (continuation/rotation). Duplicate CONTENT is reported separately.
    sessions = defaultdict(lambda: {"files": 0, "contents": set(), "max_total": 0.0, "sum_total": 0.0})
    for (label, path), scan in scans.items():
        for sid in per_file_session[(label, path)]:
            entry = sessions[sid]
            entry["files"] += 1
            entry["contents"].add(scan["sha256"])
            entry["sum_total"] += scan["total"]["total"]
            entry["max_total"] = max(entry["max_total"], scan["total"]["total"])

    duplicate_groups = defaultdict(list)
    for (label, path), scan in scans.items():
        duplicate_groups[scan["sha256"]].append((label, path))

    sum_all_files = sum(s["total"]["total"] for s in scans.values())
    sum_session_max = sum(s["max_total"] for s in sessions.values())
    multi_file = [s for s in sessions.values() if s["files"] > 1]
    multi_content = [s for s in sessions.values() if len(s["contents"]) > 1]
    dup_files = sum(len(v) - 1 for v in duplicate_groups.values() if len(v) > 1)

    top = sorted(sessions.items(), key=lambda kv: kv[1]["max_total"], reverse=True)[: args.top]

    result = {
        "reconciliation": "codex-rollout-files",
        "sanitized": True,
        "note": "Read-only scan of local Codex JSONL logs. Only totals and hashed ids.",
        "elapsed_seconds": round(time.time() - started, 3),
        "homes": per_home,
        "totals": {
            "files_scanned": len(scans),
            "unique_logical_sessions": len(sessions),
            "sum_all_files_total": sum_all_files,
            "sum_session_max_total": sum_session_max,
            "duplicate_content_groups": sum(1 for v in duplicate_groups.values() if len(v) > 1),
            "duplicate_files": dup_files,
            "sessions_with_multiple_files": len(multi_file),
            "sessions_with_multiple_contents": len(multi_content),
            "token_records": sum(s["token_records"] for s in scans.values()),
            "out_of_order_skipped": sum(s["out_of_order"] for s in scans.values()),
            "counter_resets": sum(s["resets"] for s in scans.values()),
        },
        "top_sessions": [
            {
                "id": short_id(sid),
                "files": entry["files"],
                "distinct_contents": len(entry["contents"]),
                "max_total": entry["max_total"],
                "sum_total": entry["sum_total"],
            }
            for sid, entry in top
        ],
        "reported_context": {
            "v5_ui_codex_total": 45435355912,
            "v5_ui_note": "V6/v5 engine sum across all Codex homes, 400-file window.",
            "v3_ui_codex_total": 9581676500,
            "v3_ui_note": "Equal to the v3 synthesized router-ledger total (a different dataset), so it is not a file-sum comparison.",
        },
        "method": "Per-file cumulative deltas via mission_control.core.codex_usage with reset detection; "
        "logical sessions grouped by session_meta id (hashed in output); duplicate detection by sha256.",
    }
    text = json.dumps(result, ensure_ascii=True, indent=2)
    print(text)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
