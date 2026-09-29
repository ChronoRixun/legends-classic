"""Independent verification of converted banks against the XML1 Xbox originals.
Own parser + own decoders (blockcheck.py). Checks: structure, sound entries/keys verbatim, samples first 8 bytes,
file count, format, ZTRK blobs verbatim, decoded sample counts, SNR vs Xbox decode (model B)."""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import struct, sys, os, math, array, json
from blockcheck import step, xbox_mono

XROOT = _REPO + '/xml1_xbox/sounds/zsds/'


def parse(d):
    pc = d[:8] == b'ZSNDPC  '
    es = (24, 24, 76, 4, 16, 0, 4) if pc else (24, 28, 84, 4, 16, 0, 4)
    fs, hs = struct.unpack_from('<II', d, 8)
    t = [struct.unpack_from('<III', d, 0x10 + 12 * k) for k in range(7)]
    tabs = []
    for k, (c, ko, eo) in enumerate(t):
        keys = [struct.unpack_from('<II', d, ko + 8 * j) for j in range(c)]
        ents = [d[eo + es[k] * j: eo + es[k] * (j + 1)] for j in range(c)]
        tabs.append((keys, ents))
    return {'pc': pc, 'fs': fs, 'hs': hs, 't': t, 'tabs': tabs, 'd': d}


def pc_decode(data, ch):
    if ch == 1:
        p = i = 0
        out = []
        for b in data:
            for n in (b & 15, b >> 4):
                p, i = step(n, p, i)
                out.append(p)
        return [out]
    pl = il = pr = ir = 0
    L, R = [], []
    for b in data:
        pl, il = step(b & 15, pl, il); L.append(pl)
        pr, ir = step(b >> 4, pr, ir); R.append(pr)
    return [L, R]


def xbox_decode(data, ch):
    if ch == 1:
        return [xbox_mono(data, 'B')]
    # stereo: 72-byte blocks, hdrL hdrR, then 8 x (4 bytes L, 4 bytes R)
    L, R = bytearray(), bytearray()
    for k in range(len(data) // 72):
        blk = data[72 * k:72 * k + 72]
        L += blk[0:4]; R += blk[4:8]
        for w in range(8):
            L += blk[8 + 8 * w: 12 + 8 * w]
            R += blk[12 + 8 * w: 16 + 8 * w]
    return [xbox_mono(bytes(L), 'B'), xbox_mono(bytes(R), 'B')]


def snr(ref, dec):
    s = e = 0
    for a, b in zip(ref, dec):
        for x, y in zip(a, b):
            s += x * x; e += (x - y) ** 2
    return 10 * math.log10(s / e) if e else float('inf')


def check(xpath, ppath, full_audio=True, max_audio_files=None):
    X = parse(open(xpath, 'rb').read())
    P = parse(open(ppath, 'rb').read())
    r = {'bank': os.path.basename(ppath), 'problems': []}
    pr = r['problems']
    d = P['d']
    if not P['pc']: pr.append('not pc')
    if P['fs'] != len(d): pr.append('file_size %d != %d' % (P['fs'], len(d)))
    # keys sorted, indices valid, 1:1
    for k in range(7):
        keys, ents = P['tabs'][k]
        hs = [h for h, _ in keys]
        if hs != sorted(hs): pr.append('T%d keys unsorted' % k)
        if len(set(hs)) != len(hs): pr.append('T%d dup keys' % k)
        if sorted(i for _, i in keys) != list(range(len(ents))): pr.append('T%d key->index not a permutation' % k)
    # sounds: original entries verbatim (first n), keys preserved
    xk0, xe0 = X['tabs'][0]
    pk0, pe0 = P['tabs'][0]
    n0 = len(xe0)
    if pe0[:n0] != xe0: pr.append('sound entries differ')
    xmap = {i: h for h, i in xk0}
    pmap = {i: h for h, i in pk0}
    if any(pmap.get(i) != xmap[i] for i in range(n0)): pr.append('sound keys differ')
    r['sounds'] = (n0, len(pe0))
    # alias sound entries must duplicate an original entry
    for e in pe0[n0:]:
        if e not in xe0: pr.append('alias sound entry not a copy'); break
    # samples
    xk1, xe1 = X['tabs'][1]
    pk1, pe1 = P['tabs'][1]
    if len(xe1) != len(pe1): pr.append('sample count')
    for a, b in zip(xe1, pe1):
        if a[:8] != b[:8] or any(b[8:]): pr.append('sample entry mismatch'); break
    if dict((i, h) for h, i in xk1) != dict((i, h) for h, i in pk1): pr.append('sample keys differ')
    # files
    xk2, xe2 = X['tabs'][2]
    pk2, pe2 = P['tabs'][2]
    if len(xe2) != len(pe2): pr.append('file count')
    fmts = set()
    # tracks
    xk4, xe4 = X['tabs'][4]
    pk4, pe4 = P['tabs'][4]
    n4 = len(xe4)
    r['tracks'] = (n4, len(pe4))
    xhs = X['hs']
    for j in range(n4):
        xo = struct.unpack_from('<I', xe4[j], 8)[0]
        po = struct.unpack_from('<I', pe4[j], 8)[0]
        if xe4[j][:8] != pe4[j][:8] or xe4[j][12:] != pe4[j][12:]: pr.append('track entry %d differs' % j)
        # blob: up to next blob
        xoffs = sorted(struct.unpack_from('<I', e, 8)[0] for e in xe4) + [xhs]
        xend = xoffs[xoffs.index(xo) + 1]
        xblob = X['d'][xo:xend].rstrip(b'\0')
        if P['d'][po:po + len(xblob)] != xblob: pr.append('ztrk %d differs' % j)
    if dict((i, h) for h, i in xk4) != {i: h for h, i in pk4 if i < n4}: pr.append('track keys differ')
    # audio
    snrs = []
    first_audio = min([struct.unpack_from('<I', e, 0)[0] for e in pe2] or [P['hs']])
    if first_audio != P['hs']: pr.append('hs %x != first audio %x' % (P['hs'], first_audio))
    ch_of = {}
    for e in xe1:
        ch_of[struct.unpack_from('<H', e, 0)[0]] = 2 if e[2] & 2 else 1
    nfiles = len(pe2) if max_audio_files is None else min(len(pe2), max_audio_files)
    for j in range(nfiles):
        xo, xs, xf = struct.unpack_from('<III', xe2[j], 0)
        po, ps, pf = struct.unpack_from('<III', pe2[j], 0)
        fmts.add(pf)
        ch = ch_of[j]
        if po + ps > len(d): pr.append('file %d past EOF' % j); continue
        ref = xbox_decode(X['d'][xo:xo + xs], ch)
        if pf == 0x6a:
            dec = pc_decode(d[po:po + ps], ch)
        else:
            a = array.array('h', d[po:po + ps])
            dec = [list(a[c::ch]) for c in range(ch)]
        if len(dec[0]) != len(ref[0]):
            pr.append('file %d len %d vs %d' % (j, len(dec[0]), len(ref[0])))
        snrs.append(round(snr(ref, dec), 2))
    r['formats'] = sorted(fmts)
    s = sorted(snrs)
    r['snr_median'] = s[len(s) // 2] if s else None
    r['snr_min'] = s[0] if s else None
    r['n_audio_checked'] = len(s)
    return r


if __name__ == '__main__':
    pairs = sys.argv[1:]
    for p in pairs:
        x, c = p.split('=')
        print(json.dumps(check(x, c)))
