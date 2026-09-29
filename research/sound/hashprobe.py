import sys, zsnd
from zhash import elf_hash

def keys(path):
    b = zsnd.load(path, strict=False)
    ks = {}
    for s in b.sounds:
        for h in s.hashes:
            ks[h] = ('sound', s.index)
    for t in b.tracks:
        for h in t.hashes:
            ks[h] = ('track', t.index)
    return b, ks

def probe(path, names):
    b, ks = keys(path)
    for n in names:
        h = elf_hash(n)
        r = [ks.get(h)]
        for i in range(4):
            r.append(ks.get(elf_hash('/***RANDOM***/%d' % i, h)))
        print('%-50s %08x %s' % (n, h, r))

if __name__ == '__main__':
    probe(sys.argv[1], sys.argv[2:])
