"""Synthetic spawn-floor selection and saved-ordinal regressions."""
import math
import hashlib
import xml.etree.ElementTree as ET

from xml1build import settle as S
from xml1build import x1schema as XS


TRIANGLES = (((-100, -100, 0), (100, -100, 0), (100, 100, 0)),
             ((-100, -100, 0), (100, 100, 0), (-100, 100, 0)))
BOX = (-2, -2, 0, 2, 2, 10)


def fixture():
    root = ET.Element('world')
    entity = ET.SubElement(root, 'entity', name='loose_box', classname='physent', model='invented/box',
                           mass='100', heaviness='0', health='5', deathsound='invented/break')
    group = ET.SubElement(root, 'entinst', type='loose_box')
    # Instance names repeat in real maps. Identity is the two document indices.
    ET.SubElement(group, 'inst', name='repeated', pos='20 20 50', orient='0 0 0')
    ET.SubElement(group, 'inst', name='repeated', pos='40 40 0', orient='0 0 0')
    ET.SubElement(group, 'inst', name='repeated', pos='60 60 50', orient='0.5 0 0')
    ET.SubElement(root, 'entity', name='old_anchor', classname='gameent', smartent='false', nocollide='true')
    anchor = ET.SubElement(root, 'entinst', type='old_anchor')
    ET.SubElement(anchor, 'inst', name='anchor', pos='80 80 0')
    return root, entity, group


def rows(root):
    return S.survey(root, TRIANGLES, lambda model: BOX)


def test_spawn_settle_uses_triangle_surface_not_nearest_nav_height():
    slope = S.Floor((((0, 0, 0), (10, 0, 10), (0, 10, 0)),))
    assert abs(slope.below(2, 3, 20)-2) < 1e-9
    assert slope.below(20, 20, 20) is None
    assert slope.below(2, 3, -10) is None
    stacked = S.Floor(TRIANGLES + tuple(tuple((x, y, z+30) for x, y, z in t) for t in TRIANGLES))
    assert stacked.below(0, 0, 50) == 30
    assert stacked.below(0, 0, 10) == 0


def test_spawn_settle_is_per_instance_and_preserves_old_ordinals():
    root, original, group = fixture()
    attributes = dict(original.attrib)
    report = rows(root)
    assert [r['status'] for r in report] == ['settle', 'near_floor', 'tilted']
    assert S.convert(root, report) == 1
    assert original.attrib == attributes
    assert [i.get('pos') for i in group] == ['40 40 0', '60 60 50']
    groups = root.findall('entinst')
    assert [g.get('type') for g in groups[:2]] == ['loose_box', 'old_anchor']
    assert groups[-1][0].get('pos') == '20 20 50'  # no calculated placement
    assert groups[-1][0].get('name') == 'repeated'
    alias = next(e for e in root.iter('entity') if e.get(S.MARKER))
    assert alias.get('smartent') == 'false'
    assert {k: v for k, v in alias.attrib.items() if k not in ('name', 'smartent', S.MARKER)} == {
        k: v for k, v in attributes.items() if k != 'name'}
    assert S.problems(root) == []
    before = ET.tostring(root)
    assert S.convert(root, rows(root)) == 0
    assert ET.tostring(root) == before


def test_spawn_settle_defers_movable_supports_and_missing_bounds():
    root, _, _ = fixture()
    ET.SubElement(root, 'entity', name='table', classname='physent', model='invented/table', nogravity='true')
    group = ET.SubElement(root, 'entinst', type='table')
    ET.SubElement(group, 'inst', name='support', pos='20 20 20')
    assert rows(root)[0]['status'] == 'possible_prop_support'
    group[0].set('pos', '90 90 0')
    report = S.survey(root, TRIANGLES, lambda model: None if model.endswith('table') else BOX)
    assert report[0]['status'] == 'unreadable_support'
    assert S.convert(root, report) == 0


def test_spawn_settle_keeps_fixed_disabled_scripted_and_existing_residents():
    for attrs, expected in [({'nogravity': 'true'}, 'fixed'), ({'mass': '0'}, 'fixed'),
                            ({'gravitymod': '0'}, 'fixed'), ({'mass': 'nan'}, 'invalid_placement'),
                            ({'smartent': 'false'}, 'already_resident'),
                            ({'startenabled': 'false'}, 'scripted_or_disabled'),
                            ({'spawnscript': 'invented/setup'}, 'scripted_or_disabled')]:
        root, entity, _ = fixture()
        entity.attrib.update(attrs)
        before = ET.tostring(root)
        report = rows(root)
        assert report[0]['status'] == expected
        assert S.convert(root, report) == 0
        assert ET.tostring(root) == before


def test_spawn_settle_residency_budget_defers_whole_zone():
    root, _, group = fixture()
    for i in range(S.MAX_NEW_RESIDENTS):
        ET.SubElement(group, 'inst', name=f'copy{i}', pos=f'{i-30} -50 50')
    report = rows(root)
    assert sum(r['status'] == 'residency_budget' for r in report) == S.MAX_NEW_RESIDENTS+1
    assert S.convert(root, report) == 0


def test_spawn_settle_validator_detects_bad_flags_and_order():
    root, _, _ = fixture()
    S.convert(root, rows(root))
    last = root.findall('entinst')[-1]
    root.remove(last)
    root.insert(0, last)
    assert any('ordinals' in p for p in S.problems(root))
    alias = next(e for e in root.iter('entity') if e.get(S.MARKER))
    alias.set('smartent', 'true')
    assert any('resident' in p for p in S.problems(root))
    alias.set('smartent', 'false')
    alias.set('mass', '0')
    assert any('gravity-enabled' in p for p in S.problems(root))


def test_spawn_settle_can_follow_existing_fall_volume_tail():
    root, _, _ = fixture()
    ET.SubElement(root, 'entity', name='invented_drop', classname='affectableharment', damage='32000',
                  damagetype='dmg_direct', actontouch='true', nocollide='true', boxcollision='true', smartent='false')
    group = ET.SubElement(root, 'entinst', type='invented_drop')
    ET.SubElement(group, 'inst', name='drop', pos='-80 -80 -50')
    S.convert(root, rows(root))
    assert XS.numbered_entinst_tail_problems(root, 'maps/invented/test.eng') == []
    assert [g.get('type') for g in root.findall('entinst')][2] == 'invented_drop'


def test_spawn_settle_rotated_support_box_does_not_use_sphere():
    attrs = {'pos': '0 0 0', 'orient': f'{math.pi/2} 0 0', 'model': 'invented/post'}
    box, tilted = S._box(attrs, lambda model: (-1, -2, 0, 1, 2, 100))
    assert tilted and abs(box[1]+100) < 1e-9 and abs(box[4]) < 1e-9
    assert abs(box[2]+2) < 1e-9 and abs(box[5]-2) < 1e-9


def test_spawn_settle_alias_collision_is_atomic_and_group_attributes_survive():
    root, _, group = fixture()
    group.set('invented_layer', 'ordinary')
    report = rows(root)
    alias = 'x1_settle_' + hashlib.sha256(b'loose_box').hexdigest()[:16]
    collision = ET.SubElement(root, 'entity', name=alias, classname='gameent')
    before = ET.tostring(root)
    try:
        S.convert(root, report)
    except ValueError:
        pass
    else:
        raise AssertionError('alias collision was accepted')
    assert ET.tostring(root) == before
    root.remove(collision)
    assert S.convert(root, report) == 1
    assert root.findall('entinst')[-1].get('invented_layer') == 'ordinary'


def test_spawn_settle_narrow_curb_inside_footprint_is_support():
    root, _, group = fixture()
    group[0].set('pos', '20 20 0')
    group[1].set('pos', '40 40 -12')
    road = tuple(tuple((x, y, z-12) for x, y, z in t) for t in TRIANGLES)
    # This small support misses the origin and all four footprint corners.
    curb = (((18, 25, 0), (22, 25, 0), (20, 26, 0)),)
    report = S.survey(root, road+curb, lambda model: (-10, -10, 0, 10, 10, 10))
    assert report[0]['center_floor'] == -12
    assert report[0]['static_floor'] == 0
    assert report[0]['status'] == 'static_footprint_support'
    assert S.convert(root, report) == 0
