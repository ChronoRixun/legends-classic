import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys, struct
sys.path.insert(0, _REPO + r'/research/sweep/verify')
from v_img import Img, X1, X2
im = Img(X1 if sys.argv[1] == 'x1' else X2)
for t in sys.argv[2:]:
    target = int(t, 16)
    for va, vs, raw, rs, nm, fl in im.secs:
        if nm != '.text': continue
        code = im.b[raw:raw + min(vs, rs)]
        i = code.find(b'\xe8')
        while i >= 0:
            if i + 5 <= len(code):
                rel = struct.unpack_from('<i', code, i + 1)[0]
                if va + i + 5 + rel == target:
                    print(t, 'call from %08x' % (va + i))
            i = code.find(b'\xe8', i + 1)
        i = code.find(b'\xe9')
        while i >= 0:
            if i + 5 <= len(code):
                rel = struct.unpack_from('<i', code, i + 1)[0]
                if va + i + 5 + rel == target:
                    print(t, 'jmp from %08x' % (va + i))
            i = code.find(b'\xe9', i + 1)
    for r in im.dword_refs(target):
        print(t, 'dword ref at va %08x' % (im.va(r) or 0))
