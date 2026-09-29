"""A/B test skins for the elite Acolytes (build/_skins session 1).

  18805 original (2-weight outline + 2-weight body)            -> expect spikes
  18808 outline padded to 3 weights, body left at 2             -> expect clean if the outline is the culprit
  18806 original (3-weight outline + body)                      -> control, clean
  18807 outline REDUCED from 3 to 2 weights (two largest kept)  -> expect spikes if 2-weight outlines cause them
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os
import struct
import sys

sys.path.insert(0, _REPO + r'-skins\tools')
from xml1build.igb_file import IgbFile          # noqa: E402
from xml1build import skins as SK               # noqa: E402

SRC = _REPO + r'\build\_heroes\Actors'        # pre-fix pipeline output (rename only)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'variants')
os.makedirs(OUT, exist_ok=True)


def reshape(data, select, target):
    f = IgbFile(data)
    blocks = {}
    for geo, va in SK._vertex_arrays(f):
        if not select(geo) or va.name != 'igVertexArray1_1':
            continue
        fmt = va.get(6)
        nw, ni = fmt >> 4 & 15, fmt >> 8 & 15
        if not nw or nw == target:
            continue
        n = va.get(3)
        wb, ib = f.block(va.get(7)), f.block(va.get(8))
        W = struct.unpack_from(f'<{n * nw}f', f.data, wb[0])
        I = f.data[ib[0]:ib[0] + n * ni]
        wo, io = [], bytearray()
        for v in range(n):
            pairs = list(zip(W[v * nw:(v + 1) * nw], I[v * ni:(v + 1) * ni]))
            if target < nw:
                pairs = sorted(pairs, key=lambda p: -p[0])[:target]
                s = sum(w for w, _ in pairs) or 1.0
                pairs = [(w / s, i) for w, i in pairs]
            else:
                pairs = pairs + [(0.0, pairs[0][1])] * (target - nw)
            wo.extend(w for w, _ in pairs)
            io += bytes(i for _, i in pairs)
        blocks[va.get(7)] = struct.pack(f'<{n * target}f', *wo)
        blocks[va.get(8)] = bytes(io)
        struct.pack_into('<I', f.buf, va.fields[6].offset, (fmt & ~0xff0) | target << 4 | target << 8)
        print(f'   {geo}: 0x{fmt:x} -> 0x{(fmt & ~0xff0) | target << 4 | target << 8:x} ({n} vertices)')
    out = f.rebuilt(blocks)
    IgbFile(out)
    return out


def main():
    jobs = {
        '18805': None,
        '18806': None,
        '18808': (lambda g: 'outline' in g.lower(), 3),
        '18807': (lambda g: 'outline' in g.lower(), 2),
    }
    for skin, job in jobs.items():
        data = open(os.path.join(SRC, skin + '.IGB'), 'rb').read()
        print(skin, 'original' if job is None else f'outline -> {job[1]} weights')
        if job is not None:
            data = reshape(data, *job)
        open(os.path.join(OUT, skin + '.IGB'), 'wb').write(data)


if __name__ == '__main__':
    main()
