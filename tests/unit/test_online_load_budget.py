"""Regressions driven by the 060s first Party/Post Game loading and Done-edge facts."""
import copy
import struct
import xml.etree.ElementTree as ET
from PIL import Image
from xml1build import online_menus as O, online_party as PT, igb_file as G
from test_main_appearance import fixture


def test_flat_model_images_share_pixels_without_changing_bindings_or_art():
    fields = [(n,'i') for n in (2,3,6,7,8,9,10,11,12,19,20)] + [(13,'b')]
    values = {n:0 for n,_ in fields}
    values.update({2:2,3:2,12:16,19:8})
    source = fixture([('igImage',None,fields),('igTextureAttr',None,[(12,'r')])],
        [('igImage',{**values,13:4}),('igImage',{**values,13:5}),
         ('igTextureAttr',{12:0}),('igTextureAttr',{12:1})], (b'x'*16,b'y'*16))
    graph=G.IgbFile(source);blocks={}
    picture=Image.new('RGBA',(64,32),(12,23,34,45))
    O._focus_images(graph,blocks,picture,b'\xff'*4)
    result=G.IgbFile(graph.rebuilt(blocks))
    images=result.objects_of('igImage')
    assert all(o.get(12)==images[0].ref for o in result.objects_of('igTextureAttr'))
    assert (images[0].get(2),images[0].get(3))==picture.size
    off,size=result.block(images[0].get(13))
    assert result.data[off:off+size]==picture.tobytes()
    assert sum(i.get(12) for i in images)==64*32*4+4  # old: 2 * 64 * 32 * 4
    assert (images[1].get(2),images[1].get(3),images[1].get(19))==(1,1,4)


def test_party_relative_models_are_shared_across_cards_with_no_visual_aliases():
    screen=PT.party_layout('host')
    by={e['name']:e for e in screen['items']}
    for suffix in ('card','host','same_build','checking_build','empty','tone_good'):
        items=[by[f'lc_p{n}_{suffix}'] for n in range(1,5)]
        resources={O.variant_resource(screen,e) for e in items}
        assert len(resources)==1,(suffix,resources)
        assert all(O.variant_picture(e).tobytes()==O.variant_picture(items[0]).tobytes() for e in items)
    base=by['lc_p1_host'];name=O.variant_resource(screen,base)
    for key,value in [('color',7),('parts',[dict(kind='rect',rect=(0,0,3,3),color=5)]),('rect',(0,0,48,30))]:
        changed=copy.deepcopy(base);changed[key]=value
        assert O.variant_resource(screen,changed)!=name
    shifted=copy.deepcopy(base);x,y,w,h=shifted['rect'];shifted['rect']=(x+200,y+100,w,h)
    assert O.variant_resource(screen,shifted)==name


def test_model_background_package_does_not_preload_retired_page_sprite():
    for name in (*O.MENUS,O.PARTY_MENU):
        screen=PT.party_layout() if name==O.PARTY_MENU else O.runtime_layout(name)
        tree=O.add_backdrop(O.menu_tree(screen),name)
        pkg=O.package(tree)
        assert not any(e.tag=='texture' for e in pkg)
        assert any(e.get('filename')==O.backdrop_resource(name) for e in pkg)
        assert any(e.get('filename')=='ui/models/lc_o_field' for e in pkg)
    legacy=ET.Element('menu',name='legacy',igb='synthetic',image='textures/menus/synthetic')
    assert any(e.tag=='texture' and e.get('filename')=='textures/menus/synthetic' for e in O.package(legacy))


def test_code_tools_leave_padding_for_the_live_space_done_label():
    screen=O.runtime_layout('lc_code')
    done=next(e for e in screen['items'] if e['name']=='done')
    role,scale,_=O.font_binding(done);glyphs=O.OF.metrics()['lc_'+role]
    for value in ('[Space] DONE','[Enter] DONE',chr(0x90)+' DONE'):
        width=sum(float(glyphs.get(ord(c),glyphs[63])['horizadvance']) for c in value)*scale/.8
        assert width+12<=done['rect'][2],(value,width,done['rect'])
    assert done['rect'][0]+done['rect'][2]<=597
