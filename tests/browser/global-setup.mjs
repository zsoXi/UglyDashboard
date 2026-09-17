/** Starts scripts/browser_fixture.py and waits until it serves /health. */
import { execSync, spawn } from 'node:child_process';
import { existsSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve('artifacts/team/muse1');
const INFO = process.env.MC_FIXTURE_INFO || path.join(ROOT, '.fixture-info.json');
const PID = path.join(ROOT, '.fixture-pid');
const PORT = Number(process.env.MC_FIXTURE_PORT || 0);

async function waitFor(url, timeoutMs) {
  const start = Date.now();
  for (;;) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      // not up yet
    }
    if (Date.now() - start > timeoutMs) throw new Error(`fixture never came up: ${url}`);
    await new Promise((r) => setTimeout(r, 250));
  }
}

export default async function globalSetup() {
  // The server serves the production dist bundle, so the browser suite must
  // test a freshly built artifact instead of a stale one.
  execSync('npm run build', { stdio: 'inherit' });
  for (const f of [INFO, PID]) {
    try {
      if (existsSync(f)) unlinkSync(f);
    } catch {
      // ignore stale-file cleanup failures
    }
  }
  const child = spawn(
    'python',
    ['-X', 'utf8', 'scripts/browser_fixture.py', '--port', String(PORT), '--info-file', INFO],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  );
  let readyUrl = '';
  const errors = [];
  child.stdout.on('data', (d) => {
    const line = String(d);
    const m = line.match(/READY url=(\S+)/);
    if (m) readyUrl = m[1];
  });
  child.stderr.on('data', (d) => errors.push(String(d).slice(-2000)));
  const exited = new Promise((resolve) => child.on('exit', (code) => resolve(code)));
  const deadline = Date.now() + 120_000;
  for (;;) {
    if (readyUrl) break;
    const code = await Promise.race([exited, new Promise((r) => setTimeout(() => r(null), 250))]);
    if (code !== null)
      throw new Error(`browser fixture exited early (code ${code}): ${errors.join('\n')}`);
    if (Date.now() > deadline) {
      child.kill();
      throw new Error(`browser fixture never printed READY: ${errors.join('\n')}`);
    }
  }
  const code = await Promise.race([exited, new Promise((r) => setTimeout(() => r(null), 100))]);
  if (code !== null) throw new Error(`browser fixture died right after READY (code ${code})`);
  await waitFor(`${readyUrl}/health`, 60_000);
  const info = JSON.parse(readFileSync(INFO, 'utf8'));
  if (!info.url || !info.owner_token) throw new Error('fixture info file is incomplete');
  writeFileSync(PID, String(child.pid), 'utf8');
  // Detach so the child survives after this setup process exits.
  child.unref();
  process.env.MC_FIXTURE_INFO = INFO;
}
