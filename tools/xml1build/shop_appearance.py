"""Classic Forge/Healer chrome; the native shop economy and services are intact."""
from __future__ import annotations

from . import menu_conversion as M, menu_theme as T, service_shell as H

SCENE = 'lc_shop'
FRAMES = {
    'ui/models/m_shop_panel': 'ui/models/lc_shop_panel',
    'ui/models/m_shop_options_panel': 'ui/models/lc_shop_options',
    'ui/models/m_team_browse_iteminven': 'ui/models/lc_shop_inventory',
    'ui/models/m_team_helpbar': 'ui/models/lc_shop_help',
    'ui/models/m_shop_option_focus': 'ui/models/lc_shop_tab_focus',
    'ui/models/m_shop_option_nofocus': 'ui/models/lc_shop_tab',
}
RETIRED = ('track01', 'track02', 'item_inven_bracket', 'options_hinge', 'shop_hinge01', 'shop_hinge02',
           'helpbar_hinge_left', 'helpbar_hinge_right', 'shop_focus01', 'shop_focus02', 'shop_light01', 'shop_light02')


# --loot xml1 (DESIGN 5.3): the first game's shops have no Training; the DLL cycles two tabs and labels the third
# empty, the menu file hides its control (and the focus model that follows it)
TRAINING = ('shop_option03', 'shop_option03_focus')


def extra_retired(ctx):
    """controls this build hides beyond RETIRED (their hide / enabled may differ from the native menu)"""
    from . import loot as LOOT
    return TRAINING if LOOT.selected(ctx) else ()


def tree(native, hide=()):
    root = H.tree(native, SCENE, FRAMES, RETIRED, lists=('list',))
    for item in root.findall('item'):
        if item.get('name') in hide:
            item.attrib.update(hide='true', enabled='false')
    return root


def write(ctx):
    from . import frontend as F
    original = ctx.x1_path('ui/hud/dialog.igb')
    native = ctx.base_index.path('UI/menus/x2m_shop.IGB')
    if original is None or native is None:
        raise ValueError('classic shop frame/native scene missing')
    source = original.read_bytes()
    tint = T.rgba(list(ctx.read_x1_xml('data/colors.xml'))[7].get('value'))[:3]
    report = {'frames': {}}
    for before, after in FRAMES.items():
        report['frames'][after] = H.frame(ctx, source, before, after,
                                         tint=tint if before.endswith('_focus') else None)
        # Shop refresh loads its two tab models by native name as well as the
        # definition's focus events. These resources belong only to this service.
        if before in ('ui/models/m_shop_option_focus', 'ui/models/m_shop_option_nofocus'):
            ctx.write_bytes(before + '.IGB', ctx.out_index.path(after + '.IGB').read_bytes(),
                            source='frontend:classic native dynamic shop tab resource')
    selected = ctx.base_index.path('UI/models/m_shop_select.IGB')
    if selected is None:
        raise ValueError('native shop list selection missing')
    ctx.write_bytes('UI/models/m_shop_select.IGB', M.tint_vertex_colors(selected.read_bytes(), tint),
                    source='frontend:native shop selection with classic palette')
    layout = H.retired_layout(native.read_bytes(), RETIRED)
    scene = M.place_anchors(native.read_bytes(), layout)
    ctx.write_bytes('UI/menus/' + SCENE + '.IGB', scene, source='frontend:native shop anchors with retired sequel ornament')
    halves = []
    for ext in ('.XMLB', '.engb'):
        before = ctx.read_base_xmlb('UI/menus/shop' + ext)
        after = tree(before, extra_retired(ctx))
        errors = H.control_problems(before, after, RETIRED + extra_retired(ctx))
        if errors:
            raise ValueError('; '.join(errors))
        halves.append(after)
    ctx.write_xmlb_pair('UI/menus/shop', *halves, source='frontend:classic Forge/Healer shell, native economy')
    inherited = ctx.read_base_xmlb(F.MENU_PKG_DIR + '/shop.PKGB')
    package = M.package_for(halves[0], inherited=inherited)
    ctx.write_xmlb(F.MENU_PKG_DIR + '/shop', package, ('.PKGB',), source='frontend:classic shop resource closure')
    return report
