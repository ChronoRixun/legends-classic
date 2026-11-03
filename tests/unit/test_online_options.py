"""Original synthetic Game Options trees; behavior belongs to the native class."""
import copy
import xml.etree.ElementTree as ET
from xml1build import online_menus as O
from xml1build import online_options as G


def native():
    root = ET.Element('menu', name='game_options', type='GAME_OPTIONS_MENU',
                      igb='synthetic_native', animonopen='true', menu_cancel='native_cancel')
    for n, name in enumerate(G.ROWS):
        item = ET.SubElement(root, 'item', name=name, style='native',
            up=G.ROWS[n-1], down=G.ROWS[(n+1) % len(G.ROWS)],
            usecmd='synthetic_action_'+str(n), callback='synthetic_callback', mode='0',
            enabled='true', clamp='true', animtext_scene='synthetic')
        ET.SubElement(item, 'onfocus', item='data_'+name[5:], type='focus')
        ET.SubElement(item, 'onfocus', item='synthetic_panel', type='focus', model='synthetic_old')
    for name in G.DATA:
        ET.SubElement(root, 'item', name=name, style='native', text='synthetic value',
                      gamevar='synthetic_binding', neverfocus='true')
    ET.SubElement(root, 'item', name='gamespy', type='MENU_ITEM_MODEL', model='synthetic_logo')
    ET.SubElement(root, 'item', name='synthetic_panel', type='MENU_ITEM_MODEL', model='synthetic_panel')
    ET.SubElement(root, 'item', name='text_title', text='synthetic title')
    return root


def test_options_retains_native_actions_bindings_modes_and_return():
    src = native(); before = ET.tostring(src)
    screen = G.layout(src)
    result = G.menu_tree(src, screen)
    assert ET.tostring(src) == before
    assert not G.problems(result, src, screen)
    assert result.get('type') == 'GAME_OPTIONS_MENU'
    assert result.get('menu_cancel') == 'native_cancel'
    assert result.get('igb') == G.MENU
    for name in (*G.ROWS, *G.DATA):
        old = src.find(f"item[@name='{name}']"); new = result.find(f"item[@name='{name}']")
        for key in ('usecmd','callback','mode','enabled','clamp','gamevar','platform','neverfocus','up','down'):
            assert new.get(key) == old.get(key), (name, key)
        assert not new.get('animtext_scene')
    for name in G.ROWS:
        assert result.find(f"item[@name='{name}']/onfocus[@item='data_{name[5:]}']") is not None
    assert result.find("item[@name='gamespy']").get('model') == 'ui/models/model_hide'
    assert not any('lcOnlineIntent' in e.get('usecmd','') for e in result)


def test_options_contract_rejects_changes_to_native_effects_and_missing_fields():
    src = native(); screen = G.layout(src); result = G.menu_tree(src, screen)
    for name, key in [('text_gamename','usecmd'),('data_gamename','gamevar'),('text_gametype','mode')]:
        bad = copy.deepcopy(result); bad.find(f"item[@name='{name}']").set(key,'changed')
        assert G.problems(bad, src, screen), (name,key)
    bad = copy.deepcopy(src); bad.remove(bad.find("item[@name='text_gametype']"))
    try: G.layout(bad)
    except ValueError: pass
    else: assert False, 'unsupported native tree must retain the native screen'


def test_options_scene_and_native_mouse_targets_cover_full_rows():
    src = native(); screen = G.layout(src); tree = G.menu_tree(src, screen)
    assert not O.layout_problems(screen)
    layouts = G.scene_layout(tree, screen)
    for key in G.ROWS:
        item = next(e for e in screen['items'] if e['name'] == key)
        # The native first-pass target includes both label and value.
        assert item['rect'][2] >= 500
        assert layouts[key][1][2] >= 400
        # Every pixel of the rectangle is both drawn focus and a native mouse
        # target. No separate hit-table adapter or custom input dispatch.
        rect,outline=O.focus_spec(screen,item)
        assert not outline and rect == layouts[key][1]
        # Runtime's optional closure gate names this shared resource too.
        assert O.focus_resource(rect,outline) == 'ui/models/lc_o_focus_0_-192_4144_0'
    assert len(layouts) < O.ENGINE_SCENE_ANCHORS
    assert layouts['gamespy'][0][0] < 0
    assert ('xml','ui/menus/'+G.MENU) in {(e.tag,e.get('filename')) for e in O.package(tree)}


def test_drop_in_variant_is_in_front_of_its_focus_fill():
    screen = O.runtime_layout('lc_host')
    by = {e['name']:e for e in screen['items']}
    for key in O.HOST_DROP_COPY:
        assert by[key]['plane'] < by['drop_in'].get('plane',-150)


def test_initial_hub_uses_connecting_copy_before_any_request():
    by = {e['name']:e for e in O.runtime_layout('lc_online')['items']}
    assert by['service']['text'] == 'Connecting...'
    for key in ('self_state',):
        if key in by: assert by[key]['text'] == 'Connecting...'


def test_optional_output_capability_requires_a_complete_screen(tmp_path):
    # Native-only/old output is valid as a fallback. Once advertised, the
    # optional screen must pass the same resource-closure gate as the family.
    baseline=O.output_problems(tmp_path)
    marker=tmp_path/'Data/lc_online_options.cap';marker.parent.mkdir(parents=True)
    marker.write_bytes(G.CAPABILITY)
    errors=O.output_problems(tmp_path)
    assert len(errors)>len(baseline)
    assert any(G.MENU+'.XMLB' in e for e in errors)
    marker.write_bytes(b'')
    assert O.output_problems(tmp_path)==baseline
