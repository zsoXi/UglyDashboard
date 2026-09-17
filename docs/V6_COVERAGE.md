# Data model and completeness contract (V6)

Every number the panel shows comes from local sources read read-only. This
document defines what the numbers mean, which ones can be complete at which
moment, and how incompleteness is reported. The same coverage block is shared
by the snapshot API, analytics, JSON/CSV exports and MCP, so no surface tells a
different story than another.

## Sources are read-only

* OpenCode SQLite databases (`--db`, default discovery) and Codex rollout logs
  are opened read-only; the observer never writes to them.
* The observer's own state (aggregates, checkpoints, reports, assessments)
  lives in its private state directory (`--state-dir`,
  `~/.opencode-mission-control` by default).
* If a source cannot be read, the panel reports that condition (see "Freshness
  and failures") instead of mixing old data into fresh totals.

## Token normalization

Usage is normalized into one record shape:
`input`, `output`, `reasoning`, `cache_read`, `cache_write`, `total`.

* OpenCode (`oc_usage`): values come from the provider usage object; the
  provider's `cache.read` becomes `cache_read` and `cache.write` becomes
  `cache_write`. An explicit provider `total` is preserved exactly; only when
  it is absent is the total the sum of the normalized fields.
* Codex (`codex_usage`): `cached_input_tokens` (or
  `cache_read_input_tokens`) is a subset of `input`, so it is recorded as
  `cache_read` and subtracted from `input`; `reasoning_output_tokens` is a
  subset of `output`, so it is recorded as `reasoning` and subtracted from
  `output`. The total uses `total_tokens` when present, otherwise raw
  `input + output`.
* Costs, tables, exports and MCP reuse these records; individual views do not
  re-sum raw provider fields.

## Aggregates and the bounded detail window

* Session totals are accumulated into a durable per-source
  `usage_checkpoint`, so aggregates survive restarts and progress
  independently of how much detail is kept. For Codex, every file's read
  checkpoint stores the processed session snapshot as well, so a restart
  republishes all accounted sessions instead of re-reading unchanged logs.
* Detailed usage events are kept in a bounded window per session. When the
  window drops events, the dropped count is reported
  (`detail_events_evicted`) and the session is flagged, so the affected
  breakdown can be partial.
* Consequently aggregates can be complete while details are limited. At the 1M
  benchmark fixture, session aggregates are complete for 1000/1000 sessions
  while only 148 sessions have full details in the window. This is reported,
  not hidden.

## The coverage block

Fields shared by the snapshot and analytics surfaces:

| Field | Meaning |
| --- | --- |
| `scope` | What the block describes: the loaded window (snapshot), or a range with `days`, `project`, `task_group`, `source`, `sessions_in_range`. |
| `metadata_complete` | `true`/`false`/`null` - whether source metadata (the session list) is complete for the window; `null` means unknown (no data yet). |
| `aggregates_complete` | The same three-state conclusion for usage aggregates. |
| `history_limited` | `true` when `metadata_complete` is `false` - the loaded history itself is limited. |
| `breakdowns` | Per-breakdown statuses: `daily`, `model`, `file` - each `complete`, `partial` or `unknown`. |
| `breakdown_details` | Counts behind the statuses: `sessions_scored`, `daily_partial_sessions`, `model_partial_sessions`, `file_partial_sessions`. |
| `details_truncated` | `true` when any scored session may still change its details. |
| `detail_events_evicted` | Number of usage events evicted from bounded detail windows. |
| `catching_up` | `true` while aggregates are still being rebuilt (fresh install, migration or resumed import). |
| `source_stale` | A previously readable source failed its latest refresh; the last complete snapshot is still served. |
| `read_blocked` | A source could not be read at all (no usable snapshot). |
| `discovered_sessions` / `processed_sessions` | Discovery vs processed counts when known, otherwise `null` - never a fake `0`. |
| `last_successful_read_at` | The oldest of the sources' last successful read times. |

The source-wide conclusions follow one rule: `true` only when every source
explicitly reports `true`; any explicit `false` makes the conclusion `false`;
otherwise it is `null` (unknown). Breakdown statuses are computed only from
the session flags they receive, so a complete overall total never implies a
complete per-day, per-model or per-file split.

## Per-session flags behind the breakdowns

Each scored session carries these flags:

| Flag | Complete when |
| --- | --- |
| `ledger` | no usage events were evicted and the kept event ledger sums exactly to the session total. |
| `daily` | `ledger` holds and every kept event has a day timestamp. |
| `model` | `ledger` holds and per-model totals sum exactly to the session total. |
| `file` | the detail window kept the whole history (no pending/truncated detail); file attribution needs full detail. |
| `detail_pending` | set when parts, messages or aggregates were truncated, or detail is still pending. |
| `aggregate` | `false` while this session's aggregates are still catching up. |

`daily`, `model` and `file` become `partial` as soon as a single scored session
fails its flag.

## Files view heuristic

Per-file usage distributes a session's usage equally across the files the
session touched. Rows that cannot be attributed (no files recorded) stay in
`Unassigned`, and the view labels the allocation as a heuristic - it is an
estimate, not measured per-file usage.

## Freshness and failures

* `source_stale`: the source had a complete snapshot, but the latest refresh
  failed; the panel keeps serving the last complete snapshot and flags it.
* `read_blocked`: the source has no usable snapshot (for example a permission
  or I/O failure); numbers that depend on it are missing rather than wrong.
* Both flags are part of the shared block, so exports and MCP report the same
  condition as the UI.

## One block, every surface

* Snapshot API and UI: the coverage block for the loaded window, rendered as
  structured notices (informational, incomplete, blocked) instead of silent
  guesses.
* Analytics: range coverage recomputed over the selected sessions;
  `catching_up` is range-precise - a global catch-up that cannot affect the
  selection does not flag it.
* Exports: JSON carries the block; CSV responses carry it in the
  `X-Mission-Control-Coverage` header and a downloaded CSV repeats it in the
  file body as a trailing `# coverage` metadata row.
* MCP: coverage-reading tools return the same block, and the MCP suite checks
  its consistency with the HTTP snapshot.

Regression coverage: `tests/test_v6_coverage.py` (8 tests) verifies the
contract, including `history_limited`, the three-state conclusions, `null`
instead of fake zero, scoped breakdowns, range precision and CSV/MCP parity.
