"""Synthetic regressions for delayed start-on harm loops (issue #12)."""
import xml.etree.ElementTree as ET
from types import SimpleNamespace

from xml1build import x1schema as S
from xml1build.validate import Check, Validator


def hazard(**overrides):
    attrs = dict(name='invented_hazard', classname='affectableharment',
                 firstact='1.25', loopfx='invented/steam_loop', loopfxstarton='true',
                 damage='7', actrescheduledelay='0.25', actontouch='true',
                 health='2', reactpower='invented_cool', deathscript='invented/end')
    attrs.update(overrides)
    root = ET.Element('world')
    return root, ET.SubElement(root, 'entity', attrs)


def test_delayed_harm_loop_is_name_and_location_independent():
    for rel in ('maps/invented/room.eng', 'data/entities/invented.xml'):
        for cls in ('affectableharment', 'harmtargetent', 'lightningentity'):
            root, el = hazard(classname=cls)
            before = dict(el.attrib)
            changes = S.convert(root, rel)
            assert el.get('firstact') == '0'
            assert el.get('classname') == 'affectableharment'
            assert {**el.attrib, 'firstact': before['firstact'], 'classname': cls} == before
            assert changes['harm_loop_start'] == 1
            assert not S.delayed_harm_loops(root)
            assert not S.convert(root, rel)


def test_explicit_non_smart_harm_keeps_its_configuration():
    root, el = hazard(smartfire='false', loopfxstarton='TRUE', firstact=' 2e-1 ')
    S.convert(root, 'maps/invented/elsewhere.eng')
    assert el.get('firstact') == '0'
    assert el.get('smartfire') == 'false'


def test_unrelated_loops_and_authored_off_states_keep_timing():
    for overrides in (
        {'classname': 'physent'}, {'classname': 'actionent'}, {'loopfx': ''},
        {'loopfxstarton': 'false'}, {'firstact': '0'}, {'firstact': '-1'},
        {'firstact': 'not-a-number'}, {'firstact': 'nan'}, {'firstact': 'inf'},
        {'smartfire': 'true'},
    ):
        root, el = hazard(**overrides)
        before = dict(el.attrib)
        assert not S.convert(root, 'maps/invented/elsewhere.eng')
        assert el.attrib == before
    for missing in ('loopfx', 'loopfxstarton', 'firstact'):
        root, el = hazard()
        del el.attrib[missing]
        before = dict(el.attrib)
        assert not S.convert(root, 'maps/invented/elsewhere.eng')
        assert el.attrib == before


def test_validator_rejects_dead_loop_and_accepts_converted_tree():
    # Exercise the validator entry point with facts collected from decoded output,
    # including identical localized twins. No source tree or conversion counters.
    root, el = hazard()
    names = ('maps/invented/room.engb', 'maps/invented/room.xmlb')
    scan = SimpleNamespace(
        delayed_harm_loops={n: S.delayed_harm_loops(root) for n in names},
        twins={names[1]}, files={n: {'rel': n} for n in names})
    validator = object.__new__(Validator)
    validator._scan = scan
    ck = Check('V-TBD', 'harm loop startup')
    validator.harm_loop_startup(ck)
    assert len(ck.errors) == 1
    assert names[0] in ck.errors[0] and 'invented_hazard' in ck.errors[0]
    assert 'firstact' in ck.errors[0]
    S.convert(root, 'maps/invented/room.eng')
    scan.delayed_harm_loops = {n: S.delayed_harm_loops(root) for n in names}
    ck = Check('V-TBD', 'harm loop startup')
    validator.harm_loop_startup(ck)
    assert not ck.errors


def test_relocated_loop_targets_come_from_instance_definitions():
    from xml1build.fire_wall_scripts import loop_targets, rewrite_loops
    root, el = hazard(classname='harmtargetent')
    block = ET.SubElement(root, 'entinst', type=el.get('name').upper())
    ET.SubElement(block, 'inst', name='invented_instance')
    targets = loop_targets(root)
    assert targets == {'invented_instance': {True}}
    lines = ['if ready == 1', '    act("invented_instance", "activator" )',
             '    copyOriginAndAngles("invented_instance", "destination" )', 'endif']
    out, count = rewrite_loops('invented/placement', lines, targets)
    assert count == 1
    assert out == [lines[0], '    setInvisible("invented_instance", "TRUE" )',
                   lines[1], lines[2], '    setInvisible("invented_instance", "FALSE" )', lines[3]]
    assert rewrite_loops('invented/placement', out, targets) == (out, 0)
    el.set('loopfxstarton', 'false')
    assert rewrite_loops('invented/placement', lines, loop_targets(root)) == (lines, 0)


def test_relocation_keeps_other_acts_and_rejects_ambiguous_names():
    from xml1build.fire_wall_scripts import rewrite_loops
    lines = ['act("different_entity", "different_entity" )',
             'copyOriginAndAngles("invented_loop", "destination" )',
             'copyOriginAndAngles("ordinary_prop", "destination" )']
    out, count = rewrite_loops('invented/placement', lines, {'invented_loop': {True}})
    assert count == 1 and out[0] == lines[0] and out[-1] == lines[-1]
    assert out[1:4] == ['setInvisible("invented_loop", "TRUE" )', lines[1],
                        'setInvisible("invented_loop", "FALSE" )']
    for states, source in [({True, False}, lines),
                           ({True}, ['setInvisible("invented_loop", "TRUE" )', lines[1]])]:
        try:
            rewrite_loops('invented/placement', source, {'invented_loop': states})
        except ValueError:
            pass
        else:
            raise AssertionError('unsafe visibility rewrite accepted')


def test_relocation_plan_keeps_names_in_their_script_namespace():
    from xml1build.fire_wall_scripts import relocation_plan
    root, el = hazard()
    block = ET.SubElement(root, 'entinst', type=el.get('name'))
    ET.SubElement(block, 'inst', name='invented_instance')
    other = ET.Element('world')
    ET.SubElement(other, 'entity', name='prop', classname='physent')
    ET.SubElement(ET.SubElement(other, 'entinst', type='prop'), 'inst', name='invented_instance')
    roots = {'maps/madeup/one.eng': root, 'maps/elsewhere/two.eng': other}
    ctx = SimpleNamespace(x1_rels=lambda prefix: sorted(roots), read_x1_xml=lambda rel: roots[rel])
    assert relocation_plan(ctx) == {'madeup': {'invented_instance': {True}},
                                    'elsewhere': {'invented_instance': {False}}}
