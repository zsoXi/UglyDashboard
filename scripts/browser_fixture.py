"""Repeatable browser-QA fixture for UglyDashboard.

Spawns the REAL application stack (mission_control.engine.Engine +
mission_control.server.Server, the same classes the root launcher
opencode_dashboard.py drives) against an ephemeral state directory and a
synthetic OpenCode SQLite source. Nothing outside the temporary root is
touched; no process is ever killed (dynamic port by default).

Usage (single command, no shell chaining needed):
    python -X utf8 scripts/browser_fixture.py --port 0 --info-file <path>

The info file receives {"url": ..., "owner_token": ...}. The owner token is
a fresh random Store secret; it is never printed or logged, only written to
the given file (chmod 0o600 best-effort). Stdout carries a single READY line
with the URL only.
"""

import argparse
import json
import os
import shutil
import signal
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mission_control.core import now_ms  # noqa: E402
from mission_control.engine import Engine  # noqa: E402
from mission_control.server import Server  # noqa: E402

SESSIONS = [
    # (session_id, project_key, parent_id, title, agent, model, total_tokens)
    ("fx-root", "alpha", None, "Fixture dashboard rebuild", "fx-lead", "fx-flash", 900),
    ("fx-child", "alpha", "fx-root", "Fixture interface worker", "fx-ui", "fx-pro", 640),
    ("fx-fork", "alpha", "fx-root", "Fixture experiment fork", "fx-ui", "fx-flash", 410),
    ("fx-beta", "beta", None, "Fixture docs pass", "fx-docs", "fx-flash", 260),
]


def build_source(root: Path):
    """Create a synthetic OpenCode project tree + SQLite database."""
    src = root / "fixture-src"
    projects = {}
    for key, name in (("alpha", "Fixture Alpha"), ("beta", "Fixture Beta")):
        worktree = src / name
        worktree.mkdir(parents=True, exist_ok=True)
        (worktree / "notes.md").write_text(f"# {name}\n\nSynthetic fixture file.\n", "utf-8")
        (worktree / "task.py").write_text('print("fixture")\n', "utf-8")
        projects[key] = (name, str(worktree))
    (src / "shared").mkdir(exist_ok=True)
    (src / "shared" / "common.md").write_text("# Shared\n", "utf-8")

    db = src / "opencode.db"
    con = sqlite3.connect(db)
    con.executescript(
        """CREATE TABLE project(id TEXT PRIMARY KEY,name TEXT,worktree TEXT);
        CREATE TABLE session(id TEXT PRIMARY KEY,project_id TEXT,parent_id TEXT,
            directory TEXT,title TEXT,time_created INTEGER,time_updated INTEGER);
        CREATE TABLE message(id TEXT PRIMARY KEY,session_id TEXT,time_created INTEGER,data TEXT);
        CREATE TABLE part(id TEXT PRIMARY KEY,session_id TEXT,message_id TEXT,
            time_created INTEGER,data TEXT);"""
    )
    con.execute("INSERT INTO project VALUES(?,?,?)", ("fx-p-alpha", "Fixture Alpha", projects["alpha"][1]))
    con.execute("INSERT INTO project VALUES(?,?,?)", ("fx-p-beta", "Fixture Beta", projects["beta"][1]))
    now = now_ms()
    for i, (sid, key, parent, title, agent, model, total) in enumerate(SESSIONS):
        name, worktree = projects[key]
        con.execute(
            "INSERT INTO session VALUES(?,?,?,?,?,?,?)",
            (
                sid,
                "fx-p-" + key,
                parent,
                worktree,
                title,
                now - 900000 - i * 60000,
                now - 60000 - i * 45000,
            ),
        )
        tokens = {
            "input": total - 60,
            "output": 40,
            "reasoning": 10,
            "cache": {"read": 10, "write": 0},
            "total": total,
        }
        info = {
            "role": "assistant",
            "agent": agent,
            "modelID": model,
            "providerID": "fixture",
            "time": {"created": now - 120000, "completed": now - 61000},
            "tokens": tokens,
            "cost": 0.0,
        }
        con.execute(
            "INSERT INTO message VALUES(?,?,?,?)",
            (sid + "-u", sid, now - 300000, json.dumps({"role": "user", "time": {"created": now - 300000}})),
        )
        con.execute(
            "INSERT INTO message VALUES(?,?,?,?)",
            (sid + "-a", sid, now - 120000, json.dumps(info)),
        )
        con.execute(
            "INSERT INTO part VALUES(?,?,?,?,?)",
            (
                sid + "-text",
                sid,
                sid + "-u",
                now - 300000,
                json.dumps({"type": "text", "text": f"Fixture prompt for {title} (synthetic)."}),
            ),
        )
        con.execute(
            "INSERT INTO part VALUES(?,?,?,?,?)",
            (
                sid + "-usage",
                sid,
                sid + "-a",
                now - 61000,
                json.dumps({"type": "step-finish", "tokens": tokens, "cost": 0.0}),
            ),
        )
    task = {
        "type": "tool",
        "tool": "task",
        "callID": "fx-call-task",
        "state": {
            "status": "completed",
            "input": {"description": "Fixture UI worker"},
            "metadata": {"sessionId": "fx-child"},
            "output": "Done",
        },
    }
    con.execute(
        "INSERT INTO part VALUES(?,?,?,?,?)",
        ("fx-p-task", "fx-root", "fx-root-a", now - 90000, json.dumps(task)),
    )
    edit = {
        "type": "tool",
        "tool": "edit",
        "callID": "fx-edit-1",
        "state": {
            "status": "completed",
            "input": {"filePath": str(Path(projects['alpha'][1]) / "task.py")},
            "output": "Updated",
        },
    }
    con.execute(
        "INSERT INTO part VALUES(?,?,?,?,?)",
        ("fx-p-edit", "fx-child", "fx-child-a", now - 80000, json.dumps(edit)),
    )
    con.commit()
    con.close()
    return str(db), str(src), [projects["alpha"][1], projects["beta"][1]]


def seed_events(engine: Engine):
    now = now_ms()
    items = []
    kinds = ["state", "tool", "state", "tool", "state", "tool"]
    texts = [
        "Fixture worker started dashboard rebuild",
        "edit fixture-src/task.py",
        "Fixture interface worker checkpoint",
        "task Fixture UI worker",
        "Fixture docs pass reviewed",
        "read fixture-src/notes.md",
    ]
    sessions = ["opencode:fx-root", "opencode:fx-child", "opencode:fx-fork", "opencode:fx-beta"]
    for i, (kind, text) in enumerate(zip(kinds, texts)):
        items.append(
            {
                "id": f"fx-ev-{i}",
                "ts": now - (len(kinds) - i) * 90000,
                "session_id": sessions[i % len(sessions)],
                "source": "opencode",
                "kind": kind,
                "project": "Fixture Alpha",
                "text": text,
            }
        )
    for i in range(3):
        items.append(
            {
                "id": f"fx-prompt-{i}",
                "ts": now - (i + 1) * 240000,
                "session_id": sessions[i],
                "source": "opencode",
                "kind": "prompt",
                "project": "Fixture Alpha",
                "text": f"Fixture prompt sample {i + 1} (synthetic).",
            }
        )
    # Pagination batch: pushes the event table past the UI page size (100) so
    # the timeline "Wczytaj więcej" cursor is exercised. ~100 tiny rows keep
    # the fixture small (DS-2 owns the million-event timeout work).
    for i in range(95):
        items.append(
            {
                "id": f"fx-page-{i}",
                "ts": now - 3600000 - i * 60000,
                "session_id": sessions[i % len(sessions)],
                "source": "opencode",
                "kind": "tool",
                "project": "Fixture Alpha",
                "text": f"Fixture pagination marker {i + 1} (synthetic).",
            }
        )
    engine.store.events(items)


def main():
    parser = argparse.ArgumentParser(description="Ephemeral Mission Control fixture for browser QA.")
    parser.add_argument("--port", type=int, default=0, help="Port to bind (0 = OS-assigned, default).")
    parser.add_argument("--info-file", required=True, help="Path for {url, owner_token} JSON.")
    parser.add_argument("--scan-timeout", type=float, default=30.0)
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="mc-browser-fixture-"))
    state_dir = tmp / "state"
    state_dir.mkdir()
    db_path, src_root, project_dirs = build_source(tmp)

    engine = Engine(
        str(state_dir),
        {
            "db_paths": [db_path],
            "codex_homes": [],
            "router_events": [],
            "opencode_urls": [],
            "git_enabled": False,
        },
    )
    cfg = engine.config()
    cfg.update(
        {
            "projects": project_dirs,
            "token_budget": 400,
            "poll_seconds": 60,
        }
    )
    engine.save_config(cfg)
    engine.poll()
    seed_events(engine)
    engine.begin_scan([src_root], 3)
    if engine._scan_thread is not None:
        engine._scan_thread.join(timeout=args.scan_timeout)

    try:
        server = Server(("127.0.0.1", args.port), engine)
    except OSError as exc:
        engine.close()
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"FIXTURE BIND FAILED 127.0.0.1:{args.port} ({exc}); refusing to touch other processes.")
        raise SystemExit(2)

    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}"
    info = {"url": url, "owner_token": engine.control_token}
    info_path = Path(args.info_file)
    info_path.parent.mkdir(parents=True, exist_ok=True)
    info_path.write_text(json.dumps(info), "utf-8")
    try:
        os.chmod(info_path, 0o600)
    except OSError:
        pass

    thread = threading.Thread(target=server.serve_forever, daemon=True, name="fixture-server")
    thread.start()
    print(f"READY url={url}", flush=True)

    stop = threading.Event()

    def cleanup(*_):
        stop.set()

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    try:
        while not stop.wait(0.25):
            pass
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        engine.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
