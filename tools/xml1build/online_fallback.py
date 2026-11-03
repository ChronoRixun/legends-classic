"""Fail-closed LC online resources, authored from the player's menu topology.

The default entry needs no runtime hook, private font, script intent or service.
Native online names are messages unless a verified LC skin already owns them.
"""
from __future__ import annotations
import copy
import xml.etree.ElementTree as ET

ENTRY = 'lc_online_entry'
MESSAGE = 'lc_online_unavailable'
CAPABILITY = b'lc-online-no-gamespy/1'
BACK = 'openmenu main'
BLOCKED = ('online', 'campaign_lobby', 'games_list', 'game_options', 'text_entry',
           'player_game_options', 'players_list', 'hero_list', 'region',
           'live_password', 'live_game_type', 'live_options', 'live_quickmatch',
           'live_optimatch', 'live_join_by_id', 'live_accounts', 'live_connect',
           'live_friends_list', 'live_feedback', 'live_voice_message')


def branding_item(item):
    return item.get('type') == 'MENU_ITEM_MODEL' and any(
        token in (item.get('name', '')+' '+item.get('model', '')).lower()
        for token in ('gamespy', 'logo'))


def strip_branding(native):
    """Remove model records and dangling decoration references, preserving actions."""
    root = copy.deepcopy(native)
    retired = {item.get('name') for item in root.findall('item') if branding_item(item)}
    for parent in root.iter():
        for item in list(parent):
            values = (item.get('model', '')+' '+item.get('filename', '')).lower()
            if (item.tag == 'item' and item.get('name') in retired or
                item.get('item') in retired or 'gamespy' in values or 'logo' in values):
                parent.remove(item)
    return root


def layout():
    from . import online_menus as O
    screen = dict(name=MESSAGE, items=[], shapes=[
        dict(kind='bar', rect=(43,84,158,4), color=5),
        dict(kind='panel', rect=(43,117,554,220), color=1),
        dict(kind='rect', rect=(61,357,300,30), color=2)],
        focus='back', runtime=True, native_options=True)
    for name, text, rect in (
        ('title', 'Online unavailable', (61,133,518,28)),
        ('reason', 'Online screens could not start on this build.', (61,193,518,24)),
        ('rebuild', 'Rebuild it from the launcher,', (61,230,518,24)),
        ('update', 'or update XML2 Fix.', (61,264,518,24))):
        screen['items'].append(O._entry(name,text,rect,'body',4))
    screen['items'].append(O._entry('back','Back to main menu',(61,357,300,30),'body',4,
                                   intent='native-role',usecmd=BACK,
                                   up='back',down='back',left='back',right='back'))
    return screen


def menu_tree(name):
    from . import online_menus as O
    tree = O.menu_tree(layout())
    tree.set('name',name);tree.attrib.pop('menu_cancel',None)
    # Retail CMenu::Back scans item flag 0x80 (5ad7c0), set by the
    # item's menu_cancel=true parser at 5bc84b. A root command is ignored.
    tree.find("item[@name='back']").set('menu_cancel','true')
    # Shared classic native-font styles already authored by dialog_appearance.
    # In particular, do not use lc_* slots when their DLL installer failed.
    for item in tree.findall('item'):
        if item.get('type') == 'MENU_ITEM_TEXT':
            item.set('style','STYLE_MENU' if item.get('name') == 'back' else 'STYLE_NORMAL')
            item.set('text',item.get('text','').removeprefix('~04'))
    return O.add_backdrop(tree,MESSAGE)


def resource_trees(native_trees, authored_trees, *, keep_lobbies=True):
    """Every retained online resource is either our lobby or the plain message."""
    aliases = set(BLOCKED) | {ENTRY,MESSAGE}
    kept = {}
    for name,native in native_trees.items():
        if native is None or not native.get('igb','').lower().startswith('x2m_svs_'):
            continue
        current = authored_trees.get(name)
        if (keep_lobbies and current is not None and current.get('igb') == 'lc_lobby_'+name and
            current.find("item[@name='lc_lobby_v1']") is not None):
            kept[name] = strip_branding(current)
            aliases.discard(name)
        else:
            aliases.add(name)
    return {name:menu_tree(name) for name in sorted(aliases)} | kept


def write(ctx, *, skinned_lobbies=False):
    from . import frontend as F, online_menus as O, menu_conversion as M
    original = ctx.x1_path(F.X1_MENU_IGB)
    focus = ctx.x1_path('ui/hud/dialog.igb')
    if original is None or focus is None:
        raise ValueError('online failure page needs the owned classic menu and frame')
    source,_ = M.convert_scene(original.read_bytes())
    screen = layout()
    # Below the original engine budget: this path must work when anchor hooks fail.
    scene = O.author_scene(source,screen,anchor_capacity=175)
    ctx.write_bytes('UI/menus/'+MESSAGE+'.IGB',scene,source='frontend:plain online failure scene')
    models = O.backdrop_models(focus.read_bytes(),screen)
    for item in screen['items']:
        if item['intent']:
            _,_,rect,outline,_ = O.focus_placement(screen,item)
            models[O.focus_resource(rect,outline)] = O.focus_model(focus.read_bytes(),rect,outline)
    for resource,data in models.items():
        ctx.write_bytes(resource+'.IGB',data,source='frontend:original online failure geometry')
    native_trees,authored_trees = {},{}
    # Discover every owned edition's retained online family, not a fixed six-file subset.
    for rel in list(ctx.base_index):
        if not rel.lower().startswith('ui/menus/') or not rel.lower().endswith('.engb'):
            continue
        native = ctx.read_base_xmlb(rel)
        if native is None or not native.get('igb','').lower().startswith('x2m_svs_'):
            continue
        name = rel.replace('\\','/').split('/')[-1][:-5]
        native_trees[name] = native
        authored_trees[name] = ctx.read_out_xmlb('UI/menus/'+name+'.XMLB')
    # A prior build's marker alone cannot keep a skin whose package/resources
    # were not authored this run (notably a rebuild with Menus off).
    resources = resource_trees(native_trees,authored_trees,keep_lobbies=skinned_lobbies)
    aliases,kept = [],[]
    for name,tree in resources.items():
        if tree.get('igb') != MESSAGE:
            kept.append(name)
            ctx.write_xmlb('UI/menus/'+name,tree,('.XMLB','.engb'),source='frontend:LC lobby without online branding')
            continue
        aliases.append(name)
        ctx.write_xmlb('UI/menus/'+name,tree,('.XMLB','.engb'),source='frontend:online failure instead of legacy service')
        package = M.package_for(tree)
        ET.SubElement(package,'xml',filename='ui/menus/'+name)
        ctx.write_xmlb(F.MENU_PKG_DIR+'/'+name,package,('.PKGB',),source='frontend:online failure resource closure')
    return dict(message=MESSAGE,entry=ENTRY,aliases=sorted(aliases),skinned_native=kept,
                anchors=O.anchor_count(scene),private_fonts=False,runtime_required=False)
