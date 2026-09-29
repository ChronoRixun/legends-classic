"""every instruction in .text that touches [reg+0x254] as a byte (skin prefix field) - look for range compares"""
import re
from exe import img, BASE, pe, md
text = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
t0, t1 = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize
code = img[t0:t1]
# linear sweep is unreliable; instead find byte patterns containing disp32 0x254 and disassemble from a few offsets back
hits = set()
for m in re.finditer(re.escape(b'\x54\x02\x00\x00'), code):
    for back in range(2, 8):
        st = m.start() - back
        ins = next(md.disasm(code[st:st + 16], BASE + t0 + st), None)
        if ins and ins.size >= back + 4 and '0x254]' in ins.op_str:
            hits.add((ins.address, ins.mnemonic, ins.op_str))
            break
for a, mn, op in sorted(hits):
    if 'byte' in op:
        print(f'{a:08x} {mn} {op}')
print(len(hits))
