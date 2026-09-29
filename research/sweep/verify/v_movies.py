"""Walk MPEG-PS packs of every .sfd in both games: stream ids, first ADX header per audio stream,
MPEG-1 sequence header size, SofdecStream marker."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, struct, collections, sys

roots = {'xml1': _REPO + r'/xml1_xbox/movies', 'xml2': _XML2 + r'/Movies'}


def scan(p, limit=4 << 20):
    b = open(p, 'rb').read(limit)
    streams = collections.Counter()
    first = {}
    i = 0
    seq = None
    sofdec = b.find(b'SofdecStream')
    ver = b[sofdec + 12:sofdec + 16].hex() if sofdec >= 0 else None
    while True:
        i = b.find(b'\x00\x00\x01', i)
        if i < 0 or i + 6 > len(b):
            break
        sid = b[i + 3]
        if sid == 0xba:
            i += 12 if (b[i + 4] >> 4) == 2 else 14
            continue
        if sid == 0xb3 and seq is None:
            w = (b[i + 4] << 4) | (b[i + 5] >> 4)
            h = ((b[i + 5] & 15) << 8) | b[i + 6]
            seq = (w, h)
        if sid >= 0xbb:
            ln = struct.unpack_from('>H', b, i + 4)[0]
            if 0xc0 <= sid <= 0xdf:
                streams[hex(sid)] += 1
                if sid not in first:
                    # MPEG-1 PES header: skip stuffing, STD, PTS/DTS
                    j = i + 6
                    while b[j] == 0xff:
                        j += 1
                    if (b[j] & 0xc0) == 0x40:
                        j += 2
                    if (b[j] & 0xf0) == 0x20:
                        j += 5
                    elif (b[j] & 0xf0) == 0x30:
                        j += 10
                    else:
                        j += 1
                    first[sid] = b[j:j + 8].hex()
            elif 0xe0 <= sid <= 0xef:
                streams[hex(sid)] += 1
            i += 6 + ln
            continue
        i += 3
    return seq, ver, dict(streams), {hex(k): v for k, v in first.items()}


summary = collections.Counter()
for g, r in roots.items():
    for d, _, fs in os.walk(r):
        for f in sorted(fs):
            if f.lower().endswith('.sfd'):
                seq, ver, st, first = scan(os.path.join(d, f))
                key = (g, seq, ver, tuple(sorted(st)), tuple(sorted((k, v[:4] if v.startswith('8000') else v[:8]) for k, v in first.items())))
                summary[key + (d.replace(chr(92), '/').split('/movies/')[-1].split('/')[0] if g == 'xml1' else '',)] += 1
for k, v in sorted(summary.items()):
    print(v, k)
