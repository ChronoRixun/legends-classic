"""XML1's damage-type resistance talents on XMen2.exe (xml1build.npc_values.resist_rewrite / resist_problems).
Made-up talent names built in code - no game data; only the engine's affecter / damage-type names appear."""
import xml.etree.ElementTree as ET

from xml1build import npc_values as NV


def x1_talent(name, *rows):
    """an XML1 shared <Talent> with one <level> of activepowerup rows (attribute dicts)."""
    t = ET.Element('Talent', {'name': name, 'level': '0'})
    lv = ET.SubElement(t, 'level')
    for r in rows:
        ET.SubElement(lv, 'activepowerup', dict(r, life='-1'))
    return t


def scoped(scope, level='0.2', **extra):
    return dict({'powerup': 'def_damage', 'scope_damage': scope, 'affect_type': 'scale', 'level': level}, **extra)


def x2_talent(name, *powerups):
    """an XMen2.exe-form <talent>: each powerup = (powerup attrs, [affecter attrs], with_fx)."""
    t = ET.Element('talent', {'name': name})
    lv = ET.SubElement(t, 'level')
    for attrs, affecters, fx in powerups:
        p = ET.SubElement(lv, 'powerup', attrs)
        if fx:
            ET.SubElement(p, 'special_fx', {'effect': 'made/up/aura_loop', 'fxlevel': '1', 'how_used': 'primary'})
        for a in affecters:
            ET.SubElement(p, 'affecter', a)
    return t


def affecters(t):
    return [dict(a.attrib) for a in t.iter('affecter')]


AURA = {'life': '-1', 'remove_on_death': 'true', 'share_life': '1', 'share_radius': '120'}


def test_resist_affecter_becomes_the_xml1_scoped_def_damage_row():
    src = x1_talent('sturdy_aura', scoped('dmg_physical', effect='made/up/aura', share_radius='120', share_life='1'),
                    {'powerup': 'none', 'apply_self': 'true', 'effect': 'made/up/aura_src'})
    out = x2_talent('sturdy_aura', (AURA, [{'attribute': 'resist_physical', 'level': '0.8'}], True),
                    ({'life': '-1', 'remove_on_death': 'true'}, [], True))
    assert NV.x1_resist_rows(src) == [('dmg_physical', '0.2')]
    assert NV.resist_problems(out, src)                       # XMen2.exe's form fails the validator
    n, problems = NV.resist_rewrite(out, src)
    assert (n, problems) == (1, [])
    assert affecters(out) == [{'affect_type': 'scale', 'attribute': 'def_damage_scope', 'level': '0.2',
                               'scope_damage': 'dmg_physical'}]
    # XMen2.exe's powerup shape stays: the aura's share fields and both effects
    pw = list(out.iter('powerup'))
    assert pw[0].attrib == AURA and len(list(out.iter('special_fx'))) == 2
    assert NV.resist_problems(out, src) == []
    # idempotent
    assert NV.resist_rewrite(out, src) == (0, [])
    assert len(affecters(out)) == 1


def test_only_the_resist_affecter_of_the_scoped_type_changes():
    src = x1_talent('calm_mind', scoped('dmg_mental'),
                    {'powerup': 'def_mind_control', 'level': '0.001', 'affect_type': 'scale'})
    out = x2_talent('calm_mind', ({'life': '-1'}, [{'attribute': 'resist_mental', 'level': '0.8'},
                                                   {'affect_type': 'scale', 'attribute': 'def_mind_control',
                                                    'level': '0.001'},
                                                   {'attribute': 'resist_energy', 'level': '0.5'}], False))
    assert NV.resist_rewrite(out, src) == (1, [])
    assert affecters(out) == [
        {'affect_type': 'scale', 'attribute': 'def_damage_scope', 'level': '0.2', 'scope_damage': 'dmg_mental'},
        {'affect_type': 'scale', 'attribute': 'def_mind_control', 'level': '0.001'},
        {'attribute': 'resist_energy', 'level': '0.5'}]          # another type: not XML1's row, left alone
    assert NV.resist_problems(out, src) == []


def test_mismatched_definitions_are_reported_and_left_alone():
    src = x1_talent('stone_hide', scoped('dmg_physical'))
    # no resist affecter to take XML1's row
    bare = x2_talent('stone_hide', ({'life': '-1'}, [{'attribute': 'resist_energy', 'level': '0.8'}], False))
    n, problems = NV.resist_rewrite(bare, src)
    assert n == 0 and len(problems) == 1 and 'resist_physical' in problems[0]
    assert affecters(bare) == [{'attribute': 'resist_energy', 'level': '0.8'}]
    # a second resist of the rewritten type would scale the damage twice
    double = x2_talent('stone_hide', ({'life': '-1'}, [{'attribute': 'resist_physical', 'level': '0.8'},
                                                       {'attribute': 'resist_physical', 'level': '0.1'}], False))
    n, problems = NV.resist_rewrite(double, src)
    assert n == 1 and len(problems) == 1 and 'left beside' in problems[0]
    assert NV.resist_problems(double, src)


def test_talents_without_scoped_def_damage_rows_are_not_resistance_talents():
    unscoped = x1_talent('iron_will', {'powerup': 'def_damage', 'affect_type': 'scale', 'level': '0'})
    other_type = x1_talent('fire_coat', scoped('dmg_fire'))
    additive = x1_talent('thick_coat', {'powerup': 'def_damage', 'scope_damage': 'dmg_physical', 'level': '5'})
    out = x2_talent('any', ({'life': '-1'}, [{'attribute': 'resist_physical', 'level': '0.8'}], False))
    for src in (unscoped, other_type, additive, None):
        assert NV.x1_resist_rows(src) == []
        assert NV.resist_rewrite(out, src) == (0, [])
        assert NV.resist_problems(out, src) == []
    assert affecters(out) == [{'attribute': 'resist_physical', 'level': '0.8'}]


def test_physical_aura_points_at_the_original_effects_and_nothing_else_moves():
    """C4: physical_resistant_share plays XML1's recipient swirl and officer ripple, not XMen2.exe's aura loop."""
    src = x1_talent('physical_resistant_share',
                    scoped('dmg_physical', effect='powerups/aura_physical', share_radius='120', share_life='1'),
                    {'powerup': 'none', 'apply_self': 'true', 'effect': 'powerups/aura_physical_src'})
    out = x2_talent('physical_resistant_share', (AURA, [{'attribute': 'resist_physical', 'level': '0.8'}], True),
                    ({'life': '-1', 'remove_on_death': 'true'}, [], True))
    for f, lv in zip(out.iter('special_fx'), ('1', '2')):
        f.set('fxlevel', lv)
    assert NV.x1_aura_effects(src) == ['powerups/aura_physical', 'powerups/aura_physical_src']
    assert NV.aura_fx_problems(out, src)                      # the stock loop fails the validator
    NV.resist_rewrite(out, src)
    before = [(dict(p.attrib), [dict(a.attrib) for a in p.iter('affecter')]) for p in out.iter('powerup')]
    assert NV.aura_fx_rewrite(out, src) == (2, [])
    assert [dict(f.attrib) for f in out.iter('special_fx')] == [
        {'effect': 'powerups/aura_physical', 'how_used': 'primary'},
        {'effect': 'powerups/aura_physical_src', 'how_used': 'primary'}]
    # modifiers, radius, life and death cleanup are untouched
    assert before == [(dict(p.attrib), [dict(a.attrib) for a in p.iter('affecter')]) for p in out.iter('powerup')]
    assert NV.aura_fx_problems(out, src) == [] and NV.resist_problems(out, src) == []
    assert NV.aura_fx_rewrite(out, src) == (0, [])            # idempotent


def test_aura_effects_only_touch_the_listed_talent_and_report_a_shape_mismatch():
    src = x1_talent('sturdy_aura', scoped('dmg_physical', effect='made/up/aura'))
    out = x2_talent('sturdy_aura', (AURA, [{'attribute': 'resist_physical', 'level': '0.8'}], True))
    assert NV.aura_fx_rewrite(out, src) == (0, []) and NV.aura_fx_problems(out, src) == []
    assert next(out.iter('special_fx')).get('effect') == 'made/up/aura_loop'
    src2 = x1_talent('physical_resistant_share', scoped('dmg_physical', effect='powerups/aura_physical'))
    one = x2_talent('physical_resistant_share', (AURA, [], True), ({'life': '-1'}, [], True))
    n, problems = NV.aura_fx_rewrite(one, src2)
    assert n == 0 and len(problems) == 1 and '2 primary effects' in problems[0]
    assert NV.aura_fx_rewrite(one, None)[0] == 0
