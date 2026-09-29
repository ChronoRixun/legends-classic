"""dump_dwords.py <pe> <va-hex> <count> : print dwords with string decoding if pointer to ascii."""
import sys, pefile, struct

pe = pefile.PE(sys.argv[1])
base = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
va = int(sys.argv[2], 16)
n = int(sys.argv[3], 0)


def s_at(v):
    r = v - base
    if 0 <= r < len(img):
        e = img.find(b'\0', r, r + 80)
        if e > r:
            s = img[r:e]
            if all(32 <= c < 127 for c in s):
                return s.decode()
    return None


for i in range(n):
    a = va + 4 * i
    d = struct.unpack_from('<I', img, a - base)[0]
    s = s_at(d)
    print(f'{a:08x}: {d:08x} {repr(s) if s else ""}')
