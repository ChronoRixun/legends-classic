"""Disassemble a range of a PE by RVA: disasm.py <pe> <rva> [before] [after]"""
import sys, capstone, pefile
pe = pefile.PE(sys.argv[1])
rva = int(sys.argv[2], 16)
before = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x40
after = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0x40
base = pe.OPTIONAL_HEADER.ImageBase
data = pe.get_memory_mapped_image()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
start = rva - before
for ins in md.disasm(data[start:rva + after], base + start):
    mark = '=>' if ins.address == base + rva else '  '
    print(f'{mark} {ins.address:08x}  {ins.mnemonic:7} {ins.op_str}')
