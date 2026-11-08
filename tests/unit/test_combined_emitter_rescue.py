"""The two map corrections must compose without widening equivalence."""
import copy
import xml.etree.ElementTree as ET
from test_emitter_lifetime import zone
from xml1build import common as C, emitter_lifetime as E, escort_triggers as R
from lcsave import zonecompat as Z


def test_combined_emitter_and_rescue_equivalence_is_directional_and_exact():
    before = zone()
    ET.SubElement(before, 'entinst', type='rescue_trigger').append(
        ET.Element('inst', name='rescue_trigger', pos='0 0 0'))
    ET.SubElement(before, 'entity', name='rescue_trigger', classname='gameent',
                  team='none', actmatchteam='true', actontouch='true',
                  actleader='false', boxcollision='true',
                  actscript='arbiter/rescue_complete', actteamplayer='true', smartent='false')
    after = copy.deepcopy(before)
    assert E.convert(after) == 1
    assert R.convert(after, 'arbiter/a_int/arb3_1') == 1
    raw = C.encode_xmlb(before)
    assert Z.attest_equivalent('arbiter/a_int/arb3_1', raw, C.encode_xmlb(after))
    assert not Z.attest_equivalent('arbiter/a_int/arb3_1', C.encode_xmlb(after), raw)
    assert not Z.attest_equivalent('unreviewed/zone', raw, C.encode_xmlb(after))
    after.find("entity[@name='pulse']").set('damage', '999')
    assert not Z.attest_equivalent('arbiter/a_int/arb3_1', raw, C.encode_xmlb(after))
