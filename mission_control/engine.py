"""Collection engine, alert derivation and the published dashboard snapshot."""
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


def normalize_report(raw):
    allowed = {'event_id', 'session_id', 'source', 'timestamp', 'state', 'title', 'task', 'task_group', 'model', 'agent', 'parent_id', 'directory', 'tool', 'message', 'commit_sha'}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValueError('Invalid event fields. Use the reporting schema in Integrations.')
    for key in ('event_id', 'session_id', 'source'):
        if not isinstance(raw.get(key), str) or not 1 <= len(raw[key]) <= 200:
            raise ValueError(key + ' is required (1–200 characters).')
    if raw['source'] not in ('chatgpt', 'codex', 'opencode', 'manual'):
        raise ValueError('source: chatgpt, codex, opencode or manual.')
    if raw.get('state') and raw['state'] not in STATES:
        raise ValueError('Unknown state.')
    out = copy.deepcopy(raw)
    if 'timestamp' in raw:
        ts = stamp(raw['timestamp'])
        if not ts or ts > now_ms() + 300000 or ts < now_ms() - 730 * 86400000:
            raise ValueError('timestamp is outside the accepted two-year history / five-minute clock-skew window.')
        out['timestamp'] = ts
    else:
        # Deterministic absent timestamp allows an idempotent replay of an event.
        out['timestamp'] = 0
    for key, v in out.items():
        if key not in ('timestamp',) and not isinstance(v, str):
            raise ValueError(key + ' must be a string.')
        if isinstance(v, str) and len(v) > (5000 if key in ('task', 'message') else 1000):
            raise ValueError(key + ' is too long.')
    if out.get('parent_id') == out['session_id']:
        raise ValueError('A session cannot be its own parent.')
    if out.get('commit_sha') and not re.fullmatch(r'[a-fA-F0-9]{7,64}', out['commit_sha']):
        raise ValueError('Invalid commit SHA.')
    return out


def derive_alerts(sessions, cfg, sources):
    alerts = []; now = now_ms()
    def alert(s, kind, severity, text):
        alerts.append({'id': digest(s.get('id', ''), kind), 'session_id': s.get('id', ''), 'project': s.get('directory', ''), 'kind': kind, 'severity': severity, 'text': text, 'ts': now})
    for s in sessions:
        recent = now - s['updated'] < 86400000
        if s['state'] in ACTIVE | {'retry', 'stale'} and s.get('turn_started') and now - s['updated'] > cfg['stall_seconds'] * 1000:
            alert(s, 'silence', 'warning', 'No new activity evidence within the configured threshold. Check the source; this does not prove a crash.')
        expected = cfg['expected_models'].get(s['id']) or cfg['expected_models'].get(s['agent'])
        if expected and s['model'] != 'unknown' and s['model'] != expected and recent:
            alert(s, 'model_mismatch', 'danger', f"Expected {expected}; observed {s['model']}.")
        budget = cfg['token_budget']
        if budget and s['usage']['total'] > budget and recent:
            alert(s, 'budget', 'warning', f"Session token budget exceeded: {int(s['usage']['total']):,} / {budget:,}.")
        last_tools = s['tools'][-5:]
        if recent and len(last_tools) >= 3 and all(t['state'] == 'error' for t in last_tools[-3:]):
            alert(s, 'tool_errors', 'danger', 'Three consecutive recorded tool failures.')
        if recent and len(last_tools) >= 5 and len({(t['name'], t['input']) for t in last_tools}) == 1:
            alert(s, 'possible_loop', 'warning', 'Five identical recent tool calls. Possible loop; review before interrupting.')
        if s['state'] == 'retry':
            alert(s, 'retry', 'warning', s.get('retry_message') or 'OpenCode reports retry/backoff.')
        if recent and any('429' in t.get('output', '') for t in last_tools):
            alert(s, 'rate_limit', 'warning', 'A recent tool result contains HTTP 429. Inspect the provider response.')
        roots = cfg['allowed_paths'].get(s['agent'], [])
        outside = [p for p in s['files'] if roots and not any(is_within(p if re.match(r'^(?:[A-Za-z]:|/)', p) else s['directory'] + '/' + p, r) for r in roots)]
        if outside and recent:
            alert(s, 'scope', 'danger', 'Recorded file outside assigned scope: ' + outside[0])
        if s['context_limit'] and s['context_tokens'] and s['context_tokens'] / s['context_limit'] >= .85 and recent:
            alert(s, 'context', 'warning', 'Last reported input context is at least 85% of the recorded context window.')
    writers = defaultdict(list)
    for s in sessions:
        if s['state'] in ACTIVE and now - s['updated'] < 300000:
            for p in s['files']:
                full = p if re.match(r'^(?:[A-Za-z]:|/)', p) else s['directory'] + '/' + p
                writers[path_key(full)].append(s)
    for p, values in writers.items():
        if len(values) > 1:
            alert(values[0], 'overlap:' + p, 'warning', 'Possible overlapping work on ' + p + ': ' + ', '.join(s['agent'] for s in values[:4]))
    for source in sources:
        if source.get('error'):
            alert({}, 'source:' + source['id'], 'warning', source['label'] + ': ' + source['error'])
    return sorted(alerts, key=lambda a: (a['severity'] != 'danger', a['kind']))


class Engine:
    """Collects local sources into an immutable, publishable snapshot.

    Lock lifecycle
    --------------
    ``lock`` (RLock) protects the mutable ``sessions`` / ``snapshot`` / ``cfg``
    state and the caches. ``poll_lock`` serialises collector cycles. Network,
    database and git I/O always happens *outside* ``lock``; handlers only take
    ``lock`` to read a reference or swap the published snapshot, never to run
    expensive work. ``view()`` / ``detail()`` copy the published state outside
    the lock so request handlers never block the collector.
    """

    def __init__(self, directory, overrides=None, repair_secrets=False):
        self.store = Store(directory)
        self.control_token = self.store.secret('owner.token', repair=repair_secrets)
        self.mcp_token = self.store.secret('mcp.token', repair=repair_secrets)
        self.pairing_key = self.store.secret('pairing.key', repair=repair_secrets)
        self.config_path = self.store.directory / 'config.json'
        if self.config_path.exists():
            raw = json.loads(self.config_path.read_text('utf-8'))
        else:
            raw = default_config()
        raw.update(overrides or {})
        self.cfg = validate_config(raw)
        self.lock = threading.RLock()
        self.poll_lock = threading.Lock()
        self.stop = threading.Event(); self.wake = threading.Event()
        self.db_cache = {}; self.codex_cache = {}; self.router_cache = {}
        self.git_cache = {}; self.scan_result = {'running': False, 'items': []}
        self.sessions = {}; self.previous_states = {}
        self.snapshot = {'version': VERSION, 'generated_at': 0, 'refreshing': True, 'sessions': [], 'projects': [], 'sources': [], 'alerts': [], 'definitions': [], 'router': [], 'coverage': []}
        self.started = now_ms(); self.port = 8765; self.thread = None
        self.server = None
        self._closed = False
        self._facts = []
        self._facts_revision = 0
        self.save_config(self.cfg)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


    def config(self):
        with self.lock:
            return copy.deepcopy(self.cfg)

    def save_config(self, cfg):
        checked = validate_config(cfg)
        tmp = self.config_path.with_suffix('.tmp')
        # Atomic replacement and serialization under the same lock.
        with self.lock:
            tmp.write_text(json.dumps(checked, ensure_ascii=False, indent=2), 'utf-8')
            try:
                tmp.chmod(0o600)
            except OSError:
                pass
            os.replace(tmp, self.config_path)
            self.cfg = checked
        self.wake.set()

    def start(self):
        self.thread = threading.Thread(target=self._loop, name='observer-poll', daemon=True)
        self.thread.start()

    def _loop(self):
        while not self.stop.is_set():
            try:
                self.poll()
            except Exception:
                LOG.exception('Collector cycle failed')
                with self.lock:
                    self.snapshot['collector_error'] = 'Collector error. See mission-control.log.'
                    self.snapshot['refreshing'] = False
            self.wake.wait(self.config()['poll_seconds']); self.wake.clear()

    def poll(self):
        if not self.poll_lock.acquire(blocking=False):
            return
        try:
            self._poll()
        finally:
            self.poll_lock.release()

    def _poll(self):
        cfg = self.config(); all_sessions = {}; sources = []; projects = list(cfg['projects']); definitions = []; router = []
        with self.lock:
            self.snapshot['refreshing'] = True
        for path in cfg['db_paths']:
            src = {'id': digest('db', path), 'label': 'OpenCode SQLite', 'location': path, 'kind': 'database', 'checked': now_ms()}
            try:
                key = (fingerprint(path), cfg['history_limit'])
                cached = self.db_cache.get(path)
                if not cached or cached[0] != key:
                    cached = (key, read_opencode(path, cfg['history_limit'])); self.db_cache[path] = cached
                rows, dirs, coverage = copy.deepcopy(cached[1]); projects.extend(dirs); src.update(coverage); src['ok'] = True
                for s in rows:
                    old = all_sessions.get(s['id'])
                    if old is None or s['updated'] > old['updated']:
                        all_sessions[s['id']] = s
            except Exception as e:
                src.update(ok=False, error=redact(e, 240))
            sources.append(src)
        native_dirs = list(dict.fromkeys(p for p in projects if p and Path(p).is_dir()))
        if cfg['opencode_urls']:
            with ThreadPoolExecutor(max_workers=min(4, len(cfg['opencode_urls']))) as pool:
                futures = {pool.submit(read_oc_live, url, native_dirs): url for url in cfg['opencode_urls']}
                for fut in as_completed(futures):
                    url = futures[fut]
                    src = {'id': digest('api', url), 'label': 'OpenCode live API', 'location': url, 'kind': 'api', 'checked': now_ms()}
                    try:
                        statuses, rows, defs, info = fut.result()
                        src.update(ok=True, **info); definitions.extend(defs)
                        for r in rows:
                            if not isinstance(r.get('id'), str):
                                continue
                            sid = 'opencode:' + r['id']
                            s = all_sessions.get(sid)
                            if s is None:
                                s = make_session('opencode', r['id'], r.get('title'), r.get('directory'))
                                t = obj(r.get('time')); s.update(created=int(number(t.get('created'))), updated=int(number(t.get('updated'))))
                                if r.get('parentID'):
                                    s['parent_id'] = 'opencode:' + str(r['parentID']); s['relationship'] = 'parent_unknown'
                                all_sessions[sid] = s
                            # Refresh metadata, but do not count API + DB tokens twice.
                            t = obj(r.get('time'))
                            s['updated'] = max(s['updated'], int(number(t.get('updated'))))
                            if not (s['confidence'] == 'verified' and s['state'] in ACTIVE):
                                s['_server'] = url
                            if r.get('directory'):
                                s['directory'] = r['directory']; s['project'] = path_name(r['directory']); projects.append(r['directory'])
                        for sid, st in statuses.items():
                            s = all_sessions.get('opencode:' + sid)
                            if s is None:
                                s = make_session('opencode', sid, directory=st.get('_directory'))
                                all_sessions[s['id']] = s
                            if s['confidence'] == 'verified' and s['state'] in ACTIVE and st['type'] == 'idle':
                                s['warnings'].append('Different servers report conflicting states; preserving the busy observation.')
                                continue
                            s['_server'] = url; s['observed'] = now_ms(); s['confidence'] = 'verified'
                            s['state'] = {'busy': 'running', 'idle': 'idle', 'retry': 'retry'}[st['type']]
                            if s['state'] == 'running' and s['tools'] and s['tools'][-1]['state'] == 'running':
                                s['state'] = 'tool'
                            s['state_evidence'] = 'OpenCode /session/status: ' + st['type']
                            if s['state'] == 'retry':
                                s['retry_message'] = redact(st.get('message'), 300)
                                s['retry_count'] = max(s['retry_count'], int(number(st.get('attempt'))))
                    except Exception as e:
                        src.update(ok=False, error=redact(e, 240))
                    sources.append(src)
        enrich = [s for s in all_sessions.values() if s.get('_server') and s['state'] in ACTIVE][:40]
        if enrich:
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = {pool.submit(enrich_oc_session, s): s for s in enrich}
                for f in as_completed(futures):
                    try:
                        f.result()
                    except Exception:
                        futures[f]['warnings'].append('Live message detail unavailable; status source remains separate.')
        for parent in all_sessions.values():
            for native_child in parent.get('_child_links', []):
                child = all_sessions.get('opencode:' + native_child)
                if child:
                    child['parent_id'] = parent['id']; child['relationship'] = 'delegated'
        files, coverage = discover_codex_files(cfg['codex_homes'], cfg['codex_file_limit'])
        codex_source = {'id': 'codex-logs', 'label': 'Codex session logs', 'location': ', '.join(cfg['codex_homes']), 'kind': 'codex', 'checked': now_ms(), 'ok': bool(cfg['codex_homes']), **coverage}
        if not cfg['codex_homes']:
            codex_source['note'] = 'No local Codex directory selected. Cloud sessions are not automatically visible.'
        problems = []; skipped = 0; catching_up = 0
        for path in files:
            try:
                item = self.codex_cache.setdefault(path, {'reader': JsonlReader(), 'session': make_session('codex', Path(path).stem)})
                reader = item['reader']; records = reader.read(path)
                if reader.reset:
                    item['session'] = make_session('codex', Path(path).stem)
                s = codex_apply(item['session'], records)
                skipped += reader.skipped
                if reader.offset < Path(path).stat().st_size:
                    catching_up += 1
                s['_log'] = path
                ss = copy.deepcopy(s)
                if ss['state'] in ACTIVE | {'waiting'} and now_ms() - ss['updated'] > cfg['stall_seconds'] * 1000:
                    ss['state'] = 'stale'; ss['confidence'] = 'unknown'; ss['state_evidence'] = 'Old unfinished log marker. Running/finished cannot be established.'
                old = all_sessions.get(ss['id'])
                if old is None or ss['updated'] > old['updated']:
                    all_sessions[ss['id']] = ss
                if ss['directory']:
                    projects.append(ss['directory'])
            except Exception as e:
                problems.append(redact(str(path) + ': ' + str(e), 220))
        # Release old file caches; history is rebuilt if they enter the selected window again.
        self.codex_cache = {p: v for p, v in self.codex_cache.items() if p in set(files)}
        codex_source.update(skipped_records=skipped, catching_up=catching_up, issues=problems[:10])
        if problems:
            codex_source['error'] = f'{len(problems)} unreadable Codex log(s).'
        sources.append(codex_source)
        for path in cfg['router_events']:
            src = {'id': digest('router', path), 'label': 'Router usage ledger', 'location': path, 'kind': 'router', 'checked': now_ms()}
            try:
                item = self.router_cache.setdefault(path, {'reader': JsonlReader(), 'events': deque(maxlen=30000), 'count': 0})
                records = item['reader'].read(path)
                if item['reader'].reset:
                    item['events'].clear(); item['count'] = 0
                for r in records:
                    status = r.get('status')
                    ok = isinstance(status, (int, float)) and 200 <= status < 300
                    usage = codex_usage({'input_tokens': r.get('inputTokens'), 'cached_input_tokens': r.get('cachedInputTokens'), 'output_tokens': r.get('outputTokens'), 'total_tokens': r.get('totalTokens')})
                    item['events'].append({'ts': stamp(r.get('at')), 'model': str(r.get('model') or 'unknown'), 'provider': str(r.get('provider') or 'unknown'), 'status': status, 'ok': ok, 'usage': usage, 'duration_ms': number(r.get('durationMs'))})
                    item['count'] += 1
                ledger = list(item['events'])
                src.update(ok=True, loaded_events=len(ledger), total_read=item['count'], truncated=item['count'] > 30000, skipped_records=item['reader'].skipped)
                router.append({'source': str(path), 'events': ledger, 'coverage': public_copy(src)})
            except Exception as e:
                src.update(ok=False, error=redact(e, 240))
            sources.append(src)
        # Explicit reports attach origin/task context to canonical sessions. They
        # never add tokens or override a live native status.
        seen_report_sessions = set()
        for report in self.store.reports():
            sid = report['session_id']
            if sid in seen_report_sessions:
                continue
            seen_report_sessions.add(sid)
            s = all_sessions.get(sid)
            if s is None:
                s = make_session('reported', sid, report.get('title') or report.get('task'), report.get('directory'))
                s['id'] = sid if sid.startswith('reported:') else 'reported:' + sid
                s['native_id'] = sid; s['created'] = report['timestamp'] or report['_received_at']; s['updated'] = report['timestamp'] or report['_received_at']
                s['model'] = report.get('model') or 'unknown'; s['agent'] = report.get('agent') or report['source']
                s['state'] = report.get('state') or 'unknown'; s['confidence'] = 'reported'; s['state_evidence'] = 'caller-supplied report, not independently verified'
                if s['state'] in ACTIVE and now_ms() - s['updated'] > cfg['stall_seconds'] * 1000:
                    s['state'] = 'stale'
                s['parent_id'] = report.get('parent_id', ''); s['relationship'] = 'reported' if s['parent_id'] else 'root'
                s['prompt'] = redact(report.get('task'), 5000)
                all_sessions[s['id']] = s
            s['origin'] = report['source']; s['origin_evidence'] = 'explicit MCP/HTTP report (caller claim)'
            s['task_group'] = report.get('task_group', '')
            s['reported_task'] = redact(report.get('task'), 5000)
            if report.get('commit_sha'):
                s['commit_sha'] = report['commit_sha']
        excluded = {path_key(p) for p in cfg['excluded_projects']}
        sessions = [s for s in all_sessions.values() if path_key(s['directory']) not in excluded]
        project_paths = sorted({path_key(p): p for p in projects if p and path_key(p) not in excluded}.values(), key=str.casefold)
        definitions.extend(read_definitions(project_paths))
        if not cfg['show_prompts']:
            definitions = [{**d, 'prompt': ''} for d in definitions]
        assessments = self.store.assessments()
        rows = []
        for s in sessions:
            s['assessment'] = assessments.get(s['id'])
            s['project'] = path_name(s['directory'])
            s['children'] = [c['id'] for c in sessions if c['parent_id'] == s['id'] and c['relationship'] == 'delegated']
            s['age_seconds'] = max(0, (now_ms() - s['updated']) / 1000) if s['updated'] else None
            if not cfg['show_prompts']:
                s['prompt'] = ''; s['reported_task'] = ''
                s['events'] = [e for e in s['events'] if e['kind'] != 'prompt']
            self.store.events(s['events'])
            previous = self.previous_states.get(s['id'])
            statekey = (s['state'], s['confidence'])
            if previous != statekey:
                self.store.events([{'id': digest('state', s['id'], now_ms(), statekey), 'session_id': s['id'], 'source': s['source'], 'kind': 'state', 'project': s['directory'], 'ts': now_ms(), 'text': f"{s['agent']} → {s['state']} ({s['confidence']})", 'detail': {'evidence': s['state_evidence']}}])
            self.previous_states[s['id']] = statekey
            rows.append(s)
        # Git is contextual. Never manufacture a "cost per commit" by assigning
        # every session from the previous 24 hours to every commit.
        prows = []
        for p in project_paths:
            members = [s for s in rows if path_key(s['directory']) == path_key(p)]
            g = self.git_cache.get(p)
            if cfg['git_enabled'] and (not g or time.time() - g[0] > 60) and len(prows) < 30:
                self.git_cache[p] = (time.time(), git_info(p)); g = self.git_cache[p]
            prows.append({'id': digest(p), 'path': p, 'name': path_name(p), 'sessions': len(members),
                          'active': sum(s['state'] in ACTIVE and s['confidence'] == 'verified' for s in members),
                          'reported_active': sum(s['state'] in ACTIVE and s['confidence'] != 'verified' for s in members),
                          'tokens': sum(s['usage']['total'] for s in members), 'sources': sorted({s['source'] for s in members}),
                          'git': (g[1] if g and cfg['git_enabled'] else {}), 'monitored': True})
        alerts = derive_alerts(rows, cfg, sources)
        ack = set(self.store.setting('acknowledged', []))
        for a in alerts:
            a['acknowledged'] = a['id'] in ack
        rows.sort(key=lambda s: (s['state'] not in ACTIVE, -s['updated']))
        with self.lock:
            self.sessions = {s['id']: s for s in rows}
            self.snapshot = {'version': VERSION, 'generated_at': now_ms(), 'refreshing': False,
                             'sessions': [self.summary(s) for s in rows], 'projects': prows,
                             'sources': sources, 'alerts': alerts, 'definitions': definitions,
                             'router': router, 'coverage': [s for s in sources if s.get('truncated') or s.get('catching_up')],
                             'privacy': {'show_prompts': cfg['show_prompts'], 'reporting': cfg['enable_reporting'], 'abort': cfg['allow_abort']}}
        self.store.prune(cfg['history_days'])

    @staticmethod
    def summary(s):
        omit = {'events', 'usage_events', 'tools', 'model_usage', 'prompt', 'reported_task'}
        out = {k: copy.deepcopy(v) for k, v in s.items() if k not in omit and not k.startswith('_')}
        out['task_preview'] = redact(s.get('reported_task') or s.get('prompt'), 180)
        out['last_tool'] = s['tools'][-1]['name'] if s['tools'] else ''
        out['can_abort'] = bool(s.get('_server')) and s['source'] == 'opencode'
        return out

    def view(self):
        with self.lock:
            snap = copy.deepcopy(self.snapshot)
        # Never continue advertising a verified busy state after a stalled
        # collector. Aging evidence changes presentation, not underlying data.
        now = now_ms(); freshness = max(30, self.config()['poll_seconds'] * 3) * 1000
        for s in snap['sessions']:
            if s['confidence'] == 'verified' and now - s['observed'] > freshness:
                s['confidence'] = 'unknown'; s['state'] = 'stale'
                s['state_evidence'] = 'Live status observation expired; refresh connection.'
        for p in snap['projects']:
            members = [s for s in snap['sessions'] if path_key(s['directory']) == path_key(p['path'])]
            p['active'] = sum(s['state'] in ACTIVE and s['confidence'] == 'verified' for s in members)
            p['reported_active'] = sum(s['state'] in ACTIVE and s['confidence'] != 'verified' for s in members)
        counts = Counter(s['state'] for s in snap['sessions'])
        snap['port'] = self.port
        snap['counts'] = dict(counts)
        snap['verified_active'] = sum(s['state'] in ACTIVE and s['confidence'] == 'verified' for s in snap['sessions'])
        snap['unverified_active'] = sum(s['state'] in ACTIVE and s['confidence'] != 'verified' for s in snap['sessions'])
        snap['tokens'] = sum(s['usage']['total'] for s in snap['sessions'] if s['source'] != 'reported')
        # Router requests can overlap native sessions. Keep them out of totals.
        for ledger in snap['router']:
            ev = ledger.pop('events')
            ledger['requests'] = len(ev)
            ledger['errors'] = sum(e['ok'] is False for e in ev if e['status'] is not None)
            ledger['unknown_status'] = sum(e['status'] is None for e in ev)
            ledger['tokens'] = sum(e['usage']['total'] for e in ev)
            ledger['recent'] = ev[-100:][::-1]
        return snap

    def detail(self, sid):
        with self.lock:
            s = copy.deepcopy(self.sessions.get(sid))
            defs = copy.deepcopy(self.snapshot['definitions'])
        if not s:
            raise KeyError('Session not found in the loaded window.')
        out = public_copy(s)
        freshness = max(30, self.config()['poll_seconds'] * 3) * 1000
        if out.get('confidence') == 'verified' and now_ms() - out.get('observed', 0) > freshness:
            out.update(state='stale', confidence='unknown', state_evidence='Live status observation expired; refresh connection.')
        out['definition'] = next((d for d in defs if d['name'] == s['agent'] and is_within(d.get('directory'), s['directory'])), None) or next((d for d in defs if d['name'] == s['agent']), None)
        if not self.config()['show_prompts']:
            out['prompt'] = ''; out['reported_task'] = ''; out['definition'] = None
        out['timeline'] = self.store.timeline(80, session_id=sid)['events']
        if not self.config()['show_prompts']:
            out['timeline'] = [e for e in out['timeline'] if e['kind'] != 'prompt']
        return out

    def analytics(self, days=0, project='', task_group='', source=''):
        cfg = self.config()
        cutoff = 0
        if days:
            # Inclusive local calendar window, not a rolling N*24h plus today.
            start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
            cutoff = int(start.timestamp() * 1000)
        with self.lock:
            sessions = copy.deepcopy(list(self.sessions.values()))
        models = {}; daily = defaultdict(zero_usage); filetotals = defaultdict(float); selected = []; token_total = 0
        def modelrow(model, provider):
            key = provider + '/' + model
            return models.setdefault(key, {'id': key, 'model': model, 'provider': provider, 'usage': zero_usage(), 'sessions': set(), 'requests': 0, 'recorded_cost': None,
                                            'estimated_cost': None, 'priced_tokens': 0, 'assessments': [], 'errors': 0, 'retries': 0})
        for s in sessions:
            if s['source'] == 'reported' or (source and source != s['source']) or (project and path_key(s['directory']) != path_key(project)):
                continue
            assessment = s.get('assessment') or {}
            group = assessment.get('task_group') or s.get('task_group', '')
            if task_group and group != task_group:
                continue
            if cutoff and s['updated'] < cutoff:
                continue
            selected.append(s)
            relevant = [e for e in s['usage_events'] if not cutoff or e['ts'] >= cutoff]
            for e in relevant:
                if day(e['ts']):
                    add_usage(daily[day(e['ts'])], e)
            session_tokens = sum(e['total'] for e in relevant) if cutoff else s['usage']['total']
            token_total += session_tokens
            if s['files']:
                for f in s['files']:
                    filetotals[f] += session_tokens / len(s['files'])
            if cutoff:
                bymodel = {}
                for e in relevant:
                    key = e['provider'] + '/' + e['model']
                    row = bymodel.setdefault(key, {'model': e['model'], 'provider': e['provider'], 'usage': zero_usage(), 'cost': None, 'requests': 0})
                    add_usage(row['usage'], e); row['requests'] += 1
            else:
                bymodel = s['model_usage']
            for entry in bymodel.values():
                r = modelrow(entry['model'], entry['provider']); add_usage(r['usage'], entry['usage']); r['sessions'].add(s['id']); r['requests'] += entry['requests']
                if entry.get('cost') is not None:
                    r['recorded_cost'] = (r['recorded_cost'] or 0) + entry['cost']
                pricing = cfg['pricing'].get(r['id']) or cfg['pricing'].get(r['model'])
                if pricing:
                    u = entry['usage']; components = {'input': u['input'], 'output': u['output'] + u['reasoning'], 'cache_read': u['cache_read'], 'cache_write': u['cache_write']}
                    if all(v == 0 or k in pricing for k, v in components.items()):
                        estimate = sum(v * pricing.get(k, 0) / 1e6 for k, v in components.items())
                        r['estimated_cost'] = (r['estimated_cost'] or 0) + estimate; r['priced_tokens'] += u['total']
                # Error and retry counts are session-level, not fabricated per-model splits.
                if len(s['model_usage']) == 1:
                    r['errors'] += s['errors']; r['retries'] += s['retry_count']
            if assessment:
                r = modelrow(assessment.get('model') or s['model'], assessment.get('provider') or s['provider'])
                r['assessments'].append(assessment)
        mrows = []
        for r in models.values():
            r['sessions'] = len(r['sessions'])
            assessed = r.pop('assessments'); verified_tests = [a for a in assessed if isinstance(a.get('tests_passed'), bool)]
            fixes = [a['review_fixes'] for a in assessed if isinstance(a.get('review_fixes'), int)]
            elapsed = [a['duration_seconds'] for a in assessed if isinstance(a.get('duration_seconds'), (int, float))]
            r.update(assessed_tasks=len(assessed), test_samples=len(verified_tests), test_pass_rate=sum(a['tests_passed'] for a in verified_tests) / len(verified_tests) if verified_tests else None,
                     avg_review_fixes=sum(fixes)/len(fixes) if fixes else None, avg_duration_seconds=sum(elapsed)/len(elapsed) if elapsed else None,
                     tokens_per_session=r['usage']['total']/r['sessions'] if r['sessions'] else None)
            mrows.append(r)
        activity = []
        for i in range(363, -1, -1):
            d = (datetime.now().date() - timedelta(days=i)).isoformat()
            activity.append({'date': d, **daily.get(d, zero_usage())})
        return {'tokens': token_total, 'sessions': len(selected), 'models': sorted(mrows, key=lambda r: -r['usage']['total']),
                'days': [{'date': d, **u} for d, u in sorted(daily.items())], 'activity': activity,
                'files': [{'path': f, 'estimated_tokens': round(v, 1)} for f, v in sorted(filetotals.items(), key=lambda i: -i[1])[:25]],
                'methodology': 'Loaded native sessions only. Router excluded to avoid double counting. Files use equal allocation, not measured per-file cost. Outcomes/durations are owner-reported assessments, not independently verified. No model quality ranking is inferred from token volume.',
                'cost_note': 'Missing rates/costs remain unknown. Configured USD-per-million rates are estimates, not invoices. Period costs are estimates only.',
                'days_filter': days, 'task_group': task_group, 'project': project}

    def add_report(self, raw):
        if not self.config()['enable_reporting']:
            raise PermissionError('Telemetry reporting is disabled. Enable it explicitly in Integrations.')
        data = normalize_report(raw)
        changed = self.store.report(data)
        if changed:
            self.store.events([{'id': digest('report', data['event_id']), 'ts': data['timestamp'] or now_ms(), 'session_id': data['session_id'], 'source': data['source'], 'kind': 'reported', 'project': data.get('directory', ''), 'text': redact(data.get('message') or data.get('task') or data.get('state') or 'Task report', 1200), 'detail': {'evidence': 'caller claim'}}])
            self.wake.set()
        return {'accepted': True, 'duplicate': not changed, 'event_id': data['event_id']}

    def assess(self, sid, data):
        with self.lock:
            s = self.sessions.get(sid)
        if not s:
            raise ValueError('Unknown session.')
        allowed = {'task_group', 'tests_passed', 'review_fixes', 'duration_seconds', 'notes', 'model'}
        if not isinstance(data, dict) or set(data) - allowed:
            raise ValueError('Unsupported assessment fields.')
        a = dict(data)
        for field in ('task_group', 'notes', 'model'):
            if field in a and (not isinstance(a[field], str) or len(a[field]) > 3000):
                raise ValueError('Invalid ' + field)
        if a.get('tests_passed') is not None and not isinstance(a['tests_passed'], bool):
            raise ValueError('tests_passed must be true, false or null.')
        for field in ('review_fixes', 'duration_seconds'):
            if a.get(field) is not None and (isinstance(a[field], bool) or not isinstance(a[field], int) or not 0 <= a[field] <= 10**8):
                raise ValueError(field + ' must be a nonnegative integer or null.')
        a.update(recorded_at=now_ms(), evidence='owner-reported', model=a.get('model') or s['model'], provider=s['provider'])
        self.store.assess(sid, a)
        with self.lock:
            if sid in self.sessions:
                self.sessions[sid]['assessment'] = a
        self.wake.set()
        return a

    def begin_scan(self, roots, depth):
        if not isinstance(roots, list) or not roots or len(roots) > 20 or any(not isinstance(x, str) for x in roots):
            raise ValueError('Provide 1–20 explicit scan roots.')
        if not isinstance(depth, int) or not 1 <= depth <= 10:
            raise ValueError('Scan depth must be 1–10.')
        with self.lock:
            if self.scan_result.get('running'):
                return self.scan_result
            self.scan_result = {'running': True, 'items': [], 'started': now_ms()}
        def work():
            try:
                result = scan_paths(roots, depth)
            except Exception as e:
                result = {'items': [], 'errors': [redact(e)], 'truncated': True}
            with self.lock:
                self.scan_result = {**result, 'running': False, 'finished': now_ms()}
        threading.Thread(target=work, daemon=True, name='bounded-discovery').start()
        return {'running': True}

    def adopt_scan(self, selected):
        if not isinstance(selected, list) or len(selected) > 100:
            raise ValueError('Select up to 100 discoveries.')
        with self.lock:
            available = {(i['kind'], i['path']) for i in self.scan_result.get('items', [])}
        cfg = self.config()
        mapping = {'project': 'projects', 'database': 'db_paths', 'codex': 'codex_homes', 'router': 'router_events'}
        for item in selected:
            pair = (item.get('kind'), item.get('path'))
            if pair not in available:
                raise ValueError('Selection was not returned by the last scan.')
            key = mapping[pair[0]]
            if pair[1] not in cfg[key]:
                cfg[key].append(pair[1])
        self.save_config(cfg)
        return {'added': len(selected)}

    def abort(self, sid, confirmation):
        if not self.config()['allow_abort']:
            raise PermissionError('Abort is disabled. Enable it explicitly in Settings.')
        with self.lock:
            s = copy.deepcopy(self.sessions.get(sid))
        if not s or s['source'] != 'opencode' or not s.get('_server'):
            raise ValueError('Only a known OpenCode session on a connected live server can be interrupted.')
        if confirmation != s['native_id']:
            raise ValueError('Type the exact native session ID to confirm.')
        base = s['_server'].rstrip('/')
        if base not in [u.rstrip('/') for u in self.config()['opencode_urls']]:
            raise PermissionError('Server is no longer allowlisted.')
        response = local_json(base + '/session/' + quote(s['native_id'], safe='') + '/abort?' + urlencode({'directory': s['directory']}), body={}, headers=oc_headers(), timeout=5)
        self.store.events([{'id': digest('abort', sid, now_ms()), 'ts': now_ms(), 'session_id': sid, 'kind': 'intervention', 'source': 'manual', 'project': s['directory'], 'text': 'Owner requested OpenCode abort', 'detail': {'response': response}}])
        self.wake.set()
        return {'requested': True, 'response': response}

    def close(self):
        """Deterministically stop the collector, drain HTTP work, then close the DB."""
        if getattr(self, '_closed', False):
            return
        self._closed = True
        self.stop.set(); self.wake.set()
        if self.thread:
            self.thread.join(timeout=5)
        server = getattr(self, 'server', None)
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.wait_idle(5)
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
        # Always release the observer DB once no handler or collector can use it.
        self.store.close()
