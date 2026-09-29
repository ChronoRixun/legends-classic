"""dump_text.py <exe|xbe> <out.txt> : linear-sweep disassemble .text into a greppable listing.
Each line: 'VA  mnemonic op_str [; "string"]'. Uses skipdata so it resyncs over padding/data."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capstone
from binimg import Image

img = Image(sys.argv[1])
lo, hi = img.text
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.skipdata = True
code = bytes(img.mem[lo - img.base:hi - img.base])
hexre = re.compile(r'0x([0-9a-f]{5,8})')
with open(sys.argv[2], 'w', encoding='utf-8') as f:
    for addr, size, mn, op in md.disasm_lite(code, lo):
        note = ''
        if '0x' in op:
            for m in hexre.finditer(op):
                v = int(m.group(1), 16)
                if img.ok(v) and not (lo <= v < hi):
                    s = img.cstr(v, 60)
                    if s and len(s) >= 2:
                        note = f' ; "{s}"'
                        break
        f.write(f'{addr:08x} {mn} {op}{note}\n')
