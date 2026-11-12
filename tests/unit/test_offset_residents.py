"""Props modelled away from their origin (the brig forcefield at 0 0 0): XML1 residency, save-safe append."""
import copy
import xml.etree.ElementTree as ET

from xml1build import common as C
from xml1build import death_targets as DT
from xml1build import offset_residents as RO
from xml1build import progression_relays as PR
from xml1build import settle as SE
from xml1build import x1schema as XS
from lcsave.binds import numbered_entities
from lcsave.zonecompat import attest

# A world-space forcefield: modelled where it stands (x 2212..2390, y 938..944), placed at the origin.
FIELD = (2212.0, 938.6, 0.0, 2390.5, 943.9, 79.5)
# An ordinary prop modelled around its own origin.
CRATE = (-20.0, -20.0, 0.0, 20.0, 20.0, 40.0)
BOXES = {'invented/forcefield': FIELD, 'invented/crate': CRATE}


def read_box(model):
    return BOXES[model]


def zone():
    root = ET.Element('world')
    ET.SubElement(root, 'entity', name='world')
    ET.SubElement(root, 'entity', name='old_resident', classname='physent', model='invented/crate', smartent='false')
    group = ET.SubElement(root, 'entinst', type='old_resident')
    ET.SubElement(group, 'inst', name='old_resident', pos='100 100 0')
    ET.SubElement(root, 'entity', name='field', classname='physent', model='invented/forcefield', nogravity='true',
                  material='energy', structure='2')
    group = ET.SubElement(root, 'entinst', type='field')
    ET.SubElement(group, 'inst', name='field', pos='0 0 0')
    ET.SubElement(root, 'entity', name='crate', classname='physent', model='invented/crate')
    group = ET.SubElement(root, 'entinst', type='crate')
    ET.SubElement(group, 'inst', name='crate_a', pos='500 500 0')
    ET.SubElement(group, 'inst', name='crate_b', pos='600 500 0')
    ET.SubElement(root, 'entity', name='trigger', classname='gameent', smartent='false', nocollide='true')
    group = ET.SubElement(root, 'entinst', type='trigger')
    ET.SubElement(group, 'inst', name='trigger', pos='0 0 0')
    return root


def test_origin_outside_its_model_selects_only_that_placement():
    root = zone()
    rows = RO.survey(root, read_box)
    assert [(r['name'], r['status']) for r in rows] == [('field', 'resident')]
    assert rows[0]['gap'] > 2000


def test_xml2_envelope_keeps_near_origin_props_smart():
    root = zone()
    crate = next(e for e in root.iter('entity') if e.get('name') == 'crate')
    # Modelled 64 units beside its origin is still inside XML2's own smart envelope; 65 is not.
    BOXES['invented/near'] = (64.0, -10.0, 0.0, 100.0, 10.0, 10.0)
    BOXES['invented/beyond'] = (65.0, -10.0, 0.0, 100.0, 10.0, 10.0)
    crate.set('model', 'invented/near')
    assert [r['name'] for r in RO.survey(root, read_box) if r.get('status') == 'resident'] == ['field']
    crate.set('model', 'invented/beyond')
    assert [r['name'] for r in RO.survey(root, read_box) if r.get('status') == 'resident'] == [
        'field', 'crate_a', 'crate_b']


def test_orient_and_scale_move_the_model_bounds():
    # Turned half a circle about Z the geometry lies at x -2390..-2212: still far from the origin.
    gap, world = RO.origin_gap({'pos': '0 0 0', 'orient': '0 0 3.14159265'}, FIELD)
    assert world[3] < -2200 and gap > 2000
    # Placed elsewhere the model moves with its origin: the distance is the model's own offset.
    gap2, world = RO.origin_gap({'pos': '-2300 -941 0'}, FIELD)
    assert abs(gap2 - RO.origin_gap({'pos': '0 0 0'}, FIELD)[0]) < 1e-6 and world[0] < 0 < world[3]
    # A tiny scale brings the offset geometry inside the envelope.
    gap, _ = RO.origin_gap({'pos': '0 0 0', 'scale': '0.01'}, FIELD)
    assert 0 < gap < RO.XML2_SMART_ENVELOPE


def test_explicit_smartent_other_classes_and_unreadable_models_are_kept():
    root = zone()
    field = next(e for e in root.iter('entity') if e.get('name') == 'field')
    field.set('smartent', 'true')
    assert RO.survey(root, read_box) == []
    del field.attrib['smartent']
    field.set('classname', 'gameent')                                  # numbered either way
    assert RO.survey(root, read_box) == []
    field.set('classname', 'physent')
    rows = RO.survey(root, lambda model: (_ for _ in ()).throw(ValueError('absent')))
    assert {r['status'] for r in rows} == {'unreadable_bounds'}
    assert RO.convert(root, rows) == 0


def test_conversion_appends_after_every_old_ordinal_and_is_idempotent():
    root = zone()
    before = C.encode_xmlb(root)
    old, errors = numbered_entities(root)
    assert not errors
    old = [(t, n) for t, n, _ in old]
    field_def = dict(next(e for e in root.iter('entity') if e.get('name') == 'field').attrib)
    assert RO.convert(root, RO.survey(root, read_box)) == 1
    new, errors = numbered_entities(root)
    new = [(t, n) for t, n, _ in new]
    assert not errors and new[:len(old)] == old and len(new) == len(old) + 1
    groups = root.findall('entinst')
    alias = RO.alias('field')
    assert groups[-1].get('type') == alias and [i.attrib for i in groups[-1]] == [{'name': 'field', 'pos': '0 0 0'}]
    assert 'field' not in [g.get('type') for g in groups]
    clone = next(e for e in root.iter('entity') if e.get('name') == alias)
    assert clone.get('smartent') == 'false' and clone.get(RO.MARKER) == 'true'
    assert {k: v for k, v in clone.attrib.items() if k not in ('name', 'smartent', RO.MARKER)} == {
        k: v for k, v in field_def.items() if k != 'name'}
    # the original definition stays as it was
    assert next(e for e in root.iter('entity') if e.get('name') == 'field').attrib == field_def
    assert RO.problems(root) == []
    after = C.encode_xmlb(root)
    assert RO.convert(root, RO.survey(root, read_box)) == 0 and C.encode_xmlb(root) == after
    row = attest('invented/zone', before, after)
    assert row is not None and not row['ambiguous_aliases']


def test_validator_rejects_an_old_entinst_after_the_tail_and_a_smart_copy():
    root = zone()
    RO.convert(root, RO.survey(root, read_box))
    bad = copy.deepcopy(root)
    old = next(g for g in bad.findall('entinst') if g.get('type') == 'trigger')
    bad.remove(old)
    bad.append(old)
    assert any('saved ordinals' in p for p in RO.problems(bad))
    bad = copy.deepcopy(root)
    next(e for e in bad.iter('entity') if e.get(RO.MARKER)).set('smartent', 'true')
    assert RO.problems(bad)


def test_residency_budget_defers_the_whole_zone():
    root = zone()
    group = next(g for g in root.findall('entinst') if g.get('type') == 'field')
    for n in range(RO.MAX_NEW_RESIDENTS):
        ET.SubElement(group, 'inst', name=f'field{n}', pos='0 0 0')
    rows = RO.survey(root, read_box)
    assert {r['status'] for r in rows} == {'residency_budget'}
    assert RO.convert(root, rows) == 0


def test_offset_tail_follows_existing_settle_hazard_destruction_and_progression_tails():
    root = zone()
    # older tails, as earlier releases numbered them: a settled prop, a bounded hazard, a progression relay
    ET.SubElement(root, 'entity', name='x1_settle_0', classname='physent', smartent='false', model='invented/crate',
                  **{SE.MARKER: 'true'})
    ET.SubElement(ET.SubElement(root, 'entinst', type='x1_settle_0'), 'inst', name='box', pos='9 9 9')
    ET.SubElement(root, 'entity', name='lava', classname='affectableharment', smartent='false',
                  **{XS.HAZARD_BOUNDS_MARKER: 'true'})
    ET.SubElement(ET.SubElement(root, 'entinst', type='lava'), 'inst', name='lava', pos='1 1 1', extents='-1 -1 -1 1 1 1')
    ET.SubElement(root, 'entity', name='lc_pr_poll_x', classname='actionent', smartent='false',
                  **{PR.MARKER: 'poll'})
    ET.SubElement(ET.SubElement(root, 'entinst', type='lc_pr_poll_x'), 'inst', name='lc_pr_poll_x', pos='0 0 0')
    old = [(t, n) for t, n, _ in numbered_entities(root)[0]]
    assert RO.convert(root, RO.survey(root, read_box)) == 1
    new = [(t, n) for t, n, _ in numbered_entities(root)[0]]
    assert new[:len(old)] == old and new[-1] == (RO.alias('field'), 'field')
    assert root.findall('entinst')[-1].get('type') == RO.alias('field')
    rel = 'maps/invented/zone.eng'
    assert SE.numbered_tail_problems(root, XS.post_settle_names(root, rel)) == []
    assert XS.hazard_bounds_tail_problems(root) == []
    assert XS.numbered_entinst_tail_problems(root, rel) == []
    assert not [p for p in DT.problems(root) if 'saved ordinals' in p]
    assert RO.problems(root) == []


def test_progression_validator_ignores_the_later_offset_tail():
    from test_progression_relays import world
    zone_name = 'sewers/grso/sewers3_1_1'
    root = world()
    ET.SubElement(root, 'entity', name='field', classname='physent', model='invented/forcefield')
    ET.SubElement(ET.SubElement(root, 'entinst', type='field'), 'inst', name='field', pos='0 0 0')
    assert PR.convert(root, zone_name, {}) == 1
    assert not PR.problems(root, zone_name)
    assert RO.convert(root, RO.survey(root, read_box)) == 1
    assert root.findall('entinst')[-1].get('type') == RO.alias('field')
    assert not PR.problems(root, zone_name)
    assert RO.problems(root) == []


def test_model_box_joins_render_bounds_and_collision_hull():
    from unittest.mock import patch
    import numpy as np
    hull = np.array([[[0, 0, 0], [10, 0, 0], [0, 50, 90]]], dtype=float)
    with patch('xml1build.buoys.model_bounds', return_value=(-5, 1, 2, 5, 6, 7)), \
            patch('xml1build.settle.collision_triangles', return_value=hull):
        assert RO.model_box(b'') == (-5, 0, 0, 10, 50, 90)
    with patch('xml1build.buoys.model_bounds', side_effect=ValueError('no scene')), \
            patch('xml1build.settle.collision_triangles', return_value=hull):
        assert RO.model_box(b'') == (0, 0, 0, 10, 50, 90)
    with patch('xml1build.buoys.model_bounds', side_effect=ValueError('no scene')), \
            patch('xml1build.settle.collision_triangles', side_effect=ValueError('no hull')):
        try:
            RO.model_box(b'')
        except ValueError:
            pass
        else:
            raise AssertionError('unreadable model must fail closed')


def test_zone_builder_reads_source_models_and_records_rows(tmp_path):
    from collections import Counter
    from unittest.mock import patch
    from xml1build import zones as Z
    (tmp_path / 'forcefield.igb').write_bytes(b'field')
    (tmp_path / 'crate.igb').write_bytes(b'crate')

    class Context:
        warned = []
        def x1_path(self, rel):
            return tmp_path / rel.rsplit('/', 1)[1].replace('invented', '')
        def warn(self, message):
            self.warned.append(message)
    builder = Z.Zones.__new__(Z.Zones)
    builder.ctx = Context()
    builder.counts = Counter()
    boxes = {b'field': FIELD, b'crate': CRATE}
    root, st = zone(), {}
    with patch.object(RO, 'model_box', side_effect=lambda data: boxes[data]):
        assert builder.convert_offset_residents('invented/zone', root, st) == 1
    assert [r['name'] for r in st['offset_residents']] == ['field']
    assert builder.counts['offset_residents'] == 1 and builder.counts['offset_residents_resident'] == 1
    assert root.findall('entinst')[-1].get('type') == RO.alias('field')
