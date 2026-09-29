"""Audio-level sanity over ALL banks: Xbox block alignment/header sanity; PC size/nibble checks."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys, collections, struct
import zsnd

XB = _REPO + '/xml1_xbox/sounds/zsds'
PC = _XML2 + '/Sounds/eng'

def xbox_survey():
    c = collections.Counter()
    bad = []
    for p in zsnd.iter_banks(XB):
        b = zsnd.load(p)
        smp_by_file = {}
        for s in b.samples:
            smp_by_file.setdefault(s.u16(0), []).append(s)
        for f in b.files:
            fmt = f.u32(8)
            ss = smp_by_file.get(f.index, [])
            chs = set(2 if (s.raw[2] & 2) else 1 for s in ss)
            c['files'] += 1
            c['fmt%d' % fmt] += 1
            c['samples_per_file_%d' % len(ss)] += 1
            if len(chs) != 1:
                bad.append((p, f.index, 'channels ambiguous', chs))
                continue
            ch = chs.pop()
            c['fmt%d_ch%d' % (fmt, ch)] += 1
            data = b.file_bytes(f)
            bs = 36 * ch
            if len(data) % bs:
                c['size_not_block_multiple'] += 1
                bad.append((p, f.index, 'size %d %% %d = %d' % (len(data), bs, len(data) % bs)))
            nblk = len(data) // bs
            c['blocks'] += nblk * ch
            for k in range(nblk):
                for ci in range(ch):
                    o = k * bs + 4 * ci
                    idx, res = data[o + 2], data[o + 3]
                    if idx > 88:
                        c['hdr_idx_gt88'] += 1
                    if res:
                        c['hdr_reserved_nonzero'] += 1
            # alignment of offset
            if f.u32(0) % 0x800 == 0:
                c['offset_2k_aligned'] += 1
            elif f.u32(0) % 0x10 == 0:
                c['offset_16_aligned'] += 1
            else:
                c['offset_unaligned'] += 1
    print('XBOX', dict(c))
    for x in bad[:20]:
        print('  ', x)
    print('  bad total', len(bad))

def pc_survey():
    c = collections.Counter()
    for p in zsnd.iter_banks(PC):
        b = zsnd.load(p, strict=False)
        smp_by_file = {}
        for s in b.samples:
            smp_by_file.setdefault(s.u16(0), []).append(s)
        for f in b.files:
            ss = smp_by_file.get(f.index, [])
            c['files'] += 1
            c['samples_per_file_%d' % len(ss)] += 1
            chs = set(2 if (s.raw[2] & 2) else 1 for s in ss)
            ch = chs.pop() if len(chs) == 1 else None
            c['ch%s' % ch] += 1
            if f.u32(0) % 4 == 0:
                c['off_4_aligned'] += 1
            else:
                c['off_unaligned'] += 1
            if f.u32(4) & 1:
                c['odd_size'] += 1
            # name vs sample hash check
    print('PC', dict(c))

if __name__ == '__main__':
    xbox_survey()
    pc_survey()
