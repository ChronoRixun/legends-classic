"""Moved to tools/xml1build/lib/simlookup.py (BUILDER_DESIGN.md 1.5; SPEC.md 27.13): the pipeline and the builder import it
from the xml1build package. This shim keeps the research tools importing it by its old name (`import simlookup` gives the
very same module object) and `python research/sound/simlookup.py ...` working."""
import os as _os
import sys as _sys

# research/<topic>/ -> <repo>/tools (appended: never shadows the research folder's own modules)
_TOOLS = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), 'tools')
if _TOOLS not in _sys.path:
    _sys.path.append(_TOOLS)

if __name__ == '__main__':
    import runpy as _runpy
    _runpy.run_module('xml1build.lib.simlookup', run_name='__main__', alter_sys=True)
elif __name__ != '__mp_main__':
    import importlib as _importlib
    _sys.modules[__name__] = _importlib.import_module('xml1build.lib.simlookup')
