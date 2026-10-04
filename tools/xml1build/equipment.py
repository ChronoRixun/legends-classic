"""Opt-in equipment conversion and coverage audit; never installs items in a build.

See docs/EQUIPMENT_MAPPING.md for the two-engine consumer evidence and limitations.
The frontend's default conversion is intentionally unchanged: enhancement indices
are save data. All source values and item identities come from the caller's files.
"""
from __future__ import annotations

import collections
import copy
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


SCOPE_KEYS = frozenset(('scope_damage', 'scope_attack', 'scope_node', 'scope_race',
                        'scope_character', 'scope_powers'))
# Both engines enumerate the same nine attack categories. XML1 accuracy applies
# outside punch/kick/throw, whereas critical applies only to those three.
NON_MELEE = ('direct', 'blast', 'projectile', 'beam', 'crush', 'psionic')
RACES = frozenset(('none', 'human', 'mutant', 'robot', 'sentinel', 'morlock',
                   'shadow', 'astral', 'xmen', 'brotherhood'))
DAMAGE_TYPES = frozenset(('dmg_crushing', 'dmg_blade', 'dmg_bleed', 'dmg_teleport',
                          'dmg_physical', 'dmg_telekinesis', 'dmg_mental', 'dmg_magnetic',
                          'dmg_energy', 'dmg_fire', 'dmg_electricity', 'dmg_cold', 'dmg_wind',
                          'dmg_elemental', 'dmg_radiation', 'dmg_direct', 'dmg_special'))
FLOAT_MAX = 3.4028234663852886e38


@dataclass
class Bonus:
    powerup: str
    status: str                     # exact / approximate / unsupported
    reason: str
    enhancements: list = field(default_factory=list, repr=False)

    def report(self):
        return {'bonus': self.powerup, 'status': self.status, 'reason': self.reason}


@dataclass
class Conversion:
    item: ET.Element | None
    bonuses: list[Bonus]
    error: str = ''

    @property
    def coverage(self):
        if self.item is None:
            return 'none'
        return 'partial' if any(b.status == 'unsupported' for b in self.bonuses) else 'full'

    @property
    def note(self):
        detail = '; '.join(f'{b.powerup}: {b.status} ({b.reason})' for b in self.bonuses)
        return self.error or f'{self.coverage} equipment conversion: {detail}'


def _fmt(number):
    return format(number, '.9g') if number else '0'


def _numbers(text, values):
    """Resolve a caller-supplied value code, preserving its endpoints (never its mean)."""
    if text is None:
        raise ValueError('missing level')
    if values is not None:
        try:
            text = values.resolve(text)
        except KeyError as e:
            raise ValueError('unresolved value code') from e
    try:
        nums = tuple(float(s) for s in str(text).split())
    except ValueError as e:
        raise ValueError('level needs numbers or the source values table') from e
    if len(nums) not in (1, 2) or not all(math.isfinite(n) for n in nums):
        raise ValueError('level must contain one or two finite numbers')
    if any(abs(n) > FLOAT_MAX for n in nums):
        raise ValueError('level exceeds the engine float range')
    if len(nums) == 2 and nums[0] > nums[1]:
        raise ValueError('reversed level range')
    return nums


def _level(nums, factor=1):
    return ' '.join(_fmt(n * factor) for n in nums)


def _scope(p):
    """One scope predicate: OR within each category, AND between categories.

    Both parsers fold <scope> children into the same predicate. Keep children on
    the affecter, rather than splitting a bonus into overlapping enhancements.
    """
    attrs = {k: v for k, v in p.attrib.items() if k in SCOPE_KEYS}
    children = []
    for child in p:
        if child.tag.lower() != 'scope' or not child.attrib or set(child.attrib) - SCOPE_KEYS or len(child):
            raise ValueError('unsupported scope child')
        children.append(dict(child.attrib))
    for scope in [attrs] + children:
        for key, value in scope.items():
            if not value.strip():
                raise ValueError('empty scope')
            if key == 'scope_attack' and value.lower() not in NON_MELEE + ('punch', 'kick', 'throw'):
                raise ValueError('unknown attack scope')
            if key == 'scope_race' and value.lower() not in RACES:
                raise ValueError('race has no XML2 enum; refusing an unscoped bonus')
            if key == 'scope_damage' and value.lower() not in DAMAGE_TYPES:
                raise ValueError('unknown damage scope; XML2 would silently use physical')
            if key == 'scope_powers' and value.lower() not in ('true', 'false'):
                raise ValueError('invalid scope_powers')
    return attrs, children


def _enhancement(text, attributes, scope=({}, ())):
    e = ET.Element('enhancement', {'description': text})
    pu = ET.SubElement(e, 'powerup', {'life': '-1'})
    for attrs in attributes:
        aff = ET.SubElement(pu, 'affecter', {**attrs, **scope[0]})
        for child in scope[1]:
            ET.SubElement(aff, 'scope', child)
    return e


def map_bonus(p, values=None):
    """Map one permanent source bonus; reject unsupported semantics explicitly."""
    from .frontend import STAT_WORDS, stat_scale

    p = copy.deepcopy(p)
    for node in p.iter():
        node.attrib = {k.lower(): v for k, v in node.attrib.items()}
    pw = (p.get('powerup') or '').lower()

    def no(reason):
        return Bonus(pw or '?', 'unsupported', reason)

    if p.get('func_damage'):
        callback = p.get('func_damage').lower()
        reasons = {
            'damageaddattack': 'XML2 add_attack changes same-type merging, damage level and damage mods; '
                               'requires an XML1-compatible secondary-attack callback',
            'damageaddbleed': 'XML2 add_harming uses a shared victim powerup; XML1 tick/stack/lifetime '
                              'equivalence is not established',
        }
        return no(reasons.get(callback, 'untraced damage callback'))
    allowed = SCOPE_KEYS | {'powerup', 'level', 'affect_type', 'life', 'user1'}
    if set(p.attrib) - allowed:
        return no('unhandled powerup attributes: ' + ', '.join(sorted(set(p.attrib) - allowed)))
    if p.get('life', '-1') != '-1':
        return no('only permanent equipment bonuses are supported')
    try:
        nums = _numbers(p.get('level'), values)
        scope = _scope(p)
    except ValueError as e:
        return no(str(e))
    mode = (p.get('affect_type') or 'add').lower()
    if mode not in ('add', 'scale'):
        return no('this source aggregation mode is not mapped')
    scoped = bool(scope[0] or scope[1])
    if p.get('user1') is not None and pw not in ('health_regen', 'reflect_damage'):
        return no('unhandled user1 semantics')
    if min(nums) < 0:
        return no('negative equipment levels are outside the verified mapping domain')

    status, reason = 'exact', 'same affecter contribution and aggregation'
    attr, factor = pw, 1
    extras = []
    if pw in ('strength', 'speed', 'body', 'mind', 'traits') and mode == 'add' and not scoped:
        factor = stat_scale(pw)
        status, reason = 'approximate', f'port stat conversion: source points multiplied by {factor}'
    elif pw in ('damage', 'atk_damage', 'atk_damage_scale'):
        attr = 'damage'
        status = 'approximate'
        if pw == 'damage':
            reason = 'same damage term; XML1 truncates integer contributions, XML2 rounds '
            reason += 'the added/scaled contribution upward (difference up to one HP before later modifiers)'
        else:
            if mode != 'add':
                return no('XML1 attack modifiers use their name, not affect_type, to choose aggregation')
            nums = nums[:1]  # XML1 modifier pass reads level minimum, never level_max.
            mode = 'scale' if pw.endswith('_scale') else 'add'
            reason = 'XML1 final attack modifier moved to XML2 damage-construction stage; '
            reason += 'standalone contribution matches, but additive/scale combinations need not commute '
            reason += '(base 100, damage add 10, attack scale 1.2: 132 vs 130 before rounding)'
    elif pw in ('def_damage', 'def_damage_scale'):
        if pw == 'def_damage_scale':
            return no('unregistered XML1 bonus name; legacy conversion retained only in default build path')
        attr = 'def_damage_scope' if scoped else 'def_damage'
        if len(nums) != 1 and not scoped:
            return no('cached unscoped defense does not preserve a random range')
        reason = 'subtract HP before multiplying; scoped form uses the combat-context query'
        if mode == 'scale' or any(not n.is_integer() for n in nums):
            status, reason = 'approximate', 'same defense term; XML1 truncates damage to integer HP, '
            reason += 'XML2 keeps fractional HP (less than one HP per hit before later modifiers)'
    elif pw == 'critical' and mode == 'add' and not scoped and len(nums) == 1:
        factor = 0.02
        status = 'approximate'
        reason = 'two percentage points per source rank, on punch/kick/throw; add probabilities. '
        reason += 'XML2 rejects target structure >=2, XML1 >=10; structure must be converted consistently'
    elif pw == 'accuracy' and mode == 'add' and not scoped and len(nums) == 1:
        attr, factor = 'atk_critical', 0.02
        scope = ({}, [{'scope_attack': attack} for attack in NON_MELEE])
        status = 'approximate'
        reason = 'two percentage points per source rank outside punch/kick/throw; scoped critical chance. '
        reason += 'XML2 rejects target structure >=2, XML1 >=10; structure must be converted consistently'
    elif pw == 'deflect_damage' and mode == 'add':
        factor = 0.01
        reason = 'percent to probability; successful deflection returns the incoming attack and cancels it'
    elif pw == 'reflect_damage' and mode == 'add':
        try:
            chance = _numbers(p.get('user1', '0'), values)
        except ValueError as e:
            return no(str(e))
        if len(chance) != 1 or chance[0] not in (0, 100):
            return no('XML1 user1 is a per-hit percentage roll; XML2 reflect_damage always fires. '
                      'Needs a probability gate, not a smaller every-hit damage value')
        extras.append({'attribute': 'reflect_damage', 'affect_type': 'scale', 'level': '0'})
        status, reason = 'approximate', 'fixed return damage; scale zero removes XML2 incoming-damage term. '
        reason += 'XML1 reflects before damage resolution, XML2 after; reflection flags/rounding differ'
    elif pw == 'health_regen' and mode == 'add' and not scoped and len(nums) == 1:
        if not nums[0].is_integer():
            return no('fractional HP/s aggregation requires XML1 integer-rate rounding support')
        try:
            cap = _numbers(p.get('user1', '100'), values)
        except ValueError as e:
            return no(str(e))
        if len(cap) != 1 or not 0 <= cap[0] <= 100:
            return no('health regeneration cap must be a percentage in 0..100')
        if cap[0] not in (0, 100):
            extras.append({'attribute': 'health_regen', 'affect_type': 'max', 'level': _fmt(cap[0] / 100)})
        status, reason = 'approximate', 'same HP/s and single-item cap; XML2 starts immediately instead of '
        reason += 'waiting 5/regen-scale seconds after damage, and combines caps by minimum instead of maximum'
    elif pw == 'energy_regen' and mode == 'scale' and not scoped and len(nums) == 1:
        status, reason = 'approximate', 'same regeneration multiplier; XML1 also multiplies by 1+mind/100 '
        reason += 'and truncates to integer EP/s; XML2 lacks that factor and keeps fractions'
    elif pw == 'move' and mode == 'scale' and not scoped and len(nums) == 1:
        status, reason = 'approximate', 'same movement multiplier below XML2 total cap 2.5; '
        reason += 'XML1 has no corresponding cap (e.g. combined 3.0 becomes 2.5)'
    elif pw in ('def_knockback', 'def_pain') and mode == 'scale' and not scoped and len(nums) == 1:
        reason = 'multiply incoming knockback' if pw == 'def_knockback' else 'pain animation rate is 1/scale, clamped to 0..10'
    elif pw == 'atk_knockback_scale' and mode == 'add':
        nums = nums[:1]
        reason = 'same attack-modifier pass: multiply knockback using the level minimum'
    elif pw == 'def_stun':
        return no('XML1 stun check reads only scale affecters; an additive zero is not immunity')
    elif pw == 'drain_time' and mode == 'scale' and not scoped and len(nums) == 1:
        reason = 'multiply drain_victim duration on attachment; requires a drain_victim powerup'
    elif pw == 'xp' and mode == 'scale' and not scoped and len(nums) == 1:
        status, reason = 'approximate', 'scales kill XP in XML2; XML1 also scales direct XP awards, '
        reason += 'which XML2 bypasses (100 direct XP stays 100 instead of 100 times the multiplier)'
    elif pw == 'power_cost' and mode == 'scale' and not scoped and len(nums) == 1:
        reason = 'same energy-cost multiplier'
    else:
        return no('bonus or attribute combination has no verified mapping')

    if any(abs(n * factor) > FLOAT_MAX for n in nums):
        return no('mapped level exceeds the engine float range')
    aff = {'attribute': attr, 'level': _level(nums, factor)}
    if mode == 'scale':
        aff['affect_type'] = mode
    # Static text deliberately avoids the engine's id-specific percent formatter:
    # its special formatting would mislabel paired affecters such as regen caps.
    shown = _level(nums, factor)
    labels = {'damage': 'Damage', 'def_damage': 'Damage reduction',
              'def_damage_scope': 'Damage reduction', 'move': 'Movement speed',
              'energy_regen': 'Energy regeneration', 'def_knockback': 'Incoming knockback',
              'def_pain': 'Pain duration', 'drain_time': 'Drain duration',
              'xp': 'Kill experience', 'power_cost': 'Power energy cost',
              'atk_knockback_scale': 'Attack knockback', 'traits': 'All traits', **STAT_WORDS}
    text = f'{labels.get(attr, attr)} {"x" if mode == "scale" else "+"}{shown}'
    if pw in ('critical', 'accuracy'):
        kind = 'melee' if pw == 'critical' else 'non-melee'
        text = f'+{_level(nums, 2)} percent {kind} critical chance'
    elif pw == 'deflect_damage':
        text = f'{_level(nums)} percent deflection chance'
    elif pw == 'reflect_damage':
        text = f'Returns {_level(nums)} damage when hit'
    elif pw == 'health_regen':
        text = f'Regenerates {shown} HP per second'
        if cap[0] not in (0, 100):
            text += f' up to {_fmt(cap[0])} percent health'
    elif pw == 'atk_knockback_scale':
        text = f'Attack knockback x{shown}'
    elif pw == 'def_damage' and mode == 'scale':
        text = f'Damage taken x{shown}'
    return Bonus(pw, status, reason, [_enhancement(text, [aff] + extras, scope)])


def convert_equipment(ctx, source):
    """Return a tree plus per-bonus fidelity. No input mutation or filesystem writes."""
    from .frontend import EQUIP_ATTRS, equipment_class

    if (source.get('type') or '').lower() != 'equipment':
        return Conversion(None, [], 'not equipment')
    values = ctx.x1_values() if ctx is not None else None
    name = source.get('name', '')
    cls = {'0': 'gloves', '1': 'belt', '2': 'armor'}.get(source.get('class'), equipment_class(name))
    item = ET.Element('item', {'name': name, 'type': 'equipment', 'class': cls,
                               'model': f'pickups/equip_{cls}_c', **EQUIP_ATTRS})
    if source.get('displayname'):
        item.set('displayname', source.get('displayname'))
    for req in source.findall('require'):
        attrs = {k.lower(): v for k, v in req.attrib.items()}
        if attrs.get('cat') == 'character' and attrs.get('item'):
            attrs['item'] = attrs['item'].lower()
        ET.SubElement(item, 'require', attrs)
    bonuses = [map_bonus(p, values) for p in source.findall('activepowerup')]
    for bonus in bonuses:
        item.extend(bonus.enhancements)
    return Conversion(item if item.findall('enhancement') else None, bonuses)


def audit_equipment(ctx, root):
    """JSON-serializable coverage from the player's table; never includes game text."""
    from .frontend import translate_equipment

    items = []
    for source in root.iter('item'):
        if (source.get('type') or '').lower() != 'equipment':
            continue
        result = convert_equipment(ctx, source)
        legacy, _ = translate_equipment(ctx, source)
        items.append({'name': source.get('name', ''), 'coverage': result.coverage,
                      'approximate': any(b.status == 'approximate' for b in result.bonuses),
                      'legacy_converts': legacy is not None,
                      'bonuses': [b.report() for b in result.bonuses]})
    counts = collections.Counter(i['coverage'] for i in items)
    return {'schema': 1, 'builds_changed': False, 'verification': 'static only',
            'total': len(items), 'counts': {k: counts[k] for k in ('full', 'partial', 'none')},
            'legacy_converts': sum(i['legacy_converts'] for i in items), 'items': items}
