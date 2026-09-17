# Observer state migration (v5 → V6)

Mission Control keeps its own private state in the observer directory
(`~/.opencode-mission-control` by default, or `--state-dir`). This document
describes the versioned migration that upgrades that directory from the v5
layout to the V6 layout.

The migration only touches the private observer directory. **OpenCode and
Codex source databases are never opened for writing and are never migrated.**
Credentials are never rotated.

## What changes

| Item | v5 (schema v1) | V6 (schema v2) |
| --- | --- | --- |
| Observer DB tables | `event`, `setting`, `report`, `assessment`, `oauth_client` | identical + `meta`, `usage_checkpoint` |
| Schema marker | none | `meta.schema_version = 2` |
| Configuration file | `config.json` without a version marker | `config.json` with `config_version: 2` |

Nothing is rewritten and no row is dropped:

* `usage_checkpoint` starts empty. Existing sessions are re-aggregated
  incrementally by the next collector cycles, exactly like a fresh install.
  Until that catches up, the coverage block reports `catching_up: true` and
  `aggregates_complete: false` instead of pretending the totals are final.
* Every known setting from the legacy `config.json` keeps its exact value.
* Unknown legacy configuration keys (if any) are not silently dropped: they
  are archived into the observer setting `migrated_config_backup` (the last
  10 archive entries are kept) and written to the log. Current-format files
  still reject unknown keys, so typos do not go unnoticed.

## What is never touched

* OpenCode SQLite databases and Codex session logs (read-only sources).
* `owner.token`, `mcp.token`, `pairing.key` — byte-identical before and after;
  no secret is created, rotated or quarantined by the migration.
* `observer.sqlite-wal` / `observer.sqlite-shm` sidecars are never deleted and
  never copied alone. Backups use the SQLite backup API, which produces a
  consistent snapshot including WAL content.

## Backup

Before the first change to a database that already holds rows, a consistent
copy is written next to it:

```text
observer.sqlite.pre-migration-v1-to-v2-20260917-013745
```

If a file with that name exists, a numeric suffix is added. A fresh,
row-less database is not backed up (nothing to preserve).

Restore procedure:

1. Stop the observer instance that uses the directory.
2. Keep the WAL sidecars (`observer.sqlite-wal`, `observer.sqlite-shm`)
   in place or move them together with the main file — never a lone main file.
3. Copy the backup over `observer.sqlite`.
4. Start the previous build again.

## Transactionality and interruption

The upgrade runs as one explicit SQL transaction (`BEGIN` … `COMMIT`). Python's
sqlite3 module does not wrap DDL statements in an implicit transaction, so the
migration issues an explicit `BEGIN` — this is what makes rollback real for the
`CREATE TABLE` as well.

* If the process is interrupted or a write fails, the transaction is rolled
  back: no `usage_checkpoint` table and no `schema_version` row survive. (The
  empty `meta` table itself may exist — it is created idempotently before the
  transaction and carries no state.)
* Re-running the migration on the same directory is safe and simply completes
  the upgrade. Migration is idempotent: a directory already at schema v2 is
  left untouched and reports `migrated: false`.
* A state directory written by a **newer** build is refused with a clear error
  instead of being downgraded or modified.

## Running the migration

The engine migrates lazily: any start of the application upgrades the observer
directory before the observer DB schema is used. To upgrade explicitly (for
example before packaging a state directory), use:

```text
python -X utf8 opencode_dashboard.py --migrate-state --state-dir <path>
```

* While a healthy observer still answers on the recorded port, the command
  refuses to run and exits with code `2`. Stop the instance first. A stale
  `runtime.json` is tolerated (the health check decides).
* Exit code `1` means the migration refused to proceed (for example a newer
  schema); the directory was not modified.
* Exit code `0` reports either a completed upgrade (with the backup path) or
  that the directory is already current.

## Operational warnings

* Never point two different application versions at the same state directory at
  the same time. The schema marker is the guard; it is not a multi-writer lock.
* Never delete `-wal`/`-shm` sidecars by hand. Stop the observer cleanly and let
  SQLite checkpoint them.
* The migration does not repair or recompute historical usage; it only adds the
  durable structure the V6 collector uses. Historical totals become complete
  again incrementally, and coverage states exactly what remains pending.
