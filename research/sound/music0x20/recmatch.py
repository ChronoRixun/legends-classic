"""Correlate tonight's loopback recordings with what XMen2.exe feeds each stream sub-voice.

Engine model (XMen2.exe 0x595d60 + 0x595b20): continuous IMA decode of the whole file from state (0,0);
every refill takes nsub*0x8000 PCM bytes; bytes [i*0x8000, (i+1)*0x8000) go to sub-voice i.
For stereo that is 8192 frames per sub-voice per refill.
"""
import os, sys, glob
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import zsnd, adpcm
from bank_match import corr_windows
from audio_match import load as load_rec, RATE


def engine_voices(path):
    b = zsnd.load(path, strict=False)
    s = b.samples[0]
    f = b.files[s.u16(0)]
    ch = 2 if s.raw[2] & 2 else 1
    nsub = 2 if s.raw[2] & 0x20 else 1
    x = np.array([np.frombuffer(c, dtype=np.int16) for c in adpcm.pc_decode(b.file_bytes(f), ch)]).astype(np.float64)
    C = 0x8000 // (2 * ch)
    v = [[] for _ in range(nsub)]
    pos = 0
    while pos < x.shape[1]:
        got = min(x.shape[1] - pos, nsub * C)
        per = C if got == nsub * C else got - (nsub - 1) * C
        if per <= 0:
            break
        for i in range(nsub):
            v[i].append(x[:, pos + i * C: pos + i * C + per])
        pos += got
    return [np.concatenate(q, axis=1) for q in v], x, s.u32(4), s.raw[2]


def mono(x, rate):
    m = x.mean(axis=0)
    return np.interp(np.arange(0, len(m), rate / RATE), np.arange(len(m)), m)


if __name__ == '__main__':
    recs = sys.argv[1].split(',')
    banks = sys.argv[2:]
    cands = []
    for bp in banks:
        v, full, rate, fl = engine_voices(bp)
        tag = os.path.relpath(bp, ROOT)
        cands.append((tag + ' plain', mono(full, rate)))
        for i, q in enumerate(v):
            cands.append((tag + f' voice{i}', mono(q, rate)))
        if len(v) == 2:
            m = min(q.shape[1] for q in v)
            cands.append((tag + ' voice0+1', mono(v[0][:, :m] + v[1][:, :m], rate)))
    for r in recs:
        rec = load_rec(r)
        print('==', os.path.basename(r))
        for tag, ref in cands:
            print(f'   {corr_windows(rec, ref):.3f}  {tag}')
