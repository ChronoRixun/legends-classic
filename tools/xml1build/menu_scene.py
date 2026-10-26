"""Bounded IGB scene attachment for native widgets and disc-authored menu artwork.

All widgets share one render layer and camera. Reference numbers in the primary
scene stay stable, including native animation sequences. No arbitrary binary
concatenation: metadata, object fields and typed reference arrays are relocated.
"""
from __future__ import annotations

import struct

from . import igb_file as G


def _u32(*values):
    return struct.pack('<' + 'I' * len(values), *(v & 0xffffffff for v in values))


def retire_camera(data):
    """Retire one native camera list before selecting attached artwork's camera.

    All camera graph objects and reference numbers remain present. Textures and
    extra-node resources still need to satisfy attachment's empty-list contract.
    """
    g = G.IgbFile(data)
    scenes = g.objects_of('igSceneInfo')
    if len(scenes) != 1:
        raise G.IgbError('camera selection needs one native scene')
    cameras = g.obj(scenes[0].get(7))
    if cameras is None or cameras.name != 'igGraphPathList' or cameras.get(2) != 1:
        raise G.IgbError('camera selection needs one graph-path camera')
    paths = g.list_items(cameras.ref)
    if not paths or len(paths) != 1 or g.obj(paths[0]).name != 'igGraphPath':
        raise G.IgbError('camera selection path is unreadable')
    for slot, value in ((2, 0), (3, 0), (4, -1)):
        struct.pack_into('<i', g.buf, cameras.fields[slot].offset, value)
    return g.edited()


def static_model(data, *, allow_transforms=False):
    """Retire model-local material pumps before instancing a flat backdrop.

    The original objects/keys remain present but are not registered as scene-wide
    animation infos. Callers freeze material opacity through the frame converter.
    """
    g = G.IgbFile(data)
    if g.objects_of('igTransform') and not allow_transforms:
        raise G.IgbError('static menu model must be transform-free')
    root_ref = struct.unpack_from('<I',g.data,g._obj_start-4)[0]
    root = g.obj(root_ref)
    members = g.list_items(root_ref) if root is not None else None
    scenes = [ref for ref in members or [] if g.obj(ref) is not None and g.obj(ref).name == 'igSceneInfo']
    if root is None or root.name != 'igInfoList' or len(scenes) != 1 or len(members) > 17 or any(
            g.obj(ref) is None or g.obj(ref).name not in ('igSceneInfo','igDataPumpInfo') for ref in members):
        raise G.IgbError('static menu model has unsupported info resources')
    block = g.block(root.get(4))
    if block is None:
        raise G.IgbError('static menu model has no info list data')
    struct.pack_into('<i',g.buf,block[0],scenes[0])
    struct.pack_into('<i',g.buf,root.fields[2].offset,1)
    return g.edited()


def _metadata(g):
    """Serialized type versions and auxiliary sections, checked before merging."""
    off = G.HEADER
    fields = [struct.unpack_from('<3I', g.data, off + i * 12) for i in range(g.header[9])]
    off += g.header[9] * 12 + sum(v[0] for v in fields)
    size = struct.unpack_from('<I', g.data, off)[0]
    alignment = g.data[off:off + size]
    off += size
    metas = [struct.unpack_from('<6I', g.data, off + i * 24) for i in range(g.header[3])]
    off += g.header[2]
    sections = 1 if g.header[11] == 0xb0000006 else 2
    auxiliary = []
    for _ in range(sections):
        size = struct.unpack_from('<I', g.data, off)[0]
        auxiliary.append(g.data[off:off + size])
        off += size
    if off != g._dir_start:
        raise G.IgbError('scene attachment metadata extent mismatch')
    return fields, metas, alignment, b''.join(auxiliary)


def attach(primary_data, artwork_data, *, anchors=(), keep_camera=False, merge_textures=False):
    """Attach artwork to a native anchor/animation scene and retain one scene info.

    The primary must have empty texture/camera/extra-node lists. keep_camera instead
    requires one primary camera and no incoming camera. Named anchors may instance
    transform-free static models; their local pumps must be retired first.
    merge_textures retains both texture registrations for assembled flat panels.
    Objects must be decoded; typed object-list and vertex-component buffers are
    the only supported reference-bearing memory arrays. Pixels/UVs/indices and
    numeric animation keys are copied unchanged.
    """
    gs = [G.IgbFile(primary_data), G.IgbFile(artwork_data)]
    if anchors and (len(set(anchors)) != len(anchors) or gs[1].objects_of('igTransform')):
        raise G.IgbError('instanced menu artwork needs unique anchors and a transform-free model')
    if any(g.header[11] != 0xf0000006 for g in gs):
        raise G.IgbError('scene attachment requires the modern IGB layout')
    if any(not o.decoded for g in gs for o in g.objects):
        raise G.IgbError('scene attachment needs fully decoded objects')
    if any('Ref' in f.type and f.type not in ('igObjectRefMetaField', 'igMemoryRefMetaField')
           for g in gs for o in g.objects for f in o.fields.values()):
        raise G.IgbError('scene attachment encountered an unsupported reference field')
    scenes = [g.objects_of('igSceneInfo') for g in gs]
    if any(len(values) != 1 for values in scenes):
        raise G.IgbError('scene attachment needs one scene info in each input')
    native, art = (values[0] for values in scenes)
    for g, scene_info in zip(gs, (native, art)):
        root_ref = struct.unpack_from('<I', g.data, g._obj_start - 4)[0]
        info = g.obj(root_ref)
        if info is None or info.name != 'igInfoList' or g.list_items(root_ref) != [scene_info.ref]:
            raise G.IgbError('scene attachment needs a root info list containing only its scene')
    root = gs[0].obj(native.get(5))
    if root is None or not gs[0].isa(root, 'igGroup'):
        raise G.IgbError('native scene root is not a group')
    children = gs[0].obj(root.get(7))
    if children is None or children.name != 'igNodeList' or children.get(4) not in gs[0].blocks:
        raise G.IgbError('native scene root lacks a readable child list')
    if gs[0].block(children.get(4))[1] != 4 * children.get(2):
        raise G.IgbError('native scene child buffer has unsupported spare capacity')
    for slot in (6, 7, 11):
        values = gs[0].obj(native.get(slot))
        count = 1 if slot == 7 and keep_camera else 0
        if slot == 6 and merge_textures and values is not None:
            if values.name != 'igTextureList' or not 0 <= values.get(2) <= 32:
                raise G.IgbError('panel texture registration is unsupported')
            continue
        if values is None or values.get(2) != count:
            raise G.IgbError('native menu resources are not empty; attachment would lose data')
    if keep_camera and gs[1].obj(art.get(7)).get(2) != 0:
        raise G.IgbError('instanced artwork cannot replace the selected native camera')
    targets = [children]
    if anchors:
        targets = []
        for name in anchors:
            nodes = [o for o in gs[0].objects if o.name == 'igTransform' and o.get(2) == name]
            target = gs[0].obj(nodes[0].get(7)) if len(nodes) == 1 else None
            if target is None or target.name != 'igNodeList' or target.get(4) not in gs[0].blocks or \
                    gs[0].block(target.get(4))[1] != target.get(2)*4:
                raise G.IgbError('menu artwork anchor needs one exact child list: ' + name)
            if target.ref in [item.ref for item in targets]:
                raise G.IgbError('menu artwork anchors share a child list')
            targets.append(target)
    types, type_versions, metas, meta_versions = [], {}, [], {}
    meta_maps = []
    shared_sections = None
    for g in gs:
        field_info, meta_info, alignment, auxiliary = _metadata(g)
        if shared_sections is not None and shared_sections != (alignment, auxiliary):
            raise G.IgbError('menu scenes have incompatible alignment/pool/external tables')
        shared_sections = (alignment, auxiliary)
        for name, info in zip(g.field_types, field_info):
            version = info[1:]
            if name in type_versions and type_versions[name] != version:
                raise G.IgbError('incompatible serialized field versions')
            if name not in type_versions:
                types.append(name)
                type_versions[name] = version
        mapping = {}
        for i, m in enumerate(g.metas):
            parent = g.metas[m['parent']]['name'] if m['parent'] >= 0 else None
            canonical = (m['name'], parent, m['fields'])
            version = (meta_info[i][1], meta_info[i][2], meta_info[i][5])
            existing = next((j for j, value in enumerate(metas) if value[0] == m['name']), None)
            if existing is not None:
                if metas[existing] != canonical or meta_versions[m['name']] != version:
                    raise G.IgbError('incompatible menu object schemas: ' + m['name'])
                mapping[i] = existing
            else:
                mapping[i] = len(metas)
                metas.append(canonical)
                meta_versions[m['name']] = version
        meta_maps.append(mapping)
    # Keep native references stable. The second scene info resolves to the first.
    maps = [{i: i for i in range(len(gs[0].items))}, {}]
    next_ref = len(gs[0].items)
    for old in range(len(gs[1].items)):
        if old == art.ref:
            maps[1][old] = native.ref
        else:
            maps[1][old] = next_ref
            next_ref += 1
    if next_ref > 0xffff:
        raise G.IgbError('attached menu exceeds the reference table')
    objects, blocks, directory_sources = {}, {}, {}
    for which, g in enumerate(gs):
        remap = maps[which]
        reference_blocks = set()
        for o in g.objects:
            if g.isa(o, 'igObjectList') and o.get(4) in g.blocks:
                reference_blocks.add(o.get(4))
            if o.name == 'igVertexArray1_1' and o.get(2) in g.blocks:
                reference_blocks.add(o.get(2))
        for ref, (offset, size) in g.blocks.items():
            directory_sources[remap[ref]] = (which, g.index[ref])
            blob = bytes(g.buf[offset:offset + size])
            if ref in reference_blocks:
                if size % 4:
                    raise G.IgbError('menu reference array is not word aligned')
                values = struct.unpack('<' + 'i' * (size // 4), blob)
                if any(v != -1 and v not in remap for v in values):
                    raise G.IgbError('menu reference array points outside its input')
                blob = _u32(*(remap[v] if v >= 0 else v for v in values))
            blocks[remap[ref]] = blob
        for o in g.objects:
            if which == 1 and o.ref == art.ref:
                continue
            directory_sources[remap[o.ref]] = (which, g.index[o.ref])
            record = bytearray(g.buf[o.offset:o.offset + o.size])
            struct.pack_into('<I', record, 0, meta_maps[which][o.meta])
            for field in o.fields.values():
                if field.type in ('igObjectRefMetaField', 'igMemoryRefMetaField'):
                    value = field.value
                    if value != -1 and value not in remap:
                        raise G.IgbError('menu object points outside its input')
                    struct.pack_into('<i', record, field.offset - o.offset, remap[value] if value >= 0 else value)
            objects[remap[o.ref]] = record
    # Add the art root to the native graph; its one camera becomes the shared camera.
    for target in targets:
        child_block = target.get(4)
        blocks[child_block] += _u32(maps[1][art.get(5)])
        for slot in (2, 3):
            struct.pack_into('<i', objects[target.ref], target.fields[slot].offset - target.offset,
                             len(blocks[child_block]) // 4)
    for slot in (6, 7, 11):
        if slot == 7 and keep_camera:
            continue
        if slot == 6 and merge_textures:
            textures = gs[0].obj(native.get(6))
            if textures.get(2):
                ref = textures.get(4)
                if ref not in blocks or len(blocks[ref]) != textures.get(2)*4:
                    raise G.IgbError('panel texture registration buffer is unsupported')
                incoming = gs[1].list_items(art.get(6)) or []
                blocks[ref] += _u32(*(maps[1][value] for value in incoming))
                for field in (2, 3):
                    struct.pack_into('<i', objects[textures.ref],
                                     textures.fields[field].offset - textures.offset, len(blocks[ref])//4)
                continue
        struct.pack_into('<i', objects[native.ref], native.fields[slot].offset - native.offset,
                         maps[1][art.get(slot)])
    field_blob = b''.join(_u32(len(name) + 1, *type_versions[name]) for name in types)
    field_blob += b''.join(name.encode('ascii') + b'\0' for name in types)
    names = {m[0]: i for i, m in enumerate(metas)}
    heads, bodies = bytearray(), bytearray()
    for name, parent, fields in metas:
        major, minor, slots = meta_versions[name]
        heads += _u32(len(name) + 1, major, minor, len(fields), names[parent] if parent else -1, slots)
        bodies += name.encode('ascii') + b'\0'
        bodies += b''.join(struct.pack('<3H', types.index(kind), slot, size) for kind, slot, size in fields)
    meta_blob = bytes(heads + bodies)
    entries, entry_ids, indices = [], {}, []
    obj_blob, memory = bytearray(), bytearray()
    for ref in range(next_ref):
        which, di = directory_sources[ref]
        g = gs[which]
        offset, size, fields = g._dir_entries[di]
        entry = bytearray(g.data[offset:offset + size])
        old_meta = struct.unpack_from('<I', entry)[0]
        struct.pack_into('<I', entry, 0, meta_maps[which][old_meta])
        if ref in objects:
            record = objects[ref]
            struct.pack_into('<I', entry, fields[11].offset - offset, struct.unpack_from('<I', record)[0])
            obj_blob += record
        elif ref in blocks:
            struct.pack_into('<I', entry, fields[7].offset - offset, len(blocks[ref]))
            memory += b'\0' * (-len(memory) % 4)
            memory += blocks[ref]
        else:
            raise G.IgbError('attached scene has a reference hole')
        entry = bytes(entry)
        if entry not in entry_ids:
            entry_ids[entry] = len(entries)
            entries.append(entry)
        indices.append(entry_ids[entry])
    directory = b''.join(entries)
    memory += b'\0' * (-len(memory) % 4)
    index = _u32(8 + 2 * next_ref, next_ref) + struct.pack('<' + 'H' * next_ref, *indices)
    root_ref = struct.unpack_from('<I', gs[0].data, gs[0]._obj_start - 4)[0]
    header = _u32(len(directory), len(entries), len(meta_blob), len(metas), len(obj_blob), len(objects),
                  len(memory), len(blocks), len(field_blob), len(types), G.MAGIC, 0xf0000006)
    alignment, auxiliary = shared_sections
    out = header + field_blob + alignment + meta_blob + auxiliary + directory + index + _u32(root_ref) + obj_blob + memory
    check = G.IgbFile(out)
    if len(check.objects_of('igSceneInfo')) != 1 or check.obj(root_ref).name != 'igInfoList':
        raise G.IgbError('attached scene root did not round-trip')
    for ref, blob in blocks.items():
        offset, size = check.block(ref)
        if check.data[offset:offset + size] != blob:
            raise G.IgbError('attached scene memory did not round-trip')
    return bytes(out), {'objects': len(objects), 'memory_blocks': len(blocks), 'references': next_ref,
                         'native_references': len(gs[0].items), 'scene_infos': 1}
