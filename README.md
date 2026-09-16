# OpenCode Mission Control v5

Local observer dashboard for OpenCode, Codex logs, projects, agents,
models, history and MCP. One owner, one machine: it reads your local
sources read-only and presents activity, analytics, alerts and
integrations in a browser panel. It does not run agents, send commands
to them, or modify your repositories.

> Status: v5 hardening in progress on branch
> `fix/mission-control-v5-hardening-ui` (Python hardening, strict
> frontend types/build, browser tests, delivery tooling). Anything below
> marked *pending* is not yet landed; nothing here claims an unrun
> check passed.

## Package layout (v5, not the old single file)

```text
opencode_dashboard.py      Thin launcher / compatibility API (imports mission_control)
mission_control/           Backend package: cli, core, engine, locking,
                           mcp, oauth, server, sources, store
web/                       Frontend sources (index.html, app.js, style.css)
scripts/build.mjs          Frontend bundle step (npm run build)
test_mission_control.py    Offline regression suite (root)
tests/                     Additional hardening suites
scripts/run_tests.py       Offline unittest runner (honest exit code)
scripts/smoke_startup.py   Real-dashboard smoke test on a loopback port
scripts/benchmark.py       Synthetic large-data benchmark (stdlib only)
docs/benchmarks/           Sanitized benchmark results + method notes
.github/workflows/ci.yml   Windows + Linux CI (Python 3.10/3.14, Node 22)
```

Older guides describing "one Python file with everything inside" are
obsolete: since the v5 split the HTML/CSS/JS live in `web/` and the
Python backend lives in `mission_control/`. The launcher keeps the old
command-line surface (`--db`, `--port`, `--self-test`, …).

Frontend sources live in `web/` and are bundled via `npm run build`
(esbuild → `web/dist/app.js` + `style.css` + `manifest.json` with
input/output hashes). Requirements: Node **≥ 22.13** and a clean
`npm ci` from the committed lockfile. The Python server serves the
`web/` sources directly; the bundle step is still required (and CI
runs it) to prove the shippable assets build reproducibly.

## Quick start (Windows)

Requires Python **3.10+**. Double-click `START_MISSION_CONTROL.cmd`
(uses `pyw`/`pythonw` when available so no console window stays open),
or from PowerShell — quote the path, installs often live under folders
with spaces or `!` characters:

```powershell
py -3 "D:\Path With Spaces\MissionControl\opencode_dashboard.py" --open
```

Default address: `http://127.0.0.1:8765`. The launcher opens an address
whose fragment carries a one-time owner key; the key stays in that tab's
`sessionStorage`. Never share the login-fragment URL. Closing the tab
does **not** stop the observer — use **Settings → Stop observer**
(console: Ctrl+C). Restarting the launcher reopens the panel when app
identity and owner key match.

If the port is taken, pick another:

```powershell
py -3 opencode_dashboard.py --open --port 8766
```

Linux works the same with `python3`:

```powershell
python3 opencode_dashboard.py --open --port 8765
```

Verified so far on Windows / Python 3.14.3 (see `TEST_REPORT.json`);
Linux CI runs the same suite on every push (`.github/workflows/ci.yml`,
pending first green run).

## Connecting your existing OpenCode

Point the panel at your database (repeat `--db` for several). Example
uses a placeholder — substitute your real username:

```powershell
py -3 opencode_dashboard.py --open --db "$env:USERPROFILE\.local\share\opencode\opencode.db"
```

For *confirmed current* activity also add the HTTP address of the
already-running OpenCode instance ("Connect existing OpenCode",
default candidate `http://127.0.0.1:4096`; the desktop port may differ).
The database alone gives history, not proof the process is still
working. The panel never starts a second OpenCode server, never scans
ports, never sends agent commands, and only talks to explicitly listed
loopback addresses. If that server needs Basic Auth, export
`OPENCODE_SERVER_PASSWORD` (and optional `OPENCODE_SERVER_USERNAME`) in
the panel's environment — never paste passwords into URLs or chats.

The reader adapts to the SQLite columns it finds instead of assuming one
schema; an incompatible future schema surfaces in source health, it does
not silently misread.

## Connecting Codex logs

Default is the local `.codex` directory (honours `CODEX_HOME`);
override with `--codex-home` or config:

```powershell
py -3 opencode_dashboard.py --open --codex-home "$env:USERPROFILE\.codex"
```

Reading is incremental and tolerates unfinished JSONL lines, log
rotation, partial UTF-8 and corrupt records; selection window and skips
are reported. Local logs never show cloud-only work and are not a
process-liveness probe. A turn-finished event means the turn finished —
not that the task passed tests.

## Codex as a local MCP client

Run the panel, open **Sources & MCP → Codex · local**, and copy the
generated TOML fragment into the Codex MCP config. It already contains
the real interpreter path, the current file, and the state directory:

```toml
[mcp_servers.mission_control]
command = "C:\\Path\\To\\Python\\python.exe"
args = ["D:\\MissionControl\\opencode_dashboard.py", "--mcp-stdio", "--state-dir", "C:\\Users\\you\\.opencode-mission-control"]
startup_timeout_sec = 20
tool_timeout_sec = 30
```

The stdio bridge does not spawn a second observer: it reads the port
from `runtime.json` plus a separate local MCP token. The panel must be
running. Use console `python.exe` for stdio even if the UI was started
via `pythonw.exe`. An HTTP variant is also generated in the UI and needs
`MISSION_CONTROL_MCP_TOKEN` in the Codex environment — keep it secret.

## ChatGPT as a remote MCP client (manual setup)

**Nothing here connects to your ChatGPT account automatically, and this
bridge cannot magically read all your ChatGPT conversations.** Only
calls that go through this bridge — plus events someone explicitly
reports via `report_event` — are visible. Setup is on you:

1. Put a stable HTTPS tunnel or reverse proxy in front of the local
   panel port. The app neither installs nor opens one. Remote MCP works
   only over external HTTPS; plain local use needs no tunnel.
2. In MCP settings set `public_origin` (e.g.
   `https://mc.your-domain.example`, no path) and the exact OAuth
   callback URLs your ChatGPT client shows. Default accepted callback is
   the official `https://chatgpt.com/connector_platform_oauth_redirect`.
3. Create the ChatGPT connection to `https://your-host/mcp` with OAuth
   and dynamic client registration (DCR). Do not invent static client
   credentials.
4. On *this observer's* authorize page paste the pairing key from the
   local panel. Never send it in chat or to a foreign MCP server.

Remote OAuth is effectively **off by default** (empty `public_origin`,
no public exposure). The implementation covers server/resource metadata,
DCR with callback allow-list, PKCE S256, single-use codes, audience-bound
tokens, rotation on refresh, and revocation. Remote access excludes owner
settings and agent stops. Access tokens expire after one hour; observer
restart invalidates issued tokens but keeps client registrations. This is
a single-owner local tool, not an audited multi-user identity product:
terminate TLS properly, restrict traffic, forward the accepted Host
untouched, and never disable Origin/Host checks to "fix" a tunnel.
End-to-end login against a real ChatGPT account has not been tested;
protocol and OAuth flows were verified with a controlled local client.

## MCP tools

Default read tools: `mission_overview`, `list_agents`, `agent_details`,
`list_projects`, `timeline`, `model_comparison`, `alerts`, `sources`,
`search`, `fetch`. Enabling reporting adds `report_event` (opt-in,
`enable_reporting`, off by default). Suggested client instruction:

> Check mission_overview, then list_agents. Separate confirmed activity
> from historical and reported. Give project, real model and last tool.
> Do not count agent definitions as running workers.

`report_event` needs an existing session id from `list_agents`; it is a
caller claim (no token accounting, no work started). Repeating an
`event_id` is idempotent; changing content under one id is rejected.

## What states and numbers mean

`verified` = fresh status from the OpenCode API. `recorded` = stored
state/marker in source data. `reported` = someone's claim. `unknown` /
`stale` = insufficient or expired evidence. A recent timestamp alone
never makes RUNNING; inspector state expires past the freshness window.

A stored parent id does not prove a sub-agent: only a delegating tool
call (or explicit child-launch info) upgrades to `delegated`; forks stay
separate. The graph never invents CTO/TL roles from names and shows at
most 120 nodes.

Token math: cache/reasoning normalized per source; message records and
their step-finish are not double-counted; cumulative Codex counters are
not re-added per read; the router ledger stays separate (it can overlap
native sessions). Session age is not model work time. File tables split
session tokens evenly across noted files — labelled as allocation, not
measured per-edit cost. Cost comes from stored data or explicitly
configured USD-per-million rates; there are no guessed built-in prices.

Alerts only alarm (stale source, model mismatch, errors, tool loops,
budget, out-of-scope edits, file conflicts): set exact model ids in
`expected_models` and folders in `allowed_paths`. Stopping an OpenCode
agent needs explicit `allow_abort: true` **and** the exact native id
typed by the owner; plain MCP/OAuth tokens can never abort, and Codex
logs have no abort at all.

## Scanning, retention, privacy

Scan chosen folders (e.g. your projects dir), never whole disks: bounded
depth, 6000 folders, 12 s, no symlink following, `auth.json`/`.env`
never searched. Results are checkbox-selected, monitoring starts only on
separate approval. Sources are opened read-only; own state lives in
`~/.opencode-mission-control` (`config.json`, `observer.sqlite`,
`runtime.json`, logs, `owner.token`, `mcp.token`, `pairing.key`) — the
three keys are confidential, never commit or sync that directory.

Capped coverage (defaults; source limits are shown in the panel):

| Source | Cap |
| --- | --- |
| OpenCode DB sessions | `history_limit` 1000 newest per DB |
| Codex log files | 400 newest |
| Messages / session | 800 newest |
| Parts / session | 4000 newest, 250000 total |
| Events / session | last 120 |
| Own event history | 90 days retention |
| Agent graph view | 120 nodes |
| Analytics cache | 16 entries |

Prompts/tool outputs may carry secrets; known-key redaction is best
effort, not a guarantee. `show_prompts: false` hides prompts/definitions
but does not make tool output safe to publish. On Windows, file
permissions additionally depend on directory ACLs and the user account.

## Engine lifecycle and locking (as implemented)

`Engine` (`mission_control/engine.py`) collects sources into an
immutable published snapshot. `lock` (RLock) guards
sessions/snapshot/config/facts/caches; `poll_lock` serializes collector
cycles; all network/database/git I/O happens **outside** `lock`, and
published objects are copy-on-write swapped under `lock`. Lifecycle:
construct → `start()` (background `poll()` loop) → `poll()` per cycle →
`close()`; any use after shutdown raises `LifecycleError`. Corrupt local
secrets raise `SecretError` instead of silently rotating — recovery is
explicit (delete the token file while stopped; a fresh secret is created
on next start) and quarantines the corrupt bytes to a `.bak` file.

## Verification (actual results only)

* Regression: **144 run, 0 failed, 2 skipped** (Windows, Python 3.14.3,
  ~37 s, zero `ResourceWarning`s) via `python -X utf8
  scripts/run_tests.py`. Skips: symlink creation unavailable, POSIX
  permission assertion (Windows uses ACLs).
* Built-in self-test: **10/10** via `opencode_dashboard.py --self-test`.
* Lint: `ruff check` is clean (0 errors).
* Synthetic benchmark (post-fix, `docs/benchmarks/*-after.json`):
  1000 sessions / 100 k events → cold parse ~1.4 s, cold poll **8.9 s**,
  full coverage; 1 M events → cold poll **12.6 s** publishing **96 of
  1000** sessions with `deadline_exceeded=true` / `truncated=true` (was 0
  sessions / `OperationalError: interrupted`). The incomplete window is a
  recorded, accepted limit and is marked in the UI ("Statystyki
  niepełne"). Details and honest memory method in
  `docs/benchmarks/README.md`.
* CI (`.github/workflows/ci.yml`, Windows+Ubuntu × Python 3.10/3.14,
  Node 22, ruff/pinned, self-test, regressions, `npm run check`,
  required Playwright on both OSes with synthetic-only failure
  evidence): **not yet run on GitHub** — no green claim until it is.
* Browser tests: `playwright.config.mjs` (MUSE-1), global setup spawns the
  synthetic fixture (`scripts/browser_fixture.py`, real Engine + Server,
  ephemeral data). **27/27 pass locally** (desktop + mobile) via
  `npx playwright test`; publishable screenshots land in
  `docs/screenshots/`, extra captures stay under `artifacts/`.
* Frontend gates (DS-1): `npm run lint`, `npm run typecheck` (strict),
  `npm run format:check` and `npm run build` (reproducible bundle) all
  pass — re-verified locally 2026-09-16 (Windows, repo Node).

```powershell
py -3 opencode_dashboard.py --self-test
py -3 scripts/run_tests.py
py -3 scripts/smoke_startup.py
py -3 scripts/benchmark.py
```

Full log: `artifacts/unittest.log` (local, git-ignored). Machine summary:
`TEST_REPORT.json`.

## Integration references (checked 2026-09-16)

* OpenCode server: https://opencode.ai/docs/server/
* Codex MCP: https://developers.openai.com/codex/mcp
* OpenAI app auth: https://developers.openai.com/plugins/build/auth
* MCP Streamable HTTP: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
* MCP tools: https://modelcontextprotocol.io/specification/2025-11-25/server/tools

Negotiated MCP versions are `2025-11-25` and `2025-06-18` only. Local
log formats evolve independently of the MCP spec.

## Rollback

`backup/opencode_dashboard_original.py` keeps the previously shipped
file. Stop the new observer, keep its state dir aside, and restore the
copy. OpenCode/Codex source data needs no restore — this app never
writes it.
