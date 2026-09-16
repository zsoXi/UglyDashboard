# Changelog

## 5.0.0 — hardening + redesigned UI

Working branch `fix/mission-control-v5-hardening-ui`. Only executed runs
are claimed; unverified items stay marked pending.

Done and locally verified (Windows, Python 3.14.3, Node 24.14.0):

* Backend hardening (DS-2): bounded soft read deadline
  (`OPENCODE_READ_SECONDS = 10.0`) with partial coverage instead of an
  all-or-nothing abort; per-entry router diagnostics; oversized-body
  drain returns HTTP 400; secret recovery hardening. Regression suite
  **144 tests, 0 failures, 2 skipped, 0 `ResourceWarning`s**; `ruff`
  clean.
* Frontend type-safety (DS-1): strict `tsc` 0 diagnostics, ESLint 0,
  Prettier clean, reproducible esbuild bundle; secrets reveal panel and
  stale async inspector fixed.
* Redesigned UI: light/dark theme, mobile drawer layout, rebuilt views.
* Browser tests (MUSE-1): full Playwright suite **27/27 pass**
  (desktop + mobile) against the synthetic fixture; the `#access`
  fragment is consumed and cleared, the timeline "load more" button hides
  correctly, and no owner token is written to logs (temporary probe
  removed).
* `VERSION` is now `5.0.0`, matching `package.json`; the backend, CLI,
  MCP server info and HTTP `Server` header all report it.
* Synthetic benchmark (post-fix, `docs/benchmarks/*-after.json`):
  1000 sessions / 100 k events → cold poll 8.9 s, full coverage; 1 M
  events → 12.6 s publishing 96 / 1000 sessions with
  `deadline_exceeded=true`. The incomplete window is an accepted, recorded
  limit and is marked in the UI ("Statystyki niepełne").

Pending / not claimed:

* CI (`.github/workflows/ci.yml`, Windows + Ubuntu, Python 3.10/3.14,
  Node 22, required Playwright): **not yet run on GitHub**.
* Real ChatGPT/Codex account login and the `frontend-design` plugin were
  not verified; no claim is made about them.

## 4.0.0 — prior baseline

Single-owner local observer: command center, ChatGPT MCP bridge with
OAuth/PKCE + DCR, Codex log reader, agent graph (120-node view),
shared event history, inspector with owner assessments,
source scanner, model/cost analytics, alerting, project overview.
Measured then on Linux/Python: 91 regression tests, 10 built-in
self-tests, 25 Chromium UI checks against synthetic fixtures only —
no Windows run, no real user database, no end-to-end account login,
no independent security audit. See the v4-era notes preserved in
`README.md` / `README_PL.md` verification sections.
