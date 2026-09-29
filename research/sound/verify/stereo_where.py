import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, struct, collections, sys
ROOTS = {'xml2': _XML2 + '/Sounds/eng', 'xml1': _REPO + '/xml1_xbox/sounds/zsds',
         'conv': _REPO + '/research/sound/out/all_ima/eng'}
for g, root in ROOTS.items():
    c = collections.Counter()
    ex = collections.defaultdict(list)
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if not f.lower().endswith(('.zsm', '.zss')):
                continue
            p = os.path.join(dp, f)
            d = open(p, 'rb').read()
            pc = d[:8] == b'ZSNDPC  '
            ssz = 24 if pc else 28
            cnt, ko, eo = struct.unpack_from('<III', d, 0x10 + 12)
            for i in range(cnt):
                fl = d[eo + ssz * i + 2]
                rate = struct.unpack_from('<I', d, eo + ssz * i + 4)[0]
                key = (os.path.splitext(f)[1], 'stereo' if fl & 2 else 'mono', rate, hex(fl))
                c[key] += 1
                if len(ex[key]) < 4:
                    ex[key].append(f)
    print('====', g)
    for k in sorted(c):
        print(k, c[k], ex[k])
