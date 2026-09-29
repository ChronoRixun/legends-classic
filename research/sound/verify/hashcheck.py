import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import struct, sys, os

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

def keys(path):
    d = open(path, 'rb').read()
    out = {}
    for ti in (0, 4):
        c, ko, eo = struct.unpack_from('<III', d, 0x10 + 12 * ti)
        out[ti] = {struct.unpack_from('<I', d, ko + 8 * i)[0] for i in range(c)}
    return out

X2 = _XML2 + '/Sounds/eng/'
X1 = _REPO + '/xml1_xbox/sounds/zsds/'
tests = [
    (X2 + 'a/b/abug_a.zss', 'music/abug_a', None),
    (X1 + 'n/y/nyc1_a.zss', 'music/nyc1_a', None),
    (X1 + 'n/y/nyc1_c.zss', 'music/nyc1_c', None),
    (X1 + 'n/y/nyc1_d.zsm', 'nyc1/death_styles/ds_wood_m', None),
    (X1 + 'n/y/nyc1_d.zsm', 'nyc1/death_styles/ds_metal_s', None),
    (X1 + 'n/y/nyc1_d.zsm', 'nyc1/death_styles/ds_glass_l', None),
    (X1 + 'n/y/nyc1_d.zsm', 'nyc1/death_styles/ds_junk_s', None),
    (X2 + 'c/y/cyclop_m.zsm', 'char/cyclop_m/pain', 0),
    (X2 + 'c/y/cyclop_m.zsm', 'char/cyclop_m/pain', 1),
    (X2 + 'c/y/cyclop_m.zsm', 'char/cyclop_m/death', None),
    (X1 + 'g/r/grso_m.zsm', 'character/grso_m/pain', 0),
    (X1 + 'g/r/grso_m.zsm', 'character/grso_m/death', None),
    (X1 + 'g/r/grso_m.zsm', 'character/grso_m/jump', None),
]
for path, name, rnd in tests:
    if not os.path.exists(path):
        print('MISSING', path); continue
    k = keys(path)
    h = elf(name)
    if rnd is not None:
        h = elf('/***RANDOM***/%d' % rnd, h)
    where = [t for t in (0, 4) if h in k[t]]
    print('%08x %-40s rnd=%s %s -> %s' % (h, name, rnd, os.path.basename(path), where or 'NOT FOUND'))
