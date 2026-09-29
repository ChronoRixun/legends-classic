"""finddisp.py <pe> <hex-disp> [<hex-disp-hi>] : linear-sweep disassemble .text and list instructions
whose memory displacement / immediate falls in [lo, hi]. Linear sweep can desync on data in .text,
so treat results as candidates (verify each with disasm.py)."""
import sys, capstone, pefile
from capstone import x86

pe = pefile.PE(sys.argv[1])
lo = int(sys.argv[2], 16)
hi = int(sys.argv[3], 16) if len(sys.argv) > 3 else lo
base = pe.OPTIONAL_HEADER.ImageBase
text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
code = text.get_data()
va0 = base + text.VirtualAddress
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.detail = True
md.skipdata = True
for ins in md.disasm(code, va0):
    if ins.id == 0:
        continue
    for op in ins.operands:
        v = None
        if op.type == x86.X86_OP_MEM:
            v = op.mem.disp & 0xffffffff
        elif op.type == x86.X86_OP_IMM:
            v = op.imm & 0xffffffff
        if v is not None and lo <= v <= hi:
            print(f'{ins.address:08x}  {ins.mnemonic:6} {ins.op_str}')
            break
