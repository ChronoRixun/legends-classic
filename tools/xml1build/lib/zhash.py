"""ZSND name hash, as implemented in XMen2.exe @0x590280: PJW/ELF hash over toupper(chars) (MSVCR71 toupper via
thunk 0x6723ce), with a seed (used to chain "/***RANDOM***/n" suffixes). Callers first normalise the name
(0x5902d0): backslash -> "/", then lower-case (irrelevant for the hash since it upper-cases)."""

def elf_hash(s, h=0):
    if isinstance(s, str):
        s = s.encode('latin1')
    for c in s:
        if 0x61 <= c <= 0x7a:
            c -= 0x20
        h = ((h << 4) + c) & 0xffffffff
        g = h & 0xf0000000
        if g:
            h ^= g >> 24
        h &= ~g & 0xffffffff
    return h

if __name__ == '__main__':
    import sys
    for a in sys.argv[1:]:
        print('%08x %s' % (elf_hash(a), a))
