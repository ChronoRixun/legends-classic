"""Offline validation of tools/fix_music.py (no game needed).

    python research/sound/music0x20/validate_music.py [zone=nyc1] [--banks DIR] [--no-wav]

1. Independent path (own code, not fix_music's): decode the XML1 Xbox _c bank, split into layers at 32768 frames
   (XML1 layout), decode the fixed PC bank and the old 1:1 conversion exactly as XMen2.exe streams them
   (continuous IMA, 8192-frame alternation, EOF rule), and compare every voice with every source layer:
   lag-0 correlation over 5 s windows (min / median) and SNR.
2. In-game evidence: tonight's loopback recordings vs the old bank's simulated voices (proves the engine model).
3. Continuity / seams: reference-free click ratio at the 8192-frame switch points for the fixed voices, the source
   layers, XML2's own layered banks (abug_c, new_c, sewer_c, boss1_c) and XML2's plain town1_c (control).
4. Loudness / spectrum: fixed voices vs XML1 source vs XML2 town1_c and XML2 layered voices.
5. WAVs (research/sound/music0x20/wav/<zone>_c/): XML1 reference layers and what XML2 played from the OLD bank.
Writes research/sound/music0x20/validation_<zone>.json.
"""
import os as _os  # public export: the repo root and the XML2 install instead of the author's absolute paths
_REPO = _os.path.abspath(__file__).replace('\\', '/').rsplit('/research/', 1)[0]
_XML2 = (_os.environ.get('XML2_DIR') or 'X-Men Legends II').replace('\\', '/')
import json, os, sys, wave
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'research', 'sound'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import zsnd, adpcm  # noqa: E402
import fix_music as fm  # noqa: E402  (only for metrics helpers click_ratio/spectrum/level and write_wav)
from audio_match import load as load_rec, RATE  # noqa: E402

X1 = os.path.join(ROOT, 'xml1_xbox', 'sounds', 'zsds')
X2 = _XML2 + '/Sounds/eng'
OLD = os.path.join(ROOT, 'research', 'sound', 'out', 'ima', 'eng')
REC = os.path.join(ROOT, 'research', 'overlays')


def find(root, name):
    for p in zsnd.iter_banks(root):
        if os.path.basename(p).lower() == name.lower():
            return p
    return None


# ---- independent decoders / splitters -------------------------------------------------------------------------
def xbox_pcm(path):
    b = zsnd.load(path)
    s = b.samples[0]
    ch = 2 if s.raw[2] & 2 else 1
    chans, _ = adpcm.xbox_decode(b.file_bytes(b.files[s.u16(0)]), ch)
    return np.array([np.array(c, dtype=np.int32) for c in chans]), s.u32(4), s.raw[2]


def xml1_layers(pcm):
    """XML1 default.xbe: reads of 2 x 0x9000 bytes (2 x 32768 frames); last read r -> r-32768 frames per voice."""
    C = 32768
    out = [[], []]
    pos, T = 0, pcm.shape[1]
    while pos < T:
        got = min(T - pos, 2 * C)
        per = C if got == 2 * C else got - C
        if per <= 0:
            break
        out[0].append(pcm[:, pos:pos + per])
        out[1].append(pcm[:, pos + C:pos + C + per])
        pos += got
    return [np.concatenate(o, axis=1) for o in out]


def xml2_voices(path):
    """XMen2.exe: continuous IMA from (0,0) (0x595b20); refill = nsub*0x8000 PCM bytes; chunk i -> voice i;
    final partial read: got - (nsub-1)*0x8000 bytes per voice (0x595d60)."""
    b = zsnd.load(path)
    s = b.samples[0]
    ch = 2 if s.raw[2] & 2 else 1
    nsub = 2 if s.raw[2] & 0x20 else 1
    chans = adpcm.pc_decode(b.file_bytes(b.files[s.u16(0)]), ch)
    pcm = np.array([np.array(c, dtype=np.int32) for c in chans])
    C = 0x8000 // (2 * ch)
    out = [[] for _ in range(nsub)]
    pos, T = 0, pcm.shape[1]
    while pos < T:
        got = min(T - pos, nsub * C)
        per = C if got == nsub * C else got - (nsub - 1) * C
        if per <= 0:
            break
        for i in range(nsub):
            out[i].append(pcm[:, pos + i * C:pos + i * C + per])
        pos += got
    return [np.concatenate(o, axis=1) for o in out], s.u32(4), s.raw[2]


# ---- comparison helpers ---------------------------------------------------------------------------------------
def win_corr(a, b, rate, win_s=5.0):
    """lag-0 correlation of mono a vs b in consecutive windows -> (min, median, overall)."""
    n = min(a.shape[1], b.shape[1])
    u, v = a[:, :n].mean(axis=0).astype(np.float64), b[:, :n].mean(axis=0).astype(np.float64)
    w = int(win_s * rate)
    cs = []
    for k in range(0, n - w + 1, w):
        x, y = u[k:k + w] - u[k:k + w].mean(), v[k:k + w] - v[k:k + w].mean()
        d = np.sqrt((x * x).sum() * (y * y).sum())
        if d > 0:
            cs.append(float((x * y).sum() / d))
    x, y = u - u.mean(), v - v.mean()
    return {'min': round(min(cs), 3), 'median': round(float(np.median(cs)), 3),
            'overall': round(float((x * y).sum() / np.sqrt((x * x).sum() * (y * y).sum())), 3)}


def snr(ref, x):
    n = min(ref.shape[1], x.shape[1])
    r, d = ref[:, :n].astype(np.float64), x[:, :n].astype(np.float64)
    e = ((r - d) ** 2).sum()
    return round(float(10 * np.log10((r ** 2).sum() / e)), 2) if e else float('inf')


def mono11k(x, rate):
    m = x.mean(axis=0).astype(np.float64)
    return np.interp(np.arange(0, len(m), rate / RATE), np.arange(len(m)), m)


def main(argv):
    zone = argv[0] if argv and not argv[0].startswith('--') else 'nyc1'
    banks = argv[argv.index('--banks') + 1] if '--banks' in argv else os.path.join(HERE, 'banks', 'eng')
    wav = '--no-wav' not in argv
    res = {'zone': zone}
    x1c, x1a = find(X1, zone + '_c.zss'), find(X1, zone + '_a.zss')
    fixed_c, fixed_a = find(banks, zone + '_c.zss'), find(banks, zone + '_a.zss')
    old_c = find(OLD, zone + '_c.zss') or find(os.path.join(ROOT, 'research', 'sound', 'out', 'all_ima', 'eng'), zone + '_c.zss')
    src, rate1, fl1 = xbox_pcm(x1c)
    L = xml1_layers(src)
    A, _, _ = xbox_pcm(x1a)
    res['xml1_source'] = {'bank': x1c, 'flags': hex(fl1), 'rate': rate1, 'frames': int(src.shape[1]),
                          'layer_frames': [int(l.shape[1]) for l in L], 'a_frames': int(A.shape[1]),
                          'layer0_vs_a': win_corr(L[0], A, rate1), 'layer1_vs_a': win_corr(L[1], A, rate1),
                          'layer0_vs_layer1': win_corr(L[0], L[1], rate1),
                          'layer_levels': [fm.level(l) for l in L]}
    print('XML1 source', json.dumps(res['xml1_source']))

    def compare(tag, path):
        V, r, fl = xml2_voices(path)
        Lr = L
        if r != rate1:                   # resampled output: compare against the resampled layers
            Lr, _ = fm.resample(L, rate1, r)
        d = {'bank': path, 'flags': hex(fl), 'rate': r, 'voice_frames': [int(v.shape[1]) for v in V]}
        for i, v in enumerate(V):
            for j, l in enumerate(Lr):
                d[f'voice{i}_vs_layer{j}'] = {**win_corr(v, l, r), 'snr_db': snr(l, v)}
        if len(V) == 2:
            m = min(V[0].shape[1], V[1].shape[1])
            d['mix_vs_layer0+1'] = {**win_corr(V[0][:, :m] + V[1][:, :m], Lr[0] + Lr[1], r),
                                    'snr_db': snr(Lr[0] + Lr[1], V[0][:, :m] + V[1][:, :m])}
        res[tag] = d
        print(tag, json.dumps(d))
        return V, r

    Vf, rf = compare('fixed_bank', fixed_c)
    Vo, ro = compare('old_bank', old_c)

    # ---- 2. recordings vs old-bank engine voices
    from fix_music import window_matches
    recs = {}
    for rn in ('nyc1_music_only.wav', 'nyc1_ingame.wav', 'nyc1_combat.wav'):
        rp = os.path.join(REC, rn)
        if zone != 'nyc1' or not os.path.exists(rp):
            continue
        rec = load_rec(rp)
        row = {}
        cands = {'old voice0': Vo[0], 'old voice1': Vo[1],
                 'old voice0+1': Vo[0][:, :Vo[1].shape[1]] + Vo[1], 'XML1 layer0': L[0], 'XML1 layer0+1': L[0] + L[1]}
        for k, v in cands.items():
            w = window_matches(rec, mono11k(v, ro if k.startswith('old') else rate1))
            row[k] = {'median': round(float(np.median(w)), 3), 'min': round(float(np.min(w)), 3)}
        recs[rn] = row
        print('recording', rn, json.dumps(row))
    res['recordings_vs_old_bank'] = recs
    # the same test on the fixed bank, using its own voice 0 as a perfect 'recording' of idle play
    fv0 = mono11k(Vf[0][:, :int(40 * rf)], rf)
    ov0 = mono11k(Vo[0][:, :int(40 * ro)], ro)
    res['match_tool_selftest'] = {
        'fixed_voice0_as_recording_vs_XML1_layer0': np.round(np.percentile(window_matches(fv0, mono11k(L[0], rate1)), [0, 50]), 3).tolist(),
        'old_voice0_as_recording_vs_XML1_layer0': np.round(np.percentile(window_matches(ov0, mono11k(L[0], rate1)), [0, 50]), 3).tolist()}
    print('match self-test [min, median]', json.dumps(res['match_tool_selftest']))

    # ---- 3/4. seams, loudness, spectra vs XML2
    C = 8192
    table = {}

    def row(tag, x, rate):
        table[tag] = {**fm.level(x), 'click_ratio_8192': fm.click_ratio(x, C), **fm.spectrum(x, rate)}

    row('xml1 layer0 (source)', L[0], rate1)
    row('xml1 layer1 (source)', L[1], rate1)
    row('xml1 layer0+1 (source)', L[0] + L[1], rate1)
    row('fixed voice0 (idle)', Vf[0], rf)
    row('fixed voice1', Vf[1], rf)
    row('fixed voice0+1 (combat)', Vf[0] + Vf[1], rf)
    row('old voice0 (what XML2 played)', Vo[0], ro)
    for n in ('abug_c', 'new_c', 'sewer_c', 'boss1_c'):
        V2, r2, _ = xml2_voices(find(X2, n + '.zss'))
        m = min(V2[0].shape[1], V2[1].shape[1])
        row(f'XML2 {n} voice0', V2[0], r2)
        row(f'XML2 {n} voice0+1', V2[0][:, :m] + V2[1][:, :m], r2)
    T2, r2, _ = xml2_voices(find(X2, 'town1_c.zss'))
    row('XML2 town1_c (plain, control)', T2[0], r2)
    res['seams_levels_spectra'] = table
    for k, v in table.items():
        print(f'  {k:34s} rms {v["rms_dbfs"]:6.1f}  peak {v["peak_dbfs"]:6.1f}  click {v["click_ratio_8192"]}  '
              f'centroid {v.get("centroid_hz")}  bands {v.get("band_energy")}')

    # ---- 5. WAVs
    if wav:
        d = os.path.join(HERE, 'wav', zone + '_c')
        fm.write_wav(os.path.join(d, 'xml1_reference_layer0_out_of_combat.wav'), L[0], rate1)
        fm.write_wav(os.path.join(d, 'xml1_reference_layer1_combat_layer_alone.wav'), L[1], rate1)
        fm.write_wav(os.path.join(d, 'xml1_reference_layer0+1_in_combat.wav'), L[0] + L[1], rate1)
        fm.write_wav(os.path.join(d, 'OLD_bank_what_xml2_played_out_of_combat.wav'), Vo[0], ro, 60)
        res['wav_dir'] = d
    out = os.path.join(HERE, f'validation_{zone}.json')
    with open(out, 'w') as fh:
        json.dump(res, fh, indent=1)
    print('wrote', out)


if __name__ == '__main__':
    main(sys.argv[1:])
