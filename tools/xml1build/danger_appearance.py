"""Classic Danger Room shell around native courses, roster and reward callbacks."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from . import menu_conversion as M, menu_theme as T, service_shell as H

SCENE, BACK = 'lc_danger', 'lc_danger_back'
FRAMES = {
    'ui/models/m_danger_panel': 'ui/models/lc_danger_panel',
    'ui/models/m_danger_option_panel': 'ui/models/lc_danger_options',
    'ui/models/m_danger_option_panel2': 'ui/models/lc_danger_options_alt',
    'ui/models/m_team_helpbar': 'ui/models/lc_danger_help',
    'ui/models/m_danger_option_focus': 'ui/models/lc_danger_tab_focus',
}
RETIRED = ('track01', 'track02', 'helpbar_hinge_left', 'helpbar_hinge_right',
           'hinge1', 'hinge2', 'hinge3', 'hinge4', 'options_bracket')


def tree(native):
    root = H.tree(native, SCENE, FRAMES, RETIRED, lists=('list',))
    ET.SubElement(root, 'items', file=BACK, igb=BACK, perspective_camera='true', lighting='true')
    return root


def write(ctx):
    from . import frontend as F
    original = ctx.x1_path('ui/hud/dialog.igb')
    native = ctx.base_index.path('UI/menus/x2m_dangerroom.IGB')
    backdrop = ctx.x1_path('ui/menus/menu_danger_room_back.igb')
    if original is None or native is None or backdrop is None:
        raise ValueError('classic Danger Room input missing')
    source = original.read_bytes()
    tint = T.rgba(list(ctx.read_x1_xml('data/colors.xml'))[7].get('value'))[:3]
    report = {'frames': {}}
    for before, after in FRAMES.items():
        report['frames'][after] = H.frame(ctx, source, before, after,
                                         tint=tint if before.endswith('_focus') else None)
        if before.startswith('ui/models/m_danger_'):
            ctx.write_bytes(before + '.IGB', ctx.out_index.path(after + '.IGB').read_bytes(),
                            source='frontend:classic dynamic Danger Room panel')
    for name in ('m_danger_panel_select', 'm_danger_panel_select_alt'):
        selected = ctx.base_index.path('UI/models/' + name + '.IGB')
        if selected is None:
            raise ValueError('native Danger Room selection missing: ' + name)
        ctx.write_bytes('UI/models/' + name + '.IGB', M.tint_vertex_colors(selected.read_bytes(), tint),
                        source='frontend:native Danger Room selection with classic palette')
    layout = H.retired_layout(native.read_bytes(), RETIRED)
    ctx.write_bytes('UI/menus/' + SCENE + '.IGB', M.place_anchors(native.read_bytes(), layout),
                    source='frontend:native Danger Room anchors with retired sequel ornament')
    ctx.write_bytes('UI/menus/' + BACK + '.IGB', backdrop.read_bytes(), source='frontend:original Danger Room backdrop')
    ctx.write_xmlb('UI/menus/' + BACK, ET.Element('MENU_ITEMS'), source='frontend:static Danger Room background helper')
    halves = []
    for ext in ('.XMLB', '.engb'):
        before = ctx.read_base_xmlb('UI/menus/danger_room' + ext)
        after = tree(before)
        errors = H.control_problems(before, after, RETIRED)
        if errors:
            raise ValueError('; '.join(errors))
        halves.append(after)
    ctx.write_xmlb_pair('UI/menus/danger_room', *halves, source='frontend:classic Danger Room, native courses and rewards')
    package = M.package_for(halves[0], inherited=ctx.read_base_xmlb(F.MENU_PKG_DIR + '/danger_room.PKGB'))
    ctx.write_xmlb(F.MENU_PKG_DIR + '/danger_room', package, ('.PKGB',), source='frontend:classic Danger Room resource closure')
    return report
