"""Run the prepare stages (tools/xml1build/prepare, BUILDER_DESIGN.md 1.5; SPEC.md 27) into a cache, without building.

usage: python tools/prepare_xml1.py --cache DIR [--iso IMAGE] [--base XML2_DIR]
                                    [--stages disc,tables,scripts,sound,music] [--force STAGES] [--no-movies] [--jobs N]
       python tools/prepare_xml1.py --identify IMAGE

  --identify   only probe the image (format, XBE title / title ID, the required files) and print its identity.
  --stages     which of P3-P5 to run (default: all five); P1 `disc` and P2 `tables` always run, since every later
               stage needs them. Each stage is reused from the cache while its key matches; --force re-runs the
               listed stages (or all of --stages with a bare --force). Without --iso the cache must already hold
               exactly one prepared disc.
  --no-movies  P1 leaves the 648 MB of NTSC movies out (a --no-movies build needs only movies.json); a later run
               without it adds them.
  --jobs N     worker processes for P4 / P5 (default: one per CPU).

Prints one timing line per stage. Exit code: 0 ok, 1 a stage failed (StageFailed), 3 input not usable (the
PrepareError code is printed), 5 cancelled (Ctrl+C)."""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xml1build import common as C  # noqa: E402
from xml1build import prepare  # noqa: E402
from xml1build.prepare import disc as P1, image  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--cache', help='prepare cache directory')
    ap.add_argument('--iso', help='the XML1 Xbox disc image (Redump .iso or XISO; read-only)')
    ap.add_argument('--base', default=str(C.DEFAULT_BASE), help='the XML2 PC install (read-only)')
    ap.add_argument('--stages', default=','.join(prepare.STAGES))
    ap.add_argument('--force', nargs='?', const='*', default='',
                    help='re-run these stages (comma list; bare --force = every stage in --stages)')
    ap.add_argument('--no-movies', dest='no_movies', action='store_true')
    ap.add_argument('--jobs', type=int, default=None)
    ap.add_argument('--identify', metavar='IMAGE', help='probe an image and print its identity')
    a = ap.parse_args(argv)
    try:
        if a.identify:
            with image.open_image(a.identify) as img:
                print(json.dumps(P1.identify(img), indent=1))
            return 0
        if not a.cache:
            ap.error('--cache is required')
        stages = [s.strip() for s in a.stages.split(',') if s.strip()]
        bad = [s for s in stages if s not in prepare.STAGES]
        if bad:
            ap.error(f'--stages: unknown {bad} ({", ".join(prepare.STAGES)})')
        force = stages if a.force == '*' else [s.strip() for s in a.force.split(',') if s.strip()]
        t0 = time.time()
        res = prepare.run_stages(Path(a.cache), Path(a.base), Path(a.iso) if a.iso else None, stages=stages,
                                 jobs=a.jobs, movies=not a.no_movies, force=force)
        for name, r in res.items():
            st = r['stage']
            print(f'[prepare] {name}: {"cached" if r["cached"] else str(st.get("seconds")) + "s"} '
                  f'{st.get("timings", "")} -> {r["dir"]}')
        print(f'[prepare] {", ".join(res)}: {time.time() - t0:.1f}s')
        return 0
    except prepare.PrepareError as e:
        print(f'input not usable: {e}', file=sys.stderr)
        if e.detail:
            print(f'  detail: {json.dumps(e.detail)}', file=sys.stderr)
        return 3
    except prepare.StageFailed as e:
        print(f'prepare failed: {e}', file=sys.stderr)
        return 1
    except (KeyboardInterrupt, prepare.Cancelled):
        print('cancelled', file=sys.stderr)
        return 5


if __name__ == '__main__':
    sys.exit(main())
