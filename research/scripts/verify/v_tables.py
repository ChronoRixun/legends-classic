"""Independent check of script function tables in XMen2.exe and default.xbe.
Reads the raw table at given VA, walks entries of 16 bytes until the shape breaks."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import struct, sys, json
import pefile

XML2 = _XML2 + '/XMen2.exe'
XBEP = _REPO + '/xml1_xbox/default.xbe'


class PE:
    def __init__(self, p):
        pe = pefile.PE(p)
        self.base = pe.OPTIONAL_HEADER.ImageBase
        self.mem = bytes(pe.get_memory_mapped_image())
        self.secs = [(s.Name.rstrip(b'\0').decode(), self.base + s.VirtualAddress, s.Misc_VirtualSize) for s in pe.sections]

    def ok(self, va):
        return self.base <= va < self.base + len(self.mem)

    def u32(self, va):
        return struct.unpack_from('<I', self.mem, va - self.base)[0]

    def cs(self, va, n=80):
        if not self.ok(va):
            return None
        o = va - self.base
        e = self.mem.find(b'\0', o, o + n)
        if e < 0:
            return None
        try:
            return self.mem[o:e].decode('ascii')
        except Exception:
            return None


class XBE:
    def __init__(self, p):
        d = open(p, 'rb').read()
        base, = struct.unpack_from('<I', d, 0x104)
        nsec, secaddr = struct.unpack_from('<II', d, 0x11C)
        self.base = base
        top = 0
        secs = []
        for i in range(nsec):
            o = secaddr - base + i * 56
            flags, va, vs, ra, rs, na = struct.unpack_from('<IIIIII', d, o)
            nm = d[na - base:d.index(b'\0', na - base)].decode()
            secs.append((nm, va, vs, ra, rs))
            top = max(top, va + vs)
        mem = bytearray(top - base)
        hdr = struct.unpack_from('<I', d, 0x108)[0]
        mem[:hdr] = d[:hdr]
        for nm, va, vs, ra, rs in secs:
            n = min(rs, vs)
            mem[va - base:va - base + n] = d[ra:ra + n]
        self.mem = bytes(mem)
        self.secs = [(s[0], s[1], s[2]) for s in secs]

    ok = PE.ok
    u32 = PE.u32
    cs = PE.cs


def walk(img, va, maxn=400):
    out = []
    while len(out) < maxn:
        f, n, r, a = struct.unpack_from('<IIII', img.mem, va - img.base)
        ns = img.cs(n)
        rs = img.cs(r)
        as_ = '' if a == 0 else img.cs(a)
        if ns is None or rs is None or as_ is None or f == 0:
            break
        out.append((va, f, ns, rs, as_))
        va += 16
    return out


if __name__ == '__main__':
    res = {}
    for label, img, tabs in (('xml2', PE(XML2), [0x68a908, 0x6903d8]), ('xml1', XBE(XBEP), [0x3d0b88, 0x3d5620])):
        res[label] = {}
        for t in tabs:
            ents = walk(img, t)
            print(label, hex(t), len(ents), 'first', ents[0][2], 'last', ents[-1][2], 'end', hex(ents[-1][0] + 16))
            # check entry just before the table
            f, n, r, a = struct.unpack_from('<IIII', img.mem, t - 16 - img.base)
            print('   entry before:', hex(f), img.cs(n), img.cs(r), img.cs(a) if a else '')
            res[label][hex(t)] = [(hex(e[0]), hex(e[1]), e[2], e[3], e[4]) for e in ents]
        names = [e[2] for t in res[label].values() for e in t]
        print(label, 'total', len(names), 'unique(ci)', len(set(x.lower() for x in names)))
    json.dump(res, open(_REPO + '/research/scripts/verify/tables.json', 'w'), indent=0)
