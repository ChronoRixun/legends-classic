"""find direct call/jmp rel32 sites targeting given VAs in XMen2.exe .text"""
import sys, struct
from exe import img, BASE, pe

text = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
t0 = text.VirtualAddress
t1 = t0 + text.Misc_VirtualSize
targets = {int(a, 16) for a in sys.argv[1:]}
for off in range(t0, t1 - 5):
    op = img[off]
    if op in (0xE8, 0xE9):
        rel = struct.unpack_from('<i', img, off + 1)[0]
        dst = BASE + off + 5 + rel
        if dst in targets:
            print(f'{"call" if op == 0xE8 else "jmp "} {BASE + off:08x} -> {dst:08x}')
