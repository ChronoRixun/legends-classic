"""Pure helpers for building import ledgers from owned identifier tables.

Only interoperability names/indices are returned. No text, assets, native
talent-ID registration order or mission ordinal is inferred from XML order.
"""
from __future__ import annotations

from .errors import ImportRefusal

# Same named rewrite as heroes.HERO_ONLY_PASSIVES, a build interoperability fact.
HERO_PASSIVES = ('accuracy', 'pointblank', 'grappling', 'healing_factor', 'knockback')
KEYS = ('key1', 'key2', 'key3', 'keycard1', 'keycard2', 'keycard3')


def item_rows(source_items, economy_rows, *, source_maxima, pack_limits):
    """Source <item> declarations + installed XML1 economy -> named routes.

    Callers supply source quantity ceilings explicitly. The wire byte maximum
    alone is not evidence for a smaller authored/native cap. Economy rows bind
    the original item index to the correct appended or rebuilt target name.
    """
    economy = {}
    for row in economy_rows:
        if row['source'] in economy:
            raise ImportRefusal('BUILD', 'Duplicate source index in the XML1 economy.')
        economy[row['source']] = row
    result = []
    for i, element in enumerate(e for e in source_items if e.tag.lower() == 'item'):
        attrs = {k.lower(): v for k, v in element.attrib.items()}
        name, kind = attrs['name'], attrs['type'].lower()
        low = name.lower()
        if i not in source_maxima:
            raise ImportRefusal('BUILD', 'Missing source quantity ceiling.', source_index=i)
        target = name
        if kind == 'equipment':
            row = economy.get(i)
            if row is None or not row['flags'] & 0x40:
                raise ImportRefusal('IDENTITY', 'Source equipment has no XML1 economy identity.', source_index=i)
            target, route = row['name'], 'equipment'
        elif low == 'health_item':
            route = 'health'
        elif low == 'energy_item':
            route = 'energy'
        elif low in KEYS:
            route = 'key'
        elif kind in ('money', 'xp', 'skill', 'stat') or low in ('xtreme_pip', 'skirmish_king_pip'):
            route = 'effect'
        else:
            raise ImportRefusal('IDENTITY', 'Unknown non-equipment source definition.', source_index=i)
        mapped = dict(source_index=i, source_name=name, target=target, route=route, maximum=source_maxima[i])
        if route in ('health', 'energy'):
            mapped['target_maximum'] = pack_limits[route]
        result.append(mapped)
    return result


def named_talent(target_binds, hero, source_name):
    """Resolve a declaration name after a native byte ledger has identified it.

    Per-hero aliases are essential: one source shared passive can resolve to
    a different target TALN on each hero. Numeric destination formulas are not
    used, even when current definition orders happen to coincide.
    """
    low_hero, low_name = hero.lower(), source_name.lower()
    mapped = f'x1_{low_hero}_{low_name}' if low_name in HERO_PASSIVES else low_name
    matches = []
    for owner, names in target_binds.hero_talent.items():
        if owner.lower() == low_hero:
            matches += [[owner, n] for n in names if n.lower() == mapped]
    if low_name not in HERO_PASSIVES:
        matches += [['shared', n] for n in target_binds.shared_talent if n.lower() == mapped]
    if len(matches) != 1:
        raise ImportRefusal('IDENTITY', 'Talent declaration has no unique target identity.', hero=hero, talent=source_name)
    return matches[0]


def talent_rows(captured_ledger, declarations, target_binds):
    """Resolve an externally proven native byte/name ledger per source hero.

    captured_ledger is {byte ID: source declaration name}; declarations is
    {source hero name: [legal talent names]}. Missing purchased IDs are refused
    later by the mapper; this function never fills gaps with guessed ordinals.
    """
    result = {}
    for hero, legal in declarations.items():
        allowed = {n.lower() for n in legal}
        result[hero] = {}
        for tid, name in captured_ledger.items():
            if type(tid) is not int or not 0 <= tid <= 255:
                raise ImportRefusal('IDENTITY', 'Invalid captured native talent byte ID.')
            if name.lower() in allowed:
                result[hero][str(tid)] = named_talent(target_binds, hero, name)
    return result
