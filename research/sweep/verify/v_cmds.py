"""Enumerate console-command registrations: 'push <handler>; push <name>; mov ecx,eax; call [edx+0x10|0xc]'
preceded by a call to the console singleton. Prints registered names. usage: v_cmds.py x1|x2"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys, struct, re, capstone, json
sys.path.insert(0, _REPO + r'/research/sweep/verify')
from v_img import Img, X1, X2

g = sys.argv[1]
im = Img(X1 if g == 'x1' else X2)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.skipdata = True
names = {}
for va, vs, raw, rs, nm, fl in im.secs:
    if nm != '.text':
        continue
    code = im.b[raw:raw + min(vs, rs)]
    # byte pattern: 68 xx xx xx xx 68 yy yy yy yy 8b c8 ff 52 (10|0c)
    for m in re.finditer(rb'\x68(....)\x68(....)\x8b\xc8\xff\x52([\x0c\x10\x14\x18])', code, re.S):
        h = struct.unpack('<I', m.group(1))[0]
        n = struct.unpack('<I', m.group(2))[0]
        s = im.cstr(n, 80)
        if s and re.match(rb'^[A-Za-z_][A-Za-z0-9_]*$', s):
            names.setdefault(s.decode(), []).append((hex(va + m.start()), hex(h), m.group(3).hex()))
print(len(names), 'registered names')
json.dump(names, open(_REPO + r'/research/sweep/verify/v_cmds_%s.json' % g, 'w'), indent=0, sort_keys=True)
for q in sys.argv[2:]:
    print(q, [(k, v) for k, v in names.items() if q.lower() in k.lower()])
