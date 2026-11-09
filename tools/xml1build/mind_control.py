"""Source-derived checks for converted team-switch powers (no game inputs bundled).

Do not infer inactivity from life=0: XML2 gives that attachment no expiry. Check every source rank against the
emitted application gate and both duration endpoints, independently of the style-collapse implementation.
"""
from __future__ import annotations

import math

KINDS = frozenset(('confused', 'team_switch'))


def problems(source, style, talents, values):
    """Return errors for every source talent whose chain ever applies team_switch, including its confused ranks.

    values provides resolve(value), the XML1 value-code resolver. Trees have normalized attribute names.
    """
    errors = []
    moves = {m.get('name'): m for m in source.findall('FightMove')}
    memo = {}

    def effective(name, seen=()):
        if name in memo:
            return memo[name]
        if name in seen:
            raise ValueError(f'cyclic source move inheritance: {name}')
        move = moves[name]
        parent = move.get('inherit')
        tags = {k: dict(v) for k, v in effective(parent, (*seen, name)).items()} if parent in moves else {}
        for t in move.findall('trigger'):
            if t.get('tag') is not None:
                tags.setdefault(t.get('tag'), {}).update(t.attrib)
        memo[name] = tags
        return tags

    groups = {}
    for name, move in moves.items():
        for req in move.findall('require'):
            if (req.get('cat') or '').lower() not in ('skill', 'talent'):
                continue
            if not (req.get('level') or '').isdigit():
                continue
            tags = [t for t in effective(name).values()
                    if t.get('name') == 'powerup' and t.get('powerup') in KINDS]
            groups.setdefault(req.get('item'), {})[int(req.get('level'))] = tags
    groups = {skill: ranks for skill, ranks in groups.items()
              if any(t.get('powerup') == 'team_switch' for tags in ranks.values() for t in tags)}
    tables = {}
    if talents is not None:
        for t in talents.iter('talentvalue'):
            tables.setdefault(t.get('name'), {})[int(t.get('level'))] = t.get('value')

    def emitted(value, rank, default=None):
        value = default if value is None else value
        if value is not None and value.startswith('%'):
            value = tables.get(value[1:], {}).get(rank)
        if value is None:
            raise ValueError('missing value or talentvalue rank')
        parts = tuple(float(v) for v in value.split())
        if not parts or len(parts) > 2 or not all(math.isfinite(v) for v in parts):
            raise ValueError(f'invalid numeric value {value!r}')
        return parts

    for skill, ranks in groups.items():
        candidates = [m for m in style.findall('FightMove')
                      if any(r.get('item') == skill for r in m.findall('require'))]
        if len(candidates) != 1:
            errors.append(f'{skill}: expected one converted move, found {len(candidates)}')
            continue
        triggers = [t for t in candidates[0].iter('trigger')
                    if any(a.get('attribute') in KINDS for a in t.findall('affecter'))]
        for rank, tags in sorted(ranks.items()):
            try:
                expected = []
                for t in tags:
                    lo = float(values.resolve(t['life']).split()[0])
                    hi = float(values.resolve(t.get('life_max', t['life'])).split()[0])
                    expected.append((t['powerup'], lo, max(lo, hi)))
                actual = []
                for t in triggers:
                    chance = emitted(t.get('apply_chance', t.get('apply_enemy_chance')), rank, '1')[0]
                    # A zero chance can still pass XML2's strict chance < random comparison when random=0.
                    if chance < 0:
                        continue
                    life = emitted(t.get('life'), rank)
                    lo, hi = life[0], life[-1]
                    if lo <= 0 or hi < lo:
                        raise ValueError(f'non-expiring or invalid life {life}')
                    if chance != 1:
                        raise ValueError(f'active branch has apply_chance={chance}, expected 1')
                    if hi > lo and emitted(t.get('xml1_life_range'), rank) != life:
                        raise ValueError('missing or mismatched template lifetime range')
                    for a in t.findall('affecter'):
                        if a.get('attribute') in KINDS:
                            actual.append((a.get('attribute'), lo, hi))
                if sorted(actual) != sorted(expected):
                    errors.append(f'{skill} rank {rank}: control/duration {actual} != XML1 {expected}')
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(f'{skill} rank {rank}: {exc}')
    if not groups and any(a.get('attribute') == 'team_switch' for a in style.iter('affecter')):
        errors.append('converted team_switch has no matching XML1 power')
    return errors


def zero_life_problems(style, talents):
    """V-H18: any rank resolving to life zero requires an exact -1 application gate.

    Check every rank in the owning talent as well as referenced tables. Explicit positive/negative
    source durations are retained; zero is legal only on a branch the engine cannot apply.
    """
    tables, levels = {}, {}
    if talents is not None:
        for talent in talents.findall('talent'):
            ranks = {int(v.get('level')) for v in talent.iter('talentvalue') if (v.get('level') or '').isdigit()}
            maximum = int(talent.get('maxlevel', '1'))
            levels[talent.get('name')] = max(ranks | {maximum})
        for value in talents.iter('talentvalue'):
            if (value.get('level') or '').isdigit():
                tables.setdefault(value.get('name'), {})[int(value.get('level'))] = value.get('value')

    def resolve(value, rank):
        if value is None:
            return None
        if value.startswith('%'):
            value = tables.get(value[1:], {}).get(rank)
        if value is None:
            return None
        try:
            parts = tuple(float(v) for v in value.split())
            return parts if parts and all(math.isfinite(v) for v in parts) else None
        except ValueError:
            return None

    errors = []
    for move in style.findall('FightMove'):
        count = max((levels.get(r.get('item'), 1) for r in move.findall('require')), default=1)
        for t in move.iter('trigger'):
            life = t.get('life')
            if life is None:
                continue
            refs = [v[1:] for v in t.attrib.values() if v.startswith('%')]
            maximum = max([count] + [max(tables.get(ref, {1: None})) for ref in refs])
            for rank in range(1, maximum + 1):
                duration = resolve(life, rank)
                if duration is not None and 0 in duration:
                    gate = resolve(t.get('apply_chance', t.get('apply_enemy_chance')), rank)
                    if gate != (-1.0,):
                        errors.append(f'{move.get("name")} trigger {t.get("tag")} rank {rank}: '
                                      'life resolves to 0 without apply_chance=-1')
    return errors
