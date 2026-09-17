"""C.1 precise coverage-contract regressions.

The dashboard must never present a complete total as a complete per-day,
per-model or per-file split, and it must never invent a freshness timestamp or
a progress denominator. These tests pin the shared contract used by the
snapshot (UI/overview), analytics, exports and MCP:

* full aggregates with a limited detail window stay "complete totals /
  partial details";
* aggregates that are still catching up are reported as catching up;
* a failed aggregate pass yields an unknown progress denominator, not zero;
* a failed read keeps the last successful read timestamp and marks the source
  stale instead of blocked;
* a blocked read makes no metadata or progress claims at all;
* range coverage describes the selected time/source scope, not the whole file,
  and stays consistent between HTTP surfaces and MCP.
"""

import csv
import json
import os
import sqlite3
import threading
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import mission_control as mc
import mission_control.engine as engine_mod
import test_mission_control as tmc

OVERRIDES = {
    "db_paths": [],
    "codex_homes": [],
    "router_events": [],
    "opencode_urls": [],
    "git_enabled": False,
}


def coverage_db(root, spec, project_name="Coverage campus"):
    """Build a bounded OpenCode database: session id -> list of part totals."""
    db = Path(root) / "coverage.db"
    project = str(Path(root) / project_name)
    Path(project).mkdir(exist_ok=True)
    con = sqlite3.connect(db)
    try:
        con.executescript(
            """CREATE TABLE project(id TEXT PRIMARY KEY,name TEXT,worktree TEXT);
            CREATE TABLE session(id TEXT PRIMARY KEY,project_id TEXT,parent_id TEXT,
                directory TEXT,title TEXT,time_created INTEGER,time_updated INTEGER);
            CREATE TABLE message(id TEXT PRIMARY KEY,session_id TEXT,
                time_created INTEGER,data TEXT);
            CREATE TABLE part(id TEXT PRIMARY KEY,session_id TEXT,message_id TEXT,
                time_created INTEGER,data TEXT);"""
        )
        con.execute("INSERT INTO project VALUES(?,?,?)", ("p", project_name, project))
        now = mc.now_ms()
        for index, (sid, totals) in enumerate(spec):
            con.execute(
                "INSERT INTO session VALUES(?,?,?,?,?,?,?)",
                (
                    sid,
                    "p",
                    None,
                    project,
                    "Session " + sid,
                    now - 200000 - index * 1000,
                    now - 1000 - index * 10,
                ),
            )
            con.execute(
                "INSERT INTO message VALUES(?,?,?,?)",
                (
                    sid + "-a",
                    sid,
                    now - 50000,
                    json.dumps(
                        {
                            "role": "assistant",
                            "agent": "fx",
                            "modelID": "fx-model",
                            "providerID": "fx",
                            "time": {"created": now - 60000},
                        }
                    ),
                ),
            )
            for pi, tokens in enumerate(totals):
                con.execute(
                    "INSERT INTO part VALUES(?,?,?,?,?)",
                    (
                        "%s-p%d" % (sid, pi),
                        sid,
                        sid + "-a",
                        now - 40000 + pi,
                        json.dumps(
                            {
                                "type": "step-finish",
                                "tokens": {
                                    "input": tokens,
                                    "output": 0,
                                    "reasoning": 0,
                                    "total": tokens,
                                },
                                "cost": 0.0,
                            }
                        ),
                    ),
                )
        con.commit()
    finally:
        con.close()
    return str(db), project


class CoverageBase(tmc.Base):
    def engine(self, db, **extra):
        e = mc.Engine(self.root / "state", {**OVERRIDES, "db_paths": [db], **extra})
        self.addCleanup(e.close)
        return e


class SnapshotCoverageTests(CoverageBase):
    def test_precise_complete_snapshot(self):
        db, _ = coverage_db(self.root, [("a", [5, 5]), ("b", [7])])
        e = self.engine(db)
        e.poll()
        snap = e.view()
        cov = snap["coverage"]
        self.assertEqual(cov["scope"]["kind"], "snapshot")
        self.assertEqual(cov["scope"]["sessions_loaded"], 2)
        self.assertIs(cov["metadata_complete"], True)
        self.assertIs(cov["aggregates_complete"], True)
        self.assertFalse(cov["history_limited"])
        self.assertEqual(
            cov["breakdowns"],
            {"daily": "complete", "model": "complete", "file": "complete"},
        )
        self.assertFalse(cov["details_truncated"])
        self.assertEqual(cov["detail_events_evicted"], 0)
        self.assertFalse(cov["catching_up"])
        self.assertFalse(cov["source_stale"])
        self.assertFalse(cov["read_blocked"])
        self.assertEqual(cov["discovered_sessions"], 2)
        self.assertEqual(cov["processed_sessions"], 2)
        self.assertIsNotNone(cov["last_successful_read_at"])
        self.assertEqual(snap["tokens"], 17)
        src = next(s for s in snap["sources"] if s["kind"] == "database")
        self.assertIs(src["metadata_complete"], True)
        self.assertEqual(
            src["breakdowns"],
            {"daily": "complete", "model": "complete", "file": "complete"},
        )
        # Percent processed sessions is available, but it is never a percent of
        # tokens: the contract exposes both counts, not a merged ratio.
        self.assertEqual(cov["breakdown_details"]["sessions_scored"], 2)

    def test_full_aggregates_with_limited_details(self):
        db, _ = coverage_db(self.root, [("big", [1] * 4001), ("small", [5, 5])])
        e = self.engine(db)
        e.poll()
        snap = e.view()
        cov = snap["coverage"]
        self.assertEqual(snap["tokens"], 4011)
        self.assertIs(cov["aggregates_complete"], True)
        self.assertIs(cov["metadata_complete"], True)
        self.assertFalse(cov["catching_up"])
        self.assertTrue(cov["details_truncated"])
        self.assertEqual(cov["detail_events_evicted"], 1)
        self.assertEqual(
            cov["breakdowns"],
            {"daily": "partial", "model": "partial", "file": "partial"},
        )
        self.assertEqual(cov["discovered_sessions"], 2)
        self.assertEqual(cov["processed_sessions"], 2)
        totals = {s["id"]: s["usage"]["total"] for s in e.sessions.values()}
        self.assertEqual(sorted(totals.values()), [10, 4001])

    def test_catching_up_aggregates_settle(self):
        db, _ = coverage_db(self.root, [("a", [1, 2, 3]), ("b", [4])])
        e = self.engine(db)
        with mock.patch.object(engine_mod, "AGGREGATE_BUDGET_SECONDS", -1):
            e.poll()
        cov = e.view()["coverage"]
        self.assertIs(cov["aggregates_complete"], False)
        self.assertTrue(cov["catching_up"])
        self.assertEqual(cov["processed_sessions"], 0)
        self.assertEqual(cov["discovered_sessions"], 2)
        self.assertIs(cov["metadata_complete"], True)
        self.assertTrue(e.analytics()["coverage"]["catching_up"])
        e.poll()
        cov = e.view()["coverage"]
        self.assertIs(cov["aggregates_complete"], True)
        self.assertFalse(cov["catching_up"])
        self.assertEqual(cov["processed_sessions"], 2)
        self.assertEqual(e.view()["tokens"], 10)

    def test_unknown_denominator_when_aggregate_fails(self):
        db, _ = coverage_db(self.root, [("a", [4])])
        e = self.engine(db)
        e.poll()
        with mock.patch.object(engine_mod, "aggregate_source", side_effect=RuntimeError("boom")):
            e.poll()
        cov = e.view()["coverage"]
        self.assertIs(cov["metadata_complete"], True)
        self.assertIs(cov["aggregates_complete"], False)
        self.assertIsNone(cov["processed_sessions"])
        self.assertTrue(cov["catching_up"])
        self.assertEqual(cov["discovered_sessions"], 1)

    def test_stale_previous_result_keeps_last_success(self):
        db, _ = coverage_db(self.root, [("a", [6])])
        e = self.engine(db)
        e.poll()
        first = e.view()["coverage"]
        stat = os.stat(db)
        os.utime(db, ns=(stat.st_atime_ns + 10**9, stat.st_mtime_ns + 10**9))
        with mock.patch.object(engine_mod, "read_opencode", side_effect=RuntimeError("gone")):
            e.poll()
        cov = e.view()["coverage"]
        self.assertTrue(cov["source_stale"])
        self.assertFalse(cov["read_blocked"])
        self.assertEqual(cov["last_successful_read_at"], first["last_successful_read_at"])
        self.assertEqual(cov["discovered_sessions"], 1)
        self.assertEqual(e.view()["tokens"], 6)

    def test_blocked_read_has_no_metadata_claims(self):
        e = self.engine(str(self.root / "does-not-exist.db"))
        e.poll()
        cov = e.view()["coverage"]
        self.assertTrue(cov["read_blocked"])
        self.assertIsNone(cov["metadata_complete"])
        self.assertIsNone(cov["discovered_sessions"])
        self.assertIsNone(cov["processed_sessions"])
        self.assertIs(cov["aggregates_complete"], False)
        self.assertEqual(cov["breakdowns"]["daily"], "unknown")
        self.assertEqual(cov["breakdown_details"]["sessions_scored"], 0)


class RangeCoverageTests(CoverageBase):
    def test_range_scope_follows_the_selected_filter(self):
        db, project = coverage_db(self.root, [("a", [10]), ("b", [20])])
        e = self.engine(db)
        e.poll()
        result = e.analytics()
        cov = result["coverage"]
        self.assertEqual(
            cov["scope"],
            {
                "kind": "range",
                "days": 0,
                "project": "",
                "task_group": "",
                "source": "",
                "sessions_in_range": 2,
            },
        )
        self.assertEqual(
            cov["breakdowns"],
            {"daily": "complete", "model": "complete", "file": "complete"},
        )
        self.assertIs(cov["aggregates_complete"], True)
        self.assertEqual(cov["detail_events_evicted"], 0)
        self.assertEqual(result["tokens"], 30)
        filtered = e.analytics(project=project)
        self.assertEqual(filtered["coverage"]["scope"]["sessions_in_range"], 2)
        empty = e.analytics(project=str(self.root / "elsewhere"))
        self.assertEqual(empty["coverage"]["scope"]["sessions_in_range"], 0)
        self.assertEqual(empty["coverage"]["breakdowns"]["daily"], "unknown")
        self.assertEqual(empty["tokens"], 0)


class CoverageSurfaceConsistencyTests(tmc.Base):
    def setUp(self):
        super().setUp()
        self.db, self.project = coverage_db(self.root, [("a", [4]), ("b", [6])])
        self.e = mc.Engine(self.root / "state", {**OVERRIDES, "db_paths": [self.db]})
        self.e.poll()
        self.srv = mc.Server(("127.0.0.1", 0), self.e)
        self.port = self.srv.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()
        self.http = build_opener(ProxyHandler({}), mc.NoRedirect())

    def tearDown(self):
        self.e.close()
        self.t.join()
        super().tearDown()

    def raw(self, path):
        req = Request(
            self.url + path,
            headers={"Authorization": "Bearer " + self.e.control_token},
        )
        try:
            r = self.http.open(req, timeout=5)
            status, headers_out, body = r.status, dict(r.headers), r.read()
            r.close()
        except HTTPError as ex:
            status, headers_out, body = ex.code, dict(ex.headers), ex.read()
            ex.close()
        try:
            out = json.loads(body)
        except ValueError:
            out = body.decode("utf-8", "replace")
        return status, out, headers_out

    def test_overview_export_and_mcp_share_one_coverage_contract(self):
        status, overview, _ = self.raw("/api/overview")
        self.assertEqual(status, 200)
        self.assertEqual(overview["coverage"], self.e.view()["coverage"])
        status, exported, _ = self.raw("/api/export?format=json&days=30")
        self.assertEqual(status, 200)
        self.assertEqual(exported["overview"]["coverage"], self.e.view()["coverage"])
        analytics_cov = exported["analytics"]["coverage"]
        self.assertEqual(analytics_cov["scope"]["kind"], "range")
        shared = (
            "metadata_complete",
            "aggregates_complete",
            "history_limited",
            "catching_up",
            "source_stale",
            "read_blocked",
            "discovered_sessions",
            "processed_sessions",
            "last_successful_read_at",
        )
        for key in shared:
            self.assertEqual(analytics_cov[key], overview["coverage"][key], key)
        status, csv_text, headers = self.raw("/api/export?format=csv&days=30")
        self.assertEqual(status, 200)
        lowered = {k.lower(): v for k, v in headers.items()}
        header_cov = json.loads(lowered["x-mission-control-coverage"])
        for key in (
            "metadata_complete",
            "aggregates_complete",
            "catching_up",
            "source_stale",
            "read_blocked",
            "details_truncated",
            "detail_events_evicted",
            "breakdowns",
        ):
            self.assertEqual(header_cov[key], analytics_cov[key], key)
        # A downloaded file must explain its own completeness, not rely on the
        # response header: a trailing "# coverage" metadata row carries it.
        body_cov = next(
            json.loads(row[1])
            for row in csv.reader(csv_text.splitlines())
            if row and row[0] == "# coverage"
        )
        self.assertEqual(body_cov, header_cov)
        auth = {
            "role": "owner",
            "scopes": ["mission:read", "mission:report"],
            "client_id": "coverage-test",
        }
        call = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "mission_overview", "arguments": {}},
        }
        resp = self.srv.mcp.dispatch(call, auth)
        self.assertFalse(resp["result"]["isError"])
        self.assertEqual(resp["result"]["structuredContent"]["coverage"], self.e.view()["coverage"])
        call["id"] = 2
        call["params"] = {"name": "model_comparison", "arguments": {}}
        resp = self.srv.mcp.dispatch(call, auth)
        self.assertFalse(resp["result"]["isError"])
        self.assertEqual(
            resp["result"]["structuredContent"]["coverage"],
            self.e.analytics()["coverage"],
        )


if __name__ == "__main__":
    unittest.main()
