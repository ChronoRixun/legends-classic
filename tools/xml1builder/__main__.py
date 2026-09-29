"""python -m xml1builder ... (from tools/), python tools/xml1builder ..., or the frozen xml1-builder.exe."""
import multiprocessing
import os
import sys

if __name__ == '__main__':
    multiprocessing.freeze_support()          # first: a frozen worker process runs its task here and exits
    if not __package__ and not getattr(sys, 'frozen', False):
        # run as a folder (python tools/xml1builder): make the package importable. Never frozen: the bundle
        # carries every module, and nothing next to the exe may be imported instead of it.
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from xml1builder.cli import main
    code = main()
    try:
        sys.stdout.flush()
    except (OSError, ValueError):
        pass
    sys.exit(code)
