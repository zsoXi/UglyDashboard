"""R4 regression: completed OpenCode aggregates re-verify the source rows.

A row count alone cannot see an in-place edit that keeps the number of rows
(a corrected payload of the same length), so every completed checkpoint also
stores a revision (rows, max rowid, payload bytes, newest key). The observer
must re-aggregate instead of trusting a sum computed over changed evidence.
"""

import json
import sqlite3
import time
import unittest
from copy import deepcopy

from mission_control import incremental


def _part(amount):
    return json.dumps(
        {
            "type": "step-finish",
            "tokens": {
                "input": amount,
                "output": 0,
                "reasoning": 0,
                "cache": {"read": 0, "write": 0},
                "total": amount,
            },
        }
    )


class OpenCodeRevisionTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute(
            "CREATE TABLE part (id TEXT, session_id TEXT, time_created INTEGER, data TEXT)"
        )
        self.now = int(time.time() * 1000)
        self.checkpoints = {}

    def tearDown(self):
        self.con.close()

    def _commit(self, native_id, state):
        self.checkpoints[native_id] = deepcopy(state)

    def _aggregate(self):
        return incremental.aggregate_source(
            self.con,
            [("s1", self.now)],
            self.checkpoints,
            time.monotonic() + 5,
            self._commit,
        )

    def test_in_place_row_edit_with_same_length_is_re_aggregated(self):
        self.con.execute(
            "INSERT INTO part (id, session_id, time_created, data) VALUES (?, ?, ?, ?)",
            ("p1", "s1", self.now, _part(100)),
        )
        self._aggregate()
        self.assertEqual(self.checkpoints["s1"]["usage"]["total"], 100)
        self.assertTrue(self.checkpoints["s1"]["complete"])
        self.con.execute("UPDATE part SET data = ? WHERE id = ?", (_part(900), "p1"))
        self._aggregate()
        self.assertEqual(self.checkpoints["s1"]["usage"]["total"], 900)
        self.assertTrue(self.checkpoints["s1"]["complete"])

    def test_appended_rows_still_resume_from_the_stored_cursor(self):
        self.con.execute(
            "INSERT INTO part (id, session_id, time_created, data) VALUES (?, ?, ?, ?)",
            ("p1", "s1", self.now, _part(100)),
        )
        self._aggregate()
        self.assertEqual(self.checkpoints["s1"]["usage"]["total"], 100)
        self.con.execute(
            "INSERT INTO part (id, session_id, time_created, data) VALUES (?, ?, ?, ?)",
            ("p2", "s1", self.now + 10, _part(150)),
        )
        self._aggregate()
        self.assertEqual(self.checkpoints["s1"]["usage"]["total"], 250)
        self.assertTrue(self.checkpoints["s1"]["complete"])


if __name__ == "__main__":
    unittest.main()
