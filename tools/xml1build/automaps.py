"""xml1build.automaps - XML1's automap textures as XMen2.exe .zam automaps (SPEC.md section 26).

The two games draw the pause menu's Automap and the HUD's small map from different data
(research/automaps/automaps.md has the full trace):

  XML1 (default.xbe, image base 0x10000; research/scripts/xml1_text.asm)
    The world entity carries automap_texture="<name>" and automap_offset="<u> <v>" (parser 0xbefa0: +0x8c,
    +0xcc / +0xd0). CHudAutoMap loads textures/automap/<name> (0x152690; a name already holding
    "textures/automap" is used as is) and maps a world position to a texture pixel with 0x1528c0:
    (x, y) * 1/12 (0x3dd314) - (u, v) -> column x/12 - u, row y/12 - v: 12 world units per pixel. The 125
    textures (256 / 512 px, igImage pfmt 15 = DXT3/5 whose alpha is opaque everywhere) are grey-scale art:
    black = nothing, grey (80-111) = floors and streets, white (224-255) = outlines, a few dither levels between.

  XML2 (XMen2.exe, image base 0x400000)
    A zone package entry <zam filename="automaps/<zone>"/> (CAutomapPrecacher vtable 0x69b050 slot 0 =
    0x561420: '<name>.zam' -> HUD singleton 0x81d7e0 vt+0x100 -> loader 0x5a02f0). XMen2.exe still reads
    automap_texture / automap_offset into the world entity (0x4c7f90) but nothing uses them. Every frame the
    generator 0x59fa70 (CAutomapGenerator) emits the strips of the zam cells within 8 (small map) or 10
    (overlay / pause-menu automap, 0x5a0150) cells of the player - (2r)^2 cells - as ONE triangle strip
    (CProcGeometryBuilder draw 0x584720, prim 1 -> igGeometryAttr primitive 4 = triangle strip), each vertex
    white * its alpha, through the automap playfield's own vertex builder of 0x2000 vertices (playfield type 5,
    0x584dc3; lock 0x584010 hands the generator capacity - used; the generator drops what does not fit).
    Fog of war: CAutoMap (singleton 0x815e98, vtable 0x69d5cc) keeps 82 x 82 bits of 120-unit cells from the zam
    origin; a vertex in an unexplored cell gets alpha 0 and one next to unexplored ground (+-240) turns dark
    blue (0x77). The bits live in the save's current-zone record (0x4664d0 stores 211 dwords at +0x5278,
    0x465630 restores them) and are reset on every zone change (0x484631 vt+0x28).

  .zam layout (little endian; loader 0x5a02f0):
    s16 version = 9, s16 origin_x, s16 origin_y (in CELL units, 0x69ddf4 = 240.0), s16 vertex count
    vertex count x (s16 x, s16 y, u32 ARGB)          world units; alpha = intensity (XML2: 0xcb lines, 0x32 fill)
    u32 grid[41 * 41], index cell_x * 41 + cell_y     ordinal of the cell's strip list, 0xFFFFFFFF = none
    lists to the end of the file: s16 n, s16 vertex index[n]   a triangle strip per cell (degenerate joins inside;
                                                      the generator joins cells with 2 alpha-0 vertices)

Conversion (build): the texture's luminance is split into grey (>= LUM_GREY) and white (>= LUM_WHITE); the grey
area (grey or white) is smoothed to its 5 x 5 majority (dither and speckle go, shapes wider than ~3 px stay),
white is kept exactly. Per 240-unit zam cell (20 x 20 pixels; offsets are whole pixels, so cells align with
pixel edges) each level's pixels are cut into vertical chains of row runs whose left / right edges become
Douglas-Peucker polylines (TOL_WHITE / TOL_GREY pixels), forced to break at the cell's 120-unit mid row (the fog
cell), and each chain becomes one strip segment: 2 vertices per break row. Grey is drawn first (under the white
outlines, ALPHA_GREY), then white (ALPHA_WHITE). Worst case over every (2 x 10)^2-cell window: 7,646 strip
vertices (asteroid1_2) of the 8,192 the builder holds; XML2's own zams reach 9,934 by the same count.

Pure except for numpy.
"""
from __future__ import annotations

import math
import re
import struct

import numpy as np

# ----------------------------------------------------------------------------------------------- constants
ZAM_VERSION = 9                      # 0x5a02f0: *psVar2 == 9
CELL = 240                           # 0x69ddf4 (float 240.0): zam cell size and the generator's fog-neighbour step
GRID = 41                            # 0x29: grid[41 * 41]; loader loop bound 0x1a44 bytes
GRID_DRAWN = 40                      # 0x59fa70 clamps the window end to 0x28 (exclusive): cell 40 is never drawn
FOG_CELL = 120                       # CAutoMap: 82 x 82 bits (0x52), 1/120 = 0x6e433c
WINDOW_RADIUS = 10                   # 0x5a0150 modes 2/3 (overlay, pause-menu automap); mode 1 (small map) = 8
VB_CAPACITY = 0x2000                 # CAutomapPlayfield (playfield type 5): own CProcGeometryBuilder, 0x584dc3
VB_WARN = 7800                       # validator: warn above this many strip vertices in one window
UNITS_PER_PIXEL = 12                 # default.xbe 0x1528c0: world * 1/12 (0x3dd314)
TEXTURE_DIR = 'textures/automap/'    # default.xbe 0x152690: 'textures/automap/%s' unless the name has it
PFMT_DXT = 15                        # igImage field 11 of all 125 XML1 automap textures: 4x4 blocks of 16 bytes

LUM_GREY = 48                        # >= : grey area (the art's grey is 80-111; 48-79 is dither)
LUM_WHITE = 160                      # >= : white outline (224-255)
SMOOTH_RADIUS = 2                    # grey area = majority of the (2r+1)^2 window
TOL_WHITE = 0.75                     # Douglas-Peucker tolerance, pixels
TOL_GREY = 1.5
MIN_GREY_AREA = 6                    # grey chains smaller than this many pixels are dropped
MAX_STEP = 3                         # a run moving more than this many pixels per row starts a new chain
ALPHA_GREY = 0x50                    # XML1's grey (~90/255) drawn white * alpha
ALPHA_WHITE = 0xcb                   # XML2's own outline alpha
CELL_PX = CELL // UNITS_PER_PIXEL    # 20
MID_PX = FOG_CELL // UNITS_PER_PIXEL  # 10


class AutomapError(ValueError):
    pass


# ----------------------------------------------------------------------------------------------- XML1 side
def texture_rel(name: str) -> str:
    """XML1 rel path (lowercase, '/', '.igb') of an automap_texture value (default.xbe 0x152690)."""
    n = (name or '').strip().replace('\\', '/').lower()
    if n.endswith(('.png', '.igb')):
        n = n[:-4]
    if 'textures/automap' not in n:
        n = TEXTURE_DIR + n.lstrip('/')
    return n + '.igb'


def parse_offset(value):
    """automap_offset -> (u, v) whole pixels ('%f %f', default.xbe 0xbf02e; a third number is ignored).
    Returns ((u, v), note) - note is set when a value was missing, unreadable or not a whole number."""
    if value is None or not str(value).strip():
        return (0, 0), 'no automap_offset (0 0)'
    nums = re.findall(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', str(value))
    if not nums:
        return (0, 0), f'automap_offset {value!r} unreadable (0 0)'
    f = [float(nums[0]), float(nums[1]) if len(nums) > 1 else 0.0]
    r = [int(round(x)) for x in f]
    note = None if all(abs(a - b) < 1e-6 for a, b in zip(f, r)) and len(nums) >= 2 else \
        f'automap_offset {value!r} read as {r[0]} {r[1]}'
    return (r[0], r[1]), note


def decode_texture(data: bytes):
    """Luminance (uint8, rows = v, columns = u) of the igImage of an XML1 automap texture IGB."""
    from .igb_file import IgbFile          # noqa: WPS433 - keeps this module importable without the IGB reader
    f = IgbFile(data)
    imgs = [o for o in f.objects if o.name == 'igImage']
    if len(imgs) != 1:
        raise AutomapError(f'{len(imgs)} igImage objects (one expected)')
    img = imgs[0]
    w, h, fmt = img.get(2), img.get(3), img.get(11)
    ref = img.get(13)
    if ref is None or ref not in f.blocks:
        raise AutomapError('igImage has no pixel block')
    off, size = f.blocks[ref]
    if fmt != PFMT_DXT or not w or not h or w % 4 or h % 4 or size != w * h:
        raise AutomapError(f'igImage {w}x{h} pfmt {fmt}, {size} bytes: not the DXT3/5 layout of XML1 automaps')
    blocks = np.frombuffer(f.data, np.uint8, size, off).reshape(h // 4, w // 4, 16)
    return dxt_luminance(blocks)


def dxt_luminance(blocks):
    """max(R, G, B) of DXT3/DXT5 blocks (colour half only: the XML1 automaps are opaque)."""
    bh, bw = blocks.shape[:2]
    b = blocks.astype(np.uint32)
    c0 = b[..., 8] | (b[..., 9] << 8)
    c1 = b[..., 10] | (b[..., 11] << 8)
    bits = b[..., 12] | (b[..., 13] << 8) | (b[..., 14] << 16) | (b[..., 15] << 24)

    def rgb(c):
        return np.stack([((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31],
                        -1).astype(np.int32)
    p0, p1 = rgb(c0), rgb(c1)
    # 4-colour palette (colour 2 / 3 interpolated per channel; DXT3/5 always use the 4-colour mode), then max(R,G,B)
    pal = np.stack([p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3], 2).max(-1)        # bh, bw, 4
    out = np.zeros((bh, 4, bw, 4), np.uint8)
    for py in range(4):
        for px in range(4):
            k = ((bits >> (2 * (py * 4 + px))) & 3).astype(np.int64)
            out[:, py, :, px] = np.take_along_axis(pal, k[..., None], 2)[..., 0]
    return out.reshape(bh * 4, bw * 4)


# ----------------------------------------------------------------------------------------------- conversion
def _box_mean(m, r):
    k = 2 * r + 1
    p = np.pad(m.astype(np.float32), r)
    s = np.pad(np.cumsum(np.cumsum(p, 0), 1), ((1, 0), (1, 0)))
    h, w = m.shape
    return (s[k:k + h, k:k + w] - s[0:h, k:k + w] - s[k:k + h, 0:w] + s[0:h, 0:w]) / (k * k)


def levels(lum):
    """(grey area, white) boolean masks: grey = 5x5 majority of (lum >= LUM_GREY), white = lum >= LUM_WHITE."""
    white = lum >= LUM_WHITE
    grey = (_box_mean(lum >= LUM_GREY, SMOOTH_RADIUS) >= 0.5) | white
    return grey, white


def _row_runs(mask):
    runs = []
    for row in mask:
        d = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
        runs.append(list(zip(np.nonzero(d == 1)[0].tolist(), np.nonzero(d == -1)[0].tolist())))
    return runs


def _chains(mask):
    """Vertical chains [(row, a, b)]: one run per row, each overlapping the previous one, |edge step| <= MAX_STEP."""
    h = mask.shape[0]
    runs = _row_runs(mask)
    used = [[False] * len(r) for r in runs]
    out = []
    for r in range(h):
        for i, (a, b) in enumerate(runs[r]):
            if used[r][i]:
                continue
            used[r][i] = True
            ch = [(r, a, b)]
            rr = r
            while rr + 1 < h:
                _, pa, pb = ch[-1]
                best, bo = None, 0
                for j, (a2, b2) in enumerate(runs[rr + 1]):
                    ov = min(pb, b2) - max(pa, a2)
                    if used[rr + 1][j] or ov <= 0 or abs(a2 - pa) > MAX_STEP or abs(b2 - pb) > MAX_STEP:
                        continue
                    if ov > bo:
                        best, bo = j, ov
                if best is None:
                    break
                used[rr + 1][best] = True
                ch.append((rr + 1,) + runs[rr + 1][best])
                rr += 1
            out.append(ch)
    return out


def _dp(pts, tol):
    """Douglas-Peucker on [(y, x)] (x deviation); kept indices."""
    n = len(pts)
    if n <= 2:
        return list(range(n))
    keep = {0, n - 1}
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        (y0, x0), (y1, x1) = pts[i], pts[j]
        worst, wk = -1.0, None
        for k in range(i + 1, j):
            y, x = pts[k]
            t = (y - y0) / (y1 - y0) if y1 != y0 else 0.0
            dev = abs(x - (x0 + t * (x1 - x0)))
            if dev > worst:
                worst, wk = dev, k
        if worst > tol:
            keep.add(wk)
            stack += [(i, wk), (wk, j)]
    return sorted(keep)


def _polyline(ch, tol, mid):
    """[(y, x_left, x_right)] break rows (pixel coordinates inside the cell) of one chain."""
    r0, r1 = ch[0][0], ch[-1][0] + 1
    extra = {float(mid)} if mid is not None and r0 < mid < r1 else set()
    if all(c[1] == ch[0][1] and c[2] == ch[0][2] for c in ch):
        return [(y, ch[0][1], ch[0][2]) for y in sorted({float(r0), float(r1)} | extra)]
    left = [(float(r0), ch[0][1])] + [(r + 0.5, a) for r, a, _ in ch] + [(float(r1), ch[-1][1])]
    right = [(float(r0), ch[0][2])] + [(r + 0.5, b) for r, _, b in ch] + [(float(r1), ch[-1][2])]
    kl = [left[k] for k in _dp(left, tol)]
    kr = [right[k] for k in _dp(right, tol)]

    def at(kp, y):
        for (ya, xa), (yb, xb) in zip(kp, kp[1:]):
            if ya <= y <= yb:
                return xa + (xb - xa) * ((y - ya) / (yb - ya) if yb != ya else 0.0)
        return kp[-1][1]
    ys = sorted({p[0] for p in kl} | {p[0] for p in kr} | extra)
    return [(y, at(kl, y), at(kr, y)) for y in ys]


def build(lum, offset):
    """XML1 automap luminance + automap_offset (whole pixels) -> zam dict {origin, verts, lists} or None when the
    texture is empty. verts: [(x, y, argb)]; lists: {(cell_x, cell_y): [vertex index]} (one strip per cell)."""
    grey, white = levels(lum)
    h, w = lum.shape
    ou, ov = offset
    ys, xs = np.nonzero(grey)
    if not len(xs):
        return None
    cx0 = math.floor((int(xs.min()) + ou) / CELL_PX)          # cells are 20 px; pixel u sits at world (u + ou) * 12
    cy0 = math.floor((int(ys.min()) + ov) / CELL_PX)
    cx1 = math.floor((int(xs.max()) + ou) / CELL_PX)
    cy1 = math.floor((int(ys.max()) + ov) / CELL_PX)
    verts, vidx, lists = [], {}, {}

    def vert(x, y, col):
        k = (int(round(x)), int(round(y)), col)
        i = vidx.get(k)
        if i is None:
            i = vidx[k] = len(verts)
            verts.append(k)
        return i
    for gx in range(cx0, cx1 + 1):
        u0 = gx * CELL_PX - ou
        for gy in range(cy0, cy1 + 1):
            v0 = gy * CELL_PX - ov
            su0, sv0 = max(u0, 0), max(v0, 0)
            su1, sv1 = min(u0 + CELL_PX, w), min(v0 + CELL_PX, h)
            if su1 <= su0 or sv1 <= sv0 or not grey[sv0:sv1, su0:su1].any():
                continue
            segs = []
            for mask, tol, alpha, min_area in ((grey, TOL_GREY, ALPHA_GREY, MIN_GREY_AREA),
                                              (white, TOL_WHITE, ALPHA_WHITE, 0)):
                sub = mask[sv0:sv1, su0:su1]
                if not sub.any():
                    continue
                col = (alpha << 24) | 0xffffff
                mid = MID_PX - (sv0 - v0)                  # the 120-unit fog row in sub coordinates
                for ch in _chains(sub):
                    if min_area and sum(b - a for _, a, b in ch) < min_area:
                        continue
                    seg = []
                    for y, xl, xr in _polyline(ch, tol, mid if 0 < mid < sub.shape[0] else None):
                        wy = (sv0 + y + ov) * UNITS_PER_PIXEL
                        seg += [vert((su0 + xl + ou) * UNITS_PER_PIXEL, wy, col),
                                vert((su0 + xr + ou) * UNITS_PER_PIXEL, wy, col)]
                    segs.append(seg)
            idx = []
            for s in segs:
                if idx:
                    idx += [idx[-1], s[0]]                  # degenerate join
                idx += s
            if idx:
                lists[(gx, gy)] = idx
    if not lists:
        return None
    ox = min(c[0] for c in lists)
    oy = min(c[1] for c in lists)
    return {'origin': (ox, oy), 'verts': verts,
            'lists': {(c[0] - ox, c[1] - oy): l for c, l in sorted(lists.items())}}


def pack(z) -> bytes:
    ox, oy = z['origin']
    nv = len(z['verts'])
    if nv > 0x7fff:
        raise AutomapError(f'{nv} vertices (s16 count / indices hold 32767)')
    out = bytearray(struct.pack('<4h', ZAM_VERSION, ox, oy, nv))
    for x, y, col in z['verts']:
        out += struct.pack('<hhI', x, y, col)
    grid = [0xFFFFFFFF] * (GRID * GRID)
    order = sorted(z['lists'])
    for k, (cx, cy) in enumerate(order):
        if not (0 <= cx < GRID_DRAWN and 0 <= cy < GRID_DRAWN):
            raise AutomapError(f'cell {cx},{cy} outside the drawn grid (0..{GRID_DRAWN - 1})')
        grid[cx * GRID + cy] = k
    out += struct.pack(f'<{GRID * GRID}I', *grid)
    for c in order:
        lst = z['lists'][c]
        if len(lst) > 0x7fff:
            raise AutomapError(f'cell {c}: strip of {len(lst)} vertices')
        out += struct.pack(f'<h{len(lst)}h', len(lst), *lst)
    return bytes(out)


def convert(tex_data: bytes, offset_value):
    """(zam bytes or None, info dict) for one XML1 automap texture + its automap_offset value."""
    lum = decode_texture(tex_data)
    off, note = parse_offset(offset_value)
    z = build(lum, off)
    info = {'offset': off, 'offset_note': note, 'size': [int(lum.shape[1]), int(lum.shape[0])]}
    if z is None:
        return None, info
    data = pack(z)
    p = parse(data)
    info.update(verts=len(z['verts']), cells=len(z['lists']), bytes=len(data), window=window_cost(p))
    return data, info


# ----------------------------------------------------------------------------------------------- reading / checks
def parse(data: bytes):
    """A .zam as {origin, verts, grid, lists, cell_of_list}; AutomapError when the loader 0x5a02f0 would refuse it
    or read past the end (every retail XML2 .zam parses, automaps_selftest T1)."""
    if len(data) < 8:
        raise AutomapError(f'{len(data)} bytes: shorter than the header')
    ver, ox, oy, nv = struct.unpack_from('<4h', data, 0)
    if ver != ZAM_VERSION:
        raise AutomapError(f'version {ver} (XMen2.exe loads only {ZAM_VERSION})')
    goff = 8 + 8 * nv
    loff = goff + GRID * GRID * 4
    if nv < 0 or loff > len(data):
        raise AutomapError(f'{nv} vertices + grid need {loff} bytes, file has {len(data)}')
    verts = [struct.unpack_from('<hhI', data, 8 + 8 * i) for i in range(nv)]
    grid = list(struct.unpack_from(f'<{GRID * GRID}I', data, goff))
    lists, o = [], loff
    while o < len(data):
        if o + 2 > len(data):
            raise AutomapError('truncated list header')
        n = struct.unpack_from('<h', data, o)[0]
        if n < 0 or o + 2 + 2 * n > len(data):
            raise AutomapError(f'list {len(lists)}: {n} entries run past the end')
        lists.append(list(struct.unpack_from(f'<{n}h', data, o + 2)))
        o += 2 + 2 * n
    cell_of = {}
    for i, g in enumerate(grid):
        if g != 0xFFFFFFFF:
            cell_of.setdefault(g, []).append((i // GRID, i % GRID))
    return {'origin': (ox, oy), 'verts': verts, 'grid': grid, 'lists': lists, 'cell_of_list': cell_of}


def problems(p, slack=CELL // 2):
    """Format / geometry problems of a parsed zam: grid ordinals without a list, indices out of range, vertices
    far outside the cell that lists them (retail: 0 beyond 120 units), cells the generator never draws."""
    out = []
    nv, nl = len(p['verts']), len(p['lists'])
    ox, oy = p['origin']
    for g, cells in p['cell_of_list'].items():
        if g >= nl:
            out.append(f'grid names list {g}, file has {nl}')
            continue
        bad = [k for k in p['lists'][g] if not 0 <= k < nv]
        if bad:
            out.append(f'list {g}: vertex indices {bad[:3]} out of 0..{nv - 1}')
            continue
        for cx, cy in cells:
            if cx >= GRID_DRAWN or cy >= GRID_DRAWN:
                out.append(f'list {g} at cell {cx},{cy}: the generator never draws cell 40')
            x0, y0 = (ox + cx) * CELL, (oy + cy) * CELL
            far = [p['verts'][k][:2] for k in p['lists'][g]
                   if not (x0 - slack <= p['verts'][k][0] <= x0 + CELL + slack and
                           y0 - slack <= p['verts'][k][1] <= y0 + CELL + slack)]
            if far:
                out.append(f'list {g} at cell {cx},{cy}: {len(far)} vertices outside the cell, e.g. {far[0]}')
    unused = nl - len([g for g in p['cell_of_list'] if g < nl])
    if unused:
        out.append(f'{unused} lists no grid cell names')
    return out


def window_cost(p, radius=WINDOW_RADIUS):
    """Most strip vertices the generator emits for any (2 radius)^2-cell window: sum(len(list) + 2)."""
    a = np.zeros((GRID, GRID), np.int64)
    for g, cells in p['cell_of_list'].items():
        if g < len(p['lists']):
            for cx, cy in cells:
                a[cx, cy] += len(p['lists'][g]) + 2
    s = np.pad(np.cumsum(np.cumsum(a, 0), 1), ((1, 0), (1, 0)))
    best = 0
    for cx in range(GRID):
        for cy in range(GRID):
            x0, x1 = max(cx - radius, 0), min(cx + radius, GRID_DRAWN)
            y0, y1 = max(cy - radius, 0), min(cy + radius, GRID_DRAWN)
            if x1 > x0 and y1 > y0:
                best = max(best, int(s[x1, y1] - s[x0, y1] - s[x1, y0] + s[x0, y0]))
    return best


def rasterize(p, shape, offset, alpha=None):
    """Coverage (bool, texture pixel grid `shape`) of the zam's triangles - all, or those of one alpha - sampled
    at pixel centres. For the selftest's fidelity check; plain numpy, slow but exact."""
    h, w = shape
    ou, ov = offset
    cov = np.zeros((h, w), bool)
    vs = p['verts']
    for lst in p['lists']:
        for i in range(len(lst) - 2):
            t = [vs[lst[i]], vs[lst[i + 1]], vs[lst[i + 2]]]
            if alpha is not None and any((v[2] >> 24) != alpha for v in t):
                continue
            pts = [(v[0] / UNITS_PER_PIXEL - ou, v[1] / UNITS_PER_PIXEL - ov) for v in t]
            area = (pts[1][0] - pts[0][0]) * (pts[2][1] - pts[0][1]) - (pts[2][0] - pts[0][0]) * (pts[1][1] - pts[0][1])
            if abs(area) < 1e-9:
                continue
            u0 = max(int(math.floor(min(q[0] for q in pts))), 0)
            u1 = min(int(math.ceil(max(q[0] for q in pts))), w)
            v0 = max(int(math.floor(min(q[1] for q in pts))), 0)
            v1 = min(int(math.ceil(max(q[1] for q in pts))), h)
            if u1 <= u0 or v1 <= v0:
                continue
            uu, vv = np.meshgrid(np.arange(u0, u1) + 0.5, np.arange(v0, v1) + 0.5)
            inside = np.ones(uu.shape, bool)
            for k in range(3):
                (xa, ya), (xb, yb) = pts[k], pts[(k + 1) % 3]
                e = (xb - xa) * (vv - ya) - (yb - ya) * (uu - xa)
                inside &= (e >= -1e-9) if area > 0 else (e <= 1e-9)
            cov[v0:v1, u0:u1] |= inside
    return cov


# ----------------------------------------------------------------------------------------------- validator V20
def v20(v, ck):
    """V20 automaps (SPEC 26): every converted zone whose XML1 world names an automap_texture has
    Automaps/<zone>.zam and exactly one <zam filename="automaps/<zone>"/> entry (last in its package); every zam
    in <out> parses the way the loader 0x5a02f0 reads it, keeps its vertices in their cells and stays within
    the automap playfield's 0x2000-vertex builder in every draw window; no zone package precaches an XML1
    textures/automap texture (dead in XMen2.exe) and no zone without an XML1 automap gets one."""
    zones = v.converted_zones()
    have = 0
    for z in zones:
        w = v._x1_world(z)
        tex = (w.get('automap_texture') or '').strip() if w is not None else ''
        t = v.tree(f'packages/generated/maps/{z}.pkgb')
        pkg = [(el.tag, el.get('filename') or '') for el in t] if t is not None else []
        zam_entries = [fn for k, fn in pkg if k.lower() == 'zam']
        automap_tex = [fn for k, fn in pkg if k.lower() == 'texture' and
                       (fn or '').lower().replace('\\', '/').startswith(TEXTURE_DIR)]
        for fn in automap_tex:
            ck.error(f'{z}: package precaches XML1 automap texture {fn} (XMen2.exe never reads textures/automap; '
                     f'the automap is Automaps/{z}.zam)')
        want = f'automaps/{z}'
        if not tex:
            if zam_entries:
                ck.error(f'{z}: <zam> {zam_entries} but the XML1 world has no automap_texture (XML1 showed no map)')
            continue
        ck.count('zones_with_xml1_automap')
        if not v.exists(f'{want}.zam'):
            if v.ctx.x1_path(texture_rel(tex)) is None:
                ck.warn(f'{z}: XML1 automap {tex} is not on the disc ({texture_rel(tex)}): no automap')
            else:
                ck.error(f'{z}: XML1 automap {tex} has no Automaps/{z}.zam')
            continue
        if [fn.lower() for fn in zam_entries] != [want]:
            ck.error(f'{z}: package zam entries {zam_entries}, expected exactly [{want!r}]')
        elif pkg and pkg[-1][0].lower() != 'zam':
            ck.warn(f'{z}: <zam> is not the last package entry (XML2 lists it after boy)')
        have += 1
    ck.set('zones_with_zam', have)
    # every zam this build wrote (XML2's own are checked by the selftest)
    worst = (0, None)
    for n, e in sorted(v.reg.items()):
        if not n.startswith('automaps/') or not n.endswith('.zam'):
            continue
        data = v.read(n)
        if data is None:
            ck.error(f'{e["rel"]}: registered but missing')
            continue
        ck.count('zams_checked')
        try:
            p = parse(data)
        except AutomapError as ex:
            ck.error(f'{e["rel"]}: {ex}')
            continue
        for m in problems(p):
            ck.error(f'{e["rel"]}: {m}')
        cost = window_cost(p)
        worst = max(worst, (cost, e['rel']))
        if cost > VB_CAPACITY:
            ck.error(f'{e["rel"]}: {cost} strip vertices in one draw window; the automap builder holds '
                     f'{VB_CAPACITY} (0x584dc3) and the generator drops the rest (cells vanish near the player)')
        elif cost > VB_WARN:
            ck.warn(f'{e["rel"]}: {cost} strip vertices in one draw window (builder {VB_CAPACITY})')
    ck.set('max_window_vertices', worst[0])
    if worst[1]:
        ck.note(f'largest draw window: {worst[0]} strip vertices ({worst[1]}; builder {VB_CAPACITY})')
