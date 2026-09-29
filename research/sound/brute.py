"""Brute-force sound-key naming: derive candidate names from the bank's own file names."""
import sys, itertools, re, zsnd
from zhash import elf_hash

def main(path, prefixes):
    b = zsnd.load(path, strict=False)
    ks = {}
    for s in b.sounds:
        for h in s.hashes:
            ks[h] = ('sound', s.index)
    for t in b.tracks:
        for h in t.hashes:
            ks[h] = ('track', t.index)
    bases = set()
    for f in b.files:
        n = b.file_name(f).rsplit('.', 1)[0]
        bases.add(n)
        m = re.match(r'(.*)_([a-z0-9])$', n)
        if m:
            bases.add(m.group(1))
    found = {}
    sufs = [''] + ['%s%s' % (sep, x) for sep in ('', '_', '/', '-') for x in list('0123456789abcdefgh')] + ['/***RANDOM***/%d' % i for i in range(8)]
    for pre in prefixes:
        for base in bases:
            for suf in sufs:
                n = pre + base + suf
                h = elf_hash(n)
                if h in ks:
                    found[h] = (n, ks[h])
    print(path, 'keys', len(ks), 'found', len(found))
    for h, (n, k) in sorted(found.items(), key=lambda x: x[1][0])[:400]:
        print('  %08x %-60s %s' % (h, n, k))
    miss = [(h, k) for h, k in ks.items() if h not in found]
    print(' missing', len(miss), [('%08x' % h, k) for h, k in miss[:30]])

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:] or [''])
