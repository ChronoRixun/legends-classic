"""Survey sample flags / rates / sizes of every music (_a/_c) bank in XML1 (Xbox) and XML2 (PC)."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import zsnd

ROOTS = {'xml2': _XML2 + '/Sounds/eng', 'xml1': _REPO + '/xml1_xbox/sounds/zsds'}

for game, root in ROOTS.items():
    hist = collections.Counter()
    rows = []
    for p in sorted(zsnd.iter_banks(root)):
        try:
            b = zsnd.load(p, strict=False)
        except Exception as e:
            continue
        for s in b.samples:
            fl = s.raw[2]
            f = b.files[s.u16(0)]
            base = os.path.basename(p)
            key = (base.rsplit('.', 1)[0][-2:], hex(fl), s.u32(4))
            hist[key] += 1
            if fl & 0x20 or (fl & 2):
                rows.append((base, hex(fl), s.u32(4), f.u32(4), len(b.samples)))
    print('==', game)
    for k, v in sorted(hist.items()):
        if k[1] not in ('0x0', '0x1') or k[0] in ('_a', '_c'):
            print('  ', k, v)
    for r in rows:
        print('    ', *r)
