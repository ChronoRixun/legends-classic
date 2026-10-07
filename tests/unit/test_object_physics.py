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
# These structures preserve progression, not the original punch-versus-power boundary.
def test_structure_makes_breakable_walls_openable_and_keeps_top_immune():
    root = zone(*({'name': f'wall{v}', 'classname': 'tileent', 'structure': str(v)} for v in range(11)))
    S.convert(root, 'maps/invented/zone5.eng')
    assert [by_name(root)[f'wall{v}'].get('structure') for v in range(11)] == ['0', '0', '1', '1', '1', '1', '1', '1', '1', '1', '2']
    assert not S.physics_scale_problems(root)


def test_entity_attack_level_is_preserved_while_structure_is_converted():
    root = zone({'name': 'invented_shell', 'classname': 'projectileent', 'damagelevel': '6', 'structure': '1'},
                {'name': 'invented_wall', 'classname': 'tileent', 'structure': '10'})
    assert S.physics_scale_problems(root) == [('invented_wall', 'structure', '10')]
    S.convert(root, 'maps/invented/zone6.eng')
    assert root[0].get('damagelevel') == '6' and root[0].get('structure') == '0'
    assert root[1].get('structure') == '2'


def test_style_preserves_authored_levels_and_engine_defaults():
    root = ET.fromstring('<PowerStyle><event name="invented_strike" type="ce_atk"/>'
                         '<FightMove name="invented_combo"><trigger name="invented_strike" damagelevel="3"/>'
                         '<trigger name="invented_zero" damagelevel="0"/></FightMove></PowerStyle>')
    S.convert(root, 'data/powerstyles/ps_invented.eng')
    assert root[0].get('damagelevel') is None
    assert root[1][0].get('damagelevel') == '3'
    assert root[1][1].get('damagelevel') == '0'  # authored zero is preserved; never invented by the converter


def test_conversion_keeps_ordinary_hits_above_living_character_structure():
    # Character gate 0x4293e3 requires hit level > structure, not >= as for objects.
    # Lowering an authored/default level-one hit to zero makes a normal living
    # structure-zero enemy immune. Test the real conversion with synthetic attacks.
    root = ET.fromstring('<PowerStyle>'
                         '<event name="invented_default" type="ce_atk_punch" damage="7"/>'
                         '<event name="invented_explicit" type="ce_atk_punch" damagelevel="1" damage="9"/>'
                         '<FightMove name="invented_combo"><trigger name="punch" time="0.1"/>'
                         '<trigger name="kick" time="0.3"/></FightMove></PowerStyle>')
    S.convert(root, 'data/powerstyles/ps_invented_regression.eng')
    for attack in list(root.iter('event')) + list(root.iter('trigger')):
        assert int(attack.get('damagelevel', '1')) > 0, attack.attrib
    assert root[0].get('damage') == '7' and root[1].get('damage') == '9'


def test_conversion_preserves_projectile_character_damage_eligibility():
    root = zone({'name': 'invented_pellet', 'classname': 'projectileent', 'damagelevel': '1'})
    S.convert(root, 'data/entities/invented_projectiles.eng')
    assert int(root[0].get('damagelevel')) > 0


# ------------------------------------------------------------------------------- XML1's structure, kept for xml2-fix
def test_converted_structure_keeps_xml1s_number_beside_it():
    root = zone(*({'name': f'wall{v}', 'classname': 'tileent', 'structure': str(v)} for v in range(11)))
    changes = S.convert(root, 'maps/invented/zone7.eng')
    e = by_name(root)
    assert [e[f'wall{v}'].get(S.XML1_STRUCTURE_ATTR) for v in range(11)] == [str(v) for v in range(11)]
    assert [e[f'wall{v}'].get('structure') for v in range(11)] == ['0', '0', '1', '1', '1', '1', '1', '1', '1', '1', '2']
    assert changes['xml1structure_kept'] == 11
    assert S.break_rule_problems(root) == []


def test_xml1_structure_follows_xml1s_own_clamp_and_skips_what_is_not_a_number():
    root = zone({'name': 'over', 'classname': 'physent', 'structure': '14'},
                {'name': 'under', 'classname': 'physent', 'structure': '-3'},
                {'name': 'blank', 'classname': 'physent', 'structure': ''},
                {'name': 'token', 'classname': 'physent', 'structure': '%invented'},
                {'name': 'none', 'classname': 'physent', 'heaviness': '2'})
    stats = ET.SubElement(root, 'stats', {'name': 'invented_hero', 'structure': '4'})
    S.convert(root, 'maps/invented/zone8.eng')
    e = by_name(root)
    assert (e['over'].get('structure'), e['over'].get(S.XML1_STRUCTURE_ATTR)) == ('2', '10')
    assert (e['under'].get('structure'), e['under'].get(S.XML1_STRUCTURE_ATTR)) == ('0', '0')
    for name in ('blank', 'token', 'none'):
        assert S.XML1_STRUCTURE_ATTR not in e[name].attrib
    assert S.XML1_STRUCTURE_ATTR not in stats.attrib and stats.get('structure') == '4'   # a character's stats
    assert S.break_rule_problems(root) == []


def test_an_authored_xml1_structure_is_not_overwritten():
    root = zone({'name': 'kept', 'classname': 'physent', 'structure': '6', S.XML1_STRUCTURE_ATTR: '3'})
    S.convert(root, 'maps/invented/zone9.eng')
    assert (root[0].get('structure'), root[0].get(S.XML1_STRUCTURE_ATTR)) == ('1', '3')


def test_validator_rule_flags_pairs_the_fix_cannot_use():
    root = zone({'name': 'fine', 'classname': 'tileent', 'structure': '1', S.XML1_STRUCTURE_ATTR: '2'},
                {'name': 'bare', 'classname': 'tileent', 'structure': '1'},
                {'name': 'drift', 'classname': 'tileent', 'structure': '0', S.XML1_STRUCTURE_ATTR: '5'},
                {'name': 'wide', 'classname': 'tileent', 'structure': '2', S.XML1_STRUCTURE_ATTR: '11'},
                {'name': 'text', 'classname': 'tileent', 'structure': '1', S.XML1_STRUCTURE_ATTR: 'two'},
                {'name': 'alone', 'classname': 'tileent', S.XML1_STRUCTURE_ATTR: '2'},
                {'name': 'neither', 'classname': 'tileent'})
    assert S.break_rule_problems(root) == [('bare', '1', None), ('drift', '0', '5'), ('wide', '2', '11'),
                                           ('text', '1', 'two'), ('alone', None, '2')]


def test_an_unconverted_tree_fails_the_pairing_rule_and_a_converted_one_passes():
    root = zone({'name': 'wall', 'classname': 'tileent', 'structure': '2'},
                {'name': 'crate', 'classname': 'physent', 'structure': '0'})
    assert [p[0] for p in S.break_rule_problems(root)] == ['wall', 'crate']
    S.convert(root, 'maps/invented/zone10.eng')
    assert S.break_rule_problems(root) == []
