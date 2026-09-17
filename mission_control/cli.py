"""Command line entrypoints, stdio bridge and self-test."""

import argparse
import json
import logging
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.request import Request

from .core import (
    APP,
    LOG,
    MAX_BODY,
    MAX_RESPONSE,
    STATE_DEFAULT,
    VERSION,
    codex_usage,
    is_within,
    make_session,
    now_ms,
    number,
    redact,
    validate_config,
)
from .engine import Engine, normalize_report
from .server import (
    Server,
)
from .sources import (
    LOCAL_HTTP,
    JsonlReader,
    codex_apply,
    local_json,
)


def stdio_bridge(directory):
    """MCP stdio transport proxy. Stdout is JSON-RPC only, never logging."""
    state = Path(directory).expanduser().resolve()
    try:
        runtime = json.loads((state / "runtime.json").read_text("utf-8"))
        port = runtime["port"]
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("Invalid observer port.")
        token = (state / "mcp.token").read_text("utf-8").strip()
        if len(token) < 32:
            raise ValueError("Invalid MCP token.")
    except (OSError, ValueError, KeyError) as ex:
        if sys.stderr:
            print(
                "Start Mission Control before connecting its stdio bridge: " + str(ex),
                file=sys.stderr,
            )
        return 2
    url = f"http://127.0.0.1:{port}/mcp"
    while True:
        raw = sys.stdin.buffer.readline(MAX_BODY + 1)
        if not raw:
            return 0
        if len(raw) > MAX_BODY:
            while raw and not raw.endswith(b"\n"):
                raw = sys.stdin.buffer.readline(MAX_BODY + 1)
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Message too large"},
            }
        else:
            request = None
            try:
                request = json.loads(raw)
                if not isinstance(request, dict):
                    raise ValueError("JSON-RPC object required")
                req = Request(
                    url,
                    data=json.dumps(request, allow_nan=False).encode(),
                    headers={
                        "Authorization": "Bearer " + token,
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                )
                with LOCAL_HTTP.open(req, timeout=20) as res:
                    body = res.read(MAX_RESPONSE + 1)
                    if len(body) > MAX_RESPONSE:
                        raise ValueError("Response too large")
                    if res.status == 202 or not body:
                        continue
                    response = json.loads(body)
            except Exception as ex:
                if isinstance(request, dict) and "id" not in request:
                    continue
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id") if isinstance(request, dict) else None,
                    "error": {
                        "code": -32000 if request else -32700,
                        "message": "Observer bridge: " + redact(ex, 400),
                    },
                }
        sys.stdout.write(json.dumps(response, ensure_ascii=True, allow_nan=False) + "\n")
        sys.stdout.flush()


def cli_report(path, directory):
    state = Path(directory).expanduser().resolve()
    runtime = json.loads((state / "runtime.json").read_text("utf-8"))
    token = (state / "mcp.token").read_text("utf-8").strip()
    if path == "-":
        raw = sys.stdin.buffer.read(MAX_BODY + 1)
    else:
        p = Path(path)
        if p.stat().st_size > MAX_BODY:
            raise ValueError("Report file is larger than 1 MiB.")
        raw = p.read_bytes()
    if len(raw) > MAX_BODY:
        raise ValueError("Report is larger than 1 MiB.")
    event = json.loads(raw)
    response = local_json(
        f"http://127.0.0.1:{int(runtime['port'])}/mcp",
        timeout=10,
        headers={"Authorization": "Bearer " + token},
        body={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "report_event", "arguments": event},
        },
    )
    print(json.dumps(response, indent=2, ensure_ascii=False))
    return 1 if response.get("error") or response.get("result", {}).get("isError") else 0


def builtin_self_test():
    import tempfile
    import unittest

    class Sanity(unittest.TestCase):
        def test_codex_counts_cache_once(self):
            self.assertEqual(
                codex_usage(
                    {
                        "input_tokens": 100,
                        "cached_input_tokens": 70,
                        "output_tokens": 20,
                        "reasoning_output_tokens": 5,
                    }
                )["total"],
                120,
            )

        def test_nonfinite(self):
            self.assertEqual(number(float("nan")), 0)

        def test_windows_paths(self):
            self.assertTrue(is_within(r"D:\Work\Project\a.py", r"d:\work\project"))
            self.assertFalse(is_within("/a/project2/x", "/a/project"))

        def test_no_remote_oc(self):
            with self.assertRaises(ValueError):
                validate_config({"opencode_urls": ["https://example.com"]})

        def test_no_negative_budget(self):
            with self.assertRaises(ValueError):
                validate_config({"token_budget": -1})

        def test_jsonl_partial(self):
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "log.jsonl"
                p.write_bytes(b'{"a":')
                reader = JsonlReader()
                self.assertEqual(reader.read(p), [])
                with p.open("ab") as f:
                    f.write(b"1}\n")
                self.assertEqual(reader.read(p), [{"a": 1}])
                self.assertEqual(reader.read(p), [])

        def test_repeated_cumulative_usage(self):
            s = make_session("codex", "test")
            r = {
                "timestamp": "2026-09-16T10:00:00Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {"total_token_usage": {"input_tokens": 100, "output_tokens": 20}},
                },
            }
            codex_apply(s, [r, r])
            self.assertEqual(s["usage"]["total"], 120)

        def test_redaction(self):
            self.assertNotIn("1234567890123456", redact("api_key=1234567890123456"))

        def test_report_self_parent(self):
            with self.assertRaises(ValueError):
                normalize_report(
                    {"event_id": "e", "session_id": "x", "parent_id": "x", "source": "manual"}
                )

        def test_parent_is_not_worker(self):
            s = make_session("opencode", "s")
            self.assertEqual(s["relationship"], "root")

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Sanity)
    )
    return 0 if result.wasSuccessful() else 1


def rotate_owner_token(directory):
    """Rotate only the owner credential in a state dir (no server is started)."""
    from .store import Store

    with Store(directory) as store:
        store.rotate_secret("owner.token")
        location = str(store.directory)
    print(
        "Owner token rotated in "
        + location
        + ". The previous token stops working once a dashboard is restarted; "
        "start it with --open to receive the new one. The database, "
        "configuration, mcp.token and pairing.key were not modified."
    )
    return 0


def _observer_running(state):
    """True only when a healthy observer still answers on the recorded port."""
    try:
        runtime = json.loads((state / "runtime.json").read_text("utf-8"))
        port = int(runtime["port"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    try:
        health = local_json(f"http://127.0.0.1:{port}/health", timeout=1)
    except Exception:
        return False
    return health.get("application") == "opencode-mission-control"


def migrate_state(directory):
    """Migrate only the private observer state directory and exit.

    Never touches OpenCode or Codex source databases and never rotates a
    credential. A running observer is refused because it holds the state open.
    """
    from .migration import SCHEMA_VERSION, MigrationError
    from .store import Store

    state = Path(directory).expanduser().resolve()
    if _observer_running(state):
        print(
            "An observer instance is still answering on the recorded port. "
            "Stop it before migrating its state directory."
        )
        return 2
    try:
        with Store(directory) as store:
            report = store.migration
    except MigrationError as ex:
        print("Migration refused: " + str(ex))
        return 1
    if report.get("migrated"):
        print(
            f"Observer state migrated to schema v{report['version']} "
            f"(was v{report['from_version']}). "
            f"Backup: {report['backup'] or 'none needed (no existing rows)'}. "
            "Database, settings and credentials were preserved; usage aggregates "
            "are rebuilt incrementally by the next reads."
        )
    else:
        print(f"Observer state is already at schema v{SCHEMA_VERSION}. Nothing to do.")
    return 0


def _reusable_instance(port, token):
    """True only for a healthy Mission Control app that accepts our owner token."""
    try:
        health = local_json(f"http://127.0.0.1:{port}/health", timeout=1)
        if health.get("application") != "opencode-mission-control":
            return False
        local_json(
            f"http://127.0.0.1:{port}/api/overview",
            timeout=2,
            headers={"Authorization": "Bearer " + token},
        )
        return True
    except Exception:
        return False


def _serves_shell(port):
    """A reusable instance must actually render the dashboard, not just /health."""
    try:
        with LOCAL_HTTP.open(Request(f"http://127.0.0.1:{port}/"), timeout=2) as res:
            ctype = (res.headers.get("Content-Type") or "").lower()
            head = res.read(4096)
            status = res.status
        return status == 200 and "text/html" in ctype and b"<html" in head.lower()
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description=APP + " — local observer, single Python file, no packages required."
    )
    parser.add_argument(
        "db", nargs="?", help="Optional OpenCode SQLite path (old CLI compatibility)."
    )
    parser.add_argument(
        "--db",
        dest="dbs",
        action="append",
        help="Read an OpenCode DB; repeat for multiple sources.",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--state-dir", default=os.environ.get("MISSION_CONTROL_HOME", str(STATE_DEFAULT))
    )
    parser.add_argument(
        "--opencode-url",
        action="append",
        help="URL of an existing loopback OpenCode server. Does not start another server.",
    )
    parser.add_argument(
        "--codex-home",
        action="append",
        help="Codex home containing sessions and/or archived_sessions.",
    )
    parser.add_argument(
        "--router-events", action="append", help="Optional router usage-events.jsonl ledger."
    )
    parser.add_argument(
        "--scan-root",
        action="append",
        help="Default folder in the opt-in scanner; no automatic recursive scan.",
    )
    parser.add_argument(
        "--open", action="store_true", help="Open the authenticated browser dashboard."
    )
    parser.add_argument("--no-open", action="store_true", help="Do not launch a browser.")
    parser.add_argument(
        "--quiet", action="store_true", help="Do not write console status messages."
    )
    parser.add_argument(
        "--idle-timeout",
        type=int,
        default=0,
        help="Optional shutdown after N seconds without requests. Default 0 keeps observer running.",
    )
    parser.add_argument(
        "--dev-web",
        action="store_true",
        help="Serve the unbuilt web/ sources instead of the production dist bundle "
        "(development only).",
    )
    parser.add_argument(
        "--mcp-stdio",
        action="store_true",
        help="Bridge stdio MCP to an already-running dashboard. Stdout is JSON-RPC only.",
    )
    parser.add_argument(
        "--report-event",
        metavar="JSON_FILE",
        help="Send an explicit report using MCP. Reporting must be enabled; use - for stdin.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in offline sanity tests without reading user data.",
    )
    parser.add_argument(
        "--rotate-owner-token",
        action="store_true",
        help="Rotate only the owner token in the state dir and exit. The database, "
        "configuration, mcp.token and pairing.key are preserved.",
    )
    parser.add_argument(
        "--migrate-state",
        action="store_true",
        help="Migrate the observer state directory to the current schema and exit. "
        "Never touches OpenCode or Codex source databases.",
    )
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args()
    if args.self_test:
        return builtin_self_test()
    if args.rotate_owner_token:
        return rotate_owner_token(args.state_dir)
    if args.migrate_state:
        return migrate_state(args.state_dir)
    if args.mcp_stdio:
        return stdio_bridge(args.state_dir)
    if args.report_event:
        return cli_report(args.report_event, args.state_dir)
    if not 1 <= args.port <= 65535 or args.idle_timeout < 0:
        parser.error("Invalid port or idle timeout.")
    overrides = {}
    if args.db or args.dbs:
        overrides["db_paths"] = ([args.db] if args.db else []) + (args.dbs or [])
    for argument, key in [
        ("opencode_url", "opencode_urls"),
        ("codex_home", "codex_homes"),
        ("router_events", "router_events"),
        ("scan_root", "scan_roots"),
    ]:
        if getattr(args, argument):
            overrides[key] = getattr(args, argument)
    engine = Engine(args.state_dir, overrides)
    from logging.handlers import RotatingFileHandler

    handler = RotatingFileHandler(
        engine.store.directory / "mission-control.log",
        maxBytes=2_000_000,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    should_open = not args.no_open and (args.open or len(sys.argv) == 1)
    try:
        server = Server(("127.0.0.1", args.port), engine, dev_web=args.dev_web)
    except OSError as ex:
        # 1) A healthy instance of this exact app that accepts our OWNER token
        #    and actually renders the dashboard shell can be reused. Never send
        #    an owner token to an unknown app, and never reuse a broken instance.
        if _reusable_instance(args.port, engine.control_token) and _serves_shell(args.port):
            if should_open:
                webbrowser.open(f"http://127.0.0.1:{args.port}/#access={engine.control_token}")
            engine.close()
            return 0
        # 2) Otherwise (foreign app, stale copy or broken instance) start on the
        #    next free loopback port so the launcher always yields a running app.
        server = None
        for candidate in range(args.port + 1, min(args.port + 51, 65536)):
            try:
                server = Server(("127.0.0.1", candidate), engine, dev_web=args.dev_web)
                LOG.warning("Port %s is in use; started on %s instead.", args.port, candidate)
                if not args.quiet and sys.stdout:
                    print(f"Port {args.port} is in use; using {candidate} instead.")
                break
            except OSError:
                continue
        if server is None:
            engine.close()
            raise RuntimeError(
                f"Port {args.port} is in use and no free port was found in {args.port + 1}-{args.port + 50}. Original error: {ex}"
            ) from ex
    runtime = {
        "port": server.server_address[1],
        "pid": os.getpid(),
        "version": VERSION,
        "started": now_ms(),
    }
    (engine.store.directory / "runtime.json").write_text(json.dumps(runtime), "utf-8")
    url = f"http://127.0.0.1:{engine.port}"
    if not args.quiet and sys.stdout:
        print(
            f"{APP} {VERSION}\nDashboard: {url}\nState and logs: {engine.store.directory}\nSources are read-only. Stop with Ctrl+C.\n"
        )
    engine.start()
    if should_open:
        threading.Timer(
            0.4, lambda: webbrowser.open(url + "/#access=" + engine.control_token)
        ).start()
    if args.idle_timeout:

        def watch_idle():
            while not engine.stop.wait(2):
                if time.monotonic() - server.last_request > args.idle_timeout:
                    server.shutdown()
                    return

        threading.Thread(target=watch_idle, daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        engine.close()
        LOG.info("Observer stopped")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        LOG.exception("Startup failed")
        if sys.stderr:
            print(f"{APP}: {exc}", file=sys.stderr)
        else:
            # pythonw / double-click on Windows: give a real error, not silence.
            try:
                import tkinter.messagebox

                tkinter.messagebox.showerror(APP, str(exc))
            except Exception:
                pass
        raise SystemExit(1)
