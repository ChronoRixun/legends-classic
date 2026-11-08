"""Synthetic NPC escort volumes; no owned maps or scripts."""
import copy
import xml.etree.ElementTree as ET
from unittest.mock import patch

from xml1build import common as C, scripts, escort_triggers as E
from lcsave import zonecompat as Z


def fixture(zone=None):
    zone = zone or next(iter(E.RESCUES))
    name, script = E.RESCUES[zone]
    root = ET.Element('world')
    ET.SubElement(root, 'entity', name='invented_world', classname='worldent')
    ET.SubElement(root, 'entity', name=name, classname='gameent', team='none',
                  actontouch='true', actteamplayer='true', actmatchteam='true',
                  actleader='false', boxcollision='true', actscript=script,
                  acttargets='invented_relay', nocollide='true')
    group = ET.SubElement(root, 'entinst', type=name)
    ET.SubElement(group, 'inst', name='invented_arrival', pos='12 34 56',
                  extents='-15 -25 0 15 25 90', orient='0 0 0')
    return root


def test_escort_triggers_allow_npc_without_changing_other_fields_or_placements():
    for zone in E.RESCUES:
        root = fixture(zone)
        before = copy.deepcopy(root)
        assert E.convert(root, 'maps/' + zone + '.eng') == 1
        before.find('entity[@classname="gameent"]').set('actteamplayer', 'false')
        assert C.encode_xmlb(root) == C.encode_xmlb(before)
        assert E.convert(root, zone) == 0
        assert E.problems(root, zone) == []


def test_escort_triggers_source_filters_fail_closed():
    for attr, value in [('team', 'hero'), ('actmatchteam', 'false'), ('actleader', 'true'),
                        ('actontouch', 'false'), ('boxcollision', 'false'),
                        ('actteamplayer', ''), ('classname', 'physent'),
                        ('actscript', 'invented/unrelated')]:
        root = fixture()
        root.find('entity[@classname="gameent"]').set(attr, value)
        before = C.encode_xmlb(root)
        try:
            E.convert(root, next(iter(E.RESCUES)))
        except ValueError:
            pass
        else:
            raise AssertionError('changed source contract must reject: ' + attr)
        assert C.encode_xmlb(root) == before


def test_escort_triggers_require_unique_definition_and_placement():
    zone = next(iter(E.RESCUES))
    for kind in ('missing_definition', 'duplicate_definition', 'missing_placement', 'duplicate_placement'):
        root = fixture(zone)
        trigger = root.find('entity[@classname="gameent"]')
        group = root.find('entinst')
        if kind == 'missing_definition': root.remove(trigger)
        elif kind == 'duplicate_definition': root.append(copy.deepcopy(trigger))
        elif kind == 'missing_placement': root.remove(group)
        else: root.append(copy.deepcopy(group))
        try:
            E.convert(root, zone)
        except ValueError:
            pass
        else:
            raise AssertionError('ambiguous source must reject: ' + kind)


def test_escort_triggers_unrelated_zones_and_entities_are_unchanged():
    root = fixture()
    before = C.encode_xmlb(root)
    assert E.convert(root, 'invented/unrelated') == 0
    assert E.problems(root, 'invented/unrelated') == []
    assert C.encode_xmlb(root) == before
    ET.SubElement(root, 'entity', name='invented_other', actteamplayer='true')
    E.convert(root, next(iter(E.RESCUES)))
    assert root.find('entity[@name="invented_other"]').get('actteamplayer') == 'true'


def test_escort_triggers_existing_false_filter_remains_unchanged():
    root = fixture()
    root.find('entity[@classname="gameent"]').set('actteamplayer', 'false')
    before = C.encode_xmlb(root)
    assert E.convert(root, next(iter(E.RESCUES))) == 0
    assert C.encode_xmlb(root) == before


def test_escort_triggers_output_validator_rejects_player_gate():
    root = fixture()
    assert E.problems(root, next(iter(E.RESCUES)))
    E.convert(root, next(iter(E.RESCUES)))
    assert not E.problems(root, next(iter(E.RESCUES)))


def test_escort_triggers_real_data_rewriter_calls_conversion(tmp_path):
    ctx = C.BuildContext(tmp_path / 'out', tmp_path / 'base')
    for zone in E.RESCUES:
        root = fixture(zone)
        with patch.object(scripts, '_inline_map', return_value={}), \
                patch.object(scripts, '_inline_end_refs', return_value={}), \
                patch.object(scripts, 'script_exists', return_value=True):
            scripts.rewrite_data_tree(ctx, root, 'maps/' + zone + '.eng')
        assert root.find('entity[@classname="gameent"]').get('actteamplayer') == 'false'


def test_escort_triggers_saved_zone_attestation_is_exact_and_directional():
    for zone in E.RESCUES:
        root = fixture(zone)
        previous = C.encode_xmlb(root)
        E.convert(root, zone)
        current = C.encode_xmlb(root)
        proof = Z.attest_equivalent(zone, previous, current)
        assert proof is not None, zone
        assert proof['fresh_aliases'] == proof['ambiguous_aliases'] == []
        assert Z.attest_equivalent(zone, current, previous) is None
        assert Z.attest_equivalent('invented/unrelated', previous, current) is None
        root.find('entity[@classname="gameent"]').set('acttargets', 'invented_other')
        assert Z.attest_equivalent(zone, previous, C.encode_xmlb(root)) is None
        root = C.decode_xmlb(current)
        root.find('entinst/inst').set('pos', '99 88 77')
        assert Z.attest_equivalent(zone, previous, C.encode_xmlb(root)) is None
