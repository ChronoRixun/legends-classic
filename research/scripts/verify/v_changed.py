import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os
roots = [_REPO + '/xml1_loose/scripts', _REPO + '/xml1_assets/scripts']
out = _REPO + '/research/scripts/out/scripts'
outidx = {}
for dp, dn, fn in os.walk(out):
    for f in fn:
        p = os.path.join(dp, f)
        outidx[os.path.relpath(p, out).replace(os.sep, '/').lower()] = p
seen = set()
changed = same = 0
for r in roots:
    for dp, dn, fn in os.walk(r):
        for f in fn:
            if not f.lower().endswith('.py'):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, r).replace(os.sep, '/').lower()
            if rel in seen:
                continue
            seen.add(rel)
            if open(p, 'rb').read() == open(outidx[rel], 'rb').read():
                same += 1
            else:
                changed += 1
print('source scripts', len(seen), 'changed', changed, 'unchanged', same, 'generated extra', len(outidx) - len(seen))
