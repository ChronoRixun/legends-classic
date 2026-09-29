"""Moved to tools/xml1build/lib/bescript.py (prepare stage P3, tools/xml1build/prepare/scripts.py, parses the XML1
scripts with it; SPEC.md 27). This shim keeps the research tools (analyze_scripts.py, var_*.py, popup_check.py, ...)
importing it by its old name."""
import os as _os
import sys as _sys

_TOOLS = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), 'tools')
if _TOOLS not in _sys.path:
    _sys.path.insert(0, _TOOLS)

from xml1build.lib.bescript import *  # noqa: E402,F401,F403
from xml1build.lib.bescript import parse_file, parse_line  # noqa: E402,F401
