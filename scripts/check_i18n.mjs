/** Offline i18n checks. Fails the build on structural drift between the English
 * and Polish dictionaries, on raw keys or hardcoded Polish text that would leak
 * into the UI, and on mojibake. Deliberately narrow: user data, model names and
 * machine identifiers are never flagged.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const problems = [];
/** @param {string} message */
const fail = (message) => problems.push(message);

const { EN } = await import(new URL('../web/i18n/en.js', import.meta.url));
const { PL } = await import(new URL('../web/i18n/pl.js', import.meta.url));

const PLURAL_CATEGORIES = { en: ['one', 'other'], pl: ['one', 'few', 'many', 'other'] };
const PLACEHOLDER = /\{(\w+)\}/g;
const MOJIBAKE = /(Ã[\u0080-\u00BF]?|â€|Å[\u0080-\u017A]|\uFFFD)/;

/** @param {string | Record<string, string>} value @returns {string[]} */
function placeholders(value) {
  const texts = typeof value === 'string' ? [value] : Object.values(value);
  const found = new Set();
  for (const text of texts) {
    for (const match of text.matchAll(PLACEHOLDER)) found.add(match[1]);
  }
  return [...found].sort();
}

/** @param {string} file @param {Record<string, string>} dict */
function checkDictShape(file, dict) {
  for (const [key, value] of Object.entries(dict)) {
    if (typeof value === 'string') {
      if (!value.trim()) fail(file + ': empty text for key ' + key);
      if (MOJIBAKE.test(value)) fail(file + ': mojibake in key ' + key);
      continue;
    }
    if (value && typeof value === 'object') {
      for (const [category, text] of Object.entries(value)) {
        if (typeof text !== 'string' || !text.trim()) {
          fail(file + ': empty plural category ' + category + ' for key ' + key);
        } else if (MOJIBAKE.test(text)) {
          fail(file + ': mojibake in key ' + key);
        }
      }
      continue;
    }
    fail(file + ': unsupported value type for key ' + key);
  }
}

checkDictShape('en.js', EN);
checkDictShape('pl.js', PL);

for (const key of Object.keys(EN)) {
  if (!(key in PL)) fail('pl.js: missing key ' + key);
}
for (const key of Object.keys(PL)) {
  if (!(key in EN)) fail('en.js: missing key ' + key);
}

for (const key of Object.keys(EN)) {
  if (!(key in PL)) continue;
  const en = EN[key];
  const pl = PL[key];
  const enText = typeof en === 'string';
  const plText = typeof pl === 'string';
  if (enText !== plText) {
    fail('key ' + key + ': EN and PL disagree on plural form');
    continue;
  }
  if (enText) {
    const enPh = placeholders(en);
    const plPh = placeholders(pl);
    if (enPh.join(',') !== plPh.join(',')) {
      fail('key ' + key + ': placeholder drift ' + enPh.join(',') + ' vs ' + plPh.join(','));
    }
    continue;
  }
  const enCategories = Object.keys(en).sort().join(',');
  const expected = PLURAL_CATEGORIES.en.filter((c) => c in en);
  if (enCategories !== expected.sort().join(',')) {
    fail('key ' + key + ': unexpected EN plural categories ' + enCategories);
  }
  for (const category of PLURAL_CATEGORIES.pl) {
    if (!(category in pl)) fail('key ' + key + ': PL plural misses category ' + category);
  }
  const enPh = placeholders(en);
  const plPh = placeholders(pl);
  if (enPh.join(',') !== plPh.join(',')) {
    fail('key ' + key + ': plural placeholder drift ' + enPh.join(',') + ' vs ' + plPh.join(','));
  }
}

/** @param {string} file @returns {Set<string>} quoted top-level keys */
function sourceKeys(file) {
  const text = readFileSync(path.join(root, file), 'utf8');
  const keys = new Set();
  const duplicates = new Set();
  for (const match of text.matchAll(/^ {2}'([^']+)':/gm)) {
    if (keys.has(match[1])) duplicates.add(match[1]);
    keys.add(match[1]);
  }
  for (const key of duplicates) fail(file + ': duplicate key ' + key);
  return keys;
}

const enKeys = sourceKeys('web/i18n/en.js');
const plKeys = sourceKeys('web/i18n/pl.js');
for (const key of enKeys) if (!plKeys.has(key)) fail('pl.js source: missing key ' + key);
for (const key of plKeys) if (!enKeys.has(key)) fail('en.js source: missing key ' + key);

const html = readFileSync(path.join(root, 'web/index.html'), 'utf8');
if (!/<html[^>]*lang="en"/.test(html)) fail('index.html: lang must default to "en"');
if (!/<script type="module" src="\/app\.js"><\/script>/.test(html)) {
  fail('index.html: app.js must load as a module');
}

/** Visible markup text must be localized. Dynamic sinks and pure technical
 * strings (counters, separators, SVG) are exempt via an explicit id list.
 */
const TEXT_ALLOWLIST =
  /id="(view|nav-projects|nav-agents|nav-alerts|crumb|heading|subtitle|eyebrow|viewtag|connection|side-state|loadingbar|toasts|inspector-body|login-error|doc-title)"/;
const cleaned = html
  .replace(/<script[\s\S]*?<\/script>/gi, '')
  .replace(/<style[\s\S]*?<\/style>/gi, '')
  .replace(/<!--[\s\S]*?-->/g, '');
for (const match of cleaned.matchAll(/<([a-zA-Z][\w-]*)([^>]*)>([^<]*)</g)) {
  const [, tag, attrs, text] = match;
  if (!/\p{L}/u.test(text)) continue;
  if (/data-i18n-skip/.test(attrs)) continue;
  if (/data-i18n/.test(attrs)) continue;
  if (TEXT_ALLOWLIST.test(attrs)) continue;
  if (tag === 'kbd' || tag === 'code' || tag === 'svg' || tag === 'path') continue;
  fail('index.html: text without data-i18n near <' + tag + '> "' + text.trim().slice(0, 40) + '"');
}
for (const match of cleaned.matchAll(/data-i18n(?:-html|-placeholder|-title|-aria)?="([^"]+)"/g)) {
  const key = match[1];
  if (!(key in EN)) fail('index.html: unknown i18n key ' + key);
  else if (!(key in PL)) fail('index.html: key missing in PL ' + key);
}

const js = readFileSync(path.join(root, 'web/app.js'), 'utf8');
/** @param {string} key @returns {boolean} */
const hasKey = (key) => key in EN && key in PL;
for (const match of js.matchAll(/\bt\(\s*'([^']+)'/g)) {
  const key = match[1];
  if (key.endsWith('.')) {
    // Dynamic prefix, e.g. t('view.' + name + '.title'): the family must exist.
    if (!Object.keys(EN).some((candidate) => candidate.startsWith(key))) {
      fail('app.js: t() key family missing from dictionaries: ' + key);
    }
    continue;
  }
  if (!hasKey(key)) fail('app.js: t() key missing from dictionaries: ' + key);
}
let blockComment = false;
js.split('\n').forEach((line, index) => {
  const trimmed = line.trim();
  if (blockComment) {
    if (trimmed.includes('*/')) blockComment = false;
    return;
  }
  if (trimmed.startsWith('/*')) {
    if (!trimmed.includes('*/')) blockComment = true;
    return;
  }
  if (trimmed.startsWith('//') || trimmed.startsWith('*')) return;
  if (line.includes('i18n-exempt')) return;
  const code = line.replace(/\/\/.*$/, '').replace(/\/\*[\s\S]*?\*\//g, '');
  for (const match of code.matchAll(/'([^'\\]*[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ][^'\\]*)'/g)) {
    fail('app.js:' + (index + 1) + ': hardcoded Polish text "' + match[1].slice(0, 40) + '"');
  }
});

if (problems.length) {
  console.error('i18n check failed (' + problems.length + ' problems):');
  for (const problem of problems) console.error(' - ' + problem);
  process.exit(1);
}
console.log(
  JSON.stringify({
    dictionaries: { en: Object.keys(EN).length, pl: Object.keys(PL).length },
    ok: true,
  }),
);
