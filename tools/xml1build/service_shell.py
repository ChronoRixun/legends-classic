"""Shared classic frames around native mansion-service widget contracts."""
from __future__ import annotations

import copy
import math

from . import igb_file as G, menu_conversion as M, pause_appearance as P


def model_bounds(data):
    """The root culling box is the model's final local coordinate contract."""
    graph = G.IgbFile(data)
    scenes = graph.objects_of('igSceneInfo')
    root = graph.obj(scenes[0].get(5)) if len(scenes) == 1 else None
    box = graph.obj(root.get(3)) if root else None
    if box is not None and box.name == 'igAABox':
        low, high = box.get(2), box.get(3)
    else:
        # A few native flat panels have no group bound. With no transforms,
        # every child box is already in model coordinates and may be unioned.
        boxes = graph.objects_of('igAABox')
        if graph.objects_of('igTransform') or not boxes or len(boxes) > 256:
            raise G.IgbError('service panel has no unambiguous model bounds')
        low = [min(box.get(2)[i] for box in boxes) for i in range(3)]
        high = [max(box.get(3)[i] for box in boxes) for i in range(3)]
    if any(not math.isfinite(v) for v in (*low, *high)):
        raise G.IgbError('service panel has nonfinite model bounds')
    return low, high


def model_rectangle(data):
    low, high = model_bounds(data)
    rect = (low[0], low[2], high[0], high[2])
    if any(not math.isfinite(v) for v in rect) or rect[0] >= rect[2] or rect[1] >= rect[3]:
        raise G.IgbError('service panel has invalid root bounds')
    return rect


def retired_layout(data, names):
    graph = G.IgbFile(data)
    anchors = {o.get(2) for o in graph.objects_of('igHashedUserInfo')}
    return {name: ((-4096, -80, -4096), (-1, -1, 1, 1)) for name in names if name in anchors}


def frame_problems(data, expected, *, depth=None):
    graph = G.IgbFile(data)
    points = []
    for array in graph.objects_of('igVertexArray1_1'):
        refs = graph.ref_list(array.get(2))
        row = graph.block_floats(refs[0]) if refs else []
        points.extend(zip(row[0::3], row[1::3], row[2::3]))
    if not points or graph.objects_of('igTransform'):
        return ['service frame is not flat']
    actual = (min(v[0] for v in points), min(v[2] for v in points),
              max(v[0] for v in points), max(v[2] for v in points))
    if any(not math.isfinite(v) for v in actual) or any(abs(a-b)>1e-4 for a,b in zip(actual, expected)):
        return ['service frame does not fit native model bounds']
    if depth is not None and any(not math.isfinite(v[1]) or v[1] < depth[0]-.001 or
                                 v[1] > depth[1]+.001 for v in points):
        return ['service frame obscures the native text layer']
    return []


def tree(native, scene, models, retired, lists=()):
    root = copy.deepcopy(native)
    root.attrib.update(igb=scene, lighting='true')
    for item in root.findall('item'):
        name = item.get('name', '')
        if name in retired:
            item.attrib.update(model='ui/models/model_hide', hide='true', enabled='false')
        elif item.get('model') in models:
            item.set('model', models[item.get('model')])
        if item.get('style'):
            item.set('style', P.LIST_STYLE if name in lists else P.BODY_STYLE)
        for event in item.findall('onfocus'):
            if event.get('model') in models:
                event.set('model', models[event.get('model')])
    return root


def control_problems(native, converted, retired=()):
    """Appearance may not alter service modes, callbacks, permissions or economy."""
    errors = P.native_text_problems(native, converted)
    for key in set(native.attrib) | set(converted.attrib):
        if key not in ('igb', 'lighting') and native.get(key) != converted.get(key):
            errors.append('service native root changed: ' + key)
    items = {e.get('name'): e for e in converted.findall('item')}
    visual = {'model', 'style', 'animtext_scene'}
    for old in native.findall('item'):
        name = old.get('name', '')
        new = items.get(name)
        if new is None:
            errors.append('service native item missing: ' + name)
            continue
        allowed = visual | ({'hide', 'enabled'} if name in retired else set())
        for key in set(old.attrib) | set(new.attrib):
            if key not in allowed and old.get(key) != new.get(key):
                errors.append('service native item changed: ' + name + '.' + key)
        before, after = list(old), list(new)
        if len(before) != len(after):
            errors.append('service native events changed: ' + name)
        else:
            for one, two in zip(before, after):
                if one.tag != two.tag or {k:v for k,v in one.attrib.items() if k != 'model'} != \
                        {k:v for k,v in two.attrib.items() if k != 'model'}:
                    errors.append('service native event callback changed: ' + name)
    return errors


def frame(ctx, source, native_rel, output, *, tint=None):
    native = ctx.base_index.path(native_rel + '.IGB')
    if native is None:
        raise ValueError('native service panel missing: ' + native_rel)
    rect = model_rectangle(native.read_bytes())
    border = min(8, (min(rect[2]-rect[0], rect[3]-rect[1])-1)/3)
    data, report = M.fit_flat_panel(source, rect, border=border, opaque=True)
    low, high = model_bounds(native.read_bytes())
    # Native counter/label depths vary by panel. The inventory ribbon, for
    # example, must remain behind its text at local -10 rather than inheriting
    # the dialog frame's local -20 depth and covering the numbers.
    layer = (low[1], high[1]) if low[1] < high[1] else (low[1]-.0001, high[1]+.0001)
    data = M.foreground_chrome(data, layer=layer)
    if tint is not None:
        data = M.tint_panel_materials(data, tint)
    ctx.write_bytes(output + '.IGB', data, source='frontend:classic frame at native service bounds')
    return report
