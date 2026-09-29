"""Find every direct call/jmp rel32 to a target VA and disassemble a few instructions before it.
usage: v_callers.py xml2|xml1 <target-hex> [before-bytes]"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import sys, struct
sys.path.insert(0, _REPO + '/research/scripts/verify')
from v_tables import PE, XBE, XML2, XBEP
import capstone

which = sys.argv[1]
tgt = int(sys.argv[2], 16)
before = int(sys.argv[3]) if len(sys.argv) > 3 else 24
img = PE(XML2) if which == 'xml2' else XBE(XBEP)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
mem = img.mem
hits = []
for s in img.secs:
    if s[0] not in ('.text',):
        continue
    lo = s[1] - img.base
    hi = lo + s[2]
    for o in range(lo, hi - 5):
        if mem[o] in (0xe8, 0xe9):
            rel = struct.unpack_from('<i', mem, o + 1)[0]
            if img.base + o + 5 + rel == tgt:
                hits.append(img.base + o)
print('callers of', hex(tgt), len(hits))
for h in hits:
    o = h - img.base
    # disassemble from h-before, sync by trying offsets
    best = None
    for st in range(before, 0, -1):
        ins = list(md.disasm(mem[o - st:o + 5], h - st))
        if ins and ins[-1].address == h:
            best = ins
            break
    print('---', hex(h))
    for i in (best or []):
        print('   %08x %s %s' % (i.address, i.mnemonic, i.op_str))
