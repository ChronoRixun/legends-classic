"""SPEC 94: XML1's automatic stat growth approximated in Data/autospend.XMLB (xml1build.autospend).

Invented fixtures only: the checks run on synthetic AutoSpend trees, never on game data.
"""
import xml.etree.ElementTree as ET

from xml1build import autospend as ASP


def built_autospend():
    """A synthetic Data/autospend.XMLB: XML2's two invented classes plus the two XML1 templates."""
    root = ET.Element('AutoSpend')
    ET.SubElement(root, 'CharacterClass', {'name': 'striker', 'body': '30', 'mind': '20',
                                           'speed': '20', 'strength': '30'})
    ET.SubElement(root, 'CharacterClass', {'name': 'warden', 'body': '40', 'mind': '10',
                                           'speed': '10', 'strength': '40'})
    ASP.add_x1_classes(root)
    return root


def test_cumulative_follows_the_engine_rule():
    rules = [(2, 2, {'body': 4}), (5, 5, {'speed': 2})]
    assert ASP.cumulative(rules, 1) == {'body': 0, 'mind': 0, 'speed': 0, 'strength': 0}
    assert ASP.cumulative(rules, 2)['body'] == 4          # first fire
    assert ASP.cumulative(rules, 3)['body'] == 4          # (3-2) % 2 != 0: no fire
    assert ASP.cumulative(rules, 4)['body'] == 8          # second fire, deltas accumulate
    assert ASP.cumulative(rules, 5)['speed'] == 2
    assert ASP.cumulative(rules, 10)['speed'] == 4        # second speed fire
    assert ASP.cumulative(rules, 40)['body'] == 80        # 20 even levels x 4


def test_x1_cumulative_scales_to_port_units():
    assert ASP.x1_cumulative('x1_bruiser', 40) == {'body': 80, 'mind': 32, 'speed': 16, 'strength': 44}
    assert ASP.x1_cumulative('x1_support', 40) == {'body': 4, 'mind': 112, 'speed': 16, 'strength': 40}
    assert ASP.x1_cumulative('x1_bruiser', 1) == {'body': 0, 'mind': 0, 'speed': 0, 'strength': 0}


def test_fitted_rules_match_xml1_within_the_documented_deviation():
    for cls in ASP.X1_RULES:
        for level in range(2, 41):
            got = ASP.cumulative(ASP.X1_RULES[cls], level)
            want = ASP.x1_cumulative(cls, level)
            for stat in ASP.STATS:
                assert abs(got[stat] - want[stat]) <= ASP.X1_MAX_DEV[cls][stat], (cls, level, stat)
        got40 = ASP.cumulative(ASP.X1_RULES[cls], 40)
        want40 = ASP.x1_cumulative(cls, 40)
        for stat in ASP.STATS:
            assert abs(got40[stat] - want40[stat]) <= 5, (cls, stat)


def test_good_tree_passes():
    assert ASP.problems(built_autospend()) == []


def test_missing_class_is_an_error():
    root = built_autospend()
    for el in list(root):
        if el.get('name') == 'x1_support':
            root.remove(el)
    assert any('x1_support: class missing' in m for m in ASP.problems(root))


def test_fifth_rule_is_an_error():
    root = built_autospend()
    for el in root:
        if el.get('name') == 'x1_bruiser':
            ET.SubElement(el, 'bonus', {'start': '2', 'rate': '3', 'body': '1'})
    assert any('keeps 4' in m for m in ASP.problems(root))


def test_tampered_rule_is_an_error():
    root = built_autospend()
    for el in root:
        if el.get('name') == 'x1_bruiser':
            el.find('bonus').set('rate', '3')
    msgs = ASP.problems(root)
    assert any('!= the fitted' in m for m in msgs)


def test_tampered_rule_deviating_from_xml1_is_an_error():
    root = built_autospend()
    for el in root:
        if el.get('name') == 'x1_support':
            for b in el:
                if b.get('start') == '2':            # the +3/level mind rule
                    b.set('mind', '9')
    msgs = ASP.problems(root)
    assert any('deviates' in m for m in msgs)


def test_add_x1_classes_is_idempotent():
    root = built_autospend()
    assert ASP.add_x1_classes(root) is False
    names = [c.get('name') for c in root.iter('CharacterClass')]
    assert names.count('x1_bruiser') == 1 and names.count('x1_support') == 1


def test_heroes_map_onto_the_x1_templates():
    from xml1build.heroes import AUTOSPEND
    assert set(AUTOSPEND) == {'wolverine', 'rogue', 'colossus', 'beast', 'cyclops', 'frost', 'gambit',
                              'iceman', 'jubilee', 'magma', 'nightcrawler', 'phoenix', 'profxastral',
                              'profxgladiator', 'psylocke', 'storm'}
    assert {AUTOSPEND[h] for h in ('wolverine', 'rogue', 'colossus', 'beast')} == {'x1_bruiser'}
    assert set(AUTOSPEND.values()) == {'x1_bruiser', 'x1_support'}
