"""Find string offsets/VA in a PE and references (push imm32 / mov imm32) to them."""
import sys, pefile, struct, re

pe = pefile.PE(sys.argv[1])
base = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
for name in sys.argv[2:]:
    pat = name.encode() + b'\0'
    for m in re.finditer(re.escape(pat), img):
        rva = m.start()
        if rva > 0 and img[rva - 1] != 0:
            continue
        va = base + rva
        refs = [r.start() for r in re.finditer(re.escape(struct.pack('<I', va)), img)]
        print(f'{name!r}: rva {rva:08x} va {va:08x} refs {[hex(base + r) for r in refs][:10]}')
