"""Disassemble default.xbe (XML1 Xbox) at a VA, annotating string immediates.
usage: xbedis.py <va-hex> <before-hex> <after-hex>"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import re, struct, sys, capstone

b = open(_REPO + r'/xml1_xbox/default.xbe', 'rb').read()
base = struct.unpack_from('<I', b, 0x104)[0]
n, hdr = struct.unpack_from('<II', b, 0x11c)
SECS = []
for i in range(n):
    o = hdr - base + i * 56
    flags, va, vsize, raw, rsize = struct.unpack_from('<IIIII', b, o)
    SECS.append((va, raw, rsize))


def va2off(v):
    for va, raw, size in SECS:
        if va <= v < va + size:
            return raw + v - va


def s(v):
    o = va2off(v)
    if o is None:
        return None
    e = b.find(b'\0', o, o + 200)
    t = b[o:e]
    if e > o and all(32 <= c < 127 for c in t):
        return t.decode()


va = int(sys.argv[1], 16)
before = int(sys.argv[2], 16)
after = int(sys.argv[3], 16)
o = va2off(va - before)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
for ins in md.disasm(b[o:o + before + after], va - before):
    note = ''
    for m in re.finditer(r'0x[0-9a-f]{5,8}', ins.op_str):
        t = s(int(m.group(0), 16))
        if t:
            note += '   ; "%s"' % t
    print('%s %08x  %-7s %s%s' % ('=>' if ins.address == va else '  ', ins.address, ins.mnemonic, ins.op_str, note))
