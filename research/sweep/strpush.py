"""Disassemble a function range in a PE and annotate pushed/moved immediates that point at strings.
usage: strpush.py <pe> <va-hex> <length-hex>"""
import sys, capstone, pefile, re

pe = pefile.PE(sys.argv[1])
base = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
va = int(sys.argv[2], 16)
n = int(sys.argv[3], 16)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)


def s(v):
    r = v - base
    if 0 <= r < len(img):
        e = img.find(b'\0', r, r + 200)
        t = img[r:e]
        if e > r and all(32 <= c < 127 for c in t):
            return t.decode()


for ins in md.disasm(img[va - base:va - base + n], va):
    note = ''
    for m in re.finditer(r'0x[0-9a-f]{6,8}', ins.op_str):
        t = s(int(m.group(0), 16))
        if t:
            note += '   ; "%s"' % t
    print('%08x  %-7s %s%s' % (ins.address, ins.mnemonic, ins.op_str, note))
