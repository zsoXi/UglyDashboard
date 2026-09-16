"""Private observer SQLite store and local secret management."""
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


class SecretError(RuntimeError):
    """Raised when a local secret file exists but is unusable.

    Carries the offending path and a machine-readable ``reason`` so callers can
    present a readable diagnostic instead of silently rotating credentials.
    """
    def __init__(self, path, reason):
        self.path = Path(path)
        self.reason = reason
        super().__init__(f'{reason}: {self.path}')


class Store:
    """Private observer database. Never reuses the OpenCode/Codex source DB."""
    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            self.directory.chmod(0o700)
        except OSError:
            pass
        self.path = self.directory / 'observer.sqlite'
        self.lock = threading.RLock()
        self._closed = False
        self.con = sqlite3.connect(self.path, check_same_thread=False, timeout=5)
        self.con.row_factory = sqlite3.Row
        self.con.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS event(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                ts INTEGER NOT NULL, session_id TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS event_time ON event(ts DESC);
            CREATE INDEX IF NOT EXISTS event_session ON event(session_id,ts DESC);
            CREATE TABLE IF NOT EXISTS setting(key TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS report(id TEXT PRIMARY KEY, ts INTEGER NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS assessment(session_id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS oauth_client(id TEXT PRIMARY KEY, data TEXT NOT NULL);
        ''')
        self.con.commit()

    def secret(self, name, repair=False):
        """Return a stable local secret, creating it once if absent.

        Recovery is explicit. A file that is empty, truncated or corrupt raises
        :class:`SecretError` unless ``repair=True`` is passed, in which case the
        damaged file is preserved as ``<name>.corrupt-<ts>.bak`` before a fresh
        secret is generated. Credentials are never silently rotated.
        """
        p = self.directory / name
        if p.exists():
            value = self._read_secret(p)
            if value is not None:
                return value
            if not repair:
                raise SecretError(p, 'secret file is empty, truncated or corrupt')
            self._quarantine_secret(p)
        return self._create_secret(p)

    @staticmethod
    def _read_secret(p):
        try:
            value = p.read_text('utf-8').strip()
        except (OSError, UnicodeDecodeError):
            return None
        return value if SECRET_RE.match(value) else None

    def _quarantine_secret(self, p):
        backup = p.with_name(f'{p.name}.corrupt-{int(time.time())}.bak')
        try:
            os.replace(str(p), str(backup))
            return backup
        except OSError:
            try:
                p.unlink()
            except OSError:
                pass
            return None

    def _create_secret(self, p):
        value = secrets.token_urlsafe(36)
        tmp = p.with_name(f'{p.name}.tmp-{os.getpid()}-{secrets.token_hex(4)}')
        try:
            fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError as exc:
            raise SecretError(p, f'cannot write secret ({exc.strerror or exc})') from exc
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(value + '\n')
                f.flush()
                os.fsync(f.fileno())
            try:
                os.link(str(tmp), str(p))
            except FileExistsError:
                existing = self._read_secret(p)
                if existing is None:
                    raise SecretError(p, 'secret file exists but is unreadable')
                return existing
            except OSError:
                try:
                    fd2 = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    existing = self._read_secret(p)
                    if existing is None:
                        raise SecretError(p, 'secret file exists but is unreadable')
                    return existing
                with os.fdopen(fd2, 'w', encoding='utf-8') as f2:
                    f2.write(value + '\n')
                    f2.flush()
                    os.fsync(f2.fileno())
            return value
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass

    def setting(self, key, default=None):
        with self.lock:
            row = self.con.execute('SELECT data FROM setting WHERE key=?', (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.lock, self.con:
            self.con.execute('INSERT INTO setting(key,data) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET data=excluded.data', (key, json.dumps(value, allow_nan=False)))

    def events(self, items):
        with self.lock, self.con:
            self.con.executemany('INSERT OR IGNORE INTO event(id,ts,session_id,kind,data) VALUES(?,?,?,?,?)',
                [(e['id'], int(e.get('ts') or now_ms()), e.get('session_id', ''), e.get('kind', 'event'), json.dumps(e, ensure_ascii=False, allow_nan=False)) for e in items])

    def timeline(self, limit=100, before=0, session_id='', project='', query=''):
        terms, vals = [], []
        if before:
            terms.append('seq<?'); vals.append(before)
        if session_id:
            terms.append('session_id=?'); vals.append(session_id)
        # Text search uses a bound parameter, never SQL interpolation.
        if query:
            terms.append('data LIKE ?'); vals.append('%' + query[:200] + '%')
        sql = 'SELECT seq,data FROM event' + (' WHERE ' + ' AND '.join(terms) if terms else '') + ' ORDER BY seq DESC LIMIT ?'
        vals.append(min(max(1, limit), 500) * (4 if project else 1))
        with self.lock:
            rows = self.con.execute(sql, vals).fetchall()
        result = []
        cursor = None
        for row in rows:
            cursor = row['seq']
            e = json.loads(row['data']); e['seq'] = row['seq']
            if not project or path_key(e.get('project')) == path_key(project):
                result.append(e)
            if len(result) >= limit:
                break
        return {'events': result, 'next_before': cursor if len(rows) >= min(max(1, limit), 500) else None}

    def reports(self):
        with self.lock:
            return [dict(json.loads(r[0]), _received_at=r[1]) for r in self.con.execute('SELECT data,ts FROM report ORDER BY ts DESC LIMIT 5000')]

    def report(self, data):
        with self.lock, self.con:
            found = self.con.execute('SELECT data FROM report WHERE id=?', (data['event_id'],)).fetchone()
            if found:
                if json.loads(found[0]) != data:
                    raise ValueError('event_id already exists with a different payload.')
                return False
            self.con.execute('INSERT INTO report VALUES(?,?,?)', (data['event_id'], data['timestamp'] or now_ms(), json.dumps(data, allow_nan=False)))
            return True

    def assessments(self):
        with self.lock:
            return {r[0]: json.loads(r[1]) for r in self.con.execute('SELECT session_id,data FROM assessment')}

    def assess(self, sid, data):
        with self.lock, self.con:
            self.con.execute('INSERT INTO assessment VALUES(?,?) ON CONFLICT(session_id) DO UPDATE SET data=excluded.data', (sid, json.dumps(data, allow_nan=False)))

    def prune(self, days):
        with self.lock, self.con:
            cutoff = now_ms() - days * 86400000
            self.con.execute('DELETE FROM event WHERE ts<?', (cutoff,))
            self.con.execute('DELETE FROM event WHERE seq NOT IN (SELECT seq FROM event ORDER BY seq DESC LIMIT 100000)')
            self.con.execute('DELETE FROM report WHERE ts<?', (cutoff,))
            self.con.execute('DELETE FROM report WHERE id NOT IN (SELECT id FROM report ORDER BY ts DESC LIMIT 5000)')

    def close(self):
        """Release the sqlite handle. Idempotent and safe to call twice."""
        with self.lock:
            if self._closed:
                return
            self._closed = True
            try:
                self.con.close()
            except sqlite3.Error:
                pass
