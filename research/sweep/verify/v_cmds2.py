"""Broader scan: after every call to the console singleton getter, collect string immediates pushed
in the next 8 instructions and the vtable slot called. usage: v_cmds2.py x1|x2 getter_hex"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys, struct, re, capstone, collections
sys.path.insert(0, _REPO + r'/research/sweep/verify')
from v_img import Img, X1, X2

g = sys.argv[1]
getter = int(sys.argv[2], 16)
im = Img(X1 if g == 'x1' else X2)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
slots = collections.Counter()
out = []
for va, vs, raw, rs, nm, fl in im.secs:
    if nm != '.text':
        continue
    code = im.b[raw:raw + min(vs, rs)]
    i = code.find(b'\xe8')
    while i >= 0:
        if i + 5 <= len(code) and va + i + 5 + struct.unpack_from('<i', code, i + 1)[0] == getter:
            strs = []
            slot = None
            for ins in md.disasm(code[i + 5:i + 60], va + i + 5, count=8):
                if ins.mnemonic == 'push' and ins.op_str.startswith('0x'):
                    s = im.cstr(int(ins.op_str, 16), 120)
                    if s is not None and len(s) > 0 and all(32 <= c < 127 for c in s):
                        strs.append(s.decode())
                if ins.mnemonic == 'call':
                    slot = ins.op_str
                    break
            slots[slot] += 1
            out.append((hex(va + i), slot, strs))
        i = code.find(b'\xe8', i + 1)
print('calls to getter', len(out))
print('slots', slots.most_common(12))
for q in sys.argv[3:]:
    for o in out:
        if any(q.lower() in s.lower() for s in o[2]):
            print('  ', q, o)
