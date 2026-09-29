"""Moved to tools/xml1build/lib/ztrk.py (BUILDER_DESIGN.md 1.5; SPEC.md 27.13): the pipeline and the builder import it
from the xml1build package. This shim keeps the research tools importing it by its old name (`import ztrk` gives the
very same module object) and `python research/sound/ztrk.py ...` working."""
import os as _os
import sys as _sys

# research/<topic>/ -> <repo>/tools (appended: never shadows the research folder's own modules)
_TOOLS = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), 'tools')
if _TOOLS not in _sys.path:
    _sys.path.append(_TOOLS)

if __name__ == '__main__':
    if not _sys.argv[1:]:        # the developer default: XML1's banks
        from xml1build.sources import REPO_ROOT as _ROOT
        _sys.argv[1:] = [(_ROOT / 'xml1_xbox' / 'sounds' / 'zsds').as_posix()]
    import runpy as _runpy
    _runpy.run_module('xml1build.lib.ztrk', run_name='__main__', alter_sys=True)
elif __name__ != '__mp_main__':
    import importlib as _importlib
    _sys.modules[__name__] = _importlib.import_module('xml1build.lib.ztrk')
