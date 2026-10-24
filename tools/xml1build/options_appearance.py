"""Classic Options stack while retaining every native PC action and setting."""
from __future__ import annotations

import copy
import io
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

from . import menu_conversion as M, menu_scene as S, pause_appearance as P

SCENE = 'lc_options'
ROWS = ('label_effects_volume', 'label_music_volume', 'label_combat_music',
        'label_view_angle', 'label_view_cycle', 'label_view_follow', 'label_view_shake',
        'label_subtitles', 'label_vibration', 'label_accept')
VALUES = ('fx_vol', 'music_vol', 'combat_music', 'view_angle', 'view_cycle',
          'view_follow', 'view_shake', 'subtitles')
FOCUS = ('options_fxvol_focus', 'options_musicvol_focus', 'options_combatmusic_focus',
         'view_angle_focus', 'view_cycle_focus', 'view_follow_focus', 'view_shake_focus',
         'subtitles_focus', 'options_vibration_focus', 'accept_focus')

# Native BXIG sheets: dimensions and state-cell geometry are an engine contract.
# Keep their size, state order and widget rectangles; replace only their artwork.
SPRITES = {
    'bgleft.png': ((440,437),1,(102,6,440,430)),
    'bgright.png': ((680,488),1,(0,0,680,488)),
    'title.png': ((440,81),1,(80,3,440,79)),
    'button.png': ((449,490),5,(112,3,449,95)),
    'buttonR.png': ((449,490),5,(0,3,337,95)),
    'helpb.png': ((1153,95),1,(80,3,1105,92)),
    'tabbtn.png': ((121,130),5,(0,0,121,26)),
    'tabimg.png': ((676,70),1,(0,0,650,70)),
    'tabimg2.png': ((542,70),1,(0,0,542,70)),
    'toggle.png': ((307,56),1,(0,0,307,56)),
    'popup.png': ((722,506),1,(0,0,722,506)),
}


def state_atlas(picture, size, states, rectangle):
    """Retain native vertical state cells, including disabled/pressed/hover states."""
    w,h = size
    x1,y1,x2,y2 = rectangle
    if states not in (1,5) or h % states or not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h//states):
        raise ValueError('invalid native sprite state cells')
    if picture.size != (x2-x1,y2-y1):
        raise ValueError('classic frame does not fit the native state rectangle')
    atlas = Image.new('RGBA',size)
    levels = (1,) if states == 1 else (.8,1.25,1,.55,1.12)
    original = np.asarray(picture.convert('RGBA'))
    for index,level in enumerate(levels):
        pixels = original.copy()
        pixels[:,:,:3] = np.clip(np.rint(pixels[:,:,:3].astype(float)*level),0,255).astype(np.uint8)
        atlas.paste(Image.fromarray(pixels),(x1,index*(h//states)+y1))
    return atlas


def recolor_sprite(picture, rgb):
    """Keep native slider/table atlas silhouettes and alpha, using disc palette RGB."""
    pixels = np.asarray(picture.convert('RGBA')).copy()
    channels = pixels[:,:,:3].astype(float)
    mask = (channels[:,:,0] > channels[:,:,2]*1.2) & (channels[:,:,0] > channels[:,:,1]*.8)
    colored = channels[:,:,0,None]*np.asarray(rgb)[None,None,:]
    pixels[:,:,:3][mask] = np.clip(np.rint(colored[mask]),0,255).astype(np.uint8)
    return Image.fromarray(pixels)


def toggle_highlight(selected):
    """Resolution's solid strip at the toggle widget's native label baseline.

    The 196x38 toggle starts 21 virtual pixels above its label. Painting its
    whole 307x56 atlas covers two 24-pixel rows. Its bottom 28 texels give the
    same one-row selection as Resolution without moving native controls.
    """
    if selected.size != (306, 28):
        raise ValueError('native advanced Options selection dimensions changed')
    atlas = Image.new('RGBA', (307, 56))
    atlas.paste(selected.convert('RGBA').resize((307, 28)), (0, 28))
    return atlas


def write_advanced_sprites(ctx, panel_data):
    from . import menu_raster as R, menu_theme as T
    source = list(ctx.read_x1_xml('data/colors.xml'))
    tint = T.rgba(source[7].get('value'))[:3]
    rendered, report = {},{}
    for name,(size,states,rectangle) in SPRITES.items():
        if name == 'toggle.png':
            # This is a focus strip, unlike the surrounding decorative frames.
            with Image.open(ctx.base_index.path('Texs/selecteds.png')) as picture:
                atlas = toggle_highlight(recolor_sprite(picture, tint))
            ctx.write_bytes('Texs/' + name, R.png_bytes(atlas),
                            source='frontend:one-row solid advanced Options focus')
            report[name] = {'size': size, 'states': 1, 'rectangle': (0,28,307,56)}
            continue
        path = ctx.base_index.path('Texs/'+name)
        if path is None:
            raise ValueError('native advanced Options sprite is missing: '+name)
        with Image.open(path) as picture:
            if picture.size != size:
                raise ValueError('native advanced Options atlas dimensions changed: '+name)
        x1,y1,x2,y2 = rectangle
        key = (x2-x1,y2-y1)
        if key not in rendered:
            rendered[key] = R.frame(panel_data,*key)
        atlas = state_atlas(rendered[key],size,states,rectangle)
        ctx.write_bytes('Texs/'+name,R.png_bytes(atlas),source='frontend:disc frame in native BXIG sprite cells')
        report[name] = {'size':size,'states':states,'rectangle':rectangle}
    for name in ('controllist.png','selected.png','selecteds.png','slider.png','scrollbar.png'):
        path = ctx.base_index.path('Texs/'+name)
        if path is None:
            raise ValueError('native advanced Options control sprite is missing: '+name)
        with Image.open(path) as picture:
            result = recolor_sprite(picture,tint)
            report[name] = {'size':picture.size,'alpha':'native'}
        ctx.write_bytes('Texs/'+name,R.png_bytes(result),source='frontend:native BXIG control shapes with disc palette')
    path = ctx.base_index.path('Texs/col.png')
    if path is None:
        raise ValueError('native advanced Options column sprite is missing')
    with Image.open(path) as picture:
        ctx.write_bytes('Texs/col.png',R.png_bytes(Image.new('RGBA',picture.size)),
                        source='frontend:retired sequel decorative columns')
    return report


def options_scene(original, native, panels=None):
    aliases = {'button' + str(i): name for i, name in enumerate(ROWS, 1)}
    for i in range(1, 11):
        aliases[f'button{i}_back'] = f'lc_options_panel{i:02d}'
        aliases[f'button{i}_highlight'] = FOCUS[i-1]
    aliases.update({f'field{i}': name for i, name in enumerate(VALUES, 1)})
    artwork, report = M.convert_scene(original, aliases)
    names = set(ROWS) | set(VALUES) | set(FOCUS) | {'desctext1', 'desctext2'}
    native, _ = M.rename_aliases(S.retire_camera(native), {name: 'unused_' + name for name in sorted(names)})
    data, report['attachment'] = S.attach(native, artwork)
    # Keep native label/value roles, but lay them out inside the classic panels.
    from . import igb_file as G
    graph = G.IgbFile(data)
    positions = {o.get(2): o.get(8)[12:15] for o in graph.objects if o.name == 'igTransform'}
    layout = {}
    for i, name in enumerate(ROWS):
        z = positions[name][2]
        layout[f'lc_options_panel{i+1:02d}'] = ((256,-80,z),(-135,-15,135,15))
        layout[FOCUS[i]] = ((256,-100,z),(-150,-15,150,15))
        layout[name] = ((256 if i == 9 else 245, -150, z),
                        (-125, -13, 125, 13) if i == 9 else (-122, -13, 0, 13))
        if i < 9:
            value = (*VALUES, 'vibration')[i]
            layout[value] = ((365 if i > 1 else 270, -150, z),
                             (-110, -13, 0, 13) if i > 1 else (-45, -6, 45, 6))
    layout['label_options'] = ((256,-150,372),(-100,-9,100,9))
    for number,x,halfwidth in ((1,80,70),(2,220,70),(3,300,60),(4,370,126)):
        layout[f'desctext{number}'] = ((x,-150,16),(-halfwidth,-9,halfwidth,9))
    data = M.place_anchors(data, layout)
    if panels is not None:
        panels,_ = M.fit_flat_panel(panels,(-135,-15,135,15),border=8,opaque=True)
        data, report['panels'] = S.attach(data, S.static_model(panels),
            anchors=tuple(f'lc_options_panel{i:02d}' for i in range(1,11)), keep_camera=True)
    return data, report


def options_tree(native, bar_color):
    root = copy.deepcopy(native)
    root.attrib.update(igb=SCENE, lighting='true')
    for item in root.findall('item'):
        name = item.get('name', '')
        item.attrib.pop('animtext_scene', None)
        if name in ROWS:
            item.set('style', P.LIST_STYLE)
            item.set('textalignx', 'TEXT_ALIGN_CENTER_X' if name == ROWS[-1] else 'TEXT_ALIGN_RIGHT')
            for child in list(item):
                if child.tag == 'onfocus' and child.get('model'):
                    item.remove(child)
            target = FOCUS[ROWS.index(name)]
            ET.SubElement(item, 'onfocus', item=target, type='focus',
                          model='ui/models/model_button_highlight', loop='1')
            ET.SubElement(item, 'onfocus', item=target, type='nofocus', model='ui/models/model_hide')
        elif name in FOCUS:
            item.attrib.update(model='ui/models/model_hide', neverfocus='true', animate='true')
            item.attrib.pop('hide', None)
            item.attrib.pop('enabled', None)
        elif item.get('type') == 'MENU_ITEM_MODEL':
            item.attrib.update(model='ui/models/model_hide', hide='true', enabled='false')
        elif item.get('style'):
            item.set('style', P.BODY_STYLE)
        if name in ('label_options', 'label_controls'):
            item.attrib.update(hide='true', enabled='false')
        if name in ('fx_vol', 'music_vol'):
            item.attrib.update(color=str(bar_color), parallelogram='0')
    return root


def control_problems(native, converted):
    problems = P.native_text_problems(native,converted)
    for key in ('type','no_stack','updownonly'):
        if converted.get(key) != native.get(key):
            problems.append('Options native root contract changed: '+key)
    items = {e.get('name'):e for e in converted.findall('item')}
    for old in native.findall('item'):
        new = items.get(old.get('name'))
        if new is None:
            problems.append('Options native item missing: '+old.get('name',''))
            continue
        keys = ('type','mode','gamevar','usecmd','leftcmd','rightcmd','up','down')
        if old.get('name') in ROWS or old.get('gamevar'):
            keys += ('hide','enabled','neverfocus')
        for key in keys:
            if old.get(key) != new.get(key):
                problems.append('Options native control contract changed: '+old.get('name','')+'.'+key)
    return problems


def options_package(root, inherited):
    package = copy.deepcopy(inherited)
    # Retail's PC package retains a nonexistent console-diagram prototype. The
    # adapter retires that model and the old scene; keep other dynamic resources.
    retired = {'ui/menus/x2m_options','ui/models/m_options_controls_ps2'}
    for entry in list(package):
        if entry.tag.lower() == 'model' and (entry.get('filename') or '').lower() in retired:
            package.remove(entry)
    return M.package_for(root,inherited=package)


def write(ctx):
    from . import frontend as F, main_appearance as MA
    original = ctx.x1_path('ui/menus/menu_options.igb')
    native = ctx.base_index.path('UI/menus/x2m_options.IGB')
    if original is None or native is None:
        raise ValueError('Options scene input is missing')
    panels = ctx.x1_path('ui/models/model_button.igb')
    if panels is None:
        raise ValueError('classic Options panel model is missing')
    data, report = options_scene(original.read_bytes(), native.read_bytes(), panels.read_bytes())
    styles = ctx.read_out_xmlb('Data/styles.XMLB')
    color = next(e.get('color_focus') for e in styles if e.get('name') == MA.MAIN_STYLE)
    halves = []
    for ext in ('.XMLB', '.engb'):
        old = ctx.read_base_xmlb('UI/menus/options' + ext)
        tree = options_tree(old, color)
        problems = control_problems(old, tree) + M.widget_problems(tree, data)
        if problems:
            raise ValueError('; '.join(problems))
        halves.append(tree)
    ctx.write_bytes(f'UI/menus/{SCENE}.IGB', data, source='frontend:classic Options with native PC roles')
    ctx.write_xmlb_pair('UI/menus/options', *halves, source='frontend:classic Options, native PC settings')
    inherited = ctx.read_base_xmlb(F.MENU_PKG_DIR + '/options.PKGB')
    ctx.write_xmlb(F.MENU_PKG_DIR + '/options', options_package(halves[0],inherited), ('.PKGB',),
                    source='frontend:classic Options resource closure')
    report['advanced_sprites'] = write_advanced_sprites(ctx,panels.read_bytes())
    return report
