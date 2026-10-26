"""Classic Review chrome and disc props over the native four-tab service."""
from __future__ import annotations

import copy
import struct
import xml.etree.ElementTree as ET

from . import igb_file as G, menu_conversion as M, menu_scene as S
from . import pause_appearance as P

SCENE = 'lc_review'
BACK = 'lc_review_back'
PROP = 'lc_review_prop'
KINDS = ('load', 'cin', 'comic', 'concept')
TAB = 'ui/models/lc_review_tab'
FOCUS = 'ui/models/lc_review_tab_focus'
SELECT = 'ui/models/lc_review_select'


def layout():
    result = {
        'list': ((143, -150, 189), (-102, -111, 102, 111)),
        'title': ((48, -150, 332), (0, -10, 190, 10)),
        'up_arrow': ((142, -150, 301), (-8, -6, 8, 6)),
        'down_arrow': ((142, -150, 77), (-8, -6, 8, 6)),
    }
    for i, x in enumerate((80, 197, 314, 431), 1):
        for suffix in ('text', 'focus'):
            result[f'option{i:02d}_{suffix}'] = ((x, -150 if suffix == 'text' else -120, 365),
                                                  (-54, -13, 54, 13))
    for i, x in enumerate((70, 160, 285, 410, 470), 1):
        result[f'desctext{i}'] = ((x, -150, 29), (-60, -9, 60, 9))
    return result


def tree(native):
    root = copy.deepcopy(native)
    root.attrib.update(igb=SCENE, lighting='true')
    ET.SubElement(root, 'items', file=BACK, igb=BACK, perspective_camera='true', lighting='true')
    for item in root.findall('item'):
        name = item.get('name', '')
        item.attrib.pop('animtext_scene', None)
        if name.startswith('option') and name.endswith('_text'):
            number = int(name[6:8])
            item.set('style', P.LIST_STYLE)
            for event in list(item.findall('onfocus')):
                item.remove(event)
            ET.SubElement(item, 'onfocus', item=f'option{number:02d}_focus',
                          type='focus', model=FOCUS, loop='1')
            ET.SubElement(item, 'onfocus', item=f'option{number:02d}_focus',
                          type='nofocus', model=TAB)
            ET.SubElement(item, 'onfocus', item=PROP, type='focus',
                          model=f'ui/menus/lc_review_prop_{KINDS[number-1]}', loop='1')
        elif name.startswith('option') and name.endswith('_focus'):
            item.attrib.update(model=TAB, animate='true')
        elif name == 'list':
            item.set('style', P.LIST_STYLE)
            # Preserve both native columns, fitting the duration inside the
            # original list pane rather than the sequel's full-width list.
            item.set('columns', '2 175 TEXT_ALIGN_LEFT 0 TEXT_ALIGN_RIGHT')
            for event in item.findall('onfocus'):
                if event.get('type') == 'list_focus':
                    event.set('model', SELECT)
        elif item.get('type') == 'MENU_ITEM_MODEL':
            item.attrib.update(model='ui/models/model_hide', hide='true', enabled='false')
        elif item.get('style'):
            item.set('style', P.BODY_STYLE)
        if name == 'title':
            item.set('textalignx', 'TEXT_ALIGN_LEFT')
    return root


def control_problems(native, converted):
    problems = P.native_text_problems(native, converted)
    if converted.get('type') != native.get('type'):
        problems.append('Review native class changed')
    items = {e.get('name'): e for e in converted.findall('item')}
    for old in native.findall('item'):
        new = items.get(old.get('name'))
        if new is None:
            problems.append('Review native item missing: ' + old.get('name', ''))
            continue
        for key in ('type', 'mode', 'usecmd', 'up', 'down', 'left', 'right', 'startactive', 'neverfocus'):
            if new.get(key) != old.get(key):
                problems.append('Review control changed: ' + old.get('name', '') + '.' + key)
    return problems


def scene(original, native):
    art, report = M.convert_scene(S.static_model(M.opaque_materials(original), allow_transforms=True))
    art = M.foreground_chrome(art)
    art, _ = M.rename_aliases(art, {n: 'lc_review_art_' + n for n in
                                        ('list', 'title', 'text', 'desctext1', 'desctext2')})
    data, report['attachment'] = S.attach(S.retire_camera(native), art)
    return M.place_anchors(data, layout()), report


def prop_helper(native, original):
    """Use a native model anchor with the original perspective camera.

    Only the helper's camera/light/anchor graph is reachable. Its original
    preview meshes remain serialized but cannot draw behind the selected prop.
    """
    g, source = G.IgbFile(native), G.IgbFile(original)
    scene_info = g.objects_of('igSceneInfo')[0]
    root = g.obj(scene_info.get(5))
    children = g.obj(root.get(7))
    refs = g.list_items(children.ref)
    kept = [ref for ref in refs if g.obj(ref).name == 'igLightSet' or
            g.obj(ref).name == 'igTransform' and g.obj(ref).get(2) in ('model_platform', 'Camera01')]
    if len(kept) != 3 or g.block(children.get(4))[1] != len(refs) * 4:
        raise G.IgbError('Review helper has unexpected native root children')
    offset, _ = g.block(children.get(4))
    struct.pack_into('<' + 'i' * len(kept), g.buf, offset, *kept)
    for slot in (2, 3):
        struct.pack_into('<i', g.buf, children.fields[slot].offset, len(kept))
    native_camera = next(o for o in g.objects_of('igTransform') if o.get(2) == 'Camera01')
    original_camera = next(o for o in source.objects_of('igTransform') if o.get(2) == 'Camera01')
    g.set_floats(native_camera, 8, original_camera.get(8))
    if 11 in native_camera.fields:
        struct.pack_into('<i', g.buf, native_camera.fields[11].offset, -1)
    cameras = g.objects_of('igCamera')
    selected = source.objects_of('igCamera')[0]
    for camera in cameras:
        for slot in (8, 9, 10, 12, 13):
            g.set_floats(camera, slot, selected.get(slot))
    data, _ = M.rename_aliases(g.edited(), {'model_platform': PROP})
    return M.place_anchors(data, {PROP: ((0, 0, 0), (-1, -1, 1, 1))})


def write(ctx, halves):
    from . import frontend as F, menu_theme as T
    art = ctx.x1_path('ui/menus/menu_list_view.igb')
    native = ctx.base_index.path('UI/menus/x2m_review.IGB')
    if art is None or native is None:
        raise ValueError('Review scene input missing')
    data, report = scene(art.read_bytes(), native.read_bytes())
    for root in halves:
        problems = M.widget_problems(root, data, helper_items=(PROP,))
        if problems:
            raise ValueError('; '.join(problems))
    ctx.write_bytes('UI/menus/' + SCENE + '.IGB', data, source='frontend:classic Review list and native tab anchors')
    dialog = ctx.x1_path('ui/hud/dialog.igb').read_bytes()
    button = ctx.x1_path('ui/models/model_button.igb').read_bytes()
    tab, _ = M.fit_flat_panel(button, (-54, -13, 54, 13), border=8, opaque=True)
    tint = T.rgba(list(ctx.read_x1_xml('data/colors.xml'))[7].get('value'))[:3]
    ctx.write_bytes(TAB + '.IGB', tab, source='frontend:classic Review category panel')
    ctx.write_bytes(FOCUS + '.IGB', M.tint_panel_materials(tab, tint), source='frontend:classic Review category focus')
    selection, _ = M.fit_flat_panel(dialog, (0, -7, 204, 7), border=3, opaque=True)
    selection = M.foreground_chrome(selection, layer=(2, 4))
    ctx.write_bytes(SELECT + '.IGB', M.tint_panel_materials(selection, tint), source='frontend:classic Review list selection')
    back = ctx.base_index.path('UI/menus/x2m_codex_back.IGB')
    original_back = ctx.x1_path('ui/menus/menu_list_view_back_cin.igb')
    helper_scene = prop_helper(back.read_bytes(), original_back.read_bytes())
    ctx.write_bytes('UI/menus/' + BACK + '.IGB', helper_scene, source='frontend:original Review camera with native model anchor')
    helper = ET.Element('MENU_ITEMS')
    ET.SubElement(helper, 'item', name=PROP, type='MENU_ITEM_MODEL', neverfocus='true',
                  model='ui/menus/lc_review_prop_load', animate='true')
    ctx.write_xmlb('UI/menus/' + BACK, helper, source='frontend:Review category prop helper')
    for kind in KINDS:
        path = ctx.x1_path('ui/menus/menu_list_view_back_' + kind + '.igb')
        if path is None:
            raise ValueError('original Review prop missing: ' + kind)
        ctx.write_bytes('UI/menus/lc_review_prop_' + kind + '.IGB', path.read_bytes(),
                        source='frontend:original Review category prop from disc')
    package = M.package_for(halves[0], inherited=ctx.read_base_xmlb(F.MENU_PKG_DIR + '/review.PKGB'))
    ctx.write_xmlb(F.MENU_PKG_DIR + '/review', package, ('.PKGB',), source='frontend:classic Review resource closure')
    return report
