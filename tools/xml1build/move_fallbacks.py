"""Preserve semantic move fallbacks while removing redundant collapsed rank links.

XML2's FightMove parser accepts Fallback (0x4f6c0d, name at +0x90). These are failure transitions, including
counter-exhaustion exits, not just XML1's rank-selection machinery. Trees and maps contain caller-owned data.
"""
from __future__ import annotations


def name_map(report, source=None):
    """Active source moves only; deliberately dropped roots must not donate behavior to their replacement."""
    mapping = dict(report['chain_map']) | report['renamed']
    for entry in report['kept']:
        name, _, target = entry.partition(' -> ')
        mapping[name] = target or name
    if source is not None:
        moves = {m.get('name'): m for m in source.findall('FightMove')}
        dropped = {entry.split(' (', 1)[0] for entry in report['dropped']}
        for name in moves.keys() - mapping.keys():
            cursor, seen = name, set()
            while cursor in moves and cursor not in seen and cursor not in dropped:
                seen.add(cursor)
                cursor = moves[cursor].get('inherit')
            if cursor not in dropped:
                raise ValueError(f'fallback mapping missing source move {name}')
    return mapping


def targets(source, mapping):
    """Derive surviving fallback edges from the source, walking through redundant links within one rank group.

    A rank fallback mapping back to the same output must never be serialized as a self-loop. Follow its source
    links instead: the group's root can still have a semantic exit. Conflicting exits cannot share one move.
    """
    moves = {m.get('name'): m for m in source.findall('FightMove')}
    exits = {}

    def inherited_fallback(name, seen=()):
        if name in seen:
            raise ValueError(f'{name}: cyclic source move inheritance')
        move = moves[name]
        if 'fallback' in move.attrib:
            return move.get('fallback')
        parent = move.get('inherit')
        return inherited_fallback(parent, (*seen, name)) if parent in moves else None

    for name, output in mapping.items():
        if name not in moves:
            raise ValueError(f'fallback mapping names unknown source move {name}')
        fallback = inherited_fallback(name)
        seen = {name}
        while fallback and mapping.get(fallback, fallback) == output:
            if fallback in seen:
                raise ValueError(f'{name}: cyclic source rank fallback at {fallback}')
            seen.add(fallback)
            fallback = inherited_fallback(fallback)
        if not fallback:
            continue
        if fallback in moves and fallback not in mapping:
            raise ValueError(f'{name}: fallback targets dropped source move {fallback}')
        target = mapping.get(fallback, fallback)
        if output in exits and exits[output] != target:
            raise ValueError(f'{output}: conflicting source fallback exits {exits[output]} / {target}')
        exits[output] = target
    return exits


def problems(source, style, mapping):
    """Check serialized output against authored exits, independently of converter attribute copying."""
    try:
        expected = targets(source, mapping)
    except (KeyError, ValueError) as exc:
        return [str(exc)]
    moves = {m.get('name'): m for m in style.findall('FightMove')}
    errors = []
    for name, target in expected.items():
        move = moves.get(name)
        actual = move.get('fallback') if move is not None else None
        if actual != target:
            errors.append(f'{name}: fallback {actual!r} != authored exit {target!r}')
        if target in mapping.values() and target not in moves:
            errors.append(f'{name}: fallback destination {target!r} missing from output')
    for name, move in moves.items():
        fallback = move.get('fallback')
        if fallback and name not in expected:
            errors.append(f'{name}: unexpected fallback {fallback!r}')
        if fallback == name:
            errors.append(f'{name}: fallback points to itself')
        seen = {name}
        while fallback in moves:
            if fallback in seen:
                errors.append(f'{name}: cyclic output fallback at {fallback}')
                break
            seen.add(fallback)
            fallback = moves[fallback].get('fallback')
    return errors
