#!/usr/bin/env python3
"""Cross-platform test runner used by CI and local verification.

Runs the offline unittest suite with a stable, parseable summary and writes the
complete log to artifacts/. Never hides failures: the process exit code mirrors
the unittest result.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / 'artifacts'
ART.mkdir(exist_ok=True)


def run(argv: list[str], name: str) -> int:
    log = ART / f'{name}.log'
    start = time.monotonic()
    print(f'$ {" ".join(argv)}', flush=True)
    proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    elapsed = time.monotonic() - start
    output = (proc.stdout or '') + (proc.stderr or '')
    log.write_text(output, encoding='utf-8')
    print(output, flush=True)
    print(f'[{name}] exit={proc.returncode} seconds={elapsed:.2f} log={log}', flush=True)
    return proc.returncode


def main() -> int:
    unittest_argv = [sys.executable, '-m', 'unittest', '-v', 'test_mission_control']
    code = run(unittest_argv, 'unittest')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
