"""Optional single-owner OAuth authorization-code + S256 PKCE flow."""

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from collections import deque
from urllib.parse import urlencode

from .core import (
    digest,
    redact,
)


class OAuth:
    """Single-owner optional OAuth authorization-code + S256 PKCE flow.

    Disabled until a canonical HTTPS public_origin is configured. Registrations
    use an exact callback allowlist. Access/refresh tokens are opaque, scoped,
    audience-bound, short-lived, and held in memory; restart revokes them.
    This is a local development integration, not a multi-tenant identity system.
    Put a mature TLS/auth gateway in front of an Internet-facing deployment.
    """

    def __init__(self, engine):
        self.engine = engine
        self.lock = threading.RLock()
        self.flows = {}
        self.codes = {}
        self.tokens = {}
        self.refresh = {}
        self.attempts = deque()

    def origin(self):
        o = self.engine.config()["public_origin"]
        if not o:
            raise PermissionError("Remote OAuth disabled. Set public_origin first.")
        return o

    def resource(self):
        return self.origin() + "/mcp"

    def prune(self):
        now = time.time()
        for mapping in (self.flows, self.codes, self.tokens, self.refresh):
            for key in list(mapping):
                if mapping[key]["expires"] <= now:
                    del mapping[key]
        while self.attempts and now - self.attempts[0] > 60:
            self.attempts.popleft()

    def metadata(self, resource=False):
        origin = self.origin()
        scopes = ["mission:read"] + (
            ["mission:report"] if self.engine.config()["enable_reporting"] else []
        )
        if resource:
            return {
                "resource": self.resource(),
                "authorization_servers": [origin],
                "scopes_supported": scopes,
                "bearer_methods_supported": ["header"],
            }
        return {
            "issuer": origin,
            "authorization_endpoint": origin + "/oauth/authorize",
            "token_endpoint": origin + "/oauth/token",
            "registration_endpoint": origin + "/oauth/register",
            "revocation_endpoint": origin + "/oauth/revoke",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_methods_supported": ["none"],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": scopes,
            "authorization_response_iss_parameter_supported": True,
            "client_id_metadata_document_supported": False,
        }

    def register(self, data):
        self.origin()
        redirects = data.get("redirect_uris")
        allowed = self.engine.config()["oauth_redirect_uris"]
        if (
            not isinstance(redirects, list)
            or not redirects
            or len(redirects) > 8
            or any(r not in allowed for r in redirects)
        ):
            raise ValueError(
                "redirect_uris must exactly match the owner-configured HTTPS allowlist."
            )
        if data.get("token_endpoint_auth_method", "none") != "none":
            raise ValueError("Only public clients using PKCE and auth method none are supported.")
        grants = data.get("grant_types", ["authorization_code", "refresh_token"])
        if not isinstance(grants, list) or any(
            g not in ("authorization_code", "refresh_token") for g in grants
        ):
            raise ValueError("Unsupported OAuth grant.")
        client = {
            "client_id": secrets.token_urlsafe(24),
            "client_id_issued_at": int(time.time()),
            "client_name": redact(data.get("client_name") or "MCP client", 100),
            "redirect_uris": redirects,
            "token_endpoint_auth_method": "none",
            "grant_types": grants,
            "response_types": ["code"],
        }
        store = self.engine.store
        with store.lock, store.con:
            count = store.con.execute("SELECT COUNT(*) FROM oauth_client").fetchone()[0]
            if count >= 200:
                raise ValueError(
                    "Registration limit reached. Remove unused clients from the owner settings."
                )
            store.con.execute(
                "INSERT INTO oauth_client VALUES(?,?)", (client["client_id"], json.dumps(client))
            )
        return client

    def client(self, cid):
        store = self.engine.store
        with store.lock:
            row = store.con.execute("SELECT data FROM oauth_client WHERE id=?", (cid,)).fetchone()
        if not row:
            raise ValueError("invalid_client")
        return json.loads(row[0])

    def begin(self, data):
        client = self.client(data.get("client_id", ""))
        if data.get("response_type") != "code" or data.get("code_challenge_method") != "S256":
            raise ValueError("Require response_type=code and code_challenge_method=S256.")
        redirect = data.get("redirect_uri", "")
        if (
            redirect not in client["redirect_uris"]
            or redirect not in self.engine.config()["oauth_redirect_uris"]
        ):
            raise ValueError("redirect_uri mismatch")
        challenge = data.get("code_challenge", "")
        if not isinstance(challenge, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", challenge):
            raise ValueError("Invalid S256 challenge.")
        if data.get("resource") != self.resource():
            raise ValueError("resource must match the MCP resource exactly.")
        scopes = set(str(data.get("scope") or "mission:read").split())
        allowed = set(self.metadata()["scopes_supported"])
        if not scopes or not scopes <= allowed:
            raise ValueError("Unsupported scope.")
        state = data.get("state", "")
        if not isinstance(state, str) or len(state) > 2000:
            raise ValueError("Invalid state.")
        with self.lock:
            self.prune()
            if len(self.flows) >= 200:
                raise ValueError("Too many authorization attempts.")
            fid = secrets.token_urlsafe(32)
            self.flows[fid] = {
                "client_id": client["client_id"],
                "redirect_uri": redirect,
                "challenge": challenge,
                "scope": " ".join(sorted(scopes)),
                "state": state,
                "resource": self.resource(),
                "expires": time.time() + 300,
                "attempts": 0,
            }
        return fid, client, sorted(scopes)

    def approve(self, fid, key):
        with self.lock:
            self.prune()
            flow = self.flows.get(fid)
            if not flow:
                raise ValueError("Authorization request expired.")
            if len(self.attempts) >= 20:
                raise PermissionError("Authorization attempts temporarily limited.")
            self.attempts.append(time.time())
            flow["attempts"] += 1
            if flow["attempts"] > 5:
                del self.flows[fid]
                raise PermissionError("Too many attempts. Start again.")
            if not isinstance(key, str) or not hmac.compare_digest(key, self.engine.pairing_key):
                raise PermissionError("Invalid owner pairing key.")
            code = secrets.token_urlsafe(32)
            self.codes[digest(code)] = {**flow, "expires": time.time() + 90}
            del self.flows[fid]
            params = {"code": code, "state": flow["state"], "iss": self.origin()}
            sep = "&" if "?" in flow["redirect_uri"] else "?"
            return flow["redirect_uri"] + sep + urlencode(params)

    def exchange(self, data):
        with self.lock:
            self.prune()
            if data.get("resource") != self.resource():
                raise ValueError("invalid_target")
            grant = data.get("grant_type")
            cid = data.get("client_id", "")
            self.client(cid)
            if grant == "authorization_code":
                key = digest(data.get("code", ""))
                flow = self.codes.get(key)
                if (
                    not flow
                    or flow["client_id"] != cid
                    or flow["redirect_uri"] != data.get("redirect_uri")
                ):
                    raise ValueError("invalid_grant")
                verifier = data.get("code_verifier", "")
                if not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier):
                    raise ValueError("invalid_grant")
                challenge = (
                    base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                    .rstrip(b"=")
                    .decode()
                )
                if not hmac.compare_digest(challenge, flow["challenge"]):
                    raise ValueError("invalid_grant")
                del self.codes[key]
            elif grant == "refresh_token":
                key = digest(data.get("refresh_token", ""))
                flow = self.refresh.get(key)
                if not flow or flow["client_id"] != cid:
                    raise ValueError("invalid_grant")
                del self.refresh[key]  # rotate refresh token; a replay cannot mint a token
            else:
                raise ValueError("unsupported_grant_type")
            if flow["resource"] != self.resource():
                raise ValueError("invalid_target")
            scopes = set(flow["scope"].split()) & set(self.metadata()["scopes_supported"])
            if data.get("scope"):
                requested = set(data["scope"].split())
                if not requested <= scopes:
                    raise ValueError("invalid_scope")
                scopes = requested
            access, refresh = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
            record = {
                "client_id": cid,
                "scope": " ".join(sorted(scopes)),
                "resource": self.resource(),
            }
            self.tokens[digest(access)] = {**record, "expires": time.time() + 3600}
            self.refresh[digest(refresh)] = {**record, "expires": time.time() + 30 * 86400}
            return {
                "access_token": access,
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": refresh,
                "scope": record["scope"],
            }

    def authenticate(self, token):
        if not self.engine.config()["public_origin"]:
            return None
        with self.lock:
            self.prune()
            record = self.tokens.get(digest(token))
            if not record or record["resource"] != self.resource():
                return None
            return {
                "role": "oauth",
                "scopes": record["scope"].split(),
                "client_id": record["client_id"],
            }

    def revoke(self, token="", all_tokens=False):
        with self.lock:
            if all_tokens:
                n = len(self.tokens)
                self.tokens.clear()
                self.refresh.clear()
                self.codes.clear()
                self.flows.clear()
                return n
            # Revoke all issued grants for this client, not just one access token.
            key = digest(token)
            record = self.tokens.get(key) or self.refresh.get(key)
            if record:
                cid = record["client_id"]
                self.tokens = {k: v for k, v in self.tokens.items() if v["client_id"] != cid}
                self.refresh = {k: v for k, v in self.refresh.items() if v["client_id"] != cid}
            return 0
