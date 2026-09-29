"""xml1build.automaps_selftest - SPEC 26: XML1 automap textures as XMen2.exe .zam automaps.

usage (from tools/): python -m xml1build.automaps_selftest [--out <build>] [--base "<XML2 folder>"]
                                                          [--all] [--asm-dir <research/scripts>]
  T1 the engine facts the converter rests on, re-read from the disassemblies (research/scripts/xml2_text.asm,
     xml1_text.asm): the .zam loader (version 9, 240-unit cells, grid 41 x 41, lists after it), the draw
     window's clamp to cells 0..39, the automap playfield's 0x2000-vertex builder and triangle-strip primitive,
     XML1's world -> texture transform (x 1/12 - automap_offset) and texture path
  T2 every retail XML2 .zam parses as the loader reads it, re-packs byte for byte, and 99.9% of its lists sit in
     the cell the grid names (x = index / 41, y = index % 41)
  T3 conversion of sample zones (--all: every XML1 automap): fidelity - rasterised back onto the texture, the white
     outlines are >= 0.93 recall / precision and the grey area >= 0.90 IoU; draw window <= 0x2000; no problems
  T4 placement: the XML1 nav cells of enclosed maps fall inside the drawn map (>= 0.97) with the transform, and
     well outside it (mean <= 0.75) with the rows flipped or the offset negated
  T5 (--out) V20 read-only over that build: 0 errors; nyc1_1_1 and a mansion hub have their .zam as the last
     package entry and no textures/automap entry
Writes nothing. Never launches the game.
"""
from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xml1build import common as C                # noqa: E402
from xml1build import automaps as A              # noqa: E402

ASM2 = ASM1 = X1_LOOSE = X1_ASSETS = None


def use_sources(src):
    """read the XML1 maps / textures and the disassemblies through a Sources (SPEC 27): main() passes the --out
    build's (Sources.for_out: its _build/sources.json, else developer mode)."""
    global ASM2, ASM1, X1_LOOSE, X1_ASSETS
    ASM2 = src.research / 'scripts' / 'xml2_text.asm'
    ASM1 = src.research / 'scripts' / 'xml1_text.asm'
    X1_LOOSE, X1_ASSETS = src.x1_loose, src.x1_assets


use_sources(C.Sources.developer())
ASM2_FACTS = {
    '0056144a': 'push 0x69b0bc ; ".zam"',                       # CAutomapPrecacher: '<name>.zam'
    '005a0362': 'cmp word ptr [eax], 9',                       # loader: version 9
    '005a03b4': 'fmul dword ptr [0x69ddf4]',                   # origin x 240 (fog origin)
    '005a03ec': 'lea ebx, [eax + edi*8 + 0x1a4c]',             # lists after 8 + 8n + 41*41*4
    '005a0402': 'mov edx, 0x29',                               # grid rows of 41
    '005a0418': 'cmp eax, 0x1a44',                             # 41 * 41 * 4 bytes of grid
    '0059fb28': 'mov ebp, 0x28',                               # draw window x end clamped to 40 (exclusive)
    '0059fb32': 'mov dword ptr [esp + 0x48], 0x28',            # ... and y
    '0059fba3': 'imul ebx, ebx, 0x29',                         # grid index = x * 41 + y
    '0059fef7': 'mov edi, 0x77',                               # next to unexplored ground: dark blue
    '005a01df': 'mov dword ptr [0x8a61cc], 0xa',               # overlay / menu radius 10 cells
    '00584dc3': 'push 0x2000',                                 # automap playfield (type 5): 0x2000 vertices
    '00584dca': 'call 0x588fa0',                               # ... CAutomapPlayfield constructor
    '005847c7': 'push 4',                                      # builder draw prim 1 -> triangle strip (4)
    '00596695': 'cmp edi, 0x52',                               # fog grid 82 cells
    '004c7fa2': 'push 0x68f898 ; "automap_texture"',           # read into the world entity, never used
}
ASM1_FACTS = {
    '000befb2': 'push 0x3d4c08 ; "automap_texture"',           # world +0x8c
    '000bf012': 'push 0x3d4bf8 ; "automap_offset"',            # world +0xcc / +0xd0
    '001526d6': 'push 0x3dd388 ; "textures/automap"',          # a name holding the folder is used as is
    '00152700': 'push 0x3dd360 ; "textures/automap/%s"',
    '001528cd': 'fmul dword ptr [0x3dd314]',                   # world x 1/12
    '001528f9': 'fsub dword ptr [ecx + 0x210]',                # - offset u
    '00152904': 'fsub dword ptr [ecx + 0x214]',                # - offset v
}
SAMPLES = ('nyc/alison/nyc1_1_1', 'astroid_m/visit1/asteroid1_2', 'haarp/ext/haarp_ext01',
           'mansion/man2/mansion2_2', 'sewers/hub/sewers1_1_1', 'mastermold/mastermold1')
ENCLOSED = ('astroid_m/visit1/asteroid1_2', 'mansion/man2/mansion2_2', 'sewers/hub/sewers1_1_1',
            'nuke_plant/nuke/nuke1_1', 'haarp/int/haarp2_1', 'weapon_x/wfb/wx1_2', 'hive/h_int/hive2_2_1')

fails = []


def check(cond, msg):
    print(('  ok   ' if cond else '  FAIL ') + msg, flush=True)
    if not cond:
        fails.append(msg)


def asm_lines(path, addrs):
    want = set(addrs)
    got = {}
    with open(path, encoding='latin-1') as f:
        for line in f:
            a = line[:8]
            if a in want:
                got[a] = line[9:].rstrip('\n')
    return got


def x1_zone_world(zone):
    for ext in ('.eng', '.xml'):
        p = X1_LOOSE / 'maps' / (zone + ext)
        if p.is_file():
            m = re.search(r'<entity\s+name="world"[^>]*>', p.read_text(encoding='latin-1'), re.I)
            if m:
                w = m.group(0)
                t = re.search(r'automap_texture="([^"]*)"', w, re.I)
                o = re.search(r'automap_offset="([^"]*)"', w, re.I)
                return (t.group(1) if t else None), (o.group(1) if o else None)
    return None, None


def x1_automap_zones():
    out = []
    for p in sorted((X1_LOOSE / 'maps').rglob('*')):
        if p.suffix.lower() in ('.eng', '.xml'):
            z = p.relative_to(X1_LOOSE / 'maps').as_posix()[:-4].lower()
            if z not in out and x1_zone_world(z)[0]:
                out.append(z)
    return out


def texture_bytes(tex):
    rel = A.texture_rel(tex)
    for root in (X1_LOOSE, X1_ASSETS):
        p = root / rel
        if p.is_file():
            return p.read_bytes()
    return None


def nav_cells(zone):
    p = X1_LOOSE / 'maps' / (zone + '.nav')
    if not p.is_file():
        return None, None
    s = p.read_text(encoding='latin-1')
    m = re.search(r'cellSize="([\d.]+)"', s, re.I)
    cells = [[float(v) for v in q.split()[:2]] for q in re.findall(r'p="([^"]+)"', s)]
    return (float(m.group(1)) if m else None), (np.array(cells) if cells else None)


def enclosed(mask):
    """Pixels no 4-connected path through ~mask joins to the image border (the inside of the outlines)."""
    h, w = mask.shape
    seen = np.zeros_like(mask)
    stack = [(0, c) for c in range(w)] + [(h - 1, c) for c in range(w)] + \
            [(r, 0) for r in range(h)] + [(r, w - 1) for r in range(h)]
    while stack:
        r, c = stack.pop()
        if 0 <= r < h and 0 <= c < w and not seen[r, c] and not mask[r, c]:
            seen[r, c] = True
            stack += [(r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)]
    return ~seen


def repack(p):
    ox, oy = p['origin']
    out = bytearray(struct.pack('<4h', A.ZAM_VERSION, ox, oy, len(p['verts'])))
    for x, y, col in p['verts']:
        out += struct.pack('<hhI', x, y, col)
    out += struct.pack(f'<{A.GRID * A.GRID}I', *p['grid'])
    for lst in p['lists']:
        out += struct.pack(f'<h{len(lst)}h', len(lst), *lst)
    return bytes(out)


def t1(asm_dir):
    print(f'T1 engine facts (disassemblies in {asm_dir})')
    for path, facts in ((asm_dir / ASM2.name, ASM2_FACTS), (asm_dir / ASM1.name, ASM1_FACTS)):
        if not path.is_file():
            check(False, f'{path} missing (gitignored local dump; pass --asm-dir <main tree>/research/scripts)')
            continue
        got = asm_lines(path, facts)
        for a, want in facts.items():
            check(got.get(a) == want, f'{path.name} {a}: {want!r} (found {got.get(a)!r})')


def t2(base):
    print('T2 retail XML2 .zam files')
    files = sorted((Path(base) / 'Automaps').rglob('*.zam'))
    check(len(files) >= 100, f'{len(files)} retail .zam files')
    lists = inside = 0
    worst = (0, '')
    for f in files:
        data = f.read_bytes()
        try:
            p = A.parse(data)
        except A.AutomapError as ex:
            check(False, f'{f.name}: {ex}')
            continue
        if repack(p) != data:
            check(False, f'{f.name}: does not re-pack byte for byte')
        ox, oy = p['origin']
        for g, cells in p['cell_of_list'].items():
            vs = [p['verts'][k] for k in p['lists'][g]]
            mx = sum(v[0] for v in vs) / len(vs)
            my = sum(v[1] for v in vs) / len(vs)
            for cx, cy in cells:
                lists += 1
                inside += ((ox + cx) * A.CELL <= mx <= (ox + cx + 1) * A.CELL and
                           (oy + cy) * A.CELL <= my <= (oy + cy + 1) * A.CELL)
        worst = max(worst, (A.window_cost(p), f.name))
    check(lists and inside / lists >= 0.999, f'{inside}/{lists} retail lists sit in their grid cell (x*41+y)')
    print(f'       retail worst draw window: {worst[0]} strip vertices ({worst[1]}); builder {A.VB_CAPACITY}')


def t3(zones):
    print(f'T3 conversion fidelity ({len(zones)} zones)')
    worst = (0, '')
    for z in zones:
        tex, off = x1_zone_world(z)
        data = texture_bytes(tex) if tex else None
        if data is None:
            check(False, f'{z}: XML1 automap texture {tex} not found')
            continue
        zam, info = A.convert(data, off)
        if zam is None:
            check(False, f'{z}: empty conversion')
            continue
        p = A.parse(zam)
        prob = A.problems(p)
        lum = A.decode_texture(data)
        grey, white = A.levels(lum)
        o = info['offset']
        cw = A.rasterize(p, lum.shape, o, A.ALPHA_WHITE)
        cg = A.rasterize(p, lum.shape, o, A.ALPHA_GREY) | cw
        wr = (cw & white).sum() / max(white.sum(), 1)
        wp = (cw & white).sum() / max(cw.sum(), 1)
        gi = (cg & grey).sum() / max((cg | grey).sum(), 1)
        worst = max(worst, (info['window'], z))
        check(not prob and wr >= 0.93 and wp >= 0.92 and gi >= 0.90 and info['window'] <= A.VB_CAPACITY,
              f'{z}: white recall {wr:.3f} precision {wp:.3f}, grey IoU {gi:.3f}, window {info["window"]}, '
              f'{info["verts"]} verts, {info["bytes"]} bytes{", " + prob[0] if prob else ""}')
        # idempotent / deterministic
        check(A.convert(data, off)[0] == zam, f'{z}: conversion deterministic')
    print(f'       worst draw window: {worst[0]} ({worst[1]})')


def t4():
    print('T4 placement against the XML1 nav (enclosed maps)')
    bad_flip, bad_neg = [], []
    for z in ENCLOSED:
        tex, off = x1_zone_world(z)
        data = texture_bytes(tex)
        cs, cells = nav_cells(z)
        if data is None or cells is None:
            check(False, f'{z}: texture or nav missing')
            continue
        lum = A.decode_texture(data)
        grey, _ = A.levels(lum)
        area = enclosed(grey)
        (ou, ov), _ = A.parse_offset(off)

        def frac(u_off, v_off, flip=False):
            u = ((cells[:, 0] + 0.5) * cs / A.UNITS_PER_PIXEL - u_off).astype(int)
            v = ((cells[:, 1] + 0.5) * cs / A.UNITS_PER_PIXEL - v_off).astype(int)
            if flip:
                v = lum.shape[0] - 1 - v
            ok = (u >= 0) & (u < lum.shape[1]) & (v >= 0) & (v < lum.shape[0])
            ins = np.zeros(len(u), bool)
            ins[ok] = area[v[ok], u[ok]]
            return float(ins.mean())
        f0 = frac(ou, ov)
        bad_flip.append(frac(ou, ov, True))
        bad_neg.append(frac(-ou, -ov))
        check(f0 >= 0.97, f'{z}: {f0:.3f} of {len(cells)} nav cells inside the map (flipped {bad_flip[-1]:.3f}, '
                          f'offset negated {bad_neg[-1]:.3f})')
    if bad_flip:
        check(np.mean(bad_flip) <= 0.75 and np.mean(bad_neg) <= 0.75,
              f'controls fail as they should: flipped rows {np.mean(bad_flip):.3f}, negated offset '
              f'{np.mean(bad_neg):.3f} (mean inside)')


def t5(out, base):
    print(f'T5 V20 over {out} (read-only)')
    from xml1build import validate as V            # noqa: WPS433
    import xmlb                                      # noqa: WPS433
    args = C.default_args(out=out, base=base, no_movies=True)
    ctx = C.BuildContext(out, base, args=args, registry=C.Registry.load(Path(out) / '_build' / 'registry.json'))
    ck = V.Check('V20', 'automaps')
    A.v20(V.Validator(ctx), ck)
    for e in ck.errors[:10]:
        print('    ' + e)
    check(not ck.errors, f'V20: {len(ck.errors)} errors, {len(ck.warnings)} warnings, counts {dict(ck.counts)}')
    for z in ('nyc/alison/nyc1_1_1', 'mansion/man2/mansion2_2'):
        pk = Path(out) / 'Packages' / 'generated' / 'maps' / (z + '.PKGB')
        t = xmlb.decode(pk.read_bytes()) if pk.is_file() else None
        ents = [(e.tag, (e.get('filename') or '').lower()) for e in t] if t is not None else []
        check(bool(ents) and ents[-1] == ('zam', f'automaps/{z}'), f'{z}: last package entry {ents[-1:]}')
        check(not any(k == 'texture' and f.startswith(A.TEXTURE_DIR) for k, f in ents),
              f'{z}: no textures/automap entry')
        check((Path(out) / 'Automaps' / (z + '.zam')).is_file(), f'{z}: Automaps/{z}.zam exists')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out')
    ap.add_argument('--base', default=str(C.DEFAULT_BASE))
    ap.add_argument('--all', action='store_true', help='T3 over every XML1 automap (slow: ~10 min)')
    ap.add_argument('--asm-dir', default=None, help='folder of xml2_text.asm / xml1_text.asm (default: '
                                                     'research/scripts of the Sources)')
    a = ap.parse_args()
    use_sources(C.Sources.for_out(a.out, a.base) if a.out else C.Sources.developer(a.base))
    a.asm_dir = a.asm_dir or str(ASM2.parent)
    t1(Path(a.asm_dir))
    t2(a.base)
    t3(x1_automap_zones() if a.all else list(SAMPLES))
    t4()
    if a.out:
        t5(a.out, a.base)
    print('PASS' if not fails else f'FAIL ({len(fails)})')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
