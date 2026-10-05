"""xml1build.actor_budget - XMen2.exe's 40-slot actor table (skins + animation databases), SPEC.md section 14.

Engine facts (XMen2.exe, PE base 0x400000; every address below was read from the disassembly / Ghidra output):

* One actor manager (singleton at 0x7b05e8, getter 0x56b8e0, vtable 0x69bf0c) holds every loaded actor skin
  (actors/NNNN.igb) and animation database (actors/<name>.igb) in ONE table of 0x28 = 40 slots of 0x2e0 bytes
  (0x56acd0 constructs it on obj+4 and 0x56ac10 fills the 40-entry free list; the used count is obj+0x73c4).
  Package entries 'actorskin' and 'actoranimdb' share the handler class registered at 0x5622d0/0x562bc0, whose
  load callback (0x560ec0) calls vfunc 0x14 = 0x56b1c0.  0x56b1c0 first looks the name up in the requesting pool
  and then in the permanent pool; when it is not resident it checks `cmp [obj+0x73c4], 0x28 / jge` (0x56b2c3) and
  the global 449-name resource table (0x55a6a0) and, when either is full, RETURNS NULL WITHOUT LOADING.  Nothing
  is reported.  The same function is the on-demand path used at spawn time (0x56b0a0 -> vfunc 0x14), so a
  character whose files were refused during the package load stays without them while the table is full.

* Consequence (the mansion/man4/mansion4_1 crash, gamedbg_029.log, EIP 0x5743bb): CActor::setupAnimDBs (0x41fdf0)
  stores the character's own anim DB in slot 0 of its CModelActor (0x577a60 stores the lookup result even when it
  is NULL), the fightstyle DB in slot 1, 'common' in slot 2.  The name resolver 0x577330 skips a NULL slot WITHOUT
  advancing its 175-per-database id base, so the first animation ('idle' = ea slot 0, 0x426a50) resolves inside
  the fightstyle DB with an id < 175; the playback functions (0x5743a0/0x574370/0x574310, CModelActor vtable
  0x69c264 +0x58/+0x54/+0x50) index slot id/175 = 0 and dereference the NULL database: access violation on the
  character's first frame (0x4202c0 plays ea slot 0 right after the skin is set, 0x430cd0 -> 0x42f0f0).

* What the table holds per zone: the permanent packages' anim DBs (XML2: common + 4 fightstyles; XML1 mode adds
  fightstyle_villain, as XML1's own permanent_fightstyles did), the party's 4 hero packages (skin + anim DB each),
  the zone package's actorskin/actoranimdb entries, the CHRB characters' packages (<name>_<skin>[_nc]) and the
  fightstyle DBs their talents name.  The same estimator gives at most 37 for XML2's own zone packages
  (act2/mikhail/mikhail; egypt6 and savage1 36) and 38 for the converted mansion4_1 (gambit and rogue, XML2
  herostat stand-ins, load their own 13_gambit/1301 and 07_rogue/0703 on top of the XML1 hero actors
  x1_13_gambit/15301 and x1_07_rogue/14701 the XML1 bundle precaches for them).  The engine also keeps about 3
  actors this estimate cannot see (37 + 3 fits, 38 + 3 does not), so the last-loaded character files (the CHRB
  packages: gambit's and rogue's) are the ones refused; anim id 14 = 'idle' inside fightstyle_hero (gambit).

What this module does:

1. `prune_package_root` (called once per zone from zones.build_package's caller): drops the zone package's
   actorskin/actoranimdb entries that belong to the character-actor namespace (a skin or characteranims of any
   stats entry of the build, or of an XML1 herostat hero replaced by an XML2 stand-in) but that no character the
   zone can spawn (CHRB names -> stats skin/characteranims, spawner monster_skin values) uses.  mission_*,
   fightstyle_*, moveset_*, common and bolt-on anim DBs are never touched.
2. `validate` (V13): re-derives the per-zone slot estimate from <out> alone; > ACTOR_ERROR is an error (more
   actor files than any XML2 retail zone loads), > ACTOR_WARN a warning; a zone package that still lists an
   unused character actor is an error (it costs a slot for nothing).
3. `python -m xml1build.actor_budget check <out>`: the same estimate over an existing build, read-only.
"""
from __future__ import annotations

import collections
import json
import os
import re
import sys
import threading
import xml.etree.ElementTree as ET

from . import common as C
from .lib import x1names                # is_fightstyle_name (x1_fightstyle_* styles, issue #52)

ACTOR_SLOTS = 40          # 0x56ac10: 0x28 slots; 0x56b2c3: cmp [obj+0x73c4], 0x28 / jge -> load refused (NULL)
RETAIL_MAX = 37           # highest estimate over XML2's own zone packages (act2/mikhail/mikhail; egypt6 and savage1 36)
ACTOR_ERROR = RETAIL_MAX  # above anything XML2 ships: the engine's own residents (about 3) fill the last slots
ACTOR_WARN = 35           # little headroom left for the engine's residents / on-demand loads

# XMen2.exe startFirstMission roster (0x4a7c42/0x4a7c57): magneto, cyclops, wolverine, storm.  Skins come from the
# build's herostat when it can be read (with the heroes module: the hidden Magneto placeholder 0002 and XML1's
# Cyclops 14101 / Wolverine 14301 / Storm 14401); the fallbacks below are XML2's.  heroes.validate_out (V-H9) runs
# the same estimate with the heaviest XML1 party (Iceman, Nightcrawler, Magma, Gambit; SPEC_heroes.md).
PARTY = (('magneto', '2501'), ('cyclops', '0103'), ('wolverine', '0303'), ('storm', '0403'))
PERMANENT_PKGS = ('packages/generated/maps/package/permanent', 'packages/generated/maps/package/permanent_fightstyles')

_SKIN = re.compile(r'^\d{4,5}$')
_ACTOR_KINDS = ('actorskin', 'actoranimdb')


# ---------------------------------------------------------------------------------------------- readers
class OutReader:
    """Decodes XMLB-family files of an install directory by case-insensitive relative path (no ctx needed)."""

    def __init__(self, root):
        self.root = root
        self._index = None
        self._cache = {}

    def index(self):
        if self._index is None:
            idx = {}
            for d, _, fs in os.walk(self.root):
                for f in fs:
                    idx[os.path.relpath(os.path.join(d, f), self.root).replace(os.sep, '/').lower()] = os.path.join(d, f)
            self._index = idx
        return self._index

    def tree(self, rel_noext, exts=('.engb', '.xmlb', '.pkgb', '.chrb')):
        n = C.norm(rel_noext)
        for ext in exts:
            p = self.index().get(n + ext)
            if p:
                if p not in self._cache:
                    try:
                        self._cache[p] = C.decode_xmlb(open(p, 'rb').read())
                    except Exception:      # noqa: BLE001 - reported by V3; here it just means "no data"
                        self._cache[p] = None
                return self._cache[p]
        return None


class CtxReader:
    """The same interface over a BuildContext (<out> state during the build)."""

    def __init__(self, ctx):
        self.ctx = ctx

    def tree(self, rel_noext, exts=('.engb', '.xmlb', '.pkgb', '.chrb')):
        for ext in exts:
            for spelled in (ext, ext.upper(), ext.lower()):
                rel = rel_noext + spelled
                if self.ctx.out_exists(rel):
                    try:
                        return self.ctx.read_out_xmlb(rel)
                    except Exception:      # noqa: BLE001
                        return None
        return None


class ValidatorReader:
    def __init__(self, v):
        self.v = v

    def tree(self, rel_noext, exts=('.engb', '.xmlb', '.pkgb', '.chrb')):
        for ext in exts:
            rel = C.norm(rel_noext + ext)
            if self.v.exists(rel):
                return self.v.tree(rel)
        return None


# ---------------------------------------------------------------------------------------------- stats / fightstyles
class Budget:
    """Everything the prune and the estimate need from <out>: stats, fightstyle anim DBs, permanent slots."""

    def __init__(self, reader, x1_herostat=None):
        self.r = reader
        self.lock = threading.Lock()
        self._stats = None
        self._fs = {}
        self._ns = None
        self._perm = None
        self.x1_herostat = x1_herostat      # Element or None: XML1 herostat (heroes replaced by XML2 stand-ins)

    # stats: lower name -> {skin, characteranims, skins (all costume skins), fightstyles, movesets, file}
    def stats(self):
        with self.lock:
            if self._stats is None:
                st = {}
                for f in ('herostat', 'npcstat'):
                    t = self.r.tree(f'data/{f}', ('.engb', '.xmlb'))
                    if t is None:
                        continue
                    for el in t.iter('stats'):
                        name = (el.get('name') or '').lower()
                        if not name or name in st:
                            continue
                        skin = (el.get('skin') or '').strip()
                        skins = {skin} if skin else set()
                        for k, v in el.attrib.items():
                            if k.startswith('skin_') and skin and re.fullmatch(r'\d\d', (v or '').strip()):
                                skins.add(skin[:-2] + v.strip())
                        st[name] = {
                            'file': f, 'skin': skin, 'skins': skins,
                            'characteranims': (el.get('characteranims') or '').lower(),
                            'fightstyles': [(t2.get('name') or '').lower() for t2 in el.iter('talent')
                                            if x1names.is_fightstyle_name(t2.get('name'))],
                            'movesets': [m.lower() for m in (el.get('moveset1'), el.get('moveset2')) if m],
                        }
                self._stats = st
            return self._stats

    def fightstyle_anim(self, name):
        """The anim DB a fightstyle / moveset XML names (animations="..."), or None."""
        n = C.norm(name)
        with self.lock:
            if n not in self._fs:
                t = self.r.tree(f'data/fightstyles/{n}', ('.xmlb', '.engb'))
                a = (t.get('animations') or '').lower() if t is not None else ''
                self._fs[n] = a or None
            return self._fs[n]

    def character_namespace(self):
        """('actorskin', skin) / ('actoranimdb', db) of every XML1 herostat hero, in the build's namespace (map_skin /
        map_animdb): the actors XML1 zone bundles precache for their heroes.  With the heroes module these names
        resolve to the XML1 heroes themselves, so a zone whose CHRB / spawners name the hero keeps them (zone_needs
        sees the build's herostat); a bundle entry for a hero the zone never spawns (the party loads its own package)
        is dead weight.  XML2's own zones precache actors for script-spawned characters that are in no CHRB, so the
        prune never touches anything outside this namespace."""
        with self.lock:
            if self._ns is not None:
                return self._ns
        ns = set()
        if self.x1_herostat is not None:
            for el in self.x1_herostat.iter():
                if el.tag.lower() != 'stats':
                    continue
                skin = (el.get('skin') or '').strip()
                if _SKIN.match(skin):
                    ns.add(('actorskin', C.map_skin(skin)))
                    for k, v in el.attrib.items():
                        if k.startswith('skin_') and re.fullmatch(r'\d\d', (v or '').strip()):
                            ns.add(('actorskin', C.map_skin(skin[:-2] + v.strip())))
                ca = (el.get('characteranims') or '').lower()
                if ca:
                    ns.add(('actoranimdb', C.map_animdb(ca)))
        with self.lock:
            self._ns = ns
        return ns

    def permanent_slots(self):
        with self.lock:
            if self._perm is None:
                perm = set()
                for rel in PERMANENT_PKGS:
                    t = self.r.tree(rel, ('.pkgb',))
                    if t is not None:
                        perm |= pkg_actor_slots(t)
                self._perm = perm
            return self._perm

    def party(self):
        """(('actorskin', skin), ('actoranimdb', db)) the New Game party keeps in the hero pools, plus the
        package entries of <hero>_<skin>[_nc] (fightstyle DBs are shared names and counted with the zone)."""
        out = {}
        st = self.stats()
        for name, default_skin in PARTY:
            s = st.get(name)
            skin = (s or {}).get('skin') or default_skin
            db = (s or {}).get('characteranims') or ''
            out[name] = (skin, db)
        return out


def pkg_actor_slots(root_or_entries):
    """{('actorskin'|'actoranimdb', name)} of a packagedef root or an [(tag, filename)] list."""
    out = set()
    items = root_or_entries if isinstance(root_or_entries, list) else [(e.tag, e.get('filename')) for e in root_or_entries]
    for tag, fn in items:
        k = (tag or '').lower()
        if k in _ACTOR_KINDS:
            out.add((k, C.norm(fn or '')))
    return out


def combat_off(root_or_entries):
    items = root_or_entries if isinstance(root_or_entries, list) else [(e.tag, e.get('filename')) for e in root_or_entries]
    return any((tag or '').lower() == 'combat_is' and C.norm(fn or '') == 'off' for tag, fn in items)


# ---------------------------------------------------------------------------------------------- per-zone needs
def zone_spawners(zone_root):
    """(character names lowercased, {character: set(monster_skin)}) from a converted zone XML."""
    names, skins = set(), collections.defaultdict(set)
    if zone_root is None:
        return names, skins
    for e in zone_root.iter():
        if e.tag.lower() != 'entity':
            continue
        c = (e.get('character') or '').lower()
        if c:
            names.add(c)
            ms = (e.get('monster_skin') or '').strip()
            if ms:
                skins[c].add(ms)
    return names, skins


def zone_needs(budget, chr_names, spawner_skins):
    """{('actorskin'|'actoranimdb', name)} the characters the zone can spawn need at spawn time."""
    st = budget.stats()
    need = set()
    for n in chr_names:
        s = st.get(n.lower())
        if not s:
            continue
        if s['skin']:
            need.add(('actorskin', s['skin']))
        if s['characteranims']:
            need.add(('actoranimdb', s['characteranims']))
        for f in s['fightstyles'] + s['movesets']:
            a = budget.fightstyle_anim(f)
            if a:
                need.add(('actoranimdb', a))
    for c, skins in spawner_skins.items():
        for sk in skins:
            need.add(('actorskin', sk))
    return need


def zone_estimate(budget, zone, pkg_entries, chr_names, spawner_skins):
    """Resident-slot estimate for one zone: permanent + party + zone package + CHRB packages (+monster_skin
    variant packages) + fightstyle DBs.  Returns {'total', 'permanent', 'party', 'zone', 'chars', 'slots'}."""
    perm = set(budget.permanent_slots())
    off = combat_off(pkg_entries)
    suf = '_nc' if off else ''
    party = set()
    for name, (skin, db) in budget.party().items():
        if skin:
            party.add(('actorskin', skin))
        if db:
            party.add(('actoranimdb', db))
        t = budget.r.tree(f'packages/generated/characters/{name}_{skin}{suf}', ('.pkgb',))
        if t is not None:
            party |= pkg_actor_slots(t)
    zone_slots = pkg_actor_slots(pkg_entries)
    chars = set()
    st = budget.stats()
    for n in chr_names:
        s = st.get(n.lower())
        if not s:
            continue
        for sk in {s['skin']} | set(spawner_skins.get(n.lower(), ())):
            if not sk:
                continue
            chars.add(('actorskin', sk))
            t = budget.r.tree(f'packages/generated/characters/{n.lower()}_{sk}{suf}', ('.pkgb',))
            if t is not None:
                chars |= pkg_actor_slots(t)
                for e in t:
                    if e.tag.lower() == 'fightstyle':
                        fn = C.norm(e.get('filename') or '')
                        if fn.startswith('data/fightstyles/'):
                            a = budget.fightstyle_anim(fn.split('/')[-1])
                            if a:
                                chars.add(('actoranimdb', a))
        if s['characteranims']:
            chars.add(('actoranimdb', s['characteranims']))
        for f in s['fightstyles'] + s['movesets']:
            a = budget.fightstyle_anim(f)
            if a:
                chars.add(('actoranimdb', a))
    total = perm | party | zone_slots | chars
    return {'total': len(total), 'permanent': len(perm), 'party': len(party - perm),
            'zone': len(zone_slots - perm - party), 'chars': len(chars - perm - party - zone_slots),
            'slots': sorted(total), 'combat_off': off}


# ---------------------------------------------------------------------------------------------- the prune (zones)
_BUDGETS = {}
_BUDGETS_LOCK = threading.Lock()


def budget_for_ctx(ctx):
    key = id(ctx)
    with _BUDGETS_LOCK:
        b = _BUDGETS.get(key)
        if b is None:
            try:
                x1h = ctx.read_x1_xml('data/herostat.eng')
            except Exception:      # noqa: BLE001 - no XML1 herostat: only the build's stats define the namespace
                x1h = None
            b = Budget(CtxReader(ctx), x1h)
            _BUDGETS[key] = b
        return b


def prune_package_root(ctx, zone, root, chr_names):
    """Remove from a zone packagedef root the character actors (skins / anim DBs) that no character the zone can
    spawn uses.  Returns (root, [(tag, filename), ...] dropped).  Pure apart from ctx reads."""
    b = budget_for_ctx(ctx)
    zx = CtxReader(ctx).tree(f'Maps/{zone}', ('.engb', '.xmlb', '.XMLB', '.engb'))
    names, spawner_skins = zone_spawners(zx)
    names |= {n.lower() for n in (chr_names or ()) if n}
    needed = zone_needs(b, names, spawner_skins)
    ns = b.character_namespace()
    dropped = []
    for e in list(root):
        k = (e.tag or '').lower()
        if k not in _ACTOR_KINDS:
            continue
        key = (k, C.norm(e.get('filename') or ''))
        if key in ns and key not in needed:
            root.remove(e)
            dropped.append((k, key[1]))
    if dropped:
        ctx.count('actor_entries_pruned', len(dropped))
    return root, dropped


# ---------------------------------------------------------------------------------------------- the check (V13)
def _x1_herostat(v):
    try:
        return v.ctx.read_x1_xml('data/herostat.eng')
    except Exception:      # noqa: BLE001
        return None


def zone_report(budget, reader, zone, pkg_entries):
    chrb = reader.tree(f'maps/{zone}', ('.chrb',))
    chr_names = [(c.get('name') or '').lower() for c in chrb.iter() if c.tag.lower() == 'character'] if chrb is not None else []
    zx = reader.tree(f'maps/{zone}', ('.engb', '.xmlb'))
    names, spawner_skins = zone_spawners(zx)
    names |= set(chr_names)
    est = zone_estimate(budget, zone, pkg_entries, names, spawner_skins)
    needed = zone_needs(budget, names, spawner_skins)
    ns = budget.character_namespace()
    unused = sorted(k for k in pkg_actor_slots(pkg_entries) if k in ns and k not in needed)
    est['unused_character_actors'] = unused
    est['chars'] = sorted(names)
    return est


def validate(v, ck):
    """V13 actor slots (validate.Validator v, Check ck)."""
    ck.set('actor_slots', ACTOR_SLOTS)
    ck.set('error_over', ACTOR_ERROR)
    ck.set('warn_over', ACTOR_WARN)
    reader = ValidatorReader(v)
    budget = Budget(reader, _x1_herostat(v))
    per_zone = {}
    worst = (0, None)
    for z in v.converted_zones():
        ents = v.zone_pkg(z)
        if ents is None:
            continue
        rep = zone_report(budget, reader, z, ents)
        per_zone[z] = {k: rep[k] for k in ('total', 'permanent', 'party', 'zone', 'chars', 'combat_off',
                                           'unused_character_actors')}
        ck.count('zones_checked')
        n = rep['total']
        if n > worst[0]:
            worst = (n, z)
        if n > ACTOR_ERROR:
            ck.error(f'{z}: {n} actor skins + anim DBs resident (> {ACTOR_ERROR}, the most any XML2 zone loads; '
                     f'XMen2.exe has {ACTOR_SLOTS} slots and silently refuses the rest, 0x56b2c3): the last '
                     f'character packages lose their anim DB and crash at 0x5743bb on their first animation '
                     f'(section 14). Characters: {", ".join(rep["chars"][:8])}')
        elif n > ACTOR_WARN:
            ck.warn(f'{z}: {n} actor skins + anim DBs resident (> {ACTOR_WARN}: little headroom under the '
                    f'{ACTOR_SLOTS}-slot actor table, section 14)')
        for k, name in rep['unused_character_actors']:
            ck.error(f'{z}: package precaches {k} {name}, a character actor no CHRB character or spawner of the zone '
                     f'uses (costs one of the {ACTOR_SLOTS} actor slots; zones.build_package prunes these, section 14)')
    ck.set('max_slots', worst[0])
    ck.set('max_zone', worst[1])
    ck.details['zones'] = per_zone


# ---------------------------------------------------------------------------------------------- CLI
def check(out, verbose=False):
    reader = OutReader(out)
    x1h = None
    # the XML1 herostat of the sources the build in <out> was made with (developer: xml1_loose/data/herostat.eng)
    for cand in (str(C.Sources.for_out(out).x1_loose / 'data' / 'herostat.eng'),):
        if os.path.exists(cand):
            try:
                x1h = C.sweeplib.parse_text_xml_robust(open(cand, 'rb').read())
            except Exception:      # noqa: BLE001
                x1h = None
    budget = Budget(reader, x1h)
    zones = []
    detail = os.path.join(out, '_build', 'zones_detail.json')
    converted = None
    if os.path.exists(detail):
        try:
            converted = set(json.load(open(detail)).get('converted') or [])
        except (OSError, ValueError):
            converted = None
    for rel, p in reader.index().items():
        if rel.startswith('packages/generated/maps/') and rel.endswith('.pkgb') and '/package/' not in rel:
            z = rel[len('packages/generated/maps/'):-len('.pkgb')]
            if converted is None or z in converted:
                zones.append(z)
    rows = []
    for z in sorted(zones):
        t = reader.tree(f'packages/generated/maps/{z}', ('.pkgb',))
        if t is None:
            continue
        rep = zone_report(budget, reader, z, t)
        rows.append((z, rep))
    over = [(z, r) for z, r in rows if r['total'] > ACTOR_ERROR]
    warn = [(z, r) for z, r in rows if ACTOR_WARN < r['total'] <= ACTOR_ERROR]
    unused = [(z, r) for z, r in rows if r['unused_character_actors']]
    print(f'{len(rows)} zone packages ({"converted zones" if converted is not None else "all"}); '
          f'permanent slots {len(budget.permanent_slots())}; '
          f'over {ACTOR_ERROR}: {len(over)}; warn (> {ACTOR_WARN}): {len(warn)}; with unused character actors: {len(unused)}')
    for z, r in sorted(rows, key=lambda x: -x[1]['total'])[:25 if not verbose else len(rows)]:
        flag = ' ERROR' if r['total'] > ACTOR_ERROR else (' warn' if r['total'] > ACTOR_WARN else '')
        print(f"  {z:42} total={r['total']:3} (perm {r['permanent']}, party {r['party']}, zone {r['zone']}, "
              f"chars {r['chars']}) unused={len(r['unused_character_actors'])}{flag}")
    if unused:
        print('unused character actors per zone (pruned by zones.build_package since section 14):')
        for z, r in unused:
            print(f'  {z:42} {r["unused_character_actors"]}')
    return {'zones': {z: r for z, r in rows}, 'over': [z for z, _ in over], 'warn': [z for z, _ in warn]}


def main(argv):
    if len(argv) < 2 or argv[0] != 'check':
        print(__doc__)
        return 2
    res = check(argv[1], '--verbose' in argv)
    if '--json' in argv:
        json.dump(res, open(argv[argv.index('--json') + 1], 'w'), indent=1, default=str)
    return 1 if res['over'] else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
