"""Synthetic destruction links, native field precedence and saved ordinal safety."""
import copy
import xml.etree.ElementTree as ET

from xml1build import common as C, death_targets as DT, x1schema as XS, settle as SE
from xml1build import validate as V
from lcsave.binds import numbered_entities
from lcsave.zonecompat import attest


def zone():
    return ET.fromstring('''<world>
      <entinst type="hatch"><inst name="first"/><inst name="second"/></entinst>
      <entinst type="relay"><inst name="relay"/></entinst>
      <entinst type="old_gate"><inst name="old_gate"/></entinst>
      <entinst type="other"><inst name="other"/></entinst>
      <entity name="hatch" classname="doorent" actonuse="false" toggleonact="true" actcountdisable="1"/>
      <entity name="old_gate" classname="doorent" smartent="false"/>
      <entity name="other" classname="doorent"/>
      <entity name="relay" classname="actionent"/>
      <entity name="console" classname="physent" actondeath="true" acttargets="first, second relay" deathtargets="other" deathspawn="stump"/>
      <entity name="button" classname="physent" actonuse="true" acttargets="other"/>
    </world>''')


def definitions(root):
    return {e.get('name'): e for e in root.iter('entity')}


def test_destruction_pins_only_resolved_door_types_and_preserves_puzzle():
    root = zone()
    before = copy.deepcopy(root)
    assert DT.convert(root) == 1
    defs = definitions(root)
    assert defs['hatch'].get('smartent') == 'false'
    assert defs['hatch'].get(DT.MARKER) == 'true'
    assert defs['hatch'].get('actonuse') == 'false'
    assert defs['hatch'].get('toggleonact') == 'true'
    assert defs['hatch'].get('actcountdisable') == '1'
    assert defs['other'].get('smartent') is None       # use target / overwritten death list
    assert defs['relay'].get('smartent') is None       # resident by class already
    assert defs['console'].attrib == definitions(before)['console'].attrib
    assert [g.get('type') for g in root.findall('entinst')] == ['relay', 'old_gate', 'other', 'hatch']
    assert DT.problems(root) == []
    serialized = C.encode_xmlb(root)
    assert DT.convert(root) == 0
    assert C.encode_xmlb(root) == serialized


def test_explicit_death_list_and_empty_activation_fallback():
    root = zone()
    console = definitions(root)['console']
    console.set('actondeath', 'false')
    assert [e.get('name') for e in DT.door_targets(root)] == ['other']
    console.set('actondeath', 'true')
    console.set('acttargets', '')
    assert [e.get('name') for e in DT.door_targets(root)] == ['other']
    console.set('actscript', 'made/up/death')
    assert DT.door_targets(root) == []                 # actscript-only also replaces the list


def test_spawned_actor_death_targets_use_the_prefixed_activation_fields():
    root = zone()
    console = definitions(root)['console']
    console.attrib.pop('actondeath')
    console.attrib.pop('deathtargets')
    console.set('classname', 'monsterspawnerent')
    console.set('monster_deathtargets', 'SECOND')
    assert DT.convert(root) == 1
    assert definitions(root)['hatch'].get('smartent') == 'false'
    root = zone()
    console = definitions(root)['console']
    console.attrib.pop('actondeath')
    console.attrib.pop('deathtargets')
    console.set('monster_deathtargets', 'other')
    console.set('monster_actondeath', 'true')
    console.set('monster_acttargets', 'first')
    assert [e.get('name') for e in DT.door_targets(root)] == ['hatch']


def test_death_relay_graph_reaches_doors_without_looping():
    root = zone()
    defs = definitions(root)
    defs['console'].set('acttargets', 'relay')
    defs['relay'].set('acttargets', 'relay first')
    assert [e.get('name') for e in DT.door_targets(root)] == ['hatch']
    assert DT.convert(root) == 1
    assert not DT.problems(root)


def test_existing_residency_choices_keep_placements():
    for choice in ('false', 'true'):
        root = zone()
        definitions(root)['hatch'].set('smartent', choice)
        before = C.encode_xmlb(root)
        assert DT.convert(root) == 0
        assert C.encode_xmlb(root) == before
        assert DT.problems(root) == []


def test_new_doors_follow_old_numbered_prefix_and_attest():
    root = zone()
    before = C.encode_xmlb(root)
    old, errors = numbered_entities(root)
    assert not errors
    DT.convert(root)
    new, errors = numbered_entities(root)
    assert not errors
    assert [(t, n) for t, n, _ in new[:len(old)]] == [(t, n) for t, n, _ in old]
    assert [(t, n) for t, n, _ in new[len(old):]] == [('hatch', 'first'), ('hatch', 'second')]
    row = attest('made/up/zone', before, C.encode_xmlb(root))
    assert row is not None
    assert len(row['placements']) == len(old)
    assert row['fresh_aliases']


def test_validator_rejects_missing_residency_bad_marker_and_early_tail():
    root = zone()
    assert any('needs smartent=false' in p for p in DT.problems(root))
    DT.convert(root)
    definitions(root)['hatch'].set('smartent', 'true')
    assert any('needs smartent=false' in p for p in DT.problems(root))
    definitions(root)['hatch'].set('smartent', 'false')
    definitions(root)['other'].set(DT.MARKER, 'true')
    assert any('invalid destruction target marker' in p for p in DT.problems(root))
    definitions(root)['other'].attrib.pop(DT.MARKER)
    group = root.findall('entinst')[-1]
    root.remove(group)
    root.insert(0, group)
    assert any('saved ordinals shift' in p for p in DT.problems(root))


def test_existing_resident_tails_allow_only_later_promotions():
    root = zone()
    defs = definitions(root)
    defs['relay'].set('xml1settle', 'true')
    defs['old_gate'].set('xml1embeddedfloor', 'true')
    defs['old_gate'].set('xml1settle', 'true')
    defs['other'].set('xml1hazardbounds', 'true')
    # Simulate the pre-existing residency tails before the new promotion pass.
    for typ in ('relay', 'old_gate', 'other'):
        group = next(g for g in root.findall('entinst') if g.get('type') == typ)
        root.remove(group)
        root.append(group)
    DT.convert(root)
    assert SE.numbered_tail_problems(root, XS.post_settle_names(root, 'maps/made/up.eng')) == []
    assert XS.hazard_bounds_tail_problems(root) == []
    assert DT.problems(root) == []


def test_output_validator_checks_both_localized_variants():
    root = zone()
    good = copy.deepcopy(root)
    DT.convert(good)
    class Validator:
        def converted_zones(self): return ['made/up']
        def tree(self, rel): return good if rel.endswith('.xmlb') else root
    ck = V.Check('test', 'destruction')
    V.Validator.death_target_doors(Validator(), ck)
    assert ck.errors and any('made/up.engb' in e for e in ck.errors)
