"""Durable, budget-bounded usage aggregation for OpenCode sessions.

The detail window in ``read_opencode`` keeps only the newest parts of a
session, so nothing that feeds a complete usage total may depend on it. This
module pages a session's parts in ascending ``(time_created, id)`` order,
accumulates token usage into counters, and commits the counters together with
the cursor. A later cycle -- or a restarted process -- resumes exactly where
the committed checkpoint ends, so a read budget can only end one batch, never
the aggregation itself.

Only counters are kept in memory; part payloads are parsed and dropped, so a
session with millions of parts cannot grow the process without bound.
"""

from __future__ import annotations

import time

from .core import MAX_OC_PART_PAGE, add_usage, now_ms, obj, oc_usage, zero_usage

CHECKPOINT_VERSION = 1

# Wall-clock slice a single poll cycle may spend on historical aggregation.
# Deliberately smaller than OPENCODE_READ_SECONDS so one cycle can both refresh
# details and keep making progress on the backlog without missing its cadence.
AGGREGATE_BUDGET_SECONDS = 5.0


def empty_checkpoint():
    """A fresh, never-started checkpoint for one session."""
    return {
        "v": CHECKPOINT_VERSION,
        "usage": zero_usage(),
        "cursor": None,
        "parts": 0,
        "complete": False,
        "updated": 0,
    }


def _key(row):
    return [int(row["time_created"] or 0), str(row["id"])]


def _max_key(con, native_id):
    row = con.execute(
        "SELECT time_created, id FROM part WHERE session_id=? "
        "ORDER BY time_created DESC, id DESC LIMIT 1",
        (native_id,),
    ).fetchone()
    return _key(row) if row is not None else None


def _part_revision(con, native_id):
    """Row-count-independent identity of a session's part rows.

    Counting rows alone cannot see an in-place edit that keeps the row count
    and byte totals (a corrected payload of the same length), so the newest
    rows are also probed by content. The probe is bounded and honest about
    what it covers: the last few rows are compared head-to-tail, and edits
    buried inside older rows stay outside the contract.
    """
    row = con.execute(
        "SELECT COUNT(*), COALESCE(MAX(rowid),0), "
        "COALESCE(SUM(LENGTH(CAST(data AS BLOB))),0), COALESCE(MAX(time_created),0) "
        "FROM part WHERE session_id=?",
        (native_id,),
    ).fetchone()
    tail = con.execute(
        "SELECT id, time_created, LENGTH(CAST(data AS BLOB)), "
        "SUBSTR(data, 1, 80), SUBSTR(data, -80) FROM part WHERE session_id=? "
        "ORDER BY time_created DESC, id DESC LIMIT 4",
        (native_id,),
    ).fetchall()
    probe = [
        [str(item[0]), int(item[1] or 0), int(item[2] or 0), str(item[3]), str(item[4])]
        for item in tail
    ]
    return (
        int(row[0] or 0),
        [int(row[1] or 0), int(row[2] or 0), int(row[3] or 0)],
        probe,
    )


def aggregate_session(con, native_id, checkpoint, deadline, commit, page=MAX_OC_PART_PAGE):
    """Aggregate one session's token usage across ALL of its parts.

    ``checkpoint`` is the durable state from a previous batch (or
    :func:`empty_checkpoint`). ``commit(state)`` is called after every page with
    a state that already includes that page, so a crash can never persist a
    cursor ahead of the usage it accounts for. Returns the final state.

    Semantics:
    * parts are consumed once, strictly in key order, so a re-read cannot
      double count and an appended part is picked up exactly once;
    * a source rewritten shorter than the committed cursor is re-verified from
      the start instead of trusting a sum that describes missing evidence;
    * a short or empty page means the end of the session's part history.
    """
    state = dict(checkpoint)
    state["v"] = CHECKPOINT_VERSION
    state["usage"] = dict(checkpoint.get("usage") or zero_usage())
    state["cursor"] = list(checkpoint["cursor"]) if checkpoint.get("cursor") else None
    state["parts"] = int(checkpoint.get("parts") or 0)
    state["complete"] = bool(checkpoint.get("complete"))

    top = _max_key(con, native_id)
    if top is None:
        state["complete"] = True
        state["cursor"] = None
        state["updated"] = now_ms()
        commit(state)
        return state
    cursor = state["cursor"]
    recorded = int(state["parts"] or 0)
    present = int(
        con.execute("SELECT COUNT(*) FROM part WHERE session_id=?", (native_id,)).fetchone()[0]
    )
    if recorded and present < recorded:
        # A rewritten (regenerated) source can keep a larger key while losing
        # parts, so key comparisons alone miss it; fewer parts than were already
        # accounted for means the stored sum describes evidence that no longer
        # exists, so re-verify from the start instead of trusting it.
        state["usage"] = zero_usage()
        state["parts"] = 0
        cursor = None
    elif cursor is not None and cursor > top:
        # The source was rewritten shorter than the committed cursor, so the
        # stored sum describes evidence that no longer exists: re-verify from
        # the start instead of trusting it.
        state["usage"] = zero_usage()
        state["parts"] = 0
        cursor = None
    elif cursor is not None and cursor == top:
        if not state["complete"]:
            state["complete"] = True
            state["updated"] = now_ms()
            commit(state)
        return state
    # Either the session was never finished, or new parts were appended after
    # it completed; both continue from the committed cursor.
    state["complete"] = False

    while time.monotonic() <= deadline:
        if cursor is None:
            rows = con.execute(
                "SELECT id, time_created, data FROM part WHERE session_id=? "
                "ORDER BY time_created ASC, id ASC LIMIT ?",
                (native_id, page),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT id, time_created, data FROM part WHERE session_id=? "
                "AND (time_created > ? OR (time_created = ? AND id > ?)) "
                "ORDER BY time_created ASC, id ASC LIMIT ?",
                (native_id, cursor[0], cursor[0], cursor[1], page),
            ).fetchall()
        if not rows:
            state["complete"] = True
            state["cursor"] = cursor
            state["updated"] = now_ms()
            commit(state)
            return state
        for raw in rows:
            row = dict(raw)
            payload = obj(row.get("data"))
            state["parts"] += 1
            if payload.get("type") == "step-finish" and payload.get("tokens"):
                add_usage(state["usage"], oc_usage(payload["tokens"]))
            cursor = [int(row.get("time_created") or 0), str(row.get("id") or "")]
        state["cursor"] = list(cursor)
        state["updated"] = now_ms()
        commit(state)
        if len(rows) < page:
            state["complete"] = True
            state["updated"] = now_ms()
            commit(state)
            return state
    return state


def aggregate_source(con, sessions, checkpoints, deadline, commit, state=None):
    """Continue unfinished sessions of one source until the budget runs out.

    ``sessions`` is a list of ``(native_id, ordering_key)`` pairs, newest
    first. Work resumes from ``state["next_index"]`` so a single huge session
    cannot starve the others across cycles; completed sessions are skipped
    cheaply. Returns a summary dict.
    """
    if state is None:
        state = {"next_index": 0}
    total = len(sessions)
    started = time.monotonic()
    if total == 0:
        state["next_index"] = 0
        return {"total": 0, "complete": 0, "pending": 0, "visited": 0, "seconds": 0.0}
    start = int(state.get("next_index") or 0) % total
    visited = 0
    index = start
    for _ in range(total):
        if time.monotonic() > deadline:
            break
        native_id = sessions[index][0]
        index = (index + 1) % total
        visited += 1
        current = checkpoints.get(native_id) or empty_checkpoint()
        if current.get("complete"):
            # Completed sessions are re-verified cheaply, but a row count alone
            # cannot see an in-place edit that keeps the number of rows and the
            # byte totals: the stored revision and content probe must match too.
            # A mismatch re-aggregates from the start instead of trusting a sum
            # over changed evidence.
            present, revision, probe = _part_revision(con, native_id)
            if present == int(current.get("parts") or 0):
                if current.get("revision") == revision and current.get("probe") == probe:
                    continue
                current = empty_checkpoint()
        final = aggregate_session(
            con,
            native_id,
            current,
            deadline,
            lambda st, _sid=native_id: commit(_sid, st),
        )
        if final.get("complete"):
            # Keep the revision and the bounded content probe of the evidence
            # the sum was computed over, so the next visit can skip only when
            # the stored rows still match.
            _, revision, probe = _part_revision(con, native_id)
            final["revision"] = revision
            final["probe"] = probe
            commit(native_id, final)
        checkpoints[native_id] = final
    state["next_index"] = index
    return {
        "total": total,
        "complete": sum(
            1 for sid, _ in sessions if (checkpoints.get(sid) or {}).get("complete")
        ),
        "pending": sum(
            1 for sid, _ in sessions if not (checkpoints.get(sid) or {}).get("complete")
        ),
        "visited": visited,
        "seconds": round(time.monotonic() - started, 3),
    }
