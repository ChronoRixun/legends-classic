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
    assert beam['damagescale'] == 'difficulty' and beam['damagelevel'] == '1' and beam['pierce'] == 'false'
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


# SPEC 29.3: weapon events named by the style itself (invented weapon, effects and names)
TOY = {'name': 'wp_toy_pistol', 'type': 'bullet', 'actorbolt': 'Bip01 R Hand', 'damage': 'L1', 'range': '300',
       'damagemod': 'dmgmod_test', 'firesound': 'test/toy_bang', 'muzzlefx': 'test/toy_flash',
       'muzzleaccfx': 'test/toy_tracer', 'impactfx': 'test/toy_hit'}
TOYS = {'wp_toy_pistol': TOY, 'wp_toy_lobber': dict(FREEZE, name='wp_toy_lobber')}


def two_gun_style(shots=4, others=0):
    root = ET.Element('PowerStyle')
    ET.SubElement(root, 'event', {'name': 'Left_Pop', 'inherit': 'weapon_fire', 'weapon': 'wp_toy_pistol',
                                  'boltselect': 'Bip01 L Hand', 'boltonslot': 'ebolton_altweapon'})
    ET.SubElement(root, 'event', {'name': 'right_pop', 'inherit': 'weapon_fire', 'weapon': 'WP_TOY_PISTOL'})
    m = ET.SubElement(root, 'FightMove', {'name': 'power_attack', 'animenum': 'ea_power1', 'aitype': 'beam'})
    for i in range(others):
        ET.SubElement(m, 'trigger', {'name': 'sound', 'sound': 'test/other', 'time': '0'})
    for i in range(shots):
        ET.SubElement(m, 'trigger', {'name': 'left_pop' if i % 2 == 0 else 'right_pop', 'time': f'{0.5 + i / 10:g}'})
    ET.SubElement(m, 'chain', {'action': 'idle', 'result': 'idle'})
    return root


def test_weapon_events_become_beams_with_their_bolts():
    root = two_gun_style()
    rep = W.rewrite_weapon_events(root, TOYS)
    assert rep['weapon_event_to_beam'] == 2 and rep['weapon_event_shots'] == 4
    ev = {e.get('name'): e for e in root.findall('event')}
    assert set(ev) == {'Left_Pop', 'right_pop'}                  # names kept: the triggers still find them
    left, right = ev['Left_Pop'], ev['right_pop']
    assert left.get('inherit') == 'beam' and left.get('beambolt') == 'Bip01 L Hand'
    assert right.get('beambolt') == 'Bip01 R Hand'                 # no boltselect: the weapon's actorbolt
    for e in (left, right):
        assert e.get('beameffect') == 'test/toy_tracer' and e.get('hiteffect') == 'test/toy_hit'
        assert e.get('damage') == 'L1' and e.get('maxrange') == '300' and e.get('attacktype') == 'beam'
        assert 'weapon' not in e.attrib and 'boltselect' not in e.attrib and 'time' not in e.attrib
        assert [d.get('name') for d in e.findall('damageMod')] == ['dmgmod_test']
    assert W.weapon_fire_left(root) == []


def test_weapon_event_shots_get_muzzle_fx_only_within_the_trigger_cap():
    root = two_gun_style(shots=6, others=W.MAX_TRIGGERS - 6 - 2)    # room for two effect_sound triggers
    W.rewrite_weapon_events(root, TOYS)
    trig = [c for c in root.find('FightMove') if c.tag == 'trigger']
    assert len(trig) == W.MAX_TRIGGERS
    fx = [c for c in trig if c.get('name') == 'effect_sound']
    assert [(c.get('time'), c.get('bolt')) for c in fx] == [('0.5', 'Bip01 L Hand'), ('0.6', 'Bip01 R Hand')]
    assert [c.get('name') for c in trig].count('left_pop') == 3   # every shot trigger kept
    full = two_gun_style(shots=4, others=W.MAX_TRIGGERS - 4)
    rep = W.rewrite_weapon_events(full, TOYS)
    assert not rep['weapon_event_fx_added'] and not rep['moves_over_trigger_cap']


def test_weapon_events_through_an_inheriting_event_and_non_bullets():
    root = two_gun_style(shots=1)
    ET.SubElement(root, 'event', {'name': 'left_pop_hard', 'inherit': 'left_pop', 'damage': 'L3'})
    ET.SubElement(root, 'event', {'name': 'lob', 'inherit': 'weapon_fire', 'weapon': 'wp_toy_lobber'})
    ET.SubElement(root, 'event', {'name': 'mystery', 'inherit': 'weapon_fire', 'weapon': 'wp_not_there'})
    ET.SubElement(root, 'event', {'name': 'unarmed', 'inherit': 'weapon_fire'})
    rep = W.rewrite_weapon_events(root, TOYS)
    ev = {e.get('name'): e for e in root.findall('event')}
    assert ev['left_pop_hard'].get('inherit') == 'beam' and ev['left_pop_hard'].get('beambolt') == 'Bip01 L Hand'
    assert ev['left_pop_hard'].get('damage') == 'L1'               # the weapon's damage, as XML1's weapon supplies it
    assert ev['lob'].get('inherit') == 'weapon_fire' and rep['weapon_event_projectile_kept'] == 1
    assert ev['mystery'].get('inherit') == 'weapon_fire' and rep['weapon_event_unknown_weapon'] == 1
    assert ev['unarmed'].get('inherit') == 'weapon_fire'           # names no weapon: left alone


def test_weapon_fire_left_finds_plain_and_event_shots():
    root = two_gun_style(shots=2)
    m = root.find('FightMove')
    ET.SubElement(m, 'trigger', {'name': 'weapon_fire', 'time': '0.9'})
    ET.SubElement(m, 'trigger', {'name': 'weapon_fire', 'type': 'ce_sound', 'time': '1'})   # an explicit type wins
    assert W.weapon_fire_left(root) == [('power_attack:left_pop', True), ('power_attack:right_pop', True),
                                        ('power_attack:weapon_fire', False)]
    assert W.weapon_fire_left(None) == []
