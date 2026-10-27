"""Generated OFL resources and scoping; no owned input or game process."""
import copy
import xml.etree.ElementTree as ET
from xml1build import online_fonts as F, online_menus as O, menu_theme as T

def test_source_pins_license_and_three_official_ttf_files():
    manifest=F.verify_source()
    assert len(manifest['files'])==4
    assert all(r['url'].startswith('https://raw.githubusercontent.com/google/fonts/main/ofl/barlowcondensed/') for r in manifest['files'].values())
    assert manifest['files']['OFL.txt']['sha256']=='186d750eb496a4c17a76385f82be6aea2ac1cf2de074a811d63786cf374ea73f'

def test_metrics_have_every_record_and_prompt_pixels_with_stable_codes():
    for role in F.ROLES:
        table,picture=F.generate(role)
        assert [int(e.get('num')) for e in table]==list(range(256))
        assert picture.size==(1024,1024) and picture.getbbox()
        by_num={int(e.get('num')):e for e in table}
        for code in F.PAD.keys()|F.KEYS.keys():
            e=by_num[code]
            assert int(e.get('horizadvance'))>0 and abs(int(e.get('height'))*F.SCALES[role]-14.4)<.5
            box=[round(float(e.get(k))*1024-.5) for k in ('s','t','s2','t2')]
            assert picture.crop(box).getchannel('A').getbbox()
        assert .0625<=F.SCALES[role]<=1
    assert len({F.SCALES[r] for r in F.ROLES})==4

def test_private_style_admission_cannot_select_private_slots_for_other_menus():
    colors=ET.Element('colors');styles=ET.Element('styles')
    for i in range(63):ET.SubElement(colors,'color',id=str(i),value='0 0 0 1')
    for i in range(24):ET.SubElement(styles,'style',name='retail'+str(i),font='medium')
    before=ET.tostring(styles)
    _,result,_=O.theme(colors,styles)
    assert ET.tostring(styles)==before
    assert [e.attrib for e in list(result)[:24]]==[e.attrib for e in styles]
    for e in list(result)[24:]:
        role=e.get('name').removeprefix('lc_o_')
        if role in O.STYLE_ALIASES:
            source,scale=O.STYLE_ALIASES[role]
            assert e.get('font')=='lc_'+source and abs(float(e.get('textscale'))-scale)<1e-8
        else:assert e.get('font')=='lc_'+role and abs(float(e.get('textscale'))-F.SCALES[role])<1e-8
    bad=T.text_style('unrelated',font='lc_row')
    try:T.allocate(ET.Element('colors'),ET.Element('styles'),ET.Element('colors'),[bad])
    except ValueError:pass
    else:assert False

def test_real_scaled_widths_preserve_approved_browser_fields():
    metrics=F.metrics();raw=O.layout('lc_browse');bounded=O.bound_layout(raw,metrics)
    for before,after in zip(raw['items'],bounded['items']):
        if before['name'].startswith('room_'):
            assert before['text']==after['text'],before['name']

def test_normal_approved_frames_need_no_ellipses_at_real_scales():
    metrics=F.metrics()
    for name in O.MENUS:
        raw=O.layout(name);bounded=O.bound_layout(raw,metrics)
        assert [e['text'] for e in raw['items']]==[e['text'] for e in bounded['items']],name
    cells=[e for e in O.layout('lc_code')['items'] if e['name'].startswith('cell')]
    assert cells and all(O.font_binding(e)[0]=='row' for e in cells)

def test_native_resource_validator_detects_metric_and_pixel_mismatch():
    from test_main_appearance import fixture
    from xml1build.igb_file import IgbFile
    from PIL import Image
    fields=[(i,'i') for i in (2,3,6,7,8,9,10,11,12)]+[(13,'b'),(19,'i'),(20,'i'),(22,'s')]
    values={2:32,3:32,6:100,7:8,8:8,9:8,10:8,11:7,12:4096,13:1,19:128,20:0,22:'synthetic-font'}
    template=fixture([('igImage',None,fields)],[('igImage',values)],(bytes(4096),))
    table,picture=F.generate('body')
    data=O.texture(template,picture.transpose(Image.Transpose.FLIP_TOP_BOTTOM),'lc_online_body')
    assert not F.resource_problems(table,data,'body')
    wrong=copy.deepcopy(table);wrong[65].set('horizadvance','999')
    assert any('metrics differ' in e for e in F.resource_problems(wrong,data,'body'))
    graph=IgbFile(data);offset,_=graph.block(graph.objects_of('igImage')[0].get(13))
    glyph=table[0x80];x=round(float(glyph.get('s'))*1024+4);y=1023-round(float(glyph.get('t'))*1024+4)
    corrupt=bytearray(data);corrupt[offset+(y*1024+x)*4]^=255
    assert any('atlas differs' in e for e in F.resource_problems(table,bytes(corrupt),'body'))

def test_default_device_glyphs_fit_every_authored_prompt_bound():
    import math
    mapping={'$MENU_ACCEPT':(0x80,0x90),'$MENU_BACK':(0x81,0x91),
             '$MENU_NEXT':(0x83,0xd5),'$MENU_OTHER':(0x82,0xc2),'$MENU_OK':(0x84,0x90)}
    metrics=F.metrics()
    overflows=[]
    for name in O.MENUS:
        for item in O.layout(name)['items']:
            if '$MENU_' not in item['text']:continue
            role,scale,_=O.font_binding(item);glyphs=metrics['lc_'+role]
            for device in (0,1):
                text=item['text']
                for token,codes in mapping.items():text=text.replace(token,chr(codes[device]))
                width=sum(float(glyphs[ord(c)]['horizadvance']) for c in text)*scale
                if width>math.floor(item['rect'][2]*.8):overflows.append((name,item['name'],device,width,item['rect']))
    assert not overflows,overflows
