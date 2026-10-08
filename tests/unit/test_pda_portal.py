"""Synthetic regressions for the pause menu's Blink Portal entry (issue #89)."""
import xml.etree.ElementTree as ET
from types import SimpleNamespace

from xml1build import frontend as F
from xml1build import validate_frontend as VF
from xml1build.validate import Check


def menu(text):
    """an invented PDA menu shaped like XMen2.exe's: three labels in an up/down chain, the middle one the portal
    label, its panel models, and an unrelated fourth model."""
    root = ET.Element('MENU', {'type': 'PDA_MENU', 'desctext1': text, 'updownonly': 'true'})
    ET.SubElement(root, 'precache', {'filename': 'ui/models/invented_light_on', 'type': 'model'})
    ET.SubElement(root, 'animtext', {'name': 'option03'})
    for name in F.PDA_PORTAL_MODELS + ('invented_model',):
        ET.SubElement(root, 'item', {'name': name, 'type': 'MENU_ITEM_MODEL', 'model': 'ui/models/invented'})
    ET.SubElement(root, 'item', {'name': 'label_option02', 'text': text, 'up': 'label_option01',
                                 'down': F.PDA_PORTAL_LABEL, 'usecmd': 'openmenu invented'})
    portal = ET.SubElement(root, 'item', {'name': F.PDA_PORTAL_LABEL, 'text': text, 'up': 'label_option02',
                                          'down': 'label_option04', 'animtext_scene': 'option03'})
    ET.SubElement(portal, 'onfocus', {'item': 'option03_light', 'type': 'focus'})
    ET.SubElement(root, 'item', {'name': 'label_option04', 'text': text, 'up': F.PDA_PORTAL_LABEL,
                                 'down': 'label_option05'})
    return root


def base_ctx(halves):
    def read(rel):
        if rel not in halves:
            raise KeyError(rel)
        return halves[rel]
    return SimpleNamespace(read_base_xmlb=read)


def items(root):
    return {it.get('name'): it for it in root.iter('item')}


def test_pda_menu_loses_the_portal_entry_in_both_halves():
    x, g = menu('@INVENTED@KEY'), menu('Invented text')
    px, pg, changes = F.pda_menu_trees(base_ctx({'UI/menus/pda.XMLB': x, 'UI/menus/pda.engb': g}))
    assert F.pda_portal_changes_ok(changes)
    assert changes == sorted(['remove label_option03', 'label_option02.down -> label_option04',
                              'label_option04.up -> label_option02'] + [f'hide {m}' for m in F.PDA_PORTAL_MODELS])
    for tree, text in ((px, '@INVENTED@KEY'), (pg, 'Invented text')):
        assert F.pda_portal_problems(tree) == []
        its = items(tree)
        assert F.PDA_PORTAL_LABEL not in its and 'onfocus' not in {e.tag for e in tree.iter()}
        assert its['label_option02'].get('down') == 'label_option04'
        assert its['label_option04'].get('up') == 'label_option02'
        assert its['label_option02'].get('usecmd') == 'openmenu invented'          # the other entries keep theirs
        assert its['label_option04'].get('down') == 'label_option05'
        for m in F.PDA_PORTAL_MODELS:
            assert (its[m].get('hide'), its[m].get('enabled')) == ('true', 'false')
        assert 'hide' not in its['invented_model'].attrib                          # only the portal's slot
        assert tree.find('animtext') is not None and tree.get('desctext1') == text  # each half keeps its texts


def test_menus_without_the_portal_are_left_alone():
    plain = ET.Element('MENU', {'type': 'PDA_MENU'})
    ET.SubElement(plain, 'item', {'name': 'label_option02', 'down': 'label_option04'})
    assert F.pda_without_portal(plain) is None
    other = menu('k')
    other.set('type', 'INVENTED_MENU')
    assert F.pda_without_portal(other) is None and F.PDA_PORTAL_LABEL in items(other)
    assert F.pda_menu_trees(base_ctx({'UI/menus/pda.XMLB': menu('k')})) == (None, None, [])
    _, _, changes = F.pda_menu_trees(base_ctx({'UI/menus/pda.XMLB': menu('k'), 'UI/menus/pda.engb': plain}))
    assert not F.pda_portal_changes_ok(changes)                       # halves differ: the build reports an error


def test_a_portal_label_at_the_end_of_the_chain_unlinks_its_neighbour():
    root = ET.Element('MENU', {'type': 'PDA_MENU'})
    ET.SubElement(root, 'item', {'name': 'label_option02', 'down': F.PDA_PORTAL_LABEL})
    ET.SubElement(root, 'item', {'name': F.PDA_PORTAL_LABEL, 'up': 'label_option02'})
    assert F.pda_without_portal(root) == ['label_option02.down -> None', 'remove label_option03']
    assert 'down' not in items(root)['label_option02'].attrib and F.pda_portal_problems(root) == []


def validator(trees, owner='frontend', mode='xml1'):
    v = SimpleNamespace(ctx=SimpleNamespace(opt=lambda k: mode if k == 'frontend' else None))
    v.tree = lambda rel: trees.get(rel)
    v.entry = lambda rel: {'owner': owner} if rel in trees else None
    ck = Check('V35', 'pda portal')
    VF.v_pda_portal(v, ck)
    return ck


def test_validator_rejects_the_portal_entry_in_either_front_end():
    halves = {'UI/menus/pda.XMLB': menu('k'), 'UI/menus/pda.engb': menu('t')}
    px, pg, _ = F.pda_menu_trees(base_ctx(halves))
    fixed = {'UI/menus/pda.XMLB': px, 'UI/menus/pda.engb': pg}
    for mode in ('xml1', 'xml2'):
        assert not validator(fixed, mode=mode).errors
        unfixed = {'UI/menus/pda.XMLB': menu('k'), 'UI/menus/pda.engb': menu('t')}
        errs = validator(unfixed, mode=mode).errors
        # per half: the label, two links to it, four shown models
        assert len(errs) == 14 and all('label_option03' in e or 'is shown' in e for e in errs)
    assert len(validator(fixed, owner='base').errors) == 2
    assert len(validator({}).errors) == 2
