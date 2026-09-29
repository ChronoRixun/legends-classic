"""xml1build.sound_selftest - the sound codecs against the pure-Python reference implementations, bit for bit: the
numpy path (research/sound/adpcm_np.py) and, when it is built, the compiled kernel (research/sound/ima_kernel.c via
adpcm_c.py) - the two backends adpcm.codec() chooses between for adpcm.py, convert_zsnd.py and tools/fix_music.py.

usage (from the repo root): python tools/xml1build/sound_selftest.py [--quick] [--require-kernel]
Run it both ways to cover both setups: as is (kernel built: python tools/build_sound_kernel.py) and with
XML1_SOUND_KERNEL=off (a PC without the kernel: numpy only).

  S1 xbox_decode_np == adpcm.xbox_decode_py (samples + stats) on mono and stereo files of real XML1 banks
  S2 pc_decode_np / pack_np / compare_np == pc_decode_py / pc_pack_py / compare_py
  S3 greedy lanes (encode_streams 'greedy') == encode_samples_py(search=True): real audio from random start states,
     plus silence, full-scale squares, clipping and single samples; many streams at once (lockstep + speculation)
  S4 beam lanes (encode_streams 'beam4') == encode_beam_py(width=4, cands=3), same inputs
  S5 wide beam lanes (adpcm_np.run_lanes 'wide') == fix_music.beam_window on the seam windows of a layered bank
  S6 fix_music.encode with adpcm_np (solve_chains over beam + wide units) == encode_channel with the pure-Python
     encoders, and fix_music.auto_holds == auto_hold (pure Python), on the first stretch of a layered bank
  K0 the compiled kernel: loaded and self-checked (adpcm_c.load), or why not - then K1..K6 are skipped
     (--require-kernel: a failure)
  K1 kernel decoders == the pure-Python results of S1 / S2 (samples + stats), on the same files
  K2 kernel greedy / beam4 (adpcm_c.encode_streams) == the pure-Python results of S3 / S4; adpcm.encode_samples /
     encode_beam (which use the kernel) too; input beyond the kernel's range goes to numpy
  K3 kernel wide beam, lazy and eager == fix_music.beam_window on the S5 windows (and the lazy mode really asked
     numpy's argpartition and recomputed samples)
  K4 kernel solve_chains == adpcm_np.solve_chains on chains that test its unit merging (beam4 runs of full and short
     windows, greedy runs, wide and empty units, extreme start states)
  K5 fix_music.encode / auto_holds with the kernel == the pure-Python results of S6
  K6 convert_zsnd.convert of real banks with the kernel == with numpy: same bytes, same report (temporary files)
Needs the XML1 disc files (xml1_xbox/sounds/zsds). Writes only temporary files. Exit code 0 = every check passed.
"""
import json
import os
import shutil
import sys
import tempfile
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))      # run as a file: make the xml1build package importable
from xml1build.lib import adpcm, adpcm_c, adpcm_np, convert_zsnd, fix_music, zsnd  # noqa: E402

ZSDS = os.path.join(ROOT, 'xml1_xbox', 'sounds', 'zsds')
FAIL = []
SKIPPED = []
REF = {}          # pure-Python results computed by S1..S6, checked again against the kernel by K1..K5


def check(tag, ok, what):
    print(('PASS ' if ok else 'FAIL ') + tag + ' ' + what, flush=True)
    if not ok:
        FAIL.append(tag + ' ' + what)


def bank(rel):
    return zsnd.load(os.path.join(ZSDS, *rel.split('/')))


def files_of(b, limit):
    out = []
    for f in b.files[:limit]:
        out.append((f, convert_zsnd.channels_of(b, f.index), b.file_bytes(f)))
    return out


def arr(chans):
    return [np.frombuffer(c, dtype=np.int16) if not isinstance(c, np.ndarray) else c for c in chans]


class pure_python:
    """Route adpcm's public encoders to the pure-Python references (for reference results)."""

    def __enter__(self):
        self.saved = adpcm.encode_beam, adpcm.encode_samples
        adpcm.encode_beam, adpcm.encode_samples = adpcm.encode_beam_py, adpcm.encode_samples_py

    def __exit__(self, *a):
        adpcm.encode_beam, adpcm.encode_samples = self.saved


def s1_s2(quick):
    n = 0
    REF['xbox'], REF['pc'] = [], []
    for rel, lim in (('a/c/aco_e_m.zsm', 11), ('x/_/x_common.zsm', 6 if quick else 40), ('m/e/menu_a.zss', 1),
                     ('n/y/nyc1_c.zss', 1)):
        for f, ch, data in files_of(bank(rel), lim):
            if quick and len(data) > 36 * ch * 20000:
                data = data[:36 * ch * 20000 + 7]            # keep a partial block: tail_bytes
            ref, st = adpcm.xbox_decode_py(data, ch)
            new, st2 = adpcm_np.xbox_decode_np(data, ch)
            ok = st == st2 and all(np.array_equal(np.frombuffer(r, np.int16), c) for r, c in zip(ref, new))
            if not ok:
                check('S1', False, f'{rel} file {f.index}')
                return
            REF['xbox'].append((f'{rel} file {f.index}', data, ch, ref, st))
            n += 1
            if f.index < 3:                                  # S2 on real encoder output
                nibs = [np.random.default_rng(f.index).integers(0, 16, len(ref[0]), dtype=np.uint8) for _ in range(ch)]
                pc = adpcm.pc_pack_py([c.tolist() for c in nibs])
                if pc != adpcm_np.pack_np(nibs):
                    check('S2', False, f'pack {rel} {f.index}')
                    return
                d1, d2 = adpcm.pc_decode_py(pc, ch), adpcm_np.pc_decode_np(pc, ch)
                if not all(np.array_equal(np.frombuffer(a, np.int16), b) for a, b in zip(d1, d2)):
                    check('S2', False, f'pc_decode {rel} {f.index}')
                    return
                REF['pc'].append((f'{rel} file {f.index}', pc, ch, d1))
                if adpcm.compare_py(ref, d1) != adpcm_np.compare_np(new, d2):
                    check('S2', False, f'compare {rel} {f.index}')
                    return
    odd = adpcm.pc_pack_py([[1, 2, 3]]) == adpcm_np.pack_np([np.array([1, 2, 3], np.uint8)])
    long_ok = True                                           # streams longer than one decoder piece (CHUNK)
    rng = np.random.default_rng(99)
    for ch, nbytes in ((1, adpcm_np.CHUNK + 12345), (2, adpcm_np.CHUNK + 777)):
        pc = rng.integers(0, 256, nbytes, dtype=np.uint8).tobytes()
        d1, d2 = adpcm.pc_decode_py(pc, ch), adpcm_np.pc_decode_np(pc, ch)
        long_ok &= all(np.array_equal(np.frombuffer(a, np.int16), b) for a, b in zip(d1, d2))
        long_ok &= adpcm.compare_py(d1, [a[::-1] for a in d1]) == adpcm_np.compare_np(d2, [a[::-1] for a in d2])
        REF['pc'].append((f'random {ch} ch {nbytes} bytes', pc, ch, d1))
    check('S1', True, f'xbox_decode: {n} files identical (samples + stats)')
    check('S2', odd and long_ok, 'pc_decode / pc_pack (incl. odd mono length) / compare identical, also across '
          'decoder pieces')


def test_streams(quick, rng):
    """(samples, pred, idx) cases: real audio from several banks with random / edge start states + synthetic."""
    cases = []
    for rel in ('a/c/aco_e_m.zsm', 'x/_/x_common.zsm', 'n/y/nyc1_c.zss', 'm/a/manbst_v.zss'):
        b = bank(rel)
        for f, ch, data in files_of(b, 3):
            x = adpcm_np.xbox_decode_np(data[:36 * ch * (300 if quick else 1200)], ch)[0][0].astype(np.int64)
            for _ in range(2):
                a = int(rng.integers(0, max(1, len(x) - 10)))
                ln = int(rng.integers(1, 9000 if quick else 30000))
                cases.append((x[a:a + ln], int(rng.integers(-32768, 32768)), int(rng.integers(0, 89))))
            cases.append((x, 0, 0))
    sq = np.where(np.arange(6000) // 37 % 2, 32767, -32768).astype(np.int64)
    cases += [(np.zeros(5000, np.int64), 0, 0), (np.zeros(3000, np.int64), 12000, 88), (sq, 0, 0), (sq, -32768, 88),
              (np.full(2500, 32767, np.int64), 32767, 40), (np.array([5], np.int64), 0, 0),
              (np.array([], np.int64), 3, 4), (rng.integers(-32768, 32768, 4000), 0, 0)]
    return cases


def s3_s4(quick):
    rng = np.random.default_rng(12345)
    cases = test_streams(quick, rng)
    REF['streams'] = cases
    for tag, kind in (('S3', 'greedy'), ('S4', 'beam4')):
        t0 = time.time()
        st = {}
        got = adpcm_np.encode_streams([(kind, x, p, i) for x, p, i in cases], stats=st)
        bad = 0
        refs = []
        for (x, p, i), (nl, end) in zip(cases, got):
            if kind == 'greedy':
                ref = []
                e = adpcm.encode_samples_py(x.tolist(), p, i, ref, True)
            else:
                ref, e = adpcm.encode_beam_py(x.tolist(), p, i, width=4, cands=3)
            refs.append((ref, tuple(e)))
            if list(nl) != list(ref) or tuple(end) != tuple(e):
                bad += 1
        REF[kind] = refs
        check(tag, not bad, f'{kind}: {len(cases)} streams ({sum(len(c[0]) for c in cases)} samples) identical'
              + (f' - {bad} differ' if bad else '') + f'; solver {st}; {time.time() - t0:.0f}s')
        # the public adpcm entry points route long inputs to numpy when there is no kernel
        x = cases[2][0][:6000]
        kernel_saved = adpcm.kernel
        adpcm.kernel = lambda: None
        try:
            if kind == 'greedy':
                a, b = [], []
                ok = (adpcm.encode_samples(x, 7, 9, a, True) == adpcm.encode_samples_py(x.tolist(), 7, 9, b, True)
                      and a == b)
            else:
                ok = adpcm.encode_beam(x, 7, 9, width=4, cands=3) == adpcm.encode_beam_py(x.tolist(), 7, 9, 4, 3)
        finally:
            adpcm.kernel = kernel_saved
        check(tag, ok, 'adpcm public entry point (numpy route) == reference')


def layered(quick):
    b = bank('n/y/nyc1_c.zss')
    pcm = fix_music.decode_file(b, b.files[0], 2)
    if quick:
        pcm = pcm[:, :2 * 32768 * 3]
    layers, _ = fix_music.split_layers(pcm, fix_music.xml1_chunk_frames(2))
    return layers


def s5_s6(quick):
    layers = layered(quick)
    fade, hold, head = fix_music.seam_params(44100, 'xfade')
    C2 = fix_music.xml2_chunk_frames(2)
    target, weights, wins, _ = fix_music.build_stream(layers, C2, fade, hold, head)
    x = target[0].astype(np.int64)
    rng = np.random.default_rng(7)
    W = wins[:40 if quick else 160]
    starts = [(int(rng.integers(-32768, 32768)), int(rng.integers(0, 89))) for _ in W]
    t0 = time.time()
    got = adpcm_np.run_lanes('wide', [(x[a:e], weights[a:e]) for a, e in W], starts)
    bad = 0
    refs = []
    for (a, e), s, (nl, end) in zip(W, starts, got):
        rn, re_ = fix_music.beam_window(x[a:e], weights[a:e], *s)
        refs.append((rn, tuple(re_)))
        bad += not (np.array_equal(nl, rn) and tuple(end) == tuple(re_))
    REF['wide'] = ([(x[a:e], weights[a:e]) for a, e in W], starts, refs)
    check('S5', not bad, f'wide beam: {len(W)} windows identical to fix_music.beam_window' +
          (f' - {bad} differ' if bad else '') + f'; {time.time() - t0:.0f}s')
    # S6: whole chain on a prefix, against encode_channel with the pure-Python encoders
    N = 60000 if quick else 200000
    wsub = [(a, min(e, N)) for a, e in wins if a < N]
    L0, L1 = (l.astype(np.float64) for l in layers)
    n = layers[0].shape[1]
    ends = [min(n, (k + 1) * C2) for k in range(min(-(-n // C2) - 1, 12))]
    with pure_python():
        holds = [fix_music.auto_hold(L0, L1, e, fade) for e in ends]
        t0 = time.time()
        ref = [fix_music.encode_channel(c.astype(np.int64)[:N], weights[:N], wsub, 'beam') for c in target]
        tr = time.time() - t0
    check('S6', fix_music.auto_holds(L0, L1, ends, fade, codec=adpcm_np) == holds,
          f'auto_holds (numpy) == auto_hold (pure Python) on {len(ends)} seams')
    t0 = time.time()
    st = {}
    new = fix_music.encode(target[:, :N], weights[:N], wsub, 'beam', stats=st, codec=adpcm_np)
    check('S6', new == fix_music.pack(ref), f'fix_music.encode (numpy) == encode_channel (pure Python) on {N} frames '
          f'x 2, {len(wsub)} windows; {tr:.0f}s -> {time.time() - t0:.0f}s; solver {st}')
    REF['s6'] = (target[:, :N], weights[:N], wsub, fix_music.pack(ref), (L0, L1, ends, fade, holds))


# ---------------------------------------------------------------- the compiled kernel

def k0(require):
    ok = adpcm_c.load()
    if ok:
        check('K0', True, 'kernel: ' + adpcm_c.STATUS)
    elif require:
        check('K0', False, 'kernel required: ' + adpcm_c.STATUS)
    else:
        print('SKIP K0..K6 - ' + adpcm_c.STATUS, flush=True)
        SKIPPED.append('K')
    return ok


def k1():
    bad = []
    for what, data, ch, ref, st in REF['xbox']:
        new, st2 = adpcm_c.xbox_decode_np(data, ch)
        if not (st == st2 and new.dtype == np.int16 and
                all(np.array_equal(np.frombuffer(r, np.int16), c) for r, c in zip(ref, new))):
            bad.append('xbox ' + what)
    for what, pc, ch, ref in REF['pc']:
        new = adpcm_c.pc_decode_np(pc, ch)
        if not all(np.array_equal(np.frombuffer(r, np.int16), c) for r, c in zip(ref, new)):
            bad.append('pc ' + what)
    edge = []                                               # empty / partial data, bad step indices, both paths
    for ch, data in ((1, b''), (2, b'\x01' * 71), (1, bytes(range(256)) * 3), (2, bytes([0, 0, 200, 7] * 2 + [0x9f] * 64))):
        a, sa = adpcm_c.xbox_decode_np(data, ch)
        r, sr = adpcm.xbox_decode_py(data, ch)
        edge.append(sa == sr and all(np.array_equal(np.frombuffer(q, np.int16), c) for q, c in zip(r, a)))
        edge.append(all(np.array_equal(np.frombuffer(q, np.int16), c)
                        for q, c in zip(adpcm.pc_decode_py(data, ch), adpcm_c.pc_decode_np(data, ch))))
    check('K1', not bad and all(edge), f'kernel decoders == pure Python on {len(REF["xbox"])} Xbox files and '
          f'{len(REF["pc"])} PC streams + {len(edge)} edge cases' + (f' - differ: {bad[:5]}' if bad else '')
          + ('' if all(edge) else f' - edge cases {edge}'))


def k2():
    cases = REF['streams']
    for kind in ('greedy', 'beam4'):
        t0 = time.time()
        got = adpcm_c.encode_streams([(kind, x, p, i) for x, p, i in cases])
        bad = sum(1 for (nl, end), (ref, e) in zip(got, REF[kind]) if list(nl) != list(ref) or tuple(end) != e)
        check('K2', not bad, f'kernel {kind}: {len(cases)} streams identical to the pure-Python encoder'
              + (f' - {bad} differ' if bad else '') + f'; {time.time() - t0:.2f}s')
    x = cases[2][0][:6000]
    a, b = [], []
    ok = adpcm.encode_samples(x, 7, 9, a, True) == adpcm.encode_samples_py(x.tolist(), 7, 9, b, True) and a == b
    ok &= adpcm.encode_beam(x, 7, 9, width=4, cands=3) == adpcm.encode_beam_py(x.tolist(), 7, 9, 4, 3)
    ok &= adpcm.encode_beam(x[:3000], 7, 9, 4, 3, window=333) == adpcm.encode_beam_py(x[:3000].tolist(), 7, 9, 4, 3, 333)
    big = np.array([0, 5, 1 << 21, 7] * 700, dtype=np.int64)            # beyond the kernel's range -> numpy
    ok &= not adpcm_c.fits(big) and adpcm_c.fits(np.array([-32768, 32767])) and not adpcm_c.fits(x, 0, 89)
    saved = adpcm_np.encode_streams, adpcm_np.solve_chains
    adpcm_np.encode_streams = adpcm_np.solve_chains = lambda *a, **k: 'numpy'
    try:
        ok &= adpcm_c.encode_streams([('beam4', big, 0, 0)]) == 'numpy'
        ok &= adpcm_c.solve_chains([((0, 0), [('greedy', (big,))])]) == 'numpy'
        ok &= adpcm_c.solve_chains([((1 << 22, 0), [('greedy', (x,))])]) == 'numpy'
    finally:
        adpcm_np.encode_streams, adpcm_np.solve_chains = saved
    check('K2', ok, 'adpcm.encode_samples / encode_beam through the kernel (also window 333) == reference; '
          'input beyond the kernel range is handed to numpy')


def k3():
    pays, starts, refs = REF['wide']
    for lazy in (True, False):
        st = {}
        t0 = time.time()
        bad = 0
        for (x, w), s, (rn, re_) in zip(pays, starts, refs):
            nl, end = adpcm_c.wide(x, w, s[0], s[1], lazy=lazy, stats=st)
            bad += not (np.array_equal(nl, rn) and end == re_)
        used = st.get('wide_argpartition_calls', 0) > 0 and (not lazy or st.get('wide_recomputed', 0) > 0)
        check('K3', not bad and used, f'kernel wide beam ({"lazy" if lazy else "eager"}): {len(pays)} windows identical '
              f'to fix_music.beam_window' + (f' - {bad} differ' if bad else '') + f'; {time.time() - t0:.2f}s; {st}')
    got = adpcm_c.run_lanes('wide', pays, starts)
    check('K3', all(np.array_equal(a[0], r[0]) and tuple(a[1]) == r[1] for a, r in zip(got, refs)),
          'adpcm_c.run_lanes(wide) == fix_music.beam_window')


def k4():
    rng = np.random.default_rng(4)
    b = bank('x/_/x_common.zsm')
    x = np.concatenate([adpcm_np.xbox_decode_np(b.file_bytes(f), convert_zsnd.channels_of(b, f.index))[0][0]
                        for f in b.files[:6]]).astype(np.int64)[:20000]
    w = np.where(np.arange(len(x)) % 300 < 100, 4.0, np.where(np.arange(len(x)) % 300 < 250, 1.0, 0.25))

    def U(kind, a, e):
        return (kind, (x[a:e], w[a:e]) if kind == 'wide' else (x[a:e],))
    chains = [
        ((0, 0), [U('beam4', 0, 1024), U('beam4', 1024, 2048), U('beam4', 2048, 2500), U('wide', 2500, 2610),
                  U('beam4', 2610, 3634), U('beam4', 3634, 3700), U('greedy', 3700, 3800)]),
        ((123, 40), [U('beam4', 0, 500), U('beam4', 500, 1524), U('beam4', 1524, 2548)]),     # short then full
        ((5, 5), [U('greedy', 0, 10), U('greedy', 10, 3000), U('greedy', 3000, 3000), U('greedy', 3000, 5000)]),
        ((0, 0), [U('beam4', 0, 0), U('beam4', 0, 1024), U('beam4', 1024, 1024), U('beam4', 1024, 1100)]),
        ((-32768, 88), [U('wide', 0, 0), U('wide', 0, 50), U('beam4', 50, 750), U('beam4', 750, 1450),
                        U('beam4', 1450, 1850), U('beam4', 1850, 2550)]),                     # runs of 700
        ((32767, 0), [U('wide', 5000, 5200), U('wide', 5200, 5300), U('greedy', 5300, 9000), U('beam4', 9000, 10024)]),
    ]
    for c in range(20):                                         # random chains of fix_music's shape
        units, pos = [], int(rng.integers(0, 5000))
        for _ in range(int(rng.integers(1, 8))):
            kind = ('beam4', 'greedy', 'wide')[int(rng.integers(0, 3))]
            ln = int(rng.integers(0, 1100 if kind != 'wide' else 200))
            if pos + ln > len(x):
                break
            units.append(U(kind, pos, pos + ln))
            pos += ln
        chains.append(((int(rng.integers(-32768, 32768)), int(rng.integers(0, 89))), units))
    got = adpcm_c.solve_chains(chains)
    ref = adpcm_np.solve_chains(chains)
    bad = 0
    for (a, ea), (r, er) in zip(got, ref):
        bad += not (len(a) == len(r) and all(np.array_equal(p, q) for p, q in zip(a, r)) and tuple(ea) == tuple(er))
    check('K4', not bad, f'kernel solve_chains == adpcm_np.solve_chains on {len(chains)} chains '
          f'({sum(len(u) for _, u in chains)} units)' + (f' - {bad} differ' if bad else ''))


def k5():
    target, weights, wsub, ref, (L0, L1, ends, fade, holds) = REF['s6']
    t0 = time.time()
    new = fix_music.encode(target, weights, wsub, 'beam', codec=adpcm_c)
    check('K5', new == ref, f'fix_music.encode (kernel) == encode_channel (pure Python) on {target.shape[1]} frames x 2, '
          f'{len(wsub)} windows; {time.time() - t0:.1f}s')
    check('K5', fix_music.auto_holds(L0, L1, ends, fade, codec=adpcm_c) == holds,
          f'auto_holds (kernel) == auto_hold (pure Python) on {len(ends)} seams')


def k6(quick):
    tmp = tempfile.mkdtemp(prefix='sound_selftest_')
    saved = adpcm.codec, adpcm.codec_name
    try:
        rels = [('a/c/aco_e_m.zsm', 'beam'), ('m/e/menu_a.zss', 'auto')] + ([] if quick else [('c/o/colos_v.zsm', 'auto')])
        for rel, enc in rels:
            reps, outs = [], []
            for name, mod in (('numpy', adpcm_np), ('kernel', adpcm_c)):
                adpcm.codec, adpcm.codec_name = (lambda m=mod: m), (lambda n=name: n)
                out = os.path.join(tmp, name, *rel.split('/'))
                t0 = time.time()
                r = convert_zsnd.convert(os.path.join(ZSDS, *rel.split('/')), out, encoder=enc,
                                         rekey=[('character/', 'char/')], log=lambda *a, **k: None)
                r = {k: v for k, v in json.loads(json.dumps(r)).items() if k not in ('seconds', 'codec', 'out')}
                reps.append((r, time.time() - t0))
                outs.append(open(out, 'rb').read())
            check('K6', outs[0] == outs[1] and reps[0][0] == reps[1][0],
                  f'convert {rel} ({enc}): kernel == numpy, {len(outs[1])} bytes + report; '
                  f'{reps[0][1]:.1f}s -> {reps[1][1]:.1f}s')
    finally:
        adpcm.codec, adpcm.codec_name = saved
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv):
    quick = '--quick' in argv
    t0 = time.time()
    print('sound codec:', adpcm.codec_status(), flush=True)
    s1_s2(quick)
    s3_s4(quick)
    s5_s6(quick)
    if k0('--require-kernel' in argv) and not FAIL:
        k1()
        k2()
        k3()
        k4()
        k5()
        k6(quick)
    print(f'{"FAILED: " + str(len(FAIL)) if FAIL else "all passed"}' + (' (kernel checks skipped)' if SKIPPED else '')
          + f' ({time.time() - t0:.0f}s)')
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
