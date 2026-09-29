"""Find references to a string in XMen2.exe (PE) or default.xbe (XBE): immediate operands and data pointers.
usage: xref.py <exe|xbe> <string> [--exact]"""
import re, struct, sys

path, s = sys.argv[1], sys.argv[2].encode()
b = open(path, 'rb').read()


def sections():
    if b[:4] == b'XBEH':
        base = struct.unpack_from('<I', b, 0x104)[0]
        n, hdr = struct.unpack_from('<II', b, 0x11c)
        out = []
        for i in range(n):
            o = hdr - base + i * 56
            flags, va, vsize, raw, rsize = struct.unpack_from('<IIIII', b, o)
            out.append((va, raw, rsize))
        return out
    import pefile
    pe = pefile.PE(data=b)
    ib = pe.OPTIONAL_HEADER.ImageBase
    return [(ib + sec.VirtualAddress, sec.PointerToRawData, sec.SizeOfRawData) for sec in pe.sections]


SECS = sections()


def off2va(off):
    for va, raw, size in SECS:
        if raw <= off < raw + size:
            return va + off - raw


def va2off(v):
    for va, raw, size in SECS:
        if va <= v < va + size:
            return raw + v - va


pat = b'\0' + s + b'\0' if '--exact' in sys.argv else s
for m in re.finditer(re.escape(pat), b):
    off = m.start() + (1 if pat[0] == 0 else 0)
    va = off2va(off)
    print('string at off %#x va %#x' % (off, va))
    for r in re.finditer(re.escape(struct.pack('<I', va)), b):
        rva = off2va(r.start())
        ctx = b[r.start() - 1:r.start()]
        print('   ref at off %#x va %#x  prev byte %s  next dwords %s' % (
            r.start(), rva or 0, ctx.hex(), [hex(x) for x in struct.unpack_from('<4I', b, r.start())]))
