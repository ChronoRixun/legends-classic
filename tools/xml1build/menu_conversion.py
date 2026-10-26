"""Reusable scene, package and widget contracts for classic menu conversions.

Native classes, item names, modes and commands belong to the PC menu. Artwork,
camera framing and explicitly translated styles come from the player's disc.
Font indices use main_fonts' matched classic/PC-fallback atlas and metric pairs.
"""
from __future__ import annotations

import math
import struct
import xml.etree.ElementTree as ET

from . import igb_file as G

ALIAS_OWNERS = frozenset(('igTransform', 'igHashedUserInfo', 'igStringValue'))


def place_anchors(data, layouts):
    """Place native widgets and their hit/text bounds together, without animation drift.

    Each layout is (position xyz, bounds left/bottom/right/top). Only the named
    transform's animation link is detached; sequence objects/keys stay intact.
    Refuse duplicate anchors or shared bounds before returning a modified scene.
    """
    g = G.IgbFile(data)
    for name, (position, bounds) in layouts.items():
        nodes = [o for o in g.objects if o.name == 'igTransform' and o.get(2) == name]
        aliases = [o for o in g.objects if o.name == 'igHashedUserInfo' and o.get(2) == name]
        if len(nodes) != 1 or len(aliases) != 1:
            raise G.IgbError('widget placement needs one transform and bounds alias: ' + name)
        if len(position) != 3 or len(bounds) != 4 or any(not math.isfinite(v) for v in (*position, *bounds)):
            raise G.IgbError('widget placement needs finite position and bounds')
        left, bottom, right, top = bounds
        if left >= right or bottom >= top:
            raise G.IgbError('widget placement has an empty rectangle')
        box = g.obj(aliases[0].get(3))
        if box is None or box.name != 'igAABox' or sum(
                o.get(3) == box.ref for o in g.objects if o.name == 'igHashedUserInfo') != 1:
            raise G.IgbError('widget placement needs unshared native bounds')
        node = nodes[0]
        matrix = [float(i in (0, 5, 10, 15)) for i in range(16)]
        matrix[12:15] = position
        g.set_floats(node, 8, matrix)
        if 11 in node.fields:
            field = node.fields[11]
            if field.type != 'igObjectRefMetaField':
                raise G.IgbError('unsupported widget animation link')
            struct.pack_into('<i', g.buf, field.offset, -1)
        g.set_floats(box, 2, [left, 0, bottom])
        g.set_floats(box, 3, [right, 0, top])
    return g.edited()


def placement_problems(data, layouts):
    """Validate both sides of the render/hit rectangle contract after serialization."""
    g, problems = G.IgbFile(data), []
    for name, (position, bounds) in layouts.items():
        nodes = [o for o in g.objects if o.name == 'igTransform' and o.get(2) == name]
        aliases = [o for o in g.objects if o.name == 'igHashedUserInfo' and o.get(2) == name]
        if len(nodes) != 1 or len(aliases) != 1:
            problems.append('missing or ambiguous placed widget: ' + name)
            continue
        node, box = nodes[0], g.obj(aliases[0].get(3))
        if any(abs(a-b) > 1e-4 for a,b in zip(node.get(8)[12:15], position)) or node.get(11, -1) != -1:
            problems.append('placed widget position/animation drift: ' + name)
        left, bottom, right, top = bounds
        if box is None or box.name != 'igAABox' or any(abs(a-b) > 1e-4 for a,b in
                zip(box.get(2) + box.get(3), [left, 0, bottom, right, 0, top])):
            problems.append('placed widget hit/text bounds drift: ' + name)
    return problems


def rename_aliases(data, mapping):
    """Rename complete binding triples, including unequal-length native item names.

    Rebuild only serialized object records; reference numbers and memory blocks do
    not change. A transform-only rename leaves a broken engine lookup and is refused.
    Unknown owners, alias collisions and missing triples are refused before editing.
    """
    g = G.IgbFile(data)
    if not mapping or len(set(mapping.values())) != len(mapping):
        raise G.IgbError('scene aliases must have distinct destinations')
    present = {f.value for o in g.objects for f in o.fields.values() if f.type == 'igStringMetaField'}
    edits, counts = {}, {}
    for source, target in mapping.items():
        if source == target or not target or len(target) > 128 or not target.isascii():
            raise G.IgbError('unsupported scene alias')
        if target in present:
            raise G.IgbError('scene alias destination already exists')
        fields = [(o, f) for o in g.objects for f in o.fields.values()
                  if f.type == 'igStringMetaField' and f.value == source]
        if (len(fields) != 3 or sum(o.name == 'igTransform' for o, _ in fields) != 1
                or {o.name for o, _ in fields} != ALIAS_OWNERS
                or any(not o.decoded or o.name not in ALIAS_OWNERS for o, _ in fields)):
            raise G.IgbError('scene alias needs a transform and two supported binding aliases')
        raw = target.encode('ascii') + b'\0'
        raw += b'\0' * (-len(raw) % 4)
        for o, f in fields:
            edits.setdefault(o.ref, []).append((f.offset, f.size, struct.pack('<I', len(raw)) + raw))
        counts[source] = len(fields)
    objects = bytearray()
    for o in g.objects:
        record = bytearray(g.buf[o.offset:o.offset + o.size])
        for offset, size, replacement in sorted(edits.get(o.ref, []), reverse=True):
            start = offset - o.offset
            record[start:start + size] = replacement
        struct.pack_into('<I', record, 4, len(record))
        objects += record
    prefix = bytearray(g.buf[:g._obj_start])
    struct.pack_into('<I', prefix, 16, len(objects))
    out = bytes(prefix) + bytes(objects) + bytes(g.buf[g._mem_start:])
    check = G.IgbFile(out)
    for source, target in mapping.items():
        strings = [f.value for o in check.objects for f in o.fields.values() if f.type == 'igStringMetaField']
        if source in strings or strings.count(target) != counts[source]:
            raise G.IgbError('scene aliases did not round-trip')
    if any(check.data[off:off + size] != data[g.blocks[ref][0]:g.blocks[ref][0] + size]
           for ref, (off, size) in check.blocks.items()):
        raise G.IgbError('scene alias rebuild changed a memory block')
    return out, counts


def convert_scene(data, aliases=(), *, count=None):
    """Apply the proven main-menu camera and row-spacing conversions to any shared stack."""
    from . import frontend as F
    framed, camera = F.reframe_menu_igb(data)
    if framed is None:
        raise G.IgbError('; '.join(camera['problems']))
    report = {'camera': camera}
    if count is not None:
        framed, spacing = F.space_menu_buttons(framed, count)
        if framed is None:
            raise G.IgbError('; '.join(spacing['problems']))
        report['spacing'] = spacing
    if aliases:
        framed, report['aliases'] = rename_aliases(framed, dict(aliases))
    return framed, report


def package_for(root, *, inherited=None):
    """Deterministic closure of static menu resources, retaining native dynamic precaches."""
    entries = {(e.tag.lower(), e.get('filename')) for e in inherited or () if e.get('filename')}
    entries.add(('model', 'ui/menus/' + root.get('igb')))
    for e in root.iter():
        if e.tag == 'items':
            entries.add(('model', 'ui/menus/' + e.get('igb')))
            entries.add(('xml', 'ui/menus/' + e.get('file')))
        for key in ('model', 'focusmodel', 'arrowmodel'):
            if e.get(key):
                entries.add(('model', e.get(key)))
        if e.tag == 'precache' and e.get('filename'):
            entries.add((e.get('type'), e.get('filename')))
    pkg = ET.Element('packagedef')
    for kind, name in sorted(entries):
        ET.SubElement(pkg, kind, filename=name)
    return pkg


def widget_problems(root, scene, *, focus_names=(), margin=8, optional_anchors=(), helper_items=()):
    """Validate lookup aliases, focus graph, rectangles and native onfocus item targets."""
    g = G.IgbFile(scene)
    nodes = {o.get(2): o for o in g.objects if o.name == 'igTransform' and o.decoded}
    items = {e.get('name'): e for e in root.findall('item')}
    problems = []
    for name, item in items.items():
        if name not in nodes and name not in optional_anchors:
            problems.append(f'missing scene anchor {name}')
        for action in item.findall('onfocus'):
            if action.get('item') and action.get('item') not in items and action.get('item') not in helper_items:
                problems.append(f'broken focus target {name} -> {action.get("item")}')
    for name in focus_names:
        item, node = items.get(name), nodes.get(name)
        if item is None or node is None:
            problems.append(f'missing focus item {name}')
            continue
        x, _y, z = node.get(8)[12:15]
        if not all(math.isfinite(v) for v in (x, z)) or not margin <= x <= 512 - margin or not margin <= z <= 384 - margin:
            problems.append(f'focus anchor outside safe area {name}')
        for way in ('up', 'down'):
            target = item.get(way)
            if target not in items:
                problems.append(f'broken {way} link {name} -> {target}')
    if focus_names:
        visited, current = [], focus_names[0]
        while current in items and current not in visited:
            visited.append(current)
            current = items[current].get('down')
        if current != focus_names[0] or set(visited) != set(focus_names):
            problems.append('focus chain is not one closed cycle')
    return problems


def fit_flat_panel(data, target, *, border=24, opaque=False):
    """Fit a transform-free authored frame to a native widget rectangle.

    Preserve corner bands and all atlas UVs. Only the centre spans grow; repeating
    fill quads retain their texel density. Recompute every bound with the same
    monotone map. Refuse shared position/UV blocks and unsupported layouts.
    target = (left, bottom, right, top) in native virtual-screen coordinates.
    """
    g = G.IgbFile(data)
    if g.objects_of('igTransform'):
        raise G.IgbError('panel fitting needs a flat scene without transforms')
    arrays = g.objects_of('igVertexArray1_1')
    positions = {}
    for array in arrays:
        refs = g.ref_list(array.get(2))
        count = array.get(3)
        if not isinstance(count, int) or not 1 <= count <= 65536 or not refs or refs[0] not in g.blocks or \
                g.block(refs[0])[1] != count * 12 or refs[0] in positions:
            raise G.IgbError('unsupported or shared panel positions')
        positions[refs[0]] = (array, refs, g.block_floats(refs[0]))
    xyz = [v for _, _, vertices in positions.values() for v in zip(vertices[0::3], vertices[1::3], vertices[2::3])]
    if not xyz or any(not math.isfinite(v) for vertex in xyz for v in vertex):
        raise G.IgbError('panel has no finite vertices')
    source = (min(v[0] for v in xyz), min(v[2] for v in xyz), max(v[0] for v in xyz), max(v[2] for v in xyz))
    if len(target) != 4 or any(not math.isfinite(v) for v in target) or not math.isfinite(border) or border <= 0:
        raise G.IgbError('invalid native panel rectangle')

    def axis(value, low, high, dest_low, dest_high):
        if min(high - low, dest_high - dest_low) <= 2 * border:
            raise G.IgbError('panel is too small for its corner bands')
        if value <= low + border:
            return dest_low + value - low
        if value >= high - border:
            return dest_high + value - high
        return dest_low + border + (value - low - border) * (dest_high - dest_low - 2 * border) / (high - low - 2 * border)

    def point(v):
        return [axis(v[0], source[0], source[2], target[0], target[2]), v[1],
                axis(v[2], source[1], source[3], target[1], target[3])]

    used = set(positions)
    fills = 0
    for ref, (array, refs, vertices) in positions.items():
        changed = [c for i in range(0, len(vertices), 3) for c in point(vertices[i:i + 3])]
        g.set_block_floats(ref, changed)
        # Component 11 is the first UV set in the native vertex format. Atlas
        # cells stay untouched. Out-of-range coordinates identify a tiled fill.
        uv_ref = refs[11] if len(refs) > 11 else -1
        if uv_ref in g.blocks:
            uv = g.block_floats(uv_ref)
            if len(uv) != array.get(3) * 2:
                raise G.IgbError('panel UV count disagrees with its vertices')
            if min(uv) < 0 or max(uv) > 1:
                if uv_ref in used or array.get(3) != 4:
                    raise G.IgbError('unsupported or shared tiled panel UVs')
                used.add(uv_ref)
                for coordinate, component in ((0, 0), (1, 2)):
                    old_span = max(vertices[component::3]) - min(vertices[component::3])
                    new_span = max(changed[component::3]) - min(changed[component::3])
                    if old_span <= 0:
                        raise G.IgbError('degenerate tiled panel')
                    centre = sum(uv[coordinate::2]) / 4
                    for i in range(coordinate, len(uv), 2):
                        uv[i] = centre + (uv[i] - centre) * new_span / old_span
                g.set_block_floats(uv_ref, uv)
                fills += 1
    for bounds in g.objects_of('igAABox'):
        if not bounds.decoded:
            raise G.IgbError('panel has unreadable bounds')
        for slot in (2, 3):
            g.set_floats(bounds, slot, point(bounds.get(slot)))
    out = opaque_materials(g.edited()) if opaque else g.edited()
    G.IgbFile(out)
    return out, {'source': source, 'target': target, 'border': border,
                 'vertex_arrays': len(arrays), 'tiled_fills': fills, 'opaque': opaque}


def opaque_materials(data):
    """Freeze flat chrome's alpha, including dormant pump defaults and keys.

    Retiring a pump registration alone does not define the material's startup
    alpha. Keep transforms, geometry, RGB and texture antialiasing unchanged.
    """
    g = G.IgbFile(data)
    for kind, slots in (('igMaterialAttr', (5, 6, 7)), ('igColorAttr', (4,)),
                        ('igDataPumpVec4fLinearInterface', (2,))):
        for obj in g.objects_of(kind):
            for slot in slots:
                field = obj.fields.get(slot)
                if field is None or field.type != 'igVec4fMetaField':
                    raise G.IgbError('unsupported panel opacity field')
                g.set_floats(obj, slot, [1], 3)
    for keys in g.objects_of('igVec4fList'):
        ref = keys.get(4)
        if ref == -1 and keys.get(2) == 0:
            continue
        values = g.block_floats(ref)
        if len(values) != 4 * keys.get(2):
            raise G.IgbError('panel opacity keys do not match their list')
        values[3::4] = [1] * keys.get(2)
        g.set_block_floats(ref, values)
    return g.edited()


def foreground_chrome(data, *, layer=(-110, -90)):
    """Put embedded flat chrome in the native panel layer behind native text.

    Legacy scenes can place the actual meshes near the far clipping plane even
    after moving their camera. Named UI anchors and the camera do not own these
    meshes, so moving widget transforms alone cannot bring the artwork forward.
    Retain every screen coordinate, UV, normal and relative depth ordering.
    """
    g = G.IgbFile(data)
    if len(layer) != 2 or any(not math.isfinite(v) for v in layer) or layer[0] >= layer[1]:
        raise G.IgbError('foreground chrome needs an ordered finite depth layer')
    for node in g.objects_of('igTransform'):
        children = g.list_items(node.get(7)) or []
        if any(g.obj(ref) is None or g.obj(ref).name not in ('igCamera', 'igHashedUserInfo')
               for ref in children):
            raise G.IgbError('foreground chrome cannot contain transformed meshes')
    positions = {}
    for array in g.objects_of('igVertexArray1_1'):
        refs = g.ref_list(array.get(2))
        ref = refs[0] if refs else -1
        if ref not in g.blocks or ref in positions or g.block(ref)[1] != array.get(3) * 12:
            raise G.IgbError('foreground chrome has unsupported position storage')
        positions[ref] = g.block_floats(ref)
    ys = [y for values in positions.values() for y in values[1::3]]
    if not ys or any(not math.isfinite(y) for y in ys):
        raise G.IgbError('foreground chrome has no finite vertices')
    low, high = min(ys), max(ys)
    def depth(y):
        return sum(layer)/2 if high == low else layer[0] + (y-low)*(layer[1]-layer[0])/(high-low)
    for ref, values in positions.items():
        values[1::3] = [depth(y) for y in values[1::3]]
        g.set_block_floats(ref, values)
    # UI-alias boxes are local to their untouched (retired) transforms. Only
    # model/culling boxes share the position blocks' coordinate space.
    alias_boxes = {node.get(3) for node in g.objects_of('igHashedUserInfo')}
    for box in g.objects_of('igAABox'):
        if box.ref not in alias_boxes:
            for slot in (2, 3):
                g.set_floats(box, slot, [depth(box.get(slot)[1])], 1)
    return g.edited()


def tint_vertex_colors(data, rgb):
    """Retain native selection geometry/alpha, using a colour from the disc palette."""
    if len(rgb) != 3 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in rgb):
        raise G.IgbError('invalid menu selection tint')
    g = G.IgbFile(data)
    blocks = {}
    for array in g.objects_of('igVertexArray1_1'):
        refs = g.ref_list(array.get(2))
        ref = refs[2] if len(refs) > 2 else -1
        if ref not in g.blocks or g.block(ref)[1] != 4 * array.get(3):
            raise G.IgbError('selection needs native four-byte vertex colours')
        offset, size = g.block(ref)
        blocks[ref] = (offset, size)
    if not blocks:
        raise G.IgbError('selection has no vertex colours')
    for offset, size in blocks.values():
        for at in range(offset, offset + size, 4):
            brightness = max(g.data[at:at + 3])
            g.buf[at:at + 3] = bytes(round(brightness * channel) for channel in rgb)
    return g.edited()


def tint_panel_materials(data, rgb):
    """Tint disc-authored flat chrome, retaining its texture and alpha animation."""
    if len(rgb) != 3 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in rgb):
        raise G.IgbError('invalid menu panel tint')
    g = G.IgbFile(data)
    changed = 0
    for kind, slots in (('igMaterialAttr', (5, 6, 7)), ('igColorAttr', (4,)),
                        ('igDataPumpVec4fLinearInterface', (2,))):
        for obj in g.objects_of(kind):
            for slot in slots:
                field = obj.fields.get(slot)
                if field is None or field.type != 'igVec4fMetaField':
                    raise G.IgbError('unsupported panel tint field')
                g.set_floats(obj, slot, [max(field.value[:3]) * c for c in rgb])
                changed += 1
    for keys in g.objects_of('igVec4fList'):
        ref = keys.get(4)
        if ref == -1 and keys.get(2) == 0:
            continue
        values = g.block_floats(ref)
        if len(values) != 4 * keys.get(2):
            raise G.IgbError('panel tint keys do not match their list')
        for at in range(0, len(values), 4):
            values[at:at + 3] = [max(values[at:at + 3]) * c for c in rgb]
        g.set_block_floats(ref, values)
    if not changed:
        raise G.IgbError('panel has no tintable materials')
    return g.edited()
