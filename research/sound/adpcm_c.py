"""Moved to tools/xml1build/lib/adpcm_c.py (BUILDER_DESIGN.md 1.5; SPEC.md 27.13): the pipeline and the builder import it
from the xml1build package. This shim keeps the research tools importing it by its old name (`import adpcm_c` gives the
very same module object) and `python research/sound/adpcm_c.py ...` working.
ima_kernel.c moved with it (tools/build_sound_kernel.py compiles it from there; the source sha1 compiled into
the library is unchanged)."""
import os as _os
import sys as _sys

# research/<topic>/ -> <repo>/tools (appended: never shadows the research folder's own modules)
_TOOLS = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), 'tools')
if _TOOLS not in _sys.path:
    _sys.path.append(_TOOLS)

if __name__ == '__main__':
    _sys.exit('adpcm_c is a library (xml1build.lib.adpcm_c); it has no command line')
elif __name__ != '__mp_main__':
    import importlib as _importlib
    _sys.modules[__name__] = _importlib.import_module('xml1build.lib.adpcm_c')
