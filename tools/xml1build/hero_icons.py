"""XML1's talent art adapted to the engine's bottom-up 128px, 4x4 icon sheets.

XML1 supplies four 64px icons in a 2x2 sheet. The HUD and skills screen read 32px
cells: a 256px sheet still renders quarter-crops. Resample the complete source
icons into cells 0..3 of a 128px sheet and bake circular alpha into each cell.
Cell 4 holds the intended generic passive fallback. The IGB's compressed rows
are bottom-up, so flip at the codec boundaries.

igTextureAttr slot 12 is an image OBJECT REFERENCE, not a blend setting. Preserve
it and all other container metadata; the menus already blend texture alpha.
"""
from __future__ import annotations

import struct

import numpy as np

from .igb_file import IgbError, IgbFile

GRID_IN = 2                      # XML1's <hero>_all layout: 2x2 cells
GRID_OUT = 4                     # the grid XMen2.exe reads (engine.md 3.4)
CELL_IN = 64                     # XML1's source cells
CELL_OUT = 32                    # the HUD/skills reader uses 32-pixel cells in a 128-pixel sheet
SIZE_OUT = GRID_OUT * CELL_OUT
PFMT_DXT = 15                    # igImage field 11 of every XML1/XML2 UI icon sheet (automaps.py PFMT_DXT)


class HeroIconError(ValueError):
    pass


# ------------------------------------------------------------------------------------------------------ DXT5
def decode_dxt5(data, w, h):
    """RGBA (h, w, 4) uint8 of a w*h DXT5 block stream (row-major 4x4 blocks, 16 bytes each)."""
    b = np.frombuffer(data, np.uint8).reshape(h // 4, w // 4, 16)
    a0, a1 = b[..., 0].astype(np.int32), b[..., 1].astype(np.int32)
    abits = (b[..., 2].astype(np.uint64) | (b[..., 3].astype(np.uint64) << 8) | (b[..., 4].astype(np.uint64) << 16) |
             (b[..., 5].astype(np.uint64) << 24) | (b[..., 6].astype(np.uint64) << 32) | (b[..., 7].astype(np.uint64) << 40))
    c0 = b[..., 8].astype(np.uint32) | (b[..., 9].astype(np.uint32) << 8)
    c1 = b[..., 10].astype(np.uint32) | (b[..., 11].astype(np.uint32) << 8)
    cbits = (b[..., 12].astype(np.uint32) | (b[..., 13].astype(np.uint32) << 8) |
             (b[..., 14].astype(np.uint32) << 16) | (b[..., 15].astype(np.uint32) << 24))
    r0, g0, bl0 = (c0 >> 11) & 31, (c0 >> 5) & 63, c0 & 31
    r1, g1, bl1 = (c1 >> 11) & 31, (c1 >> 5) & 63, c1 & 31
    out = np.zeros((h, w, 4), np.uint8)
    for py in range(4):
        for px in range(4):
            i = py * 4 + px
            ci = (cbits >> (2 * i)) & 3
            ai = (abits >> (3 * i)) & 7
            r = np.where(ci == 0, r0, np.where(ci == 1, r1, np.where(ci == 2, (2 * r0 + r1) // 3, (r0 + 2 * r1) // 3)))
            g = np.where(ci == 0, g0, np.where(ci == 1, g1, np.where(ci == 2, (2 * g0 + g1) // 3, (g0 + 2 * g1) // 3)))
            bl = np.where(ci == 0, bl0, np.where(ci == 1, bl1, np.where(ci == 2, (2 * bl0 + bl1) // 3, (bl0 + 2 * bl1) // 3)))
            a = np.where(ai <= 1, np.where(ai == 0, a0, a1),
                     np.where(a0 > a1, ((8 - ai) * a0 + (ai - 1) * a1) // 7,
                              np.where(ai < 6, ((6 - ai) * a0 + (ai - 1) * a1) // 5,
                                       np.where(ai == 6, 0, 255))))
            out[py::4, px::4, 0] = (r * 255 // 31).astype(np.uint8)
            out[py::4, px::4, 1] = (g * 255 // 63).astype(np.uint8)
            out[py::4, px::4, 2] = (bl * 255 // 31).astype(np.uint8)
            out[py::4, px::4, 3] = a.astype(np.uint8)
    return out


def _pack565(v):
    """(bh, bw, 3) uint8 RGB -> (bh, bw) uint16 565, the DXT endpoint ordering preserved per block."""
    return (((v[..., 0].astype(np.uint32) * 31 + 127) // 255) << 11) | \
           (((v[..., 1].astype(np.uint32) * 63 + 127) // 255) << 5) | ((v[..., 2].astype(np.uint32) * 31 + 127) // 255)


def _unpack565(c):
    """(bh, bw) uint16 565 -> (bh, bw, 3) uint8 RGB (engine expansion: *255/31, *255/63)."""
    return np.stack([(c >> 11 & 31) * 255 // 31, (c >> 5 & 63) * 255 // 63, (c & 31) * 255 // 31], -1).astype(np.uint8)


def encode_dxt5(rgba):
    """DXT5 block stream of an (h, w, 4) uint8 array (w, h multiples of 4), vectorized over blocks.

    Per 4x4 block: alpha endpoints are the block's min/max with the 8-value index mode; colour endpoints the
    per-channel min/max, ordered as 565, with each texel taking the nearest palette entry.
    DXT5 uses four colours even when its endpoints are equal. Interpolate in int32
    so bright colours cannot overflow uint8 before division."""
    h, w = rgba.shape[:2]
    px = rgba.reshape(h // 4, 4, w // 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(h // 4, w // 4, 16, 4).astype(np.int32)
    bh, bw = px.shape[:2]
    out = np.zeros((bh, bw, 16), np.uint8)
    a = px[..., 3]
    a0, a1 = a.max(-1), a.min(-1)
    pal_a = np.stack([a0, a1] + [((8 - i) * a0 + (i - 1) * a1) // 7 for i in range(2, 8)], -1)   # bh, bw, 8
    aidx = np.where((a0 == a1)[..., None], 0, np.abs(a[..., None] - pal_a[:, :, None, :]).argmin(-1))
    abits = np.zeros((bh, bw), np.uint64)
    for i in range(16):
        abits |= aidx[..., i].astype(np.uint64) << (3 * i)
    out[..., 0] = a0.astype(np.uint8)
    out[..., 1] = a1.astype(np.uint8)
    for j in range(6):
        out[..., 2 + j] = (abits >> (8 * j) & 255).astype(np.uint8)
    cmax = px[..., :3].max(-2)
    cmin = px[..., :3].min(-2)
    e0, e1 = _pack565(cmax), _pack565(cmin)
    swap = e0 < e1                                                                        # DXT5 always has four colours
    e0s, e1s = np.where(swap, e1, e0), np.where(swap, e0, e1)
    p0, p1 = _unpack565(e0s).astype(np.int32), _unpack565(e1s).astype(np.int32)
    pal = np.stack([p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3], -2).astype(np.int32)  # bh, bw, 4, 3
    cidx = ((px[..., None, :3] - pal[:, :, None, :, :]) ** 2).sum(-1).argmin(-1)          # bh, bw, 16
    cbits = np.zeros((bh, bw), np.uint32)
    for i in range(16):
        cbits |= cidx[..., i].astype(np.uint32) << (2 * i)
    out[..., 8] = (e0s & 255).astype(np.uint8)
    out[..., 9] = (e0s >> 8).astype(np.uint8)
    out[..., 10] = (e1s & 255).astype(np.uint8)
    out[..., 11] = (e1s >> 8).astype(np.uint8)
    for j in range(4):
        out[..., 12 + j] = (cbits >> (8 * j) & 255).astype(np.uint8)
    return out.tobytes()


# ------------------------------------------------------------------------------------------------------ rebuild
def _circle_alpha(cell):
    """(cell, cell) uint8 alpha: XML2's icons read as discs inset in their cell; the round mask matches the
    talent_icon_back plate's proportions (opaque blob ~30 of 32 px -> r ~0.44*cell here, 1.5 px linear rim)."""
    y, x = np.mgrid[0:cell, 0:cell]
    d = np.sqrt((y - (cell - 1) / 2) ** 2 + (x - (cell - 1) / 2) ** 2)
    r, rim = cell * 0.44, cell * (1.5 / 64)
    return np.clip((r + rim - d) / (2 * rim) * 255, 0, 255).astype(np.uint8)


def relayout(rgba):
    """the top-down 2x2 source as a 128px 4x4 sheet: cell k is resampled and gains the
    circular alpha; the unused cells 4..15 are transparent."""
    side = GRID_IN * CELL_IN
    if rgba.shape != (side, side, 4):
        raise HeroIconError(f'expected a {side}x{side} atlas, got {rgba.shape[1]}x{rgba.shape[0]}')
    out = np.zeros((SIZE_OUT, SIZE_OUT, 4), np.uint8)
    mask = _circle_alpha(CELL_OUT)
    for k in range(GRID_IN * GRID_IN):
        sy, sx = (k // GRID_IN) * CELL_IN, (k % GRID_IN) * CELL_IN
        dy, dx = (k // GRID_OUT) * CELL_OUT, (k % GRID_OUT) * CELL_OUT
        # Average each 2x2 source square; nearest-neighbour loses thin details at HUD size.
        cell = rgba[sy:sy + CELL_IN, sx:sx + CELL_IN].astype(np.int32)
        cell = cell.reshape(CELL_OUT, 2, CELL_OUT, 2, 4).sum((1, 3)) // 4
        cell = cell.astype(np.uint8)
        cell[..., 3] = (cell[..., 3].astype(np.int32) * mask.astype(np.int32) // 255).astype(np.uint8)
        out[dy:dy + CELL_OUT, dx:dx + CELL_OUT] = cell
    return out


def _image(f):
    imgs = [o for o in f.objects if o.name == 'igImage' and o.decoded]
    if len(imgs) != 1:
        raise HeroIconError(f'{len(imgs)} igImage objects (one expected)')
    img = imgs[0]
    w, h, fmt, ref = img.get(2), img.get(3), img.get(11), img.get(13)
    if (w, h) != (SIZE_OUT, SIZE_OUT) or fmt != PFMT_DXT or ref not in f.blocks:
        raise HeroIconError(f'igImage {w}x{h} pfmt {fmt}: not the 128px DXT5 icon atlas layout')
    off, size = f.blocks[ref]
    if size != w * h or img.get(12) != size or img.get(19) != w // 4 * 16:
        raise HeroIconError('icon pixel block size or row pitch disagrees with its image')
    attrs = [o for o in f.objects if o.name == 'igTextureAttr' and o.decoded]
    if not attrs or any(a.fields.get(12) is None or
                        a.fields[12].type != 'igObjectRefMetaField' or f.obj(a.get(12)) is not img for a in attrs):
        raise HeroIconError('texture attribute does not reference the atlas image')
    return img, off, size


def is_regenerated(data):
    """Check the actual converted layout; dimensions alone cannot distinguish it from XML1's raw sheet."""
    try:
        f = IgbFile(data)
        img, off, size = _image(f)
        rgba = decode_dxt5(f.data[off:off + size], SIZE_OUT, SIZE_OUT)[::-1]
        if rgba[2 * CELL_OUT:, :, 3].any() or rgba[CELL_OUT:2 * CELL_OUT, CELL_OUT:, 3].any():
            return False
        for k in range(5):
            y, x = (k // GRID_OUT) * CELL_OUT, (k % GRID_OUT) * CELL_OUT
            cell = rgba[y:y + CELL_OUT, x:x + CELL_OUT, 3]
            if cell[0, 0] or cell[-1, -1] or cell[CELL_OUT // 2, CELL_OUT // 2] == 0:
                return False
        return True
    except (IgbError, HeroIconError, struct.error):
        return False


def regenerate(data, passive_data):
    """Convert the raw bottom-up sheet without resizing its IGB or changing any object references."""
    try:
        f = IgbFile(data)
        img, off, size = _image(f)
        passive = IgbFile(passive_data)
        _, poff, psize = _image(passive)
    except (IgbError, struct.error) as e:
        raise HeroIconError(f'not an IGB: {e}') from e
    rgba = decode_dxt5(f.data[off:off + size], SIZE_OUT, SIZE_OUT)[::-1].copy()
    out = relayout(rgba)
    # The skill menu uses the hero sheet for generic passive index 4 as well.
    # Include the intended fallback rather than leaving those rows with blank icons.
    cell = decode_dxt5(passive.data[poff:poff + psize], SIZE_OUT, SIZE_OUT)[::-1][CELL_OUT:2 * CELL_OUT, :CELL_OUT].copy()
    cell[..., 3] = (cell[..., 3].astype(np.int32) * _circle_alpha(CELL_OUT) // 255).astype(np.uint8)
    out[CELL_OUT:2 * CELL_OUT, :CELL_OUT] = cell
    blob = encode_dxt5(out[::-1].copy())
    f.buf[off:off + size] = blob
    out = f.edited()
    if not is_regenerated(out):
        raise HeroIconError('converted atlas failed the layout check')
    return out
