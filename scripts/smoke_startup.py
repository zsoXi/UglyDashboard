"""Start the real dashboard on a free loopback port and smoke-test the entrypoint.

Uses a fresh temporary state directory by default and only ever stops the child
process it spawned (resolved via runtime.json, which is the real interpreter pid
because the venv python.exe is a redirector). Use ``--state-dir``/``--port`` to
target a specific port; if that port is busy the app auto-selects the next free
one and this script reports the switch.
"""
import argparse
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / 'opencode_dashboard.py'


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def request(url, token=None, data=None, timeout=5):
    req = urllib.request.Request(url, data=data)
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()
        exc.close()
        return exc.code, body


def kill(pid):
    if pid:
        subprocess.run(['taskkill', '/PID', str(pid), '/F'], capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--state-dir')
    ap.add_argument('--port', type=int)
    ap.add_argument('--timeout', type=float, default=25.0)
    args = ap.parse_args()

    tmp = None
    if args.state_dir:
        state = Path(args.state_dir).expanduser().resolve()
        state.mkdir(parents=True, exist_ok=True)
    else:
        tmp = tempfile.TemporaryDirectory(prefix='mc-smoke-')
        state = Path(tmp.name)
    wanted = args.port or free_port()

    proc = subprocess.Popen(
        [sys.executable, str(LAUNCHER), '--port', str(wanted), '--state-dir', str(state), '--no-open', '--quiet'],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    child_pid = None
    port = wanted
    ok = True
    try:
        deadline = time.monotonic() + args.timeout
        ready = False
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            try:
                runtime = json.loads((state / 'runtime.json').read_text('utf-8'))
                child_pid = runtime.get('pid')
                port = runtime['port']
                code, _ = request(f'http://127.0.0.1:{port}/health', timeout=1)
                if code == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(0.2)
        if not ready:
            out, err = proc.communicate(timeout=5)
            print('STARTUP FAILED')
            print('stdout:', out.strip()[-2000:])
            print('stderr:', err.strip()[-2000:])
            return 1

        if port != wanted:
            print(f'NOTE port {wanted} was busy; app auto-selected {port}')
        base = f'http://127.0.0.1:{port}'
        token = (state / 'owner.token').read_text('utf-8').strip()

        checks = [('/health', None), ('/', None), ('/style.css', None), ('/app.js', None),
                  ('/api/overview', token), ('/api/config', token), ('/api/timeline', token)]
        failed = 0
        for path, tok in checks:
            code, body = request(base + path, tok)
            good = code == 200 and (path != '/' or b'<html' in body.lower())
            failed += 0 if good else 1
            print(f'{"OK " if good else "BAD"} {code} {path} ({len(body)} bytes)')
        code, body = request(base + '/api/overview', token)
        try:
            print('overview keys:', ','.join(sorted(json.loads(body))[:12]))
        except Exception:
            pass
        print('RESULT', 'PASS' if failed == 0 else f'FAIL ({failed})', 'port', port, 'child', child_pid)
        ok = failed == 0
        return 0 if ok else 2
    finally:
        # Graceful stop first, then force only the child we spawned.
        body = json.dumps({'confirm': 'STOP OBSERVER'}).encode()
        request(f'http://127.0.0.1:{port}/api/shutdown', (state / 'owner.token').read_text('utf-8').strip(),
                data=body, timeout=6)
        for _ in range(40):
            if proc.poll() is not None:
                break
            time.sleep(0.25)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        kill(child_pid)
        if tmp is not None:
            tmp.cleanup()


if __name__ == '__main__':
    raise SystemExit(main())
