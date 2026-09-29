"""Moved to tools/xml1build/lib/x1names.py (BUILDER_DESIGN.md 1.5; SPEC.md 27.13): the pipeline and the builder import it
from the xml1build package. This shim keeps the research tools importing it by its old name (`import x1names` gives the
very same module object) and `python research/characters/x1names.py ...` working.
Its default collision table is still research/characters/collisions.json (x1names.default_collisions: under the repo
root, no longer relative to the module file)."""
import os as _os
import sys as _sys

# research/<topic>/ -> <repo>/tools (appended: never shadows the research folder's own modules)
_TOOLS = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), 'tools')
if _TOOLS not in _sys.path:
    _sys.path.append(_TOOLS)

if __name__ == '__main__':
    _sys.exit('x1names is a library (xml1build.lib.x1names); it has no command line')
elif __name__ != '__mp_main__':
    import importlib as _importlib
    _sys.modules[__name__] = _importlib.import_module('xml1build.lib.x1names')
