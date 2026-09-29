"""Empirical layout analysis of layered (flag 0x20) music in XML1 (Xbox) and XML2 (PC).

For a decoded stereo stream x and a candidate chunk size C, split x into two sub-streams by alternating C-frame
chunks and measure how continuous each sub-stream is at the joins (|1st diff| at the join / mean |1st diff|).
The true layout gives ~1.0 at the joins of the de-interleaved layers; a wrong one gives big jumps.
Also: correlation of layer 0 / layer 1 with the zone's _a track, and chunk-to-chunk spectral similarity.
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import os, sys, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import zsnd, adpcm

X1 = _REPO + '/xml1_xbox/sounds/zsds'
X2 = _XML2 + '/Sounds/eng'


def find(root, name):
    for p in zsnd.iter_banks(root):
        if os.path.basename(p).lower() == name.lower():
            return p
    raise FileNotFoundError(name)


def decode(path):
    b = zsnd.load(path, strict=False)
    s = b.samples[0]
    f = b.files[s.u16(0)]
    ch = 2 if s.raw[2] & 2 else 1
    data = b.file_bytes(f)
    if b.platform == 'xbox':
        chans, _ = adpcm.xbox_decode(data, ch)
    else:
        chans = adpcm.pc_decode(data, ch)
    return np.array([np.frombuffer(c, dtype=np.int16) for c in chans]).astype(np.float64), s.u32(4), s.raw[2]


def split(x, C, nsub=2):
    parts = [[] for _ in range(nsub)]
    for k in range(0, x.shape[1], C):
        parts[(k // C) % nsub].append(x[:, k:k + C])
    return [np.concatenate(p, axis=1) for p in parts]


def join_jump(layer, C):
    """Mean |first difference| at chunk joins relative to the mean everywhere (1.0 = seamless)."""
    m = layer.mean(axis=0)
    d = np.abs(np.diff(m))
    ks = np.arange(C, len(m) - 1, C)
    if len(ks) == 0:
        return None
    return round(float(d[ks - 1].mean() / (d.mean() + 1e-9)), 2)


def raw_jump(x, C):
    """Same metric on the undivided stream at multiples of C."""
    return join_jump(x, C)


def corr(a, b):
    n = min(a.shape[1], b.shape[1])
    a = a[:, :n].mean(axis=0); b = b[:, :n].mean(axis=0)
    a = a - a.mean(); b = b - b.mean()
    return round(float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9)), 3)


def best_lag_corr(a, b, maxlag=200000):
    """max normalised xcorr of mono a vs b over lags (FFT), returns (r, lag)."""
    a = a.mean(axis=0); b = b.mean(axis=0)
    n = min(len(a), len(b))
    a = a[:n] - a[:n].mean(); b = b[:n] - b[:n].mean()
    size = 1 << int(np.ceil(np.log2(2 * n)))
    c = np.fft.irfft(np.fft.rfft(a, size) * np.conj(np.fft.rfft(b, size)), size)
    c = c / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9)
    i = int(np.argmax(np.abs(c)))
    lag = i if i < size // 2 else i - size
    return round(float(c[i]), 3), lag


def analyze(c_path, a_path, cands):
    x, rate, fl = decode(c_path)
    rep = {'bank': os.path.basename(c_path), 'rate': rate, 'flags': hex(fl), 'frames': int(x.shape[1])}
    a = None
    if a_path:
        a, ar, _ = decode(a_path)
        rep['a_frames'] = int(a.shape[1])
    rep['raw_jump'] = {C: raw_jump(x, C) for C in cands}
    rep['split'] = {}
    for C in cands:
        L = split(x, C)
        r = {'jump': [join_jump(l, C) for l in L]}
        if a is not None:
            r['corr_a_lag0'] = [corr(l, a) for l in L]
        rep['split'][C] = r
    return rep, x, a


if __name__ == '__main__':
    cands = [4096, 8192, 16384, 32768, 65536]
    out = {}
    jobs = [('xml2', 'abug_c.zss', 'abug_a.zss'), ('xml2', 'sewer_c.zss', 'sewer_a.zss'),
            ('xml2', 'new_c.zss', 'new_a.zss'), ('xml2', 'town1_c.zss', 'town1_a.zss'),
            ('xml1', 'nyc1_c.zss', 'nyc1_a.zss'), ('xml1', 'sewer1_c.zss', 'sewer1_a.zss'),
            ('xml1', 'mandgr_c.zss', 'mandgr_a.zss')]
    for game, c, a in jobs:
        root = X2 if game == 'xml2' else X1
        rep, x, A = analyze(find(root, c), find(root, a), cands)
        print(json.dumps(rep))
