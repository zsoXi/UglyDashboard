"""V6 incremental usage aggregation: durable, idempotent, resumable.

These tests pin the Etap C contract: usage totals are aggregated over ALL
usage-bearing parts in ascending key order, the cursor is committed together
with the accumulated usage, and a cycle that runs out of budget resumes from
the committed checkpoint instead of restarting or losing tokens.
"""

import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import mission_control as mc
from mission_control import incremental as inc


class SeqClock:
    """Monotonic clock stub: pops the next value, then stays on the last one."""

    def __init__(self, values):
        self.values = list(values)
        self.last = self.values[-1] if self.values else 0.0

    def __call__(self):
        if self.values:
            self.last = self.values.pop(0)
        return self.last


def _step_finish(total, input_tokens=None):
    tokens = {
        "input": total if input_tokens is None else input_tokens,
        "output": 0,
        "reasoning": 0,
        "total": total,
    }
    return json.dumps({"type": "step-finish", "tokens": tokens, "cost": 0.0})


def make_parts_db(root, sessions):
    """sessions: {session_id: [(time_created, part_id, tokens_total), ...]}"""
    db = Path(root) / "incremental.db"
    con = sqlite3.connect(db)
    try:
        con.execute(
            "CREATE TABLE part(id TEXT PRIMARY KEY, session_id TEXT, message_id TEXT,"
            " time_created INTEGER, data TEXT)"
        )
        for sid, parts in sessions.items():
            for ts, pid, total in parts:
                con.execute(
                    "INSERT INTO part VALUES(?,?,?,?,?)",
                    (pid, sid, sid + "-m", ts, _step_finish(total)),
                )
        con.commit()
    finally:
        con.close()
    return db


def run_aggregate(db, sessions, checkpoints, budget=5.0, state=None):
    committed = {}
    with mc.readonly_db(str(db)) as con:
        summary = inc.aggregate_source(
            con,
            sessions,
            checkpoints,
            time.monotonic() + budget,
            lambda sid, st: committed.__setitem__(sid, st),
            state=state,
        )
    return committed, summary


class IncrementalAggregationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_forward_pass_totals_all_parts_and_is_idempotent(self):
        db = make_parts_db(
            self.root,
            {
                "a": [(1, "a1", 10), (2, "a2", 20), (3, "a3", 30)],
                "b": [(1, "b1", 5), (2, "b2", 15)],
            },
        )
        checkpoints = {}
        committed, summary = run_aggregate(db, [("a", 3), ("b", 2)], checkpoints)
        self.assertEqual(summary["complete"], 2)
        self.assertEqual(summary["pending"], 0)
        self.assertEqual(committed["a"]["usage"]["total"], 60)
        self.assertEqual(committed["b"]["usage"]["total"], 20)
        self.assertTrue(checkpoints["a"]["complete"])

        # Re-running the same material must not change any sum. A completed
        # session is skipped without a new commit, so the persisted checkpoints
        # are the source of truth here.
        before = {sid: checkpoints[sid]["usage"]["total"] for sid in checkpoints}
        _committed2, summary2 = run_aggregate(db, [("a", 3), ("b", 2)], checkpoints)
        after = {sid: checkpoints[sid]["usage"]["total"] for sid in checkpoints}
        self.assertEqual(before, after)
        self.assertEqual(summary2["complete"], 2)
        self.assertEqual(summary2["pending"], 0)
        self.assertEqual(checkpoints["a"]["usage"]["total"], 60)
        self.assertEqual(checkpoints["b"]["usage"]["total"], 20)

    def test_budget_stop_resumes_from_committed_cursor(self):
        db = make_parts_db(self.root, {"a": [(1, "a1", 7), (2, "a2", 11), (3, "a3", 13)]})
        checkpoint = inc.empty_checkpoint()
        committed = {}

        def commit(state):
            committed["a"] = json.loads(json.dumps(state))

        # First pass: one page of two parts, then the budget is exhausted. The
        # clock is patched inside the read-only scope, so the connection's own
        # progress guard keeps using the real clock and never interrupts.
        with mc.readonly_db(str(db)) as con:
            with mock.patch.object(
                inc.time, "monotonic", SeqClock([0.0, 99.0, 99.0, 99.0])
            ):
                state = inc.aggregate_session(con, "a", checkpoint, 10.0, commit, page=2)
        self.assertFalse(state["complete"])
        self.assertEqual(state["parts"], 2)
        self.assertEqual(state["usage"]["total"], 18)
        self.assertIsNotNone(state["cursor"])

        # Second pass resumes from the cursor and accounts the remaining part.
        checkpoint = committed["a"]
        with mc.readonly_db(str(db)) as con:
            with mock.patch.object(inc.time, "monotonic", SeqClock([0.0] * 8)):
                state2 = inc.aggregate_session(con, "a", checkpoint, 10.0, commit, page=2)
        self.assertTrue(state2["complete"])
        self.assertEqual(state2["parts"], 3)
        self.assertEqual(state2["usage"]["total"], 31)

    def test_appended_parts_add_only_their_own_contribution(self):
        db = make_parts_db(self.root, {"a": [(1, "a1", 10), (2, "a2", 20)]})
        checkpoints = {}
        run_aggregate(db, [("a", 2)], checkpoints)
        self.assertEqual(checkpoints["a"]["usage"]["total"], 30)

        con = sqlite3.connect(str(db))
        try:
            con.execute(
                "INSERT INTO part VALUES(?,?,?,?,?)",
                ("a3", "a", "a-m", 3, _step_finish(5)),
            )
            con.execute(
                "INSERT INTO part VALUES(?,?,?,?,?)",
                ("a4", "a", "a-m", 4, _step_finish(6)),
            )
            con.commit()
        finally:
            con.close()

        run_aggregate(db, [("a", 2)], checkpoints)
        self.assertEqual(checkpoints["a"]["usage"]["total"], 41)
        self.assertTrue(checkpoints["a"]["complete"])
        self.assertEqual(checkpoints["a"]["parts"], 4)

        # A third, identical read changes nothing.
        run_aggregate(db, [("a", 2)], checkpoints)
        self.assertEqual(checkpoints["a"]["usage"]["total"], 41)

    def test_rewritten_shorter_source_resets_instead_of_keeping_old_total(self):
        db = make_parts_db(self.root, {"a": [(1, "a1", 10), (2, "a2", 20), (3, "a3", 30)]})
        checkpoints = {}
        run_aggregate(db, [("a", 3)], checkpoints)
        self.assertEqual(checkpoints["a"]["usage"]["total"], 60)

        # Simulate a rewrite: the old parts are gone, the new generation is smaller.
        con = sqlite3.connect(str(db))
        try:
            con.execute("DELETE FROM part WHERE session_id='a'")
            con.execute(
                "INSERT INTO part VALUES(?,?,?,?,?)",
                ("n1", "a", "a-m", 10, _step_finish(4)),
            )
            con.commit()
        finally:
            con.close()

        run_aggregate(db, [("a", 3)], checkpoints)
        self.assertEqual(checkpoints["a"]["usage"]["total"], 4)
        self.assertTrue(checkpoints["a"]["complete"])

    def test_rotation_gives_every_session_a_chance(self):
        db = make_parts_db(
            self.root,
            {
                "huge": [(i, "h%d" % i, 1) for i in range(20)],
                "small1": [(1, "s1", 2)],
                "small2": [(1, "s2", 3)],
            },
        )
        checkpoints = {}
        state = {"next_index": 0}

        # One cycle that stops right after the first session. The clock is
        # patched inside the read-only scope and stays below the connection's
        # 12 s progress guard, so no query is interrupted.
        with mc.readonly_db(str(db)) as con:
            with mock.patch.object(
                inc.time, "monotonic", SeqClock([0.0, 0.0, 1.0, 1.0, 1.0, 1.0])
            ):
                summary = inc.aggregate_source(
                    con,
                    [("huge", 30), ("small1", 20), ("small2", 10)],
                    checkpoints,
                    deadline=0.5,
                    commit=lambda sid, st: checkpoints.__setitem__(sid, st),
                    state=state,
                )
        self.assertEqual(state["next_index"], 1)
        self.assertLess(summary["complete"], 3)
        self.assertIn("huge", checkpoints)

        # The next cycle starts with the next session, not with the huge one.
        with mc.readonly_db(str(db)) as con:
            with mock.patch.object(inc.time, "monotonic", SeqClock([0.0] * 64)):
                inc.aggregate_source(
                    con,
                    [("huge", 30), ("small1", 20), ("small2", 10)],
                    checkpoints,
                    deadline=10.0,
                    commit=lambda sid, st: checkpoints.__setitem__(sid, st),
                    state=state,
                )
        self.assertIn("small1", checkpoints)
        self.assertTrue(checkpoints["small1"]["complete"])


class EngineFullCoverageTests(unittest.TestCase):
    """The engine must reach 1000/1000-style complete aggregates over cycles."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.db = self.root / "opencode.db"
        con = sqlite3.connect(self.db)
        try:
            con.executescript(
                """CREATE TABLE project(id TEXT PRIMARY KEY,name TEXT,worktree TEXT);
                CREATE TABLE session(id TEXT PRIMARY KEY,project_id TEXT,parent_id TEXT,
                    directory TEXT,title TEXT,time_created INTEGER,time_updated INTEGER);
                CREATE TABLE message(id TEXT PRIMARY KEY,session_id TEXT,time_created INTEGER,data TEXT);
                CREATE TABLE part(id TEXT PRIMARY KEY,session_id TEXT,message_id TEXT,
                    time_created INTEGER,data TEXT);"""
            )
            con.execute("INSERT INTO project VALUES('p','P','C:/work')")
            expected = 0
            self.expected = {}
            for index in range(3):
                sid = "s%d" % index
                con.execute(
                    "INSERT INTO session VALUES(?,?,?,?,?,?,?)",
                    (sid, "p", None, "C:/work", "Session %d" % index, 1000 + index, 2000 + index),
                )
                con.execute(
                    "INSERT INTO message VALUES(?,?,?,?)",
                    (sid + "-m", sid, 2000 + index, json.dumps({"role": "assistant", "agent": "a", "modelID": "m", "providerID": "pv"})),
                )
                for j in range(4):
                    total = 10 * (index + 1) + j
                    con.execute(
                        "INSERT INTO part VALUES(?,?,?,?,?)",
                        ("%s-p%d" % (sid, j), sid, sid + "-m", 100 + j, _step_finish(total)),
                    )
                    expected += total
            con.commit()
            self.expected_total = expected
        finally:
            con.close()

    def _engine(self):
        overrides = {
            "db_paths": [str(self.db)],
            "opencode_urls": [],
            "codex_homes": [],
            "router_events": [],
            "git_enabled": False,
            "projects": [],
            "poll_seconds": 3,
        }
        engine = mc.Engine(str(self.root / "state"), overrides)
        self.addCleanup(engine.close)
        return engine

    def test_poll_reaches_complete_aggregates_without_changing_sums(self):
        engine = self._engine()
        engine.poll()
        src = next(s for s in engine.view()["sources"] if s["kind"] == "database")
        self.assertTrue(src["aggregates_complete"])
        self.assertEqual(src["pending_sessions"], 0)
        self.assertEqual(src["aggregate_sessions_complete"], 3)
        total = sum(s["usage"]["total"] for s in engine.sessions.values())
        self.assertEqual(total, self.expected_total)

        # A second cycle must not add or lose a single token.
        engine.poll()
        total2 = sum(s["usage"]["total"] for s in engine.sessions.values())
        self.assertEqual(total2, self.expected_total)
        src2 = next(s for s in engine.view()["sources"] if s["kind"] == "database")
        self.assertTrue(src2["aggregates_complete"])


if __name__ == "__main__":
    unittest.main()
