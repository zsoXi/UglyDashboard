'use strict';
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
const fmt = (n) =>
  n == null ? '—' : Number(n).toLocaleString('pl-PL', { maximumFractionDigits: 0 });
/** @param {number | null | undefined} n @returns {string} */
const compact = (n) =>
  n == null
    ? '—'
    : n >= 1e6
      ? (n / 1e6).toFixed(2) + 'M'
      : n >= 1e3
        ? (n / 1e3).toFixed(1) + 'K'
        : fmt(n);
/** @param {number | null | undefined} t @returns {string} */
const date = (t) =>
  t
    ? new Date(t).toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'short' })
    : 'brak czasu';
/** @param {number | null | undefined} t @returns {string} */
const ago = (t) => {
  if (!t) return 'brak danych';
  const s = Math.max(0, (Date.now() - t) / 1000);
  return s < 60
    ? Math.floor(s) + ' s temu'
    : s < 3600
      ? Math.floor(s / 60) + ' min temu'
      : s < 86400
        ? Math.floor(s / 3600) + ' godz. temu'
        : Math.floor(s / 86400) + ' dni temu';
};
/** @param {number | null | undefined} s @returns {string} */
const duration = (s) =>
  s == null
    ? '—'
    : s >= 3600
      ? (s / 3600).toFixed(1) + ' h'
      : s >= 60
        ? Math.round(s / 60) + ' min'
        : Math.round(s) + ' s';
/** @param {number | null | undefined} n @returns {string} */
const money = (n) => (n == null ? '—' : '$' + Number(n).toFixed(3));
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
/** @type {Record<string, [string, string]>} */
const titles = {
  overview: [
    'Centrum operacyjne',
    'Każdy projekt. Każdy agent. Jeden obraz pracy, oparty na rzeczywistych źródłach.',
  ],
  projects: [
    'Twoje projekty',
    'Osobne przestrzenie pracy, wspólny obraz sytuacji. Bez zgadywania, który projekt jest który.',
  ],
  agents: [
    'Agenci i sesje',
    'Bieżące stany obok dowodów. Definicje agentów nie są liczone jako uruchomienia.',
  ],
  graph: [
    'Graf zespołów',
    'Rzeczywiste relacje sesji. Linia ciągła oznacza potwierdzoną delegację, przerywana relację niepotwierdzoną lub fork.',
  ],
  timeline: [
    'Historia zdarzeń',
    'Wspólna historia OpenCode, Codex, MCP i interwencji właściciela.',
  ],
  analytics: [
    'Modele i zużycie',
    'Tokeny to pomiar wykorzystania, nie ocena jakości. Wyniki testów i review wymagają rzeczywistych danych.',
  ],
  alerts: [
    'Wymaga uwagi',
    'Sygnały do sprawdzenia. Żaden alert nie uruchamia automatycznej interwencji.',
  ],
  integrations: [
    'Źródła i MCP',
    'Połącz lokalne źródła. Udostępnij panel Codexowi i ChatGPT przez chroniony most MCP.',
  ],
  settings: [
    'Ustawienia obserwatora',
    'Zakres odczytu, reguły i prywatność. Zmiany dotyczą panelu, nie konfiguracji Twoich agentów.',
  ],
};
if (!titles[view]) view = 'overview';
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
    throw new Error('Potrzebny klucz właściciela.');
  }
  /** @type {unknown} */
  let data;
  try {
    data = await res.json();
  } catch (cause) {
    throw new Error('Nieprawidłowa odpowiedź serwera.', { cause });
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
  const title =
    view === 'overview'
      ? [
          'Centrum operacyjne',
          'Każdy projekt. Każdy agent. Jeden obraz pracy, oparty na rzeczywistych źródłach.',
        ]
      : titles[view];
  const searchWrap = $input('search').closest('.search-wrap');
  if (searchWrap instanceof HTMLElement) searchWrap.hidden = view === 'analytics';
  $input('search').hidden = view === 'analytics';
  $select('state-filter').hidden = view === 'analytics';
  $('heading').textContent = title[0];
  $('subtitle').textContent = title[1];
  $('crumb').textContent = title[0];
  $('filters').hidden = ['integrations', 'settings', 'timeline', 'alerts'].includes(view);
  /** @type {Record<string, string>} */
  const labels = {
    overview: 'YOUR WORKSPACE / AT A GLANCE',
    projects: 'WORKSPACES / PROJECT INTELLIGENCE',
    agents: 'OPERATIONS / AGENT INSPECTOR',
    graph: 'TOPOLOGY / VERIFIED RELATIONSHIPS',
    timeline: 'OBSERVABILITY / EVENT STREAM',
    analytics: 'ANALYTICS / MEASURED USAGE',
    alerts: 'ATTENTION / HUMAN IN CONTROL',
    integrations: 'CONNECTIONS / LOCAL + MCP',
    settings: 'SYSTEM / WORKSPACE SETTINGS',
  };
  $('eyebrow').textContent = labels[view] || 'MISSION CONTROL';
  htmlAll('.nav [data-view]').forEach((button) => {
    const current = button.dataset.view === view;
    button.classList.toggle('active', current);
    if (current) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  $('viewtag').textContent =
    view === 'graph'
      ? 'VERIFIED RELATIONS'
      : view === 'integrations'
        ? 'AUTHENTICATED MCP'
        : 'OBSERVER MODE';
  document.title = title[0] + ' · UglyDashboard';
}

/** @param {string} v @returns {Promise<void>} */
async function go(v) {
  if (!titles[v]) return;
  view = v;
  localStorage.setItem('mc-view', v);
  head();
  $('view').innerHTML = '<div class="loading">Ładowanie widoku…</div>';
  await render(true);
}
/** @param {string} title @param {string} text @param {string} [button] @returns {string} */
function empty(title, text, button = '') {
  return (
    '<div class="empty"><h3>' + esc(title) + '</h3><p>' + esc(text) + '</p>' + button + '</div>'
  );
}
/** @returns {string} */
function coverage() {
  if (!SNAP) return '';
  const warnings = SNAP.coverage || [];
  if (!warnings.length) return '';
  const detail = warnings
    .map((s) => {
      const loaded = s.loaded_sessions;
      const total = s.total_sessions;
      const counted =
        typeof loaded === 'number' && typeof total === 'number' && loaded < total
          ? 'niepełne: ' + loaded + ' z ' + total + ' sesji'
          : 'niepełne: pokazano wybrany fragment historii';
      const reason = s.catching_up
        ? 'trwa odczyt dużych plików'
        : s.deadline_exceeded || s.truncated
          ? 'przekroczono limit odczytu'
          : 'część danych poza oknem';
      return esc(s.label) + ' — ' + counted + ' (' + reason + ')';
    })
    .join('; ');
  return (
    '<div class="notice coverage-note" role="status">Statystyki niepełne — to nie cała ' +
    'historia. ' +
    detail +
    '. Otwórz Źródła i MCP, aby zobaczyć pełny zakres.</div>'
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
      'Aktywni · potwierdzeni',
      verified,
      unverified + ' dodatkowych wg logu lub raportu',
      'pulse',
      'agents',
    ],
    [
      '',
      'Projekty w widoku',
      projects,
      sessions.length + ' sesji w załadowanym oknie',
      'projects',
      'projects',
    ],
    [
      '',
      'Zużyte tokeny',
      compact(tokens),
      'Źródła natywne · bez dublowania routera',
      'analytics',
      'analytics',
    ],
    [
      alerts ? 'red' : '',
      'Wymaga Twojej uwagi',
      alerts,
      'Alerty oczekujące na potwierdzenie',
      'alerts',
      'alerts',
    ],
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
    '" aria-label="Otwórz projekt ' +
    esc(project.name) +
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
    '</strong><small>aktywnych · API</small></div>' +
    '<div><strong>' +
    compact(project.tokens) +
    '</strong><small>tokeny w oknie</small></div>' +
    '<div><strong>' +
    fmt(project.sessions) +
    '</strong><small>sesje</small></div></div>' +
    '<div class="campus-bottom"><div class="chips">' +
    project.sources.map((s) => source(s)).join('') +
    '</div>' +
    '<span class="branch-label" title="' +
    esc(project.git?.branch || 'Git niedostępny') +
    '">' +
    uiIcon('graph') +
    esc(project.git?.branch || 'bez Git') +
    '</span></div></article>'
  );
}

/** @param {SessionSummary[]} rows @param {number} [max] @returns {string} */
function sessionTable(rows, max = 200) {
  if (!rows.length)
    return empty(
      'Brak sesji w tym widoku',
      'Wyczyść filtry lub podłącz źródła, aby zobaczyć rzeczywiste sesje.',
    );
  return (
    '<div class="tablewrap"><table class="table"><thead><tr>' +
    '<th>Agent / zadanie</th><th>Stan / dowód</th><th>Model</th><th>Projekt</th><th class="right">Tokeny</th><th>Aktywność</th>' +
    '</tr></thead><tbody>' +
    rows
      .slice(0, max)
      .map(
        (s) =>
          '<tr data-inspect="' +
          esc(s.id) +
          '" tabindex="0" role="button" aria-label="Sprawdź sesję ' +
          esc(s.agent) +
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
          esc(s.origin === 'unknown' ? 'inicjator nieustalony' : s.origin) +
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
      ? '<p class="note table-coverage">Pokazano ' +
        max +
        ' z ' +
        rows.length +
        ' pasujących sesji. Zawęź filtry.</p>'
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
    ' tok</span></div></article>'
  );
}
/** @param {TimelineEvent[]} events @param {number} [max] @returns {string} */
function eventList(events, max = 20) {
  if (!events.length)
    return '<p class="note">Nie zarejestrowano jeszcze zdarzeń w tym zakresie.</p>';
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
        esc(s.ok ? 'połączono' : s.error ? 'błąd' : 'brak źródła') +
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
      '<div class="sectionhead"><h2>Przestrzenie pracy <span>' +
      ps.length +
      '</span></h2><button data-view="projects">Wszystkie projekty ↗</button></div>' +
      (ps.length
        ? '<div class="grid3">' + ps.slice(0, 6).map(campus).join('') + '</div>'
        : empty(
            'Czas podłączyć Twoją fabrykę agentów',
            'Wybierz katalogi projektów i źródła danych. Panel nie tworzy demonstracyjnych workerów.',
            '<button class="primary" data-view="integrations">Dodaj źródła</button>',
          )) +
      '<div class="sectionhead"><h2>Ostatnie i aktywne sesje</h2><button data-view="agents">Inspektor agentów ↗</button></div><div class="panel">' +
      sessionTable(rows, 8) +
      '</div><div class="grid2" style="margin-top:18px"><div class="panel"><div class="paneltitle"><h2>Strumień zdarzeń</h2><button class="smallbtn" data-view="timeline">Otwórz</button></div><div id="overview-events"><p class="note">Odczyt historii…</p></div></div><div class="panel"><div class="paneltitle"><h2>Łączność</h2><span class="eyebrow">SOURCE HEALTH</span></div>' +
      sourcesMini() +
      '<div class="notice info">Potwierdzone aktywne: odczyt API OpenCode. Znaczniki w logach Codexa i raporty MCP mają osobną klasę pewności.</div></div></div>';
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
            'Brak projektów',
            'Zeskanuj wybrane foldery lub dopisz ścieżki w ustawieniach.',
            '<button data-view="integrations">Otwórz źródła</button>',
          )) +
      ps
        .map(
          (p) =>
            '<div class="sectionhead"><h2>' +
            esc(p.name) +
            ' <span>' +
            esc(p.git?.branch || 'Git niedostępny') +
            '</span></h2><button data-project="' +
            esc(p.path) +
            '">Sesje projektu ↗</button></div><div class="panel">' +
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
              : '<p class="note">' +
                esc(p.git?.error || 'Nie odczytano historii Git dla tego folderu.') +
                '</p>') +
            '<p class="note" style="margin-top:14px">Commit jest kontekstem projektu. Panel nie przypisuje mu fikcyjnego kosztu z całych poprzednich 24 godzin.</p></div>',
        )
        .join('');
  } else if (view === 'agents') {
    box.innerHTML =
      statsCards(rows) +
      coverage() +
      '<div class="sectionhead"><h2>Uruchomienia <span>' +
      rows.length +
      '</span></h2><div class="view-controls"><button data-mode="table" class="smallbtn ' +
      (!cardsMode ? 'active' : '') +
      '">Tabela</button><button data-mode="cards" class="smallbtn ' +
      (cardsMode ? 'active' : '') +
      '">Karty</button></div></div>' +
      (cardsMode
        ? '<div class="agentcards">' + rows.slice(0, 200).map(agentCard).join('') + '</div>'
        : '<div class="panel">' + sessionTable(rows) + '</div>');
  } else if (view === 'graph') {
    if (force || !$svg('graph-svg')) {
      box.innerHTML =
        '<div class="notice info">Graf nie wymyśla CTO ani TL na podstawie nazw. Pokazuje identyfikatory i relacje istniejące w źródłach. Przesuwaj tło, używaj kółka lub przycisków powiększenia.</div><div class="graphwrap" id="graph-wrap"><div class="graph-toolbar"><button data-zoom="in" aria-label="Powiększ">+</button><button data-zoom="out" aria-label="Pomniejsz">−</button><button data-zoom="fit">Dopasuj</button></div><svg id="graph-svg" aria-label="Graf relacji agentów" role="img"><g id="graph-layer"></g></svg><div class="graphlegend"><span>━ potwierdzona delegacja</span><span>┄ fork / niepotwierdzony rodzic</span><span id="graph-count"></span></div></div>';
      bindGraph();
    }
    if (!graphDragged) drawGraph(rows);
  } else if (view === 'timeline') {
    if (force || !$('timeline-events')) {
      box.innerHTML =
        '<div class="panel"><div class="formrow"><label>Przeszukaj historię<input id="timeline-query" placeholder="np. retry, test, nazwa agenta…" value="' +
        esc(timelineQuery) +
        '"></label><button id="timeline-search">Szukaj</button></div><div class="notice info">Paginacja według kolejności zapisu do obserwatora; w pobranym fragmencie sortujemy po czasie zdarzenia. Starsze logi mogą zostać zaimportowane później.</div><div id="timeline-events"></div><button id="timeline-more" class="smallbtn" style="margin-top:16px">Wczytaj więcej</button></div>';
      await loadTimeline(false);
    }
  } else if (view === 'analytics') {
    if (force || !$('analytics-results')) {
      box.innerHTML =
        '<div class="panel"><div class="formrow"><label>Okres<select id="days"><option value="0">Załadowana historia</option><option value="7">Ostatnie 7 dni</option><option value="30">Ostatnie 30 dni</option><option value="90">Ostatnie 90 dni</option><option value="365">Ostatni rok</option></select></label><label>Porównywalna grupa zadań<input id="task-group" placeholder="np. dashboard-ui-benchmark" value="' +
        esc(taskGroup) +
        '"></label><button id="analytics-apply">Zastosuj</button><button data-export="json">JSON</button><button data-export="csv">CSV</button></div><p class="note" style="margin-top:12px">Modelom przypisujemy rzeczywiste tokeny. Wyniki testów, czas i poprawki zapisujesz w inspektorze. Brak oceny pozostaje brakiem oceny.</p></div><div id="analytics-results"><div class="loading">Obliczanie…</div></div>';
      $select('days').value = String(days);
    }
    await loadAnalytics(seq);
  } else if (view === 'alerts') {
    const alerts = SNAP.alerts;
    box.innerHTML =
      '<div class="sectionhead"><h2>Sygnały <span>' +
      alerts.filter((a) => !a.acknowledged).length +
      ' nowych</span></h2><button id="ack-all">Przyjmij wszystkie do wiadomości</button></div>' +
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
                esc(a.severity === 'danger' ? 'Wysoki priorytet' : 'Do sprawdzenia') +
                '</h3><p>' +
                esc(a.text) +
                '</p></div><div class="actions">' +
                (a.session_id
                  ? '<button class="smallbtn" data-inspect="' +
                    esc(a.session_id) +
                    '">Inspektor</button>'
                  : '') +
                (!a.acknowledged
                  ? '<button class="smallbtn" data-ack="' + esc(a.id) + '">Przyjmij</button>'
                  : badge('przyjęto')) +
                '</div></article>',
            )
            .join('')
        : empty(
            'Nic nie wymaga interwencji',
            'Nie wykryto alertów w aktualnie załadowanych źródłach. To nie jest gwarancja braku błędów w kodzie.',
          ));
  } else if (view === 'integrations') {
    if (force) await integrations(seq);
  } else if (view === 'settings') {
    if (force) await settings(seq);
  }
}
/** @param {UsageDay[]} data @returns {string} */
function chart(data) {
  if (!data.length) return '<p class="note">Brak rekordów zużycia w tym okresie.</p>';
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
    '" role="img" aria-label="Dzienne zużycie tokenów">';
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
    '</svg><div class="legend"><span><i style="background:var(--accent)"></i>input bez cache</span><span><i style="background:var(--green)"></i>output</span><span><i style="background:var(--purple)"></i>reasoning</span><span><i style="background:var(--amber)"></i>cache</span></div>' +
    (data.length > 120
      ? '<p class="note">Wykres: ostatnie 120 dni z rekordami. Eksport obejmuje cały wybrany zakres.</p>'
      : '')
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
      '</div><div class="sectionhead"><h2>Zużycie w czasie <span>' +
      compact(a.tokens) +
      ' tok · ' +
      a.sessions +
      ' sesji</span></h2></div><div class="panel">' +
      chart(a.days) +
      '</div><div class="sectionhead"><h2>Porównanie modeli</h2><span class="micro">Wyniki testów i review: deklaracje właściciela</span></div><div class="panel tablewrap"><table class="table"><thead><tr><th>Model / provider</th><th class="right">Tokeny</th><th class="right">Sesje</th><th class="right">Śr. tok / sesję</th><th class="right">Testy / próba</th><th class="right">Śr. poprawek</th><th class="right">Czas zadania</th><th class="right">Koszt zapisany</th><th class="right">Estymata</th></tr></thead><tbody>' +
      a.models
        .map(
          (m) =>
            '<tr><td><div class="name">' +
            esc(m.model) +
            '</div><div class="under">' +
            esc(m.provider) +
            ' · ' +
            m.assessed_tasks +
            ' ocen</div></td><td class="right num">' +
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
      (a.models.length
        ? ''
        : empty('Brak zużycia dla wybranych filtrów', 'Zmień okres albo dodaj źródło danych.')) +
      '<p class="note" style="margin-top:15px">' +
      esc(a.cost_note) +
      ' W porównaniu nie ma fikcyjnych ocen jakości.</p></div><div class="grid2" style="margin-top:18px"><div class="panel"><h2>Aktywność · 52 tygodnie</h2><div class="heatmap">' +
      a.activity
        .map(
          (d) =>
            '<div class="heatcell l' +
            (d.total ? Math.max(1, Math.ceil((d.total / max) * 4)) : 0) +
            '" title="' +
            esc(d.date + ' · ' + fmt(d.total) + ' tokenów') +
            '"></div>',
        )
        .join('') +
      '</div><p class="note">Intensywność z dostępnych rekordów źródłowych. Puste pole oznacza brak zarejestrowanych tokenów, nie udowodnioną bezczynność.</p></div><div class="panel"><h2>Pliki · przybliżony podział</h2>' +
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
      '<p class="note" style="margin-top:12px">Równy podział tokenów sesji między odnotowane pliki. To estymata przypisania, nie zmierzony koszt konkretnej edycji.</p></div></div>' +
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
    '<div class="sectionhead"><h2>Router · osobny rejestr</h2></div><div class="notice">Te żądania mogą pokrywać się z sesjami Codexa lub OpenCode. Nie dodajemy ich do łącznych tokenów. Rejestr pokazuje własne załadowane okno i nie stosuje filtrów projektu/grupy.</div>' +
    SNAP.router
      .map(
        (r) =>
          '<div class="panel" style="margin-bottom:12px"><p class="note">' +
          esc(r.source) +
          '</p><div class="chips" style="margin:12px 0">' +
          badge(r.requests + ' requests') +
          badge(compact(r.tokens) + ' tokens') +
          badge(r.errors + ' errors') +
          badge(r.unknown_status + ' unknown status') +
          '</div><div class="tablewrap"><table class="table"><thead><tr><th>Czas</th><th>Model</th><th>Status</th><th class="right">Tokeny</th></tr></thead><tbody>' +
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
            ? '\nRodzic poza widocznym zakresem: ' + s.parent_id
            : ''),
      ) +
      '</title></g>';
  });
  layer.innerHTML = edges + nodes;
  $('graph-count').textContent = shown.length + ' / ' + rows.length + ' sesji';
  graphTransform();
  if (!rows.length) {
    layer.innerHTML =
      '<text x="30" y="50" fill="var(--muted)" font-size="14">Brak sesji w tym widoku. Dodaj źródła lub wyczyść filtry.</text>';
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
  $('inspector-title').textContent = 'Odczyt sesji…';
  $('inspector-body').innerHTML = '<div class="loading">Odczyt danych źródłowych…</div>';
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
        ['Agent', s.agent],
        ['Model', s.model],
        ['Projekt', s.directory || 'nieustalony'],
        ['Sesja', s.id],
        ['Rodzic', s.parent_id || 'brak'],
        ['Relacja', s.relationship],
        ['Inicjator', s.origin + ' · ' + s.origin_evidence],
        ['Utworzenie', date(s.created)],
        ['Ostatni zapis', date(s.updated)],
        [
          'Kontekst',
          s.context_tokens == null
            ? 'nieznany'
            : fmt(s.context_tokens) + ' / ' + fmt(s.context_limit),
        ],
      ]
        .map(([k, v]) => '<dt>' + esc(k) + '</dt><dd>' + esc(v) + '</dd>')
        .join('') +
      '</dl><div class="btnrow"><button class="smallbtn" id="copy-session">Kopiuj ID</button><button class="smallbtn" data-project="' +
      esc(s.directory) +
      '">Sesje projektu</button><button class="smallbtn" id="reload-session">Odśwież inspektor</button>' +
      (SNAP?.privacy.abort && s.source === 'opencode'
        ? '<button class="smallbtn dangerbtn" id="abort-session">Przerwij sesję…</button>'
        : '') +
      '</div><h3>Zużycie i kontekst</h3><div class="panel"><div class="splithead"><h2>' +
      compact(u.total) +
      ' tokenów</h2><span class="micro">' +
      (s.usage_known ? 'odczyt źródła' : 'brak pomiaru') +
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
      '<p class="note" style="margin-top:12px">Input nie obejmuje tu cache. Reasoning jest wydzielone z outputu. Zachowujemy osobno sumę zgłoszoną przez źródło.</p></div>' +
      (s.warnings?.length
        ? '<div class="notice">' + s.warnings.map(esc).join('<br>') + '</div>'
        : '') +
      '<h3>Zadanie / ostatni prompt</h3><pre class="codebox">' +
      esc(
        s.reported_task ||
          s.prompt ||
          'Brak zarejestrowanego promptu albo wyłączone udostępnianie treści.',
      ) +
      '</pre>' +
      (s.definition
        ? '<details class="toolrow"><summary>Definicja agenta · ' +
          esc(s.definition.source) +
          '</summary><pre class="codebox">' +
          esc(s.definition.prompt || s.definition.description) +
          '</pre></details>'
        : '') +
      '<h3>Ostatnie wywołania narzędzi</h3>' +
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
        : '<p class="note">Brak zapisanych wywołań w załadowanym zakresie.</p>') +
      '<h3>Odnotowane pliki</h3><pre class="codebox">' +
      esc(s.files.join('\n') || 'Brak odnotowanych edycji.') +
      '</pre><h3>Ocena wykonania · dane właściciela</h3><div class="panel formgrid"><label>Grupa porównywalnych zadań<input id="assessment-group" value="' +
      esc(a.task_group || s.task_group || '') +
      '" placeholder="np. ui-regression-round-1"></label><label>Model oceniany<input id="assessment-model" value="' +
      esc(a.model || s.model) +
      '"></label><div class="formgrid two"><label>Testy<select id="assessment-tests"><option value="">Nie sprawdzono</option><option value="true">Przeszły</option><option value="false">Nie przeszły</option></select></label><label>Poprawki po review<input id="assessment-fixes" type="number" min="0" step="1" value="' +
      esc(a.review_fixes ?? '') +
      '" placeholder="nieznane"></label></div><label>Zmierzone wykonanie w sekundach<input id="assessment-duration" type="number" min="0" step="1" value="' +
      esc(a.duration_seconds ?? '') +
      '" placeholder="nie szacuj z czasu istnienia sesji"></label><label>Notatki<textarea id="assessment-notes" rows="3">' +
      esc(a.notes || '') +
      '</textarea></label><button class="primary" id="save-assessment">Zapisz ocenę</button><p class="note">Wynik przypisujesz do wybranego modelu. W sesji wielomodelowej oceniaj wyłącznie to, co faktycznie zweryfikowałeś.</p></div><h3>Historia sesji</h3>' +
      eventList(
        (s.timeline || []).sort((a, b) => b.ts - a.ts),
        25,
      );
    $select('assessment-tests').value = a.tests_passed == null ? '' : String(a.tests_passed);
  } catch (e) {
    if (seq !== inspectSeq) return;
    $('inspector-title').textContent = 'Nie udało się odczytać sesji';
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
            esc(s.location || 'Nie wybrano źródła') +
            '</div><p>' +
            esc(s.error || s.note || (s.ok ? 'Odczyt aktywny' : 'Niepołączono')) +
            '</p><div class="chips" style="margin-top:10px">' +
            (s.loaded_sessions != null
              ? badge(s.loaded_sessions + ' / ' + s.total_sessions + ' sessions')
              : '') +
            (s.loaded_files != null ? badge(s.loaded_files + ' logs') : '') +
            (s.truncated ? badge('ograniczony zakres', 'waiting') : '') +
            (s.skipped_records ? badge(s.skipped_records + ' skipped', 'waiting') : '') +
            '</div></div>',
        )
        .join('') +
      '</div><div class="sectionhead"><h2>Znajdź projekty i źródła</h2><span class="micro">Skan ograniczony do wybranych folderów</span></div><div class="panel"><div class="formgrid"><label>Foldery startowe · jeden na linię<textarea id="scan-roots" rows="2">' +
      esc(cfg.scan_roots.join('\n')) +
      '</textarea></label><div class="formrow"><label>Głębokość<select id="scan-depth"><option>3</option><option selected>5</option><option>8</option><option>10</option></select></label><button id="scan-start" class="primary">Skanuj wybrane foldery</button></div><p class="note">Szukamy znaczników Git, .opencode, opencode.db, .codex i usage-events.jsonl. Bez odczytu plików auth.json, .env i cudzych katalogów przez dowiązania. Limit: 6000 folderów lub 12 sekund. Skan niczego automatycznie nie dodaje.</p><div id="scan-status"></div><div id="scan-results" class="scanner-results"></div><button id="scan-adopt" hidden>Monitoruj zaznaczone wyniki</button></div></div><div class="sectionhead"><h2>Połączenie z istniejącym OpenCode</h2></div><div class="panel"><div class="formrow"><label>Adres lokalnego API<input id="oc-url" placeholder="http://127.0.0.1:4096"></label><button id="oc-add">Dodaj serwer</button></div><p class="note" style="margin-top:12px">Podaj adres już działającej instancji. Panel nie uruchamia osobnego OpenCode i nie skanuje portów. Losowy port aplikacji desktopowej trzeba wskazać. Hasło jest pobierane wyłącznie ze zmiennych OPENCODE_SERVER_PASSWORD / OPENCODE_SERVER_USERNAME procesu panelu.</p><pre class="codebox">' +
      esc(cfg.opencode_urls.join('\n')) +
      '</pre></div><div class="sectionhead"><h2>MCP · Codex i ChatGPT</h2><span class="viewtag">' +
      info.tools.length +
      ' TOOLS</span></div><div class="grid2"><div class="panel"><h2>Codex · lokalnie</h2><p class="note">Wklej do konfiguracji MCP Codexa. Most stdio łączy się z tym uruchomionym panelem i sam odczytuje lokalny token. Nie tworzy drugiego obserwatora.</p><pre class="codebox" id="stdio-config">' +
      esc(info.stdio_toml) +
      '</pre><button class="smallbtn" data-copy="stdio-config">Kopiuj konfigurację stdio</button><details class="secrets"><summary>Wariant HTTP z tokenem środowiskowym</summary><pre class="codebox" id="http-config">' +
      esc(info.http_toml) +
      '</pre><p class="note">Ustaw MISSION_CONTROL_MCP_TOKEN w środowisku procesu Codexa. Nie wklejaj tokenu do rozmowy.</p><input readonly type="password" value="' +
      esc('') +
      '" id="mcp-token" aria-label="Token MCP"><button class="smallbtn" data-copy="mcp-token">Kopiuj token MCP</button></details></div><div class="panel"><h2>ChatGPT · HTTPS + OAuth</h2><div class="mcpstep"><span class="n">1</span><p>Skonfiguruj stały tunel HTTPS do portu ' +
      esc(String(SNAP.port || 8765)) +
      '. Tunel nie jest otwierany automatycznie.</p></div><div class="mcpstep"><span class="n">2</span><p>Ustaw publiczny adres i dokładny callback widoczny w konfiguracji połączenia ChatGPT.</p></div><div class="formgrid"><label>Publiczny adres HTTPS<input id="public-origin" placeholder="https://mc.twoja-domena.pl" value="' +
      esc(cfg.public_origin) +
      '"></label><label>Dozwolone callbacki OAuth · jeden na linię<textarea id="oauth-callbacks" rows="2">' +
      esc(cfg.oauth_redirect_uris.join('\n')) +
      '</textarea></label><button id="save-remote">Zapisz ustawienia zdalne</button></div><div class="mcpstep"><span class="n">3</span><p>Połącz ChatGPT z <code>' +
      esc(info.remote_url || 'https://twój-host/mcp') +
      '</code>, wybierz OAuth oraz dynamiczną rejestrację DCR. Pozostaw statyczne dane klienta puste.</p></div><details class="secrets"><summary>Klucz właściciela do formularza parowania</summary><p class="note">Wklej wyłącznie na stronie autoryzacji tego obserwatora. Nie wysyłaj w czacie ani do innego MCP.</p><input type="password" readonly value="' +
      esc('') +
      '" id="pairing-key" aria-label="Klucz parowania"><button class="smallbtn" data-copy="pairing-key">Kopiuj klucz</button></details><button class="smallbtn dangerbtn" id="revoke-oauth">Unieważnij zdalne tokeny OAuth</button></div></div><div class="notice">MCP nie daje automatycznie dostępu do wszystkich rozmów ChatGPT. Zobaczysz tylko wywołania tego mostu oraz jawnie przesłane raporty. Lokalny log Codexa nie obejmuje automatycznie sesji działających wyłącznie w chmurze.</div><div class="panel"><h2>Raportowanie pochodzenia zadania</h2><label class="togglelabel"><input id="reporting-toggle" type="checkbox" ' +
      (cfg.enable_reporting ? 'checked' : '') +
      '> Udostępnij narzędzie report_event (zapis tylko w obserwatorze)</label><pre class="codebox" id="report-example">' +
      esc(
        JSON.stringify(
          {
            event_id: 'unikalny-identyfikator-zdarzenia',
            source: 'chatgpt',
            session_id: 'opencode:ses_TUTAJ_PRAWDZIWE_ID',
            task: 'Sprawdzenie regresji UI',
            task_group: 'dashboard-ui-round-1',
            state: 'running',
          },
          null,
          2,
        ),
      ) +
      '</pre><p class="note">Powiąż raport z prawdziwym canonical session_id z list_agents. Raport nie zastępuje stanu API, nie nalicza tokenów i nie uruchamia pracy. Zmiana narzędzi wymaga odświeżenia ich listy po stronie klienta.</p></div><div class="sectionhead"><h2>Klienci tego mostu</h2></div><div class="panel">' +
      (SNAP.mcp_clients?.length
        ? SNAP.mcp_clients
            .map(
              (c) =>
                '<div class="statusline"><span class="label">' +
                esc(c.name) +
                '</span><span class="num">' +
                fmt(c.calls) +
                ' calls</span><span class="small">' +
                esc(ago(c.last_seen)) +
                '</span></div>',
            )
            .join('')
        : '<p class="note">Żaden klient nie zainicjował jeszcze tego mostu. Nazwy klientów pochodzą z ich deklaracji.</p>') +
      '</div><div class="sectionhead"><h2>Definicje agentów <span>' +
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
        : '<p class="note">Definicje zostaną odczytane z API albo globalnych i projektowych folderów agent/agents.</p>') +
      '</div><details class="panel" style="margin-top:18px"><summary>Uwagi integracyjne i ograniczenia</summary><pre class="codebox">' +
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
      '<div class="grid2"><div class="panel"><h2>Konfiguracja</h2><p class="note">Zmiany są sprawdzane i zapisywane atomowo. Ceny w pricing podajesz jako USD za milion tokenów; brak ceny nie oznacza zera. Możesz wykluczyć projekt przez excluded_projects.</p><textarea id="config-editor" class="codeedit" spellcheck="false" aria-label="Konfiguracja JSON">' +
      esc(JSON.stringify(CONFIG, null, 2)) +
      '</textarea><div class="btnrow"><button class="primary" id="config-save">Sprawdź i zapisz</button><button id="config-reload">Wczytaj ponownie</button></div><div id="config-status" class="note"></div></div><div class="panel"><h2>Najważniejsze reguły</h2><dl class="details"><dt>show_prompts</dt><dd>Wyłącza prompt i treść definicji. Wyniki narzędzi nadal mogą zawierać poufne dane.</dd><dt>enable_reporting</dt><dd>Włącza report_event; domyślnie wyłączone.</dd><dt>allow_abort</dt><dd>Włącza przycisk przerwania tylko dla właściciela, z wpisaniem ID. MCP nie może przerwać agenta.</dd><dt>expected_models</dt><dd>Mapa nazwa agenta / ID sesji → dokładny ID modelu. Niezgodność generuje alert, nie automatyczną zmianę.</dd><dt>allowed_paths</dt><dd>Mapa nazwa agenta → lista dozwolonych folderów edycji.</dd><dt>stall_seconds</dt><dd>Próg braku nowych dowodów aktywności, a nie automatyczny wyrok o awarii.</dd><dt>token_budget</dt><dd>Limit informacyjny na sesję. 0 wyłącza alert.</dd><dt>history_limit</dt><dd>Liczba ostatnio aktualizowanych sesji z każdej bazy. Zakres nie jest całą historią, jeśli limit zostanie osiągnięty.</dd><dt>codex_file_limit</dt><dd>Liczba najnowszych lokalnych logów Codexa.</dd><dt>history_days</dt><dd>Retencja własnej historii obserwatora. Źródła nie są usuwane.</dd></dl><div class="notice">Panel nie instaluje aktualizacji, nie odpala workerów, nie przełącza płatnych modeli i nie modyfikuje źródłowych baz.</div><p class="note">Własne pliki aplikacji: config.json, observer.sqlite, owner.token, mcp.token, pairing.key i mission-control.log. Trzy pliki kluczy są poufne.</p><div class="sectionhead"><h2>Zakończ pracę panelu</h2></div><p class="note">Zamknięcie karty nie wyłącza obserwatora. Ten przycisk zatrzymuje wyłącznie panel i jego most MCP, bez zatrzymywania agentów.</p><button class="dangerbtn" id="stop-observer">Zatrzymaj obserwator</button></div></div>';
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
      ? 'Skanowanie wybranych folderów…'
      : s.scanned_dirs != null
        ? s.scanned_dirs +
          ' folderów · ' +
          s.items.length +
          ' wyników' +
          (s.truncated ? ' · limit osiągnięty; zawęź folder lub skanuj kolejny zakres' : '')
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
    toast('Skopiowano.');
  } catch (_) {
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) el.select();
    toast('Schowek niedostępny. Zaznacz i skopiuj tekst ręcznie.', true);
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
      ? (fresh ? 'Odczyt ' : 'Dane wymagają odświeżenia · ') + ago(snap.generated_at)
      : 'Pierwszy odczyt źródeł…';
    $('status-dot').className = 'dot ' + (fresh ? 'pulse' : 'off');
    $('side-dot').className = 'dot ' + (fresh ? '' : 'off');
    $('side-state').textContent = fresh ? 'Obserwator działa' : 'Oczekiwanie na dane';
    $('nav-projects').textContent = String(snap.projects.length);
    $('nav-agents').textContent = String(snap.sessions.length);
    $('nav-agents').title = 'Sesje w załadowanym oknie; aktywność jest liczona osobno';
    $('nav-alerts').textContent = String(snap.alerts.filter((a) => !a.acknowledged).length);
    const select = $select('project-filter'),
      value = select.value;
    const options =
      '<option value="">Wszystkie projekty</option>' +
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
    $('connection').textContent = 'Brak połączenia · ' + errorText(e);
    $('status-dot').className = 'dot off';
    $('side-dot').className = 'dot off';
    $('side-state').textContent = 'Połączenie niedostępne';
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
$button('notify').addEventListener('click', async () => {
  if (!('Notification' in window)) {
    toast('Ta przeglądarka nie obsługuje powiadomień.', true);
    return;
  }
  if (localStorage.getItem('mc-notify') === '1') {
    localStorage.setItem('mc-notify', '0');
    toast('Powiadomienia wyłączone.');
    return;
  }
  const p = await Notification.requestPermission();
  localStorage.setItem('mc-notify', p === 'granted' ? '1' : '0');
  toast(
    p === 'granted'
      ? 'Powiadomienia nowych alertów włączone.'
      : 'Powiadomienia nie zostały udostępnione.',
  );
});
$button('refresh').addEventListener('click', async () => {
  try {
    await api('/api/refresh', {});
    toast('Zażądano nowego odczytu źródeł.');
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
      toast('Przyjęto alert do wiadomości.');
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
      if (!res.ok) throw new Error('Eksport nie powiódł się.');
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
        toast('Skopiowano ID sesji.');
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
        toast('Zapisano ocenę właściciela.');
        break;
      }
      case 'abort-session': {
        if (!DETAIL) break;
        const confirmText = prompt(
          'To zatrzyma rzeczywistą sesję OpenCode. Wpisz dokładnie ID:\n' + DETAIL.native_id,
        );
        if (confirmText !== DETAIL.native_id) {
          toast('Nie przerwano sesji.');
          break;
        }
        await api('/api/abort', { session_id: DETAIL.id, confirm: confirmText });
        toast('Wysłano żądanie przerwania. Sprawdź nowy stan źródła.');
        break;
      }
      case 'ack-all':
        if (!SNAP) break;
        await api('/api/ack', { ids: SNAP.alerts.filter((a) => !a.acknowledged).map((a) => a.id) });
        toast('Przyjęto widoczne alerty.');
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
        toast('Dodano ' + selected.length + ' źródeł/projektów do monitorowania.');
        break;
      }
      case 'oc-add': {
        const url = $input('oc-url').value.trim().replace(/\/$/, '');
        if (!url) break;
        const cfg = /** @type {DashboardConfig} */ (await api('/api/config'));
        if (!cfg.opencode_urls.includes(url)) cfg.opencode_urls.push(url);
        await api('/api/config', cfg);
        toast('Zapisano adres istniejącego OpenCode.');
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
        toast('Zapisano ustawienia OAuth. Tunel HTTPS wymaga osobnej konfiguracji.');
        await load(true);
        break;
      }
      case 'revoke-oauth':
        if (
          confirm(
            'Unieważnić wszystkie zdalne tokeny OAuth? Klienci będą musieli połączyć się ponownie.',
          )
        ) {
          await api('/api/revoke', {});
          toast('Zdalne tokeny zostały unieważnione.');
        }
        break;
      case 'config-save': {
        const cfg = JSON.parse($textarea('config-editor').value);
        await api('/api/config', cfg);
        $('config-status').textContent =
          'Zapisano. Nowe ustawienia zostaną zastosowane w kolejnym odczycie.';
        toast('Konfiguracja przeszła walidację.');
        break;
      }
      case 'config-reload':
        await settings(renderSeq);
        break;
      case 'stop-observer':
        if (
          confirm('Zatrzymać tylko ten obserwator? Agenci OpenCode i Codex będą nadal działać.')
        ) {
          await api('/api/shutdown', { confirm: 'STOP OBSERVER' });
          toast('Obserwator zatrzymywany. Ponowne uruchomienie: launcher lub plik Python.');
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
      toast(
        cfg.enable_reporting
          ? 'Raportowanie włączone. Odśwież listę narzędzi w klientach MCP.'
          : 'Raportowanie wyłączone.',
      );
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
    toggle.setAttribute('aria-label', expanded ? 'Zamknij nawigację' : 'Otwórz nawigację');
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
    title.textContent = 'Sekrety i tokeny';
    const note = document.createElement('p');
    note.className = 'muted';
    note.textContent =
      'Wartości są pokazywane dopiero po kliknięciu i traktowane jak hasła. Nigdy nie udostępniaj ich niezaufanym narzędziom.';
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
      button.textContent = 'Pokaż';
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
      toast('Ujawniono ' + name + '. Ukryj lub skopiuj ręcznie.');
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
