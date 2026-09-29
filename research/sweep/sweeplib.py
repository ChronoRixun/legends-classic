"""Moved to tools/xml1build/lib/sweeplib.py (BUILDER_DESIGN.md 1.5; SPEC.md 27.13): the pipeline imports it from the
xml1build package. This shim keeps the sweep scripts' `from sweeplib import ...` working, with the developer folders
X1 / X1A / X2 they use (the library itself has no paths: it takes them from its callers)."""
import os as _os
import sys as _sys

# research/sweep/ -> <repo>/tools (appended: never shadows the research folder's own modules)
_TOOLS = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), 'tools')
if _TOOLS not in _sys.path:
    _sys.path.append(_TOOLS)

from xml1build.lib.sweeplib import *  # noqa: E402,F401,F403
from xml1build.lib.sweeplib import ET, load_xmlb, normalise_text_xml, parse_text_xml_robust, walk_files, xmlb  # noqa
from xml1build.sources import REPO_ROOT as _ROOT, DEFAULT_XML2 as _X2  # noqa: E402

X1 = (_ROOT / 'xml1_loose').as_posix()
X1A = (_ROOT / 'xml1_assets').as_posix()
X2 = _X2.as_posix()
