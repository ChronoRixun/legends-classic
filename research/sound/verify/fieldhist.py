import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, struct, collections
ROOTS = {'xml2': _XML2 + '/Sounds/eng', 'xml1': _REPO + '/xml1_xbox/sounds/zsds'}
for g, root in ROOTS.items():
    H = [collections.Counter() for _ in range(24)]
    S = collections.defaultdict(collections.Counter)
    T = [collections.Counter() for _ in range(16)]
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if not f.endswith(('.zsm', '.zss')):
                continue
            d = open(os.path.join(dp, f), 'rb').read()
            pc = d[:8] == b'ZSNDPC  '
            c, k, e = struct.unpack_from('<III', d, 0x10)
            for i in range(c):
                ent = d[e + 24 * i:e + 24 * i + 24]
                for j in range(2, 24):
                    H[j][ent[j]] += 1
            c, k, e = struct.unpack_from('<III', d, 0x10 + 12)
            ss = 24 if pc else 28
            for i in range(c):
                ent = d[e + ss * i:e + ss * i + ss]
                for j in range(3, ss):
                    if j in (4, 5, 6, 7):
                        continue
                    S[j][ent[j]] += 1
            c, k, e = struct.unpack_from('<III', d, 0x10 + 12 * 4)
            if not pc:
                for i in range(c):
                    ent = d[e + 16 * i:e + 16 * i + 16]
                    for j in list(range(0, 8)) + list(range(12, 16)):
                        T[j][ent[j]] += 1
    print('=====', g)
    print('sound entry byte histograms (pos: top values):')
    for j in range(2, 24):
        print('  %2d' % j, {hex(a): b for a, b in H[j].most_common(6)})
    print('sample entry non-index bytes:', {j: {hex(a): b for a, b in S[j].most_common(4)} for j in sorted(S)})
    if g == 'xml1':
        print('track entry bytes:', {j: {hex(a): b for a, b in T[j].most_common(4)} for j in range(16) if T[j]})
