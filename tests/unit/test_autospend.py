"""SPEC 94: XML1's automatic stat growth approximated in Data/autospend.XMLB (xml1build.autospend).

Invented fixtures only: synthetic stat_rules / AutoSpend trees built here, never game data. The synthetic templates
are generated from the fitted rules themselves (zero deviation), so the checks exercise the engine rule, the format
limits and the validator, not the real tables.
"""
import xml.etree.ElementTree as ET

from xml1build import autospend as ASP


def synthetic_stat_rules(spend=None, shift=None):
    """A stat_rules-shaped tree whose two templates grant what X1_RULES grants, rounded to whole XML1 points (port
    units / scale, cumulative rounding), one invented hero per template. `shift` = (template, stat, level): move that stat's bonus one level later."""
    root = ET.Element('STAT_RULES')
    for tmpl, cls in ASP.X1_TEMPLATES.items():
        ch = ET.SubElement(root, 'CHARACTER', {'name': tmpl})
        per_level = {}
        prev = {s: 0 for s in ASP.STATS}
        for level in range(ASP.FIRST_LEVEL, ASP.LAST_X1_LEVEL + 1):
            cum = ASP.cumulative(ASP.X1_RULES[cls], level)
            points = {s: round(cum[s] / ASP.STAT_SCALE[s]) for s in ASP.STATS}
            for s in ASP.STATS:
                per_level.setdefault(level, []).extend([s] * max(points[s] - prev[s], 0))
            prev = points
        if shift and shift[0] == tmpl:
            _, stat, lv = shift
            per_level[lv].remove(stat)
            per_level[lv + 1].append(stat)
        for level in range(ASP.FIRST_LEVEL, ASP.LAST_X1_LEVEL + 1):
            attrs = {} if level == ASP.FIRST_LEVEL else {'offset': str(level)}
            lv = ET.SubElement(ch, 'level', attrs)
            for s in per_level[level]:
                ET.SubElement(lv, 'bonus', {'cat': 'trait', 'item': s, 'level': '1'})
        for item, n in (spend or {'body': 3, 'agility': 2, 'mind': 1}).items():
            for _ in range(n):
                ET.SubElement(ch[0], 'spend', {'cat': 'trait', 'item': item, 'level': '1'})
    ET.SubElement(root, 'CHARACTER', {'name': 'Hero_A', 'template': 'bruiser'})
    ET.SubElement(root, 'CHARACTER', {'name': 'Hero_B', 'template': 'support'})
    return root


def base_autospend():
    """XML2-shaped AutoSpend with four invented classes."""
    root = ET.Element('AutoSpend')
    for n in ('alpha', 'beta', 'gamma', 'delta'):
        c = ET.SubElement(root, 'CharacterClass', {'name': n, 'body': '30', 'mind': '20', 'speed': '20',
                                                    'strength': '30'})
        ET.SubElement(c, 'bonus', {'start': '2', 'rate': '1', 'body': '1'})
    return root


def built(keep=('delta',)):
    templates, _ = ASP.x1_templates(synthetic_stat_rules())
    root = base_autospend()
    ASP.set_x1_classes(root, templates, keep)
    return root, templates


def test_engine_fire_rule():
    assert [ASP.fires(5, 5, lv) for lv in (4, 5, 9, 10, 15)] == [0, 1, 1, 2, 3]
    assert [ASP.fires(6, 0, lv) for lv in (5, 6, 7, 45)] == [0, 1, 1, 1]       # rate 0: once, at start
    rules = [(2, 2, {'body': 4}), (5, 5, {'speed': 2})]
    assert ASP.cumulative(rules, 3)['body'] == 4 and ASP.cumulative(rules, 4)['body'] == 8
    assert ASP.cumulative(rules, 10)['speed'] == 4


def test_template_parse_offsets_spend_and_heroes():
    templates, heroes = ASP.x1_templates(synthetic_stat_rules(spend={'body': 2, 'agility': 3, 'speed': 1}))
    assert heroes == {'hero_a': 'bruiser', 'hero_b': 'support'}
    assert templates['bruiser']['spend'] == {'body': 2, 'speed': 4}               # agility counts as speed
    for tmpl, cls in ASP.X1_TEMPLATES.items():
        for level in (2, 9, 40, 45):
            got = ASP.x1_cumulative(templates[tmpl], level)
            want = ASP.cumulative(ASP.X1_RULES[cls], min(level, 40))
            assert all(abs(got[s] - want[s]) <= ASP.STAT_SCALE[s] // 2 for s in ASP.STATS), (tmpl, level)


def test_x1_classes_go_first_and_unused_classes_are_dropped():
    root, _ = built(keep=('delta',))
    names = [c.get('name') for c in root.iter('CharacterClass')]
    assert names == ['x1_bruiser', 'x1_support', 'delta']
    assert len(names) <= ASP.CLASS_LIMIT


def test_kept_classes_that_cannot_fit_raise():
    templates, _ = ASP.x1_templates(synthetic_stat_rules())
    for keep in (('alpha', 'beta', 'gamma'), ('omega',)):
        try:
            ASP.set_x1_classes(base_autospend(), templates, keep)
        except ValueError:
            continue
        raise AssertionError(f'{keep}: no ValueError')


def test_set_is_idempotent():
    root, templates = built()
    assert ASP.set_x1_classes(root, templates, ('delta',)) is False


def test_good_tree_passes():
    root, templates = built()
    _, heroes = ASP.x1_templates(synthetic_stat_rules())
    assert ASP.problems(root, templates, heroes, {'hero_a': 'x1_bruiser', 'hero_b': 'x1_support'},
                        {'x1_bruiser', 'x1_support', 'delta'}) == []


def test_class_past_the_fourth_is_an_error():
    """The appended layout (XML2's four classes, then ours) never loads ours: 0x43d18d skips classes 5+."""
    templates, _ = ASP.x1_templates(synthetic_stat_rules())
    root = base_autospend()
    root.append(ASP._class_element('x1_bruiser', {}))
    root.append(ASP._class_element('x1_support', {}))
    msgs = ASP.problems(root, templates)
    assert any('loads the first 4' in m for m in msgs)
    assert any('x1_bruiser: not among the first 4' in m for m in msgs)


def test_used_class_dropped_is_an_error():
    root, templates = built(keep=('delta',))
    assert any("'gamma'" in m for m in ASP.problems(root, templates, used={'gamma'}))


def test_fifth_rule_and_tampered_rule_are_errors():
    root, templates = built()
    cls = next(c for c in root if c.get('name') == 'x1_bruiser')
    ET.SubElement(cls, 'bonus', {'start': '2', 'rate': '3', 'body': '1'})
    assert any('keeps 4' in m for m in ASP.problems(root, templates))
    root, templates = built()
    next(c for c in root if c.get('name') == 'x1_support').find('bonus').set('rate', '3')
    assert any('!= the fitted' in m for m in ASP.problems(root, templates))


def test_deviation_from_the_players_table_is_an_error():
    root, _ = built()
    templates, _ = ASP.x1_templates(synthetic_stat_rules(shift=('support', 'body', 6)))   # body 0 allowed
    assert any('body at level 6 deviates' in m for m in ASP.problems(root, templates))


def test_weights_and_hero_template_mismatch_are_errors():
    root, templates = built()
    next(c for c in root if c.get('name') == 'x1_bruiser').set('body', '99')
    _, heroes = ASP.x1_templates(synthetic_stat_rules())
    msgs = ASP.problems(root, templates, heroes, {'hero_a': 'x1_support'})
    assert any('auto-spend weights' in m for m in msgs)
    assert any('hero_a: herostat autospend' in m for m in msgs)


def test_heroes_map_onto_the_x1_classes():
    from xml1build.heroes import AUTOSPEND
    assert set(AUTOSPEND.values()) == set(ASP.X1_TEMPLATES.values())
