import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys
sys.path.insert(0, _REPO + r'/research/sweep/verify')
from v_img import Img, X1, X2
im = Img(X1 if sys.argv[1] == 'x1' else X2)
for a in sys.argv[2:]:
    v = int(a, 16); o = im.off(v)
    while not (im.b[o-1] == 0xcc and im.b[o-2] == 0xcc) and not (im.b[o-1]==0xc3 and im.b[o-2]==0xcc) :
        o -= 1
    print(a, 'function start ~', hex(im.va(o)))
