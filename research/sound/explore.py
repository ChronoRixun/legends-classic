import struct, sys, os, glob

def hdr(path):
    d = open(path, 'rb').read()
    magic = d[:8]
    fsize, f0c = struct.unpack_from('<II', d, 8)
    tabs = []
    for i in range(7):
        tabs.append(struct.unpack_from('<III', d, 0x10 + i * 12))
    return d, magic, fsize, f0c, tabs

if __name__ == '__main__':
    for p in sys.argv[1:]:
        d, magic, fsize, f0c, tabs = hdr(p)
        print(p, magic, len(d), hex(fsize), hex(f0c))
        for i, t in enumerate(tabs):
            print('  tab%d cnt=%d keys=%#x vals=%#x' % (i, t[0], t[1], t[2]))
