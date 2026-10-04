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
    check = Check('V-TBD', 'fall kill volumes')
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
