"""GameSpy fallback and branding regressions on synthetic menu definitions."""
import xml.etree.ElementTree as ET
from xml1build import frontend as F, online_native_skins as N
from test_online_native_skins import native
from xml1build import online_fallback as B


def test_main_online_entry_cannot_open_gamespy_when_runtime_hooks_are_absent():
    assert F.PLAY_ONLINE_CMD == 'openmenu lc_online_entry'
    assert next(command for number, _, command in F.MENU_BUTTONS if number == 7) == 'openmenu lc_online_entry'


def test_native_online_skins_remove_branding_model_items_and_their_focus_references():
    src = native('campaign_lobby')
    ET.SubElement(src, 'item', name='gamespy', type='MENU_ITEM_MODEL', model='ui/models/m_gamespy_logo')
    target = src.find("item[@name='text_hostgame']")
    ET.SubElement(target, 'onfocus', item='gamespy', model='ui/models/m_gamespy_logo', type='focus')
    tree = N.menu_tree('campaign_lobby', src, N.layout('campaign_lobby', src))
    assert tree.find("item[@name='gamespy']") is None
    assert not any('gamespy' in str(element.attrib).lower() for element in tree.iter())
    assert tree.find("item[@name='text_hostgame']").get('usecmd') == 'synthetic_effect_0'
    assert src.find("item[@name='gamespy']") is not None


def test_failure_entry_and_every_legacy_alias_use_native_fonts_and_back_to_main():
    for name in ('lc_online_entry','lc_online_unavailable','online','campaign_lobby',
                 'games_list','game_options','text_entry','player_game_options',
                 'players_list','hero_list','region','live_password','live_connect'):
        tree = B.menu_tree(name)
        assert tree.get('name') == name and tree.get('igb') == 'lc_online_unavailable'
        assert not tree.get('type')
        assert tree.get('menu_cancel') is None
        back = tree.find("item[@name='back']")
        assert back.get('usecmd') == 'openmenu main'
        assert back.get('menu_cancel') == 'true'
        assert all(back.get(direction) == 'back' for direction in ('up','down','left','right'))
        assert all(item.get('style') in ('STYLE_NORMAL','STYLE_MENU')
                   for item in tree.findall('item') if item.get('type') == 'MENU_ITEM_TEXT')
        assert not any('lcOnlineIntent' in str(item.attrib) for item in tree.iter())
        assert 'could not start' in tree.find("item[@name='reason']").get('text')


def test_retained_online_branding_removal_preserves_nonbranding_models_and_actions():
    src = ET.Element('menu',type='SYNTHETIC_MENU',igb='x2m_svs_synthetic')
    for name,model in [('gamespy','ui/models/m_gamespy_logo'),
                       ('sequel_mark','ui/models/m_xmen2_logo'),
                       ('panel','ui/models/synthetic_panel')]:
        ET.SubElement(src,'item',name=name,type='MENU_ITEM_MODEL',model=model)
    action = ET.SubElement(src,'item',name='native_action',usecmd='synthetic_action')
    ET.SubElement(action,'onfocus',item='sequel_mark',type='focus')
    ET.SubElement(action,'onfocus',item='panel',type='focus',model='ui/models/synthetic_panel')
    ET.SubElement(src,'precache',type='model',filename='ui/models/m_gamespy_logo')
    tree = B.strip_branding(src)
    assert tree.find("item[@name='gamespy']") is None and tree.find("item[@name='sequel_mark']") is None
    assert tree.find("item[@name='panel']").get('model') == 'ui/models/synthetic_panel'
    action = tree.find("item[@name='native_action']")
    assert action.get('usecmd') == 'synthetic_action' and len(action) == 1
    assert action[0].get('item') == 'panel' and tree.find('precache') is None


def test_resource_authoring_blocks_unknown_retained_online_scenes_and_keeps_only_lc_lobbies():
    raw = {name:ET.Element('menu',type='SYNTHETIC_MENU',igb='x2m_svs_'+name)
           for name in ('online','host','join','edition_specific')}
    host = ET.Element('menu',type='HOST_MENU',igb='lc_lobby_host')
    ET.SubElement(host,'item',name='lc_lobby_v1')
    ET.SubElement(host,'item',name='start',usecmd='synthetic_start')
    # A marker alone must not certify the old scene.
    join = ET.Element('menu',type='JOIN_MENU',igb='x2m_svs_join')
    ET.SubElement(join,'item',name='lc_lobby_v1')
    trees = B.resource_trees(raw,{'host':host,'join':join})
    for name in ('online','join','edition_specific','lc_online_entry'):
        assert trees[name].get('igb') == 'lc_online_unavailable' and not trees[name].get('type')
    assert trees['host'].get('type') == 'HOST_MENU'
    assert trees['host'].find("item[@name='start']").get('usecmd') == 'synthetic_start'
    off = B.resource_trees(raw,{'host':host},keep_lobbies=False)
    assert all(not tree.get('type') for tree in off.values())


def test_online_packages_drop_logo_precaches_but_keep_native_dynamic_dependencies():
    from xml1build import online_menus as O
    tree = ET.Element('menu',name='synthetic',igb='synthetic')
    ET.SubElement(tree,'precache',type='model',filename='ui/models/m_gamespy_logo')
    ET.SubElement(tree,'precache',type='model',filename='ui/models/synthetic_dynamic')
    files = {item.get('filename') for item in O.package(tree)}
    assert 'ui/models/m_gamespy_logo' not in files
    assert 'ui/models/synthetic_dynamic' in files
