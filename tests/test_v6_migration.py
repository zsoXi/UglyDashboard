"""V6 observer-state migration regressions.

Only the private observer directory is migrated: the v5 database gains the
versioned ``meta`` marker and the durable ``usage_checkpoint`` table. Nothing
is rewritten, no credential is rotated, no source database is touched, and an
interrupted run can be retried. These tests pin the empty install, a real v5
state, an existing V6 state, interruption, write failure, a newer schema and
the CLI entrypoint.
"""

import json
import sqlite3
import unittest
from unittest import mock

import mission_control as mc
import mission_control.cli as cli_mod
import mission_control.migration as migration_mod
import test_mission_control as tmc

OVERRIDES = {
    "db_paths": [],
    "codex_homes": [],
    "router_events": [],
    "opencode_urls": [],
    "git_enabled": False,
}

V5_SCHEMA = """CREATE TABLE event(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
    ts INTEGER NOT NULL, session_id TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL);
CREATE INDEX event_time ON event(ts DESC);
CREATE INDEX event_session ON event(session_id, ts DESC);
CREATE TABLE setting(key TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE report(id TEXT PRIMARY KEY, ts INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE assessment(session_id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE oauth_client(id TEXT PRIMARY KEY, data TEXT NOT NULL);"""

SECRETS = {
    "owner.token": "owner_" + "a" * 40,
    "mcp.token": "mcp_" + "b" * 40,
    "pairing.key": "pair_" + "c" * 40,
}

LEGACY_CONFIG = {
    "poll_seconds": 15,
    "show_prompts": False,
    "pricing": {"m": {"input": 1}},
    "projects": ["C:/x"],
    "legacy_setting": "keep",
}

COUNT_TABLES = ("event", "setting", "report", "assessment", "oauth_client")


def table_counts(con):
    counts = {}
    for name in COUNT_TABLES:
        try:
            counts[name] = con.execute("SELECT COUNT(*) FROM " + name).fetchone()[0]
        except sqlite3.Error:
            counts[name] = None
    return counts


class MigrationTests(tmc.Base):
    def build_v5_state(self):
        state = self.root / "state"
        state.mkdir(parents=True)
        db = state / "observer.sqlite"
        con = sqlite3.connect(db)
        try:
            con.executescript(V5_SCHEMA)
            con.execute(
                "INSERT INTO event(id, ts, session_id, kind, data) VALUES(?,?,?,?,?)",
                ("e1", 1, "opencode:s1", "tool", "{}"),
            )
            con.execute(
                "INSERT INTO setting(key, data) VALUES(?,?)",
                ("acknowledged", json.dumps([1])),
            )
            con.execute("INSERT INTO setting(key, data) VALUES(?,?)", ("codex_cursor", "3"))
            con.execute(
                "INSERT INTO report(id, ts, data) VALUES(?,?,?)",
                ("r1", 1, json.dumps({"session_id": "opencode:s1"})),
            )
            con.execute(
                "INSERT INTO assessment(session_id, data) VALUES(?,?)",
                ("opencode:s1", json.dumps({"task_group": "g1"})),
            )
            con.execute(
                "INSERT INTO oauth_client(id, data) VALUES(?,?)",
                ("c1", json.dumps({"client_name": "probe"})),
            )
            con.commit()
        finally:
            con.close()
        (state / "config.json").write_text(json.dumps(LEGACY_CONFIG), "utf-8")
        for name, value in SECRETS.items():
            (state / name).write_text(value + "\n", "utf-8")
        return state

    def open_engine(self, state):
        engine = mc.Engine(state, dict(OVERRIDES))
        self.addCleanup(engine.close)
        return engine

    def backups(self, state):
        return sorted((state).glob("observer.sqlite.pre-migration-v1-to-v2-*"))

    def test_fresh_install_marks_current_schema(self):
        engine = self.open_engine(self.root / "fresh")
        report = engine.store.migration
        self.assertFalse(report["migrated"])
        self.assertEqual(report["version"], mc.SCHEMA_VERSION)
        self.assertEqual(engine.config()["config_version"], mc.CONFIG_VERSION)
        self.assertEqual(self.backups(self.root / "fresh"), [])

    def test_v5_state_migrates_transactionally_and_preserves_data(self):
        state = self.build_v5_state()
        before_secrets = {name: (state / name).read_bytes() for name in SECRETS}
        engine = self.open_engine(state)
        report = engine.store.migration
        self.assertTrue(report["migrated"])
        self.assertEqual(report["from_version"], 1)
        self.assertEqual(report["version"], mc.SCHEMA_VERSION)
        backups = self.backups(state)
        self.assertEqual(len(backups), 1)

        main = sqlite3.connect(state / "observer.sqlite")
        backup = sqlite3.connect(backups[0])
        try:
            self.assertEqual(
                main.execute(
                    "SELECT value FROM meta WHERE key='schema_version'"
                ).fetchone()[0],
                str(mc.SCHEMA_VERSION),
            )
            self.assertEqual(
                main.execute("SELECT COUNT(*) FROM usage_checkpoint").fetchone()[0], 0
            )
            main_counts, backup_counts = table_counts(main), table_counts(backup)
            # Every legacy row survives the migration; the engine additionally
            # stores one migrated_config_backup setting after the upgrade.
            for table in ("event", "report", "assessment", "oauth_client"):
                self.assertEqual(main_counts[table], backup_counts[table])
            self.assertEqual(main_counts["setting"], backup_counts["setting"] + 1)
            self.assertIsNone(
                backup.execute(
                    "SELECT value FROM meta WHERE key='schema_version'"
                ).fetchone(),
            )
            self.assertEqual(table_counts(main)["event"], 1)
        finally:
            main.close()
            backup.close()

        for name, value in before_secrets.items():
            self.assertEqual((state / name).read_bytes(), value)
        self.assertEqual(list(state.glob("*.corrupt-*")), [])

        config = engine.config()
        self.assertEqual(config["poll_seconds"], 15)
        self.assertFalse(config["show_prompts"])
        self.assertEqual(config["pricing"], {"m": {"input": 1}})
        self.assertEqual(config["projects"], ["C:/x"])
        self.assertEqual(config["config_version"], mc.CONFIG_VERSION)
        on_disk = json.loads((state / "config.json").read_text("utf-8"))
        self.assertEqual(on_disk["config_version"], mc.CONFIG_VERSION)
        history = engine.store.setting("migrated_config_backup", [])
        self.assertEqual(len(history), 1)
        self.assertIn("legacy_setting", history[0]["keys"])

    def test_current_v6_state_is_untouched(self):
        state = self.root / "state"
        engine = self.open_engine(state)
        checkpoint = {
            "v": 1,
            "usage": {
                "input": 3,
                "output": 0,
                "reasoning": 0,
                "cache_read": 0,
                "cache_write": 0,
                "total": 3,
            },
            "cursor": None,
            "parts": 1,
            "complete": True,
            "updated": 123,
        }
        engine.store.put_checkpoints("opencode:x", [("s1", checkpoint)])
        engine.close()
        self.assertEqual(self.backups(state), [])

        reopened = self.open_engine(state)
        self.assertFalse(reopened.store.migration["migrated"])
        self.assertEqual(reopened.store.checkpoints("opencode:x")["s1"], checkpoint)
        self.assertEqual(self.backups(state), [])
        self.assertEqual(reopened.store.migration["version"], mc.SCHEMA_VERSION)

    def test_repeated_open_creates_no_second_backup(self):
        state = self.build_v5_state()
        engine = self.open_engine(state)
        engine.close()
        self.assertEqual(len(self.backups(state)), 1)
        again = self.open_engine(state)
        self.assertFalse(again.store.migration["migrated"])
        again.close()
        self.assertEqual(len(self.backups(state)), 1)

    def test_interrupted_migration_rolls_back_and_retries(self):
        state = self.build_v5_state()
        real = migration_mod._migrate_to_2

        def interrupted(con):
            real(con)
            raise RuntimeError("interrupted")

        with mock.patch.object(migration_mod, "_migrate_to_2", side_effect=interrupted):
            with self.assertRaises(RuntimeError):
                mc.Store(state)

        con = sqlite3.connect(state / "observer.sqlite")
        try:
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE name='usage_checkpoint'"
                ).fetchone()[0],
                0,
            )
            self.assertIsNone(
                con.execute(
                    "SELECT value FROM meta WHERE key='schema_version'"
                ).fetchone(),
            )
        finally:
            con.close()

        engine = self.open_engine(state)
        self.assertTrue(engine.store.migration["migrated"])
        con = sqlite3.connect(state / "observer.sqlite")
        try:
            self.assertEqual(table_counts(con)["event"], 1)
        finally:
            con.close()

    def test_write_error_rolls_back_and_retries(self):
        state = self.build_v5_state()
        failure = sqlite3.OperationalError("disk full")
        with mock.patch.object(migration_mod, "_write_version", side_effect=failure):
            with self.assertRaises(sqlite3.OperationalError):
                mc.Store(state)

        con = sqlite3.connect(state / "observer.sqlite")
        try:
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE name='usage_checkpoint'"
                ).fetchone()[0],
                0,
            )
            self.assertIsNone(
                con.execute(
                    "SELECT value FROM meta WHERE key='schema_version'"
                ).fetchone(),
            )
        finally:
            con.close()

        engine = self.open_engine(state)
        self.assertTrue(engine.store.migration["migrated"])

    def test_newer_schema_is_refused(self):
        state = self.root / "state"
        engine = self.open_engine(state)
        engine.close()
        con = sqlite3.connect(state / "observer.sqlite")
        try:
            con.execute("UPDATE meta SET value='99' WHERE key='schema_version'")
            con.commit()
        finally:
            con.close()

        with self.assertRaises(mc.MigrationError) as caught:
            mc.Store(state)
        self.assertIn("refusing", str(caught.exception))

        con = sqlite3.connect(state / "observer.sqlite")
        try:
            self.assertEqual(
                con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0],
                "99",
            )
        finally:
            con.close()

    def test_cli_migrates_and_refuses_running_observer(self):
        state = self.build_v5_state()
        self.assertEqual(cli_mod.migrate_state(state), 0)
        con = sqlite3.connect(state / "observer.sqlite")
        try:
            self.assertEqual(
                con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0],
                str(mc.SCHEMA_VERSION),
            )
        finally:
            con.close()
        self.assertEqual(cli_mod.migrate_state(state), 0)

        second = self.root / "second"
        second.mkdir()
        (second / "observer.sqlite").write_bytes(b"")
        (second / "runtime.json").write_text(json.dumps({"port": 9}), "utf-8")
        with mock.patch.object(
            cli_mod, "local_json", return_value={"application": "opencode-mission-control"}
        ):
            self.assertEqual(cli_mod.migrate_state(second), 2)
        con = sqlite3.connect(second / "observer.sqlite")
        try:
            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE name='meta'"
                ).fetchone()[0],
                0,
            )
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
