import {
  applyStatic,
  formatDateTime,
  formatMoney,
  formatNumber,
  getLanguage,
  missingKeys,
  nextLanguage,
  readPreference,
  setLanguage,
  t,
  writePreference,
} from './i18n/core.js';
/** @type {Record<string, string>} */
const UI_ICONS = {
  overview:
    '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  projects:
    '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M3 11h18"/>',
  agents:
    '<rect x="4" y="6" width="16" height="14" rx="4"/><path d="M12 3v3M1 11v4m22-4v4M8 15h8"/><path d="M8 10h.01M16 10h.01" stroke-width="3"/>',
  graph:
    '<rect x="9" y="2" width="6" height="5" rx="1"/><rect x="2" y="17" width="6" height="5" rx="1"/><rect x="16" y="17" width="6" height="5" rx="1"/><path d="M12 7v5M5 17v-5h14v5"/>',
  timeline:
    '<path d="M8 4h13M8 12h13M8 20h13"/><circle cx="3" cy="4" r="1"/><circle cx="3" cy="12" r="1"/><circle cx="3" cy="20" r="1"/>',
  analytics: '<path d="M4 3v18h18M9 16v-5m5 5V7m5 9V3"/>',
  alerts: '<path d="M12 3 2.5 20h19Z" stroke-linejoin="round"/><path d="M12 9v5m0 3h.01"/>',
  integrations: '<path d="m8 3 5 5m3-3 5 5M12 3l9 9M3 21l6-6M7 9l8 8m-7-9-3 3a5 5 0 0 0 7 7l3-3"/>',
  settings:
    '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="2" fill="var(--side)"/><circle cx="16" cy="12" r="2" fill="var(--side)"/><circle cx="8" cy="18" r="2" fill="var(--side)"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
  bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
  refresh:
    '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.5 5.5a8 8 0 0 1 13 5M4.5 13.5a8 8 0 0 0 13 5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  shield: '<path d="m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6Z"/><path d="m8 12 3 3 5-6"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  logout: '<path d="M9 3H4v18h5m4-4 5-5-5-5M8 12h13"/>',
  pulse: '<path d="M2 12h5l3-8 4 16 3-8h5"/>',
  stack: '<path d="m12 3 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 16l9 5 9-5"/>',
};
/** @param {string} name @returns {string} */
function uiIcon(name) {
  const shape = UI_ICONS[name] || UI_ICONS.overview;
  return (
    '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    shape +
    '</svg>'
  );
}

/** A required DOM node. Missing markup is a descriptive runtime error.
 * @param {string} id
 * @returns {HTMLElement}
 */
function $(id) {
  const node = document.getElementById(id);
  if (!node) throw new Error('Missing dashboard element: ' + id);
  return node;
}
/** @param {string} id @returns {HTMLInputElement} */
function $input(id) {
  const node = $(id);
  if (!(node instanceof HTMLInputElement)) throw new Error('Expected input: ' + id);
  return node;
}
/** @param {string} id @returns {HTMLSelectElement} */
function $select(id) {
  const node = $(id);
  if (!(node instanceof HTMLSelectElement)) throw new Error('Expected select: ' + id);
  return node;
}
/** @param {string} id @returns {HTMLTextAreaElement} */
function $textarea(id) {
  const node = $(id);
  if (!(node instanceof HTMLTextAreaElement)) throw new Error('Expected textarea: ' + id);
  return node;
}
/** @param {string} id @returns {HTMLButtonElement} */
function $button(id) {
  const node = $(id);
  if (!(node instanceof HTMLButtonElement)) throw new Error('Expected button: ' + id);
  return node;
}
/** @param {string} id @returns {HTMLDialogElement} */
function $dialog(id) {
  const node = $(id);
  if (!(node instanceof HTMLDialogElement)) throw new Error('Expected dialog: ' + id);
  return node;
}
/** @param {string} id @returns {SVGGraphicsElement} */
function $svg(id) {
  const node = document.querySelector('#' + CSS.escape(id));
  if (!(node instanceof SVGGraphicsElement)) throw new Error('Expected SVG graphics node: ' + id);
  return node;
}
/** @param {string} selector @returns {HTMLElement[]} */
function htmlAll(selector) {
  return Array.from(document.querySelectorAll(selector)).filter(
    (node) => node instanceof HTMLElement,
  );
}

/** @type {Record<string, string>} */
const HTML_ESCAPES = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
};
/** @param {unknown} x @returns {string} */
const esc = (x) => String(x ?? '').replace(/[&<>"']/g, (c) => HTML_ESCAPES[c] ?? c);
/** @param {number | null | undefined} n @returns {string} */
const fmt = (n) => (n == null ? '—' : formatNumber(n, { maximumFractionDigits: 0 }));
/** @param {number | null | undefined} n @returns {string} */
const compact = (n) =>
  n == null
    ? '—'
    : n >= 1e6
      ? (n / 1e6).toFixed(2) + 'M'
      : n >= 1e3
        ? (n / 1e3).toFixed(1) + 'K'
        : fmt(n);
/** @param {number | null | undefined} ts @returns {string} */
const date = (ts) => (ts ? formatDateTime(ts) : t('time.none'));
/** @param {number | null | undefined} ts @returns {string} */
const ago = (ts) => {
  if (!ts) return t('time.unknown');
  const s = Math.max(0, (Date.now() - ts) / 1000);
  return s < 60
    ? t('time.ago.seconds', { n: Math.floor(s) })
    : s < 3600
      ? t('time.ago.minutes', { n: Math.floor(s / 60) })
      : s < 86400
        ? t('time.ago.hours', { n: Math.floor(s / 3600) })
        : t('time.ago.days', { n: Math.floor(s / 86400) });
};
/** @param {number | null | undefined} s @returns {string} */
const duration = (s) =>
  s == null
    ? '—'
    : s >= 3600
      ? t('duration.hours', { n: (s / 3600).toFixed(1) })
      : s >= 60
        ? t('duration.minutes', { n: Math.round(s / 60) })
        : t('duration.seconds', { n: Math.round(s) });
/** @param {number | null | undefined} n @returns {string} */
const money = (n) => (n == null ? '—' : formatMoney(n));
/** @param {SessionSummary} s @returns {boolean} */
const active = (s) => ['running', 'tool', 'thinking'].includes(s.state);
/** @param {unknown} x @param {string} [cls] @returns {string} */
const badge = (x, cls = '') => '<span class="badge ' + esc(cls || x) + '">' + esc(x) + '</span>';
/** @param {unknown} s @returns {string} */
const source = (s) => '<span class="source ' + esc(s) + '">' + esc(s) + '</span>';
/** @param {unknown} s @param {number} [n] @returns {string} */
const truncate = (s, n = 55) =>
  String(s || '').length > n ? String(s).slice(0, n - 1) + '…' : String(s || '');
/** @type {['input', 'output', 'reasoning', 'cache_read', 'cache_write']} */
const keys = ['input', 'output', 'reasoning', 'cache_read', 'cache_write'];
/** @type {Record<string, string>} */
const colors = {
  input: 'var(--accent)',
  output: 'var(--green)',
  reasoning: 'var(--purple)',
  cache_read: 'var(--amber)',
  cache_write: 'var(--amber)',
};
/** @type {ScanState | null} */
let scanSnapshot = null;
let token = sessionStorage.getItem('mc-owner') || '';
let view = localStorage.getItem('mc-view') || 'overview';
/** @type {Snapshot | null} */
let SNAP = null;
/** @type {DashboardConfig | null} */
let CONFIG = null;
/** @type {SessionDetail | null} */
let DETAIL = null;
let loading = false;
let renderSeq = 0;
/** @type {TimelineEvent[]} */
let timelineData = [];
/** @type {number | null} */
let timelineCursor = null;
let timelineQuery = '';
let graphPose = { x: 20, y: 28, k: 1 };
let graphDragged = false;
let days = 0;
let taskGroup = '';
let cardsMode = localStorage.getItem('mc-cards') === '1';
/** @type {Set<string> | null} */
let knownAlerts = null;
/** @type {IntegrationInfo | null} */
let INTEGRATION = null;
let inspectSeq = 0;
/** View titles are rebuilt from the active dictionaries, so a language switch
 * re-renders every label consistently.
 * @returns {Record<string, [string, string]>}
 */
function titles() {
  return {
    overview: [t('view.overview.title'), t('view.overview.subtitle')],
    projects: [t('view.projects.title'), t('view.projects.subtitle')],
    agents: [t('view.agents.title'), t('view.agents.subtitle')],
    graph: [t('view.graph.title'), t('view.graph.subtitle')],
    timeline: [t('view.timeline.title'), t('view.timeline.subtitle')],
    analytics: [t('view.analytics.title'), t('view.analytics.subtitle')],
    alerts: [t('view.alerts.title'), t('view.alerts.subtitle')],
    integrations: [t('view.integrations.title'), t('view.integrations.subtitle')],
    settings: [t('view.settings.title'), t('view.settings.subtitle')],
  };
}
if (!titles()[view]) view = 'overview';
/** Reads an owner token from the #access fragment, stores it and clears the
 * fragment so the secret never stays in the address bar. Runs on first load
 * and again on hashchange, because navigating to the same document with a new
 * fragment does not re-execute this script.
 * @returns {boolean} true when a fragment token was consumed.
 */
function consumeAccessFragment() {
  const access = new URLSearchParams(location.hash.slice(1)).get('access');
  if (!access) return false;
  token = access;
  sessionStorage.setItem('mc-owner', token);
  history.replaceState(null, '', location.pathname + location.search);
  return true;
}
consumeAccessFragment();
window.addEventListener('hashchange', () => {
  if (consumeAccessFragment()) void load(true);
});
let theme = localStorage.getItem('mc-theme') || 'dark';
document.documentElement.dataset.theme = theme;
setLanguage(readPreference('mc-lang', 'en'));
applyStatic(document);
window.mcMissingKeys = missingKeys;
/** Keeps the topbar language chip in sync with the active language.
 * @returns {void}
 */
function syncLang() {
  $('lang-code').textContent = getLanguage().toUpperCase();
}
syncLang();
/** @param {string} text @param {boolean} [error] @returns {void} */
function toast(text, error = false) {
  const el = document.createElement('div');
  el.className = 'toast' + (error ? ' error' : '');
  el.textContent = text;
  $('toasts').append(el);
  setTimeout(() => el.remove(), 5500);
}
/** Extracts a human message from an unknown thrown value or server error body.
 * @param {unknown} error
 * @returns {string}
 */
function errorText(error) {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  if (error && typeof error === 'object' && 'error' in error) {
    const value = /** @type {{ error?: unknown }} */ (error).error;
    if (typeof value === 'string') return value;
  }
  return '';
}
/** @param {string} path
 * @param {unknown} [body]
 * @returns {Promise<unknown>}
 */
async function api(path, body) {
  /** @type {RequestInit} */
  const opts = { headers: { Authorization: 'Bearer ' + token } };
  if (body !== undefined) {
    opts.method = 'POST';
    opts.headers = { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (res.status === 401) {
    $('login').hidden = false;
    throw new Error(t('error.login_required'));
  }
  /** @type {unknown} */
  let data;
  try {
    data = await res.json();
  } catch (cause) {
    throw new Error(t('error.bad_response'), { cause });
  }
  if (!res.ok) throw new Error(errorText(data) || 'HTTP ' + res.status);
  return data;
}
/** @returns {SessionSummary[]} */
function selectedSessions() {
  if (!SNAP) return [];
  const q = $input('search').value.toLowerCase(),
    p = $select('project-filter').value,
    src = $select('source-filter').value,
    st = $select('state-filter').value;
  return SNAP.sessions.filter(
    (s) =>
      (!p || s.directory === p) &&
      (!src || s.source === src) &&
      (!q ||
        [s.title, s.model, s.agent, s.directory, s.task_preview, s.id]
          .join(' ')
          .toLowerCase()
          .includes(q)) &&
      (!st ||
        (st === 'active'
          ? active(s)
          : st === 'verified'
            ? active(s) && s.confidence === 'verified'
            : s.state === st)),
  );
}
/** @returns {void} */
function head() {
  const title = [t('view.' + view + '.title'), t('view.' + view + '.subtitle')];
  const searchWrap = $input('search').closest('.search-wrap');
  if (searchWrap instanceof HTMLElement) searchWrap.hidden = view === 'analytics';
  $input('search').hidden = view === 'analytics';
  $select('state-filter').hidden = view === 'analytics';
  $('heading').textContent = title[0];
  $('subtitle').textContent = title[1];
  $('crumb').textContent = title[0];
  $('filters').hidden = ['integrations', 'settings', 'timeline', 'alerts'].includes(view);
  $('eyebrow').textContent = t('view.' + view + '.eyebrow');
  htmlAll('.nav [data-view]').forEach((button) => {
    const current = button.dataset.view === view;
    button.classList.toggle('active', current);
    if (current) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  $('viewtag').textContent =
    view === 'graph'
      ? t('viewtag.relations')
      : view === 'integrations'
        ? t('viewtag.mcp')
        : t('viewtag.observer');
  document.title = title[0] + ' · ' + t('brand.name');
}

/** @param {string} v @returns {Promise<void>} */
async function go(v) {
  if (!titles()[v]) return;
  view = v;
  localStorage.setItem('mc-view', v);
  head();
  $('view').innerHTML = '<div class="loading">' + esc(t('loading.view')) + '</div>';
  await render(true);
}
/** @param {string} title @param {string} text @param {string} [button] @returns {string} */
function empty(title, text, button = '') {
  return (
    '<div class="empty"><h3>' + esc(title) + '</h3><p>' + esc(text) + '</p>' + button + '</div>'
  );
}
/** Renders the structured completeness contract from the backend:
 * availability, metadata, aggregates, breakdowns, details, freshness,
 * progress and errors. Complete aggregates with a limited detail window are
 * informative, not a warning.
 * @returns {string}
 */
function coverage() {
  if (!SNAP) return '';
  const c = SNAP.coverage;
  if (!c || Array.isArray(c)) return '';
  const breakdowns = c.breakdowns || {};
  /** @type {Array<'daily' | 'model' | 'file'>} */
  const breakdownKeys = ['daily', 'model', 'file'];
  const names = breakdownKeys
    .filter((k) => breakdowns[k] === 'partial')
    .map((k) => t('breakdown.' + (k === 'file' ? 'files' : k)));
  const lines = [];
  let degraded = false;
  if (c.aggregates_complete === false) {
    degraded = true;
    lines.push(t(c.catching_up ? 'coverage.catching_up' : 'coverage.aggregates_partial'));
  } else if (c.aggregates_complete === true && c.details_truncated) {
    lines.push(t('coverage.complete_limited'));
  }
  if (c.metadata_complete === false) {
    const limit = c.scope && typeof c.scope.window_limit === 'number' ? c.scope.window_limit : null;
    lines.push(t('coverage.history_limited', { limit: limit === null ? '—' : fmt(limit) }));
  }
  if (names.length) lines.push(t('coverage.breakdowns_partial', { names: names.join(', ') }));
  if (c.detail_events_evicted) lines.push(t('coverage.evicted', { n: c.detail_events_evicted }));
  if (c.source_stale) {
    degraded = true;
    lines.push(t('coverage.source_stale'));
  }
  if (c.read_blocked) {
    degraded = true;
    lines.push(t('coverage.read_blocked'));
  }
  if (!lines.length) return '';
  lines.push(t('coverage.hint'));
  return (
    '<div class="notice coverage-note' +
    (degraded ? ' coverage-degraded' : '') +
    '" role="status">' +
    esc(lines.join(' ')) +
    '</div>'
  );
}
/** @param {SessionSummary[]} sessions @returns {string} */
function statsCards(sessions) {
  if (!SNAP) return '';
  const verified = sessions.filter((s) => active(s) && s.confidence === 'verified').length;
  const unverified = sessions.filter((s) => active(s) && s.confidence !== 'verified').length;
  const projects = new Set(sessions.map((s) => s.directory).filter(Boolean)).size;
  const alerts = SNAP.alerts.filter(
    (a) => !a.acknowledged && (!a.session_id || sessions.some((s) => s.id === a.session_id)),
  ).length;
  const tokens = sessions
    .filter((s) => s.source !== 'reported')
    .reduce((n, s) => n + s.usage.total, 0);
  /** @type {Array<[string, string, string | number, string, string, string]>} */
  const cards = [
    [
      'green',
      t('kpi.active.label'),
      verified,
      t('kpi.active.note', { n: unverified }),
      'pulse',
      'agents',
    ],
    [
      '',
      t('kpi.projects.label'),
      projects,
      t('kpi.projects.note', { n: sessions.length }),
      'projects',
      'projects',
    ],
    ['', t('kpi.tokens.label'), compact(tokens), t('kpi.tokens.note'), 'analytics', 'analytics'],
    [alerts ? 'red' : '', t('kpi.alerts.label'), alerts, t('kpi.alerts.note'), 'alerts', 'alerts'],
  ];
  return (
    '<div class="kpis">' +
    cards
      .map(
        ([cls, label, value, note, glyph, target]) =>
          '<button type="button" class="kpi ' +
          cls +
          '" data-view="' +
          target +
          '">' +
          '<div class="kpi-top"><span class="label">' +
          esc(label) +
          '</span><span class="kpi-icon">' +
          uiIcon(glyph) +
          '</span></div>' +
          '<div class="value">' +
          esc(value) +
          '</div><p class="desc">' +
          esc(note) +
          '</p></button>',
      )
      .join('') +
    '</div>'
  );
}

/** @param {ProjectSummary} project @returns {string} */
function campus(project) {
  return (
    '<article class="panel campus" tabindex="0" role="button" data-project="' +
    esc(project.path) +
    '" aria-label="' +
    esc(t('campus.open.aria', { name: project.name })) +
    '">' +
    '<div class="campus-head"><div class="projectglyph">' +
    esc(project.name.slice(0, 2).toUpperCase()) +
    '</div>' +
    '<div><h3>' +
    esc(project.name) +
    '</h3><div class="path" title="' +
    esc(project.path) +
    '">' +
    esc(project.path) +
    '</div></div>' +
    '<span class="campus-arrow">' +
    uiIcon('arrow') +
    '</span></div>' +
    '<div class="statrow"><div><strong>' +
    fmt(project.active) +
    '</strong><small>' +
    esc(t('campus.active.api')) +
    '</small></div>' +
    '<div><strong>' +
    compact(project.tokens) +
    '</strong><small>' +
    esc(t('campus.tokens')) +
    '</small></div>' +
    '<div><strong>' +
    fmt(project.sessions) +
    '</strong><small>' +
    esc(t('campus.sessions')) +
    '</small></div></div>' +
    '<div class="campus-bottom"><div class="chips">' +
    project.sources.map((s) => source(s)).join('') +
    '</div>' +
    '<span class="branch-label" title="' +
    esc(project.git?.branch || t('git.unavailable')) +
    '">' +
    uiIcon('graph') +
    esc(project.git?.branch || t('git.none')) +
    '</span></div></article>'
  );
}

/** @param {SessionSummary[]} rows @param {number} [max] @returns {string} */
function sessionTable(rows, max = 200) {
  if (!rows.length) return empty(t('table.empty.title'), t('table.empty.text'));
  return (
    '<div class="tablewrap"><table class="table"><thead><tr>' +
    '<th>' +
    esc(t('table.agent')) +
    '</th><th>' +
    esc(t('table.state')) +
    '</th><th>' +
    esc(t('table.model')) +
    '</th><th>' +
    esc(t('table.project')) +
    '</th><th class="right">' +
    esc(t('table.tokens')) +
    '</th><th>' +
    esc(t('table.activity')) +
    '</th>' +
    '</tr></thead><tbody>' +
    rows
      .slice(0, max)
      .map(
        (s) =>
          '<tr data-inspect="' +
          esc(s.id) +
          '" tabindex="0" role="button" aria-label="' +
          esc(t('table.inspect.aria', { agent: s.agent })) +
          '">' +
          '<td><div class="agent-name"><span class="agent-avatar">' +
          uiIcon('agents') +
          '</span><div>' +
          '<div class="name">' +
          esc(s.agent) +
          '</div><div class="under" title="' +
          esc(s.title) +
          '">' +
          esc(s.title) +
          '</div></div></div></td>' +
          '<td><div class="chips">' +
          badge(s.state) +
          badge(s.confidence) +
          '</div><div class="under">' +
          source(s.source) +
          '</div></td>' +
          '<td><div class="num" title="' +
          esc(s.model) +
          '">' +
          esc(truncate(s.model, 35)) +
          '</div><div class="under">' +
          esc(s.origin === 'unknown' ? t('origin.unknown') : s.origin) +
          '</div></td>' +
          '<td><div class="name">' +
          esc(s.project) +
          '</div><div class="under">' +
          esc(s.last_tool || s.relationship) +
          '</div></td>' +
          '<td class="right num">' +
          (s.usage_known ? compact(s.usage.total) : '—') +
          '</td>' +
          '<td class="num">' +
          esc(ago(s.updated)) +
          '</td></tr>',
      )
      .join('') +
    '</tbody></table></div>' +
    (rows.length > max
      ? '<p class="note table-coverage">' +
        esc(t('table.coverage', { max, total: rows.length })) +
        '</p>'
      : '')
  );
}

/** @param {SessionSummary} s @returns {string} */
function agentCard(s) {
  return (
    '<article class="panel agentcard" data-inspect="' +
    esc(s.id) +
    '" tabindex="0" role="button"><div class="splithead">' +
    source(s.source) +
    badge(s.state) +
    '</div><h3>' +
    esc(s.agent) +
    '</h3><div class="task">' +
    esc(s.task_preview || s.title) +
    '</div><div class="chips">' +
    badge(truncate(s.model, 40)) +
    badge(s.confidence) +
    '</div><div class="cardfoot"><span>' +
    esc(s.project) +
    '</span><span>' +
    (s.usage_known ? compact(s.usage.total) : '—') +
    ' ' +
    esc(t('card.tokens_suffix')) +
    '</span></div></article>'
  );
}
/** @param {TimelineEvent[]} events @param {number} [max] @returns {string} */
function eventList(events, max = 20) {
  if (!events.length) return '<p class="note">' + esc(t('events.none')) + '</p>';
  return (
    '<div class="activitylist">' +
    events
      .slice(0, max)
      .map(
        (e) =>
          '<div class="event ' +
          esc(e.kind) +
          '"><span class="evdot"></span><div><button ' +
          (e.session_id ? 'data-inspect="' + esc(e.session_id) + '"' : 'disabled') +
          ' class="evtext">' +
          esc(truncate(e.text, 180)) +
          '</button><div class="evmeta">' +
          esc(e.source) +
          ' · ' +
          esc(e.kind) +
          (e.project ? ' · ' + esc(e.project.replace(/\\/g, '/').split('/').pop()) : '') +
          '</div></div><time title="' +
          esc(date(e.ts)) +
          '">' +
          esc(ago(e.ts)) +
          '</time></div>',
      )
      .join('') +
    '</div>'
  );
}
/** @returns {string} */
function sourcesMini() {
  if (!SNAP) return '';
  return SNAP.sources
    .map(
      (s) =>
        '<div class="statusline"><span class="dot ' +
        (s.ok ? '' : 'off') +
        '"></span><span class="label">' +
        esc(s.label) +
        '</span><span class="small">' +
        esc(s.ok ? t('source.connected') : s.error ? t('source.error') : t('source.missing')) +
        '</span></div>',
    )
    .join('');
}
/** @param {boolean} [force] @returns {Promise<void>} */
async function render(force = false) {
  if (!SNAP) return;
  const seq = ++renderSeq;
  const rows = selectedSessions();
  const box = $('view');
  if (view === 'overview') {
    const ps = SNAP.projects.filter(
      (p) => !$select('project-filter').value || p.path === $select('project-filter').value,
    );
    box.innerHTML =
      statsCards(rows) +
      coverage() +
      '<div class="sectionhead"><h2>' +
      esc(t('overview.workspaces')) +
      ' <span>' +
      ps.length +
      '</span></h2><button data-view="projects">' +
      esc(t('overview.all_projects')) +
      '</button></div>' +
      (ps.length
        ? '<div class="grid3">' + ps.slice(0, 6).map(campus).join('') + '</div>'
        : empty(
            t('overview.connect.title'),
            t('overview.connect.text'),
            '<button class="primary" data-view="integrations">' +
              esc(t('overview.connect.button')) +
              '</button>',
          )) +
      '<div class="sectionhead"><h2>' +
      esc(t('overview.recent')) +
      '</h2><button data-view="agents">' +
      esc(t('overview.inspector')) +
      '</button></div><div class="panel">' +
      sessionTable(rows, 8) +
      '</div><div class="grid2" style="margin-top:18px"><div class="panel"><div class="paneltitle"><h2>' +
      esc(t('overview.events')) +
      '</h2><button class="smallbtn" data-view="timeline">' +
      esc(t('overview.open')) +
      '</button></div><div id="overview-events"><p class="note">' +
      esc(t('loading.history')) +
      '</p></div></div><div class="panel"><div class="paneltitle"><h2>' +
      esc(t('overview.health')) +
      '</h2><span class="eyebrow">' +
      esc(t('overview.health.eyebrow')) +
      '</span></div>' +
      sourcesMini() +
      '<div class="notice info">' +
      esc(t('overview.health.note')) +
      '</div></div></div>';
    try {
      const data = /** @type {TimelineResponse} */ (await api('/api/timeline?limit=12'));
      if (seq === renderSeq && $('overview-events'))
        $('overview-events').innerHTML = eventList(
          data.events.sort((a, b) => b.ts - a.ts),
          7,
        );
    } catch (e) {
      if (seq === renderSeq && $('overview-events'))
        $('overview-events').textContent = errorText(e);
    }
  } else if (view === 'projects') {
    const chosen = $select('project-filter').value;
    const ps = SNAP.projects.filter((p) => !chosen || p.path === chosen);
    box.innerHTML =
      coverage() +
      (ps.length
        ? '<div class="grid3">' + ps.map(campus).join('') + '</div>'
        : empty(
            t('projects.empty.title'),
            t('projects.empty.text'),
            '<button data-view="integrations">' + esc(t('projects.empty.button')) + '</button>',
          )) +
      ps
        .map(
          (p) =>
            '<div class="sectionhead"><h2>' +
            esc(p.name) +
            ' <span>' +
            esc(p.git?.branch || t('git.unavailable')) +
            '</span></h2><button data-project="' +
            esc(p.path) +
            '">' +
            esc(t('projects.sessions.button')) +
            '</button></div><div class="panel">' +
            (p.git?.commits?.length
              ? '<div class="activitylist">' +
                p.git.commits
                  .slice(0, 5)
                  .map(
                    (c) =>
                      '<div class="event"><span class="evdot"></span><div><div class="evtext">' +
                      esc(c.subject) +
                      '</div><div class="evmeta">' +
                      esc(c.sha.slice(0, 12)) +
                      '</div></div><time>' +
                      esc(date(c.ts)) +
                      '</time></div>',
                  )
                  .join('') +
                '</div>'
              : '<p class="note">' + esc(p.git?.error || t('projects.git.error')) + '</p>') +
            '<p class="note" style="margin-top:14px">' +
            esc(t('projects.commit.note')) +
            '</p></div>',
        )
        .join('');
  } else if (view === 'agents') {
    box.innerHTML =
      statsCards(rows) +
      coverage() +
      '<div class="sectionhead"><h2>' +
      esc(t('agents.runs')) +
      ' <span>' +
      rows.length +
      '</span></h2><div class="view-controls"><button data-mode="table" class="smallbtn ' +
      (!cardsMode ? 'active' : '') +
      '">' +
      esc(t('agents.mode.table')) +
      '</button><button data-mode="cards" class="smallbtn ' +
      (cardsMode ? 'active' : '') +
      '">' +
      esc(t('agents.mode.cards')) +
      '</button></div></div>' +
      (cardsMode
        ? '<div class="agentcards">' + rows.slice(0, 200).map(agentCard).join('') + '</div>'
        : '<div class="panel">' + sessionTable(rows) + '</div>');
  } else if (view === 'graph') {
    if (force || !$svg('graph-svg')) {
      box.innerHTML =
        '<div class="notice info">' +
        esc(t('graph.notice')) +
        '</div><div class="graphwrap" id="graph-wrap"><div class="graph-toolbar"><button data-zoom="in" aria-label="' +
        esc(t('graph.zoom.in')) +
        '">+</button><button data-zoom="out" aria-label="' +
        esc(t('graph.zoom.out')) +
        '">−</button><button data-zoom="fit">' +
        esc(t('graph.zoom.fit')) +
        '</button></div><svg id="graph-svg" aria-label="' +
        esc(t('graph.svg.aria')) +
        '" role="img"><g id="graph-layer"></g></svg><div class="graphlegend"><span>' +
        esc(t('graph.legend.confirmed')) +
        '</span><span>' +
        esc(t('graph.legend.fork')) +
        '</span><span id="graph-count"></span></div></div>';
      bindGraph();
    }
    if (!graphDragged) drawGraph(rows);
  } else if (view === 'timeline') {
    if (force || !$('timeline-events')) {
      box.innerHTML =
        '<div class="panel"><div class="formrow"><label>' +
        esc(t('timeline.search.label')) +
        '<input id="timeline-query" placeholder="' +
        esc(t('timeline.search.placeholder')) +
        '" value="' +
        esc(timelineQuery) +
        '"></label><button id="timeline-search">' +
        esc(t('timeline.search.button')) +
        '</button></div><div class="notice info">' +
        esc(t('timeline.notice')) +
        '</div><div id="timeline-events"></div><button id="timeline-more" class="smallbtn" style="margin-top:16px">' +
        esc(t('timeline.more')) +
        '</button></div>';
      await loadTimeline(false);
    }
  } else if (view === 'analytics') {
    if (force || !$('analytics-results')) {
      box.innerHTML =
        '<div class="panel"><div class="formrow"><label>' +
        esc(t('analytics.period')) +
        '<select id="days"><option value="0">' +
        esc(t('analytics.period.loaded')) +
        '</option><option value="7">' +
        esc(t('analytics.period.7')) +
        '</option><option value="30">' +
        esc(t('analytics.period.30')) +
        '</option><option value="90">' +
        esc(t('analytics.period.90')) +
        '</option><option value="365">' +
        esc(t('analytics.period.365')) +
        '</option></select></label><label>' +
        esc(t('analytics.group.label')) +
        '<input id="task-group" placeholder="' +
        esc(t('analytics.group.placeholder')) +
        '" value="' +
        esc(taskGroup) +
        '"></label><button id="analytics-apply">' +
        esc(t('analytics.apply')) +
        '</button><button data-export="json">JSON</button><button data-export="csv">CSV</button></div><p class="note" style="margin-top:12px">' +
        esc(t('analytics.note')) +
        '</p></div><div id="analytics-results"><div class="loading">' +
        esc(t('loading.analytics')) +
        '</div></div>';
      $select('days').value = String(days);
    }
    await loadAnalytics(seq);
  } else if (view === 'alerts') {
    const alerts = SNAP.alerts;
    box.innerHTML =
      '<div class="sectionhead"><h2>' +
      esc(t('alerts.heading')) +
      ' <span>' +
      esc(t('alerts.new', { n: alerts.filter((a) => !a.acknowledged).length })) +
      '</span></h2><button id="ack-all">' +
      esc(t('alerts.ack_all')) +
      '</button></div>' +
      (alerts.length
        ? alerts
            .map(
              (a) =>
                '<article class="alert ' +
                esc(a.severity) +
                (a.acknowledged ? ' ack' : '') +
                '"><div class="body"><small>' +
                esc(a.kind) +
                '</small><h3>' +
                esc(
                  a.severity === 'danger'
                    ? t('alerts.severity.danger')
                    : t('alerts.severity.default'),
                ) +
                '</h3><p>' +
                esc(a.text) +
                '</p></div><div class="actions">' +
                (a.session_id
                  ? '<button class="smallbtn" data-inspect="' +
                    esc(a.session_id) +
                    '">' +
                    esc(t('alerts.inspect')) +
                    '</button>'
                  : '') +
                (!a.acknowledged
                  ? '<button class="smallbtn" data-ack="' +
                    esc(a.id) +
                    '">' +
                    esc(t('alerts.ack')) +
                    '</button>'
                  : badge(t('alerts.acked'))) +
                '</div></article>',
            )
            .join('')
        : empty(t('alerts.empty.title'), t('alerts.empty.text')));
  } else if (view === 'integrations') {
    if (force) await integrations(seq);
  } else if (view === 'settings') {
    if (force) await settings(seq);
  }
}
/** @param {UsageDay[]} data @returns {string} */
function chart(data) {
  if (!data.length) return '<p class="note">' + esc(t('analytics.chart.none')) + '</p>';
  const rows = data.slice(-120),
    w = 960,
    h = 210,
    p = 25,
    m = Math.max(...rows.map((d) => d.total), 1),
    bw = (w - 2 * p) / rows.length;
  let out =
    '<svg class="chart" viewBox="0 0 ' +
    w +
    ' ' +
    h +
    '" role="img" aria-label="' +
    esc(t('analytics.chart.aria')) +
    '">';
  for (let i = 0; i < 3; i++) {
    let y = p + (i * (h - p * 2)) / 2;
    out +=
      '<line class="gridline" x1="' + p + '" x2="' + (w - p) + '" y1="' + y + '" y2="' + y + '"/>';
  }
  rows.forEach((d, i) => {
    let acc = 0;
    keys.forEach((k) => {
      let v = d[k] || 0;
      if (v <= 0) return;
      let barh = (v / m) * (h - 2 * p);
      out +=
        '<rect x="' +
        (p + i * bw + 1) +
        '" y="' +
        (h - p - ((acc + v) / m) * (h - 2 * p)) +
        '" width="' +
        Math.max(1, bw - 3) +
        '" height="' +
        barh +
        '" fill="' +
        colors[k] +
        '"><title>' +
        esc(d.date + ' · ' + k + ': ' + fmt(v)) +
        '</title></rect>';
      acc += v;
    });
    if (i % Math.max(1, Math.ceil(rows.length / 8)) === 0)
      out +=
        '<text x="' + (p + i * bw) + '" y="' + (h - 5) + '">' + esc(d.date.slice(5)) + '</text>';
  });
  return (
    out +
    '</svg><div class="legend"><span><i style="background:var(--accent)"></i>' +
    esc(t('legend.input')) +
    '</span><span><i style="background:var(--green)"></i>' +
    esc(t('legend.output')) +
    '</span><span><i style="background:var(--purple)"></i>' +
    esc(t('legend.reasoning')) +
    '</span><span><i style="background:var(--amber)"></i>' +
    esc(t('legend.cache')) +
    '</span></div>' +
    (data.length > 120 ? '<p class="note">' + esc(t('analytics.chart.window')) + '</p>' : '')
  );
}
/** @returns {URLSearchParams} */
function analyticsQuery() {
  return new URLSearchParams({
    days: String(days),
    project: $select('project-filter').value,
    source: $select('source-filter').value,
    task_group: taskGroup,
  });
}
/** @param {number} [seq] @returns {Promise<void>} */
async function loadAnalytics(seq = renderSeq) {
  try {
    const a = /** @type {Analytics} */ (await api('/api/analytics?' + analyticsQuery()));
    if (seq !== renderSeq || !$('analytics-results')) return;
    const max = Math.max(...a.activity.map((d) => d.total), 1);
    $('analytics-results').innerHTML =
      coverage() +
      '<div class="notice info">' +
      esc(a.methodology) +
      '</div><div class="sectionhead"><h2>' +
      esc(t('analytics.usage_time')) +
      ' <span>' +
      esc(
        t('analytics.usage_window', {
          tokens: compact(a.tokens),
          sessions: t('sessions_short', { n: a.sessions }),
        }),
      ) +
      '</span></h2></div><div class="panel">' +
      chart(a.days) +
      '</div><div class="sectionhead"><h2>' +
      esc(t('analytics.models')) +
      '</h2><span class="micro">' +
      esc(t('analytics.owner_declarations')) +
      '</span></div><div class="panel tablewrap"><table class="table"><thead><tr><th>' +
      esc(t('analytics.table.model')) +
      '</th><th class="right">' +
      esc(t('analytics.table.tokens')) +
      '</th><th class="right">' +
      esc(t('analytics.table.sessions')) +
      '</th><th class="right">' +
      esc(t('analytics.table.avg')) +
      '</th><th class="right">' +
      esc(t('analytics.table.tests')) +
      '</th><th class="right">' +
      esc(t('analytics.table.fixes')) +
      '</th><th class="right">' +
      esc(t('analytics.table.duration')) +
      '</th><th class="right">' +
      esc(t('analytics.table.recorded')) +
      '</th><th class="right">' +
      esc(t('analytics.table.estimate')) +
      '</th></tr></thead><tbody>' +
      a.models
        .map(
          (m) =>
            '<tr><td><div class="name">' +
            esc(m.model) +
            '</div><div class="under">' +
            esc(m.provider) +
            ' · ' +
            esc(t('analytics.assessments', { n: m.assessed_tasks })) +
            '</div></td><td class="right num">' +
            compact(m.usage.total) +
            '</td><td class="right num">' +
            fmt(m.sessions) +
            '</td><td class="right num">' +
            compact(m.tokens_per_session) +
            '</td><td class="right num">' +
            (m.test_pass_rate == null
              ? '—'
              : Math.round(m.test_pass_rate * 100) + '% / ' + m.test_samples) +
            '</td><td class="right num">' +
            (m.avg_review_fixes == null ? '—' : m.avg_review_fixes.toFixed(1)) +
            '</td><td class="right num">' +
            duration(m.avg_duration_seconds) +
            '</td><td class="right num">' +
            money(m.recorded_cost) +
            '</td><td class="right num">' +
            money(m.estimated_cost) +
            '</td></tr>',
        )
        .join('') +
      '</tbody></table>' +
      (a.models.length ? '' : empty(t('analytics.empty.title'), t('analytics.empty.text'))) +
      '<p class="note" style="margin-top:15px">' +
      esc(a.cost_note) +
      ' ' +
      esc(t('analytics.cost_suffix')) +
      '</p></div><div class="grid2" style="margin-top:18px"><div class="panel"><h2>' +
      esc(t('analytics.activity')) +
      '</h2><div class="heatmap">' +
      a.activity
        .map(
          (d) =>
            '<div class="heatcell l' +
            (d.total ? Math.max(1, Math.ceil((d.total / max) * 4)) : 0) +
            '" title="' +
            esc(t('analytics.heat.tooltip', { date: d.date, n: fmt(d.total) })) +
            '"></div>',
        )
        .join('') +
      '</div><p class="note">' +
      esc(t('analytics.heat.note')) +
      '</p></div><div class="panel"><h2>' +
      esc(t('analytics.files')) +
      '</h2>' +
      a.files
        .slice(0, 10)
        .map(
          (f) =>
            '<div class="statusline"><span class="label mono" style="font-size:10px;overflow-wrap:anywhere">' +
            esc(f.path) +
            '</span><span class="num">' +
            compact(f.estimated_tokens) +
            '</span></div>',
        )
        .join('') +
      '<p class="note" style="margin-top:12px">' +
      esc(t('analytics.files.note')) +
      '</p></div></div>' +
      routerPanel();
  } catch (e) {
    if ($('analytics-results'))
      $('analytics-results').innerHTML =
        '<div class="notice danger">' + esc(errorText(e)) + '</div>';
  }
}
/** @returns {string} */
function routerPanel() {
  if (!SNAP) return '';
  if (!SNAP.router.length) return '';
  return (
    '<div class="sectionhead"><h2>' +
    esc(t('router.heading')) +
    '</h2></div><div class="notice">' +
    esc(t('router.notice')) +
    '</div>' +
    SNAP.router
      .map(
        (r) =>
          '<div class="panel" style="margin-bottom:12px"><p class="note">' +
          esc(r.source) +
          '</p><div class="chips" style="margin:12px 0">' +
          badge(t('router.requests', { n: r.requests })) +
          badge(t('router.tokens', { n: compact(r.tokens) })) +
          badge(t('router.errors', { n: r.errors })) +
          badge(t('router.unknown', { n: r.unknown_status })) +
          '</div><div class="tablewrap"><table class="table"><thead><tr><th>' +
          esc(t('router.table.time')) +
          '</th><th>' +
          esc(t('router.table.model')) +
          '</th><th>' +
          esc(t('router.table.status')) +
          '</th><th class="right">' +
          esc(t('router.table.tokens')) +
          '</th></tr></thead><tbody>' +
          r.recent
            .slice(0, 12)
            .map(
              (e) =>
                '<tr><td class="num">' +
                esc(date(e.ts)) +
                '</td><td>' +
                esc(e.model) +
                '</td><td>' +
                badge(e.status == null ? 'unknown' : String(e.status), e.ok ? 'done' : 'error') +
                '</td><td class="num right">' +
                compact(e.usage.total) +
                '</td></tr>',
            )
            .join('') +
          '</tbody></table></div></div>',
      )
      .join('')
  );
}
/** @param {boolean} [more] @returns {Promise<void>} */
async function loadTimeline(more = false) {
  try {
    const q = new URLSearchParams({ limit: '100', query: timelineQuery });
    if (more && timelineCursor) q.set('before', String(timelineCursor));
    const d = /** @type {TimelineResponse} */ (await api('/api/timeline?' + q));
    if (!more) timelineData = [];
    const ids = new Set(timelineData.map((x) => x.id));
    d.events.forEach((e) => {
      if (!ids.has(e.id)) timelineData.push(e);
    });
    timelineCursor = d.next_before;
    if ($('timeline-events'))
      $('timeline-events').innerHTML = eventList(
        [...timelineData].sort((a, b) => b.ts - a.ts),
        2000,
      );
    if ($button('timeline-more')) $button('timeline-more').hidden = !timelineCursor;
  } catch (e) {
    toast(errorText(e), true);
  }
}
function graphTransform() {
  const g = $svg('graph-layer');
  if (g)
    g.setAttribute('transform', `translate(${graphPose.x},${graphPose.y}) scale(${graphPose.k})`);
}
/** @param {SessionSummary[]} rows @returns {void} */
function drawGraph(rows) {
  const svg = $svg('graph-svg'),
    layer = $svg('graph-layer');
  if (!svg || !layer) return;
  const shown = rows.slice(0, 120),
    /** @type {Map<string, SessionSummary>} */
    map = new Map(shown.map((s) => [s.id, s])),
    /** @type {Map<string, number>} */
    depths = new Map();
  /** @param {string} id @param {Set<string>} [seen] @returns {number} */
  function depth(id, seen = new Set()) {
    if (depths.has(id)) return depths.get(id) || 0;
    if (seen.has(id) || seen.size > 10) return 0;
    seen.add(id);
    const s = map.get(id);
    const d = s && map.has(s.parent_id) ? Math.min(8, 1 + depth(s.parent_id, seen)) : 0;
    depths.set(id, d);
    return d;
  }
  shown.forEach((s) => depth(s.id));
  /** @type {Map<number, number>} */
  const cols = new Map(),
    /** @type {Map<string, {x: number, y: number}>} */
    pos = new Map();
  shown.forEach((s) => {
    const d = depths.get(s.id) || 0;
    const n = cols.get(d) || 0;
    cols.set(d, n + 1);
    pos.set(s.id, { x: d * 255, y: n * 125 });
  });
  let edges = '',
    nodes = '';
  shown.forEach((s) => {
    const p = pos.get(s.id);
    if (!p) return;
    const pp = pos.get(s.parent_id);
    if (pp) {
      edges +=
        '<path class="edge ' +
        (s.relationship === 'delegated'
          ? active(s) && s.confidence === 'verified'
            ? 'flow'
            : ''
          : 'uncertain') +
        '" d="M' +
        (pp.x + 205) +
        ',' +
        (pp.y + 45) +
        ' C' +
        (pp.x + 230) +
        ',' +
        (pp.y + 45) +
        ' ' +
        (p.x - 25) +
        ',' +
        (p.y + 45) +
        ' ' +
        p.x +
        ',' +
        (p.y + 45) +
        '"><title>' +
        esc(s.relationship) +
        '</title></path>';
    }
    nodes +=
      '<g class="gnode ' +
      (s.confidence === 'verified' ? '' : 'unverified') +
      '" transform="translate(' +
      p.x +
      ',' +
      p.y +
      ')" tabindex="0" role="button" aria-label="' +
      esc(s.agent + ' ' + s.state) +
      '" data-inspect="' +
      esc(s.id) +
      '"><rect width="205" height="96"/><text class="sub" x="14" y="20">' +
      esc(s.source.toUpperCase() + ' · ' + s.confidence) +
      '</text><text class="title" x="14" y="42">' +
      esc(truncate(s.agent, 26)) +
      '</text><text class="sub" x="14" y="61">' +
      esc(truncate(s.model, 30)) +
      '</text><text class="state" x="14" y="82">' +
      esc(s.state.toUpperCase()) +
      '</text><text class="sub" x="105" y="82">' +
      esc(truncate(s.project, 15)) +
      '</text><title>' +
      esc(
        s.title +
          '\n' +
          s.state_evidence +
          (s.parent_id && !map.has(s.parent_id)
            ? '\n' + t('graph.parent_outside', { id: s.parent_id })
            : ''),
      ) +
      '</title></g>';
  });
  layer.innerHTML = edges + nodes;
  $('graph-count').textContent = t('graph.count', { shown: shown.length, total: rows.length });
  graphTransform();
  if (!rows.length) {
    layer.innerHTML =
      '<text x="30" y="50" fill="var(--muted)" font-size="14">' + esc(t('graph.empty')) + '</text>';
  }
}
/** @returns {void} */
function fitGraph() {
  const layer = $svg('graph-layer'),
    svg = $svg('graph-svg');
  if (!layer || !svg) return;
  const b = layer.getBBox();
  graphPose.k = Math.min(
    1.2,
    (svg.clientWidth - 60) / Math.max(b.width, 1),
    (svg.clientHeight - 70) / Math.max(b.height, 1),
  );
  graphPose.x = 30 - b.x * graphPose.k;
  graphPose.y = 35 - b.y * graphPose.k;
  graphTransform();
}
/** @returns {void} */
function bindGraph() {
  const svg = $svg('graph-svg');
  /** @type {{x: number, y: number, px: number, py: number} | null} */
  let drag = null;
  svg.addEventListener('pointerdown', (e) => {
    if (e.target instanceof Element && e.target.closest('[data-inspect]')) return;
    drag = { x: e.clientX, y: e.clientY, px: graphPose.x, py: graphPose.y };
    graphDragged = true;
    svg.setPointerCapture(e.pointerId);
    svg.classList.add('dragging');
  });
  svg.addEventListener('pointermove', (e) => {
    if (!drag) return;
    graphPose.x = drag.px + e.clientX - drag.x;
    graphPose.y = drag.py + e.clientY - drag.y;
    graphTransform();
  });
  const stop = () => {
    drag = null;
    graphDragged = false;
    svg.classList.remove('dragging');
  };
  svg.addEventListener('pointerup', stop);
  svg.addEventListener('pointercancel', stop);
  svg.addEventListener(
    'wheel',
    (e) => {
      e.preventDefault();
      const rect = svg.getBoundingClientRect(),
        x = e.clientX - rect.left,
        y = e.clientY - rect.top,
        old = graphPose.k,
        k = Math.max(0.08, Math.min(3, old * (e.deltaY < 0 ? 1.1 : 0.9)));
      graphPose.x = x - ((x - graphPose.x) * k) / old;
      graphPose.y = y - ((y - graphPose.y) * k) / old;
      graphPose.k = k;
      graphTransform();
    },
    { passive: false },
  );
}
/** @param {string} id @returns {Promise<void>} */
async function inspect(id) {
  const seq = ++inspectSeq;
  $('inspector-title').textContent = t('loading.inspect');
  $('inspector-body').innerHTML =
    '<div class="loading">' + esc(t('loading.inspect_body')) + '</div>';
  if (!$dialog('inspector').open) $dialog('inspector').showModal();
  try {
    const s = /** @type {SessionDetail} */ (
      await api('/api/session?' + new URLSearchParams({ id }))
    );
    if (seq !== inspectSeq) return;
    DETAIL = s;
    $('inspector-title').textContent = s.title || s.id;
    const u = s.usage,
      a = s.assessment || {};
    /** @param {keyof UsageTotals} k @returns {number} */
    const pct = (k) => (u.total ? Math.min(100, (u[k] / u.total) * 100) : 0);
    $('inspector-body').innerHTML =
      '<div class="chips">' +
      source(s.source) +
      badge(s.state) +
      badge(s.confidence) +
      '</div><div class="notice info">' +
      esc(s.state_evidence) +
      '</div><dl class="details">' +
      [
        [t('inspect.labels.agent'), s.agent],
        [t('inspect.labels.model'), s.model],
        [t('inspect.labels.project'), s.directory || t('inspect.value.unset')],
        [t('inspect.labels.session'), s.id],
        [t('inspect.labels.parent'), s.parent_id || t('inspect.value.none')],
        [t('inspect.labels.relationship'), s.relationship],
        [t('inspect.labels.origin'), s.origin + ' · ' + s.origin_evidence],
        [t('inspect.labels.created'), date(s.created)],
        [t('inspect.labels.updated'), date(s.updated)],
        [
          t('inspect.labels.context'),
          s.context_tokens == null
            ? t('inspect.value.unknown')
            : fmt(s.context_tokens) + ' / ' + fmt(s.context_limit),
        ],
      ]
        .map(([k, v]) => '<dt>' + esc(k) + '</dt><dd>' + esc(v) + '</dd>')
        .join('') +
      '</dl><div class="btnrow"><button class="smallbtn" id="copy-session">' +
      esc(t('inspect.copy_id')) +
      '</button><button class="smallbtn" data-project="' +
      esc(s.directory) +
      '">' +
      esc(t('inspect.project_sessions')) +
      '</button><button class="smallbtn" id="reload-session">' +
      esc(t('inspect.reload')) +
      '</button>' +
      (SNAP?.privacy.abort && s.source === 'opencode'
        ? '<button class="smallbtn dangerbtn" id="abort-session">' +
          esc(t('inspect.abort')) +
          '</button>'
        : '') +
      '</div><h3>' +
      esc(t('inspect.usage')) +
      '</h3><div class="panel"><div class="splithead"><h2>' +
      esc(t('inspect.usage.tokens', { n: compact(u.total) })) +
      '</h2><span class="micro">' +
      (s.usage_known ? esc(t('inspect.usage.source')) : esc(t('inspect.usage.none'))) +
      '</span></div><div class="meter" style="margin:16px 0">' +
      keys.map((k) => '<span class="' + k + '" style="width:' + pct(k) + '%"></span>').join('') +
      '</div>' +
      keys
        .map(
          (k) =>
            '<div class="statusline"><span class="label">' +
            esc(k) +
            '</span><span class="num">' +
            fmt(u[k]) +
            '</span></div>',
        )
        .join('') +
      '<p class="note" style="margin-top:12px">' +
      esc(t('inspect.usage.note')) +
      '</p></div>' +
      (s.warnings?.length
        ? '<div class="notice">' + s.warnings.map(esc).join('<br>') + '</div>'
        : '') +
      '<h3>' +
      esc(t('inspect.task')) +
      '</h3><pre class="codebox">' +
      esc(s.reported_task || s.prompt || t('inspect.task.empty')) +
      '</pre>' +
      (s.definition
        ? '<details class="toolrow"><summary>' +
          esc(t('inspect.definition', { source: s.definition.source })) +
          '</summary><pre class="codebox">' +
          esc(s.definition.prompt || s.definition.description) +
          '</pre></details>'
        : '') +
      '<h3>' +
      esc(t('inspect.tools')) +
      '</h3>' +
      (s.tools.length
        ? s.tools
            .slice()
            .reverse()
            .slice(0, 25)
            .map(
              (t) =>
                '<details class="toolrow"><summary><span>' +
                esc(t.name) +
                '</span>' +
                badge(t.state) +
                '<span class="stamp">' +
                esc(ago(t.ts)) +
                '</span></summary><pre class="codebox">' +
                esc(t.command || t.input) +
                '</pre>' +
                (t.output ? '<pre class="codebox">' + esc(t.output) + '</pre>' : '') +
                '</details>',
            )
            .join('')
        : '<p class="note">' + esc(t('inspect.tools.none')) + '</p>') +
      '<h3>' +
      esc(t('inspect.files')) +
      '</h3><pre class="codebox">' +
      esc(s.files.join('\n') || t('inspect.files.none')) +
      '</pre><h3>' +
      esc(t('inspect.assessment')) +
      '</h3><div class="panel formgrid"><label>' +
      esc(t('inspect.assessment.group')) +
      '<input id="assessment-group" value="' +
      esc(a.task_group || s.task_group || '') +
      '" placeholder="' +
      esc(t('inspect.assessment.group.placeholder')) +
      '"></label><label>' +
      esc(t('inspect.assessment.model')) +
      '<input id="assessment-model" value="' +
      esc(a.model || s.model) +
      '"></label><div class="formgrid two"><label>' +
      esc(t('inspect.assessment.tests')) +
      '<select id="assessment-tests"><option value="">' +
      esc(t('inspect.assessment.tests.none')) +
      '</option><option value="true">' +
      esc(t('inspect.assessment.tests.pass')) +
      '</option><option value="false">' +
      esc(t('inspect.assessment.tests.fail')) +
      '</option></select></label><label>' +
      esc(t('inspect.assessment.fixes')) +
      '<input id="assessment-fixes" type="number" min="0" step="1" value="' +
      esc(a.review_fixes ?? '') +
      '" placeholder="' +
      esc(t('inspect.assessment.fixes.placeholder')) +
      '"></label></div><label>' +
      esc(t('inspect.assessment.duration')) +
      '<input id="assessment-duration" type="number" min="0" step="1" value="' +
      esc(a.duration_seconds ?? '') +
      '" placeholder="' +
      esc(t('inspect.assessment.duration.placeholder')) +
      '"></label><label>' +
      esc(t('inspect.assessment.notes')) +
      '<textarea id="assessment-notes" rows="3">' +
      esc(a.notes || '') +
      '</textarea></label><button class="primary" id="save-assessment">' +
      esc(t('inspect.assessment.save')) +
      '</button><p class="note">' +
      esc(t('inspect.assessment.note')) +
      '</p></div><h3>' +
      esc(t('inspect.history')) +
      '</h3>' +
      eventList(
        (s.timeline || []).sort((a, b) => b.ts - a.ts),
        25,
      );
    $select('assessment-tests').value = a.tests_passed == null ? '' : String(a.tests_passed);
  } catch (e) {
    if (seq !== inspectSeq) return;
    $('inspector-title').textContent = t('inspect.error.title');
    $('inspector-body').innerHTML = '<div class="notice danger">' + esc(errorText(e)) + '</div>';
  }
}
/** @param {number} seq @returns {Promise<void>} */
async function integrations(seq) {
  try {
    const [cfg, info] = /** @type {[DashboardConfig, IntegrationInfo]} */ (
      await Promise.all([api('/api/config'), api('/api/integrations')])
    );
    if (seq !== renderSeq) return;
    if (!SNAP) return;
    CONFIG = cfg;
    INTEGRATION = info;
    $('view').innerHTML =
      '<div class="sourcegrid">' +
      SNAP.sources
        .map(
          (s) =>
            '<div class="panel sourcecard"><div class="splithead"><span class="label">' +
            esc(s.label) +
            '</span><span class="dot ' +
            (s.ok ? '' : 'off') +
            '"></span></div><div class="path">' +
            esc(s.location || t('int.sources.none')) +
            '</div><p>' +
            esc(
              s.error || s.note || (s.ok ? t('int.sources.active') : t('int.sources.disconnected')),
            ) +
            '</p><div class="chips" style="margin-top:10px">' +
            (s.loaded_sessions != null
              ? badge(
                  t('int.sources.sessions', {
                    loaded: fmt(s.loaded_sessions),
                    total: fmt(s.total_sessions),
                  }),
                )
              : '') +
            (s.loaded_files != null
              ? badge(t('int.sources.logs', { n: fmt(s.loaded_files) }))
              : '') +
            (s.truncated ? badge(t('int.sources.truncated'), 'waiting') : '') +
            (s.skipped_records
              ? badge(t('int.sources.skipped', { n: fmt(s.skipped_records) }), 'waiting')
              : '') +
            '</div></div>',
        )
        .join('') +
      '</div><div class="sectionhead"><h2>' +
      esc(t('int.sources.heading')) +
      '</h2><span class="micro">' +
      esc(t('int.sources.micro')) +
      '</span></div><div class="panel"><div class="formgrid"><label>' +
      esc(t('int.roots.label')) +
      '<textarea id="scan-roots" rows="2">' +
      esc(cfg.scan_roots.join('\n')) +
      '</textarea></label><div class="formrow"><label>' +
      esc(t('int.depth.label')) +
      '<select id="scan-depth"><option>3</option><option selected>5</option><option>8</option><option>10</option></select></label><button id="scan-start" class="primary">' +
      esc(t('int.scan.button')) +
      '</button></div><p class="note">' +
      esc(t('int.scan.note')) +
      '</p><div id="scan-status"></div><div id="scan-results" class="scanner-results"></div><button id="scan-adopt" hidden>' +
      esc(t('int.adopt.button')) +
      '</button></div></div><div class="sectionhead"><h2>' +
      esc(t('int.oc.heading')) +
      '</h2></div><div class="panel"><div class="formrow"><label>' +
      esc(t('int.oc.url.label')) +
      '<input id="oc-url" placeholder="http://127.0.0.1:4096"></label><button id="oc-add">' +
      esc(t('int.oc.add')) +
      '</button></div><p class="note" style="margin-top:12px">' +
      esc(t('int.oc.note')) +
      '</p><pre class="codebox">' +
      esc(cfg.opencode_urls.join('\n')) +
      '</pre></div><div class="sectionhead"><h2>' +
      esc(t('int.mcp.heading')) +
      '</h2><span class="viewtag">' +
      esc(t('int.mcp.tools', { n: info.tools.length })) +
      '</span></div><div class="grid2"><div class="panel"><h2>' +
      esc(t('int.codex.title')) +
      '</h2><p class="note">' +
      esc(t('int.codex.note')) +
      '</p><pre class="codebox" id="stdio-config">' +
      esc(info.stdio_toml) +
      '</pre><button class="smallbtn" data-copy="stdio-config">' +
      esc(t('int.codex.copy')) +
      '</button><details class="secrets"><summary>' +
      esc(t('int.http.summary')) +
      '</summary><pre class="codebox" id="http-config">' +
      esc(info.http_toml) +
      '</pre><p class="note">' +
      esc(t('int.http.note')) +
      '</p><input readonly type="password" value="' +
      esc('') +
      '" id="mcp-token" aria-label="' +
      esc(t('int.mcp.token.aria')) +
      '"><button class="smallbtn" data-copy="mcp-token">' +
      esc(t('int.mcp.copy')) +
      '</button></details></div><div class="panel"><h2>' +
      esc(t('int.chatgpt.title')) +
      '</h2><div class="mcpstep"><span class="n">1</span><p>' +
      esc(t('int.step1', { port: fmt(SNAP.port || 8765) })) +
      '</p></div><div class="mcpstep"><span class="n">2</span><p>' +
      esc(t('int.step2')) +
      '</p></div><div class="formgrid"><label>' +
      esc(t('int.origin.label')) +
      '<input id="public-origin" placeholder="' +
      esc(t('int.origin.placeholder')) +
      '" value="' +
      esc(cfg.public_origin) +
      '"></label><label>' +
      esc(t('int.callbacks.label')) +
      '<textarea id="oauth-callbacks" rows="2">' +
      esc(cfg.oauth_redirect_uris.join('\n')) +
      '</textarea></label><button id="save-remote">' +
      esc(t('int.remote.save')) +
      '</button></div><div class="mcpstep"><span class="n">3</span><p>' +
      t('int.step3.html', { url: esc(info.remote_url || 'https://your-host.example/mcp') }) +
      '</p></div><details class="secrets"><summary>' +
      esc(t('int.pairing.summary')) +
      '</summary><p class="note">' +
      esc(t('int.pairing.note')) +
      '</p><input type="password" readonly value="' +
      esc('') +
      '" id="pairing-key" aria-label="' +
      esc(t('int.pairing.aria')) +
      '"><button class="smallbtn" data-copy="pairing-key">' +
      esc(t('int.pairing.copy')) +
      '</button></details><button class="smallbtn dangerbtn" id="revoke-oauth">' +
      esc(t('int.revoke')) +
      '</button></div></div><div class="notice">' +
      esc(t('int.notice')) +
      '</div><div class="panel"><h2>' +
      esc(t('int.reporting.title')) +
      '</h2><label class="togglelabel"><input id="reporting-toggle" type="checkbox" ' +
      (cfg.enable_reporting ? 'checked' : '') +
      '> ' +
      esc(t('int.reporting.toggle')) +
      '</label><pre class="codebox" id="report-example">' +
      esc(
        JSON.stringify(
          {
            event_id: t('int.reporting.example.event_id'),
            source: 'chatgpt',
            session_id: 'opencode:ses_TUTAJ_PRAWDZIWE_ID',
            task: t('int.reporting.example.task'),
            task_group: 'dashboard-ui-round-1',
            state: 'running',
          },
          null,
          2,
        ),
      ) +
      '</pre><p class="note">' +
      esc(t('int.reporting.note')) +
      '</p></div><div class="sectionhead"><h2>' +
      esc(t('int.clients.heading')) +
      '</h2></div><div class="panel">' +
      (SNAP.mcp_clients?.length
        ? SNAP.mcp_clients
            .map(
              (c) =>
                '<div class="statusline"><span class="label">' +
                esc(c.name) +
                '</span><span class="num">' +
                esc(t('int.clients.calls', { n: fmt(c.calls) })) +
                '</span><span class="small">' +
                esc(ago(c.last_seen)) +
                '</span></div>',
            )
            .join('')
        : '<p class="note">' + esc(t('int.clients.none')) + '</p>') +
      '</div><div class="sectionhead"><h2>' +
      esc(t('int.definitions.heading')) +
      ' <span>' +
      SNAP.definitions.length +
      '</span></h2></div><div class="panel">' +
      (SNAP.definitions.length
        ? SNAP.definitions
            .slice(0, 100)
            .map(
              (d) =>
                '<div class="defcard"><h3>' +
                esc(d.name) +
                ' ' +
                badge(d.mode) +
                '</h3><p>' +
                esc(d.description) +
                '</p><div class="micro">' +
                esc(typeof d.model === 'string' ? d.model : JSON.stringify(d.model)) +
                ' · ' +
                esc(d.source) +
                ' · ' +
                esc(d.directory) +
                '</div></div>',
            )
            .join('')
        : '<p class="note">' + esc(t('int.definitions.none')) + '</p>') +
      '</div><details class="panel" style="margin-top:18px"><summary>' +
      esc(t('int.instructions.summary')) +
      '</summary><pre class="codebox">' +
      esc(info.instructions) +
      '</pre></details>';
    await scanProgress();
  } catch (e) {
    if (seq === renderSeq)
      $('view').innerHTML = '<div class="notice danger">' + esc(errorText(e)) + '</div>';
  }
}
/** @param {number} seq @returns {Promise<void>} */
async function settings(seq) {
  try {
    CONFIG = /** @type {DashboardConfig} */ (await api('/api/config'));
    if (seq !== renderSeq) return;
    $('view').innerHTML =
      '<div class="grid2"><div class="panel"><h2>' +
      esc(t('set.config.title')) +
      '</h2><p class="note">' +
      esc(t('set.config.note')) +
      '</p><textarea id="config-editor" class="codeedit" spellcheck="false" aria-label="' +
      esc(t('set.config.aria')) +
      '">' +
      esc(JSON.stringify(CONFIG, null, 2)) +
      '</textarea><div class="btnrow"><button class="primary" id="config-save">' +
      esc(t('set.save')) +
      '</button><button id="config-reload">' +
      esc(t('set.reload')) +
      '</button></div><div id="config-status" class="note"></div></div><div class="panel"><h2>' +
      esc(t('set.rules.title')) +
      '</h2><dl class="details"><dt>show_prompts</dt><dd>' +
      esc(t('set.rule.show_prompts')) +
      '</dd><dt>enable_reporting</dt><dd>' +
      esc(t('set.rule.enable_reporting')) +
      '</dd><dt>allow_abort</dt><dd>' +
      esc(t('set.rule.allow_abort')) +
      '</dd><dt>expected_models</dt><dd>' +
      esc(t('set.rule.expected_models')) +
      '</dd><dt>allowed_paths</dt><dd>' +
      esc(t('set.rule.allowed_paths')) +
      '</dd><dt>stall_seconds</dt><dd>' +
      esc(t('set.rule.stall_seconds')) +
      '</dd><dt>token_budget</dt><dd>' +
      esc(t('set.rule.token_budget')) +
      '</dd><dt>history_limit</dt><dd>' +
      esc(t('set.rule.history_limit')) +
      '</dd><dt>codex_file_limit</dt><dd>' +
      esc(t('set.rule.codex_file_limit')) +
      '</dd><dt>history_days</dt><dd>' +
      esc(t('set.rule.history_days')) +
      '</dd></dl><div class="notice">' +
      esc(t('set.notice')) +
      '</div><p class="note">' +
      esc(t('set.files.note')) +
      '</p><div class="sectionhead"><h2>' +
      esc(t('set.stop.title')) +
      '</h2></div><p class="note">' +
      esc(t('set.stop.note')) +
      '</p><button class="dangerbtn" id="stop-observer">' +
      esc(t('set.stop.button')) +
      '</button></div></div>';
  } catch (e) {
    if (seq === renderSeq)
      $('view').innerHTML = '<div class="notice danger">' + esc(errorText(e)) + '</div>';
  }
}
/** @returns {Promise<void>} */
async function scanProgress() {
  if (view !== 'integrations' || !$('scan-status')) return;
  try {
    const s = /** @type {ScanState} */ (await api('/api/scan'));
    scanSnapshot = s;
    $button('scan-start').disabled = s.running;
    $('scan-status').textContent = s.running
      ? t('scan.running')
      : s.scanned_dirs != null
        ? t('scan.status', {
            dirs: t('scan.folders', { n: fmt(s.scanned_dirs) }),
            items: t('scan.results', { n: fmt(s.items.length) }),
          }) + (s.truncated ? t('scan.limit') : '')
        : '';
    if (!s.running) {
      $('scan-results').innerHTML =
        (s.items || [])
          .map(
            (i, n) =>
              '<label class="discovery"><input type="checkbox" data-scan-index="' +
              n +
              '" checked><span>' +
              badge(i.kind) +
              ' <b>' +
              esc(i.name) +
              '</b><br><code>' +
              esc(i.path) +
              '</code></span></label>',
          )
          .join('') +
        (s.errors?.length ? '<p class="note">' + s.errors.map(esc).join('<br>') + '</p>' : '');
      $button('scan-adopt').hidden = !s.items?.length;
    } else setTimeout(scanProgress, 1300);
  } catch (e) {
    if ($('scan-status')) $('scan-status').textContent = errorText(e);
  }
}
/** @param {string} id @returns {Promise<void>} */
async function copyText(id) {
  const el = $(id);
  if (!el) return;
  const text =
    el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement
      ? el.value
      : el.textContent || '';
  try {
    await navigator.clipboard.writeText(text);
    toast(t('copy.done'));
  } catch (_) {
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) el.select();
    toast(t('copy.unavailable'), true);
  }
}
/** @param {boolean} [force] @returns {Promise<void>} */
async function load(force = false) {
  if (loading || !token) {
    if (!token) $('login').hidden = false;
    return;
  }
  loading = true;
  $('loadingbar').classList.add('on');
  try {
    const snap = /** @type {Snapshot} */ (await api('/api/overview'));
    SNAP = snap;
    $('login').hidden = true;
    $('login-error').textContent = '';
    const fresh = snap.generated_at && Date.now() - snap.generated_at < 45000;
    $('connection').textContent = snap.generated_at
      ? fresh
        ? t('conn.read', { ago: ago(snap.generated_at) })
        : t('conn.stale', { ago: ago(snap.generated_at) })
      : t('conn.first');
    $('status-dot').className = 'dot ' + (fresh ? 'pulse' : 'off');
    $('side-dot').className = 'dot ' + (fresh ? '' : 'off');
    $('side-state').textContent = fresh ? t('side.running') : t('side.waiting');
    $('nav-projects').textContent = String(snap.projects.length);
    $('nav-agents').textContent = String(snap.sessions.length);
    $('nav-agents').title = t('nav.agents.title');
    $('nav-alerts').textContent = String(snap.alerts.filter((a) => !a.acknowledged).length);
    const select = $select('project-filter'),
      value = select.value;
    const options =
      '<option value="">' +
      esc(t('filters.project.all')) +
      '</option>' +
      snap.projects
        .map((p) => '<option value="' + esc(p.path) + '">' + esc(p.name) + '</option>')
        .join('');
    if (select.innerHTML !== options) {
      select.innerHTML = options;
      select.value = value;
    }
    const unseen = snap.alerts.filter(
      (a) => !a.acknowledged && knownAlerts && !knownAlerts.has(a.id),
    );
    if (
      knownAlerts &&
      localStorage.getItem('mc-notify') === '1' &&
      'Notification' in window &&
      Notification.permission === 'granted'
    ) {
      unseen
        .slice(0, 3)
        .forEach(
          (a) => new Notification('Mission Control · ' + a.kind, { body: a.text, tag: a.id }),
        );
    }
    knownAlerts = new Set(snap.alerts.map((a) => a.id));
    head();
    if (force || ['overview', 'agents', 'projects', 'graph', 'alerts'].includes(view))
      await render(force);
    else if (view === 'analytics' && !document.activeElement?.closest('.formrow'))
      await render(false);
  } catch (e) {
    $('connection').textContent = t('conn.error', { error: errorText(e) });
    $('status-dot').className = 'dot off';
    $('side-dot').className = 'dot off';
    $('side-state').textContent = t('side.offline');
    if (!SNAP) $('view').innerHTML = '<div class="notice danger">' + esc(errorText(e)) + '</div>';
    if (force) toast(errorText(e), true);
  } finally {
    loading = false;
    $('loadingbar').classList.remove('on');
  }
}
$('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  token = $input('login-token').value.trim();
  sessionStorage.setItem('mc-owner', token);
  try {
    await api('/api/overview');
    $('login').hidden = true;
    await load(true);
  } catch (ex) {
    $('login-error').textContent = errorText(ex);
  }
});
$button('theme').addEventListener('click', () => {
  theme = theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('mc-theme', theme);
});
$button('lang').addEventListener('click', () => {
  const lang = setLanguage(nextLanguage());
  writePreference('mc-lang', lang);
  syncLang();
  applyStatic(document);
  head();
  if (SNAP) void render(false);
});
$button('notify').addEventListener('click', async () => {
  if (!('Notification' in window)) {
    toast(t('toast.notify.unsupported'), true);
    return;
  }
  if (localStorage.getItem('mc-notify') === '1') {
    localStorage.setItem('mc-notify', '0');
    toast(t('toast.notify.off'));
    return;
  }
  const p = await Notification.requestPermission();
  localStorage.setItem('mc-notify', p === 'granted' ? '1' : '0');
  toast(p === 'granted' ? t('toast.notify.on') : t('toast.notify.denied'));
});
$button('refresh').addEventListener('click', async () => {
  try {
    await api('/api/refresh', {});
    toast(t('toast.refresh'));
    await load(true);
  } catch (e) {
    toast(errorText(e), true);
  }
});
$button('close-inspector').addEventListener('click', () => $dialog('inspector').close());
$dialog('inspector').addEventListener('click', (e) => {
  if (e.target === $dialog('inspector')) {
    const r = $dialog('inspector').getBoundingClientRect();
    if (e.clientX < r.left) $dialog('inspector').close();
  }
});
/** @type {number | undefined} */
let searchTimer;
['search', 'project-filter', 'source-filter', 'state-filter'].forEach((id) =>
  $(id).addEventListener(id === 'search' ? 'input' : 'change', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => render(false), id === 'search' ? 160 : 0);
  }),
);
$button('reset-filters').addEventListener('click', () => {
  ['search', 'project-filter', 'source-filter', 'state-filter'].forEach((id) => {
    const node = $(id);
    if (node instanceof HTMLInputElement || node instanceof HTMLSelectElement) node.value = '';
  });
  render(false);
});
document.addEventListener('keydown', (e) => {
  if (!(e.target instanceof Element)) return;
  if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('[data-inspect],[data-project]')) {
    e.preventDefault();
    e.target.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  }
  if (
    e.key === '/' &&
    !['INPUT', 'TEXTAREA'].includes(e.target.tagName) &&
    !$dialog('inspector').open
  ) {
    e.preventDefault();
    $input('search').focus();
  }
});
document.addEventListener('click', async (e) => {
  if (!(e.target instanceof Element)) return;
  const b = e.target.closest('button,[data-inspect],[data-project]');
  if (!(b instanceof HTMLElement) && !(b instanceof SVGElement)) return;
  try {
    if (b.dataset.view) {
      await go(b.dataset.view);
      return;
    }
    if (b.dataset.inspect) {
      await inspect(b.dataset.inspect);
      return;
    }
    if (b.dataset.project !== undefined) {
      $select('project-filter').value = b.dataset.project;
      $dialog('inspector').close();
      await go('agents');
      return;
    }
    if (b.dataset.mode) {
      cardsMode = b.dataset.mode === 'cards';
      localStorage.setItem('mc-cards', cardsMode ? '1' : '0');
      await render();
      return;
    }
    if (b.dataset.copy) {
      await copyText(b.dataset.copy);
      return;
    }
    if (b.dataset.zoom) {
      if (b.dataset.zoom === 'fit') fitGraph();
      else {
        graphPose.k = Math.max(
          0.08,
          Math.min(3, graphPose.k * (b.dataset.zoom === 'in' ? 1.2 : 0.8)),
        );
        graphTransform();
      }
      return;
    }
    if (b.dataset.ack) {
      await api('/api/ack', { ids: [b.dataset.ack] });
      if (b instanceof HTMLButtonElement) b.disabled = true;
      toast(t('toast.ack'));
      setTimeout(() => load(true), 600);
      return;
    }
    if (b.dataset.export) {
      const format = b.dataset.export;
      const q = analyticsQuery();
      q.set('format', format);
      const res = await fetch('/api/export?' + q, {
        headers: { Authorization: 'Bearer ' + token },
      });
      if (!res.ok) throw new Error(t('error.export'));
      const blob = await res.blob(),
        url = URL.createObjectURL(blob),
        a = document.createElement('a');
      a.href = url;
      a.download = 'mission-control.' + format;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      return;
    }
    switch (b.id) {
      case 'timeline-search':
        timelineQuery = $input('timeline-query').value;
        await loadTimeline(false);
        break;
      case 'timeline-more':
        await loadTimeline(true);
        break;
      case 'analytics-apply':
        days = Number($select('days').value);
        taskGroup = $input('task-group').value.trim();
        await loadAnalytics();
        break;
      case 'copy-session':
        if (!DETAIL) break;
        await navigator.clipboard.writeText(DETAIL.id);
        toast(t('inspect.copied'));
        break;
      case 'reload-session':
        if (!DETAIL) break;
        await inspect(DETAIL.id);
        break;
      case 'save-assessment': {
        if (!DETAIL) break;
        const raw = $select('assessment-tests').value;
        /** @param {string} id @returns {number | null} */
        const optional = (id) => ($input(id).value === '' ? null : Number($input(id).value));
        await api('/api/assessment', {
          session_id: DETAIL.id,
          assessment: {
            task_group: $input('assessment-group').value.trim(),
            model: $input('assessment-model').value.trim(),
            tests_passed: raw === '' ? null : raw === 'true',
            review_fixes: optional('assessment-fixes'),
            duration_seconds: optional('assessment-duration'),
            notes: $textarea('assessment-notes').value,
          },
        });
        toast(t('toast.assessment'));
        break;
      }
      case 'abort-session': {
        if (!DETAIL) break;
        const confirmText = prompt(t('inspect.abort.prompt', { native: DETAIL.native_id }));
        if (confirmText !== DETAIL.native_id) {
          toast(t('inspect.abort.cancelled'));
          break;
        }
        await api('/api/abort', { session_id: DETAIL.id, confirm: confirmText });
        toast(t('inspect.abort.sent'));
        break;
      }
      case 'ack-all':
        if (!SNAP) break;
        await api('/api/ack', { ids: SNAP.alerts.filter((a) => !a.acknowledged).map((a) => a.id) });
        toast(t('toast.ack_all'));
        setTimeout(() => load(true), 700);
        break;
      case 'scan-start': {
        const roots = $textarea('scan-roots')
          .value.split('\n')
          .map((x) => x.trim())
          .filter(Boolean);
        await api('/api/scan', { roots, depth: Number($select('scan-depth').value) });
        await scanProgress();
        break;
      }
      case 'scan-adopt': {
        if (!scanSnapshot) break;
        const snap = scanSnapshot;
        const selected = [...htmlAll('[data-scan-index]:checked')].map(
          (el) => snap.items[Number(el.dataset.scanIndex)],
        );
        await api('/api/adopt', { selected });
        toast(t('int.adopt.toast', { n: fmt(selected.length) }));
        break;
      }
      case 'oc-add': {
        const url = $input('oc-url').value.trim().replace(/\/$/, '');
        if (!url) break;
        const cfg = /** @type {DashboardConfig} */ (await api('/api/config'));
        if (!cfg.opencode_urls.includes(url)) cfg.opencode_urls.push(url);
        await api('/api/config', cfg);
        toast(t('toast.oc.added'));
        await load(true);
        break;
      }
      case 'save-remote': {
        const cfg = /** @type {DashboardConfig} */ (await api('/api/config'));
        cfg.public_origin = $input('public-origin').value.trim();
        cfg.oauth_redirect_uris = $textarea('oauth-callbacks')
          .value.split('\n')
          .map((x) => x.trim())
          .filter(Boolean);
        await api('/api/config', cfg);
        toast(t('toast.remote.saved'));
        await load(true);
        break;
      }
      case 'revoke-oauth':
        if (confirm(t('confirm.revoke'))) {
          await api('/api/revoke', {});
          toast(t('toast.revoked'));
        }
        break;
      case 'config-save': {
        const cfg = JSON.parse($textarea('config-editor').value);
        await api('/api/config', cfg);
        $('config-status').textContent = t('set.saved');
        toast(t('set.valid'));
        break;
      }
      case 'config-reload':
        await settings(renderSeq);
        break;
      case 'stop-observer':
        if (confirm(t('set.confirm.stop'))) {
          await api('/api/shutdown', { confirm: 'STOP OBSERVER' });
          toast(t('toast.shutdown'));
        }
        break;
    }
  } catch (ex) {
    toast(errorText(ex), true);
  }
});
document.addEventListener('change', async (e) => {
  if (!(e.target instanceof HTMLInputElement)) return;
  const target = e.target;
  if (target.id === 'reporting-toggle') {
    try {
      const cfg = /** @type {DashboardConfig} */ (await api('/api/config'));
      cfg.enable_reporting = target.checked;
      await api('/api/config', cfg);
      toast(cfg.enable_reporting ? t('toast.reporting.on') : t('toast.reporting.off'));
    } catch (ex) {
      toast(errorText(ex), true);
      target.checked = !target.checked;
    }
  }
});
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) load(false);
});
head();
load(true);
setInterval(() => {
  if (!document.hidden) load(false);
}, 5000);

/* Accessible mobile navigation. No application or session state is fabricated. */
(function setupNavigation() {
  const sidebarNode = document.getElementById('sidebar');
  const toggleNode = document.getElementById('menu-toggle');
  const scrimNode = document.getElementById('sidebar-scrim');
  if (!(sidebarNode instanceof HTMLElement)) return;
  if (!(toggleNode instanceof HTMLElement)) return;
  if (!(scrimNode instanceof HTMLElement)) return;
  const sidebar = sidebarNode;
  const toggle = toggleNode;
  const scrim = scrimNode;
  const mobile = window.matchMedia('(max-width: 900px)');
  let expanded = false;

  /** @param {boolean} value @param {boolean} [restoreFocus] @returns {void} */
  function setExpanded(value, restoreFocus = false) {
    expanded = mobile.matches && value;
    sidebar.classList.toggle('open', expanded);
    sidebar.inert = mobile.matches && !expanded;
    const main = document.getElementById('main-content');
    if (main) main.inert = expanded;
    scrim.hidden = !expanded;
    toggle.setAttribute('aria-expanded', String(expanded));
    toggle.setAttribute('aria-label', expanded ? t('topbar.menu.close') : t('topbar.menu.open'));
    document.body.classList.toggle('nav-open', expanded);
    if (expanded) {
      const target = sidebar.querySelector('.nav button.active') || sidebar.querySelector('button');
      if (target instanceof HTMLElement) target.focus();
    } else if (restoreFocus) toggle.focus();
  }

  toggle.addEventListener('click', () => setExpanded(!expanded, expanded));
  scrim.addEventListener('click', () => setExpanded(false, true));
  sidebar.addEventListener('click', (event) => {
    if (event.target instanceof Element && event.target.closest('[data-view]') && expanded) {
      setExpanded(false, true);
    }
  });
  document.addEventListener('keydown', (event) => {
    if (!expanded) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      setExpanded(false, true);
    } else if (event.key === 'Tab') {
      const items = Array.from(sidebar.querySelectorAll('button:not(:disabled), a[href]')).filter(
        (node) => node instanceof HTMLElement,
      );
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });
  mobile.addEventListener('change', () => setExpanded(false));
  setExpanded(false);
})();

/* Explicit secret reveal: values are fetched only after an owner click. */
(function revealPanel() {
  const hostNode = document.getElementById('view');
  if (!(hostNode instanceof HTMLElement)) return;
  const host = hostNode;
  let busy = false;

  /** @param {string} name @returns {Element | null} */
  function findOutput(name) {
    return (
      Array.from(host.querySelectorAll('[data-reveal-out]')).find(
        (node) => node.getAttribute('data-reveal-out') === name,
      ) || null
    );
  }

  function mount() {
    const info = INTEGRATION;
    if (!info || !host.querySelector('#scan-roots')) return;
    if (host.querySelector('[data-reveal-panel]')) return;
    const names = Array.isArray(info.secrets) ? info.secrets : [];
    if (!names.length) return;
    const section = document.createElement('section');
    section.className = 'panel';
    section.setAttribute('data-reveal-panel', '1');
    const title = document.createElement('h2');
    title.textContent = t('reveal.title');
    const note = document.createElement('p');
    note.className = 'muted';
    note.textContent = t('reveal.note');
    const list = document.createElement('div');
    list.style.display = 'grid';
    list.style.gap = '.5rem';
    for (const name of names) {
      const row = document.createElement('div');
      row.style.display = 'flex';
      row.style.alignItems = 'center';
      row.style.gap = '.5rem';
      row.style.flexWrap = 'wrap';
      const label = document.createElement('span');
      label.className = 'muted';
      label.style.minWidth = '8rem';
      label.textContent = name;
      const button = document.createElement('button');
      button.type = 'button';
      button.setAttribute('data-reveal', name);
      button.textContent = t('reveal.show');
      const output = document.createElement('output');
      output.setAttribute('data-reveal-out', name);
      output.style.fontFamily = 'ui-monospace, monospace';
      output.style.wordBreak = 'break-all';
      row.append(label, button, output);
      list.append(row);
    }
    section.append(title, note, list);
    host.append(section);
  }

  /** Keeps the static secret fields in sync so their copy buttons keep working.
   * @param {string} name
   * @param {string} value
   * @returns {void}
   */
  function syncField(name, value) {
    const id = name === 'mcp_token' ? 'mcp-token' : name === 'pairing_key' ? 'pairing-key' : '';
    if (!id) return;
    const field = document.getElementById(id);
    if (field instanceof HTMLInputElement) field.value = value;
  }

  /** @param {HTMLButtonElement} button @returns {Promise<void>} */
  async function reveal(button) {
    if (busy) return;
    const name = button.getAttribute('data-reveal');
    if (!name) return;
    const output = findOutput(name);
    busy = true;
    button.disabled = true;
    try {
      const result = /** @type {RevealResult} */ (await api('/api/reveal', { name }));
      const value = result.value || '';
      if (output) output.textContent = value;
      syncField(name, value);
      toast(t('toast.reveal', { name }));
    } catch (error) {
      toast(errorText(error), true);
    } finally {
      busy = false;
      button.disabled = false;
    }
  }

  host.addEventListener('click', (event) => {
    if (!(event.target instanceof Element)) return;
    const button = event.target.closest('[data-reveal]');
    if (!(button instanceof HTMLButtonElement) || !host.contains(button)) return;
    event.preventDefault();
    reveal(button);
  });

  new MutationObserver(mount).observe(host, { childList: true, subtree: true });
  mount();
})();
