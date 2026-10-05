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


# ---------------------------------------------------------------------------------------------- grabbing enemies
def _shared(value='2'):
    root = ET.Element('talents')
    t = ET.SubElement(root, 'talent', {'name': 'grab', 'hidden': 'true'})
    tvs = ET.SubElement(t, 'talentvalues')
    if value is not None:
        ET.SubElement(tvs, 'talentvalue', {'level': '1', 'name': 'grab_scale_dmg', 'value': value})
    return root


def _hero(name, *talents, playable='true'):
    st = ET.Element('stats', {'name': name, 'playable': playable} if playable else {'name': name})
    for t in talents:
        ET.SubElement(st, 'talent', {'level': '1', 'name': t})
    return st


def test_every_playable_hero_must_carry_the_grab_talent():
    from xml1build import heroes as H
    heroes = [_hero('InventedA', 'grab', 'invented_power'), _hero('InventedB', 'invented_power'),
              _hero('default', playable=None)]
    msgs = H.grab_problems(heroes, _shared())
    assert len(msgs) == 1 and msgs[0].startswith('InventedB:')


def test_the_shared_grab_talent_needs_a_positive_scale():
    from xml1build import heroes as H
    heroes = [_hero('InventedA', 'GRAB')]
    assert H.grab_problems(heroes, _shared()) == []
    for bad in (_shared('0'), _shared(None), ET.Element('talents'), None):
        assert any(m.startswith('shared_talents:') for m in H.grab_problems(heroes, bad))


# ---------------------------------------------------------------------------------------------- breaking objects
def test_structure_keeps_xml1s_punch_versus_power_boundary():
    root = zone(*({'name': f'wall{v}', 'classname': 'tileent', 'structure': str(v)} for v in range(11)))
    S.convert(root, 'maps/invented/zone5.eng')
    got = [by_name(root)[f'wall{v}'].get('structure') for v in range(11)]
    assert got == ['0', '0', '1', '1', '1', '1', '1', '1', '1', '1', '2']
    assert not S.physics_scale_problems(root)


def test_entity_damage_level_and_unconverted_structure_rule():
    root = zone({'name': 'invented_shell', 'classname': 'projectileent', 'damagelevel': '6', 'structure': '1'},
                {'name': 'invented_wall', 'classname': 'tileent', 'structure': '10'})
    assert S.physics_scale_problems(root) == [('invented_wall', 'structure', '10')]
    S.convert(root, 'maps/invented/zone6.eng')
    e = by_name(root)
    assert e['invented_shell'].get('damagelevel') == '1' and e['invented_shell'].get('structure') == '0'
    assert e['invented_wall'].get('structure') == '2'


STYLE = ('<PowerStyle>'
         '<event name="invented_slash" type="ce_atk" damage="5"/>'
         '<event name="invented_bash" type="ce_atk_punch" damagelevel="1"/>'
         '<FightMove name="combo1"><trigger name="punch" time="0.2"/><trigger name="kick" damagelevel="2" time="0.3"/>'
         '<trigger name="teleport_punch" time="0.4"/></FightMove>'
         '<FightMove name="power1"><trigger name="invented_slash" damagelevel="3" time="0.1"/>'
         '<trigger name="effect" time="0.1"/></FightMove>'
         '</PowerStyle>')


def test_style_attack_levels_punch_zero_powers_one():
    root = ET.fromstring(STYLE)
    S.convert(root, 'data/powerstyles/ps_invented.eng')
    ev = {e.get('name'): e for e in root.iter('event')}
    assert ev['invented_slash'].get('damagelevel') == '0'           # typed attack, default 1 = a punch
    assert ev['invented_bash'].get('damagelevel') == '0'
    combo = {t.get('name'): t.get('damagelevel') for t in root[2]}
    assert combo == {'punch': '0', 'kick': '1', 'teleport_punch': '1'}   # shared punch 1 -> 0, XML1 2 -> 1
    power = {t.get('name'): t.get('damagelevel') for t in root[3]}
    assert power == {'invented_slash': '1', 'effect': None}
    assert S.damage_level_problems(root) == []


def test_damage_level_rule_flags_xml1_levels_and_bare_typed_attacks():
    root = ET.fromstring(STYLE)
    probs = S.damage_level_problems(root)
    assert ('event', 'invented_slash', 'type=ce_atk without damagelevel') in probs
    assert any(p[2] == 'damagelevel=3' for p in probs) and any(p[2] == 'damagelevel=2' for p in probs)


def test_non_style_files_keep_their_attack_attributes():
    root = ET.fromstring(STYLE)
    S.convert(root, 'maps/invented/not_a_style.eng')
    assert [t.get('damagelevel') for t in root[2]] == [None, '2', None]


def test_shared_events_shipped_on_the_xml1_scale():
    from xml1build import combat_events as CE
    root = ET.fromstring('<events><event name="punch" type="ce_atk_punch" damagelevel="1"/>'
                         '<event name="punch_heavy" inherit="punch"/>'
                         '<event name="teleport_punch" type="ce_atk_post_tele_punch" damagelevel="2"/>'
                         '<event name="invented_fry" type="ce_atk"/><event name="invented_fx" type="ce_effect"/></events>')
    changes = CE.shared_events_on_x1_scale(root)
    got = {e.get('name'): e.get('damagelevel') for e in root}
    assert got == {'punch': '0', 'punch_heavy': None, 'teleport_punch': '1', 'invented_fry': '0', 'invented_fx': None}
    assert set(changes) == {'punch', 'teleport_punch', 'invented_fry'}
