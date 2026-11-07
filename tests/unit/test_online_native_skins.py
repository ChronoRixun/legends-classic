"""Synthetic native editor contracts: effects, key graph and mouse geometry."""
import copy
import xml.etree.ElementTree as ET
from xml1build import online_menus as O, online_native_skins as N


def native(name='text_entry'):
    if name!='text_entry':
        root=ET.Element('menu',name=name,type=N.TYPES[name],igb='synthetic',
                        menu_cancel='synthetic_cancel',no_stack='true',updownonly='true')
        for key in N.REQUIRED[name]:
            ET.SubElement(root,'item',name=key,style='synthetic',text='synthetic content',
                          mode='0',neverfocus='true',callback='synthetic_callback')
        for i,key in enumerate(N.CONTROLS[name]):
            item=root.find(f"item[@name='{key}']")
            item.set('neverfocus','false');item.set('usecmd','synthetic_effect_'+str(i))
            item.set('up',N.CONTROLS[name][i-1]);item.set('down',N.CONTROLS[name][(i+1)%len(N.CONTROLS[name])])
            ET.SubElement(item,'onfocus',item='synthetic_decoration',model='synthetic',type='focus')
            ET.SubElement(item,'onfocus',item='synthetic_value',type='focus')
        if name=='online':
            for i,key in enumerate(('msg_eula','msg_eula_euro','msg_dnas','msg_esrb'),1):
                item=root.find(f"item[@name='{key}']")
                item.set('mode',str(i));item.set('type','MENU_ITEM_TEXTBOX');item.set('arrowmodel','synthetic_arrow')
        if name=='games_list':
            listing=root.find("item[@name='text_list']");listing.set('type','MENU_ITEM_LISTBOX')
            listing.set('columns','2 358 TEXT_ALIGN_LEFT 0 TEXT_ALIGN_RIGHT')
            for kind,target in [('list_focus','text_list'),('list_up_arrow','up_arrow'),('list_down_arrow','down_arrow')]:
                ET.SubElement(listing,'onfocus',type=kind,item=target,model='synthetic',loop='1')
            root.find("item[@name='game_details']").set('type','MENU_ITEM_TEXTBOX')
        ET.SubElement(root,'item',name='synthetic_decoration',type='MENU_ITEM_MODEL',model='synthetic')
        return root
    root=ET.Element('menu',name=name,type=N.TYPES[name],igb='synthetic',
                    menu_cancel='synthetic_cancel',mode='0')
    for i,key in enumerate(N.KEYS):
        item=ET.SubElement(root,'item',name=key,style='synthetic',
            up=N.KEYS[(i-9)%40],down=N.KEYS[(i+9)%40],
            left=N.KEYS[i-1],right=N.KEYS[(i+1)%40],
            usecmd='synthetic_key_'+str(i),text='synthetic',mode='0')
        ET.SubElement(item,'onfocus',item='old_focus',type='focus',model='synthetic')
    ET.SubElement(root,'item',name='data_playername',gamevar='synthetic_buffer',neverfocus='true')
    ET.SubElement(root,'item',name='text_title',text='synthetic title',neverfocus='true')
    ET.SubElement(root,'item',name='old_focus',type='MENU_ITEM_MODEL',model='synthetic')
    return root


def test_native_text_editor_preserves_every_key_action_graph_and_buffer():
    src=native(); before=ET.tostring(src)
    screen=N.layout('text_entry',src); tree=N.menu_tree('text_entry',src,screen)
    assert ET.tostring(src)==before
    assert not N.problems('text_entry',tree,src,screen)
    for key in (*N.KEYS,'data_playername','text_title'):
        old=src.find(f"item[@name='{key}']"); new=tree.find(f"item[@name='{key}']")
        for attr in ('text','gamevar','up','down','left','right','mode','neverfocus'):
            assert new.get(attr)==old.get(attr),(key,attr)
        if key in N.KEYS:
            assert new.get('usecmd')=='runscript lcOnlineIntent('+str(100+N.KEYS.index(key))+')'
    assert len(tree.findall('.//onfocus'))==42
    assert tree.get('menu_cancel')=='synthetic_cancel'
    assert tree.find("item[@name='old_focus']").get('model')=='ui/models/model_hide'


def test_native_text_editor_rejects_missing_keys_changed_effects_and_overbudget():
    src=native(); screen=N.layout('text_entry',src); tree=N.menu_tree('text_entry',src,screen)
    for key,attr in [(N.KEYS[0],'right'),(N.KEYS[39],'usecmd'),('data_playername','gamevar')]:
        bad=copy.deepcopy(tree); bad.find(f"item[@name='{key}']").set(attr,'changed')
        assert N.problems('text_entry',bad,src,screen)
    bad=native(); bad.remove(bad.find(f"item[@name='{N.KEYS[35]}']"))
    try: N.layout('text_entry',bad)
    except ValueError: pass
    else: assert False,'partial keyboard must retain retail'
    for i in range(36): ET.SubElement(tree[0],'onfocus',type='focus')
    assert 'native focus pool exceeded' in N.problems('text_entry',tree,src,screen)


def test_native_text_editor_mouse_rectangles_equal_drawn_focus_and_do_not_overlap():
    screen=N.layout('text_entry',native()); layouts=O.scene_layout(screen)
    controls=[e for e in screen['items'] if e['intent']]
    for item in controls:
        target,_,rect,outline,_=O.focus_placement(screen,item)
        assert not outline and rect==layouts[item['name']][1]==layouts[target][1]
        assert item['rect'][2]>=50 and item['rect'][3]>=26
    for i,a in enumerate(controls):
        x,y,w,h=a['rect']
        for b in controls[i+1:]:
            bx,by,bw,bh=b['rect']
            assert x+w<=bx or bx+bw<=x or y+h<=by or by+bh<=y


def test_native_editor_groups_only_variable_key_backgrounds_within_item_budget():
    src=native(); screen=N.layout('text_entry',src)
    tree=N.menu_tree('text_entry',src,screen); O.add_backdrop(tree,N.MENUS['text_entry'])
    by={e['name']:e for e in screen['items']}
    groups={'lc_text_keys_6_11':range(5,11), 'lc_text_keys_12_36':range(11,36),
            'lc_text_keys_name_tools':(37,38)}
    covered=[]
    for name,indices in groups.items():
        group=by[name]; x,y,_,_=group['rect']
        drawn=[(x+p['rect'][0],y+p['rect'][1],*p['rect'][2:]) for p in group['parts']]
        expected=[by[N.KEYS[i]]['rect'] for i in indices]
        assert drawn==expected and all(p['kind']=='rect' and p['color']==2 for p in group['parts'])
        covered+=expected
        model=tree.find(f"item[@name='{name}']")
        assert model.get('type')=='MENU_ITEM_MODEL' and model.get('model')==O.variant_resource(screen,group)
        # Start loaded: the native renderer must retain the real model when the DLL unhides it later.
        assert model.get('hide') is None
    static=[p['rect'] for p in screen['shapes'] if p['kind']=='rect']
    assert all(rect not in static for rect in covered), 'hidden cells must not survive in the baked backdrop'
    assert all(by[N.KEYS[i]]['rect'] in static for i in (*range(5),36,39))
    assert len(groups)==3 and not O.menu_item_problems(tree)


def test_optional_native_text_editor_marker_requires_resource_closure(tmp_path):
    baseline=O.output_problems(tmp_path)
    path=tmp_path/N.marker('text_entry');path.parent.mkdir(parents=True)
    path.write_bytes(N.capability('text_entry'))
    assert any('lc_text_entry.XMLB' in e for e in O.output_problems(tmp_path))
    path.write_bytes(b'unsupported\n')
    assert any('invalid native online skin marker' in e for e in O.output_problems(tmp_path))
    path.write_bytes(b'')
    assert O.output_problems(tmp_path)==baseline


def test_other_ways_retains_all_policy_modes_content_and_native_effects():
    for name in ('online','campaign_lobby','games_list','player_game_options'):
        src=native(name);before=ET.tostring(src)
        screen=N.layout(name,src);tree=N.menu_tree(name,src,screen)
        assert ET.tostring(src)==before
        assert not N.problems(name,tree,src,screen)
        assert tree.get('no_stack')=='true' and tree.get('menu_cancel')=='synthetic_cancel'
        for key in N.REQUIRED[name]:
            old=src.find(f"item[@name='{key}']");new=tree.find(f"item[@name='{key}']")
            for attr in ('text','mode','callback','usecmd','columns','up','down','neverfocus','type'):
                assert new.get(attr)==old.get(attr),(name,key,attr)
            if old.get('type') in ('MENU_ITEM_TEXTBOX','MENU_ITEM_LISTBOX') and not (name=='games_list' and key=='text_list'):
                assert new.get('style')==old.get('style')
        for key in N.CONTROLS[name]:
            assert tree.find(f"item[@name='{key}']/onfocus[@item='synthetic_value']") is not None
        for attr in ('mode','text','type','callback'):
            bad=copy.deepcopy(tree);bad.find(f"item[@name='{N.REQUIRED[name][0]}']").set(attr,'changed')
            assert N.problems(name,bad,src,screen)


def test_native_lan_browser_keeps_list_scroll_selection_columns_and_return():
    src=native('games_list');screen=N.layout('games_list',src);tree=N.menu_tree('games_list',src,screen)
    listing=tree.find("item[@name='text_list']")
    assert listing.get('columns')=='2 358 TEXT_ALIGN_LEFT 0 TEXT_ALIGN_RIGHT'
    events=listing.findall('onfocus')
    assert [(e.get('type'),e.get('item'),e.get('loop')) for e in events]==[
        ('list_focus','text_list','1'),('list_up_arrow','up_arrow','1'),('list_down_arrow','down_arrow','1')]
    assert {e.get('model') for e in events}=={
        'ui/models/lc_o_lan_focus','ui/models/lc_o_picker_up','ui/models/lc_o_picker_down'}
    layouts=O.native_lobby_layouts(tree,screen)
    assert layouts['text_list'][1]==(0,-137.6,424.0,0)
    assert layouts['up_arrow'][0][0]>layouts['text_list'][0][0]
    assert ('xml','ui/menus/lc_games_list') in {(e.tag,e.get('filename')) for e in O.package(tree)}


def test_unknown_native_interactive_widgets_refuse_optional_authoring():
    for name in N.MENUS:
        tree=native(name)
        ET.SubElement(tree,'item',name='synthetic_extra_action',type='MENU_ITEM_TEXT',usecmd='synthetic')
        try: N.layout(name,tree)
        except ValueError: pass
        else: assert False,name


def test_lan_rows_use_private_scale_and_header_describes_the_native_composite_column():
    src=native('games_list');screen=N.layout('games_list',src);tree=N.menu_tree('games_list',src,screen)
    by={e['name']:e for e in screen['items']}
    assert tree.find("item[@name='text_list']").get('style')==O.font_binding(by['text_list'])[2]
    assert by['text_list']['style']=='row'
    assert by['lc_lan_players']['text']=='CAMPAIGN / PLAYERS'
    assert by['lc_lan_players']['rect'][0]+by['lc_lan_players']['rect'][2]==by['text_list']['rect'][0]+by['text_list']['rect'][2]
