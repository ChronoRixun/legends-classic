"""SPEC 29: XML1 weapon definitions as style triggers (xml1build.weapons) on made-up styles - no game data."""
import xml.etree.ElementTree as ET

from xml1build import weapons as W

MP5 = {'name': 'wp_mp5', 'type': 'bullet', 'actorbolt': 'Bip01 R Hand', 'damage': 'L1', 'range': '550',
       'firesound': 'character/grso_m/fire_mp5', 'muzzlefx': 'weapons/mp5/mp5_muzzle',
       'muzzleaccfx': 'weapons/mp5/mp5_tracer', 'impactfx': 'weapons/mp5/mp5_impact'}
FLAME = {'name': 'wp_flamethrower', 'type': 'flame', 'actorbolt': 'Bip01 R Hand', 'damage': 'L3',
         'damagetype': 'dmg_fire', 'range': '275', 'continuousbeam': 'true', 'warmuptime': '1',
         'muzzleaccfx': 'weapons/flamethrower/flame_shot', 'firesound': 'character/grso_m/fire_flame',
         'chargefx': 'weapons/flamethrower/flame_charge', 'chargesound': 'character/grso_m/fire_start'}
FREEZE = {'name': 'wp_freeze_gun', 'type': 'projectile', 'entfile': 'freezegun_ents', 'projectileent': 'ice_bullet',
          'projectilespeed': '400', 'damage': 'L5', 'muzzlefx': 'weapons/freezegun/freeze_muzzle',
          'firesound': 'character/grso_m/fire_freeze'}
BATON = {'name': 'wp_baton', 'category': 'melee', 'damage': 'L2'}


def style(moves):
    root = ET.Element('PowerStyle')
    for name, triggers in moves:
        m = ET.SubElement(root, 'FightMove', {'name': name, 'animenum': 'ea_power1'})
        ET.SubElement(m, 'trigger', {'name': 'stop', 'time': '0'})
        for t in triggers:
            ET.SubElement(m, 'trigger', t)
        ET.SubElement(m, 'chain', {'action': 'idle', 'result': 'idle'})
    return root


def triggers(move):
    return [(c.get('name'), c.attrib) for c in move if c.tag == 'trigger']


def test_variant_names():
    assert W.variant_name('ps_grso', 'wp_mp5') == 'x1_ps_grso_mp5'
    assert W.variant_name('x1_ps_pistol', 'wp_pistol') == 'x1_ps_pistol_pistol'
    assert W.variant_name('ps_flamethrower', 'Wp_Flamethrower') == 'x1_ps_flamethrower_flamethrower'


def test_bullet_single_shot_becomes_beam_plus_effect_sound():
    root = style([('power_attack', [{'name': 'weapon_fire', 'time': '0'}])])
    rep = W.apply(root, MP5)
    assert rep['weapon_fire_replaced'] == 1 and rep['weapon_bullet'] == 1
    t = triggers(root.find('FightMove'))
    names = [n for n, _ in t]
    assert names == ['stop', 'beam', 'effect_sound']            # the stop stays first; no weapon_fire left
    beam = dict(t[1][1])
    assert beam['beameffect'] == 'weapons/mp5/mp5_tracer' and beam['hiteffect'] == 'weapons/mp5/mp5_impact'
    assert beam['damage'] == 'L1' and beam['maxrange'] == '550' and beam['beambolt'] == 'Bip01 R Hand'
    assert beam['damagescale'] == 'difficulty' and beam['damagelevel'] == '0' and beam['pierce'] == 'false'
    fx = dict(t[2][1])
    assert fx['effect'] == 'weapons/mp5/mp5_muzzle' and fx['sound'] == 'character/grso_m/fire_mp5'


def test_burst_stays_under_the_trigger_cap():
    fires = [{'name': 'weapon_fire', 'time': f'{0.3 + 0.07 * i:.2f}'} for i in range(7)]
    root = style([('power_boost', fires)])
    W.apply(root, MP5)
    t = triggers(root.find('FightMove'))
    assert len(t) <= W.MAX_TRIGGERS
    assert sum(1 for n, _ in t if n == 'beam') == 7                 # every shot still hits
    assert sum(1 for n, _ in t if n == 'effect_sound') >= 4         # the flash + sound on at least every other


def test_flame_is_a_tagged_beam_driven_by_the_constant_beam_timer():
    root = style([('flame_sweep', [
        {'name': 'beamdata', 'setbeam': 'true', 'time': '0.2', 'type': 'ce_set_constantbeamdata'},
        {'name': 'weapon_fire', 'tag': '150', 'time': '-1'},
        {'name': 'beamdata', 'setbeam': 'false', 'time': '0.9', 'type': 'ce_set_constantbeamdata'}])])
    rep = W.apply(root, FLAME)
    assert rep['weapon_fire_replaced'] == 1 and rep['constantbeam_interval_set'] == 1
    t = triggers(root.find('FightMove'))
    on = next(a for n, a in t if n == 'beamdata' and a.get('setbeam') == 'true')
    assert on['timeinterval'] == '0.1' and 'beameffect' not in on          # the beamdata event reads only its timer
    kinds = [n for n, _ in t]
    assert 'weapon_fire' not in kinds and kinds.count('beamdata') == 2
    flame = next(a for n, a in t if n == 'beam')
    assert flame['tag'] == '150' and flame['time'] == '-1'                 # fired by ch_constantbeam's tag
    assert flame['beameffect'] == 'weapons/flamethrower/flame_shot' and flame['damage'] == 'L3'
    assert flame['maxrange'] == '275' and flame['damagetype'] == 'dmg_fire'
    assert flame['pierce'] == 'true' and flame['noaimfx'] == 'true' and flame['useboltinfo'] == 'true'
    roar = next(a for n, a in t if n == 'sound' and a['sound'] == 'character/grso_m/fire_flame')
    assert roar['tag'] == '100' and roar['time'] == '-1'                    # looped by the engine while the beam is on
    assert any(n == 'effect_sound' and a['effect'] == 'weapons/flamethrower/flame_charge' for n, a in t)   # wind-up


def test_projectile_weapon_spawns_its_entity():
    root = style([('power_attack', [{'name': 'weapon_fire', 'time': '0.1'}])])
    W.apply(root, FREEZE)
    t = dict((n, a) for n, a in triggers(root.find('FightMove')))
    assert t['projectile']['entity'] == 'ice_bullet' and t['projectile']['filename'] == 'freezegun_ents'
    assert t['projectile']['speed'] == '400' and t['projectile']['time'] == '0.1'
    assert t['projectile']['damage'] == 'L5' and t['projectile']['targetable'] == 'true'


def test_damage_modifier_becomes_a_child():
    root = style([('power_attack', [{'name': 'weapon_fire', 'time': '0'}])])
    W.apply(root, dict(MP5, damagemod='dmgmod_no_pain'))
    beam = next(c for c in root.find('FightMove') if c.get('name') == 'beam')
    assert [m.get('name') for m in beam.findall('damageMod')] == ['dmgmod_no_pain']


def test_melee_weapon_changes_nothing():
    root = style([('power_attack', [{'name': 'punch', 'time': '0.3'}])])
    before = ET.tostring(root)
    assert not W.apply(root, BATON)
    assert ET.tostring(root) == before


def test_charge_never_before_time_zero():
    root = style([('power_attack', [{'name': 'weapon_fire', 'time': '0.2'}])])
    W.apply(root, FLAME)                                          # warmuptime 1 > 0.2 -> the wind-up at 0
    t = triggers(root.find('FightMove'))
    charge = next(a for n, a in t if n == 'effect_sound' and 'flame_charge' in a['effect'])
    assert charge['time'] == '0'


def test_weapon_moves_get_an_ai_type_so_xml2_fires_them():
    root = style([('power_attack', [{'name': 'weapon_fire', 'time': '0'}])])
    rep = W.apply(root, MP5)
    m = root.find('FightMove')
    assert rep['aitype_added'] == 1
    assert m.get('aitype') == 'beamanyrange' and m.get('aireusetime') == '3' and m.get('priority') == '5'
    root = style([('power_attack', [{'name': 'weapon_fire', 'time': '0.1'}])])
    W.apply(root, FREEZE)
    assert root.find('FightMove').get('aitype') == 'projectile'
    root = style([('flame_sweep', [{'name': 'weapon_fire', 'tag': '150', 'time': '-1'}])])
    W.apply(root, FLAME)
    assert root.find('FightMove').get('aitype') == 'projectilenear'
    root = style([('power_attack', [{'name': 'weapon_fire', 'time': '0'}])])
    root.find('FightMove').set('aitype', 'beam')                  # an XML1 move that already says
    assert not W.apply(root, MP5)['aitype_added'] and root.find('FightMove').get('aitype') == 'beam'
