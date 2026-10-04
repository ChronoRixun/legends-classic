"""Synthetic regressions for HAARP's delayed fire-wall effect (issue #12)."""
import xml.etree.ElementTree as ET
from xml1build import x1schema as S


def wall(**changes):
    attrs = dict(name='fire_wall', classname='affectableharment',
                 firstact='1', loopfx='ambient/fire_wall', loopfxstarton='true',
                 damage='7', actrescheduledelay='0.25', actrescheduledelaymin='0.25',
                 stophero='false', stopnpcenemy='false', reactpower='extinguish')
    attrs.update(changes)
    root = ET.Element('world')
    return root, ET.SubElement(root, 'entity', attrs)


def test_haarp_wall_retains_loop_without_changing_damage_mode():
    root, entity = wall()
    before = dict(entity.attrib)
    changes = S.convert(root, 'maps/haarp/ext/haarp_ext01.eng')
    assert entity.get('firstact') == '0' and 'smartfire' not in entity.attrib
    assert {**entity.attrib, 'firstact': before['firstact']} == before
    assert changes['haarp_fire_wall_loop_start'] == 1
    assert not S.convert(root, 'maps/haarp/ext/haarp_ext01.eng')


def test_fire_wall_fix_does_not_change_unrelated_or_explicit_entities():
    for overrides, rel in [
        ({}, 'maps/invented/example.eng'),
        ({'name': 'other'}, 'maps/haarp/ext/haarp_ext01.eng'),
        ({'classname': 'physent'}, 'maps/haarp/ext/haarp_ext01.eng'),
        ({'loopfx': 'invented/other'}, 'maps/haarp/ext/haarp_ext01.eng'),
        ({'smartfire': 'false'}, 'maps/haarp/ext/haarp_ext01.eng'),
        ({'loopfxstarton': 'false'}, 'maps/haarp/ext/haarp_ext01.eng'),
        ({'firstact': '0'}, 'maps/haarp/ext/haarp_ext01.eng'),
    ]:
        root, entity = wall(**overrides)
        before = dict(entity.attrib)
        S.convert(root, rel)
        assert entity.attrib == before

def test_wall_preserves_activation_order_and_restarts_loop():
    from xml1build.fire_wall_scripts import rewrite
    lines = ['if ready == 1', '    act("fire_wall01", "fire_wall01" )',
             '    copyOriginAndAngles("fire_wall01", "fire_wall01_spot" )', 'endif']
    changed = rewrite('haarp/ext/create_firewall1', lines)
    assert changed == ['if ready == 1', '    setInvisible("fire_wall01", "TRUE" )',
                       lines[1], lines[2], '    setInvisible("fire_wall01", "FALSE" )', 'endif']
    assert rewrite('haarp/ext/create_firewall1', changed) == changed
    assert rewrite('synthetic/unrelated', lines) == lines


def test_unexpected_wall_script_fails_instead_of_silently_remaining_broken():
    from xml1build.fire_wall_scripts import rewrite
    try:
        rewrite('haarp/ext/create_firewall1', ['act("other", "other" )'])
    except ValueError:
        pass
    else:
        raise AssertionError('unknown activation sequence accepted')

def test_move_only_wall_script_does_not_add_an_activation():
    from xml1build.fire_wall_scripts import rewrite
    lines = ['    copyOriginAndAngles("fire_wall02b", "fire_wall02b_spot" )']
    out = rewrite('haarp/ext/create_firewall1b', lines)
    assert out == ['    setInvisible("fire_wall02b", "TRUE" )', lines[0],
                   '    setInvisible("fire_wall02b", "FALSE" )']
    assert rewrite('haarp/ext/create_firewall1b', out) == out
