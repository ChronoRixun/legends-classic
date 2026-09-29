"""dump_img.py <exe|xbe> <va-hex> <count> : dword dump with string decoding (PE or XBE)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from binimg import Image

img = Image(sys.argv[1])
va = int(sys.argv[2], 16)
for i in range(int(sys.argv[3], 0)):
    a = va + 4 * i
    d = img.u32(a)
    s = img.cstr(d, 80) if img.ok(d) else None
    print(f'{a:08x}: {d:08x} {repr(s) if s else ""}')
