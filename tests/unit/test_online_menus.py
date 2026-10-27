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
    assert state.selected == len(state.rooms)-1 and state.offset == len(state.rooms)-7
    for _ in range(40): state.dispatch('scroll:-1')
    assert (state.selected, state.offset) == (0, 0)
    for i in range(len(state.rooms)):
        state.selected = i; state.rebound()
        screen = O.layout('lc_browse', state)
        assert not O.layout_problems(screen)
        assert len([e for e in screen['items'] if e['name'].startswith('room_')]) == 49
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
    assert len(result[0])==71 and len(result[1])==28
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
    assert len(state.rooms)==50 and state.selected==49 and state.offset==43


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
    assert O.reserved_budget(c,s)==(4,4)
    s.remove(next(e for e in s if e.get('name')=='lc_o_title'))
    assert O.reserved_budget(c,s)==(8,4)


def anchor_fixture(broken=False):
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
    state.dispatch('page:1'); assert (state.selected,state.offset)==(2,2)
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
    assert ''.join(keys)==O.ALPHABET+'<'
    assert all(e['text']=='W' for e in screen['items'] if e['name'].startswith('cell'))


def test_all_authored_background_previews_render_without_font_inputs():
    for name in O.MENUS:
        picture=O.render(O.layout(name),size=(640,480),text=False)
        assert picture.size==(640,480)
