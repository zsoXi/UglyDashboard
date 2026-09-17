# Synthetic large-data benchmarks

Reproducible load measurements for the real `Engine.poll()` /
`Engine.analytics()` code paths. All data is synthetic and lives in a
temporary directory; no user database, log, secret or home path is read
or written. Result files in this directory contain only sanitized data
(no filesystem paths, no usernames). Full console logs are kept out of
the repo under `artifacts/team/muse2/`.

## How to run

```powershell
python -X utf8 scripts/benchmark.py
python -X utf8 scripts/benchmark.py --sessions 1000 --events 1000000
python -X utf8 scripts/benchmark.py --output docs/benchmarks/result.json
```

Defaults: 1000 sessions, 100000 events, `history_limit` 1000. The fixture
mirrors the regression-suite SQLite schema (`project/session/message/part`)
plus the indexes a real OpenCode database has, so keyset paging behaves
as in production. Events are spread across sessions (about 100 per
session by default), so no single request loads unbounded per-session
history; the production caps (`MAX_OC_MESSAGES_PER_SESSION`,
`MAX_OC_PARTS_PER_SESSION`, `MAX_OC_PARTS_TOTAL`) stay in force and any
truncation is recorded in the `coverage_*` fields.

What is timed (wall clock, `perf_counter`):

* `parse_cold_seconds` — `read_opencode()` straight against the fixture.
* `poll_cold_seconds` — one cold `Engine.poll()` on a fresh state dir,
  untraced, exactly as production runs it.
* `analytics_cold_seconds` / `analytics_warm_seconds` — first
  `Engine.analytics()` (aggregation) and second call (ordered-dict cache
  hit, `ANALYTICS_CACHE_MAX=16`).

Memory is reported honestly per probe (see `memory_method` in each JSON):
tracemalloc peak is Python allocations in bytes; stdlib `resource` is
used only where it exists (never on Windows); on Windows the process
working set comes from psapi in bytes. A probe that did not run is not
reported. Timings come from the untraced run because tracemalloc
overhead alone can trip the bounded query guard (observed: traced cold
poll aborted at ~12.3 s while succeeding untraced).

## Status note (2026-09-16): pre-fix vs post-fix

The million-event collector timeout was fixed by DS-2 (bounded soft
deadline + partial coverage instead of an all-or-nothing abort). The
pre-fix JSONs (`result-win-py314.json`, `result-win-py314-1m.json`) are
kept unchanged for before/after evidence; the post-fix runs are the
separate `*-after.json` files below, produced with the same script and
defaults. The post-fix stress run still does not load the full
1000-session history inside the budget — that is a deliberate, recorded
limit, not a silent failure (see the coverage fields and the UI
`Statystyki niepełne` notice).

## Pre-fix results — Windows, Python 3.14.3 (2026-09-16)

### Default: 1000 sessions / 100000 events (`result-win-py314.json`)

* Fixture: 24.8 MB SQLite, generated in ~0.6 s.
* Cold parse (`read_opencode`): ~1.4 s, full coverage, no truncation.
* Cold `Engine.poll()`: **12.0 s on re-run (29.2 s on first run)** —
  the DB read is ~1.4 s of that; the rest is Engine overhead
  (snapshotting plus per-session observer-store writes). Single-number
  timings on this machine vary run to run; treat the range as the result.
* Analytics cold ~0.02 s, warm ~0.001–0.003 s (cache works as designed).
* Memory: tracemalloc peak ~25.6 MB Python allocations during cold poll;
  process working set ~175 MB, peak ~234 MB (whole interpreter).
* Coverage: `total_sessions=1000, loaded_sessions=1000`,
  `parts_loaded=98000`, `truncated=false`.

### Stress: 1000 sessions / 1000000 events (`result-win-py314-1m.json`)

* Fixture: 247 MB SQLite.
* **Both the direct reader and the untraced cold poll abort with
  `OperationalError: interrupted`: the 12-second per-connection query
  guard fires, the database source reports `ok=false`, and the poll
  publishes 0 sessions.** The per-session/parts caps never get a chance
  to degrade gracefully because the guard is all-or-nothing per source.
* Minimal reproduction: `python -X utf8 scripts/benchmark.py --events 1000000`
* Reported to DS-2 in `artifacts/team/muse2/CROSS_SCOPE.md`; not edited
  here (Python collectors are DS-2 owned).

## Post-fix results — Windows, Python 3.14.3 (2026-09-16)

### 1000 sessions / 100000 events (`result-win-py314-after.json`)

* Cold `Engine.poll()`: **8.91 s** (was ~12.0 s), full coverage
  (`total_sessions=1000, loaded_sessions=1000, truncated=false`).
* Cold parse ~1.39 s; analytics cold ~0.024 s / warm ~0.003 s.
* Memory: tracemalloc peak ~32.2 MB Python allocations; process working
  set ~238 MB peak (whole interpreter).

### 1000 sessions / 1000000 events (`result-win-py314-1m-after.json`)

* Fixture: 247 MB SQLite.
* Cold `Engine.poll()`: **12.63 s**, publishing **96 of 1000 sessions**
  with `deadline_exceeded=true`, `truncated=true` and an explicit
  source error ("Read exceeded its deadline; partial coverage."). The
  direct reader reports `loaded_sessions=95`. Instead of aborting to 0
  sessions (`OperationalError: interrupted`), the reader now stops at
  the soft deadline, keeps the newest sessions it already read, and
  records the incomplete coverage so the dashboard marks it.
* Analytics over the published window: 96 sessions.
* Minimal reproduction:
  `python -X utf8 scripts/benchmark.py --events 1000000`
* **Known limit, accepted and marked:** a full cold read of all 1000
  sessions at ~0.13 s/session would take ~100 s+ and defeat the 10 s
  soft budget whose purpose is to never blank the view. The UI shows
  "Statystyki niepełne — to nie cała historia. … niepełne: 96 z 1000
  sesji (przekroczono limit odczytu)". No claim of a full 1000-session
  load is made for the stress fixture.

## Limits of these numbers

* One Windows machine, no controlled environment; run-to-run variance is
  real (see the 12 s vs 29 s cold poll above).
* tracemalloc covers Python allocations only, not native/SQLite memory.
* No user data, no network, no browser involved.
* CI does not run this benchmark (too heavy); it is a manual,
  reproducible procedure.
