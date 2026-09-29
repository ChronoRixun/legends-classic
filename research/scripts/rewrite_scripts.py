"""rewrite_scripts.py - RETIRED: ported to tools/xml1build/prepare/scripts.py (prepare stage P3, SPEC.md 27.5), which
now holds the rules, the engine facts they rest on and the code. The original generator (analysis at import over
hard-coded D:/ paths) is in git history.

This wrapper keeps the old command line for developer mode: it runs the port over the developer trees (xml1_loose,
xml1_assets) with research/scripts/mission_plan.json into research/scripts/out (or --out DIR; the mission texts
already in <out>/data/missions are compiled, as before) and writes rewrite_report.txt / .json next to this file.
Its output is byte-identical to the original's (tools/prepare_equiv.py).

usage:  python rewrite_scripts.py [--out DIR]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from xml1build.prepare import scripts as P3  # noqa: E402


def main(argv):
    out = argv[argv.index('--out') + 1] if '--out' in argv else os.path.join(HERE, 'out')
    with open(os.path.join(HERE, 'mission_plan.json')) as fh:
        plan = json.load(fh)
    api1, api2 = P3.load_api(os.path.dirname(HERE))
    rw = P3.Rewriter(os.path.join(ROOT, 'xml1_loose'), os.path.join(ROOT, 'xml1_assets'), plan, api1, api2)
    lines, rep, _ = rw.write(out)
    P3.write_report(HERE, lines, rep)
    print('\n'.join(lines[:80]))


if __name__ == '__main__':
    main(sys.argv[1:])
