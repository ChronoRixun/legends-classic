"""SPEC 37 (2026-10-01 audit W10, issue #8) on made-up data - no game files:
XML1 objective attributes `required` and `updatedescription` (tools/xml1build/prepare/tables.mission_plan).
required="false" -> major="false" in the XML2 mission text (the engine's Secondary HUD list); updatedescription
is retained for the guarded xml2-fix completion-text reader (SPEC 47)."""
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from xml1build.prepare import tables as T

MISSIONS_XML = '<MISSIONS><MISSION name="one"/><MISSION name="two"/></MISSIONS>'
ONE = ('<MISSION name="one"><OBJECTIVE name="main" descname="Main" description="desc_main" '
       'updatedescription="upd_main" count="3" required="true" xp="10"/>'
       '<OBJECTIVE name="side" descname="Side" description="desc_side" '
       'updatedescription="upd_side" required="false" xp="5"/></MISSION>')
TWO = ('<MISSION name="two"><OBJECTIVE name="plain" descname="Plain" description="desc_plain" xp="0"/>'
       '</MISSION>')


def mission_plan():
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    mdir = root / 'data' / 'missions'
    mdir.mkdir(parents=True)
    (mdir / 'missions.xml').write_text(MISSIONS_XML, encoding='latin-1')
    (mdir / 'one.eng').write_text(ONE, encoding='latin-1')
    (mdir / 'two.eng').write_text(TWO, encoding='latin-1')
    loose = root / 'loose'
    loose.mkdir()
    plan, texts = T.mission_plan(root, loose)
    tmp.cleanup()
    return plan, texts


def act_objectives(texts):
    root = ET.fromstring(texts['x1_act01.xml'])
    return {o.get('name'): o for o in root.iter('OBJECTIVE')}


def test_required_false_becomes_major_false_and_other_attrs_hold():
    _plan, texts = mission_plan()
    objs = act_objectives(texts)
    assert objs['main'].get('major') == 'true'                    # required="true" stays primary
    assert objs['side'].get('major') == 'false'                   # required="false" -> the Secondary HUD list
    assert objs['plain'].get('major') == 'true'                   # absent required stays primary
    assert objs['main'].get('count') == '3' and objs['main'].get('xp') == '10'
    assert objs['side'].get('description') == 'desc_side'


def test_updatedescription_is_counted_and_carried_to_the_engine():
    plan, texts = mission_plan()
    objs = act_objectives(texts)
    assert objs['main'].get('updatedescription') == 'upd_main'
    assert objs['side'].get('updatedescription') == 'upd_side'
    assert 'updatedescription' not in objs['plain'].attrib
    assert plan['objectives_with_updatedescription'] == 2
    assert plan['objectives_major_false'] == 1
    one = {o['name']: o for o in plan['missions']['one']['objectives']}
    assert one['main']['updatedescription'] == 'upd_main'       # retained without changing objective identity
    assert one['side']['updatedescription'] == 'upd_side'
    assert 'updatedescription' not in plan['missions']['two']['objectives'][0]


def test_developer_missions_gain_completion_text_without_reordering():
    from xml1build.objective_text import apply_completion_text
    plan, texts = mission_plan()
    root = ET.fromstring(texts['x1_act01.xml'])
    for o in root:
        o.attrib.pop('updatedescription', None)
    before = [(o.get('name'), dict(o.attrib)) for o in root]
    assert apply_completion_text(root, 'x1_act01', plan['missions']) == 2
    assert [(o.get('name'), {k:v for k,v in o.attrib.items() if k != 'updatedescription'}) for o in root] == before
    assert apply_completion_text(root, 'x1_act01', plan['missions']) == 0


def test_conflicting_completion_text_does_not_regroup_saved_objectives():
    from xml1build.objective_text import apply_completion_text
    plan, texts = mission_plan()
    info = dict(plan['missions']['one'])
    info['objectives'] = [dict(info['objectives'][0], updatedescription='different')]
    plan['missions']['conflicting'] = info
    try:
        apply_completion_text(ET.fromstring(texts['x1_act01.xml']), 'x1_act01', plan['missions'])
    except ValueError:
        pass
    else:
        raise AssertionError('conflicting completion text silently changed saved objective identity')
