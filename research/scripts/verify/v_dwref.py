"""Find every occurrence of a dword value (absolute reference) in an image. usage: v_dwref.py xml2|xml1 <hex>..."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys, struct
sys.path.insert(0, _REPO + '/research/scripts/verify')
from v_tables import PE, XBE, XML2, XBEP
img = PE(XML2) if sys.argv[1] == 'xml2' else XBE(XBEP)
for a in sys.argv[2:]:
    v = struct.pack('<I', int(a, 16))
    o = 0
    res = []
    while True:
        o = img.mem.find(v, o)
        if o < 0:
            break
        res.append(hex(img.base + o))
        o += 1
    print(a, len(res), res[:40])
