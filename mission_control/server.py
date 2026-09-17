"""Local-only HTTP server and request handler."""

import copy
import csv
import hashlib
import hmac
import html
import io
import json
import os
import socket
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .core import (
    LOG,
    MAX_BODY,
    PACKAGE_ROOT,
    VERSION,
    LifecycleError,
    digest,
    now_ms,
    redact,
    stdio_script_args,
)
from .mcp import MCP
from .oauth import OAuth

WEB_DIR = PACKAGE_ROOT / "web"
DIST_DIR = WEB_DIR / "dist"


def _read_text(path, fallback=""):
    try:
        return path.read_text("utf-8")
    except OSError:
        LOG.warning("Missing web asset %s", path)
        return fallback


def _web_asset(name, fallback=""):
    """Load a static asset from ``web/`` next to the launcher (dev mode only)."""
    return _read_text(WEB_DIR / name, fallback)


def _dist_assets():
    """Verified production assets from ``web/dist``.

    Returns ``(assets, error)``. When the build is missing or does not match
    its manifest, ``assets`` is ``None`` and ``error`` is a readable reason.
    Sources in ``web/`` are never used as a silent fallback.
    """
    try:
        manifest = json.loads((DIST_DIR / "manifest.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None, "The production frontend build is missing (web/dist/manifest.json)."
    outputs = manifest.get("outputs") if isinstance(manifest, dict) else None
    if not isinstance(outputs, dict) or not outputs:
        return None, "The production frontend manifest is unreadable or incomplete."
    assets = {}
    for name, expected in outputs.items():
        if name not in ("index.html", "app.js", "style.css"):
            return None, f"The production manifest lists an unexpected asset: {name}."
        try:
            raw = (DIST_DIR / name).read_bytes()
        except OSError:
            return None, f"The production frontend is incomplete: web/dist/{name} is missing."
        if hashlib.sha256(raw).hexdigest() != expected:
            return None, f"The production frontend does not match its manifest: web/dist/{name}."
        assets[name] = raw.decode("utf-8")
    for name in ("index.html", "app.js", "style.css"):
        if name not in assets:
            return None, f"The production manifest is incomplete (missing {name})."
    return assets, ""


PAGE = _web_asset(
    "index.html",
    '<!doctype html><html lang="en"><meta charset="utf-8">'
    "<title>Mission Control</title><body><p>Frontend assets are missing "
    "(web/index.html). Reinstall the full project.</p></body></html>",
)
JS = _web_asset("app.js", "")
CSS = _web_asset("style.css", "")
# Exact-name allowlist for the offline i18n modules the page imports.
I18N_ASSETS = {name: _web_asset("i18n/" + name, "") for name in ("en.js", "pl.js", "core.js")}

BUILD_ERROR_PAGE = (
    '<!doctype html><html lang="en"><meta charset="utf-8">'
    "<title>Mission Control · build required</title>"
    '<body style="font-family:system-ui;padding:2rem;max-width:44rem">'
    "<h1>Production frontend not available</h1><p>__REASON__</p>"
    "<p>Build the frontend with <code>npm run build</code> (Node.js required) "
    "or reinstall the complete package that ships <code>web/dist</code>.</p>"
    "</body></html>"
)


def build_error_page(reason):
    return BUILD_ERROR_PAGE.replace("__REASON__", html.escape(reason or "Unknown build error."))


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32
    # On Windows SO_REUSEADDR lets a second process silently bind a port that is
    # already in use (hijacking), which hides "port busy". Use exclusive binding
    # there; keep SO_REUSEADDR on POSIX only to avoid TIME_WAIT restarts.
    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        if os.name == "nt":
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except (AttributeError, OSError):
                pass
        super().server_bind()

    def __init__(self, address, engine, dev_web=False):
        self.engine = engine
        self.dev_web = dev_web
        if dev_web:
            # Explicit development mode: serve the unbuilt sources.
            self.assets = {"index.html": PAGE, "app.js": JS, "style.css": CSS}
            self.asset_error = ""
        else:
            assets, error = _dist_assets()
            self.assets = assets or {}
            self.asset_error = error
            if error:
                LOG.warning("Production frontend unavailable: %s", error)
        self.oauth = OAuth(engine)
        self.mcp = MCP(engine)
        self.slots = threading.BoundedSemaphore(32)
        self.last_request = time.monotonic()
        self.rate_lock = threading.Lock()
        self.rate = {}
        self._active = 0
        self._active_cond = threading.Condition()
        self._serving = threading.Event()
        self._serve_thread = None
        self._stop_lock = threading.Lock()
        super().__init__(address, Handler)
        engine.port = self.server_address[1]
        engine.server = self

    def serve_forever(self, poll_interval=0.5):
        """Record that the accept loop is live so shutdown() is only called when valid."""
        self._serve_thread = threading.current_thread()
        self._serving.set()
        try:
            super().serve_forever(poll_interval)
        finally:
            self._serving.clear()

    def request_stop(self, timeout=5.0):
        """Stop the accept loop if it is running, drain handlers, then close.

        ``ThreadingHTTPServer.shutdown()`` blocks forever unless
        ``serve_forever()`` is running on another thread, so it is only called
        when this instance is actually serving. A slow handler or accept loop
        raises :class:`LifecycleError` instead of closing underneath live work.
        """
        with self._stop_lock:
            if self._serving.is_set():
                self.shutdown()
                thread = self._serve_thread
                if thread is not None and thread is not threading.current_thread():
                    thread.join(timeout)
                    if thread.is_alive():
                        raise LifecycleError(f"HTTP server did not stop within {timeout}s")
            if not self.wait_idle(timeout):
                raise LifecycleError(f"HTTP handlers still active after {timeout}s; not closing")
            self.server_close()

    def _begin(self):
        with self._active_cond:
            self._active += 1

    def _end(self):
        with self._active_cond:
            self._active -= 1
            if self._active <= 0:
                self._active_cond.notify_all()

    def wait_idle(self, timeout=5.0):
        """Block until no request handler is running (or timeout)."""
        deadline = time.monotonic() + timeout
        with self._active_cond:
            while self._active > 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._active_cond.wait(remaining)
            return True

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            # Tell the client explicitly instead of resetting the connection.
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                )
            except OSError:
                pass
            request.close()
            return
        self._begin()
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            self._end()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()
            self._end()

    def rate_ok(self, key, maximum=80):
        now = time.monotonic()
        with self.rate_lock:
            if len(self.rate) > 1000:
                self.rate = {k: v for k, v in self.rate.items() if v and now - v[-1] < 60}
            q = self.rate.setdefault(key, deque())
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= maximum:
                return False
            q.append(now)
            return True


class Handler(BaseHTTPRequestHandler):
    server_version = "MissionControl/" + VERSION
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(12)
        self._body_read = False
        self._drained = False

    def _drain_body(self):
        """Consume an unread request body before responding.

        Closing a socket with unread receive data makes Windows send a TCP RST,
        which the client observes as ``ConnectionAbortedError`` instead of the
        401/403 we just wrote. Rejections that never call ``body()`` therefore
        drain the declared length (bounded by ``MAX_BODY``) first.
        """
        if self._drained:
            return
        self._drained = True
        if self._body_read:
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            return
        if not 0 < length <= MAX_BODY + 262144:
            # Drain requests that are only slightly oversized so the client can
            # still read the clean 400 instead of a Windows connection reset.
            # Anything larger is refused without draining to stay bounded.
            return
        remaining = length
        try:
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 65536))
                if not chunk:
                    break
                remaining -= len(chunk)
        except OSError:
            pass

    def log_message(self, fmt, *args):
        # No auth query strings, bearer tokens, authorization codes or form bodies.
        LOG.info("%s %s", self.command, self.path.split("?")[0])

    @property
    def engine(self):
        return self.server.engine

    def send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        self._drain_body()
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        )
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def gate(self):
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        origin = self.engine.config()["public_origin"]
        if origin:
            hosts.add(urlparse(origin).netloc)
        host = self.headers.get("Host", "").lower()
        if host not in {h.lower() for h in hosts}:
            self.send(403, {"error": "Host not allowed"})
            return False
        request_origin = self.headers.get("Origin")
        # Match full scheme/authority, not merely Origin == attacker-controlled Host.
        allowed_origins = {
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
            f"http://[::1]:{port}",
        }
        if origin:
            allowed_origins.add(origin)
        if request_origin and request_origin not in allowed_origins:
            self.send(403, {"error": "Origin not allowed"})
            return False
        self.server.last_request = time.monotonic()
        return True

    def authorization(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        token = header[7:]
        if len(token) > 2000:
            return None
        if hmac.compare_digest(token, self.engine.control_token):
            return {
                "role": "owner",
                "scopes": ["mission:read", "mission:report"],
                "client_id": "owner",
            }
        if hmac.compare_digest(token, self.engine.mcp_token):
            scopes = ["mission:read"] + (
                ["mission:report"] if self.engine.config()["enable_reporting"] else []
            )
            return {"role": "local-mcp", "scopes": scopes, "client_id": "local-mcp"}
        return self.server.oauth.authenticate(token)

    def require(self, owner=False, mcp=False):
        auth = self.authorization()
        if auth and (not owner or auth["role"] == "owner"):
            return auth
        extra = {}
        if mcp and self.engine.config()["public_origin"]:
            origin = self.engine.config()["public_origin"]
            extra["WWW-Authenticate"] = (
                f'Bearer resource_metadata="{origin}/.well-known/oauth-protected-resource", scope="mission:read"'
            )
        self.send(
            401 if auth is None else 403,
            {"error": "Owner access required" if owner else "Authentication required"},
            extra=extra,
        )
        return None

    def body(self, form=False):
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Chunked request bodies are not supported.")
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            raise ValueError("Invalid Content-Length") from None
        if not 0 < length <= MAX_BODY:
            raise ValueError("Request body must be 1 byte–1 MiB.")
        typ = self.headers.get("Content-Type", "").split(";")[0].lower()
        expected = "application/x-www-form-urlencoded" if form else "application/json"
        if typ != expected:
            raise ValueError("Expected " + expected)
        raw = self.rfile.read(length)
        self._body_read = True
        if len(raw) != length:
            raise ValueError("Incomplete request body")
        if form:
            parsed = parse_qs(raw.decode("utf-8"), max_num_fields=30)
            if any(len(v) != 1 for v in parsed.values()):
                raise ValueError("Duplicate form fields")
            return {k: v[0] for k, v in parsed.items()}
        try:
            data = json.loads(
                raw,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    ValueError("Nonfinite JSON is not supported.")
                ),
            )
        except (UnicodeError, ValueError):
            raise ValueError("Invalid JSON body") from None
        if not isinstance(data, dict):
            raise ValueError("Request must be a JSON object")
        return data

    def do_GET(self):
        if not self.gate():
            return
        try:
            u = urlparse(self.path)
            path = u.path
            q = {k: v[-1] for k, v in parse_qs(u.query, max_num_fields=30).items()}
            if path in ("/", "/index.html"):
                asset = self.server.assets.get("index.html")
                if asset is None:
                    # A readable instruction page instead of a blank error or a
                    # silent fallback to the unbuilt sources.
                    self.send(
                        200,
                        build_error_page(self.server.asset_error),
                        "text/html; charset=utf-8",
                    )
                    return
                self.send(200, asset, "text/html; charset=utf-8")
                return
            if path == "/app.js":
                asset = self.server.assets.get("app.js")
                if asset is None:
                    self.send(
                        503,
                        {"error": self.server.asset_error or "Production frontend unavailable."},
                    )
                    return
                self.send(200, asset, "application/javascript; charset=utf-8")
                return
            if path == "/style.css":
                asset = self.server.assets.get("style.css")
                if asset is None:
                    self.send(
                        503,
                        {"error": self.server.asset_error or "Production frontend unavailable."},
                    )
                    return
                self.send(200, asset, "text/css; charset=utf-8")
                return
            if path.startswith("/i18n/"):
                # The dist bundle inlines the dictionaries; the allowlisted
                # modules are only served by explicit development mode.
                asset = I18N_ASSETS.get(path[len("/i18n/") :]) if self.server.dev_web else None
                if asset:
                    self.send(200, asset, "text/javascript; charset=utf-8")
                else:
                    self.send(404, {"error": "Not found"})
                return
            if path == "/health":
                self.send(
                    200,
                    {
                        "healthy": True,
                        "version": VERSION,
                        "application": "opencode-mission-control",
                    },
                )
                return
            if path.startswith("/.well-known/"):
                if path in (
                    "/.well-known/oauth-protected-resource",
                    "/.well-known/oauth-protected-resource/mcp",
                ):
                    self.send(200, self.server.oauth.metadata(True))
                    return
                if path == "/.well-known/oauth-authorization-server":
                    self.send(200, self.server.oauth.metadata())
                    return
                self.send(404, {"error": "Not found"})
                return
            if path == "/oauth/authorize":
                if not self.server.rate_ok(("authorize", self.client_address[0]), 30):
                    self.send(429, {"error": "Too many requests"})
                    return
                fid, client, scopes = self.server.oauth.begin(q)
                body = (
                    OAUTH_PAGE.replace("__FLOW__", html.escape(fid, quote=True))
                    .replace("__CLIENT__", html.escape(client["client_name"]))
                    .replace("__SCOPES__", html.escape(", ".join(scopes)))
                    .replace("__CALLBACK__", html.escape(q.get("redirect_uri", "")))
                )
                self.send(200, body, "text/html; charset=utf-8")
                return
            if path == "/mcp":
                if self.require(mcp=True):
                    self.send(
                        405,
                        {
                            "error": "Use POST. This server returns request-scoped JSON and does not offer an unsolicited SSE stream."
                        },
                        extra={"Allow": "POST"},
                    )
                return
            if not path.startswith("/api/"):
                self.send(404, {"error": "Not found"})
                return
            if not self.require(owner=True):
                return
            e = self.engine
            if path == "/api/overview":
                snap = e.view()
                with self.server.mcp.lock:
                    snap["mcp_clients"] = list(copy.deepcopy(self.server.mcp.clients).values())
                self.send(200, snap)
            elif path == "/api/session":
                self.send(200, e.detail(q.get("id", "")))
            elif path == "/api/timeline":
                result = e.store.timeline(
                    min(200, max(1, int(q.get("limit", 80)))),
                    int(q.get("before", 0)),
                    q.get("session_id", ""),
                    q.get("project", ""),
                    q.get("query", ""),
                )
                if not e.config()["show_prompts"]:
                    result["events"] = [ev for ev in result["events"] if ev["kind"] != "prompt"]
                self.send(200, result)
            elif path == "/api/analytics":
                days = int(q.get("days", 0))
                if not 0 <= days <= 730:
                    raise ValueError("Invalid days filter")
                self.send(
                    200,
                    e.analytics(
                        days, q.get("project", ""), q.get("task_group", ""), q.get("source", "")
                    ),
                )
            elif path == "/api/config":
                self.send(200, e.config())
            elif path == "/api/scan":
                with e.lock:
                    result = copy.deepcopy(e.scan_result)
                self.send(200, result)
            elif path == "/api/integrations":
                origin = e.config()["public_origin"]
                # Resolve the stable root launcher, not this module, so the
                # exported command stays correct after the package split.
                script_args = stdio_script_args()
                command = sys.executable or "python"
                # A GUI-launched observer may run under pythonw.exe, whose
                # standard streams are absent. MCP must use console Python.
                executable = Path(command)
                if executable.name.lower() in ("pythonw.exe", "pythonw"):
                    command = str(
                        executable.with_name(
                            "python.exe" if executable.suffix.lower() == ".exe" else "python"
                        )
                    )
                # JSON strings are valid TOML basic strings for these path values.
                args = [*script_args, "--mcp-stdio", "--state-dir", str(e.store.directory)]
                toml = (
                    "[mcp_servers.mission_control]\ncommand = "
                    + json.dumps(command)
                    + "\nargs = "
                    + json.dumps(args)
                    + "\nstartup_timeout_sec = 20\ntool_timeout_sec = 30\n"
                )
                http_toml = f'[mcp_servers.mission_control]\nurl = "http://127.0.0.1:{e.port}/mcp"\nbearer_token_env_var = "MISSION_CONTROL_MCP_TOKEN"\n'
                self.send(
                    200,
                    {
                        "stdio_toml": toml,
                        "http_toml": http_toml,
                        "mcp_url": f"http://127.0.0.1:{e.port}/mcp",
                        "remote_url": origin + "/mcp" if origin else "",
                        "secrets": REVEALABLE_SECRETS,
                        "state_directory": str(e.store.directory),
                        "reporting": e.config()["enable_reporting"],
                        "tools": self.server.mcp.tools(),
                        "instructions": INTEGRATION_NOTES,
                    },
                )
            elif path == "/api/export":
                kind = q.get("format", "json")
                analytics = e.analytics(
                    int(q.get("days", 0)),
                    q.get("project", ""),
                    q.get("task_group", ""),
                    q.get("source", ""),
                )
                if kind == "csv":
                    out = io.StringIO()
                    writer = csv.writer(out)
                    fields = [
                        "date",
                        "input",
                        "output",
                        "reasoning",
                        "cache_read",
                        "cache_write",
                        "total",
                    ]
                    writer.writerow(fields)
                    for row in analytics["days"]:
                        writer.writerow([row.get(k, "") for k in fields])
                    # Row/column limits must never hide the completeness contract:
                    # the same coverage block as the JSON export travels with CSV.
                    self.send(
                        200,
                        out.getvalue(),
                        "text/csv; charset=utf-8",
                        {
                            "Content-Disposition": 'attachment; filename="mission-control-days.csv"',
                            "X-Mission-Control-Coverage": json.dumps(
                                analytics.get("coverage") or {},
                                ensure_ascii=True,
                                separators=(",", ":"),
                            ),
                        },
                    )
                elif kind == "json":
                    self.send(
                        200,
                        {"overview": e.view(), "analytics": analytics},
                        extra={
                            "Content-Disposition": 'attachment; filename="mission-control.json"'
                        },
                    )
                else:
                    raise ValueError("Export format must be json or csv.")
            else:
                self.send(404, {"error": "Not found"})
        except PermissionError as ex:
            self.send(403, {"error": redact(ex, 400)})
        except (ValueError, KeyError, TypeError) as ex:
            self.send(400, {"error": redact(ex, 400)})
        except Exception:
            LOG.exception("GET failed")
            self.send(500, {"error": "Observer error. See the local log."})

    def do_POST(self):
        if not self.gate():
            return
        try:
            path = urlparse(self.path).path
            if path.startswith("/oauth/"):
                if not self.server.rate_ok(("oauth", self.client_address[0]), 60):
                    self.send(429, {"error": "Too many requests"})
                    return
                if path == "/oauth/register":
                    self.send(201, self.server.oauth.register(self.body()))
                    return
                data = self.body(form=True)
                if path == "/oauth/authorize":
                    redirect = self.server.oauth.approve(
                        data.get("flow", ""), data.get("pairing_key", "")
                    )
                    self.send(303, "", "text/plain", {"Location": redirect})
                    return
                if path == "/oauth/token":
                    self.send(200, self.server.oauth.exchange(data))
                    return
                if path == "/oauth/revoke":
                    self.server.oauth.revoke(data.get("token", ""))
                    self.send(200, {})
                    return
                self.send(404, {"error": "Not found"})
                return
            if path == "/mcp":
                auth = self.require(mcp=True)
                if not auth:
                    return
                protocol = self.headers.get("MCP-Protocol-Version")
                if protocol and protocol not in ("2025-11-25", "2025-06-18"):
                    self.send(400, {"error": "Unsupported MCP protocol version"})
                    return
                data = self.body()
                result = self.server.mcp.dispatch(data, auth)
                self.send(202, b"") if result is None else self.send(200, result)
                return
            if not path.startswith("/api/"):
                self.send(404, {"error": "Not found"})
                return
            if not self.require(owner=True):
                return
            data = self.body()
            e = self.engine
            if path == "/api/refresh":
                e.wake.set()
                self.send(202, {"requested": True})
            elif path == "/api/shutdown":
                if data.get("confirm") != "STOP OBSERVER":
                    raise ValueError("Explicit observer shutdown confirmation required.")
                self.send(202, {"stopping": True, "agents_affected": False})
                threading.Thread(
                    target=self.server.shutdown, name="owner-shutdown", daemon=True
                ).start()
            elif path == "/api/config":
                e.save_config(data)
                self.send(200, {"saved": True})
            elif path == "/api/scan":
                self.send(202, e.begin_scan(data.get("roots"), data.get("depth", 5)))
            elif path == "/api/adopt":
                self.send(200, e.adopt_scan(data.get("selected")))
            elif path == "/api/report":
                self.send(200, e.add_report(data))
            elif path == "/api/assessment":
                self.send(200, e.assess(data.get("session_id"), data.get("assessment")))
            elif path == "/api/abort":
                self.send(200, e.abort(data.get("session_id"), data.get("confirm")))
            elif path == "/api/reveal":
                name = data.get("name")
                if name not in REVEALABLE_SECRETS:
                    raise ValueError("Unknown secret name.")
                if not self.server.rate_ok(("reveal", self.client_address[0]), 10):
                    raise PermissionError("Too many reveal requests. Wait a minute.")
                value = {
                    "pairing_key": e.pairing_key,
                    "mcp_token": e.mcp_token,
                    "owner_token": e.control_token,
                }[name]
                e.store.events(
                    [
                        {
                            "id": digest("reveal", name, now_ms()),
                            "ts": now_ms(),
                            "session_id": "observer",
                            "source": "owner",
                            "kind": "secret-reveal",
                            "project": "",
                            "text": f"Owner revealed {name}",
                            "detail": {"name": name},
                        }
                    ]
                )
                self.send(
                    200,
                    {
                        "name": name,
                        "value": value,
                        "warning": "Treat this like a password. It grants local control; never share it or paste it into untrusted sites.",
                    },
                )
            elif path == "/api/ack":
                ids = data.get("ids")
                if (
                    not isinstance(ids, list)
                    or len(ids) > 500
                    or any(not isinstance(i, str) for i in ids)
                ):
                    raise ValueError("Invalid alert IDs.")
                current = set(e.store.setting("acknowledged", []))
                current.update(ids)
                e.store.set_setting("acknowledged", sorted(current)[-2000:])
                e.wake.set()
                self.send(200, {"acknowledged": len(ids)})
            elif path == "/api/revoke":
                self.send(200, {"revoked": self.server.oauth.revoke(all_tokens=True)})
            elif path == "/api/reset-clients":
                if data.get("confirm") != "REVOKE ALL":
                    raise ValueError("Confirmation required.")
                self.server.oauth.revoke(all_tokens=True)
                with e.store.lock, e.store.con:
                    e.store.con.execute("DELETE FROM oauth_client")
                self.send(200, {"deleted": True})
            else:
                self.send(404, {"error": "Not found"})
        except PermissionError as ex:
            self.send(403, {"error": redact(ex, 400)})
        except (ValueError, KeyError, TypeError) as ex:
            self.send(400, {"error": redact(ex, 400)})
        except Exception:
            LOG.exception("POST failed")
            self.send(500, {"error": "Observer error. See the local log."})

    def do_DELETE(self):
        if self.gate():
            self.send(
                405,
                {"error": "Stateless transport. No session deletion endpoint."},
                extra={"Allow": "GET, POST"},
            )

    def do_OPTIONS(self):
        if self.gate():
            self.send(405, {"error": "Cross-origin browser access is disabled."})


INTEGRATION_NOTES = """Codex: the stdio configuration bridges to this already-running dashboard and reads a local observer token. No second scanner is started. Alternatively use authenticated HTTP and set MISSION_CONTROL_MCP_TOKEN in the Codex process environment.
ChatGPT: configure a stable HTTPS tunnel/reverse proxy to the dashboard port. Set public_origin to that exact HTTPS origin and put the exact callback displayed by ChatGPT in oauth_redirect_uris. Create an MCP connection to https://your-host/mcp, choose OAuth with dynamic registration (DCR), leave static client credentials empty. On the authorization page enter the owner pairing key from this local panel. OAuth tokens expire after one hour; refresh rotates; restarting the observer revokes issued tokens. The tunnel is not installed or opened automatically. For an Internet-facing deployment use a hardened TLS/auth gateway and rate limiting.

MCP does not read unrelated ChatGPT conversations or other MCP servers automatically. report_event records only events explicitly sent to this observer; linking source=chatgpt is a caller claim. To show a ChatGPT→OpenCode relationship use the exact canonical session_id returned by list_agents. A root reported conversation can use reported:chatgpt:my-thread. API calls made directly to a different OpenCode MCP server remain invisible until reported or present in source telemetry.

Source files: OpenCode SQLite is opened read-only with a consistent snapshot. Codex uses local sessions/archived_sessions JSONL files, with bounded incremental reads and explicit coverage warnings. Cloud-only Codex sessions are unavailable without export/telemetry. Router logs are a separate ledger, never added to native totals.

Safety: prompts/tool output may contain private data. Redaction is best-effort. Disable show_prompts to suppress prompt text and agent-definition bodies; tool output may still be sensitive. OAuth read grants can inspect loaded sessions. Never publish owner.token, mcp.token or pairing.key. MCP cannot abort agents; the owner UI can do so only after enablement and typed confirmation. No automatic model switching, agent spawning, shell commands, updates or paid calls occur."""


REVEALABLE_SECRETS = ("pairing_key", "mcp_token", "owner_token")


OAUTH_PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mission Control · Authorize</title><link rel="stylesheet" href="/style.css"><body><main class="authbox"><div class="brandmark">M</div><p class="eyebrow">OWNER APPROVAL</p><h1>Connect __CLIENT__</h1><p>This app requests <strong>__SCOPES__</strong>. Read access can expose local project names, agent sessions and, when enabled, prompt/tool content. Reporting writes observer telemetry only.</p><p class="note">Callback: __CALLBACK__</p><form action="/oauth/authorize" method="post"><input type="hidden" name="flow" value="__FLOW__"><label>Owner pairing key <input name="pairing_key" type="password" autocomplete="off" required minlength="32" placeholder="From your local Integrations screen"></label><button class="primary" type="submit">Approve connection</button></form><p class="muted">Only approve an integration you started. The key is never given to the connecting app.</p></main></body></html>"""
