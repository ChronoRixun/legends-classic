"""Field histograms of every table entry across all banks of both games."""
import struct, collections, sys
from explore import hdr
from survey import ROOTS, files

ESZ = {b'ZSNDPC  ': (24, 24, 76, 16), b'ZSNDXBOX': (24, 28, 84, 16)}

def u16s(b):
    return struct.unpack('<%dH' % (len(b) // 2), b)

for plat, root in ROOTS.items():
    hist = collections.defaultdict(collections.Counter)
    for p in files(root):
        d, magic, fsize, f0c, tabs = hdr(p)
        es = ESZ[magic]
        import os; b = os.path.basename(p); suf = b.rsplit('_', 1)[1] if '_' in b else b
        for ti, name in ((0, 'snd'), (1, 'smp'), (2, 'file'), (4, 'trk')):
            cnt, ko, vo = tabs[ti]
            sz = es[ti if ti < 3 else 3]
            for i in range(cnt):
                e = d[vo + i * sz: vo + (i + 1) * sz]
                if name == 'file':
                    nlen = 64
                    head = e[:sz - nlen]
                    for j, v in enumerate(struct.unpack('<%dI' % (len(head) // 4), head)):
                        if j >= 2:
                            hist['%s.u32[%d]' % (name, j)][v] += 1
                    nm = e[sz - nlen:].split(b'\0')[0].decode('latin1')
                    ext = nm.rsplit('.', 1)[-1] if '.' in nm else '(none)'
                    hist['file.ext'][ext] += 1
                    hist['file.fmt_by_suffix'][(suf, struct.unpack_from('<I', e, 8)[0])] += 1
                else:
                    for j, v in enumerate(u16s(e)):
                        if name == 'snd' and j == 0:
                            continue
                        if name == 'smp' and j == 0:
                            continue
                        if name == 'trk' and j in (4, 5):
                            continue
                        hist['%s.u16[%d]' % (name, j)][v] += 1
                    if name == 'smp':
                        hist['smp.flags_by_suffix'][(suf, e[2], e[3])] += 1
                    if name == 'snd':
                        hist['snd.flags_by_suffix'][(suf, u16s(e)[1])] += 1
    print('=====', plat)
    for k in sorted(hist):
        c = hist[k]
        items = sorted(c.items(), key=lambda x: -x[1])
        print('%-24s %s%s' % (k, ', '.join('%s:%d' % (hex(a) if isinstance(a, int) else a, b) for a, b in items[:24]), ' ...(%d distinct)' % len(c) if len(c) > 24 else ''))
