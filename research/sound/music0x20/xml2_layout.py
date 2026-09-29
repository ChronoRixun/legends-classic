"""How is XML2's own layered (0x22) IMA music laid out and encoded?

A: engine decode = one continuous IMA state over the whole file, then 8192-frame chunks alternate voice0/voice1.
B: split the IMA BYTES into 0x2000-byte chunks first (8192 stereo frames), decode each layer with its own state.
Compare the continuity of the de-interleaved layers at the chunk joins, and how the first samples of each chunk
behave (decoder slew) under A.
"""
import os, sys, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import zsnd, adpcm
from analyze_layers import find, join_jump, corr, best_lag_corr, X2, X1

CH = 0x2000  # IMA bytes per 8192-frame stereo chunk


def pcm(chans):
    return np.array([np.frombuffer(c, dtype=np.int16) for c in chans]).astype(np.float64)


def head_err(x, C, k=32):
    """mean |2nd diff| over the first k frames after each join vs overall (slew/click indicator)."""
    m = x.mean(axis=0)
    d2 = np.abs(np.diff(m, 2))
    ks = np.arange(C, len(m) - k, C)
    near = np.concatenate([d2[j - 2:j + 6] for j in ks])
    return round(float(near.mean() / d2.mean()), 2)


def main(name, a_name):
    p = find(X2, name)
    b = zsnd.load(p, strict=False)
    s = b.samples[0]
    data = b.file_bytes(b.files[s.u16(0)])
    # A
    x = pcm(adpcm.pc_decode(data, 2))
    A = [np.concatenate([x[:, k:k + 8192] for k in range(i * 8192, x.shape[1], 16384)], axis=1) for i in range(2)]
    # B
    parts = [b''.join(data[k:k + CH] for k in range(i * CH, len(data), 2 * CH)) for i in range(2)]
    B = [pcm(adpcm.pc_decode(q, 2)) for q in parts]
    a = pcm(adpcm.pc_decode(zsnd.load(find(X2, a_name), strict=False).file_bytes(
        zsnd.load(find(X2, a_name), strict=False).files[0]), 2))
    rep = {'bank': name, 'bytes': len(data), 'chunks': len(data) / CH,
           'A_jump': [join_jump(l, 8192) for l in A], 'B_jump': [join_jump(l, 8192) for l in B],
           'A_head': [head_err(l, 8192) for l in A], 'B_head': [head_err(l, 8192) for l in B],
           'A_dc': [[round(float(l[c].mean()), 1) for c in range(2)] for l in A],
           'B_dc': [[round(float(l[c].mean()), 1) for c in range(2)] for l in B],
           'A_rms': [round(float(np.sqrt((l ** 2).mean())), 1) for l in A],
           'B_rms': [round(float(np.sqrt((l ** 2).mean())), 1) for l in B],
           'A_vs_B_corr': [corr(A[i], B[i]) for i in range(2)],
           'A0_vs_a': best_lag_corr(A[0], a), 'A1_vs_a': best_lag_corr(A[1], a),
           'len_layers': [l.shape[1] for l in A], 'a_len': a.shape[1]}
    # per-chunk correlation of layer0 with _a (lag 0), first 40 chunks
    n = min(A[0].shape[1], a.shape[1])
    pc = []
    for k in range(0, min(n, 8192 * 40), 8192):
        u = A[0][:, k:k + 8192].mean(axis=0); v = a[:, k:k + 8192].mean(axis=0)
        u = u - u.mean(); v = v - v.mean()
        pc.append(round(float((u * v).sum() / (np.sqrt((u * u).sum() * (v * v).sum()) + 1e-9)), 2))
    rep['A0_vs_a_per_chunk'] = pc
    print(json.dumps(rep))


if __name__ == '__main__':
    for c, a in [('abug_c.zss', 'abug_a.zss'), ('new_c.zss', 'new_a.zss')]:
        main(c, a)
