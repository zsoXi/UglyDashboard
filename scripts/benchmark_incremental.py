"""Incremental-aggregation benchmark for V6 (Etap C evidence).

Generates a TEMPORARY synthetic OpenCode SQLite fixture and drives the REAL
Engine in repeated poll cycles until aggregate coverage is complete. The
expected token sum is computed by the GENERATOR (an independent arithmetic
formula), never by calling the production usage helpers, so a bug in the
reader cannot make the expectation agree with itself.

Measured and reported per fixture size:
  * metadata availability - sessions visible after the first cycle;
  * full-coverage time and number of cycles;
  * sessions/events processed and the expected token sum;
  * overview (Engine.view) latency while the import is still running;
  * analytics cold and warm latency;
  * memory (tracemalloc peak; Windows working set via psapi) with the
    measurement method stated explicitly;
  * restart mid-import (fresh Engine on the same state dir continues without
    loss or double counting) and restart after completion (sums unchanged).

Only synthetic data in a temporary directory is used. No user database, log,
secret or home path is read or written. Paths in the report are sanitized.

Usage:
  python -X utf8 scripts/benchmark_incremental.py
  python -X utf8 scripts/benchmark_incremental.py --events 1000000
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import shutil
import sqlite3
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mission_control import Engine  # noqa: E402

SCHEMA = """CREATE TABLE project(id TEXT PRIMARY KEY,name TEXT,worktree TEXT);
CREATE TABLE session(id TEXT PRIMARY KEY,project_id TEXT,parent_id TEXT,
  directory TEXT,title TEXT,time_created INTEGER,time_updated INTEGER);
CREATE TABLE message(id TEXT PRIMARY KEY,session_id TEXT,
  time_created INTEGER,data TEXT);
CREATE TABLE part(id TEXT PRIMARY KEY,session_id TEXT,message_id TEXT,
  time_created INTEGER,data TEXT);"""

INDEXES = """CREATE INDEX idx_bench_session_updated ON session(time_updated);
CREATE INDEX idx_bench_message_session ON message(session_id);
CREATE INDEX idx_bench_part_session ON part(session_id);"""


def part_total(session_index: int, part_index: int) -> int:
    """Deterministic per-part total owned by the GENERATOR.

    Independent of mission_control.core.oc_usage: a plain arithmetic rule so
    the expected sum is an external ground truth.
    """
    return (session_index * 7 + part_index * 13) % 251 + 1


def build_fixture(db_path: Path, sessions: int, parts_per_session: int) -> dict:
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    con.execute(
        "INSERT INTO project VALUES(?,?,?)",
        ("p0", "bench-project", "bench-worktree"),
    )
    base = 1_700_000_000_000
    expected = 0
    messages: list[tuple] = []
    parts: list[tuple] = []
    for i in range(sessions):
        sid = "inc-s%05d" % i
        created = base + i * 1000
        con.execute(
            "INSERT INTO session VALUES(?,?,?,?,?,?,?)",
            (sid, "p0", None, "bench-worktree", "bench session %d" % i, created, created + 500),
        )
        messages.append(
            (
                sid + "-u",
                sid,
                created,
                json.dumps({"role": "user", "time": {"created": created}}),
            )
        )
        messages.append(
            (
                sid + "-a",
                sid,
                created + 100,
                json.dumps(
                    {
                        "role": "assistant",
                        "agent": "bench-agent",
                        "modelID": "bench-model",
                        "providerID": "bench",
                        "time": {"created": created + 100, "completed": created + 500},
                        "tokens": {
                            "input": 0,
                            "output": 0,
                            "reasoning": 0,
                            "cache": {"read": 0, "write": 0},
                            "total": 0,
                        },
                        "cost": 0.0,
                    }
                ),
            )
        )
        for j in range(parts_per_session):
            total = part_total(i, j)
            expected += total
            payload = json.dumps(
                {
                    "type": "step-finish",
                    "tokens": {
                        "input": total,
                        "output": 0,
                        "reasoning": 0,
                        "cache": {"read": 0, "write": 0},
                        "total": total,
                    },
                    "cost": 0.0,
                }
            )
            parts.append((sid + "-p%06d" % j, sid, sid + "-a", created + 200 + j, payload))
    con.executemany("INSERT INTO message VALUES(?,?,?,?)", messages)
    for k in range(0, len(parts), 20000):
        con.executemany("INSERT INTO part VALUES(?,?,?,?,?)", parts[k : k + 20000])
    con.executescript(INDEXES)
    con.commit()
    con.close()
    return {
        "sessions": sessions,
        "parts_per_session": parts_per_session,
        "messages": len(messages),
        "parts": len(parts),
        "events": len(messages) + len(parts),
        "expected_total_tokens": expected,
        "db_bytes": db_path.stat().st_size,
    }


def working_set_bytes() -> int | None:
    if os.name != "nt":
        return None

    class _Counters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
        ]

    try:
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        psapi.GetProcessMemoryInfo.restype = ctypes.c_int
        counters = _Counters()
        counters.cb = ctypes.sizeof(_Counters)
        if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return int(counters.WorkingSetSize)
    except Exception:
        return None
    return None


def make_engine(state_dir: Path, db_path: Path) -> Engine:
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
            "history_limit": 1000,
        },
    )


def db_source(engine: Engine) -> dict:
    for src in engine.view().get("sources", []):
        if src.get("kind") == "database":
            return {k: v for k, v in src.items() if k != "location"}
    return {}


def session_token_sum(engine: Engine) -> float:
    return sum(float(s.get("usage", {}).get("total") or 0) for s in engine.sessions.values())


def run_size(label: str, sessions: int, parts_per_session: int, tmp: Path) -> dict:
    db_path = tmp / ("fixture-%s.db" % label)
    generated = build_fixture(db_path, sessions, parts_per_session)
    state_dir = tmp / ("state-%s" % label)
    state_dir.mkdir()
    engine = make_engine(state_dir, db_path)
    cycles = 0
    metadata_ms = None
    first_view_ms = None
    full_seconds = None
    tracemalloc.start()
    try:
        started = time.perf_counter()
        while cycles < 100:
            cycles += 1
            engine.poll()
            if metadata_ms is None:
                metadata_ms = round((time.perf_counter() - started) * 1000.0, 1)
                view_started = time.perf_counter()
                engine.view()
                first_view_ms = round((time.perf_counter() - view_started) * 1000.0, 1)
            src = db_source(engine)
            if src.get("aggregates_complete"):
                full_seconds = round(time.perf_counter() - started, 3)
                break
        source = db_source(engine)
        got = session_token_sum(engine)
        cold_started = time.perf_counter()
        engine.analytics()
        analytics_cold = round(time.perf_counter() - cold_started, 3)
        warm_started = time.perf_counter()
        engine.analytics()
        analytics_warm = round(time.perf_counter() - warm_started, 3)
        _, peak = tracemalloc.get_traced_memory()
        result = {
            "label": label,
            "fixture": generated,
            "cycles_to_full_coverage": cycles,
            "metadata_available_ms": metadata_ms,
            "first_overview_while_importing_ms": first_view_ms,
            "full_coverage_seconds": full_seconds,
            "sessions_visible": len(engine.sessions),
            "source": {
                k: source.get(k)
                for k in (
                    "ok",
                    "aggregates_complete",
                    "aggregate_sessions_complete",
                    "pending_sessions",
                    "details_truncated",
                    "truncated_sessions",
                    "loaded_sessions",
                    "total_sessions",
                    "catching_up",
                )
                if k in source
            },
            "expected_total_tokens": generated["expected_total_tokens"],
            "received_total_tokens": got,
            "sums_match": abs(got - generated["expected_total_tokens"]) < 1e-6,
            "analytics_cold_seconds": analytics_cold,
            "analytics_warm_seconds": analytics_warm,
            "tracemalloc_peak_bytes": int(peak),
            "windows_working_set_bytes": working_set_bytes(),
            "memory_method": "tracemalloc peak = Python allocations (bytes); "
            "Windows working set via GetProcessMemoryInfo (bytes)",
        }
        # Restart after completion: a fresh Engine over the SAME state dir.
        engine.close()
        engine2 = make_engine(state_dir, db_path)
        try:
            engine2.poll()
            after = session_token_sum(engine2)
            result["restart_after_completion_total"] = after
            result["restart_after_completion_unchanged"] = abs(after - got) < 1e-6
        finally:
            engine2.close()
    finally:
        try:
            tracemalloc.stop()
        except Exception:
            pass
        try:
            engine.close()
        except Exception:
            pass
    return result


def run_restart_mid_import(sessions: int, parts_per_session: int, tmp: Path) -> dict:
    db_path = tmp / "fixture-restart.db"
    generated = build_fixture(db_path, sessions, parts_per_session)
    state_dir = tmp / "state-restart"
    state_dir.mkdir()
    engine = make_engine(state_dir, db_path)
    try:
        engine.poll()  # one partial cycle only (budget-bounded)
        src = db_source(engine)
        partial_complete = src.get("aggregates_complete")
        partial_total = session_token_sum(engine)
    finally:
        engine.close()
    engine2 = make_engine(state_dir, db_path)
    cycles = 0
    try:
        while cycles < 100:
            cycles += 1
            engine2.poll()
            if db_source(engine2).get("aggregates_complete"):
                break
        final_total = session_token_sum(engine2)
    finally:
        engine2.close()
    return {
        "first_cycle_complete": partial_complete,
        "first_cycle_total": partial_total,
        "resumed_cycles": cycles,
        "final_total": final_total,
        "expected_total_tokens": generated["expected_total_tokens"],
        "sums_match": abs(final_total - generated["expected_total_tokens"]) < 1e-6,
        "no_double_count": final_total <= generated["expected_total_tokens"] + 1e-6,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="V6 incremental aggregation benchmark")
    parser.add_argument("--sessions", type=int, default=1000)
    parser.add_argument("--parts", type=int, default=0,
                        help="parts per session (0 = derive from --events)")
    parser.add_argument("--events", type=int, default=100000)
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    if args.sessions < 1:
        print("sessions must be >= 1", flush=True)
        return 2
    if args.parts:
        parts_per_session = args.parts
    else:
        parts_per_session = max(1, (args.events - 2 * args.sessions) // args.sessions)
    if parts_per_session < 1:
        print("parts per session must be >= 1", flush=True)
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="mc-inc-bench-"))
    try:
        small = run_size("100k", args.sessions, parts_per_session, tmp)
        large_parts = max(parts_per_session, 1000)
        large = run_size("1m", args.sessions, large_parts, tmp)
        restart = run_restart_mid_import(args.sessions, large_parts, tmp)
        report = {
            "benchmark": "v6-incremental-aggregation",
            "sanitized": True,
            "note": "Synthetic temporary fixture; expected sums come from the "
            "generator's independent arithmetic, never from the production reader.",
            "environment": {
                "python": platform.python_version(),
                "platform": platform.system(),
                "machine": platform.machine(),
            },
            "sizes": {
                "100k": small,
                "1m": large,
            },
            "restart_mid_import": restart,
        }
        print(json.dumps(report, ensure_ascii=True, indent=2), flush=True)
        if args.output:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
