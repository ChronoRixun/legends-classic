"""Original English menu typography with the PC's non-printable and extended glyphs.

The engine has four global font indices. Keep its maps and every other language;
append English medium/big overrides with matched imported metrics and atlases.
English menus/dialogs sharing those two indices also use the classic letters.
"""
from __future__ import annotations

import copy
import math
import struct
import xml.etree.ElementTree as ET

import numpy as np

from . import igb_file as G
from .hero_icons import decode_dxt5


def decode_font_dxt3(data, w, h):
    """Font format 15 uses four-bit explicit alpha (DXT3), not interpolated DXT5 alpha."""
    rgba = decode_dxt5(data, w, h)              # the colour halves have the same four-colour layout
    blocks = np.frombuffer(data, np.uint8).reshape(h // 4, w // 4, 16)
    for y in range(4):
        for x in range(4):
            index = 4 * y + x
            rgba[y::4, x::4, 3] = ((blocks[..., index // 2] >> (4 * (index % 2))) & 15) * 17
    return rgba


def _glyphs(root):
    out = {}
    for entry in root:
        num = int(entry.get('num', '-1'))
        if not 0 <= num < 256 or num in out:
            raise ValueError('font has an invalid or duplicate glyph number')
        out[num] = entry
    return out


def combine_metrics(original, pc, original_size, pc_size, canvas_size):
    """Classic printable letters; retain PC controls, extended glyphs and absent letters.

    UVs move to their own part of the combined atlas. Glyph sizes/advances are not
    stretched. The two metric tables must describe the textures supplied with them.
    """
    classic, fallback = _glyphs(original), _glyphs(pc)
    root = ET.Element(original.tag, dict(original.attrib))
    ow, oh = original_size
    pw, ph = pc_size
    cw, ch = canvas_size
    if min(ow, oh, pw, ph) < 1 or ow + pw > cw or max(oh, ph) > ch:
        raise ValueError('font atlas rectangles do not fit')
    kept = []
    for num, entry in sorted(fallback.items()):
        candidate = classic.get(num)
        use_classic = (32 <= num <= 126 and candidate is not None and
                       int(candidate.get('horizadvance', '0')) > 0)
        glyph = copy.deepcopy(candidate if use_classic else entry)
        w, h, x = (ow, oh, 0) if use_classic else (pw, ph, ow)
        if not use_classic:
            kept.append(num)
        for key, extent, total, offset in (('s', w, cw, x), ('s2', w, cw, x),
                                           ('t', h, ch, 0), ('t2', h, ch, 0)):
            value = float(glyph.get(key, 'nan'))
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('font glyph has an invalid texture coordinate')
            glyph.set(key, format((value * extent + offset) / total, '.10g'))
        root.append(glyph)
    return root, kept


def _image(g):
    images = g.objects_of('igImage')
    if not images or any(not image.decoded for image in images):
        raise G.IgbError('font atlas lacks readable images')
    image = max(images, key=lambda o: o.get(2) * o.get(3))
    w, h = image.get(2), image.get(3)
    if not 4 <= w <= 1024 or not 4 <= h <= 1024 or w & (w - 1) or h & (h - 1):
        raise G.IgbError('unsupported font atlas dimensions')
    block = g.block(image.get(13))
    if block is None:
        raise G.IgbError('font atlas lacks pixels')
    off, size = block
    blob = g.data[off:off + size]
    if image.get(11) == 15 and size == w * h:
        rgba = decode_font_dxt3(blob, w, h)
    elif image.get(11) == 7 and size == w * h * 4:
        rgba = np.frombuffer(blob, np.uint8).reshape(h, w, 4).copy()
    else:
        raise G.IgbError('unsupported font pixel format or byte count')
    return rgba


def combined_atlas(original_data, pc_data):
    """Pack both atlases without resizing their base pixels; rebuild the existing mip chain.

    Use the native uncompressed four-channel format to preserve the supplied glyph
    pixels without a lossy recompression. Refuse shared or unsupported image blocks.
    """
    original, pc = G.IgbFile(original_data), G.IgbFile(pc_data)
    first, second = _image(original), _image(pc)
    oh, ow = first.shape[:2]
    ph, pw = second.shape[:2]
    w = 1 << (ow + pw - 1).bit_length()
    h = 1 << (max(oh, ph) - 1).bit_length()
    if w > 2048 or h > 1024:
        raise G.IgbError('combined font atlas exceeds its bounded dimensions')
    canvas = np.zeros((h, w, 4), np.uint8)
    canvas[:oh, :ow] = first
    canvas[:ph, ow:ow + pw] = second
    images = sorted(original.objects_of('igImage'), key=lambda o: -(o.get(2) * o.get(3)))
    refs = [image.get(13) for image in images]
    if len(refs) != len(set(refs)):
        raise G.IgbError('font mip levels share pixel blocks')
    blocks, levels = {}, []
    pixels = canvas
    for level, image in enumerate(images):
        if level:
            # Dimensions remain powers of two; a one-pixel axis stays one pixel.
            hh, ww = pixels.shape[:2]
            if hh > 1:
                pixels = ((pixels[0::2].astype(np.uint16) + pixels[1::2]) // 2).astype(np.uint8)
            if ww > 1:
                pixels = ((pixels[:, 0::2].astype(np.uint16) + pixels[:, 1::2]) // 2).astype(np.uint8)
        hh, ww = pixels.shape[:2]
        blob = pixels.tobytes()
        blocks[image.get(13)] = blob
        fields = {2: ww, 3: hh, 11: 7, 12: len(blob), 19: ww * 4}
        fields.update({slot: value for slot, value in ((6, 100), (7, 8), (8, 8), (9, 8), (10, 8), (20, 0))
                       if slot in image.fields})
        for slot, value in fields.items():
            field = image.fields.get(slot)
            if field is None or field.size != 4:
                raise G.IgbError('unsupported font image field layout')
            struct.pack_into('<i', original.buf, field.offset, value)
        levels.append((ww, hh))
    data = original.rebuilt(blocks)
    check = G.IgbFile(data)
    if not np.array_equal(_image(check), canvas):
        raise G.IgbError('combined font pixels did not round-trip')
    return data, {'original_size': (ow, oh), 'pc_size': (pw, ph),
                  'canvas_size': (w, h), 'levels': levels}


def write_fonts(ctx):
    """Only English overrides in the active PC/HD maps; HUD/digital and PC aliases stay intact."""
    details = []
    for map_name, suffix in (('fonts_pc', ''), ('fonts_hd', '_hd')):
        root = ctx.read_base_xmlb(f'UI/fonts/{map_name}.XMLB')
        for index, source_name in (('medium', 'font_xmen_med'), ('big', 'font_xmen_big')):
            # Select the PC English entry while retaining the full original map.
            entries = [entry for entry in root if entry.get('index') == index and
                       ('eng' in (entry.get('language') or 'eng').split(','))]
            if len(entries) != 1:
                raise ValueError('font map needs one PC English entry for each classic override')
            entry = entries[0]
            name = f'lc_main_{index}{suffix}'
            original_name = source_name + suffix
            metrics = ctx.read_x1_xml(f'ui/fonts/{original_name}.xml')
            texture = ctx.x1_path(f'textures/fonts/{original_name}.igb')
            if metrics is None or texture is None:
                raise ValueError('original menu font pair is missing')
            pc_metrics = ctx.read_base_xmlb(f'UI/fonts/{entry.get("data")}.XMLB')
            pc_texture = ctx.base_index.path(f'Textures/fonts/{entry.get("texture")}.IGB')
            if pc_texture is None:
                raise ValueError('PC fallback font texture is missing')
            data, report = combined_atlas(texture.read_bytes(), pc_texture.read_bytes())
            table, kept = combine_metrics(metrics, pc_metrics, report['original_size'],
                                           report['pc_size'], report['canvas_size'])
            if len(table) != 256:
                raise ValueError('PC fallback font must retain all 256 glyph slots')
            ctx.write_bytes(f'Textures/fonts/{name}.IGB', data, source='frontend:classic letters and PC glyph atlas')
            ctx.write_xmlb(f'UI/fonts/{name}', table, source='frontend:metrics paired with combined font atlas')
            ET.SubElement(root, 'font', {'index': index, 'language': 'eng', 'data': name, 'texture': name})
            details.append({'map': map_name, 'index': index, 'name': name,
                            'pc_glyphs': kept, **report})
        ctx.write_xmlb(f'UI/fonts/{map_name}', root, source='frontend:English classic font overrides')
    return details
