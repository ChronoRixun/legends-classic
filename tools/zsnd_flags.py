"""Clear sample-flag bits in a PC ZSND bank in place (e.g. XML1's 0x20 combat-music flag).

usage: zsnd_flags.py <bank> <mask_to_clear_hex>
"""
import os, sys

from xml1build.lib import zsnd  # noqa: E402  (tools/ is this script's folder)

path, mask = sys.argv[1], int(sys.argv[2], 16)
bank = zsnd.load(path)
data = bytearray(open(path, 'rb').read())
_, _, entries_off = zsnd.struct.unpack_from('<III', data, 0x10 + 12 * 1)
size = zsnd.ESIZE[zsnd.MAGIC_PC][1]
changed = 0
for i in range(len(bank.samples)):
    off = entries_off + i * size + 2
    if data[off] & mask:
        data[off] &= ~mask & 0xff
        changed += 1
open(path, 'wb').write(data)
zsnd.load(path)
print(f'{os.path.basename(path)}: cleared {mask:#x} on {changed} sample(s)')
