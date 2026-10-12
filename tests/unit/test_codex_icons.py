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


# ---- issue #97: the codex list's highlight over the whole row (an invented two-transform bar)
import struct  # noqa: E402

from test_main_appearance import fixture, u32  # noqa: E402
from xml1build.igb_file import IgbFile  # noqa: E402


def bar_igb(outer_x=40.0, outer_rows=None, gap_box=(20.0, 100.0)):
    node = [(2, 's'), (3, 'r'), (5, 'i')]
    group = node + [(7, 'r')]
    list_fields = [(2, 'i'), (3, 'i'), (4, 'b')]
    specs = [('igObject', None, []), ('igNamedObject', 'igObject', [(2, 's')]),
             ('igNode', 'igNamedObject', node), ('igGroup', 'igNode', group),
             ('igTransform', 'igGroup', group + [(8, 'm')]),
             ('igAABox', 'igObject', [(2, 'v'), (3, 'v')]),
             ('igDataList', 'igObject', list_fields), ('igNodeList', 'igDataList', list_fields)]

    def matrix(x, rows=None):
        m = [float(i in (0, 5, 10, 15)) for i in range(16)]
        if rows:
            m[:12] = rows
        m[12] = x
        return m
    lo, hi = gap_box
    objects = [('igTransform', {2: 'barA', 3: 2, 5: 2, 7: 4, 8: matrix(outer_x, outer_rows)}),
               ('igTransform', {2: 'barA', 3: 3, 5: 2, 7: -1, 8: matrix(10.0)}),
               ('igAABox', {2: (lo, 0, -5), 3: (hi, 0, 5)}),
               ('igAABox', {2: (lo - outer_x, 0, -5), 3: (hi - outer_x, 0, 5)}),
               ('igNodeList', {2: 1, 3: 1, 4: 6}),
               ('igAABox', {2: (lo, 0, -5), 3: (hi, 0, 5)})]
    return fixture(specs, objects, (u32(1),))


def test_bar_stretched_from_the_row_origin_to_its_own_right_end():
    data, rep = F.codex_select_igb(bar_igb())
    assert rep == {'gap': 20.0, 'right': 100.0, 'scale': 1.25, 'bounds': 2}
    g = IgbFile(data)
    outer, inner = g.objects_of('igTransform')
    m = outer.get(8)
    assert m[0] == 1.25 and m[12] == 25.0 and m[5] == 1.0 and m[13:16] == [0.0, 0.0, 1.0]
    assert inner.get(8)[12] == 10.0                                  # the bar's own placement untouched
    boxes = [(list(b.get(2))[0], list(b.get(3))[0]) for b in g.objects_of('igAABox')]
    assert boxes == [(0.0, 100.0), (-20.0, 60.0), (0.0, 100.0)]
    # the inner span mapped through the new outer transform is exactly the row [0, right]
    assert -20.0 * m[0] + m[12] == 0.0 and 60.0 * m[0] + m[12] == 100.0
    assert len(data) == len(bar_igb())                               # an in-place edit


def test_bar_refused_unless_it_is_the_expected_shape():
    rotated = [0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0]
    assert F.codex_select_igb(bar_igb(outer_rows=rotated))[0] is None
    assert 'already starts' in F.codex_select_igb(bar_igb(outer_x=20.0, gap_box=(0.0, 80.0)))[1]['problem']
    assert F.codex_select_igb(b'not an igb')[0] is None


def test_codex_list_highlight_points_at_the_ports_model():
    x = F.codex_menu_trees(base_ctx({'UI/menus/codex.XMLB': menu('k'), 'UI/menus/codex.engb': menu('t')}))[0]
    assert F.codex_select_problems(x)                                # XML2's model: a problem
    assert F.use_codex_select(x) == 1 and F.use_codex_select(x) == 0
    assert F.codex_select_problems(x) == []
    lst = next(it for it in x.iter('item') if it.get('name') == 'list')
    assert [f.get('model') for f in lst.findall('onfocus')] == [F.CODEX_SELECT_X1]


def highlight_validator(trees, owners, mode='xml1'):
    v = SimpleNamespace(ctx=SimpleNamespace(opt=lambda k: mode if k == 'frontend' else None))
    v.tree = lambda rel: trees.get(rel)
    v.entry = lambda rel: {'owner': owners[rel]} if rel in owners else None
    ck = Check('V58', 'codex highlight')
    VF.v_codex_highlight(v, ck)
    return ck


def test_validator_wants_the_stretched_highlight_in_both_halves():
    fixed = F.codex_menu_trees(base_ctx({'UI/menus/codex.XMLB': menu('k'), 'UI/menus/codex.engb': menu('t')}))[0]
    F.use_codex_select(fixed)
    igb = F.CODEX_SELECT_X1 + '.igb'
    good = {'UI/menus/codex.XMLB': fixed, 'UI/menus/codex.engb': fixed}
    assert not highlight_validator(good, {igb: 'frontend'}).errors
    assert len(highlight_validator(good, {}).errors) == 1            # the model file is missing
    old = {'UI/menus/codex.XMLB': menu('k'), 'UI/menus/codex.engb': menu('t')}
    assert len(highlight_validator(old, {igb: 'frontend'}).errors) == 2
    assert not highlight_validator(old, {}, mode='xml2').errors
