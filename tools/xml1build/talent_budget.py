"""TalentRegistry demand: 100 registered talents and 9 distinct files (V-TBD, number assigned at merge).

Count actual package winners, permanent/zone/NPC packages and the worst seated party. The registry's file slots
and its talent objects are separate limits; the ID radix stays 100. Registration at 0x4c0080 refuses a new name
silently once any sub-pool count reaches 100; the file loader at 0x4c0460 refuses a 10th distinct file (the
shared loader 0x4c05d0 itself admits only ids 0..98). Demand model per zone:

  data/shared_talents (both halves, 0x4c05d0)          - every zone pays it
  the zone package's xml_talents entries               - zone NPC heroes precached before their styles
  each CHRB character's character package xml_talents  - heroes seat their own file; an NPC whose stats name
                                                         talents outside shared lists its talent_sets set file
                                                         (the TalentRegistry fix: NPC-only specials moved out
                                                         of shared_talents into data/talents/npc* files)
  the worst four-hero party's files                    - combat off seats the _nc packages instead

A zone exactly at a capacity is a warning: a scripted spawn outside the CHRB roster can still load a talent
file, and none would fit. Duplicate file/name loads are reuse, not extra slots. Styles a script loads later
are not modeled (same caveat as V23).
"""
import itertools
from . import common as C
from . import style_budget as SB
from . import actor_budget as AB
from . import npc_values as NV
from . import talent_sets as TS

TALENTS = 100
FILES = 9
SHARED_CAP = 99               # 0x4c05d0 ids 0..98: the shared loader's exclusive upper bound


def _canon(el):
    return (el.tag, tuple(sorted(el.attrib.items())), tuple(_canon(c) for c in el))


def package_talents(entries):
    return {C.norm(fn or '') for kind, fn in entries or ()
            if (kind or '').lower() == 'xml_talents' and fn}


def demand(files, counts):
    files = set(files)
    missing = sorted(files - counts.keys())
    if missing:
        raise ValueError('unknown talent file: ' + ', '.join(missing))
    values = [counts[f] for f in files]
    # Runtime lookup reuses an already registered talent name even if another file lists it.
    # Integer counts are useful for synthetic disjoint fixtures; production passes actual name sets.
    if all(isinstance(v, int) for v in values):
        total = sum(values)
    elif all(isinstance(v, (set, frozenset)) for v in values):
        total = len(set().union(*values))
    else:
        raise ValueError('talent demand needs all counts or all name sets')
    return dict(talents=total, files=len(files))


def problems(total):
    out = []
    if total['talents'] > TALENTS:
        out.append(f"{total['talents']} demanded unique talent names > {TALENTS}")
    if total['files'] > FILES:
        out.append(f"{total['files']} talent files > {FILES}")
    return out


def worst_party(base, heroes, counts, size=4):
    names = sorted(heroes)
    best, who = demand(base, counts), ()
    file_max, file_party = best['files'], ()
    for party in itertools.combinations(names, min(size, len(names))):
        d = demand(set(base).union(*(heroes[h] for h in party)), counts)
        if d['files'] > file_max:
            file_max, file_party = d['files'], party
        if (d['talents'], d['files']) > (best['talents'], best['files']) or not who:
            best, who = d, party
    best['files'] = file_max
    best['file_party'] = file_party
    return best, who


def validate(v, ck):
    ck.set('talent_capacity', TALENTS)
    ck.set('file_capacity', FILES)
    counts = {}

    def count(files):
        for rel in files:
            ln = C.norm(rel)
            if ln not in counts:
                t = v.tree(ln + '.engb')
                if t is None:
                    t = v.tree(ln + '.xmlb')
                if t is None:
                    raise ValueError('unknown talent file: ' + ln)
                counts[ln] = frozenset((x.get('name') or '').lower() for x in t.iter() if x.tag.lower() == 'talent')
                if '' in counts[ln]:
                    raise ValueError('talent without a name in ' + ln)
        return files

    def entries(rel):
        return count(package_talents(SB._entries(v, rel)))

    # shared pool: the loader admits ids 0..98, and both halves must agree
    shared = set(v.stats()['talents']['.engb'] or [])
    if len(shared) > SHARED_CAP:
        ck.error(f'data/shared_talents: {len(shared)} talents > the shared loader\'s {SHARED_CAP} ids '
                 f'(0x4c05d0); registration past it is silently dropped')
    counts['data/shared_talents'] = frozenset(shared)

    permanent = set()
    for rel in SB.PERMANENT_PKGS:
        permanent.update(entries(rel + '.pkgb'))
    # shared_talents is loaded independently of character packages (0x4c05d0)
    permanent.update(count({'data/shared_talents'}))

    heroes = SB._heroes(v)
    hero_names = {name for name, _ in heroes}
    parties = {off: {name: entries(SB.CHARACTER_PKG.format(name=name, skin=skin, nc='_nc' if off else ''))
                     for name, skin in heroes} for off in (False, True)}

    # npcstat: every referenced talent resolves in shared or in a built npc set file; the set mapping must
    # match what the NPCs' packages list (talent_sets). Untouched XML2 leftovers (origin 'xml2', per V5's
    # canon-against-base test) stay exactly as retail and are not part of the partition.
    npc_refs = {}
    t = v.tree('data/npcstat.engb')
    if t is None:
        ck.error('data/npcstat.engb missing or undecodable')
        t = []
    try:
        base = {(el.get('name') or '').lower(): _canon(el)
                for el in v.ctx.read_base_xmlb('Data/npcstat.engb').iter('stats')}
    except Exception:          # noqa: BLE001 - no base install (or a synthetic validator): everything is ours
        base = {}
    for st in t.iter('stats'):
        ln = (st.get('name') or '').lower()
        if not ln:
            continue
        if ln in base and _canon(st) == base[ln]:
            continue
        npc_refs[ln] = {(x.get('name') or '').lower() for x in st.iter('talent')}
    moving = {r for refs in npc_refs.values() for r in refs} - shared
    set_files = TS.file_sets(npc_refs, moving)
    covered = set().union(*set_files.values()) if set_files else set()
    for name, refs in sorted(npc_refs.items()):
        for r in sorted(refs - shared):
            if r not in covered:
                ck.error(f'npcstat {name}: talent {r} resolves neither in shared_talents nor any npc set file')
    built_sets = {C.norm(r) for r in v.idx.under('data/talents') if r.lower().endswith('.engb')}
    for rel, s in sorted(set_files.items()):
        if C.norm(rel) + '.engb' not in built_sets:
            ck.error(f'{rel}: the npc set file the stats demand is missing from the build')
            continue
        count({rel})
        got = counts[C.norm(rel)]
        if got != set(s):
            ck.error(f'{rel}: defines {sorted(got)}, the npcstat partition expects {sorted(set(s))}')
    for rel in built_sets:
        ln = rel.lower()
        base = ln.rsplit('/', 1)[-1]
        if base.startswith('npc_') or 'npc_generic' in base:
            if C.norm(rel[:-5]) not in {C.norm(r) for r in set_files}:
                ck.warn(f'{rel}: no npcstat entry demands this set file (dead weight in the build)')

    # the same roster zones.py packs: CHRB + map spawners/spawn lists + script-closure spawns +
    # Danger Room courses of this arena. The zone package must list every set file the selector
    # keeps, so a future uncovered character source fails the build here.
    try:
        x1h = v.ctx.read_x1_xml('data/herostat.eng')
        hero_refs = {(t.get('name') or '').lower() for t in x1h.iter() if t.tag.lower() == 'talent'}
    except Exception:          # noqa: BLE001
        hero_refs = set()

    def _script_text_of(ref):
        r = C.norm(ref)
        cands = []
        out_rel = v.ctx.out_index.get(C.script_ref(r)) if hasattr(v.ctx, 'out_index') else None
        if out_rel:
            cands.append(v.ctx.out / out_rel)
        try:
            cands.append(v.ctx.research_path('scripts/out/scripts') / (r + '.py'))
        except Exception:      # noqa: BLE001
            pass
        try:
            p = v.ctx.x1_path(f'scripts/{r}.py')
            if p is not None:
                cands.append(p)
        except Exception:      # noqa: BLE001
            pass
        for c in cands:
            if c.is_file():
                try:
                    return c.read_text(encoding='utf-8', errors='replace')
                except OSError:
                    return None
        return None

    def zone_roster(zone, pkg):
        roster = set(SB._chr_names(v, zone))
        for ext in ('.engb', '.xmlb'):
            roster |= TS.map_spawn_roster(v.tree(f'maps/{zone}{ext}'))
        roster |= TS.dangerroom_zone_roster(v.tree('data/dangerroom.engb'), zone)
        refs = [C.script_ref(fn) for kind, fn in pkg or () if (kind or '').lower() == 'script']
        if refs:
            closed = TS.script_closure_refs(refs, _script_text_of)
            roster |= TS.script_zone_roster({r: _script_text_of(r) for r in closed},
                                            lambda n: n in npc_refs)
        return roster

    def npc_set_file(name):
        s = TS.npc_set(npc_refs.get(name, ()), moving)
        return TS.set_file(s) if s else None

    by_name = v.stats()['by_name']
    high = 0
    zone_list = sorted(v.converted_zones())
    retained_zones = []
    try:
        converted_set = set(v.converted_zones())
        for rel in v.idx.under('packages/generated/maps'):
            if rel.lower().endswith('.pkgb'):
                zone = C.norm(rel)[len('packages/generated/maps/'):-len('.pkgb')]
                if zone not in converted_set:
                    retained_zones.append(zone)
    except Exception:          # noqa: BLE001
        retained_zones = []
    zone_list = sorted(set(zone_list) | set(retained_zones))
    for zone in zone_list:
        pkg = v.zone_pkg(zone)
        if pkg is None:
            continue
        base = permanent | count(package_talents(pkg))
        roster = zone_roster(zone, pkg)
        required = {}
        for name in sorted(roster):
            stat = by_name.get(name)
            if stat is not None and name in hero_names:
                skin = (stat[1].get('skin') or '').strip()
                if skin:
                    base.update(entries(SB.CHARACTER_PKG.format(name=name, skin=skin, nc='')))
                continue
            refs = npc_refs.get(name)
            if refs:
                required[name] = TS.npc_moving(refs, hero_refs, TS.X2_BASE_TALENTS, NV.ENERGY_TALENT)
        kept = TS.zone_set_files([s for s in required.values() if s])
        zone_talent_entries = {C.norm(t) for k, t in (pkg or ()) if (k or '').lower() == 'xml_talents' and t}
        for rel in sorted(kept):
            base.add(C.norm(rel))
            if C.norm(rel) not in zone_talent_entries:
                who = sorted(n for n, s in required.items() if s and TS.set_file(s) == rel)
                ck.error(f"{zone}: {rel} is not listed in the zone package, but {', '.join(who)} "
                         f"can appear here (roster: CHRB / map spawners / scripts / Danger Room courses); "
                         f"its talents would register nowhere")
        for name in sorted(roster):
            if name in hero_names:
                rel = C.norm(f'data/talents/{name}')
                base.add(rel)
                if rel not in zone_talent_entries:
                    ck.error(f"{zone}: {rel} is not listed in the zone package, but the hero appears here "
                             f"as an NPC (roster: CHRB / map spawners / scripts / Danger Room courses); "
                             f"the NPC copy's talents would register nowhere")
        total, party = worst_party(base, parties[AB.combat_off(pkg)], counts)
        if total['talents'] > high:
            ck.details['worst_demand'] = {'zone': zone, 'party': list(party),
                                          'files': {f: len(counts[f]) for f in sorted(
                                              set(base).union(*(parties[AB.combat_off(pkg)][h] for h in party)))}}
        high = max(high, total['talents'])
        ck.count('zones_checked')
        for problem in problems(total):
            who = total['file_party'] if 'talent files' in problem else party
            ck.error(f"{zone}: {problem}; party {', '.join(who)}; TalentRegistry would silently refuse registration")
        if total['talents'] == TALENTS:
            ck.warn(f"{zone}: {total['talents']} demanded unique talent names == {TALENTS}: the registry is "
                    f"full and a talent a script loads later would be refused")
        if total['files'] == FILES:
            ck.warn(f"{zone}: {total['files']} talent files == {FILES}: the file list is full and a talent file "
                    f"a script loads later would be refused")
    ck.set('talents_demand_max', high)
    ck.set('shared_pool', len(shared))
    ck.set('npc_set_files', len(set_files))
