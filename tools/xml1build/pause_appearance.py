"""Classic pause stack over the PC PDA service; input/actions remain native."""
from __future__ import annotations

import copy
import math
import xml.etree.ElementTree as ET

from . import menu_conversion as M, menu_theme as T, main_appearance as MA, menu_scene as S

SCENE = 'lc_pause'
ROWS = ('label_option01', 'label_option02', 'label_option04', 'label_option05',
        'label_option06', 'label_option07', 'label_option08', 'label_option09')
BODY_STYLE, LIST_STYLE = 'STYLE_LC_BODY', 'STYLE_LC_LIST'
PLAYERS_PANEL = 'ui/models/lc_pda_players_panel'
PLAYERS_SELECT = 'ui/models/lc_pda_players_select'
OBJECTIVES_PANEL = 'ui/models/lc_objectives_panel'
OBJECTIVES_ICON = 'ui/models/lc_objectives_icon'
OBJECTIVES_FOCUS = 'ui/models/lc_objectives_focus'
# XMen2.exe draws slot n's objective picture (n = 0..6) at a FIXED virtual-screen
# point, not at its selector: centre (36, 346 - 45 n), 34 units square
# (0x5cda36 imul 0x2d, 0x5cda3c 0x15a, 0x5cda43 34.0, 0x5cda84 36.0; the selector
# item only gives the picture its depth). Each selector anchor therefore sits on
# its slot's picture centre, with a square frame and hit box centred there.
PDA_PICTURE_X, PDA_PICTURE_TOP, PDA_PICTURE_STEP, PDA_PICTURE_SIZE = 36, 346, 45, 34
OBJECTIVES_PICTURE_FRAME = (-22, -22, 22, 22)
# The first game's objectives screen (captured on the Xbox original) is an inset
# honeycomb panel with its Back prompt in a separate bar 30..56 units above the bottom
# edge. The PDA keeps a full-width panel for the fixed picture column; its bottom
# strip rises off the screen edge towards that bar, as far as slot 7's frame (z 54)
# allows, and stays clear of a desktop taskbar shown over a borderless window.
OBJECTIVES_PANEL_RECT = (0, 14, 512, 384)
PROMPT_Z = 33


def picture_centre(slot):
    """virtual-screen centre of the engine's objective picture for selector slot 0..6"""
    return PDA_PICTURE_X, PDA_PICTURE_TOP - PDA_PICTURE_STEP * slot
# The retail definition itself names these two optional decorative anchors that
# are absent from its scene. Preserve that native fallback; neither is focusable.
OPTIONAL_ANCHORS = ('option05_light', 'object_helpbar')


def native_text_problems(native, converted):
    """Appearance conversion must leave native token expansion/localization intact.

    Check full values, including focused-row hints and secondary-mode help. A
    literal keyboard hint is just as wrong as a literal pad glyph: both prevent
    the engine from following the last input device and the player's bindings.
    """
    before = {item.get('name'): item for item in native.iter('item')}
    after = {item.get('name'): item for item in converted.iter('item')}
    before[None], after[None] = native, converted
    problems = []
    for name, original in before.items():
        actual = after.get(name)
        if actual is None:
            problems.append(f'native prompt/text contract: missing item {name}')
            continue
        keys = {key for key in set(original.attrib) | set(actual.attrib)
                if key == 'text' or key.startswith('desctext')}
        for key in sorted(keys):
            if actual.get(key) != original.get(key):
                problems.append(f'native prompt/text contract: {name or "menu"}.{key} changed')
    return problems


def pause_scene(data, native_data=None):
    aliases = {}
    for number, label in enumerate(ROWS + ('debug_text',), 1):
        slot = label.removeprefix('label_') if label != 'debug_text' else 'debug'
        aliases[f'button{number}'] = label
        aliases[f'button{number}_back'] = slot
        aliases[f'button{number}_highlight'] = slot + '_focus'
    artwork, report = M.convert_scene(data, aliases, count=len(ROWS))
    if native_data is None:
        return artwork, report
    # Native animation sequences keep their references, but their old pause
    # anchors must not shadow the new named anchors in the attached artwork.
    names = list(aliases.values()) + ['desctext1', 'desctext2']
    native, report['retired_aliases'] = M.rename_aliases(native_data, {n: 'unused_' + n for n in names})
    # Native objective state/navigation stays in PDA mode 1. Place its widgets
    # explicitly; detach only these anchors from the sliding panel animation.
    native = M.place_anchors(native, objectives_layout())
    merged, report['attachment'] = S.attach(native, artwork)
    merged = M.place_anchors(merged, {
        f'desctext{i}': ((x, -150, PROMPT_Z), (-70, -10, 70, 10))
        for i, x in ((1, 80), (2, 232), (3, 300), (4, 410), (5, 450))})
    return merged, report


def objectives_layout():
    left, bottom, right, top = OBJECTIVES_PANEL_RECT
    cx, cz, hw, hh = (left + right) / 2, (bottom + top) / 2, (right - left) / 2, (top - bottom) / 2
    layout = {
        'object_screen': ((cx, -80, cz), (-hw, -hh, hw, hh)),
        # Left-aligned title to the right of the picture column (slot 1's frame is x 14..58, z 324..368).
        'label_objectives': ((139, -120, 355), (-69, -9, 69, 9)),
        'object_name': ((288, -120, 313), (-174, -9, 174, 9)),
        'object_desc': ((288, -120, 263), (-174, -34, 174, 34)),
        # Above the panel's bottom strip (it ends about 38 units above the panel's bottom edge).
        'object_steps': ((288, -120, 138), (-174, -82, 174, 82)),
    }
    # The native refresh restores hinge models/visibility after XML hiding.
    # Detach their animation and retire their anchors outside the menu view.
    for i in range(1, 5):
        layout[f'object_hinge{i:02d}'] = ((-4096, -80, -4096), (-1, -1, 1, 1))
    for i in range(1, 8):
        for suffix in ('bracket', 'light'):
            layout[f'icon{i:02d}_{suffix}'] = ((-4096, -80, -4096), (-1, -1, 1, 1))
    for i in range(1, 8):
        x, z = picture_centre(i - 1)
        for suffix in ('', '_focus', '_current'):
            layout[f'icon{i:02d}' + suffix] = ((x, -125 if suffix else -120, z), OBJECTIVES_PICTURE_FRAME)
    return layout


def objectives_layout_problems(layout=None):
    """Each selector frame holds its slot's engine-drawn picture; frames, title and
    texts stay apart and inside the panel, above its bottom strip."""
    layout = objectives_layout() if layout is None else layout
    problems = []

    def rect(name):
        (x, _, z), (l, b, r, t) = layout[name]
        return x + l, z + b, x + r, z + t

    def overlap(a, b):
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

    panel = rect('object_screen')
    if any(abs(a - b) > 1e-6 for a, b in zip(panel, OBJECTIVES_PANEL_RECT)):
        problems.append('objective panel is not the classic panel rectangle')
    if panel[0] < 0 or panel[1] < 0 or panel[2] > 512 or panel[3] > 384:
        problems.append('objective panel leaves the 4:3 virtual screen')
    strip_top = panel[1] + 38
    frames = []
    for slot in range(7):
        name = f'icon{slot + 1:02d}'
        frame = rect(name)
        px, pz = picture_centre(slot)
        half = PDA_PICTURE_SIZE / 2
        if not (frame[0] <= px - half and px + half <= frame[2] and frame[1] <= pz - half and pz + half <= frame[3]):
            problems.append(f'{name} frame misses its engine-drawn picture')
        for suffix in ('_focus', '_current'):
            if rect(name + suffix) != frame:
                problems.append(f'{name}{suffix} is not on its selector frame')
        if frame[1] < strip_top or frame[3] > panel[3]:
            problems.append(f'{name} frame leaves the panel interior')
        frames.append((name, frame))
    for i, (name, frame) in enumerate(frames):
        for other, second in frames[i + 1:]:
            if overlap(frame, second):
                problems.append(f'{name} and {other} frames overlap')
    texts = ('label_objectives', 'object_name', 'object_desc', 'object_steps')
    for text in texts:
        box = rect(text)
        if box[1] < strip_top or box[3] > panel[3] or box[0] < panel[0] or box[2] > panel[2]:
            problems.append(f'{text} leaves the panel interior')
        for name, frame in frames:
            if overlap(box, frame):
                problems.append(f'{text} overlaps the {name} frame')
    return problems


def selector_problems(data):
    """Catch a frame centred on the hit anchor instead of the native picture."""
    from . import igb_file as G
    graph = G.IgbFile(data)
    vertices = []
    for array in graph.objects_of('igVertexArray1_1'):
        refs = graph.ref_list(array.get(2))
        row = graph.block_floats(refs[0]) if refs else []
        vertices.extend(zip(row[0::3], row[1::3], row[2::3]))
    if not vertices or graph.objects_of('igTransform'):
        return ['objective selector frame is not flat']
    bounds = (min(v[0] for v in vertices), min(v[2] for v in vertices),
              max(v[0] for v in vertices), max(v[2] for v in vertices))
    return ['objective selector frame misses the native picture'] if any(not math.isfinite(v) for v in bounds) or any(
        abs(a-b) > 1e-4 for a, b in zip(bounds, OBJECTIVES_PICTURE_FRAME)) else []


def pause_tree(native):
    """Keep native widgets and modes in one scene with the converted classic stack.

    Native PDA code still finds every named item. Its objective/player widgets keep
    their native scene and animation contracts. Debug/portal models stay hidden.
    """
    root = copy.deepcopy(native)
    root.set('igb', SCENE)
    root.set('lighting', 'true')
    pause_names = set(ROWS) | {'debug_text', 'debug', 'debug_focus', 'desctext1', 'desctext2'}
    pause_names |= {n.removeprefix('label_') + suffix for n in ROWS for suffix in ('', '_focus')}
    for item in list(root.findall('item')):
        name = item.get('name')
        if name in ROWS:
            number = ROWS.index(name)
            for attr in ('animtext_scene', 'textalignx', 'textaligny'):
                item.attrib.pop(attr, None)
            item.attrib.update(style=MA.MAIN_STYLE, up=ROWS[number - 1], down=ROWS[(number + 1) % len(ROWS)])
            if number == 0:
                item.set('startactive', 'true')
            for child in list(item):
                if child.tag == 'onfocus':
                    item.remove(child)
            slot = name.removeprefix('label_')
            ET.SubElement(item, 'onfocus', {'item': slot + '_focus', 'type': 'focus',
                                          'model': 'ui/models/model_button_highlight', 'loop': '1'})
            ET.SubElement(item, 'onfocus', {'item': slot + '_focus', 'type': 'nofocus',
                                          'model': 'ui/models/model_hide'})
        elif name in pause_names:
            item.attrib.pop('animtext_scene', None)
            if name in ('debug_text', 'debug', 'debug_focus'):
                item.attrib.update(hide='true', enabled='false')
                item.attrib.pop('up', None)
                item.attrib.pop('down', None)
            elif name in ('desctext1', 'desctext2'):
                item.set('style', MA.HELP_STYLE)
                for attr in ('textalignx', 'textaligny'):
                    item.attrib.pop(attr, None)
            else:
                item.set('model', 'ui/models/model_hide' if name.endswith('_focus') else 'ui/models/model_button')
                item.set('neverfocus', 'true')
                if name.endswith('_focus'):
                    item.set('animate', 'true')
        elif item.get('style'):
            item.set('style', LIST_STYLE if name == 'players' else BODY_STYLE)
        if name == 'players_panel':
            item.set('model', PLAYERS_PANEL)
        elif name == 'players':
            for action in item.findall('onfocus'):
                if action.get('type') == 'list_focus':
                    action.set('model', PLAYERS_SELECT)
        elif name == 'object_screen':
            item.set('model', OBJECTIVES_PANEL)
        elif name and name.startswith('icon') and name[-2:].isdigit():
            item.set('model', OBJECTIVES_ICON)
            for action in item.findall('onfocus'):
                if action.get('model'):
                    action.set('model', OBJECTIVES_FOCUS if action.get('item', '').endswith('_focus')
                               else 'ui/models/model_hide')
        if name in objectives_layout():
            item.attrib.pop('animtext_scene', None)
            if name == 'label_objectives':
                item.attrib.update(textalignx='TEXT_ALIGN_LEFT', textaligny='TEXT_ALIGN_CENTER_Y')
    for item in root.findall('item'):
        name = item.get('name') or ''
        if (name.startswith('pause_bracket_') or name.endswith('_light') and name.startswith('option') or
                name.startswith('option03') or
                name in ('track01', 'track02', 'helpbar', 'helpbar_hinge_left', 'helpbar_hinge_right')):
            item.attrib.update(hide='true', enabled='false')
            item.set('model', 'ui/models/model_hide')
        if (name.startswith('object_hinge') or name.startswith('icon') and
                name.endswith(('_bracket', '_light')) or name in
                ('object_light', 'object_focus', 'object_desc_light', 'object_desc_focus')):
            item.attrib.update(hide='true', enabled='false')
            item.set('model', 'ui/models/model_hide')
    return root


def write(ctx):
    from . import frontend as F
    native_x, native_e, _ = F.pda_menu_trees(ctx)
    if native_x is None:
        raise ValueError('native PDA menu halves are missing')
    source = ctx.x1_path('ui/menus/menu_pause.igb')
    if source is None:
        raise ValueError('original pause scene is missing')
    native_scene = ctx.base_index.path('UI/menus/x2m_pda.IGB')
    if native_scene is None:
        raise ValueError('native PDA scene is missing')
    scene, report = pause_scene(source.read_bytes(), native_scene.read_bytes())
    halves = []
    for native in (native_x, native_e):
        root = pause_tree(native)
        problems = M.widget_problems(root, scene, focus_names=ROWS, optional_anchors=OPTIONAL_ANCHORS)
        problems += native_text_problems(native, root)
        if problems:
            raise ValueError('; '.join(problems))
        halves.append(root)
    # Allocate after the established main palette; keep its IDs/font names stable.
    colors, styles, ids = T.allocate(ctx.read_out_xmlb('Data/colors.XMLB'),
                                    ctx.read_out_xmlb('Data/styles.XMLB'),
                                    ctx.read_x1_xml('data/colors.xml'), (
        T.text_style(BODY_STYLE), T.text_style(LIST_STYLE, normal=1, focus=4, allow=True)))
    ctx.write_xmlb('Data/colors', colors, source='frontend:shared classic menu palette')
    ctx.write_xmlb('Data/styles', styles, source='frontend:shared classic menu styles')
    ctx.write_bytes(f'UI/menus/{SCENE}.IGB', scene, source='frontend:original pause scene with native PDA aliases')
    ctx.write_xmlb_pair(F.PDA_MENU_REL, *halves, source='frontend:classic pause, native PDA actions')
    native_package = ctx.read_base_xmlb(f'{F.MENU_PKG_DIR}/pda.PKGB')
    for entry in list(native_package):
        if entry.get('filename') == 'ui/menus/x2m_pda':
            native_package.remove(entry)
    package = M.package_for(halves[0], inherited=native_package)
    ctx.write_xmlb(f'{F.MENU_PKG_DIR}/pda', package, ('.PKGB',), source='frontend:classic pause resource closure')
    for rel in ('ui/models/model_button.igb', 'ui/models/model_button_highlight.igb'):
        path = ctx.x1_path(rel)
        if path is None:
            raise ValueError('original shared menu model is missing: ' + rel)
        ctx.write_bytes(rel, path.read_bytes(), source='frontend:original shared menu chrome from disc')
    dialog = ctx.x1_path('ui/hud/dialog.igb')
    if dialog is None:
        raise ValueError('original dialog frame is missing')
    players_frame, report['players_frame'] = M.fit_flat_panel(dialog.read_bytes(), (-147, -164, 147, 65), opaque=True)
    ctx.write_bytes(PLAYERS_PANEL + '.IGB', players_frame,
                    source='frontend:classic opaque frame around native player list/textbox')
    _, (pl, pb, pr, pt) = objectives_layout()['object_screen']
    objective_frame, report['objectives_frame'] = M.fit_flat_panel(
        dialog.read_bytes(), (pl, pb, pr, pt), opaque=True)
    ctx.write_bytes(OBJECTIVES_PANEL + '.IGB', objective_frame,
                    source='frontend:full-screen classic objective frame')
    icon_frame, _ = M.fit_flat_panel(dialog.read_bytes(), OBJECTIVES_PICTURE_FRAME, border=5, opaque=True)
    ctx.write_bytes(OBJECTIVES_ICON + '.IGB', icon_frame, source='frontend:classic objective selector')
    # PDA refresh selects this native resource by name, overriding its XML item
    # model. Scope the replacement to the objective selector's own resource.
    ctx.write_bytes('UI/models/m_pda_icon_screen.IGB', icon_frame,
                    source='frontend:classic native dynamic objective selector')
    original_colors = list(ctx.read_x1_xml('data/colors.xml'))
    tint = T.rgba(original_colors[7].get('value'))[:3]
    players_select = ctx.base_index.path('UI/models/m_pda_players_select.IGB')
    if players_select is None:
        raise ValueError('native player selection geometry is missing')
    ctx.write_bytes(PLAYERS_SELECT + '.IGB', M.tint_vertex_colors(players_select.read_bytes(), tint),
                    source='frontend:native player selection with the original palette')
    ctx.write_bytes(OBJECTIVES_FOCUS + '.IGB', M.tint_panel_materials(icon_frame, tint),
                    source='frontend:classic focus frame fitted around native objective picture')
    report.update(colors=len(colors), styles=len(styles), color_ids=ids,
                  color_headroom=T.COLOR_LIMIT - len(colors), style_headroom=T.STYLE_LIMIT - len(styles))
    return report
