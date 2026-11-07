"""Keep doors reached by destruction present for native target delivery.

XML2 already translates actondeath/acttargets into the physical death list
(0x498de7). Its target query (0x41b230) only dispatches to live entities. A
door outside the hero streaming radius misses the one-shot event. Pin only
placed door types reached by these lists; preserve authored residency choices.
Newly numbered placements follow every old placement to preserve saved ordinals.
"""
from __future__ import annotations

import re

MARKER = 'xml1deathtarget'
_SEPARATORS = re.compile(r'[ ,\t\r\n]+')


def door_targets(root):
    """Door definitions reached by a physical entity's native death target list.

    Resolve instance names, including aliases of one type. XML2 replaces the
    explicit death list with acttargets when actondeath has activation content;
    it does not merge the two lists. Ordinary use-only acttargets are excluded.
    """
    definitions = {e.get('name', '').lower(): e for e in root.iter('entity')}
    targets = set()
    for e in definitions.values():
        value = e.get('deathtargets', '')
        if e.get('actondeath', '').lower() == 'true' and (e.get('acttargets') or e.get('actscript')):
            value = e.get('acttargets', '')
        targets.update(t.lower() for t in _SEPARATORS.split(value.strip()) if t)
        # The spawner's prefixed attributes configure the spawned actor's same
        # physical death handler; these are not activation of the spawner itself.
        value = e.get('monster_deathtargets', '')
        if e.get('monster_actondeath', '').lower() == 'true' and (
                e.get('monster_acttargets') or e.get('monster_actscript')):
            value = e.get('monster_acttargets', '')
        targets.update(t.lower() for t in _SEPARATORS.split(value.strip()) if t)
    # A death can activate a relay or the source spawner before its acttargets
    # reach a door. Follow that authored graph, including aliases and cycles.
    instances = {}
    for group in root.findall('entinst'):
        for inst in group.findall('inst'):
            instances.setdefault(inst.get('name', '').lower(), set()).add(group.get('type', '').lower())
    pending = list(targets)
    visited = set()
    types = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        for typ in instances.get(name, ()):
            types.add(typ)
            e = definitions.get(typ)
            if e is not None:
                pending.extend(t.lower() for t in _SEPARATORS.split(e.get('acttargets', '').strip()) if t)
    return [e for n, e in definitions.items() if n in types and e.get('classname', '').lower() == 'doorent']


def names(root):
    return {e.get('name') for e in root.iter('entity') if e.get(MARKER) == 'true'}


def convert(root):
    """Pin missing source residency and append only the new numbered types."""
    changed = 0
    for e in door_targets(root):
        if e.get('smartent') is None:
            e.set('smartent', 'false')
            e.set(MARKER, 'true')
            changed += 1
    marked = names(root)
    for group in list(root.findall('entinst')):
        if group.get('type') in marked:
            root.remove(group)
            root.append(group)
    return changed


def problems(root):
    """Every selected door must be resident; every promotion must be in the tail."""
    doors = {e.get('name'): e for e in door_targets(root)}
    out = [f'{n}: destruction target door needs smartent=false'
           for n, e in doors.items() if e.get('smartent') is None or
           (e.get(MARKER) == 'true' and e.get('smartent') != 'false')]
    marked = names(root)
    out += [f'{n}: invalid destruction target marker' for n in sorted(marked - doors.keys())]
    in_tail = False
    for group in root.findall('entinst'):
        if group.get('type') in marked:
            in_tail = True
        elif in_tail:
            out.append('new destruction target precedes an old entinst (saved ordinals shift)')
    return out
