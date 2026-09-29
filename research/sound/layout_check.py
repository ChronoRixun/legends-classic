"""Verify the PC data layout rule across ALL XML2 banks: files stored in table order? first at header_size?
padding between files = align to 4? trailing bytes?"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import collections, zsnd

c = collections.Counter()
ex = []
for p in zsnd.iter_banks(_XML2 + '/Sounds/eng'):
    b = zsnd.load(p, strict=False)
    if not b.files:
        continue
    offs = [(f.u32(0), f.u32(4), f.index) for f in b.files]
    in_order = all(offs[i][0] < offs[i + 1][0] for i in range(len(offs) - 1))
    c['table_order' if in_order else 'not_table_order'] += 1
    srt = sorted(offs)
    c['first_at_header' if srt[0][0] == b.header_size else 'first_not_at_header'] += 1
    if srt[0][0] != b.header_size:
        ex.append((p, hex(b.header_size), hex(srt[0][0])))
    for (o1, s1, _), (o2, s2, _) in zip(srt, srt[1:]):
        gap = o2 - (o1 + s1)
        exp = (-(o1 + s1)) % 4
        c['gap_align4' if gap == exp else 'gap_other'] += 1
    end = srt[-1][0] + srt[-1][1]
    c['trail_%d' % (len(b.data) - end)] += 1
    c['hdr_mod4_%d' % (b.header_size % 4)] += 1
    # padding bytes content
print(dict(c))
print(ex[:10])
