import struct, sys, pefile

STEPS = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
         130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963, 1060,
         1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484,
         7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767]
IDX = [-1, -1, -1, -1, 2, 4, 6, 8]

def off2va(pe, off):
    for s in pe.sections:
        if s.PointerToRawData <= off < s.PointerToRawData + s.SizeOfRawData:
            return pe.OPTIONAL_HEADER.ImageBase + s.VirtualAddress + off - s.PointerToRawData

for path in sys.argv[1:]:
    d = open(path, 'rb').read()
    pe = pefile.PE(path, fast_load=True)
    for name, vals in (('steps', STEPS), ('idx', IDX)):
        for fmt in ('h', 'i'):
            pat = struct.pack('<%d%s' % (len(vals), fmt), *vals)
            i = d.find(pat)
            while i >= 0:
                print(path, name, fmt, 'off %#x va %#x' % (i, off2va(pe, i)))
                i = d.find(pat, i + 1)
    # also search step table partial (first 10)
    for fmt in ('h', 'i'):
        pat = struct.pack('<10' + fmt, *STEPS[:10])
        i = d.find(pat)
        while i >= 0:
            print(path, 'steps10', fmt, 'off %#x va %#x' % (i, off2va(pe, i)))
            i = d.find(pat, i + 1)
    # xbox: IDX with 16 entries
    for fmt in ('h', 'i', 'b'):
        pat = struct.pack('<16' + fmt, *(IDX + IDX))
        i = d.find(pat)
        while i >= 0:
            print(path, 'idx16', fmt, 'off %#x va %#x' % (i, off2va(pe, i)))
            i = d.find(pat, i + 1)
