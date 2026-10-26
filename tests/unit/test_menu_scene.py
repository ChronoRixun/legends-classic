"""Synthetic scenes distinguish references from numeric keys and pixel bytes."""
import struct

from xml1build import menu_scene as S
from xml1build.igb_file import IgbError, IgbFile
from test_main_appearance import fixture, raises


def scene(name, *, light_root=False, textures=False):
    schemas = [('igDataList', None, [(2, 'i'), (3, 'i'), (4, 'b')]),
               ('igObjectList', 'igDataList', [(2, 'i'), (3, 'i'), (4, 'b')])]
    for kind in ('igInfoList', 'igNodeList', 'igTextureList', 'igGraphPathList'):
        schemas.append((kind, 'igObjectList', [(2, 'i'), (3, 'i'), (4, 'b')]))
    schemas += [('igLongList', 'igDataList', [(2, 'i'), (3, 'i'), (4, 'b')]),
                ('igSceneInfo', None, [(5, 'r'), (6, 'r'), (7, 'r'), (11, 'r')]),
                ('igGroup', None, [(2, 's'), (3, 'r'), (5, 'i'), (7, 'r')]),
                ('igTransform', None, [(2, 's'), (8, 'm')])]
    if light_root:
        schemas.append(('igLightStateSet', 'igGroup', [(2, 's'), (3, 'r'), (5, 'i'), (7, 'r')]))
    matrix = [float(i in (0, 5, 10, 15)) for i in range(16)]
    objects = [('igInfoList', {2: 1, 3: 1, 4: 9}),
               ('igSceneInfo', {5: 2, 6: 4, 7: 5, 11: 6}),
               ('igLightStateSet' if light_root else 'igGroup', {2: 'synth_root', 3: -1, 5: 0, 7: 3}),
               ('igNodeList', {2: 1, 3: 1, 4: 10}),
               ('igTextureList', {2: int(textures), 3: int(textures), 4: 12 if textures else -1}),
               ('igGraphPathList', {2: 0, 3: 0, 4: -1}),
               ('igNodeList', {2: 0, 3: 0, 4: -1}),
               ('igTransform', {2: name, 8: matrix}),
               ('igLongList', {2: 2, 3: 2, 4: 11})]
    return fixture(schemas, objects, (struct.pack('<i', 1), struct.pack('<i', 7),
                                      struct.pack('<2i', 1, 7), struct.pack('<i',7) if textures else b'synthetic pixels'))


def test_scene_attachment_relocates_object_lists_but_preserves_numeric_keys_and_pixels():
    native, art = scene('synth_native'), scene('synth_art')
    data, report = S.attach(native, art)
    g, before = IgbFile(data), IgbFile(native)
    assert report['scene_infos'] == 1 and len(g.objects_of('igSceneInfo')) == 1
    assert g.obj(7).get(2) == 'synth_native'  # Every native reference number stays stable.
    root_children = g.list_items(3)
    assert len(root_children) == 2 and root_children[0] == 7
    art_root = g.obj(root_children[1])
    art_children = g.list_items(art_root.get(7))
    assert g.obj(art_children[0]).get(2) == 'synth_art' and art_children[0] != 7
    for values in g.objects_of('igLongList'):
        assert g.ref_list(values.get(4)) == [1, 7]  # Integers resembling references are not relocated.
    blobs = [data[o:o + n] for o, n in g.blocks.values()]
    assert blobs.count(b'synthetic pixels') == 2
    assert native == scene('synth_native') and art == scene('synth_art')


def test_scene_attachment_refuses_existing_native_camera_resources():
    g = IgbFile(scene('synth_native'))
    field = g.obj(5).fields[2]
    struct.pack_into('<i', g.buf, field.offset, 1)
    raises(IgbError, lambda: S.attach(g.edited(), scene('synth_art')))


def test_scene_attachment_retains_light_state_group_root_and_native_references():
    result, _ = S.attach(scene('synthetic_light', light_root=True), scene('synthetic_art'))
    graph = IgbFile(result)
    assert graph.obj(2).name == 'igLightStateSet'
    assert graph.obj(7).get(2) == 'synthetic_light'
    assert len(graph.list_items(3)) == 2


def test_scene_attachment_refuses_schema_mismatch_and_dangling_reference_array():
    bad = bytearray(scene('synth_art'))
    # Serialized field version differs even though the local reader can decode it.
    struct.pack_into('<I', bad, 48 + 4, 2)
    raises(IgbError, lambda: S.attach(scene('synth_native'), bytes(bad)))
    g = IgbFile(scene('synth_art'))
    offset, _ = g.block(10)
    struct.pack_into('<i', g.buf, offset, 9000)
    raises(IgbError, lambda: S.attach(scene('synth_native'), g.edited()))


def instance_scene(art=False):
    fields = [(2, 'i'), (3, 'i'), (4, 'b')]
    schemas = [('igDataList', None, fields), ('igObjectList', 'igDataList', fields)]
    schemas += [(name, 'igObjectList', fields) for name in
                ('igInfoList', 'igNodeList', 'igTextureList', 'igGraphPathList')]
    group = [(2, 's'), (3, 'r'), (5, 'i'), (7, 'r')]
    schemas += [('igGroup', None, group), ('igTransform', 'igGroup', group+[(8, 'm')]),
                ('igSceneInfo', None, [(5, 'r'), (6, 'r'), (7, 'r'), (11, 'r')]),
                ('igGraphPath', None, [(2, 'r')]), ('igDataPumpInfo', None, [(2, 'r')])]
    matrix = [float(i in (0, 5, 10, 15)) for i in range(16)]
    n = 9 if art else 13
    objects = [('igInfoList', {2: 2 if art else 1, 3: 2 if art else 1, 4: n}),
               ('igSceneInfo', {5: 2, 6: 4, 7: 5, 11: 6}),
               ('igGroup', {2: 'synth_root', 3: -1, 5: 0, 7: 3}),
               ('igNodeList', {2: 1 if art else 2, 3: 1 if art else 2, 4: n+1}),
               ('igTextureList', {2: 0, 3: 0, 4: -1}),
               ('igGraphPathList', {2: 0 if art else 1, 3: 0 if art else 1, 4: -1 if art else n+4}),
               ('igNodeList', {2: 0, 3: 0, 4: -1})]
    if art:
        objects += [('igGroup', {2: 'flat_art', 3: -1, 5: 0, 7: -1}),
                    ('igDataPumpInfo', {2: -1})]
        blocks = (struct.pack('<2i',8,1), struct.pack('<i',7))
    else:
        objects += [('igTransform', {2: 'bone_a', 3: -1, 5: 0, 7: 9, 8: matrix}),
                    ('igTransform', {2: 'bone_b', 3: -1, 5: 0, 7: 10, 8: matrix}),
                    ('igNodeList', {2: 1, 3: 1, 4: n+2}),
                    ('igNodeList', {2: 1, 3: 1, 4: n+3}), ('igGraphPath', {2: -1}),
                    ('igGroup', {2: 'synth_leaf', 3: -1, 5: 0, 7: -1})]
        blocks = tuple(struct.pack('<'+'i'*len(row),*row) for row in ([1],[7,8],[12],[12],[11]))
    return fixture(schemas,objects,blocks)


def test_flat_panel_instancing_keeps_camera_and_retires_model_local_pump_registration():
    art = S.static_model(instance_scene(True))
    result,_ = S.attach(instance_scene(),art,anchors=('bone_a','bone_b'),keep_camera=True)
    graph = IgbFile(result)
    assert graph.list_items(3) == [7,8]
    first,second = graph.list_items(9),graph.list_items(10)
    assert first[0] == second[0] == 12 and first[-1] == second[-1]
    assert graph.obj(first[-1]).name == 'igGroup'
    assert graph.obj(1).get(7) == 5 and graph.list_items(5) == [11]
    assert [graph.obj(ref).name for ref in graph.list_items(0)] == ['igSceneInfo']
    assert len(graph.objects_of('igDataPumpInfo')) == 1  # Retained, but no longer a registered animation owner.
    raises(IgbError,lambda:S.attach(instance_scene(),art,anchors=('missing',),keep_camera=True))
    raises(IgbError,lambda:S.attach(instance_scene(),instance_scene(True),anchors=('bone_a',),keep_camera=True))


def test_panel_attachment_keeps_both_texture_registrations_when_requested():
    # Reuse a nonempty existing typed reference buffer as a synthetic texture
    # registration; attachment must preserve both sides, not discard the first.
    data=scene('synth_panel',textures=True)
    raises(IgbError,lambda:S.attach(data,data))
    result,_=S.attach(data,data,merge_textures=True)
    out=IgbFile(result)
    textures=out.obj(out.objects_of('igSceneInfo')[0].get(6))
    refs=out.list_items(textures.ref)
    assert len(refs)==2 and refs[0]==7 and refs[1]!=7
    assert all(out.obj(ref).get(2)=='synth_panel' for ref in refs)
