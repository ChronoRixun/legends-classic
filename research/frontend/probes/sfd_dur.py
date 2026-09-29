"""sfd_dur.py <sfd>... : duration of a Sofdec movie from its first ADX (stream 0xC0) header: total samples / rate."""
import sys, glob, os, struct

def adx_duration(path, limit=4 << 20):
    d = open(path, 'rb').read(limit)
    i = 0
    while True:
        i = d.find(b'\x00\x00\x01\xc0', i)
        if i < 0:
            return None
        plen = struct.unpack_from('>H', d, i + 4)[0]
        body = d[i + 6:i + 6 + plen]
        # skip MPEG-1 packet header stuffing / PTS
        j = 0
        while j < len(body) and body[j] == 0xFF:
            j += 1
        if j < len(body) and (body[j] & 0xC0) == 0x40:
            j += 2
        if j < len(body):
            b = body[j]
            if (b & 0xF0) == 0x20:
                j += 5
            elif (b & 0xF0) == 0x30:
                j += 10
            elif b == 0x0F:
                j += 1
        h = body[j:j + 16]
        if len(h) >= 16 and h[0] == 0x80 and h[1] == 0x00:
            rate = int.from_bytes(h[8:12], 'big')
            samples = int.from_bytes(h[12:16], 'big')
            return samples / rate if rate else None
        i += 4

for pat in sys.argv[1:]:
    for p in sorted(glob.glob(pat)):
        dur = adx_duration(p)
        print(f'{os.path.basename(p)[:-4]:8} {dur:.2f}' if dur else f'{os.path.basename(p)} ?')
