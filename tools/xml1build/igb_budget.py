"""IGB info-cache budget: offline check / fix of zone packages against XMen2.exe's 200-record CIGBInfoCache2.

XMen2.exe keeps every precached IGB (package 'model' entries, motion-path files, effect models, HUD heads and
on-demand model loads) in one global pool of 200 records (CIGBInfoCache2 ctor 0x56e9c0: 'mov edx,0xc7' /
'cmp eax,0xc8'; precache 0x56ed00 at 0x56ede5: 'cmp [this+0x73ec],0xc8; jge -> xor eax,eax' = silent NULL).
A zone package's own map IGB ('model maps/<zone>') is its last model entry, so when the package needs more
records than are free the playfield never loads ('Loading Zone igb...' fails at 0x48548b) and CMap re-requests
the previous zone (0x4854ac-0x4854c7: vtbl+0xbc with the old name, load flag set again): the game bounces back
with no exception and no message. With XML2's New Game party ~51 records are resident outside the zone group
(maps/package/permanent 16, items 20, 4 hero packages 15), which matches the observation that a 145-model
package loaded and a 153-model one did not (SPEC 13).

usage:
  python tools/xml1build/igb_budget.py check <out> [--json FILE] [--all]
      Reports every converted zone's records (distinct model names + motion-path files), its NPC packages'
      extra records, and the tile entries against the tiles its instances can name (zones.tile_models_used).
      Exit 1 if any zone is over IGB_ZONE_ERROR. --all also lists XML2's own zones.
  python tools/xml1build/igb_budget.py fix <out> --dest DIR [--zones a/b/c,...] [--apply [--backup DIR]]
      Rewrites the zone PKGBs whose tile entries differ from the engine's used set (only the tiles the zone's
      tile instances can name, SPEC 13) into DIR/Packages/generated/maps/<zone>.PKGB plus DIR/igb_budget_fix.json.
      Nothing in <out> changes unless --apply: then the originals are copied to --backup (default
      DIR/backup) first and the fixed files copied over <out>. Reversible: copy the backup back.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from xml1build import common as C          # noqa: E402
from xml1build import zones as Z           # noqa: E402  (pure helpers: tile_models_used, igb_records)
import xmlb                                # noqa: E402

NEW_GAME_PARTY = Z.NEW_GAME_PARTY


class Tree:
    """case-insensitive view of a build tree (or the XML1 loose tree) keyed by norm() rel."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.files = {}
        for d, _, fs in os.walk(self.root):
            for f in fs:
                p = Path(d) / f
                self.files[C.norm(p.relative_to(self.root).as_posix())] = p

    def path(self, rel):
        return self.files.get(C.norm(rel))

    def find(self, rel_noext, exts):
        for e in exts:
            p = self.files.get(C.norm(rel_noext + e))
            if p:
                return p
        return None

    def under(self, prefix):
        p = C.norm(prefix)
        return [k for k in self.files if k.startswith(p)]

    def xmlb(self, rel_noext, exts):
        p = self.find(rel_noext, exts)
        return xmlb.decode(p.read_bytes()) if p else None


def zone_ids(out: Tree, x1: Tree, all_zones=False):
    pre = 'packages/generated/maps/'
    zs = []
    for k in sorted(out.files):
        if not (k.startswith(pre) and k.endswith('.pkgb')) or k.startswith(pre + 'package/'):
            continue
        z = k[len(pre):-5]
        if not all_zones and x1.path(f'packages/generated/maps/{z}.fb') is None and \
                x1.find(f'maps/{z}', ('.eng', '.xml')) is None:
            continue
        if out.find(f'maps/{z}', ('.engb', '.xmlb')) is None:
            continue
        zs.append(z)
    return zs


def pkg_entries(out: Tree, z):
    root = out.xmlb(f'packages/generated/maps/{z}', ('.pkgb',))
    return [(e.tag.lower(), C.norm(e.get('filename') or '')) for e in root] if root is not None else None


def folder_files_fn(out: Tree, x1: Tree):
    cache = {}

    def folder_files(folder):
        folder = C.norm(folder).strip('/')
        if folder not in cache:
            pre = f'models/{folder}/'
            stems = set()
            for t in (out, x1):
                for k in t.under(pre):
                    if k.endswith('.igb') and '/' not in k[len(pre):]:
                        stems.add(k[len(pre):-4])
            cache[folder] = stems
        return cache[folder]
    return folder_files


_effects = {}


def effect_models(out: Tree, eff):
    """models named inside effects/<eff>.xmlb (modelname, nested *fxfile)."""
    eff = C.norm(eff)
    if eff.startswith('effects/'):
        eff = eff[8:]
    if eff in _effects:
        return _effects[eff]
    _effects[eff] = set()
    root = out.xmlb('effects/' + eff, ('.xmlb', '.engb'))
    got = set()
    if root is not None:
        for el in root.iter():
            for k, v in el.attrib.items():
                kl, s = k.lower(), (v or '').strip()
                if not s:
                    continue
                if kl == 'modelname':
                    m = C.norm(s)
                    if m.endswith('.igb'):
                        m = m[:-4]
                    got.add(m if '/' in m else 'models/' + m)
                elif kl.endswith('fxfile'):
                    got |= effect_models(out, s)
    _effects[eff] = got
    return got


def package_igbs(out: Tree, rel_noext):
    root = out.xmlb(rel_noext, ('.pkgb',))
    if root is None:
        return None
    names = set()
    for e in root:
        k, fn = e.tag.lower(), C.norm(e.get('filename') or '')
        if k == 'model':
            names.add(fn)
        elif k == 'motionpath':
            names.add('motionpaths/' + fn.rpartition('/')[0])
        elif k == 'effect':
            names |= effect_models(out, fn)
    return names


def stats_index(out: Tree):
    st = {}
    for f in ('data/herostat', 'data/npcstat'):
        root = out.xmlb(f, ('.engb', '.xmlb'))
        if root is None:
            continue
        for e in root.iter():
            if e.tag.lower() == 'stats' and e.get('name'):
                st[e.get('name').lower()] = dict(e.attrib)
    return st


def resident_estimate(out: Tree, stats):
    """records outside the zone group: permanent + items packages, plus the New Game party's packages, and the
    worst case (the 4 largest hero packages)."""
    base = set()
    for rel in ('packages/generated/maps/package/permanent', 'packages/generated/maps/package/permanent_pc',
                'packages/generated/items', 'packages/generated/item_ents', 'packages/generated/common_ents',
                'packages/generated/maps/package/permanent_fightstyles'):
        base |= package_igbs(out, rel) or set()
    heroes = {}
    hero_root = out.xmlb('data/herostat', ('.engb', '.xmlb'))
    if hero_root is not None:
        for e in hero_root.iter():
            if e.tag.lower() == 'stats' and e.get('name') and e.get('skin'):
                n = e.get('name').lower()
                igbs = package_igbs(out, f'packages/generated/characters/{n}_{e.get("skin")}')
                if igbs is not None:
                    heroes[n] = igbs
    party = set(base)
    for h in NEW_GAME_PARTY:
        party |= heroes.get(h, set())
    worst = set(base)
    for n, igbs in sorted(heroes.items(), key=lambda kv: -len(kv[1] - base))[:4]:
        worst |= igbs
    return {'base': len(base), 'new_game_party': len(party), 'worst_4_heroes': len(worst),
            'hero_packages_found': len(heroes)}


def npc_extra(out: Tree, stats, z, ents, own):
    """IGBs the zone's NPC character packages add to the zone group beyond the zone package's own."""
    combat_off = any(k == 'combat_is' and fn == 'off' for k, fn in ents)
    need, mskin = set(), {}
    chrb = out.xmlb(f'maps/{z}', ('.chrb',))
    if chrb is not None:
        for c in chrb.iter():
            if c.tag.lower() == 'character' and c.get('name'):
                need.add(c.get('name').lower())
    zx = out.xmlb(f'maps/{z}', ('.engb', '.xmlb'))
    if zx is not None:
        for e in zx.iter():
            if e.tag.lower() == 'entity' and e.get('character'):
                need.add(e.get('character').lower())
                if e.get('monster_skin'):
                    mskin[e.get('character').lower()] = e.get('monster_skin')
    extra = set()
    for n in sorted(need):
        a = stats.get(n)
        if not a:
            continue
        skin = mskin.get(n) or a.get('skin')
        igbs = package_igbs(out, f'packages/generated/characters/{a.get("name", n).lower()}_{skin}'
                                 f'{"_nc" if combat_off else ""}')
        if igbs:
            extra |= igbs
    return extra - own


def analyse(out: Tree, x1: Tree, all_zones=False):
    stats = stats_index(out)
    ff = folder_files_fn(out, x1)
    rows = []
    for z in zone_ids(out, x1, all_zones):
        ents = pkg_entries(out, z)
        if ents is None:
            continue
        own = {fn for k, fn in ents if k == 'model'} | {'motionpaths/' + fn.rpartition('/')[0]
                                                        for k, fn in ents if k == 'motionpath'}
        rec = Z.igb_records(ents)
        tree = out.xmlb(f'maps/{z}', ('.engb', '.xmlb'))
        tiles = Z.tile_models_used(tree, ff) if tree is not None else {'folders': {}, 'used': {}, 'insts': 0, 'bad': []}
        listed = {fn for k, fn in ents if k == 'model' and fn.startswith('models/tiles/')}
        used = set().union(*tiles['used'].values()) if tiles['used'] else set()
        row = {'zone': z, 'records': rec, 'npc_extra': len(npc_extra(out, stats, z, ents, own)),
               'tiles_listed': len(listed), 'tiles_used': len(used), 'tiles_missing': sorted(used - listed),
               'tiles_extra': sorted(listed - used), 'tile_instances': tiles['insts'],
               'tile_folders': sorted(set(tiles['folders'].values())), 'bad_tile_insts': tiles['bad'],
               'after_fix': rec - len(listed - used) + len(used - listed)}
        row['status'] = ('error' if rec > Z.IGB_ZONE_ERROR else 'warn' if rec > Z.IGB_ZONE_WARN else 'ok')
        rows.append(row)
    rows.sort(key=lambda r: -r['records'])
    return {'limit': Z.IGB_CACHE_RECORDS, 'error_over': Z.IGB_ZONE_ERROR, 'warn_over': Z.IGB_ZONE_WARN,
            'resident': resident_estimate(out, stats), 'zones': rows}


def cmd_check(a):
    out, x1 = Tree(a.out), Tree(a.x1)
    doc = analyse(out, x1, a.all)
    r = doc['resident']
    print(f'XMen2.exe IGB info cache: {doc["limit"]} records; resident outside the zone group: {r["base"]} '
          f'(permanent/items) + New Game party = {r["new_game_party"]} (budget {doc["limit"] - r["new_game_party"]}), '
          f'worst 4 heroes = {r["worst_4_heroes"]} (budget {doc["limit"] - r["worst_4_heroes"]})')
    print(f'{"records":>7} {"+npc":>4} {"tiles":>5} {"used":>4} {"fixed":>5}  status  zone')
    n_err = n_warn = 0
    for row in doc['zones']:
        if row['status'] == 'error':
            n_err += 1
        elif row['status'] == 'warn':
            n_warn += 1
        if a.top and row['status'] == 'ok' and row['records'] <= a.top:
            continue
        flag = ' (tiles differ)' if row['tiles_missing'] or row['tiles_extra'] else ''
        print(f'{row["records"]:7} {row["npc_extra"]:4} {row["tiles_listed"]:5} {row["tiles_used"]:4} '
              f'{row["after_fix"]:5}  {row["status"]:6}  {row["zone"]}{flag}')
    print(f'{len(doc["zones"])} zones: {n_err} over {doc["error_over"]} (cannot load), {n_warn} over {doc["warn_over"]}; '
          f'{sum(1 for r in doc["zones"] if r["tiles_missing"] or r["tiles_extra"])} with tile entries != used set')
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(doc, indent=1), encoding='utf-8')
        print('written', a.json)
    return 1 if n_err else 0


def fixed_entries(ents, used):
    """package entries with tile models = used set: unused tiles dropped, missing ones inserted where the first
    tile entry was (else before the zone's core block)."""
    listed = [fn for k, fn in ents if k == 'model' and fn.startswith('models/tiles/')]
    keep = [(k, fn) for k, fn in ents if not (k == 'model' and fn.startswith('models/tiles/') and fn not in used)]
    have = {fn for k, fn in keep if k == 'model'}
    add = [('model', m) for m in sorted(used) if m not in have]
    if add:
        first = next((i for i, (k, fn) in enumerate(keep) if k == 'model' and fn.startswith('models/tiles/')), None)
        if first is None:
            first = next((i for i, (k, fn) in enumerate(keep) if k in ('characters', 'zonexml', 'nav')), len(keep))
        keep = keep[:first] + add + keep[first:]
    return keep, [m for m in listed if m not in used], [m for _, m in add]


def cmd_fix(a):
    out, x1 = Tree(a.out), Tree(a.x1)
    dest = Path(a.dest)
    only = {C.norm(z) for z in a.zones.split(',')} if a.zones else None
    doc = analyse(out, x1)
    ff = folder_files_fn(out, x1)
    manifest = {'out': str(out.root), 'dest': str(dest), 'zones': {}}
    changed = []
    for row in doc['zones']:
        z = row['zone']
        if only and z not in only:
            continue
        if not row['tiles_missing'] and not row['tiles_extra']:
            continue
        ents = pkg_entries(out, z)
        tree = out.xmlb(f'maps/{z}', ('.engb', '.xmlb'))
        used = set().union(*Z.tile_models_used(tree, ff)['used'].values())
        new, dropped, added = fixed_entries(ents, used)
        copied = []
        for m in added:                                   # a used tile the build tree lacks: copy it from XML1
            if out.path(m + '.igb') is None:
                src = x1.path(m + '.igb')
                if src is None:
                    print(f'  {z}: used tile {m}.igb exists nowhere; not listed')
                    new = [e for e in new if e != ('model', m)]
                    continue
                dst = dest / (m + '.IGB')
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied.append(m + '.IGB')
        root = Z.ET.Element('packagedef')
        for k, fn in new:
            Z.ET.SubElement(root, k, {'filename': fn})
        data = C.encode_xmlb(root)
        rel = Path('Packages/generated/maps') / (z + '.PKGB')
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        after = Z.igb_records(new)
        manifest['zones'][z] = {'records_before': row['records'], 'records_after': after, 'dropped': dropped,
                                'added': added, 'igb_copied': copied, 'file': rel.as_posix(),
                                'original': out.path(f'packages/generated/maps/{z}.pkgb').as_posix()}
        changed.append((z, row['records'], after, len(dropped), len(added)))
        print(f'  {z}: {row["records"]} -> {after} records ({len(dropped)} tiles dropped, {len(added)} added)')
    dest.mkdir(parents=True, exist_ok=True)
    (dest / 'igb_budget_fix.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    print(f'{len(changed)} zone packages written under {dest} (manifest igb_budget_fix.json)')
    if a.apply and changed:
        backup = Path(a.backup) if a.backup else dest / 'backup'
        for z, info in manifest['zones'].items():
            orig = Path(info['original'])
            b = backup / Path(info['file'])
            b.parent.mkdir(parents=True, exist_ok=True)
            if not b.exists():
                shutil.copy2(orig, b)
            shutil.copy2(dest / info['file'], orig)
            for rel in info['igb_copied']:
                tgt = out.root / rel
                tgt.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest / rel, tgt)
        print(f'applied to {out.root}; originals backed up under {backup}')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('check')
    c.add_argument('out')
    c.add_argument('--x1', default=None, help="the XML1 loose tree (default: the one <out> was built from, Sources.for_out)")
    c.add_argument('--json')
    c.add_argument('--all', action='store_true', help='also XML2 zones')
    c.add_argument('--top', type=int, default=0, help='only print zones above this many records (and all non-ok)')
    f = sub.add_parser('fix')
    f.add_argument('out')
    f.add_argument('--x1', default=None, help="the XML1 loose tree (default: the one <out> was built from, Sources.for_out)")
    f.add_argument('--dest', required=True)
    f.add_argument('--zones')
    f.add_argument('--apply', action='store_true')
    f.add_argument('--backup')
    a = ap.parse_args(argv)
    a.x1 = a.x1 or str(C.Sources.for_out(a.out).x1_loose)
    return cmd_check(a) if a.cmd == 'check' else cmd_fix(a)


if __name__ == '__main__':
    sys.exit(main())
