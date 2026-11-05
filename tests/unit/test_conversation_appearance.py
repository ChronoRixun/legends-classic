"""Invented transformed conversation scenes; never uses game files or pixel fixtures."""
import struct
from types import SimpleNamespace
from unittest.mock import patch

from xml1build import common as C
from xml1build.igb_file import IgbError, IgbFile
from xml1build.sources import Sources
from test_main_appearance import fixture


MODEL = 'UI/hud/convo_background.IGB'


def appearance():
    from xml1build import conversation_appearance
    return conversation_appearance


def scene(*, shared=False, colored=False, wrong_type=None):
    """Two transformed meshes, distinct image encodings and optional shared pixels."""
    lst = [(2, 'i'), (3, 'i'), (4, 'b')]
    specs = [('igDataList', None, []), ('igNodeList', 'igDataList', lst),
             ('igAttrList', 'igDataList', lst), ('igInfoList', 'igDataList', lst),
             ('igSceneInfo', None, [(5, 'r')]),
             ('igGroup', None, [(7, 'r')]),
             ('igTransform', None, [(7, 'r'), (8, 'm')]),
             ('igGeometry', None, [(7, 'r'), (8, 'r')]),
             ('igGeometryAttr1_5', None, [(4, 'r'), (5, 'r'), (6, 'i')]),
             ('igVertexArray1_1', None, [(2, 'b'), (3, 'i'), (6, 'i')]),
             ('igIndexArray', None, [(2, 'b'), (3, 'i')]),
             ('igTextureBindAttr', None, [(4, 'r')]),
             ('igTextureAttr', None, [(12, 'r')]),
             ('igImage', None, [(2, 'i'), (3, 'i'), (11, 'i'), (12, 'i'), (13, 'b')])]
    if wrong_type:
        owner, slot, kind = wrong_type
        specs = [(name, parent, [(n, kind if name == owner and n == slot else t) for n, t in fields])
                 for name, parent, fields in specs]
    objects, blocks, fixups = [], [], []

    def obj(kind, values):
        objects.append((kind, values))
        return len(objects) - 1

    def block(values, slot, data):
        fixups.append((values, slot, len(blocks)))
        blocks.append(data)

    def items(kind, refs):
        values = {2: len(refs), 3: len(refs), 4: -1}
        if refs:
            block(values, 4, struct.pack('<' + 'i' * len(refs), *refs))
        return obj(kind, values)

    children = []
    shared_pixel = None
    for number in range(2):
        va = {2: -1, 3: 4, 6: 65543 if colored else 65537}
        streams = [-1] * 20
        # Patch the stream table once all object references have been assigned.
        table = len(blocks)
        block(va, 2, b'')
        positions = len(blocks)
        blocks.append(struct.pack('<12f', 0, 0, 0, 20, 0, 0, 0, 0, 20, 20, 0, 20))
        uv = len(blocks)
        blocks.append(struct.pack('<8f', 0, 0, 1, 0, 0, 1, 1, 1))
        fixups.append((streams, 0, positions))
        fixups.append((streams, 11, uv))
        if colored:
            for slot, data in ((1, struct.pack('<12f', *([0, 1, 0] * 4))), (2, bytes([127]) * 16)):
                fixups.append((streams, slot, len(blocks)))
                blocks.append(data)
        fixups.append((blocks, table, streams))
        vertex = obj('igVertexArray1_1', va)
        ia = {2: -1, 3: 4}
        block(ia, 2, struct.pack('<4H', 0, 1, 2, 3))
        index = obj('igIndexArray', ia)
        geom = obj('igGeometryAttr1_5', {4: vertex, 5: index, 6: 4})
        fmt = 15 if number == 0 or shared else 7
        image = {2: 4, 3: 4, 11: fmt, 12: 16 if fmt == 15 else 64, 13: -1}
        if shared and shared_pixel is not None:
            fixups.append((image, 13, shared_pixel))
        else:
            shared_pixel = len(blocks)
            block(image, 13, bytes([number + 3]) * image[12])
        texture = obj('igTextureAttr', {12: obj('igImage', image)})
        binding = obj('igTextureBindAttr', {4: texture})
        mesh = obj('igGeometry', {7: -1, 8: items('igAttrList', [geom, binding])})
        matrix = [float(i in (0, 5, 10, 15)) for i in range(16)]
        matrix[0], matrix[12], matrix[14] = 1.25, number * 30., 12.
        children.append(obj('igTransform', {7: items('igNodeList', [mesh]), 8: matrix}))
    root = obj('igGroup', {7: items('igNodeList', children)})
    info = obj('igSceneInfo', {5: root})
    loader_root = items('igInfoList', [info])
    for values, slot, value in fixups:
        if values is not blocks:
            values[slot] = len(objects) + value
    for values, slot, value in fixups:
        if values is blocks:
            values[slot] = struct.pack('<20i', *value)
    result = bytearray(fixture(specs, objects, blocks))
    graph = IgbFile(result)
    struct.pack_into('<i', result, graph._obj_start - 4, loader_root)
    return bytes(result)


def reject(data, message):
    try:
        appearance().convert(data, scene())
    except IgbError as exc:
        assert message in str(exc), str(exc)
        assert '--classic-conversation off' in str(exc)
    else:
        raise AssertionError('unsupported scene accepted')


def test_conversation_conversion_preserves_transforms_images_and_every_source_byte():
    source, pc = scene(), scene(shared=True)
    converted, report = appearance().convert(source, pc)
    assert converted == source
    assert appearance().convert(source, pc) == (converted, report)
    assert report['geometries'] == 2 and report['transforms'] == 2 and report['images'] == 2
    assert not appearance().problems(converted)


def test_conversation_shared_readonly_image_blocks_are_supported():
    data = scene(shared=True)
    assert appearance().convert(data, scene())[0] == data


def test_conversation_supports_normal_and_packed_color_streams_without_modifying_them():
    data = scene(colored=True)
    assert appearance().convert(data, scene())[0] == data
    graph = IgbFile(data)
    graph.set_int(graph.objects_of('igVertexArray1_1')[0], 6, 65538)
    reject(graph.edited(), 'layout')


def test_conversation_rejects_truncated_data_and_unsupported_layout():
    data = scene()
    for end in (0, 30, 64, len(data) - 1, len(data) - 16):
        reject(data[:end], '')
    bad = bytearray(data)
    struct.pack_into('<I', bad, 44, 0xb0000006)
    reject(bad, 'layout')


def test_conversation_rejects_missing_references_and_out_of_range_indices():
    graph = IgbFile(scene())
    graph.set_int(graph.objects_of('igTextureAttr')[0], 12, 99999)
    reject(graph.edited(), 'reference')
    graph = IgbFile(scene())
    off, _ = graph.block(graph.objects_of('igIndexArray')[0].get(2))
    struct.pack_into('<H', graph.buf, off, 4)
    reject(graph.edited(), 'index')


def test_conversation_rejects_loader_root_drift_and_cyclic_scene_graph():
    graph = IgbFile(scene())
    struct.pack_into('<i', graph.buf, graph._obj_start - 4, 0)
    reject(graph.edited(), 'root')
    graph = IgbFile(scene())
    transform = graph.objects_of('igTransform')[0]
    child_list = graph.obj(transform.get(7))
    off, _ = graph.block(child_list.get(4))
    struct.pack_into('<i', graph.buf, off, transform.ref)
    reject(graph.edited(), 'cyclic')


def test_conversation_rejects_wrong_reference_field_types_with_actionable_diagnostic():
    for owner, slot in (('igImage', 13), ('igVertexArray1_1', 2), ('igNodeList', 4),
                        ('igTextureAttr', 12), ('igTextureBindAttr', 4), ('igSceneInfo', 5)):
        for kind in ('f', 'i'):
            data = scene(wrong_type=(owner, slot, kind))
            assert appearance().problems(data), (owner, slot, kind)
            reject(data, 'reference')


def test_conversation_rejects_nonfinite_geometry_and_projective_transforms():
    graph = IgbFile(scene())
    ref = graph.ref_list(graph.objects_of('igVertexArray1_1')[0].get(2))[0]
    vertices = graph.block_floats(ref)
    vertices[0] = float('nan')
    graph.set_block_floats(ref, vertices)
    reject(graph.edited(), 'finite')
    graph = IgbFile(scene())
    graph.set_floats(graph.objects_of('igTransform')[0], 8, [2.], first=15)
    reject(graph.edited(), 'transform')


def test_conversation_rejects_bad_image_lengths_encoding_and_shared_stream_aliases():
    for slot, value in ((12, 999), (11, 99), (2, 0), (13, -1)):
        graph = IgbFile(scene())
        graph.set_int(graph.objects_of('igImage')[0], slot, value)
        reject(graph.edited(), 'image')
    graph = IgbFile(scene())
    va = graph.objects_of('igVertexArray1_1')[0]
    off, _ = graph.block(va.get(2))
    struct.pack_into('<i', graph.buf, off + 11 * 4, graph.ref_list(va.get(2))[0])
    reject(graph.edited(), 'stream')


def context(tmp_path, option='off', frontend='xml2'):
    root, base, out = (tmp_path / name for name in ('inputs', 'base', 'out'))
    source = root / 'xml1_loose/ui/hud/convo_background.igb'
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(scene())
    target = base / MODEL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(scene(shared=True))
    C.sync_base(base, out, log=lambda *_: None)
    ctx = C.BuildContext(out, base, sources=Sources.developer(base, root=root),
                         args=C.default_args(classic_conversation=option, frontend=frontend, builder_mode=True))
    ctx.build_dir.mkdir(parents=True, exist_ok=True)
    ctx.module = 'frontend'
    return ctx, source, target


def test_conversation_write_is_opt_in_and_has_one_output_only(tmp_path):
    ctx, source, base = context(tmp_path)
    assert appearance().write(ctx) == {'mode': 'off'}
    assert not ctx.registry.entries and (ctx.out / MODEL).read_bytes() == base.read_bytes()
    original = source.read_bytes()
    ctx.args.classic_conversation = 'xml1'
    appearance().write(ctx)
    assert set(ctx.registry.entries) == {MODEL.lower()}
    assert (ctx.out / MODEL).read_bytes() == original == source.read_bytes()
    assert ctx.registry.get(MODEL)['owner'] == 'frontend'


def test_conversation_missing_or_invalid_selection_does_not_read_or_write_inputs(tmp_path):
    ctx, _, _ = context(tmp_path)
    del ctx.args.classic_conversation
    with patch.object(ctx, 'x1_path', side_effect=AssertionError('OFF must not read disc')):
        assert appearance().write(ctx) == {'mode': 'off'}
        ctx.args.classic_conversation = 'invalid'
        try:
            appearance().write(ctx)
        except IgbError:
            pass
        else:
            raise AssertionError('invalid selection accepted')
    assert not ctx.registry.entries


def test_conversation_missing_inputs_refused_before_output_is_claimed(tmp_path):
    ctx, _, base = context(tmp_path, 'xml1')
    with patch.object(ctx, 'x1_path', return_value=None):
        try:
            appearance().write(ctx)
        except IgbError as exc:
            assert 'Re-prepare' in str(exc) and '--classic-conversation off' in str(exc)
        else:
            raise AssertionError('missing input accepted')
    assert not ctx.registry.entries
    assert (ctx.out / MODEL).read_bytes() == base.read_bytes()


def test_conversation_cancellation_before_and_after_atomic_write_can_resume(tmp_path):
    from xml1builder.cancel import Cancelled
    ctx, source, base = context(tmp_path, 'xml1')

    def cancel(kind, detail):
        if kind == 'conversation':
            raise Cancelled()

    with patch.object(C, '_CHECKPOINT', cancel):
        try:
            appearance().write(ctx)
        except Cancelled:
            pass
        else:
            raise AssertionError('cancel ignored')
    assert (ctx.out / MODEL).read_bytes() == base.read_bytes() and not ctx.registry.entries
    appearance().write(ctx)
    assert (ctx.out / MODEL).read_bytes() == source.read_bytes()

    def cancel_after_write(kind, detail):
        if kind == 'write':
            raise Cancelled()

    with patch.object(C, '_CHECKPOINT', cancel_after_write):
        try:
            appearance().write(ctx)
        except Cancelled:
            pass
        else:
            raise AssertionError('post-write cancel ignored')
    assert (ctx.out / MODEL).read_bytes() == source.read_bytes()
    # A restart syncs before conversion, so even an uncommitted write is reset.
    ctx.registry = C.Registry()
    C.sync_base(ctx.base, ctx.out, log=lambda *_: None)
    appearance().write(ctx)
    assert (ctx.out / MODEL).read_bytes() == source.read_bytes()


def test_conversation_bad_input_leaves_native_output_and_reports_recovery(tmp_path):
    ctx, source, base = context(tmp_path, 'xml1')
    source.write_bytes(b'synthetic invalid scene')
    try:
        appearance().write(ctx)
    except IgbError as exc:
        assert '--classic-conversation off' in str(exc)
    else:
        raise AssertionError('unsupported scene was written')
    assert (ctx.out / MODEL).read_bytes() == base.read_bytes()
    assert not ctx.registry.entries


def test_conversation_frontend_hook_runs_even_with_native_main_menu(tmp_path):
    from xml1build import frontend as F, classic_hud
    ctx, source, _ = context(tmp_path, 'xml1', 'xml2')
    # Unrelated frontend families need their own owned inputs; retain the real conversation writer.
    with patch.object(classic_hud, 'write'), patch.object(F, 'write_personal_items',
            return_value={'problems': [], 'items': [], 'textures': {}}), patch.object(F, 'write_pda_menu'):
        F.run(ctx)
    assert (ctx.out / MODEL).read_bytes() == source.read_bytes()


def test_conversation_validator_compares_selected_owned_bytes_and_off_base(tmp_path):
    from xml1build.validate import Check
    ctx, _, base = context(tmp_path, 'xml1')
    appearance().write(ctx)
    validator = SimpleNamespace(ctx=ctx, idx=ctx.out_index)
    check = Check('conversation', 'conversation appearance')
    appearance().validate(validator, check)
    assert not check.errors
    ctx.args.classic_conversation = 'off'
    check = Check('conversation', 'conversation appearance')
    appearance().validate(validator, check)
    assert check.errors
    (ctx.out / MODEL).write_bytes(base.read_bytes())
    check = Check('conversation', 'conversation appearance')
    appearance().validate(validator, check)
    assert not check.errors
