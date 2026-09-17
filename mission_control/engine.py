"""Collection engine, alert derivation and the published dashboard snapshot."""

import copy
import json
import os
import re
import threading
import time
from collections import Counter, OrderedDict, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlencode

from .core import (
    ACTIVE,
    LOG,
    STATES,
    VERSION,
    Diagnostics,
    LifecycleError,
    add_usage,
    codex_usage,
    day,
    default_config,
    digest,
    fingerprint,
    is_within,
    make_session,
    now_ms,
    number,
    obj,
    path_key,
    path_name,
    public_copy,
    readonly_db,
    redact,
    stamp,
    validate_config,
    zero_usage,
)
from .incremental import AGGREGATE_BUDGET_SECONDS, aggregate_source
from .migration import migrate_config
from .sources import (
    JsonlReader,
    codex_apply,
    discover_all_codex_files,
    enrich_oc_session,
    git_info,
    local_json,
    oc_headers,
    read_definitions,
    read_oc_live,
    read_opencode,
    scan_paths,
)
from .store import Store


def normalize_report(raw):
    allowed = {
        "event_id",
        "session_id",
        "source",
        "timestamp",
        "state",
        "title",
        "task",
        "task_group",
        "model",
        "agent",
        "parent_id",
        "directory",
        "tool",
        "message",
        "commit_sha",
    }
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValueError("Invalid event fields. Use the reporting schema in Integrations.")
    for key in ("event_id", "session_id", "source"):
        if not isinstance(raw.get(key), str) or not 1 <= len(raw[key]) <= 200:
            raise ValueError(key + " is required (1–200 characters).")
    if raw["source"] not in ("chatgpt", "codex", "opencode", "manual"):
        raise ValueError("source: chatgpt, codex, opencode or manual.")
    if raw.get("state") and raw["state"] not in STATES:
        raise ValueError("Unknown state.")
    out = copy.deepcopy(raw)
    if "timestamp" in raw:
        ts = stamp(raw["timestamp"])
        if not ts or ts > now_ms() + 300000 or ts < now_ms() - 730 * 86400000:
            raise ValueError(
                "timestamp is outside the accepted two-year history / five-minute clock-skew window."
            )
        out["timestamp"] = ts
    else:
        # Deterministic absent timestamp allows an idempotent replay of an event.
        out["timestamp"] = 0
    for key, v in out.items():
        if key not in ("timestamp",) and not isinstance(v, str):
            raise ValueError(key + " must be a string.")
        if isinstance(v, str) and len(v) > (5000 if key in ("task", "message") else 1000):
            raise ValueError(key + " is too long.")
    if out.get("parent_id") == out["session_id"]:
        raise ValueError("A session cannot be its own parent.")
    if out.get("commit_sha") and not re.fullmatch(r"[a-fA-F0-9]{7,64}", out["commit_sha"]):
        raise ValueError("Invalid commit SHA.")
    return out


def derive_alerts(sessions, cfg, sources):
    alerts = []
    now = now_ms()

    def alert(s, kind, severity, text):
        alerts.append(
            {
                "id": digest(s.get("id", ""), kind),
                "session_id": s.get("id", ""),
                "project": s.get("directory", ""),
                "kind": kind,
                "severity": severity,
                "text": text,
                "ts": now,
            }
        )

    for s in sessions:
        recent = now - s["updated"] < 86400000
        if (
            s["state"] in ACTIVE | {"retry", "stale"}
            and s.get("turn_started")
            and now - s["updated"] > cfg["stall_seconds"] * 1000
        ):
            alert(
                s,
                "silence",
                "warning",
                "No new activity evidence within the configured threshold. Check the source; this does not prove a crash.",
            )
        expected = cfg["expected_models"].get(s["id"]) or cfg["expected_models"].get(s["agent"])
        if expected and s["model"] != "unknown" and s["model"] != expected and recent:
            alert(s, "model_mismatch", "danger", f"Expected {expected}; observed {s['model']}.")
        budget = cfg["token_budget"]
        if budget and s["usage"]["total"] > budget and recent:
            alert(
                s,
                "budget",
                "warning",
                f"Session token budget exceeded: {int(s['usage']['total']):,} / {budget:,}.",
            )
        last_tools = s["tools"][-5:]
        if recent and len(last_tools) >= 3 and all(t["state"] == "error" for t in last_tools[-3:]):
            alert(s, "tool_errors", "danger", "Three consecutive recorded tool failures.")
        if (
            recent
            and len(last_tools) >= 5
            and len({(t["name"], t["input"]) for t in last_tools}) == 1
        ):
            alert(
                s,
                "possible_loop",
                "warning",
                "Five identical recent tool calls. Possible loop; review before interrupting.",
            )
        if s["state"] == "retry":
            alert(
                s, "retry", "warning", s.get("retry_message") or "OpenCode reports retry/backoff."
            )
        if recent and any("429" in t.get("output", "") for t in last_tools):
            alert(
                s,
                "rate_limit",
                "warning",
                "A recent tool result contains HTTP 429. Inspect the provider response.",
            )
        roots = cfg["allowed_paths"].get(s["agent"], [])
        outside = [
            p
            for p in s["files"]
            if roots
            and not any(
                is_within(p if re.match(r"^(?:[A-Za-z]:|/)", p) else s["directory"] + "/" + p, r)
                for r in roots
            )
        ]
        if outside and recent:
            alert(s, "scope", "danger", "Recorded file outside assigned scope: " + outside[0])
        if (
            s["context_limit"]
            and s["context_tokens"]
            and s["context_tokens"] / s["context_limit"] >= 0.85
            and recent
        ):
            alert(
                s,
                "context",
                "warning",
                "Last reported input context is at least 85% of the recorded context window.",
            )
    writers = defaultdict(list)
    for s in sessions:
        if s["state"] in ACTIVE and now - s["updated"] < 300000:
            for p in s["files"]:
                full = p if re.match(r"^(?:[A-Za-z]:|/)", p) else s["directory"] + "/" + p
                writers[path_key(full)].append(s)
    for p, values in writers.items():
        if len(values) > 1:
            alert(
                values[0],
                "overlap:" + p,
                "warning",
                "Possible overlapping work on "
                + p
                + ": "
                + ", ".join(s["agent"] for s in values[:4]),
            )
    for source in sources:
        if source.get("error"):
            alert({}, "source:" + source["id"], "warning", source["label"] + ": " + source["error"])
    return sorted(alerts, key=lambda a: (a["severity"] != "danger", a["kind"]))


def build_fact(s):
    """Compact, read-only analytics view of a single published session."""
    daily = defaultdict(zero_usage)
    daily_models = defaultdict(dict)
    for e in s["usage_events"]:
        d = day(e["ts"])
        if not d:
            continue
        add_usage(daily[d], e)
        key = (e["provider"], e["model"])
        row = daily_models[d].setdefault(key, {"usage": zero_usage(), "requests": 0})
        add_usage(row["usage"], e)
        row["requests"] += 1
    assessment = s.get("assessment")
    return {
        "id": s["id"],
        "source": s["source"],
        "updated": s["updated"],
        "project": path_key(s["directory"]),
        "directory": s["directory"],
        "group": (assessment or {}).get("task_group") or s.get("task_group", ""),
        "model": s["model"],
        "provider": s["provider"],
        "usage_total": s["usage"]["total"],
        "files": tuple(s["files"]),
        "errors": s["errors"],
        "retries": s["retry_count"],
        "model_usage": tuple(
            {
                "model": m["model"],
                "provider": m["provider"],
                "usage": dict(m["usage"]),
                "cost": m.get("cost"),
                "requests": m["requests"],
            }
            for m in s["model_usage"].values()
        ),
        "assessment": copy.deepcopy(assessment) if assessment else None,
        "daily": {d: dict(u) for d, u in daily.items()},
        "daily_models": {d: {k: dict(v) for k, v in m.items()} for d, m in daily_models.items()},
        "usage_events_dropped": s.get("usage_events_dropped", 0),
        "session_flags": session_flags(s),
    }


def build_facts(rows):
    """Compactly pre-aggregate published sessions for analytics.

    Returns shared, read-only structures computed once per published revision.
    Per-day and per-day-per-model usage are summed here so a request never walks
    the full ``usage_events`` history again, and nothing needs a deep copy of the
    whole session graph.
    """
    return [build_fact(s) for s in rows]


def codex_session_payload(s):
    """JSON-safe snapshot of a fully processed Codex session for a checkpoint.

    Stored with the per-file read checkpoint so a restarted observer can
    republish every accounted session from durable state instead of re-reading
    unchanged logs. The activity timeline (``events``) is not part of any
    snapshot surface and is skipped; usage events are kept so coverage flags and
    analytics stay identical to the pre-restart state.
    """
    return {
        k: copy.deepcopy(v)
        for k, v in s.items()
        if (k == "_cumulative" or not k.startswith("_")) and k != "events"
    }


def _restore_codex_item(path, saved):
    """Rebuild a cached Codex item from a durable checkpoint.

    Returns ``None`` when the checkpoint does not carry a usable session
    payload (an older state, or a file that never finished a read), in which
    case the file is read again instead of publishing invented totals. When
    the checkpoint also carries the reader position, the restored reader
    continues from there so an appended file applies only its new records;
    checkpoints without a position fall back to a full read (the reader
    detects the missing identity and resets).
    """
    payload = saved.get("session") if isinstance(saved, dict) else None
    if not isinstance(payload, dict) or not payload.get("usage"):
        return None
    s = make_session("codex", Path(path).stem)
    for key, value in payload.items():
        s[key] = copy.deepcopy(value)
    s["usage_known"] = bool(s.get("usage_known") or s["usage"].get("total"))
    reader = JsonlReader()
    offset = saved.get("offset")
    if isinstance(offset, int) and offset > 0:
        reader.offset = offset
        identity = saved.get("identity")
        if isinstance(identity, (list, tuple)) and len(identity) == 2:
            reader.identity = (identity[0], identity[1])
        mtime_ns = saved.get("mtime_ns")
        if isinstance(mtime_ns, int):
            reader.mtime = mtime_ns
    return {"reader": reader, "session": s}


COVERAGE_COMPLETE = "complete"
COVERAGE_PARTIAL = "partial"
COVERAGE_UNKNOWN = "unknown"

# Which session source each coverage-relevant kind of source feeds.
SESSION_SOURCE_KINDS = {"opencode": "database", "codex": "codex"}


def session_flags(s):
    """Exact per-session completeness facts shared by every coverage surface.

    ``ledger`` compares the kept usage-event ledger with the session total,
    ``daily``/``model`` are only complete when that ledger covers the full
    total, ``file`` records whether the detail window kept the whole history,
    ``detail_pending`` marks sessions whose detail may still change and
    ``aggregate`` marks usage aggregates that are still catching up. A complete
    overall total never inflates a partial breakdown on its own.
    """
    usage = s.get("usage") or {}
    total = int(number(usage.get("total")))
    events = s.get("usage_events") or []
    dropped = int(s.get("usage_events_dropped") or 0)
    ledger_total = sum(int(number(e.get("total"))) for e in events)
    ledger_ok = dropped == 0 and ledger_total == total
    daily_ok = ledger_ok and all(day(e.get("ts")) for e in events)
    model_total = sum(
        int(number((m.get("usage") or {}).get("total")))
        for m in (s.get("model_usage") or {}).values()
    )
    model_ok = ledger_ok and model_total == total
    detail_pending = bool(
        s.get("parts_truncated")
        or s.get("messages_truncated")
        or s.get("_aggregate_truncated")
        or s.get("_pending_detail")
    )
    return {
        "ledger": ledger_ok,
        "daily": daily_ok,
        "model": model_ok,
        "file": not detail_pending,
        "evicted": dropped,
        "detail_pending": detail_pending,
        "aggregate": bool(s.get("_aggregate_complete", True)),
    }


def _flag_status(flags, key):
    if not flags:
        return COVERAGE_UNKNOWN
    return COVERAGE_COMPLETE if all(f[key] for f in flags) else COVERAGE_PARTIAL


def _conclude(values):
    """True only when every source explicitly reports True, None when unknown."""
    if not values:
        return None
    if any(v is False for v in values):
        return False
    if any(v is None for v in values):
        return None
    return True


def coverage_breakdowns(flags):
    return {
        "daily": _flag_status(flags, "daily"),
        "model": _flag_status(flags, "model"),
        "file": _flag_status(flags, "file"),
    }


def coverage_breakdown_details(flags):
    return {
        "sessions_scored": len(flags),
        "daily_partial_sessions": sum(1 for f in flags if not f["daily"]),
        "model_partial_sessions": sum(1 for f in flags if not f["model"]),
        "file_partial_sessions": sum(1 for f in flags if not f["file"]),
    }


def _coverage_details(flags):
    return {
        "details_truncated": any(f["detail_pending"] for f in flags),
        "detail_events_evicted": sum(f["evicted"] for f in flags),
    }


def assemble_coverage(flags, sources, scope):
    """One coverage block shared by the snapshot, analytics, exports and MCP.

    Source-wide fields (metadata, aggregates, discovery counts, freshness)
    describe the loaded source window; breakdowns and detail fields are scored
    on the exact session flags they receive, so a complete total never implies
    a complete per-day, per-model or per-file split.
    """
    session_sources = [
        s
        for s in sources
        if s.get("kind") in ("database", "codex") and s.get("scoped") is not False
    ]
    discovered = [
        s.get("discovered_sessions")
        for s in session_sources
        if s.get("discovered_sessions") is not None
    ]
    processed = [
        s.get("processed_sessions")
        for s in session_sources
        if s.get("processed_sessions") is not None
    ]
    reads = [
        s.get("last_successful_read_at")
        for s in session_sources
        if s.get("last_successful_read_at")
    ]
    metadata_complete = _conclude([s.get("metadata_complete") for s in session_sources])
    details = _coverage_details(flags)
    return {
        "scope": dict(scope),
        "metadata_complete": metadata_complete,
        "aggregates_complete": _conclude(
            [s.get("aggregates_complete") for s in session_sources]
        ),
        "history_limited": metadata_complete is False,
        "breakdowns": coverage_breakdowns(flags),
        "breakdown_details": coverage_breakdown_details(flags),
        "details_truncated": details["details_truncated"],
        "detail_events_evicted": details["detail_events_evicted"],
        "catching_up": bool(
            any(s.get("catching_up") for s in sources)
            or any(not f["aggregate"] for f in flags)
        ),
        "source_stale": any(s.get("stale") for s in sources),
        "read_blocked": any(s.get("read_blocked") for s in sources),
        "discovered_sessions": sum(discovered) if discovered else None,
        "processed_sessions": sum(processed) if processed else None,
        "last_successful_read_at": min(reads) if reads else None,
    }


def build_snapshot_coverage(rows, sources, scope):
    return assemble_coverage([session_flags(s) for s in rows], sources, scope)


def unknown_coverage(scope):
    """Honest placeholder before the first collector cycle published data."""
    return assemble_coverage([], [], scope)


def range_coverage(selected_facts, basis, days, project, task_group, source):
    """Coverage for one analytics range over the exact selected facts.

    Source-wide fields are inherited from the published basis; breakdowns and
    detail fields are recomputed for the selected sessions only. ``catching_up``
    is range-precise: a global catch-up that cannot touch the selected range
    does not flag it.
    """
    base = dict(basis or {})
    flags = [f["session_flags"] for f in selected_facts]
    selected_kinds = {
        SESSION_SOURCE_KINDS.get(f.get("source"))
        for f in selected_facts
        if f.get("source")
    }
    catching_kinds = set(base.get("catching_kinds") or ())
    details = _coverage_details(flags)
    return {
        "scope": {
            "kind": "range",
            "days": days,
            "project": project or "",
            "task_group": task_group or "",
            "source": source or "",
            "sessions_in_range": len(selected_facts),
        },
        "metadata_complete": base.get("metadata_complete"),
        "aggregates_complete": base.get("aggregates_complete"),
        "history_limited": base.get("metadata_complete") is False,
        "breakdowns": coverage_breakdowns(flags),
        "breakdown_details": coverage_breakdown_details(flags),
        "details_truncated": details["details_truncated"],
        "detail_events_evicted": details["detail_events_evicted"],
        "catching_up": bool(
            any(not f["aggregate"] for f in flags)
            or (catching_kinds & selected_kinds)
        ),
        "source_stale": bool(base.get("source_stale")),
        "read_blocked": bool(base.get("read_blocked")),
        "discovered_sessions": base.get("discovered_sessions"),
        "processed_sessions": base.get("processed_sessions"),
        "last_successful_read_at": base.get("last_successful_read_at"),
    }


def compute_analytics(facts, cutoff, cfg, days, project, task_group, source, basis=None):
    """Pure aggregation over pre-built facts (no session deep copies)."""
    models = {}
    daily = defaultdict(zero_usage)
    filetotals = defaultdict(float)
    selected = 0
    selected_facts = []
    token_total = 0
    dropped = 0
    cutoff_day = day(cutoff) if cutoff else ""

    def modelrow(model, provider):
        key = provider + "/" + model
        return models.setdefault(
            key,
            {
                "id": key,
                "model": model,
                "provider": provider,
                "usage": zero_usage(),
                "sessions": set(),
                "requests": 0,
                "recorded_cost": None,
                "estimated_cost": None,
                "priced_tokens": 0,
                "assessments": [],
                "errors": 0,
                "retries": 0,
            },
        )

    for s in facts:
        if (
            s["source"] == "reported"
            or (source and source != s["source"])
            or (project and s["project"] != path_key(project))
        ):
            continue
        if task_group and s["group"] != task_group:
            continue
        if cutoff and s["updated"] < cutoff:
            continue
        selected += 1
        selected_facts.append(s)
        dropped += s.get("usage_events_dropped", 0)
        if cutoff:
            session_tokens = 0
            for d, u in s["daily"].items():
                if d >= cutoff_day:
                    add_usage(daily[d], u)
                    session_tokens += u["total"]
            bymodel = {}
            for d, entries in s["daily_models"].items():
                if d < cutoff_day:
                    continue
                for (provider, model), row in entries.items():
                    out = bymodel.setdefault(
                        provider + "/" + model,
                        {
                            "model": model,
                            "provider": provider,
                            "usage": zero_usage(),
                            "cost": None,
                            "requests": 0,
                        },
                    )
                    add_usage(out["usage"], row["usage"])
                    out["requests"] += row["requests"]
        else:
            for d, u in s["daily"].items():
                add_usage(daily[d], u)
            session_tokens = s["usage_total"]
            bymodel = {
                m["provider"] + "/" + m["model"]: {
                    "model": m["model"],
                    "provider": m["provider"],
                    "usage": m["usage"],
                    "cost": m["cost"],
                    "requests": m["requests"],
                }
                for m in s["model_usage"]
            }
        token_total += session_tokens
        if s["files"]:
            for f in s["files"]:
                filetotals[f] += session_tokens / len(s["files"])
        for entry in bymodel.values():
            r = modelrow(entry["model"], entry["provider"])
            add_usage(r["usage"], entry["usage"])
            r["sessions"].add(s["id"])
            r["requests"] += entry["requests"]
            if entry.get("cost") is not None:
                r["recorded_cost"] = (r["recorded_cost"] or 0) + entry["cost"]
            pricing = cfg["pricing"].get(r["id"]) or cfg["pricing"].get(r["model"])
            if pricing:
                u = entry["usage"]
                components = {
                    "input": u["input"],
                    "output": u["output"] + u["reasoning"],
                    "cache_read": u["cache_read"],
                    "cache_write": u["cache_write"],
                }
                if all(v == 0 or k in pricing for k, v in components.items()):
                    estimate = sum(v * pricing.get(k, 0) / 1e6 for k, v in components.items())
                    r["estimated_cost"] = (r["estimated_cost"] or 0) + estimate
                    r["priced_tokens"] += u["total"]
            # Error and retry counts are session-level, not fabricated per-model splits.
            if len(s["model_usage"]) == 1:
                r["errors"] += s["errors"]
                r["retries"] += s["retries"]
        assessment = s["assessment"]
        if assessment:
            r = modelrow(
                assessment.get("model") or s["model"], assessment.get("provider") or s["provider"]
            )
            r["assessments"].append(assessment)
    mrows = []
    for r in models.values():
        r["sessions"] = len(r["sessions"])
        assessed = r.pop("assessments")
        verified_tests = [a for a in assessed if isinstance(a.get("tests_passed"), bool)]
        fixes = [a["review_fixes"] for a in assessed if isinstance(a.get("review_fixes"), int)]
        elapsed = [
            a["duration_seconds"]
            for a in assessed
            if isinstance(a.get("duration_seconds"), (int, float))
        ]
        r.update(
            assessed_tasks=len(assessed),
            test_samples=len(verified_tests),
            test_pass_rate=sum(a["tests_passed"] for a in verified_tests) / len(verified_tests)
            if verified_tests
            else None,
            avg_review_fixes=sum(fixes) / len(fixes) if fixes else None,
            avg_duration_seconds=sum(elapsed) / len(elapsed) if elapsed else None,
            tokens_per_session=r["usage"]["total"] / r["sessions"] if r["sessions"] else None,
        )
        mrows.append(r)
    activity = []
    for i in range(363, -1, -1):
        d = (datetime.now().date() - timedelta(days=i)).isoformat()
        activity.append({"date": d, **daily.get(d, zero_usage())})
    return {
        "tokens": token_total,
        "sessions": selected,
        "models": sorted(mrows, key=lambda r: -r["usage"]["total"]),
        "days": [{"date": d, **u} for d, u in sorted(daily.items())],
        "activity": activity,
        "files": [
            {"path": f, "estimated_tokens": round(v, 1)}
            for f, v in sorted(filetotals.items(), key=lambda i: -i[1])[:25]
        ],
        "methodology": "Loaded native sessions only. Router excluded to avoid double counting. Files use equal allocation, not measured per-file cost. Outcomes/durations are owner-reported assessments, not independently verified. No model quality ranking is inferred from token volume.",
        "cost_note": "Missing rates/costs remain unknown. Configured USD-per-million rates are estimates, not invoices. Period costs are estimates only.",
        "days_filter": days,
        "task_group": task_group,
        "project": project,
        "usage_events_dropped": dropped,
        "coverage": range_coverage(selected_facts, basis, days, project, task_group, source),
    }


class Engine:
    """Collects local sources into an immutable, publishable snapshot.

    Lock lifecycle
    --------------
    ``lock`` (RLock) protects the ``sessions`` / ``snapshot`` / ``cfg`` state,
    the published ``_facts`` and the caches. ``poll_lock`` serialises collector
    cycles. Network, database and git I/O always happens *outside* ``lock``;
    handlers only take ``lock`` to read a reference, never to run expensive
    work. Every published object (``sessions``, ``snapshot``, ``_facts``) is
    treated as immutable copy-on-write: collectors and mutators build a new
    structure and swap it under ``lock``, so readers can copy outside the lock
    without a torn read. ``assess`` never mutates a published fact in place.
    """

    MAX_PREVIOUS_STATES = 5000
    GIT_CACHE_TTL = 3600
    ANALYTICS_CACHE_MAX = 16

    def __init__(self, directory, overrides=None, repair_secrets=False):
        self.store = Store(directory)
        self._closed = False
        self._closing = False
        self._close_lock = threading.Lock()
        try:
            self.control_token = self.store.secret("owner.token", repair=repair_secrets)
            self.mcp_token = self.store.secret("mcp.token", repair=repair_secrets)
            self.pairing_key = self.store.secret("pairing.key", repair=repair_secrets)
            self.config_path = self.store.directory / "config.json"
            if self.config_path.exists():
                raw = json.loads(self.config_path.read_text("utf-8"))
            else:
                raw = {}
            # Legacy v5 configuration files have no version marker. Known
            # settings are preserved exactly; unknown keys are archived into the
            # observer store instead of being silently dropped.
            raw, archived = migrate_config(raw, set(default_config()))
            if archived:
                history = self.store.setting("migrated_config_backup", []) or []
                history.append({"archived_at": now_ms(), "keys": archived})
                self.store.set_setting("migrated_config_backup", history[-10:])
                LOG.warning("Archived unknown legacy settings: %s", ", ".join(sorted(archived)))
            raw.update(overrides or {})
            self.cfg = validate_config(raw)
            self.lock = threading.RLock()
            self.poll_lock = threading.Lock()
            self.stop = threading.Event()
            self.wake = threading.Event()
            self.db_cache = {}
            self._aggregate_state = {}
            self.codex_cache = {}
            self.router_cache = {}
            self.git_cache = {}
            self.scan_result = {"running": False, "items": []}
            self.sessions = {}
            self.previous_states = {}
            # Persisted per-source read freshness: a failed or deadline-limited
            # read keeps the last successful timestamp instead of faking one.
            self._read_health = dict(self.store.setting("source_read_health", {}) or {})
            self._coverage_basis = None
            self.snapshot = {
                "version": VERSION,
                "generated_at": 0,
                "refreshing": True,
                "sessions": [],
                "projects": [],
                "sources": [],
                "alerts": [],
                "definitions": [],
                "router": [],
                "coverage": unknown_coverage({"kind": "snapshot", "sessions_loaded": 0}),
            }
            self.started = now_ms()
            self.port = 8765
            self.thread = None
            self._scan_thread = None
            self.server = None
            self._facts = ()
            self._facts_revision = 0
            self._config_revision = 0
            self._analytics_cache = OrderedDict()
            self.save_config(self.cfg)
        except BaseException:
            # Never leak the observer DB when construction fails part-way.
            self.store.close()
            self._closed = True
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def config(self):
        with self.lock:
            return copy.deepcopy(self.cfg)

    def save_config(self, cfg):
        checked = validate_config(cfg)
        tmp = self.config_path.with_suffix(".tmp")
        # Atomic replacement and serialization under the same lock.
        with self.lock:
            tmp.write_text(json.dumps(checked, ensure_ascii=False, indent=2), "utf-8")
            try:
                tmp.chmod(0o600)
            except OSError:
                pass
            os.replace(tmp, self.config_path)
            self.cfg = checked
            # Pricing/config changes must invalidate cached aggregates at once.
            self._config_revision = getattr(self, "_config_revision", 0) + 1
            self._analytics_cache.clear()
        self.wake.set()

    def start(self):
        if self._closing or self._closed:
            raise LifecycleError("engine is shutting down")
        if self.thread is not None and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._loop, name="observer-poll", daemon=True)
        self.thread.start()

    def _loop(self):
        while not self.stop.is_set():
            try:
                self.poll()
            except LifecycleError:
                break
            except Exception:
                LOG.exception("Collector cycle failed")
                with self.lock:
                    self.snapshot = {
                        **self.snapshot,
                        "collector_error": "Collector error. See mission-control.log.",
                        "refreshing": False,
                    }
            self.wake.wait(self.config()["poll_seconds"])
            self.wake.clear()

    def poll(self):
        """Run one collector cycle, serialised and rejected once shutting down."""
        if self._closing or self._closed:
            raise LifecycleError("engine is shutting down")
        with self.poll_lock:
            if self._closing or self._closed:
                raise LifecycleError("engine is shutting down")
            self._poll()

    def _poll(self):
        cfg = self.config()
        all_sessions = {}
        sources = []
        projects = list(cfg["projects"])
        definitions = []
        router = []
        with self.lock:
            self.snapshot = {**self.snapshot, "refreshing": True}
        for path in cfg["db_paths"]:
            src = {
                "id": digest("db", path),
                "label": "OpenCode SQLite",
                "location": path,
                "kind": "database",
                "checked": now_ms(),
            }
            cached = self.db_cache.get(path)
            rows, dirs = [], []
            stale = False
            note = ""
            try:
                key = (fingerprint(path), cfg["history_limit"])
                if not cached or cached[0] != key:
                    fresh = read_opencode(path, cfg["history_limit"])
                    if fresh[2].get("deadline_exceeded"):
                        # A partial read is better than none, but a previously
                        # complete snapshot is better still. Either way the
                        # source is flagged so the UI can show honest coverage.
                        stale = True
                        if cached is not None:
                            note = "Read exceeded its deadline; showing the last complete snapshot."
                        else:
                            note = "Read exceeded its deadline; partial coverage."
                            cached = (key, fresh)
                    else:
                        cached = (key, fresh)
                        self.db_cache[path] = cached
                rows, dirs, coverage = copy.deepcopy(cached[1])
                src.update(coverage)
                src["ok"] = True
                self._mark_read(src["id"], not stale, note or None)
            except Exception as e:
                if cached is None:
                    src.update(ok=False, error=redact(e, 240), read_blocked=True)
                else:
                    # Never drop every session on a transient read failure: fall
                    # back to the last complete snapshot and mark it stale.
                    rows, dirs, coverage = copy.deepcopy(cached[1])
                    src.update(coverage)
                    src.update(ok=False, stale=True, error=redact(e, 240))
                self._mark_read(src["id"], False, e)
            if stale:
                src["stale"] = True
                src["error"] = note
            self._aggregate_db_source(src, path, rows)
            projects.extend(dirs)
            for s in rows:
                old = all_sessions.get(s["id"])
                if old is None or s["updated"] > old["updated"]:
                    all_sessions[s["id"]] = s
            sources.append(src)
        native_dirs = list(dict.fromkeys(p for p in projects if p and Path(p).is_dir()))
        if cfg["opencode_urls"]:
            with ThreadPoolExecutor(max_workers=min(4, len(cfg["opencode_urls"]))) as pool:
                futures = {
                    pool.submit(read_oc_live, url, native_dirs): url for url in cfg["opencode_urls"]
                }
                for fut in as_completed(futures):
                    url = futures[fut]
                    src = {
                        "id": digest("api", url),
                        "label": "OpenCode live API",
                        "location": url,
                        "kind": "api",
                        "checked": now_ms(),
                    }
                    try:
                        statuses, rows, defs, info = fut.result()
                        src.update(ok=True, **info)
                        self._mark_read(src["id"], True)
                        definitions.extend(defs)
                        for r in rows:
                            if not isinstance(r.get("id"), str):
                                continue
                            sid = "opencode:" + r["id"]
                            s = all_sessions.get(sid)
                            if s is None:
                                s = make_session(
                                    "opencode", r["id"], r.get("title"), r.get("directory")
                                )
                                t = obj(r.get("time"))
                                s.update(
                                    created=int(number(t.get("created"))),
                                    updated=int(number(t.get("updated"))),
                                )
                                if r.get("parentID"):
                                    s["parent_id"] = "opencode:" + str(r["parentID"])
                                    s["relationship"] = "parent_unknown"
                                all_sessions[sid] = s
                            # Refresh metadata, but do not count API + DB tokens twice.
                            t = obj(r.get("time"))
                            s["updated"] = max(s["updated"], int(number(t.get("updated"))))
                            if not (s["confidence"] == "verified" and s["state"] in ACTIVE):
                                s["_server"] = url
                            if r.get("directory"):
                                s["directory"] = r["directory"]
                                s["project"] = path_name(r["directory"])
                                projects.append(r["directory"])
                        for sid, st in statuses.items():
                            s = all_sessions.get("opencode:" + sid)
                            if s is None:
                                s = make_session("opencode", sid, directory=st.get("_directory"))
                                all_sessions[s["id"]] = s
                            if (
                                s["confidence"] == "verified"
                                and s["state"] in ACTIVE
                                and st["type"] == "idle"
                            ):
                                s["warnings"].append(
                                    "Different servers report conflicting states; preserving the busy observation."
                                )
                                continue
                            s["_server"] = url
                            s["observed"] = now_ms()
                            s["confidence"] = "verified"
                            s["state"] = {"busy": "running", "idle": "idle", "retry": "retry"}[
                                st["type"]
                            ]
                            if (
                                s["state"] == "running"
                                and s["tools"]
                                and s["tools"][-1]["state"] == "running"
                            ):
                                s["state"] = "tool"
                            s["state_evidence"] = "OpenCode /session/status: " + st["type"]
                            if s["state"] == "retry":
                                s["retry_message"] = redact(st.get("message"), 300)
                                s["retry_count"] = max(
                                    s["retry_count"], int(number(st.get("attempt")))
                                )
                    except Exception as e:
                        src.update(ok=False, error=redact(e, 240))
                        self._mark_read(src["id"], False, e)
                    sources.append(src)
        enrich = [s for s in all_sessions.values() if s.get("_server") and s["state"] in ACTIVE][
            :40
        ]
        if enrich:
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = {pool.submit(enrich_oc_session, s): s for s in enrich}
                for f in as_completed(futures):
                    try:
                        f.result()
                    except Exception:
                        futures[f]["warnings"].append(
                            "Live message detail unavailable; status source remains separate."
                        )
        for parent in all_sessions.values():
            for native_child in parent.get("_child_links", []):
                child = all_sessions.get("opencode:" + native_child)
                if child:
                    child["parent_id"] = parent["id"]
                    child["relationship"] = "delegated"
        all_files, coverage = discover_all_codex_files(cfg["codex_homes"])
        done_checkpoints = self.store.checkpoints("codex")
        total_files = len(all_files)
        batch = max(1, int(cfg["codex_file_limit"]))
        start = (int(self.store.setting("codex_cursor", 0) or 0)) % total_files if total_files else 0
        stats = {}
        files = []
        reuse = []
        over = []
        last_read_index = None
        for offset in range(total_files):
            index = (start + offset) % total_files
            path = all_files[index]
            try:
                stat = Path(path).stat()
                size, mtime_ns = stat.st_size, stat.st_mtime_ns
            except OSError:
                continue
            stats[path] = (size, mtime_ns)
            saved = done_checkpoints.get(path) or {}
            restorable = isinstance(saved.get("session"), dict)
            unchanged = (
                saved.get("complete")
                and int(saved.get("size") or -1) == size
                and saved.get("mtime_ns") is not None
                and int(saved.get("mtime_ns") or 0) == mtime_ns
            )
            if unchanged and (path in self.codex_cache or restorable):
                # Already aggregated and unchanged: publish the session from the
                # cache or from the durable checkpoint payload instead of
                # re-reading the file, so the snapshot keeps every processed
                # Codex session (also across restarts) while the batch rotates.
                reuse.append(path)
                continue
            if len(files) < batch:
                files.append(path)
                last_read_index = index
            else:
                # The file changed but this cycle's read budget is spent. It must
                # still be published from its last known payload, and its
                # completeness must not be claimed until the change is read.
                over.append(path)
        if total_files:
            self.store.set_setting(
                "codex_cursor",
                (last_read_index + 1) % total_files if last_read_index is not None else start,
            )
        codex_source = {
            "id": "codex-logs",
            "label": "Codex session logs",
            "location": ", ".join(cfg["codex_homes"]),
            "kind": "codex",
            "checked": now_ms(),
            "ok": bool(cfg["codex_homes"]),
            **coverage,
        }
        if not cfg["codex_homes"]:
            codex_source["note"] = (
                "No local Codex directory selected. Cloud sessions are not automatically visible."
            )
        problems = []
        skipped = 0
        catching_up = 0
        codex_diag = Diagnostics()
        for path in files:
            try:
                item = self.codex_cache.setdefault(
                    path,
                    {"reader": JsonlReader(), "session": make_session("codex", Path(path).stem)},
                )
                item.pop("restored", False)
                reader = item["reader"]
                records = reader.read(path)
                if reader.reset:
                    item["session"] = make_session("codex", Path(path).stem)
                s = codex_apply(item["session"], records, codex_diag)
                skipped += reader.skipped
                if reader.offset < Path(path).stat().st_size:
                    catching_up += 1
                s["_log"] = path
                ss = copy.deepcopy(s)
                if (
                    ss["state"] in ACTIVE | {"waiting"}
                    and now_ms() - ss["updated"] > cfg["stall_seconds"] * 1000
                ):
                    ss["state"] = "stale"
                    ss["confidence"] = "unknown"
                    ss["state_evidence"] = (
                        "Old unfinished log marker. Running/finished cannot be established."
                    )
                old = all_sessions.get(ss["id"])
                if old is None or ss["updated"] > old["updated"]:
                    all_sessions[ss["id"]] = ss
                if ss["directory"]:
                    projects.append(ss["directory"])
            except Exception as e:
                problems.append(redact(str(path) + ": " + str(e), 220))
        # Release old file caches; history is rebuilt if they enter the selected window again.
        self.codex_cache = {p: v for p, v in self.codex_cache.items() if p in set(all_files)}
        for path in reuse + over:
            item = self.codex_cache.get(path)
            if not item:
                item = _restore_codex_item(path, done_checkpoints.get(path) or {})
                if item is None:
                    continue
                self.codex_cache[path] = item
            ss = copy.deepcopy(item["session"])
            old = all_sessions.get(ss["id"])
            if old is None or ss["updated"] > old["updated"]:
                all_sessions[ss["id"]] = ss
            if ss["directory"]:
                projects.append(ss["directory"])
        updates = {}
        for path in files:
            item = self.codex_cache.get(path)
            if not item:
                continue
            try:
                stat = Path(path).stat()
            except OSError:
                continue
            complete = item["reader"].offset >= stat.st_size
            data = {"size": stat.st_size, "complete": complete}
            if complete:
                # Keep the processed session itself in the durable checkpoint so
                # a restart can publish every accounted Codex session without
                # re-reading unchanged logs and without inventing totals.
                data["session"] = codex_session_payload(item["session"])
                data["mtime_ns"] = stat.st_mtime_ns
                data["offset"] = item["reader"].offset
                if item["reader"].identity:
                    data["identity"] = list(item["reader"].identity)
            updates[path] = data
        if updates:
            self.store.put_checkpoints("codex", list(updates.items()))
        done_checkpoints.update(updates)
        files_complete = 0
        for path in all_files:
            cp = done_checkpoints.get(path) or {}
            stat_pair = stats.get(path)
            if (
                cp.get("complete")
                and stat_pair is not None
                and cp.get("size") == stat_pair[0]
                and cp.get("mtime_ns") is not None
                and cp.get("mtime_ns") == stat_pair[1]
            ):
                files_complete += 1
        pending_files = max(0, int(coverage.get("files_found") or 0) - files_complete)
        codex_source.update(
            files_found=int(coverage.get("files_found") or 0),
            loaded_files=len(files) + len(reuse) + len(over),
            files_complete=files_complete,
            pending_files=pending_files,
            aggregates_complete=pending_files == 0,
            truncated=bool(coverage.get("truncated")),
            skipped_records=skipped,
            catching_up=catching_up + pending_files,
            issues=problems[:10],
            rejected_records=codex_diag.snapshot(),
        )
        if problems:
            codex_source["error"] = f"{len(problems)} unreadable Codex log(s)."
        sources.append(codex_source)
        if cfg["codex_homes"]:
            self._mark_read(codex_source["id"], True)
        for path in cfg["router_events"]:
            src = {
                "id": digest("router", path),
                "label": "Router usage ledger",
                "location": path,
                "kind": "router",
                "checked": now_ms(),
            }
            try:
                item = self.router_cache.setdefault(
                    path,
                    {
                        "reader": JsonlReader(),
                        "events": deque(maxlen=30000),
                        "count": 0,
                        "diag": Diagnostics(),
                    },
                )
                records = item["reader"].read(path)
                if item["reader"].reset:
                    item["events"].clear()
                    item["count"] = 0
                    item["diag"] = Diagnostics()
                diag = item["diag"]
                for r in records:
                    status = r.get("status")
                    ok = isinstance(status, (int, float)) and 200 <= status < 300
                    usage = codex_usage(
                        {
                            "input_tokens": r.get("inputTokens"),
                            "cached_input_tokens": r.get("cachedInputTokens"),
                            "output_tokens": r.get("outputTokens"),
                            "total_tokens": r.get("totalTokens"),
                        },
                        diag,
                    )
                    item["events"].append(
                        {
                            "ts": stamp(r.get("at")),
                            "model": str(r.get("model") or "unknown"),
                            "provider": str(r.get("provider") or "unknown"),
                            "status": status,
                            "ok": ok,
                            "usage": usage,
                            "duration_ms": number(
                                r.get("durationMs"), diagnostics=diag, field="router.duration_ms"
                            ),
                        }
                    )
                    item["count"] += 1
                ledger = list(item["events"])
                src.update(
                    ok=True,
                    loaded_events=len(ledger),
                    total_read=item["count"],
                    truncated=item["count"] > 30000,
                    skipped_records=item["reader"].skipped,
                    rejected_records=diag.snapshot(),
                )
                router.append({"source": str(path), "events": ledger, "coverage": public_copy(src)})
                self._mark_read(src["id"], True)
            except Exception as e:
                src.update(ok=False, error=redact(e, 240), read_blocked=True)
                self._mark_read(src["id"], False, e)
            sources.append(src)
        # Explicit reports attach origin/task context to canonical sessions. They
        # never add tokens or override a live native status.
        seen_report_sessions = set()
        for report in self.store.reports():
            sid = report["session_id"]
            if sid in seen_report_sessions:
                continue
            seen_report_sessions.add(sid)
            s = all_sessions.get(sid)
            if s is None:
                s = make_session(
                    "reported",
                    sid,
                    report.get("title") or report.get("task"),
                    report.get("directory"),
                )
                s["id"] = sid if sid.startswith("reported:") else "reported:" + sid
                s["native_id"] = sid
                s["created"] = report["timestamp"] or report["_received_at"]
                s["updated"] = report["timestamp"] or report["_received_at"]
                s["model"] = report.get("model") or "unknown"
                s["agent"] = report.get("agent") or report["source"]
                s["state"] = report.get("state") or "unknown"
                s["confidence"] = "reported"
                s["state_evidence"] = "caller-supplied report, not independently verified"
                if s["state"] in ACTIVE and now_ms() - s["updated"] > cfg["stall_seconds"] * 1000:
                    s["state"] = "stale"
                s["parent_id"] = report.get("parent_id", "")
                s["relationship"] = "reported" if s["parent_id"] else "root"
                s["prompt"] = redact(report.get("task"), 5000)
                all_sessions[s["id"]] = s
            s["origin"] = report["source"]
            s["origin_evidence"] = "explicit MCP/HTTP report (caller claim)"
            s["task_group"] = report.get("task_group", "")
            s["reported_task"] = redact(report.get("task"), 5000)
            if report.get("commit_sha"):
                s["commit_sha"] = report["commit_sha"]
        excluded = {path_key(p) for p in cfg["excluded_projects"]}
        sessions = [s for s in all_sessions.values() if path_key(s["directory"]) not in excluded]
        project_paths = sorted(
            {path_key(p): p for p in projects if p and path_key(p) not in excluded}.values(),
            key=str.casefold,
        )
        definitions.extend(read_definitions(project_paths))
        if not cfg["show_prompts"]:
            definitions = [{**d, "prompt": ""} for d in definitions]
        assessments = self.store.assessments()
        rows = []
        pending = []
        for s in sessions:
            s["assessment"] = assessments.get(s["id"])
            s["project"] = path_name(s["directory"])
            s["children"] = [
                c["id"]
                for c in sessions
                if c["parent_id"] == s["id"] and c["relationship"] == "delegated"
            ]
            s["age_seconds"] = max(0, (now_ms() - s["updated"]) / 1000) if s["updated"] else None
            if not cfg["show_prompts"]:
                s["prompt"] = ""
                s["reported_task"] = ""
                s["events"] = [e for e in s["events"] if e["kind"] != "prompt"]
            pending.extend(s["events"])
            previous = self.previous_states.get(s["id"])
            statekey = (s["state"], s["confidence"])
            if previous != statekey:
                pending.append(
                    {
                        "id": digest("state", s["id"], now_ms(), statekey),
                        "session_id": s["id"],
                        "source": s["source"],
                        "kind": "state",
                        "project": s["directory"],
                        "ts": now_ms(),
                        "text": f"{s['agent']} → {s['state']} ({s['confidence']})",
                        "detail": {"evidence": s["state_evidence"]},
                    }
                )
            self.previous_states[s["id"]] = statekey
            if len(pending) >= 5000:
                self.store.events(pending)
                pending.clear()
            rows.append(s)
        if pending:
            self.store.events(pending)
            pending.clear()
        # Git is contextual. Never manufacture a "cost per commit" by assigning
        # every session from the previous 24 hours to every commit.
        prows = []
        for p in project_paths:
            members = [s for s in rows if path_key(s["directory"]) == path_key(p)]
            g = self.git_cache.get(p)
            if cfg["git_enabled"] and (not g or time.time() - g[0] > 60) and len(prows) < 30:
                self.git_cache[p] = (time.time(), git_info(p))
                g = self.git_cache[p]
            prows.append(
                {
                    "id": digest(p),
                    "path": p,
                    "name": path_name(p),
                    "sessions": len(members),
                    "active": sum(
                        s["state"] in ACTIVE and s["confidence"] == "verified" for s in members
                    ),
                    "reported_active": sum(
                        s["state"] in ACTIVE and s["confidence"] != "verified" for s in members
                    ),
                    "tokens": sum(s["usage"]["total"] for s in members),
                    "sources": sorted({s["source"] for s in members}),
                    "git": (g[1] if g and cfg["git_enabled"] else {}),
                    "monitored": True,
                }
            )
        alerts = derive_alerts(rows, cfg, sources)
        ack = set(self.store.setting("acknowledged", []))
        for a in alerts:
            a["acknowledged"] = a["id"] in ack
        rows.sort(key=lambda s: (s["state"] not in ACTIVE, -s["updated"]))
        retained = {s["id"] for s in rows}
        self._prune_state_tracking(retained, cfg)
        facts = tuple(build_facts(rows))
        for src in sources:
            self._apply_coverage(src, rows)
        coverage = build_snapshot_coverage(
            rows,
            sources,
            {
                "kind": "snapshot",
                "window_limit": int(cfg["history_limit"]),
                "sessions_loaded": len(rows),
            },
        )
        coverage_basis = {
            **coverage,
            "catching_kinds": sorted({s["kind"] for s in sources if s.get("catching_up")}),
        }
        # ``rows`` are already detached copies produced by the DB/codex read
        # windows, so publish them directly instead of duplicating the entire
        # session set (the duplicate deepcopy dominated cold-poll time at scale).
        published = {s["id"]: s for s in rows}
        snapshot = {
            "version": VERSION,
            "generated_at": now_ms(),
            "refreshing": False,
            "sessions": [self.summary(s) for s in rows],
            "projects": prows,
            "sources": sources,
            "alerts": alerts,
            "definitions": definitions,
            "router": router,
            "coverage": coverage,
            "privacy": {
                "show_prompts": cfg["show_prompts"],
                "reporting": cfg["enable_reporting"],
                "abort": cfg["allow_abort"],
            },
        }
        with self.lock:
            self.sessions = published
            self._facts = facts
            self._facts_revision += 1
            self._analytics_cache.clear()
            self._coverage_basis = coverage_basis
            self.snapshot = snapshot
        self.store.prune(cfg["history_days"])

    def _mark_read(self, src_id, ok, error=None):
        """Persist per-source read freshness without ever inventing a timestamp."""
        health = self._read_health.setdefault(src_id, {})
        if ok:
            health["last_success_at"] = now_ms()
        else:
            health["last_error_at"] = now_ms()
            health["last_error"] = redact(error or "read failed", 240)
        self.store.set_setting("source_read_health", self._read_health)

    def _apply_coverage(self, src, rows):
        """Attach the per-source completeness fields used by every coverage view."""
        health = self._read_health.get(src.get("id")) or {}
        src["last_successful_read_at"] = health.get("last_success_at")
        src["last_error_at"] = health.get("last_error_at")
        src["read_blocked"] = bool(src.get("read_blocked"))
        kind = src.get("kind")
        if kind == "database":
            src["scoped"] = True
            if src.get("ok") is False and not src.get("stale"):
                src["metadata_complete"] = None
                src["discovered_sessions"] = None
                src["processed_sessions"] = None
                src["aggregates_complete"] = False
            else:
                expected = int(src.get("total_sessions") or 0)
                loaded = int(src.get("metadata_sessions") or 0)
                src["metadata_complete"] = loaded >= expected
                src["discovered_sessions"] = expected
                done = src.get("aggregate_sessions_complete")
                src["processed_sessions"] = int(done) if done is not None else None
            flags = [
                session_flags(s)
                for s in rows
                if path_key(s.get("_db") or "") == path_key(src.get("location") or "")
            ]
            src["breakdowns"] = coverage_breakdowns(flags)
            src["detail_events_evicted"] = sum(f["evicted"] for f in flags)
        elif kind == "codex":
            ok = src.get("ok") is not False
            # No configured Codex home is "out of scope", not "incomplete".
            src["scoped"] = ok
            src["metadata_complete"] = (not src.get("truncated")) if ok else None
            src["discovered_sessions"] = int(src.get("files_found") or 0) if ok else None
            src["processed_sessions"] = int(src.get("files_complete") or 0) if ok else None
            flags = [session_flags(s) for s in rows if s.get("source") == "codex"]
            src["breakdowns"] = coverage_breakdowns(flags)
            src["detail_events_evicted"] = sum(f["evicted"] for f in flags)
        return src

    def _prune_state_tracking(self, retained, cfg):
        """Bound state-change memory and per-source caches to what is retained.

        ``previous_states`` only exists to detect transitions of currently
        visible sessions, so anything outside the retained window is dropped.
        A hard cap protects against a pathological window size.
        """
        previous = self.previous_states
        for sid in list(previous):
            if sid not in retained:
                del previous[sid]
        if len(previous) > self.MAX_PREVIOUS_STATES:
            for sid in list(previous)[: len(previous) - self.MAX_PREVIOUS_STATES]:
                del previous[sid]
        db_paths = set(cfg["db_paths"])
        for path in list(self.db_cache):
            if path not in db_paths:
                del self.db_cache[path]
        router_paths = set(cfg["router_events"])
        for path in list(self.router_cache):
            if path not in router_paths:
                del self.router_cache[path]
        aggregate_sources = {"opencode:" + path_key(p) for p in db_paths}
        for source_id in list(self._aggregate_state):
            if source_id not in aggregate_sources:
                del self._aggregate_state[source_id]
        for path in list(self.git_cache):
            if time.time() - self.git_cache[path][0] > self.GIT_CACHE_TTL:
                del self.git_cache[path]

    def _aggregate_db_source(self, src, path, rows):
        """Commit budget-bounded usage aggregates for one OpenCode database.

        Independently of the (bounded) detail window, every session's usage is
        accumulated over all step-finish parts in ascending key order and the
        cursor is persisted together with the counters, so a cycle can stop at
        any page boundary without losing or double counting tokens. A cycle
        resumes where the previous one stopped, so a finite source reaches full
        coverage instead of stopping at the first deadline.
        """
        if not rows:
            if src.get("ok"):
                src.update(
                    aggregates_complete=True,
                    aggregate_sessions_complete=0,
                    pending_sessions=0,
                    details_truncated=False,
                )
            else:
                src.update(aggregates_complete=False, pending_sessions=None)
            return
        source_id = "opencode:" + path_key(path)
        checkpoints = self.store.checkpoints(source_id)
        order = sorted(rows, key=lambda s: s.get("updated") or 0, reverse=True)
        pairs = [(s["native_id"], s.get("updated") or 0) for s in order]
        state = self._aggregate_state.setdefault(source_id, {"next_index": 0})
        pending = {}
        deadline = time.monotonic() + AGGREGATE_BUDGET_SECONDS
        try:
            with readonly_db(path) as con:
                aggregate_source(
                    con,
                    pairs,
                    checkpoints,
                    deadline,
                    lambda sid, st, _p=pending: _p.__setitem__(sid, st),
                    state=state,
                )
            if pending:
                self.store.put_checkpoints(source_id, list(pending.items()))
        except Exception as e:
            # Never publish aggregates we could not persist; the next cycle
            # retries from the last committed checkpoint.
            src["aggregate_error"] = redact(e, 160)
            src["aggregates_complete"] = False
            src["pending_sessions"] = None
            src["catching_up"] = True
            return
        complete = 0
        for s in rows:
            st = checkpoints.get(s["native_id"])
            if st and st.get("complete"):
                # Only override when the aggregate actually accounted for
                # parts; sessions with no parts at all keep the reader's
                # recorded fallback (message-level tokens) untouched.
                if st.get("parts") and (st.get("usage") or {}).get("total"):
                    s["usage"] = dict(st["usage"])
                    s["usage_known"] = True
                s["_aggregate_complete"] = True
                complete += 1
            else:
                s["_aggregate_complete"] = False
        expected = int(src.get("metadata_sessions") or len(rows))
        src["aggregate_sessions_complete"] = complete
        src["pending_sessions"] = max(0, expected - complete)
        src["aggregates_complete"] = src["pending_sessions"] == 0
        src["details_truncated"] = bool(src.get("truncated_sessions"))
        if src["pending_sessions"]:
            src["catching_up"] = True

    @staticmethod
    def summary(s):
        omit = {"events", "usage_events", "tools", "model_usage", "prompt", "reported_task"}
        out = {k: copy.deepcopy(v) for k, v in s.items() if k not in omit and not k.startswith("_")}
        out["task_preview"] = redact(s.get("reported_task") or s.get("prompt"), 180)
        out["last_tool"] = s["tools"][-1]["name"] if s["tools"] else ""
        out["can_abort"] = bool(s.get("_server")) and s["source"] == "opencode"
        return out

    def view(self):
        with self.lock:
            reference = self.snapshot
        # The snapshot is replaced wholesale, never mutated in place, so the
        # deep copy is safe outside the lock and cannot block the collector.
        snap = copy.deepcopy(reference)
        # Never continue advertising a verified busy state after a stalled
        # collector. Aging evidence changes presentation, not underlying data.
        now = now_ms()
        freshness = max(30, self.config()["poll_seconds"] * 3) * 1000
        for s in snap["sessions"]:
            if s["confidence"] == "verified" and now - s["observed"] > freshness:
                s["confidence"] = "unknown"
                s["state"] = "stale"
                s["state_evidence"] = "Live status observation expired; refresh connection."
        for p in snap["projects"]:
            members = [
                s for s in snap["sessions"] if path_key(s["directory"]) == path_key(p["path"])
            ]
            p["active"] = sum(
                s["state"] in ACTIVE and s["confidence"] == "verified" for s in members
            )
            p["reported_active"] = sum(
                s["state"] in ACTIVE and s["confidence"] != "verified" for s in members
            )
        counts = Counter(s["state"] for s in snap["sessions"])
        snap["port"] = self.port
        snap["counts"] = dict(counts)
        snap["verified_active"] = sum(
            s["state"] in ACTIVE and s["confidence"] == "verified" for s in snap["sessions"]
        )
        snap["unverified_active"] = sum(
            s["state"] in ACTIVE and s["confidence"] != "verified" for s in snap["sessions"]
        )
        snap["tokens"] = sum(
            s["usage"]["total"] for s in snap["sessions"] if s["source"] != "reported"
        )
        # Router requests can overlap native sessions. Keep them out of totals.
        for ledger in snap["router"]:
            ev = ledger.pop("events")
            ledger["requests"] = len(ev)
            ledger["errors"] = sum(e["ok"] is False for e in ev if e["status"] is not None)
            ledger["unknown_status"] = sum(e["status"] is None for e in ev)
            ledger["tokens"] = sum(e["usage"]["total"] for e in ev)
            ledger["recent"] = ev[-100:][::-1]
        return snap

    def detail(self, sid):
        with self.lock:
            reference = self.sessions.get(sid)
            defs_ref = self.snapshot["definitions"]
        s = copy.deepcopy(reference)
        defs = copy.deepcopy(defs_ref)
        if not s:
            raise KeyError("Session not found in the loaded window.")
        out = public_copy(s)
        freshness = max(30, self.config()["poll_seconds"] * 3) * 1000
        if out.get("confidence") == "verified" and now_ms() - out.get("observed", 0) > freshness:
            out.update(
                state="stale",
                confidence="unknown",
                state_evidence="Live status observation expired; refresh connection.",
            )
        out["definition"] = next(
            (
                d
                for d in defs
                if d["name"] == s["agent"] and is_within(d.get("directory"), s["directory"])
            ),
            None,
        ) or next((d for d in defs if d["name"] == s["agent"]), None)
        if not self.config()["show_prompts"]:
            out["prompt"] = ""
            out["reported_task"] = ""
            out["definition"] = None
        out["timeline"] = self.store.timeline(80, session_id=sid)["events"]
        if not self.config()["show_prompts"]:
            out["timeline"] = [e for e in out["timeline"] if e["kind"] != "prompt"]
        return out

    def analytics(self, days=0, project="", task_group="", source=""):
        cutoff = 0
        if days:
            # Inclusive local calendar window, not a rolling N*24h plus today.
            start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
                days=days - 1
            )
            cutoff = int(start.timestamp() * 1000)
        key = (days, path_key(project) if project else "", task_group, source)
        # Capture one coherent (facts, config, revision) triple under the lock.
        # The calendar day is part of the key so a stalled collector cannot keep
        # serving yesterday's cutoff, and the config revision invalidates stale
        # pricing the moment settings change.
        with self.lock:
            cfg = copy.deepcopy(self.cfg)
            revision = self._facts_revision
            config_revision = self._config_revision
            facts = self._facts
            basis = self._coverage_basis
            cache_key = (revision, config_revision, day(now_ms())) + key
            cached = self._analytics_cache.get(cache_key)
        if cached is None:
            # Aggregation runs outside the lock over one immutable revision.
            cached = compute_analytics(
                facts, cutoff, cfg, days, project, task_group, source, basis=basis
            )
            with self.lock:
                if self._facts_revision == revision and self._config_revision == config_revision:
                    self._analytics_cache[cache_key] = cached
                    while len(self._analytics_cache) > self.ANALYTICS_CACHE_MAX:
                        self._analytics_cache.popitem(last=False)
        return copy.deepcopy(cached)

    def add_report(self, raw):
        if not self.config()["enable_reporting"]:
            raise PermissionError(
                "Telemetry reporting is disabled. Enable it explicitly in Integrations."
            )
        data = normalize_report(raw)
        changed = self.store.report(data)
        if changed:
            self.store.events(
                [
                    {
                        "id": digest("report", data["event_id"]),
                        "ts": data["timestamp"] or now_ms(),
                        "session_id": data["session_id"],
                        "source": data["source"],
                        "kind": "reported",
                        "project": data.get("directory", ""),
                        "text": redact(
                            data.get("message")
                            or data.get("task")
                            or data.get("state")
                            or "Task report",
                            1200,
                        ),
                        "detail": {"evidence": "caller claim"},
                    }
                ]
            )
            self.wake.set()
        return {"accepted": True, "duplicate": not changed, "event_id": data["event_id"]}

    def assess(self, sid, data):
        with self.lock:
            s = self.sessions.get(sid)
        if not s:
            raise ValueError("Unknown session.")
        allowed = {
            "task_group",
            "tests_passed",
            "review_fixes",
            "duration_seconds",
            "notes",
            "model",
        }
        if not isinstance(data, dict) or set(data) - allowed:
            raise ValueError("Unsupported assessment fields.")
        a = dict(data)
        for field in ("task_group", "notes", "model"):
            if field in a and (not isinstance(a[field], str) or len(a[field]) > 3000):
                raise ValueError("Invalid " + field)
        if a.get("tests_passed") is not None and not isinstance(a["tests_passed"], bool):
            raise ValueError("tests_passed must be true, false or null.")
        for field in ("review_fixes", "duration_seconds"):
            if a.get(field) is not None and (
                isinstance(a[field], bool)
                or not isinstance(a[field], int)
                or not 0 <= a[field] <= 10**8
            ):
                raise ValueError(field + " must be a nonnegative integer or null.")
        a.update(
            recorded_at=now_ms(),
            evidence="owner-reported",
            model=a.get("model") or s["model"],
            provider=s["provider"],
        )
        self.store.assess(sid, a)
        self._publish_assessment(sid, a)
        self.wake.set()
        return a

    def _publish_assessment(self, sid, assessment):
        """Copy-on-write publish of one assessment.

        ``_facts`` is treated as immutable once published, so a concurrent
        analytics read never observes a half-updated fact. The (potentially
        large) fact is rebuilt outside the lock; the published structures are
        only replaced when the session object we derived from is still current.
        """
        for _ in range(8):
            with self.lock:
                current = self.sessions.get(sid)
            if current is None:
                return
            updated = {**current, "assessment": assessment}
            fact = build_fact(updated)
            with self.lock:
                if self.sessions.get(sid) is current:
                    self.sessions = {**self.sessions, sid: updated}
                    self._facts = tuple(fact if f["id"] == sid else f for f in self._facts)
                    self._facts_revision += 1
                    self._analytics_cache.clear()
                    return
        # A collector kept replacing the session mid-flight; the stored
        # assessment is still picked up by the next poll. Nothing to publish.

    def begin_scan(self, roots, depth):
        if self._closing or self._closed:
            raise LifecycleError("engine is shutting down")
        if (
            not isinstance(roots, list)
            or not roots
            or len(roots) > 20
            or any(not isinstance(x, str) for x in roots)
        ):
            raise ValueError("Provide 1–20 explicit scan roots.")
        if not isinstance(depth, int) or not 1 <= depth <= 10:
            raise ValueError("Scan depth must be 1–10.")
        with self.lock:
            if self.scan_result.get("running"):
                return self.scan_result
            self.scan_result = {"running": True, "items": [], "started": now_ms()}

        def work():
            try:
                result = scan_paths(roots, depth)
            except Exception as e:
                result = {"items": [], "errors": [redact(e)], "truncated": True}
            with self.lock:
                self.scan_result = {**result, "running": False, "finished": now_ms()}

        self._scan_thread = threading.Thread(target=work, daemon=True, name="bounded-discovery")
        self._scan_thread.start()
        return {"running": True}

    def adopt_scan(self, selected):
        if not isinstance(selected, list) or len(selected) > 100:
            raise ValueError("Select up to 100 discoveries.")
        with self.lock:
            available = {(i["kind"], i["path"]) for i in self.scan_result.get("items", [])}
        cfg = self.config()
        mapping = {
            "project": "projects",
            "database": "db_paths",
            "codex": "codex_homes",
            "router": "router_events",
        }
        for item in selected:
            pair = (item.get("kind"), item.get("path"))
            if pair not in available:
                raise ValueError("Selection was not returned by the last scan.")
            key = mapping[pair[0]]
            if pair[1] not in cfg[key]:
                cfg[key].append(pair[1])
        self.save_config(cfg)
        return {"added": len(selected)}

    def abort(self, sid, confirmation):
        if not self.config()["allow_abort"]:
            raise PermissionError("Abort is disabled. Enable it explicitly in Settings.")
        with self.lock:
            s = copy.deepcopy(self.sessions.get(sid))
        if not s or s["source"] != "opencode" or not s.get("_server"):
            raise ValueError(
                "Only a known OpenCode session on a connected live server can be interrupted."
            )
        if confirmation != s["native_id"]:
            raise ValueError("Type the exact native session ID to confirm.")
        base = s["_server"].rstrip("/")
        if base not in [u.rstrip("/") for u in self.config()["opencode_urls"]]:
            raise PermissionError("Server is no longer allowlisted.")
        response = local_json(
            base
            + "/session/"
            + quote(s["native_id"], safe="")
            + "/abort?"
            + urlencode({"directory": s["directory"]}),
            body={},
            headers=oc_headers(),
            timeout=5,
        )
        self.store.events(
            [
                {
                    "id": digest("abort", sid, now_ms()),
                    "ts": now_ms(),
                    "session_id": sid,
                    "kind": "intervention",
                    "source": "manual",
                    "project": s["directory"],
                    "text": "Owner requested OpenCode abort",
                    "detail": {"response": response},
                }
            ]
        )
        self.wake.set()
        return {"requested": True, "response": response}

    def close(self, timeout=5):
        """Deterministically release every resource this engine owns.

        Returns ``True`` only when the collector thread, the scanner thread and
        the HTTP server have all stopped and the observer DB is closed. If a
        worker does not stop in time, raises :class:`LifecycleError` and leaves
        the DB open rather than yanking it out from under a live thread.
        Simultaneous callers serialise on ``_close_lock``; the first performs
        the shutdown and the rest return the same success.
        """
        with self._close_lock:
            if self._closed:
                return True
            self._closing = True
            self.stop.set()
            self.wake.set()
            if not self._join_worker(self.thread, timeout):
                raise LifecycleError(
                    f"collector thread did not stop within {timeout}s; observer DB left open"
                )
            if not self._join_worker(getattr(self, "_scan_thread", None), timeout):
                raise LifecycleError(
                    f"scanner thread did not stop within {timeout}s; observer DB left open"
                )
            # Also serialise with a direct poll() not driven by self.thread, so a
            # late collector cycle cannot outlive the Store it reads from.
            if not self.poll_lock.acquire(timeout=timeout):
                raise LifecycleError(
                    f"a poll cycle did not stop within {timeout}s; observer DB left open"
                )
            self.poll_lock.release()
            server = getattr(self, "server", None)
            if server is not None:
                server.request_stop(timeout)
            self.store.close()
            self._closed = True
            return True

    @staticmethod
    def _join_worker(thread, timeout):
        if thread is None:
            return True
        if thread is threading.current_thread():
            if thread.is_alive():
                raise LifecycleError("cannot close the engine from its own live worker thread")
            return True
        thread.join(timeout)
        return not thread.is_alive()
