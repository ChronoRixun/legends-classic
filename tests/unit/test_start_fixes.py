"""SPEC 41: tabled player-start moves, on invented zones built in code."""
import xml.etree.ElementTree as ET

from xml1build import start_fixes as S

TABLE = {'maps/test/hall': {'start_a': ('10 20 30', '40 50 60')}}


def zone(pos='10 20 30'):
    root = ET.Element('world')
    g = ET.SubElement(root, 'entinst', {'type': 'start_a'})
    ET.SubElement(g, 'inst', {'name': 'start_a', 'pos': pos, 'orient': '0 0 1'})
    g = ET.SubElement(root, 'entinst', {'type': 'start_b'})
    ET.SubElement(g, 'inst', {'name': 'start_b', 'pos': '1 2 3'})
    return root


def test_moves_only_the_tabled_start_and_keeps_facing():
    root = zone()
    assert S.fix_player_starts(root, 'maps/test/hall.eng', TABLE) == 1
    a, b = [i for g in root.iter('entinst') for i in g]
    assert a.attrib == {'name': 'start_a', 'pos': '40 50 60', 'orient': '0 0 1'} and b.get('pos') == '1 2 3'
    assert S.fix_player_starts(root, 'maps/test/hall.eng', TABLE) == 0          # idempotent
    assert S.fix_player_starts(zone(), 'maps/test/other.eng', TABLE) == 0       # other zones untouched


def test_fails_closed_on_a_different_source():
    for root in (zone('11 20 30'), ET.Element('world')):
        try:
            S.fix_player_starts(root, 'maps/test/hall.engb', TABLE)
        except ValueError:
            pass
        else:
            raise AssertionError('an unexpected position or a missing start must fail')


def test_the_shipped_table_names_its_tested_spot():
    expected, tested = S.START_FIXES['maps/mansion/man8/subbasement8']['player_start01']
    assert len(expected.split()) == 3 and len(tested.split()) == 3 and expected != tested
