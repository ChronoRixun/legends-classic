"""Block-structure comparison source vs rewritten, excluding legacy `if __name__` lines and allowing
generated if/endif pairs (sign extension)."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re
roots = [_REPO + '/xml1_loose/scripts', _REPO + '/xml1_assets/scripts']
out = _REPO + '/research/scripts/out/scripts'


def kw(t):
    c = {'if': 0, 'elif': 0, 'elseif': 0, 'else': 0, 'endif': 0}
    for line in t.replace('\r\n', '\n').split('\n'):
        s = line.split('#', 1)[0].strip()
        if not s or '__name__' in s:
            continue
        f = re.split(r'[\s(:]', s, maxsplit=1)[0].lower()
        if f in c:
            c[f] += 1
    return c


outidx = {}
for dp, dn, fn in os.walk(out):
    for f in fn:
        p = os.path.join(dp, f)
        outidx[os.path.relpath(p, out).replace(os.sep, '/').lower()] = p
bad = n = 0
seen = set()
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
            n += 1
            if rel not in outidx:
                print('missing', rel)
                bad += 1
                continue
            a = kw(open(p, 'rb').read().decode('latin-1'))
            b = kw(open(outidx[rel], 'rb').read().decode('latin-1'))
            extra = b['if'] - a['if']
            if (a['elif'], a['elseif'], a['else']) != (b['elif'], b['elseif'], b['else']) or extra < 0 \
                    or (b['endif'] - a['endif']) != extra:
                bad += 1
                print(rel, a, b)
print('files', n, 'mismatches:', bad)
