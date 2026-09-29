"""Check whether a loopback recording contains a reference track (normalised cross-correlation).

usage: audio_match.py <recording.wav> <reference.wav> [<reference.wav> ...]
Prints, per reference, the best correlation of a 3 s window of the recording against the
whole reference (after resampling both to 11025 Hz mono). ~1.0 = same audio, ~0 = unrelated.
"""
import sys, wave
import numpy as np

RATE = 11025


def load(path):
    with wave.open(path) as w:
        n, ch, rate, width = w.getnframes(), w.getnchannels(), w.getframerate(), w.getsampwidth()
        raw = np.frombuffer(w.readframes(n), dtype='<i2' if width == 2 else np.uint8).astype(np.float64)
    mono = raw.reshape(-1, ch).mean(axis=1)
    idx = np.arange(0, len(mono), rate / RATE)
    return np.interp(idx, np.arange(len(mono)), mono)


def best_corr(rec, ref):
    win = rec[RATE:RATE * 4] if len(rec) > RATE * 4 else rec
    win = (win - win.mean()) / (win.std() + 1e-9)
    n = len(win)
    size = 1 << int(np.ceil(np.log2(len(ref) + n)))
    corr = np.fft.irfft(np.fft.rfft(ref, size) * np.conj(np.fft.rfft(win, size)), size)[:len(ref) - n]
    csum = np.concatenate([[0], np.cumsum(ref)])
    csq = np.concatenate([[0], np.cumsum(ref * ref)])
    means = (csum[n:len(ref)] - csum[:len(ref) - n]) / n
    var = (csq[n:len(ref)] - csq[:len(ref) - n]) / n - means ** 2
    norm = corr / (np.sqrt(np.maximum(var, 1e-9)) * n)
    i = int(np.argmax(np.abs(norm)))
    return float(norm[i]), i / RATE


if __name__ == '__main__':
    rec = load(sys.argv[1])
    for ref_path in sys.argv[2:]:
        c, at = best_corr(rec, load(ref_path))
        print(f'{c:+.3f} at {at:7.2f}s  {ref_path}')
