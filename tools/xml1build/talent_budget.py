"""TalentRegistry demand: 100 registered talents and 9 distinct files.

Count actual package winners, permanent/zone/NPC packages and the worst seated party.
The registry's file slots and its talent objects are separate limits; the ID radix stays 100.
"""
import itertools
from . import common as C
from . import style_budget as SB
from . import actor_budget as AB

TALENTS = 100
FILES = 9


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
        for name in files:
            if name not in counts:
                tree = v.tree(name + '.engb')
                if tree is None:
                    tree = v.tree(name + '.xmlb')
                if tree is None:
                    raise ValueError('unknown talent file: ' + name)
                counts[name] = frozenset((t.get('name') or '').lower() for t in tree.iter() if t.tag.lower() == 'talent')
                if '' in counts[name]:
                    raise ValueError('talent without a name in ' + name)
        return files
    def entries(rel):
        return count(package_talents(SB._entries(v, rel)))
    permanent = set()
    for rel in SB.PERMANENT_PKGS:
        permanent.update(entries(rel + '.pkgb'))
    # shared_talents is loaded independently of character packages.
    permanent.update(count({'data/shared_talents'}))
    heroes = SB._heroes(v)
    hero_names = {name for name, _ in heroes}
    parties = {off: {name: entries(SB.CHARACTER_PKG.format(name=name, skin=skin, nc='_nc' if off else ''))
                     for name, skin in heroes} for off in (False, True)}
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
        total, party = worst_party(base, parties[AB.combat_off(pkg)], counts)
        if total['talents'] > high:
            ck.details['worst_demand'] = {'zone': zone, 'party': list(party),
                                         'files': {f: len(counts[f]) for f in sorted(set(base).union(*(parties[AB.combat_off(pkg)][h] for h in party)))}}
        high = max(high, total['talents'])
        ck.count('zones_checked')
        for problem in problems(total):
            who = total['file_party'] if 'talent files' in problem else party
            ck.error(f"{zone}: {problem}; party {', '.join(who)}; TalentRegistry would silently refuse registration")
    ck.set('talents_demand_max', high)
