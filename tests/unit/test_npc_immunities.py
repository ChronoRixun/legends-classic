"""SPEC 30: XML1's inline NPC immunity talents as shared talents in XML2's boss_resistances form (xml1build.npc_values).
Made-up characters and talent names built in code - no game data; only the engine's affecter attribute names appear."""
import xml.etree.ElementTree as ET

from xml1build import npc_values as NV


def row(powerup, **attrs):
    a = {'powerup': powerup, 'life': '-1'}
    a.update(attrs)
    return a


def scaled(powerup, level):
    return row(powerup, affect_type='scale', level=level)


def stats_el(parent, name, level, *talents):
    """<stats> with inline <Talent><level> trees; each talent = (name, [levels]) where a level is a list of
    activepowerup attribute dicts (an empty list = an empty level, a dict = a level with just attributes)."""
    st = ET.SubElement(parent, 'stats', {'name': name, 'level': str(level)})
    for tname, levels in talents:
        t = ET.SubElement(st, 'Talent', {'name': tname, 'level': '1'})
        for lv in levels:
            if isinstance(lv, dict):
                ET.SubElement(t, 'level', lv)
                continue
            el = ET.SubElement(t, 'level')
            for p in lv:
                if '_require' in p:
                    ET.SubElement(el, 'require', p['_require'])
                else:
                    ET.SubElement(el, 'activepowerup', p)
    return st


def npcstat():
    root = ET.Element('characters')
    body_a = [scaled('def_mind_control', '0.1'), scaled('def_stun', '0'), scaled('def_knockback', '0')]
    body_a_reordered = [scaled('def_knockback', '0'), scaled('def_stun', '0'), scaled('def_mind_control', '0.1')]
    body_bc = [row('def_grab'), row('def_finisher'), scaled('def_pain', '0')]
    body_mind = [scaled('def_mind_control', '0.1')]
    stats_el(root, 'BossA1', 4, ('bossa_special', [body_a]), ('tough_skin_ref', []))
    stats_el(root, 'BossA2', 9, ('bossa_special', [body_a_reordered]))
    stats_el(root, 'BossB1', 9, ('bossb_special', [body_bc]))
    stats_el(root, 'BossC1', 10, ('bossc_special', [body_bc]))
    stats_el(root, 'BossC3', 20, ('bossc_special', [body_bc]))
    stats_el(root, 'SplitterA', 12, ('splitter_special', [body_mind + [row('none', func_hurt='Splitter_Hurt')]]))
    stats_el(root, 'BossD2', 14, ('zeta_special', [body_mind]))
    stats_el(root, 'BruiserB', 7, ('tough_skin', [[row('def_damage', scope_damage='dmg_physical', affect_type='scale',
                                                      level='0.5')]]))
    # not immunity bodies: two levels; a non-immunity powerup; an empty level; a timed powerup
    stats_el(root, 'RobotX', 20, ('robotx_special', [[scaled('def_stun', '0')],
                                                     [scaled('def_stun', '0'), row('def_reflect_pain')]]))
    stats_el(root, 'MindA', 30, ('minda_fighting', [[{'_require': {'cat': 'level', 'level': '1'}},
                                                     row('special', damagetype='dmg_mental', level='L1',
                                                         scope_damage='dmg_physical')]]),
             ('minda_xtreme', [{'description': 'STORM OF THOUGHT'}]))
    stats_el(root, 'Wisp', 3, ('wisp_spawn', [[row('def_stun', affect_type='scale', level='0', life='5')]]))
    return root


def definition(name, affecters):
    """a shared-talent definition in XML2's boss_resistances form, built in code."""
    t = ET.Element('talent', {'name': name})
    pw = ET.SubElement(ET.SubElement(t, 'level'), 'powerup', {'life': '-1'})
    for a in affecters:
        ET.SubElement(pw, 'affecter', a)
    return t


ENGINE_FORM = definition('test_resistances', [
    {'affect_type': 'scale', 'attribute': 'def_mind_control', 'level': '0.1'},
    {'affect_type': 'scale', 'attribute': 'def_pain', 'level': '0'},
    {'attribute': 'def_grab'}, {'attribute': 'def_pickup'}, {'attribute': 'def_finisher'},
    {'affect_type': 'scale', 'attribute': 'def_stun', 'level': '0'},
    {'affect_type': 'scale', 'attribute': 'no_iceshell', 'level': '0'},
    {'affect_type': 'scale', 'attribute': 'def_knockback', 'level': '0'},
    {'attribute': 'slow_immune', 'level': '1'}])


def _talent(root, stats, name):
    st = next(s for s in root.iter('stats') if s.get('name') == stats)
    return next(t for t in st if t.get('name') == name)


def test_immunity_rows_classify_the_inline_bodies():
    root = npcstat()
    rows, losses = NV.immunity_rows(_talent(root, 'BossA1', 'bossa_special'))
    assert rows == [('def_mind_control', 'scale', '0.1', ''), ('def_stun', 'scale', '0', ''),
                    ('def_knockback', 'scale', '0', '')]
    assert losses == []
    # the same body in another order is the same key
    rows2, _ = NV.immunity_rows(_talent(root, 'BossA2', 'bossa_special'))
    assert NV.immunity_key(rows) == NV.immunity_key(rows2) and rows != rows2
    # a `none` row (an XML1 code callback) is a reported loss, not a disqualification
    rows, losses = NV.immunity_rows(_talent(root, 'SplitterA', 'splitter_special'))
    assert rows == [('def_mind_control', 'scale', '0.1', '')]
    assert losses == ['activepowerup none (func_hurt=Splitter_Hurt) dropped']
    # scope_damage rides on the row
    rows, _ = NV.immunity_rows(_talent(root, 'BruiserB', 'tough_skin'))
    assert rows == [('def_damage', 'scale', '0.5', 'dmg_physical')]
    # not immunity bodies: two levels, a non-immunity powerup, an empty level, a timed powerup
    assert NV.immunity_rows(_talent(root, 'RobotX', 'robotx_special'))[0] is None
    assert NV.immunity_rows(_talent(root, 'MindA', 'minda_fighting'))[0] is None
    assert NV.immunity_rows(_talent(root, 'MindA', 'minda_xtreme'))[0] is None
    assert NV.immunity_rows(_talent(root, 'Wisp', 'wisp_spawn'))[0] is None


def test_immunity_plan_names_one_shared_talent_per_body():
    root = npcstat()
    plan = NV.immunity_plan(root, exclude={'dr_stun', 'robotx_special'})
    canon = {b['canonical']: b for b in plan['bodies'].values()}
    # 4 bodies: A; B/C (one body, two names); mind-control-only (splitter + zeta); tough skin
    assert sorted(canon) == ['bossa_special', 'bossc_special', 'splitter_special', 'tough_skin']
    # the body shared by several names takes the name most entries used (C 2 > B 1) ...
    assert canon['bossc_special']['names'] == {'bossc_special': 2, 'bossb_special': 1}
    assert sorted(canon['bossc_special']['entries']) == ['BossB1', 'BossC1', 'BossC3']
    # ... and on a tie (one entry each) the alphabetically first name
    assert canon['splitter_special']['names'] == {'splitter_special': 1, 'zeta_special': 1}
    # every alias resolves a body key to its canonical name
    for key, b in plan['bodies'].items():
        assert plan['alias'][key] == b['canonical']
    # XML2-defined names and the non-immunity trees are skipped with a reason
    assert plan['skipped'][('RobotX', 'robotx_special')] == 'defined by XML2 shared_talents'
    assert ('MindA', 'minda_fighting') in plan['skipped']
    assert ('MindA', 'minda_xtreme') in plan['skipped']
    assert ('Wisp', 'wisp_spawn') in plan['skipped']
    assert list(plan['losses']) == [('SplitterA', 'splitter_special')]
    # a stats list instead of a tree gives the same plan
    plan2 = NV.immunity_plan(list(root.iter('stats')), exclude={'dr_stun', 'robotx_special'})
    assert plan2['alias'] == plan['alias']


def test_canonical_tie_break_is_alphabetical():
    root = npcstat()
    plan = NV.immunity_plan(root)
    canon = {b['canonical'] for b in plan['bodies'].values()}
    # splitter_special and zeta_special carry the same body on one entry each: the alphabetically first name
    assert 'splitter_special' in canon and 'zeta_special' not in canon


def test_immunity_talent_is_the_engine_form():
    x2 = ENGINE_FORM
    rows = NV.definition_rows(x2)
    assert rows is not None and NV.is_immunity_talent(x2)
    # a definition rebuilt from its rows is the definition, byte for byte
    assert ET.tostring(NV.immunity_talent('test_resistances', rows)) == ET.tostring(x2)
    root = npcstat()
    rows, _ = NV.immunity_rows(_talent(root, 'BossA1', 'bossa_special'))
    t = NV.immunity_talent('bossa_special', rows)
    assert ET.tostring(t) == ET.tostring(definition('bossa_special', [
        {'affect_type': 'scale', 'attribute': 'def_mind_control', 'level': '0.1'},
        {'affect_type': 'scale', 'attribute': 'def_stun', 'level': '0'},
        {'affect_type': 'scale', 'attribute': 'def_knockback', 'level': '0'}]))
    # round trip: the definition's rows are the body
    assert NV.immunity_key(NV.definition_rows(t)) == NV.immunity_key(rows)
    rows, _ = NV.immunity_rows(_talent(root, 'BruiserB', 'tough_skin'))
    t = NV.immunity_talent('tough_skin', rows)
    assert [a.attrib for a in t.iter('affecter')] == [{'affect_type': 'scale', 'attribute': 'def_damage',
                                                        'level': '0.5', 'scope_damage': 'dmg_physical'}]


def test_is_immunity_talent_rejects_other_shared_forms():
    # a resistance (resist_* is a resistance, not an immunity affecter)
    assert not NV.is_immunity_talent(definition('thick_hide', [{'attribute': 'resist_physical', 'level': '0.8'}]))
    # an empty definition (what characters.ensure_talent writes for unknown names)
    empty = ET.Element('talent', {'name': 'bossa_special'})
    ET.SubElement(empty, 'level')
    assert not NV.is_immunity_talent(empty)
    # a two-level definition
    two = definition('robotx_special', [{'affect_type': 'scale', 'attribute': 'def_stun', 'level': '0'}])
    ET.SubElement(ET.SubElement(ET.SubElement(two, 'level'), 'powerup', {'life': '-1'}), 'affecter',
                  {'attribute': 'def_reflect_pain'})
    assert not NV.is_immunity_talent(two)
    # a talentvalue-driven one, a class powerup
    assert not NV.is_immunity_talent(NV.energy_talent(3))
    cls = definition('x', [{'attribute': 'def_stun', 'level': '0'}])
    cls.find('level/powerup').set('class', 'add_attack')
    assert not NV.is_immunity_talent(cls)
    assert NV.is_immunity_talent(definition('dr_stun', [{'affect_type': 'scale', 'attribute': 'def_stun',
                                                         'level': '0'}]))
