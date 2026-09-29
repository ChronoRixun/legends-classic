"""xml1build.skins_selftest - SPEC 25: XML1 skins' blend weights (the elite Acolytes' spikes) and the V21 checks.

usage (from tools/): python -m xml1build.skins_selftest [--out <build>]
  T1 igb_file.rebuilt: every XML1 and XML2 actor IGB re-reads after rebuilt({}) with the same objects, fields and
     memory blocks; a resized block re-reads with its new size and every other block unchanged
  T2 skins.pad_blend_weights over every numeric XML1 actor: no blended array keeps 1-2 weights, every vertex keeps
     its weighted bones (same bone -> weight sums), positions / index buffers / other blocks untouched, the
     in-IGB names unchanged, idempotent (a second pass returns the same bytes)
  T3 skins.check_skin: the elite Acolyte 4805 against 48_acolyteenergy has no error and no skeleton mismatch, its
     two 2-weight arrays are listed (and gone once padded); injected defects (index outside the palette, weights
     off 1) are errors; AstralGhost's ponytail (3705 against 37_astralghost) is a skin / skeleton mismatch
  T4 (--out) V21 read-only over that build: 0 errors, the 13 disc mismatches as inherited warnings
Writes nothing. Never launches the game.
"""
from __future__ import annotations

import argparse
import collections
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xml1build import common as C                # noqa: E402
from xml1build import skins as SK                # noqa: E402
from xml1build.igb_file import IgbError, IgbFile  # noqa: E402

X1_ACTORS = X2_ACTORS = SRC = None
FAILS = []


def use_sources(src):
    """read the XML1 and XML2 actors through a Sources (SPEC 27): main() passes the --out build's
    (Sources.for_out: its _build/sources.json, else developer mode)."""
    global X1_ACTORS, X2_ACTORS, SRC
    SRC = src
    X1_ACTORS = src.x1_loose / 'actors'
    X2_ACTORS = src.xml2 / 'actors'


use_sources(C.Sources.developer())


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print('  FAIL', msg)
    return cond


def _snapshot(f):
    objs = [(o.ref, o.name, {s: fl.value for s, fl in o.fields.items()}) for o in f.objects]
    blocks = {r: bytes(f.data[o:o + n]) for r, (o, n) in f.blocks.items()}
    return objs, blocks


def t1():
    print('T1 igb_file.rebuilt')
    n = 0
    for d in (X1_ACTORS, X2_ACTORS):
        for p in sorted(d.iterdir()):
            if p.suffix.lower() != '.igb':
                continue
            try:
                f = IgbFile(p.read_bytes())
            except IgbError:
                continue
            g = IgbFile(f.rebuilt({}))
            n += 1
            if not check(_snapshot(f) == _snapshot(g), f'{p.name}: rebuilt({{}}) reads back differently'):
                break
    check(n > 950, f'only {n} actor IGBs read')
    f = IgbFile((X1_ACTORS / '4805.igb').read_bytes())
    va = [va for _g, va in SK._vertex_arrays(f) if va.get(6) == 0x221][0]
    ref = va.get(8)
    blob = bytes(range(7)) * 300
    g = IgbFile(f.rebuilt({ref: blob}))
    a, b = _snapshot(f), _snapshot(g)
    check(b[1][ref] == blob, 'resized block content')
    check({k: v for k, v in a[1].items() if k != ref} == {k: v for k, v in b[1].items() if k != ref},
          'other blocks changed by a resize')
    check(a[0] == b[0], 'objects changed by a resize')
    print(f'  {n} IGBs round-trip; a {len(blob)}-byte resize re-reads')


def _bone_weights(f, va):
    fmt, n = va.get(6), va.get(3)
    nw, ni = fmt >> 4 & 15, fmt >> 8 & 15
    wb, ib = f.block(va.get(7)), f.block(va.get(8))
    W = struct.unpack_from(f'<{n * nw}f', f.data, wb[0])
    I = f.data[ib[0]:ib[0] + n * ni]
    out = []
    for v in range(n):
        acc = collections.defaultdict(float)
        for k in range(nw):
            acc[I[v * ni + k]] += W[v * nw + k]
        out.append({i: round(w, 6) for i, w in acc.items() if abs(w) > 1e-9})
    return out


def t2():
    print('T2 pad_blend_weights over every numeric XML1 actor')
    padded = arrays = 0
    formats = collections.Counter()
    for p in sorted(X1_ACTORS.iterdir()):
        if p.suffix.lower() != '.igb' or not p.stem.isdigit() or p.stat().st_size == 0:
            continue
        data = p.read_bytes()
        out, changes = SK.pad_blend_weights(data)
        if not changes:
            check(out is data, f'{p.name}: unchanged file not returned as is')
            continue
        padded += 1
        arrays += len(changes)
        for c in changes:
            formats[f"{c['format']}->{c['new_format']}"] += 1
        f, g = IgbFile(data), IgbFile(out)
        fa = {va.ref: va for _geo, va in SK._vertex_arrays(f)}
        ga = {va.ref: va for _geo, va in SK._vertex_arrays(g)}
        check(fa.keys() == ga.keys(), f'{p.name}: vertex arrays differ')
        changed = set()
        for ref, va in fa.items():
            vb = ga[ref]
            nw = vb.get(6) >> 4 & 15
            check(nw == 0 or nw >= SK.MIN_WEIGHTS, f'{p.name}: array {ref} still {nw} weights')
            if va.get(6) >> 4 & 15:
                check(_bone_weights(f, va) == _bone_weights(g, vb), f'{p.name}: array {ref} bone weights changed')
            if va.get(6) != vb.get(6):
                changed |= {va.get(7), va.get(8)}
        fb, gb = _snapshot(f)[1], _snapshot(g)[1]
        for ref in fb:
            if ref not in changed:
                check(fb[ref] == gb[ref], f'{p.name}: block {ref} changed')
        check([(o.ref, o.name) for o in f.objects] == [(o.ref, o.name) for o in g.objects], f'{p.name}: objects')
        names = lambda x: sorted(o.get(2) for o in x.objects if isinstance(o.get(2), str))   # noqa: E731
        check(names(f) == names(g), f'{p.name}: object names changed')
        again, ch2 = SK.pad_blend_weights(out)
        check(again is out and not ch2, f'{p.name}: not idempotent')
    check(padded >= 30, f'only {padded} skins padded')   # 32 on the XML1 disc
    print(f'  {padded} skins, {arrays} arrays padded: {dict(formats)}')


def t3():
    print('T3 check_skin')
    skin = (X1_ACTORS / '4805.igb').read_bytes()
    db = (X1_ACTORS / '48_acolyteenergy.igb').read_bytes()
    r = SK.check_skin(skin, db)
    check(not r['errors'] and not r['mismatch'], f'4805: {r["errors"]} {r["mismatch"]}')
    check(sorted(fm for _g, fm in r['low_weight']) == ['0x10223', '0x221'], f'4805 low weights: {r["low_weight"]}')
    check(r['bones_used'].get('Bip01 Head', 0) > 0, 'bones_used')
    padded, _ = SK.pad_blend_weights(skin)
    r = SK.check_skin(padded, db)
    check(not r['errors'] and not r['low_weight'], f'4805 padded: {r["errors"]} {r["low_weight"]}')
    # defects: an index outside the palette, a weight off 1
    f = IgbFile(padded)
    va = [va for geo, va in SK._vertex_arrays(f) if 'outline' in geo][0]
    ib, wb = f.block(va.get(8)), f.block(va.get(7))
    f.buf[ib[0]] = 40
    struct.pack_into('<f', f.buf, wb[0], 5.0)
    r = SK.check_skin(f.edited(), db)
    check(any('outside the 32-entry blend palette' in e for e in r['errors']), f'palette defect: {r["errors"]}')
    check(any('do not sum to 1' in e for e in r['errors']), f'weight defect: {r["errors"]}')
    # a used bone the anim DB lacks: AstralGhost's ponytail (3705 against 37_astralghost)
    r = SK.check_skin((X1_ACTORS / '3705.igb').read_bytes(), (X1_ACTORS / '37_astralghost.igb').read_bytes())
    check(r['mismatch'].get('Bip01 Ponytail11') == 56 and r['mismatch'].get('Bip01 Ponytail1') == 24,
          f'missing bone: {r["mismatch"]}')
    print('  ok' if not FAILS else '  (see failures)')


def t4(out):
    print(f'T4 V21 over {out}')
    from xml1build import validate as V
    base = str(SRC.xml2)
    args = C.default_args(out=out, base=base, no_movies=True, jobs=4,
                          frontend=getattr(C.args_for_out(out, base), 'frontend', None))
    ctx = C.BuildContext(out, base, args=args, registry=C.Registry.load(Path(out) / '_build' / 'registry.json'))
    v = V.Validator(ctx)
    ck = V.Check('V21', 'skins')
    SK.validate(v, ck)
    print(f'  {ck.counts.get("skins_checked")} skins, {len(ck.errors)} errors, {len(ck.warnings)} warnings')
    for e in ck.errors[:10]:
        print('   ', e)
    check(not ck.errors, 'V21 errors')
    inherited = [w for w in ck.warnings if 'inherited' in w]
    check(len(inherited) >= 13, f'{len(inherited)} inherited skin / skeleton mismatch warnings (13 disc skins)')


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out')
    ap.add_argument('--base', default=str(C.DEFAULT_BASE))
    a = ap.parse_args(argv)
    use_sources(C.Sources.for_out(a.out, a.base) if a.out else C.Sources.developer(a.base))
    t1()
    t2()
    t3()
    if a.out:
        t4(a.out)
    print('FAILED' if FAILS else 'all passed', len(FAILS))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
