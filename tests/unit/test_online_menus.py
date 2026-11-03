"""Synthetic online presentation and fixture contracts; no game input or networking."""
import copy
import xml.etree.ElementTree as ET
from xml1build import online_menus as O
from test_main_appearance import raises


def test_code_grid_graph_and_fixture_editing():
    state = O.Fixture()
    screen = O.layout('lc_code', state)
    assert not O.layout_problems(screen)
    keys = [e for e in screen['items'] if e['name'].startswith('key_')]
    assert len(keys) == 32
    state.dispatch('clear')
    for char in 'K7QN2X9M':
        state.dispatch('code:' + char)
    assert state.code == 'K7QN2X9M' and state.phase == 'resolved fixture'
    state.dispatch('delete'); assert state.code == 'K7QN2X9'
    state.dispatch('clear'); assert not state.code
    state.dispatch('paste', 'K7QN-2X9M'); assert state.code == 'K7QN2X9M'
    state.dispatch('paste', 'bad;command'); assert state.code == 'K7QN2X9M' and state.error
    state.menu='lc_code'
    state.dispatch('back'); assert state.code == 'K7QN2X9'
    state.dispatch('clear'); state.dispatch('back'); assert state.menu == 'lc_online'


def test_browse_bounded_scroll_clipping_and_disabled_join():
    state = O.Fixture()
    for _ in range(40): state.dispatch('scroll:1')
    assert state.selected == len(state.rooms)-1 and state.offset == len(state.rooms)-O.BROWSE_ROWS
    for _ in range(40): state.dispatch('scroll:-1')
    assert (state.selected, state.offset) == (0, 0)
    for i in range(len(state.rooms)):
        state.selected = i; state.rebound()
        screen = O.layout('lc_browse', state)
        assert not O.layout_problems(screen)
        assert len([e for e in screen['items'] if e['name'].startswith('room_')]) == 7 * O.BROWSE_ROWS
    state.selected = 5; state.dispatch('join'); assert state.error and state.phase != 'resolved fixture'
    state.rooms = []; state.rebound()
    assert (state.selected,state.offset)==(0,0)
    assert 'No public games' in str(O.layout('lc_browse', state))
    assert not O.layout_problems(O.layout('lc_browse',state))
    state.dispatch('join'); assert state.error
    assert len(O.field('long $BAD #123 ~12 | name', 12)) <= 12
    assert not any(c in O.field('$#~|;%name',20) for c in '$#~|;%')


def test_paired_menus_packages_commands_and_mutation_detection():
    for name in O.MENUS:
        screen = O.layout(name)
        tree = O.menu_tree(screen)
        assert not O.layout_problems(screen)
        assert not O.tree_problems(tree, screen)
        assert all('runscript' not in e.get('usecmd','') for e in tree.iter())
        package = O.package(tree)
        assert ('xml','ui/menus/'+name) in {(e.tag,e.get('filename')) for e in package}
        bad = copy.deepcopy(screen); bad['items'][0]['rect'] = (-2,0,20,20)
        assert O.layout_problems(bad)
        focus = next(e for e in tree if e.get('down'))
        focus.set('right','missing'); assert O.tree_problems(tree,screen)
    assert O.NATIVE_ENTRY == 'openmenu online'
    state = O.Fixture(); state.dispatch('open-room'); assert state.phase == 'host preview fixture'
    assert len(state.members)==3
    raises(ValueError, lambda: state.dispatch('unknown;script'))


def test_theme_overflow_is_atomic_and_preserves_unrelated_tables():
    colors = ET.Element('colors'); styles = ET.Element('styles')
    for i in range(63): ET.SubElement(colors,'color',id=str(i),value='0 0 0 1')
    for i in range(24): ET.SubElement(styles,'style',name='native'+str(i))
    before = ET.tostring(colors), ET.tostring(styles)
    result = O.theme(colors, styles)
    assert len(result[0])==71 and len(result[1])==31
    assert (ET.tostring(colors), ET.tostring(styles))==before

    for i in range(63,68): ET.SubElement(colors,'color',id=str(i),value='0 0 0 1')
    raises(ValueError, lambda: O.theme(colors,styles))
    assert len(colors)==68 and len(styles)==24


def test_fixture_errors_back_reentry_and_command_manifest():
    state=O.Fixture()
    for screen in O.MENUS:
        state.dispatch('open:'+screen); state.dispatch('error')
        assert state.error and not O.layout_problems(O.layout(screen,state))
        state.dispatch('dismiss'); assert not state.error
    for intent in O.command_manifest():
        state.dispatch(intent)
    state.dispatch('visibility'); assert state.visibility in ('PRIVATE','PUBLIC')
    state.dispatch('campaign'); state.dispatch('drop-in')
    assert 'next area' in str(O.layout('lc_host',state))
    raises(ValueError,lambda:O.layout('unowned'))


def test_back_deletes_last_cell_without_leaving_and_caps_browser_cache():
    state=O.Fixture(menu='lc_code',code='K')
    state.dispatch('back')
    assert state.menu=='lc_code' and state.code==''
    state.dispatch('back'); assert state.menu=='lc_online'
    state.dispatch('open:lc_host'); state.dispatch('back'); assert state.menu=='lc_online'
    state.rooms=O.synthetic_rooms()*10; state.selected=1000; state.rebound()
    assert len(state.rooms)==50 and state.selected==49 and state.offset==50-O.BROWSE_ROWS


def test_native_initial_focus_and_budget_consumption_are_explicit():
    for name in O.MENUS:
        screen=O.layout(name)
        active=[e.get('name') for e in O.menu_tree(screen) if e.get('startactive')=='true']
        assert active==[screen['focus']]
    colors=ET.Element('colors');styles=ET.Element('styles')
    for i in range(63): ET.SubElement(colors,'color',id=str(i),value='0 0 0 1')
    for i in range(24): ET.SubElement(styles,'style',name='native'+str(i))
    assert O.reserved_budget(colors,styles)==(8,4)
    c,s,_=O.theme(colors,styles)
    assert O.reserved_budget(c,s)==(4,1)
    s.remove(next(e for e in s if e.get('name')=='lc_o_title'))
    assert O.reserved_budget(c,s)==(8,4)


def anchor_fixture(broken=False, *, item_name=False):
    """Invented native-shaped binding graph and camera for serializer coverage."""
    import struct
    from test_main_appearance import fixture
    fields=[(2,'s'),(3,'r'),(5,'i')]
    lists=[(2,'i'),(3,'i'),(4,'b')]
    specs=[('igNode',None,fields),('igGroup','igNode',fields+[(7,'r')]),
           ('igTransform','igGroup',fields+[(7,'r'),(8,'m'),(11,'r')]),
           ('igHashedUserInfo','igGroup',fields+[(7,'r'),(8,'r')]),
           ('igCamera','igNode',fields),('igStringValue',None,[(2,'s')]),
           ('igAABox',None,[(2,'v'),(3,'v')]),('igDataList',None,lists),
           ('igObjectList','igDataList',lists)]
    specs += [(kind,'igObjectList',lists) for kind in ('igInfoList','igNodeList','igTextureList','igGraphPathList')]
    specs += [('igSceneInfo',None,[(5,'r'),(6,'r'),(7,'r'),(11,'r')])]
    identity=[float(i in (0,5,10,15)) for i in range(16)]
    objects=[('igInfoList',{2:1,3:1,4:15}),('igSceneInfo',{5:2,6:9,7:10,11:11}),
             ('igGroup',{2:'synth_root',3:-1,5:0,7:3}),('igNodeList',{2:2,3:2,4:16}),
             ('igTransform',{2:'template',3:-1,5:0,7:5,8:identity,11:-1}),
             ('igNodeList',{2:1,3:1,4:17}),
             ('igHashedUserInfo',{2:'template',3:7,5:0,7:-1,8:8}),
             ('igAABox',{2:[0,0,-10],3:[100,0,0]}),
             ('igStringValue',{2:'broken' if broken else 'template'}),
             ('igTextureList',{2:0,3:0,4:-1}),('igGraphPathList',{2:0,3:0,4:-1}),
             ('igNodeList',{2:0,3:0,4:-1}),
             ('igTransform',{2:'synth_camera_transform',3:-1,5:0,7:13,8:identity,11:-1}),
             ('igNodeList',{2:1,3:1,4:18}),('igCamera',{2:'synth_camera',3:-1,5:0})]
    if item_name:
        specs += [('igStringKey',None,[(2,'s')]),('igProperty',None,[(2,'r'),(3,'r')])]
        objects += [('igStringKey',{2:'ItemName'}),('igProperty',{2:15,3:8})]
        objects[6][1][8]=16
        for index in (0,3,5,13): objects[index][1][4]+=2
    return fixture(specs,objects,tuple(struct.pack('<'+'i'*len(v),*v) for v in ((1,),(4,12),(6,),(14,))))


def test_authored_scenes_clone_complete_aliases_and_preserve_camera_and_inputs():
    from xml1build import menu_scene as S, menu_conversion as M
    from xml1build.igb_file import IgbFile, IgbError
    source=anchor_fixture()
    for name in O.MENUS:
        screen=O.layout(name); placements=O.scene_layout(screen)
        data=S.author_anchors(source,'template',placements)
        assert data==S.author_anchors(source,'template',placements)
        graph=IgbFile(data)
        assert graph.obj(14).get(2)=='synth_camera'
        assert not M.placement_problems(data,placements)
        assert not M.widget_problems(O.menu_tree(screen),data)
        for key in placements:
            assert len([o for o in graph.objects if o.name in ('igTransform','igHashedUserInfo','igStringValue') and o.get(2)==key])==3
        assert source==anchor_fixture()
    raises(IgbError,lambda:S.author_anchors(anchor_fixture(True),'template',{'test':((1,2,3),(0,-1,1,0))}))
    raises(IgbError,lambda:S.author_anchors(source,'missing',{'test':((1,2,3),(0,-1,1,0))}))
    raises(IgbError,lambda:S.author_anchors(source,'template',{'test':((float('nan'),2,3),(0,-1,1,0))}))


def test_family_palette_overflow_fails_before_any_context_write():
    class Context:
        writes=[]
        def opt(self,key,default):return 'on'
        def read_out_xmlb(self,rel):
            root=ET.Element('colors' if 'colors' in rel else 'styles')
            if 'colors' in rel:
                for i in range(75): ET.SubElement(root,'color',id=str(i),value='0 0 0 1')
            return root
        def __getattr__(self,name):
            if name.startswith('write'): return lambda *a,**k:self.writes.append((a,k))
            raise AssertionError('preflight touched input before checking palette: '+name)
    ctx=Context()
    raises(ValueError,lambda:O.write(ctx))
    assert not ctx.writes


def test_host_preview_and_page_controls_follow_fixture_settings():
    state=O.Fixture()
    state.dispatch('campaign');state.dispatch('drop-in')
    screen=O.layout('lc_host',state)
    values={e['name']:e['text'] for e in screen['items']}
    assert values['preview_save']=='New campaign - Normal'
    assert values['preview_drop']=='Drop-in off'
    page=min(O.BROWSE_ROWS,len(state.rooms)-O.BROWSE_ROWS)
    state.dispatch('page:1'); assert (state.selected,state.offset)==(page,page)
    state.dispatch('page:-1'); assert (state.selected,state.offset)==(0,0)


def test_seven_field_ellipsis_uses_measured_width_without_overflow():
    widths={c:(12 if c=='W' else 3) for c in 'Wlong name.'}
    measure=lambda value:sum(widths.get(c,6) for c in value)
    for width in (1,9,20,60,128):
        clipped=O.fit_text('WW long name',width,measure)
        assert measure(clipped)<=width
    assert O.fit_text('name',60,measure)=='name'
    raises(ValueError,lambda:O.fit_text('name',0,measure))


def test_scene_validator_detects_broken_third_alias_and_graph_reachability():
    from xml1build import menu_scene as S
    from xml1build.igb_file import IgbFile
    import struct
    screen=O.layout('lc_online')
    data=S.author_anchors(anchor_fixture(),'template',O.scene_layout(screen))
    assert not O.scene_problems(screen,data)
    graph=IgbFile(data)
    root=graph.obj(graph.objects_of('igSceneInfo')[0].get(5));children=graph.obj(root.get(7))
    for slot in (2,3):struct.pack_into('<i',graph.buf,children.fields[slot].offset,1)
    assert any('unreachable' in p for p in O.scene_problems(screen,graph.rebuilt({children.get(4):struct.pack('<i',12)})))


def test_native_menu_tree_clips_all_seven_fields_using_retained_metric_widths():
    state=O.Fixture()
    for row in state.rooms:
        row.update(name='W'*32,host='W'*31,area='W'*31,status='W'*20)
    screen=O.layout('lc_browse',state)
    metrics={index:{ord(c):{'horizadvance':'12'} for c in 'W./ SAMEOTHER0123456789'} for index in ('medium','big')}
    bounded=O.bound_layout(screen,metrics)
    tree=O.menu_tree(bounded)
    entries={e.get('name'):e for e in tree}
    for item in bounded['items']:
        if item['name'].startswith('room_'):
            text=entries[item['name']].get('text','')
            if text.startswith('~'):text=text[3:]
            measure=lambda value:sum(float(metrics['medium'].get(ord(c),{'horizadvance':'12'})['horizadvance']) for c in value)
            assert measure(text)<=item['rect'][2]*.8
    assert screen['items']!=bounded['items']


def test_generated_image_names_are_scoped_without_changing_pixels():
    from test_main_appearance import fixture
    from xml1build.igb_file import IgbFile
    source=fixture([('igImage',None,[(22,'s')])],[('igImage',{22:'synthetic-source.png'})],(b'synthetic pixels',))
    result=O.namespace_images(source,'test_scope')
    before,after=IgbFile(source),IgbFile(result)
    assert after.objects_of('igImage')[0].get(22)=='test_scope_0'
    assert before.objects_of('igImage')[0].get(22)=='synthetic-source.png'
    assert before.blocks.keys()==after.blocks.keys()
    for ref,(offset,size) in before.blocks.items():
        new_offset,new_size=after.blocks[ref]
        assert size==new_size and source[offset:offset+size]==result[new_offset:new_offset+new_size]


def test_focused_row_retains_status_decoration_in_native_focus_picture():
    screen=O.layout('lc_browse')
    item=next(e for e in screen['items'] if e['name']=='room_0_0')
    rect,outline=O.focus_spec(screen,item)
    image=O.focus_picture(screen,item,rect)
    assert outline and image.size[0]>1000
    # Selected steel fill must not cover the independent status diamond.
    x=round((410.5-44)*3);y=round((193-178)*2.25)
    assert image.getpixel((x,y))==tuple(bytes.fromhex(O.PALETTE[6]))


def test_native_grid_labels_keep_every_symbol_with_wide_glyph_advances():
    metrics={index:{ord(c):{'horizadvance':str(20 if index=='medium' else 32)} for c in O.ALPHABET+'<.'} for index in ('medium','big')}
    state=O.Fixture(code='WWWWWWWW')
    screen=O.bound_layout(O.layout('lc_code',state),metrics)
    keys=[e['text'] for e in screen['items'] if e['name'].startswith('key_')]
    assert ''.join(keys)==O.ALPHABET
    assert next(e for e in screen['items'] if e['name']=='key_31')['intent']=='delete'
    assert any(e['kind']=='backspace' for e in screen['shapes'])
    assert all(e['text']=='W' for e in screen['items'] if e['name'].startswith('cell'))


def test_all_authored_background_previews_render_without_font_inputs():
    for name in O.MENUS:
        picture=O.render(O.layout(name),size=(640,480),text=False)
        assert picture.size==(640,480)


def test_native_description_refresh_preserves_tokens_and_has_all_five_bindings():
    for name in O.MENUS:
        screen=O.layout(name)
        tree=O.menu_tree(screen)
        items={e.get('name'):e for e in tree.findall('item')}
        anchors=O.scene_layout(screen)
        for i in range(1,6):
            key='desctext'+str(i)
            assert key in items and key in anchors and key in tree.attrib
            value=items[key].get('text','')
            if value:
                assert '$MENU_' in value and '[' not in value
                assert tree.get(key).startswith('~04$MENU_')
        mutated=copy.deepcopy(tree); mutated.attrib.pop('desctext3')
        assert 'native description contract' in O.tree_problems(mutated,screen)
    state=O.Fixture(rooms=[])
    screen=O.layout('lc_browse',state)
    focus=next(e for e in screen['items'] if e['name']==screen['focus'])
    assert focus['prompt_key']=='refresh' and not O.layout_problems(screen)


def test_description_authoring_retires_source_alias_collision_without_losing_camera():
    from xml1build import menu_scene as S
    from xml1build.igb_file import IgbFile
    position=((0,-150,0),(0,-12,80,0))
    original=S.author_anchors(anchor_fixture(),'template',{'button1':position,'desctext1':position})
    before=IgbFile(original)
    screen=O.layout('lc_online')
    result=O.author_scene(original,screen)
    assert not O.scene_problems(screen,result)
    after=IgbFile(result)
    assert after.obj(14).get(2)==before.obj(14).get(2)=='synth_camera'
    assert len([o for o in after.objects_of('igTransform') if o.get(2)=='desctext1'])==1
    assert len([o for o in before.objects_of('igTransform') if o.get(2)=='desctext1'])==1


def test_device_preview_follows_companion_labels_without_fabricating_icons():
    assert O.preview_text('$MENU_ACCEPT Select')=='A Select'
    assert O.preview_text('$MENU_OTHER Change name')=='X Change name'
    assert O.preview_text('$MENU_ACCEPT Select','keyboard')=='[Enter] Select'
    assert O.preview_text('$MENU_BACK Back','keyboard')=='[Esc] Back'
    assert O.preview_text('$MENU_OK Open')=='[Start] Open'
    raises(ValueError,lambda:O.preview_text('$MENU_OK','unknown'))


def test_pad_prompt_tokens_name_the_job_the_dll_binds_to_x_and_y():
    # 060p live round failure 8: the screens' prompts and the DLL's pad buttons must agree. $MENU_OTHER jobs are X in the
    # designs, $MENU_NEXT jobs are Y; the pad_prompts hook draws them as the pad's X / Y on these screens only.
    assert O.PAD_TOKEN_BUTTONS=={'$MENU_OTHER':'X','$MENU_NEXT':'Y'}
    other_jobs=('change','name','clear','kick','ready')
    next_jobs=('rejoin','paste','refresh','copy')
    found={'$MENU_OTHER':set(),'$MENU_NEXT':set()}
    for key,token in O.PROMPT_TOKENS.items():
        if token in found: found[token].add(key)
    assert found['$MENU_OTHER']=={'clear','name','change'} and found['$MENU_NEXT']=={'paste','refresh','rejoin'}
    for name in O.MENUS:
        for item in O.layout(name)['items']:
            text=item.get('text') or ''
            for token,jobs in (('$MENU_OTHER',other_jobs),('$MENU_NEXT',next_jobs)):
                if token in text:
                    assert any(job in text.lower() for job in jobs),(name,item['name'],text)
    assert O.preview_text('$MENU_NEXT Rejoin')=='Y Rejoin' and O.preview_text('$MENU_OTHER Clear')=='X Clear'
    assert O.preview_text('$MENU_NEXT Rejoin','keyboard')=='[Y] Rejoin'


def test_right_aligned_fields_keep_their_native_alignment_after_serialization():
    screen=O.layout('lc_online')
    tree=O.menu_tree(screen)
    by_name={e.get('name'):e for e in tree}
    for item in screen['items']:
        if item.get('align')=='right':
            assert by_name[item['name']].get('textalignx')=='TEXT_ALIGN_RIGHT'
            position,bounds=O.scene_layout(screen)[item['name']]
            assert abs(position[0]-item['rect'][0]*.8)<1e-6
            assert bounds[0]==0 and abs(bounds[2]-item['rect'][2]*.8)<1e-6
    # Long hints are clipped using the full interval ending at the approved edge.
    item=next(e for e in screen['items'] if e['name']=='host_hint')
    assert item['rect'][0]+item['rect'][2]==294
    metrics={index:{i:{'horizadvance':'6'} for i in range(128)} for index in ('medium','big')}
    bounded=O.bound_layout(screen,metrics)
    value=next(e for e in bounded['items'] if e['name']=='host_hint')['text']
    assert value.startswith('Private or ') and len(value)*6<=113*.8
    assert len(value)>int(70*.8/6)


def test_every_authored_menu_scene_fits_the_engine_anchor_capacity():
    from xml1build import menu_scene as S, online_fonts as F
    from xml1build.igb_file import IgbError
    cap=O.engine_scene_anchors(O.ANCHOR_CAPABILITY)
    assert O.BROWSE_ROWS==7 and cap==512 and O.engine_scene_anchors(b'')==175
    for name in O.MENUS:
        screen=O.bound_layout(O.runtime_layout(name),F.metrics())
        layouts={**O.backdrop_layouts(),**O.scene_layout(screen)}
        assert len(layouts)<=cap, (name,len(layouts))
        authored=S.author_anchors(anchor_fixture(item_name=True),'template',layouts,anchor_capacity=cap)
        assert O.anchor_count(authored)==len(layouts)
        assert not any('engine holds' in problem for problem in O.scene_problems(screen,authored,anchor_capacity=cap))
        assert not any('engine holds 175' in problem for problem in O.scene_problems(screen,authored))
    layouts=O.scene_layout(O.bound_layout(O.runtime_layout('lc_browse'),F.metrics()))
    assert len(layouts)<=175
    # Keep the 175/176 boundary proof independent of the current menu composition.
    overflow={f'synthetic_anchor_{n}':((0,0,0),(0,-1,1,0)) for n in range(176)}
    raises(IgbError,lambda:S.author_anchors(anchor_fixture(),'template',overflow))
    expanded=S.author_anchors(anchor_fixture(item_name=True),'template',overflow,anchor_capacity=cap)
    assert O.anchor_count(expanded)==176
    assert any('engine holds 175' in problem for problem in O.scene_problems(screen,expanded))
    probes=b' '.join(O.DLL_PROBES)
    assert not O.capability_problems(probes)
    assert O.capability_problems(probes.replace(O.ANCHOR_CAPABILITY,b''))


def test_anchor_count_matches_the_engine_walk_on_the_060p_candidate_scenes():
    """Fixture from the live round: the 060p candidate's own menu scenes. The engine-walk count reproduces the crash
    (Browse 241 > 175) and the screens that worked (Host lobby 153, Join by code 132, Hub 96)."""
    import unittest
    from pathlib import Path
    menus=Path('D:/Projects/xml1-port/build/_candidate_060p/UI/menus')
    if not (menus/'lc_browse.IGB').is_file(): raise unittest.SkipTest('060p candidate build not on this machine')
    counts={n:O.anchor_count((menus/(n+'.IGB')).read_bytes()) for n in ('lc_browse','lc_lobby_host','lc_code','lc_online')}
    assert counts=={'lc_browse':241,'lc_lobby_host':153,'lc_code':132,'lc_online':67}, counts
    assert counts['lc_browse']>O.ENGINE_SCENE_ANCHORS>=max(v for k,v in counts.items() if k!='lc_browse')


def test_every_screen_draws_its_art_as_scene_models_not_the_menu_sprite():
    # Live 060p: the untyped lc_ menus are the base CMenu (vtable 0x69e41c), whose init (0x5af7b0) never
    # reads `image`, so the sprite background never drew (black screen, text only); the typed lobbies
    # drew it pinned to 512 x 384 and upside down. The art now travels as the first two scene models.
    for name in O.MENUS:
        tree=O.add_backdrop(O.menu_tree(O.runtime_layout(name)),name)
        first=list(tree.findall('item'))[:2]
        assert [e.get('name') for e in first]==list(O.BACKDROP_ITEMS)
        assert all(e.get('type')=='MENU_ITEM_MODEL' and e.get('neverfocus')=='true' for e in first)
        assert first[0].get('model')=='ui/models/lc_o_field' and first[1].get('model')==O.backdrop_resource(name)
        assert tree.get('image')==''
    layouts=O.backdrop_layouts()
    assert set(layouts)==set(O.BACKDROP_ITEMS) and all(anchor==(0,-150,384) for anchor,_ in layouts.values())
    l,b,r,t=O.BACKDROP_RECT;assert (l,b,r,t)==(0,-384,512,0)  # exactly the 640 x 480 composition
    l,b,r,t=O.FIELD_RECT
    # hor+ view: 384 tall, aspect*384 wide, centred on x=256 -> covers 16:9, 16:10, 21:9 and 32:9 (3.56:1)
    for aspect in (4/3,16/10,16/9,21/9,32/9):
        half=aspect*384/2;assert l<=256-half and r>=256+half and (b,t)==(-384,0)
    assert O.FIELD_DEPTH>O.BACKDROP_DEPTH>40  # behind every focus bar (40) and scene, field deepest


def test_backdrop_field_continues_the_composition_gradient():
    art=O.render(O.runtime_layout('lc_online'),size=(1024,1024),text=False,focus=False)
    field=O.field_picture()
    # Left/right edges of the 4:3 art are bare gradient; the field must meet them row for row.
    for y in (0,128,255):
        edge=art.getpixel((0,y*4)); fill=field.getpixel((0,y))[:3]
        assert max(abs(a-b) for a,b in zip(edge,fill))<=3


def test_browse_focus_bars_share_one_model_item_at_the_same_screen_position():
    """060q: every Browse focus bar is one model item at the scene origin; each bar's geometry is its owner's own
    focus rect moved by the owner's anchor, so it lands where the per-item anchor put it (pixel for pixel). The lobbies
    share one item per plane."""
    from xml1build import online_fonts as F
    screen=O.bound_layout(O.runtime_layout('lc_browse'),F.metrics())
    root=O.menu_tree(screen);layouts=O.scene_layout(screen)
    assert layouts[O.SHARED_FOCUS][0]==O.SHARED_FOCUS_ORIGIN
    assert [e.get('name') for e in root.findall('item')].count(O.SHARED_FOCUS)==1
    assert [n for n in layouts if n.endswith('_focus')]==[O.SHARED_FOCUS]
    sx,sy,sz=O.SHARED_FOCUS_ORIGIN;checked=0
    for e in screen['items']:
        if not (e['intent'] and (e['enabled'] or screen.get('runtime'))): continue
        target,owner,rect,outline,relative=O.focus_placement(screen,e)
        assert target==O.SHARED_FOCUS
        ax,ay,az=O._anchor(owner);assert ay==sy
        assert all(abs(m-(r+o))<1e-3 for m,r,o in zip(rect,relative,(ax-sx,az-sz,ax-sx,az-sz)))
        item=next(i for i in root.findall('item') if i.get('name')==e['name'])
        assert [(f.get('item'),f.get('type'),f.get('model')) for f in item.findall('onfocus')]==[(O.SHARED_FOCUS,'focus',O.focus_resource(rect,outline,O.focus_variant(screen,owner)))]
        checked+=1
    assert checked>=11
    # the lobbies share one focus item per plane (-150 actions, -300 player list / Leave confirm)
    for role in O.LOBBIES:
        lob=O.bound_layout(O.lobby_layout(role),F.metrics());lay=O.scene_layout(lob)
        assert sorted(n for n in lay if n.endswith('_focus') or n.startswith(O.SHARED_FOCUS))==[O.SHARED_FOCUS,O.SHARED_FOCUS+'_300'],role
        assert lay[O.SHARED_FOCUS+'_300'][0]==(0,-300,384)
        tree=O.menu_tree(lob)
        for name in ('lc_leave_yes','lc_leave_cancel','lc_lobby_dismiss','text_leaveroom','lc_copy_code'):
            item=next(i for i in tree.findall('item') if i.get('name')==name)
            plane=next(e for e in lob['items'] if e['name']==name).get('plane',-150)
            assert {f.get('item') for f in item.findall('onfocus')}=={O.shared_focus(plane)[0]},(role,name)
    # the other screens keep their own per-item focus anchors and nofocus events
    hub=O.menu_tree(O.bound_layout(O.runtime_layout('lc_online'),F.metrics()))
    assert O.SHARED_FOCUS not in {i.get('name') for i in hub.findall('item')}
    assert any(f.get('type')=='nofocus' for i in hub.findall('item') for f in i.findall('onfocus'))


def _built_screens():
    from xml1build import online_fonts as F, online_party as PT
    screens={name:O.bound_layout(O.runtime_layout(name),F.metrics()) for name in O.MENUS}
    screens.update({name:O.bound_layout(O.lobby_layout(name),F.metrics()) for name in O.LOBBIES})
    screens[O.PARTY_MENU]=O.bound_layout(PT.party_layout('host'),F.metrics())
    return screens


def test_mouse_hit_table_lists_every_drawn_focus_bar():
    """0.6 preview fix E (live 060p item 7): the engine hit-tests the box an item's text is laid out in (0x5bc530 ->
    0x5bc1b0), every focus bar is larger (an ordinary row: 12 units left/right, 5 above, 2 below), so the bar's top and
    both ends were dead. The builder lists each drawn bar (absolute view units) for the DLL's scoped hit test."""
    screens=_built_screens()
    data=O.hit_table(screens)
    assert data.startswith(b'lc-online-hits/2\n') and data.endswith(b'\n') and b'\r' not in data
    lines=data.decode('ascii').splitlines()[1:]
    rows={(l.split()[0],l.split()[1]):tuple(map(float,l.split()[2:6])) for l in lines}
    assert len(rows)==len(lines)  # one bar per item and screen
    for name,screen in screens.items():
        drawn=[e for e in screen['items'] if e['intent'] and (e['enabled'] or screen.get('runtime'))]
        for e in drawn:
            if e['intent']=='native-picker':
                assert (name,e['name']) not in rows  # the Kick picker LISTBOX hit-tests its own rows
                continue
            L,B,R,T=rows[(name,e['name'])]
            assert L<R and B<T
            # the bar is the focus model's geometry (focus_placement) at the owner's anchor - the same numbers the
            # model file is fitted to, independent of the shared-focus origin
            _,owner,rect,_,(l,b,r,t)=O.focus_placement(screen,e)
            ax,_,az=O._anchor(owner)
            assert all(abs(u-v)<1e-3 for u,v in zip((L,B,R,T),(ax+l,az+b,ax+r,az+t))),(name,e['name'])
    # An ordinary row (Hub Join by code at (58,178,236,22)): the text box padded 12 / 5 / 12 / 2 view units.
    assert rows[('lc_online','code')]==(34.4,222.0,247.2,246.6)
    # The live 060p measurement at 1280x720 (16:9: view 682.7 wide, left -85.3; 1.875 px per unit): bar x 225-630 drawn,
    # clickable only from x 249 (the text box): the table's left edge is the drawn one.
    assert abs((34.4+85.3333)*1.875-224.5)<1
    # Browse rows: every cell of a row carries the whole row's bar
    assert rows[('lc_browse','room_0_0')]==rows[('lc_browse','room_0_6')]


def test_mouse_hit_table_is_written_with_the_menus_and_required_from_the_dll():
    assert O.HITS_FILE=='Data/lc_online_hits.txt' and b'lc-online-hits/1' in O.DLL_PROBES
    import inspect
    source=inspect.getsource(O.write)
    assert 'hit_table(authored_layouts)' in source and 'HITS_FILE' in source


def test_kicked_guest_notice_is_a_plain_hub_notice_within_the_anchor_budget():
    """0.6 preview fix E: a guest the host removed (native Kick) sees 'The host removed you from the game.' on the Hub,
    not the host-left panel. One hidden notice node (no new scene); Browse never raises it, so it spends no anchor there."""
    from xml1build import online_fonts as F
    assert O.NOTICE_TEXT['lc_notice_removed']=='The host removed you from the game.'
    assert 'lc_notice_removed' in O.BROWSE_UNREACHABLE_NOTICES
    hub=O.bound_layout(O.runtime_layout('lc_online'),F.metrics())
    node=next(e for e in hub['items'] if e['name']=='lc_notice_removed')
    assert node.get('hidden') and not node['intent'] and node['color']==7
    browse=O.bound_layout(O.runtime_layout('lc_browse'),F.metrics())
    assert 'lc_notice_removed' not in {e['name'] for e in browse['items']}
    for name in O.MENUS:
        assert len(O.scene_layout(O.bound_layout(O.runtime_layout(name),F.metrics())))+len(O.backdrop_layouts())<=O.engine_scene_anchors(O.ANCHOR_CAPABILITY), name


# ---- 0.6 preview fix E2: the hit table is validated by the builder and compared with the built bars ---------------------------

def _hit_screens():
    return _built_screens()


def test_hit_table_validator_names_every_reason_the_dll_parser_refuses():
    good = O.hit_table(_hit_screens())
    assert O.hit_table_problems(good) == []
    header = b'lc-online-hits/1\n'
    row = b'lc_online host 34.4 253.2 247.2 277.8\n'
    cases = {
        'bom': b'\xef\xbb\xbf' + header + row, 'crlf': header.replace(b'\n', b'\r\n') + row.replace(b'\n', b'\r\n'),
        'header': b'lc-online-hits/2\n' + row, 'no rows': header, 'empty': b'', 'unterminated': header + row[:-1],
        'long line': header + row[:-1] + b'7' * 300 + b'\n', 'duplicate': header + row + row, 'blank line': header + b'\n' + row,
        'double space': header + b'lc_online  host 1 2 3 4\n', 'trailing space': header + b'lc_online host 1 2 3 4 \n',
        'name dash': header + b'lc_online ho-st 1 2 3 4\n', 'name dot': header + b'lc_online ho.st 1 2 3 4\n',
        'name long': header + b'lc_online ' + b'a' * 64 + b' 1 2 3 4\n',
        'exponent': header + b'lc_online host 1e2 2 3 4\n', 'plus': header + b'lc_online host +1 2 3 4\n',
        'comma': header + b'lc_online host 1,5 2 3 4\n',
        'range': header + b'lc_online host 5000 2 6000 4\n', 'inverted x': header + b'lc_online host 3 2 3 4\n',
        'inverted y': header + b'lc_online host 1 4 3 4\n',
        'five fields': header + b'lc_online host 1 2 3\n', 'seven fields': header + b'lc_online host 1 2 3 4 5\n',
        'non ascii': header + 'lc_online h\u00e9st 1 2 3 4\n'.encode('utf-8'),
        'too many': header + b''.join(b'm i%d 1 2 3 4\n' % i for i in range(O.HITS_MAX_ENTRIES + 1)),
        'too big': header + b'm i 1 2 3 4\n' * (O.HITS_MAX_FILE // 12 + 1),
    }
    for label, data in cases.items():
        assert O.hit_table_problems(data), label
    assert O.hit_table_problems(header + row) == []
    assert O.hit_table_problems(header + row + b'host text_startgame 34.4 46.8 180 71.4\n') == []


def test_hit_table_refuses_at_build_time_what_would_switch_the_hit_boxes_off():
    """One bad name or rectangle makes the DLL refuse the whole table (every co-op screen goes back to the engine's dead
    strips); the builder raises instead of writing it."""
    screens = _hit_screens()
    real = O.hit_rows
    try:
        for bad in ([('bad-name', 0, 0, 10, 10)], [('x', 5, 0, 5, 10)], [('x', 0, 10, 10, 10)], [('x', 0, 0, 1e9, 10)],
                    [('x', 0, 0, 10, 10), ('x', 20, 0, 30, 10)]):
            O.hit_rows = lambda screen, bad=bad: bad
            raises(ValueError, lambda: O.hit_table(screens))
    finally:
        O.hit_rows = real
    O.hit_table(screens)


def test_hit_table_refuses_a_bar_that_reaches_the_kick_picker():
    """The Kick picker is a focusable item the table does not list: a bar over it would let the engine hand it the click."""
    screens = _hit_screens()
    picker = O.hit_unlisted_boxes(screens['host'])
    assert [p[0] for p in picker] == ['text_playername1']
    _, l, b, r, t = picker[0]
    for name, screen in screens.items():
        for _, pl, pb, pr, pt in O.hit_unlisted_boxes(screen):
            for item, bl, bb, br, bt in O.hit_rows(screen):
                assert not (bl < pr and pl < br and bb < pt and pb < bt), (name, item)
    real = O.hit_rows
    try:
        O.hit_rows = lambda screen: real(screen) + [('overlap', l + 10, b + 10, r - 10, t - 10)] if screen['name'] == 'host' else real(screen)
        raises(ValueError, lambda: O.hit_table(screens))
    finally:
        O.hit_rows = real


def _dll_parser():
    import os
    import pathlib
    import unittest
    exe = os.environ.get('XML2_FIX_HITS_PARSE_TEST')
    if not exe or not pathlib.Path(exe).exists():
        raise unittest.SkipTest('set XML2_FIX_HITS_PARSE_TEST to xml2_online_hits_parse_test.exe (xml2-fix)')
    return exe


def test_builder_output_passes_the_dll_parser_and_verdicts_agree(tmp_path):
    """The builder's real table goes through the DLL's own parser (online_menus_hits::parse, built as
    xml2_online_hits_parse_test): accepted, every entry the builder's number; and a set of broken files get the same accept /
    refuse verdict from the builder's validator and the DLL's parser."""
    import subprocess
    exe = _dll_parser()
    data = O.hit_table(_hit_screens())

    def run(blob, name):
        path = tmp_path / name
        path.write_bytes(blob)
        done = subprocess.run([exe, str(path)], capture_output=True, text=True)
        return done.returncode, done.stdout

    code, out = run(data, 'builder.txt')
    assert code == 0, out
    entries = [l.split() for l in out.splitlines() if l.startswith('ENTRY ')]
    rows = O.hit_table_rows(data)
    assert len(entries) == sum(len(v) for v in rows.values())
    for _, menu, item, *numbers in entries:
        assert all(abs(float(a) - b) < 1e-3 for a, b in zip(numbers, rows[menu][item])), (menu, item)
    header = b'lc-online-hits/1\n'
    row = b'lc_online host 34.4 253.2 247.2 277.8\n'
    variants = [data, header + row, b'\xef\xbb\xbf' + data, data.replace(b'\n', b'\r\n'), data + data.split(b'\n')[1] + b'\n',
                header + row[:-1], header + b'\n' + row,
                header + b'lc_online ho-st 1 2 3 4\n', header + b'lc_online host 1e2 2 3 4\n', header + b'lc_online host 3 2 3 4\n',
                header + b'lc_online host 1 4 3 4\n',
                header + b'lc_online host 4096 0 4097 1\n', header + b'lc_online host -4096 -4096 4096 4096\n',
                header + b'lc_online host .5 -.5 5. 1\n',
                header + row[:-1] + b'7' * 300 + b'\n', header + b'a' * 100 + b' host 1 2 3 4\n', header + b'a' * 64 + b' host 1 2 3 4\n',
                header + b'a' * 63 + b' host 1 2 3 4\n',
                header + b'lc_online  host 1 2 3 4\n', header + b'lc_online host 1 2 3 4 \n', header, b'',
                header + b''.join(b'm i%d 1 2 3 4\n' % i for i in range(O.HITS_MAX_ENTRIES)),
                header + b''.join(b'm i%d 1 2 3 4\n' % i for i in range(O.HITS_MAX_ENTRIES + 1))]
    for n, blob in enumerate(variants):
        code, out = run(blob, 'variant%d.txt' % n)
        assert (code == 0) == (O.hit_table_problems(blob) == []), (n, code, out[:200], O.hit_table_problems(blob)[:3])


def _built_output():
    import os
    import pathlib
    import unittest
    for candidate in (os.environ.get('XML1_BUILT_OUT'), r'D:\Projects\xml1-port\build\_candidate_060q'):
        if candidate and (pathlib.Path(candidate) / 'UI/menus/lc_online.XMLB').exists():
            dll=pathlib.Path(candidate)/'dinput.dll'
            if O.BROWSE_ROWS>5 and (not dll.is_file() or O.engine_scene_anchors(dll.read_bytes())==175):
                continue  # This owned-output gate requires a build made with the expanded capability.
            return pathlib.Path(candidate)
    raise unittest.SkipTest('no compatible built online-menus output (set XML1_BUILT_OUT; seven rows require menu-anchors/512)')


def test_hit_table_matches_the_focus_bars_as_built():
    """The table against the BUILT scenes (not focus_placement again): every item's focus model, read from the built output
    (its vertices) and placed at its anchor's transform in the built scene IGB, is the table's row - left, bottom and top
    exactly, the right edge exactly or by the model's lean (FOCUS_LEAN: a wide solid bar leans right as it rises, so its top
    edge sits 4 view units right of the table's bottom-edge rectangle); and the table lists exactly the items that draw one."""
    from xml1build import common as C
    out = _built_output()
    screens = _hit_screens()
    data = O.hit_table(screens)

    def model(resource):
        path = out / (resource + '.IGB')
        return path.read_bytes() if path.exists() else None

    read = (lambda n: C.decode_xmlb((out / ('UI/menus/' + n + '.XMLB')).read_bytes()),
            lambda igb: (out / ('UI/menus/' + igb + '.IGB')).read_bytes(), model)
    assert O.hit_scene_problems(data, list(screens), *read) == []
    # the check bites: a moved row, a row for an item with no bar, a missing row and a too-wide row are all named
    lines = data.decode('ascii').split('\n')
    moved = [l.replace('lc_online code 34.4 222 247.2 246.6', 'lc_online code 34.4 223 247.2 246.6') for l in lines]
    assert moved != lines
    assert any('lc_online: code' in p for p in O.hit_scene_problems('\n'.join(moved).encode('ascii'), list(screens), *read))
    assert any('no focus model' in p for p in O.hit_scene_problems(data + b'lc_online ghost 1 2 3 4 0\n', list(screens), *read))
    dropped = [l for l in lines if not l.startswith('lc_online browse ')]
    assert any('draws a focus bar but the table has no row' in p for p in O.hit_scene_problems('\n'.join(dropped).encode('ascii'), list(screens), *read))
    wide = [l.replace('lc_online code 34.4 222 247.2 246.6', 'lc_online code 34.4 222 255 246.6') for l in lines]
    assert any('lc_online: code' in p for p in O.hit_scene_problems('\n'.join(wide).encode('ascii'), list(screens), *read))
    assert O.hit_table_rows(data)['lc_online']['code'] == (34.4, 222.0, 247.2, 246.6) and O.FOCUS_LEAN == 4


def test_060s_slanted_right_edge_is_described_and_legacy_table_exposes_the_gap():
    """060s g5 log: pixel 624,222 -> view 247.73,265.33, outside v1 right=247.2 but on the drawn amber bar."""
    screens=_hit_screens()
    data=O.hit_table(screens)
    fields=next(line.split() for line in data.decode('ascii').splitlines()[1:] if line.startswith('lc_online host '))
    l,b,r,t,lean=map(float,fields[2:])
    assert lean==4
    def inside(x,y):
        shift=lean*(y-b)/(t-b)
        return b<y<=t and l+shift<=x<r+shift
    assert not l<=247.73<r and inside(247.73,265.33)
    assert inside(249.87,276.53)  # actual top-right of the row, near pixel 628,201
    assert not inside(277.60,276.53)  # live probe 680,201 picked the separate YOU-card triangle
    assert not inside(l, t) and inside(l+lean,t)  # the shear is applied to both ends
    # The builder's built-model check must reject the old rectangle even though its bounds used to pass.
    from xml1build import common as C
    out=_built_output()
    read=(lambda n:C.decode_xmlb((out/('UI/menus/'+n+'.XMLB')).read_bytes()),lambda n:(out/('UI/menus/'+n+'.IGB')).read_bytes(),lambda n:(out/(n+'.IGB')).read_bytes())
    legacy=b'lc-online-hits/1\n'+b'\n'.join(b' '.join(line.split()[:6]) for line in data.splitlines()[1:])+b'\n'
    assert any('lc_online: host' in problem for problem in O.hit_scene_problems(legacy,list(screens),*read))
    for extra in (b'65',b'-65',b'NaN',b'1e2'):
        assert O.hit_table_problems(b'lc-online-hits/2\nx y 1 2 3 4 '+extra+b'\n')


def test_060s_hostleft_actions_form_a_closed_native_navigation_ring():
    screen=O.runtime_layout('lc_online')
    tree=O.menu_tree(screen)
    for name,other in [('lc_hostleft_again','lc_hostleft_back'),('lc_hostleft_back','lc_hostleft_again')]:
        item=tree.find("item[@name='%s']"%name)
        assert item.get('enabled')=='false' and item.get('neverfocus')=='false'
        assert all(item.get(direction)==other for direction in ('left','right','up','down'))

def test_host_visibility_pair_draws_in_front_of_its_focus_bar():
    screen=O.runtime_layout('lc_host')
    by={e['name']:e for e in screen['items']}
    assert by['lc_host_private']['plane']==by['lc_host_public']['plane']==-170
    assert by['visibility'].get('plane',-150)==-150  # the focus bar's plane: -170 is nearer the camera


def test_focus_models_draw_exactly_one_alpha_blended_layer():
    """060q live: dialog.igb's three layers - an opaque 144-vertex frame (no blend state) and an additive 12-vertex inset
    beside the alpha quad - drew the picture's transparent texels black (the black box behind "1 of N ready.", the outline
    bar to the YOUR ROOM badge, the light frame round the 4:3 field) and a lighter inner rectangle on every amber bar."""
    import unittest
    from pathlib import Path
    from PIL import Image
    src=Path('D:/Projects/xml1-port/xml1_loose/ui/hud/dialog.igb')
    if not src.is_file(): raise unittest.SkipTest('owned dialog.igb not available on this machine')
    source=src.read_bytes()
    picture=Image.new('RGBA',(64,32));picture.paste((255,255,255,255),(0,0,8,8))
    for rect,outline,pic in (((0,-13.6,56,0),True,picture),((0,-20,177,0),False,None),(O.BACKDROP_RECT,True,picture),
                             (O.FIELD_RECT,True,O.field_picture())):
        layers=O.panel_layers(O.focus_model(source,rect,outline,pic))
        drawn=[l for l in layers if not l[3]]
        assert len(layers)==3 and len(drawn)==1 and drawn[0][0]==4 and drawn[0][1] and drawn[0][2]==(4,5)
        l,b,r,t=drawn[0][4]
        lean=0 if outline or rect[2]-rect[0]<50 else 4
        assert all(abs(u-v)<1e-4 for u,v in zip((l,b,t,r),(rect[0],rect[1],rect[3],rect[2]+lean))),(rect,drawn[0][4])
    # the unpatched source really is three drawn layers: opaque, additive and alpha
    from xml1build import igb_file as G, menu_conversion as M
    raw=O._layer_walk(G.IgbFile(M.fit_flat_panel(source,(0,-13.6,56,0),border=1,opaque=True)[0]))
    assert sorted((s,f) for _,s,f in raw)==sorted([(False,None),(True,(4,1)),(True,(4,5))])


def test_footer_prompt_focus_bars_never_cover_a_neighbouring_prompt():
    """060q live (failure 11): Browse's focused Refresh bar ran over "[Enter] Join" and "[Esc] Back" - the ordinary row's
    12-unit bar ends on prompts 3-5 layout units apart. Every footer prompt's drawn bar stays clear of the next prompt's."""
    for name,screen in _built_screens().items():
        rows=[]
        for e in screen['items']:
            if not (e['intent'] and (e['enabled'] or screen.get('runtime'))) or e['rect'][1]<O.FOOTER_TOP: continue
            _,owner,_,_,(l,b,r,t)=O.focus_placement(screen,e);ax,_,_=O._anchor(owner)
            rows.append((ax+l,ax+r,e['name'],e['rect']))
        rows.sort()
        for (l1,r1,n1,box1),(l2,r2,n2,box2) in zip(rows,rows[1:]):
            assert r1<l2,(name,n1,n2)
            assert r1<box2[0]*.8 and l2>(box1[0]+box1[2])*.8,(name,n1,n2)   # never over the other prompt's text


def test_party_field_paints_no_amber_action_under_a_focusable_item():
    """060q live (failure 8): INVITE was painted amber in the static field (plus its focus tick), so the rail's focused PARTY
    and INVITE showed two amber bars at once. Amber under an action comes only from its focus model now."""
    from xml1build import online_party as PT
    screen=PT.party_layout('host')
    actions=[e.get('hit_rect') or e['rect'] for e in screen['items'] if e['intent']]
    def meets(a,b): return a[0]<b[0]+b[2] and b[0]<a[0]+a[2] and a[1]<b[1]+b[3] and b[1]<a[1]+a[3]
    for q in screen['shapes']:
        if q['color']==5 and q['kind'] in ('bar','slash','rect'):
            assert not any(meets(q['rect'],a) for a in actions),q
    by={e['name']:e for e in screen['items']}
    assert by['lc_party_invite']['color']==4 and by['lc_party_invite_hint']['color']==3


def _panel_graph(layers):
    """A synthetic flat panel in the owned dialog.igb's shape (all numbers invented): igSceneInfo -> root igAttrSet -> one
    igAttrSet per layer (optional blend state / function) -> igGeometry -> igGeometryAttr1_5 -> igVertexArray1_1.
    layers = [(vertex count, blend enabled or None, (src, dst) or None)]."""
    import struct
    from test_main_appearance import fixture
    lst = [(2, 'i'), (3, 'i'), (4, 'b')]
    schemas = [('igDataList', None, []), ('igNodeList', 'igDataList', lst), ('igAttrList', 'igDataList', lst),
               ('igSceneInfo', None, [(5, 'r')]), ('igAttrSet', None, [(7, 'r'), (8, 'r')]), ('igGeometry', None, [(7, 'r'), (8, 'r')]),
               ('igBlendStateAttr', None, [(4, 'i')]), ('igBlendFunctionAttr', None, [(4, 'i'), (5, 'i')]),
               ('igGeometryAttr1_5', None, [(4, 'r')]), ('igVertexArray1_1', None, [(2, 'b'), (3, 'i')])]
    objects, blocks = [], []
    def obj(name, values): objects.append((name, values)); return len(objects) - 1
    pending = []   # (object index, slot, block index) patched after the object count is known
    def block(data): blocks.append(data); return len(blocks) - 1
    def data_list(name, refs):
        b = block(struct.pack('<' + 'i' * len(refs), *refs)); i = obj(name, {2: len(refs), 3: len(refs), 4: 0}); pending.append((i, 4, b)); return i
    children = []
    for n, state, func in layers:
        pos = block(struct.pack('<' + 'f' * (3 * n), *[float(k) for k in range(3 * n)]))
        comp = block(b'')   # replaced below: the component ref list (positions first)
        va = obj('igVertexArray1_1', {2: 0, 3: n}); pending.append((va, 2, comp)); blocks[comp] = ('comp', pos)
        ga = obj('igGeometryAttr1_5', {4: va})
        geo = obj('igGeometry', {7: data_list('igNodeList', []), 8: data_list('igAttrList', [ga])})
        attrs = []
        if state is not None: attrs.append(obj('igBlendStateAttr', {4: int(state)}))
        if func is not None: attrs.append(obj('igBlendFunctionAttr', {4: func[0], 5: func[1]}))
        children.append(obj('igAttrSet', {7: data_list('igNodeList', [geo]), 8: data_list('igAttrList', attrs)}))
    root = obj('igAttrSet', {7: data_list('igNodeList', children), 8: data_list('igAttrList', [])})
    obj('igSceneInfo', {5: root})
    base = len(objects)
    blocks = [struct.pack('<i', base + b[1]) if isinstance(b, tuple) else b for b in blocks]
    for i, slot, b in pending: objects[i][1][slot] = base + b
    return fixture(schemas, objects, tuple(blocks))


def test_blended_layer_keeps_the_alpha_quad_and_refuses_any_other_panel():
    """Fix H: the dialog.igb shape (opaque 144-vertex frame, additive 12-vertex inset, one SRC_ALPHA / INV_SRC_ALPHA quad) gives
    the quad; a panel with no such quad, two of them, or an alpha layer that is not a quad is refused, never guessed."""
    from xml1build import igb_file as G
    dialog = [(144, None, None), (12, True, (4, 1)), (4, True, (4, 5))]
    g = G.IgbFile(_panel_graph(dialog))
    keep = O.blended_layer(g)
    assert g.obj(keep).get(3) == 4
    walk = O._layer_walk(g)
    assert sorted((s, f) for _, s, f in walk) == sorted([(False, None), (True, (4, 1)), (True, (4, 5))])
    assert [l[0] for l in O.panel_layers(_panel_graph(dialog))] == [144, 12, 4]
    for bad in ([(144, None, None), (12, True, (4, 1))],                     # no alpha quad
                [(4, True, (4, 5)), (4, True, (4, 5))],                       # two alpha quads
                [(144, None, None), (12, True, (4, 5))],                      # the alpha layer is not a quad
                [(4, False, (4, 5))]):                                        # blend state off
        raises(G.IgbError, lambda bad=bad: O.blended_layer(G.IgbFile(_panel_graph(bad))))


def test_validator_scene_capacity_follows_the_companion_dll():
    # 060s integration: V-online called scene_problems with the retail default (175) and refused the seven-row Browse
    # (214 anchors) that output_problems / authoring accept with the DLL's menu-anchors/512 probe.
    import ast, inspect
    from xml1build import validate_frontend as VF
    calls = [n for n in ast.walk(ast.parse(inspect.getsource(VF))) if isinstance(n, ast.Call)
             and getattr(n.func, 'attr', None) == 'scene_problems']
    assert calls and all(any(k.arg == 'anchor_capacity' for k in c.keywords) for c in calls)


def test_060t_hostleft_has_only_the_focused_action_amber():
    screen=O.runtime_layout('lc_online')
    by={e['name']:e for e in screen['items']}
    actions=[by[k]['hit_rect'] for k in ('lc_hostleft_again','lc_hostleft_back')]
    panel=by['lc_hub_host_left']
    x,y,_,_=panel['rect']
    for part in panel['parts']:
        if part.get('color')!=5 or part.get('kind') not in ('bar','rect'): continue
        a,b,c,d=part['rect']; box=(x+a,y+b,c,d)
        assert not any(box[0]<q[0]+q[2] and q[0]<box[0]+box[2] and box[1]<q[1]+q[3] and q[1]<box[1]+box[3] for q in actions)
    assert by['lc_hostleft_again']['color']==4


def test_060t_footer_polygons_never_steal_the_select_edge():
    for name,screen in _built_screens().items():
        entries={e['name']:e for e in screen['items']}
        bars=[]
        for key,l,b,r,t in O.hit_rows(screen):
            if entries[key]['rect'][1]>=O.FOOTER_TOP:
                bars.append((key,l,b,r,t,O.hit_lean(screen,key)))
        for a in bars:
            for z in bars:
                if a[0]>=z[0]:continue
                low,high=max(a[2],z[2]),min(a[4],z[4])
                for step in range(1,101):
                    y=low+(high-low)*step/101
                    al,ar=a[1]+a[5]*(y-a[2])/(a[4]-a[2]),a[3]+a[5]*(y-a[2])/(a[4]-a[2])
                    zl,zr=z[1]+z[5]*(y-z[2])/(z[4]-z[2]),z[3]+z[5]*(y-z[2])/(z[4]-z[2])
                    assert ar<=zl or zr<=al,(name,a[0],z[0],y)


def test_060t_browse_diagnostic_has_room_for_the_redacted_error():
    screen=O.runtime_layout('lc_browse');by={e['name']:e for e in screen['items']}
    diag=by['broker_error']['rect'];prev=by['scroll_up']['rect']
    assert diag[2]>=150  # the longest allowlisted list error at the label font, in its own line
    assert diag[1]+diag[3]<=prev[1] or prev[1]+prev[3]<=diag[1]


def test_060t_every_control_including_retry_fits_retail_focus_events():
    # 5af147 refuses the 76th global focus record (52 bytes at 8a72b0).
    for name,screen in _built_screens().items():
        tree=O.menu_tree(screen)
        events=tree.findall('.//onfocus')
        assert len(events)<=75,(name,len(events))
        for item in tree.findall('item'):
            if item.get('usecmd'):
                assert any(e.get('type')=='focus' for e in item.findall('onfocus')), (name,item.get('name'))


def test_060u_browse_header_has_space_for_the_visible_fresh_and_stale_count():
    screen=O.runtime_layout('lc_browse');by={e['name']:e for e in screen['items']}
    # One DATA field owns the whole count, including singular wording. The old
    # PUBLIC GAMES - N arrangement only allowed 60 units and never showed it.
    assert not by['list_header']['text']
    count=by['list_count'];assert count['data'] and count['rect'][2]>=132
    stale=by['lc_broker_stale']['rect']
    assert count['rect'][0]+count['rect'][2]<=stale[0]
    tree=O.menu_tree(screen)
    assert tree.find("item[@name='list_count']").get('clamp')=='true'


def test_relay_refusal_has_specific_authored_notice():
    assert 'TURN' in O.NOTICE_TEXT['lc_notice_relay']
    for name in ('lc_code', 'lc_browse'):
        assert O.menu_tree(O.runtime_layout(name)).find("item[@name='lc_notice_relay']") is not None
