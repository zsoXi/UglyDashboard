# Changelog

## 6.0.0 — Mission Control V6

Working branch: `feat/mission-control-v6`. Implemented and verified in the
isolated V6 worktree; the running v5 instance was not modified.

### Data completeness (C.1)

- One shared coverage contract across snapshot, analytics, JSON/CSV export and
  MCP: metadata vs aggregates vs details vs per-day/per-model/per-file
  breakdowns, progress counts, freshness and stale/blocked read states.
- Completeness is scoped to the selected sources and time range;
  `history_limited` marks a bounded session window, unknown values stay
  `null` instead of a fake zero.
- CSV export carries the same block in the `X-Mission-Control-Coverage` header,
  and a downloaded CSV repeats it in the file body as a trailing `# coverage`
  metadata row, so the artifact stays self-describing;
  "totals complete, detailed history limited" is informational, not a warning.
- Codex usage aggregates are durable: every read checkpoint stores the
  processed session snapshot, so a restart republishes every accounted session
  (sums, models, days) instead of losing history or re-reading unchanged logs.

### English / Polish (D.1)

- Full offline localization with two dictionaries (454 stable keys each),
  English default for new installs, persisted topbar switch (`html lang`
  updated; filters, view and inspector preserved).
- `Intl` dates, numbers, currency and plurals; machine identifiers, model
  names and source text are never translated.
- `scripts/check_i18n.mjs` enforces dictionary parity and detects missing keys,
  raw keys, hardcoded Polish text and mojibake; wired into `npm run check`.

### Usage report (D.2)

- Periods: Today / 7 / 30 / 90 days / last year / all recorded history from the
  shared aggregates; one source+period filter for every element.
- Summary cards (tokens, sessions, recorded cost, estimated cost, unknown-cost
  count) with an explicit currency note.
- Reasoning fold and percentage composition toggles change presentation only,
  never totals; sessions-in-period and projects-in-period panels; files panel
  with an `Unassigned` row and a heuristic label; heatmap separates missing
  records from confirmed zeros.

### Production frontend (E.1)

- The observer serves the built artifact from `web/dist` and verifies every
  file against `web/dist/manifest.json` (sha256). A missing or mismatched build
  yields a readable instruction page and 503 for assets — never a silent
  fallback to unbuilt sources.
- `--dev-web` explicitly serves `web/` sources (with an exact-name `/i18n/*`
  allowlist); the browser suite rebuilds the bundle before testing.

### State migration (E.2)

- Versioned, transactional, idempotent v5→V6 observer migration: schema v2 adds
  the `meta` marker and the durable `usage_checkpoint` table in one explicit
  transaction; a newer schema is refused.
- A consistent pre-migration copy is created with the SQLite backup API
  (`observer.sqlite.pre-migration-v1-to-v2-<timestamp>`); `-wal`/`-shm`
  sidecars are never handled by hand.
- Legacy configuration keeps every known setting; unknown keys are archived
  under the `migrated_config_backup` setting. CLI: `--migrate-state`
  (exit 0/1/2; refuses while an observer still answers).

### MCP and security (E.3)

- MCP protocol checks for both supported versions, stable read tools,
  conditional `report_event`, strict argument validation, resources, pagination
  and coverage consistency with the UI; no settings, secrets, abort or
  shutdown access; stdio stdout stays JSON-RPC only.
- Security review kept loopback bind, owner/MCP/OAuth separation, Host/Origin
  allowlist, rate limits, CSP and owner-only reveal intact;
  `--rotate-owner-token` remains the controlled rotation procedure.

### Incremental read correctness (E.7)

- Durable Codex checkpoints now store `mtime_ns`, the reader offset and the
  file identity: a rewrite that keeps the byte size is detected by its changed
  mtime and re-read (after the next poll and after a restart alike), and a
  restored reader continues from the durable offset while the checkpoint keeps
  the cumulative counter, so appended cumulative readings apply as deltas
  without double counting.
- A file changed beyond the one-cycle read budget is still published from its
  last known snapshot and remains flagged pending: completeness is computed
  against the live file state, so a batched cycle can no longer hide changed
  sessions behind `aggregates_complete`.
- OpenCode aggregates re-verify completed sessions with a revision (row count,
  `MAX(rowid)`, total payload bytes, newest key) plus a bounded content probe of
  the newest rows; an in-place edit that keeps the row count and byte totals is
  re-aggregated instead of trusted. The residual limit for edits buried in
  older rows is documented in `docs/V6_COVERAGE.md`, not silently ignored.
- Period breakdowns built on evicted detail (the per-session `usage_events`
  cap) are partial by design and labelled as such; they are not presented as
  full analytics.

### Incremental read correctness (E.8)

- Codex restart, partial line: the durable checkpoint represents a consistent
  reader state (a safe offset after the last complete line, `resolved`). An
  unfinished trailing line is read again from that position and closed exactly
  once, `complete`/`aggregates_complete` are not claimed while any read byte is
  still an open line, and a finished file resumes from the checkpoint without
  re-reading its history.
- Codex restart, append while stopped: a file changed while the observer was
  off is restored from its checkpoint (offset, identity, mtime, cumulative
  counter) in the read path too, and a rebuild publishes the last good state
  instead of a lower partial sum, so the first poll after a restart shows the
  current total rather than a re-read from zero.

### Numbers

- Python: 197 tests, 0 failures, 2 environmental skips, 0 ResourceWarnings.
- Browser: Playwright 38/38 on the production `dist`.
- Benchmarks (expectations from the generator): 1000 sessions / 100k events =
  12 347 213 tokens exact, full coverage 10.6 s (1 cycle); 1000 sessions /
  1M events = 126 001 216 tokens exact, full coverage 127 s (7 cycles);
  mid-import restart resumed to the exact total (87 317 016 → 126 001 216, no
  double counting). Memory is reported as tracemalloc peak (90 MB / 243 MB);
  process RSS is unavailable on this host (`null`).

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
