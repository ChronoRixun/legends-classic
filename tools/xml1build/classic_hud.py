"""Classic HUD assets, paired with XML2 Fix's opt-in presentation adapter.

The frontend stage writes these for every port. Read artwork from owned inputs only. The PC
sprite atlas stays in its own quadrant; original art and derived bar strips use
explicit, separate UVs. No menu palette, font, or style slots are consumed.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path

import numpy as np

from .igb_file import IgbError, IgbFile
from .main_fonts import decode_font_dxt3

CONTRACT = 'LC-HUD-4'
MARKER = 'lc-hud.txt'
ATLAS_SIZE = (256, 512)


def _integer(g, obj, slot, value):
    f = obj.fields.get(slot)
    if f is None or f.size != 4:
        raise IgbError('unsupported HUD integer field')
    struct.pack_into('<i', g.buf, f.offset, value)


def _rename_images(g, old, new):
    if len(old) != len(new):
        raise IgbError('HUD image aliases must keep their serialized length')
    for image in g.objects_of('igImage'):
        field = image.fields.get(22)
        if field is not None and field.type == 'igStringMetaField':
            name = field.value.replace(old, new).encode('latin-1')
            g.buf[field.offset + 4:field.offset + 4 + len(name)] = name


def _mesh_streams(g, va):
    # Slot 2 is a 20-reference stream table, NOT interleaved vertex data.
    # Positions occupy stream 0; the first UV pair occupies stream 11.
    refs = g.ref_list(va.get(2))
    count = va.get(3)
    if va.get(6) != 65537 or len(refs) != 20 or not isinstance(count,int) or not 1 <= count <= 65536:
        raise IgbError('unsupported HUD vertex stream table')
    if any(ref != -1 for i,ref in enumerate(refs) if i not in (0,11)):
        raise IgbError('unexpected HUD vertex stream')
    for index,stride in ((0,12),(11,8)):
        block = g.block(refs[index])
        if block is None or block[1] != count*stride or not all(math.isfinite(x) for x in g.block_floats(refs[index])):
            raise IgbError('invalid HUD position/UV stream')
    for array in g.objects_of('igIndexArray'):
        block = g.block(array.get(2))
        if block is None or block[1] != array.get(3)*2:
            raise IgbError('invalid HUD index stream length')
        off,size = block
        if any(index >= count for index in struct.unpack_from('<'+'H'*(size//2),g.data,off)):
            raise IgbError('HUD index outside vertex stream')
    return refs[0],refs[11]


def pixels(data):
    g = IgbFile(data)
    images = g.objects_of('igImage')
    if not images:
        raise IgbError('HUD image missing')
    img = max(images, key=lambda o: o.get(2) * o.get(3))
    w, h = img.get(2), img.get(3)
    if (w, h) != (128, 256):
        raise IgbError('HUD input must be 128 by 256')
    block = g.block(img.get(13))
    if block is None:
        raise IgbError('HUD pixels missing')
    off, size = block
    blob = g.data[off:off + size]
    if img.get(11) == 15 and size == w * h:
        rgba = decode_font_dxt3(blob, w, h)
    elif img.get(11) == 7 and size == w * h * 4:
        rgba = np.frombuffer(blob, np.uint8).reshape(h, w, 4)
    else:
        raise IgbError('unsupported HUD pixel encoding or payload length')
    return rgba.copy()


def frame(original, width=114, height=24):
    """A thin bevelled border, with its light colour read from the disc chrome.

    The original executable draws this frame procedurally (105x27, a 103x25
    black inset), rather than using the atlas's small-map corner artwork.
    """
    if original.shape != (256, 128, 4) or original.dtype != np.uint8:
        raise ValueError('HUD source shape/dtype')
    if not (16 <= width <= 256 and 8 <= height <= 256):
        raise ValueError('HUD frame size')
    chrome = original[:48,:16].reshape(-1,4)
    chrome = chrome[chrome[:,3] >= 128]
    if not len(chrome):
        raise IgbError('HUD chrome has no opaque colour sample')
    light = chrome[np.argmax(chrome[:,:3].astype(np.uint16).sum(axis=1)),:3]
    out = np.zeros((height, width, 4), np.uint8)
    y,x = np.mgrid[:height,:width]
    rx,by = width-1-x,height-1-y
    distance = np.minimum.reduce([x,y,rx,by,(x+y-5)/2**.5,(rx+y-5)/2**.5,
                                  (x+by-5)/2**.5,(rx+by-5)/2**.5])
    inside = distance >= 0
    out[inside,3] = 255
    out[inside & (distance < 1),:3] = light
    return out


def inner_mask(width, height):
    """White beveled coverage; the native target routine supplies its pulse colour."""
    y,x = np.mgrid[:height,:width]
    rx,by = width-1-x,height-1-y
    inside = (x+y>=4)&(rx+y>=4)&(x+by>=4)&(rx+by>=4)
    out = np.zeros((height,width,4),np.uint8)
    out[inside] = 255
    return out


def small_map_frame(original):
    """Classic chrome adaptation around the port map; no terrain is imported."""
    out = frame(original, 128, 128)
    # Only the bevel is opaque. The existing vector map and its fog/markers
    # must remain visible through the entire interior.
    out[:, :, 3] *= out[:, :, :3].any(axis=2)
    return out


def atlas(pc, original):
    if any(a.shape != (256, 128, 4) or a.dtype != np.uint8 for a in (pc, original)):
        raise ValueError('HUD atlas source shape/dtype')
    out = np.zeros((512, 256, 4), np.uint8)
    out[:256, :128] = pc
    out[:256, 128:] = original
    # Original vertical health/energy gradients, rotated so zero is at the left.
    out[256:260, :64] = original[:64, 16:20].transpose(1, 0, 2)
    out[264:268, :64] = original[:64, 22:26].transpose(1, 0, 2)
    out[272:296, :224] = frame(original,224,24)
    out[300:312, :48] = frame(original,48,12)
    out[320:342, :222] = inner_mask(222,22)
    out[348:358, :46] = inner_mask(46,10)
    # XBE 0x15b85d draws XP with sprite 8. Its UVs select the silver
    # vertical strip (x=27..30, y=0..64), rotated across the meter.
    # Sample the interior texels, excluding the adjacent blue energy strip.
    out[360:363, :64] = original[:64, 28:31].transpose(1, 0, 2)
    out[384:512, :128] = small_map_frame(original)
    return out


def texture_container(template, rgba):
    """Rebuild every existing image level, retaining image/texture references."""
    g = IgbFile(template)
    _rename_images(g, 'hud', 'lch')
    images = sorted(g.objects_of('igImage'), key=lambda o: -o.get(2) * o.get(3))
    if not images or rgba.dtype != np.uint8 or rgba.shape != (512, 256, 4):
        raise IgbError('unsupported HUD atlas contract')
    refs = [o.get(13) for o in images]
    if len(set(refs)) != len(refs) or any(g.block(ref) is None for ref in refs):
        raise IgbError('HUD image levels need distinct pixel blocks')
    blocks = {}
    level = rgba
    for img in images:
        h, w = level.shape[:2]
        blob = level.tobytes()
        for slot, value in {2:w, 3:h, 6:100, 7:8, 8:8, 9:8, 10:8, 11:7, 12:len(blob), 19:w*4, 20:0}.items():
            _integer(g, img, slot, value)
        blocks[img.get(13)] = blob
        # Existing chain has nine levels; the last 1x2 level is valid.
        level = ((level[::2, ::2].astype(np.uint16) + level[1::2, ::2] +
                  level[::2, 1::2] + level[1::2, 1::2]) // 4).astype(np.uint8) if w > 1 and h > 1 else level
    result = g.rebuilt(blocks)
    IgbFile(result)
    return result


def panel(scene, original):
    """Use the original scene's unlit alpha material with an explicit X/Z quad."""
    g = IgbFile(scene)
    _rename_images(g, 'hud_rgba_ps2', 'lc_hud_panel')
    vertices = g.objects_of('igVertexArray1_1')
    indices = g.objects_of('igIndexArray')
    primitives = g.objects_of('igPrimLengthArray1_1')
    transforms = g.objects_of('igTransform')
    images = g.objects_of('igImage')
    if any(len(items) != 1 for items in (vertices, indices, primitives, transforms, images)):
        raise IgbError('unsupported original HUD scene topology')
    va, ia, pa, tr, im = [items[0] for items in (vertices, indices, primitives, transforms, images)]
    if va.get(6) != 65537 or im.get(11) != 7 or im.get(2) != 128 or im.get(3) != 256:
        raise IgbError('unsupported original HUD vertex/image layout')
    position_ref, uv_ref = _mesh_streams(g, va)
    # Inset the straight frame to meet the native fill (the old frame slanted).
    # The parent adds +10. Native controller-colour quads subtract 5 from that
    # depth (0x5a3700 / 0x5a3751 / 0x5a37a8), so the face must be nearer than +5.
    # Local -6 gives +4: colour remains visible around the face and on its tag.
    mesh = [(8., -6., 13.5, 0., 27/32), (8., -6., -13.5, 0., 0.),
            (113., -6., 13.5, 105/128, 27/32), (113., -6., -13.5, 105/128, 0.)]
    blocks = {position_ref: struct.pack('<12f', *(x for v in mesh for x in v[:3])),
              uv_ref: struct.pack('<8f', *(x for v in mesh for x in v[3:])),
              ia.get(2): struct.pack('<4H', 0, 1, 2, 3), pa.get(2): struct.pack('<I', 4)}
    _integer(g, va, 3, 4)
    _integer(g, ia, 3, 4)
    _integer(g, pa, 3, 1)
    rgba = np.zeros((32, 128, 4), np.uint8)
    rgba[:27, :105] = frame(original, width=105, height=27)
    blocks[im.get(13)] = rgba.tobytes()
    for slot, value in {2:128, 3:32, 12:rgba.nbytes, 19:512}.items():
        _integer(g, im, slot, value)
    g.set_floats(tr, 8, [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1])
    for box in g.objects_of('igAABox'):
        g.set_floats(box, 2, [8, -7, -13.5])
        g.set_floats(box, 3, [113, -5, 13.5])
    result = g.rebuilt(blocks)
    IgbFile(result)
    return result


def portrait_frame(scene, original):
    """Retain the authored original mesh/UVs; bind the separate Xbox pixels."""
    if original.shape != (256,128,4) or original.dtype != np.uint8:
        raise IgbError('unsupported original portrait atlas')
    g = IgbFile(scene)
    images = g.objects_of('igImage')
    if len(images) != 1 or len(g.objects_of('igTransform')) != 1 or len(g.objects_of('igVertexArray1_1')) != 1:
        raise IgbError('unsupported original portrait scene')
    im = images[0]
    _mesh_streams(g, g.objects_of('igVertexArray1_1')[0])
    block = g.block(im.get(13))
    if (im.get(2),im.get(3),im.get(11)) != (128,256,7) or block is None or block[1] != original.nbytes:
        raise IgbError('unsupported original portrait image')
    _rename_images(g, 'hud_rgba_ps2', 'lc_hud_frame')
    off,size = block
    g.buf[off:off+size] = original.tobytes()
    return g.edited()


def party_frame(scene, original):
    """The native party selector needs a centred emblem, not the entire HUD mesh.

    Reuse the disc scene's unlit alpha material and serialize an explicit quad.
    The silver/blue emblem contains no input glyphs; head placement, selection,
    power icons and input prompts remain native.
    """
    g = IgbFile(panel(scene, original))
    _rename_images(g, 'lc_hud_panel', 'lc_partycore')
    va = g.objects_of('igVertexArray1_1')[0]
    position_ref, uv_ref = _mesh_streams(g, va)
    im = g.objects_of('igImage')[0]
    rgba = original[128:192, 64:128].copy()
    # The source tile has opaque black corners: the original clips it with a
    # round mesh. Reproduce that coverage explicitly on our bounded quad.
    y, x = np.mgrid[:64, :64]
    coverage = np.clip(32 - np.hypot(x-31.5, y-31.5), 0, 1)
    rgba[:, :, 3] = np.minimum(rgba[:, :, 3], (coverage*255).astype(np.uint8))
    mesh = [(-25., 0., 25.), (-25., 0., -25.),
            (25., 0., 25.), (25., 0., -25.)]
    blocks = {position_ref: struct.pack('<12f', *(x for v in mesh for x in v)),
              uv_ref: struct.pack('<8f', .5/64,.5/64, .5/64,63.5/64,
                                  63.5/64,.5/64, 63.5/64,63.5/64),
              im.get(13): rgba.tobytes()}
    for slot, value in {2:64, 3:64, 12:rgba.nbytes, 19:256}.items():
        _integer(g, im, slot, value)
    for box in g.objects_of('igAABox'):
        g.set_floats(box, 2, [-25, -1, -25])
        g.set_floats(box, 3, [25, 1, 25])
    result = g.rebuilt(blocks)
    check = IgbFile(result)
    _mesh_streams(check, check.objects_of('igVertexArray1_1')[0])
    return result


def convert(pc, xbox, scene):
    """Validate every input before returning the complete private asset set."""
    original = pixels(xbox)
    assets = {'Textures/ui/lch.IGB': texture_container(pc, atlas(pixels(pc), original)),
              'UI/hud/lc_healthpanel.IGB': panel(scene, original)}
    assets['UI/hud/lc_healthpanel_pc.IGB'] = assets['UI/hud/lc_healthpanel.IGB']
    assets['UI/hud/lc_partycross.IGB'] = party_frame(scene, original)
    assets['UI/hud/lc_partycross_pc.IGB'] = assets['UI/hud/lc_partycross.IGB']
    assets[MARKER] = (CONTRACT+'\n').encode('ascii')
    return assets


def converted(ctx):
    paths = (ctx.base_index.path('Textures/ui/hud.IGB'),
             ctx.x1_path('textures/ui/hud_rgba_xbox.igb'),
             ctx.x1_path('ui/hud/hud_sp_xbox.igb'))
    if any(path is None for path in paths):
        raise IgbError('classic HUD needs the owned PC atlas and Xbox atlas/scene')
    return convert(*(path.read_bytes() for path in paths))


def write(ctx):
    assets = converted(ctx)
    for name, data in assets.items():
        ctx.write_bytes(name, data, source='frontend:classic HUD private atlas and geometry')
    ctx.set_count('classic_hud_files', len(assets))
    ctx.note('classic HUD: private assets registered; requires companion [Game] ClassicHud=xml1')


def validate(v, ck):
    """V-TBD-hud: stale, missing or mismatched conversion must fail the build."""
    from . import fix_ini as FI
    if FI.game_keys().get('ClassicHud') != 'xml1':
        ck.error('classic HUD requires [Game] ClassicHud=xml1')
    for name, expected in converted(v.ctx).items():
        path = v.idx.path(name)
        if path is None or path.read_bytes() != expected:
            ck.error('classic HUD output missing or differs from owned-input conversion: '+name)
        ck.count('classic_hud_files')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--disc', type=Path, required=True, help='extracted owned disc root')
    p.add_argument('--base', type=Path, required=True, help='owned PC installation')
    p.add_argument('--out', type=Path, required=True, help='private built port directory')
    args = p.parse_args()
    out = args.out.resolve()
    if not (out/'XMen2.exe').is_file() or any(out.is_relative_to(source.resolve()) for source in (args.disc,args.base)):
        p.error('--out must be a separate built port')
    xbox = (args.disc/'textures/ui/hud_rgba_xbox.igb').read_bytes()
    pc = (args.base/'Textures/ui/hud.IGB').read_bytes()
    scene = (args.disc/'ui/hud/hud_sp_xbox.igb').read_bytes()
    # Finish validation/conversion before writing any output.
    assets = convert(pc, xbox, scene)
    for name, data in assets.items():
        path = out/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(json.dumps({'contract':CONTRACT, 'assets':{k:len(v) for k,v in assets.items()}}))


if __name__ == '__main__':
    main()
