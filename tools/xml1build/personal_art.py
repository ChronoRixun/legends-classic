"""xml1build.personal_art - re-frame the first game's bedroom-item pictures for XMen2.exe's menu image
sprite (SPEC 56, issue #47).

XMen2.exe draws the ITEM's texture as the menu's background sprite stretched over the whole 512x384 virtual
screen (the menu's rect getter feeds the manager a fixed 512x384, XMen2.exe 0x5b7c60; default.xbe adds the
same sprite at the 256x128 rect its init sets: x 128..384, z 202..330, bottom-up). The first game's 512x256
painted art therefore fills the screen in the port ("too big") and covers the item's text area, where the
first game drew the picture small over the desk backdrop. Re-composing every texture to 512x384 with the art
inside the first game's sprite window makes the engine's fullscreen draw reproduce the first game's layout:
the picture in its window, its wall / desk colours (a soft stretch of the art) continuing to the screen
edges. Everything works in the IGB's own row order (the engine's v-flip is unchanged), so window row 202..330
shows at screen z 202..330.

Pure Python (the builder adds no imaging dependency); pixels are flat row-major lists of (r, g, b).
"""
from __future__ import annotations

import struct

from . import igb_file as G

SCREEN = (512, 384)                      # the virtual screen the sprite is stretched over
WINDOW = (128, 202, 384, 330)            # the art's window in texture rows (shows at XML1's sprite rect)
BACKDROP_SMALL = (64, 32)                # the art shrunk this far before it is stretched back as the backdrop
PFMT_DXT3 = 15                           # igImage pixel format of the personal textures (4x4 blocks of 16 bytes)


# ----------------------------------------------------------------------------------------------------- pixels
def half(px, w, h):
    """(pixels, w, h) at half size, 2x2 box average (w and h even)."""
    out = []
    for y in range(0, h, 2):
        r0, r1 = px[y * w:(y + 1) * w], px[(y + 1) * w:(y + 2) * w]
        for x in range(0, w, 2):
            a, b, c, d = r0[x], r0[x + 1], r1[x], r1[x + 1]
            out.append(tuple((a[i] + b[i] + c[i] + d[i]) // 4 for i in range(3)))
    return out, w // 2, h // 2


def scale(px, w, h, W, H):
    """(pixels, W, H): bilinear resample; (0.5, 0.5)-centred mapping."""
    out = []
    for y in range(H):
        sy = (y + 0.5) * h / H - 0.5
        y0 = min(max(int(sy), 0), h - 1)
        y1 = min(y0 + 1, h - 1)
        fy = min(max(sy - y0, 0.0), 1.0)
        for x in range(W):
            sx = (x + 0.5) * w / W - 0.5
            x0 = min(max(int(sx), 0), w - 1)
            x1 = min(x0 + 1, w - 1)
            fx = min(max(sx - x0, 0.0), 1.0)
            p00, p01, p10, p11 = px[y0 * w + x0], px[y0 * w + x1], px[y1 * w + x0], px[y1 * w + x1]
            out.append(tuple(int(p00[i] * (1 - fx) * (1 - fy) + p01[i] * fx * (1 - fy) +
                                 p10[i] * (1 - fx) * fy + p11[i] * fx * fy + 0.5) for i in range(3)))
    return out


def compose(px, w, h, window=WINDOW):
    """(pixels, SCREEN): the art (w x h) inside `window` over a soft stretch of itself, so the painted
    scene's wall / desk continue to the screen edges like the menu IGB's backdrop did in the first game."""
    W, H = SCREEN
    small, sw, sh = px, w, h
    while sw > BACKDROP_SMALL[0] or sh > BACKDROP_SMALL[1]:
        small, sw, sh = half(small, sw, sh)
    canvas = scale(small, sw, sh, W, H)
    win, ww, wh = px, w, h
    while ww > window[2] - window[0] or wh > window[3] - window[1]:
        win, ww, wh = half(win, ww, wh)
    win = scale(win, ww, wh, window[2] - window[0], window[3] - window[1]) \
        if (ww, wh) != (window[2] - window[0], window[3] - window[1]) else win
    for row in range(window[3] - window[1]):
        y = window[1] + row
        canvas[y * W + window[0]:y * W + window[2]] = win[row * (window[2] - window[0]):(row + 1) * (window[2] - window[0])]
    return canvas


# ----------------------------------------------------------------------------------------------------- DXT3/5
def _c565(p):
    return (p[0] * 31 // 255 << 11) | (p[1] * 63 // 255 << 5) | (p[2] * 31 // 255)


def _rgb(c):
    return ((c >> 11 & 31) * 255 // 31, (c >> 5 & 63) * 255 // 63, (c & 31) * 255 // 31)


def dxt_decode(data, w, h):
    """pixels (row-major) of one DXT3/5 image (16-byte blocks; the 8 alpha bytes first, ignored - every
    personal texture is opaque)."""
    px = []
    nbx = (w + 3) // 4
    for by in range((h + 3) // 4):
        rows = [[] for _ in range(4)]
        for bx in range(nbx):
            blk = data[16 * (by * nbx + bx):16 * (by * nbx + bx) + 16]
            c0, c1, bits = struct.unpack_from('<HHI', blk, 8)
            r0, r1 = _rgb(c0), _rgb(c1)
            pal = [r0, r1, tuple((2 * a + b) // 3 for a, b in zip(r0, r1)),
                   tuple((a + 2 * b) // 3 for a, b in zip(r0, r1))]
            for i in range(16):
                rows[i // 4].append(pal[bits >> (2 * i) & 3])
        for row in rows:
            px += row[:w]
    return px[:w * h]


def dxt_encode(px, w, h):
    """DXT3/5 bytes of pixels (row-major), opaque alpha, two-endpoint fit by luminance."""
    out = bytearray()
    for by in range((h + 3) // 4):
        for bx in range((w + 3) // 4):
            block = [px[min(by * 4 + i // 4, h - 1) * w + min(bx * 4 + i % 4, w - 1)] for i in range(16)]
            lum = [p[0] * 2 + p[1] * 3 + p[2] for p in block]
            c0, c1 = _c565(block[lum.index(max(lum))]), _c565(block[lum.index(min(lum))])
            if c0 == c1:
                c1 = c0 ^ 1
            r0, r1 = _rgb(c0), _rgb(c1)
            pal = [r0, r1, tuple((2 * a + b) // 3 for a, b in zip(r0, r1)),
                   tuple((a + 2 * b) // 3 for a, b in zip(r0, r1))]
            bits = 0
            for i, p in enumerate(block):
                best = min(range(4), key=lambda k: sum((a - b) ** 2 for a, b in zip(p, pal[k])))
                bits |= best << (2 * i)
            out += b'\xff' * 8 + struct.pack('<HHI', c0, c1, bits)
    return bytes(out)


# ----------------------------------------------------------------------------------------------------- the IGB
def recompose_igb(data):
    """(bytes, report): the personal-item texture IGB with its art re-composed to 512x384 (compose), the
    same igImage count (the mip chain continues the halving to 1x1). Raises IgbError on a layout it cannot
    place (the build then keeps the byte copy and reports the texture)."""
    g = G.IgbFile(data)
    images = sorted(g.objects_of('igImage'), key=lambda o: -(o.get(2) * o.get(3)))
    if not images:
        raise G.IgbError('no igImage')
    base = images[0]
    if base.get(11) != PFMT_DXT3:
        raise G.IgbError(f'pixel format {base.get(11)}, not DXT3/5 ({PFMT_DXT3})')
    bw, bh = base.get(2), base.get(3)
    b = g.block(base.get(13))
    if b is None or b[1] != 16 * (bw // 4) * (bh // 4):
        raise G.IgbError(f'base image {bw}x{bh}: pixel block {b and b[1]} bytes')
    art = dxt_decode(g.data[b[0]:b[0] + b[1]], bw, bh)
    canvas = compose(art, bw, bh)
    blocks, rep = {}, []
    px, w, h = canvas, SCREEN[0], SCREEN[1]
    for i, o in enumerate(images):
        if i:
            px, w, h = half(px, w, h) if w % 2 == 0 and h % 2 == 0 else (scale(px, w, h, max(1, w // 2), max(1, h // 2)), max(1, w // 2), max(1, h // 2))
        blob = dxt_encode(px, w, h)
        blocks[o.get(13)] = blob
        for slot, val in ((2, w), (3, h), (12, len(blob)), (19, max(16, w * 4))):
            struct.pack_into('<i', g.buf, o.fields[slot].offset, val)
        rep.append((w, h))
    return g.rebuilt(blocks), {'levels': rep}
