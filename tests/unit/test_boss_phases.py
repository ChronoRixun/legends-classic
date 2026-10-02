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
