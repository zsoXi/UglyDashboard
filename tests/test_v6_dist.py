"""E.1 production-dist serving regressions.

The default server must ship exactly the verified production artifact from
``web/dist`` and never silently fall back to the unbuilt ``web/`` sources.
A missing or tampered build produces a readable error page instead of a stale
or unverified frontend; the explicit ``dev_web`` mode is the only way to serve
sources, and even then only the three i18n modules are exposed by exact name.
"""

import hashlib
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import mission_control as mc
import mission_control.server as server_mod
import test_mission_control as tmc

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DIST = WEB / "dist"

OVERRIDES = {
    "db_paths": [],
    "codex_homes": [],
    "router_events": [],
    "opencode_urls": [],
    "git_enabled": False,
}


class DistServerTests(tmc.Base):
    def make_server(self, dev_web=False):
        engine = mc.Engine(self.root / "state", dict(OVERRIDES))
        srv = mc.Server(("127.0.0.1", 0), engine, dev_web=dev_web)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()

        def stop():
            engine.close()
            thread.join(timeout=10)

        self.addCleanup(stop)
        self.http = build_opener(ProxyHandler({}), mc.NoRedirect())
        self.url = "http://127.0.0.1:%d" % srv.server_address[1]
        return srv

    def raw(self, path):
        try:
            res = self.http.open(Request(self.url + path), timeout=5)
            status, headers, body = res.status, dict(res.headers), res.read()
            res.close()
        except HTTPError as ex:
            status, headers, body = ex.code, dict(ex.headers), ex.read()
            ex.close()
        return status, body, headers

    def test_default_server_serves_verified_dist_artifact(self):
        self.make_server()
        manifest = json.loads((DIST / "manifest.json").read_text("utf-8"))
        expected = {
            "/": ("index.html", "text/html"),
            "/app.js": ("app.js", "application/javascript"),
            "/style.css": ("style.css", "text/css"),
        }
        for path, (name, ctype) in expected.items():
            status, body, headers = self.raw(path)
            self.assertEqual(status, 200, path)
            self.assertIn(ctype, headers.get("Content-Type", ""), path)
            self.assertEqual(hashlib.sha256(body).hexdigest(), manifest["outputs"][name], path)
            self.assertEqual(body, (DIST / name).read_bytes(), path)

    def test_missing_build_never_falls_back_to_sources(self):
        empty = Path(tempfile.mkdtemp(dir=self.root))
        with mock.patch.object(server_mod, "DIST_DIR", empty):
            self.make_server()
        status, body, _ = self.raw("/")
        self.assertEqual(status, 200)
        self.assertIn(b"npm run build", body)
        self.assertNotEqual(body, (WEB / "index.html").read_bytes())
        for path in ("/app.js", "/style.css"):
            status, _, _ = self.raw(path)
            self.assertEqual(status, 503, path)

    def test_tampered_manifest_is_reported(self):
        fake = Path(tempfile.mkdtemp(dir=self.root))
        for name in ("index.html", "app.js", "style.css"):
            (fake / name).write_bytes((DIST / name).read_bytes())
        manifest = json.loads((DIST / "manifest.json").read_text("utf-8"))
        manifest["outputs"]["app.js"] = "0" * 64
        (fake / "manifest.json").write_text(json.dumps(manifest), "utf-8")
        with mock.patch.object(server_mod, "DIST_DIR", fake):
            self.make_server()
        status, body, _ = self.raw("/")
        self.assertEqual(status, 200)
        self.assertIn(b"does not match its manifest", body)
        self.assertNotEqual(body, (WEB / "index.html").read_bytes())
        status, _, _ = self.raw("/app.js")
        self.assertEqual(status, 503)

    def test_dev_web_serves_sources_and_i18n_allowlist(self):
        self.make_server(dev_web=True)
        status, body, _ = self.raw("/")
        self.assertEqual(status, 200)
        self.assertEqual(body, (WEB / "index.html").read_bytes())
        status, body, _ = self.raw("/app.js")
        self.assertEqual(status, 200)
        self.assertEqual(body, (WEB / "app.js").read_bytes())
        status, body, headers = self.raw("/i18n/core.js")
        self.assertEqual(status, 200)
        self.assertIn("text/javascript", headers.get("Content-Type", ""))
        self.assertIn(b"export function t", body)
        status, _, _ = self.raw("/i18n/observer.sqlite")
        self.assertEqual(status, 404)

    def test_static_handler_refuses_secrets_and_traversal(self):
        self.make_server()
        for path in (
            "/secrets.json",
            "/config.json",
            "/observer.sqlite",
            "/web/app.js",
            "/i18n/core.js",
            "/../mission_control/cli.py",
        ):
            status, body, _ = self.raw(path)
            self.assertEqual(status, 404, path)
            self.assertNotIn(b"def ", body, path)

    def test_server_resolves_assets_independently_of_cwd(self):
        previous = os.getcwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(tempfile.mkdtemp(dir=self.root))
        self.make_server()
        status, body, _ = self.raw("/")
        self.assertEqual(status, 200)
        self.assertIn(b"<html", body.lower())


if __name__ == "__main__":
    unittest.main()
