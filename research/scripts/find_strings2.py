"""find_strings2.py <exe|xbe> str... : locate NUL-terminated strings and code/data refs to them (PE or XBE)."""
import sys, os, re, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from binimg import Image

img = Image(sys.argv[1])
for name in sys.argv[2:]:
    pat = name.encode() + b'\0'
    for m in re.finditer(re.escape(pat), img.mem):
        off = m.start()
        va = img.base + off
        refs = [img.base + r.start() for r in re.finditer(re.escape(struct.pack('<I', va)), img.mem)]
        # also refs to a string that is a suffix-shared tail are not counted
        print(f'{name!r}: va {va:08x} prevbyte {img.mem[off-1]:02x} refs {[hex(r) for r in refs][:12]}')
