"""Synthetic bonus semantics of the economy's converter (xml1build.item_bonuses): every source powerup converts,
every record is single-valued, and every non-exact conversion carries a reason. Invented items only."""
import xml.etree.ElementTree as ET

from xml1build import item_bonuses as IB
from xml1build.heroes import Values


def bonus(name, level, **attrs):
    return ET.Element('activepowerup', {'powerup': name, 'level': level, 'life': '-1', **attrs})


def source(*bonuses, **attrs):
    e = ET.Element('item', {'name': 'invented_token', 'type': 'equipment', 'class': '0', **attrs})
    e.extend(bonuses)
    return e


def values():
    r = ET.Element('values')
    ET.SubElement(r, 'value', name='L7', min='12', max='18')
    ET.SubElement(r, 'value', name='A7', min='9')
    ET.SubElement(r, 'value', name='L8', min='10', max='10')
    return Values(r)


def affecters(result):
    return list(result.enhancements[0].iter('affecter'))


def test_bonus_flat_defense_is_hp_and_scoped_defense_uses_context_query():
    p = bonus('def_damage', '9')
    a = affecters(IB.map_bonus(p))[0]
    assert a.attrib == {'attribute': 'def_damage', 'level': '9'}
    p.set('scope_attack', 'beam')
    a = affecters(IB.map_bonus(p))[0]
    assert a.get('attribute') == 'def_damage_scope' and a.get('scope_attack') == 'beam'


def test_bonus_ranges_become_one_number_and_the_final_attack_modifier_keeps_its_minimum():
    r = IB.map_bonus(bonus('damage', 'L7'), values())
    assert affecters(r)[0].get('level') == '15' and r.status == IB.APPROXIMATE and 'mean' in r.reason
    r = IB.map_bonus(bonus('atk_damage', 'L7'), values())
    assert affecters(r)[0].get('level') == '12' and r.status == IB.APPROXIMATE
    r = IB.map_bonus(bonus('damage', 'L8'), values())          # min == max: not a collapse
    assert affecters(r)[0].get('level') == '10' and 'mean' not in r.reason


def test_bonus_accuracy_and_melee_critical_use_probability_in_separate_domains():
    a = affecters(IB.map_bonus(bonus('accuracy', '4')))[0]
    assert a.get('attribute') == 'atk_critical' and a.get('level') == '0.08'
    assert {s.get('scope_attack') for s in a} == set(IB.NON_MELEE)
    a = affecters(IB.map_bonus(bonus('critical', '3')))[0]
    assert a.get('attribute') == 'critical' and a.get('level') == '0.06' and not list(a)


def test_bonus_regeneration_retains_cap_with_one_record():
    r = IB.map_bonus(bonus('health_regen', '4', user1='50'))
    assert len(r.enhancements) == 1 and r.status == IB.APPROXIMATE
    assert [a.get('level') for a in affecters(r)] == ['4', '0.5']
    assert affecters(r)[1].get('affect_type') == 'max'


def test_bonus_reflection_is_the_expected_value_with_no_per_hit_gate():
    r = IB.map_bonus(bonus('reflect_damage', '8', user1='25'))
    assert r.status == IB.APPROXIMATE and 'expected value' in r.reason
    assert [(a.get('level'), a.get('affect_type')) for a in affecters(r)] == [('2', None), ('0', 'scale')]
    r = IB.map_bonus(bonus('reflect_damage', '7', user1='100'))
    assert [(a.get('level'), a.get('affect_type')) for a in affecters(r)] == [('7', None), ('0', 'scale')]
    assert 'expected value' not in r.reason
    r = IB.map_bonus(bonus('reflect_damage', 'L7', user1='50'), values())          # range x chance
    assert affecters(r)[0].get('level') == '7.5' and 'mean' in r.reason
    for p in (bonus('reflect_damage', '7'), bonus('reflect_damage', '7', user1='0'), bonus('reflect_damage', '7', user1='101')):
        assert IB.map_bonus(p).status == IB.UNSUPPORTED


def test_bonus_child_scopes_share_one_record_without_splitting_or_broadening():
    p = bonus('atk_damage_scale', '1.2', scope_race='Robot')
    ET.SubElement(p, 'scope', scope_attack='punch')
    ET.SubElement(p, 'scope', scope_attack='kick')
    before = ET.tostring(p)
    r = IB.map_bonus(p)
    assert len(r.enhancements) == 1
    a = affecters(r)[0]
    assert a.get('scope_race') == 'Robot' and len(list(a)) == 2
    assert a.get('affect_type') == 'scale'
    assert ET.tostring(p) == before


def test_bonus_negative_traits_and_scoped_power_cost_are_preserved():
    assert affecters(IB.map_bonus(bonus('body', '-2')))[0].get('level') == '-8'
    a = affecters(IB.map_bonus(bonus('power_cost', '0.7', affect_type='scale', scope_node='invented_flight')))[0]
    assert a.get('scope_node') == 'invented_flight' and a.get('level') == '0.7'


def test_bonus_original_noops_are_explicit_and_do_not_create_immunity():
    for name in ('def_damage_scale', 'def_stun'):
        r = IB.map_bonus(bonus(name, '0'))
        assert r.status == IB.SOURCE_NOOP and r.kind == 'noop-original' and affecters(r)[0].get('attribute') == 'none'


def test_bonus_def_damage_scale_resist_option_writes_the_pc_scoped_resistance_scale_record():
    # D8: default (and resist=False) is the original no-op; resist=True is the scoped damage-resistance scale record
    default = IB.map_bonus(bonus('def_damage_scale', '0.5', scope_damage='dmg_energy'))
    assert default.status == IB.SOURCE_NOOP and default.kind == 'noop-original' and default.family == 'original no-op'
    r = IB.map_bonus(bonus('def_damage_scale', '0.5', scope_damage='dmg_energy'), resist=True)
    assert r.status == IB.APPROXIMATE and r.kind == 'bonus-approx' and r.family == IB.RESIST_FAMILY and r.reason
    a = affecters(r)
    assert len(a) == 1 and a[0].get('attribute') == 'def_damage_scope' and a[0].get('affect_type') == 'scale'
    assert a[0].get('level') == '0.5' and a[0].get('scope_damage') == 'dmg_energy'
    assert IB.single_valued(r.enhancements[0]) and r.enhancements[0].get('description') == 'Damage taken x0.5'
    # the same record the source def_damage scale items already get (its authored form is the model)
    twin = IB.map_bonus(bonus('def_damage', '0.5', affect_type='scale', scope_damage='dmg_energy'))
    assert ET.tostring(twin.enhancements[0]) == ET.tostring(r.enhancements[0])
    # an attack-type scope and the zero multiplier (full immunity) convert; a negative or a range does not
    beam = IB.map_bonus(bonus('def_damage_scale', '0.8', scope_attack='beam'), resist=True)
    assert beam.status == IB.APPROXIMATE and affecters(beam)[0].get('scope_attack') == 'beam'
    zero = IB.map_bonus(bonus('def_damage_scale', '0', scope_damage='dmg_mental'), resist=True)
    assert zero.status == IB.APPROXIMATE and 'full immunity' in zero.reason and affecters(zero)[0].get('level') == '0'
    assert IB.map_bonus(bonus('def_damage_scale', '-1', scope_damage='dmg_mental'), resist=True).status == IB.UNSUPPORTED
    assert IB.map_bonus(bonus('def_damage_scale', 'L7', scope_damage='dmg_mental'), values(), resist=True).status \
        == IB.UNSUPPORTED
    # def_stun stays the original no-op in both modes
    assert IB.map_bonus(bonus('def_stun', '0'), resist=True).status == IB.SOURCE_NOOP


def test_equipment_resist_applies_to_items_whose_only_bonus_is_def_damage_scale():
    dead = source(bonus('def_damage_scale', '0.5', scope_damage='dmg_physical'))
    mixed = source(bonus('def_damage_scale', '0.5', scope_damage='dmg_physical'), bonus('body', '1'))
    assert not IB.convert_equipment(None, dead, name='x_dead', values=None).item.findall('enhancement')
    on = IB.convert_equipment(None, dead, name='x_dead', values=None, def_damage_scale='resist')
    assert len(on.item.findall('enhancement')) == 1 and on.bonuses[0].status == IB.APPROXIMATE
    m = IB.convert_equipment(None, mixed, name='x_mixed', values=None, def_damage_scale='resist')
    assert [b.status for b in m.bonuses] == [IB.SOURCE_NOOP, IB.APPROXIMATE] and len(m.item.findall('enhancement')) == 1


def test_bonus_callbacks_use_the_shipped_pc_forms_not_a_pending_row():
    r = IB.map_bonus(bonus('special', 'L7', func_damage='damageaddattack', damagetype='dmg_fire', scope_attack='punch'),
                     values())
    pu = r.enhancements[0].find('powerup')
    assert r.status == IB.APPROXIMATE and r.kind == 'bonus-approx'
    assert pu.get('class') == 'add_attack' and pu.get('damagetype') == 'dmg_fire' and pu.get('life') == '-1'
    a = pu.find('affecter')
    assert a.get('attribute') == 'special' and a.get('level') == '15' and a.get('scope_attack') == 'punch'
    assert IB.single_valued(r.enhancements[0])
    r = IB.map_bonus(bonus('none', 'A7', func_damage='DamageAddBleed', user1='5', scope_attack='projectile'), values())
    pu = r.enhancements[0].find('powerup')
    assert r.status == IB.APPROXIMATE and pu.get('class') == 'add_harming' and pu.get('damage') == '9'
    assert pu.get('time') == '5' and pu.get('radiation') == 'false'
    assert pu.find('affecter/scope').get('scope_attack') == 'projectile'
    for p in (bonus('special', 'L7', func_damage='damageaddattack'),          # no damage type
              bonus('none', 'A7', func_damage='DamageAddBleed'),               # no duration
              bonus('none', 'A7', func_damage='DamageAddBleed', user1='0'),
              bonus('special', 'L7', func_damage='unknown_callback', damagetype='dmg_fire')):
        assert IB.map_bonus(p, values()).status == IB.UNSUPPORTED


def test_bonus_invalid_unknown_and_nonfinite_values_are_reported():
    for p in (bonus('unknown_bonus', '4'), bonus('damage', 'nan'), bonus('damage', 'L9'),
              bonus('damage', '8 2'), bonus('damage', '4', scope_race='invented_race'),
              bonus('body', '1', life='20')):
        r = IB.map_bonus(p, values())
        assert r.status == IB.UNSUPPORTED and r.reason and not r.enhancements


def test_every_converted_record_is_single_valued():
    ok = [bonus('damage', 'L7'), bonus('atk_damage', 'L7'), bonus('reflect_damage', 'L7', user1='30'),
          bonus('special', 'L7', func_damage='damageaddattack', damagetype='dmg_direct'), bonus('body', '2'),
          bonus('health_regen', '3', user1='40'), bonus('speed', '1')]
    for p in ok:
        r = IB.map_bonus(p, values())
        assert r.enhancements and all(IB.single_valued(e) for e in r.enhancements), p.attrib
    e = ET.fromstring('<enhancement><powerup><affecter attribute="damage" level="1 2"/></powerup></enhancement>')
    assert not IB.single_valued(e)


def test_equipment_source_cost_class_unique_and_requirements_do_not_use_name_heuristics():
    for n, cls in IB.CLASS_MAP.items():
        s = source(bonus('body', '1'), name='invented_armor_belt', **{'class': n, 'cost': '1234', 'unique': 'true',
                                                                       'description': 'invented text'})
        ET.SubElement(s, 'require', cat='character', item='Invented_Hero')
        ET.SubElement(s, 'require', cat='level', level='17')
        before = ET.tostring(s)
        r = IB.convert_equipment(None, s, name='lc_x1_invented', displayname='Invented Name', values=None).item
        assert r.get('class') == cls and r.get('model') == 'pickups/equip_' + cls + '_c'
        assert r.get('cost') == '1234' and r.get('unique') == 'true'
        assert r.get('displayname') == 'Invented Name' and r.get('description') == 'invented text'
        assert r.get('enemy_level') == '-1' and r.get('quality') is None
        assert r.find('require').get('item') == 'invented_hero' and r.findall('require')[1].get('level') == '17'
        assert r.get('name') == 'lc_x1_invented' and ET.tostring(s) == before
    r = IB.convert_equipment(None, source(bonus('body', '1')), name='lc_x1_x', values=None).item
    assert r.get('cost') is None and r.get('unique') is None


def test_equipment_noop_bonuses_write_no_record_and_keep_source_order():
    s = source(bonus('body', '1'), bonus('def_damage_scale', '0', scope_damage='dmg_mental'), bonus('speed', '2'))
    c = IB.convert_equipment(None, s, name='lc_x1_x', values=None)
    assert [b.status for b in c.bonuses] == [IB.APPROXIMATE, IB.SOURCE_NOOP, IB.APPROXIMATE]
    assert len(c.item.findall('enhancement')) == 2
    assert c.coverage == 'full'
    s = source(bonus('def_damage_scale', '0'))
    assert not IB.convert_equipment(None, s, name='lc_x1_x', values=None).item.findall('enhancement')


def test_family_and_kind_labels_cover_every_status():
    assert {IB.Bonus('damage', st, '').kind for st in (IB.EXACT, IB.APPROXIMATE, IB.SOURCE_NOOP, IB.ADAPTER)} == \
        {'exact', 'bonus-approx', 'noop-original', 'adapter'}
    assert IB.Bonus('reflect_damage', IB.EXACT, '').family == 'reflection'
    assert IB.Bonus('invented', IB.EXACT, '').family == 'other'
