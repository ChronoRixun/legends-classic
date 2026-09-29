"""verifier helper: disassemble VA ranges and read strings/tables from XMen2.exe (read-only)."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys, struct, re, capstone, pefile

EXE = _XML2 + '/XMen2.exe'
pe = pefile.PE(EXE, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.detail = False


def dis(va, before=0x20, after=0x40, out=print):
    start = va - before - BASE
    for ins in md.disasm(img[start:va - BASE + after], BASE + start):
        mark = '=>' if ins.address == va else '  '
        out(f'{mark} {ins.address:08x}  {ins.mnemonic:7} {ins.op_str}')


def cstr(va, n=200):
    o = va - BASE
    e = img.index(b'\0', o)
    return img[o:min(e, o + n)].decode('latin-1')


def u32(va):
    return struct.unpack_from('<I', img, va - BASE)[0]


def find_bytes(pat):
    return [m.start() + BASE for m in re.finditer(re.escape(pat), img)]


def find_str(s):
    return find_bytes(s.encode() + b'\0')


def xrefs_imm(va):
    """addresses of instructions whose bytes contain the 32-bit immediate va (push/mov imm)."""
    pat = struct.pack('<I', va)
    return [m.start() + BASE for m in re.finditer(re.escape(pat), img)]


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'dis':
        dis(int(sys.argv[2], 16), int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x20,
            int(sys.argv[4], 0) if len(sys.argv) > 4 else 0x40)
    elif cmd == 'str':
        for a in sys.argv[2:]:
            print(a, repr(cstr(int(a, 16))))
    elif cmd == 'find':
        for s in sys.argv[2:]:
            locs = find_str(s)
            print(s, [hex(x) for x in locs], 'xrefs:', {hex(x): [hex(y) for y in xrefs_imm(x)] for x in locs})
    elif cmd == 'dw':
        va = int(sys.argv[2], 16)
        n = int(sys.argv[3], 0)
        for i in range(n):
            v = u32(va + 4 * i)
            s = ''
            try:
                if BASE <= v < BASE + len(img):
                    s = repr(cstr(v, 60))
            except Exception:
                pass
            print(f'{va + 4 * i:08x}: {v:08x} {s}')
