"""Classic-compatible native image viewer with readable device-aware paging hints."""
from __future__ import annotations

import copy
from . import menu_conversion as M, pause_appearance as P

SCENE = 'lc_image_viewer'
LAYOUT = {
    'desctext1': ((40,-880,24),(0,-8,140,8)),
    'desctext2': ((320,-880,24),(-65,-8,65,8)),
    'desctext3': ((430,-880,24),(-65,-8,65,8)),
}


def viewer_scene(native):
    # This PC compatibility scene already contains the classic flat frame. Keep
    # its three paging anchors; the original console scene has only one hint.
    data,report = M.convert_scene(native)
    return M.place_anchors(data,LAYOUT),report


def viewer_tree(native):
    root = copy.deepcopy(native)
    root.attrib.update(igb=SCENE,lighting='true')
    for item in root.findall('item'):
        if item.get('name') in LAYOUT:
            item.attrib.update(style=P.BODY_STYLE,neverfocus='true')
            if item.get('name') == 'desctext1':
                item.set('textalignx','TEXT_ALIGN_LEFT')
    return root


def problems(native, converted):
    errors = P.native_text_problems(native,converted)
    for key in ('type','no_stack','anyinput','depth'):
        if native.get(key) != converted.get(key):
            errors.append('image viewer native paging/return contract changed: '+key)
    return errors


def write(ctx):
    from . import frontend as F
    native = ctx.base_index.path('UI/menus/menu_image_viewer.IGB')
    if native is None:
        raise ValueError('native compatible image viewer scene is missing')
    data,report = viewer_scene(native.read_bytes())
    halves = []
    for ext in ('.XMLB','.engb'):
        before = ctx.read_base_xmlb('UI/menus/image_viewer'+ext)
        root = viewer_tree(before)
        errors = problems(before,root)+M.widget_problems(root,data)
        if errors:
            raise ValueError('; '.join(errors))
        halves.append(root)
    ctx.write_bytes(f'UI/menus/{SCENE}.IGB',data,source='frontend:compatible viewer frame and foreground PC paging hints')
    ctx.write_xmlb_pair('UI/menus/image_viewer',*halves,source='frontend:classic viewer, native PC paging/return')
    package = ctx.read_base_xmlb(F.MENU_PKG_DIR+'/image_viewer.PKGB')
    ctx.write_xmlb(F.MENU_PKG_DIR+'/image_viewer',M.package_for(halves[0],inherited=package),('.PKGB',),
                    source='frontend:classic viewer resource closure')
    return report
