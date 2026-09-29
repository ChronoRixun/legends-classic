"""Print ASCII strings (with file offset and VA) from a PE, filtered by regex."""
import re, sys, pefile

def strings(path, minlen=4):
    d = open(path, 'rb').read()
    for m in re.finditer(rb'[\x20-\x7e]{%d,}' % minlen, d):
        yield m.start(), m.group().decode('latin1')

def off2va(pe, off):
    for s in pe.sections:
        if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
            return pe.OPTIONAL_HEADER.ImageBase + s.VirtualAddress + off - s.PointerToRawData
    return None

if __name__ == '__main__':
    path, pat = sys.argv[1], sys.argv[2]
    pe = pefile.PE(path, fast_load=True)
    rx = re.compile(pat, re.I)
    for off, s in strings(path):
        if rx.search(s):
            va = off2va(pe, off)
            print('%08x %s %s' % (off, ('%08x' % va) if va else '--------', s))
