# Security

Single-owner local observer. There is no multi-user model: whoever holds
the owner key controls the panel, and the panel must never be exposed
to the internet without a properly configured TLS layer and traffic
restrictions in front of it. This file states the controls as
implemented, not as audited — no independent security audit exists.

## Credentials and where they live

Own state lives in `~/.opencode-mission-control` (or `--state-dir`):
`config.json`, `observer.sqlite`, `runtime.json`, logs, plus three
confidential key files: `owner.token` (panel login, settings, shutdown),
`mcp.token` (local MCP clients), `pairing.key` (remote OAuth pairing).
Never commit, copy, or sync this directory. Secret files are written
with `0o600` where the platform honours it; on Windows protection
additionally depends on directory ACLs and the user account.

Corrupt, empty or truncated secrets raise `SecretError` — never a silent
rotation that could hide the problem. Recovery is explicit: stop the
observer, delete (or repair) the offending token file, start again; a
fresh secret is created and corrupt bytes are quarantined to a `.bak`
file. Permission/I-O failures leave credentials untouched.

Rotate the owner secret with the documented controlled procedure:

```text
python -X utf8 opencode_dashboard.py --rotate-owner-token --state-dir <state>
```

It atomically replaces **only** `owner.token` (no backup copy is kept) and
preserves `observer.sqlite`, `config.json`, `mcp.token` and `pairing.key`. A
running observer keeps the previous token in memory until it is restarted;
restarting also invalidates issued OAuth access tokens (client registrations
are kept). Rotate the production token after the earlier terminal-log
exposure — but never execute it without the owner's approval.

## Local HTTP surface

Implemented protections, to be preserved:

- Loopback-only default bind (`127.0.0.1`); serving outside loopback is an
  explicit opt-in with `public_origin`.
- Owner / MCP / OAuth token separation with constant-time comparisons.
- `Host` and `Origin` allowlist (the configured `public_origin` is the only
  additional allowed authority).
- Bounded concurrency: 32 request slots, explicit 503 instead of hangs.
- 1 MiB body limit; oversized bodies are drained to return a clean 400;
  chunked bodies and invalid or non-finite JSON are rejected.
- Per-IP rate limits: authorize 30/min, oauth 60/min, reveal 10/min,
  general 80/min.
- Strict response policy: CSP `default-src 'none'` with `'self'` scripts and
  styles, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Cache-Control: no-store`.
- Stateless MCP transport (POST only, no unsolicited SSE stream).
- Exact-name static allowlist; directories, configuration, logs and secrets
  are never served.
- `POST /api/reveal` is owner-only, rate-limited and audited without recording
  the secret value.
- Abort requires `allow_abort` plus the exact typed native session ID;
  shutdown requires the explicit `STOP OBSERVER` confirmation.
- The path scanner is bounded (depth, 6000 directories, 12 s, no symlink
  traversal, skips `auth.json` and `.env`).
- `scripts/check_secrets.py` scans the repository and local evidence
  directories, prints only path/line/label/length, and fails CI on a hit.
- Translation dictionaries cannot weaken escaping: every rendered user or
  source text remains HTML-escaped.

## Privilege boundaries

* Owner key: full panel including settings, assessments, shutdown.
* MCP token / OAuth access token: read tools plus `report_event` only
  when reporting is enabled. They can never change settings, stop the
  observer, or abort agents.
* Agent abort is doubly gated: `allow_abort: true` in config **and** the
  owner typing the exact native session id. There is no Codex-log abort.
* `report_event` submissions are caller claims: no token accounting,
  no work started, no status override of native state.

## Source handling

OpenCode databases open read-only; Codex logs, router ledgers and git
are read, never written. The live OpenCode API is contacted only at
explicitly configured loopback URLs — no port scanning, no second
server, no agent commands. The opt-in folder scanner is bounded (depth,
6000 folders, 12 s, no symlink following) and never searches
`auth.json` / `.env`. Known-secret-pattern redaction in prompts and tool
output is best effort, not a guarantee; `show_prompts: false` reduces
exposure but does not make tool output safe to publish.

## Remote exposure (opt-in)

Remote MCP/ChatGPT access requires the owner to configure `public_origin`
(empty by default, i.e. effectively off), terminate TLS in a reverse
proxy/tunnel the app does not provide, forward the accepted Host
untouched, and keep Origin/Host checks enabled. OAuth uses DCR with a
callback allow-list, PKCE S256, single-use codes, audience-bound tokens
with hourly expiry and rotation on refresh. OAuth redirect and pairing
material must never travel through chat or third-party servers.

## Reporting a problem

Open an issue in this repository with: version/branch, OS + Python,
what you expected, what happened, and redacted logs (scrub tokens,
keys, callback URLs and absolute home paths first). Do not file live
secrets; if you did, rotate them per the procedure above.
