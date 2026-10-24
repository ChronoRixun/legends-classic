"""Synthetic native Codex modes and input contracts, without game data."""
import copy
import xml.etree.ElementTree as ET

from xml1build import codex_appearance as K


def native():
    root = ET.Element('MENU', type='CODEX_MENU', name='synthetic',
                      desctext1='$MENU_BACK Return', desctext3='$MENU_DETAILS Read')
    ET.SubElement(root, 'items', file='codex_back', igb='synthetic_back', perspective_camera='true')
    ET.SubElement(root, 'item', name='list', type='MENU_ITEM_LISTCODEX', mode='0',
                  startactive='true', style='SYNTHETIC')
    ET.SubElement(root, 'item', name='desc', type='MENU_ITEM_TEXTBOX', mode='1', style='SYNTHETIC')
    return root


def test_codex_retains_native_list_detail_modes_and_helper_identity():
    source = native()
    before = ET.tostring(source)
    root = K.tree(source)
    assert ET.tostring(source) == before
    assert not K.control_problems(source, root)
    assert root.find('items').get('file') == 'codex_back'
    assert root.find('items').get('igb') == K.BACK
    assert root.find("item[@name='list']").get('mode') == '0'
    assert root.find("item[@name='desc']").get('mode') == '1'


def test_codex_rejects_mode_changes_missing_bio_widget_and_literal_prompts():
    source = native()
    for change in ('mode', 'widget', 'token'):
        root = copy.deepcopy(K.tree(source))
        if change == 'mode':
            root.find("item[@name='desc']").set('mode', '0')
        elif change == 'widget':
            root.remove(root.find("item[@name='desc']"))
        else:
            root.set('desctext3', 'Y Read')
        assert K.control_problems(source, root)
