"""Synthetic fall-volume regressions; no game data or entity names."""
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from xml1build import common as C, x1schema as S
from xml1build.validate import Check, Validator


def fixture(**changes):
    root = ET.Element('world')
    attrs = dict(name='pit_alpha', classname='affectableharment', damage='32000',
                 damagetype='dmg_direct', actontouch='true', nocollide='true',
                 actscript='invented/hide_fallen', informai='false')
    attrs.update(changes)
    entity = ET.SubElement(root, 'entity', attrs)
    group = ET.SubElement(root, 'entinst', type='pit_alpha')
    ET.SubElement(group, 'inst', name='pit_west', pos='10 20 -80', extents='-25 -35 0 25 35 60')
    ET.SubElement(group, 'inst', name='pit_east', pos='100 200 -90', extents='-45 -55 0 45 55 70')
    return root, entity


def test_fall_volume_preserves_damage_scripts_and_each_instance():
    root, entity = fixture(boxdamage='false')
    before = dict(entity.attrib)
    instances = ET.tostring(root.find('entinst'))
    counts = S.convert(root, 'Maps/Invented/Cliff.eng')
    assert counts['fall_kill_volumes'] == 1
    assert entity.attrib == dict(before, boxcollision='true', smartent='false')
    assert ET.tostring(root.find('entinst')) == instances
    assert not S.convert(root, 'Maps/Invented/Cliff.eng')
    # The actual output writer must retain XML2's binary-search attribute order.
    encoded = C.encode_xmlb(root)
    decoded = C.decode_xmlb(encoded)
    assert not C.xmlb_attr_problems(decoded)
    assert decoded.find('entity').attrib == entity.attrib


def test_fall_volume_covers_remapped_class_and_existing_collision_flag():
    root, entity = fixture(classname='harmtargetent', boxcollision='true', smartent='true')
    counts = S.convert(root, 'maps/invented/cave.xml')
    assert counts['fall_kill_volumes'] == 1
    assert entity.get('classname') == 'affectableharment'
    assert entity.get('boxcollision') == 'true' and entity.get('smartent') == 'false'


def test_fall_volume_does_not_change_other_hazards_or_nonmap_entities():
    for changes, rel in [
        ({'damage': '12'}, 'maps/invented/cliff.eng'),
        ({'damagetype': 'dmg_fire'}, 'maps/invented/cliff.eng'),
        ({'actontouch': 'false'}, 'maps/invented/cliff.eng'),
        ({'nocollide': 'false'}, 'maps/invented/cliff.eng'),
        ({'classname': 'gameent'}, 'maps/invented/cliff.eng'),
        ({}, 'data/entities/invented.xml'),
    ]:
        root, _ = fixture(**changes)
        before = ET.tostring(root)
        assert not S.convert(root, rel)
        assert ET.tostring(root) == before


def check_fixture(folder, root, source='invented'):
    validator = Validator.__new__(Validator)
    validator._scan = None
    validator.reg = {}
    for suffix in ('.xmlb', '.engb'):
        name = 'maps/invented/cliff' + suffix
        path = folder / ('cliff' + suffix)
        path.write_bytes(C.encode_xmlb(root))
        validator.reg[name] = dict(rel=name, owner='zones', source=source)
    validator.idx = SimpleNamespace(path=lambda name: folder / Path(name).name)
    validator.is_x1_source = lambda value: value == 'invented'
    check = Check('V26', 'fall kill volumes')
    validator.fall_kill_volumes(check)
    return check


def test_fall_volume_validator_detects_each_missing_flag_once_per_twin_pair():
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        root, entity = fixture()
        bad = check_fixture(folder, root)
        assert len(bad.errors) == 1
        assert 'boxcollision=true' in bad.errors[0] and 'smartent=false' in bad.errors[0]
        assert bad.counts['volumes_checked'] == 1
        S.convert(root, 'maps/invented/cliff.eng')
        good = check_fixture(folder, root)
        assert not good.errors and good.counts['volumes_checked'] == 1
        for key, value in [('boxcollision', 'false'), ('smartent', 'true')]:
            expected = entity.get(key)
            entity.set(key, value)
            assert len(check_fixture(folder, root).errors) == 1
            entity.set(key, expected)
        entity.attrib.pop('smartent')
        assert not check_fixture(folder, root, source='native').errors


def test_deferred_volume_keeps_source_form_without_excluding_neighbor_hazards():
    from unittest.mock import patch
    # Re-enabling the conversion for a deferred room must fail this test.
    deferred = {'maps/invented/flooded': frozenset({'pit_alpha'})}
    for rel in ('maps/invented/flooded.eng', 'Maps\\Invented\\Flooded.XMLB'):
        root, entity = fixture()
        before = dict(entity.attrib)
        other = ET.SubElement(root, 'entity', dict(before, name='pit_beta'))
        with patch.object(S, 'FALL_KILL_DEFERRED', deferred, create=True):
            changes = S.convert(root, rel)
        assert entity.attrib == before
        assert other.get('boxcollision') == 'true' and other.get('smartent') == 'false'
        assert changes['fall_kill_volumes'] == 1
    root, entity = fixture()
    with patch.object(S, 'FALL_KILL_DEFERRED', deferred, create=True):
        S.convert(root, 'maps/invented/other.eng')
    assert entity.get('boxcollision') == 'true' and entity.get('smartent') == 'false'


def test_validator_reports_deferral_and_rejects_accidental_reactivation():
    from unittest.mock import patch
    deferred = {'maps/invented/cliff': frozenset({'pit_alpha'})}
    with tempfile.TemporaryDirectory() as temp, patch.object(S, 'FALL_KILL_DEFERRED', deferred, create=True):
        root, entity = fixture()
        check = check_fixture(Path(temp), root)
        assert not check.errors
        assert check.counts['volumes_deferred'] == 1
        assert len(check.allowed) == 1 and '#5' in check.allowed[0]
        for changed_flags in ({'smartent': 'false'}, {'boxcollision': 'true', 'smartent': 'false'}):
            root, entity = fixture(**changed_flags)
            check = check_fixture(Path(temp), root)
            assert len(check.errors) == 1
        # boxcollision alone is inert, and one source volume carries it itself: not a reactivation
        root, entity = fixture(boxcollision='true')
        assert not check_fixture(Path(temp), root).errors


def test_player_only_volume_gets_the_leader_gate_for_the_exact_pair_only():
    from unittest.mock import patch
    listed = {'maps/invented/gorge': frozenset({'pit_alpha'})}
    for rel in ('maps/invented/gorge.eng', 'Maps\\Invented\\Gorge.XMLB'):
        root, entity = fixture()
        before = dict(entity.attrib)
        instances = ET.tostring(root.find('entinst'))
        other = ET.SubElement(root, 'entity', dict(before, name='pit_beta'))
        with patch.object(S, 'FALL_KILL_LEADER_ONLY', listed):
            changes = S.convert(root, rel)
            assert changes['fall_kill_volumes'] == 2
            assert entity.attrib == dict(before, boxcollision='true', smartent='false', actleader='true')
            assert 'actleader' not in other.attrib
            assert other.get('boxcollision') == 'true' and other.get('smartent') == 'false'
            assert ET.tostring(root.find('entinst')) == instances
            assert not S.convert(root, rel)
        decoded = C.decode_xmlb(C.encode_xmlb(root))
        assert not C.xmlb_attr_problems(decoded)
        assert decoded.find('entity').attrib == entity.attrib
    root, entity = fixture()
    with patch.object(S, 'FALL_KILL_LEADER_ONLY', listed):
        S.convert(root, 'maps/invented/other.eng')
    assert 'actleader' not in entity.attrib and entity.get('boxcollision') == 'true'
    # an already converted volume (two flags) that becomes listed still gains the gate
    root, entity = fixture(boxcollision='true', smartent='false')
    with patch.object(S, 'FALL_KILL_LEADER_ONLY', listed):
        assert S.convert(root, 'maps/invented/gorge.eng')['fall_kill_volumes'] == 1
    assert entity.get('actleader') == 'true'


def test_player_only_registry_is_narrow_and_never_deferred():
    assert len(S.FALL_KILL_LEADER_ONLY) == 1
    for stem, names in S.FALL_KILL_LEADER_ONLY.items():
        assert stem == stem.lower() and stem.startswith('maps/') and '.' not in stem
        assert len(names) == 1
        assert not names & S.FALL_KILL_DEFERRED.get(stem, frozenset())
    assert S.FALL_KILL_LEADER_FLAGS == {'actleader': 'true'}


def test_validator_requires_the_leader_gate_on_listed_volumes_and_nowhere_else():
    from unittest.mock import patch
    listed = {'maps/invented/cliff': frozenset({'pit_alpha'})}
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        with patch.object(S, 'FALL_KILL_LEADER_ONLY', listed):
            # lethal to everyone again (the gate was lost): error
            root, entity = fixture(boxcollision='true', smartent='false')
            bad = check_fixture(folder, root)
            assert len(bad.errors) == 1 and 'actleader=true' in bad.errors[0]
            assert bad.counts['volumes_player_only'] == 1
            for wrong in ('false', 'TRUE '):
                entity.set('actleader', wrong)
                assert len(check_fixture(folder, root).errors) == 1
            root, entity = fixture()
            S.convert(root, 'maps/invented/cliff.eng')
            good = check_fixture(folder, root)
            assert not good.errors
            assert good.counts['volumes_player_only'] == 1 and good.counts['volumes_checked'] == 1
            # the gate does not excuse a missing collision flag
            entity.set('smartent', 'true')
            assert len(check_fixture(folder, root).errors) == 1
        # not listed: a gate that spread to another volume is an error; without it the volume is fine
        root, entity = fixture(boxcollision='true', smartent='false', actleader='true')
        spread = check_fixture(folder, root)
        assert len(spread.errors) == 1 and 'FALL_KILL_LEADER_ONLY' in spread.errors[0]
        assert not spread.counts.get('volumes_player_only')
        entity.attrib.pop('actleader')
        assert not check_fixture(folder, root).errors
