/** Stops the fixture spawned by global-setup.mjs (own child only). */
import { existsSync, readFileSync, unlinkSync } from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve('artifacts/team/muse1');
const PID = path.join(ROOT, '.fixture-pid');

function alive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export default async function globalTeardown() {
  if (!existsSync(PID)) return;
  const pid = Number(readFileSync(PID, 'utf8').trim());
  try {
    unlinkSync(PID);
  } catch {
    // ignore
  }
  if (!Number.isFinite(pid) || !alive(pid)) return;
  try {
    process.kill(pid, 'SIGTERM');
  } catch {
    return;
  }
  const deadline = Date.now() + 15_000;
  while (alive(pid) && Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 250));
  }
  if (alive(pid)) {
    try {
      process.kill(pid, 'SIGKILL');
    } catch {
      // already gone
    }
  }
}
