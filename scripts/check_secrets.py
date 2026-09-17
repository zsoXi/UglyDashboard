"""Repository guard: fail when a real secret leaks into files or artifacts.

Scans the files Git would ship (tracked + untracked-not-ignored) plus the
local, git-ignored evidence directories (``artifacts/``, ``test-results/``,
``playwright-report/``) for shapes that only real credentials have:
``#access=`` fragments, ``Bearer`` headers, ``sk-`` keys, serialized secret
fields and standalone token lines. Matched values are never printed; only the
location, the pattern name and the value length are reported.

Usage:
    python -X utf8 scripts/check_secrets.py
    python -X utf8 scripts/check_secrets.py --root <dir>
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
}
# Local evidence directories that are git-ignored but still must stay clean.
EVIDENCE_DIRS = ("artifacts", "test-results", "playwright-report")
MAX_BYTES = 8_000_000
# Deliberate local credential stores (created 0600 by the app or its fixture);
# they are git-ignored files, not leaks. Their values are still never printed.
ALLOWED_CREDENTIAL_NAMES = {".fixture-info.json", "owner.token", "mcp.token", "pairing.key"}

PATTERNS = [
    ("access-fragment", re.compile(r"#access=([A-Za-z0-9_\-]{16,})")),
    ("bearer-token", re.compile(r"(?i)\bbearer\s+([A-Za-z0-9._\-]{24,})")),
    ("sk-key", re.compile(r"\bsk-([A-Za-z0-9]{24,})")),
    (
        "secret-field",
        re.compile(r"\"(?:owner_token|mcp_token|pairing_key)\"\s*:\s*\"([A-Za-z0-9_\-]{16,})\""),
    ),
    ("standalone-token", re.compile(r"^([A-Za-z0-9_\-]{32,512})\s*$")),
]


def _plausible_token(value: str) -> bool:
    """True when a run of token characters looks like a real credential.

    Real secrets mix letters and digits and are not one repeated character.
    This rejects false positives such as unittest separator lines (``----…``)
    and long test identifiers that contain no digits.
    """
    return (
        len(set(value)) >= 3
        and any(char.isalpha() for char in value)
        and any(char.isdigit() for char in value)
    )


def _git_files(root: Path):
    """Return files Git would ship, or None when Git is unavailable."""

    def _run(*args):
        result = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            check=True,
        )
        return [p for p in result.stdout.decode("utf-8", "replace").split("\0") if p]

    try:
        names = _run("ls-files", "-z") + _run("ls-files", "-z", "--others", "--exclude-standard")
    except (OSError, subprocess.SubprocessError):
        return None
    return [root / name for name in names]


def _skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def _walk_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and not _skipped(path):
            yield path


def scan_file(path: Path):
    """Yield (line_number, label, value_length) for every suspicious line."""
    try:
        if path.stat().st_size > MAX_BYTES:
            return
        text = path.read_text("utf-8")
    except (OSError, UnicodeDecodeError):
        return
    for number, line in enumerate(text.splitlines(), 1):
        for label, pattern in PATTERNS:
            match = pattern.search(line)
            if match is None:
                continue
            value = match.group(1) if match.groups() else match.group(0)
            if label == "standalone-token" and not _plausible_token(value):
                continue
            yield number, label, len(value)


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(ROOT), help="Directory to scan (default: repo root).")
    parser.add_argument("--quiet", action="store_true", help="Print only problems.")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    files = _git_files(root)
    if files is None:
        files = list(_walk_files(root))
    else:
        for name in EVIDENCE_DIRS:
            directory = root / name
            if directory.is_dir():
                files.extend(p for p in directory.rglob("*") if p.is_file() and not _skipped(p))

    scanned = set()
    hits = []
    for path in files:
        if path.name in ALLOWED_CREDENTIAL_NAMES:
            continue
        key = str(path)
        if key in scanned:
            continue
        scanned.add(key)
        for number, label, length in scan_file(path):
            hits.append((path, number, label, length))

    for path, number, label, length in hits:
        print(
            "LEAK "
            + _relative(path, root)
            + ":"
            + str(number)
            + " ["
            + label
            + "] value redacted ("
            + str(length)
            + " chars)"
        )
    if hits:
        print("FAIL: " + str(len(hits)) + " possible secret(s) found.")
        return 1
    if not args.quiet:
        print("OK: no secret patterns in " + str(len(scanned)) + " scanned file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
