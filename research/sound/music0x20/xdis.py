"""Disassemble XML1's default.xbe (or any PE) by VA, or search it for an instruction pattern.

    python xdis.py dis <va> [len]            (default xbe)
    python xdis.py grep <regex> [--pe PATH]  scan .text linearly for instructions matching regex
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import re, sys, os
import capstone
sys.path.insert(0, _REPO + '/research/scripts')
from binimg import Image

XBE = _REPO + '/xml1_xbox/default.xbe'


def dis(img, va, n=0x100):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    for ins in md.disasm(bytes(img.mem[va - img.base: va - img.base + n]), va):
        print(f'   {ins.address:08x}  {ins.mnemonic:7} {ins.op_str}')


def grep(img, pat):
    rx = re.compile(pat)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    lo, hi = img.text
    # linear sweep with resync: disassemble from every function-ish start is overkill; do a plain sweep
    pos = lo
    code = bytes(img.mem[lo - img.base: hi - img.base])
    off = 0
    while off < len(code):
        got = False
        for ins in md.disasm(code[off:off + 0x10000], lo + off):
            s = f'{ins.mnemonic} {ins.op_str}'
            if rx.search(s):
                print(f'{ins.address:08x}  {s}')
            off = ins.address + ins.size - lo
            got = True
        if not got:
            off += 1


if __name__ == '__main__':
    args = sys.argv[1:]
    path = XBE
    if '--pe' in args:
        i = args.index('--pe'); path = args[i + 1]; del args[i:i + 2]
    img = Image(path)
    if args[0] == 'dis':
        dis(img, int(args[1], 16), int(args[2], 0) if len(args) > 2 else 0x100)
    else:
        grep(img, args[1])
