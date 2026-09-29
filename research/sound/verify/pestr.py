import sys, pefile
pe = pefile.PE(sys.argv[1])
img = pe.get_memory_mapped_image()
base = pe.OPTIONAL_HEADER.ImageBase
for a in sys.argv[2:]:
    if a.startswith('find:'):
        s = a[5:].encode()
        i = img.find(s)
        while i >= 0:
            print('%08x %r' % (base + i, img[i:i + 48].split(b'\0')[0]))
            i = img.find(s, i + 1)
        continue
    va = int(a, 16)
    r = va - base
    print('%08x %r' % (va, img[r:r + 64].split(b'\0')[0]))
