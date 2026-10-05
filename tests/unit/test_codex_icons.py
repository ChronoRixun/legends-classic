"""Synthetic regressions for the codex list's icon cells (issue #48)."""
import xml.etree.ElementTree as ET
from types import SimpleNamespace

from xml1build import frontend as F
from xml1build import validate_frontend as VF
from xml1build.validate import Check


def menu(help_text):
    root = ET.Element('MENU', {'name': 'codex', 'type': 'CODEX_MENU', 'desctext1': help_text})
    ET.SubElement(root, 'precache', {'filename': 'ui/menus/invented_back', 'type': 'model'})
    ET.SubElement(root, 'precache', {'filename': 'textures/ui/mini_convo_icons', 'type': 'texture'})
    ET.SubElement(root, 'item', {'name': 'title', 'text': help_text})
    lst = ET.SubElement(root, 'item', {'name': 'list', 'type': 'MENU_ITEM_LISTCODEX', 'mode': '0',
                                       'icons': 'textures/ui/mini_convo_icons.png', 'icons_cols': '8',
                                       'icons_rows': '8', 'style': 'STYLE_INVENTED'})
    ET.SubElement(lst, 'onfocus', {'type': 'list_focus', 'model': 'ui/models/invented_select'})
    ET.SubElement(root, 'item', {'name': 'desc', 'type': 'MENU_ITEM_TEXTBOX'})
    return root


def base_ctx(halves):
    def read(rel):
        if rel not in halves:
            raise KeyError(rel)
        return halves[rel]
    return SimpleNamespace(read_base_xmlb=read)


def test_codex_menu_loses_only_the_list_icons_in_both_halves():
    x, g = menu('@INVENTED@KEY'), menu('Invented text')
    before = {k: ET.tostring(v) for k, v in (('x', x), ('g', g))}
    kx, kg, removed = F.codex_menu_trees(base_ctx({'UI/menus/codex.XMLB': x, 'UI/menus/codex.engb': g}))
    assert removed == ['list.icons', 'list.icons_cols', 'list.icons_rows', 'precache textures/ui/mini_convo_icons']
    for tree, text in ((kx, '@INVENTED@KEY'), (kg, 'Invented text')):
        assert F.codex_icon_problems(tree) == []
        lst = next(it for it in tree.iter('item') if it.get('name') == 'list')
        assert lst.attrib == {'name': 'list', 'type': 'MENU_ITEM_LISTCODEX', 'mode': '0', 'style': 'STYLE_INVENTED'}
        assert lst.find('onfocus') is not None                   # selection still drawn
        assert [p.get('filename') for p in tree.findall('precache')] == ['ui/menus/invented_back']
        assert tree.get('desctext1') == text                     # each half keeps its own texts
    assert before['x'] != ET.tostring(kx)


def test_missing_base_menu_reports_nothing_to_write():
    assert F.codex_menu_trees(base_ctx({'UI/menus/codex.XMLB': menu('k')})) == (None, None, [])


def validator(trees, owner='frontend', mode='xml1'):
    v = SimpleNamespace(ctx=SimpleNamespace(opt=lambda k: mode if k == 'frontend' else None))
    v.tree = lambda rel: trees.get(rel)
    v.entry = lambda rel: {'owner': owner} if rel in trees else None
    ck = Check('V29', 'codex icons')
    VF.v_codex_icons(v, ck)
    return ck


def test_validator_rejects_icon_cells_and_xml2_menu():
    fixed = {'UI/menus/codex.XMLB': F.codex_menu_trees(base_ctx({'UI/menus/codex.XMLB': menu('k'),
                                                                   'UI/menus/codex.engb': menu('t')}))[0]}
    fixed['UI/menus/codex.engb'] = fixed['UI/menus/codex.XMLB']
    assert not validator(fixed).errors
    unfixed = {'UI/menus/codex.XMLB': menu('k'), 'UI/menus/codex.engb': menu('t')}
    errs = validator(unfixed).errors
    assert len(errs) == 8 and all('icons' in e or 'mini_convo_icons' in e for e in errs)
    assert len(validator(fixed, owner='base').errors) == 2
    assert not validator(unfixed, mode='xml2').errors
