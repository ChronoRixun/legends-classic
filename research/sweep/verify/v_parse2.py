"""sweeplib.parse_text_xml_robust: round-trip every non-empty XML1 text file, and compare its XMLB output
with the stock parser's for files the stock parser accepts (to detect semantic changes)."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, collections
sys.path.insert(0, _REPO + r'/tools')
sys.path.insert(0, _REPO + r'/research/sweep')
import convert_zone, xmlb, sweeplib

EXTS = {'.xml', '.eng', '.fre', '.ger', '.chr', '.nav'}
roots = [_REPO + r'/xml1_loose', _REPO + r'/xml1_assets']
files = {}
for r in roots:
    for d, _, fs in os.walk(r):
        for f in fs:
            if os.path.splitext(f)[1].lower() in EXTS:
                p = os.path.join(d, f)
                files.setdefault(os.path.relpath(p, r).replace(os.sep, '/').lower(), p)
ok = 0
fail = []
same = 0
differ = []
for rel, p in sorted(files.items()):
    if os.path.getsize(p) == 0:
        continue
    try:
        root = sweeplib.parse_text_xml_robust(p)
        b = xmlb.encode(root)
        xmlb.decode(b)
        ok += 1
    except Exception as ex:
        fail.append((rel, repr(ex)[:150]))
        continue
    try:
        b0 = xmlb.encode(convert_zone.parse_text_xml(p))
    except Exception:
        continue
    if b0 == b:
        same += 1
    else:
        differ.append(rel)
print('robust ok', ok, 'fail', len(fail), fail[:10])
print('identical to stock output', same, 'different', len(differ), differ[:30])
