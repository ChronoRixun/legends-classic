import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from xml1build import fix_ini as F
from xml1build import turrets as TU
import harness


class FakeValues:  # 40 x binary32 0.7 truncates to 27, x 1.3 to 51
    """invented value table: code -> minimum"""
    table = {'Q7': ('40', '50')}

    def resolve(self, code):
        if code not in self.table:
            raise KeyError(code)
        return ' '.join(v for v in self.table[code] if v)


def _zone():
    root = ET.Element('world')
    g = ET.SubElement(root, 'entinst', type='gizmo_turret')
    ET.SubElement(g, 'inst', name='gizmo_a', pos='10 -20 30.5', orient='0 -0.25 1.5')
    ET.SubElement(g, 'inst', name='gizmo_b', pos='40 50 60', orient='0 0 0')
    w = ET.SubElement(root, 'entinst', type='waypoint')
    ET.SubElement(w, 'inst', name='gizmo_a', pos='1 2 3')                 # same name, another type: not a turret
    ET.SubElement(root, 'entity', name='gizmo_turret', classname='physent', turretweapon='wp_fake_launcher',
                  turnrate='30', visextent='80', yawextent='70', pitchextent='0', resetdelay='2', mintime='0')
    s = ET.SubElement(root, 'entinst', type='gizmo_gun')
    ET.SubElement(s, 'inst', name='gun_z', pos='0 0 0', orient='0 0 0')
    ET.SubElement(root, 'entity', name='gizmo_gun', classname='physent', turretweapon='wp_fake_gun')
    return root


WEAPONS = {'wp_fake_launcher': {'type': 'projectile', 'recoiltime': '4', 'count': '2', 'spread': '15',
                                'projectilespeed': '300', 'accuracy': '10', 'range': '700', 'damage': 'Q7',
                                'projectileent': 'dart_fake', 'entfile': 'fake_ents'},
           'wp_fake_gun': {'type': 'bullet', 'recoiltime': '0.5', 'range': '500', 'damage': 'Q7'}}


def test_placements_carry_authored_values_and_defaults():
    lines, skipped = TU.placements('fake/zone_q', _zone(), WEAPONS, FakeValues())
    assert [l for l, _ in lines] == [
        'fake/zone_q|gizmo_a|10,-20,30.5,0,-0.25,1.5|600,0,0,2,80,70,0,30,29|2,4,2,15,300,10,700,27,51|dart_fake|fake_ents',
        'fake/zone_q|gizmo_b|40,50,60,0,0,0|600,0,0,2,80,70,0,30,29|2,4,2,15,300,10,700,27,51|dart_fake|fake_ents']
    assert skipped == ['fake/zone_q:gun_z: bullet weapon wp_fake_gun not emitted by the controller yet']


def test_scanner_defaults_are_the_original_constructor():
    root = ET.Element('world')
    g = ET.SubElement(root, 'entinst', type='bare')
    ET.SubElement(g, 'inst', name='bare1', pos='1 2 3', orient='0 0 0')
    ET.SubElement(root, 'entity', name='bare', classname='physent', turretweapon='wp_fake_launcher')
    (line, _), = TU.placements('fake/zone_r', root, WEAPONS, FakeValues())[0]
    assert line.split('|')[3] == '600,0,0.75,10,30,45,45,20,29'


def test_unresolvable_or_unknown_weapons_are_skipped():
    root = _zone()
    weapons = {'wp_fake_launcher': dict(WEAPONS['wp_fake_launcher'], damage='ZZ9')}
    lines, skipped = TU.placements('fake/zone_q', root, weapons, FakeValues())
    assert not lines and any('does not resolve' in s for s in skipped) and any('not in XML1 weapons' in s for s in skipped)


def test_contract_validation():
    lines, _ = TU.placements('fake/zone_q', _zone(), WEAPONS, FakeValues())
    good = {'revision': 1, 'placements': [l for l, _ in lines]}
    assert TU.validate_contract(good) == []
    assert TU.validate_contract({'revision': 2, 'placements': []})
    assert TU.validate_contract(dict(good, placements=good['placements'] * 2))      # duplicates
    assert TU.validate_contract(dict(good, placements=['fake|x;y|1|2|3|4|5']))
    assert TU.validate_contract(dict(good, placements=good['placements'][:1] * 1 + ['a/b|c|1,2|1|1|p|f']))


def test_ini_keys_need_a_valid_contract_and_port_identity():
    lines, _ = TU.placements('fake/zone_q', _zone(), WEAPONS, FakeValues())
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp)
        assert F.build_turrets(out) == {}
        (out / '_build').mkdir()
        meta = out / '_build/turrets.json'
        meta.write_text(json.dumps({'revision': 1, 'placements': [l for l, _ in lines]}))
        keys = F.build_turrets(out)
        assert keys['Game'] == {'Xml1Turrets': '1'}
        assert keys['Xml1Turrets']['Count'] == '2' and keys['Xml1Turrets']['T2'] == lines[1][0]
        meta.write_text(json.dumps({'revision': 1, 'placements': []}))
        assert F.build_turrets(out) == {}
        meta.write_text(json.dumps({'revision': 9, 'placements': [l for l, _ in lines]}))
        assert F.build_turrets(out) == {}
    keys = {'Game': {'Xml1Turrets': '1'}, 'Xml1Turrets': {'Count': '1', 'T1': lines[0][0]}}
    text = harness.ini_text('windowed', 1280, 720, True, port_identity=True, turrets=keys)
    assert 'Xml1Turrets=1' in text and '[Xml1Turrets]' in text and f'T1={lines[0][0]}' in text
    assert 'Xml1Turrets' not in harness.ini_text('windowed', 1280, 720, True, turrets=keys)
    # every key the port may write is port-owned (dropped again when a build no longer has turrets)
    assert 'Xml1Turrets' in F.PORT_OWNED['Game'] and 'T32' in F.PORT_OWNED['Xml1Turrets']
