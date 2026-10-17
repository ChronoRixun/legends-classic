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
    assert m.get('aitype') == 'beamanyrange' and m.get('aireusetime') == '3' and m.get('priority') is None
    root = style([('power_attack', [{'name': 'weapon_fire', 'time': '0.1'}])])
    W.apply(root, FREEZE)
    assert root.find('FightMove').get('aitype') == 'projectile'
    root = style([('flame_sweep', [{'name': 'weapon_fire', 'tag': '150', 'time': '-1'}])])
    W.apply(root, FLAME)
    assert root.find('FightMove').get('aitype') == 'projectilenear'
    root = style([('power_attack', [{'name': 'weapon_fire', 'time': '0'}])])
    root.find('FightMove').set('aitype', 'beam')                  # an XML1 move that already says
    assert not W.apply(root, MP5)['aitype_added'] and root.find('FightMove').get('aitype') == 'beam'


def test_weapon_ai_translation_preserves_reaction_priority():
    # V45: an AI type schedules a shot; it does not grant reaction immunity.
    # Exercise all translated weapon types, explicit/omitted priorities, and an
    # existing AI declaration. Unrelated moves and the override stay authored.
    for kind in ('bullet', 'beam', 'projectile', 'flame'):
        weapon = dict(TOY, name='wp_test_launcher', type=kind,
                      entfile='test_entities', projectileent='test_bolt')
        for priority in (None, '0', '3', 'uninterruptable'):
            for ai in (None, 'test_existing_ai'):
                root = style([('test_shot', [{'name': 'weapon_fire', 'time': '0'}]),
                              ('test_idle', [{'name': 'stop', 'time': '0'}])])
                shot, idle = root.findall('FightMove')
                shot.set('priority_override', '2')
                if priority is not None:
                    shot.set('Priority', priority)
                if ai is not None:
                    shot.set('aitype', ai)
                idle.set('priority', '6')
                W.apply(root, weapon)
                priorities = {k.lower(): v for k, v in shot.attrib.items() if k.lower().startswith('priority')}
                expected = {'priority_override': '2'}
                if priority is not None:
                    expected['priority'] = priority
                assert priorities == expected
                assert idle.get('priority') == '6'
                assert shot.get('aitype') == (ai or W.AI_TYPE[kind])


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
    root = two_gun_style(shots=6, others=W.STOCK_TRIGGERS - 6 - 2)    # room for two effect_sound triggers
    W.rewrite_weapon_events(root, TOYS, max_triggers=19)
    trig = [c for c in root.find('FightMove') if c.tag == 'trigger']
    assert len(trig) == W.STOCK_TRIGGERS
    fx = [c for c in trig if c.get('name') == 'effect_sound']
    assert [(c.get('time'), c.get('bolt')) for c in fx] == [('0.5', 'Bip01 L Hand'), ('0.6', 'Bip01 R Hand')]
    assert [c.get('name') for c in trig].count('left_pop') == 3   # every shot trigger kept
    full = two_gun_style(shots=4, others=W.STOCK_TRIGGERS - 4)
    rep = W.rewrite_weapon_events(full, TOYS, max_triggers=19)
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


def test_burst_sound_reclaims_a_midmove_bolton_holster_cycle():
    """issue #83: XML1 puts the fire sound on the weapon_fire EVENT, so every shot of a burst sounds; the port
    must spend triggers per shot, so a move whose shots do not fit drops a mid-move bolton holster/redraw
    cycle (the weapon stays attached) to give every shot its muzzle flash + fire sound."""
    root = ET.Element('PowerStyle')
    ET.SubElement(root, 'event', {'name': 'left_pop', 'inherit': 'weapon_fire', 'weapon': 'wp_toy_pistol',
                                  'boltselect': 'Bip01 L Hand'})
    ET.SubElement(root, 'event', {'name': 'right_pop', 'inherit': 'weapon_fire', 'weapon': 'wp_toy_pistol'})
    m = ET.SubElement(root, 'FightMove', {'name': 'power_attack', 'animenum': 'ea_power1', 'aitype': 'beam'})
    for slot in ('ebolton_weapon', 'ebolton_altweapon'):
        ET.SubElement(m, 'trigger', {'name': 'bolton', 'time': '0.08', 'boltslot': slot})
    for slot in ('ebolton_weapon', 'ebolton_altweapon'):
        ET.SubElement(m, 'trigger', {'name': 'removebolton', 'time': '0.18', 'boltslot': slot})
    ET.SubElement(m, 'trigger', {'name': 'toss', 'time': '0.2'})
    for slot in ('ebolton_weapon', 'ebolton_altweapon'):
        ET.SubElement(m, 'trigger', {'name': 'bolton', 'time': '0.45', 'boltslot': slot})
    for i in range(6):
        ET.SubElement(m, 'trigger', {'name': 'left_pop' if i % 2 == 0 else 'right_pop', 'time': f'{0.5 + i / 25:g}'})
    for slot in ('ebolton_weapon', 'ebolton_altweapon'):
        ET.SubElement(m, 'trigger', {'name': 'removebolton', 'time': '0.92', 'boltslot': slot})
    rep = W.rewrite_weapon_events(root, TOYS, max_triggers=19)
    trig = [c for c in m if c.tag == 'trigger']
    assert len(trig) <= W.MAX_TRIGGERS                     # the reclaimed slots went to the burst's sound
    assert len([c for c in trig if c.get('name') == 'effect_sound']) == 6
    assert rep['weapon_event_bolton_churn_dropped'] == 2   # one holster+redraw pair per boltslot
    assert [c.get('name') for c in trig].count('left_pop') == 3
    fx = [c for c in trig if c.get('name') == 'effect_sound']
    assert len(fx) == 6 and all(c.get('sound') == 'test/toy_bang' for c in fx)
    assert not [c for c in trig if c.get('name') == 'removebolton' and c.get('time') == '0.18']
    assert [c.get('name') for c in trig].count('removebolton') == 2   # only the move-end holster remains


def test_raised_limit_keeps_all_shots_and_authored_holster_cycles():
    root = two_gun_style(shots=10, others=7)
    m = root.find('FightMove')
    ET.SubElement(m, 'trigger', {'name': 'removebolton', 'boltslot': 'toy', 'time': '0.1'})
    ET.SubElement(m, 'trigger', {'name': 'bolton', 'boltslot': 'toy', 'time': '0.2'})
    original = [dict(c.attrib) for c in m]
    rep = W.rewrite_weapon_events(root, TOYS)
    assert W.trigger_capacity() == 64
    assert rep['weapon_event_fx_added'] == 10
    assert not rep['weapon_event_bolton_churn_dropped']
    assert len(m.findall('trigger')) == 29
    assert W.silent_shots(root) == []
    assert [dict(c.attrib) for c in m if c.get('name') != 'effect_sound'] == original
    # The raised validator catches a missing shot sound even without any holster cycle.
    m.remove(m.findall("trigger[@name='effect_sound']")[-1])
    assert W.silent_shots(root) == ['power_attack:right_pop']


def test_missing_limit_uses_stock_and_plain_weapon_burst_preserves_every_sound():
    from xml1build import fix_ini as FI
    saved = FI.LIMITS.pop('MoveTriggers')
    try:
        assert W.trigger_capacity() == 19
        root = two_gun_style(shots=10, others=7)
        rep = W.rewrite_weapon_events(root, TOYS)
        assert rep['weapon_event_fx_added'] == 2
    finally:
        FI.LIMITS['MoveTriggers'] = saved
    root = style([('burst', [{'name': 'weapon_fire', 'time': str(i/20)} for i in range(12)])])
    W.apply(root, MP5)
    assert len(root.find('FightMove').findall("trigger[@name='effect_sound']")) == 12


def test_configured_trigger_validator_counts_inherited_events_without_trimming():
    from xml1build import combat_events as CE
    root = ET.Element('PowerStyle')
    parent = ET.SubElement(root, 'FightMove', name='toy_parent')
    for i in range(64):
        ET.SubElement(parent, 'trigger', name='sound', tag=str(i))
    child = ET.SubElement(root, 'FightMove', name='toy_child', inherit='toy_parent')
    ET.SubElement(child, 'trigger', tag='0', sound='test/update')
    shared = {'sound': ('ce_sound', {'name': 'sound', 'type': 'ce_sound'})}
    assert not [f for f in CE.style_findings(root, shared) if f.kind == 'trigger_cap']
    ET.SubElement(child, 'trigger', name='sound', tag='90')
    over = [f for f in CE.style_findings(root, shared) if f.kind == 'trigger_cap']
    assert len(over) == 1 and over[0].move == 'toy_child' and over[0].name == '65'


def test_full_trigger_ini_refuses_an_existing_dll_without_the_capability():
    import tempfile
    from pathlib import Path
    from xml1build import fix_ini as FI
    with tempfile.TemporaryDirectory() as tmp:
        dll = Path(tmp) / 'dinput.dll'
        FI.check_move_trigger_dll(dll, {'Limits': {'MoveTriggers': '64'}})
        dll.write_bytes(b'toy old runtime')
        try:
            FI.check_move_trigger_dll(dll, {'Limits': {'MoveTriggers': '64'}})
        except ValueError as exc:
            assert 'MoveTriggers' in str(exc)
        else:
            raise AssertionError('old runtime accepted full-trigger output')
        FI.check_move_trigger_dll(dll, {'Limits': {}})
        dll.write_bytes('MoveTriggers'.encode('utf-16le'))
        FI.check_move_trigger_dll(dll, {'Limits': {'MoveTriggers': '64'}})


def test_sound_validation_uses_authored_weapon_bindings_not_ordinary_beams():
    root = two_gun_style(shots=4)
    ET.SubElement(root, 'event', name='toy_energy', inherit='beam', attacktype='beam')
    ET.SubElement(root.find('FightMove'), 'trigger', name='toy_energy', time='0.9')
    names = W.named_weapon_events(root)
    assert names == {'left_pop', 'right_pop'}
    W.rewrite_weapon_events(root, TOYS)
    assert W.silent_shots(root, event_names=names) == []
    m = root.find('FightMove')
    m.remove(m.findall("trigger[@name='effect_sound']")[-1])
    assert W.silent_shots(root, event_names=names) == ['power_attack:right_pop']
