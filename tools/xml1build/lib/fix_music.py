"""Convert XML1 music banks (flag 0x20 "layered" combat music and plain stereo music) for XML2 PC.

    python tools/fix_music.py fix [<bank|dir> ...] [--out DIR] [--rate keep|22050] [--encoder beam|greedy]
                                  [--seam xfade|hard] [--flatten layer0|mix] [--only nyc1,sewer1_c]
                                  [--jobs N] [--wav DIR] [--wav-seconds S] [--force]
    python tools/fix_music.py simulate <pc_bank> [...] [--wav DIR] [--wav-seconds S]
    python tools/fix_music.py match <recording.wav> <pc_bank> [--xml1 <xbox_bank>]
    python tools/fix_music.py layout <bank> [...]

Inputs of `fix` (default: every *_a/*_c music bank of XML1 under xml1_xbox/sounds/zsds) can be XML1 Xbox banks
or the 1:1 PC conversions in research/sound/out/all_ima (for those the Xbox original with the same c1/c2/name
path is used as the lossless source when it exists; otherwise the PC IMA stream is decoded and its layout
detected). Output: <out>/<c1>/<c2>/<name>.zss (default research/sound/music0x20/banks/eng) and
_fix_music_report.json. Every output is re-parsed and re-decoded exactly the way XMen2.exe streams it.

WHAT FLAG 0x20 IS (identical design in both engines; see research/sound/music0x20/README.txt for addresses)
  0x20 = the file holds TWO sub-streams of equal length ("layers") played in sync on two voices of one stream:
  layer 0 = base music (in 23 of XML1's 29 layered banks it contains the zone's _a material, r=0.43-0.95),
  layer 1 = combat layer added on top (never correlates with _a, |r| <= 0.03). Both games start <zone>_c if a
  game-state check passes and it exists, else <zone>_a (XMen2 0x4782bd / XML1 0x7b081; in game, Sanctuary and
  nyc1 idle both played _c). The music cross-fader (XMen2 0x477010 / XML1
  0x7a300, same code) sets state 2 (not in combat) = voice 0 at full, voice 1 silent; state 3 (combat) =
  voice 0 + voice 1 (XMen2 0x58fea0 -> 0x58ff00 -> 0x5958d0 = SetVolume per sub-voice buffer).
  Data layout = the layers cut into fixed chunks and alternated: L0 c0, L1 c0, L0 c1, L1 c1, ...; at EOF the last
  read is split as (bytes_read - (n-1)*chunk) per voice, so layer 0's last chunk is padded and never fully played.
    XML1 default.xbe : chunk = 0x9000 bytes of Xbox ADPCM per voice for stereo (0x4800 mono) = 512 blocks =
                       32768 frames (0x193953); each voice's chunks are independent Xbox-ADPCM blocks.
    XML2 XMen2.exe   : chunk = 0x8000 bytes of decoded PCM per voice = 8192 stereo frames (0x595d60), taken
                       from ONE continuous IMA decode of the whole file (0x595b20: state shared by both voices,
                       reset to (0,0) only when the stream loops).
  So a 1:1 transcode (XML1 chunking) makes XML2 hand 8192-frame slices of the 32768-frame chunks to the two
  voices: out of combat XML2 plays L0[0:8k], L0[16k:24k], L1[0:8k], L1[16k:24k], ... (confirmed in game:
  nyc1_music_only.wav = simulated XML2 voice 0 of the old bank at r=1.000).

THE FIX
  Decode the XML1 source, split it into its two layers at 32768 frames (lossless, from Xbox ADPCM), optionally
  resample, and rebuild XML2's layout: 8192-frame chunks alternating L0/L1 (layer 0's last chunk padded),
  encoded as ONE continuous IMA stream from state (0,0) - the way XML2's own 37 layered banks are encoded.
  Seams (--seam xfade, default): XML2's decoder state runs straight from one layer's chunk into the other's.
  The last FADE+HOLD frames of every layer-1 chunk are cross-faded into the layer-0 frames that immediately
  precede the next layer-0 chunk (FADE = 8 frames per 22050 Hz, HOLD chosen per seam so the IMA step index
  - which can only fall by one per sample - has come down to layer 0's level), so the decoder arrives there
  exactly on layer 0's waveform with a settled step size: voice 0 (all out-of-combat music) has no seams (its
  error near the switches is below its error elsewhere). The first 16 frames of each layer-1 chunk are
  cross-faded from layer 0's continuation. The cost is confined to voice 1, which is only heard in combat and
  always together with voice 0 (~0.5-2 ms per 0.19 s at 44.1 kHz where layer 1 is replaced by layer 0).
  XML2's own layered banks hard-switch instead: seam click ratio 2.9-16 in voice 0, 1.6-3.9 in the combat mix.
  --seam hard: plain hard switches everywhere (like XML2's own banks; both voices click).
  --flatten layer0|mix: fallback that stores ONE plain stereo stream (layer 0, or layer0+layer1) and clears 0x20.
  --rate keep (default) keeps XML1's 44100 Hz (proven to stream in game); --rate 22050 = XML2's usual rate.
  Plain stereo banks (_a, menu_c) are re-encoded (beam search) from the Xbox source, flags unchanged.
"""
import argparse, json, os, struct, sys, time, wave
import numpy as np

from . import zsnd, adpcm, adpcm_np, convert_zsnd
from ..sources import REPO_ROOT, DEFAULT_XML2

# developer-mode defaults of the CLI (python tools/fix_music.py ...); prepare stage P5 passes both roots explicitly
ROOT = str(REPO_ROOT)     # was tools/.. (this module moved from tools/fix_music.py, BUILDER_DESIGN.md 1.5)
XBOX_ROOT = os.path.join(ROOT, 'xml1_xbox', 'sounds', 'zsds').replace('\\', '/')
XML2_ROOT = (DEFAULT_XML2 / 'Sounds' / 'eng').as_posix()
DEFAULT_OUT = os.path.join(ROOT, 'research', 'sound', 'music0x20', 'banks', 'eng').replace('\\', '/')
FLAG_STEREO, FLAG_LAYERED = 0x02, 0x20
XML1_CHUNK_BYTES = {1: 0x4800, 2: 0x9000}      # default.xbe 0x193953 (nBlockAlign 0x24 / 0x48)
XML2_CHUNK_PCM_BYTES = 0x8000                  # XMen2.exe 0x595d60
W_VOICE0, W_VOICE1, W_PAD = 4.0, 1.0, 0.25     # beam-search error weights near seams
DIFF = np.array(adpcm.DIFF, dtype=np.int64)
NEXT = np.array(adpcm.NEXT, dtype=np.int64)


def xml1_chunk_frames(ch):
    return XML1_CHUNK_BYTES[ch] // (36 * ch) * 64          # 32768 for mono and stereo


def xml1_chunk_frames_at(ch, rate):
    """XML1 chunk length after a PC bank was resampled from XML1's 44100 Hz (resample_music.py: 22050 -> 16384)."""
    c = xml1_chunk_frames(ch)
    return c * rate // 44100 if (c * rate) % 44100 == 0 else c


def xml2_chunk_frames(ch):
    return XML2_CHUNK_PCM_BYTES // (2 * ch)               # 8192 stereo, 16384 mono


def seam_params(rate, seam):
    """(fade, hold, head) frames: layer-1 tail cross-fade into layer 0 + hold (None = per seam, auto_hold), and the
    layer-1 head cross-fade. Chosen with research/sound/music0x20/seam_experiment.py: the shortest tail that leaves
    voice 0's seams indistinguishable from the rest of the music (near-seam SNR >= elsewhere, click ratio ~1)."""
    if seam != 'xfade':
        return 0, 0, 0
    k = max(1, round(rate / 22050))
    return 8 * k, None, 16


# ---------------------------------------------------------------- decoding / layers

def to_np(chans):
    return np.array([np.frombuffer(c, dtype=np.int16) for c in chans]).astype(np.int32)


def decode_file(bank, f, ch):
    data = bank.file_bytes(f)
    if bank.platform == 'xbox':
        return adpcm.codec().xbox_decode_np(data, ch)[0].astype(np.int32)  # == to_np(adpcm.xbox_decode_py(...)[0])
    if bank.file_format(f) == 0x6a:
        return adpcm.codec().pc_decode_np(data, ch).astype(np.int32)       # == to_np(adpcm.pc_decode_py(...))
    return np.frombuffer(data[:len(data) // (2 * ch) * 2 * ch], dtype='<i2').reshape(-1, ch).T.astype(np.int32)


def split_layers(pcm, chunk, nsub=2):
    """De-interleave nsub sub-streams exactly as both engines do: full reads of nsub*chunk frames, chunk i of a read
    -> voice i; a final partial read of r frames gives every voice r - (nsub-1)*chunk frames (layer 0's last chunk
    is padding beyond that). Returns (layers, info)."""
    T = pcm.shape[1]
    R = nsub * chunk
    full, rem = divmod(T, R)
    per = rem - (nsub - 1) * chunk if rem else 0
    info = {'frames_in': int(T), 'chunk': int(chunk), 'full_reads': int(full), 'last_read': int(rem)}
    if rem and per <= 0:
        info['warning'] = f'final read of {rem} frames leaves {per} for each voice; the partial read is dropped'
        per = 0
    layers = []
    for i in range(nsub):
        parts = [pcm[:, k * R + i * chunk: k * R + (i + 1) * chunk] for k in range(full)]
        if per:
            parts.append(pcm[:, full * R + i * chunk: full * R + i * chunk + per])
        layers.append(np.concatenate(parts, axis=1) if parts else pcm[:, :0])
    if per and nsub > 1:
        pad = pcm[:, full * R + per: full * R + chunk]
        info['layer0_unplayed_pad_frames'] = int(pad.shape[1])
        info['layer0_unplayed_pad_peak'] = int(np.abs(pad).max()) if pad.size else 0
    info['layer_frames'] = int(layers[0].shape[1])
    return layers, info


def engine_voices(data, ch, nsub):
    """What XMen2.exe plays on each stream sub-voice: continuous IMA decode from (0,0) (0x595b20), then the
    0x8000-PCM-byte chunk distribution of 0x595d60 (same EOF rule as split_layers)."""
    pcm = adpcm.codec().pc_decode_np(data, ch).astype(np.int32)            # == to_np(adpcm.pc_decode_py(...))
    if nsub == 1:
        return [pcm], pcm, {'frames_in': int(pcm.shape[1])}
    v, info = split_layers(pcm, xml2_chunk_frames(ch), nsub)
    return v, pcm, info


def join_jump(layer, chunk):
    """Mean |1st difference| across the joins k*chunk of a de-interleaved layer / mean |1st difference|.
    ~1 = the layer is continuous there (right layout), >>1 = pieces of unrelated audio were glued (wrong)."""
    m = layer.astype(np.float64).mean(axis=0)
    d = np.abs(np.diff(m))
    ks = np.arange(chunk, len(m) - 1, chunk)
    if not len(ks) or d.mean() == 0:
        return None
    return round(float(d[ks - 1].mean() / d.mean()), 2)


def detect_layout(pcm, ch, rate=44100, win=2048, guard=256):
    """Which chunking a layered stream uses: XML1 (32768 frames) or XML2 (8192 stereo / 16384 mono).
    The raw stream switches layers at every XML2-chunk boundary in XML2 layout, but only at every XML1-chunk
    boundary in XML1 layout. Compare the short-time spectra just before / after (skipping `guard` frames of
    codec slew) the XML2-chunk boundaries that are XML1-chunk boundaries with those that are not:
    ratio >> 1 -> XML1 layout, ~1 -> XML2 layout. Returns ('xml1'|'xml2', {'ratio': r})."""
    C1, C2 = xml1_chunk_frames_at(ch, rate), xml2_chunk_frames(ch)
    m = pcm.astype(np.float64).mean(axis=0)
    edges = np.geomspace(40, 11000, 20) / 44100 * win    # fractional bin edges (scale-free enough for both rates)
    bins = np.clip(np.digitize(np.arange(win // 2 + 1), edges), 0, len(edges))
    w = np.hanning(win)

    def spec(a):
        S = np.abs(np.fft.rfft(a * w)) ** 2
        return np.log10(np.bincount(bins, S, minlength=len(edges) + 1) + 1.0)

    d = {True: [], False: []}
    for p in range(C2, len(m) - win - guard, C2):
        if p - win - guard < 0:
            continue
        a, b = spec(m[p - guard - win:p - guard]), spec(m[p + guard:p + guard + win])
        d[p % C1 == 0].append(float(np.abs(a - b).mean()))
    if not d[True] or not d[False]:
        return 'xml1', {'ratio': None}
    r = float(np.median(d[True]) / (np.median(d[False]) + 1e-9))
    return ('xml1' if r > 1.5 else 'xml2'), {'ratio': round(r, 2)}


# ---------------------------------------------------------------- resampling (2:1, circular = loop-safe)

def lowpass_taps(n=255, cutoff=0.2275):
    """Windowed-sinc (Blackman) low-pass, cutoff as a fraction of the INPUT rate (0.2275*44100 = 10.0 kHz)."""
    k = np.arange(n) - (n - 1) / 2
    h = 2 * cutoff * np.sinc(2 * cutoff * k) * np.blackman(n)
    return h / h.sum()


def decimate2_loop(layer):
    h = lowpass_taps()
    n = layer.shape[1]
    out = []
    size = 1 << int(np.ceil(np.log2(n + len(h))))
    H = np.fft.rfft(h, size)
    half = (len(h) - 1) // 2
    for c in layer.astype(np.float64):
        xx = np.concatenate([c[-half:], c, c[:half]])        # the music loops: filter across the loop point
        y = np.fft.irfft(np.fft.rfft(xx, size) * H, size)[2 * half: 2 * half + n]
        out.append(y[::2])
    return np.clip(np.round(np.array(out)), -32768, 32767).astype(np.int32)


def resample(layers, rate, target):
    if not target or target == rate:
        return layers, rate
    if rate != 2 * target:
        raise ValueError(f'only 2:1 downsampling is implemented ({rate} -> {target})')
    return [decimate2_loop(l) for l in layers], target


# ---------------------------------------------------------------- XML2 layered stream construction

def raised_cos(k):
    return 0.5 - 0.5 * np.cos(np.pi * (np.arange(k) + 0.5) / k) if k > 0 else np.zeros(0)


def steady_index(x, end, n=192):
    """IMA step index a (greedy) encoder has settled on when it reaches `end` while tracking x (one channel)."""
    a = max(0, end - n)
    seg = [int(v) for v in x[a:end]]
    if not seg:
        return 0
    nl = []
    _, idx = adpcm.encode_samples(seg, seg[0], 0, nl, True)
    return idx


def auto_hold(L0, L1, e, fade, lo=8, hi=96):
    """Frames of pure layer 0 needed at the end of a layer-1 chunk so the IMA step index has come down from layer 1's
    level to layer 0's before the next layer-0 chunk starts at `e`: the index can only fall by 1 per sample."""
    need = 0
    for c in range(L0.shape[0]):
        i1 = steady_index(L1[c], e - fade - lo)
        i0 = steady_index(L0[c], e)
        need = max(need, i1 - i0 - fade // 2 + 6)
    return int(min(hi, max(lo, need)))


def auto_holds(L0, L1, ends, fade, lo=8, hi=96, codec=None):
    """== [auto_hold(L0, L1, e, fade, lo, hi) for e in ends]; the greedy steady_index() runs of every seam are
    independent, so they run together (codec.run_lanes, default adpcm.codec(): kernel calls or numpy lanes)."""
    pays, starts = [], []
    for e in ends:
        for c in range(L0.shape[0]):
            for x, end in ((L1[c], e - fade - lo), (L0[c], e)):
                seg = x[max(0, end - 192):end].astype(np.int64)             # steady_index(x, end): int(v) of whole floats
                pays.append((seg,))
                starts.append((int(seg[0]) if len(seg) else 0, 0))
    idx = [r[1][1] if len(p[0]) else 0 for r, p in zip((codec or adpcm.codec()).run_lanes('greedy', pays, starts),
                                                        pays)]
    out, k = [], 0
    for e in ends:
        need = 0
        for c in range(L0.shape[0]):
            need = max(need, idx[k] - idx[k + 1] - fade // 2 + 6)
            k += 2
        out.append(int(min(hi, max(lo, need))))
    return out


def build_stream(layers, chunk, fade, hold, head=0, w0=W_VOICE0, w1=W_VOICE1):
    """Interleave two equal-length layers in XML2's layout and build the PCM the IMA encoder must reproduce.
    fade/hold: the last fade+hold frames of every layer-1 chunk except the last are cross-faded (raised cosine) into
    the layer-0 frames that immediately precede the next layer-0 chunk; hold=None picks it per seam (auto_hold).
    head > 0: the first `head` frames of each layer-1 chunk are cross-faded from layer 0's continuation.
    Returns (target int32 (ch, N), weights float (N,), windows [(a, e)], stats)."""
    L0, L1 = (l.astype(np.float64) for l in layers)
    ch, n = L0.shape
    assert L1.shape == L0.shape
    K = -(-n // chunk)
    ext0 = np.concatenate([L0, np.tile(L0, (1, -(-2 * chunk // n)))], axis=1)   # layer 0 as the loop it is
    segs, wts, wins = [], [], [(0, 160)]
    pos, altered, holds = 0, 0, []
    auto = auto_holds(L0, L1, [min(n, (k + 1) * chunk) for k in range(K - 1)], fade) if hold is None else None
    for k in range(K):
        a, e = k * chunk, min(n, (k + 1) * chunk)
        m = e - a
        s0, w = L0[:, a:e], np.full(m, w0)
        last = k == K - 1
        if m < chunk:                    # padding of layer 0's last chunk: never played (engine plays only m
            P = chunk - m                # frames of it); bridge from the loop start into layer 1's own pre-roll
            q = min(P, 256)
            r = np.ones(P)
            r[:q] = raised_cos(q)
            pad = ext0[:, n:n + P] * (1 - r) + L1[:, a - P:a] * r
            s0, w = np.concatenate([s0, pad], axis=1), np.concatenate([w, np.full(P, W_PAD)])
        segs.append(s0)
        wts.append(w)
        pos += chunk
        if not (last and m < chunk):     # switch into the layer-1 chunk (after a padded chunk it is seamless)
            wins.append((pos - 16, pos + 96))
        s1 = L1[:, a:e].copy()
        if head and not (last and m < chunk):
            h = min(head, m)
            r = raised_cos(h)
            s1[:, :h] = ext0[:, e:e + h] * (1 - r) + s1[:, :h] * r
            altered += h
        t = 0
        if not last and fade + (hold or 0) + (hold is None):
            hd = auto[k] if hold is None else hold                   # == auto_hold(L0, L1, e, fade)
            holds.append(hd)
            t = fade + hd
            # arrive at the next layer-0 chunk on layer 0's own waveform with a settled step size
            tail = np.concatenate([raised_cos(fade), np.ones(hd)])
            s1[:, m - t:] = s1[:, m - t:] * (1 - tail) + ext0[:, e - t:e] * tail
            altered += t
        if not last:
            wins.append((pos + m - t - 24, pos + m + 64))
        segs.append(s1)
        wts.append(np.full(m, w1))
        pos += m
    target = np.clip(np.round(np.concatenate(segs, axis=1)), -32768, 32767).astype(np.int32)
    weights = np.concatenate(wts)
    N = target.shape[1]
    merged = []
    for a, e in sorted((max(0, a), min(N, e)) for a, e in wins):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        elif e > a:
            merged.append([a, e])
    st = {'voice1_frames_altered': altered, 'beam_windows': len(merged)}
    if holds:
        st['hold_frames'] = {'min': int(min(holds)), 'median': int(np.median(holds)), 'max': int(max(holds))}
    return target, weights, merged, st


# ---------------------------------------------------------------- IMA encoding

def beam_window(target, weight, pred, idx, width=64):
    """Weighted beam search over all 16 nibbles per sample (width survivors, deduplicated decoder states)."""
    P = np.array([pred], dtype=np.int64)
    I = np.array([idx], dtype=np.int64)
    E = np.zeros(1)
    par, nib = [], []
    for s, wt in zip(target.tolist(), weight.tolist()):
        p = P[:, None] + DIFF[I]
        np.clip(p, -32768, 32767, out=p)
        e = E[:, None] + wt * (p - s).astype(np.float64) ** 2
        ni = NEXT[I]
        p, e, ni = p.ravel(), e.ravel(), ni.ravel()
        key = (p + 32768) * 89 + ni
        order = np.lexsort((e, key))
        ks = key[order]
        first = np.ones(len(ks), dtype=bool)
        first[1:] = ks[1:] != ks[:-1]
        cand = order[first]
        if len(cand) > width:
            cand = cand[np.argpartition(e[cand], width - 1)[:width]]
        par.append(cand >> 4)
        nib.append(cand & 15)
        P, I, E = p[cand], ni[cand], e[cand]
    b = int(np.argmin(E))
    fp, fi = int(P[b]), int(I[b])
    out = np.empty(len(par), dtype=np.uint8)
    for t in range(len(par) - 1, -1, -1):
        out[t] = nib[t][b]
        b = int(par[t][b])
    return out, (fp, fi)


def encode_channel(x, weights, windows, body='beam'):
    """Continuous IMA from (0,0): weighted wide beam inside `windows`, adpcm.encode_beam (width 4, 3 candidates)
    or the greedy encoder elsewhere."""
    N = len(x)
    out = np.empty(N, dtype=np.uint8)
    pred, idx, pos = 0, 0, 0

    def run_body(a, e):
        nonlocal pred, idx
        if e <= a:
            return
        seg = x[a:e].tolist()
        if body == 'beam':
            nl, (pred, idx) = adpcm.encode_beam(seg, pred, idx, width=4, cands=3)
        else:
            nl = []
            pred, idx = adpcm.encode_samples(seg, pred, idx, nl, True)
        out[a:e] = nl

    for a, e in windows:
        run_body(pos, a)
        nl, (pred, idx) = beam_window(x[a:e], weights[a:e], pred, idx)
        out[a:e] = nl
        pos = e
    run_body(pos, N)
    return out


def pack(nibs):
    if len(nibs) == 1:
        n = nibs[0]
        if len(n) & 1:
            n = np.concatenate([n, np.zeros(1, dtype=np.uint8)])
        return (n[0::2] | (n[1::2] << 4)).astype(np.uint8).tobytes()
    return (nibs[0] | (nibs[1] << 4)).astype(np.uint8).tobytes()


def chain_units(x, weights, windows, body='beam'):
    """The units encode_channel() runs in order: adpcm.encode_beam's 1024-sample windows (or greedy pieces) of each
    body stretch, and a beam_window() per window."""
    kind = 'beam4' if body == 'beam' else 'greedy'
    units, pos = [], 0
    for a, e in windows:
        assert a >= pos, (a, pos)
        if a > pos:
            units += adpcm_np.stream_units(kind, x[pos:a])
        units.append(('wide', (x[a:e], weights[a:e])))
        pos = e
    if len(x) > pos:
        units += adpcm_np.stream_units(kind, x[pos:])
    return units


def encode(target, weights, windows, body='beam', stats=None, codec=None):
    """== pack([encode_channel(c.astype(np.int64), weights, windows, body) for c in target]): every channel's unit
    chain is solved by codec.solve_chains (default adpcm.codec(): the compiled kernel, sequentially, or adpcm_np's
    speculative numpy lanes; both exact)."""
    chains = [((0, 0), chain_units(c, weights, windows, body)) for c in target]
    return pack([np.concatenate(nl) if nl else np.zeros(0, dtype=np.uint8)
                 for nl, _ in (codec or adpcm.codec()).solve_chains(chains, stats=stats)])


# ---------------------------------------------------------------- metrics

def dbfs(v):
    return round(float(20 * np.log10(max(float(v), 1e-9) / 32768.0)), 1)


def snr_db(ref, x):
    n = min(ref.shape[1], x.shape[1])
    r, d = ref[:, :n].astype(np.float64), x[:, :n].astype(np.float64)
    err = ((r - d) ** 2).sum()
    return round(float(10 * np.log10((r ** 2).sum() / err)), 2) if err else float('inf')


def seam_report(v, ref, chunk, before=8, after=56):
    """Error of a played voice against the audio it should play, split into frames near the engine's chunk switches
    ([s-before, s+after) around every multiple of `chunk`) and all other frames."""
    n = min(v.shape[1], ref.shape[1])
    e = (v[:, :n] - ref[:, :n]).astype(np.float64)
    r = ref[:, :n].astype(np.float64)
    seams = np.arange(chunk, n - after, chunk)
    near = np.zeros(n, dtype=bool)
    for s in seams:
        near[s - before:s + after] = True
    far = ~near
    out = {'seams': int(len(seams))}
    for tag, msk in (('near_seams', near), ('elsewhere', far)):
        if msk.any():
            ee = (e[:, msk] ** 2).mean()
            out[tag] = {'err_rms_dbfs': dbfs(np.sqrt(ee)), 'snr_db': round(float(10 * np.log10((r[:, msk] ** 2).mean() / ee)), 2) if ee else None,
                        'err_peak': int(np.abs(e[:, msk]).max())}
    return out


def click_ratio(x, chunk):
    """Reference-free seam click: mean over chunk switches of max|2nd difference| in [s-4, s+12) divided by the
    same statistic at mid-chunk positions (1.0 = the switch points look like any other point of the music)."""
    m = x.astype(np.float64).mean(axis=0)
    d2 = np.abs(np.diff(m, 2))
    seams = np.arange(chunk, len(m) - chunk, chunk)
    if not len(seams):
        return None
    mids = seams + chunk // 2

    def pk(ps):
        return np.array([d2[p - 5:p + 11].max() for p in ps])
    c = pk(mids).mean()
    return round(float(pk(seams).mean() / c), 2) if c else None


def spectrum(x, rate, nfft=4096, frames=200):
    m = x.astype(np.float64).mean(axis=0)
    if len(m) < nfft:
        return {}
    starts = np.linspace(0, len(m) - nfft, min(frames, len(m) // nfft)).astype(int)
    w = np.hanning(nfft)
    S = np.mean([np.abs(np.fft.rfft(m[s:s + nfft] * w)) ** 2 for s in starts], axis=0)
    f = np.fft.rfftfreq(nfft, 1 / rate)
    tot = S.sum() or 1.0
    bands = {}
    for lo, hi in ((0, 250), (250, 2000), (2000, 6000), (6000, 11025), (11025, 22050)):
        if lo < rate / 2:
            bands[f'{lo}-{hi}'] = round(float(S[(f >= lo) & (f < hi)].sum() / tot), 4)
    return {'centroid_hz': int((S * f).sum() / tot), 'band_energy': bands}


def level(x):
    xf = x.astype(np.float64)
    return {'rms_dbfs': dbfs(np.sqrt((xf ** 2).mean())), 'peak_dbfs': dbfs(np.abs(xf).max())}


def corr0(a, b):
    n = min(a.shape[1], b.shape[1])
    u, v = a[:, :n].astype(np.float64).mean(axis=0), b[:, :n].astype(np.float64).mean(axis=0)
    u, v = u - u.mean(), v - v.mean()
    return round(float((u * v).sum() / (np.sqrt((u * u).sum() * (v * v).sum()) + 1e-9)), 3)


# ---------------------------------------------------------------- WAV

def write_wav(path, pcm, rate, seconds=None):
    x = pcm if not seconds else pcm[:, :int(seconds * rate)]
    x = np.clip(x, -32768, 32767).astype('<i2')
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with wave.open(path, 'wb') as w:
        w.setnchannels(x.shape[0])
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(x.T.tobytes())


# ---------------------------------------------------------------- bank conversion

def rel3(path):
    return '/'.join(path.replace('\\', '/').split('/')[-3:])


def xbox_original(path, xbox_root=None):
    p = os.path.join(xbox_root or XBOX_ROOT, *rel3(path).split('/'))
    return p if os.path.exists(p) else None


class Skip(Exception):
    pass


def source_audio(bank, path, s, xbox_root=None):
    """-> (pcm, source, flags, rate, channels) of one sample. For a PC bank the XML1 Xbox original with the same
    c1/c2/name path is used when its structure matches (it is the lossless source, and its flags/rate are the true
    ones even if the PC bank was resampled or had 0x20 cleared); otherwise the PC bank's own audio."""
    if bank.platform == 'pc':
        xp = xbox_original(path, xbox_root)
        if xp:
            xb = zsnd.load(xp)
            if len(xb.samples) == len(bank.samples) and len(xb.files) == len(bank.files):
                xs = xb.samples[s.index]
                if (xs.raw[2] & FLAG_STEREO) == (s.raw[2] & FLAG_STEREO):
                    ch = 2 if xs.raw[2] & FLAG_STEREO else 1
                    return decode_file(xb, xb.files[xs.u16(0)], ch), 'xbox:' + xp, xs.raw[2], xs.u32(4), ch
    ch = 2 if s.raw[2] & FLAG_STEREO else 1
    return (decode_file(bank, bank.files[s.u16(0)], ch), ('pc:' if bank.platform == 'pc' else 'xbox:') + path,
            s.raw[2], s.u32(4), ch)


def fix_bank(in_path, out_path, rate_mode='keep', body='beam', seam='xfade', flatten=None, force=False,
             wav_dir=None, wav_seconds=None, log=print, xbox_root=None, xml2_root=None):
    """xbox_root: the XML1 sounds/zsds tree holding the Xbox originals of PC-bank inputs (default XBOX_ROOT);
    xml2_root: XML2's Sounds/eng (report field xml2_ships_same_name; default XML2_ROOT). The prepare stage P5
    (xml1build/prepare/sound.py) passes both."""
    t0 = time.time()
    bank = zsnd.load(in_path)
    name = os.path.splitext(os.path.basename(out_path))[0]
    rep = {'in': in_path, 'out': out_path, 'platform': bank.platform, 'codec': adpcm.codec_name(), 'samples': []}
    files_out, sample_meta = {}, {}
    for s in bank.samples:
        pcm, src, fl, rate, ch = source_audio(bank, in_path, s, xbox_root)
        sr = {'file': s.u16(0), 'source': src, 'flags_in': hex(fl), 'rate_in': rate, 'frames_in': int(pcm.shape[1])}
        if (fl, rate) != (s.raw[2], s.u32(4)):
            sr['input_entry'] = {'flags': hex(s.raw[2]), 'rate': s.u32(4)}
        if fl & FLAG_LAYERED:
            layout = 'xml1'
            if src.startswith('pc:'):
                layout, scores = detect_layout(pcm, ch, rate)
                sr['layout_scores'] = scores
                if layout == 'xml2' and not force:
                    raise Skip(f'{in_path}: already in XML2 layout {scores}')
                if layout == 'xml1':
                    msg = ('no Xbox original found: decoded the 1:1 PC conversion, whose encoder had to slew at every '
                           '32768-frame layer switch; those clicks are now part of layer 0/1 (use the Xbox bank)')
                    sr['warning'] = msg
                    log('WARNING', in_path, msg, flush=True)
            C1 = xml1_chunk_frames_at(ch, rate) if layout == 'xml1' else xml2_chunk_frames(ch)
            layers, info = split_layers(pcm, C1)
            sr['split'] = info
            sr['layer_join_jump'] = [join_jump(l, C1) for l in layers]
        else:
            layers = [pcm]
        out_rate = rate
        if rate_mode != 'keep':
            layers, out_rate = resample(layers, rate, int(rate_mode))
        new_fl = fl
        if len(layers) == 2 and flatten:
            layers = [layers[0] if flatten == 'layer0' else np.clip(layers[0] + layers[1], -32768, 32767)]
            new_fl = fl & ~FLAG_LAYERED
        C2 = xml2_chunk_frames(ch)
        n = layers[0].shape[1]
        if len(layers) == 2:
            fade, hold, head = seam_params(out_rate, seam)
            target, weights, wins, st = build_stream(layers, C2, fade, hold, head)
            sr.update({'xml2_chunk': C2, 'seam': seam, 'fade': fade, 'hold': hold or 'auto', 'head': head, **st})
        else:
            target, weights, wins = layers[0], np.ones(n), [(0, 160)]
        data = encode(target, weights, wins, body)
        # ---- verify exactly as XMen2.exe will play it
        voices, full, vinfo = engine_voices(data, ch, 2 if new_fl & FLAG_LAYERED else 1)
        for v, l in zip(voices, layers):
            assert v.shape == l.shape, (v.shape, l.shape)
        sr.update({'flags_out': hex(new_fl), 'rate_out': out_rate, 'layer_frames': int(n),
                   'seconds': round(n / out_rate, 2), 'bytes_out': len(data), 'stream_snr_db': snr_db(target, full),
                   'voices': []})
        for i, (v, l) in enumerate(zip(voices, layers)):
            vr = {'voice': i, 'snr_db': snr_db(l, v), **level(v), 'click_ratio': None}
            if len(voices) == 2:
                vr['seams'] = seam_report(v, l, C2)
                vr['click_ratio'] = click_ratio(v, C2)
                vr['click_ratio_source'] = click_ratio(l, C2)
            sr['voices'].append(vr)
        if len(voices) == 2:
            mix, ref = voices[0] + voices[1], layers[0] + layers[1]
            sr['combat_mix'] = {'snr_db': snr_db(ref, mix), 'seams': seam_report(mix, ref, C2),
                                'click_ratio': click_ratio(mix, C2), 'click_ratio_source': click_ratio(ref, C2),
                                **level(np.clip(mix, -32768, 32767))}
            sr['layer0_vs_layer1_corr'] = corr0(layers[0], layers[1])
            sr['loop_start_frame'] = [[int(x) for x in l[:, 0]] for l in layers]
        if wav_dir:
            d = os.path.join(wav_dir, name)
            if len(voices) == 2:
                write_wav(os.path.join(d, 'xml2_voice0_out_of_combat.wav'), voices[0], out_rate, wav_seconds)
                write_wav(os.path.join(d, 'xml2_voice1_combat_layer_alone.wav'), voices[1], out_rate, wav_seconds)
                write_wav(os.path.join(d, 'xml2_voice0+1_in_combat.wav'), voices[0] + voices[1], out_rate, wav_seconds)
            else:
                write_wav(os.path.join(d, f'xml2_{out_rate}.wav'), voices[0], out_rate, wav_seconds)
        sample_meta[s.index] = (new_fl, out_rate)
        files_out[s.u16(0)] = data
        rep['samples'].append(sr)
    # ---- rebuild the bank: sounds verbatim, sample flags/rate patched, file names .wav, format 0x6a
    files = []
    for f in bank.files:
        nm = bank.file_name(f)
        if nm.lower().endswith('.xbadpcm'):
            nm = nm[:-8] + '.wav'
        nb = nm.encode('latin1')[:63]
        if f.index not in files_out:
            raise zsnd.ZsndError(f'file {f.index} is not used by any sample')
        files.append((f.hashes, struct.pack('<III', 0, 0, 0x6a) + nb + b'\0' * (64 - len(nb)), files_out[f.index]))
    samples = []
    for s in bank.samples:
        raw = bytearray(s.raw[:8] + b'\0' * convert_zsnd.PC_SAMPLE_TAIL)
        raw[2], rt = sample_meta[s.index]
        struct.pack_into('<I', raw, 4, rt)
        samples.append((s.hashes, bytes(raw)))
    sounds = [(s.hashes, s.raw) for s in bank.sounds]
    tracks = [(t.hashes, t.raw, bank.ztrk[i]) for i, t in enumerate(bank.tracks)]
    out = convert_zsnd.build_pc(sounds, samples, files, tracks)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, 'wb') as fh:
        fh.write(out)
    chk = zsnd.load(out_path)                               # strict re-parse of what is on disk
    assert [x.raw for x in chk.sounds] == [x.raw for x in bank.sounds]
    assert [x.hashes for x in chk.sounds] == [x.hashes for x in bank.sounds]
    for s in chk.samples:
        f = chk.files[s.u16(0)]
        assert chk.file_bytes(f) == files_out[f.index] and chk.file_format(f) == 0x6a
        assert (s.raw[2], s.u32(4)) == sample_meta[s.index]
    rep['bytes'] = len(out)
    rep['xml2_ships_same_name'] = os.path.exists(os.path.join(xml2_root or XML2_ROOT, *rel3(out_path).split('/')))
    rep['seconds_taken'] = round(time.time() - t0, 1)
    brief = []
    for sr in rep['samples']:
        for v in sr['voices']:
            brief.append({'v': v['voice'], 'snr': v['snr_db'],
                          'seam_snr': v.get('seams', {}).get('near_seams', {}).get('snr_db'),
                          'click': v['click_ratio']})
        if 'combat_mix' in sr:
            brief.append({'mix_snr': sr['combat_mix']['snr_db'], 'mix_click': sr['combat_mix']['click_ratio']})
    log(json.dumps({'out': out_path, 'flags': [sr['flags_out'] for sr in rep['samples']],
                    'rate': [sr['rate_out'] for sr in rep['samples']], 's': rep['seconds_taken'], 'check': brief}),
        flush=True)
    return rep


# ---------------------------------------------------------------- simulate / match / layout

def bank_voices(path):
    bank = zsnd.load(path, strict=False)
    for s in bank.samples:
        f = bank.files[s.u16(0)]
        ch = 2 if s.raw[2] & FLAG_STEREO else 1
        nsub = 2 if s.raw[2] & FLAG_LAYERED else 1
        v, full, info = engine_voices(bank.file_bytes(f), ch, nsub)
        yield s, ch, nsub, v, full, info


def simulate(path, wav_dir=None, seconds=None):
    for s, ch, nsub, v, full, info in bank_voices(path):
        rate = s.u32(4)
        r = {'bank': path, 'flags': hex(s.raw[2]), 'rate': rate, 'split': info, 'voices': []}
        if nsub == 2:
            r['layout_detected'] = detect_layout(full, ch, rate)
        for i, x in enumerate(v):
            r['voices'].append({'voice': i, 'frames': int(x.shape[1]), **level(x), **spectrum(x, rate),
                                'click_ratio': click_ratio(x, xml2_chunk_frames(ch)) if nsub == 2 else None})
        if nsub == 2:
            r['combat_mix_click_ratio'] = click_ratio(v[0] + v[1], xml2_chunk_frames(ch))
        if wav_dir:
            base = os.path.splitext(os.path.basename(path))[0]
            for i, x in enumerate(v):
                write_wav(os.path.join(wav_dir, f'{base}__engine_voice{i}.wav'), x, rate, seconds)
            if nsub == 2:
                write_wav(os.path.join(wav_dir, f'{base}__engine_voice0+1.wav'), v[0] + v[1], rate, seconds)
        yield r


def window_matches(rec, ref, win_s=2.0, hop_s=1.0, RATE=11025):
    """Per window of the recording: best normalised correlation against anywhere in ref (both 11025 Hz mono)."""
    n = int(RATE * win_s)
    if len(ref) < n or len(rec) < n:
        return []
    size = 1 << int(np.ceil(np.log2(len(ref) + n)))
    R = np.fft.rfft(ref, size)
    csum = np.concatenate([[0], np.cumsum(ref)])
    csq = np.concatenate([[0], np.cumsum(ref * ref)])
    means = (csum[n:] - csum[:-n]) / n
    sd = np.sqrt(np.maximum((csq[n:] - csq[:-n]) / n - means ** 2, 1e-6))
    out = []
    for st in range(0, len(rec) - n + 1, int(RATE * hop_s)):
        w = rec[st:st + n]
        if w.std() < 1e-3:
            continue
        w = (w - w.mean()) / w.std()
        c = np.fft.irfft(R * np.conj(np.fft.rfft(w, size)), size)[:len(ref) - n + 1]
        m = min(len(c), len(sd))
        out.append(float(np.max(np.abs(c[:m] / (sd[:m] * n)))))
    return out


def match(rec_path, banks, xml1=None):
    from audio_match import load, RATE      # tools/audio_match.py (the developer `match` command only)

    def mono(x, rate):
        m = x.astype(np.float64).mean(axis=0)
        return np.interp(np.arange(0, len(m), rate / RATE), np.arange(len(m)), m)
    rec = load(rec_path)
    cands = []
    for p in banks:
        try:
            lab = os.path.relpath(p, ROOT).replace(os.sep, '/')
        except ValueError:
            lab = p
        for s, ch, nsub, v, full, info in bank_voices(p):
            rate = s.u32(4)
            lab2 = f'{lab} [{hex(s.raw[2])} {rate} Hz]'
            cands.append((lab2 + ' XML2 voice0 (out of combat)', mono(v[0], rate)))
            if nsub == 2:
                cands.append((lab2 + ' XML2 voice1 (combat layer)', mono(v[1], rate)))
                cands.append((lab2 + ' XML2 voice0+1 (combat)', mono(v[0] + v[1], rate)))
    if xml1:
        xb = zsnd.load(xml1)
        for s in xb.samples:
            ch = 2 if s.raw[2] & FLAG_STEREO else 1
            pcm = decode_file(xb, xb.files[s.u16(0)], ch)
            if s.raw[2] & FLAG_LAYERED:
                ls, _ = split_layers(pcm, xml1_chunk_frames(ch))
                cands += [('XML1 layer0 (reference, out of combat)', mono(ls[0], s.u32(4))),
                          ('XML1 layer1 (reference, combat layer)', mono(ls[1], s.u32(4))),
                          ('XML1 layer0+1 (reference, combat)', mono(ls[0] + ls[1], s.u32(4)))]
            else:
                cands.append(('XML1 ' + os.path.basename(xml1) + ' (reference)', mono(pcm, s.u32(4))))
    print(f'recording {rec_path}: {len(rec) / RATE:.1f} s; per 2 s window (hop 1 s): best correlation anywhere in the '
          'reference. A correct bank gives median ~0.9+ against XML2 voice0 AND against XML1 layer0 when idle.')
    rows = []
    for tag, ref in cands:
        w = window_matches(rec, ref)
        if w:
            rows.append((float(np.median(w)), float(np.min(w)), float(np.max(w)), len(w), tag))
    for med, mn, mx, k, tag in sorted(rows, reverse=True):
        print(f'  median {med:.3f}  min {mn:.3f}  max {mx:.3f}  ({k} windows)  {tag}')
    return rows


def layout(path):
    bank = zsnd.load(path, strict=False)
    for s in bank.samples:
        ch = 2 if s.raw[2] & FLAG_STEREO else 1
        pcm = decode_file(bank, bank.files[s.u16(0)], ch)
        r = {'bank': path, 'platform': bank.platform, 'flags': hex(s.raw[2]), 'rate': s.u32(4),
             'frames': int(pcm.shape[1])}
        if s.raw[2] & FLAG_LAYERED:
            r['layout'] = 'xml1' if bank.platform == 'xbox' else detect_layout(pcm, ch, s.u32(4))
        print(json.dumps(r))


# ---------------------------------------------------------------- CLI

def _job(args):
    src, dst, opts = args
    try:
        return fix_bank(src, dst, **opts)
    except Skip as e:
        print('SKIP', e, flush=True)
        return {'in': src, 'out': None, 'skipped': str(e)}
    except Exception as e:  # keep the batch going; the report lists failures
        import traceback
        traceback.print_exc()
        return {'in': src, 'out': dst, 'error': repr(e), 'trace': traceback.format_exc()}


def collect(inputs, only):
    out = []
    for inp in inputs:
        paths = [inp] if os.path.isfile(inp) else sorted(zsnd.iter_banks(inp))
        for p in paths:
            base = os.path.basename(p).lower()
            if not base.endswith(('_a.zss', '_c.zss')):
                continue
            if only and base.rsplit('_', 1)[0] not in only and base[:-4] not in only:
                continue
            b = zsnd.load(p, strict=False)
            if b.samples and all(s.raw[2] & FLAG_STEREO for s in b.samples):
                out.append(p.replace('\\', '/'))
    return out


def main(argv):
    if argv and argv[0] == 'simulate':
        ap = argparse.ArgumentParser(prog='fix_music.py simulate')
        ap.add_argument('banks', nargs='+')
        ap.add_argument('--wav')
        ap.add_argument('--wav-seconds', type=float)
        a = ap.parse_args(argv[1:])
        for p in a.banks:
            for r in simulate(p, a.wav, a.wav_seconds):
                print(json.dumps(r))
        return
    if argv and argv[0] == 'match':
        ap = argparse.ArgumentParser(prog='fix_music.py match')
        ap.add_argument('recording')
        ap.add_argument('banks', nargs='+')
        ap.add_argument('--xml1', help='XML1 Xbox bank to use as the reference (layers split at 32768 frames)')
        a = ap.parse_args(argv[1:])
        match(a.recording, a.banks, a.xml1)
        return
    if argv and argv[0] == 'layout':
        for p in argv[1:]:
            layout(p)
        return
    if argv and argv[0] == 'fix':
        argv = argv[1:]
    ap = argparse.ArgumentParser(prog='fix_music.py')
    ap.add_argument('inputs', nargs='*')
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--rate', default='keep', help="keep (XML1's 44100, default) or 22050")
    ap.add_argument('--encoder', default='beam', choices=['beam', 'greedy'])
    ap.add_argument('--seam', default='xfade', choices=['xfade', 'hard'])
    ap.add_argument('--flatten', choices=['layer0', 'mix'],
                    help='fallback: ONE plain stereo stream (layer 0, or layer0+layer1), 0x20 cleared')
    ap.add_argument('--only', help='comma list of zones (nyc1) or banks (nyc1_c)')
    ap.add_argument('--jobs', type=int, default=os.cpu_count() or 1)
    ap.add_argument('--wav', help='write engine-simulated voice WAVs to DIR/<bank>/')
    ap.add_argument('--wav-seconds', type=float, default=None)
    ap.add_argument('--force', action='store_true', help='re-process PC banks that are already in XML2 layout')
    a = ap.parse_args(argv)
    only = set(x.strip().lower() for x in a.only.split(',')) if a.only else None
    banks = collect(a.inputs or [XBOX_ROOT], only)
    opts = {'rate_mode': a.rate, 'body': a.encoder, 'seam': a.seam, 'flatten': a.flatten, 'force': a.force,
            'wav_dir': a.wav, 'wav_seconds': a.wav_seconds}
    jobs = [(p, os.path.join(a.out, *rel3(p).split('/')).replace('\\', '/'), opts) for p in banks]
    jobs.sort(key=lambda j: -os.path.getsize(j[0]))          # biggest first for better packing
    print('sound codec:', adpcm.codec_status(), flush=True)
    print(f'{len(jobs)} music bank(s) -> {a.out}', flush=True)
    if a.jobs > 1 and len(jobs) > 1:
        from multiprocessing import Pool
        with Pool(min(a.jobs, len(jobs))) as pool:
            reps = pool.map(_job, jobs, chunksize=1)
    else:
        reps = [_job(j) for j in jobs]
    os.makedirs(a.out, exist_ok=True)
    rp = os.path.join(a.out, '_fix_music_report.json')
    with open(rp, 'w') as fh:
        json.dump(reps, fh, indent=1)
    bad = [r for r in reps if 'error' in r]
    skipped = [r for r in reps if 'skipped' in r]
    print(f'done: {len(reps) - len(bad) - len(skipped)} ok, {len(skipped)} skipped, {len(bad)} failed; report {rp}')
    for r in bad:
        print('FAILED', r['in'], r['error'])


if __name__ == '__main__':
    main(sys.argv[1:])
