"""OFL Barlow Condensed metrics and prompt glyphs for four private font slots.

No network or installed fonts are used. The TTFs and license are pinned next to
this module. The owned atlas supplies only its container topology; every pixel
and metric in the private output is generated here.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont

SOURCE = Path(__file__).with_name('fonts') / 'barlowcondensed'
BASE_SIZES = {'title':96,'row':64,'body':64,'label':64}
ROLES = {'title': ('BarlowCondensed-ExtraBoldItalic.ttf',37),
         'row': ('BarlowCondensed-Bold.ttf',15),
         'body': ('BarlowCondensed-Medium.ttf',12.5),
         'label': ('BarlowCondensed-Bold.ttf',11)}
SCALES = {role: size*.8/BASE_SIZES[role] for role,(_,size) in ROLES.items()}
COMPACT_TITLE_SCALE = 22*.8/BASE_SIZES['title']
CODE_CELL_SCALE = 37*.8/BASE_SIZES['row']
PAD = {0x80+i:(letter,color) for i,(letter,color) in enumerate(
       (('A','#5AD68A'),('B','#FF6F55'),('X','#5B95FF'),('Y','#FFC83D')))}
PAD.update({0x84:('menu','#C4D4E9'),0x85:('pages','#C4D4E9'),0x86:('dpad','#C4D4E9')})
KEYS = dict(enumerate(('Enter','Esc','Space','Tab','Back','Del','Ins','Home','End',
                      'PgUp','PgDn','Up','Down','Left','Right','Shift'),0x90))
KEYS.update({0xc0+i:chr(65+i) for i in range(26)})
KEYS.update({0xe0+i:str(i) for i in range(10)})
KEYS.update({0xea+i:'F'+str(i+1) for i in range(12)})
KEYS.update({0xf6:'Ctrl',0xf7:'Alt',0xf9:'Ctrl+V'})

def verify_source():
    manifest=json.loads((SOURCE/'manifest.json').read_text(encoding='utf-8'))
    for name,record in manifest['files'].items():
        if Path(name).name != name or hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()!=record['sha256']:
            raise ValueError('Barlow Condensed source hash mismatch: '+name)
    return manifest

def generate(role):
    """Return native 256-record XML metrics and a top-down RGBA atlas.

    The loader's record is <hhhhi4f>: width, height, advance, x offset,
    baseline and four UVs. Atlas sampling subtracts its half-texel in the map
    loader, so our authored UVs include that half-texel.
    """
    verify_source()
    base_size=BASE_SIZES[role]
    font=ImageFont.truetype(str(SOURCE/ROLES[role][0]),base_size)
    # Caps have a fixed design height even in the large title atlas. Keep their
    # lettering inside that cap rather than inheriting the title face's ppem.
    key_size=min(round(base_size*.9),round(14.4/SCALES[role]*.67))
    key_font=ImageFont.truetype(str(SOURCE/'BarlowCondensed-Bold.ttf'),key_size)
    ascent,descent=font.getmetrics()
    if role=='title':ascent=-font.getbbox('H',anchor='ls')[1]+round(3.2/SCALES[role])
    root=ET.Element('FONT_TABLE',ascender=str(ascent),descender=str(descent),
                    height=str(ascent+descent),pointsize=str(base_size))
    atlas=Image.new('RGBA',(1024,1024));x=y=2;shelf=0
    fallback=None
    for code in range(256):
        if not 32<=code<=126 and code not in PAD and code not in KEYS and fallback is not None:
            ET.SubElement(root,'glyph',**dict(fallback,num=str(code)))
            continue
        char=chr(code) if 32<=code<=126 else '?'
        bbox=font.getbbox(char,anchor='ls');left,top,right,bottom=bbox
        width,height=right-left,bottom-top
        advance=round(font.getlength(char));baseline=-top;offset=left
        tile=Image.new('RGBA',(max(1,width),max(1,height)))
        if code in PAD:
            letter,color=PAD[code];height=round(14.4/SCALES[role]);width=round(height*.75)
            advance=width+round(base_size*.15);baseline=ascent+round(base_size/6);offset=0
            tile=Image.new('RGBA',(128,128));draw=ImageDraw.Draw(tile)
            draw.ellipse((2,2,125,125),fill=color)
            icon_font=ImageFont.truetype(str(SOURCE/'BarlowCondensed-Bold.ttf'),88)
            if letter=='menu':
                for yy in (42,62,82):draw.rectangle((35,yy,93,yy+6),fill='#0A1830')
            elif letter=='pages':
                draw.rectangle((35,35,75,75),outline='#0A1830',width=8)
                draw.rectangle((53,53,93,93),fill=color,outline='#0A1830',width=8)
            elif letter=='dpad':
                draw.rectangle((53,30,75,98),fill='#0A1830');draw.rectangle((30,53,98,75),fill='#0A1830')
            else:draw.text((64,64),letter,font=icon_font,anchor='mm',fill='#0A1830')
            tile=tile.resize((width,height),Image.Resampling.LANCZOS)
        elif code in KEYS:
            label=KEYS[code];height=round(14.4/SCALES[role])
            width=max(round(height*.75),round(key_font.getlength(label))+round(base_size*.3))
            advance=width+round(base_size*.15);baseline=ascent+round(base_size/6);offset=0
            tile=Image.new('RGBA',(width*4,height*4));draw=ImageDraw.Draw(tile)
            # A dark edge also keeps the shared cap legible on white primary
            # controls; it needs no renderer-color or device-specific variant.
            edge=max(1,round(height*.1));border=max(4,round(height*.2));radius=round(height*.15)
            draw.rounded_rectangle((2,2,width*4-3,height*4-3),radius=radius,outline='#0A1830',width=border+edge)
            draw.rounded_rectangle((2+edge,2+edge,width*4-3-edge,height*4-3-edge),
                                   radius=max(1,radius-edge),outline='#C4D4E9',width=border)
            kf=ImageFont.truetype(str(SOURCE/'BarlowCondensed-Bold.ttf'),key_size*4)
            draw.text((width*2,height*2),label,font=kf,anchor='mm',fill='#EEF3FA',
                      stroke_width=edge,stroke_fill='#0A1830')
            tile=tile.resize((width,height),Image.Resampling.LANCZOS)
        else:
            ImageDraw.Draw(tile).text((-left,-top),char,font=font,anchor='ls',fill='white')
        if x+width+2>atlas.width:x=2;y+=shelf+4;shelf=0
        if y+height+2>atlas.height:raise ValueError(f'private font atlas overflow: {role}, glyph {code}, y={y}, h={height}')
        atlas.alpha_composite(tile,(x,y))
        entry=ET.SubElement(root,'glyph',num=str(code),width=str(width),height=str(height),
                      horizoffset=str(offset),baseline=str(baseline),horizadvance=str(advance),
                      s=format((x+.5)/1024,'.10g'),t=format((y+.5)/1024,'.10g'),
                      s2=format((x+width+.5)/1024,'.10g'),t2=format((y+height+.5)/1024,'.10g'))
        if char=='?' and code not in PAD and code not in KEYS:fallback=dict(entry.attrib)
        x+=width+4;shelf=max(shelf,height)
    return root,atlas

def write(ctx,template):
    from . import online_menus as O
    manifest=verify_source();details={}
    for role in ROLES:
        name='lc_online_'+role;table,picture=generate(role)
        pixels=O.texture(template,picture.transpose(Image.Transpose.FLIP_TOP_BOTTOM),name)
        ctx.write_xmlb('UI/fonts/'+name,table,source='frontend:OFL Barlow private metrics')
        ctx.write_bytes('Textures/fonts/'+name+'.IGB',pixels,source='frontend:OFL Barlow private atlas')
        details[role]={'index':4+list(ROLES).index(role),'font':'lc_'+role,'resource':name,
                       'nominal_size':ROLES[role][1],'atlas_pointsize':BASE_SIZES[role],'textscale':SCALES[role]}
    # Separate maps keep the classic maps byte-identical. The DLL redirects only
    # the PC/HD loader paths to these copies when the opt-in transaction succeeds.
    for original,suffix in (('fonts_pc','pc'),('fonts_hd','hd')):
        table=ctx.read_out_xmlb('UI/fonts/'+original+'.XMLB')
        for role in ROLES:
            ET.SubElement(table,'font',index='lc_'+role,data='lc_online_'+role,
                          texture='lc_online_'+role)
        ctx.write_xmlb('UI/fonts/lc_fonts_'+suffix,table,source='frontend:scoped font map')
    ctx.write_bytes('licenses/BarlowCondensed-OFL.txt',(SOURCE/'OFL.txt').read_bytes(),source='frontend:OFL license')
    ctx.write_bytes('licenses/BarlowCondensed-source.json',
                    (json.dumps(manifest,indent=2)+'\n').encode(),source='frontend:font provenance')
    return details

def metrics():
    return {'lc_'+role:{int(e.get('num')):dict(e.attrib) for e in generate(role)[0]} for role in ROLES}

def resource_problems(table,data,role):
    """Verify native metrics and every emitted mip against the pinned source."""
    from . import igb_file as G
    expected,picture=generate(role);problems=[]
    if table is None or table.attrib!=expected.attrib or [dict(e.attrib) for e in table]!=[dict(e.attrib) for e in expected]:
        problems.append('private font metrics differ: '+role)
    if data is None:return problems+['private font atlas missing: '+role]
    try:
        graph=G.IgbFile(data)
        images=sorted(graph.objects_of('igImage'),key=lambda o:-o.get(2)*o.get(3))
        if not images or len({o.get(13) for o in images})!=len(images):
            raise ValueError('missing images or shared pixels')
        picture=picture.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        for level,image in enumerate(images):
            width=height=max(1,1024>>level)
            if image.get(2)!=width or image.get(3)!=height or image.get(11)!=7:
                raise ValueError('wrong image dimensions/format')
            block=graph.block(image.get(13))
            if block is None:raise ValueError('missing image pixels')
            offset,size=block;expected_pixels=picture.resize((width,height)).tobytes()
            if size!=len(expected_pixels) or data[offset:offset+size]!=expected_pixels:
                raise ValueError('atlas pixels do not match the metrics/source')
    except (ValueError,G.IgbError,TypeError,KeyError) as error:
        problems.append('private font atlas differs: '+role+': '+str(error))
    return problems
