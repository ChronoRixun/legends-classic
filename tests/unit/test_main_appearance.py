"""Invented palettes, glyphs and scene graphs for the main-menu importer."""
import copy
import struct
import xml.etree.ElementTree as ET

import numpy as np

from xml1build import frontend as F
from xml1build import main_appearance as MA
from xml1build import main_fonts as MF
from xml1build.igb_file import IgbError, IgbFile
from test_hero_icons import icon_igb


def raises(kind, function):
    try:
        function()
    except kind:
        return
    raise AssertionError(f'expected {kind.__name__}')


def palette():
    root = ET.Element('colors')
    for index in range(12):
        ET.SubElement(root, 'color', value=f'{index / 100} {index / 100 + .1} {index / 100 + .2} 1')
    return root


def test_palette_preserves_pc_entries_and_reuses_only_nonpulsing_values():
    source = palette()
    colors = ET.Element('colors')
    ET.SubElement(colors, 'color', id='3', value=source[9].get('value'))
    ET.SubElement(colors, 'color', id='8', value=source[10].get('value'), pulse='1 1 1 1')
    styles = ET.Element('styles'); ET.SubElement(styles, 'style', name='SYNTH_STYLE', font='medium')
    before = copy.deepcopy(colors)
    out, styled, ids = MA.palette_styles(colors, styles, source)
    assert [e.attrib for e in colors] == [e.attrib for e in before]
    assert [e.attrib for e in list(out)[:len(before)]] == [e.attrib for e in before]
    assert ids[9] == '3' and ids[10] != '8'
    assert styled[0].attrib == styles[0].attrib
    assert len({e.get('id') for e in out}) == len(out)
    again, restyled, _ = MA.palette_styles(out, styled, source)
    assert ET.tostring(again) == ET.tostring(out) and ET.tostring(restyled) == ET.tostring(styled)


def test_palette_and_style_capacity_fail_without_trimming():
    colors = ET.Element('colors')
    for index in range(75): ET.SubElement(colors, 'color', id=str(index), value='1 0 0 1')
    styles = ET.Element('styles')
    raises(ValueError, lambda: MA.palette_styles(colors, styles, palette()))
    assert len(colors) == 75
    colors = ET.Element('colors')
    for index in range(31): ET.SubElement(styles, 'style', name=f'SYNTH_{index}')
    raises(ValueError, lambda: MA.palette_styles(colors, styles, palette()))
    assert len(styles) == 31


def test_palette_rejects_duplicate_ids_and_nonfinite_channels():
    root = ET.fromstring('<colors><color id="2" value="0 0 0 1"/><color id="2" value="1 1 1 1"/></colors>')
    raises(ValueError, lambda: MA.palette_styles(root, ET.Element('styles'), palette()))
    source = palette(); source[9].set('value', 'nan 0 0 1')
    raises(ValueError, lambda: MA.palette_styles(ET.Element('colors'), ET.Element('styles'), source))


def metrics(rows, advance):
    root = ET.Element('SYNTH_FONT', height='12')
    for number in rows:
        ET.SubElement(root, 'glyph', num=str(number), width='8', height='8', baseline='7',
                      horizadvance=str(advance), horizoffset='0', s='.25', s2='.5', t='.25', t2='.5')
    return root


def test_metrics_preserve_pc_controls_extended_and_missing_printable_glyphs():
    original, pc = metrics((0, 32, 65), 7), metrics((0, 32, 35, 65, 200), 11)
    out, kept = MF.combine_metrics(original, pc, (32, 32), (32, 32), (64, 32))
    glyphs = {int(e.get('num')): e for e in out}
    assert set(kept) == {0, 35, 200}
    assert glyphs[65].get('horizadvance') == '7' and float(glyphs[65].get('s')) == .125
    for number in kept:
        assert glyphs[number].get('horizadvance') == '11' and float(glyphs[number].get('s')) == .625
    assert original[0].get('s') == '.25' and pc[0].get('s') == '.25'


def test_font_alpha_is_explicit_four_bit_alpha():
    block = bytes((i | ((i + 1) << 4)) for i in range(0, 16, 2)) + struct.pack('<HHI', 0xffff, 0, 0)
    rgba = MF.decode_font_dxt3(block, 4, 4)
    assert np.array_equal(rgba[:, :, 3], np.arange(16, dtype=np.uint8).reshape(4, 4) * 17)
    assert np.all(rgba[:, :, :3] == 255)


def test_combined_atlas_keeps_base_pixels_in_separate_rectangles():
    first = np.full((32, 32, 4), (255, 255, 255, 255), np.uint8)
    second = np.full((32, 32, 4), (0, 0, 0, 255), np.uint8)
    def opaque_font(rgba):
        # icon_igb's RGB block halves are reusable, but fonts use explicit DXT3 alpha.
        g = IgbFile(icon_igb(rgba)); image = g.objects_of('igImage')[0]
        offset, size = g.block(image.get(13))
        for start in range(offset, offset + size, 16): g.buf[start:start + 8] = b'\xff' * 8
        return g.edited()
    data, report = MF.combined_atlas(opaque_font(first), opaque_font(second))
    rgba = MF._image(IgbFile(data))
    assert report['canvas_size'] == (64, 32)
    assert np.array_equal(rgba[:, :32], first) and np.array_equal(rgba[:, 32:], second)


def u32(*values):
    return struct.pack('<' + 'I' * len(values), *(value & 0xffffffff for value in values))


def fixture(schemas, objects, blocks=(), old=False):
    """Minimal original-format writer; all names, geometry and pixel blocks are invented."""
    types = {'i': ('igIntMetaField', 4), 'r': ('igObjectRefMetaField', 4),
             'b': ('igMemoryRefMetaField', 4), 's': ('igStringMetaField', 4),
             'm': ('igMatrix44fMetaField', 64), 'v': ('igVec3fMetaField', 12), 'f': ('igFloatMetaField', 4)}
    specs = [('igObjectDirEntry', None, [(11, 'i')]), ('igMemoryDirEntry', None, [(7, 'i')])] + schemas
    names = {name: index for index, (name, _parent, _fields) in enumerate(specs)}
    keys = list(types)
    fields = u32(*[v for key in keys for v in (len(types[key][0]) + 1, 1, 0)])
    fields += b''.join(types[key][0].encode() + b'\0' for key in keys)
    heads, bodies = b'', b''
    for name, parent, schema in specs:
        raw = name.encode() + b'\0'
        heads += u32(len(raw), 1, 0, len(schema), names[parent] if parent else -1, 0)
        bodies += raw + b''.join(struct.pack('<3H', keys.index(key), slot, types[key][1]) for slot, key in schema)
    metas, encoded = heads + bodies, b''
    for name, values in objects:
        payload = b''
        for slot, key in specs[names[name]][2]:
            value = values[slot]
            if key == 's':
                raw = value.encode() + b'\0'; raw += b'\0' * (-len(raw) % 4); payload += u32(len(raw)) + raw
            elif key in ('m', 'v', 'f'):
                vector = value if key != 'f' else [value]
                payload += struct.pack('<' + 'f' * len(vector), *vector)
            else: payload += u32(value)
        encoded += u32(names[name], 8 + len(payload)) + payload
    directory = b''.join(u32(0, 12, names[name]) for name, _values in objects)
    directory += b''.join(u32(1, 12, len(block)) for block in blocks)
    count = len(objects) + len(blocks)
    index = u32(8 + 2 * count, count) + struct.pack('<' + 'H' * count, *range(count))
    memory = b''
    for block in blocks: memory += b'\0' * (-len(memory) % 4) + block
    memory += b'\0' * (-len(memory) % 4)
    body = fields + u32(4) + metas + u32(4) + (b'' if old else u32(4)) + directory + index + u32(0) + encoded + memory
    return u32(len(directory), count, len(metas), len(specs), len(encoded), len(objects), len(memory), len(blocks),
               len(fields), len(types), 0xfada, 0xb0000006 if old else 0xf0000006) + body


def test_help_alias_moves_all_bindings_and_refuses_unknown_owners():
    matrix = [float(index == 0 or index == 5 or index == 10 or index == 15) for index in range(16)]
    schemas = [('igTransform', None, [(2, 's'), (8, 'm')]), ('igHashedUserInfo', None, [(2, 's')]),
               ('igStringValue', None, [(2, 's')]), ('igNovelAlias', None, [(2, 's')])]
    objects = [('igTransform', {2: 'auxline01', 8: matrix}), ('igHashedUserInfo', {2: 'auxline01'}),
               ('igStringValue', {2: 'auxline01'})]
    data = fixture(schemas, objects)
    out, _ = MA.help_alias(data, 'auxline01', 'newhelp01', 12)
    assert len(out) == len(data) and out.count(b'newhelp01') == 3 and b'auxline01' not in out
    assert IgbFile(out).objects_of('igTransform')[0].get(8)[14] == 12
    objects[-1] = ('igNovelAlias', {2: 'auxline01'})
    bad = fixture(schemas, objects)
    raises(IgbError, lambda: MA.help_alias(bad, 'auxline01', 'newhelp01'))


def test_legacy_pc_layout_omits_only_the_pool_name_section():
    specs = [('igStringValue', None, [(2, 's')])]
    out = fixture(specs, [('igStringValue', {2: 'synthetic'})], old=True)
    assert IgbFile(out).objects[0].get(2) == 'synthetic'
    malformed = bytearray(fixture(specs, [('igStringValue', {2: 'synthetic'})]))
    struct.pack_into('<I', malformed, 44, 0xb0000006)
    raises(IgbError, lambda: IgbFile(malformed))


def test_layout_choice_reaches_both_builder_parsers():
    import build_xml1
    from xml1builder.cli import make_parser
    assert build_xml1.parse_args(['--out', 'synthetic', '--main-menu-layout', 'widescreen']).main_menu_layout == 'widescreen'
    assert make_parser().parse_args(['build', '--main-menu-layout', 'widescreen']).main_menu_layout == 'widescreen'


def test_generated_menu_help_does_not_disable_mouse_and_quit_contract():
    from xml1build import fix_ini as FI
    class Context:
        def read_x1_xml(self, _path):
            root = ET.Element('MENU', desctext1='SYNTH_HELP')
            for number in range(1, 7):
                ET.SubElement(root, 'item', name=f'button{number}', text=f'Choice_{number}')
            return root
    menu = F.menu_tree(Context())
    assert FI.menu_items_for(menu, eighth=True) == ','.join(F.MAIN_MENU_ITEMS_MOUSE_ALL)
    keys = FI.game_keys(main_menu_items=FI.menu_items_for(menu, eighth=True))
    assert keys['ClassicMainBackdrop'] == '1' and 'ClassicMainBackdrop' in FI.PORT_OWNED['Game']


def scene_fixture():
    node = [(2, 's'), (3, 'r'), (5, 'i')]
    group = node + [(7, 'r')]
    list_fields = [(2, 'i'), (3, 'i'), (4, 'b')]
    specs = [('igObject', None, []), ('igNamedObject', 'igObject', [(2, 's')]),
             ('igNode', 'igNamedObject', node), ('igGroup', 'igNode', group),
             ('igTransform', 'igGroup', group + [(8, 'm')]),
             ('igAttrSet', 'igGroup', group + [(8, 'r')]), ('igGeometry', 'igAttrSet', group + [(8, 'r')]),
             ('igAABox', 'igObject', [(2, 'v'), (3, 'v')]),
             ('igCamera', 'igNode', node + [(8, 'f'), (9, 'f'), (10, 'f')]),
             ('igDataList', 'igObject', list_fields), ('igNodeList', 'igDataList', list_fields),
             ('igAttrList', 'igDataList', list_fields), ('igLightList', 'igDataList', list_fields),
             ('igGeometryAttr', 'igObject', [(4, 'r')]),
             ('igVertexArray', 'igObject', [(2, 'b'), (3, 'i'), (6, 'i')]),
             ('igLightSet', 'igNode', group), ('igLightAttr', 'igObject', [(6, 'v')]),
             ('igSceneInfo', 'igObject', [(5, 'r')])]
    def transform(name, children, position):
        matrix = [float(i in (0, 5, 10, 15)) for i in range(16)]
        matrix[12:15] = position
        return {2: name, 3: -1, 5: 2, 7: children, 8: matrix}
    objects = [('igSceneInfo', {5: 1}), ('igGroup', {2: 'rootA', 3: -1, 5: 2, 7: 2}),
               ('igNodeList', {2: 4, 3: 4, 4: 15}),
               ('igTransform', transform('cameraA', 4, F.MENU_CAMERA_POS)),
               ('igNodeList', {2: 1, 3: 1, 4: 16}),
               ('igCamera', {2: 'viewA', 3: -1, 5: 2, 8: 30, 9: 100, 10: 1100}),
               ('igTransform', transform('optionA', -1, (100, 0, 60))),
               ('igGeometry', {2: 'emblemA', 3: 8, 5: 2, 7: -1, 8: 9}),
               ('igAABox', {2: (20, 0, 80), 3: (40, 2, 100)}),
               ('igAttrList', {2: 1, 3: 1, 4: 17}), ('igGeometryAttr', {4: 11}),
               ('igVertexArray', {2: 18, 3: 2, 6: 1}),
               ('igLightSet', {2: 'lampA', 3: -1, 5: 2, 7: 13}),
               ('igLightList', {2: 1, 3: 1, 4: 20}), ('igLightAttr', {6: (100, 30, 200)})]
    blocks = (u32(3, 6, 7, 12), u32(5), u32(10), u32(19),
              struct.pack('<6f', 20, 0, 80, 40, 2, 100), u32(14))
    return fixture(specs, objects, blocks)


def test_widescreen_moves_composition_and_bounds_without_scaling_or_camera_changes():
    data = scene_fixture(); original = IgbFile(data)
    moved, report = MA.widescreen_scene(data)
    out = IgbFile(moved)
    assert len(data) == len(moved) and report['vertices'] == 2
    assert out.obj(3).get(8) == original.obj(3).get(8) # camera unchanged
    before, after = original.obj(6).get(8), out.obj(6).get(8)
    assert before[:12] == after[:12] and after[12] - before[12] == MA.WIDE_X
    assert after[13:] == before[13:]
    for slot in (2, 3):
        assert out.obj(8).get(slot)[0] - original.obj(8).get(slot)[0] == MA.WIDE_X
        assert out.obj(8).get(slot)[1:] == original.obj(8).get(slot)[1:]
    a, b = original.block_floats(19), out.block_floats(19)
    assert [b[i] - a[i] for i in (0, 3)] == [MA.WIDE_X, MA.WIDE_X]
    assert b[3] - b[0] == a[3] - a[0]
    assert out.obj(14).get(6) == [148, 30, 200]
    assert original.edited() == data


def test_widescreen_refuses_noncanonical_camera_and_truncated_graph():
    data = scene_fixture(); g = IgbFile(data); g.set_floats(g.obj(3), 8, [0], 12)
    raises(IgbError, lambda: MA.widescreen_scene(g.edited()))
    raises(IgbError, lambda: MA.widescreen_scene(data[:-4]))
