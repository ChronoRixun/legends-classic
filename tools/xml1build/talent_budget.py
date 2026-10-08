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
        if '/npc/' in ln or 'npc_generic' in ln:
            if C.norm(rel[:-5]) not in {C.norm(r) for r in set_files}:
                ck.warn(f'{rel}: no npcstat entry demands this set file (dead weight in the build)')

    def npc_set_file(name):
        s = TS.npc_set(npc_refs.get(name, ()), moving)
        return TS.set_file(s) if s else None

    by_name = v.stats()['by_name']
    high = 0
    for zone in sorted(v.converted_zones()):
        pkg = v.zone_pkg(zone)
        if pkg is None:
            continue
        base = permanent | count(package_talents(pkg))
        for name in SB._chr_names(v, zone):
            stat = by_name.get(name)
            if stat is not None and name not in hero_names:
                skin = (stat[1].get('skin') or '').strip()
                if skin:
                    base.update(entries(SB.CHARACTER_PKG.format(name=name, skin=skin, nc='')))
            else:
                rel = npc_set_file(name)
                if rel:
                    base.add(C.norm(rel))
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
