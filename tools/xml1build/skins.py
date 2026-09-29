"""xml1build.skins - XML1 actor skins on XMen2.exe: structure, blend weights and skeleton checks (SPEC.md section 25).

Started from late-game test bug B3 (research/campaign/late_game_test.md): the elite Acolytes AcolyteEnergy_B /
AcolyteLeader_B (skins 4805 / 4808 -> 18805 / 18808) drew huge black spike polygons in Asteroid M's Magneto room.
research/characters/skins.md has the whole investigation. What it established:

* The two skins are sound. In both, every vertex array's weights sum to 1, every blend index is inside the skin's
  32-entry blend-matrix palette, every palette entry is a skeleton bone, the palette resolves every outline vertex to
  the same bone as the nearest body vertex, the index buffers stay inside their vertex arrays, and every bone the
  skin blends with exists (by name) in the anim DB 48_acolyteenergy. The skins' bone ORDER differs from the anim
  DB's ('Motion' second instead of last, as in 4803 / 4806 / 4807 and 130 of the 200 XML1 skin / anim DB pairs);
  the bodies animate correctly, so XMen2.exe matches bones by name. The pipeline changes nothing but the names
  (x1names.igb_rename).
* The spikes did not come back in game. The same 18805 file, next to 18808 with its outline widened to 3 weights,
  drew clean in seven build/_skins sessions (asteroid1_1 fights, the Magneto meeting camera and fight - the late
  test's own path: begin_asteroid_rock / begin_asteroid_int / XP to 31 / the zone link - after a 17-zone session,
  after a return to the main menu, with Alchemy's CPU skinning forced, after the r302 movie, with the late test's
  xml2-fix DLL 1c750e3). So B3 is a runtime state of that one session (6-20 fps with three other game windows, a
  pad connected, ~1 h of play), not a property of the files.
* What the elite skins do have that XML2's used characters do not: vertex arrays blended with 2 weights (the body
  0x10223 and the cel outline 0x221; igVertexFormat bits 4-7 = weights, 8-11 = indices, libIGGfx.dll 0x10001d30 /
  0x10001d60). 21 of the XML1 skins the stats use blend 1 or 2 weights somewhere (plain AcolyteEnergy 4801 too,
  Sentinels, the bots, Master Mold, Jubilee, ...); XML2's used skins blend 3 or 4. Alchemy's DX8 path pads every
  blended array to 4 internal weights (igDxVertexArray1_1::makeConcrete / initUnusedBlendWeights, 0x10047040 /
  0x10047ff0) and its CPU path blends any count (igVectorBlending SSE 0x10022df0), and nothing was seen misdrawn;
  it is recorded (V21 note) because it is the one engine path XML2's own content never exercises.

`pad_blend_weights` (not applied by the build; `python -m xml1build.skins pad <in> <out>` for experiments): rewrites
every blended vertex array with 1-2 weights to 3 weights / 3 indices (0x221 -> 0x331, 0x10223 -> 0x10333, 0x111 ->
0x331, 0x10113 -> 0x10333); a padded slot gets weight 0.0 and the vertex's first bone index, so every vertex lands
exactly where it did. The weight and index blocks grow (igb_file.IgbFile.rebuilt). An outline padded this way drew
correctly in game (18808 in the sessions above), so it is ready if B3 is ever reproduced and points at it.

`check_skin` (validate V21; `python -m xml1build.skins check <out>` / `scan <xml1 tree>`), per skin against its anim DB:
  error  an unreadable skin, a vertex array whose weight and index counts differ, a blend index outside the palette,
         a palette entry no skeleton bone carries, weights that do not sum to 1 (none on the XML1 disc);
  warn   skin / skeleton mismatch: a bone the skin's vertices are weighted to that the anim DB skeleton lacks (no
         animated transform for it) - 13 XML1 skins as shipped (ponytail bones, Master Mold's wing and finger bones,
         the Sentinel spider's toes; inherited);
  note   arrays blended with 1-2 weights, palette bones the anim DB lacks that no vertex uses, a shared bone with a
         different parent in the skin than in the anim DB.
"""
from __future__ import annotations

import collections
import json
import os
import struct
import sys

from .igb_file import IgbError, IgbFile
from .sources import DEFAULT_XML2

MIN_WEIGHTS = 3           # what every XML2 character in use blends with (3 or 4); pad_blend_weights' target
WEIGHT_SUM_TOL = 1e-3


def _fmt_counts(fmt):
    return fmt >> 4 & 0xf, fmt >> 8 & 0xf         # igVertexFormat::getBlendWeightCount / getBlendIndexCount


def _vertex_arrays(f):
    """[(geometry name, vertex array)] of every igGeometry's geometry attributes, in file order."""
    out, seen = [], set()
    for g in f.objects_of('igGeometry'):
        for a in f.list_items(g.get(8)) or []:
            ga = f.obj(a)
            if ga is None or not f.isa(ga, 'igGeometryAttr'):
                continue
            va = f.obj(ga.get(4))
            if va is None or not f.isa(va, 'igVertexArray') or va.ref in seen:
                continue
            seen.add(va.ref)
            out.append((g.get(2) or '', va))
    for va in f.objects_of('igVertexArray1_1'):         # arrays no geometry names (none seen; kept for safety)
        if va.ref not in seen:
            seen.add(va.ref)
            out.append(('', va))
    return out


def pad_blend_weights(data, min_weights=MIN_WEIGHTS):
    """(new IGB bytes, [change dicts]) with every blended igVertexArray1_1 of fewer than `min_weights` weights
    widened to `min_weights` weights and indices (weight 0.0, the vertex's first bone index). Unchanged input
    comes back as the same bytes object. Raises IgbError on a file igb_file cannot read or an array whose weight
    and index counts differ (not seen on the XML1 disc)."""
    f = IgbFile(data)
    blocks, changes = {}, []
    for geo, va in _vertex_arrays(f):
        if va.name != 'igVertexArray1_1' or not va.decoded:
            continue
        fmt = va.get(6)
        nw, ni = _fmt_counts(fmt)
        if nw == 0 or nw >= min_weights:
            continue
        if ni != nw:
            raise IgbError(f'{geo}: vertex format 0x{fmt:x} has {nw} weights but {ni} indices')
        n = va.get(3)
        wref, iref = va.get(7), va.get(8)
        wb, ib = f.block(wref), f.block(iref)
        if wb is None or ib is None or wb[1] != 4 * nw * n or ib[1] != ni * n:
            raise IgbError(f'{geo}: weight / index blocks {wb} / {ib} do not hold {n} x {nw}')
        if wref in blocks or iref in blocks:
            raise IgbError(f'{geo}: weight / index block shared with another vertex array')
        W = struct.unpack_from(f'<{n * nw}f', f.data, wb[0])
        I = f.data[ib[0]:ib[0] + n * ni]
        pad = min_weights - nw
        w_out, i_out = [], bytearray()
        for v in range(n):
            w_out.extend(W[v * nw:(v + 1) * nw])
            w_out.extend([0.0] * pad)
            i_out += I[v * ni:(v + 1) * ni]
            i_out += bytes([I[v * ni]]) * pad
        blocks[wref] = struct.pack(f'<{n * min_weights}f', *w_out)
        blocks[iref] = bytes(i_out)
        new_fmt = (fmt & ~0xff0) | (min_weights << 4) | (min_weights << 8)
        struct.pack_into('<I', f.buf, va.fields[6].offset, new_fmt)
        changes.append({'geometry': geo, 'vertices': n, 'format': f'0x{fmt:x}', 'new_format': f'0x{new_fmt:x}'})
    if not changes:
        return data, []
    out = f.rebuilt(blocks)
    g = IgbFile(out)                                    # the result must read back, with the new formats
    got = [_fmt_counts(va.get(6))[0] for _geo, va in _vertex_arrays(g) if va.name == 'igVertexArray1_1']
    if any(0 < w < min_weights for w in got):
        raise IgbError('padding did not take')
    return out, changes


# ------------------------------------------------------------------------------------------------ checks
def skeleton(f):
    """[(bone name, parent index, blend matrix index)] of the file's first igSkeleton, or None."""
    sk = f.objects_of('igSkeleton')
    if not sk:
        return None
    bones = []
    for r in f.list_items(sk[0].get(4)) or []:
        b = f.obj(r)
        bones.append((b.get(2) or '', b.get(3), b.get(4)))
    return bones


def _palette_arrays(f):
    """[(palette list, [(geometry name, vertex array)])] per igBlendMatrixSelect (the arrays drawn under it)."""
    out = []
    for bms in f.objects_of('igBlendMatrixSelect'):
        pal = f.list_items(bms.get(10)) or []
        stack, vas, seen = [bms.ref], [], set()
        while stack:
            o = f.obj(stack.pop())
            if o is None or o.ref in seen:
                continue
            seen.add(o.ref)
            if o.name == 'igGeometry':
                for a in f.list_items(o.get(8)) or []:
                    ga = f.obj(a)
                    if ga is not None and f.isa(ga, 'igGeometryAttr'):
                        vas.append((o.get(2) or '', f.obj(ga.get(4))))
            if f.isa(o, 'igGroup'):
                stack.extend(f.list_items(o.get(7)) or [])
        out.append((pal, vas))
    return out


def check_skin(data, animdb=None):
    """one skin IGB (bytes), optionally against its anim DB (bytes): {'errors': [...], 'mismatch': {bone: vertices
    weighted to it that the anim DB skeleton lacks}, 'low_weight': [(geometry, format)], 'notes': [...],
    'arrays': [(geometry, format)], 'bones_used': {bone: vertices}}."""
    errors, notes, low = [], [], []
    mismatch = {}
    f = IgbFile(data)
    bones = skeleton(f)
    bm2bone = {bm: name for name, _p, bm in bones or () if isinstance(bm, int) and bm >= 0}
    used = collections.Counter()
    arrays = []
    for geo, va in _vertex_arrays(f):
        fmt = va.get(6) if va.name == 'igVertexArray1_1' else None
        arrays.append((geo, f'0x{fmt:x}' if fmt is not None else va.name))
        if fmt is None:
            continue
        nw, ni = _fmt_counts(fmt)
        if nw and nw < MIN_WEIGHTS:
            low.append((geo, f'0x{fmt:x}'))
        if nw != ni:
            errors.append(f'{geo}: vertex format 0x{fmt:x}: {nw} weights but {ni} bone indices')
    for pal, vas in _palette_arrays(f):
        for i, bm in enumerate(pal):
            if bm not in bm2bone:
                errors.append(f'blend palette entry {i} = matrix {bm}: no skeleton bone has it')
        for geo, va in vas:
            if va is None or va.name != 'igVertexArray1_1':
                continue
            fmt, n = va.get(6), va.get(3)
            nw, ni = _fmt_counts(fmt)
            if not nw or not ni:
                continue
            wb, ib = f.block(va.get(7)), f.block(va.get(8))
            if wb is None or ib is None or wb[1] < 4 * nw * n or ib[1] < ni * n:
                errors.append(f'{geo}: weight / index blocks too small for {n} vertices x {nw}')
                continue
            W = struct.unpack_from(f'<{n * nw}f', f.data, wb[0])
            I = f.data[ib[0]:ib[0] + n * ni]
            bad_sum = bad_idx = 0
            k = min(nw, ni)
            for v in range(n):
                ws = W[v * nw:(v + 1) * nw]
                if abs(sum(ws) - 1.0) > WEIGHT_SUM_TOL:
                    bad_sum += 1
                for j in range(k):
                    ix = I[v * ni + j]
                    if ix >= len(pal):
                        bad_idx += 1
                    elif ws[j] > 1e-4:
                        used[bm2bone.get(pal[ix], f'matrix {pal[ix]}')] += 1
            if bad_sum:
                errors.append(f'{geo}: {bad_sum} of {n} vertices have weights that do not sum to 1')
            if bad_idx:
                errors.append(f'{geo}: {bad_idx} bone indices outside the {len(pal)}-entry blend palette')
    if animdb is not None and bones:
        db = skeleton(IgbFile(animdb))
        if db is None:
            errors.append('anim DB has no skeleton')
        else:
            names = {name for name, _p, _bm in db}
            db_parent = {name: (db[p][0] if isinstance(p, int) and 0 <= p < len(db) else None) for name, p, _ in db}
            sk_parent = {name: (bones[p][0] if isinstance(p, int) and 0 <= p < len(bones) else None)
                         for name, p, _ in bones}
            for name, _p, bm in bones:
                if not (isinstance(bm, int) and bm >= 0):
                    continue
                if name not in names:
                    if used.get(name):
                        mismatch[name] = used[name]
                    else:
                        notes.append(f'palette bone {name!r} is not in the anim DB skeleton (no vertex uses it)')
                elif sk_parent.get(name) != db_parent.get(name):
                    notes.append(f'bone {name!r}: parent {sk_parent.get(name)!r} in the skin, '
                                 f'{db_parent.get(name)!r} in the anim DB')
    return {'errors': errors, 'mismatch': mismatch, 'low_weight': low, 'notes': notes, 'arrays': arrays,
            'bones_used': dict(used)}


def mismatch_text(mismatch):
    return ('skin / skeleton mismatch: vertices weighted to bones the anim DB skeleton lacks (no animated '
            'transform): ' + ', '.join(f'{b} ({n})' for b, n in sorted(mismatch.items())))


# ------------------------------------------------------------------------------------------------ validate V21
def validate(v, ck):
    """V21 skins (validate.Validator v, Check ck): every XML1-origin stats entry's skin (and its costume skins
    that exist) against its characteranims anim DB, with check_skin. A mismatch the XML1 disc's own files have is
    a warning marked inherited (13 skins); a new one is an error."""
    stats = v.stats()
    pairs = {}
    for lname, rec in stats['by_name'].items():
        el = rec[1] if isinstance(rec, tuple) else rec
        skin = (el.get('skin') or '').strip()
        anims = (el.get('characteranims') or '').strip().lower()
        if not skin or not anims:
            continue
        skins = [skin] + [f'{skin[:-2]}{val.strip().zfill(2)}' for k, val in el.attrib.items()
                          if k.lower().startswith('skin_') and val.strip().isdigit() and len(skin) >= 4]
        for sk in dict.fromkeys(skins):
            skin_rel = f'actors/{sk}.igb'
            if not v.exists(skin_rel) or not v.is_x1(skin_rel):
                continue                                    # XML2's own skins are not ours to check
            pairs.setdefault((skin_rel, f'actors/{anims}.igb'), []).append(el.get('name') or lname)
    cache = {}

    def read(rel):
        if rel not in cache:
            cache[rel] = v.read(rel)
        return cache[rel]

    low_skins = {}
    for (skin_rel, db_rel), who in sorted(pairs.items()):
        data = read(skin_rel)
        if data is None:
            continue                                        # V5 reports missing skins
        ck.count('skins_checked')
        try:
            r = check_skin(data, read(db_rel))
        except IgbError as ex:
            ck.error(f'{v.idx.get(skin_rel) or skin_rel}: unreadable IGB ({ex})')
            continue
        tag = f'{v.idx.get(skin_rel) or skin_rel} ({", ".join(sorted(who)[:3])}; anim DB {db_rel[7:-4]})'
        for e in r['errors']:
            ck.error(f'{tag}: {e}')
        if r['mismatch']:
            inherited = _inherited_mismatch(v, skin_rel, db_rel, r['mismatch'])
            ck.count('skins_skeleton_mismatch')
            if inherited:
                ck.warn(f'{tag}: {mismatch_text(r["mismatch"])} - inherited (the XML1 disc\'s own skin and anim DB)')
            else:
                ck.error(f'{tag}: {mismatch_text(r["mismatch"])}')
        if r['low_weight']:
            low_skins[skin_rel] = r['low_weight']
    ck.count('skins_low_blend_weights', len(low_skins))
    if low_skins:
        ck.note(f'{len(low_skins)} XML1 skins blend 1-2 weights per vertex in some arrays (XML2\'s used characters '
                f'blend 3-4; drawn correctly so far, section 25): '
                + ', '.join(sorted(r[7:-4] for r in low_skins)))
    ck.details['low_blend_weights'] = {k: v2 for k, v2 in sorted(low_skins.items())}


def _inherited_mismatch(v, skin_rel, db_rel, mismatch):
    """the same bones are missing when the XML1 disc's own skin is checked against the XML1 disc's own anim DB."""
    import re
    ctx = v.ctx
    m = re.fullmatch(r'actors/(\d+)\.igb', skin_rel)
    if not m:
        return False
    num = int(m.group(1))
    src = ctx.x1_path(f'actors/{num - 14000:04d}.igb') if num >= 14000 else None
    db = db_rel[len('actors/'):-len('.igb')]
    db_src = ctx.x1_path(f'actors/{db[3:] if db.startswith("x1_") else db}.igb')
    if src is None or db_src is None:
        return False
    try:
        r = check_skin(src.read_bytes(), db_src.read_bytes())
    except (IgbError, OSError):
        return False
    return set(mismatch) <= set(r['mismatch'])


# ------------------------------------------------------------------------------------------------ CLI
def _stats_pairs(root):
    """(name, skin, characteranims) of every herostat / npcstat entry of an XML1 text data dir."""
    import re
    out = []
    for fn in ('herostat.eng', 'npcstat.eng'):
        p = os.path.join(root, 'data', fn)
        if not os.path.exists(p):
            continue
        for m in re.finditer(r'<stats\b([^>]*)>', open(p, encoding='latin-1').read()):
            a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
            out.append((a.get('name'), a.get('skin'), (a.get('characteranims') or '').lower()))
    return out


def scan(actors_dir, pairs, fallback_dirs=()):
    """check every (name, skin, anims) pair whose skin file exists under actors_dir; returns rows."""
    rows = []

    def find(stem):
        for d in (actors_dir,) + tuple(fallback_dirs):
            for ext in ('.igb', '.IGB'):
                p = os.path.join(d, stem + ext)
                if os.path.exists(p):
                    return p
        return None

    for name, skin, anims in pairs:
        if not skin:
            continue
        sp = find(skin)
        if sp is None:
            continue
        ap = find(anims) if anims else None
        try:
            r = check_skin(open(sp, 'rb').read(), open(ap, 'rb').read() if ap else None)
        except IgbError as ex:
            r = {'errors': [f'unreadable: {ex}'], 'mismatch': {}, 'low_weight': [], 'notes': [], 'arrays': [],
                 'bones_used': {}}
        rows.append({'name': name, 'skin': skin, 'anims': anims, **r})
    return rows


def _print(rows, verbose):
    for r in rows:
        if not (r['errors'] or r['mismatch'] or r['low_weight'] or (verbose and r['notes'])):
            continue
        print(f"{r['name']} skin {r['skin']} anims {r['anims']}: "
              + '; '.join(f'{g} {fm}' for g, fm in r['arrays']))
        for e in r['errors']:
            print(f'    ERROR {e}')
        if r['mismatch']:
            print(f'    warn  {mismatch_text(r["mismatch"])}')
        if r['low_weight']:
            print(f"    note  1-2 blend weights: {', '.join(f'{g} {fm}' for g, fm in r['low_weight'])}")
        if verbose:
            for w in r['notes']:
                print(f'    note  {w}')
    bad = sum(bool(r['errors']) for r in rows)
    mism = sorted({r['skin'] for r in rows if r['mismatch']})
    low = sorted({r['skin'] for r in rows if r['low_weight']})
    print(f'{len(rows)} stats skins checked: {bad} with errors, {len(mism)} skins with a skin / skeleton mismatch '
          f'{mism}, {len(low)} skins with 1-2 blend weights {low}')
    return 1 if bad else 0


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog='python -m xml1build.skins')
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('check', help='a build: its XML1 herostat / npcstat skins against their anim DBs')
    c.add_argument('out')
    c.add_argument('-v', '--verbose', action='store_true')
    s = sub.add_parser('scan', help='an XML1 tree (xml1_loose): the disc skins against their anim DBs')
    s.add_argument('root')
    s.add_argument('--base', default=str(DEFAULT_XML2), help='for anim DBs XML1 shares with XML2')
    s.add_argument('-v', '--verbose', action='store_true')
    s.add_argument('--json')
    p = sub.add_parser('pad', help='widen one IGB\'s 1-2 weight vertex arrays to 3 (in -> out; experiments only)')
    p.add_argument('src')
    p.add_argument('dst')
    a = ap.parse_args(argv)
    if a.cmd == 'pad':
        out, changes = pad_blend_weights(open(a.src, 'rb').read())
        open(a.dst, 'wb').write(out)
        print(json.dumps(changes, indent=1))
        return 0
    if a.cmd == 'scan':
        rows = scan(os.path.join(a.root, 'actors'), _stats_pairs(a.root), (os.path.join(a.base, 'actors'),))
        if a.json:
            json.dump(rows, open(a.json, 'w'), indent=1)
        return _print(rows, a.verbose)
    # check: read the build's stats through xmlb
    import xmlb                   # tools/xmlb.py (tools/ is on sys.path with this package)
    pairs = []
    for fn in ('herostat.engb', 'npcstat.engb'):
        path = os.path.join(a.out, 'Data', fn)
        if os.path.exists(path):
            for el in xmlb.decode(open(path, 'rb').read()).iter('stats'):
                pairs.append((el.get('name'), (el.get('skin') or '').strip(),
                              (el.get('characteranims') or '').strip().lower()))
    rows = [r for r in scan(os.path.join(a.out, 'Actors'), pairs)
            if r['skin'].isdigit() and int(r['skin']) >= 14000]
    return _print(rows, a.verbose)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
