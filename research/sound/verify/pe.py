"""pe.py <exe|xbe-alias> cmd args
cmds: ptrs <va> <n>   dump n dwords with string deref
      iat <va>        name the import at IAT slot va
      dis <va> <n>    disasm n bytes
      xref <va>       imm32 refs + call/jmp rel32 refs
      str <va>...
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys, struct, pefile, capstone
EXE = _XML2 + '/XMen2.exe'
path = sys.argv[1]
if path == 'exe':
    path = EXE
pe = pefile.PE(path)
img = pe.get_memory_mapped_image()
b = pe.OPTIONAL_HEADER.ImageBase
cmd = sys.argv[2]
a = sys.argv[3:]


def s_at(v):
    if b <= v < b + len(img):
        return img[v - b:v - b + 48].split(b'\0')[0]
    return None


if cmd == 'ptrs':
    va = int(a[0], 16)
    for i in range(int(a[1])):
        v = struct.unpack_from('<I', img, va - b + 4 * i)[0]
        print('%08x: %08x %r' % (va + 4 * i, v, s_at(v)))
elif cmd == 'iat':
    iat = {}
    for e in pe.DIRECTORY_ENTRY_IMPORT:
        for i in e.imports:
            iat[i.address] = (e.dll, i.name)
    for x in a:
        print(x, iat.get(int(x, 16)))
elif cmd == 'dis':
    va = int(a[0], 16)
    n = int(a[1], 0)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    for ins in md.disasm(img[va - b:va - b + n], va):
        extra = ''
        for tok in ins.op_str.replace('[', ' ').replace(']', ' ').replace(',', ' ').split():
            if tok.startswith('0x') and len(tok) >= 8:
                s = s_at(int(tok, 16))
                if s and len(s) >= 3 and all(32 <= c < 127 for c in s):
                    extra = '   ; %r' % s
        print('%08x  %-7s %s%s' % (ins.address, ins.mnemonic, ins.op_str, extra))
elif cmd == 'xref':
    for x in a:
        va = int(x, 16)
        pat = struct.pack('<I', va)
        i = img.find(pat)
        while i >= 0:
            print('imm/data @%08x' % (b + i))
            i = img.find(pat, i + 1)
        for s in pe.sections:
            if s.Characteristics & 0x20000000:
                lo, hi = s.VirtualAddress, s.VirtualAddress + s.Misc_VirtualSize
                for j in range(lo, hi - 5):
                    if img[j] in (0xE8, 0xE9):
                        rel = struct.unpack_from('<i', img, j + 1)[0]
                        if b + j + 5 + rel == va:
                            print('%s @%08x' % ('call' if img[j] == 0xE8 else 'jmp', b + j))
elif cmd == 'str':
    for x in a:
        print(x, s_at(int(x, 16)))
