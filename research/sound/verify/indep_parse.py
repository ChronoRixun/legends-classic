"""Independent ZSND structural check (does not import the researcher's zsnd.py).
Infers entry sizes from gaps between table spans instead of assuming them."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, struct, sys, collections

ROOTS = {'xml2': _XML2 + '/Sounds/eng', 'xml1': _REPO + '/xml1_xbox/sounds/zsds'}
if len(sys.argv) > 1:
    ROOTS = {'arg%d' % i: a for i, a in enumerate(sys.argv[1:])}


def banks(root):
    for dp, dn, fn in os.walk(root):
        for f in sorted(fn):
            if f.lower().endswith(('.zss', '.zsm')):
                yield os.path.join(dp, f).replace('\\', '/')


for gname, root in ROOTS.items():
    magics = collections.Counter()
    esize = collections.defaultdict(collections.Counter)
    tot = collections.Counter()
    fsize_rel = collections.Counter()
    hsize_rel = collections.Counter()
    fmt = collections.Counter()
    unsorted = 0
    empty = 0
    align = collections.Counter()
    mult = collections.Counter()
    tracks_banks = 0
    file_use = collections.Counter()
    rates = collections.Counter()
    flags = collections.Counter()
    ext_suffix = collections.Counter()
    for p in banks(root):
        d = open(p, 'rb').read()
        tot['banks'] += 1
        magic = d[:8]
        magics[magic] += 1
        fs, hs = struct.unpack_from('<II', d, 8)
        tabs = [struct.unpack_from('<III', d, 0x10 + 12 * i) for i in range(7)]
        if len(d) == 100:
            empty += 1
        # spans: collect all key/entry starts
        starts = []
        for ti, (c, ko, eo) in enumerate(tabs):
            if c:
                starts.append((ko, ti, 'k'))
                starts.append((eo, ti, 'e'))
        # ztrk
        trk_offs = []
        c4, k4, e4 = tabs[4]
        is_pc = magic == b'ZSNDPC  '
        starts.sort()
        # first span must be 0x64
        if starts and starts[0][0] != 0x64:
            tot['first_not_64'] += 1
        # infer sizes
        for i, (o, ti, kind) in enumerate(starts):
            nxt = starts[i + 1][0] if i + 1 < len(starts) else None
            c = tabs[ti][0]
            if nxt is None:
                # last span: end at first ZTRK or header_size
                if c4:
                    # first ztrk offset: track entry +8
                    try:
                        offs = [struct.unpack_from('<I', d, e4 + 16 * j + 8)[0] for j in range(c4)]
                        nxt = min(offs)
                    except struct.error:
                        nxt = hs
                    if nxt > len(d):
                        nxt = hs
                else:
                    nxt = hs
            sz = (nxt - o) / c
            esize[(ti, kind)][sz] += 1
        for ti in range(7):
            tot['t%d' % ti] += tabs[ti][0]
            c, ko, eo = tabs[ti]
            prev = -1
            for j in range(c):
                h, idx = struct.unpack_from('<II', d, ko + 8 * j)
                if h < prev:
                    unsorted += 1
                prev = h
        if c4:
            tracks_banks += 1
        # file entries
        c2, k2, e2 = tabs[2]
        fsz = 76 if is_pc else 84
        c1, k1, e1 = tabs[1]
        ssz = 24 if is_pc else 28
        for j in range(c1):
            fi = struct.unpack_from('<H', d, e1 + ssz * j)[0]
            fl = d[e1 + ssz * j + 2]
            rate = struct.unpack_from('<I', d, e1 + ssz * j + 4)[0]
            file_use[(p, fi)] += 1
            rates[rate] += 1
            flags[fl] += 1
        for j in range(c2):
            off, size, f = struct.unpack_from('<III', d, e2 + fsz * j)
            fmt[f] += 1
            tot['audio_bytes'] += size
            align[off % 0x800 == 0] += 1
            ch = 2 if f == 3 else 1
            mult[size % (36 * ch) == 0] += 1
            if (p, j) not in file_use:
                tot['file_unused'] += 1
        fsize_rel['exact' if fs == len(d) else ('rounded800' if fs == (len(d) + 0x7ff) // 0x800 * 0x800 else 'other:%d-%d' % (fs, len(d)))] += 1
        # header_size vs first audio offset
        if c2:
            first = min(struct.unpack_from('<I', d, e2 + fsz * j)[0] for j in range(c2))
            hsize_rel['hs==first_audio' if hs == first else ('hs<first' if hs < first else 'hs>first')] += 1
        ext_suffix[(os.path.splitext(p)[1].lower(), os.path.splitext(p)[0][-2:])] += 1
    print('=====', gname, root)
    print('magics', dict(magics))
    print('totals', dict(tot), 'empty(100B)', empty, 'banks with tracks', tracks_banks)
    print('inferred entry sizes', {('T%d%s' % k): dict(v) for k, v in sorted(esize.items())})
    print('unsorted key pairs', unsorted)
    print('file_size rel', dict(fsize_rel))
    print('header_size rel', dict(hsize_rel))
    print('file formats', dict(fmt))
    print('2KB aligned', dict(align), 'size multiple of 36*ch', dict(mult))
    print('file use counts', collections.Counter(file_use.values()))
    print('rates', dict(rates))
    print('sample flags', {hex(k): v for k, v in flags.items()})
    print('ext/suffix', dict(ext_suffix))
