"""Compare CRI Sofdec (.sfd) headers: XML1 Xbox vs XML2 PC.
Reports: MPEG pack type (MPEG-1 0x21.. vs MPEG-2 0x44..), 'SofdecStream' signature, video resolution / frame rate /
MPEG-2 extension presence (from the first sequence header), audio stream ids and whether the audio payload is ADX
(0x8000 header + '(c)CRI'), AIX ('AIXF') or other, file sizes."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import json, os, re, struct

X1M = _REPO + r'/xml1_xbox/movies'
X2M = _XML2 + r'/Movies'
FR = {1: 23.976, 2: 24, 3: 25, 4: 29.97, 5: 30, 6: 50, 7: 59.94, 8: 60}


def info(p):
    b = open(p, 'rb').read(4 * 1024 * 1024)
    size = os.path.getsize(p)
    r = {'size': size}
    if b[:4] == b'\x00\x00\x01\xba':
        r['pack'] = 'mpeg2' if (b[4] & 0xC0) == 0x40 else ('mpeg1' if (b[4] & 0xF0) == 0x20 else hex(b[4]))
    else:
        r['pack'] = 'not-ps:' + b[:4].hex()
    r['sofdec_sig'] = b'SofdecStream' in b[:0x4000]
    m = re.search(rb'SofdecStream[^\0]{0,40}', b[:0x4000])
    if m:
        r['sofdec_str'] = m.group(0).decode('latin-1', 'replace')
    i = b.find(b'\x00\x00\x01\xb3')
    if i >= 0:
        w = (b[i + 4] << 4) | (b[i + 5] >> 4)
        h = ((b[i + 5] & 0xF) << 8) | b[i + 6]
        r['video'] = '%dx%d' % (w, h)
        r['fps'] = FR.get(b[i + 7] & 0xF)
        r['mpeg2_video'] = b.find(b'\x00\x00\x01\xb5', i, i + 200) >= 0
    # walk the program stream properly: pack headers + PES packets with explicit lengths
    pos, streams, first = 0, {}, {}
    while pos + 6 <= len(b) and b[pos:pos + 3] == b'\x00\x00\x01':
        sid = b[pos + 3]
        if sid == 0xba:
            pos += 12 if (b[pos + 4] & 0xF0) == 0x20 else 14 + (b[pos + 13] & 7)
            continue
        if sid == 0xb9:
            break
        ln = struct.unpack_from('>H', b, pos + 4)[0]
        payload = b[pos + 6:pos + 6 + ln]
        if sid not in streams:
            q = 0
            if 0xc0 <= sid <= 0xef:
                while q < len(payload) and payload[q] == 0xff:   # MPEG-1 stuffing
                    q += 1
                if q < len(payload) and (payload[q] & 0xC0) == 0x40:  # STD buffer
                    q += 2
                if q < len(payload):
                    q += {0x2: 5, 0x3: 10}.get(payload[q] >> 4, 1)   # PTS / PTS+DTS / 0x0F
            head = payload[q:q + 64]
            if 0xe0 <= sid <= 0xef:
                kind = 'video'
            elif head[:2] == b'\x80\x00' and b'(c)CRI' in head:
                kind = 'adx'
            elif head[:4] == b'AIXF':
                kind = 'aix'
            else:
                kind = head[:8].hex()
            streams[sid] = kind
        pos += 6 + ln
    r['parsed_bytes'] = pos
    r['streams'] = {'%02x' % k: v for k, v in sorted(streams.items())}
    r['audio_kinds'] = sorted({v for k, v in streams.items() if 0xc0 <= k <= 0xdf})
    r['audio_streams'] = sorted('%02x' % k for k in streams if 0xc0 <= k <= 0xdf)
    return r


def scan(root):
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            if f.lower().endswith('.sfd'):
                p = os.path.join(d, f)
                out[os.path.relpath(p, root).replace(os.sep, '/')] = info(p)
    return out


if __name__ == '__main__':
    a, b = scan(X1M), scan(X2M)
    json.dump({'xml1': a, 'xml2': b}, open(_REPO + r'/research/sweep/movies.json', 'w'), indent=1)
    import collections
    for name, s in (('XML1', a), ('XML2', b)):
        sig = collections.Counter((v['pack'], v.get('video'), v.get('fps'), v.get('mpeg2_video'),
                                   tuple(v['audio_kinds']), tuple(v['audio_streams']), v['sofdec_sig']) for v in s.values())
        print(name, len(s), 'files', sum(v['size'] for v in s.values()) // 2**20, 'MiB')
        for k, n in sig.most_common():
            print('   ', n, k)
    n1 = {k.split('/')[-1].lower() for k in a}
    n2 = {k.split('/')[-1].lower() for k in b}
    print('name collisions:', sorted(n1 & n2))
    print('XML1 ntsc/pal:', collections.Counter(k.split('/')[0] for k in a))
    print('sample XML1:', list(a.items())[:2])
    print('sample XML2:', list(b.items())[:2])
