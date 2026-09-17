import { EN } from './en.js';
import { PL } from './pl.js';

/** Central offline i18n runtime. Dictionaries live in en.js / pl.js and use
 * stable dot keys with {placeholder} interpolation. Plural entries are objects
 * keyed by Intl.PluralRules categories (one / few / many / other).
 */

/** @type {Record<string, Record<string, string | Record<string, string>>>} */
const DICTS = { en: EN, pl: PL };
/** @type {Record<string, string>} */
const LOCALES = { en: 'en-US', pl: 'pl-PL' };
/** @type {string[]} */
export const LANGUAGES = ['en', 'pl'];
const FALLBACK = 'en';

let lang = FALLBACK;
/** @type {Set<string>} */
const missing = new Set();

/** @returns {string} */
export function getLanguage() {
  return lang;
}

/** @param {string} next @returns {string} */
export function setLanguage(next) {
  lang = Object.prototype.hasOwnProperty.call(DICTS, next) ? next : FALLBACK;
  if (typeof document !== 'undefined') document.documentElement.lang = lang;
  return lang;
}

/** The next language in the switch order. @returns {string} */
export function nextLanguage() {
  const index = LANGUAGES.indexOf(lang);
  return LANGUAGES[(index + 1) % LANGUAGES.length] ?? FALLBACK;
}

/** @returns {string} */
export function locale() {
  return LOCALES[lang] ?? LOCALES[FALLBACK];
}

/** @param {number} value @param {Intl.NumberFormatOptions} [options] @returns {string} */
export function formatNumber(value, options) {
  return new Intl.NumberFormat(locale(), options).format(value);
}

/** Data currency rendering: the stored currency is never converted.
 * @param {number} value @param {string} [currency] @returns {string}
 */
export function formatMoney(value, currency = 'USD') {
  return new Intl.NumberFormat(locale(), {
    style: 'currency',
    currency,
    maximumFractionDigits: 3,
  }).format(value);
}

/** @param {number} ts @returns {string} */
export function formatDateTime(ts) {
  return new Intl.DateTimeFormat(locale(), { dateStyle: 'short', timeStyle: 'short' }).format(
    new Date(ts),
  );
}

/** @param {string} key @returns {string | Record<string, string> | undefined} */
function lookup(key) {
  const dict = DICTS[lang] ?? DICTS[FALLBACK];
  return dict[key] ?? DICTS[FALLBACK][key];
}

/** Translate a stable key. A missing key is returned verbatim and recorded so
 * tests can fail on it; it is never silently swallowed.
 * @param {string} key
 * @param {Record<string, string | number>} [params]
 * @returns {string}
 */
export function t(key, params) {
  let entry = lookup(key);
  if (entry == null) {
    missing.add(key);
    return key;
  }
  if (typeof entry === 'object') {
    const count = Number(params?.n ?? 0);
    const rule = new Intl.PluralRules(locale()).select(Number.isFinite(count) ? count : 0);
    entry = entry[rule] ?? entry.other ?? entry.one ?? '';
  }
  return String(entry).replace(/\{(\w+)\}/g, (match, name) =>
    params && name in params ? String(params[name]) : match,
  );
}

/** Keys requested but absent from both dictionaries (runtime check hook).
 * @returns {string[]}
 */
export function missingKeys() {
  return [...missing].sort();
}

/** Storage-safe preference read. A broken or blocked store must never break
 * the language switch.
 * @param {string} key @param {string} fallback @returns {string}
 */
export function readPreference(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value == null || value === '' ? fallback : value;
  } catch (_error) {
    return fallback;
  }
}

/** @param {string} key @param {string} value @returns {void} */
export function writePreference(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (_error) {
    /* Storage unavailable (private mode / blocked): preference is session-only. */
  }
}

/** Replace all marked static text in the document shell. Dynamic views call
 * t() directly; this only covers markup that ships in index.html.
 * @param {ParentNode} [root] @returns {void}
 */
export function applyStatic(root = document) {
  root.querySelectorAll('[data-i18n]').forEach((node) => {
    node.textContent = t(node.getAttribute('data-i18n') ?? '');
  });
  root.querySelectorAll('[data-i18n-html]').forEach((node) => {
    node.innerHTML = t(node.getAttribute('data-i18n-html') ?? '');
  });
  root.querySelectorAll('[data-i18n-placeholder]').forEach((node) => {
    node.setAttribute('placeholder', t(node.getAttribute('data-i18n-placeholder') ?? ''));
  });
  root.querySelectorAll('[data-i18n-title]').forEach((node) => {
    node.setAttribute('title', t(node.getAttribute('data-i18n-title') ?? ''));
  });
  root.querySelectorAll('[data-i18n-aria]').forEach((node) => {
    node.setAttribute('aria-label', t(node.getAttribute('data-i18n-aria') ?? ''));
  });
}
