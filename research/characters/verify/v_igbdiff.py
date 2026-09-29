import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import struct, re
pairs = [(_REPO + '/xml1_loose/actors/5810.igb',
          _REPO + '/research/characters/out/grso_riot_scheme/Actors/19810.IGB'),
         (_REPO + '/xml1_loose/ui/hud/characters/5810.igb',
          _REPO + '/research/characters/out/grso_riot_scheme/UI/HUD/characters/19810.IGB')]
for a, b in pairs:
    x, y = open(a, 'rb').read(), open(b, 'rb').read()
    print(a.split('/')[-1], len(x), len(y), 'magic', x[:0x10].hex())
    diffs = [i for i in range(min(len(x), len(y))) if x[i] != y[i]]
    print(' differing bytes', len(diffs))
    # group into runs, show old/new string at each run
    runs = []
    for i in diffs:
        if runs and i - runs[-1][1] <= 8:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    for s, e in runs:
        # find string start: scan back to after length prefix
        st = s
        while st > 0 and x[st - 1] != 0 and st > s - 20:
            st -= 1
        plen = struct.unpack_from('<I', x, st - 4)[0]
        print(f'  @{st:#x} plen={plen} old={x[st:st+plen]!r} new={y[st:st+plen]!r}')
