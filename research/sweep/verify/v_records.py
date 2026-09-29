"""For named script functions, locate the string, find dword refs to it in data, and dump
the surrounding dwords to check the {handler, name, ret, args} layout independently."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys, struct
sys.path.insert(0, _REPO + r'/research/sweep/verify')
from v_img import Img, X1, X2

names = sys.argv[2:]
im = Img(X1 if sys.argv[1] == 'x1' else X2)
for sec in im.secs:
    print('SEC', sec[4], hex(sec[0]), hex(sec[1]), hex(sec[2]), hex(sec[3]), hex(sec[5]))
for nm in names:
    hits = [o for o in im.find_all(b'\0' + nm.encode() + b'\0')]
    print('==', nm, 'string hits', len(hits))
    for h in hits:
        sv = im.va(h + 1)
        refs = im.dword_refs(sv)
        print('  str va', hex(sv), 'refs', len(refs))
        for r in refs:
            rv = im.va(r)
            d = struct.unpack_from('<6I', im.b, r - 8)
            desc = []
            for k, x in enumerate(d):
                s = im.cstr(x, 60)
                desc.append('%08x%s' % (x, ('(' + s.decode('latin1') + ')') if s is not None and all(32 <= c < 127 for c in s) and len(s) < 40 else ''))
            print('   ref at va', hex(rv) if rv else None, ' [-8..+16]:', ' '.join(desc))
