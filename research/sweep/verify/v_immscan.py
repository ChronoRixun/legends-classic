"""Scan a code section for instructions with a given displacement/immediate; print addr + text.
usage: v_immscan.py x1|x2 hex1 [hex2 ...]"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys, capstone
sys.path.insert(0, _REPO + r'/research/sweep/verify')
from v_img import Img, X1, X2

im = Img(X1 if sys.argv[1] == 'x1' else X2)
vals = [int(v, 16) for v in sys.argv[2:]]
pats = ['0x%x' % v for v in vals]
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.skipdata = True
for va, vs, raw, rs, nm, fl in im.secs:
    if nm != '.text':
        continue
    code = im.b[raw:raw + min(vs, rs)]
    for ins in md.disasm(code, va):
        ops = ins.op_str
        for p in pats:
            if p in ops and (ops.endswith(p) or (p + ']') in ops or (p + ',') in ops or (' + ' + p) in ops):
                print('%08x  %s %s' % (ins.address, ins.mnemonic, ops))
                break
