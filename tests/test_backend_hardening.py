"""DS-2 backend hardening regressions.

Adds negative/lifecycle coverage on top of ``test_mission_control`` for the
areas DS-2 owns: deterministic close/context managers, bounded state caches,
revision-keyed analytics caches, cross-thread credential lock timeouts,
visible diagnostics for rejected router numbers, launcher-path stability and
HTTP request-hardening (Host/Origin, body limits, duplicate fields, methods).

Every fixture lives in a temporary directory; no real project, credential or
source database is ever opened.
"""

import json
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import mission_control as mc
import mission_control.engine as engine_mod
import mission_control.locking as locking
import test_mission_control as tmc

OVERRIDES = {
    "db_paths": [],
    "codex_homes": [],
    "router_events": [],
    "opencode_urls": [],
    "git_enabled": False,
}


class EngineBase(tmc.Base):
    def make_engine(self, extras=None):
        e = mc.Engine(self.root / "state", {**OVERRIDES, **(extras or {})})
        self.addCleanup(e.close)
        return e


class LifecycleHardeningTests(EngineBase):
    def test_engine_context_manager_is_deterministic(self):
        e = mc.Engine(self.root / "state", dict(OVERRIDES))
        store = e.store
        with e:
            self.assertFalse(e._closed)
            self.assertFalse(store._closed)
        self.assertTrue(e._closed)
        self.assertTrue(store._closed)
        # Closing again is a no-op that still reports success.
        self.assertTrue(e.close())

    def test_engine_context_manager_closes_on_exception(self):
        e = mc.Engine(self.root / "state", dict(OVERRIDES))
        with self.assertRaises(RuntimeError):
            with e:
                raise RuntimeError("boom")
        self.assertTrue(e._closed)
        self.assertTrue(e.store._closed)

    def test_close_never_started_engine_is_idempotent(self):
        e = self.make_engine()
        self.assertFalse(e._closed)
        self.assertTrue(e.close())
        self.assertTrue(e._closed)
        self.assertTrue(e.close())

    def test_store_context_manager_closes_and_is_idempotent(self):
        s = mc.Store(self.root / "store2")
        with s:
            s.set_setting("k", 1)
            self.assertFalse(s._closed)
        self.assertTrue(s._closed)
        s.close()
        s.close()


class CacheBoundsTests(EngineBase):
    def test_state_and_cache_pruning_drops_stale_entries(self):
        e = self.make_engine()
        e.previous_states = {"keep:1": ("idle", "verified"), "ghost:1": ("running", "verified")}
        e.db_cache["/ghost/db"] = {"reader": None}
        e.router_cache["/ghost/router"] = {"reader": None}
        e.git_cache["/ghost/repo"] = (0.0, {})
        e._prune_state_tracking({"keep:1"}, e.config())
        self.assertEqual(list(e.previous_states), ["keep:1"])
        self.assertEqual(e.db_cache, {})
        self.assertEqual(e.router_cache, {})
        self.assertEqual(e.git_cache, {})

    def test_previous_states_hard_cap(self):
        e = self.make_engine()
        e.MAX_PREVIOUS_STATES = 3
        retained = {f"s{i}" for i in range(10)}
        e.previous_states = {sid: ("idle", "verified") for sid in retained}
        e._prune_state_tracking(retained, e.config())
        self.assertEqual(len(e.previous_states), 3)


class AnalyticsCacheHardeningTests(EngineBase):
    def make_engine(self, extras=None):
        db, project = tmc.fixture_db(self.root)
        e = mc.Engine(
            self.root / "state",
            {**OVERRIDES, "db_paths": [db], "projects": [project], **(extras or {})},
        )
        self.addCleanup(e.close)
        e.poll()
        return e

    def test_analytics_cache_is_keyed_by_filters(self):
        e = self.make_engine()
        e.analytics(source="opencode")
        e.analytics(source="codex")
        e.analytics()
        self.assertEqual(len(e._analytics_cache), 3)
        first = e.analytics(source="opencode")
        self.assertEqual(e.analytics(source="opencode"), first)

    def test_poll_invalidates_analytics_cache(self):
        e = self.make_engine()
        e.analytics()
        self.assertTrue(e._analytics_cache)
        e.poll()
        self.assertEqual(len(e._analytics_cache), 0)

    def test_analytics_cache_is_bounded(self):
        e = self.make_engine()
        for days in range(1, 25):
            e.analytics(days=days)
        self.assertLessEqual(len(e._analytics_cache), e.ANALYTICS_CACHE_MAX)


class SecretLockHardeningTests(tmc.Base):
    def test_secret_lock_times_out_for_contending_thread(self):
        path = self.root / "cred.lock"
        outcome = {}

        def contending():
            try:
                with locking.secret_lock(path, timeout=0.2):
                    outcome["acquired"] = True
            except TimeoutError:
                outcome["timeout"] = True

        with locking.secret_lock(path, timeout=5):
            t = threading.Thread(target=contending)
            t.start()
            t.join(5)
        self.assertTrue(outcome.get("timeout"), outcome)
        self.assertNotIn("acquired", outcome)

    def test_secret_lock_is_reusable_after_release(self):
        path = self.root / "cred.lock"
        with locking.secret_lock(path, timeout=1):
            pass
        with locking.secret_lock(path, timeout=1):
            pass


class RouterDiagnosticsTests(EngineBase):
    def test_router_bad_numbers_are_reported_not_silently_zeroed(self):
        p = self.root / "router.jsonl"
        ts = datetime.now(timezone.utc).isoformat()
        rows = [
            {
                "at": ts,
                "model": "fixture",
                "provider": "fixture",
                "status": 200,
                "inputTokens": -5,
                "outputTokens": 3,
                "totalTokens": -100,
                "durationMs": "not-a-number",
            },
            {
                "at": ts,
                "model": "fixture",
                "provider": "fixture",
                "status": 500,
                "inputTokens": 10,
                "outputTokens": 5,
                "totalTokens": 20,
                "durationMs": 12,
            },
        ]
        p.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
        e = self.make_engine({"router_events": [str(p)]})
        e.poll()
        src = next(s for s in e.view()["sources"] if s["kind"] == "router")
        rejected = src.get("rejected_records") or {}
        self.assertGreaterEqual(rejected.get("rejected_total", 0), 1)
        counts = rejected.get("counts", {})
        self.assertTrue(any(key.endswith(":negative") for key in counts), counts)
        self.assertIn("router.duration_ms:not-a-number", counts)
        self.assertGreaterEqual(e.view()["router"][0]["tokens"], 0)


class ScaleCoverageTests(EngineBase):
    """A huge OpenCode DB must degrade to bounded, honest partial coverage.

    The read-only connection enforces a hard 12s progress guard. Instead of
    letting that interrupt publish zero sessions, the reader keeps a soft
    deadline and the engine preserves the last complete snapshot.
    """

    def _engine(self, db, project):
        e = mc.Engine(
            self.root / "state",
            {**OVERRIDES, "db_paths": [db], "projects": [project]},
        )
        self.addCleanup(e.close)
        return e

    def test_reader_soft_deadline_returns_partial_coverage(self):
        db, _ = tmc.fixture_db(self.root)
        sessions, _dirs, coverage = mc.read_opencode(db, budget_seconds=0.0)
        # Never raises, always returns a tuple, and keeps the newest session.
        self.assertGreaterEqual(len(sessions), 1)
        # An already-expired budget stops after the newest session and reports
        # the truncation explicitly (deterministic even on coarse clocks).
        self.assertLess(coverage["loaded_sessions"], coverage["total_sessions"])
        self.assertTrue(coverage["deadline_exceeded"])
        self.assertTrue(coverage["truncated"])

    def test_engine_publishes_partial_read_and_marks_source_stale(self):
        db, project = tmc.fixture_db(self.root)
        e = self._engine(db, project)
        partial = (
            [],
            [],
            {
                "total_sessions": 3,
                "loaded_sessions": 0,
                "parts_loaded": 0,
                "truncated_sessions": 0,
                "deadline_exceeded": True,
                "truncated": True,
                "rejected_records": {"rejected_total": 0, "counts": {}, "samples": []},
            },
        )
        with mock.patch.object(engine_mod, "read_opencode", return_value=partial):
            e.poll()
        src = next(s for s in e.view()["sources"] if s["kind"] == "database")
        self.assertTrue(src.get("stale"))
        self.assertTrue(src.get("deadline_exceeded"))

    def test_engine_preserves_last_snapshot_when_read_fails(self):
        db, project = tmc.fixture_db(self.root)
        e = self._engine(db, project)
        e.poll()
        before = set(e.sessions)
        self.assertTrue(before)
        Path(db).touch()  # change the fingerprint so the cache misses
        with mock.patch.object(
            engine_mod, "read_opencode", side_effect=RuntimeError("transient")
        ):
            e.poll()
        self.assertEqual(set(e.sessions), before)
        src = next(s for s in e.view()["sources"] if s["kind"] == "database")
        self.assertFalse(src["ok"])
        self.assertTrue(src.get("stale"))


class LauncherPathTests(tmc.Base):
    def test_stdio_script_args_targets_existing_launcher(self):
        args = mc.stdio_script_args()
        if args == ["-m", "mission_control"]:
            self.skipTest("launcher file is not present next to the package")
        self.assertEqual(Path(args[-1]).name, "opencode_dashboard.py")
        self.assertTrue(Path(args[-1]).is_file())

    def test_launcher_path_points_at_package_root(self):
        self.assertEqual(mc.launcher_path().name, "opencode_dashboard.py")


class HttpHardeningTests(tmc.Base):
    def setUp(self):
        super().setUp()
        self.e = mc.Engine(
            self.root / "state",
            {**OVERRIDES, "db_paths": [], "git_enabled": False},
        )
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

    def raw(self, path, method="GET", data=None, token="owner", headers=None):
        h = dict(headers or {})
        if token == "owner":
            h["Authorization"] = "Bearer " + self.e.control_token
        elif token == "mcp":
            h["Authorization"] = "Bearer " + self.e.mcp_token
        elif token:
            h["Authorization"] = "Bearer " + str(token)
        req = Request(self.url + path, data=data, headers=h, method=method)
        try:
            r = self.http.open(req, timeout=5)
            status, headers_out, raw = r.status, dict(r.headers), r.read()
            r.close()
        except HTTPError as e:
            status, headers_out, raw = e.code, dict(e.headers), e.read()
            e.close()
        try:
            out = json.loads(raw)
        except ValueError:
            out = raw.decode("utf-8", "replace")
        return status, out, headers_out

    def test_delete_and_options_are_not_allowed(self):
        self.assertEqual(self.raw("/api/overview", method="DELETE", token=False)[0], 405)
        self.assertEqual(self.raw("/api/overview", method="OPTIONS", token=False)[0], 405)

    def test_oversized_body_rejected(self):
        blob = b"x" * (mc.MAX_BODY + 1)
        status, _, _ = self.raw(
            "/api/refresh",
            method="POST",
            data=blob,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)

    def test_duplicate_form_fields_rejected(self):
        status, _, _ = self.raw(
            "/oauth/token",
            method="POST",
            data=b"grant_type=a&grant_type=b",
            token=False,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(status, 400)

    def test_nonfinite_json_rejected(self):
        status, _, _ = self.raw(
            "/api/refresh",
            method="POST",
            data=b'{"n": NaN}',
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)

    def test_host_port_mismatch_denied(self):
        status, _, _ = self.raw(
            "/api/overview", headers={"Host": f"127.0.0.1:{self.port + 1}"}
        )
        self.assertEqual(status, 403)

    def test_unknown_static_path_not_served(self):
        for path in ("/secrets.json", "/web/app.js", "/../mission_control/cli.py"):
            status, body, _ = self.raw(path, token=False)
            self.assertEqual(status, 404, path)
            self.assertNotIn("def ", body if isinstance(body, str) else "")

    def test_reveal_from_foreign_origin_denied(self):
        status, _, _ = self.raw(
            "/api/reveal",
            method="POST",
            data=json.dumps({"name": "owner_token"}).encode(),
            headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
        )
        self.assertEqual(status, 403)

    def test_reveal_is_post_only(self):
        status, body, _ = self.raw("/api/reveal")
        self.assertEqual(status, 404)
        self.assertNotIn(self.e.control_token, body if isinstance(body, str) else "")

    def test_mcp_token_cannot_start_scan(self):
        status, _, _ = self.raw(
            "/api/scan",
            method="POST",
            data=json.dumps({"roots": ["x"], "depth": 1}).encode(),
            token="mcp",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 403)

    def test_scan_rejects_too_many_roots(self):
        status, _, _ = self.raw(
            "/api/scan",
            method="POST",
            data=json.dumps({"roots": [f"/tmp/root{i}" for i in range(21)], "depth": 1}).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
