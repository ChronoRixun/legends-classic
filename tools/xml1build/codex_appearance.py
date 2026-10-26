"""Disc Codex panels and actor backdrop, retaining native list/detail modes."""
from __future__ import annotations

import copy

from . import menu_conversion as M, menu_scene as S, pause_appearance as P

SCENE, BACK = 'lc_codex', 'lc_codex_back'
# Retail itself names this retired decorative panel without a scene anchor.
OPTIONAL_ANCHORS = ('panel_codex',)
LAYOUT = {
    'list': ((141, -150, 286), (-102, -72, 102, 72)),
    'desc': ((252, -150, 133), (-213, -60, 213, 60)),
    'name': ((357, -150, 215), (-80, -10, 80, 10)),
    'title': ((256, -150, 372), (-150, -8, 150, 8)),
    'up_arrow': ((142, -150, 359), (-8, -6, 8, 6)),
    'down_arrow': ((142, -150, 211), (-8, -6, 8, 6)),
}
for _i, _x in enumerate((78, 200, 320, 390, 445), 1):
    LAYOUT[f'desctext{_i}'] = ((_x, -150, 28), (-65, -9, 65, 9))


def tree(native):
    root = copy.deepcopy(native)
    root.attrib.update(igb=SCENE, lighting='true')
    for helper in root.findall('items'):
        helper.set('igb', BACK)
    for precache in root.findall('precache'):
        if precache.get('filename') == 'ui/menus/x2m_codex_back':
            precache.set('filename', 'ui/menus/' + BACK)
    for item in root.findall('item'):
        name = item.get('name', '')
        item.attrib.pop('animtext_scene', None)
        if item.get('type') == 'MENU_ITEM_MODEL':
            item.attrib.update(model='ui/models/model_hide', hide='true', enabled='false')
        elif item.get('style'):
            item.set('style', P.LIST_STYLE if name == 'list' else P.BODY_STYLE)
        if name in ('name', 'title'):
            item.set('textalignx', 'TEXT_ALIGN_CENTER_X')
    return root


def control_problems(native, converted):
    errors = P.native_text_problems(native, converted)
    for key in ('type', 'name', 'all_controllers', 'desctext5'):
        if native.get(key) != converted.get(key):
            errors.append('Codex native root contract changed: ' + key)
    items = {e.get('name'): e for e in converted.findall('item')}
    for old in native.findall('item'):
        new = items.get(old.get('name'))
        if new is None:
            errors.append('Codex native item missing: ' + old.get('name', ''))
            continue
        for key in ('type', 'mode', 'usecmd', 'up', 'down', 'left', 'right', 'startactive', 'neverfocus'):
            if old.get(key) != new.get(key):
                errors.append('Codex native control changed: ' + old.get('name', '') + '.' + key)
    return errors


def scene(original, native):
    art, report = M.convert_scene(S.static_model(M.opaque_materials(original), allow_transforms=True))
    art = M.foreground_chrome(art)
    aliases = {n: 'lc_codex_art_' + n for n in ('list', 'desc', 'name', 'desctext1', 'desctext2', 'desctext3')}
    art, _ = M.rename_aliases(art, aliases)
    data, report['attachment'] = S.attach(S.retire_camera(native), art)
    return M.place_anchors(data, LAYOUT), report


def write(ctx, halves):
    from . import frontend as F, menu_theme as T
    original = ctx.x1_path('ui/menus/menu_codex.igb')
    native = ctx.base_index.path('UI/menus/x2m_codex.IGB')
    if original is None or native is None:
        raise ValueError('Codex scene input missing')
    data, report = scene(original.read_bytes(), native.read_bytes())
    for root in halves:
        errors = M.widget_problems(root, data, optional_anchors=OPTIONAL_ANCHORS)
        if errors:
            raise ValueError('; '.join(errors))
    ctx.write_bytes('UI/menus/' + SCENE + '.IGB', data, source='frontend:original Codex panels with native modes')
    backdrop = ctx.x1_path('ui/menus/menu_codex_back.igb')
    if backdrop is None:
        raise ValueError('original Codex actor backdrop missing')
    ctx.write_bytes('UI/menus/' + BACK + '.IGB', backdrop.read_bytes(), source='frontend:original Codex actor backdrop')
    # Both games use the same actor/platform roles in this helper. Keep the
    # native class, preview callbacks and resource selection; only its scene moves.
    helper = ctx.read_base_xmlb('UI/menus/codex_back.XMLB')
    ctx.write_xmlb('UI/menus/codex_back', helper, source='frontend:native Codex actor helper')
    platform = ctx.x1_path('ui/models/model_codex_platform.igb')
    if platform is None:
        raise ValueError('original Codex platform missing')
    ctx.write_bytes('UI/models/model_codex_platform.IGB', platform.read_bytes(), source='frontend:original Codex actor platform')
    tint = T.rgba(list(ctx.read_x1_xml('data/colors.xml'))[7].get('value'))[:3]
    selection, _ = M.fit_flat_panel(ctx.x1_path('ui/hud/dialog.igb').read_bytes(),
                                     (0, -7, 204, 7), border=3, opaque=True)
    selection = M.foreground_chrome(selection, layer=(2, 4))
    ctx.write_bytes(F.CODEX_SELECT_X1 + '.IGB', M.tint_panel_materials(selection, tint),
                    source='frontend:classic Codex whole-row selection')
    package = M.package_for(halves[0], inherited=ctx.read_base_xmlb(F.MENU_PKG_DIR + '/codex.PKGB'))
    ctx.write_xmlb(F.MENU_PKG_DIR + '/codex', package, ('.PKGB',), source='frontend:classic Codex resource closure')
    return report
