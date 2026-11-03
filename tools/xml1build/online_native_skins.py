"""Optional LC scenes for native online services, using the player's definitions.

The native classes retain input, limits, modes, values, actions and return paths.
Only presentation is authored here; unsupported definitions keep retail assets.
"""
from __future__ import annotations
import copy
import xml.etree.ElementTree as ET
from . import online_menus as O

MENUS = {'text_entry': 'lc_text_entry', 'online':'lc_other_online',
         'campaign_lobby':'lc_campaign_lobby', 'games_list':'lc_games_list',
         'player_game_options':'lc_player_game_options'}
TYPES = {'text_entry': 'TEXT_ENTRY_MENU', 'online':'ONLINE_MENU',
         'campaign_lobby':'CAMPAIGN_LOBBY_MENU', 'games_list':'GAMES_LIST_MENU',
         'player_game_options':'PLAYER_GAME_OPTIONS_MENU'}
KEYS = tuple(f'text_inputkeys{i:02}' for i in range(1, 41))
CONTROLS = {'text_entry':KEYS, 'online':('text_playername','text_networkset','text_ready'),
            'campaign_lobby':('text_hostgame','text_joingame'), 'games_list':(),
            'player_game_options':('text_gamename','text_difficulty','text_mapname')}
REQUIRED = {'text_entry':(*KEYS,'data_playername','text_title'),
            'online':(*CONTROLS['online'],'data_playerfile','data_networkfile',
                      'msg_eula','msg_eula_euro','msg_dnas','msg_esrb','text_title'),
            'campaign_lobby':(*CONTROLS['campaign_lobby'],'text_title'),
            'games_list':('text_title','text_list','game_details','up_arrow','down_arrow'),
            'player_game_options':(*CONTROLS['player_game_options'],'data_gamename','data_difficulty','text_title')}
PRESENTATION = {'style', 'textalignx', 'textaligny', 'animtext_scene'}


def capability(name):
    return ('lc-online-skin/' + name + '/1\n').encode('ascii')


def marker(name):
    return 'Data/lc_online_skin_' + name + '.cap'


def layout(name, native):
    existing = {e.get('name'): e for e in native.findall('item')} if native is not None else {}
    required = REQUIRED[name]
    if native is None or native.get('type') != TYPES[name] or any(k not in existing for k in required):
        raise ValueError('unsupported native online contract: ' + name)
    known=set(required) | {f'desctext{i}' for i in range(1,6)}
    if any(key not in known and item.get('type')!='MENU_ITEM_MODEL' for key,item in existing.items()):
        raise ValueError('unsupported additional native online widget: ' + name)
    if name=='games_list' and (existing['text_list'].get('type')!='MENU_ITEM_LISTBOX' or
                              existing['game_details'].get('type')!='MENU_ITEM_TEXTBOX'):
        raise ValueError('unsupported native browser widgets')
    screen = dict(name=MENUS[name], items=[], shapes=[], focus=CONTROLS[name][0] if CONTROLS[name] else 'text_list', runtime=True,
                  lobby=True, native_options=True, fixture_only=False)
    def text(key, rect, style='body', value='', color=4, active=False):
        e = O._entry(key, value, rect, style, color,
                     **({'intent': 'native-role', 'usecmd': ''} if active else {}))
        if active:
            for direction in ('up', 'down', 'left', 'right'):
                target = existing[key].get(direction, key)
                e[direction] = target if target in CONTROLS[name] else key
        screen['items'].append(e)
        return e
    screen['shapes'] += [dict(kind='bar', rect=(43,24,55,16), color=5),
                         dict(kind='bar', rect=(43,84,158,4), color=5),
                         dict(kind='panel', rect=(43,117,554,274), color=1)]
    text('lc_online_tag', (51,26,43,13), 'label', 'ONLINE', 0)
    text('lc_brand', (104,25,270,14), 'label', 'LEGENDS CLASSIC', 3)
    text('text_title', (43,48,554,38), 'title')
    if name != 'text_entry':
        screen['shapes'][-1]['rect']=(43,117,554,296)
        if name == 'online':
            for key,y in zip(CONTROLS[name],(137,213,304)):
                text(key,(61,y,518,28 if key=='text_ready' else 50),'row',active=True)
            text('data_playerfile',(80,163,480,21),'row')
            text('data_networkfile',(80,239,480,21),'row')
            # Each policy/information mode retains its own native content,
            # mode predicate, scrolling service and acceptance/return behavior.
            for key in ('msg_eula','msg_eula_euro','msg_dnas','msg_esrb'):
                text(key,(61,130,518,268))
        elif name == 'player_game_options':
            for key,y in zip(CONTROLS[name],(137,213,304)):
                text(key,(61,y,518,28 if key=='text_mapname' else 50),'row',active=True)
            text('data_gamename',(80,163,480,21),'row')
            text('data_difficulty',(80,239,480,21),'row')
        elif name == 'campaign_lobby':
            for key,y in zip(CONTROLS[name],(151,257)):
                text(key,(61,y,518,50),'row',active=True)
            text('lc_host_help',(76,209,490,20),value='Choose the campaign and open a game.',color=3)
            text('lc_join_help',(76,315,490,20),value='Find a game on your network or at a known address.',color=3)
        else:
            text('lc_lan_header',(61,127,400,16),'label','GAME',3)
            text('lc_lan_players',(485,127,90,16),'label','PLAYERS',3)['align']='right'
            text('text_list',(61,151,530,172))
            text('game_details',(61,343,518,60))
            text('up_arrow',(581,151,9,12))
            text('down_arrow',(581,311,9,12))
        for i,(x,w) in enumerate(((43,106),(155,106),(267,106),(379,106),(491,106)),1):
            text('desctext'+str(i),(x,455,w,18))
        return screen
    text('data_playername', (61,130,518,27), 'row')
    screen['shapes'].append(dict(kind='rect', rect=(61,126,518,34), color=2))
    for i, key in enumerate(KEYS[:36]):
        rect = (70 + (i % 9)*56, 180 + (i // 9)*36, 50, 26)
        text(key, rect, 'row', active=True)['align'] = 'center'
        screen['shapes'].append(dict(kind='rect', rect=rect, color=2))
    for i, key in enumerate(KEYS[36:]):
        rect = (61+i*132,338,122,28)
        text(key, rect, 'body', active=True)['align'] = 'center'
        screen['shapes'].append(dict(kind='rect', rect=rect, color=2))
    # Native PC supplied no clickable Cancel. Mouse activation enters the same
    # Escape character path as the keyboard; original key links remain intact.
    screen['items'].append(O._entry('lc_text_cancel','Cancel',(43,402,132,28),'body',4,
        intent='native-role',usecmd='runscript lcOnlineIntent(140)',
        up=KEYS[36],down=KEYS[36],left=KEYS[39],right=KEYS[36],align='center'))
    screen['shapes'].append(dict(kind='rect',rect=(43,402,132,28),color=2))
    for i, (x,w) in enumerate(((43,106),(155,106),(267,106),(379,106),(491,106)), 1):
        text('desctext'+str(i), (x,455,w,18))
    return screen


def menu_tree(name, native, screen, palette_ids=None):
    root = copy.deepcopy(native)
    root.set('name', MENUS[name]); root.set('igb', MENUS[name]); root.set('image', '')
    for key, value in [('lighting','false'),('animonopen','false'),('animonclose','false')]:
        root.set(key, value)
    authored = O.menu_tree(screen, palette_ids)
    existing = {e.get('name'): e for e in root.findall('item')}
    for src in authored.findall('item'):
        actual = existing.get(src.get('name'))
        if actual is None:
            root.append(copy.deepcopy(src)); continue
        for key in PRESENTATION - {'animtext_scene'}:
            # LISTBOX/TEXTBOX renderers own their native metrics/scroll extent;
            # they do not use the private CText scaling hook.
            if key=='style' and actual.get('type') in ('MENU_ITEM_LISTBOX','MENU_ITEM_TEXTBOX'): continue
            if key in src.attrib: actual.set(key, src.get(key))
        actual.attrib.pop('animtext_scene', None)
        if src.get('name') in CONTROLS[name]:
            if name=='text_entry':
                actual.set('usecmd', 'runscript lcOnlineIntent('+str(100+KEYS.index(src.get('name')))+')')
            for child in list(actual):
                if child.tag == 'onfocus' and child.get('model'): actual.remove(child)
            # Native focus deactivation retires its model record (0x5ae580).
            # Like the retail keyboard, one record/key fits the 75-record pool.
            for child in src:
                if child.tag == 'onfocus' and child.get('type') == 'focus':
                    actual.append(copy.deepcopy(child))
    for item in existing.values():
        if item.get('type') == 'MENU_ITEM_MODEL':
            item.set('model', 'ui/models/model_hide')
        if item.get('arrowmodel'): item.set('arrowmodel','ui/models/lc_o_picker_down')
    for precache in root.findall('precache'):
        if precache.get('type')=='model': precache.set('filename','ui/models/lc_o_picker_down')
    if name=='games_list':
        listing=existing['text_list']
        for event in listing.findall('onfocus'):
            replacement={'list_focus':'ui/models/lc_o_picker_focus',
                         'list_up_arrow':'ui/models/lc_o_picker_up',
                         'list_down_arrow':'ui/models/lc_o_picker_down'}.get(event.get('type'))
            if replacement: event.set('model',replacement)
    return root


def problems(name, tree, native, screen):
    errors = O.layout_problems(screen)
    allowed_root = {'name','igb','image','lighting','animonopen','animonclose'}
    for key in set(native.attrib) | set(tree.attrib):
        if key not in allowed_root and tree.get(key) != native.get(key):
            errors.append('native root contract changed: ' + key)
    for old in native.findall('item'):
        new = tree.find(f"item[@name='{old.get('name')}']")
        if new is None:
            errors.append('missing native item: '+old.get('name')); continue
        allowed = PRESENTATION | {'arrowmodel'} | ({'model'} if old.get('type') == 'MENU_ITEM_MODEL' else set())
        if name=='text_entry' and old.get('name') in KEYS:
            allowed |= {'usecmd'}
            if new.get('usecmd') != 'runscript lcOnlineIntent('+str(100+KEYS.index(old.get('name')))+')':
                errors.append('invalid native key command: '+old.get('name'))
        for key in set(old.attrib) | set(new.attrib):
            if key not in allowed and new.get(key) != old.get(key):
                errors.append('native contract changed: '+old.get('name')+'/'+key)
        for child in old:
            if not (child.tag == 'onfocus' and child.get('model')) and not any(
                    ET.tostring(child) == ET.tostring(c) for c in new):
                errors.append('native child missing: '+old.get('name'))
    if len(tree.findall('.//onfocus')) > 75: errors.append('native focus pool exceeded')
    if name=='text_entry':
        cancel=tree.find("item[@name='lc_text_cancel']")
        if cancel is None or cancel.get('usecmd')!='runscript lcOnlineIntent(140)':
            errors.append('native Escape button contract')
    return errors


def prepare(ctx, name, source, atlas, focus_source, palette_ids, metrics, anchor_capacity):
    native = ctx.read_base_xmlb('UI/menus/'+name+'.engb')
    screen = O.bound_layout(layout(name,native), metrics)
    tree = menu_tree(name,native,screen,palette_ids)
    errors = problems(name,tree,native,screen)
    data = O.author_scene(source,screen,O.native_lobby_layouts(tree,screen),anchor_capacity=anchor_capacity)
    errors += O.scene_problems(screen,data,anchor_capacity=anchor_capacity)
    if errors: raise ValueError('; '.join(errors))
    models = O.backdrop_models(focus_source,screen)
    if name in ('online','games_list'): models.update(O.picker_models(focus_source))
    for item in screen['items']:
        if not item['intent']: continue
        _,_,rect,outline,_ = O.focus_placement(screen,item)
        resource = O.focus_resource(rect,outline,O.focus_variant(screen,item))
        if resource not in models: models[resource] = O.focus_model(focus_source,rect,outline,slant=0)
    O.add_backdrop(tree,MENUS[name])
    pixels = O.texture(atlas,O.render(screen,text=False,focus=False),MENUS[name])
    return (MENUS[name],tree,data,pixels), models
