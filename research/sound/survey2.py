import struct, sys, os, collections
from explore import hdr
from survey import ROOTS, files

for plat, root in ROOTS.items():
    for p in files(root):
        d, magic, fsize, f0c, tabs = hdr(p)
        if tabs[4][0] and plat == 'pc':
            print('PC tracks:', p, tabs[4])
        if not tabs[0][0]:
            print(plat, 'empty:', p, len(d), hex(f0c))
