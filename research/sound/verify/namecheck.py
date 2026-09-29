import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import json, struct, os, sys
sys.path.insert(0, _REPO + '/research/sound/verify')
from blockcheck import step  # noqa (keeps module import cheap)


def elf(s, h=0):
    for ch in s.encode('latin1'):
        if 97 <= ch <= 122:
            ch -= 32
        h = ((h << 4) + ch) & 0xffffffff
        g = h & 0xf0000000
        if g:
            h ^= g >> 24
        h &= ~g & 0xffffffff
    return h


n1 = json.load(open(_REPO + '/research/sound/names_xml1.json'))
X1 = _REPO + '/xml1_xbox/sounds/zsds/'
tot = hit = bad = 0
per = {}
for dp, dn, fn in os.walk(X1):
    for f in fn:
        rel = os.path.relpath(os.path.join(dp, f), X1).replace(os.sep, '/')
        d = open(X1 + rel, 'rb').read()
        ks = []
        for t in (0, 4):
            c, ko, eo = struct.unpack_from('<III', d, 0x10 + 12 * t)
            ks += [struct.unpack_from('<I', d, ko + 8 * j)[0] for j in range(c)]
        names = n1.get(rel, {})
        h = 0
        for k in ks:
            nm = names.get('%08x' % k)
            if nm is not None:
                parts = nm.split('/***RANDOM***/')
                hv = elf(parts[0]) if len(parts) == 1 else elf('/***RANDOM***/' + parts[1], elf(parts[0]))
                if hv != k:
                    bad += 1
                else:
                    h += 1
        tot += len(ks)
        hit += h
        per[rel] = (h, len(ks))
print('recovered names %d / %d = %.1f%%, wrong-hash names %d' % (hit, tot, 100 * hit / tot, bad))
for b in ['n/y/nyc1_a.zss', 'n/y/nyc1_c.zss', 'n/y/nyc1_d.zsm', 'n/y/nyc1_m.zsm', 'n/y/nyc1_v.zss', 'g/r/grso_m.zsm']:
    print(b, per.get(b))
