"""Disassemble the sound module range of XMen2.exe linearly (function by function is hard; do a sliding linear
sweep from several starts) and list every instruction with immediate 0x6a or referencing [reg+8] of a file entry."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import pefile, capstone
pe = pefile.PE(_XML2 + '/XMen2.exe')
img = pe.get_memory_mapped_image()
b = 0x400000
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.skipdata = True
hits = set()
for lo, hi in ((0x58d000, 0x598000), (0x615000, 0x618000)):
    for start in range(lo, lo + 16):
        for ins in md.disasm(img[start - b:hi - b], start):
            if ins.mnemonic in ('cmp', 'sub', 'test') and ins.op_str.endswith(', 0x6a'):
                hits.add((ins.address, ins.mnemonic, ins.op_str))
for h in sorted(hits):
    print('%08x %s %s' % h)
