"""Offline unittest runner. UTF-8 logs, bounded ASCII JSON on stdout, honest exit code."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "tests", nargs="*", help="Optional dotted test names; default: discover all root tests."
    )
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    log_path = artifacts / "unittest.log"
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8", newline="\n") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            loader = unittest.defaultTestLoader
            suite = (
                loader.loadTestsFromNames(args.tests)
                if args.tests
                else loader.discover(str(ROOT), pattern="test_*.py", top_level_dir=str(ROOT))
            )
            result = unittest.TextTestRunner(stream=log, verbosity=2, warnings="default").run(suite)
    # ResourceWarnings remain visible in the full log and fail this gate.
    resource_warnings = log_path.read_text(encoding="utf-8").count("ResourceWarning:")
    success = result.wasSuccessful() and not resource_warnings
    summary = {
        "success": bool(success),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": [{"test": str(test), "reason": reason} for test, reason in result.skipped],
        "expected_failures": len(result.expectedFailures),
        "unexpected_successes": len(result.unexpectedSuccesses),
        "resource_warnings": resource_warnings,
        "seconds": round(time.monotonic() - started, 3),
        "python": platform.python_version(),
        "platform": platform.system(),
        "failed_tests": [str(test) for test, _ in result.failures + result.errors],
        "log": "artifacts/unittest.log",
    }
    (artifacts / "test-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True), flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
