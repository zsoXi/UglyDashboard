# Incremental aggregation benchmark (V6)

Evidence for the V6 collector and the completeness contract under load. The
benchmark is fully synthetic: it generates a temporary OpenCode-shaped SQLite
fixture and drives the real `Engine` through poll cycles until aggregate
coverage is complete. No user database, session, log or secret is read.

## How to run

```powershell
python -X utf8 scripts/benchmark_incremental.py
python -X utf8 scripts/benchmark_incremental.py --events 1000000
```

## Method

* The generator writes a temporary fixture with the OpenCode schema
  (`project`, `session`, `message`, `part`) and embeds usage events in message
  data.
* The expected token sum comes from the generator's own arithmetic (an
  independent formula), never from the production usage helpers, so a reader
  bug cannot make the expectation agree with itself.
* The real `Engine` runs repeated poll cycles on the fixture until coverage
  reports complete. Measured: metadata visibility after the first cycle,
  cycles and seconds to full coverage, overview (`Engine.view`) latency while
  the import is still running, analytics cold/warm latency, and memory
  (`tracemalloc` peak; the Windows working-set probe is reported separately
  when available).
* Each run ends with restart checks: stop mid-import, start a fresh engine on
  the same state directory, verify the sum continues without loss or double
  counting; then restart after completion and verify the sums are unchanged.
* Fixture paths are sanitized, the temporary directory is removed afterwards,
  and the JSON summary is written outside version control.

## Results - Windows, Python 3.14.3 (2026-09-17)

| Metric | 100k fixture | 1M fixture |
| --- | ---: | ---: |
| Sessions | 1,000 | 1,000 |
| Usage events | 100,000 | 1,002,000 |
| Parts | 98,000 | 1,000,000 |
| Expected total tokens (generator) | 12,347,213 | 126,001,216 |
| Received total tokens (engine) | 12,347,213 | 126,001,216 |
| Cycles to full coverage | 1 | 7 |
| Full coverage time | 10.56 s | 126.946 s |
| Metadata visible after first cycle | 10,510.2 ms | 18,490.9 ms |
| First overview while importing | 20.4 ms | 23.1 ms |
| Analytics cold / warm | 0.033 s / 0.001 s | 0.027 s / 0.002 s |
| tracemalloc peak | 90,318,555 B | 242,816,596 B |
| Working set (psapi) | not reported (null) | not reported (null) |
| Detail window | all sessions | 148 of 1,000 sessions with full details (aggregates complete for 1,000/1,000) |

Expected and received sums match exactly at both sizes.

Restart behaviour:

* Mid-import restart: the first cycle stopped at 87,317,016 tokens; a fresh
  engine on the same state directory resumed and reached 126,001,216 in 1
  additional cycle - sums match, no double counting.
* Restart after full import: totals unchanged for both fixture sizes.

## Comparison with the Stage C baseline

Stage C measured 9.5 s / 1 cycle (100k) and 103.6 s / 6 cycles (1M). This run
measures 10.56 s / 1 cycle and 126.946 s / 7 cycles - roughly 11% and 22%
slower. Expected sums and restart behaviour are unchanged. The difference is
consistent with the completeness bookkeeping added in C.1 (coverage flags,
ledger checks, checkpoint writes) plus machine load. The original Stage C
numbers remain valid for the code as measured then and are not rewritten.

## Where these numbers appear

`TEST_REPORT.json` (machine-readable) and `docs/V6_STATUS.md` (stage summary).
