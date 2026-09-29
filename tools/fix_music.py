"""Moved to tools/xml1build/lib/fix_music.py (BUILDER_DESIGN.md 1.5; SPEC.md 27.13): prepare stage P5 imports it from
the xml1build package. This shim keeps `python tools/fix_music.py fix|simulate|match|layout ...` and the research
scripts' `import fix_music` (the very same module object) working; see the module for the usage."""
import sys as _sys

if __name__ == '__main__':
    from xml1build.lib.fix_music import main as _main
    _main(_sys.argv[1:])
elif __name__ != '__mp_main__':
    import importlib as _importlib
    _sys.modules[__name__] = _importlib.import_module('xml1build.lib.fix_music')
