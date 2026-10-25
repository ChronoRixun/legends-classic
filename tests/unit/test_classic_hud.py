"""Synthetic HUD data checks: alpha codec, UV quadrants and mesh bounds."""
import struct
import tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from xml1build import classic_hud as H
from xml1build.igb_file import IgbFile, IgbError
from test_main_appearance import fixture, raises


def test_final_setting_migrates_pilot_and_rejects_pilot_only_dll():
    from xml1build import fix_ini as FI
    keys = {'Game': {'ClassicHud': 'xml1'}}
    assert FI.game_keys()['ClassicHud'] == 'xml1'
    assert 'ClassicHud' not in FI.game_keys(xml1_opening=False)
    with tempfile.TemporaryDirectory() as tmp:
        dll = Path(tmp)/'dinput.dll'
        dll.write_bytes('ClassicHudPilot\0'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[Game] ClassicHud']
        dll.write_bytes('ClassicHud\0'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == []
        ini = Path(tmp)/'xml2-fix.ini'
        ini.write_text('[Game]\nClassicHudPilot=1\nUserPreference=keep\n')
        FI.write_port_keys(tmp, keys)
        result = ini.read_text()
        assert 'ClassicHudPilot' not in result and 'ClassicHud=xml1' in result
        assert 'UserPreference=keep' in result


def test_pipeline_registers_assets_and_validator_detects_corruption():
    from types import SimpleNamespace
    assets = {'Textures/ui/test.IGB': b'synthetic', H.MARKER: (H.CONTRACT+'\n').encode()}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        registered = {}
        def write(name, data, **kwargs):
            dest = root/name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            registered[name] = kwargs['source']
        ctx = SimpleNamespace(write_bytes=write, set_count=lambda *a: None, note=lambda *a: None)
        errors = []
        ck = SimpleNamespace(error=errors.append, count=lambda *a: None)
        idx = SimpleNamespace(path=lambda name: root/name if (root/name).exists() else None)
        with patch.object(H, 'converted', return_value=assets):
            H.write(ctx)
            assert set(registered) == set(assets)
            H.validate(SimpleNamespace(ctx=ctx, idx=idx), ck)
            assert errors == []
            (root/H.MARKER).write_bytes(b'old contract')
            H.validate(SimpleNamespace(ctx=ctx, idx=idx), ck)
            assert len(errors) == 1 and H.MARKER in errors[0]


def image_schema():
    return ('igImage', None, [(i, 'b' if i == 13 else 's' if i == 22 else 'i')
                             for i in (2,3,6,7,8,9,10,11,12,13,19,20,22)])


def image_values(ref, width=128, height=256, fmt=7):
    return {2:width,3:height,6:100,7:8,8:8,9:8,10:8,11:fmt,
            12:width*height*(4 if fmt==7 else 1),13:ref,19:width*4,20:0,22:'synthetic.png'}


def test_explicit_alpha_and_row_orientation_are_not_hero_icon_dxt5():
    block=bytes.fromhex('1032547698badcfe')+struct.pack('<HHI',0xffff,0,0)
    source=fixture([image_schema()],[('igImage',image_values(1,fmt=15))],(block*(128*256//16),))
    rgba=H.pixels(source)
    assert np.array_equal(rgba[:4,:4,3],np.arange(16,dtype=np.uint8).reshape(4,4)*17)
    assert (rgba[:4,:4,:3]==255).all()
    raises(IgbError,lambda:H.pixels(source[:-16]))


def test_repack_preserves_native_cells_and_original_gradient_direction():
    pc=np.zeros((256,128,4),np.uint8);pc[:]=(12,34,56,255)
    original=pc.copy();original[:64,16:20,0]=np.arange(64,dtype=np.uint8)[:,None]
    original[:64,22:26,1]=np.arange(64,dtype=np.uint8)[:,None]
    original[:64,28:31,2]=np.arange(64,dtype=np.uint8)[:,None]
    out=H.atlas(pc,original)
    assert np.array_equal(out[:256,:128],pc)
    assert np.array_equal(out[:256,128:],original)
    assert np.array_equal(out[256,:,0][:64],np.arange(64))
    assert np.array_equal(out[264,:,1][:64],np.arange(64))
    assert np.array_equal(out[360:363,:64],original[:64,28:31].transpose(1,0,2))
    assert np.array_equal(out[361,:64,2],np.arange(64))
    assert not out[363:].any()  # no small-map frame: everything under the XP strip is transparent
    raises(ValueError,lambda:H.atlas(pc[:128],original))


def test_texture_rebuild_keeps_references_and_dimensions():
    pc=np.full((256,128,4),255,np.uint8)
    source=fixture([image_schema()],[('igImage',image_values(1))],(pc.tobytes(),))
    atlas=H.atlas(pc,pc)
    out=H.texture_container(source,atlas);g=IgbFile(out);im=g.objects_of('igImage')[0]
    assert (im.get(2),im.get(3),im.get(13),im.get(12))==(256,512,1,256*512*4)
    off,size=g.blocks[1]
    assert out[off:off+size]==atlas.tobytes()
    assert out==H.texture_container(source,atlas)


def test_panel_explicit_quad_and_bounds_replace_export_transform():
    schemas=[('igVertexArray1_1',None,[(2,'b'),(3,'i'),(6,'i')]),
             ('igIndexArray',None,[(2,'b'),(3,'i')]),
             ('igPrimLengthArray1_1',None,[(2,'b'),(3,'i')]),
             ('igTransform',None,[(8,'m')]),image_schema(),
             ('igAABox',None,[(2,'v'),(3,'v')])]
    objects=[('igVertexArray1_1',{2:6,3:3,6:65537}),
             ('igIndexArray',{2:7,3:3}),('igPrimLengthArray1_1',{2:8,3:1}),
             ('igTransform',{8:[2.]*16}),('igImage',image_values(9)),
             ('igAABox',{2:[-500.]*3,3:[500.]*3})]
    refs=[-1]*20;refs[0]=10;refs[11]=11
    blocks=(struct.pack('<20i',*refs),bytes(6),struct.pack('<I',3),bytes(128*256*4),bytes(36),bytes(24))
    source=fixture(schemas,objects,blocks)
    rgba=np.full((256,128,4),255,np.uint8)
    portrait=IgbFile(H.portrait_frame(source,rgba))
    assert portrait.obj(3).get(8)==[2.]*16  # original portrait geometry is not flattened
    assert portrait.obj(0).get(3)==3 and portrait.block_floats(10)==[0.]*9
    off,size=portrait.blocks[9]
    assert portrait.data[off:off+size]==rgba.tobytes()
    # A complete HUD scene in the native party-cross slot left an opaque disc.
    # The role-specific quad samples only the owned emblem and keeps head slots.
    rgba[128:192,64:128] = (17,42,91,255)
    party=IgbFile(H.party_frame(source,rgba))
    assert party.obj(0).get(3)==4
    pp,pu=H._mesh_streams(party,party.obj(0))
    assert party.block_floats(pp)[::3]==[-25,-25,25,25]
    assert party.block_floats(pp)[1::3]==[0]*4
    pim=party.objects_of('igImage')[0]
    assert (pim.get(2),pim.get(3))==(64,64)
    po,ps=party.block(pim.get(13))
    tile=np.frombuffer(party.data[po:po+ps],np.uint8).reshape(64,64,4)
    assert tuple(tile[32,32])==(17,42,91,255) and tile[0,0,3]==0
    assert np.array_equal(tile[:,:,:3],rgba[128:192,64:128,:3])
    assert party.block_floats(pu)[1] < party.block_floats(pu)[3]
    assert party.data==H.party_frame(source,rgba)
    out=H.panel(source,rgba);g=IgbFile(out)
    assert g.obj(0).get(3)==4 and g.obj(1).get(3)==4
    assert g.ref_list(6)==refs  # a float position must never become an object reference
    assert g.block_floats(10)[::3]==[8,8,113,113]
    assert len(g.block_floats(11))==8
    assert all(depth+10 < 5 for depth in g.block_floats(10)[1::3])  # native owner colour is at +5
    assert g.obj(5).get(2)==[8,-7,-13.5] and g.obj(5).get(3)==[113,-5,13.5]
    assert g.obj(3).get(8)==[float(i%5==0) for i in range(16)]
    assert out==H.panel(source,rgba)
    objects[0][1][6]=65541
    raises(IgbError,lambda:H.panel(fixture(schemas,objects,blocks),rgba))
    objects[0][1][6]=65537
    bad=list(blocks);bad[0]=struct.pack('<20f',*([12.]*20))
    raises(IgbError,lambda:H.panel(fixture(schemas,objects,bad),rgba))
    bad=list(blocks);bad[1]=struct.pack('<3H',0,1,3)
    raises(IgbError,lambda:H.portrait_frame(fixture(schemas,objects,bad),rgba))


def test_frame_has_thin_outline_black_centre_and_clear_bevel_corners():
    original=np.full((256,128,4),255,np.uint8)
    out=H.frame(original,105,27)
    assert not out[0,0].any() and not out[-1,-1].any()
    assert tuple(out[0,52])==(255,255,255,255)
    assert tuple(out[13,52])==(0,0,0,255)
    original[:48,:16,3]=0
    raises(IgbError,lambda:H.frame(original))


def test_target_inner_masks_keep_native_pulses_inside_the_bevel():
    for width,height in ((224,24),(48,12)):
        source=np.full((256,128,4),255,np.uint8)
        outer=H.frame(source,width,height)
        mask=H.inner_mask(width-2,height-2)
        # A full rectangular black interior would erase the diagonal outline.
        assert not mask[0,0].any() and tuple(mask[height//2-1,width//2-1])==(255,255,255,255)
        assert np.all(mask[:,:,3] <= outer[1:-1,1:-1,3])


def test_atlas_carries_no_small_map_frame():
    original=np.full((256,128,4),255,np.uint8)
    assert not hasattr(H,'small_map_frame')
    assert not H.atlas(original,original)[363:].any()
    raises(ValueError,lambda:H.frame(original,128,257))
