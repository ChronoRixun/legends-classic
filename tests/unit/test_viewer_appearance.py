"""Invented viewer tokens retain native paging and return ownership."""
import xml.etree.ElementTree as ET
from xml1build import viewer_appearance as V


def test_viewer_skin_keeps_device_tokens_paging_and_return_attributes():
    native = ET.fromstring('<MENU type="IMAGE_VIEWER_MENU" no_stack="true" anyinput="true" depth="0" '
        'desctext1="$MENU_BACK Synth return" desctext2="$MENU_PREV Synth prior" desctext3="$MENU_NEXT Synth later">'
        '<item name="desctext1"/><item name="desctext2"/><item name="desctext3"/></MENU>')
    before = ET.tostring(native)
    root = V.viewer_tree(native)
    assert not V.problems(native,root)
    assert root.get('desctext3') == '$MENU_NEXT Synth later'
    assert root.get('anyinput') == 'true' and root.get('no_stack') == 'true'
    assert ET.tostring(native) == before
    root.set('desctext1','B Synth return')
    root.set('no_stack','false')
    errors = V.problems(native,root)
    assert any('prompt/text contract' in error for error in errors)
    assert any('paging/return contract' in error for error in errors)
