"""xml1build.igb_anim_merge - transplant XML1 animation clips into XML2's shared animation database (SPEC 107.1).

XMen2.exe loads Actors/common.IGB into anim DB slot 2 of every actor (0x41ff9d pushes "common"), so a clip in that file
is visible to every character, victims included. XML1's actors/common.igb carries the flying-carry and Juggernaut-grab
clips XML2's lacks; with the AnimEnums capacity raise (xml2-fix [Limits] AnimEnums, rule 48) their enums resolve, and
the clips must be in the file the engine searches. The clips are read from the player's own XML1 disc at build time;
nothing of them is in this repository.

Facts this relies on (checked on every run, refused otherwise):
  * both files use the 0xf0000006 layout with byte-identical meta-field tables and identical alignment / external
    directory / memory pool sections;
  * both have the same 39 meta objects by name, each with the same parent, fields and versions. The ORDER differs
    between XML1's and XML2's common.igb (igEnbayaAnimationSource is meta 34 in one, 11 in the other), so every
    transplanted object's meta number and its directory entry's slot 11 are remapped by name;
  * each has one igSkeleton `common_skel` with equal bone lists (every igSkeletonBoneInfo field) and joint count: the
    clips' bindings point at the target's skeleton instead of a copy;
  * references live only in igObjectRefMetaField / igMemoryRefMetaField fields and in the memory blocks an igObjectList
    holds (slot 4; the directory entry's element type, slot 10, says igObjectRefMetaField for exactly those blocks).

A clip's closure is everything reachable from its igAnimation through those references, stopping at the skeleton.
Reaching another igAnimation, an igAnimationDatabase, an igInfoList or a second skeleton is refused (no clip of the 21
does). The closures are appended in source reference order (deterministic), the new clips are appended to the target
database's animation list in the source database's order, and the result is verified: every original object and
memory block byte-identical at its old reference number (the animation list's count / capacity and its data block's
appended references aside), every transplanted object / block byte-identical to its source after mapping references
and meta numbers back, every clip name present once.

Pure: bytes in, bytes out (no file I/O)."""
from __future__ import annotations

import collections
import hashlib
import struct

from . import igb_file as G
from .igb_file import IgbError, IgbFile

# design 5.1 (agent-work/anim-enum-design/DESIGN.md): the 21 XML1 clips the 23 built-in enums name
REQUIRED_CLIPS = (
    'p_flyingcarry_flyfast', 'p_flyingcarry_flyslow', 'p_flyingcarry_idle', 'p_flyingcarry_pickup',
    'p_flyingcarry_throwdown', 'p_flyingcarry_throwforward',
    'v_flyingcarry_enemy_flyfast', 'v_flyingcarry_enemy_flyslow', 'v_flyingcarry_enemy_idle',
    'v_flyingcarry_enemy_throwdown', 'v_flyingcarry_enemy_throwforward',
    'v_flyingcarry_flyfast', 'v_flyingcarry_flyslow', 'v_flyingcarry_idle', 'v_flyingcarry_pickup',
    'v_flyingcarry_throwforward',
    'jug_grabbed_attempt', 'jug_grabbed_struggle', 'jug_grabbed_throw', 'jug_grabbed_throw_left',
    'jug_grabbed_throw_right',
)
# clips XML1's shared_anims names that XML1's own common.igb does not have: the enum resolves to enum 0's animation
# through the cache build's default (PC 0x4260d3..0x426122; XML1 the same loop), on XML1 and on the port alike.
# Not invented: the mapping is kept verbatim and the clip stays absent. clip (lower) -> the enum that names it
KNOWN_ABSENT_IN_XML1 = {
    'v_flyingcarry_enemy_pickup': 'ea_flyingcarry_pickup_v',
    'v_flyingcarry_throwdown': 'ea_flyingcarry_throwdown_a',
}
SKELETON = 'common_skel'
LAYOUT = 0xf0000006
REF_FIELDS = ('igObjectRefMetaField', 'igMemoryRefMetaField')
STOP_KINDS = ('igAnimationDatabase', 'igInfoList', 'igAnimation', 'igSkeleton')


class MergeError(IgbError):
    pass


# ------------------------------------------------------------------------------------------------ structure
def _meta_sections(g):
    """(meta-field bytes, [(name, major, minor, slots)] per meta object, the bytes of the alignment, external
    directory and memory pool sections)."""
    d, h = g.data, g.header
    fields = d[G.HEADER:G.HEADER + h[8]]
    off = G.HEADER + h[8]
    size = struct.unpack_from('<I', d, off)[0]
    alignment = d[off:off + size]
    off += size
    heads = [struct.unpack_from('<6I', d, off + 24 * i) for i in range(h[3])]
    off += h[2]
    aux = []
    for _ in range(1 if h[11] == 0xb0000006 else 2):
        size = struct.unpack_from('<I', d, off)[0]
        aux.append(d[off:off + size])
        off += size
    if off != g._dir_start:
        raise MergeError('meta sections do not end at the directory')
    versions = [(g.metas[i]['name'], hd[1], hd[2], hd[5]) for i, hd in enumerate(heads)]
    return fields, versions, alignment + b''.join(aux)


def meta_map(target, source):
    """{source meta number: target meta number}; refuses files whose type tables are not the same by name."""
    if target.header[11] != LAYOUT or source.header[11] != LAYOUT:
        raise MergeError(f'both files must use the 0x{LAYOUT:x} layout')
    tf, tv, ta = _meta_sections(target)
    sf, sv, sa = _meta_sections(source)
    if tf != sf or target.field_types != source.field_types:
        raise MergeError('meta-field tables differ')
    if ta != sa:
        raise MergeError('alignment / external directory / memory pool sections differ')

    def canon(g, i, ver):
        m = g.metas[i]
        parent = g.metas[m['parent']]['name'] if m['parent'] >= 0 else None
        return (m['name'], parent, tuple(m['fields']), ver[1:])

    tc = {canon(target, i, v)[0]: canon(target, i, v) for i, v in enumerate(tv)}
    sc = {canon(source, i, v)[0]: canon(source, i, v) for i, v in enumerate(sv)}
    if len(tc) != len(tv) or len(sc) != len(sv):
        raise MergeError('duplicate meta object names')
    if tc != sc:
        diff = sorted(n for n in set(tc) | set(sc) if tc.get(n) != sc.get(n))
        raise MergeError(f'meta objects differ: {diff[:6]}')
    return {i: target.meta_index[m['name']] for i, m in enumerate(source.metas)}


def ref_blocks(g):
    """the memory blocks holding reference arrays: the data block (slot 4) of every igObjectList-derived object.
    A directory entry whose element type (slot 10, when the layout has it) says igObjectRefMetaField must be one of
    them and the other way round, else the file is refused."""
    held = {o.get(4) for o in g.objects if g.isa(o, 'igObjectList') and o.get(4) in g.blocks}
    for ref in g.blocks:
        kind, vals = g.directory[g.index[ref]]
        t = vals.get(10)
        if isinstance(t, int) and 0 <= t < len(g.field_types):
            if (g.field_types[t] == 'igObjectRefMetaField') != (ref in held):
                raise MergeError(f'memory block {ref}: element type {g.field_types[t]} disagrees with its owner')
    for ref in held:
        if g.blocks[ref][1] % 4:
            raise MergeError(f'memory block {ref}: reference array of {g.blocks[ref][1]} bytes')
    return held


def _children(g, ref, refs_in):
    o = g.items[ref]
    if o is None:
        return [v for v in g.ref_list(ref) if v != -1] if ref in refs_in else []
    if not o.decoded:
        raise MergeError(f'object {ref} ({o.name}) does not decode')
    out = []
    for slot in sorted(o.fields):
        f = o.fields[slot]
        if f.type in REF_FIELDS:
            if f.value != -1:
                out.append(f.value)
        elif 'Ref' in f.type:
            raise MergeError(f'object {ref} ({o.name}) slot {slot}: unsupported reference field {f.type}')
    return out


def skeleton(g):
    sk = [o for o in g.objects_of('igSkeleton')]
    if len(sk) != 1 or sk[0].get(2) != SKELETON:
        raise MergeError(f'needs exactly one igSkeleton {SKELETON!r}, found {[o.get(2) for o in sk]}')
    return sk[0]


def bones(g, sk):
    """every igSkeletonBoneInfo of the skeleton's bone list as {slot: value}, in order; plus the joint count."""
    refs = g.list_items(sk.get(4))
    if refs is None:
        raise MergeError(f'{sk.get(2)}: unreadable bone list')
    out = []
    for r in refs:
        b = g.obj(r)
        if b is None or b.name != 'igSkeletonBoneInfo' or not b.decoded:
            raise MergeError(f'{sk.get(2)}: bone {r} is not an igSkeletonBoneInfo')
        out.append({s: f.value for s, f in sorted(b.fields.items())})
    return out, sk.get(6)


def database(g):
    dbs = g.objects_of('igAnimationDatabase')
    if len(dbs) != 1:
        raise MergeError(f'needs exactly one igAnimationDatabase, found {len(dbs)}')
    lst = g.obj(dbs[0].get(6))
    if lst is None or lst.name != 'igAnimationList' or not lst.decoded:
        raise MergeError('the animation database has no igAnimationList')
    return dbs[0], lst


def clip_names(g):
    """the names of the database's animations, in list order."""
    _db, lst = database(g)
    refs = g.list_items(lst.ref)
    if refs is None:
        raise MergeError('unreadable animation list')
    names = []
    for r in refs:
        a = g.obj(r)
        if a is None or a.name != 'igAnimation':
            raise MergeError(f'animation list item {r} is not an igAnimation')
        names.append(a.get(2))
    return names


def closure(g, root, skel_ref, refs_in):
    """the items reachable from igAnimation `root`, the skeleton excluded (sorted reference numbers)."""
    seen, todo = set(), [root]
    while todo:
        r = todo.pop()
        if r in seen or r == skel_ref:
            continue
        if not 0 <= r < len(g.items):
            raise MergeError(f'reference {r} out of range')
        o = g.items[r]
        if o is not None and r != root and any(g.isa(o, k) for k in STOP_KINDS):
            raise MergeError(f'clip {g.items[root].get(2)!r} reaches {o.name} {r}')
        seen.add(r)
        todo.extend(_children(g, r, refs_in))
    return sorted(seen)


# ------------------------------------------------------------------------------------------------ transplant
def _remap_object(g, o, metas, remap):
    rec = bytearray(g.buf[o.offset:o.offset + o.size])
    struct.pack_into('<I', rec, 0, metas[o.meta])
    for f in o.fields.values():
        if f.type in REF_FIELDS and f.value != -1:
            if f.value not in remap:
                raise MergeError(f'object {o.ref} ({o.name}) points outside its closure ({f.value})')
            struct.pack_into('<i', rec, f.offset - o.offset, remap[f.value])
    return bytes(rec)


def _remap_refs(data, remap, where):
    vals = struct.unpack(f'<{len(data) // 4}i', data)
    if any(v != -1 and v not in remap for v in vals):
        raise MergeError(f'{where}: reference array points outside its closure')
    return struct.pack(f'<{len(vals)}i', *(remap[v] if v != -1 else -1 for v in vals))


def _entry(g, ref, target, kind, meta=None):
    """item `ref`'s directory entry of source `g`, in the target's numbering (entry meta object; object type)."""
    o, n, fields = g._dir_entries[g.index[ref]]
    e = bytearray(g.buf[o:o + n])
    struct.pack_into('<I', e, 0, target.meta_index[kind])
    if meta is not None:
        struct.pack_into('<I', e, fields[11].offset - o, meta)
    return bytes(e)


def transplant(target_data, source_data, names=REQUIRED_CLIPS):
    """(Actors/common.IGB with the XML1 clips `names` added, report). target_data: XML2's common.IGB; source_data:
    XML1's actors/common.igb. Raises MergeError (an IgbError) when the files do not meet the facts above."""
    t, s = IgbFile(target_data), IgbFile(source_data)
    metas = meta_map(t, s)
    tsk, ssk = skeleton(t), skeleton(s)
    if bones(t, tsk) != bones(s, ssk):
        raise MergeError(f'{SKELETON}: the two skeletons differ (bone list or joint count)')
    t_refs, s_refs = ref_blocks(t), ref_blocks(s)
    _tdb, tlist = database(t)
    tcount, tcap = tlist.get(2), tlist.get(3)
    tblock = t.block(tlist.get(4))
    if tcount != tcap or tblock is None or tblock[1] != 4 * tcount:
        raise MergeError('the target animation list has spare capacity or no exact data block')
    have = [n.lower() for n in clip_names(t)]
    if len(set(have)) != len(have):
        raise MergeError('the target animation database has duplicate clip names')
    wanted = [n.lower() for n in names]
    if len(set(wanted)) != len(wanted):
        raise MergeError('duplicate clip names requested')
    clash = sorted(set(wanted) & set(have))
    if clash:
        raise MergeError(f'the target already has {clash}')
    _sdb, slist = database(s)
    s_order = s.list_items(slist.ref)
    by_name = collections.defaultdict(list)
    for r in s_order:
        by_name[(s.obj(r).get(2) or '').lower()].append(r)
    missing = [n for n in wanted if len(by_name.get(n, ())) != 1]
    if missing:
        raise MergeError(f'clips missing (or not unique) in the source database: {missing}')
    roots = [r for r in s_order if (s.obj(r).get(2) or '').lower() in set(wanted)]   # source DB order
    union = set()
    per_clip = {}
    for r in roots:
        c = closure(s, r, ssk.ref, s_refs)
        per_clip[s.obj(r).get(2)] = len(c)
        union.update(c)
    order = sorted(union)
    base = len(t.items)
    remap = {r: base + i for i, r in enumerate(order)}
    remap[ssk.ref] = tsk.ref
    items = []
    for r in order:
        o = s.items[r]
        if o is not None:
            items.append(('object', _entry(s, r, t, 'igObjectDirEntry', metas[o.meta]),
                          _remap_object(s, o, metas, remap)))
        else:
            off, size = s.blocks[r]
            data = bytes(s.buf[off:off + size])
            if r in s_refs:
                data = _remap_refs(data, remap, f'memory block {r}')
            items.append(('memory', _entry(s, r, t, 'igMemoryDirEntry'), data))
    new_anims = [remap[r] for r in roots]
    list_block = bytes(t.buf[tblock[0]:tblock[0] + tblock[1]]) + struct.pack(f'<{len(new_anims)}i', *new_anims)
    t.set_int(tlist, 2, tcount + len(new_anims))
    t.set_int(tlist, 3, tcap + len(new_anims))
    out = t.appended(items, {tlist.get(4): list_block})
    report = verify(out, target_data, source_data, remap, metas, tlist.ref, new_anims, wanted)
    report.update({'clips': [s.obj(r).get(2) for r in roots], 'closure_items': len(order), 'per_clip': per_clip,
                   'objects_added': sum(1 for k, _e, _p in items if k == 'object'),
                   'blocks_added': sum(1 for k, _e, _p in items if k == 'memory'),
                   'skeleton_target_ref': tsk.ref})
    return out, report


def verify(out, target_data, source_data, remap, metas, list_ref, new_anims, wanted):
    """step 4 of design 5.1 on the written bytes; returns the report's counts, raises MergeError."""
    o, t, s = IgbFile(out), IgbFile(target_data), IgbFile(source_data)
    n_old = len(t.items)
    if len(o.items) != n_old + len(remap) - 1:
        raise MergeError('item count after the merge is wrong')
    tlist = t.items[list_ref]
    for r in range(n_old):
        a, b = t.items[r], o.items[r]
        if (a is None) != (b is None):
            raise MergeError(f'item {r} changed kind')
        if a is not None:
            old = bytearray(t.data[a.offset:a.offset + a.size])
            if r == list_ref:
                for slot in (2, 3):
                    struct.pack_into('<i', old, a.fields[slot].offset - a.offset, a.get(slot) + len(new_anims))
            if bytes(old) != o.data[b.offset:b.offset + b.size]:
                raise MergeError(f'original object {r} ({a.name}) is not byte-identical')
        else:
            (ao, asz), (bo, bsz) = t.blocks[r], o.blocks[r]
            old = t.data[ao:ao + asz]
            if r == tlist.get(4):
                old += struct.pack(f'<{len(new_anims)}i', *new_anims)
            if old != o.data[bo:bo + bsz]:
                raise MergeError(f'original memory block {r} is not byte-identical')
    back = {v: k for k, v in remap.items()}
    meta_back = {v: k for k, v in metas.items()}
    s_refs = ref_blocks(s)
    for sref, tref in remap.items():
        if tref < n_old:
            continue                                    # the shared skeleton
        a, b = s.items[sref], o.items[tref]
        if (a is None) != (b is None):
            raise MergeError(f'transplanted item {sref} -> {tref} changed kind')
        if a is not None:
            rec = bytearray(o.data[b.offset:b.offset + b.size])
            struct.pack_into('<I', rec, 0, meta_back[b.meta])
            for f in b.fields.values():
                if f.type in REF_FIELDS and f.value != -1:
                    struct.pack_into('<i', rec, f.offset - b.offset, back[f.value])
            if bytes(rec) != s.data[a.offset:a.offset + a.size]:
                raise MergeError(f'transplanted object {sref} ({a.name}) differs from its source')
        else:
            (ao, asz), (bo, bsz) = s.blocks[sref], o.blocks[tref]
            data = o.data[bo:bo + bsz]
            if sref in s_refs:
                vals = struct.unpack(f'<{bsz // 4}i', data)
                data = struct.pack(f'<{len(vals)}i', *(back[v] if v != -1 else -1 for v in vals))
            if data != s.data[ao:ao + asz]:
                raise MergeError(f'transplanted memory block {sref} differs from its source')
    names = [n.lower() for n in clip_names(o)]
    if len(set(names)) != len(names):
        raise MergeError('clip names are not unique after the merge')
    absent = [n for n in wanted if n not in names]
    if absent:
        raise MergeError(f'clips absent after the merge: {absent}')
    return {'animations_before': len(clip_names(t)), 'animations_after': len(names),
            'items_before': n_old, 'items_after': len(o.items),
            'directory_entries_added': o.header[1] - t.header[1],
            'bytes': len(out), 'sha256': hashlib.sha256(out).hexdigest()}
