"""Disc-authored loading chrome around the native PC loading service."""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET

from . import igb_file as G, menu_conversion as M, menu_scene as S

SCENE = 'lc_loading'


retire_camera = S.retire_camera


def loading_scene(original, native, spinner=None):
    g = G.IgbFile(retire_camera(native))
    # This native loader predates hashed widget aliases: its one raw transform
    # name is the whole binding. Do not weaken the shared triple-alias contract.
    fields = [(o, f) for o in g.objects for f in o.fields.values()
              if f.type == 'igStringMetaField' and f.value == 'loadstatus']
    if len(fields) != 1 or fields[0][0].name != 'igTransform':
        raise G.IgbError('loading needs its single raw status anchor')
    field = fields[0][1]
    g.buf[field.offset + 4:field.offset + 14] = b'old_status'
    native = g.edited()
    artwork, report = M.convert_scene(original)
    result, report['attachment'] = S.attach(native, artwork)
    if spinner is not None:
        animation, report['spinner_camera'] = M.convert_scene(spinner)
        result, report['spinner_attachment'] = S.attach(retire_camera(result), animation)
    result = M.place_anchors(result, {'loadstatus': ((53, -880, 27), (0, -8, 400, 8))})
    return result, report


def loading_tree(native):
    root = copy.deepcopy(native)
    root.set('igb', SCENE)
    root.set('lighting', 'true')
    ET.SubElement(root, 'item', name='loadstatus', gamevar='loadstatus', style='STYLE_LC_BODY',
                  type='MENU_ITEM_TEXT', textalignx='TEXT_ALIGN_LEFT', textaligny='TEXT_ALIGN_CENTER_Y')
    # Keep the native helper/loader lifecycle. Its console-sequel logo/effect are
    # cosmetic; the converted scene supplies the first game's loading chrome.
    return root


def write(ctx):
    from . import frontend as F
    original = ctx.x1_path('ui/menus/menu_loading.igb')
    native = ctx.base_index.path('UI/menus/x2m_loading.IGB')
    if original is None or native is None:
        raise ValueError('loading scene input is missing')
    spinner = ctx.x1_path('ui/menus/loading_anim.igb')
    if spinner is None:
        raise ValueError('original loading animation is missing')
    data, report = loading_scene(original.read_bytes(), native.read_bytes(), spinner.read_bytes())
    root = loading_tree(ctx.read_base_xmlb('UI/menus/loading.XMLB'))
    ctx.write_bytes(f'UI/menus/{SCENE}.IGB', data, source='frontend:classic loading scene with native anchors')
    ctx.write_xmlb('UI/menus/loading', root, source='frontend:classic chrome, native loading service')
    helper = ctx.read_base_xmlb('UI/menus/loading_back.XMLB')
    for item in helper.findall('item'):
        item.attrib.update(hide='true', enabled='false')
        if item.get('model'):
            item.set('model', 'ui/models/model_hide')
    ctx.write_xmlb('UI/menus/loading_back', helper, source='frontend:retired sequel loading decoration')
    inherited = ctx.read_base_xmlb(F.MENU_PKG_DIR + '/loading.PKGB')
    package = M.package_for(root, inherited=inherited)
    ctx.write_xmlb(F.MENU_PKG_DIR + '/loading', package, ('.PKGB',),
                    source='frontend:classic loading resource closure')
    return report
