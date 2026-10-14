"""Synthetic hazard residency and old-save ordinal regressions."""
import xml.etree.ElementTree as ET

from xml1build import x1schema as S, settle as SE
from xml1build.validate import Validator, Check
from lcsave.binds import numbered_entities


REL = 'maps/invented/yard.engb'


def add(root, name, cls='affectableharment', **attrs):
    e = ET.SubElement(root, 'entity', name=name, classname=cls, **attrs)
    g = ET.SubElement(root, 'entinst', type=name)
    ET.SubElement(g, 'inst', name=name + '_a', pos='12 24 0', extents='-4 -5 0 4 5 9')
    return e, g


def ordinals(root):
    rows, problems = numbered_entities(root)
    assert not problems
    return [(t, n) for t, n, _ in rows]


def test_new_hazards_append_after_existing_residents_without_mutating_placements():
    root = ET.Element('world')
    fire, fg = add(root, 'invented_heat', damage='3', boxdamage='true')
    ET.SubElement(fg, 'inst', name='repeated', pos='36 72 0', extents='-6 -5 0 6 5 9')
    resident, _ = add(root, 'invented_pinned', smartent='false')
    add(root, 'invented_gate', cls='gameent')
    add(root, 'invented_settled', cls='physent', smartent='false', xml1settle='true')
    before = ordinals(root)
    placements = ET.tostring(fg)
    original = dict(fire.attrib)
    resident_original = dict(resident.attrib)
    assert S.convert_hazard_bounds(root, REL) == 1
    assert ordinals(root)[:len(before)] == before
    assert ET.tostring(fg) == placements
    assert fire.attrib == dict(original, smartent='false', xml1hazardbounds='true')
    assert resident.attrib == resident_original
    assert not SE.problems(root, S.post_settle_names(root, REL))
    assert not S.hazard_bounds_problems(root, REL)
    encoded = ET.tostring(root)
    assert S.convert_hazard_bounds(root, REL) == 0
    assert ET.tostring(root) == encoded


def test_existing_fall_tails_keep_their_ordinals():
    root = ET.Element('world')
    add(root, 'invented_heat')
    add(root, 'invented_gate', cls='gameent')
    fall = dict(damage='32000', damagetype='dmg_direct', actontouch='true', nocollide='true', smartent='false')
    add(root, 'invented_old_pit', **fall)
    add(root, 'invented_prop', cls='physent', smartent='false', xml1settle='true')
    add(root, 'invented_late_pit', **fall)
    S.FALL_KILL_ENABLED_LATE['maps/invented/yard'] = frozenset({'invented_late_pit'})
    try:
        before = ordinals(root)
        S.convert_hazard_bounds(root, REL)
        assert ordinals(root)[:len(before)] == before
        assert not S.numbered_entinst_tail_problems(root, REL)
        assert not SE.problems(root, S.post_settle_names(root, REL))
        assert not S.hazard_bounds_problems(root, REL)
        # A new hazard inserted between either old tail shifts existing ordinals.
        group = root.findall('entinst')[-1]
        root.remove(group)
        root.insert(0, group)
        assert S.hazard_bounds_problems(root, REL)
    finally:
        del S.FALL_KILL_ENABLED_LATE['maps/invented/yard']


def test_exclusions_do_not_activate_deferred_falls_or_change_other_classes():
    root = ET.Element('world')
    add(root, 'invented_model', model='invented/shape')
    add(root, 'invented_streamed', smartent='true')
    add(root, 'invented_prop', cls='physent')
    add(root, 'invented_pit', damage='32000', damagetype='dmg_direct', actontouch='true', nocollide='true')
    ET.SubElement(root, 'entity', name='invented_spawn', classname='affectableharment', extent='-3 -3 -3 3 3 3')
    _, group = add(root, 'invented_no_bounds')
    group[0].attrib.pop('extents')
    before = ET.tostring(root)
    assert S.convert_hazard_bounds(root, REL) == 0
    assert ET.tostring(root) == before


def test_validator_rejects_missing_residency_and_misordered_new_hazards():
    root = ET.Element('world')
    _, group = add(root, 'invented_hazard')
    add(root, 'invented_old', cls='gameent')
    validator = Validator.__new__(Validator)
    validator.converted_zones = lambda: {'invented/yard'}
    validator.tree = lambda rel: root
    def check():
        ck = Check('V-TBD', 'hazard bounds')
        validator.hazard_bounds(ck)
        return ck.errors
    assert any('smartent=false' in e for e in check())
    S.convert_hazard_bounds(root, REL)
    assert not check()
    root.remove(group)
    root.insert(0, group)
    assert any('ordinals' in e for e in check())
