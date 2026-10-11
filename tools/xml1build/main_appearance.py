"""Bounded main-menu palette and scene aliases; assets are read from the player's disc.

The PC model parser defaults to an invisible model (0x5c5080). Its main-menu open
method hides desctext1 (0x5c99e1), so the imported help anchor needs a separate name.
Styles use modern colour fields, not the first game's legacy colour attribute.
"""
from __future__ import annotations

import copy
import math
import xml.etree.ElementTree as ET

from . import igb_file as G

MAIN_STYLE = 'STYLE_LC_MAIN'
HELP_STYLE = 'STYLE_LC_MAIN_DESC'
HELP_NODE = 'helptext1'                         # same byte length as the original alias
HELP_Z = 4.0                                  # below the eight PC rows, inside the visible footer
COLOR_LIMIT = 75
STYLE_LIMIT = 32
LAYOUTS = ('classic', 'widescreen')
WIDE_X = 48.0                                 # rigid composition offset; no mesh/font stretching


def _rgba(value):
    values = tuple(float(v) for v in (value or '').split())
    if len(values) != 4 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in values):
        raise ValueError('menu palette needs four finite colour channels in 0..1')
    return values


def palette_styles(base_colors, base_styles, original_colors):
    """Append only the original main's colours/styles; preserve every existing PC entry.

    Reuse identical non-pulsing colours and allocate unoccupied IDs deterministically.
    Refuse either native table ceiling before returning any output.
    """
    colors, styles = copy.deepcopy(base_colors), copy.deepcopy(base_styles)
    used = {}
    for entry in colors:
        idx = int(entry.get('id', '-1'))
        if not 0 <= idx < COLOR_LIMIT or idx in used:
            raise ValueError('PC palette has an invalid or duplicate colour ID')
        _rgba(entry.get('value'))
        used[idx] = entry
    source = list(original_colors)
    mapping = {}
    for idx in (0, 5, 9, 10):
        if idx >= len(source):
            raise ValueError('original palette lacks a main-menu colour')
        value = source[idx].get('value')
        rgba = _rgba(value)
        found = next((key for key, entry in sorted(used.items())
                      if not entry.get('pulse') and _rgba(entry.get('value')) == rgba), None)
        if found is None:
            found = next((key for key in range(COLOR_LIMIT) if key not in used), None)
            if found is None:
                raise ValueError('no free native palette ID for the original main menu')
            used[found] = ET.SubElement(colors, 'color', {'id': str(found), 'value': value})
        mapping[idx] = str(found)
    names = [entry.get('name') for entry in styles]
    if len(names) != len(set(names)):
        raise ValueError('PC style table has duplicate names')
    for entry in list(styles):
        if entry.get('name') in (MAIN_STYLE, HELP_STYLE):
            styles.remove(entry)
    if len(styles) + 2 > STYLE_LIMIT:
        raise ValueError('original main styles exceed the native style table')
    for name, font, normal, focus, disabled, allow in (
            (MAIN_STYLE, 'big', 9, 10, 5, 'true'),
            (HELP_STYLE, 'medium', 0, 0, 5, 'false')):
        ET.SubElement(styles, 'style', {'name': name, 'font': font,
            'color_nofocus': mapping[normal], 'color_focus': mapping[focus],
            'color_highlight': mapping[focus], 'color_disabled': mapping[disabled],
            'allow_focus': allow, 'focus_time': '0'})
    return colors, styles, mapping


def help_alias(data, source_name='desctext1', target_name=HELP_NODE, z=HELP_Z):
    """Rename the transform and its serialized binding aliases, keeping byte sizes intact.

    A transform rename alone does not change the engine's component lookup: the
    igHashedUserInfo and igStringValue aliases must follow it. Refuse unknown layouts.
    """
    if len(source_name.encode('ascii')) != 9 or len(target_name.encode('ascii')) != 9:
        raise G.IgbError('main help aliases must fit the existing nine-byte names')
    g = G.IgbFile(data)
    aliases = []
    allowed = {'igTransform', 'igHashedUserInfo', 'igStringValue'}
    transforms = []
    for obj in g.objects:
        for field in obj.fields.values():
            if field.type == 'igStringMetaField' and field.value == source_name:
                if not obj.decoded or obj.name not in allowed:
                    raise G.IgbError('unsupported main help alias owner')
                aliases.append(field)
                if obj.name == 'igTransform':
                    transforms.append(obj)
    if len(aliases) != 3 or len(transforms) != 1:
        raise G.IgbError('main help needs its transform and two binding aliases')
    for field in aliases:
        g.buf[field.offset + 4:field.offset + 13] = target_name.encode('ascii')
    g.set_floats(transforms[0], 8, [z], 14)
    out = g.edited()
    check = G.IgbFile(out)
    if len(out) != len(data) or any(field.value == source_name for obj in check.objects
                                   for field in obj.fields.values()):
        raise G.IgbError('main help alias verification failed')
    return out, {'aliases': len(aliases), 'node': target_name, 'z': z}


def write_styles(ctx):
    original = ctx.read_x1_xml('data/colors.xml')
    if original is None:
        raise ValueError('original palette is missing')
    colors, styles, mapping = palette_styles(ctx.read_base_xmlb('Data/colors.XMLB'),
                                             ctx.read_base_xmlb('Data/styles.XMLB'), original)
    ctx.write_xmlb('Data/colors', colors, source='frontend:bounded original main palette')
    ctx.write_xmlb('Data/styles', styles, source='frontend:original main styles in PC schema')
    return {'color_ids': mapping, 'colors': len(colors), 'styles': len(styles)}


def widescreen_scene(data, dx=WIDE_X):
    """Move logo, panels, text, hit bounds and lights together; leave the menu camera fixed.

    The engine already preserves aspect ratio. Refuse layouts the shared reader
    cannot move completely, including shared world/local bounds.
    """
    from . import frontend as F
    g = G.IgbFile(data)
    frame = F._scene_frame(g)
    if frame['problems']:
        raise G.IgbError('; '.join(frame['problems']))
    camera = frame['camera_transform']
    if any(abs(a - b) > 1e-4 for a, b in zip(camera.get(8)[12:15], F.MENU_CAMERA_POS)):
        raise G.IgbError('widescreen main needs the PC menu camera')
    counts = {'transforms': 0, 'bounds': 0, 'vertices': 0, 'lights': 0}
    for obj in frame['transforms'].values():
        if obj.ref != camera.ref:
            g.set_floats(obj, 8, [obj.get(8)[12] + dx], 12)
            counts['transforms'] += 1
    for ref in frame['bounds']:
        box = g.obj(ref)
        if box is None or not box.decoded or not g.isa(box, 'igAABox'):
            raise G.IgbError('unsupported widescreen main bound')
        for slot in (2, 3):
            g.set_floats(box, slot, [box.get(slot)[0] + dx])
        counts['bounds'] += 1
    for array in frame['vertex_arrays'].values():
        blocks = g.ref_list(array.get(2))
        count, fmt = array.get(3), array.get(6)
        block = g.block(blocks[0]) if blocks else None
        if not isinstance(fmt, int) or not fmt & 1 or not isinstance(count, int) or \
                block is None or block[1] != 12 * count:
            raise G.IgbError('unsupported widescreen main vertex positions')
        xyz = g.block_floats(blocks[0])
        for i in range(0, len(xyz), 3):
            xyz[i] += dx
        g.set_block_floats(blocks[0], xyz)
        counts['vertices'] += count
    for ref in frame['lights']:
        light = g.obj(ref)
        if light.fields.get(6) is None or light.fields[6].type != 'igVec3fMetaField':
            raise G.IgbError('unsupported widescreen main light position')
        g.set_floats(light, 6, [light.get(6)[0] + dx])
        counts['lights'] += 1
    return g.edited(), {'layout': 'widescreen', 'x': dx, **counts}
