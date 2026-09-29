"""Merge every converted XML1 bank whose file name collides with an XML2 bank into XML2's bank (XML2 entries win).
Output: out/merged/eng/<rel> + _merge_report.json. Usage: python merge_all.py [converted_root] [out_root] [xml2_sounds]

RETIRED into tools/xml1build/prepare/sound.py (prepare stage P4, SPEC.md 27.6: merge_all(), the same loop over
merge_zsnd.merge); this wrapper keeps the old command line and developer defaults. The original ran its loop at
import; its output and report are byte-identical to the stage's (tools/sound_equiv.py)."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from xml1build.prepare import sound as P4  # noqa: E402


def main(argv):
    conv = argv[0] if len(argv) > 0 else _REPO + '/research/sound/out/all_ima/eng'
    out = argv[1] if len(argv) > 1 else _REPO + '/research/sound/out/merged/eng'
    xml2 = argv[2] if len(argv) > 2 else _XML2 + '/Sounds/eng'
    reps, lines = P4.merge_all(conv, out, xml2)
    print('\n'.join(lines))


if __name__ == '__main__':
    main(sys.argv[1:])
