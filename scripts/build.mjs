import { build } from 'esbuild';
import { createHash } from 'node:crypto';
import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('..', import.meta.url));
const web = path.join(root, 'web');
const dist = path.join(web, 'dist');
await mkdir(dist, { recursive: true });
await build({
  entryPoints: [path.join(web, 'app.js')],
  outfile: path.join(dist, 'app.js'),
  bundle: true,
  minify: true,
  target: 'es2022',
  charset: 'utf8',
  legalComments: 'none',
  logLevel: 'warning',
});
await build({
  entryPoints: [path.join(web, 'style.css')],
  outfile: path.join(dist, 'style.css'),
  minify: true,
  target: 'es2022',
  charset: 'utf8',
  legalComments: 'none',
  logLevel: 'warning',
});
// The production artifact is what the server ships: index.html is copied into
// dist so the manifest describes exactly the files the server reads.
await copyFile(path.join(web, 'index.html'), path.join(dist, 'index.html'));
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
const inputs = {},
  outputs = {};
const inputNames = [
  'index.html',
  'app.js',
  'style.css',
  'i18n/en.js',
  'i18n/pl.js',
  'i18n/core.js',
];
for (const name of inputNames) inputs[name] = sha(await readFile(path.join(web, name)));
for (const name of ['index.html', 'app.js', 'style.css'])
  outputs[name] = sha(await readFile(path.join(dist, name)));
await writeFile(
  path.join(dist, 'manifest.json'),
  JSON.stringify({ inputs, outputs }, null, 2) + '\n',
);
console.log(JSON.stringify({ built: Object.keys(outputs), reproducible: true }));
