"""Invented menu graphs, palettes and asymmetric glyph atlases; no game inputs."""
import xml.etree.ElementTree as ET
import struct

import numpy as np

from xml1build import menu_theme as T, menu_conversion as M, main_fonts as MF
from xml1build.igb_file import IgbError, IgbFile
from test_main_appearance import fixture, palette, raises, metrics
from test_hero_icons import icon_igb


def alias_scene(*, broken=False):
    identity = [float(i in (0, 5, 10, 15)) for i in range(16)]
    identity[12:15] = [256, 0, 192]
    schemas = [('igTransform', None, [(2, 's'), (8, 'm')]),
               ('igHashedUserInfo', None, [(2, 's')]), ('igStringValue', None, [(2, 's')])]
    objects = [('igTransform', {2: 'row1', 8: identity}),
               ('igHashedUserInfo', {2: 'row1'}), ('igStringValue', {2: 'other' if broken else 'row1'})]
    return fixture(schemas, objects, (b'synthetic resource block',))


def test_variable_alias_renaming_preserves_references_and_memory():
    source = alias_scene()
    data, report = M.rename_aliases(source, {'row1': 'native_control01'})
    before, after = IgbFile(source), IgbFile(data)
    assert report == {'row1': 3}
    assert len(data) > len(source) and before.index == after.index
    assert [o.get(2) for o in after.objects] == ['native_control01'] * 3
    assert before.blocks
    for ref, (offset, size) in before.blocks.items():
        new_offset, new_size = after.block(ref)
        assert size == new_size and source[offset:offset + size] == data[new_offset:new_offset + size]


def test_alias_import_refuses_transform_only_rename_and_collisions():
    raises(IgbError, lambda: M.rename_aliases(alias_scene(broken=True), {'row1': 'native_control01'}))
    raises(IgbError, lambda: M.rename_aliases(alias_scene(broken=True), {'row1': 'other'}))
    raises(IgbError, lambda: M.rename_aliases(alias_scene(), {'absent': 'native_control01'}))


def placement_scene(shared=False):
    matrix = [float(i in (0, 5, 10, 15)) for i in range(16)]
    specs = [('igTransform', None, [(2, 's'), (8, 'm'), (11, 'r')]),
             ('igHashedUserInfo', None, [(2, 's'), (3, 'r')]),
             ('igAABox', None, [(2, 'v'), (3, 'v')]),
             ('igSyntheticSequence', None, [(2, 'i')])]
    objects = [('igTransform', {2: 'synth_widget', 8: matrix, 11: 3}),
               ('igHashedUserInfo', {2: 'synth_widget', 3: 2}),
               ('igAABox', {2: [-1, 0, -1], 3: [1, 0, 1]}),
               ('igSyntheticSequence', {2: 938})]
    if shared:
        objects.append(('igHashedUserInfo', {2: 'synth_other', 3: 2}))
    return fixture(specs, objects)


def test_widget_placement_updates_hit_bounds_and_detaches_animation_without_editing_keys():
    source = placement_scene()
    result = IgbFile(M.place_anchors(source, {'synth_widget': ((200, -80, 190), (-40, -30, 40, 30))}))
    assert result.obj(0).get(8)[12:15] == [200, -80, 190]
    assert result.obj(0).get(11) == -1
    assert result.obj(2).get(2) == [-40, 0, -30] and result.obj(2).get(3) == [40, 0, 30]
    assert result.obj(3).get(2) == 938
    layout = {'synth_widget': ((200, -80, 190), (-40, -30, 40, 30))}
    assert not M.placement_problems(result.edited(), layout)
    result.set_floats(result.obj(2), 3, [41, 0, 30])
    assert any('bounds drift' in p for p in M.placement_problems(result.edited(), layout))


def test_widget_placement_refuses_shared_bounds_missing_alias_and_nonfinite_geometry():
    spec = {'synth_widget': ((200, -80, 190), (-40, -30, 40, 30))}
    raises(IgbError, lambda: M.place_anchors(placement_scene(True), spec))
    raises(IgbError, lambda: M.place_anchors(placement_scene(), {'missing': next(iter(spec.values()))}))
    raises(IgbError, lambda: M.place_anchors(placement_scene(), {'synth_widget': ((0, 0, float('nan')), (-1, -1, 1, 1))}))


def test_shared_allocator_preserves_headroom_and_legacy_focus_colours():
    colors, styles, mapping = T.allocate(ET.Element('colors'), ET.Element('styles'), palette(), [
        {'name': 'SYNTH_LIST', 'font': 'medium', 'color': '1', 'color_focus': '4', 'color_disabled': '5'}])
    assert len(colors) == 3 and len(styles) == 1
    assert styles[0].get('color_nofocus') == mapping[1]
    assert styles[0].get('color_highlight') == mapping[4]
    again = T.allocate(colors, styles, palette(), [
        {'name': 'SYNTH_LIST', 'font': 'medium', 'color': '1', 'color_focus': '4', 'color_disabled': '5'}])
    assert ET.tostring(again[0]) == ET.tostring(colors) and ET.tostring(again[1]) == ET.tostring(styles)


def test_shared_allocator_refuses_reserved_capacity_without_partial_mutation():
    colors = ET.Element('colors')
    for i in range(T.COLOR_LIMIT - T.COLOR_RESERVE):
        ET.SubElement(colors, 'color', id=str(i), value='1 0 0 1')
    before = ET.tostring(colors)
    raises(ValueError, lambda: T.allocate(colors, ET.Element('styles'), palette(), [T.text_style('SYNTH')]))
    assert ET.tostring(colors) == before
    styles = ET.Element('styles')
    for i in range(T.STYLE_LIMIT - T.STYLE_RESERVE):
        ET.SubElement(styles, 'style', name=f'SYNTH_{i}')
    raises(ValueError, lambda: T.allocate(ET.Element('colors'), styles, palette(), [T.text_style('NEW')]))


def test_pulsing_original_colour_is_not_replaced_with_static_match():
    source = palette()
    source[0].set('pulse', '1 1 1 1')
    base = ET.Element('colors')
    ET.SubElement(base, 'color', id='0', value=source[0].get('value'))
    colors, _, mapping = T.allocate(base, ET.Element('styles'), source, [T.text_style('SYNTH')])
    assert mapping[0] != '0' and colors[int(mapping[0])].get('pulse') == '1 1 1 1'


def test_package_collects_nested_focus_models_and_preserves_dynamic_resources():
    menu = ET.fromstring('<MENU igb="synth_scene"><item name="row1"><onfocus model="ui/models/synth_focus"/>'
                         '</item><items file="synth_helper" igb="synth_back"/></MENU>')
    inherited = ET.fromstring('<packagedef><texture filename="textures/synth_dynamic"/></packagedef>')
    entries = {(e.tag, e.get('filename')) for e in M.package_for(menu, inherited=inherited)}
    assert entries == {('model', 'ui/menus/synth_scene'), ('model', 'ui/models/synth_focus'),
                       ('model', 'ui/menus/synth_back'), ('xml', 'ui/menus/synth_helper'),
                       ('texture', 'textures/synth_dynamic')}


def test_widget_validation_detects_broken_focus_and_missing_anchor():
    root = ET.fromstring('<MENU><item name="row1" up="row1" down="row1"/></MENU>')
    assert not M.widget_problems(root, alias_scene(), focus_names=('row1',))
    root[0].set('down', 'missing')
    assert any('broken down' in s for s in M.widget_problems(root, alias_scene(), focus_names=('row1',)))
    root[0].set('name', 'missing')
    assert any('missing scene anchor' in s for s in M.widget_problems(root, alias_scene()))


def test_combined_font_glyph_samples_the_correct_uv_quadrant():
    # Four deliberately distinct quadrants expose vertical flips and atlas offsets.
    pixels = np.zeros((32, 32, 4), np.uint8)
    pixels[:16, :16] = (240, 0, 0, 255)
    pixels[:16, 16:] = (0, 240, 0, 255)
    pixels[16:, :16] = (0, 0, 240, 255)
    pixels[16:, 16:] = (240, 240, 0, 255)
    def font(data):
        g = IgbFile(icon_igb(data))
        image = g.objects_of('igImage')[0]
        offset, size = g.block(image.get(13))
        for start in range(offset, offset + size, 16):
            g.buf[start:start + 8] = b'\xff' * 8
        return g.edited()
    original, pc = font(pixels), font(pixels[:, ::-1].copy())
    combined, report = MF.combined_atlas(original, pc)
    source_metrics, pc_metrics = metrics((65,), 7), metrics((65, 200), 11)
    for root in (source_metrics, pc_metrics):
        for glyph in root:
            glyph.attrib.update(s='.6', s2='.9', t='.1', t2='.4')
    table, kept = MF.combine_metrics(source_metrics, pc_metrics, (32, 32), (32, 32), report['canvas_size'])
    rgba = MF._image(IgbFile(combined))
    for glyph in table:
        number = int(glyph.get('num'))
        x = int((float(glyph.get('s')) + float(glyph.get('s2'))) / 2 * rgba.shape[1])
        y = int((float(glyph.get('t')) + float(glyph.get('t2'))) / 2 * rgba.shape[0])
        reference = MF._image(IgbFile(pc if number in kept else original))
        assert np.array_equal(rgba[y, x], reference[8, 24])
    assert not np.array_equal(rgba[8, 24], rgba[24, 24])


def flat_panel(uv):
    schemas = [('igVertexArray1_1', None, [(2, 'b'), (3, 'i')]),
               ('igAABox', None, [(2, 'v'), (3, 'v')])]
    # Four corner vertices. Reference numbers: two objects, then four blocks.
    refs = [3] + [-1] * 10 + [4] + [-1] * 8
    vertices = (0, 0, 0, 100, 0, 0, 0, 0, 100, 100, 0, 100)
    return fixture(schemas, [('igVertexArray1_1', {2: 2, 3: 4}),
                             ('igAABox', {2: [0, 0, 0], 3: [100, 0, 100]})], (
        struct.pack('<20i', *refs), struct.pack('<12f', *vertices), struct.pack('<8f', *uv)))


def test_frame_fitting_keeps_atlas_quadrant_and_updates_culling_bounds():
    # A lower-right atlas cell must remain there after geometry fitting.
    uv = (.5, .5, 1, .5, .5, 1, 1, 1)
    data, report = M.fit_flat_panel(flat_panel(uv), (20, 40, 180, 240), border=10)
    g = IgbFile(data)
    assert tuple(g.block_floats(4)) == uv
    assert g.objects_of('igAABox')[0].get(2) == [20, 0, 40]
    assert g.objects_of('igAABox')[0].get(3) == [180, 0, 240]
    assert report['tiled_fills'] == 0


def test_objective_selector_rejects_frame_centred_on_hit_anchor():
    from xml1build import pause_appearance as P
    source = flat_panel((0, 0, 1, 0, 0, 1, 1, 1))
    old, _ = M.fit_flat_panel(source, (-40, -22, 40, 22), border=5)
    fitted, _ = M.fit_flat_panel(source, P.OBJECTIVES_PICTURE_FRAME, border=5)
    assert P.selector_problems(old)
    assert not P.selector_problems(fitted)


def test_frame_fitting_preserves_tiled_fill_orientation_and_density():
    uv = (-1, -2, 1, -2, -1, 2, 1, 2)
    data, _ = M.fit_flat_panel(flat_panel(uv), (0, 0, 200, 150), border=10)
    mapped = IgbFile(data).block_floats(4)
    assert mapped == [-2, -3, 2, -3, -2, 3, 2, 3]
    raises(IgbError, lambda: M.fit_flat_panel(flat_panel(uv), (0, 0, 10, 100), border=10))


def test_foreground_chrome_keeps_screen_shape_and_uvs_in_front_of_world_but_behind_text():
    source = IgbFile(flat_panel((0, 0, 1, 0, 0, 1, 1, 1)))
    vertices = source.block_floats(3)
    vertices[1::3] = [130, 230, 130, 230]
    source.set_block_floats(3, vertices)
    source.set_floats(source.obj(1), 2, [0, 130, 0])
    source.set_floats(source.obj(1), 3, [100, 230, 100])
    result = IgbFile(M.foreground_chrome(source.edited()))
    after = result.block_floats(3)
    assert after[0::3] == vertices[0::3] and after[2::3] == vertices[2::3]
    assert min(after[1::3]) == -110 and max(after[1::3]) == -90
    assert -150 < min(after[1::3])  # Native text is in front of every panel.
    assert result.obj(1).get(2) == [0, -110, 0]
    assert result.obj(1).get(3) == [100, -90, 100]
    assert result.block_floats(4) == source.block_floats(4)


def test_native_row_frame_stays_behind_its_glyph_plane():
    source = flat_panel((0, 0, 1, 0, 0, 1, 1, 1))
    graph = IgbFile(M.foreground_chrome(source, layer=(2, 4)))
    assert graph.block_floats(3)[1::3] == [3] * 4
    assert graph.obj(1).get(2)[1] == graph.obj(1).get(3)[1] == 3


def test_selection_tint_preserves_native_alpha_and_geometry():
    schemas = [('igVertexArray1_1', None, [(2, 'b'), (3, 'i')])]
    refs = [-1, -1, 2] + [-1] * 17
    colors = bytes((200, 100, 0, 70, 100, 50, 0, 255))
    source = fixture(schemas, [('igVertexArray1_1', {2: 1, 3: 2})],
                     (struct.pack('<20i', *refs), colors))
    data = M.tint_vertex_colors(source, (.25, .5, 1))
    g = IgbFile(data)
    offset, size = g.block(2)
    assert data[offset:offset + size] == bytes((50, 100, 200, 70, 25, 50, 100, 255))


def test_panel_tint_updates_animation_rgb_but_preserves_alpha_and_other_blocks():
    schemas = [('igMaterialAttr', None, [(5, 'q'), (6, 'q'), (7, 'q')]),
               ('igDataList', None, [(2, 'i'), (3, 'i'), (4, 'b')]),
               ('igVec4fList', 'igDataList', [(2, 'i'), (3, 'i'), (4, 'b')])]
    source = fixture(schemas, [
        ('igMaterialAttr', {5: [.2, .4, .8, .5], 6: [1, 1, 1, .75], 7: [0, 0, 0, 1]}),
        ('igVec4fList', {2: 2, 3: 2, 4: 2})],
        (struct.pack('<8f', 1, .5, 0, .25, .5, .2, 0, .75), b'synthetic texture'))
    tinted = M.tint_panel_materials(source, (.25, .5, 1))
    g = IgbFile(tinted)
    assert all(abs(a - b) < 1e-6 for a, b in zip(g.obj(0).get(5), [.2, .4, .8, .5]))
    assert g.obj(0).get(6) == [.25, .5, 1, .75]
    assert g.block_floats(2) == [.25, .5, 1, .25, .125, .25, .5, .75]
    offset, size = g.block(3)
    assert tinted[offset:offset + size] == b'synthetic texture'
    raises(IgbError, lambda: M.tint_panel_materials(source, (float('nan'), 0, 0)))


def test_opaque_subpanel_preserves_edge_texture_and_removes_material_fade():
    # A flat pane with a material shared by its animation keys. Opacity is an
    # explicit subpanel choice; the ordinary dialog retains the authored alpha.
    schemas = [('igVertexArray1_1', None, [(2, 'b'), (3, 'i')]),
               ('igMaterialAttr', None, [(5, 'q'), (6, 'q'), (7, 'q')]),
               ('igDataList', None, [(2, 'i'), (3, 'i'), (4, 'b')]),
               ('igVec4fList', 'igDataList', [(2, 'i'), (3, 'i'), (4, 'b')])]
    refs = [4] + [-1] * 19
    source = fixture(schemas, [('igVertexArray1_1', {2: 3, 3: 4}),
        ('igMaterialAttr', {5: [1, 1, 1, .5], 6: [1, 1, 1, .5], 7: [1, 1, 1, .5]}),
        ('igVec4fList', {2: 2, 3: 2, 4: 5})], (
            struct.pack('<20i', *refs), struct.pack('<12f', 0, 0, 0, 100, 0, 0, 0, 0, 100, 100, 0, 100),
            struct.pack('<8f', 1, 1, 1, 0, .5, .5, .5, .8), b'synthetic edge texture'))
    fitted, _ = M.fit_flat_panel(source, (0, 0, 200, 200), opaque=True)
    g = IgbFile(fitted)
    assert all(g.obj(1).get(slot)[3] == 1 for slot in (5, 6, 7))
    assert g.block_floats(5)[3::4] == [1, 1]
    offset, size = g.block(6)
    assert fitted[offset:offset + size] == b'synthetic edge texture'


def test_embedded_chrome_opacity_freezes_pumps_without_moving_transforms_or_pixels():
    schemas = [('igTransform', None, [(2, 's'), (8, 'm')]),
               ('igMaterialAttr', None, [(5, 'q'), (6, 'q'), (7, 'q')]),
               ('igColorAttr', None, [(4, 'q')]),
               ('igDataPumpVec4fLinearInterface', None, [(2, 'q')]),
               ('igDataList', None, [(2, 'i'), (3, 'i'), (4, 'b')]),
               ('igVec4fList', 'igDataList', [(2, 'i'), (3, 'i'), (4, 'b')])]
    matrix = [float(i in (0, 5, 10, 15)) for i in range(16)]
    source = fixture(schemas, [('igTransform', {2: 'synthetic_panel', 8: matrix}),
        ('igMaterialAttr', {5: [1, .5, .25, 0], 6: [1, 1, 1, .8], 7: [0, 0, 0, .2]}),
        ('igColorAttr', {4: [1, 1, 1, 0]}), ('igDataPumpVec4fLinearInterface', {2: [0, 0, 0, 0]}),
        ('igVec4fList', {2: 2, 3: 2, 4: 5})],
        (struct.pack('<8f', 1, .5, .25, 0, .5, .2, .1, .8), b'synthetic pixels'))
    result = M.opaque_materials(source)
    g = IgbFile(result)
    assert g.obj(0).get(8) == matrix
    assert all(g.obj(1).get(slot)[3] == 1 for slot in (5, 6, 7))
    assert g.obj(2).get(4) == [1, 1, 1, 1]
    assert g.obj(3).get(2) == [0, 0, 0, 1]
    assert g.block_floats(5)[3::4] == [1, 1]
    offset, size = g.block(6)
    assert result[offset:offset + size] == b'synthetic pixels'
