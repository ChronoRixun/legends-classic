"""Compare instruction streams (mnemonics + operand shapes) of two code windows: XBE vs PC exe."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys, capstone, re
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)

def norm(ins):
    ops = re.sub(r'0x[0-9a-f]{5,}', 'ADDR', ins.op_str)
    return ins.mnemonic + ' ' + ops

def window(path, off, before, after):
    d = open(path, 'rb').read()
    return [norm(i) for i in md.disasm(d[off - before: off + after], 0)]

xbe = _REPO + '/xml1_xbox/default.xbe'
exe = _XML2 + '/XMen2.exe'
pairs = [(0x17f1f3, 0x193623), (0x17ed49, 0x193179)]
for xo, eo in pairs:
    for before in range(0x40, 0x60):
        a = window(xbe, xo, before, 0x300)
        b = window(exe, eo, 0x40, 0x300)
    a = window(xbe, xo, 0, 0x400)
    b = window(exe, eo, 0, 0x400)
    n = min(len(a), len(b))
    same = sum(1 for i in range(n) if a[i] == b[i])
    first_diff = next((i for i in range(n) if a[i] != b[i]), None)
    print('xbe %#x vs exe %#x: %d/%d identical normalized instructions, first diff at #%s' % (xo, eo, same, n, first_diff))
    if first_diff is not None:
        for i in range(max(0, first_diff - 2), min(n, first_diff + 4)):
            print('   ', a[i], '|', b[i])
