"""Keep the existing disc credits restoration safe across caller images and endings."""
import copy
from types import SimpleNamespace
import xml.etree.ElementTree as ET
from xml1build import frontend as F


def test_credits_clear_previous_picture_without_changing_native_endgame_callback():
    native = ET.fromstring('<MENU type="CREDITS_MENU" endgame="true" name="synth_ending" '
                           'igb="synth_native" image="textures/synth_previous">'
                           '<precache type="xml_resident" filename="data/synth_roll"/></MENU>')
    before = ET.tostring(native)
    ctx = SimpleNamespace(read_base_xmlb=lambda rel:copy.deepcopy(native))
    root = F.credits_menu_tree(ctx,'credits_end','synth_classic')
    assert root.get('image') == ''
    assert root.get('endgame') == 'true' and root.get('type') == 'CREDITS_MENU'
    assert root.get('name') == 'synth_ending'
    assert root.find('precache').get('filename') == 'data/synth_roll'
    assert ET.tostring(native) == before
