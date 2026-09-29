"""for every `call 0x44b8f0` (stats-manager singleton getter), report a following `call [reg+0x10]`
(FUN_0044c030 = loader that registers names) within the next few instructions, with preceding pushes."""
import struct, re
from exe import img, BASE, pe, md, cstr

text = [s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text'][0]
t0, t1 = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize
sites = []
for off in range(t0, t1 - 5):
    if img[off] == 0xE8 and BASE + off + 5 + struct.unpack_from('<i', img, off + 1)[0] == 0x44b8f0:
        sites.append(BASE + off)
hits = 0
for s in sites:
    ins = list(md.disasm(img[s - BASE:s - BASE + 40], s))[:8]
    pushes = []
    for i in ins[1:]:
        if i.mnemonic == 'push':
            pushes.append(i.op_str)
        if i.mnemonic == 'call':
            if re.fullmatch(r'dword ptr \[e[a-z]x \+ 0x10\]', i.op_str):
                hits += 1
                desc = []
                for p in pushes:
                    try:
                        v = int(p, 16)
                        desc.append(repr(cstr(v)) if BASE <= v < BASE + len(img) else p)
                    except ValueError:
                        desc.append(p)
                print(f'{s:08x}: vt+0x10 pushes={desc}')
            break
print('sites', len(sites), 'vt+0x10 hits', hits)
