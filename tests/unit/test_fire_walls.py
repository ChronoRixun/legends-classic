"""Synthetic regressions for HAARP's delayed fire-wall effect (issue #12)."""
import xml.etree.ElementTree as ET
from xml1build import x1schema as S


def wall(**changes):
    attrs = dict(name='fire_wall', classname='affectableharment',
                 firstact='1', loopfx='ambient/fire_wall', loopfxstarton='true',
                 damage='7', actrescheduledelay='0.25', actrescheduledelaymin='0.25',
                 stophero='false', stopnpcenemy='false', reactpower='extinguish')
    attrs.update(changes)
    root = ET.Element('world')
    return root, ET.SubElement(root, 'entity', attrs)


def test_delayed_haarp_wall_uses_native_effect_activation():
    root, entity = wall()
    before = dict(entity.attrib)
    changes = S.convert(root, 'maps/haarp/ext/haarp_ext01.eng')
    assert entity.get('smartfire') == 'true'
    assert {k: v for k, v in entity.attrib.items() if k != 'smartfire'} == before
    assert changes['haarp_fire_wall_smartfire'] == 1
    assert not S.convert(root, 'maps/haarp/ext/haarp_ext01.eng')


def test_fire_wall_fix_does_not_change_unrelated_or_explicit_entities():
    for overrides, rel in [
        ({}, 'maps/invented/example.eng'),
        ({'name': 'other'}, 'maps/haarp/ext/haarp_ext01.eng'),
        ({'classname': 'physent'}, 'maps/haarp/ext/haarp_ext01.eng'),
        ({'loopfx': 'invented/other'}, 'maps/haarp/ext/haarp_ext01.eng'),
        ({'smartfire': 'false'}, 'maps/haarp/ext/haarp_ext01.eng'),
        ({'loopfxstarton': 'false'}, 'maps/haarp/ext/haarp_ext01.eng'),
        ({'firstact': '0'}, 'maps/haarp/ext/haarp_ext01.eng'),
    ]:
        root, entity = wall(**overrides)
        before = dict(entity.attrib)
        S.convert(root, rel)
        assert entity.attrib == before
