"""Course-local visibility and the original game's fallback party.

The PC course spawner reveals actors before queued passive powerups activate.
A spawn cloak hides them again on the next update. Course-only variants omit
that cloak; campaign stats and subsequent combat cloaks remain intact.
"""
from __future__ import annotations

import copy
import hashlib

SPAWNER_TAGS = frozenset(('SPAWNER', 'MUSTDIE', 'MUSTSURVIVE'))
SPAWN_CLOAK = 'spawn_invis'


def has_spawn_cloak(stats):
    return any(c.tag.lower() == 'talent' and (c.get('name') or '').lower() == SPAWN_CLOAK for c in stats)


def actor_variants(courses, stats):
    """Original lower-case stats name -> stable, short course-only stats name."""
    refs = {(s.get('character') or '').lower() for c in courses.iter('COURSE')
            for s in c if s.tag in SPAWNER_TAGS}
    names = {(s.get('name') or '').lower(): s for s in stats.iter('stats')}
    out = {}
    for name in sorted(refs & names.keys()):
        if has_spawn_cloak(names[name]):
            alias = 'x1dr_' + hashlib.sha1(name.encode('utf-8')).hexdigest()[:10]
            if alias in names or alias in out.values():
                raise ValueError(f'Danger Room actor alias collision: {alias}')
            out[name] = alias
    return out


def plan(ctx):
    from . import common as C
    if C.frontend_mode(ctx) != 'xml1':
        return {}
    key = '_danger_room_actor_variants'
    if key not in ctx.shared:
        ctx.shared[key] = actor_variants(ctx.read_x1_xml('data/dangerroom.eng'),
                                         ctx.read_x1_xml('data/npcstat.eng'))
    return ctx.shared[key]


def visible_variant(stats, name):
    out = copy.deepcopy(stats)
    out.set('name', name)
    for c in list(out):
        if c.tag.lower() == 'talent' and (c.get('name') or '').lower() == SPAWN_CLOAK:
            out.remove(c)
    return out
