"""LC Game Options presentation over the native online setup service.

The original game_options definition is an authoring input; failure uses an LC message. No session
values, commands, availability gates or native data bindings are authored here.
"""
from __future__ import annotations
import copy
import xml.etree.ElementTree as ET
from . import online_menus as O

MENU = 'lc_game_options'
CAPABILITY = b'lc-online-options/1\n'
# These identifiers are the native service's ABI, including the PC maximum
# player row (text_mapname). The Xbox-only row retains its platform gate.
ROWS = ('text_gamename','text_difficulty','text_gametype','text_mapname',
        'text_maxplayers','text_inviteslots')
DATA = ('data_gamename','data_difficulty','data_gametype','data_mapname','data_maxplayers')
PRESENTATION = {'style','textalignx','textaligny','animtext_scene'}


def layout(native):
    if native is None: raise ValueError('native Game Options definition is missing')
    existing = {e.get('name'):e for e in native.findall('item')}
    if native.get('type') != 'GAME_OPTIONS_MENU' or any(k not in existing for k in (*ROWS,*DATA)):
        raise ValueError('unsupported native Game Options contract')
    screen = dict(name=MENU, items=[], shapes=[], focus=ROWS[0], runtime=True,
                  lobby=True, native_options=True, fixture_only=False)
    def text(key, value, rect, style='body', color=4, **kw):
        e = O._entry(key,value,rect,style,color,**kw)
        screen['items'].append(e)
        return e
    screen['shapes'] += [dict(kind='bar',rect=(43,24,55,16),color=5),
                         dict(kind='bar',rect=(43,84,158,4),color=5),
                         dict(kind='panel',rect=(43,117,554,232),color=1),
                         dict(kind='rect',rect=(61,380,518,24),color=2)]
    text('lc_online_tag','ONLINE',(51,26,43,13),'label',0)
    text('lc_brand','LEGENDS CLASSIC',(104,25,270,14),'label',3)
    text('text_title','GAME OPTIONS',(43,45,554,43),'title')
    # Native initialization supplies the localized labels and values. Empty
    # fields here prevent baking a guessed campaign, difficulty or player cap.
    for name,y in zip(ROWS,(137,187,237,287,287,380)):
        e = text(name,'',(61,y,518,24),'row',intent='native-role',usecmd='')
        for direction in ('up','down','left','right'):
            e[direction] = existing[name].get(direction,name)
    for name,y in zip(DATA,(137,187,237,287,287)):
        text(name,'',(280,y,298,24),'row',data=True,selected_with='text_'+name[5:])
    for i,(x,w) in enumerate(((43,106),(155,106),(267,106),(379,106),(491,106)),1):
        text('desctext'+str(i),'',(x,455,w,18),'body')
    text('lc_options_help','Choose the campaign, then open your room.',(61,326,518,17),'body',3)
    text('lc_options_path','Online > Host > Game options',(361,431,236,16),'label',3,align='right')
    return screen


def menu_tree(native, screen, palette_ids=None):
    from .online_fallback import strip_branding
    root = strip_branding(native)
    root.set('name',MENU); root.set('igb',MENU); root.set('image','')
    root.set('lighting','false')
    root.set('animonopen','false'); root.set('animonclose','false')
    authored = O.menu_tree(screen,palette_ids)
    existing = {e.get('name'):e for e in root.findall('item')}
    for src in authored.findall('item'):
        name = src.get('name'); actual = existing.get(name)
        if actual is None:
            root.append(copy.deepcopy(src)); continue
        for key in PRESENTATION - {'animtext_scene'}:
            if key in src.attrib: actual.set(key,src.get(key))
        actual.attrib.pop('animtext_scene',None)
        if name == 'text_title': actual.set('text',src.get('text'))
        if name in ROWS:
            # Keep non-model focus notifications to the native value widgets.
            # Only the old decorative model swaps are replaced.
            for child in list(actual):
                if child.tag == 'onfocus' and child.get('model'): actual.remove(child)
            for child in src: actual.append(copy.deepcopy(child))
    authored_names = {e['name'] for e in screen['items']}
    for name,item in existing.items():
        if name not in authored_names and item.get('type') == 'MENU_ITEM_MODEL':
            item.set('model','ui/models/model_hide')
    ET.SubElement(root,'item',name='lc_options_v1',type='MENU_ITEM_TEXT',text='',
                  neverfocus='true',hide='true',enabled='false')
    return root


def scene_layout(tree, screen):
    # The old decorative anchors are retired, while their parsed items remain
    # available to native init/update. The original animation scene is not used.
    return O.native_lobby_layouts(tree,screen)


def problems(tree, native, screen):
    errors = O.layout_problems(screen) + O.menu_item_problems(tree)
    if tree.get('type') != native.get('type'): errors.append('native setup class changed')
    for key,value in native.attrib.items():
        if key not in {'name','igb','image','lighting','animonopen','animonclose'} and tree.get(key) != value:
            errors.append('native root contract changed: '+key)
    for old in native.findall('item'):
        from .online_fallback import branding_item
        if branding_item(old): continue
        name = old.get('name'); new = tree.find(f"item[@name='{name}']")
        if new is None:
            errors.append('missing native setup item: '+name); continue
        allowed = PRESENTATION | ({'model'} if old.get('type') == 'MENU_ITEM_MODEL' else set())
        if name == 'text_title': allowed |= {'text'}
        for key in set(old.attrib) | set(new.attrib):
            if key not in allowed and new.get(key) != old.get(key):
                errors.append('native setup contract changed: '+name+'/'+key)
        for child in old:
            if child.tag == 'onfocus' and not child.get('model') and not any(
                    ET.tostring(child) == ET.tostring(c) for c in new):
                errors.append('native focus notification missing: '+name)
    return errors


def prepare(ctx, source, atlas, focus_source, palette_ids, metrics, anchor_capacity):
    """Build everything before publication; the caller publishes no skin on error."""
    native = ctx.read_base_xmlb('UI/menus/game_options.engb')
    screen = O.bound_layout(layout(native),metrics)
    tree = menu_tree(native,screen,palette_ids)
    errors = problems(tree,native,screen)
    data = O.author_scene(source,screen,scene_layout(tree,screen),anchor_capacity=anchor_capacity)
    errors += O.scene_problems(screen,data,anchor_capacity=anchor_capacity)
    if errors: raise ValueError('; '.join(errors))
    models = O.backdrop_models(focus_source,screen)
    for item in screen['items']:
        if not item['intent']: continue
        _,_,rect,outline,_ = O.focus_placement(screen,item)
        resource = O.focus_resource(rect,outline,O.focus_variant(screen,item))
        if resource not in models:
            models[resource] = O.focus_model(focus_source,rect,outline,slant=0)
    O.add_backdrop(tree,MENU)
    pixels = O.texture(atlas,O.render(screen,text=False,focus=False),MENU)
    return (MENU,tree,data,pixels), models
