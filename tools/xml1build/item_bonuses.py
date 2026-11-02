"""The first game's equipment bonuses as the PC engine's item enhancements (loot step 1).

See docs/ITEM_BONUSES.md for the two-engine consumer evidence and limitations. Since 0.4.2 (`--loot xml1`,
xml1build.loot) every one of the 168 source powerups is converted: nothing is pending (owner decision D3), every
record the economy writes is single-valued (plan A's x1_make_instance fixes the interpolation, so min == max), and
every conversion that is not exact is reported with its reason for the generated approximations file. The legacy
converter (frontend.translate_equipment) is untouched for builds without the option. All source values and item
identities come from the caller's files.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
import xml.etree.ElementTree as ET


SCOPE_KEYS = frozenset(('scope_damage', 'scope_attack', 'scope_node', 'scope_race',
                        'scope_character', 'scope_powers', 'scope_non_powers', 'scope_talent'))
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

# Bonus.status values (the first four are conversions, 'unsupported' is an error in a loot build)
EXACT, APPROXIMATE, SOURCE_NOOP, ADAPTER, UNSUPPORTED = 'exact', 'approximate', 'source_noop', 'adapter', 'unsupported'
# the approximations file's row kind of each status
KIND_OF_STATUS = {EXACT: 'exact', APPROXIMATE: 'bonus-approx', SOURCE_NOOP: 'noop-original', ADAPTER: 'adapter'}
# the family column of the approximations file (ITEM_BONUSES.md families), by source powerup
FAMILY = {'strength': 'stat scale', 'speed': 'stat scale', 'body': 'stat scale', 'mind': 'stat scale',
          'traits': 'stat scale', 'damage': 'damage stage', 'atk_damage': 'damage stage',
          'atk_damage_scale': 'damage stage', 'def_damage': 'defense', 'def_damage_scale': 'original no-op',
          'def_stun': 'original no-op', 'critical': 'critical chance', 'accuracy': 'critical chance',
          'deflect_damage': 'deflection', 'reflect_damage': 'reflection', 'health_regen': 'regeneration',
          'energy_regen': 'regeneration', 'move': 'movement', 'def_knockback': 'knockback',
          'def_pain': 'knockback', 'atk_knockback_scale': 'knockback', 'drain_time': 'drain', 'xp': 'experience',
          'power_cost': 'power cost', 'special': 'secondary attack', 'none': 'damage over time'}


@dataclass
class Bonus:
    powerup: str
    status: str                     # EXACT / APPROXIMATE / SOURCE_NOOP / ADAPTER / UNSUPPORTED
    reason: str
    enhancements: list = field(default_factory=list, repr=False)
    family_name: str = ''            # overrides the family of the source powerup (the D8 resist records)

    def report(self):
        return {'bonus': self.powerup, 'status': self.status, 'reason': self.reason}

    @property
    def kind(self):
        return KIND_OF_STATUS.get(self.status)

    @property
    def family(self):
        return self.family_name or FAMILY.get(self.powerup, 'other')


@dataclass
class Conversion:
    item: ET.Element | None
    bonuses: list[Bonus]
    error: str = ''

    @property
    def coverage(self):
        if self.item is None:
            return 'none'
        return 'partial' if any(b.status == UNSUPPORTED for b in self.bonuses) else 'full'

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


def _mean(nums):
    return sum(nums) / len(nums)


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
            if key in ('scope_powers', 'scope_non_powers') and value.lower() not in ('true', 'false'):
                raise ValueError('invalid scope_powers')
    return attrs, children


def _enhancement(text, attributes, scope=({}, ()), powerup=None):
    """<enhancement><powerup life="-1"><affecter .../>...: `powerup` adds attributes to the powerup element (the
    class="add_attack" / class="add_harming" forms the shipped XML2 gear uses)."""
    e = ET.Element('enhancement', {'description': text})
    pu = ET.SubElement(e, 'powerup', {'life': '-1', **(powerup or {})})
    for attrs in attributes:
        aff = ET.SubElement(pu, 'affecter', {**attrs, **scope[0]})
        for child in scope[1]:
            ET.SubElement(aff, 'scope', child)
    return e


def single_valued(enhancement):
    """True when every affecter level of an enhancement is one number (the premise of plan A's fixed interpolation:
    the engine draws between `min max`; with min == max every draw gives the same bonus)."""
    for aff in enhancement.iter('affecter'):
        level = aff.get('level')
        if level is not None and len(level.split()) != 1:
            return False
    return True


RANGE_NOTE = 'the source range collapses to its mean (every economy record is single-valued)'


def _callback(p, values, pw, no):
    """func_damage callbacks (special / damageaddattack, none / DamageAddBleed). Both have a PC mechanism in the
    shipped XML2 gear, so neither is an adapter row; both are approximations (merging, damage mods, tick shape)."""
    callback = p.get('func_damage').lower()
    if callback not in ('damageaddattack', 'damageaddbleed'):
        return no('untraced damage callback')
    try:
        nums = _numbers(p.get('level'), values)
        scope = _scope(p)
    except ValueError as e:
        return no(str(e))
    if p.get('life', '-1') != '-1':
        return no('only permanent equipment bonuses are supported')
    amount = _mean(nums)
    note = RANGE_NOTE if len(nums) == 2 else ''
    if callback == 'damageaddattack':
        damage_type = (p.get('damagetype') or '').lower()
        if pw != 'special' or damage_type not in DAMAGE_TYPES:
            return no('secondary attack needs the special powerup and a known damage type')
        # the shipped XML2 item form (NANOCORE_STAFF): class add_attack + a flat `special` affecter
        reason = ('the PC add_attack fixed-damage form: one flat secondary hit of the source amount; XML2 merges it with '
                  'same-type damage and applies its own damage mods')
        if p.get('damagemod'):
            reason += f'; the source damage mod {p.get("damagemod").lower()} is not carried'
        if note:
            reason += '; ' + note
        text = f'+{_fmt(amount)} {damage_type.replace("dmg_", "").replace("_", " ")} damage on hit'
        enh = _enhancement(text, [{'attribute': 'special', 'level': _fmt(amount)}], scope,
                           {'class': 'add_attack', 'damagetype': damage_type})
        return Bonus(pw, APPROXIMATE, reason, [enh])
    # DamageAddBleed: add_harming damage over time (HAMMER_NIMROD's radiation="false" bleed form)
    try:
        seconds = _numbers(p.get('user1'), values)
    except ValueError as e:
        return no('bleed duration: ' + str(e))
    if len(seconds) != 1 or seconds[0] <= 0:
        return no('bleed duration must be one positive number')
    e = ET.Element('enhancement', {'description': f'+{_fmt(amount)} bleed damage over {_fmt(seconds[0])} seconds'})
    pu = ET.SubElement(e, 'powerup', {'class': 'add_harming', 'damage': _fmt(amount), 'life': '-1',
                                      'radiation': 'false', 'time': _fmt(seconds[0])})
    if scope[0] or scope[1]:
        ps = ET.SubElement(pu, 'affecter', {'attribute': 'powerup_scope'})
        for sc in ([scope[0]] if scope[0] else []) + list(scope[1]):
            ET.SubElement(ps, 'scope', sc)
    reason = ('the PC add_harming damage-over-time form (the shipped bleed gear\'s): the source tick, stacking and '
              'lifetime rules are XML1 code and are not reproduced')
    if note:
        reason += '; ' + note
    return Bonus(pw, APPROXIMATE, reason, [e])


# D8 (DESIGN 12): `def_damage_scale` is never registered by the original's parser, so the four items whose only bonus it
# is carried no working bonus in XML1. DEF_DAMAGE_SCALE_MODES: 'noop' (default; the original's behaviour, no record) or
# 'resist' (the authored multiplier written as the PC damage-resistance record the source `def_damage` scale items
# already use; every such record is a `bonus-approx` row).
DEF_DAMAGE_SCALE_MODES = ('noop', 'resist')
RESIST_FAMILY = 'defense (resist)'


def map_bonus(p, values=None, resist=False):
    """Map one permanent source bonus; reject unsupported semantics explicitly. Every record written is single-valued.
    resist: write `def_damage_scale` as a damage-resistance record instead of the original's no-op (D8)."""
    from .frontend import STAT_WORDS, stat_scale

    p = copy.deepcopy(p)
    for node in p.iter():
        node.attrib = {k.lower(): v for k, v in node.attrib.items()}
    pw = (p.get('powerup') or '').lower()

    def no(reason):
        return Bonus(pw or '?', UNSUPPORTED, reason)

    if p.get('func_damage'):
        return _callback(p, values, pw, no)
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
    if min(nums) < 0 and pw not in ('strength', 'speed', 'body', 'mind', 'traits'):
        return no('negative level outside the supported stat mapping')

    status, reason = EXACT, 'same affecter contribution and aggregation'
    attr, factor = pw, 1
    extras = []
    collapsed = ''
    if pw in ('strength', 'speed', 'body', 'mind', 'traits') and mode == 'add' and not scoped:
        factor = stat_scale(pw)
        status, reason = APPROXIMATE, f'port stat conversion: source points multiplied by {factor}'
    elif pw in ('damage', 'atk_damage', 'atk_damage_scale'):
        attr = 'damage'
        status = APPROXIMATE
        if pw == 'damage':
            reason = 'same damage term; XML1 truncates integer contributions, XML2 rounds '
            reason += 'the added/scaled contribution upward (difference up to one HP before later modifiers)'
            if len(nums) == 2:
                nums = (_mean(nums),)
                collapsed = RANGE_NOTE
        else:
            if mode != 'add':
                return no('XML1 attack modifiers use their name, not affect_type, to choose aggregation')
            nums = nums[:1]  # XML1 modifier pass reads level minimum, never level_max.
            mode = 'scale' if pw.endswith('_scale') else 'add'
            reason = 'XML1 final attack modifier moved to XML2 damage-construction stage; '
            reason += 'standalone contribution matches, but additive/scale combinations need not commute '
            reason += '(base 100, damage add 10, attack scale 1.2: 132 vs 130 before rounding)'
    elif pw == 'def_damage_scale' and not resist:
        return Bonus(pw, SOURCE_NOOP, 'unregistered in original bonus table 0x44e8c8; preserve original no-op',
                     [_enhancement('Inactive source bonus', [{'attribute': 'none', 'level': '0'}], scope)])
    elif pw == 'def_damage' or pw == 'def_damage_scale':          # (the latter only with resist: D8)
        resisted = pw == 'def_damage_scale'
        if resisted:
            mode = 'scale'                  # the authored value is a multiplier (0.5 = half the damage taken)
        attr = 'def_damage_scope' if scoped else 'def_damage'
        if len(nums) != 1:
            return no('cached unscoped defense does not preserve a random range' if not scoped
                      else 'a defense range cannot be a single-valued record')
        reason = 'subtract HP before multiplying; scoped form uses the combat-context query'
        if resisted:
            status = APPROXIMATE
            reason = ('owner option D8 (resist): the original never registers def_damage_scale (bonus table 0x44e8c8), '
                      'so the item had no working bonus there; the authored multiplier is written as the PC scoped '
                      'damage-resistance scale record (incoming damage of the scope x the value, the form the source '
                      'def_damage scale items use)')
            if nums[0] == 0:
                reason += '; a multiplier of 0 is full immunity to the scope'
        elif mode == 'scale' or any(not n.is_integer() for n in nums):
            status, reason = APPROXIMATE, 'same defense term; XML1 truncates damage to integer HP, '
            reason += 'XML2 keeps fractional HP (less than one HP per hit before later modifiers)'
    elif pw == 'critical' and mode == 'add' and not scoped and len(nums) == 1:
        factor = 0.02
        status = APPROXIMATE
        reason = 'two percentage points per source rank, on punch/kick/throw; add probabilities. '
        reason += 'XML2 rejects target structure >=2, XML1 >=10; structure must be converted consistently'
    elif pw == 'accuracy' and mode == 'add' and not scoped and len(nums) == 1:
        attr, factor = 'atk_critical', 0.02
        scope = ({}, [{'scope_attack': attack} for attack in NON_MELEE])
        status = APPROXIMATE
        reason = 'two percentage points per source rank outside punch/kick/throw; scoped critical chance. '
        reason += 'XML2 rejects target structure >=2, XML1 >=10; structure must be converted consistently'
    elif pw == 'deflect_damage' and mode == 'add':
        factor = 0.01
        reason = 'percent to probability; successful deflection returns the incoming attack and cancels it'
    elif pw == 'reflect_damage' and mode == 'add':
        if p.get('user1') is None:
            return no('reflection without a chance')
        try:
            chance = _numbers(p.get('user1'), values)
        except ValueError as e:
            return no(str(e))
        if len(chance) != 1 or not 0 < chance[0] <= 100:
            return no('XML1 user1 is a per-hit percentage in 1..100')
        fraction = chance[0] / 100
        if fraction < 1 or len(nums) == 2:
            # DESIGN 2.3: no per-hit gate (it would be a lockstep draw): the return damage at its expected value
            nums = (_mean(nums) * fraction,)
            collapsed = (f'XML1 rolls {_fmt(chance[0])} percent per hit, the record returns the expected value '
                         f'(chance x amount) on every hit with no gate'
                         + ('; ' + RANGE_NOTE if p.get('level') and len(_numbers(p.get('level'), values)) == 2 else ''))
        extras.append({'attribute': 'reflect_damage', 'affect_type': 'scale', 'level': '0'})
        status, reason = APPROXIMATE, 'fixed return damage; scale zero removes XML2 incoming-damage term. '
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
        status, reason = APPROXIMATE, 'same nominal regeneration coefficient and single-item cap; '
        reason += 'each scheduled tick restores 0.1 times the rate, so late ticks lower elapsed-time HP/s. '
        reason += 'XML2 starts immediately instead of waiting 5/regen-scale seconds after damage, '
        reason += 'and combines caps by minimum instead of maximum'
    elif pw == 'energy_regen' and mode == 'scale' and not scoped and len(nums) == 1:
        status, reason = APPROXIMATE, 'same regeneration multiplier; XML1 also multiplies by 1+mind/100 '
        reason += 'and truncates to integer EP/s; XML2 lacks that factor and keeps fractions'
    elif pw == 'move' and mode == 'scale' and not scoped and len(nums) == 1:
        status, reason = APPROXIMATE, 'same movement multiplier below XML2 total cap 2.5; '
        reason += 'XML1 has no corresponding cap (e.g. combined 3.0 becomes 2.5)'
    elif pw in ('def_knockback', 'def_pain') and mode == 'scale' and not scoped and len(nums) == 1:
        reason = 'multiply incoming knockback' if pw == 'def_knockback' else 'pain animation rate is 1/scale, clamped to 0..10'
    elif pw == 'atk_knockback_scale' and mode == 'add':
        nums = nums[:1]
        reason = 'same attack-modifier pass: multiply knockback using the level minimum'
    elif pw == 'def_stun' and mode == 'add' and nums == (0.0,):
        return Bonus(pw, SOURCE_NOOP, 'original stun check reads scale only; additive zero has no effect',
                     [_enhancement('Inactive source bonus', [{'attribute': 'none', 'level': '0'}], scope)])
    elif pw == 'drain_time' and mode == 'scale' and not scoped and len(nums) == 1:
        reason = 'multiply drain_victim duration on attachment; requires a drain_victim powerup'
    elif pw == 'xp' and mode == 'scale' and not scoped and len(nums) == 1:
        status, reason = APPROXIMATE, 'scales kill XP in XML2; XML1 also scales direct XP awards, '
        reason += 'which XML2 bypasses (100 direct XP stays 100 instead of 100 times the multiplier)'
    elif pw == 'power_cost' and mode == 'scale' and len(nums) == 1:
        reason = 'same energy-cost multiplier'
    else:
        return no('bonus or attribute combination has no verified mapping')

    if collapsed:
        status = APPROXIMATE
        reason = reason + '; ' + collapsed
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
        text = f'Health regeneration +{shown}'
        if cap[0] not in (0, 100):
            text += f' up to {_fmt(cap[0])} percent health'
    elif pw == 'atk_knockback_scale':
        text = f'Attack knockback x{shown}'
    elif pw in ('def_damage', 'def_damage_scale') and mode == 'scale':
        text = f'Damage taken x{shown}'
    enh = _enhancement(text, [aff] + extras, scope)
    if not single_valued(enh):
        return no('the converted record is not single-valued')
    return Bonus(pw, status, reason, [enh], RESIST_FAMILY if pw == 'def_damage_scale' else '')


# ------------------------------------------------------------------------------------------ equipment definitions
CLASS_MAP = {'0': 'gloves', '1': 'belt', '2': 'armor'}
OWN_SLOTS = 8
OWN_ABSENT = 0xffff                  # the W2 sentinel for "no own record"


def convert_equipment(ctx, source, *, name, displayname=None, values=None, def_damage_scale='noop'):
    """One source equipment definition -> (Conversion): an XML2 <item type="equipment"> named `name` whose children
    are the requirements and one enhancement per converted source powerup in source order (a source no-op keeps its
    explicit `none` record's place only when ``noop_records`` is true; the economy does not write one, as XML1 does
    nothing there). Source cost / unique / class are copied as they are; text is filled by the caller.
    def_damage_scale 'resist' (D8): an item whose every bonus is `def_damage_scale` (the four dead items) gets the
    authored multiplier as a damage-resistance record; any other mode or item keeps the original's no-op."""
    if source.get('type', '').lower() != 'equipment':
        return Conversion(None, [], 'not equipment')
    cls = CLASS_MAP.get(source.get('class'))
    if cls is None or not source.get('name'):
        raise ValueError('equipment requires a name and numeric class 0..2')
    a = {'name': name, 'type': 'equipment', 'class': cls, 'model': f'pickups/equip_{cls}_c', 'enemy_level': '-1',
         'heft': 'light'}
    # Missing cost remains missing; it must not acquire a guessed sale price.
    if source.get('cost') is not None:
        a['cost'] = source.get('cost')
    if source.get('unique') is not None:
        a['unique'] = source.get('unique')
    a['displayname'] = displayname if displayname is not None else source.get('displayname', '')
    if source.get('description') is not None:
        a['description'] = source.get('description')
    item = ET.Element('item', a)
    for req in source.findall('require'):
        attrs = {k.lower(): v for k, v in req.attrib.items()}
        if attrs.get('cat') not in ('character', 'level'):
            raise ValueError('unmapped equipment requirement category')
        if attrs.get('cat') == 'character' and attrs.get('item'):
            attrs['item'] = attrs['item'].lower()
        ET.SubElement(item, 'require', attrs)
    values = values if values is not None else (ctx.x1_values() if ctx is not None else None)
    powerups = source.findall('activepowerup')
    resist = (def_damage_scale == 'resist' and bool(powerups)
              and all((p.get('powerup') or p.get('POWERUP') or '').lower() == 'def_damage_scale' for p in powerups))
    bonuses = [map_bonus(p, values, resist=resist) for p in powerups]
    for bonus in bonuses:
        if bonus.status == SOURCE_NOOP:
            continue                  # XML1 does nothing for it either: no record
        for enh in bonus.enhancements:
            item.append(enh)
    return Conversion(item, bonuses)
