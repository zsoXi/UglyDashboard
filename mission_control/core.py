"""Shared constants, validation and pure helpers."""
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


VERSION = '4.0.0'


APP = 'OpenCode Mission Control'


ACTIVE = {'running', 'thinking', 'tool'}


TERMINAL = {'done', 'error', 'cancelled'}


STATES = ACTIVE | TERMINAL | {'idle', 'waiting', 'retry', 'stale', 'unknown'}


MAX_BODY = 1024 * 1024


MAX_RESPONSE = 16 * 1024 * 1024


MAX_LINE = 4 * 1024 * 1024

# Per-session usage ledger cap. Session totals remain exact; the event-level
# ledger is truncated (oldest first) so analytics stay predictably bounded.
MAX_SESSION_USAGE_EVENTS = 4000


HOME = Path.home()


STATE_DEFAULT = HOME / '.opencode-mission-control'


LOG = logging.getLogger('mission-control')


class LifecycleError(RuntimeError):
    """Raised when a thread or server cannot be stopped deterministically."""

# Repository/install root of the package, used to resolve the stable thin
# launcher regardless of which module is executing.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def launcher_path():
    """Absolute path to the thin root entrypoint used for MCP stdio."""
    return PACKAGE_ROOT / 'opencode_dashboard.py'


def stdio_script_args():
    """Args that start this application in ``--mcp-stdio`` mode.

    Prefers the stable root launcher; falls back to ``-m mission_control`` for
    installed layouts where the launcher file is not present.
    """
    candidate = launcher_path()
    if candidate.is_file():
        return [str(candidate)]
    return ['-m', 'mission_control']


class Diagnostics:
    """Thread-safe counter of rejected/coerced input values.

    Usage parsing must never silently turn invalid or negative numbers into a
    plausible zero. Rejections are recorded here and surfaced in coverage so a
    data bug is visible instead of hidden.
    """

    MAX_SAMPLES = 25

    def __init__(self):
        self.lock = threading.Lock()
        self.counts = Counter()
        self.samples = deque(maxlen=self.MAX_SAMPLES)

    def record(self, field, value, reason):
        with self.lock:
            self.counts[f'{field}:{reason}'] += 1
            if len(self.samples) < self.MAX_SAMPLES:
                self.samples.append({'field': str(field), 'reason': reason, 'value': safe_repr(value)})

    def extend(self, other):
        if other is None:
            return
        with other.lock:
            other_counts = dict(other.counts)
            other_samples = list(other.samples)
        with self.lock:
            for key, count in other_counts.items():
                self.counts[key] += count
            for sample in other_samples:
                if len(self.samples) < self.MAX_SAMPLES:
                    self.samples.append(sample)

    def snapshot(self):
        with self.lock:
            return {'rejected_total': sum(self.counts.values()), 'counts': dict(self.counts),
                    'samples': list(self.samples)}


def safe_repr(value, limit=80):
    try:
        text = repr(value)
    except Exception:
        text = f'<{type(value).__name__}>'
    return text if len(text) <= limit else text[:limit] + '…'


def now_ms() -> int:
    return int(time.time() * 1000)


def number(value, default=0, diagnostics=None, field='value'):
    """Coerce ``value`` to a finite, non-negative float.

    Invalid values (non-numeric, non-finite, negative) fall back to ``default``
    and, when a :class:`Diagnostics` collector is supplied, are recorded as a
    rejection instead of being silently clamped.
    """
    try:
        n = float(value)
    except (ValueError, TypeError, OverflowError):
        if diagnostics is not None:
            diagnostics.record(field, value, 'not-a-number')
        return default
    if not math.isfinite(n):
        if diagnostics is not None:
            diagnostics.record(field, value, 'non-finite')
        return default
    if n < 0:
        if diagnostics is not None:
            diagnostics.record(field, value, 'negative')
        return default
    return n


def stamp(value) -> int:
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            return 0
        return int(value if value > 1e11 else value * 1000)
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return int(dt.timestamp() * 1000)
    except (TypeError, ValueError, OverflowError, OSError):
        return 0


def day(ms):
    try:
        return datetime.fromtimestamp(ms / 1000).date().isoformat()
    except (ValueError, OSError, OverflowError):
        return ''


def digest(*parts):
    return hashlib.sha256('\x1f'.join(str(x) for x in parts).encode()).hexdigest()[:32]


def obj(raw):
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw or '{}')
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def redact(value, limit=4000):
    """Best-effort masking, not a guarantee that arbitrary prose has no secrets."""
    s = str(value or '')[:max(limit * 2, 4096)]
    s = re.sub(r'(?i)\b(sk-[a-z0-9_-]{10,}|gh[pousr]_[a-z0-9_]{15,}|github_pat_[a-z0-9_]{15,})', '[REDACTED]', s)
    s = re.sub(r'(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization)\s*[=:]\s*[\"\']?)[^\s\"\',;}]+', r'\1[REDACTED]', s)
    s = re.sub(r'(?i)\bBearer\s+[a-z0-9._~+/=-]+', 'Bearer [REDACTED]', s)
    return s[:limit]


def public_copy(value):
    if isinstance(value, dict):
        return {k: public_copy(v) for k, v in value.items() if not k.startswith('_')}
    if isinstance(value, list):
        return [public_copy(v) for v in value]
    return value


def path_key(path):
    s = str(path or '').replace('\\', '/').rstrip('/')
    if re.match(r'^[A-Za-z]:/', s):
        return s.casefold()
    return s


def path_name(path):
    return str(path or '').replace('\\', '/').rstrip('/').split('/')[-1] or 'Unassigned'


def is_within(path, root):
    p, r = path_key(path), path_key(root)
    return bool(r) and (p == r or p.startswith(r + '/'))


def existing_unique(paths):
    out, seen = [], set()
    for p in paths:
        p = Path(os.path.expandvars(str(p))).expanduser()
        key = path_key(p.resolve())
        if key not in seen and p.exists():
            seen.add(key)
            out.append(str(p.resolve()))
    return out


def default_config():
    data = Path(os.environ.get('XDG_DATA_HOME', str(HOME / '.local/share')))
    codehome = Path(os.environ.get('CODEX_HOME', str(HOME / '.codex')))
    dbs = [data / 'opencode/opencode.db', HOME / '.local/share/opencode/opencode.db']
    for env in ('LOCALAPPDATA', 'APPDATA'):
        if os.environ.get(env):
            dbs += [Path(os.environ[env]) / 'opencode/opencode.db']
    return {
        'db_paths': existing_unique(dbs), 'codex_homes': existing_unique([codehome]),
        'router_events': existing_unique([codehome / 'codex-router/usage-events.jsonl']),
        'opencode_urls': ['http://127.0.0.1:4096'],
        'projects': [], 'excluded_projects': [], 'scan_roots': [str(HOME)],
        'poll_seconds': 8, 'history_limit': 1000, 'codex_file_limit': 400,
        'history_days': 90, 'show_prompts': True, 'enable_reporting': False,
        'allow_abort': False, 'expected_models': {}, 'allowed_paths': {},
        'stall_seconds': 600, 'token_budget': 0, 'public_origin': '',
        'oauth_redirect_uris': ['https://chatgpt.com/connector_platform_oauth_redirect'],
        'pricing': {}, 'git_enabled': True,
    }


def validate_config(raw):
    if not isinstance(raw, dict):
        raise ValueError('Configuration must be an object.')
    result = default_config()
    unknown = set(raw) - set(result)
    if unknown:
        raise ValueError('Unknown settings: ' + ', '.join(sorted(unknown)))
    result.update(raw)
    for key in ('db_paths', 'codex_homes', 'router_events', 'projects', 'excluded_projects', 'scan_roots', 'oauth_redirect_uris', 'opencode_urls'):
        if not isinstance(result[key], list) or len(result[key]) > 100 or any(not isinstance(x, str) or len(x) > 4096 for x in result[key]):
            raise ValueError(key + ' must be a list of up to 100 strings.')
    for key, lo, hi in [('poll_seconds', 3, 120), ('history_limit', 50, 10000), ('codex_file_limit', 10, 3000), ('history_days', 1, 730), ('stall_seconds', 30, 86400), ('token_budget', 0, 10**12)]:
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi or not math.isfinite(value):
            raise ValueError(f'{key} must be between {lo} and {hi}.')
        result[key] = int(value)
    for key in ('show_prompts', 'enable_reporting', 'allow_abort', 'git_enabled'):
        if not isinstance(result[key], bool):
            raise ValueError(key + ' must be true or false.')
    for url in result['opencode_urls']:
        u = urlparse(url)
        if u.scheme != 'http' or u.hostname not in ('localhost', '127.0.0.1', '::1') or u.username or u.password or u.query or u.fragment or u.path not in ('', '/'):
            raise ValueError('OpenCode URLs must be explicit loopback HTTP origins. Use an SSH tunnel for remote OpenCode.')
        if u.port is not None and not 1 <= u.port <= 65535:
            raise ValueError('Invalid OpenCode port.')
    origin = result['public_origin']
    if not isinstance(origin, str):
        raise ValueError('public_origin must be a string.')
    if origin:
        u = urlparse(origin)
        if u.scheme != 'https' or not u.netloc or u.username or u.password or u.path not in ('', '/') or u.query or u.fragment:
            raise ValueError('public_origin must be an HTTPS origin without path, credentials or query.')
        result['public_origin'] = origin.rstrip('/')
    for uri in result['oauth_redirect_uris']:
        u = urlparse(uri)
        if u.scheme != 'https' or not u.netloc or u.username or u.password or u.fragment:
            raise ValueError('OAuth callback allowlist accepts exact HTTPS URIs only.')
    for key in ('expected_models', 'allowed_paths', 'pricing'):
        if not isinstance(result[key], dict) or len(result[key]) > 200:
            raise ValueError(key + ' must be an object with at most 200 entries.')
    if any(not isinstance(v, str) for v in result['expected_models'].values()):
        raise ValueError('Expected models must be exact model ID strings.')
    if any(not isinstance(v, list) or any(not isinstance(p, str) for p in v) for v in result['allowed_paths'].values()):
        raise ValueError('Allowed paths must map an agent name to a list of directories.')
    for model, pricing in result['pricing'].items():
        if not isinstance(pricing, dict) or any(k not in {'input', 'output', 'cache_read', 'cache_write'} for k in pricing):
            raise ValueError('Pricing fields: input, output, cache_read, cache_write; USD per million tokens.')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in pricing.values()):
            raise ValueError('Pricing must contain finite nonnegative numbers.')
    return result


@contextmanager
def readonly_db(path):
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    con = sqlite3.connect(p.as_uri() + '?mode=ro', uri=True, timeout=1.5)
    con.row_factory = sqlite3.Row
    try:
        con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN')  # consistent snapshot across all SELECTs, including WAL
        deadline = time.monotonic() + 12
        con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        yield con
    finally:
        con.close()


def columns(con, table):
    # Only literal, application-owned table names may reach this helper.
    if table not in {'session', 'message', 'part', 'project', 'session_input'}:
        raise ValueError('Unexpected table.')
    return {r[1] for r in con.execute(f'PRAGMA table_info("{table}")')}


def fingerprint(path):
    vals = []
    for s in ('', '-wal', '-shm'):
        try:
            st = Path(str(path) + s).stat()
            vals.append((st.st_mtime_ns, st.st_size))
        except OSError:
            vals.append(None)
    return tuple(vals)


def zero_usage():
    return {'input': 0, 'output': 0, 'reasoning': 0, 'cache_read': 0, 'cache_write': 0, 'total': 0}


def oc_usage(t, diagnostics=None):
    t = obj(t)
    c = obj(t.get('cache'))
    out = dict(input=number(t.get('input'), diagnostics=diagnostics, field='opencode.input'),
               output=number(t.get('output'), diagnostics=diagnostics, field='opencode.output'),
               reasoning=number(t.get('reasoning'), diagnostics=diagnostics, field='opencode.reasoning'),
               cache_read=number(c.get('read'), diagnostics=diagnostics, field='opencode.cache_read'),
               cache_write=number(c.get('write'), diagnostics=diagnostics, field='opencode.cache_write'))
    # Preserve provider-normalized explicit totals; never silently replace them.
    out['total'] = number(t.get('total'), diagnostics=diagnostics, field='opencode.total') if t.get('total') is not None else sum(out.values())
    return out


def codex_usage(t, diagnostics=None):
    t = obj(t)
    inp = number(t.get('input_tokens'), diagnostics=diagnostics, field='codex.input')
    out = number(t.get('output_tokens'), diagnostics=diagnostics, field='codex.output')
    cached = min(inp, number(t.get('cached_input_tokens', t.get('cache_read_input_tokens')), diagnostics=diagnostics, field='codex.cache_read'))
    reasoning = number(t.get('reasoning_output_tokens'), diagnostics=diagnostics, field='codex.reasoning')
    # Codex cached input is a subset of input; reasoning is a subset of output.
    return {'input': inp - cached, 'output': max(0, out - reasoning),
            'reasoning': reasoning, 'cache_read': cached, 'cache_write': 0,
            'total': number(t.get('total_tokens'), diagnostics=diagnostics, field='codex.total') if t.get('total_tokens') is not None else inp + out}


def add_usage(a, b):
    for k in zero_usage():
        a[k] = a.get(k, 0) + b.get(k, 0)


def make_session(source, sid, title='', directory=''):
    return {'id': source + ':' + sid, 'native_id': sid, 'source': source, 'sources': [source],
            'title': redact(title or sid, 240), 'directory': str(directory or ''),
            'project': path_name(directory), 'parent_id': '', 'relationship': 'root',
            'agent': 'unknown', 'model': 'unknown', 'provider': 'unknown',
            'origin': 'unknown', 'origin_evidence': 'not recorded',
            'state': 'unknown', 'state_evidence': 'no live connection', 'confidence': 'unknown',
            'created': 0, 'updated': 0, 'observed': 0, 'turn_started': 0,
            'usage': zero_usage(), 'usage_known': False, 'cost': None, 'messages': 0,
            'prompt': '', 'tools': [], 'files': [], 'usage_events': [], 'events': [],
            'model_usage': {}, 'context_tokens': None, 'context_limit': None,
            'errors': 0, 'retry_count': 0, 'warnings': [], '_completed': 0, '_error_at': 0,
            'usage_events_dropped': 0}


def add_event(s, kind, text, ts, eid='', detail=None):
    s['events'].append({'id': digest(s['id'], eid or ts, kind, text), 'session_id': s['id'],
                        'ts': ts or s['updated'], 'source': s['source'], 'kind': kind,
                        'text': redact(text, 1200), 'project': s['directory'],
                        'detail': detail or {}})


def record_usage(s, usage, ts, model=None, provider=None, cost=None):
    name = model or s['model']
    prov = provider or s['provider']
    add_usage(s['usage'], usage)
    s['usage_known'] = True
    key = prov + '/' + name
    m = s['model_usage'].setdefault(key, {'model': name, 'provider': prov, 'usage': zero_usage(), 'cost': None, 'requests': 0})
    add_usage(m['usage'], usage)
    m['requests'] += 1
    if isinstance(cost, (int, float)) and math.isfinite(cost) and cost >= 0:
        m['cost'] = (m['cost'] or 0) + cost
        s['cost'] = (s['cost'] or 0) + cost
    events = s['usage_events']
    events.append({'ts': ts, 'model': name, 'provider': prov, **usage})
    # Bounded per-session history: totals stay exact, only the per-event ledger is
    # capped so analytics work is predictable. Dropped records are counted so the
    # truncation is visible in coverage instead of silently distorting per-day
    # breakdowns.
    if len(events) > MAX_SESSION_USAGE_EVENTS:
        dropped = len(events) - MAX_SESSION_USAGE_EVENTS
        del events[:dropped]
        s['usage_events_dropped'] = s.get('usage_events_dropped', 0) + dropped


def bounded_append(items, value, limit=100):
    items.append(value)
    if len(items) > limit:
        del items[:len(items) - limit]


def extract_files(name, inputs):
    out = []
    if name in ('edit', 'write', 'read', 'apply_patch', 'applyPatch', 'functions.apply_patch'):
        for k in ('filePath', 'path', 'file_path'):
            if isinstance(inputs.get(k), str):
                out.append(inputs[k])
        patch = inputs.get('patchText', inputs.get('patch', inputs.get('input', '')))
        if isinstance(patch, str):
            out += re.findall(r'^\*\*\* (?:Update|Add|Delete) File: (.+)$', patch, flags=re.M)
    return out


def tool_detail(name, callid, state, ts, inputs=None, output='', exit_code=None):
    inputs = obj(inputs)
    command = inputs.get('command', inputs.get('cmd', ''))
    if isinstance(command, list):
        command = ' '.join(map(str, command))
    return {'id': str(callid), 'name': str(name), 'state': str(state), 'ts': ts,
            'command': redact(command, 1500), 'input': redact(json.dumps(inputs, ensure_ascii=False), 2000),
            'output': redact(output, 2500), 'exit_code': exit_code, 'files': extract_files(name, inputs)}


SECRET_RE = re.compile(r'^[A-Za-z0-9_\-]{32,512}$')
