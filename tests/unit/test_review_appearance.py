"""Invented Review labels prove native category and input contracts survive."""
import copy
import xml.etree.ElementTree as ET

from xml1build import review_appearance as R, menu_conversion as M


def native():
    root = ET.Element('MENU', type='REVIEW_PATHS_MENU', igb='synthetic',
                      desctext3='$MENU_ACCEPT Choose', desctext4='$MENU_BACK Return')
    for i in range(1, 5):
        ET.SubElement(root, 'item', name=f'option{i:02d}_text', text=f'Synthetic {i}',
                      style='SYNTHETIC', neverfocus='true')
        ET.SubElement(root, 'item', name=f'option{i:02d}_focus', type='MENU_ITEM_MODEL',
                      model='ui/models/synthetic', neverfocus='true')
    item = ET.SubElement(root, 'item', name='list', type='MENU_ITEM_LISTBOX',
                         startactive='true', up='list', down='list', left='list', right='list')
    ET.SubElement(item, 'onfocus', type='list_focus', model='ui/models/synthetic_select')
    return root


def test_review_keeps_native_tabs_and_list_routing_with_separate_prop_events():
    source = native()
    before = ET.tostring(source)
    result = R.tree(source)
    assert ET.tostring(source) == before
    assert not R.control_problems(source, result)
    for i, kind in enumerate(R.KINDS, 1):
        item = result.find(f"item[@name='option{i:02d}_text']")
        events = item.findall('onfocus')
        assert any(e.get('item') == R.PROP and e.get('model').endswith('_' + kind)
                   for e in events)
    resources = {(e.tag, e.get('filename')) for e in M.package_for(result)}
    assert ('xml', 'ui/menus/' + R.BACK) in resources
    for kind in R.KINDS:
        assert ('model', 'ui/menus/lc_review_prop_' + kind) in resources


def test_review_rejects_changed_device_tokens_and_native_list_actions():
    source = native()
    for change in ('token', 'class', 'navigation', 'category'):
        result = copy.deepcopy(R.tree(source))
        if change == 'token':
            result.set('desctext4', 'B Return')
        elif change == 'class':
            result.set('type', 'SYNTHETIC_CLASS')
        elif change == 'navigation':
            result.find("item[@name='list']").set('right', 'other')
        else:
            result.remove(result.find("item[@name='option01_text']"))
        assert R.control_problems(source, result)
