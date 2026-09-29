"""Moved to tools/xml1build/lib/adpcm_np.py (BUILDER_DESIGN.md 1.5; SPEC.md 27.13): the pipeline and the builder import it
from the xml1build package. This shim keeps the research tools importing it by its old name (`import adpcm_np` gives the
very same module object) and `python research/sound/adpcm_np.py ...` working."""
import os as _os
import sys as _sys

# research/<topic>/ -> <repo>/tools (appended: never shadows the research folder's own modules)
_TOOLS = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), 'tools')
if _TOOLS not in _sys.path:
    _sys.path.append(_TOOLS)

if __name__ == '__main__':
    _sys.exit('adpcm_np is a library (xml1build.lib.adpcm_np); it has no command line')
elif __name__ != '__mp_main__':
    import importlib as _importlib
    _sys.modules[__name__] = _importlib.import_module('xml1build.lib.adpcm_np')
