"""Synthetic regressions for XML1 object physics on XMen2.exe's scales (issue #51): lifting."""
import xml.etree.ElementTree as ET

from xml1build import x1schema as S


def zone(*entities):
    root = ET.Element('world')
    for attrs in entities:
        ET.SubElement(root, 'entity', attrs)
    return root


def by_name(root):
    return {e.get('name'): e for e in root.iter('entity')}


def test_heaviness_follows_xml1_lift_ranks():
    # XML1: anyone lifts 0-1, might rank r lifts r + 1, 5 never; XMen2.exe: might_heaviness r lifts r, 3 never
    root = zone(*({'name': f'box{v}', 'classname': 'physent', 'heaviness': str(v)} for v in range(6)))
    changes = S.convert(root, 'maps/invented/zone1.eng')
    got = {n: e.get('heaviness') for n, e in by_name(root).items()}
    assert got == {'box0': '0', 'box1': '0', 'box2': '1', 'box3': '2', 'box4': '3', 'box5': '3'}
    assert changes['heaviness_rescaled'] == 5                  # 0 is the same on both scales
    assert not S.physics_scale_problems(root)


def test_every_entity_class_but_not_character_stats():
    root = zone({'name': 'gate', 'classname': 'doorent', 'heaviness': '4'},
                {'name': 'lift', 'classname': 'moverent', 'heaviness': '3'},
                {'name': 'rock', 'classname': 'projectileent', 'heaviness': '4'})
    stats = ET.SubElement(root, 'stats', {'name': 'invented_hero', 'heaviness': '4'})
    S.convert(root, 'maps/invented/zone2.eng')
    assert {n: e.get('heaviness') for n, e in by_name(root).items()} == {'gate': '3', 'lift': '2', 'rock': '3'}
    assert stats.get('heaviness') == '4'


def test_unparsable_or_missing_heaviness_is_left_alone():
    root = zone({'name': 'a', 'classname': 'physent', 'heaviness': ''},
                {'name': 'b', 'classname': 'physent', 'heaviness': '%invented'},
                {'name': 'c', 'classname': 'physent'})
    S.convert(root, 'maps/invented/zone3.eng')
    e = by_name(root)
    assert e['a'].get('heaviness') == '' and e['b'].get('heaviness') == '%invented' and 'heaviness' not in e['c'].attrib


def test_validator_rule_flags_an_unconverted_tree():
    root = zone({'name': 'crate', 'classname': 'physent', 'heaviness': '5'},
                {'name': 'can', 'classname': 'physent', 'heaviness': '1'})
    assert S.physics_scale_problems(root) == [('crate', 'heaviness', '5')]
    S.convert(root, 'maps/invented/zone4.eng')
    assert S.physics_scale_problems(root) == []
