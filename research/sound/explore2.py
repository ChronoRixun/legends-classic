import struct, sys
from explore import hdr

ESZ = {b'ZSNDPC  ': (24, 24, 76, 16), b'ZSNDXBOX': (24, 28, 84, 16)}

def main(p, n=6):
    d, magic, fsize, f0c, tabs = hdr(p)
    print(p, magic, len(d), hex(fsize), hex(f0c))
    names = ['sounds', 'samples', 'files', 't3', 't4', 't5', 't6']
    for ti, (cnt, ko, vo) in enumerate(tabs):
        if not cnt:
            continue
        # entry size
        if ti < 6:
            nxt = None
        esz = None
        # derive entry size from next table's keys offset
        ends = sorted(set([t[1] for t in tabs] + [t[2] for t in tabs] + [f0c]))
        end = min(e for e in ends if e > vo) if any(e > vo for e in ends) else f0c
        esz = (end - vo) // cnt
        print(' %s cnt=%d keys=%#x vals=%#x esz=%s (rem %d)' % (names[ti], cnt, ko, vo, esz, (end - vo) % cnt))
        for i in range(min(cnt, n)):
            k, idx = struct.unpack_from('<II', d, ko + i * 8)
            e = d[vo + i * esz: vo + (i + 1) * esz]
            print('   key %08x -> %3d | %s' % (k, idx, e.hex(' ')))

if __name__ == '__main__':
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    main(sys.argv[1], n)
