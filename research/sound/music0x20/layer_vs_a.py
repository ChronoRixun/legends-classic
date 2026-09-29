"""For every XML1 layered _c bank: how do layer 0 / layer 1 relate to the zone's _a track?
lag-0 correlation (5 s windows median) and best-lag correlation (11025 Hz mono, FFT)."""
import os, sys, json
from multiprocessing import Pool
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', '..', 'tools'))
import fix_music as fm, zsnd  # noqa


def mono11k(x, rate):
    m = x.astype(np.float64).mean(axis=0)
    return np.interp(np.arange(0, len(m), rate / 11025), np.arange(len(m)), m)


def bestlag(a, b):
    n = min(len(a), len(b))
    a, b = a - a.mean(), b - b.mean()
    size = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    c = np.fft.irfft(np.fft.rfft(a, size) * np.conj(np.fft.rfft(b, size)), size)
    c /= np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9
    i = int(np.argmax(np.abs(c)))
    return round(float(c[i]), 3), (i if i < size // 2 else i - size) / 11025


def job(cp):
    ap = cp[:-6] + '_a.zss'
    if not os.path.exists(ap):
        return None
    b = zsnd.load(cp)
    if not b.samples:
        return None
    s = b.samples[0]
    if not s.raw[2] & 0x20:
        return None
    x = fm.decode_file(b, b.files[0], 2)
    L, _ = fm.split_layers(x, 32768)
    ab = zsnd.load(ap)
    A = fm.decode_file(ab, ab.files[0], 2)
    r = s.u32(4)
    m0, m1, ma = mono11k(L[0], r), mono11k(L[1], r), mono11k(A, r)
    return {'bank': os.path.basename(cp), 'layer_s': round(L[0].shape[1] / r, 1), 'a_s': round(A.shape[1] / r, 1),
            'L0_vs_a_lag0': fm.corr0(L[0], A), 'L0_vs_a_best': bestlag(m0, ma), 'L1_vs_a_best': bestlag(m1, ma),
            'L0_vs_L1_lag0': fm.corr0(L[0], L[1])}


if __name__ == '__main__':
    cs = sorted(p for p in zsnd.iter_banks(fm.XBOX_ROOT) if p.endswith('_c.zss'))
    with Pool(8) as pool:
        res = [r for r in pool.map(job, cs) if r]
    for r in res:
        print(json.dumps(r))
    json.dump(res, open(os.path.join(HERE, 'layer_vs_a.json'), 'w'), indent=1)
