"""Etap C: Codex logs must reach full coverage in bounded batches.

The per-cycle file limit bounds ONE cycle; it must never mean that other
discovered logs are skipped forever. Each batch must publish the sessions it
processed (including files skipped as already complete) so the snapshot can
never lose a session that was already accounted for - including after a
restart, which must republish the durable checkpoints instead of re-reading
unchanged logs.
"""

import json
import tempfile
import unittest
from pathlib import Path

import mission_control as mc

# The product validates codex_file_limit in the 10..3000 range, so the batch
# bound is exercised with the smallest supported limit.
SMALL_BATCH = 10
FILE_COUNT = 12


def _usage(total):
    return {
        "input_tokens": total,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": total,
    }


def _write_session(home, session_id, total_tokens, created, when):
    logs = Path(home) / "sessions" / "2026" / "09" / "17"
    logs.mkdir(parents=True, exist_ok=True)

    def row(kind, payload, index):
        return {"timestamp": created + index, "type": kind, "payload": payload}

    usage = _usage(total_tokens)
    records = [
        row("session_meta", {"id": session_id, "cwd": str(Path(home) / "project")}, 0),
        row(
            "event_msg",
            {"type": "token_count", "info": {"total_token_usage": usage, "last_token_usage": usage}},
            1,
        ),
        row("event_msg", {"type": "task_complete", "turn_id": "turn-" + session_id}, 2),
    ]
    path = logs / ("rollout-%s-%s.jsonl" % (session_id, when))
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        "utf-8",
    )
    return path


def _expected_tokens(count=FILE_COUNT):
    """Independent generator arithmetic: totals are 100 + i * 10."""
    return sum(100 + index * 10 for index in range(count))


class CodexIncrementalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mc-v6-codex-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _config(self, limit):
        return {
            "db_paths": [],
            "codex_homes": [str(self.root / "codex-home")],
            "router_events": [],
            "opencode_urls": [],
            "projects": [],
            "git_enabled": False,
            "codex_file_limit": limit,
            "poll_seconds": 3,
        }

    def _engine(self, limit):
        home = self.root / "codex-home"
        for index in range(FILE_COUNT):
            _write_session(
                str(home),
                "cx-%02d" % index,
                100 + index * 10,
                1_700_000_000 + index * 100,
                "%02d" % index,
            )
        engine = mc.Engine(self.root / "state", self._config(limit))
        self.addCleanup(engine.close)
        return engine

    @staticmethod
    def _codex_source(engine):
        return next(s for s in engine.view()["sources"] if s.get("kind") == "codex")

    @staticmethod
    def _tokens(engine):
        return sum(s["usage"]["total"] for s in engine.view()["sessions"])

    def test_batched_cycles_reach_full_coverage_without_losing_sessions(self):
        engine = self._engine(limit=SMALL_BATCH)
        first_complete = None
        for _ in range(8):
            engine.poll()
            source = self._codex_source(engine)
            if first_complete is None:
                first_complete = int(source.get("files_complete") or 0)
            if source.get("aggregates_complete"):
                break
        source = self._codex_source(engine)
        # The batch really bounded the first cycle.
        self.assertLess(first_complete, FILE_COUNT)
        # Full coverage of all discovered logs, reached incrementally.
        self.assertEqual(source["files_found"], FILE_COUNT)
        self.assertEqual(source["files_complete"], FILE_COUNT)
        self.assertEqual(source["pending_files"], 0)
        self.assertTrue(source["aggregates_complete"])
        # Every session accounted exactly once.
        sessions = engine.view()["sessions"]
        self.assertEqual(len(sessions), FILE_COUNT)
        self.assertEqual(self._tokens(engine), _expected_tokens())
        # Re-polling an unchanged source must neither lose nor duplicate data.
        engine.poll()
        engine.poll()
        self.assertEqual(len(engine.view()["sessions"]), FILE_COUNT)
        self.assertEqual(self._tokens(engine), _expected_tokens())
        self.assertTrue(self._codex_source(engine)["aggregates_complete"])

    def test_larger_batch_processes_everything_in_one_cycle(self):
        engine = self._engine(limit=1000)
        engine.poll()
        source = self._codex_source(engine)
        self.assertEqual(source["files_complete"], FILE_COUNT)
        self.assertEqual(source["pending_files"], 0)
        self.assertTrue(source["aggregates_complete"])
        self.assertEqual(self._tokens(engine), _expected_tokens())

    def test_restart_republishes_durable_checkpoints_without_recounting(self):
        engine = self._engine(limit=1000)
        engine.poll()
        expected = _expected_tokens()
        self.assertEqual(len(engine.view()["sessions"]), FILE_COUNT)
        self.assertEqual(self._tokens(engine), expected)
        engine.close()
        # A fresh process on the same state directory must republish every
        # accounted session from the durable checkpoint payloads: no lost
        # history after a restart and no cumulative deltas applied twice.
        restarted = mc.Engine(self.root / "state", self._config(limit=1000))
        self.addCleanup(restarted.close)
        restarted.poll()
        source = self._codex_source(restarted)
        self.assertTrue(source["aggregates_complete"])
        self.assertEqual(source["pending_files"], 0)
        self.assertEqual(len(restarted.view()["sessions"]), FILE_COUNT)
        self.assertEqual(self._tokens(restarted), expected)
        payloads = restarted.store.checkpoints("codex")
        self.assertTrue(payloads)
        self.assertTrue(
            all(isinstance(entry.get("session"), dict) for entry in payloads.values())
        )
        # Idle polling after the restart must stay stable too.
        restarted.poll()
        self.assertEqual(len(restarted.view()["sessions"]), FILE_COUNT)
        self.assertEqual(self._tokens(restarted), expected)


if __name__ == "__main__":
    unittest.main()
