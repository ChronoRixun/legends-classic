"""Decode every sample in ZSND banks and rank them by correlation with a loopback recording.

usage: bank_match.py <recording.wav> <bank> [<bank> ...]
"""
import os, sys
import numpy as np

from xml1build.lib import adpcm, zsnd  # noqa: E402  (tools/ is this script's folder)
from audio_match import load, RATE  # noqa: E402


def decoded(bank_path):
    bank = zsnd.load(bank_path, strict=False)
    for s in bank.samples:
        f = bank.files[s.u16(0)]
        rate = s.u32(4)
        channels = 2 if s.raw[2] & 0x02 else 1
        data = bank.file_bytes(f)
        if bank.file_format(f) == 0x6a:
            chans = adpcm.pc_decode(data, channels)
        else:
            chans = adpcm.xbox_decode(data, channels)[0]
        mono = np.mean([np.asarray(c, dtype=np.float64) for c in chans], axis=0)
        idx = np.arange(0, len(mono), rate * float(os.environ.get('RATE_SCALE', '1')) / RATE)
        yield bank.file_name(f), np.interp(idx, np.arange(len(mono)), mono)


def corr_windows(rec, ref, win_s=2.0):
    """Best |normalised correlation| of any 2 s window of rec against ref."""
    n = int(RATE * win_s)
    if len(ref) < n or len(rec) < n:
        return 0.0
    best = 0.0
    for start in range(0, len(rec) - n, RATE * 2):
        win = rec[start:start + n]
        win = (win - win.mean()) / (win.std() + 1e-9)
        size = 1 << int(np.ceil(np.log2(len(ref) + n)))
        corr = np.fft.irfft(np.fft.rfft(ref, size) * np.conj(np.fft.rfft(win, size)), size)[:len(ref) - n + 1]
        csum = np.concatenate([[0], np.cumsum(ref)])
        csq = np.concatenate([[0], np.cumsum(ref * ref)])
        means = (csum[n:] - csum[:-n]) / n
        var = (csq[n:] - csq[:-n]) / n - means ** 2
        m = min(len(corr), len(var))
        norm = corr[:m] / (np.sqrt(np.maximum(var[:m], 1e-6)) * n)
        best = max(best, float(np.max(np.abs(norm))))
    return best


if __name__ == '__main__':
    rec = load(sys.argv[1])
    scores = []
    for bank in sys.argv[2:]:
        for name, pcm in decoded(bank):
            scores.append((corr_windows(rec, pcm), os.path.basename(bank), name))
    for s, b, n in sorted(scores, reverse=True)[:12]:
        print(f'{s:.3f}  {b}  {n}')
