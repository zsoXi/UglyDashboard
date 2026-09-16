"""Command line entrypoints, stdio bridge and self-test."""
import argparse
import base64
import copy
import csv
import hashlib
import hmac
import html
import io
import ipaddress
import json
import logging
import math
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PureWindowsPath
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse, unquote
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from .core import *  # noqa: F401,F403
from .sources import *  # noqa: F401,F403
from .store import *  # noqa: F401,F403
from .engine import *  # noqa: F401,F403
from .server import *  # noqa: F401,F403


def stdio_bridge(directory):
    """MCP stdio transport proxy. Stdout is JSON-RPC only, never logging."""
    state = Path(directory).expanduser().resolve()
    try:
        runtime = json.loads((state / 'runtime.json').read_text('utf-8'))
        port = runtime['port']
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError('Invalid observer port.')
        token = (state / 'mcp.token').read_text('utf-8').strip()
        if len(token) < 32:
            raise ValueError('Invalid MCP token.')
    except (OSError, ValueError, KeyError) as ex:
        if sys.stderr:
            print('Start Mission Control before connecting its stdio bridge: ' + str(ex), file=sys.stderr)
        return 2
    url = f'http://127.0.0.1:{port}/mcp'
    while True:
        raw = sys.stdin.buffer.readline(MAX_BODY + 1)
        if not raw:
            return 0
        if len(raw) > MAX_BODY:
            while raw and not raw.endswith(b'\n'):
                raw = sys.stdin.buffer.readline(MAX_BODY + 1)
            response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Message too large'}}
        else:
            request = None
            try:
                request = json.loads(raw)
                if not isinstance(request, dict):
                    raise ValueError('JSON-RPC object required')
                req = Request(url, data=json.dumps(request, allow_nan=False).encode(), headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'})
                with LOCAL_HTTP.open(req, timeout=20) as res:
                    body = res.read(MAX_RESPONSE + 1)
                    if len(body) > MAX_RESPONSE:
                        raise ValueError('Response too large')
                    if res.status == 202 or not body:
                        continue
                    response = json.loads(body)
            except Exception as ex:
                if isinstance(request, dict) and 'id' not in request:
                    continue
                response = {'jsonrpc': '2.0', 'id': request.get('id') if isinstance(request, dict) else None,
                            'error': {'code': -32000 if request else -32700, 'message': 'Observer bridge: ' + redact(ex, 400)}}
        sys.stdout.write(json.dumps(response, ensure_ascii=True, allow_nan=False) + '\n')
        sys.stdout.flush()


def cli_report(path, directory):
    state = Path(directory).expanduser().resolve()
    runtime = json.loads((state / 'runtime.json').read_text('utf-8'))
    token = (state / 'mcp.token').read_text('utf-8').strip()
    if path == '-':
        raw = sys.stdin.buffer.read(MAX_BODY + 1)
    else:
        p = Path(path)
        if p.stat().st_size > MAX_BODY:
            raise ValueError('Report file is larger than 1 MiB.')
        raw = p.read_bytes()
    if len(raw) > MAX_BODY:
        raise ValueError('Report is larger than 1 MiB.')
    event = json.loads(raw)
    response = local_json(f'http://127.0.0.1:{int(runtime["port"])}/mcp', timeout=10,
                          headers={'Authorization': 'Bearer ' + token},
                          body={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'report_event', 'arguments': event}})
    print(json.dumps(response, indent=2, ensure_ascii=False))
    return 1 if response.get('error') or response.get('result', {}).get('isError') else 0


def builtin_self_test():
    import tempfile
    import unittest
    class Sanity(unittest.TestCase):
        def test_codex_counts_cache_once(self):
            self.assertEqual(codex_usage({'input_tokens': 100, 'cached_input_tokens': 70, 'output_tokens': 20, 'reasoning_output_tokens': 5})['total'], 120)
        def test_nonfinite(self):
            self.assertEqual(number(float('nan')), 0)
        def test_windows_paths(self):
            self.assertTrue(is_within(r'D:\Work\Project\a.py', r'd:\work\project'))
            self.assertFalse(is_within('/a/project2/x', '/a/project'))
        def test_no_remote_oc(self):
            with self.assertRaises(ValueError):
                validate_config({'opencode_urls': ['https://example.com']})
        def test_no_negative_budget(self):
            with self.assertRaises(ValueError):
                validate_config({'token_budget': -1})
        def test_jsonl_partial(self):
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / 'log.jsonl'; p.write_bytes(b'{"a":')
                reader = JsonlReader(); self.assertEqual(reader.read(p), [])
                with p.open('ab') as f:
                    f.write(b'1}\n')
                self.assertEqual(reader.read(p), [{'a': 1}]); self.assertEqual(reader.read(p), [])
        def test_repeated_cumulative_usage(self):
            s = make_session('codex', 'test')
            r = {'timestamp': '2026-09-16T10:00:00Z', 'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {'total_token_usage': {'input_tokens': 100, 'output_tokens': 20}}}}
            codex_apply(s, [r, r]); self.assertEqual(s['usage']['total'], 120)
        def test_redaction(self):
            self.assertNotIn('1234567890123456', redact('api_key=1234567890123456'))
        def test_report_self_parent(self):
            with self.assertRaises(ValueError):
                normalize_report({'event_id': 'e', 'session_id': 'x', 'parent_id': 'x', 'source': 'manual'})
        def test_parent_is_not_worker(self):
            s = make_session('opencode', 's'); self.assertEqual(s['relationship'], 'root')
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Sanity))
    return 0 if result.wasSuccessful() else 1


def main():
    parser = argparse.ArgumentParser(description=APP + ' — local observer, single Python file, no packages required.')
    parser.add_argument('db', nargs='?', help='Optional OpenCode SQLite path (old CLI compatibility).')
    parser.add_argument('--db', dest='dbs', action='append', help='Read an OpenCode DB; repeat for multiple sources.')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--state-dir', default=os.environ.get('MISSION_CONTROL_HOME', str(STATE_DEFAULT)))
    parser.add_argument('--opencode-url', action='append', help='URL of an existing loopback OpenCode server. Does not start another server.')
    parser.add_argument('--codex-home', action='append', help='Codex home containing sessions and/or archived_sessions.')
    parser.add_argument('--router-events', action='append', help='Optional router usage-events.jsonl ledger.')
    parser.add_argument('--scan-root', action='append', help='Default folder in the opt-in scanner; no automatic recursive scan.')
    parser.add_argument('--open', action='store_true', help='Open the authenticated browser dashboard.')
    parser.add_argument('--no-open', action='store_true', help='Do not launch a browser.')
    parser.add_argument('--quiet', action='store_true', help='Do not write console status messages.')
    parser.add_argument('--idle-timeout', type=int, default=0, help='Optional shutdown after N seconds without requests. Default 0 keeps observer running.')
    parser.add_argument('--mcp-stdio', action='store_true', help='Bridge stdio MCP to an already-running dashboard. Stdout is JSON-RPC only.')
    parser.add_argument('--report-event', metavar='JSON_FILE', help='Send an explicit report using MCP. Reporting must be enabled; use - for stdin.')
    parser.add_argument('--self-test', action='store_true', help='Run built-in offline sanity tests without reading user data.')
    parser.add_argument('--version', action='version', version=VERSION)
    args = parser.parse_args()
    if args.self_test:
        return builtin_self_test()
    if args.mcp_stdio:
        return stdio_bridge(args.state_dir)
    if args.report_event:
        return cli_report(args.report_event, args.state_dir)
    if not 1 <= args.port <= 65535 or args.idle_timeout < 0:
        parser.error('Invalid port or idle timeout.')
    overrides = {}
    if args.db or args.dbs:
        overrides['db_paths'] = ([args.db] if args.db else []) + (args.dbs or [])
    for argument, key in [('opencode_url', 'opencode_urls'), ('codex_home', 'codex_homes'), ('router_events', 'router_events'), ('scan_root', 'scan_roots')]:
        if getattr(args, argument):
            overrides[key] = getattr(args, argument)
    engine = Engine(args.state_dir, overrides)
    from logging.handlers import RotatingFileHandler
    handler = RotatingFileHandler(engine.store.directory / 'mission-control.log', maxBytes=2_000_000, backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    LOG.addHandler(handler); LOG.setLevel(logging.INFO)
    should_open = not args.no_open and (args.open or len(sys.argv) == 1)
    try:
        server = Server(('127.0.0.1', args.port), engine)
    except OSError as ex:
        # Reuse only a server that both identifies itself and accepts this
        # observer's OWNER token. Never send an owner fragment to an unknown app.
        try:
            health = local_json(f'http://127.0.0.1:{args.port}/health', timeout=1)
            if health.get('application') != 'opencode-mission-control':
                raise ValueError('Different application on this port.')
            local_json(f'http://127.0.0.1:{args.port}/api/overview', timeout=2, headers={'Authorization': 'Bearer ' + engine.control_token})
            if should_open:
                webbrowser.open(f'http://127.0.0.1:{args.port}/#access={engine.control_token}')
            engine.close()
            return 0
        except Exception:
            engine.close()
            raise RuntimeError(f'Port {args.port} is in use. Close the other app or run with --port 8766. Original error: {ex}') from ex
    runtime = {'port': server.server_address[1], 'pid': os.getpid(), 'version': VERSION, 'started': now_ms()}
    (engine.store.directory / 'runtime.json').write_text(json.dumps(runtime), 'utf-8')
    url = f'http://127.0.0.1:{engine.port}'
    if not args.quiet and sys.stdout:
        print(f'{APP} {VERSION}\nDashboard: {url}\nState and logs: {engine.store.directory}\nSources are read-only. Stop with Ctrl+C.\n')
    engine.start()
    if should_open:
        threading.Timer(.4, lambda: webbrowser.open(url + '/#access=' + engine.control_token)).start()
    if args.idle_timeout:
        def watch_idle():
            while not engine.stop.wait(2):
                if time.monotonic() - server.last_request > args.idle_timeout:
                    server.shutdown(); return
        threading.Thread(target=watch_idle, daemon=True).start()
    try:
        server.serve_forever(poll_interval=.4)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close(); engine.close()
        LOG.info('Observer stopped')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        LOG.exception('Startup failed')
        if sys.stderr:
            print(f'{APP}: {exc}', file=sys.stderr)
        else:
            # pythonw / double-click on Windows: give a real error, not silence.
            try:
                import tkinter.messagebox
                tkinter.messagebox.showerror(APP, str(exc))
            except Exception:
                pass
        raise SystemExit(1)
