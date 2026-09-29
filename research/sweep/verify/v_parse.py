"""Run the stock tools/convert_zone.parse_text_xml over every XML1 text-XML file (both trees, dedup by rel path)
and report failures. Then run sweeplib.normalise_text_xml and check it."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, collections, traceback
sys.path.insert(0, _REPO + r'/tools')
sys.path.insert(0, _REPO + r'/research/sweep')
import convert_zone, xmlb

EXTS = {'.xml', '.eng', '.fre', '.ger', '.chr', '.nav'}
roots = [_REPO + r'/xml1_loose', _REPO + r'/xml1_assets']
files = {}
allcount = collections.Counter()
for r in roots:
    for d, _, fs in os.walk(r):
        for f in fs:
            e = os.path.splitext(f)[1].lower()
            if e in EXTS:
                p = os.path.join(d, f)
                rel = os.path.relpath(p, r).replace(os.sep, '/').lower()
                allcount[r] += 1
                files.setdefault(rel, p)
print('per-root counts', dict(allcount), 'distinct rel', len(files))
fails = []
empty = 0
for rel, p in sorted(files.items()):
    if os.path.getsize(p) == 0:
        empty += 1
        continue
    try:
        convert_zone.parse_text_xml(p)
    except Exception as ex:
        fails.append((rel, str(ex)[:120]))
print('empty', empty, 'nonempty', len(files) - empty, 'stock-parser failures', len(fails))
for f in fails:
    print('  ', f)
try:
    import sweeplib
    nf = []
    ok = 0
    for rel, p in sorted(files.items()):
        if os.path.getsize(p) == 0:
            continue
        try:
            root = sweeplib.normalise_text_xml(p) if 'path' in sweeplib.normalise_text_xml.__code__.co_varnames[:1] else sweeplib.normalise_text_xml(open(p, 'rb').read())
            b = xmlb.encode(root)
            xmlb.decode(b)
            ok += 1
        except Exception as ex:
            nf.append((rel, repr(ex)[:150]))
    print('sweeplib normalise+encode+decode ok', ok, 'fail', len(nf), nf[:10])
except Exception:
    traceback.print_exc()
