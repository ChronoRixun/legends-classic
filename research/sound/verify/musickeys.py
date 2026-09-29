import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, struct, sys
sys.path.insert(0, _REPO + '/research/sound/verify')
from namecheck import elf
for root in [_XML2 + '/Sounds/eng', _REPO + '/xml1_xbox/sounds/zsds',
             _REPO + '/research/sound/out/all_ima/eng']:
    ok = bad = empty = 0
    bads = []
    for dp, dn, fn in os.walk(root):
        for f in fn:
            base, ext = os.path.splitext(f)
            if base[-2:] not in ('_a', '_c') or ext not in ('.zss', '.zsm'):
                continue
            d = open(os.path.join(dp, f), 'rb').read()
            c, ko, eo = struct.unpack_from('<III', d, 0x10)
            ks = {struct.unpack_from('<I', d, ko + 8 * j)[0] for j in range(c)}
            if not ks:
                empty += 1
            elif elf('music/' + base) in ks:
                ok += 1
            else:
                bad += 1
                bads.append(f)
    print(root, 'ok', ok, 'bad', bad, 'empty', empty, bads[:10])
