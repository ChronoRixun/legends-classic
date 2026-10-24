"""Native pause action and submode preservation using invented labels and commands."""
import xml.etree.ElementTree as ET
import copy
import struct
from types import SimpleNamespace

from xml1build import pause_appearance as P, menu_theme as T, validate_frontend as V, frontend as F, common as C
from xml1build.validate import Check
from test_main_appearance import fixture, palette


def native_menu():
    root = ET.Element('MENU', type='PDA_MENU', igb='synth_native',
                      desctext1='$MENU_BACK Return', desctext2='$MENU_ACCEPT Choose')
    for i, name in enumerate(P.ROWS):
        row = ET.SubElement(root, 'item', name=name, text=f'Invented {i}', mode='0 2',
                            usecmd=f'synth_action_{i}', style='SYNTH', animtext_scene='synth')
        ET.SubElement(row, 'onfocus', item='synth_old', model='ui/models/synth_old')
        slot = name.removeprefix('label_')
        for suffix in ('', '_focus', '_light'):
            ET.SubElement(root, 'item', name=slot + suffix, mode='0 2', type='MENU_ITEM_MODEL')
    for name, mode, kind in [('object_desc', '1', 'MENU_ITEM_TEXTBOX'),
                             ('players', '2', 'MENU_ITEM_LISTBOX'),
                             ('players_help', '2', 'MENU_ITEM_TEXTBOX')]:
        ET.SubElement(root, 'item', name=name, mode=mode, type=kind, style='SYNTH',
                      usecmd='synth_service', icons='textures/synth_icons', icons_cols='2')
    root.find("item[@name='label_option09']").set('desctext2', '$MENU_ACCEPT Invented focus hint')
    root.find("item[@name='players_help']").set('text', 'Invented help: $MENU_ACCEPT toggles a row.')
    return root


def test_pause_skin_retains_native_commands_modes_and_service_widgets():
    original = native_menu()
    before = ET.tostring(original)
    root = P.pause_tree(original)
    assert ET.tostring(original) == before and root.get('type') == original.get('type')
    rows = {e.get('name'): e for e in root.findall('item')}
    for old in original.findall('item'):
        name = old.get('name')
        if name in P.ROWS:
            assert rows[name].get('usecmd') == old.get('usecmd')
            assert rows[name].get('text') == old.get('text') and rows[name].get('mode') == old.get('mode')
    secondary = {e.get('name'): e for e in root}
    for name in ('object_desc', 'players', 'players_help'):
        old = next(e for e in original if e.get('name') == name)
        for key in ('type', 'usecmd', 'mode', 'icons', 'icons_cols'):
            assert secondary[name].get(key) == old.get(key)
    assert secondary['option01_light'].get('hide') == 'true'
    assert root.find('items') is None


def test_pause_focus_visits_all_native_roles_without_removed_portal_or_debug():
    root = P.pause_tree(native_menu())
    rows = {e.get('name'): e for e in root.findall('item')}
    current, visited = P.ROWS[0], []
    while current not in visited:
        visited.append(current)
        following = rows[current].get('down')
        assert rows[following].get('up') == current
        current = following
    assert tuple(visited) == P.ROWS and current == P.ROWS[0]
    assert len(rows[P.ROWS[0]].findall('onfocus')) == 2


def validator_fixture():
    native = native_menu()
    root = P.pause_tree(native)
    matrix = [float(i in (0, 5, 10, 15)) for i in range(16)]
    matrix[12:15] = [256, 0, 192]
    node = [(2, 's'), (3, 'r'), (5, 'i')]
    group = node + [(7, 'r')]
    fields = [(2, 'i'), (3, 'i'), (4, 'b')]
    specs = [('igNode', None, node), ('igGroup', 'igNode', group),
             ('igTransform', 'igGroup', group + [(8, 'm')]),
             ('igCamera', 'igNode', node + [(8, 'f'), (9, 'f'), (10, 'f')]),
             ('igDataList', None, fields), ('igNodeList', 'igDataList', fields),
             ('igSceneInfo', None, [(5, 'r')])]
    camera = list(matrix)
    for row in range(3):
        camera[row * 4:row * 4 + 3] = F.MENU_CAMERA_ROWS[row]
    camera[12:15] = F.MENU_CAMERA_POS
    names = [item.get('name') for item in root.findall('item')]
    count = 6 + len(names)
    objects = [('igSceneInfo', {5: 1}), ('igGroup', {2: 'synth_root', 3: -1, 5: 2, 7: 2}),
               ('igNodeList', {2: 1 + len(names), 3: 1 + len(names), 4: count}),
               ('igTransform', {2: 'synth_camera', 3: -1, 5: 2, 7: 4, 8: camera}),
               ('igNodeList', {2: 1, 3: 1, 4: count + 1}),
               ('igCamera', {2: 'synth_view', 3: -1, 5: 2, 8: 25, 9: 100, 10: 1100})]
    objects += [('igTransform', {2: name, 3: -1, 5: 2, 7: -1, 8: matrix}) for name in names]
    children = [3, *range(6, count)]
    scene = fixture(specs, objects, (struct.pack('<' + 'i' * len(children), *children), struct.pack('<i', 5)))
    colors, styles, _ = T.allocate(ET.Element('colors'), ET.Element('styles'), palette(), [
        T.text_style(name) for name in (P.BODY_STYLE, P.LIST_STYLE, 'STYLE_NORMAL', 'STYLE_MENU')])
    localized = copy.deepcopy(native)
    localized.set('desctext1', '@SYNTH@RETURN')
    localized.set('desctext2', '@SYNTH@CHOOSE')
    localized.find("item[@name='label_option09']").set('desctext2', '@SYNTH@FOCUS')
    localized.find("item[@name='players_help']").set('text', '@SYNTH@HELP')
    native_halves = {'UI/menus/pda.XMLB': localized, 'UI/menus/pda.engb': native}
    trees = {rel: P.pause_tree(tree) for rel, tree in native_halves.items()}
    trees.update({'Data/colors.XMLB': colors, 'Data/styles.XMLB': styles})
    ctx = SimpleNamespace(opt=lambda key: 'xml1' if key == 'frontend' else None,
                          read_base_xmlb=lambda rel: copy.deepcopy(native_halves[rel]))
    from test_menu_conversion import flat_panel
    from xml1build import menu_conversion as M
    selector, _ = M.fit_flat_panel(flat_panel((0, 0, 1, 0, 0, 1, 1, 1)),
                                   P.OBJECTIVES_PICTURE_FRAME, border=5)
    selectors = {n.lower() + '.igb' for n in
                 (P.OBJECTIVES_ICON, P.OBJECTIVES_FOCUS, 'UI/models/m_pda_icon_screen')}
    validator = SimpleNamespace(ctx=ctx, tree=lambda rel: trees.get(rel),
                                read=lambda rel: selector if rel.lower() in selectors else scene)
    return validator, trees


def test_classic_pause_validator_catches_split_scene_and_changed_action():
    validator, trees = validator_fixture()
    ck = Check('V-TBD', 'classic pause')
    V.v_classic_pause(validator, ck)
    assert not ck.errors, ck.errors
    ET.SubElement(trees['UI/menus/pda.engb'], 'items', file='synth_extra', igb='synth_other_scene')
    ck = Check('V-TBD', 'classic pause')
    V.v_classic_pause(validator, ck)
    assert any('one scene' in error for error in ck.errors)
    item = next(e for e in trees['UI/menus/pda.engb'] if e.get('name') == P.ROWS[0])
    item.set('usecmd', 'synth_wrong_action')
    ck = Check('V-TBD', 'classic pause')
    V.v_classic_pause(validator, ck)
    assert any('native service contract' in error for error in ck.errors)


def test_pause_binary_output_keeps_native_prompt_and_focus_tokens():
    root = C.decode_xmlb(C.encode_xmlb(P.pause_tree(native_menu())))
    assert root.get('desctext1') == '$MENU_BACK Return'
    assert root.get('desctext2') == '$MENU_ACCEPT Choose'
    assert root.find("item[@name='label_option09']").get('desctext2') == '$MENU_ACCEPT Invented focus hint'
    assert root.find("item[@name='players_help']").get('text') == 'Invented help: $MENU_ACCEPT toggles a row.'


def test_objective_decorations_stay_outside_wide_view_after_native_refresh():
    # Native PDA refresh can restore a decoration's model and visibility. Its
    # anchor must remain outside the view even after those flags are restored.
    from xml1build import menu_conversion as M, igb_file as G
    names = tuple('object_hinge%02d' % i for i in range(1, 5)) + tuple(
        'icon%02d_%s' % (i, suffix) for i in range(1, 8) for suffix in ('bracket', 'light'))
    layouts = {name: P.objectives_layout()[name] for name in names}
    matrix = [float(i in (0, 5, 10, 15)) for i in range(16)]
    schemas = [('igTransform', None, [(2, 's'), (8, 'm'), (11, 'r')]),
               ('igHashedUserInfo', None, [(2, 's'), (3, 'r')]),
               ('igAABox', None, [(2, 'v'), (3, 'v')]),
               ('igSyntheticSequence', None, [(2, 'i')])]
    objects = [('igSyntheticSequence', {2: 927})]
    for name in names:
        at = len(objects)
        objects.extend([('igTransform', {2: name, 8: matrix, 11: 0}),
                        ('igHashedUserInfo', {2: name, 3: at + 2}),
                        ('igAABox', {2: [-1, 0, -1], 3: [1, 0, 1]})])
    scene = M.place_anchors(fixture(schemas, objects), layouts)
    assert not M.placement_problems(scene, layouts)
    graph = G.IgbFile(scene)
    assert graph.obj(0).get(2) == 927
    for node in graph.objects_of('igTransform'):
        x, _, z = node.get(8)[12:15]
        assert abs(x) > 2048 and abs(z) > 2048
        assert node.get(11) == -1


def test_classic_pause_validator_rejects_baked_or_missing_root_prompts():
    for replacement in ('B Return', '\x02 Return', '[Esc] Return', None):
        validator, trees = validator_fixture()
        root = trees['UI/menus/pda.engb']
        if replacement is None:
            root.attrib.pop('desctext1')
        else:
            root.set('desctext1', replacement)
        ck = Check('V-TBD', 'classic pause')
        V.v_classic_pause(validator, ck)
        assert any('native prompt/text contract' in error for error in ck.errors), replacement


def test_classic_pause_validator_rejects_baked_focus_and_help_text():
    for name, attr, value in (('label_option09', 'desctext2', 'A Invented focus hint'),
                               ('players_help', 'text', 'Invented help: A toggles a row.')):
        validator, trees = validator_fixture()
        trees['UI/menus/pda.engb'].find(f"item[@name='{name}']").set(attr, value)
        ck = Check('V-TBD', 'classic pause')
        V.v_classic_pause(validator, ck)
        assert any('native prompt/text contract' in error for error in ck.errors), name


def test_classic_pause_validator_checks_the_matching_localization_half():
    validator, trees = validator_fixture()
    ck = Check('V-TBD', 'classic pause')
    V.v_classic_pause(validator, ck)
    assert not ck.errors, ck.errors
    trees['UI/menus/pda.XMLB'].set('desctext2', '$MENU_ACCEPT Choose')
    ck = Check('V-TBD', 'classic pause')
    V.v_classic_pause(validator, ck)
    assert any('native prompt/text contract' in error for error in ck.errors)
