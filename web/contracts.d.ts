/*
 * Shared DTOs for the dashboard front-end.
 *
 * These ambient interfaces describe the JSON actually produced by the Python
 * observer (mission_control/server.py, engine.py, core.py, store.py) and
 * consumed by web/app.js. They are type-only: the build (scripts/build.mjs)
 * bundles web/app.js alone, so nothing here is shipped to the browser.
 *
 * Optional fields mirror payloads that only appear under some conditions
 * (e.g. an error string instead of coverage counts). Nullable metrics stay
 * explicitly `| null` so "unknown" is never confused with zero.
 */

/** Token counters. `total` may be provider-normalized, not a naive sum. */
interface UsageTotals {
  input: number;
  output: number;
  reasoning: number;
  cache_read: number;
  cache_write: number;
  total: number;
}

/** Owner-reported assessment stored per canonical session id. */
interface Assessment {
  task_group?: string;
  model?: string;
  provider?: string;
  tests_passed?: boolean | null;
  review_fixes?: number | null;
  duration_seconds?: number | null;
  notes?: string;
  recorded_at?: number;
  evidence?: string;
}

/** One recorded tool call (`core.tool_detail`). */
interface ToolCall {
  id: string;
  name: string;
  state: string;
  ts: number;
  command: string;
  input: string;
  output: string;
  exit_code: number | null;
  files: string[];
}

/** An agent definition file or OpenCode `/agent` entry. */
interface AgentDefinition {
  name: string;
  mode: string;
  model: unknown;
  description: string;
  source: string;
  directory: string;
  prompt?: string;
}

/** One row of `Engine.summary` / a `SNAP.sessions` item. */
interface SessionSummary {
  id: string;
  native_id: string;
  source: string;
  sources: string[];
  title: string;
  directory: string;
  project: string;
  parent_id: string;
  relationship: string;
  agent: string;
  model: string;
  provider: string;
  origin: string;
  origin_evidence: string;
  state: string;
  state_evidence: string;
  confidence: string;
  created: number;
  updated: number;
  observed: number;
  turn_started: number;
  usage: UsageTotals;
  usage_known: boolean;
  cost: number | null;
  messages: number;
  context_tokens: number | null;
  context_limit: number | null;
  errors: number;
  retry_count: number;
  warnings: string[];
  retry_message?: string;
  task_group?: string;
  commit_sha?: string;
  assessment?: Assessment | null;
  usage_events_dropped?: number;
  task_preview: string;
  last_tool: string;
  can_abort: boolean;
  children: string[];
  age_seconds: number | null;
}

/** Per-model rollup kept on a session (`make_session.model_usage`). */
interface ModelUsage {
  model: string;
  provider: string;
  usage: UsageTotals;
  cost: number | null;
  requests: number;
}

/** Full session payload from `GET /api/session` (`engine.detail`). */
interface SessionDetail {
  id: string;
  native_id: string;
  source: string;
  sources: string[];
  title: string;
  directory: string;
  project: string;
  parent_id: string;
  relationship: string;
  agent: string;
  model: string;
  provider: string;
  origin: string;
  origin_evidence: string;
  state: string;
  state_evidence: string;
  confidence: string;
  created: number;
  updated: number;
  observed: number;
  turn_started: number;
  usage: UsageTotals;
  usage_known: boolean;
  cost: number | null;
  messages: number;
  context_tokens: number | null;
  context_limit: number | null;
  errors: number;
  retry_count: number;
  warnings: string[];
  retry_message?: string;
  task_group?: string;
  commit_sha?: string;
  assessment?: Assessment | null;
  usage_events_dropped?: number;
  prompt: string;
  reported_task: string;
  tools: ToolCall[];
  files: string[];
  model_usage: Record<string, ModelUsage>;
  events: TimelineEvent[];
  timeline: TimelineEvent[];
  definition: AgentDefinition | null;
  children?: string[];
  age_seconds?: number | null;
}

/** A git commit summary (`sources.git_info`). */
interface GitCommit {
  sha: string;
  ts: number;
  subject: string;
}

/** Git context for a project; degrades to `{ error }` when unavailable. */
interface GitInfo {
  branch?: string;
  commits?: GitCommit[];
  error?: string;
}

/** A project row from the observer snapshot. */
interface ProjectSummary {
  id: string;
  path: string;
  name: string;
  sessions: number;
  active: number;
  reported_active: number;
  tokens: number;
  sources: string[];
  git: GitInfo;
  monitored: boolean;
}

/** Source health/coverage entry (`SNAP.sources`). */
interface SourceStatus {
  id: string;
  label: string;
  location?: string;
  kind?: string;
  checked?: number;
  ok?: boolean;
  error?: string;
  note?: string;
  loaded_sessions?: number;
  total_sessions?: number;
  parts_loaded?: number;
  truncated_sessions?: number;
  aggregate_truncated_sessions?: number;
  loaded_files?: number;
  truncated?: boolean;
  deadline_exceeded?: boolean;
  stale?: boolean;
  catching_up?: boolean;
  skipped_records?: number;
  directories_checked?: number;
  issues?: string[];
  loaded_events?: number;
  total_read?: number;
  health?: unknown;
  rejected_records?: unknown;
}

/** Derived alert (`derive_alerts`). `acknowledged` is added in the snapshot. */
interface AlertRecord {
  id: string;
  session_id: string;
  project: string;
  kind: string;
  severity: string;
  text: string;
  ts: number;
  acknowledged: boolean;
}

/** One router request from the separate ledger. */
interface RouterEvent {
  ts: number;
  model: string;
  provider: string;
  status: number | null;
  ok: boolean;
  usage: UsageTotals;
  duration_ms: number;
}

/** Router ledger after `Engine.view` folding. Never added to native totals. */
interface RouterLedger {
  source: string;
  requests: number;
  errors: number;
  unknown_status: number;
  tokens: number;
  recent: RouterEvent[];
  coverage?: unknown;
}

/** Structured completeness contract shared by overview, analytics, exports and MCP. */
interface CoverageBlock {
  scope: {
    kind: string;
    window_limit?: number;
    sessions_loaded?: number;
    sessions_in_range?: number;
    days?: number;
    project?: string;
    task_group?: string;
    source?: string;
  };
  metadata_complete: boolean | null;
  aggregates_complete: boolean | null;
  history_limited: boolean;
  breakdowns: { daily: string; model: string; file: string };
  breakdown_details: Record<string, number>;
  details_truncated: boolean;
  detail_events_evicted: number;
  catching_up: boolean;
  source_stale: boolean;
  read_blocked: boolean;
  discovered_sessions: number | null;
  processed_sessions: number | null;
  last_successful_read_at: number | null;
}

/** Runtime i18n hook exposed for browser tests. */
interface Window {
  mcMissingKeys: () => string[];
}

/** One MCP bridge client declaration. */
interface McpClient {
  name: string;
  identity?: string;
  last_seen?: number;
  calls: number;
}

/** `GET /api/overview` root payload. */
interface Snapshot {
  version: string;
  generated_at: number;
  refreshing: boolean;
  sessions: SessionSummary[];
  projects: ProjectSummary[];
  sources: SourceStatus[];
  alerts: AlertRecord[];
  definitions: AgentDefinition[];
  router: RouterLedger[];
  coverage: CoverageBlock;
  privacy: { show_prompts: boolean; reporting: boolean; abort: boolean };
  mcp_clients?: McpClient[];
  port?: number;
  counts?: Record<string, number>;
  verified_active?: number;
  unverified_active?: number;
  tokens?: number;
}

/** One persisted observer/state event. */
interface TimelineEvent {
  id: string;
  session_id: string;
  ts: number;
  source: string;
  kind: string;
  text: string;
  project: string;
  detail?: unknown;
  seq?: number;
}

/** `GET /api/timeline` payload. */
interface TimelineResponse {
  events: TimelineEvent[];
  next_before: number | null;
}

/** One calendar day of usage. */
interface UsageDay {
  date: string;
  input: number;
  output: number;
  reasoning: number;
  cache_read: number;
  cache_write: number;
  total: number;
}

/** One model rollup from `compute_analytics`. */
interface AnalyticsModel {
  id: string;
  model: string;
  provider: string;
  usage: UsageTotals;
  sessions: number;
  requests: number;
  recorded_cost: number | null;
  estimated_cost: number | null;
  priced_tokens: number;
  errors: number;
  retries: number;
  assessed_tasks: number;
  test_samples: number;
  test_pass_rate: number | null;
  avg_review_fixes: number | null;
  avg_duration_seconds: number | null;
  tokens_per_session: number | null;
}

/** `GET /api/analytics` payload. */
interface Analytics {
  tokens: number;
  sessions: number;
  models: AnalyticsModel[];
  days: UsageDay[];
  activity: UsageDay[];
  files: Array<{ path: string; estimated_tokens: number }>;
  methodology: string;
  cost_note: string;
  days_filter: number;
  task_group: string;
  project: string;
  usage_events_dropped: number;
  coverage: CoverageBlock;
}

/** Validated observer configuration (`core.default_config`). */
interface DashboardConfig {
  db_paths: string[];
  codex_homes: string[];
  router_events: string[];
  opencode_urls: string[];
  projects: string[];
  excluded_projects: string[];
  scan_roots: string[];
  poll_seconds: number;
  history_limit: number;
  codex_file_limit: number;
  history_days: number;
  show_prompts: boolean;
  enable_reporting: boolean;
  allow_abort: boolean;
  expected_models: Record<string, string>;
  allowed_paths: Record<string, string[]>;
  stall_seconds: number;
  token_budget: number;
  public_origin: string;
  oauth_redirect_uris: string[];
  pricing: Record<string, Record<string, number>>;
  git_enabled: boolean;
}

/** One discovered path from `/api/scan`. */
interface ScanItem {
  kind: string;
  path: string;
  name: string;
}

/** Bounded discovery state (`engine.begin_scan` / `scan_paths`). */
interface ScanState {
  running: boolean;
  items: ScanItem[];
  scanned_dirs?: number;
  truncated?: boolean;
  errors?: string[];
  seconds?: number;
  started?: number;
  finished?: number;
}

/** `GET /api/integrations` payload. Secret values are NOT included here. */
interface IntegrationInfo {
  stdio_toml: string;
  http_toml: string;
  mcp_url: string;
  remote_url: string;
  secrets: string[];
  state_directory: string;
  reporting: boolean;
  tools: Array<{ name: string }>;
  instructions: string;
}

/** `POST /api/reveal` payload: fetched only after an explicit owner click. */
interface RevealResult {
  name: string;
  value: string;
  warning: string;
}
