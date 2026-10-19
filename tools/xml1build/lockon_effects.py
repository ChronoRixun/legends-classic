"""Authored lock-on effect paths for the companion's visual-only handler bridge.

The first engine emitted three common effects from ch_lockon/ch_lockedon. The
PC handlers retain their targeting but omit those emissions. Their three dormant
effect triggers preserve the authored beam, surface and acquired-target paths.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import common as C

KEY = 'Xml1LockOnEffects'
AIM_KEY = 'Xml1LockOnAim'
_PATH = re.compile(r'[a-z0-9_-]+(?:/[a-z0-9_-]+)*\Z', re.IGNORECASE)


def paths(root):
    """Return the distinct triples and malformed move names; never guess roles."""
    triples, problems = set(), []
    for move in root.iter():
        if move.tag.lower() != 'fightmove' or move.get('handler', '').lower() != 'ch_lockon':
            continue
        values = [C.norm(e.get('effect', '')) for e in move
                  if e.tag.lower() == 'trigger' and e.get('name', '').lower() == 'effect'
                  and e.get('time') == '-1']
        if len(values) != 3 or any(not _PATH.fullmatch(v) or len(v) > 127 for v in values):
            problems.append(move.get('name', '<unnamed>'))
        else:
            triples.add(tuple(values))
    return triples, problems


def inspect(out):
    """Inspect both compiled halves, all styles and every selected effect file."""
    out = Path(out)
    index = C.FileIndex(out)
    triples, problems, moves = set(), [], 0
    for rel in index.under('data/powerstyles/'):
        if not rel.lower().endswith(('.xmlb', '.engb')):
            continue
        root = C.decode_xmlb(index.path(rel).read_bytes())
        found, bad = paths(root)
        triples.update(found)
        moves += sum(e.get('handler', '').lower() == 'ch_lockon' for e in root.iter())
        problems += [f'{rel}: malformed lock-on effects in {name}' for name in bad]
    if len(triples) > 1:
        problems.append('lock-on handlers disagree on the three common effect paths')
    for triple in sorted(triples):
        for effect in triple:
            rel = index.find(f'effects/{effect}', ('.xmlb',))
            if rel is None or index.path(rel).stat().st_size <= 8:
                problems.append(f'lock-on effect missing or empty: {effect}')
    return triples, problems, moves


def keys(out):
    triples, problems, _ = inspect(out)
    if problems:
        raise ValueError('; '.join(problems))
    return {KEY: ','.join(next(iter(triples))), AIM_KEY: '1'} if triples else {}


def validate(ctx, ck):
    triples, problems, moves = inspect(ctx.out)
    ck.set('lockon_moves', moves)
    ck.set('lockon_effect_paths', len(set(v for t in triples for v in t)))
    for problem in problems:
        ck.error(problem)
    if triples and not problems:
        ck.note('three authored lock-on effects available; companion animated-head aiming requires its gameplay rule')
