"""Opt-in disc-authored conversation background, keeping the native PC renderer.

Only the same-name model is replaced. Authored transforms, materials, embedded
images and geometry stay byte-for-byte intact; text and portraits are separate
native objects. Structural acceptance is not proof of visual compatibility.
"""
from __future__ import annotations

import math
import struct

from . import common as C, igb_file as G

MODEL = 'UI/hud/convo_background.IGB'
SOURCE = 'ui/hud/convo_background.igb'
MODES = ('off', 'xml1')
RECOVERY = 'Rebuild with --classic-conversation off to keep the native PC conversation background.'
_OBJECT_REF = 'igObjectRefMetaField'
_MEMORY_REF = 'igMemoryRefMetaField'
_REFERENCE_FIELDS = (
    ('igSceneInfo', {5: _OBJECT_REF}),
    ('igGroup', {7: _OBJECT_REF}),
    ('igTransform', {7: _OBJECT_REF}),
    ('igAttrSet', {7: _OBJECT_REF, 8: _OBJECT_REF}),
    ('igGeometry', {7: _OBJECT_REF, 8: _OBJECT_REF}),
    ('igGeometryAttr1_5', {4: _OBJECT_REF, 5: _OBJECT_REF}),
    ('igVertexArray1_1', {2: _MEMORY_REF}),
    ('igIndexArray', {2: _MEMORY_REF}),
    ('igPrimLengthArray1_1', {2: _MEMORY_REF}),
    ('igTextureBindAttr', {4: _OBJECT_REF}),
    ('igTextureAttr', {12: _OBJECT_REF}),
    ('igImage', {13: _MEMORY_REF}),
)


def mode(ctx):
    value = ctx.opt('classic_conversation', 'off')
    if value not in MODES:
        raise G.IgbError('Unsupported --classic-conversation selection. ' + RECOVERY)
    return value


def _file(data):
    if len(data) < G.HEADER:
        raise G.IgbError('conversation model is shorter than its header')
    header = struct.unpack_from('<12I', data)
    if header[11] != 0xf0000006:
        raise G.IgbError('unsupported conversation IGB layout (requires 0xf0000006)')
    # Bound parser allocations/loops by the input, including malformed counts.
    if len(data) > 16 * 1024 * 1024 or any(header[i] > len(data) // 4 for i in (1, 3, 5, 7, 9)):
        raise G.IgbError('conversation model has excessive section counts or size')
    try:
        graph = G.IgbFile(data)
    except (struct.error, IndexError, TypeError) as exc:
        raise G.IgbError('malformed conversation IGB sections') from exc
    for index, meta in enumerate(graph.metas):
        seen = {index}
        parent = meta['parent']
        while parent != -1:
            if parent in seen or not 0 <= parent < len(graph.metas):
                raise G.IgbError('invalid conversation metadata inheritance')
            seen.add(parent)
            parent = graph.metas[parent]['parent']
    return graph


def _contract(data):
    g = _file(data)

    def obj(ref, kind):
        value = g.obj(ref)
        if value is None or not g.isa(value, kind):
            raise G.IgbError('conversation reference must name ' + kind)
        return value

    def block(ref, size, label):
        value = g.block(ref) if isinstance(ref, int) else None
        if value is None or value[1] != size:
            raise G.IgbError('invalid conversation ' + label + ' block length/reference')
        return value

    # Every serialized object/memory reference must resolve, even when its node
    # is not reachable from the scene. Shared read-only blocks are safe when all
    # consumers agree on their layout; this converter never edits them.
    for o in g.objects:
        if not o.decoded:
            raise G.IgbError('undecoded conversation object: ' + o.name)
        for kind, fields in _REFERENCE_FIELDS:
            if g.isa(o, kind):
                for slot, field_type in fields.items():
                    field = o.fields.get(slot)
                    if field is None or field.type != field_type or not isinstance(field.value, int):
                        raise G.IgbError('unsupported conversation reference field layout: ' + kind)
        for f in o.fields.values():
            if f.type == 'igObjectRefMetaField' and f.value != -1 and g.obj(f.value) is None:
                raise G.IgbError('invalid conversation object reference')
            if f.type == 'igMemoryRefMetaField' and f.value != -1 and g.block(f.value) is None:
                raise G.IgbError('invalid conversation memory reference')
            if f.type in G._FLOATS:
                values = f.value if isinstance(f.value, list) else [f.value]
                if any(v is None or not math.isfinite(v) for v in values):
                    raise G.IgbError('conversation geometry/attributes must be finite')
        if g.isa(o, 'igObjectList') or o.name in ('igInfoList', 'igNodeList', 'igAttrList',
                                               'igTextureList', 'igGraphPathList'):
            field = o.fields.get(4)
            if field is None or field.type != _MEMORY_REF or not isinstance(field.value, int):
                raise G.IgbError('unsupported conversation reference list field layout')
            count, capacity, ref = o.get(2), o.get(3), o.get(4)
            if not isinstance(count, int) or not isinstance(capacity, int) or not 0 <= count <= capacity <= 65536:
                raise G.IgbError('invalid conversation reference list count/capacity')
            if ref == -1 and capacity == 0:
                continue
            block(ref, capacity * 4, 'reference list')
            if any(r != -1 and g.obj(r) is None for r in g.ref_list(ref)):
                raise G.IgbError('invalid conversation reference list member')

    transforms = g.objects_of('igTransform')
    for transform in transforms:
        matrix = transform.get(8)
        if (not isinstance(matrix, list) or len(matrix) != 16
                or [matrix[i] for i in (3, 7, 11, 15)] != [0., 0., 0., 1.]):
            raise G.IgbError('unsupported conversation transform (requires finite affine matrix)')
        determinant = (matrix[0] * (matrix[5] * matrix[10] - matrix[6] * matrix[9])
                       - matrix[1] * (matrix[4] * matrix[10] - matrix[6] * matrix[8])
                       + matrix[2] * (matrix[4] * matrix[9] - matrix[5] * matrix[8]))
        if not math.isfinite(determinant) or determinant == 0:
            raise G.IgbError('singular conversation transform')

    vertex_counts = {}
    for array in g.objects_of('igVertexArray1_1'):
        count = array.get(3)
        if not isinstance(count, int) or not 1 <= count <= 65536 or array.get(6) not in (65537, 65543):
            raise G.IgbError('unsupported conversation vertex stream layout')
        block(array.get(2), 80, 'vertex stream table')
        refs = g.ref_list(array.get(2))
        if any(r != -1 and g.block(r) is None for r in refs):
            raise G.IgbError('invalid conversation stream reference')
        streams = {0: 12, 11: 8}
        if array.get(6) == 65543:
            streams.update({1: 12, 2: 4})  # normals and packed vertex colour, retained verbatim
        if any(ref != -1 for i, ref in enumerate(refs) if i not in streams):
            raise G.IgbError('unsupported conversation vertex stream layout')
        for slot, stride in streams.items():
            block(refs[slot], count * stride, 'position/UV stream')
            if slot != 2 and any(not math.isfinite(v) for v in g.block_floats(refs[slot])):
                raise G.IgbError('conversation vertex stream must be finite')
        vertex_counts[array.ref] = count

    geometries = g.objects_of('igGeometryAttr1_5')
    if not geometries:
        raise G.IgbError('conversation model has no supported geometry')
    for geometry in geometries:
        array = obj(geometry.get(4), 'igVertexArray1_1')
        indices = obj(geometry.get(5), 'igIndexArray')
        count = indices.get(3)
        if (not isinstance(count, int) or not 3 <= count <= 65536 or geometry.get(6) not in (3, 4)
                or (geometry.get(6) == 3 and count % 3)):
            raise G.IgbError('unsupported conversation triangle/index layout')
        off, _ = block(indices.get(2), count * 2, 'index stream')
        if any(index >= vertex_counts[array.ref] for index in struct.unpack_from(f'<{count}H', g.data, off)):
            raise G.IgbError('conversation index outside vertex array')
    for lengths in g.objects_of('igPrimLengthArray1_1'):
        count = lengths.get(3)
        if not isinstance(count, int) or not 1 <= count <= 65536:
            raise G.IgbError('invalid conversation primitive count')
        block(lengths.get(2), count * 4, 'primitive lengths')

    images = g.objects_of('igImage')
    if not images:
        raise G.IgbError('conversation model has no embedded images')
    for image in images:
        w, h, fmt = image.get(2), image.get(3), image.get(11)
        if not all(isinstance(v, int) and 1 <= v <= 4096 for v in (w, h)) or fmt not in (7, 15):
            raise G.IgbError('unsupported conversation image dimensions/encoding (requires RGBA8 or DXT3)')
        size = w * h * 4 if fmt == 7 else ((w + 3) // 4) * ((h + 3) // 4) * 16
        if image.get(12) != size:
            raise G.IgbError('conversation image declared length disagrees with dimensions')
        block(image.get(13), size, 'image pixels')
    for texture in g.objects_of('igTextureAttr'):
        obj(texture.get(12), 'igImage')
    for binding in g.objects_of('igTextureBindAttr'):
        obj(binding.get(4), 'igTextureAttr')

    scenes = g.objects_of('igSceneInfo')
    if len(scenes) != 1:
        raise G.IgbError('conversation model requires one scene')
    root_ref = struct.unpack_from('<i', g.data, g._obj_start - 4)[0]
    root = g.obj(root_ref)
    members = g.list_items(root_ref)
    if (root is None or root.name != 'igInfoList' or members is None
            or members.count(scenes[0].ref) != 1):
        raise G.IgbError('conversation loader root must retain its scene information')
    reached, stack, visits = set(), [(scenes[0].get(5), ())], 0
    while stack:
        ref, ancestors = stack.pop()
        visits += 1
        if ref in ancestors or len(ancestors) > 64 or visits > 4096:
            raise G.IgbError('cyclic or excessive conversation scene graph')
        node = g.obj(ref)
        if node is None or node.name not in ('igGroup', 'igTransform', 'igAttrSet', 'igGeometry'):
            raise G.IgbError('unsupported conversation scene node/reference')
        if node.name in ('igAttrSet', 'igGeometry'):
            attrs = g.list_items(node.get(8))
            if attrs is None:
                raise G.IgbError('conversation node has no attribute list')
            reached.update(attrs)
        if node.get(7, -1) != -1:
            children = g.list_items(node.get(7))
            if children is None:
                raise G.IgbError('conversation node has no child list')
            stack.extend((child, ancestors + (ref,)) for child in children)
    if any(o.ref not in reached for o in geometries):
        raise G.IgbError('conversation geometry is outside the scene graph')
    return {'geometries': len(geometries), 'transforms': len(transforms), 'images': len(images)}


def problems(data):
    """Structural diagnostics for the supported transformed scene/image contract."""
    try:
        _contract(data)
    except G.IgbError as exc:
        return [str(exc)]
    return []


def convert(xbox: bytes, pc: bytes) -> tuple[bytes, dict]:
    """Validate first, then preserve the authored scene without fitting or re-encoding."""
    try:
        report = _contract(xbox)
        _file(pc)
    except G.IgbError as exc:
        raise G.IgbError(f'Unsupported conversation background: {exc}. {RECOVERY}') from exc
    return bytes(xbox), {'mode': 'xml1', 'byte_preserving': True, **report}


def converted(ctx):
    source, native = ctx.x1_path(SOURCE), ctx.base_index.path(MODEL)
    if source is None or native is None:
        raise G.IgbError('Conversation background input missing: needs the prepared XML1 disc model '
                         'and base UI/hud/convo_background.IGB. Re-prepare your owned inputs. ' + RECOVERY)
    C.checkpoint('conversation', MODEL)
    return convert(source.read_bytes(), native.read_bytes())


def write(ctx) -> dict:
    """Use only BuildContext sources and its atomic, registered output writer."""
    if mode(ctx) == 'off':
        return {'mode': 'off'}
    data, report = converted(ctx)
    ctx.write_bytes(MODEL, data, source='frontend:owned XML1 conversation background (byte-preserving)')
    return report


def validate(v, ck):
    """ON must match conversion; OFF must retain the base model, in either frontend."""
    try:
        selected = mode(v.ctx)
        if selected == 'xml1':
            expected, _ = converted(v.ctx)
            entry = v.ctx.registry.get(MODEL)
            if entry is None or entry['owner'] != 'frontend':
                ck.error('classic conversation background is not owned by frontend')
        else:
            native = v.ctx.base_index.path(MODEL)
            if native is None:
                raise G.IgbError('native conversation background missing from base')
            expected = native.read_bytes()
        path = v.idx.path(MODEL)
        if path is None or path.read_bytes() != expected:
            ck.error(f'conversation background missing or differs from {selected} selection: {MODEL}')
        ck.count('conversation_backgrounds')
    except (G.IgbError, OSError) as exc:
        ck.error(str(exc))
