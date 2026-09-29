import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import struct, sys, os, glob, collections
from explore import hdr

ROOTS = {'pc': _XML2 + '/Sounds/eng', 'xbox': _REPO + '/xml1_xbox/sounds/zsds'}

def files(root):
    out = []
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if f.lower().endswith(('.zss', '.zsm')):
                out.append(os.path.join(dp, f).replace('\\', '/'))
    return sorted(out)

if __name__ == '__main__':
    for plat, root in ROOTS.items():
        fl = files(root)
        tabcnt = collections.Counter()
        mism = []
        for p in fl:
            d, magic, fsize, f0c, tabs = hdr(p)
            if fsize != len(d):
                mism.append((p, fsize, len(d)))
            for i, t in enumerate(tabs):
                if t[0]:
                    tabcnt[i] += 1
            # table contiguity
            prev = 0x64
            for i, (c, k, v) in enumerate(tabs):
                if k != prev:
                    print('noncontig', p, i, hex(k), hex(prev))
                prev = v
        print(plat, len(fl), 'files; tables nonempty in #files:', dict(tabcnt), 'size mismatches:', mism[:5], len(mism))
