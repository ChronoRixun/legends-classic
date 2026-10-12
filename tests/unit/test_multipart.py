"""Issue #3: XML1 breakable parts - the fix key and the V-TBD validator (synthetic stats, invented names)."""
import xml.etree.ElementTree as ET

from xml1build import fix_ini
from xml1build.validate import Validator, Check


def test_port_owns_and_enables_multipart():
    assert 'Xml1Multipart' in fix_ini.PORT_OWNED['Game']
    assert fix_ini.game_keys()['Xml1Multipart'] == '1'
    assert 'Xml1Multipart' not in fix_ini.game_keys(xml1_opening=False)


def _stats(name, parts):
    el = ET.Element('stats', name=name)
    for p in parts:
        ET.SubElement(el, 'Multipart', p)
    return el


class _Fake:
    """Just what vtbd_multipart reads: XML1 stats (authored case) and built stats (lower-case XMLB keys)."""
    vtbd_multipart = Validator.vtbd_multipart
    MULTIPART_KEPT = Validator.MULTIPART_KEPT
    MULTIPART_PARTS_MAX = Validator.MULTIPART_PARTS_MAX
    MULTIPART_RECORDS = Validator.MULTIPART_RECORDS

    def __init__(self, x1, built):
        self._x1, self._built = x1, built

    def x1_stats(self):
        return {e.get('name').lower(): ('npcstat', e) for e in self._x1}

    def stats(self):
        return {'by_name': {e.get('name').lower(): ('npcstat', e) for e in self._built}}


ARM = {'bone': 'Bip01 R UpperArm', 'health': '50', 'effectOnDeath': 'fx/boom', 'loopEffect': 'fx/spark',
       'effectBone': 'Bip01 R UpperArm', 'linkToPower': 'powerSmash', 'hideSkin': '9901_arm'}


def _lower(d):
    return {k.lower(): v for k, v in d.items()}


def _run(x1, built):
    ck = Check('V-TBD', 'breakable parts')
    _Fake(x1, built).vtbd_multipart(ck)
    return ck


def test_kept_rows_pass_with_lowercase_keys():
    ck = _run([_stats('Robot', [ARM, ARM])], [_stats('robot', [_lower(ARM), _lower(ARM)])])
    assert not ck.errors and not ck.warnings
    assert ck.counts.get('parts') == 2


def test_dropped_attribute_and_row_are_errors():
    lost = _lower(ARM)
    del lost['linktopower']
    ck = _run([_stats('Robot', [ARM, ARM])], [_stats('robot', [lost, _lower(ARM)])])
    assert any('linktopower' in e for e in ck.errors)
    ck = _run([_stats('Robot', [ARM, ARM])], [_stats('robot', [_lower(ARM)])])
    assert any('2 XML1 Multipart rows, 1 built' in e for e in ck.errors)


def test_fifth_part_and_full_pool():
    ck = _run([_stats('Robot', [ARM] * 5)], [_stats('robot', [_lower(ARM)] * 5)])
    assert any('the first game holds 4' in e for e in ck.errors)
    many = [_stats(f'Bot{i}', [ARM]) for i in range(13)]
    ck = _run(many, [_stats(f'bot{i}', [_lower(ARM)]) for i in range(13)])
    assert any('13-record pool' in e for e in ck.errors)


def test_xml1_removable_talents_are_tagged_and_split():
    """XML1's remove="true" takes every def_damage powerup (talents included); XMen2.exe removes by tag name."""
    from xml1build.characters import tag_x1_removable_talents
    x1 = ET.fromstring('<talents><talent name="mind_shield"><level>'
                       '<activepowerup powerup="def_damage" scope_damage="dmg_mental" level="0.2"/>'
                       '<activepowerup powerup="def_mind_control" level="0.001"/></level></talent>'
                       '<talent name="quick_feet"><level><activepowerup powerup="speed" level="2"/></level></talent>'
                       '</talents>')
    x1_talents = {t.get('name'): t for t in x1.iter('talent')}

    def x2():
        return ET.fromstring('<talents><talent name="mind_shield"><level><powerup life="-1">'
                             '<affecter attribute="resist_mental" level="0.8"/>'
                             '<affecter attribute="def_mind_control" affect_type="scale" level="0.001"/>'
                             '</powerup></level></talent>'
                             '<talent name="quick_feet"><level><powerup life="-1">'
                             '<affecter attribute="resist_speed_thing" level="1"/></powerup></level></talent></talents>')
    roots = (x2(), x2())
    assert tag_x1_removable_talents(roots, x1_talents) == ['mind_shield']
    for root in roots:
        pus = root.find('talent').find('level').findall('powerup')
        assert [p.get('tag_name') for p in pus] == ['def_damage', None]
        assert [a.get('attribute') for a in pus[0]] == ['resist_mental']
        assert [a.get('attribute') for a in pus[1]] == ['def_mind_control'] and pus[1].get('life') == '-1'
        assert root.findall('talent')[1].find('level').find('powerup').get('tag_name') is None
    assert tag_x1_removable_talents(roots, x1_talents) == []      # idempotent
