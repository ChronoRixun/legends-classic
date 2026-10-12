"""Synthetic regression fixtures for the bottom-up, 32-pixel talent-icon cells."""
import struct
import numpy as np
from xml1build import hero_icons as HI
from xml1build.igb_file import IgbError, IgbFile

MAGIC, VERSION = 0xFADA, 0xF0000006
INT, OBJ, MEM = 0, 1, 2
FTYPES = (b'igIntMetaField\0', b'igObjectRefMetaField\0', b'igMemoryRefMetaField\0')
ODE, MDE, IMG, ATTR = range(4)
METAS = (
    ('igObjectDirEntry', [(INT, 11, 4)]),
    ('igMemoryDirEntry', [(INT, 7, 4)]),
    ('igImage', [(INT, 2, 4), (INT, 3, 4), (INT, 11, 4), (INT, 12, 4), (MEM, 13, 4), (INT, 19, 4)]),
    ('igTextureAttr', [(OBJ, 12, 4)]),
)

def _u32s(*v):
    return struct.pack(f'<{len(v)}I', *v)

def icon_igb(rgba):
    """One image at ref 0, its texture attr at ref 1, bottom-up DXT5 pixels at ref 2."""
    h, w = rgba.shape[:2]
    blob = HI.encode_dxt5(rgba[::-1].copy())
    recs = _u32s(*[x for n in FTYPES for x in (len(n), 1, 0)]) + b''.join(FTYPES)
    heads, bodies = b'', b''
    for name, fields in METAS:
        nb = name.encode() + b'\0'
        heads += _u32s(len(nb), 1, 0, len(fields), 0xFFFFFFFF, 0)
        bodies += nb + b''.join(struct.pack('<3H', t, s, z) for t, s, z in fields)
    metas = heads + bodies
    directory = _u32s(ODE, 12, IMG) + _u32s(ODE, 12, ATTR) + _u32s(MDE, 12, len(blob))
    index = _u32s(14, 3) + struct.pack('<3H', 0, 1, 2)
    objects = _u32s(IMG, 32, w, h, HI.PFMT_DXT, len(blob), 2, w // 4 * 16) + _u32s(ATTR, 12, 0)
    body = recs + _u32s(4) + metas + _u32s(4) + _u32s(4) + directory + index + _u32s(0) + objects + blob
    return _u32s(len(directory), 3, len(metas), 4, len(objects), 2, len(blob), 1,
                 len(recs), len(FTYPES), MAGIC, VERSION) + body

def quadrants():
    rgba = np.zeros((128, 128, 4), np.uint8)
    colors = [(200, 30, 30), (30, 200, 30), (30, 30, 200), (200, 200, 30)]
    for k, c in enumerate(colors):
        rgba[k // 2 * 64:(k // 2 + 1) * 64, k % 2 * 64:(k % 2 + 1) * 64] = (*c, 255)
    return rgba, colors

def passive_igb():
    rgba = np.zeros((128, 128, 4), np.uint8)
    rgba[32:64, :32] = (40, 170, 240, 255)
    return icon_igb(rgba)

def read_pixels(data):
    f = IgbFile(data)
    img = next(o for o in f.objects if o.name == 'igImage')
    off, size = f.blocks[img.get(13)]
    return f, img, HI.decode_dxt5(f.data[off:off + size], img.get(2), img.get(3))[::-1].copy()

def test_fixture_has_an_image_reference_not_a_blend_field():
    f, img, _ = read_pixels(icon_igb(quadrants()[0]))
    attr = next(o for o in f.objects if o.name == 'igTextureAttr')
    assert attr.fields[12].type == 'igObjectRefMetaField'
    assert f.obj(attr.get(12)) is img

def test_dxt5_bright_interpolants_do_not_overflow():
    # Each block needs all four grey palette entries, including values above 127.
    rgba = np.zeros((4, 4, 4), np.uint8)
    rgba[..., :3] = np.array([120, 160, 200, 240], np.uint8)[None, :, None]
    rgba[..., 3] = 255
    blob = HI.encode_dxt5(rgba)
    # Independently decode its colour palette with Python integers (no numpy uint8 arithmetic).
    c0, c1, bits = struct.unpack_from('<HHI', blob, 8)
    def grey(c):
        return ((c >> 11 & 31) * 255 // 31, (c >> 5 & 63) * 255 // 63, (c & 31) * 255 // 31)
    p0, p1 = grey(c0), grey(c1)
    palette = [p0, p1, tuple((2*a+b)//3 for a,b in zip(p0,p1)), tuple((a+2*b)//3 for a,b in zip(p0,p1))]
    rgb = np.array([palette[bits >> (2*i) & 3] for i in range(16)]).reshape(4, 4, 3)
    assert np.abs(rgb - rgba[..., :3].astype(int)).mean() < 4

def test_relayout_resizes_complete_icons_to_32_pixel_cells():
    rgba, colors = quadrants()
    out = HI.relayout(rgba)
    assert out.shape == (128, 128, 4)
    for k, c in enumerate(colors):
        cell = out[:32, k*32:(k+1)*32]
        assert tuple(cell[16, 16, :3]) == c
        assert cell[16, 16, 3] == 255
        assert cell[0, 0, 3] == cell[-1, -1, 3] == 0
    assert out[32:, :, 3].max() == 0

def test_regenerate_preserves_image_reference_and_bottom_up_storage():
    rgba, colors = quadrants()
    # An off-centre feature distinguishes a vertical flip from a correctly oriented icon.
    rgba[12:24, 26:38, :3] = (245, 245, 245)
    original = icon_igb(rgba)
    out = HI.regenerate(original, passive_igb())
    f, img, back = read_pixels(out)
    assert (img.get(2), img.get(3)) == (128, 128)
    assert img.get(12) == 16384 and img.get(19) == 512
    attr = next(o for o in f.objects if o.name == 'igTextureAttr')
    assert attr.get(12) == 0 and f.obj(attr.get(12)) is img
    assert back[8, 16, :3].min() > 220
    assert back[24, 16, 0] < 215
    for k, c in enumerate(colors):
        assert np.abs(back[16, k*32+16, :3].astype(int) - c).max() < 12
    assert back[64:, :, 3].max() == 0
    assert back[32:64, 32:, 3].max() == 0
    assert HI.is_regenerated(out)
    assert not HI.is_regenerated(original)
    assert len(out) == len(original)

def test_regenerated_check_rejects_a_broken_texture_reference():
    out = HI.regenerate(icon_igb(quadrants()[0]), passive_igb())
    f = IgbFile(out)
    attr = next(o for o in f.objects if o.name == 'igTextureAttr')
    struct.pack_into('<i', f.buf, attr.fields[12].offset, 2)  # points at pixels, not an image
    assert not HI.is_regenerated(f.edited())

def test_relayout_rejects_the_wrong_size():
    try:
        HI.relayout(np.zeros((64, 64, 4), np.uint8))
    except HI.HeroIconError:
        return
    raise AssertionError('wrong-sized source accepted')

def test_regenerate_rejects_garbage():
    for bad in (b'', b'\0'*64, icon_igb(quadrants()[0])[:60], icon_igb(quadrants()[0])[:241]):
        try:
            HI.regenerate(bad, passive_igb())
        except HI.HeroIconError:
            continue
        raise AssertionError('garbage accepted')


def test_regenerate_supplies_round_passive_fallback_cell_4():
    _, _, back = read_pixels(HI.regenerate(icon_igb(quadrants()[0]), passive_igb()))
    assert np.abs(back[48, 16, :3].astype(int) - (40, 170, 240)).max() < 12
    assert back[48, 16, 3] == 255
    assert back[32, 0, 3] == back[63, 31, 3] == 0


def test_regenerated_check_rejects_truncated_metadata():
    assert not HI.is_regenerated(icon_igb(quadrants()[0])[:241])
