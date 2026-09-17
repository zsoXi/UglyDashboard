"""Read-only collectors for OpenCode SQLite, OpenCode live API, Codex logs and git."""

import base64
import json
import os
import re
import sqlite3
import subprocess
import time
from collections import deque
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .core import (
    HOME,
    MAX_LINE,
    MAX_OC_MESSAGES_PER_SESSION,
    MAX_OC_PART_PAGE,
    MAX_OC_PARTS_PER_SESSION,
    MAX_OC_PARTS_TOTAL,
    MAX_RESPONSE,
    OPENCODE_READ_SECONDS,
    Diagnostics,
    add_event,
    bounded_append,
    codex_usage,
    columns,
    digest,
    existing_unique,
    make_session,
    number,
    obj,
    oc_usage,
    path_key,
    path_name,
    readonly_db,
    record_usage,
    redact,
    stamp,
    tool_detail,
    zero_usage,
)


def read_opencode(path, limit=1000, budget_seconds=None):
    result, dirs = [], []
    diag = Diagnostics()
    soft_budget = OPENCODE_READ_SECONDS if budget_seconds is None else float(budget_seconds)
    deadline = time.monotonic() + soft_budget
    deadline_exceeded = False
    with readonly_db(path) as con:
        sc = columns(con, "session")
        if not {"id"}.issubset(sc):
            raise ValueError("Unsupported OpenCode schema: missing session.id")
        pc, mc, pt = columns(con, "project"), columns(con, "message"), columns(con, "part")
        projects = {}
        if {"id", "worktree"}.issubset(pc):
            projects = {r["id"]: dict(r) for r in con.execute("SELECT * FROM project")}
            dirs = [r["worktree"] for r in projects.values() if r.get("worktree")]
        total = con.execute("SELECT COUNT(*) FROM session").fetchone()[0]
        order = "time_updated" if "time_updated" in sc else "id"
        rows = con.execute(
            f"SELECT * FROM session ORDER BY {order} DESC LIMIT ?", (limit,)
        ).fetchall()
        sessions = {}
        for r in rows:
            r = dict(r)
            metadata = obj(r.get("data"))
            r = {**metadata, **r}
            project = projects.get(r.get("project_id"), {})
            directory = r.get("directory") or project.get("worktree") or ""
            s = make_session("opencode", str(r["id"]), r.get("title"), directory)
            t = obj(r.get("time"))
            s.update(
                created=int(number(r.get("time_created", t.get("created")))),
                updated=int(number(r.get("time_updated", t.get("updated")))),
                agent=r.get("agent") or "unknown",
                model=r.get("model") or "unknown",
                _db=str(path),
            )
            if isinstance(s["model"], (dict, str)) and obj(s["model"]):
                sm = obj(s["model"])
                s["model"] = sm.get("modelID", sm.get("id", "unknown"))
                s["provider"] = sm.get("providerID", "unknown")
            s["parent_id"] = (
                "opencode:" + str(r.get("parent_id") or r.get("parentID"))
                if r.get("parent_id") or r.get("parentID")
                else ""
            )
            s["relationship"] = "parent_unknown" if s["parent_id"] else "root"
            s["_rollup"] = r
            sessions[s["native_id"]] = s
        parts_total = 0
        truncated = False
        can_message = {"id", "session_id", "data"}.issubset(mc)
        mo = "time_created" if "time_created" in mc else "id"
        can_part = {"session_id", "data"}.issubset(pt)
        po = "time_created" if "time_created" in pt else "id"
        has_part_id = "id" in pt
        read_state = {"hit": False}

        def fetch(query, args):
            # The read-only connection installs a hard 12s progress guard; a very
            # large database can still trip it mid-query. Convert that interrupt
            # into bounded partial coverage instead of publishing nothing.
            try:
                return con.execute(query, args).fetchall()
            except sqlite3.OperationalError as e:
                if "interrupt" in str(e).lower():
                    read_state["hit"] = True
                    return []
                raise

        processed = 0
        for s in list(sessions.values()):
            # A non-positive budget must deterministically stop after the newest
            # session: comparing monotonic() > deadline is unreliable on coarse
            # clocks (Windows uses ~15 ms ticks), so an explicit guard is used.
            if processed and (
                soft_budget <= 0 or read_state["hit"] or time.monotonic() > deadline
            ):
                deadline_exceeded = True
                break
            message_info = {}
            if can_message:
                # Only the newest window is read; older messages are dropped and
                # reported via messages_truncated instead of growing without bound.
                rows_m = fetch(
                    f"SELECT * FROM message WHERE session_id=? ORDER BY {mo} DESC LIMIT ?",
                    (s["native_id"], MAX_OC_MESSAGES_PER_SESSION + 1),
                )
                if len(rows_m) > MAX_OC_MESSAGES_PER_SESSION:
                    truncated = True
                    s["messages_truncated"] = True
                    rows_m = rows_m[:MAX_OC_MESSAGES_PER_SESSION]
                for r in reversed(rows_m):
                    r = dict(r)
                    d = obj(r["data"])
                    ts = int(number(r.get("time_created", obj(d.get("time")).get("created"))))
                    s["messages"] += 1
                    message_info[r["id"]] = d
                    if d.get("role") == "assistant":
                        s["agent"] = d.get("agent") or s["agent"]
                        s["model"] = (
                            d.get("modelID") or obj(d.get("model")).get("modelID") or s["model"]
                        )
                        s["provider"] = d.get("providerID") or s["provider"]
                        complete = int(number(obj(d.get("time")).get("completed")))
                        s["_completed"] = max(s["_completed"], complete)
                        if d.get("error"):
                            s["_error_at"] = max(s["_error_at"], complete or ts)
                            s["errors"] += 1
                            add_event(
                                s,
                                "error",
                                json.dumps(d["error"], ensure_ascii=False),
                                complete or ts,
                                r["id"],
                            )
                        if d.get("tokens"):
                            s.setdefault("_message_usage", []).append(
                                (
                                    d["tokens"],
                                    ts,
                                    d.get("modelID"),
                                    d.get("providerID"),
                                    d.get("cost"),
                                )
                            )
                    elif d.get("role") == "user":
                        s["turn_started"] = max(s["turn_started"], ts)
            if can_part and parts_total < MAX_OC_PARTS_TOTAL:
                # Newest-first keyset paging keeps memory bounded per session; the
                # window is capped and truncation is reported to the caller.
                budget = min(MAX_OC_PARTS_PER_SESSION, MAX_OC_PARTS_TOTAL - parts_total)
                rows_p = []
                if has_part_id:
                    cursor = None
                    while len(rows_p) <= budget:
                        page = min(MAX_OC_PART_PAGE, budget + 1 - len(rows_p))
                        if cursor is None:
                            q = f"SELECT * FROM part WHERE session_id=? ORDER BY {po} DESC, id DESC LIMIT ?"
                            args = (s["native_id"], page)
                        else:
                            q = f"SELECT * FROM part WHERE session_id=? AND ({po} < ? OR ({po} = ? AND id < ?)) ORDER BY {po} DESC, id DESC LIMIT ?"
                            args = (s["native_id"], cursor[0], cursor[0], cursor[1], page)
                        fetched = fetch(q, args)
                        rows_p.extend(fetched)
                        if len(fetched) < page:
                            break
                        last = fetched[-1]
                        cursor = (last[po], last["id"])
                else:
                    rows_p = fetch(
                        f"SELECT * FROM part WHERE session_id=? ORDER BY {po} DESC LIMIT ?",
                        (s["native_id"], budget + 1),
                    )
                older_cursor = None
                if len(rows_p) > budget:
                    truncated = True
                    s["parts_truncated"] = True
                    rows_p = rows_p[:budget]
                    if rows_p:
                        older_cursor = (
                            (rows_p[-1][po], rows_p[-1]["id"]) if has_part_id else len(rows_p)
                        )
                parts_total += len(rows_p)
                for r in reversed(rows_p):
                    r = dict(r)
                    d = obj(r["data"])
                    ts = int(number(r.get("time_created", obj(d.get("time")).get("start"))))
                    mid = message_info.get(r.get("message_id"), {})
                    typ = d.get("type")
                    pid = r.get("id", digest(r["data"]))
                    if typ == "step-finish" and d.get("tokens"):
                        record_usage(
                            s,
                            oc_usage(d["tokens"], diag),
                            ts,
                            mid.get("modelID"),
                            mid.get("providerID"),
                            d.get("cost"),
                        )
                    elif typ == "text" and mid.get("role") == "user" and d.get("text"):
                        s["prompt"] = redact(d["text"], 5000)
                        add_event(s, "prompt", d["text"], ts, pid)
                    elif typ == "tool":
                        state = obj(d.get("state"))
                        inp = obj(state.get("input"))
                        name = d.get("tool", "tool")
                        tool = tool_detail(
                            name,
                            d.get("callID", pid),
                            state.get("status", "unknown"),
                            ts,
                            inp,
                            state.get("output", state.get("error", "")),
                        )
                        bounded_append(s["tools"], tool, 80)
                        if name not in ("read",):
                            s["files"] += tool["files"]
                        if tool["state"] == "error":
                            s["errors"] += 1
                        add_event(
                            s,
                            "tool",
                            f"{name}: {tool['state']}"
                            + (" · " + tool["command"][:160] if tool["command"] else ""),
                            ts,
                            str(pid) + ":" + tool["state"],
                        )
                        # Delegation is evidenced by the task tool, not just parentID.
                        child = obj(state.get("metadata")).get("sessionId") or obj(
                            state.get("metadata")
                        ).get("sessionID")
                        if name == "task" and child in sessions:
                            sessions[child]["relationship"] = "delegated"
                            sessions[child]["parent_id"] = s["id"]
                        if name == "task" and child:
                            s.setdefault("_child_links", []).append(str(child))
                    elif typ == "retry":
                        s["retry_count"] += 1
                        add_event(s, "retry", str(d.get("error", "Retry")), ts, pid)
                if older_cursor is not None:
                    # Usage aggregates must not depend on the detail window: page
                    # through the older parts with a usage-only read (no detail is
                    # retained) so the session totals include every step-finish, not
                    # only the newest MAX_OC_PARTS_PER_SESSION of them. Memory stays
                    # bounded by the page size; the soft deadline bounds the work and
                    # any remainder is reported as aggregate_truncated.
                    cursor = older_cursor
                    while True:
                        if read_state["hit"] or time.monotonic() > deadline:
                            s["_aggregate_truncated"] = True
                            if read_state["hit"]:
                                deadline_exceeded = True
                            break
                        if has_part_id:
                            q = (
                                f"SELECT * FROM part WHERE session_id=? AND "
                                f"({po} < ? OR ({po} = ? AND id < ?)) "
                                f"ORDER BY {po} DESC, id DESC LIMIT ?"
                            )
                            args = (
                                s["native_id"],
                                cursor[0],
                                cursor[0],
                                cursor[1],
                                MAX_OC_PART_PAGE,
                            )
                        else:
                            q = (
                                f"SELECT * FROM part WHERE session_id=? "
                                f"ORDER BY {po} DESC LIMIT ? OFFSET ?"
                            )
                            args = (s["native_id"], MAX_OC_PART_PAGE, cursor)
                        page_rows = fetch(q, args)
                        if not page_rows:
                            break
                        for raw in page_rows:
                            r = dict(raw)
                            d = obj(r.get("data"))
                            if d.get("type") == "step-finish" and d.get("tokens"):
                                ts = int(
                                    number(
                                        r.get("time_created")
                                        or obj(d.get("time")).get("start")
                                    )
                                )
                                mid = message_info.get(r.get("message_id"), {})
                                record_usage(
                                    s,
                                    oc_usage(d["tokens"], diag),
                                    ts,
                                    mid.get("modelID"),
                                    mid.get("providerID"),
                                    d.get("cost"),
                                )
                        if len(page_rows) < MAX_OC_PART_PAGE:
                            break
                        if has_part_id:
                            last = page_rows[-1]
                            cursor = (last[po], last["id"])
                        else:
                            cursor += len(page_rows)
            if read_state["hit"]:
                deadline_exceeded = True
                break
            processed += 1
        if deadline_exceeded:
            # Keep only the newest fully-read sessions. Anything after the break
            # was never detailed and would otherwise publish as empty ghosts.
            sessions = {s["native_id"]: s for s in list(sessions.values())[:processed]}
        for s in sessions.values():
            if not s["usage_known"]:
                for t, ts, model, prov, cost in s.get("_message_usage", []):
                    record_usage(s, oc_usage(t, diag), ts, model, prov, cost)
            if not s["usage_known"]:
                r = s["_rollup"]
                if any(k in r for k in ("tokens_input", "tokens_output")):
                    u = {
                        k: number(r.get("tokens_" + k), diagnostics=diag, field="tokens_" + k)
                        for k in zero_usage()
                        if k != "total"
                    }
                    u["total"] = sum(u.values())
                    record_usage(s, u, s["updated"], cost=r.get("cost"))
                    s["warnings"].append(
                        "Legacy session rollup; model/time attribution is session-level only."
                    )
            if (
                s["_error_at"]
                and s["_error_at"] >= s["turn_started"]
                and s["_error_at"] >= s["_completed"]
            ):
                s["state"], s["state_evidence"], s["confidence"] = (
                    "error",
                    "recorded assistant error",
                    "recorded",
                )
            elif s["_completed"] and s["_completed"] >= s["turn_started"]:
                s["state"], s["state_evidence"], s["confidence"] = (
                    "idle",
                    "last assistant response completed; task outcome unknown",
                    "recorded",
                )
            s["files"] = sorted(set(s["files"]))[:200]
            s["events"] = s["events"][-120:]
            if s.get("parts_truncated"):
                s["warnings"].append(
                    "Part detail history capped at %d newest parts; usage totals still "
                    "include the older parts." % MAX_OC_PARTS_PER_SESSION
                )
            if s.get("_aggregate_truncated"):
                s["warnings"].append(
                    "Usage aggregate stopped at the read budget; older usage is still pending."
                )
            if s.get("messages_truncated"):
                s["warnings"].append(
                    "Message history capped at %d newest messages." % MAX_OC_MESSAGES_PER_SESSION
                )
            add_event(s, "session", "Session recorded: " + s["title"], s["created"], "created")
            result.append(s)
    truncated_sessions = sum(
        1 for s in result if s.get("parts_truncated") or s.get("messages_truncated")
    )
    aggregate_truncated = sum(1 for s in result if s.get("_aggregate_truncated"))
    coverage = {
        "total_sessions": total,
        "loaded_sessions": len(result),
        "parts_loaded": parts_total,
        "truncated_sessions": truncated_sessions,
        "aggregate_truncated_sessions": aggregate_truncated,
        "deadline_exceeded": deadline_exceeded,
        "truncated": bool(
            total > limit
            or truncated
            or parts_total >= MAX_OC_PARTS_TOTAL
            or deadline_exceeded
            or aggregate_truncated
        ),
        "rejected_records": diag.snapshot(),
    }
    return result, dirs, coverage


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Redirects disabled for local API requests.")


LOCAL_HTTP = build_opener(ProxyHandler({}), NoRedirect())


def local_json(url, timeout=2, body=None, headers=None):
    u = urlparse(url)
    if u.scheme != "http" or u.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Only explicit local HTTP endpoints are allowed.")
    h = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        h["Content-Type"] = "application/json"
    req = Request(url, data=json.dumps(body).encode() if body is not None else None, headers=h)
    with LOCAL_HTTP.open(req, timeout=timeout) as res:
        # Socket timeout plus byte limit. Avoid reading unlimited responses.
        raw = res.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("API response exceeds 16 MiB.")
        return json.loads(raw)


def oc_headers():
    password = os.environ.get("OPENCODE_SERVER_PASSWORD")
    if not password:
        return {}
    value = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode") + ":" + password
    return {"Authorization": "Basic " + base64.b64encode(value.encode()).decode()}


def probe_opencode(base):
    health = local_json(base.rstrip("/") + "/global/health", headers=oc_headers())
    if not isinstance(health, dict) or not health.get("healthy"):
        raise ValueError("Endpoint is not a healthy OpenCode server.")
    return health


def read_oc_live(base, directories, include_sessions=True):
    base = base.rstrip("/")
    health = probe_opencode(base)
    statuses, api_sessions, definitions, issues = {}, [], [], []
    try:
        projs = local_json(base + "/project", headers=oc_headers())
        discovered = (
            [p.get("worktree") for p in projs if isinstance(p, dict) and p.get("worktree")]
            if isinstance(projs, list)
            else []
        )
    except Exception:
        discovered = []
    dirs = list(dict.fromkeys([""] + directories + discovered))[:50]
    for directory in dirs:
        q = "?" + urlencode({"directory": directory}) if directory else ""
        try:
            status = local_json(base + "/session/status" + q, headers=oc_headers())
            if isinstance(status, dict):
                for sid, val in status.items():
                    if isinstance(val, dict) and val.get("type") in ("busy", "idle", "retry"):
                        old = statuses.get(sid)
                        if not old or val.get("type") in ("busy", "retry"):
                            statuses[sid] = {**val, "_directory": directory}
            if include_sessions:
                qs = urlencode({"directory": directory, "limit": 200})
                rows = local_json(base + "/session?" + qs, headers=oc_headers())
                if isinstance(rows, list):
                    api_sessions.extend(r for r in rows if isinstance(r, dict))
        except Exception as e:
            issues.append(f"{directory or 'default'}: {redact(e, 180)}")
    try:
        a = local_json(base + "/agent", headers=oc_headers())
        if isinstance(a, list):
            definitions = [
                dict(
                    name=x.get("name", "unknown"),
                    mode=x.get("mode", "unknown"),
                    model=x.get("model", ""),
                    description=redact(x.get("description"), 500),
                    source="OpenCode API",
                    directory="",
                    prompt="",
                )
                for x in a
                if isinstance(x, dict)
            ]
    except Exception:
        pass
    return (
        statuses,
        api_sessions,
        definitions,
        {
            "health": health,
            "issues": issues,
            "directories_checked": len(dirs),
            "truncated": len(directories + discovered) > 49,
        },
    )


def enrich_oc_session(s):
    base = s.get("_server", "").rstrip("/")
    if not base:
        return
    query = urlencode({"directory": s["directory"], "limit": 12})
    rows = local_json(
        base + "/session/" + quote(s["native_id"], safe="") + "/message?" + query,
        headers=oc_headers(),
        timeout=2,
    )
    if not isinstance(rows, list):
        return
    current_tools = {t["id"]: t for t in s["tools"]}
    for row in rows:
        if not isinstance(row, dict):
            continue
        info = obj(row.get("info"))
        ts = int(number(obj(info.get("time")).get("created")))
        if info.get("role") == "assistant":
            s["agent"] = info.get("agent") or s["agent"]
            s["model"] = info.get("modelID") or s["model"]
            s["provider"] = info.get("providerID") or s["provider"]
        for part in row.get("parts", []):
            if not isinstance(part, dict):
                continue
            typ = part.get("type")
            if typ == "text" and info.get("role") == "user":
                s["prompt"] = redact(part.get("text"), 5000)
                s["turn_started"] = max(s["turn_started"], ts)
            elif typ == "tool":
                state = obj(part.get("state"))
                name = part.get("tool", "tool")
                pid = part.get("callID") or part.get("id", str(ts))
                t = tool_detail(
                    name,
                    pid,
                    state.get("status", "unknown"),
                    ts,
                    state.get("input"),
                    state.get("output", state.get("error", "")),
                )
                current_tools[t["id"]] = t
                if name != "read":
                    s["files"] += t["files"]
                if state.get("status") == "running" and s["state"] == "running":
                    s["state"] = "tool"
                if name == "task":
                    child = obj(state.get("metadata")).get("sessionId") or obj(
                        state.get("metadata")
                    ).get("sessionID")
                    if child:
                        s.setdefault("_child_links", []).append(str(child))
            elif (
                typ == "reasoning"
                and s["state"] == "running"
                and not obj(info.get("time")).get("completed")
            ):
                s["state"] = "thinking"  # only the part TYPE; never expose reasoning text
    s["tools"] = sorted(current_tools.values(), key=lambda t: t["ts"])[-80:]
    s["files"] = sorted(set(s["files"]))[:200]
    if not s.get("_db"):
        s["warnings"].append(
            "API-only metadata/details; usage is unknown until the source DB is selected."
        )


def reject_json_constant(value):
    raise ValueError("Non-finite JSON value: " + value)


class JsonlReader:
    """Incremental complete-line reader. Handles append, rotation, truncation,
    same-size rewrites, split UTF-8, and long lines without unbounded allocation.
    Complete records are delivered once per file version; partial tails wait.
    """

    def __init__(self):
        self.offset = 0
        self.identity = None
        self.mtime = None
        self.discarding = False
        self.pending = b""
        self.skipped = 0
        self.reset = False
        self.anchor = b""

    def read(self, path, budget=16 * 1024 * 1024):
        st = Path(path).stat()
        identity = (st.st_dev, st.st_ino)
        self.reset = (
            self.identity != identity
            or st.st_size < self.offset
            or (
                self.mtime is not None
                and st.st_mtime_ns != self.mtime
                and st.st_size == self.offset
                and not self.pending
            )
        )
        if not self.reset and self.offset and self.anchor:
            with open(path, "rb") as check:
                check.seek(max(0, self.offset - len(self.anchor)))
                if check.read(len(self.anchor)) != self.anchor:
                    self.reset = True  # truncate/rewrite can grow beyond old offset
        if self.reset:
            self.offset = 0
            self.pending = b""
            self.discarding = False
            self.skipped = 0
        self.identity, self.mtime = identity, st.st_mtime_ns
        records = []
        with open(path, "rb") as f:
            f.seek(self.offset)
            consumed = 0
            while consumed < budget:
                chunk = f.read(min(65536, budget - consumed))
                if not chunk:
                    break
                consumed += len(chunk)
                self.offset += len(chunk)
                pieces = chunk.split(b"\n")
                for i, piece in enumerate(pieces):
                    end = i < len(pieces) - 1
                    if self.discarding:
                        if end:
                            self.discarding = False
                        continue
                    self.pending += piece
                    if len(self.pending) > MAX_LINE:
                        self.pending = b""
                        self.skipped += 1
                        self.discarding = not end
                    elif end:
                        raw = self.pending
                        self.pending = b""
                        try:
                            value = json.loads(raw, parse_constant=reject_json_constant)
                            if isinstance(value, dict):
                                records.append(value)
                        except (UnicodeDecodeError, ValueError):
                            if raw.strip():
                                self.skipped += 1
        with open(path, "rb") as check:
            check.seek(max(0, self.offset - 128))
            self.anchor = check.read(min(128, self.offset))
        return records


def codex_apply(s, records, diagnostics=None):
    calls = s.setdefault("_calls", {})
    cumulative = s.setdefault("_cumulative", zero_usage())
    for r in records:
        ts = stamp(r.get("timestamp"))
        p = obj(r.get("payload"))
        typ = r.get("type")
        s["updated"] = max(s["updated"], ts)
        if typ == "session_meta":
            if p.get("id"):
                s["native_id"] = str(p["id"])
                s["id"] = "codex:" + s["native_id"]
            s["created"] = stamp(p.get("timestamp")) or ts or s["created"]
            s["directory"] = p.get("cwd", s["directory"])
            s["project"] = path_name(s["directory"])
            s["origin"] = redact(p.get("originator") or "Codex", 100)
            s["origin_evidence"] = "Codex session_meta.originator"
            s["provider"] = p.get("model_provider") or s["provider"]
            s["agent"] = p.get("agent_nickname") or p.get("agent_role") or "Codex"
            sub = obj(obj(p.get("source")).get("subagent"))
            spawn = obj(sub.get("thread_spawn"))
            parent = spawn.get("parent_thread_id") or sub.get("parent_thread_id")
            if parent:
                s["parent_id"] = "codex:" + str(parent)
                s["relationship"] = "delegated"
            elif p.get("forked_from_id"):
                s["parent_id"] = "codex:" + str(p["forked_from_id"])
                s["relationship"] = "fork"
            add_event(s, "session", "Codex session recorded", ts, "created")
        elif typ == "turn_context":
            s["model"] = p.get("model") or s["model"]
            s["directory"] = p.get("cwd") or s["directory"]
            s["project"] = path_name(s["directory"])
            s["effort"] = p.get("effort", p.get("reasoning_effort", ""))
        elif typ == "event_msg":
            et = p.get("type")
            if et in ("task_started", "turn_started"):
                s["state"] = "running"
                s["turn_started"] = ts
                s["confidence"] = "recorded"
                s["state_evidence"] = (
                    "turn-start marker in local log; process liveness not verified"
                )
                add_event(s, "started", "Turn started", ts, str(p.get("turn_id", ts)))
            elif et in ("task_complete", "task_completed", "turn_complete", "turn_completed"):
                s["state"] = "done"
                s["_completed"] = ts
                s["confidence"] = "recorded"
                s["state_evidence"] = (
                    "explicit turn-complete marker; not a verified project outcome"
                )
                add_event(s, "completed", "Turn completed", ts, str(p.get("turn_id", ts)))
            elif et in ("turn_aborted", "task_aborted"):
                s["state"] = "cancelled"
                s["confidence"] = "recorded"
                s["state_evidence"] = "explicit abort marker"
                add_event(s, "cancelled", "Turn aborted", ts)
            elif et in ("error", "stream_error"):
                s["errors"] += 1
                add_event(s, "error", str(p.get("message", p)), ts)
                if et == "error":
                    s["state"] = "error"
                    s["confidence"] = "recorded"
                    s["state_evidence"] = "explicit error event"
            elif et == "token_count":
                info = obj(p.get("info"))
                total = obj(info.get("total_token_usage"))
                if total:
                    if ts and ts < s.get("_usage_timestamp", 0):
                        if "Out-of-order usage event skipped." not in s["warnings"]:
                            s["warnings"].append("Out-of-order usage event skipped.")
                        continue
                    s["_usage_timestamp"] = ts
                    u = codex_usage(total, diagnostics)
                    # Cumulative counters may reset after a new context. Never add
                    # repeated total_token_usage records a second time.
                    if u["total"] < cumulative.get("total", 0):
                        delta = u
                        if (
                            "Cumulative token counter reset; a new sequence was started."
                            not in s["warnings"]
                        ):
                            s["warnings"].append(
                                "Cumulative token counter reset; a new sequence was started."
                            )
                    else:
                        delta = {k: max(0, u[k] - cumulative.get(k, 0)) for k in u}
                    if delta["total"] > 0:
                        record_usage(s, delta, ts)
                    s["_cumulative"] = cumulative = u
                    last = codex_usage(info.get("last_token_usage"), diagnostics)
                    s["context_tokens"] = (
                        last["input"] + last["cache_read"]
                        if info.get("last_token_usage")
                        else s["context_tokens"]
                    )
                    s["context_limit"] = info.get("model_context_window") or s["context_limit"]
                if p.get("rate_limits"):
                    s["rate_limits"] = p["rate_limits"]
            elif et == "user_message" and p.get("message"):
                s["prompt"] = redact(p["message"], 5000)
                if s["title"] == s["native_id"] or s["title"].startswith("rollout-"):
                    s["title"] = redact(p["message"], 160)
            elif et in (
                "request_user_input",
                "exec_approval_request",
                "apply_patch_approval_request",
            ):
                s["state"] = "waiting"
                s["confidence"] = "recorded"
                s["state_evidence"] = "recorded approval request"
                add_event(s, "waiting", "Approval/input requested", ts)
        elif typ == "response_item":
            it = p.get("type")
            if it == "message":
                s["messages"] += 1
                text = "\n".join(
                    str(c.get("text", "")) for c in p.get("content", []) if isinstance(c, dict)
                )
                if p.get("role") == "user" and text:
                    s["prompt"] = redact(text, 5000)
                    if s["title"] == s["native_id"] or s["title"].startswith("rollout-"):
                        s["title"] = redact(text, 160)
                    add_event(s, "prompt", text, ts, p.get("id", ""))
            elif it in ("function_call", "custom_tool_call"):
                name = p.get("name", "tool")
                cid = p.get("call_id", str(ts))
                inp = obj(p.get("arguments")) or {"input": p.get("input", "")}
                tool = tool_detail(name, cid, "running", ts, inp)
                calls[cid] = tool
                bounded_append(s["tools"], tool, 80)
                s["files"] += tool["files"]
                s["state"] = "tool"
                s["confidence"] = "recorded"
                s["state_evidence"] = "recorded tool call; process liveness not verified"
                add_event(
                    s,
                    "tool",
                    name + (" · " + tool["command"][:160] if tool["command"] else ""),
                    ts,
                    cid,
                )
            elif it in ("function_call_output", "custom_tool_call_output"):
                cid = p.get("call_id")
                output = p.get("output", "")
                if isinstance(output, dict):
                    exitcode = output.get("exit_code")
                    text = json.dumps(output, ensure_ascii=False)
                else:
                    text = str(output)
                    match = re.search(r"(?:Process exited with code|Exit code:)\s*(-?\d+)", text)
                    exitcode = int(match.group(1)) if match else None
                if cid in calls:
                    tool = calls[cid]
                    tool.update(
                        output=redact(text, 2500),
                        exit_code=exitcode,
                        state="error" if exitcode not in (None, 0) else "completed",
                    )
                    if tool["state"] == "error":
                        s["errors"] += 1
                    add_event(
                        s,
                        "tool_result",
                        tool["name"] + ": " + tool["state"],
                        ts,
                        str(cid) + ":result",
                    )
                    s["state"] = "running"
                    s["state_evidence"] = "tool returned; waiting for a terminal marker"
    s["files"] = sorted(set(s["files"]))[:200]
    s["events"] = s["events"][-150:]
    # Keep only a bounded amount of usage detail. The full accumulated totals
    # remain intact; a warning makes the shorter time-series coverage explicit.
    if len(s["usage_events"]) > 20000:
        s["usage_events"] = s["usage_events"][-20000:]
        if "Usage timeline capped at 20,000 records." not in s["warnings"]:
            s["warnings"].append("Usage timeline capped at 20,000 records.")
    if len(calls) > 200:
        keep = {t["id"] for t in s["tools"]}
        s["_calls"] = {k: v for k, v in calls.items() if k in keep}
    return s


def discover_codex_files(homes, limit):
    candidates = []
    visited = 0
    deadline = time.monotonic() + 6
    truncated = False
    for home in homes:
        for root in (Path(home) / "sessions", Path(home) / "archived_sessions"):
            if not root.is_dir():
                continue
            for directory, dirs, files in os.walk(root, followlinks=False):
                dirs[:] = [d for d in dirs if not Path(directory, d).is_symlink()]
                for name in files:
                    visited += 1
                    if name.endswith(".jsonl"):
                        p = Path(directory, name)
                        try:
                            if not p.is_symlink():
                                candidates.append((p.stat().st_mtime_ns, str(p)))
                        except OSError:
                            pass
                if visited > 30000 or time.monotonic() > deadline:
                    truncated = True
                    dirs[:] = []
                    break
    candidates.sort(reverse=True)
    return [p for _, p in candidates[:limit]], {
        "files_found": len(candidates),
        "loaded_files": min(len(candidates), limit),
        "truncated": truncated or len(candidates) > limit,
    }


def read_definitions(projects):
    paths = [HOME / ".config/opencode/agents", HOME / ".config/opencode/agent"]
    for p in projects:
        paths.extend([Path(p) / ".opencode/agents", Path(p) / ".opencode/agent"])
    out = []
    for directory in existing_unique(paths):
        for f in sorted(Path(directory).glob("*.md"))[:300]:
            try:
                if f.is_symlink() or f.stat().st_size > 128000:
                    continue
                raw = f.read_text("utf-8-sig")
                meta = {}
                # Small, explicit frontmatter subset. Not a general YAML parser.
                body = raw
                if raw.startswith("---"):
                    parts = raw.split("---", 2)
                    if len(parts) == 3:
                        for line in parts[1].splitlines():
                            m = re.match(r"^(name|description|mode|model):\s*(.*?)\s*$", line)
                            if m:
                                meta[m[1]] = m[2].strip("\"'")
                        body = parts[2].strip()
                out.append(
                    {
                        "name": meta.get("name") or f.stem,
                        "mode": meta.get("mode", "unspecified"),
                        "model": meta.get("model", ""),
                        "description": redact(meta.get("description"), 500),
                        "source": "definition file",
                        "directory": directory,
                        "prompt": redact(body, 6000),
                    }
                )
            except (OSError, UnicodeError):
                continue
    return out


def scan_paths(roots, depth=5, max_dirs=6000, max_seconds=12):
    start = time.monotonic()
    count = 0
    found = {}
    errors = []
    truncated = False
    skips = {
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "AppData",
        "Windows",
        "Program Files",
        "Program Files (x86)",
        "$Recycle.Bin",
        "Library",
        ".cache",
        "target",
        "dist",
        "build",
    }

    def add(kind, p):
        path = str(Path(p).resolve())
        found[kind + ":" + path_key(path)] = {"kind": kind, "path": path, "name": path_name(path)}

    for root in roots:
        p = Path(os.path.expandvars(root)).expanduser()
        if not p.is_dir():
            errors.append("Folder not found: " + str(p))
            continue
        queue = deque([(p, 0)])
        while queue:
            directory, level = queue.popleft()
            count += 1
            if count > max_dirs or time.monotonic() - start > max_seconds:
                truncated = True
                break
            try:
                if directory.is_symlink():
                    continue
                children = list(os.scandir(directory))
                names = {e.name for e in children}
                if ".git" in names or ".opencode" in names:
                    add("project", directory)
                if "opencode.db" in names:
                    add("database", directory / "opencode.db")
                if "usage-events.jsonl" in names:
                    add("router", directory / "usage-events.jsonl")
                if directory.name == ".codex" or (
                    "sessions" in names
                    and ("config.toml" in names or "session_index.jsonl" in names)
                ):
                    add("codex", directory)
                if level < depth:
                    for e in children:
                        if (
                            e.is_dir(follow_symlinks=False)
                            and e.name not in skips
                            and (
                                not e.name.startswith(".")
                                or e.name in (".local", ".opencode", ".codex", ".config")
                            )
                        ):
                            queue.append((Path(e.path), level + 1))
            except (OSError, PermissionError) as e:
                if len(errors) < 30:
                    errors.append(redact(e, 180))
        if truncated:
            break
    return {
        "items": sorted(found.values(), key=lambda x: (x["kind"], x["path"])),
        "scanned_dirs": count,
        "truncated": truncated,
        "errors": errors,
        "seconds": round(time.monotonic() - start, 2),
    }


def git_info(directory):
    if not Path(directory).is_dir():
        return {"error": "Directory unavailable"}
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}

    def run(args):
        p = subprocess.run(
            ["git", "--no-optional-locks", "-C", directory, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            env=env,
        )
        if p.returncode:
            raise ValueError(redact(p.stderr.strip(), 200))
        return p.stdout

    try:
        branch = run(["symbolic-ref", "--short", "-q", "HEAD"]).strip()
    except Exception:
        branch = "(detached or unavailable)"
    try:
        raw = run(["log", "-12", "--format=%H%x1f%ct%x1f%s"])
        commits = []
        for line in raw.splitlines():
            parts = line.split("\x1f", 2)
            if len(parts) == 3:
                commits.append(
                    {"sha": parts[0], "ts": stamp(int(parts[1])), "subject": redact(parts[2], 300)}
                )
        # No diff contents or project commands are executed.
        return {"branch": branch, "commits": commits}
    except Exception as e:
        return {"branch": branch, "commits": [], "error": redact(e, 180)}
