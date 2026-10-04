"""xml1build.style_budget - V23: the fighting / power style registry of every converted zone (SPEC 43, issue #31).

XMen2.exe keeps every loaded style file - fighting styles, power styles, movesets and data/shared_nodes - in one
registry of 19 entries (0x78a800; registration 0x4ffb30, refused at 0x4ffb8a when the count is 19). A style that is
already registered costs nothing; a new one past the 19th is refused without a word, and the hero whose power style it
was has no special moves. The permanent packages and the zone's package fill the registry first, then the party's
packages in seat order, so the hero seated last loses out. XML1's zones need up to 22 with a four-hero party.

xml2-fix 1.3.1 [Limits] FightStyles raises the registry (20..32); the port's ini asks for fix_ini.LIMITS['FightStyles']
and this check counts every converted zone against that number: the permanent styles, the zone package's, the
packages of the zone's CHRB characters and the worst four-hero party's. A zone with combat off loads the heroes'
_nc packages instead. Distinct file names are counted, not package entries.

Styles a script loads later (a scripted spawn outside the CHRB roster, a temporary power) are not modeled: the raise
leaves headroom for them, and a zone exactly at the capacity is a warning for that reason."""
from __future__ import annotations

import itertools

from . import actor_budget as AB
from . import common as C
from . import fix_ini as FI

STOCK_STYLES = 19         # 0x4ffb8a: cmp [manager+0x1a4], 0x13
PARTY_SIZE = 4
PERMANENT_PKGS = AB.PERMANENT_PKGS
CHARACTER_PKG = 'packages/generated/characters/{name}_{skin}{nc}.pkgb'


def capacity(limits=None):
    """The registry size the shipped ini asks xml2-fix for ([Limits] FightStyles), else the game's own 19."""
    value = (FI.LIMITS if limits is None else limits).get('FightStyles')
    try:
        return max(int(value), STOCK_STYLES) if value is not None else STOCK_STYLES
    except ValueError:
        return STOCK_STYLES


def package_styles(entries):
    """The distinct style files an [(kind, filename)] package list registers, in order."""
    out = []
    for kind, fn in entries or ():
        name = C.norm(fn or '')
        if (kind or '').lower() == 'fightstyle' and name and name not in out:
            out.append(name)
    return out


def worst_party(base, hero_styles, size=PARTY_SIZE):
    """(count, heroes): the most distinct styles `base` plus any `size` heroes register, and the first such party
    in name order. hero_styles: {hero: styles of the hero's package}."""
    base = set(base)
    extras = {h: frozenset(s) - base for h, s in hero_styles.items()}
    names = sorted(extras)
    best = (len(base), ())
    for party in itertools.combinations(names, min(size, len(names))):
        n = len(base) + len(frozenset().union(*(extras[h] for h in party)))
        if n > best[0] or not best[1]:
            best = (n, party)
    return best


def zone_count(permanent, zone_entries, npc_styles, hero_styles, size=PARTY_SIZE):
    """{'total', 'base', 'party', 'zone_styles'} of one zone: permanent + zone package + the CHRB characters'
    packages, then the worst party."""
    zone_styles = package_styles(zone_entries)
    base = set(permanent) | set(zone_styles) | set(npc_styles)
    total, party = worst_party(base, hero_styles, size)
    return {'total': total, 'base': len(base), 'party': list(party), 'zone_styles': zone_styles}


# ---------------------------------------------------------------------------------------------- the validator
def _entries(v, rel):
    n = C.norm(rel)
    if n in v.scan.pkg:
        return v.scan.pkg[n]
    t = v.tree(n)
    return [(el.tag, el.get('filename')) for el in t] if t is not None else []


def _heroes(v):
    """[(lower name, skin)] of the playable herostat entries (a power style, not the default entry)."""
    variants = v.stats()['variants']
    stats = variants.get('.engb', {}).get('herostat') or variants.get('.xmlb', {}).get('herostat') or []
    out = []
    for el in stats:
        name = (el.get('name') or '').lower()
        if name and name != 'default' and (el.get('powerstyle') or '').strip() and (el.get('skin') or '').strip():
            out.append((name, el.get('skin').strip()))
    return out


def _chr_names(v, zone):
    t = v.tree(f'maps/{zone}.chrb')
    return sorted({(c.get('name') or '').lower() for c in t.iter('character')} - {''}) if t is not None else []


def validate(v, ck):
    """V23 fight styles (validate.Validator v, Check ck)."""
    cap = capacity()
    ck.set('capacity', cap)
    ck.set('stock_capacity', STOCK_STYLES)
    permanent = []
    for rel in PERMANENT_PKGS:
        for s in package_styles(_entries(v, rel + '.pkgb')):
            if s not in permanent:
                permanent.append(s)
    ck.set('permanent_styles', len(permanent))
    heroes = _heroes(v)
    ck.set('heroes', len(heroes))

    def hero_styles(nc):
        return {name: set(package_styles(_entries(v, CHARACTER_PKG.format(name=name, skin=skin, nc=nc))))
                for name, skin in heroes}

    party_styles = {False: hero_styles(''), True: hero_styles('_nc')}
    hero_names = {name for name, _ in heroes}
    by_name = v.stats()['by_name']
    per_zone = {}
    worst = (0, None)
    for z in sorted(v.converted_zones()):
        ents = v.zone_pkg(z)
        if ents is None:
            continue
        npc = set()
        for name in _chr_names(v, z):
            e = by_name.get(name)
            if e is None or name in hero_names:       # heroes are counted as the party
                continue
            skin = (e[1].get('skin') or '').strip()
            if skin:
                npc.update(package_styles(_entries(v, CHARACTER_PKG.format(name=name, skin=skin, nc=''))))
        off = AB.combat_off(ents)
        rep = zone_count(permanent, ents, npc, party_styles[off])
        rep['combat_off'] = off
        per_zone[z] = {k: rep[k] for k in ('total', 'base', 'party', 'combat_off')}
        ck.count('zones_checked')
        n = rep['total']
        if n > worst[0]:
            worst = (n, z)
        who = ', '.join(rep['party'])
        if n > cap:
            ck.error(f'{z}: {n} distinct fighting / power styles with the party {who} (> {cap}; {rep["base"]} before '
                     f'the party). XMen2.exe refuses a style past the registry\'s size without reporting it '
                     f'(0x4ffb8a) and the hero seated last has no powers (SPEC 43)')
        elif n == cap:
            ck.warn(f'{z}: {n} distinct fighting / power styles with the party {who}: the registry '
                    f'({cap} entries) is full, with no room for a style a script loads later (SPEC 43)')
        if n > STOCK_STYLES:
            ck.count('zones_over_stock')
    ck.set('max_styles', worst[0])
    ck.set('max_zone', worst[1])
    ck.details['zones'] = per_zone
