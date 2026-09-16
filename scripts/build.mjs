import { build } from 'esbuild';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('..', import.meta.url));
const web = path.join(root, 'web');
const dist = path.join(web, 'dist');
await mkdir(dist, { recursive: true });
await build({
  entryPoints: [path.join(web, 'app.js')],
  outfile: path.join(dist, 'app.js'),
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
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
const inputs = {},
  outputs = {};
for (const name of ['index.html', 'app.js', 'style.css'])
  inputs[name] = sha(await readFile(path.join(web, name)));
for (const name of ['app.js', 'style.css'])
  outputs[name] = sha(await readFile(path.join(dist, name)));
await writeFile(
  path.join(dist, 'manifest.json'),
  JSON.stringify({ inputs, outputs }, null, 2) + '\n',
);
console.log(JSON.stringify({ built: Object.keys(outputs), reproducible: true }));
