"""Synthetic script/XML tests for boss-phase compatibility helpers; no game data."""
import xml.etree.ElementTree as ET
from xml1build import boss_phases as B


def test_phase_insert_keeps_condition_scope_and_crlf():
    text = '\r\n'.join(['if guardian_phase == 2', '     chooseMode("guardian", "shield")', 'endif', ''])
    out, n = B.insert_after_call(text, 'chooseMode', 'guardian', 'shield', ['protect("guardian", "TRUE")'])
    assert n == 1
    assert '     chooseMode("guardian", "shield")\r\n     protect("guardian", "TRUE")\r\nendif' in out
    assert '\n' not in out.replace('\r\n', '')
    assert B.insert_after_call(out, 'chooseMode', 'guardian', 'shield', ['protect("guardian", "TRUE")']) == (out, 0)


def test_phase_insert_matches_quotes_without_editing_other_actors_or_comments():
    text = '\n'.join([" chooseMode ( 'guardian', 'shield' )", 'chooseMode("decoy", "shield")',
                      '# chooseMode("guardian", "shield")'])
    out, n = B.insert_after_call(text, 'chooseMode', 'guardian', 'shield', ['protect("guardian", "TRUE")'])
    assert n == 1 and out.count('protect(') == 1
    assert 'chooseMode("decoy", "shield")' in out


def test_spawn_guard_does_not_reset_completed_phase():
    out = B.guard_before('phase = getPhase()\r\nif phase == 0\r\n     begin()\r\nendif\r\n',
                         'if phase == 0', 'phase < 4', 'startShield("guardian")')
    assert 'if phase < 4\r\n     startShield("guardian")\r\nendif\r\nif phase == 0' in out
    assert B.guard_before(out, 'if phase == 0', 'phase < 4', 'startShield("guardian")') == out
    for text in ('begin()', 'if phase == 0\nif phase == 0'):
        try: B.guard_before(text, 'if phase == 0', 'phase < 4', 'startShield("guardian")')
        except ValueError: pass
        else: raise AssertionError('ambiguous or missing source anchor must fail')


def test_floor_relocation_preserves_instance_identity_and_facing():
    root = ET.Element('world')
    ground = ET.SubElement(root, 'entinst', {'type': 'safe_floor'})
    ET.SubElement(ground, 'inst', {'name': 'arrival', 'pos': '12 34 5'})
    boss = ET.SubElement(root, 'entinst', {'type': 'guardian_spawn'})
    inst = ET.SubElement(boss, 'inst', {'name': 'guardian', 'pos': '900 0 500', 'orient': '0 0 1'})
    assert B.relocate_spawn(root, 'guardian_spawn', 'safe_floor') == 1
    assert inst.attrib == {'name': 'guardian', 'pos': '12 34 5', 'orient': '0 0 1'}
    assert B.relocate_spawn(root, 'guardian_spawn', 'safe_floor') == 0


def test_floor_relocation_rejects_missing_or_ambiguous_start():
    root = ET.Element('world')
    try: B.relocate_spawn(root, 'guardian_spawn', 'safe_floor')
    except ValueError: pass
    else: raise AssertionError('missing floor marker must fail')


def test_unrelated_scripts_and_zones_are_unchanged():
    text = 'chooseMode("guardian", "shield")\r\n'
    assert B.rewrite_script('unrelated/encounter', text) == text
    # Explicitly guard the other agent's ownership boundary.
    assert B.rewrite_script('haarp/ext/test_encounter', text) == text
    root = ET.Element('world')
    assert B.rewrite_data(root, 'maps/unrelated/test.xml') == 0


def test_shield_relay_preserves_targets_and_is_idempotent():
    root = ET.Element('world')
    relay = ET.SubElement(root, 'entity', {'name': 'barrier', 'classname': 'actionent',
        'acttargets': 'helpers', 'actcountact': '3',
        'actscript': "setPatternSequence('guardian','barrier_mode')"})
    assert B.protect_relay(root, 'barrier', 'guardian', 'barrier_mode') == 1
    assert relay.get('actscript') == "setPatternSequence('guardian','barrier_mode')" + r'\n\r' + 'setInvulnerable("guardian","TRUE")'
    assert relay.get('actcountact') == '3' and relay.get('acttargets') == 'helpers'
    assert B.protect_relay(root, 'barrier', 'guardian', 'barrier_mode') == 0



def test_entry_guard_checks_actor_before_repositioning():
    text = 'waitForSpawn()\r\nsetTarget("guardian")\r\n'
    out = B.guard_before(text, 'setTarget("guardian")', 'present == 1',
                         'moveTo("guardian","floor")', setup=('present = exists("guardian")',))
    assert 'present = exists("guardian")\r\nif present == 1\r\n     moveTo("guardian","floor")\r\nendif' in out
    assert B.guard_before(out, 'setTarget("guardian")', 'present == 1',
                          'moveTo("guardian","floor")', setup=('present = exists("guardian")',)) == out


def test_delayed_release_stays_inside_transition_and_after_wait():
    source = 'if phase == 2\n     chooseMode("guardian", "attack")\nendif\n'
    statements = ['waittimed ( 0.100 )', 'protect("guardian", "FALSE")']
    result, count = B.insert_after_call(source, 'chooseMode', 'guardian', 'attack', statements)
    assert count == 1
    assert 'chooseMode("guardian", "attack")\r\n     waittimed ( 0.100 )\r\n     protect("guardian", "FALSE")\r\nendif' in result
    assert B.insert_after_call(result, 'chooseMode', 'guardian', 'attack', statements) == (result, 0)


def test_named_floor_marker_uses_walkable_height_without_moving_party_or_second_form():
    root = ET.Element('world')
    group = ET.SubElement(root, 'entinst', type='nav')
    ET.SubElement(group, 'inst', name='other', pos='90 80 -9')
    ET.SubElement(group, 'inst', name='arena', pos='700 400 -9')
    group = ET.SubElement(root, 'entinst', type='arrival')
    start = ET.SubElement(group, 'inst', name='party', pos='10 20 50')
    group = ET.SubElement(root, 'entinst', type='guardian_spawn')
    boss = ET.SubElement(group, 'inst', name='guardian', pos='1 2 3', orient='1 0 0')
    group = ET.SubElement(root, 'entinst', type='second_spawn')
    second = ET.SubElement(group, 'inst', pos='4 5 6')
    assert B.relocate_spawn(root, 'guardian_spawn', 'nav', floor_name='arena', height_type='arrival') == 1
    assert boss.attrib == dict(name='guardian', pos='700 400 50', orient='1 0 0')
    assert start.get('pos') == '10 20 50' and second.get('pos') == '4 5 6'
    assert B.relocate_spawn(root, 'guardian_spawn', 'nav', floor_name='arena', height_type='arrival') == 0
    # Duplicates across separate groups must not be hidden by a dict keyed on type.
    duplicate = ET.SubElement(root, 'entinst', type='nav')
    ET.SubElement(duplicate, 'inst', name='arena', pos='700 400 -9')
    try: B.relocate_spawn(root, 'guardian_spawn', 'nav', floor_name='arena', height_type='arrival')
    except ValueError: pass
    else: raise AssertionError('duplicate named marker must fail')


def test_multiple_entry_statements_stay_inside_alive_guard():
    source = 'setTarget("guardian")\r\n'
    statements = ['moveTo("guardian","arena")', 'z=getZ("arrival")', 'setZ("guardian",z)']
    result = B.guard_before(source, 'setTarget("guardian")', 'present == 1', statements)
    assert 'if present == 1\r\n     ' + '\r\n     '.join(statements) + '\r\nendif' in result
    assert B.guard_before(result, 'setTarget("guardian")', 'present == 1', statements) == result


def test_deferred_core_encounter_is_not_rewritten():
    source = 'chooseMode("guardian", "attack")\r\n'
    for ref in ('mastermold/mmspawn', 'mastermold/mmpain', 'mastermold/checkcore'):
        assert B.rewrite_script(ref, source) == source
    root = ET.Element('world')
    ET.SubElement(root, 'entity', name='invented_core', team='hero')
    before = ET.tostring(root)
    assert B.rewrite_data(root, 'maps/mastermold/mastermold2') == 0
    assert ET.tostring(root) == before
