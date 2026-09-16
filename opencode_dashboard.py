"""Thin launcher / compatibility entrypoint for OpenCode Mission Control.

The implementation now lives in the :mod:`mission_control` package. This file
remains the stable double-click entrypoint (``opencode_dashboard.py``) and keeps
the historical flat namespace importable for tooling, the MCP stdio bridge and
the regression suite.
"""
import json  # noqa: F401
import sys  # noqa: F401
from datetime import datetime, timedelta, timezone  # noqa: F401
from pathlib import Path  # noqa: F401

from mission_control import *  # noqa: F401,F403
from mission_control.cli import (  # noqa: F401
    builtin_self_test,
    cli_report,
    main,
    stdio_bridge,
)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        LOG.exception('Startup failed')
        if sys.stderr:
            print(f'{APP}: {exc}', file=sys.stderr)
        else:
            try:
                import tkinter.messagebox
                tkinter.messagebox.showerror(APP, str(exc))
            except Exception:
                pass
        raise SystemExit(1)
