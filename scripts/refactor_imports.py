"""One-shot: replace sibling star-imports with explicit imports.

Run from the repository root:
    .venv/Scripts/python.exe scripts/refactor_imports.py

It derives each module's public top-level names from the AST, expands every
``from .<sibling> import *`` into an explicit import of those names, gives the
package facade an ``__all__``, and rewrites the launcher re-exports. Ruff
(``--fix --select F401``) is expected to trim the now-explicit unused imports
afterwards.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / 'mission_control'
MODULES = ['core', 'sources', 'store', 'engine', 'oauth', 'mcp', 'server', 'cli']
LAUNCHER = ROOT / 'opencode_dashboard.py'


def public_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text('utf-8'))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        names.add(name.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return sorted(n for n in names if not n.startswith('_'))


def explicit_import(module: str, names: list[str]) -> str:
    if not names:
        return ''
    if sum(len(n) for n in names) + 2 * len(names) < 88:
        return f'from .{module} import ' + ', '.join(names)
    body = ''.join(f'    {name},\n' for name in names)
    return f'from .{module} import (\n{body})'


def main() -> None:
    owned = {mod: public_names(PKG / f'{mod}.py') for mod in MODULES}
    union: list[str] = sorted({name for names in owned.values() for name in names})

    for mod in MODULES:
        path = PKG / f'{mod}.py'
        lines = path.read_text('utf-8').splitlines(keepends=True)
        out: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('from .') and ' import *' in stripped:
                sibling = stripped.split('from .')[1].split(' ')[0]
                replacement = explicit_import(sibling, owned.get(sibling, []))
                if replacement:
                    out.append(replacement + '\n')
            else:
                out.append(line)
        path.write_text(''.join(out), 'utf-8')
        print(f'{mod}.py: {len(owned[mod])} public names')

    init = ['"""OpenCode Mission Control backend package.',
            '',
            'The public surface is re-exported flat so the thin launcher and the',
            'regression suite keep using the historical single-module API.',
            '"""',
            '']
    for mod in MODULES:
        block = explicit_import(mod, owned[mod])
        if block:
            init.append(block)
    init.append('')
    init.append('__all__ = [')
    for name in union:
        init.append(f'    {name!r},')
    init.append(']')
    init.append('')
    (PKG / '__init__.py').write_text('\n'.join(init), 'utf-8')
    print(f'__init__.py: __all__ with {len(union)} names')

    launcher = LAUNCHER.read_text('utf-8')
    # Keep the cli helpers and the mission_control surface importable flat.
    launcher = launcher.replace(
        'from mission_control import *  # noqa: F401,F403',
        'from mission_control import __all__ as _MC_ALL\n'
        'from mission_control import (' + ', '.join(union) + ')  # explicit re-export\n'
        '_ALL = list(_MC_ALL) + [\n'
        '    "builtin_self_test", "cli_report", "main", "stdio_bridge",\n'
        '    "datetime", "timedelta", "timezone", "json", "sys", "Path",\n'
        ']')
    launcher = launcher.replace(
        'from mission_control.cli import (  # noqa: F401',
        'from mission_control.cli import (')
    launcher = launcher.replace("from pathlib import Path  # noqa: F401",
                                'from pathlib import Path')
    launcher = launcher.replace('import json  # noqa: F401', 'import json')
    launcher = launcher.replace('import sys  # noqa: F401', 'import sys')
    launcher = launcher.replace('from datetime import datetime, timedelta, timezone  # noqa: F401',
                                'from datetime import datetime, timedelta, timezone')
    if '__all__' not in launcher:
        launcher = launcher.replace("if __name__ == '__main__':",
                                    "__all__ = _ALL\n\n\nif __name__ == '__main__':")
    LAUNCHER.write_text(launcher, 'utf-8')
    print('opencode_dashboard.py: explicit re-export')


if __name__ == '__main__':
    main()
