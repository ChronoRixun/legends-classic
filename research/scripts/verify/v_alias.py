"""Names used both as mission var and mission flag in XML1 (same store in XML1 -> aliasing)."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, re, collections, sys
roots = [_REPO + '/xml1_loose', _REPO + '/xml1_assets']
RE = re.compile(r'(get|set)(Mission|Game)(Var|Flag)\s*\(\s*["\']([^"\']+)["\']', re.I)
use = collections.defaultdict(set)
files = collections.defaultdict(set)
for root in roots:
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if not f.lower().endswith(('.py', '.eng', '.xml', '.chr', '.fre', '.ger')):
                continue
            p = os.path.join(dp, f)
            t = open(p, 'rb').read().decode('latin-1')
            for m in RE.finditer(t):
                kind = (m.group(2).lower(), m.group(3).lower())
                use[m.group(4).lower()].add(kind)
                files[(m.group(4).lower(), kind)].add(os.path.relpath(p, root))
both = {n: k for n, k in use.items() if ('mission', 'var') in k and ('mission', 'flag') in k}
print('names used as both mission var and mission flag:', len(both))
for n, k in sorted(both.items()):
    print('  ', n, sorted(k))
    for kind in (('mission', 'var'), ('mission', 'flag')):
        print('       ', kind, sorted(files[(n, kind)])[:4])
gm = {n: k for n, k in use.items() if ('game', 'var') in k and (('mission', 'var') in k or ('mission', 'flag') in k)}
print('names used in both game and mission stores:', len(gm), sorted(gm))
