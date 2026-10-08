"""Run the synthetic unit tests without pytest (BUILDER_DESIGN.md 6.1): every test_* function of every test_*.py
module here. No game data is read. `python tests/unit/run.py [-k substring]`; pytest collects the same functions
(conftest.py puts this folder and tools/ on sys.path). A test that raises unittest.SkipTest (pytest honours it too)
needs a capability this machine lacks: it is reported as SKIP with its reason and does not fail the run.
Exit code 0 = all passed (or skipped)."""
import importlib
import sys
import time
import traceback
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / 'tools'))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    pat = argv[argv.index('-k') + 1] if '-k' in argv else ''
    failed, passed, skipped = [], 0, []
    t0 = time.time()
    for path in sorted(HERE.glob('test_*.py')):
        mod = importlib.import_module(path.stem)
        for name in sorted(n for n in dir(mod) if n.startswith('test_')):
            fn = getattr(mod, name)
            if not callable(fn) or (pat and pat not in f'{path.stem}.{name}'):
                continue
            t = time.time()
            try:
                fn()
                passed += 1
                print(f'PASS {path.stem}.{name} ({time.time() - t:.2f}s)')
            except unittest.SkipTest as e:
                skipped.append(f'{path.stem}.{name}')
                print(f'SKIP {path.stem}.{name}: {e}')
            except Exception:  # noqa: BLE001
                failed.append(f'{path.stem}.{name}')
                print(f'FAIL {path.stem}.{name}')
                traceback.print_exc()
    print(f'{passed} passed, {len(skipped)} skipped, {len(failed)} failed in {time.time() - t0:.1f}s'
          + (f': {failed}' if failed else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
