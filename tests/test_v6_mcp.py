"""E.3 MCP protocol, completeness and security regressions.

The MCP surface must expose exactly the same data model as the UI and the
exports: stable tool names and fields, the shared coverage block, conditional
reporting and no path to settings, secrets, abort or shutdown. The stdio
bridge must keep stdout JSON-RPC-clean even when it is started from a foreign
working directory and the state directory contains spaces. Server logs must
never contain credentials or query strings.
"""

import json
import logging
import subprocess
import sys
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import mission_control as mc
import test_mission_control as tmc

OVERRIDES = {
    "db_paths": [],
    "codex_homes": [],
    "router_events": [],
    "opencode_urls": [],
    "git_enabled": False,
}

SUPPORTED_PROTOCOLS = ("2025-11-25", "2025-06-18")

READ_TOOLS = {
    "mission_overview",
    "list_agents",
    "agent_details",
    "list_projects",
    "timeline",
    "model_comparison",
    "alerts",
    "sources",
    "search",
    "fetch",
}


class McpTests(tmc.Base):
    def setUp(self):
        super().setUp()
        self.e = mc.Engine(self.root / "state", {**OVERRIDES, "db_paths": []})
        self.e.poll()
        self.srv = mc.Server(("127.0.0.1", 0), self.e)
        self.port = self.srv.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()
        self.http = build_opener(ProxyHandler({}), mc.NoRedirect())

    def tearDown(self):
        self.e.close()
        self.thread.join(timeout=10)
        super().tearDown()

    def raw(self, path, method="GET", data=None, token="owner", headers=None):
        prepared = dict(headers or {})
        if token == "owner":
            prepared["Authorization"] = "Bearer " + self.e.control_token
        elif token == "mcp":
            prepared["Authorization"] = "Bearer " + self.e.mcp_token
        elif token:
            prepared["Authorization"] = "Bearer " + str(token)
        req = Request(self.url + path, data=data, headers=prepared, method=method)
        try:
            res = self.http.open(req, timeout=5)
            status, out_headers, body = res.status, dict(res.headers), res.read()
            res.close()
        except HTTPError as ex:
            status, out_headers, body = ex.code, dict(ex.headers), ex.read()
            ex.close()
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = body.decode("utf-8", "replace")
        return status, parsed, out_headers

    def rpc(self, method, params=None, token="mcp", rid=1):
        body = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            body["params"] = params
        return self.raw(
            "/mcp",
            method="POST",
            data=json.dumps(body).encode(),
            token=token,
            headers={"Content-Type": "application/json"},
        )

    def call_tool(self, name, arguments=None):
        status, out, _ = self.rpc(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )
        self.assertEqual(status, 200, out)
        self.assertFalse(out["result"]["isError"], out)
        return out["result"]["structuredContent"]

    def tool_names(self):
        status, out, _ = self.rpc("tools/list")
        self.assertEqual(status, 200)
        return {tool["name"] for tool in out["result"]["tools"]}

    def test_initialize_negotiates_supported_versions_and_falls_back(self):
        for version in SUPPORTED_PROTOCOLS:
            status, out, _ = self.rpc(
                "initialize",
                {"protocolVersion": version, "clientInfo": {"name": "probe", "version": "1"}},
            )
            self.assertEqual(status, 200)
            self.assertEqual(out["result"]["protocolVersion"], version)
            self.assertEqual(out["result"]["serverInfo"]["name"], "opencode-mission-control")
        status, out, _ = self.rpc("initialize", {"protocolVersion": "1999-01-01"})
        self.assertEqual(status, 200)
        self.assertEqual(out["result"]["protocolVersion"], SUPPORTED_PROTOCOLS[0])

    def test_tools_list_is_stable_and_reporting_is_conditional(self):
        self.assertEqual(self.tool_names(), READ_TOOLS)
        status, out, _ = self.rpc(
            "tools/call",
            {"name": "report_event", "arguments": {"event_id": "e", "session_id": "s"}},
        )
        self.assertEqual(status, 200)
        self.assertEqual(out["error"]["code"], -32602)

        cfg = self.e.config()
        cfg["enable_reporting"] = True
        self.e.save_config(cfg)
        self.assertEqual(self.tool_names(), READ_TOOLS | {"report_event"})
        first = self.call_tool(
            "report_event",
            {"event_id": "ev-1", "session_id": "manual:probe", "source": "manual"},
        )
        self.assertTrue(first["accepted"])
        self.assertFalse(first["duplicate"])
        again = self.call_tool(
            "report_event",
            {"event_id": "ev-1", "session_id": "manual:probe", "source": "manual"},
        )
        self.assertTrue(again["duplicate"])

    def test_tools_schema_annotations_and_validation(self):
        status, out, _ = self.rpc("tools/list")
        self.assertEqual(status, 200)
        for tool in out["result"]["tools"]:
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertIn("readOnlyHint", tool["annotations"])
            self.assertTrue(tool["annotations"]["readOnlyHint"])
            self.assertEqual(tool["name"], tool["name"].strip())
        status, out, _ = self.rpc(
            "tools/call", {"name": "search", "arguments": {"query": "x", "bogus": 1}}
        )
        self.assertEqual(out["error"]["code"], -32602)
        status, out, _ = self.rpc(
            "tools/call", {"name": "search", "arguments": {"query": "x" * 6001}}
        )
        self.assertEqual(out["error"]["code"], -32602)
        status, out, _ = self.rpc("tools/call", {"name": "search", "arguments": "nope"})
        self.assertEqual(out["error"]["code"], -32602)

    def test_resources_expose_mission_overview(self):
        status, out, _ = self.rpc("resources/list")
        self.assertEqual(status, 200)
        uris = [resource["uri"] for resource in out["result"]["resources"]]
        self.assertIn("mission://overview", uris)
        status, out, _ = self.rpc(
            "resources/read", {"uri": "mission://overview"}
        )
        self.assertEqual(status, 200)
        content = out["result"]["contents"][0]
        self.assertEqual(content["mimeType"], "application/json")
        parsed = json.loads(content["text"])
        self.assertIn("coverage", parsed)
        status, out, _ = self.rpc("resources/read", {"uri": "mission://missing"})
        self.assertEqual(out["error"]["code"], -32602)

    def test_limits_and_coverage_consistency(self):
        listing = self.call_tool("list_agents", {"limit": 500})
        self.assertIn("matched", listing)
        self.assertIn("loaded_total", listing)
        self.assertEqual(listing["coverage"]["scope"]["kind"], "snapshot")
        for key in ("metadata_complete", "aggregates_complete", "history_limited"):
            self.assertIn(key, listing["coverage"])
        status, out, _ = self.rpc(
            "tools/call", {"name": "list_agents", "arguments": {"limit": 501}}
        )
        self.assertEqual(out["error"]["code"], -32602)
        status, out, _ = self.rpc(
            "tools/call", {"name": "list_agents", "arguments": {"limit": 0}}
        )
        self.assertEqual(out["error"]["code"], -32602)

        comparison = self.call_tool("model_comparison", {})
        self.assertEqual(comparison["coverage"]["scope"]["kind"], "range")
        self.assertEqual(
            set(comparison["coverage"]["breakdowns"]), {"daily", "model", "file"}
        )
        overview = self.call_tool("mission_overview", {})
        self.assertEqual(overview["coverage"]["scope"]["kind"], "snapshot")
        self.assertIn("Tokens exclude router ledger", overview["note"])

    def test_notifications_are_accepted_and_unknown_methods_fail(self):
        body = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        status, out, _ = self.raw(
            "/mcp",
            method="POST",
            data=json.dumps(body).encode(),
            token="mcp",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 202)
        self.assertEqual(out, "")

        reply = self.raw(
            "/mcp",
            method="POST",
            data=json.dumps({"jsonrpc": "2.0", "id": 9, "method": "no/such/method"}).encode(),
            token="mcp",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(reply[1]["error"]["code"], -32601)

    def test_mcp_token_cannot_reveal_settings_or_stop_observer(self):
        status, _, _ = self.raw(
            "/api/reveal",
            method="POST",
            data=json.dumps({"name": "owner_token"}).encode(),
            token="mcp",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 403)
        status, _, _ = self.raw(
            "/api/config",
            method="POST",
            data=json.dumps(self.e.config()).encode(),
            token="mcp",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 403)
        status, _, _ = self.raw(
            "/api/shutdown",
            method="POST",
            data=json.dumps({"confirm": "STOP OBSERVER"}).encode(),
            token="mcp",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 403)

    def test_mcp_responses_never_contain_secret_values(self):
        payload = json.dumps(self.call_tool("mission_overview", {}))
        for secret in (self.e.control_token, self.e.mcp_token, self.e.pairing_key):
            self.assertNotIn(secret, payload)

    def test_logs_never_carry_secrets_or_query_strings(self):
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = Capture()
        previous = mc.LOG.level
        mc.LOG.addHandler(handler)
        mc.LOG.setLevel(logging.INFO)
        try:
            self.raw("/?access=" + self.e.control_token, token=False)
            self.raw("/api/overview")
        finally:
            mc.LOG.removeHandler(handler)
            mc.LOG.setLevel(previous)
        joined = "\n".join(records)
        self.assertNotIn(self.e.control_token, joined)
        self.assertNotIn("access=", joined)
        self.assertNotIn("Bearer", joined)

    def test_stdio_bridge_stdout_is_clean_from_foreign_cwd(self):
        state = self.root / "state spaced" / "observer home"
        engine = mc.Engine(state, {**OVERRIDES, "db_paths": []})
        self.addCleanup(engine.close)
        server = mc.Server(("127.0.0.1", 0), engine)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def stop():
            engine.close()
            thread.join(timeout=10)

        self.addCleanup(stop)
        (engine.store.directory / "runtime.json").write_text(
            json.dumps({"port": server.server_address[1]}), "utf-8"
        )
        cwd = self.root / "foreign cwd"
        cwd.mkdir()
        proc = subprocess.Popen(
            [
                sys.executable,
                "-X",
                "utf8",
                str(mc.launcher_path()),
                "--mcp-stdio",
                "--state-dir",
                str(engine.store.directory),
            ],
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ]
            for request in requests:
                proc.stdin.write((json.dumps(request) + "\n").encode())
            proc.stdin.flush()
            lines = [proc.stdout.readline().decode() for _ in range(2)]
            proc.stdin.close()
            code = proc.wait(timeout=20)
        finally:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(code, 0)
        responses = [json.loads(line) for line in lines]
        self.assertEqual(responses[0]["id"], 1)
        self.assertIn("result", responses[0])
        self.assertEqual(responses[1]["id"], 2)
        names = {tool["name"] for tool in responses[1]["result"]["tools"]}
        self.assertEqual(names, READ_TOOLS)


if __name__ == "__main__":
    unittest.main()
