"""Fill unused native mini-portrait cells from the player's original HUD heads.

The native 8x8 grid and locked cell 63 stay intact. These five cells are not
used by the converted roster or retained NPCs; refuse a future NPC collision.
"""
from __future__ import annotations

import struct

import numpy as np
from PIL import Image

from . import igb_file as G, main_fonts as MF

ATLAS = 'Textures/ui/mini_convo_icons.IGB'
CELLS = {'beast': 48, 'frost': 49, 'jubilee': 50, 'magma': 51, 'psylocke': 52}
HEADS = {'beast': '0501', 'frost': '1501', 'jubilee': '1601', 'magma': '1801', 'psylocke': '1201'}


def check_cells(npc):
    for entry in npc.iter('stats'):
        if entry.get('textureicon') in {str(cell) for cell in CELLS.values()}:
            raise G.IgbError('reserved roster portrait cell is used by an NPC: ' + entry.get('name', ''))


def regenerate(template, heads):
    if set(heads) != set(CELLS):
        raise G.IgbError('roster portraits require all five original HUD heads')
    graph = G.IgbFile(template)
    images = graph.objects_of('igImage')
    if not images or max((image.get(2), image.get(3)) for image in images) != (256, 256):
        raise G.IgbError('roster portraits require the native 256px mini-portrait atlas')
    rgba = MF._image(graph).copy()
    for hero, cell in CELLS.items():
        head = MF._image(G.IgbFile(heads[hero]))
        if head.shape != (128, 128, 4):
            raise G.IgbError('roster portrait requires a 128px original HUD head: ' + hero)
        # Both resources store pixels bottom-up. Resize without a vertical flip.
        thumb = np.asarray(Image.fromarray(head).resize((32, 32), Image.Resampling.LANCZOS))
        y, x = (7 - cell // 8) * 32, (cell % 8) * 32
        rgba[y:y+32, x:x+32] = thumb
    blocks = {}
    for image in images:
        width, height = image.get(2), image.get(3)
        if (not isinstance(width, int) or width != height or width not in (1, 2, 4, 8, 16, 32, 64, 128, 256)
                or image.get(13) in blocks or graph.block(image.get(13)) is None):
            raise G.IgbError('unsupported mini-portrait mip chain')
        pixels = rgba if width == 256 else np.asarray(Image.fromarray(rgba).resize(
            (width, height), Image.Resampling.LANCZOS))
        # Native RGBA8 avoids recompressing untouched PC portraits. Existing
        # image/texture references, dimensions and complete mip chain survive.
        blob = pixels.tobytes()
        for slot, value in {6:100, 7:8, 8:8, 9:8, 10:8, 11:7, 12:len(blob), 19:width*4, 20:0}.items():
            field = image.fields.get(slot)
            if field is None:
                if slot in (6, 7, 8, 9, 10, 20):
                    continue
                raise G.IgbError('unsupported mini-portrait image field')
            if field.size != 4:
                raise G.IgbError('unsupported mini-portrait image field')
            struct.pack_into('<i', graph.buf, field.offset, value)
        blocks[image.get(13)] = blob
    return graph.rebuilt(blocks)


def expected(ctx):
    native = ctx.base_index.path(ATLAS)
    if native is None:
        raise G.IgbError('native mini-portrait atlas missing')
    heads = {}
    for hero, skin in HEADS.items():
        source = ctx.x1_path('hud/hud_head_' + skin + '.igb')
        if source is None:
            raise G.IgbError('original roster HUD head missing: ' + hero)
        heads[hero] = source.read_bytes()
    return regenerate(native.read_bytes(), heads)


def validate(ctx, npc):
    check_cells(npc)
    actual = ctx.out_index.path(ATLAS)
    if actual is None or actual.read_bytes() != expected(ctx):
        raise G.IgbError('roster mini-portrait atlas differs from original-head conversion')


def write(ctx, npc):
    check_cells(npc)
    data = expected(ctx)
    ctx.write_bytes(ATLAS, data, source='heroes:original HUD heads in unused native roster portrait cells', replace=True)
    return {'cells': CELLS, 'heads': HEADS, 'bytes': len(data)}
