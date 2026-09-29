"""Do shipping XML2 zones reference nav / zam / boy / characters files that do not exist on disk?
(Evidence for how to treat XML1's 0-byte .nav files: omit the file rather than write an empty NAVB.)"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import collections, os, sys
sys.path.insert(0, _REPO + r'/research/sweep')
from sweeplib import walk_files, load_xmlb, X2

files = walk_files(X2)
root = os.path.join(X2, 'Packages', 'generated', 'maps')
res = collections.defaultdict(collections.Counter)
examples = collections.defaultdict(list)
EXT = {'nav': '.navb', 'zam': '.zam', 'boy': '.boyb', 'characters': '.chrb', 'zonexml': '.xmlb'}
for d, _, fs in os.walk(root):
    for f in fs:
        if not f.upper().endswith('.PKGB'):
            continue
        r = load_xmlb(os.path.join(d, f))
        zx = [e.get('filename') for e in r if e.tag == 'zonexml']
        if not zx or (zx[0].lower() + '.xmlb') not in files:
            continue  # only packages of zones that really exist
        for e in r:
            if e.tag in EXT:
                ok = (e.get('filename').lower() + EXT[e.tag]) in files
                res[e.tag][ok] += 1
                if not ok and len(examples[e.tag]) < 8:
                    examples[e.tag].append(os.path.relpath(os.path.join(d, f), root).replace(os.sep, '/'))
for k, v in res.items():
    print(k, dict(v), examples.get(k))
