"""Synthetic large-data benchmark for UglyDashboard v5 (MUSE-2 owned).

Generates a TEMPORARY synthetic OpenCode SQLite fixture (>=1000 sessions,
100000 events by default, --events up to 1000000) and times the REAL
Engine/analytics code paths:

  * read_opencode() cold parse of the fixture DB
  * Engine.poll() cold collector cycle (uses the same capped history
    windows as production, so per-session history is never loaded
    unboundedly -- see MAX_OC_PARTS_PER_SESSION / MAX_OC_PARTS_TOTAL)
  * Engine.analytics() cold (first aggregation) and warm (cache hit)

Memory is reported honestly: tracemalloc Python-allocation peak is always
reported in bytes; stdlib ``resource`` is used only conditionally (it does
not exist on Windows); on Windows the process working set is read via
ctypes/psapi when available. The ``memory_method`` field always states
exactly which probe produced each number and its units.

Only synthetic data in a temporary directory is used. No user database,
log, secret or home path is read or written. Paths in the report are
sanitized (basenames only) so no local usernames leak into docs.

Usage:
  python -X utf8 scripts/benchmark.py
  python -X utf8 scripts/benchmark.py --sessions 1000 --events 1000000
  python -X utf8 scripts/benchmark.py --output docs/benchmarks/result.json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sqlite3
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mission_control import Engine, read_opencode  # noqa: E402


def build_fixture(db_path: Path, sessions: int, events: int) -> dict:
    """Create a synthetic opencode.db. Events are spread across sessions so
    no single session carries unbounded history (avg events/session stays
    small even at --events 1000000). Returns fixture stats."""
    project = "bench-project"
    con = sqlite3.connect(db_path)
    con.executescript(
        """CREATE TABLE project(id TEXT PRIMARY KEY,name TEXT,worktree TEXT);
        CREATE TABLE session(id TEXT PRIMARY KEY,project_id TEXT,parent_id TEXT,
          directory TEXT,title TEXT,time_created INTEGER,time_updated INTEGER);
        CREATE TABLE message(id TEXT PRIMARY KEY,session_id TEXT,
          time_created INTEGER,data TEXT);
        CREATE TABLE part(id TEXT PRIMARY KEY,session_id TEXT,message_id TEXT,
          time_created INTEGER,data TEXT);"""
    )
    con.execute("INSERT INTO project VALUES(?,?,?)", ("p0", project, "bench-worktree"))
    # Reserve 2 messages per session; the rest of the event budget is parts.
    parts_total = max(0, events - 2 * sessions)
    base_parts, extra = divmod(parts_total, sessions)
    now = int(time.time() * 1000)
    msg_rows: list[tuple] = []
    part_rows: list[tuple] = []
    ts = now - 90 * 86400000
    for i in range(sessions):
        sid = "bench-s%06d" % i
        created = ts + i * 1000
        con.execute(
            "INSERT INTO session VALUES(?,?,?,?,?,?,?)",
            (sid, "p0", None, "bench-worktree", "bench session %d" % i, created, created + 5000),
        )
        user = json.dumps({"role": "user", "time": {"created": created}})
        info = {
            "role": "assistant",
            "agent": "bench-agent",
            "modelID": "bench-model",
            "providerID": "bench",
            "time": {"created": created + 1000, "completed": created + 5000},
            "tokens": {
                "input": 100,
                "output": 20,
                "reasoning": 5,
                "cache": {"read": 10, "write": 0},
                "total": 135,
            },
            "cost": 0.001,
        }
        msg_rows.append((sid + "-u", sid, created, user))
        msg_rows.append((sid + "-a", sid, created + 1000, json.dumps(info)))
        n_parts = base_parts + (1 if i < extra else 0)
        for j in range(n_parts):
            # Mix step-finish usage parts with tool parts, like real data.
            if j % 4 == 3:
                payload = json.dumps(
                    {
                        "type": "tool",
                        "tool": "read",
                        "callID": "c-%d-%d" % (i, j),
                        "state": {
                            "status": "completed",
                            "input": {"filePath": "bench/file.txt"},
                            "output": "ok",
                        },
                    }
                )
            else:
                payload = json.dumps(
                    {"type": "step-finish", "tokens": info["tokens"], "cost": 0.001}
                )
            part_rows.append(
                ("p-%d-%d" % (i, j), sid, sid + "-a", created + 2000 + j, payload)
            )
    con.executemany("INSERT INTO message VALUES(?,?,?,?)", msg_rows)
    # Batch part inserts so 1M events does not blow up memory/time.
    for k in range(0, len(part_rows), 20000):
        con.executemany(
            "INSERT INTO part VALUES(?,?,?,?,?)", part_rows[k : k + 20000]
        )
    # Indexes mirror a real OpenCode database (keyset paging filters on
    # session_id / time ordering). Without them any large fixture would
    # degenerate into full table scans per session, which is not what
    # production reads look like.
    con.executescript(
        """CREATE INDEX idx_bench_session_updated ON session(time_updated);
        CREATE INDEX idx_bench_message_session ON message(session_id);
        CREATE INDEX idx_bench_part_session ON part(session_id);"""
    )
    con.commit()
    counts = {
        "sessions": sessions,
        "messages": len(msg_rows),
        "parts": len(part_rows),
        "events": len(msg_rows) + len(part_rows),
        "avg_events_per_session": round((len(msg_rows) + len(part_rows)) / sessions, 2),
    }
    con.close()
    return counts


def memory_snapshot(extra_label: str) -> dict:
    """Honest memory report: state exactly which probes ran and their units."""
    out: dict = {"label": extra_label}
    try:
        current, peak = tracemalloc.get_traced_memory()
        out["tracemalloc_current_bytes"] = int(current)
        out["tracemalloc_peak_bytes"] = int(peak)
        out["tracemalloc"] = "active (Python allocations only, bytes)"
    except Exception as exc:  # pragma: no cover - defensive
        out["tracemalloc"] = "unavailable: %s" % exc
    try:
        import resource  # noqa: F401 -- absent on Windows by design

        ru = __import__("resource").getrusage(__import__("resource").RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            out["ru_maxrss_bytes"] = int(ru)
            out["resource"] = "stdlib resource.ru_maxrss, native unit bytes (macOS)"
        else:
            out["ru_maxrss_bytes"] = int(ru) * 1024
            out["resource"] = "stdlib resource.ru_maxrss, native unit KiB, converted to bytes"
    except ImportError:
        out["resource"] = "not available on Windows (no stdlib resource module)"
    except Exception as exc:  # pragma: no cover - defensive
        out["resource"] = "probe failed: %s" % exc
    if os.name == "nt":
        try:
            import ctypes

            class _Counters(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            kernel32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi
            # Default ctypes restype (c_int) truncates 64-bit handles; the
            # pseudo-handle -1 must survive intact, so declare pointer widths.
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            psapi.GetProcessMemoryInfo.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_ulong,
            ]
            psapi.GetProcessMemoryInfo.restype = ctypes.c_int
            proc = kernel32.GetCurrentProcess()
            counters = _Counters()
            counters.cb = ctypes.sizeof(_Counters)
            if psapi.GetProcessMemoryInfo(proc, ctypes.byref(counters), counters.cb):
                out["windows_working_set_bytes"] = int(counters.WorkingSetSize)
                out["windows_peak_working_set_bytes"] = int(counters.PeakWorkingSetSize)
                out["windows"] = "GetProcessMemoryInfo working set, bytes"
            else:
                out["windows"] = "GetProcessMemoryInfo call failed"
        except Exception as exc:  # pragma: no cover - defensive
            out["windows"] = "probe failed: %s" % exc
    else:
        out["windows"] = "not applicable (non-Windows platform)"
    return out


def timed(fn):
    started = time.perf_counter()
    result = fn()
    return result, round(time.perf_counter() - started, 3)


def make_engine(state_dir: Path, db_path: Path, history_limit: int) -> Engine:
    return Engine(
        str(state_dir),
        overrides={
            "db_paths": [str(db_path)],
            "opencode_urls": [],
            "codex_homes": [],
            "router_events": [],
            "projects": [],
            "scan_roots": [],
            "git_enabled": False,
            "history_limit": history_limit,
        },
    )


def db_source_entry(engine: Engine) -> dict:
    for src in engine.snapshot.get("sources", []):
        if src.get("kind") == "database":
            # Sanitized: drop local filesystem paths (may contain usernames).
            return {k: v for k, v in src.items() if k != "location"}
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sessions", type=int, default=1000)
    parser.add_argument("--events", type=int, default=100000)
    parser.add_argument("--history-limit", type=int, default=1000,
                        help="Engine history_limit (sessions loaded, newest first)")
    parser.add_argument("--output", type=str, default="",
                        help="Optional JSON file for the sanitized result")
    parser.add_argument("--keep-db", action="store_true",
                        help="Keep the temp fixture dir for inspection")
    args = parser.parse_args()
    if args.sessions < 1000:
        print("sessions must be >= 1000 for a large-data benchmark", flush=True)
        return 2
    if args.events < args.sessions:
        print("events must be >= sessions", flush=True)
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="mc-bench-"))
    db_path = tmp / "opencode.db"
    state_dir = tmp / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "a").mkdir(exist_ok=True)
    (state_dir / "b").mkdir(exist_ok=True)

    gen_started = time.perf_counter()
    fixture = build_fixture(db_path, args.sessions, args.events)
    fixture["db_bytes"] = db_path.stat().st_size
    fixture_seconds = round(time.perf_counter() - gen_started, 3)

    # Cold parse through the real production reader (reports capped coverage).
    # read_opencode enforces a bounded query guard; if a fixture ever trips
    # it, record the error honestly instead of crashing the benchmark --
    # Engine.poll() itself degrades to ok=False per source in that case.
    try:
        (rows, _dirs, coverage), parse_seconds = timed(
            lambda: read_opencode(str(db_path), args.history_limit)
        )
        del rows
        parse_error = ""
    except Exception as exc:
        coverage = {"error": "%s: %s" % (type(exc).__name__, exc)}
        parse_seconds = None
        parse_error = "%s: %s" % (type(exc).__name__, exc)

    # Phase 1 (untraced): realistic production timings. tracemalloc adds
    # large overhead to allocation-heavy collection, so wall-clock figures
    # come from an untraced cold Engine, exactly as production runs it.
    engine = make_engine(state_dir / "a", db_path, args.history_limit)
    try:
        _, poll_seconds = timed(engine.poll)
        src_entry = db_source_entry(engine)
        src_coverage = {
            k: src_entry.get(k)
            for k in (
                "ok",
                "error",
                "total_sessions",
                "loaded_sessions",
                "parts_loaded",
                "truncated_sessions",
                "truncated",
                "rejected_records",
            )
            if k in src_entry
        }
        sessions_seen = len(engine.sessions)

        analytics_cold, analytics_cold_seconds = timed(lambda: engine.analytics())
        analytics_warm, analytics_warm_seconds = timed(lambda: engine.analytics())
        # Traced analytics-warm (cache-hit copy) gives a memory sample without
        # disturbing the cold timings above.
        tracemalloc.start()
        timed(lambda: engine.analytics())
        warm_mem = memory_snapshot("analytics warm (cache hit)")
        tracemalloc.stop()
        cold_mem = {"note": "not traced separately; cold aggregation peak is "
                            "bounded by the analytics-warm sample plus one "
                            "aggregation pass over in-memory facts"}
    finally:
        engine.close()

    # Phase 2 (traced): peak Python allocations during a cold poll. Tracing
    # overhead can itself trip the bounded query guard; the timing of this
    # run is reported as traced_seconds and the guard outcome is recorded
    # honestly -- it is NOT the production timing (see poll_cold_seconds).
    engine_b = make_engine(state_dir / "b", db_path, args.history_limit)
    try:
        tracemalloc.start()
        _, traced_poll_seconds = timed(engine_b.poll)
        poll_mem = memory_snapshot("cold poll (traced)")
        poll_mem["traced_poll_seconds"] = traced_poll_seconds
        poll_mem["traced_poll_ok"] = db_source_entry(engine_b).get("ok")
        poll_mem["traced_poll_note"] = (
            "tracemalloc slows allocation-heavy collection; traced seconds "
            "overstate production wall time and may trip the query guard."
        )
        tracemalloc.stop()
    finally:
        engine_b.close()

    result = {
        "benchmark": "mission-control-synthetic-large-data",
        "sanitized": True,
        "note": "Synthetic temporary fixture only; no user data touched. "
                "History windows are the production caps; coverage records "
                "any truncation.",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.system(),
            "machine": platform.machine(),
        },
        "config": {
            "sessions": args.sessions,
            "events_requested": args.events,
            "history_limit": args.history_limit,
        },
        "fixture": fixture,
        "fixture_generation_seconds": fixture_seconds,
        "parse_cold_seconds": parse_seconds,
        "parse_error": parse_error,
        "poll_cold_seconds": poll_seconds,
        "analytics_cold_seconds": analytics_cold_seconds,
        "analytics_warm_seconds": analytics_warm_seconds,
        "analytics_sessions": analytics_cold.get("sessions"),
        "analytics_tokens": analytics_cold.get("tokens"),
        "snapshot_sessions": sessions_seen,
        "coverage_direct_reader": coverage,
        "coverage_engine_poll": src_coverage,
        "memory_poll": poll_mem,
        "memory_analytics_cold": cold_mem,
        "memory_analytics_warm": warm_mem,
        "memory_method": "tracemalloc peak = Python allocations in bytes; "
                         "resource.ru_maxrss only where stdlib resource exists "
                         "(Unix; KiB except macOS bytes); Windows working set "
                         "via psapi bytes where available. No method is "
                         "reported where its probe did not run.",
        "cache_effect": "analytics warm is expected faster (OrderedDict cache, "
                        "ANALYTICS_CACHE_MAX=16); cold builds facts, warm is a copy.",
    }
    # Rate is only meaningful when the poll actually loaded sessions.
    if fixture["events"] and poll_seconds and src_coverage.get("ok"):
        result["events_per_second_poll"] = round(fixture["events"] / poll_seconds, 1)
    else:
        result["events_per_second_poll"] = None
    print(json.dumps(result, ensure_ascii=True, indent=2), flush=True)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    if args.keep_db:
        print("fixture kept at: <tmpdir> (%s)" % db_path.name, flush=True)
    else:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
