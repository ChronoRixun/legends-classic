"""xml1build.media_music - offline check that an XML1 music bank plays correctly through XMen2.exe's stream player.

Private helper of xml1build.media (pure functions; runs in worker processes; never writes).

Why this exists. XML1 and XML2 both give a music sample with flag 0x20 ("layered", every _c combat bank) TWO
stream voices that play in sync: layer 0 (the base track, heard out of combat) and layer 1 (added in combat).
The two layers are stored chunk-interleaved in ONE file, but the chunk size differs between the engines:
  XML1 default.xbe 0x193953: 0x4800/0x9000 bytes of Xbox ADPCM per sub-voice = 32768 frames per chunk.
  XML2 XMen2.exe   0x595d60: per refill, count * 0x8000 PCM bytes are decoded from one continuous IMA stream and
                             bytes [i*0x8000, (i+1)*0x8000) go to voice i = 8192 stereo frames per chunk. At EOF the
                             last read is split as (got - 0x8000) bytes per voice, so layer 0's last chunk must be
                             complete (padded) and the stream must not end inside it.
A 1:1 transcode (research/sound/out/all_ima) keeps XML1's 32768-frame layout, so XMen2.exe hands alternating
8192-frame slices of BOTH layers to BOTH voices. tools/fix_music.py (orchestrator) re-interleaves at 8192 frames
(optionally resampling 2:1 or flattening to one plain stream, --flatten); its outputs are
research/sound/music0x20/banks/eng (default --out; 44.1 kHz by default) and .../banks_22k/eng. The in-game loopback recordings matched this engine model (fix_music.py
docstring: nyc1_music_only.wav = simulated voice 0 of the old bank at r=1.000).

What check_bank() does, independently of fix_music.py's own pipeline:
  1. decode the installed PC bank's IMA stream exactly as XMen2.exe does (continuous IMA from state 0/0,
     adpcm.pc_decode) and split it into the engine's voices with the 0x595d60 rule (own implementation);
  2. decode the ORIGINAL Xbox bank (xml1_xbox/sounds/zsds, adpcm.xbox_decode) and split it into XML1's layers
     with the 0x193953 rule (32768-frame chunks, trailing padding dropped);
  3. bring the reference to the installed rate (1:1, or a 2:1 pair average when 44100 -> 22050) and correlate
     every voice with every layer on the mono mix, over the whole length and in 5-second windows.
A bank passes when voice i matches layer i (whole-length r >= OWN_MIN, every window >= WINDOW_MIN) and not the
other layer (r <= CROSS_MAX), the voice lengths equal the layer lengths (after 2:1: ceil(n / 2)), and the stream
never ends inside layer 0. A 32768-frame-layout bank fails - its voice 0 alternates between the layers. A
flattened bank (0x20 cleared, one plain stream) must match layer 0 or layer 0 + layer 1.
"""
from __future__ import annotations

import os

import numpy as np

from .lib import adpcm, zsnd            # were research/sound

ALGO = 'xml1build.media_music v4: engine split 0x595d60 vs xbox layers 0x193953, pair-average 2:1, mono corr, flatten'
XML2_CHUNK_BYTES = 0x8000             # PCM bytes per sub-voice per refill (XMen2.exe 0x595d60)
XML1_CHUNK_FRAMES = 32768             # frames per sub-voice chunk in XML1 (default.xbe 0x193953)
FLAG_LOOP, FLAG_STEREO, FLAG_8BIT, FLAG_LAYERED = 0x01, 0x02, 0x04, 0x20
IMA = 0x6a
# calibrated on the 61 music banks (2026-09-27): fixed-layout banks own r >= 0.934 (hivext_a), worst 5 s window
# >= 0.925, cross |r| <= 0.02; the 29 layered 1:1 all_ima banks own r <= 0.26, worst window <= 0.2 (or EOF error)
OWN_MIN = 0.90                        # whole-length correlation of voice i with layer i
WINDOW_MIN = 0.80                     # every 5 s window of voice i with layer i
CROSS_MAX = 0.50                      # voice i with the other layer
WINDOW_SECONDS = 5.0


class LayoutError(ValueError):
    pass


def xml2_chunk_frames(ch):
    return XML2_CHUNK_BYTES // (2 * ch)


def sample_layout(flags):
    """(channels, sub-voices) of a sample entry's flags (XMen2.exe 0x5950a8 / 0x59610a)."""
    return (2 if flags & FLAG_STEREO else 1), (2 if flags & FLAG_LAYERED else 1)


def engine_voice_frames(total_frames, ch, nsub):
    """Frames each sub-voice receives from a stream of total_frames (XMen2.exe 0x595d60 refill rule).
    Raises LayoutError when a final read ends inside layer 0 (negative per-voice size)."""
    chunk = xml2_chunk_frames(ch)
    full, rest = divmod(total_frames, nsub * chunk)
    if rest == 0:
        return full * chunk
    per = rest - (nsub - 1) * chunk
    if per <= 0:
        raise LayoutError(f'stream of {total_frames} frames ends inside layer 0 (last read {rest} frames, '
                          f'needs > {(nsub - 1) * chunk}): XMen2.exe computes a non-positive voice length')
    return full * chunk + per


def engine_voices(pcm, ch, nsub):
    """pcm (ch, n) -> list of nsub arrays (ch, m): what XMen2.exe feeds each sub-voice."""
    n = pcm.shape[1]
    m = engine_voice_frames(n, ch, nsub)          # validates the tail
    chunk = xml2_chunk_frames(ch)
    if nsub == 1:
        return [pcm]
    out = [[] for _ in range(nsub)]
    pos = 0
    while pos < n:
        got = min(n - pos, nsub * chunk)
        per = chunk if got == nsub * chunk else got - (nsub - 1) * chunk
        for i in range(nsub):
            out[i].append(pcm[:, pos + i * chunk: pos + i * chunk + per])
        pos += got
    voices = [np.concatenate(o, axis=1) for o in out]
    assert all(v.shape[1] == m for v in voices)
    return voices


def xml1_layers(pcm, nsub, chunk=XML1_CHUNK_FRAMES):
    """XML1 layout: chunk-interleaved sub-streams; trailing pad of the earlier layers dropped."""
    if nsub == 1:
        return [pcm]
    parts = [[] for _ in range(nsub)]
    for k in range(0, pcm.shape[1], chunk):
        parts[(k // chunk) % nsub].append(pcm[:, k:k + chunk])
    layers = [np.concatenate(p, axis=1) for p in parts]
    n = min(l.shape[1] for l in layers)
    return [l[:, :n] for l in layers]


def _arr(chans):
    """array('h') channels -> float32 (ch, n); float32 keeps a worker near 0.8 GB on the longest bank."""
    return np.array([np.frombuffer(c, dtype=np.int16) for c in chans]).astype(np.float32)


def _mono(x):
    return x.mean(axis=0)


def _corr(a, b):
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    a = a[:n].astype(np.float64)
    b = b[:n].astype(np.float64)
    a -= a.mean()
    b -= b.mean()
    d = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / d) if d > 0 else 0.0


def _window_corr(a, b, rate):
    n = min(len(a), len(b))
    w = int(WINDOW_SECONDS * rate)
    vals = []
    for s in range(0, max(1, n - w + 1), w):
        x, y = a[s:s + w], b[s:s + w]
        if len(x) < w // 2 or np.abs(y).max(initial=0) < 64:      # skip silent reference windows
            continue
        vals.append(_corr(x, y))
    return vals


def check_bank(installed_path, xbox_path):
    """-> {'ok', 'problems': [...], 'samples': [...], 'algo'}; see module docstring. Pure (reads two files)."""
    res = {'algo': ALGO, 'installed': str(installed_path), 'xbox': str(xbox_path), 'ok': False, 'problems': [],
           'samples': []}
    pc = zsnd.load(str(installed_path))
    xb = zsnd.load(str(xbox_path), strict=False)
    if pc.platform != 'pc' or xb.platform != 'xbox':
        res['problems'].append(f'platforms {pc.platform}/{xb.platform}, expected pc/xbox')
        return res
    if len(pc.samples) != len(xb.samples) or len(pc.files) != len(xb.files):
        res['problems'].append(f'{len(pc.samples)}/{len(pc.files)} samples/files vs Xbox '
                               f'{len(xb.samples)}/{len(xb.files)}')
        return res
    for s, t in zip(pc.samples, xb.samples):
        row = {'sample': s.index, 'flags': s.raw[2], 'rate': s.u32(4), 'xbox_flags': t.raw[2],
               'xbox_rate': t.u32(4)}
        res['samples'].append(row)
        if s.u16(0) != t.u16(0):
            res['problems'].append(f'sample {s.index}: file index {s.u16(0)} vs Xbox {t.u16(0)}')
            continue
        flattened = s.raw[2] != t.raw[2] and s.raw[2] == t.raw[2] & ~FLAG_LAYERED & 0xff
        if s.raw[2] != t.raw[2] and not flattened:
            res['problems'].append(f'sample {s.index}: flags {s.raw[2]:#x} vs Xbox {t.raw[2]:#x}')
            continue
        ch, nsub = sample_layout(s.raw[2])
        xch, xnsub = sample_layout(t.raw[2])
        f, g = pc.files[s.u16(0)], xb.files[t.u16(0)]
        if pc.file_format(f) != IMA:
            res['problems'].append(f'sample {s.index}: file format {pc.file_format(f):#x}, streams are IMA 0x6a')
            continue
        rate, xrate = s.u32(4), t.u32(4)
        if xrate not in (rate, 2 * rate):
            res['problems'].append(f'sample {s.index}: rate {rate} vs Xbox {xrate} (only 1:1 or 2:1)')
            continue
        pcm = _arr(adpcm.pc_decode(pc.file_bytes(f), ch))
        try:
            voices = engine_voices(pcm, ch, nsub)
        except LayoutError as e:
            res['problems'].append(f'sample {s.index}: {e}')
            continue
        del pcm
        xchans, st = adpcm.xbox_decode(xb.file_bytes(g), xch)
        xpcm = _arr(xchans)
        del xchans
        layers = xml1_layers(xpcm, xnsub)
        del xpcm
        if xrate == 2 * rate:              # pair average: floor(n / 2) frames; fix_music's FIR gives ceil(n / 2)
            layers = [0.5 * (l[:, 0:l.shape[1] - 1:2] + l[:, 1::2]) for l in layers]
        refs = layers
        if flattened:                      # --flatten: one plain stream = layer 0, or layer 0 + layer 1
            L0 = _mono(layers[0])
            mix = layers[0] + layers[1]
            pick = 'mix' if _corr(_mono(voices[0]), _mono(mix)) > _corr(_mono(voices[0]), L0) else 'layer0'
            refs = [mix if pick == 'mix' else layers[0]]
            row['flattened'] = pick
        expect = [l.shape[1] for l in refs]
        row.update({'channels': ch, 'voices': nsub, 'voice_frames': [int(v.shape[1]) for v in voices],
                    'layer_frames_ref': [int(e) for e in expect]})
        for i, v in enumerate(voices):
            if not 0 <= v.shape[1] - expect[i] <= 1:
                res['problems'].append(f'sample {s.index}: voice {i} has {v.shape[1]} frames, the XML1 layer '
                                       f'{expect[i]} (+0/1)')
        V = [_mono(v) for v in voices]
        L = [_mono(l) for l in refs]
        mat = [[round(_corr(V[i], L[j]), 4) for j in range(nsub)] for i in range(nsub)]
        row['corr'] = mat
        wins = []
        for i in range(nsub):
            w = _window_corr(V[i], L[i], rate)
            wins.append(round(min(w), 4) if w else None)
            if mat[i][i] < OWN_MIN:
                res['problems'].append(f'sample {s.index}: voice {i} ~ XML1 layer {i} r={mat[i][i]} < {OWN_MIN}')
            if w and min(w) < WINDOW_MIN:
                res['problems'].append(f'sample {s.index}: voice {i} ~ XML1 layer {i} worst 5 s window '
                                       f'r={min(w):.3f} < {WINDOW_MIN}')
            for j in range(nsub):
                if j != i and mat[i][j] > CROSS_MAX:
                    res['problems'].append(f'sample {s.index}: voice {i} ~ XML1 layer {j} r={mat[i][j]} > '
                                           f'{CROSS_MAX} (layers mixed)')
        row['window_min'] = wins
    res['ok'] = not res['problems']
    return res


def check_job(installed_path, xbox_path):
    """ProcessPool entry point (module level, picklable): never raises; errors become problems."""
    try:
        return check_bank(installed_path, xbox_path)
    except Exception as e:  # noqa: BLE001 - reported per bank by media.py
        return {'algo': ALGO, 'installed': str(installed_path), 'xbox': str(xbox_path), 'ok': False,
                'problems': [f'check failed: {type(e).__name__}: {e}'], 'samples': []}


def is_music_bank(bank, rel):
    """a stream bank <name>_a/_c.zss whose samples are all stereo (the music player's banks)."""
    r = str(rel).lower()
    return r.endswith(('_a.zss', '_c.zss')) and bool(bank.samples) and \
        all(s.raw[2] & FLAG_STEREO for s in bank.samples)


def structure_diff(new, ref):
    """Differences between an installed music bank and the reference conversion of the same XML1 bank that must
    not exist: sound table (keys + entries), track table + ZTRK, sample keys / file index / flags, file keys and
    count. Rates and audio may differ (resampled / re-interleaved)."""
    errs = []
    if [s.hashes for s in new.sounds] != [s.hashes for s in ref.sounds]:
        errs.append('sound keys differ from the reference conversion')
    elif [s.raw for s in new.sounds] != [s.raw for s in ref.sounds]:
        errs.append('sound entries differ from the reference conversion')
    if [t.hashes for t in new.tracks] != [t.hashes for t in ref.tracks] or \
            [new.ztrk[i] for i in range(len(new.tracks))] != [ref.ztrk[i] for i in range(len(ref.tracks))]:
        errs.append('track table / ZTRK differs from the reference conversion')
    if [s.hashes for s in new.samples] != [s.hashes for s in ref.samples]:
        errs.append('sample keys differ from the reference conversion')
    else:
        for a, b in zip(new.samples, ref.samples):
            flags_ok = a.raw[2] == b.raw[2] or a.raw[2] == b.raw[2] & ~FLAG_LAYERED & 0xff   # (--flatten)
            if a.u16(0) != b.u16(0) or not flags_ok:
                errs.append(f'sample {b.index}: file/flags {a.u16(0)}/{a.raw[2]:#x} vs {b.u16(0)}/{b.raw[2]:#x}')
                break
            if a.raw[3:4] != b.raw[3:4] or a.raw[8:] != b.raw[8:]:
                errs.append(f'sample {b.index}: entry bytes {a.raw.hex()} vs {b.raw.hex()} (outside flags/rate)')
                break
    if [f.hashes for f in new.files] != [f.hashes for f in ref.files]:
        errs.append('file keys differ from the reference conversion')
    return errs


def stat_key(p):
    if p is None or not os.path.isfile(p):
        return None
    st = os.stat(p)
    return [st.st_size, st.st_mtime_ns]
