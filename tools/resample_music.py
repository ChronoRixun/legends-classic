"""Downsample 44.1 kHz samples in a converted PC ZSND bank to 22.05 kHz (XML2's music rate).

usage: resample_music.py <in_pc_bank> <out_pc_bank>

XML2 PC only ever streams 22050 Hz stereo; XML1's 44100 Hz stereo music does not play correctly
through XML2's stream reader. Decodes each 44.1 kHz IMA file, low-pass filters and decimates 2:1,
re-encodes IMA from state (0, 0) and rewrites the sample rate. Everything else is kept verbatim.
"""
import os, struct, sys
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from xml1build.lib import adpcm, convert_zsnd, zsnd  # noqa: E402  (tools/ is this script's folder)

TAPS = 63


def halfband_decimate(x):
    n = np.arange(TAPS) - (TAPS - 1) / 2
    h = np.sinc(n / 2) / 2 * np.blackman(TAPS)
    y = np.convolve(np.asarray(x, dtype=np.float64), h, mode='same')[::2]
    return np.clip(np.round(y), -32768, 32767).astype(np.int64).tolist()


def main(src, dst):
    bank = zsnd.load(src)
    assert bank.platform == 'pc', 'expects a converted PC bank'
    rate_of = {s.u16(0): s.u32(4) for s in bank.samples}
    stereo_of = {s.u16(0): bool(s.raw[2] & 0x02) for s in bank.samples}
    files, changed = [], []
    for f in bank.files:
        fmt = bank.file_format(f)
        audio = bank.file_bytes(f)
        if rate_of.get(f.index) == 44100 and fmt == 0x6a:
            ch = 2 if stereo_of[f.index] else 1
            chans = adpcm.pc_decode(audio, ch)
            audio = adpcm.pcm_to_pc([halfband_decimate(c) for c in chans])
            changed.append(f.index)
        meta = struct.pack('<III', 0, 0, fmt) + f.raw[12:]
        files.append((f.hashes, meta, audio))
    samples = []
    for s in bank.samples:
        raw = bytearray(s.raw)
        if s.u16(0) in changed:
            struct.pack_into('<I', raw, 4, 22050)
        samples.append((s.hashes, bytes(raw)))
    sounds = [(s.hashes, s.raw) for s in bank.sounds]
    tracks = [(t.hashes, t.raw, bank.ztrk[i]) for i, t in enumerate(bank.tracks)]
    out = convert_zsnd.build_pc(sounds, samples, files, tracks)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    open(dst, 'wb').write(out)
    check = zsnd.load(dst)
    print(f'{os.path.basename(dst)}: resampled {len(changed)} file(s); {len(check.samples)} samples; {len(out)} bytes')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
