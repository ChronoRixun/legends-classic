"""Rasterize flat disc-authored frame meshes for the PC's separate sprite UI.

This is deterministic asset conversion, not a new drawing of the game's art.
Positions, UVs, strip topology and texture pixels all come from the input IGB.
"""
from __future__ import annotations

import io
import struct

import numpy as np
from PIL import Image

from . import igb_file as G, menu_conversion as M, main_fonts as MF


def texture(g, ref):
    image = g.obj(ref)
    if image is None or image.name != 'igImage':
        raise G.IgbError('sprite frame texture is missing')
    w, h = image.get(2), image.get(3)
    if not all(isinstance(n, int) and 4 <= n <= 2048 and not n & (n - 1) for n in (w, h)):
        raise G.IgbError('unsupported sprite frame texture dimensions')
    block = g.block(image.get(13))
    if block is None:
        raise G.IgbError('sprite frame texture pixels are missing')
    offset, size = block
    raw = g.data[offset:offset+size]
    if image.get(11) == 15 and size == w*h:
        return MF.decode_font_dxt3(raw, w, h)
    if image.get(11) == 7 and size == 4*w*h:
        return np.frombuffer(raw, np.uint8).reshape(h, w, 4).copy()
    raise G.IgbError('unsupported sprite frame pixel format')


def sample(pixels, uv, repeat=False):
    if not np.isfinite(uv).all():
        raise G.IgbError('sprite frame has nonfinite UV coordinates')
    h, w = pixels.shape[:2]
    xy = np.mod(uv, 1) if repeat else np.clip(uv, 0, 1)
    x = np.minimum((xy[..., 0]*w).astype(np.int64), w-1)
    y = np.minimum((xy[..., 1]*h).astype(np.int64), h-1)
    return pixels[y, x].astype(np.float32)/255


def triangle(canvas, positions, uv, pixels, repeat=False):
    """Top-down pixel centres, barycentric UVs and straight-alpha source-over."""
    h, w = canvas.shape[:2]
    points = np.asarray(positions, np.float64)[:, [0, 2]]
    points[:, 1] = h - points[:, 1]
    low = np.maximum(np.floor(points.min(axis=0)).astype(int), 0)
    high = np.minimum(np.ceil(points.max(axis=0)).astype(int), (w, h))
    if np.any(low >= high):
        return
    a,b,c = points
    denominator = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
    if abs(denominator) < 1e-8:
        return
    yy,xx = np.mgrid[low[1]:high[1],low[0]:high[0]]
    xx,yy = xx+.5,yy+.5
    wa = ((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/denominator
    wb = ((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/denominator
    wc = 1-wa-wb
    mask = (wa >= -1e-8) & (wb >= -1e-8) & (wc >= -1e-8)
    if not np.any(mask):
        return
    coords = wa[...,None]*uv[0]+wb[...,None]*uv[1]+wc[...,None]*uv[2]
    src = sample(pixels, coords[mask], repeat)
    region = canvas[low[1]:high[1],low[0]:high[0]]
    dst = region[mask]
    alpha = src[:,3:4]+dst[:,3:4]*(1-src[:,3:4])
    rgb = (src[:,:3]*src[:,3:4]+dst[:,:3]*dst[:,3:4]*(1-src[:,3:4]))/np.maximum(alpha,1e-8)
    region[mask] = np.concatenate((rgb,alpha),axis=1)


def frame(data, width, height):
    if not all(isinstance(n,int) and 16 <= n <= 2048 for n in (width,height)):
        raise G.IgbError('unsupported sprite frame size')
    g = G.IgbFile(data)
    vertices = [g.block_floats(g.ref_list(o.get(2))[0]) for o in g.objects_of('igVertexArray1_1')]
    xyz = [v for row in vertices for v in zip(row[0::3],row[1::3],row[2::3])]
    if not xyz:
        raise G.IgbError('sprite frame has no geometry')
    if any(not np.isfinite(p).all() for p in xyz):
        raise G.IgbError('sprite frame has nonfinite positions')
    span = min(max(p[k] for p in xyz)-min(p[k] for p in xyz) for k in (0,2))
    border = min(12, (span-1)/3, (min(width,height)-1)/3)
    data,_ = M.fit_flat_panel(data,(0,0,width,height),border=border,opaque=True)
    g = G.IgbFile(data)
    canvas = np.zeros((height,width,4),np.float32)
    textures, visited, draws = {},set(),0

    def walk(ref, image_ref=None, depth=0):
        nonlocal draws
        if depth > 64 or ref in visited:
            raise G.IgbError('cyclic or excessive sprite frame graph')
        visited.add(ref)
        node = g.obj(ref)
        if node is None:
            raise G.IgbError('sprite frame has a missing node')
        attrs = g.list_items(node.get(8)) or []
        geometries = []
        for index in attrs:
            attr = g.obj(index)
            if attr.name == 'igTextureBindAttr':
                tex = g.obj(attr.get(4))
                if tex is None or tex.name != 'igTextureAttr':
                    raise G.IgbError('sprite frame has an unsupported texture binding')
                image_ref = tex.get(12)
            elif attr.name == 'igGeometryAttr1_5':
                geometries.append(attr)
        for geometry in geometries:
            if image_ref is None or geometry.get(6) != 4:
                raise G.IgbError('sprite frame needs textured triangle strips')
            array,index_array = g.obj(geometry.get(4)),g.obj(geometry.get(5))
            components = g.ref_list(array.get(2))
            positions = np.asarray(g.block_floats(components[0]),np.float64).reshape(-1,3)
            uv = np.asarray(g.block_floats(components[11]),np.float64).reshape(-1,2)
            block = g.block(index_array.get(2))
            if block is None or block[1] != 2*index_array.get(3) or len(positions) != len(uv):
                raise G.IgbError('sprite frame has invalid indices or UVs')
            indices = struct.unpack_from('<'+'H'*index_array.get(3),g.data,block[0])
            if any(i >= len(positions) for i in indices):
                raise G.IgbError('sprite frame index outside vertex array')
            if image_ref not in textures:
                textures[image_ref] = texture(g,image_ref)
            repeat = bool(np.any((uv < 0)|(uv > 1)))
            for i in range(2,len(indices)):
                chosen = list(indices[i-2:i+1])
                triangle(canvas,positions[chosen],uv[chosen],textures[image_ref],repeat)
            draws += 1
        for child in g.list_items(node.get(7)) or []:
            walk(child,image_ref,depth+1)
        visited.remove(ref)
    infos = g.objects_of('igSceneInfo')
    if len(infos) != 1:
        raise G.IgbError('sprite frame needs one scene')
    walk(infos[0].get(5))
    if draws == 0:
        raise G.IgbError('sprite frame drew no geometry')
    return Image.fromarray(np.clip(np.rint(canvas*255),0,255).astype(np.uint8))


def png_bytes(picture):
    buffer = io.BytesIO()
    picture.save(buffer,format='PNG',optimize=False)
    return buffer.getvalue()
