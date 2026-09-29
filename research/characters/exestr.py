"""exestr.py <pe> <regex> : list ASCII strings in a PE matching regex, with VA, plus code xrefs
(push imm32 / mov r,imm32 / any 4-byte absolute occurrence in .text)."""
import re, sys, struct, pefile

pe = pefile.PE(sys.argv[1])
pat = re.compile(sys.argv[2].encode(), re.I)
base = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
text = next(s for s in pe.sections if s.Name.startswith(b'.text'))
t0, t1 = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize
tbytes = img[t0:t1]
for m in re.finditer(rb'[\x20-\x7e]{3,}', img):
    s = m.group()
    if not pat.search(s):
        continue
    va = base + m.start()
    needle = struct.pack('<I', va)
    refs = []
    i = tbytes.find(needle)
    while i >= 0 and len(refs) < 12:
        refs.append(hex(base + t0 + i))
        i = tbytes.find(needle, i + 1)
    print(f'{va:08x} {s.decode()!r:60} refs={refs}')
