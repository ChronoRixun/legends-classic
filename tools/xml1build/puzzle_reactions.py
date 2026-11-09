"""Structural producer checks for converted power-trigger puzzles.

The masks are interoperability facts from the retail attack-system vtable
0x685a64: extinguish 0x453870, weld 0x4538d0, charge 0x453920,
bridge 0x453890 and move 0x453950. A producer is necessary, not proof
that a ray/projectile reaches the target. Collision and aim require live checks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import copy
import math

from . import combat_events as CE


DAMAGE_TYPES = {
    'dmg_crushing': 1, 'dmg_blade': 2, 'dmg_bleed': 4, 'dmg_teleport': 8,
    'dmg_physical': 0x80, 'dmg_telekinesis': 0x100, 'dmg_mental': 0x800,
    'dmg_magnetic': 0x1000, 'dmg_energy': 0x8000, 'dmg_fire': 0x10000,
    'dmg_electricity': 0x20000, 'dmg_cold': 0x40000, 'dmg_wind': 0x80000,
    'dmg_elemental': 0xff0000, 'dmg_radiation': 0x8000000,
    'dmg_direct': 0x10000000, 'dmg_special': 0x20000000,
}
REACTIONS = ('weld', 'move', 'extinguish', 'charge', 'bridge')
# These two definitions already have no qualifying hero power in XML1's
# Wolverine-only flashback. Keep that inherited constraint visible; it is not
# evidence of a conversion regression or of an impossible environmental route.
INHERITED_NO_HERO = frozenset({
    ('weapon_x/wfb/wx1_1', 'battery_trigger01', 'charge'),
    ('weapon_x/wfb/wx1_2', 'battery_trigger02', 'charge'),
})


def accepts(reaction, kind, mods, level):
    """Retail classifiers on a hit's damage type, modifier names and level."""
    if reaction == 'move':
        return bool(kind & 0x81100)  # The move classifier returns 1, not level.
    if level <= 0:
        return False
    if reaction == 'weld':
        return 'dmgmod_weld' in mods
    if reaction == 'extinguish':
        return 'dmgmod_extinguish' in mods
    if reaction == 'charge':
        return 'dmgmod_energize' in mods or bool(kind & 0xf03f000)
    if reaction == 'bridge':
        return 'dmgmod_environment' in mods and kind in (0x100, 0x1000, 0x40000)
    return False


def _attrs(el):
    return {k.lower(): v for k, v in el.attrib.items()}


@dataclass
class Event:
    typ: str
    attrs: dict = field(default_factory=dict)
    mods: set = field(default_factory=set)


def _event(el, table, previous=None):
    a = _attrs(el)
    parent = previous or table.get((a.get('inherit') or a.get('name') or '').lower())
    typ = a.get('type', '').lower() or (parent.typ if parent else '')
    if typ not in CE.CE_TYPES:
        return None
    attrs = dict(parent.attrs) if parent else {'damagetype': 'dmg_physical', 'damagelevel': '1'}
    attrs.update(a)
    mods = set(parent.mods) if parent else set()
    mods.update(_attrs(c).get('name', '').lower() for c in el if c.tag.lower() == 'damagemod')
    return Event(typ, attrs, mods)


def _events(root, table):
    table = dict(table)
    if root is not None:
        for el in root:
            if el.tag.lower() == 'event':
                event = _event(el, table)
                if event is not None:
                    table[event.attrs.get('name', '').lower()] = event
    return table


def _level(value):
    # DamageLevel uses the literal value-table reader, then stores one byte
    # (0x4dbf70); unlike damage/maxrange it does not resolve %talent values.
    try:
        number = float(value.split()[0])
        return (int(number) & 0xff) if math.isfinite(number) else 0
    except (ValueError, IndexError):
        return 0


def producers(style, shared):
    """Reaction -> power/chain move names with a matching emitted attack.

    Resolve shared/local events, move inheritance, tagged updates and modifier
    inheritance. Inspect power1/2/3/9 and their chain destinations, so an unused
    local event cannot satisfy a puzzle. This checks structural availability,
    not affordability or collision.
    """
    result = {r: set() for r in REACTIONS}
    if style is None:
        return result
    table = _events(style, _events(shared, {}))
    moves = {el.get('name', '').lower(): el for el in style if el.tag.lower() == 'fightmove'}
    memo = {}

    def effective(name, seen=()):
        if name in memo:
            return memo[name]
        if name not in moves or name in seen:
            return [], {}, table
        move = moves[name]
        parent = move.get('inherit', '').lower()
        triggers, chains, inherited_events = (copy.deepcopy(effective(parent, seen + (name,)))
                                               if parent else ([], {}, table))
        local = _events(move, inherited_events)
        for el in move:
            if el.tag.lower() == 'trigger':
                tag = el.get('tag')
                index = next((i for i, (t, _) in enumerate(triggers) if tag is not None and t == tag), None)
                previous = triggers[index][1] if index is not None else None
                event = _event(el, local, previous)
                if event is not None:
                    if index is None:
                        triggers.append((tag, event))
                    else:
                        triggers[index] = (tag, event)
            elif el.tag.lower() == 'chain':
                chains[el.get('action', '').lower()] = el.get('result', '').lower()
        memo[name] = triggers, chains, local
        return triggers, chains, local

    pending = [n for n in ('power1', 'power2', 'power3', 'power9') if n in moves]
    visited = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        triggers, chains, _ = effective(name)
        pending.extend(n for n in chains.values() if n in moves)
        for _, event in triggers:
            if not event.typ.startswith('ce_atk'):
                continue
            kind = 0
            for token in event.attrs.get('damagetype', 'dmg_physical').lower().split():
                kind |= DAMAGE_TYPES.get(token, 0)
            level = _level(event.attrs.get('damagelevel', '1'))
            for reaction in REACTIONS:
                if accepts(reaction, kind, event.mods, level):
                    result[reaction].add(name)
    return result


def missing_producers(root, heroes):
    """Placed powertriggerent definitions with no producer in the given party."""
    placed = {el.get('type') for el in root.iter('entinst')}
    result = []
    for el in root.iter('entity'):
        reaction = el.get('reactpower', '').lower()
        if (el.get('classname', '').lower() == 'powertriggerent'
                and el.get('name') in placed and reaction in REACTIONS
                and not any(p.get(reaction) for p in heroes.values())):
            result.append((el.get('name'), reaction))
    return result


def available_heroes(zone, plan, roster):
    """Restrict directories whose mission entries agree on one forced party.

    Other shared directories remain unrestricted: their starts alone cannot
    establish which mission owns a later map.
    """
    owners = [row for row in plan.values() if row.get('zone')
              and zone.rsplit('/', 1)[0] == row['zone'].lower().rsplit('/', 1)[0]]
    parties = {frozenset(row.get('seat', ())) for row in owners}
    if owners and all(row.get('status') == 'seat' for row in owners) and len(parties) == 1:
        return set(next(iter(parties)))
    return set(roster)


def validate(v, ck):
    from . import common as C, heroes as H, scripts as S
    shared = v.tree(CE.SHARED_EVENTS_REL)
    roster = H.hero_plan(v.ctx)['heroes']
    plan = S.forced_party_plan(v.ctx)
    inventory = {}
    for name in roster:
        row = v.stats()['by_name'].get(name.lower())
        if row is None:
            continue  # V5 reports missing stats; no producer is assumed.
        style = row[1].get('powerstyle', '')
        root = v.tree(f'data/powerstyles/{style}.engb')
        if root is None:
            root = v.tree(f'data/powerstyles/{style}.xmlb')
        inventory[name.lower()] = producers(root, shared)
    for zone in v.converted_zones():
        root = v.tree(f'maps/{zone}.engb')
        if root is None:
            root = v.tree(f'maps/{zone}.xmlb')
        if root is None:
            continue
        available = available_heroes(zone, plan if C.forced_teams_mode(v.ctx) == 'seat' else {}, inventory)
        party = {h: inventory[h] for h in available if h in inventory}
        ck.count('zones_checked')
        for name, reaction in missing_producers(root, party):
            message = (f'{zone} {name}: reactpower={reaction} has no producing hero power '
                       f'in the available roster {sorted(available)}')
            if (zone, name, reaction) in INHERITED_NO_HERO:
                ck.warn(message + '; inherited XML1 forced-solo constraint; environmental routes not checked')
            else:
                ck.error(message)
    ck.details['producers'] = {h: {r: sorted(m) for r, m in p.items()} for h, p in inventory.items()}
