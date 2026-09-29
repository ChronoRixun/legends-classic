"""dis.py <exe|xbe> <va-hex> [len] [--stop-ret] : disassemble by VIRTUAL ADDRESS (PE or XBE).
Annotates immediate operands that point at ASCII strings."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capstone
from binimg import Image

img = Image(sys.argv[1])
va = int(sys.argv[2], 16)
n = int(sys.argv[3], 0) if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else 0x100
stop = '--stop-ret' in sys.argv
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
o = va - img.base
for ins in md.disasm(bytes(img.mem[o:o + n]), va):
    note = ''
    for m in re.finditer(r'0x([0-9a-f]{5,8})', ins.op_str):
        v = int(m.group(1), 16)
        if img.ok(v):
            s = img.cstr(v, 60)
            if s and len(s) >= 2:
                note += f'  ; "{s}"'
    print(f'  {ins.address:08x}  {ins.mnemonic:7} {ins.op_str}{note}')
    if stop and ins.mnemonic == 'ret':
        break
