"""Versioned migration of the observer's own state.

Only the private observer directory is migrated: the OpenCode and Codex source
databases are never opened for writing and are not touched by this module.
Migration steps are idempotent and are committed in one transaction, so an
interrupted run can simply be retried. Before the first change to a database
that already holds rows, a consistent copy is made with the SQLite backup API
(WAL-safe; the ``-wal``/``-shm`` sidecars are never deleted or copied alone).
"""

import sqlite3
import time
from pathlib import Path

# Observer schema history:
#   v1 - v5-era tables: event, setting, report, assessment, oauth_client.
#   v2 - V6 (Etap C) adds the durable usage_checkpoint table. Nothing is
#        rewritten: existing rows, settings, assessments and secrets stay
#        exactly as they are and usage aggregates are rebuilt incrementally by
#        the next reads instead of being marked complete.
SCHEMA_VERSION = 2
CONFIG_VERSION = 2

CORE_TABLES = ("event", "setting", "report", "assessment", "oauth_client")
DATA_TABLES = CORE_TABLES + ("usage_checkpoint",)


class MigrationError(RuntimeError):
    """State cannot be migrated safely (newer schema, unreadable version)."""


def _tables(con):
    rows = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def _has_rows(con, tables):
    """True when any of the fixed, application-owned tables holds a row."""
    for name in tables:
        try:
            if con.execute("SELECT COUNT(*) FROM " + name).fetchone()[0]:
                return True
        except sqlite3.Error:
            continue
    return False


def _backup(con, db_path):
    """Consistent pre-migration copy through the SQLite backup API."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for attempt in range(64):
        name = f"{db_path.name}.pre-migration-v1-to-v{SCHEMA_VERSION}-{stamp}"
        if attempt:
            name += f"-{attempt}"
        dest = db_path.with_name(name)
        if dest.exists():
            continue
        target = sqlite3.connect(str(dest))
        try:
            con.backup(target)
            target.commit()
        finally:
            target.close()
        return dest
    raise MigrationError("cannot create a pre-migration backup: names exhausted")


def _migrate_to_2(con):
    """V6 (Etap C): add durable usage checkpoints; keep every existing row."""
    con.execute(
        "CREATE TABLE IF NOT EXISTS usage_checkpoint(source_id TEXT NOT NULL, "
        "item_id TEXT NOT NULL, updated INTEGER NOT NULL, data TEXT NOT NULL, "
        "PRIMARY KEY(source_id, item_id))"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS usage_checkpoint_source ON usage_checkpoint(source_id)"
    )


def _write_version(con, version):
    con.execute(
        "INSERT INTO meta(key,value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(version),),
    )


def migrate_store(con):
    """Bring one observer database to :data:`SCHEMA_VERSION`.

    Returns a report dict with ``migrated``, ``version``, ``from_version`` and
    ``backup`` (path or None). Raises :class:`MigrationError` when the database
    says it is newer than this build; in that case nothing is modified.
    """
    con.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    row = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    tables = _tables(con)
    if row is not None:
        try:
            version = int(str(row[0]))
        except (TypeError, ValueError):
            raise MigrationError(
                "observer schema version is unreadable: " + repr(row[0])
            ) from None
        if version > SCHEMA_VERSION:
            raise MigrationError(
                f"observer state uses schema v{version}, but this build supports "
                f"v{SCHEMA_VERSION}; refusing to modify it. Use a newer build or a "
                "copy of the state directory."
            )
    elif "usage_checkpoint" in tables:
        # A V6 build created the table and stopped before writing the marker.
        version = SCHEMA_VERSION
    elif tables & set(CORE_TABLES):
        version = 1
    else:
        version = SCHEMA_VERSION

    needs_marker = row is None
    migrated = version < SCHEMA_VERSION
    report = {
        "migrated": migrated,
        "version": SCHEMA_VERSION,
        "from_version": version,
        "backup": None,
    }
    backup = None
    if migrated and _has_rows(con, DATA_TABLES):
        backup = _backup(con, Path(con.execute("PRAGMA database_list").fetchone()[2]))
    report["backup"] = str(backup) if backup else None
    if migrated or needs_marker:
        # An explicit transaction keeps the schema change and the version
        # marker atomic. Python's legacy sqlite3 mode does not wrap DDL in an
        # implicit transaction, so a bare `with con:` would autocommit the
        # CREATE TABLE even when the marker write fails.
        con.execute("BEGIN")
        try:
            if migrated and version == 1:
                _migrate_to_2(con)
            _write_version(con, SCHEMA_VERSION)
        except BaseException:
            con.rollback()
            raise
        else:
            con.commit()
    return report


def migrate_config(raw, known):
    """Normalize a legacy ``config.json`` to the current schema.

    Returns ``(normalized, archived)``. A configuration written by this build
    (``config_version`` present) is passed through untouched so typos are still
    rejected by validation; a legacy file keeps every known setting, gets the
    version marker and returns unknown keys so the caller can archive them
    instead of silently dropping them.
    """
    if not isinstance(raw, dict):
        raise MigrationError("Configuration must be an object.")
    if raw.get("config_version") == CONFIG_VERSION:
        return dict(raw), {}
    archived = {k: v for k, v in raw.items() if k not in known and k != "config_version"}
    normalized = {k: v for k, v in raw.items() if k in known}
    normalized["config_version"] = CONFIG_VERSION
    return normalized, archived
