"""Private observer SQLite store and local secret management."""

import json
import os
import secrets
import sqlite3
import sys
import threading
import time
from pathlib import Path

from .core import (
    SECRET_RE,
    now_ms,
    path_key,
)
from .locking import secret_lock
from .migration import migrate_store


class SecretError(RuntimeError):
    """Raised when a local secret file exists but is unusable.

    Carries the offending path and a machine-readable ``reason`` so callers can
    present a readable diagnostic instead of silently rotating credentials.
    """

    def __init__(self, path, reason):
        # Keep the path as given. Coercing through Path() here would consult
        # os.name at call time on some Python versions, which breaks under
        # tests that simulate POSIX on Windows. Every call site already
        # passes a Path.
        self.path = path
        self.reason = reason
        super().__init__(f"{reason}: {self.path}")


class Store:
    """Private observer database. Never reuses the OpenCode/Codex source DB."""

    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            self.directory.chmod(0o700)
        except OSError:
            pass
        self.path = self.directory / "observer.sqlite"
        self.lock = threading.RLock()
        self._closed = False
        self.con = sqlite3.connect(self.path, check_same_thread=False, timeout=5)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        try:
            # Versioned, transactional and idempotent: a legacy (v5-era) database
            # is upgraded here, a current one is left exactly as it is. Source
            # OpenCode/Codex databases are never involved.
            self.migration = migrate_store(self.con)
        except BaseException:
            self.con.close()
            raise
        self.con.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS event(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                ts INTEGER NOT NULL, session_id TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS event_time ON event(ts DESC);
            CREATE INDEX IF NOT EXISTS event_session ON event(session_id,ts DESC);
            CREATE TABLE IF NOT EXISTS setting(key TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS report(id TEXT PRIMARY KEY, ts INTEGER NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS assessment(session_id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS oauth_client(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS usage_checkpoint(source_id TEXT NOT NULL, item_id TEXT NOT NULL,
                updated INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(source_id, item_id));
            CREATE INDEX IF NOT EXISTS usage_checkpoint_source ON usage_checkpoint(source_id);
        """)
        self.con.commit()

    def secret(self, name, repair=False):
        """Read/create a stable credential; repair corrupt content only explicitly.

        Every decision is taken under the same persistent advisory lock. In
        particular, a missing-file observation must never be combined with a
        later exists() check to falsely diagnose a concurrent creation as corrupt.
        Permission/I/O failures leave credentials untouched. No stale-lock unlink.
        """
        if (
            not isinstance(name, str)
            or not name
            or name in (".", "..")
            or "/" in name
            or chr(92) in name
        ):
            raise ValueError("Secret name must be a plain filename")
        p = self.directory / name
        try:
            with secret_lock(p.with_name(name + ".lock")):
                if p.exists():
                    value = self._read_secret(p)
                    if value is not None:
                        return value
                    if not repair:
                        raise SecretError(p, "secret file is empty, truncated or corrupt")
                    self._quarantine_secret(p)
                return self._create_secret(p)
        except SecretError:
            raise
        except OSError as exc:
            raise SecretError(p, f"credential transaction failed ({exc})") from exc

    def rotate_secret(self, name):
        """Atomically replace ONE credential with a fresh value.

        Used for owner-token rotation. Only the named file is touched: the
        private database, the saved configuration and the other independent
        credentials (mcp.token, pairing.key) are never modified. The previous
        value is overwritten without a backup, so it stops being accepted the
        next time a process reads this file; a dashboard that is already running
        keeps the old token in memory until it is restarted.
        """
        if (
            not isinstance(name, str)
            or not name
            or name in (".", "..")
            or "/" in name
            or chr(92) in name
        ):
            raise ValueError("Secret name must be a plain filename")
        p = self.directory / name
        try:
            with secret_lock(p.with_name(name + ".lock")):
                return self._create_secret(p, rotate=True)
        except SecretError:
            raise
        except OSError as exc:
            raise SecretError(p, f"credential rotation failed ({exc})") from exc

    @staticmethod
    def _read_secret(p):
        """Return the secret text, ``None`` if invalid, or raise on unreadable.

        A permission/IO error is deliberately distinct from corrupt content:
        corruption may be repairable, but an unreadable file must never cause a
        rotation that could hide the underlying problem.
        """
        try:
            raw = p.read_text("utf-8")
        except UnicodeDecodeError:
            return None
        except OSError as exc:
            raise SecretError(p, f"secret file is unreadable ({exc.strerror or exc})") from exc
        value = raw.strip()
        return value if SECRET_RE.match(value) else None

    def _quarantine_secret(self, p):
        """Preserve corrupt bytes without clobbering an existing backup.

        Windows rename refuses an existing destination. POSIX uses a no-clobber
        hardlink followed by unlink, while the credential lock remains held. A
        crash between those operations leaves BOTH copies recoverable.
        """
        stamp = time.strftime("%Y%m%d-%H%M%S")
        for _ in range(64):
            backup = p.with_name(f"{p.name}.corrupt-{stamp}-{secrets.token_hex(4)}.bak")
            try:
                if sys.platform == "win32":
                    os.rename(str(p), str(backup))
                else:
                    os.link(str(p), str(backup))
                    p.unlink()
                return backup
            except FileExistsError:
                continue
            except OSError as exc:
                raise SecretError(
                    p, f"cannot preserve corrupt credential; original retained ({exc})"
                ) from exc
        raise SecretError(p, "cannot preserve corrupt credential: backup names exhausted")

    def _create_secret(self, p, rotate=False):
        value = secrets.token_urlsafe(36)
        tmp = p.with_name(f"{p.name}.tmp-{os.getpid()}-{secrets.token_hex(6)}")
        fd = None
        try:
            fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                fd = None
                f.write(value + "\n")
                f.flush()
                os.fsync(f.fileno())
            if rotate:
                # Rotation must really invalidate the previous value: replace
                # the destination atomically and keep no copy of the old secret.
                try:
                    os.replace(str(tmp), str(p))
                except OSError as exc:
                    raise SecretError(
                        p, f"cannot rotate secret atomically ({exc.strerror or exc})"
                    ) from exc
                return value
            return self._publish_secret(tmp, p, value)
        except SecretError:
            raise
        except OSError as exc:
            raise SecretError(p, f"cannot write secret ({exc.strerror or exc})") from exc
        finally:
            if fd is not None:
                os.close(fd)
            try:
                tmp.unlink()
            except OSError:
                pass

    @staticmethod
    def _publish_secret(tmp, p, value):
        """Publish a fully written temp file without clobbering or partial writes."""
        try:
            os.link(str(tmp), str(p))
            return value
        except FileExistsError:
            pass
        except OSError as exc:
            # Hardlinks are unavailable (e.g. some network/FAT volumes). On
            # Windows os.rename is atomic and refuses an existing destination;
            # on POSIX os.rename would clobber, so fail closed instead of
            # publishing a partially written file.
            if os.name != "nt":
                raise SecretError(
                    p, f"cannot publish secret atomically ({exc.strerror or exc})"
                ) from exc
            try:
                os.rename(str(tmp), str(p))
                return value
            except FileExistsError:
                pass
            except OSError as exc2:
                raise SecretError(
                    p, f"cannot publish secret atomically ({exc2.strerror or exc2})"
                ) from exc2
        existing = Store._read_secret(p)
        if existing is None:
            raise SecretError(p, "secret file exists but is unreadable or corrupt")
        return existing

    def setting(self, key, default=None):
        with self.lock:
            row = self.con.execute("SELECT data FROM setting WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.lock, self.con:
            self.con.execute(
                "INSERT INTO setting(key,data) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET data=excluded.data",
                (key, json.dumps(value, allow_nan=False)),
            )

    def checkpoints(self, source_id):
        """Load the durable per-item usage checkpoints of one source."""
        with self.lock:
            rows = self.con.execute(
                "SELECT item_id, data FROM usage_checkpoint WHERE source_id=?", (source_id,)
            ).fetchall()
        return {row["item_id"]: json.loads(row["data"]) for row in rows}

    def put_checkpoints(self, source_id, items):
        """Persist checkpoints in ONE transaction per call.

        ``items`` is a sequence of (item_id, data). Writing the cursor and the
        aggregate it belongs to atomically is what prevents an interrupted
        cycle from losing or double-counting usage.
        """
        if not items:
            return
        ts = now_ms()
        with self.lock, self.con:
            self.con.executemany(
                "INSERT INTO usage_checkpoint(source_id,item_id,updated,data) VALUES(?,?,?,?) "
                "ON CONFLICT(source_id,item_id) DO UPDATE SET updated=excluded.updated, "
                "data=excluded.data",
                [(source_id, item_id, ts, json.dumps(data, allow_nan=False)) for item_id, data in items],
            )

    def delete_checkpoint(self, source_id, item_id):
        with self.lock, self.con:
            self.con.execute(
                "DELETE FROM usage_checkpoint WHERE source_id=? AND item_id=?",
                (source_id, item_id),
            )

    def events(self, items):
        with self.lock, self.con:
            self.con.executemany(
                "INSERT OR IGNORE INTO event(id,ts,session_id,kind,data) VALUES(?,?,?,?,?)",
                [
                    (
                        e["id"],
                        int(e.get("ts") or now_ms()),
                        e.get("session_id", ""),
                        e.get("kind", "event"),
                        json.dumps(e, ensure_ascii=False, allow_nan=False),
                    )
                    for e in items
                ],
            )

    def timeline(self, limit=100, before=0, session_id="", project="", query=""):
        terms, vals = [], []
        if before:
            terms.append("seq<?")
            vals.append(before)
        if session_id:
            terms.append("session_id=?")
            vals.append(session_id)
        # Text search uses a bound parameter, never SQL interpolation.
        if query:
            terms.append("data LIKE ?")
            vals.append("%" + query[:200] + "%")
        sql = (
            "SELECT seq,data FROM event"
            + (" WHERE " + " AND ".join(terms) if terms else "")
            + " ORDER BY seq DESC LIMIT ?"
        )
        vals.append(min(max(1, limit), 500) * (4 if project else 1))
        with self.lock:
            rows = self.con.execute(sql, vals).fetchall()
        result = []
        cursor = None
        for row in rows:
            cursor = row["seq"]
            e = json.loads(row["data"])
            e["seq"] = row["seq"]
            if not project or path_key(e.get("project")) == path_key(project):
                result.append(e)
            if len(result) >= limit:
                break
        return {
            "events": result,
            "next_before": cursor if len(rows) >= min(max(1, limit), 500) else None,
        }

    def reports(self):
        with self.lock:
            return [
                dict(json.loads(r[0]), _received_at=r[1])
                for r in self.con.execute("SELECT data,ts FROM report ORDER BY ts DESC LIMIT 5000")
            ]

    def report(self, data):
        with self.lock, self.con:
            found = self.con.execute(
                "SELECT data FROM report WHERE id=?", (data["event_id"],)
            ).fetchone()
            if found:
                if json.loads(found[0]) != data:
                    raise ValueError("event_id already exists with a different payload.")
                return False
            self.con.execute(
                "INSERT INTO report VALUES(?,?,?)",
                (
                    data["event_id"],
                    data["timestamp"] or now_ms(),
                    json.dumps(data, allow_nan=False),
                ),
            )
            return True

    def assessments(self):
        with self.lock:
            return {
                r[0]: json.loads(r[1])
                for r in self.con.execute("SELECT session_id,data FROM assessment")
            }

    def assess(self, sid, data):
        with self.lock, self.con:
            self.con.execute(
                "INSERT INTO assessment VALUES(?,?) ON CONFLICT(session_id) DO UPDATE SET data=excluded.data",
                (sid, json.dumps(data, allow_nan=False)),
            )

    def prune(self, days):
        with self.lock, self.con:
            cutoff = now_ms() - days * 86400000
            self.con.execute("DELETE FROM event WHERE ts<?", (cutoff,))
            self.con.execute(
                "DELETE FROM event WHERE seq NOT IN (SELECT seq FROM event ORDER BY seq DESC LIMIT 100000)"
            )
            self.con.execute("DELETE FROM report WHERE ts<?", (cutoff,))
            self.con.execute(
                "DELETE FROM report WHERE id NOT IN (SELECT id FROM report ORDER BY ts DESC LIMIT 5000)"
            )

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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False
