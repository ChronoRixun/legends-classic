"""Small PE helpers: xrefs to a VA (imm32 scan), disassembly of a function by VA.
usage:
  python peutil.py xref <pe> <va-hex> [...]
  python peutil.py dis <pe> <va-hex> [nbytes]
  python peutil.py func <pe> <va-hex>        (find function start by scanning back to CC/90 padding, disasm to ret)
  python peutil.py strx <pe> <string>        (find string VA then xrefs)
"""
import sys, struct, pefile, capstone

_cache = {}

def load(path):
    if path not in _cache:
        pe = pefile.PE(path)
        img = pe.get_memory_mapped_image()
        _cache[path] = (pe, img)
    return _cache[path]

def text_range(pe):
    for s in pe.sections:
        if s.Characteristics & 0x20000000:
            return s.VirtualAddress, s.VirtualAddress + s.Misc_VirtualSize
    raise RuntimeError

def xrefs(path, va):
    pe, img = load(path)
    base = pe.OPTIONAL_HEADER.ImageBase
    pat = struct.pack('<I', va)
    out = []
    i = img.find(pat)
    while i >= 0:
        out.append(base + i)
        i = img.find(pat, i + 1)
    # call/jmp rel32
    lo, hi = text_range(pe)
    for j in range(lo, hi - 5):
        if img[j] in (0xE8, 0xE9):
            rel = struct.unpack_from('<i', img, j + 1)[0]
            if base + j + 5 + rel == va:
                out.append(('call' if img[j] == 0xE8 else 'jmp', base + j))
    return out

def dis(path, va, n=0x100):
    pe, img = load(path)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    rva = va - base
    return list(md.disasm(img[rva:rva + n], va))

def func_start(path, va):
    pe, img = load(path)
    base = pe.OPTIONAL_HEADER.ImageBase
    rva = va - base
    j = rva
    while j > 0:
        if img[j - 1] in (0xCC, 0x90) and img[j] not in (0xCC, 0x90):
            # check alignment 16
            if j % 16 == 0:
                return base + j
        j -= 1
    return None

def pr(insns, stop_ret=False):
    for ins in insns:
        print(f'{ins.address:08x}  {ins.bytes.hex():20s} {ins.mnemonic:7} {ins.op_str}')
        if stop_ret and ins.mnemonic == 'ret':
            break

if __name__ == '__main__':
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == 'xref':
        for a in sys.argv[3:]:
            va = int(a, 16)
            for r in xrefs(path, va):
                if isinstance(r, tuple):
                    print('%08x <- %s %08x  (func %s)' % (va, r[0], r[1], hex(func_start(path, r[1]) or 0)))
                else:
                    print('%08x <- data/imm @%08x  (func %s)' % (va, r, hex(func_start(path, r) or 0)))
    elif cmd == 'dis':
        va = int(sys.argv[3], 16)
        n = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0x100
        pr(dis(path, va, n))
    elif cmd == 'func':
        va = int(sys.argv[3], 16)
        s = func_start(path, va)
        n = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0x800
        print('func start', hex(s))
        pr(dis(path, s, n), stop_ret=False)
    elif cmd == 'strx':
        pe, img = load(path)
        base = pe.OPTIONAL_HEADER.ImageBase
        s = sys.argv[3].encode() + b'\0'
        i = img.find(s)
        while i >= 0:
            if i == 0 or img[i - 1] == 0 or True:
                print('string @%08x' % (base + i))
                for r in xrefs(path, base + i):
                    if not isinstance(r, tuple):
                        print('   <- @%08x (func %s)' % (r, hex(func_start(path, r) or 0)))
            i = img.find(s, i + 1)
