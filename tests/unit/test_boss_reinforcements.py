"""Synthetic lift handoffs: preserve authored timing and bound collision bypass."""
import xml.etree.ElementTree as ET
from unittest.mock import patch
from xml1build import boss_phases as B


def source():
    return '\n'.join(['spawnGuards()', 'act("lift_alpha","lift_alpha")',
                      'waittimed ( 4.500 )', 'setReactToEnemies("guard_one","TRUE")',
                      'setReactToEnemies("guard_two","TRUE")', 'waittimed ( 1.000 )',
                      'act("lift_alpha","lift_alpha")', ''])


def tree():
    root = ET.Element('world')
    group = ET.SubElement(root, 'entinst', type='arrival_type')
    for name, pos in [('wp_guard_one02', '10 20 30'), ('wp_guard_two02', '-10 20 30')]:
        ET.SubElement(group, 'inst', name=name, pos=pos, orient='0 0 1')
    ET.SubElement(root, 'entity', name='arrival_type', classname='waypointent', nocollide='true',
                  actscript="setWaypointPath('_ACTIVATOR_', ' ', 0)")
    return root


ACTORS = ('guard_one', 'guard_two')
MARKERS = frozenset('wp_' + actor + '02' for actor in ACTORS)


def test_lift_handoff_keeps_waits_and_restores_even_without_arrival():
    original = source()
    out = B.lift_handoff(original, 'lift_alpha', ACTORS)
    assert '\n' not in out.replace('\r\n', '')
    lines = out.split('\r\n')
    for actor in ACTORS:
        start = lines.index(f'setNoClip("{actor}", "TRUE" )')
        path = lines.index(f'setWaypointPath("{actor}", "{actor}", 2 )')
        stop = lines.index(f'setNoClip("{actor}", "FALSE" )')
        assert lines.index('waittimed ( 4.500 )') < start < path < lines.index('waittimed ( 1.000 )')
        assert stop > max(i for i, line in enumerate(lines) if line.startswith('act('))
    assert [line for line in lines if not line.startswith(('setNoClip(', 'setWaypointPath('))] == original.split('\n')
    assert B.lift_handoff(out, 'lift_alpha', ACTORS) == out
    assert 'setHealth' not in out and 'setNoGravity' not in out


def test_handoff_rejects_missing_duplicate_or_reordered_source_anchors():
    good = source()
    bad = [good.replace('waittimed ( 4.500 )', 'waittimed ( 9.000 )'),
           good.replace('setReactToEnemies("guard_one","TRUE")', ''),
           good.replace('setReactToEnemies("guard_one","TRUE")', 'setReactToEnemies("guard_one","TRUE")\n' * 2),
           good.replace('waittimed ( 1.000 )', ''),
           good.replace('spawnGuards()', 'act("lift_alpha","lift_alpha")')]
    for value in bad:
        try: B.lift_handoff(value, 'lift_alpha', ACTORS)
        except ValueError: pass
        else: raise AssertionError('changed lift contract must fail closed')


def test_arrival_restores_world_collision_and_keeps_stop_action_and_ordinals():
    root = tree()
    before = [dict(el.attrib) for el in root.iter('inst')]
    assert B.lift_arrivals(root, MARKERS) == 1
    definition = root.find('entity')
    assert definition.get('beeline') == 'true'
    assert definition.get('actscript') == 'setNoClip("_ACTIVATOR_", "FALSE" )' + r'\n\r' + "setWaypointPath('_ACTIVATOR_', ' ', 0)"
    assert before == [dict(el.attrib) for el in root.iter('inst')]
    assert B.lift_arrivals(root, MARKERS) == 0


def test_arrival_rejects_shared_unrelated_marker_or_changed_action():
    for change in ('extra', 'missing', 'duplicate', 'action', 'position', 'class'):
        root = tree()
        if change == 'extra': ET.SubElement(root.find('entinst'), 'inst', name='unrelated', pos='1 2 3')
        elif change == 'missing': root.find('entinst').remove(root.find('entinst/inst'))
        elif change == 'duplicate': ET.SubElement(root.find('entinst'), 'inst', name='wp_guard_one02', pos='1 2 3')
        elif change == 'action': root.find('entity').set('actscript', 'differentAction()')
        elif change == 'position': root.find('entinst/inst').set('pos', 'nan 2 3')
        else: root.find('entity').set('classname', 'physent')
        before = ET.tostring(root)
        try: B.lift_arrivals(root, MARKERS)
        except ValueError: pass
        else: raise AssertionError(change)
        assert ET.tostring(root) == before


def test_reinforcement_dispatch_and_validator_are_scoped():
    refs = {'invented/lift': ('lift_alpha', ACTORS)}
    with patch.object(B, 'TOAD_ELEVATOR_SCRIPTS', refs), patch.object(B, 'TOAD_REINFORCEMENT_ZONES', {'maps/invented/arena'}), patch.object(B, 'TOAD_WAVE_MARKERS', MARKERS):
        original = source()
        assert B.rewrite_script('other/lift', original) == original
        result = B.rewrite_script('scripts/invented/lift.py', original)
        assert result != original and B.reinforcement_script_problems(result, 'invented/lift') == []
        assert B.reinforcement_script_problems(original, 'invented/lift')
        root = tree()
        assert B.reinforcement_map_problems(root, 'maps/invented/arena.xmlb')
        assert B.rewrite_data(root, 'maps/other/arena') == 0
        assert B.rewrite_data(root, 'maps/invented/arena.xmlb') == 1
        assert B.reinforcement_map_problems(root, 'maps/invented/arena.xmlb') == []
