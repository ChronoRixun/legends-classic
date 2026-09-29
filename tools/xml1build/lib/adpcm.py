"""
IMA ADPCM codecs for the two platforms.

XBOX ("xbadpcm", ZSND file format 1 and 3): Xbox ADPCM = IMA ADPCM in 36-byte blocks per channel:
  4-byte header {s16 predictor, u8 step_index, u8 0} + 32 data bytes = 64 nibbles, low nibble first.
  Output per block and channel = 64 samples = the header sample followed by the samples of nibbles 0..62;
  nibble 63 is not played. (Established empirically: blockmodel.py junction smoothness and xcompare.py
  time-alignment against the identical recordings shipped as PC IMA in XML2's x_common.zsm -- this model
  aligns at lag 0 with r=0.999; it is also what ffmpeg's adpcm_ima_xbox decoder outputs.)
  Stereo: block = hdrL(4) hdrR(4) then 8 x {4 bytes L, 4 bytes R} = 72 bytes.

PC (ZSND file format 0x6a), from XMen2.exe 0x616770 (mono) / 0x616880 (stereo), wrappers 0x616a00/0x616a30
and the streaming reader 0x595b20:
  headerless continuous IMA ADPCM, decoder state starts at predictor 0, index 0 and is never reset.
  mono: low nibble first; stereo: each byte = L sample (low nibble) + R sample (high nibble).

The *_py functions are the reference implementations (pure Python). The public names (xbox_decode, pc_decode,
pc_pack, compare, encode_samples, encode_beam) return exactly the same values, computed with numpy by adpcm_np.py
(the beam encoder only for width 4 / 3 candidates, the one the pipeline uses); tools/xml1build/sound_selftest.py
checks the equivalence.
Backends: codec() is what the sound stages use - adpcm_c (the optional compiled kernel ima_kernel.c, built by
tools/build_sound_kernel.py) when it loads and passes its self-check, else adpcm_np; both have encode_streams /
solve_chains / run_lanes / xbox_decode_np / pc_decode_np and give the same results. codec_status() says which one
runs and why (the stages log it). The public functions below use codec() too (encode_samples / encode_beam: the
kernel for any length, numpy from FAST_MIN samples, else pure Python).
"""
from array import array

STEPS = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97,
         107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
         876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871,
         5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
         27086, 29794, 32767]
IDX = [-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8]

# precomputed: DIFF[idx][nib] = signed delta, NEXT[idx][nib] = next index
DIFF = []
NEXT = []
for _i, _s in enumerate(STEPS):
    row, nrow = [], []
    for _n in range(16):
        d = _s >> 3
        if _n & 4: d += _s
        if _n & 2: d += _s >> 1
        if _n & 1: d += _s >> 2
        row.append(-d if _n & 8 else d)
        ni = _i + IDX[_n]
        nrow.append(0 if ni < 0 else 88 if ni > 88 else ni)
    DIFF.append(row)
    NEXT.append(nrow)
from bisect import bisect_left
SORTED_D = []
SORTED_N = []
for _row in DIFF:
    _o = sorted(range(16), key=lambda n: (_row[n], n))
    SORTED_D.append([_row[n] for n in _o])
    SORTED_N.append(_o)


def decode_nibbles(nibs, pred, idx, out):
    """Decode an iterable of nibbles from state (pred, idx), append to out. Returns new state."""
    D, N = DIFF, NEXT
    for n in nibs:
        pred += D[idx][n]
        if pred > 32767: pred = 32767
        elif pred < -32768: pred = -32768
        idx = N[idx][n]
        out.append(pred)
    return pred, idx


def encode_samples_py(samples, pred, idx, nibs_out, search=True):
    """IMA-encode samples from state (pred, idx). Greedy best-nibble search (search=True) or classic encoder.
    Appends nibbles to nibs_out, returns final state."""
    D, N = DIFF, NEXT
    SD, SN = SORTED_D, SORTED_N
    for s in samples:
        if search:
            # reconstruction deltas are monotonic in the nibble, so the closest one is a neighbour of the
            # bisect position (equivalent to trying all 16, but ~5x faster)
            sd = SD[idx]
            k = bisect_left(sd, s - pred)
            best = None
            for j in (k - 1, k):
                if 0 <= j < 16:
                    p = pred + sd[j]
                    if p > 32767: p = 32767
                    elif p < -32768: p = -32768
                    e = p - s
                    if e < 0: e = -e
                    if best is None or e < best:
                        best = e
                        n = SN[idx][j]
                        bp = p
            pred = bp
        else:
            step = STEPS[idx]
            diff = s - pred
            n = 0
            if diff < 0:
                n = 8
                diff = -diff
            if diff >= step: n |= 4; diff -= step
            step >>= 1
            if diff >= step: n |= 2; diff -= step
            step >>= 1
            if diff >= step: n |= 1
            pred += D[idx][n]
            if pred > 32767: pred = 32767
            elif pred < -32768: pred = -32768
        idx = N[idx][n]
        nibs_out.append(n)
    return pred, idx


def encode_beam_py(samples, pred=0, idx=0, width=8, cands=4, window=1024):
    """Beam-search IMA encoder (minimises summed squared error over a sliding window).
    Keeps `width` best decoder states; each expands by the `cands` reconstructions nearest the target.
    Commits the best path every `window` samples. Returns (nibbles, (pred, idx))."""
    SD, SN, N = SORTED_D, SORTED_N, NEXT
    out = []
    n_total = len(samples)
    pos = 0
    while pos < n_total:
        seg = samples[pos:pos + window]
        beam = [(0, pred, idx, None)]  # (err, pred, idx, path) path = (nibble, parent_path)
        for s in seg:
            nxt = {}
            for err, p0, i0, path in beam:
                sd = SD[i0]
                k = bisect_left(sd, s - p0)
                lo = k - cands // 2
                if lo < 0: lo = 0
                hi = lo + cands
                if hi > 16:
                    hi = 16
                    lo = 16 - cands
                sn = SN[i0]
                for j in range(lo, hi):
                    p = p0 + sd[j]
                    if p > 32767: p = 32767
                    elif p < -32768: p = -32768
                    e = p - s
                    e = err + e * e
                    nib = sn[j]
                    key = (p, N[i0][nib])
                    old = nxt.get(key)
                    if old is None or e < old[0]:
                        nxt[key] = (e, p, key[1], (nib, path))
            beam = sorted(nxt.values(), key=lambda t: t[0])[:width]
        err, pred, idx, path = beam[0]
        seg_nibs = []
        while path is not None:
            seg_nibs.append(path[0])
            path = path[1]
        seg_nibs.reverse()
        out.extend(seg_nibs)
        pos += window
    return out, (pred, idx)


# ---------------------------------------------------------------- XBOX

def xbox_blocks(data, channels):
    """Yield per block: list per channel of (hdr_pred, hdr_idx, reserved, nibbles[64])."""
    bs = 36 * channels
    nblk = len(data) // bs
    for b in range(nblk):
        blk = data[b * bs:(b + 1) * bs]
        chans = []
        for c in range(channels):
            h = blk[4 * c: 4 * c + 4]
            pred = int.from_bytes(h[0:2], 'little', signed=True)
            chans.append([pred, h[2], h[3], []])
        body = blk[4 * channels:]
        # 4-byte words interleaved per channel
        for w in range(8):
            for c in range(channels):
                word = body[(w * channels + c) * 4:(w * channels + c) * 4 + 4]
                nl = chans[c][3]
                for byte in word:
                    nl.append(byte & 15)
                    nl.append(byte >> 4)
        yield chans


def xbox_decode_py(data, channels):
    """Return list of array('h') per channel, plus stats."""
    outs = [array('h') for _ in range(channels)]
    stats = {'blocks': 0, 'bad_idx': 0, 'reserved_nonzero': 0, 'hdr_state_mismatch': 0, 'tail_bytes': len(data) % (36 * channels)}
    prev = [None] * channels
    for chans in xbox_blocks(data, channels):
        stats['blocks'] += 1
        for c, (pred, idx, res, nibs) in enumerate(chans):
            if idx > 88:
                stats['bad_idx'] += 1
                idx = 88
            if res:
                stats['reserved_nonzero'] += 1
            if prev[c] is not None and prev[c] != (pred, idx):
                stats['hdr_state_mismatch'] += 1
            outs[c].append(pred)
            prev[c] = decode_nibbles(nibs[:63], pred, idx, outs[c])
    return outs, stats


# ---------------------------------------------------------------- PC

def pc_decode_py(data, channels):
    outs = [array('h') for _ in range(channels)]
    D, N = DIFF, NEXT
    if channels == 1:
        pred, idx = 0, 0
        o = outs[0]
        for byte in data:
            for n in (byte & 15, byte >> 4):
                pred += D[idx][n]
                if pred > 32767: pred = 32767
                elif pred < -32768: pred = -32768
                idx = N[idx][n]
                o.append(pred)
    else:
        pl = pr = il = ir = 0
        ol, orr = outs
        for byte in data:
            n = byte & 15
            pl += D[il][n]
            if pl > 32767: pl = 32767
            elif pl < -32768: pl = -32768
            il = N[il][n]
            ol.append(pl)
            n = byte >> 4
            pr += D[ir][n]
            if pr > 32767: pr = 32767
            elif pr < -32768: pr = -32768
            ir = N[ir][n]
            orr.append(pr)
    return outs


def pc_pack_py(nib_chans):
    ch = len(nib_chans)
    if ch == 1:
        nl = nib_chans[0]
        if len(nl) & 1:
            nl = list(nl) + [0]
        return bytes(nl[i] | (nl[i + 1] << 4) for i in range(0, len(nl), 2))
    l, r = nib_chans
    assert len(l) == len(r)
    return bytes(a | (b << 4) for a, b in zip(l, r))


# ---------------------------------------------------------------- public entry points (numpy, same results)

FAST_MIN = 4096          # shorter inputs: the pure-Python code is as fast as the vectorised one


def _np():
    from . import adpcm_np      # noqa: needs numpy; imported on first use
    return adpcm_np


def kernel():
    """adpcm_c if the compiled kernel is loaded and passed its self-check, else None."""
    from . import adpcm_c       # noqa: loads + self-checks the library once per process
    return adpcm_c if adpcm_c.load() else None


def codec():
    """The encoder backend of the sound stages: adpcm_c (compiled kernel) or adpcm_np (numpy); same results."""
    return kernel() or _np()


def codec_name():
    """'kernel' or 'numpy' (the field the stage reports carry)."""
    return 'kernel' if kernel() else 'numpy'


def codec_status():
    """One line for the logs: which encoder backend runs, and why not the kernel if it does not."""
    from . import adpcm_c
    adpcm_c.load()
    return adpcm_c.STATUS


def _to_h(a):
    out = array('h')
    out.frombytes(a.astype('<i2').tobytes())
    return out


def xbox_decode(data, channels):
    """Return list of array('h') per channel, plus stats (== xbox_decode_py)."""
    pcm, st = codec().xbox_decode_np(data, channels)
    return [_to_h(c) for c in pcm], st


def pc_decode(data, channels):
    """== pc_decode_py: list of array('h') per channel."""
    return [_to_h(c) for c in codec().pc_decode_np(data, channels)]


def pc_pack(nib_chans):
    """== pc_pack_py."""
    return _np().pack_np(nib_chans)


def compare(a_chans, b_chans):
    """== compare_py."""
    return _np().compare_np(a_chans, b_chans)


def encode_samples(samples, pred, idx, nibs_out, search=True):
    """== encode_samples_py (appends the nibbles to nibs_out, returns the final state)."""
    if search:
        k = kernel()
        if k and k.fits(samples, pred, idx):
            nl, end = k.greedy(samples, pred, idx)
            nibs_out.extend(nl.tolist())
            return end
        if len(samples) >= FAST_MIN:
            (nl, end), = _np().encode_streams([('greedy', samples, pred, idx)])
            nibs_out.extend(nl.tolist())
            return end
    return encode_samples_py(samples, pred, idx, nibs_out, search)


def encode_beam(samples, pred=0, idx=0, width=8, cands=4, window=1024):
    """== encode_beam_py -> (nibbles list, (pred, idx))."""
    if (width, cands) == (4, 3):
        k = kernel()
        if k and k.fits(samples, pred, idx) and window >= 1:
            nl, end = k.beam4(samples, pred, idx, window)
            return nl.tolist(), end
        if len(samples) >= FAST_MIN:
            (nl, end), = _np().encode_streams([('beam4', samples, pred, idx)], window=window)
            return nl.tolist(), end
    return encode_beam_py(samples, pred, idx, width, cands, window)


def xbox_to_pc(data, channels, search=True, encoder='beam'):
    """Transcode Xbox ADPCM -> PC headerless IMA ADPCM: decode (block model above) and re-encode continuously
    from state (0, 0). encoder: 'beam' (beam search, width 4 / 3 candidates; +2..10 dB SNR over greedy on
    transient-heavy SFX), 'greedy' (closest reconstruction per sample) or 'classic' (textbook IMA encoder).
    Returns (pc_bytes, stats, reference_pcm_per_channel)."""
    ref, st = xbox_decode(data, channels)
    nib_out = []
    for c in range(channels):
        if encoder == 'beam':
            nl, _ = encode_beam(ref[c], width=4, cands=3)
        else:
            nl = []
            encode_samples(ref[c], 0, 0, nl, encoder != 'classic' and search)
        nib_out.append(nl)
    return pc_pack(nib_out), st, ref


def pcm_to_pc(chans, search=True):
    """Encode PCM (list of per-channel int sequences) to PC IMA ADPCM."""
    nib_out = []
    for c in chans:
        nl = []
        encode_samples(c, 0, 0, nl, search)
        nib_out.append(nl)
    return pc_pack(nib_out)


# ---------------------------------------------------------------- WAV helpers

def write_wav(path, chans, rate):
    import struct
    ch = len(chans)
    n = len(chans[0])
    inter = array('h', bytes(2 * n * ch))
    for c in range(ch):
        inter[c::ch] = chans[c]
    body = inter.tobytes()
    with open(path, 'wb') as f:
        f.write(b'RIFF' + struct.pack('<I', 36 + len(body)) + b'WAVEfmt ' +
                struct.pack('<IHHIIHH', 16, 1, ch, rate, rate * 2 * ch, 2 * ch, 16) + b'data' +
                struct.pack('<I', len(body)) + body)


def pcm_stats(chans):
    import math
    n = sum(len(c) for c in chans)
    if not n:
        return {'n': 0}
    peak = max(max(abs(min(c)), abs(max(c))) for c in chans if len(c))
    ss = sum(sum(x * x for x in c) for c in chans)
    rms = math.sqrt(ss / n)
    clip = sum(sum(1 for x in c if x >= 32767 or x <= -32768) for c in chans)
    # zero crossing rate as a sanity check against noise-like garbage
    zc = 0
    for c in chans:
        zc += sum(1 for a, b in zip(c, c[1:]) if (a < 0) != (b < 0))
    return {'n': n, 'peak': peak, 'rms': round(rms, 1), 'clipped': clip, 'zcr': round(zc / n, 4)}


def compare_py(a_chans, b_chans):
    import math
    n = min(len(a_chans[0]), len(b_chans[0]))
    sig = err = 0
    exact = 0
    maxe = 0
    for a, b in zip(a_chans, b_chans):
        for x, y in zip(a[:n], b[:n]):
            d = x - y
            sig += x * x
            err += d * d
            if d == 0: exact += 1
            if abs(d) > maxe: maxe = abs(d)
    tot = n * len(a_chans)
    snr = 10 * math.log10(sig / err) if err else float('inf')
    return {'n': n, 'exact_pct': round(100 * exact / tot, 3), 'snr_db': round(snr, 2), 'max_err': maxe}
