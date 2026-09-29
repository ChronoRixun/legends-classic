"""xrefs.py <exe|xbe> <lo-hex> [hi-hex] : list E8/E9 rel32 calls/jumps whose target lies in [lo, hi]."""
import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from binimg import Image

img = Image(sys.argv[1])
lo = int(sys.argv[2], 16)
hi = int(sys.argv[3], 16) if len(sys.argv) > 3 else lo
tlo, thi = img.text
m = img.mem
for va in range(tlo, thi - 5):
    o = va - img.base
    op = m[o]
    if op in (0xE8, 0xE9):
        t = (va + 5 + struct.unpack_from('<i', m, o + 1)[0]) & 0xFFFFFFFF
        if lo <= t <= hi:
            print(f'{va:08x}: {"call" if op == 0xE8 else "jmp "} {t:08x}')
