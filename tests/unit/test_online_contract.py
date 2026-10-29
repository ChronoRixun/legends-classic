"""DLL handoff regressions, using invented menu trees and capability bytes."""
import copy
import xml.etree.ElementTree as ET
from xml1build import online_menus as O, fix_ini as FI
from test_main_appearance import raises


def test_exact_input_commands_and_localized_bindings():
    for name in O.MENUS:
        screen = O.runtime_layout(name)
        tree = O.menu_tree(screen)
        assert tree.get('menu_cancel') == 'runscript lcOnlineIntent(6)'
        items = {e.get('name'): e for e in tree.findall('item')}
        assert items['lc_inline_error'].get('hide') == 'true'
        assert not O.runtime_problems(tree, screen)
        bad = copy.deepcopy(tree)
        next(e for e in bad if e.get('usecmd')).set('usecmd', 'runscript lcOnlineIntent(15)')
        assert O.runtime_problems(bad, screen)
    tree = O.menu_tree(O.runtime_layout('lc_code'))
    items = {e.get('name'): e for e in tree.findall('item')}
    assert [items['key_'+str(i)].get('usecmd') for i in range(31)] == [O.command(32+i) for i in range(31)]
    assert items['key_31'].get('usecmd') == O.command(11)
    assert items['cell0'].get('gamevar') is None
    assert items['lc_notice_recent_save'].get('hide') == 'true'
    for menu,expect in {
        'lc_online':{'host':2,'code':3,'browse':4,'other':5,'change_name':9,'rejoin':14},
        'lc_code':{'paste':10,'clear':12,'done':13},
    }.items():
        nodes={e.get('name'):e for e in O.menu_tree(O.runtime_layout(menu))}
        for key,number in expect.items():assert nodes[key].get('usecmd')==f'runscript lcOnlineIntent({number})'
    hub={e.get('name'):e for e in O.menu_tree(O.runtime_layout('lc_online'))}
    assert hub['rejoin'].get('enabled')=='false'
    assert hub['lc_recent_empty'].get('hide')=='true'


def test_capability_refusal_and_complete_resource_gate():
    data = b'\0'.join(O.DLL_PROBES)
    assert not O.capability_problems(data)
    for token in O.DLL_PROBES:
        assert O.capability_problems(data.replace(token, b'!'))
    raises(ValueError, lambda: O.command(15))
    raises(ValueError, lambda: O.command(1))
    raises(ValueError, lambda: O.command(2.0))
    keys = {'Online': {'Menus': '1'}, 'Game': {'LegendsClassicFonts': '1'}, 'Limits': {'ScriptFunctions': '320'}}
    raises(FI.FixTooOld, lambda: FI.check_online_dll(data, keys))


def native(role):
    root = ET.Element('MENU', name=role, type=role.upper()+'_MENU', igb='invented', waitmode='keep')
    for name in ('data_name', 'desctext1', 'desctext2', 'desctext3', 'desctext4', 'desctext5',
                 'text_playername1', 'text_readycheck1', 'text_leaveroom',
                 *(['text_startgame', 'text_kickplayer'] if role == 'host' else ['text_readygame'])):
        ET.SubElement(root, 'item', name=name, type='MENU_ITEM_LISTBOX' if name.endswith('1') and name.startswith('text_') else 'MENU_ITEM_TEXT', callback='keep',style='STYLE_MENU_WHITE_MED')
    return root


def test_native_lobby_retains_actions_lists_callbacks_and_mutation_guards():
    for role in ('host', 'join'):
        original = native(role)
        screen = O.lobby_layout(role)
        tree = O.lobby_tree(original, screen)
        assert not O.lobby_problems(tree, original, screen)
        assert tree.get('type') == original.get('type') and tree.get('waitmode') == 'keep'
        items = {e.get('name'): e for e in tree.findall('item')}
        assert all(items[e.get('name')].get('callback') == 'keep' for e in original)
        for name in ('text_playername1', 'text_readycheck1'):
            assert items[name].get('type') == 'MENU_ITEM_LISTBOX'
            assert items[name].get('style') == 'STYLE_MENU_WHITE_MED'
            bad = copy.deepcopy(tree); bad.remove(next(e for e in bad if e.get('name') == name))
            assert O.lobby_problems(bad, original, screen)
        for name in ('text_startgame', 'text_kickplayer', 'text_readygame', 'text_leaveroom'):
            if name in items: assert not items[name].get('usecmd')
        assert items['lc_copy_code'].get('usecmd') == O.command(16)
        assert items['lc_leave_yes'].get('usecmd') == O.command(17)
        assert items['lc_leave_cancel'].get('usecmd') == O.command(8)
        assert 'lc_party' not in ET.tostring(tree).decode()
        assert not O.layout_problems(screen)
        required={'lc_lobby_v1','lc_self_name','lc_self_initial','lc_self_hosting','lc_self_joined',
                  'lc_self_ready','lc_room_code','lc_copy_code','lc_code_copied','lc_ready_count','lc_member_count',
                  'lc_waiting_name','lc_ready_waiting','lc_ready_all','lc_ready_solo','lc_leave_confirm',
                  'lc_lobby_error','lc_leave_yes','lc_leave_cancel','lc_lobby_dismiss','lc_guest_unready','lc_guest_leave'}
        required|={f'lc_p{n}_{suffix}' for n in range(1,5) for suffix in (
            'name','slot','ping','card','ready','not_ready','host','hero_fallback','you','ms','measuring',
            'same_build','checking_build','selected','empty','empty_title','empty_help','empty_plus')}
        assert required<=items.keys()
        for key in required:
            bad=copy.deepcopy(tree);bad.remove(next(e for e in bad if e.get('name')==key))
            assert O.lobby_problems(bad,original,screen)


def test_lobby_prompts_are_not_tied_to_the_native_help_animation():
    """060r live (fix K): the lobby prompts kept the native desctext items' animtext_scene="help" (the native help bar's
    fade-in, which the authored scene does not carry), so not one lobby prompt was drawn - no X Kick player / X Ready / Copy.
    Every LC-laid native item drops it (as the codex, options and pause reskins do); the Copy prompt is the keyboard form
    (the DLL rebinds it to "Y Copy code" for a pad)."""
    for role in ('host', 'join'):
        original = native(role)
        for e in original:
            if e.get('name').startswith('desctext'): e.set('animtext_scene', 'help')
            if e.get('name') == 'data_name': e.set('animtext_scene', 'name')
        screen = O.lobby_layout(role)
        laid = {e['name'] for e in screen['items']}
        tree = O.lobby_tree(original, screen)
        assert not O.lobby_problems(tree, original, screen)
        items = {e.get('name'): e for e in tree.findall('item')}
        for i in range(1, 6):
            assert items['desctext%d' % i].get('animtext_scene') is None, role
        assert all(items[n].get('animtext_scene') is None for n in laid if n in items)
        assert items['data_name'].get('animtext_scene') == 'name'  # a native item LC does not lay out keeps its own
        assert items['desctext3'].get('text', '').endswith('Ctrl+C Copy code')
        assert items['desctext2'].get('text', '').endswith('$MENU_OTHER Kick player' if role == 'host' else '$MENU_OTHER Ready / Unready')


def test_built_lobby_prompts_are_not_tied_to_the_native_help_animation():
    """The same on the BUILT lobbies (XML1_BUILT_OUT): 060r's host.XMLB / join.XMLB fail this (desctext1..5 animtext_scene="help")."""
    import os
    import pathlib
    import pytest
    from xml1build import common as C
    out = os.environ.get('XML1_BUILT_OUT')
    if not out or not (pathlib.Path(out) / 'UI/menus/host.XMLB').exists():
        pytest.skip('no built output (set XML1_BUILT_OUT)')
    for role in ('host', 'join'):
        tree = C.decode_xmlb((pathlib.Path(out) / ('UI/menus/%s.XMLB' % role)).read_bytes())
        items = {e.get('name'): e for e in tree.findall('item')}
        for i in range(1, 6):
            assert items['desctext%d' % i].get('animtext_scene') is None, (role, i)


def test_combined_option_off_and_capacity_are_not_inferred_from_files():
    from types import SimpleNamespace
    from xml1build import script_functions as SF
    assert not O.enabled(SimpleNamespace())
    assert not O.enabled(SimpleNamespace(opt=lambda key,default:default))
    assert O.enabled(SimpleNamespace(opt=lambda key,default:'on'))
    assert SF.ONLINE_API['lcOnlineIntent']['ret']=='n'
    assert SF.ONLINE_API['lcOnlineIntent']['args']=='i'
    keys={'Online':{'Menus':'1'},'Game':{'LegendsClassicFonts':'1'}}
    FI.check_online_dll(b'\0'.join(O.DLL_PROBES),keys)
    for capacity in ('0','320','4097','bad'):
        raises(FI.FixTooOld,lambda:FI.check_online_dll(b'\0'.join(O.DLL_PROBES),{**keys,'Limits':{'ScriptFunctions':capacity}}))
    FI.check_online_dll(b'',{'Online':{'Menus':'0'}})


def test_lobby_action_mouse_bounds_follow_full_approved_bars():
    """The mouse reaches the whole approved bar through the hit table (fix E); the label keeps its own text box. 060q live:
    with the bar as the layout box CText drew START GAME / KICK PLAYER / LEAVE at the bar's left edge (the S clipped)."""
    for role in ('host','join'):
        screen=O.lobby_layout(role)
        placements=O.scene_layout(screen)
        bars={r[0]:r[1:] for r in O.hit_rows(screen)}
        for item in screen['items']:
            if item.get('hit_rect'):
                (x,_,z),(l,b,r,t)=placements[item['name']]
                rx,ry,rw,rh=item['rect']
                assert abs(x+l-rx*.8)<1e-6 and abs(x+r-(rx+rw)*.8)<1e-6
                assert abs(z+t-(480-ry)*.8)<1e-6 and abs(z+b-(480-ry-rh)*.8)<1e-6
                if item['name'] in bars:
                    L,B,R,T=bars[item['name']];hx,hy,hw,hh=item['hit_rect']
                    assert L<=hx*.8+1e-6 and R>=(hx+hw)*.8-1e-6 and T>=(480-hy)*.8-1e-6 and B<=(480-hy-hh)*.8+0.5


def test_card_names_use_upright_bold_and_measured_approved_scale():
    screen=O.lobby_layout('host')
    name=next(e for e in screen['items'] if e['name']=='lc_p1_name')
    role,scale,style=O.font_binding(name)
    assert role=='row' and abs(scale-18*.8/64)<1e-8
    assert style=='lc_o_card_name'


def test_installer_refuses_old_fix_warning_path_and_leaves_ini_untouched():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as folder:
        out=Path(folder)
        ini=out/'xml2-fix.ini';ini.write_bytes(b'[Online]\nMenus=0\n')
        keys={'Online':{'Menus':'1'},'Game':{'LegendsClassicFonts':'1'}}
        raises(FI.FixTooOld,lambda:FI.write_port_keys(out,keys,old_fix_ok=True))
        assert ini.read_bytes()==b'[Online]\nMenus=0\n'
        assert not (out/'Data/lc_online_menus.cap').exists()
        drop=FI.dropped_keys({})
        assert 'Menus' in drop['Online'] and 'LegendsClassicFonts' in drop['Game']


def test_optional_lobby_scene_children_are_owned_by_the_hidden_variant():
    screen=O.lobby_layout('host')
    items={e['name']:e for e in screen['items']}
    for n in range(1,5):
        for suffix in ('card','empty'):
            e=items[f'lc_p{n}_{suffix}']
            assert e.get('hidden') and e.get('parts')
            assert not e['text']
    for name in ('lc_leave_confirm','lc_lobby_error','lc_code_copied'):
        assert items[name]['parts'][0]['kind']=='panel'
    for name in ('lc_guest_leave','lc_guest_unready'):
        assert '$MENU_BACK' in items[name]['text'] and not items[name]['intent']


def test_build_option_roundtrip_and_on_to_off_invalidates_frontend():
    import json
    import tempfile
    from pathlib import Path
    import build_xml1
    from xml1build import common as C
    from xml1builder.cli import make_parser
    assert make_parser().parse_args(['build']).online_menus=='off'
    assert make_parser().parse_args(['build','--online-menus','on']).online_menus=='on'
    with tempfile.TemporaryDirectory() as folder:
        out=Path(folder);(out/'_build').mkdir()
        (out/'_build/report.json').write_text(json.dumps({'build':{'online_menus':'on'}}))
        assert C.args_for_out(out).online_menus=='on'
        args=build_xml1.parse_args(['--out',str(out),'--online-menus','off'])
        assert 'frontend' in build_xml1.plan_content_opts(out,args,[])
    raises(SystemExit,lambda:build_xml1.parse_args(['--out','synthetic','--frontend','xml2','--online-menus','on']))


def test_runtime_buttons_keep_focus_resources_before_the_dll_enables_them():
    for name,key in (('lc_online','rejoin'),('lc_code','done'),('host','lc_leave_cancel'),('host','lc_copy_code')):
        screen=O.runtime_layout(name) if name in O.MENUS else O.lobby_layout(name)
        tree=O.menu_tree(screen)
        item=next(e for e in tree if e.get('name')==key)
        assert item.get('enabled')=='false'
        focus=item.find('onfocus')
        assert focus is not None and focus.get('model').startswith('ui/models/lc_o_focus_')
        assert focus.get('item') in O.scene_layout(screen)
        assert focus.get('item')==(O.focus_target(screen,next(e for e in screen['items'] if e['name']==key))[0])  # lobbies: one per plane (060q)


def test_baked_start_bar_does_not_freeze_an_invented_solo_gate():
    for count in (1,4):
        screen=O.lobby_layout('host',members=count)
        start=next(e for e in screen['shapes'] if e['rect']==(43,391,177,31))
        assert not start.get('dim')


def test_runtime_device_glyphs_fit_the_same_keyboard_pad_and_mouse_bounds():
    from xml1build import online_fonts as F
    metrics=F.metrics()
    mapping={'$MENU_ACCEPT':(0x80,0x90),'$MENU_BACK':(0x81,0x91),
             '$MENU_NEXT':(0x83,0xd5),'$MENU_OTHER':(0x82,0xc2),'$MENU_OK':(0x84,0x90)}
    screens=[*(O.runtime_layout(n) for n in O.MENUS),*(O.lobby_layout(n) for n in O.LOBBIES)]
    for screen in screens:
        for item in screen['items']:
            if '$MENU_' not in item['text']:continue
            role,scale,_=O.font_binding(item)
            for device in (0,1):
                value=item['text']
                for token,codes in mapping.items():value=value.replace(token,chr(codes[device]))
                width=sum(float(metrics['lc_'+role][ord(c)]['horizadvance']) for c in value)*scale
                assert width<=item['rect'][2]*.8,(screen['name'],item['name'],device,width)


def test_picker_decoration_owns_its_backdrop_and_retained_arrow_geometry():
    original=native('host')
    for key in ('players_up_arrow','players_down_arrow'):
        ET.SubElement(original,'item',name=key,type='MENU_ITEM_MODEL',neverfocus='true')
    screen=O.lobby_layout('host',members=4,fixture=True,picker=True)
    tree=O.lobby_tree(original,screen)
    placements=O.native_lobby_layouts(tree,screen)
    for key in ('players_up_arrow','players_down_arrow'):
        (x,y,z),(l,b,r,t)=placements[key]
        assert 43*.8<=x+l<x+r<=597*.8
        assert (480-354)*.8<=z+b<z+t<=(480-189)*.8
    items={e['name']:e for e in screen['items']}
    for n in range(1,5):
        selected=items[f'lc_p{n}_selected']
        assert any(p['kind']=='panel' for p in selected['parts'])
        assert selected['plane']+40<items['lc_p1_name'].get('plane',-150)
        assert items['text_playername1']['plane']<selected['plane']+40


def test_off_does_not_require_optional_palette_slots_or_owned_online_inputs():
    class Context:
        def opt(self,key,default):return 'off'
        def read_out_xmlb(self,rel):raise AssertionError('OFF read optional resources')
    assert O.write(Context())=={'enabled':False,'production_entry':'openmenu online'}


def test_supported_code_tool_instructions_are_not_ellipsized():
    from xml1build import online_fonts as F
    screen=O.runtime_layout('lc_code')
    bounded=O.bound_layout(screen,F.metrics())
    instructions={e['name']:e['text'] for e in bounded['items']}
    assert instructions['desctext3']=='Ctrl+V Paste'
    assert instructions['desctext4']=='Shift+Del Clear'


def test_code_background_does_not_freeze_edit_cursor_or_disabled_done():
    screen=O.runtime_layout('lc_code')
    cells=[s for s in screen['shapes'] if s['rect'][1]==130 and s['rect'][3]==54]
    assert len(cells)==8 and all(s.get('outline')==3 for s in cells)
    assert not any(s['color']==5 and s['rect'][1] in (130,172) for s in screen['shapes'])
    done=next(s for s in screen['shapes'] if s['rect']==(483,307,104,46))
    assert not done.get('dim')


def test_inline_panel_and_buttons_occlude_summary_on_safe_separate_planes():
    screen=O.lobby_layout('host');items={e['name']:e for e in screen['items']}
    for key in ('lc_leave_confirm','lc_lobby_error','lc_code_copied'):
        panel=items[key]
        assert panel['plane']+40<items['lc_ready_count'].get('plane',-150)
    for key in ('lc_leave_yes','lc_leave_cancel','lc_lobby_dismiss'):
        button=items[key]
        assert button['plane']<items['lc_leave_confirm']['plane']+40
        (l,b,r,t),_=O.focus_spec(screen,button);x,y,_,_=button['rect']
        assert x+l/.8>=43 and x+r/.8<=597
        assert y-t/.8>=356 and y-b/.8<=385


def test_picker_backdrop_covers_complete_card_data_bounds():
    screen=O.lobby_layout('host')
    chosen=next(e for e in screen['items'] if e['name']=='lc_p1_selected')
    panel=next(p for p in chosen['parts'] if p['kind']=='panel')
    x,y,_,_=chosen['rect'];px,py,pw,ph=panel['rect'];left,top=x+px,y+py
    for e in screen['items']:
        if e.get('data') and e['name'].startswith('lc_p'):
            ex,ey,ew,eh=e['rect']
            if e['name'].endswith('_slot'):continue
            assert left<=ex and ex+ew<=left+pw
            assert top<=ey and ey+eh<=top+ph


def test_guest_fixture_readiness_agrees_with_self_card_actions_and_summary():
    for ready in (False,True):
        items={e['name']:e for e in O.lobby_layout('join',members=4,ready=ready,fixture=True)['items']}
        assert items['lc_p2_ready']['hidden'] is not ready
        assert items['lc_p2_not_ready']['hidden'] is ready
        assert items['lc_guest_unready']['hidden'] is not ready
        assert items['lc_guest_leave']['hidden'] is ready
        assert items['lc_ready_count']['text']==('4' if ready else '1')
        assert items['lc_waiting_name']['text']==('' if ready else 'Kitty')
    items={e['name']:e for e in O.lobby_layout('host',members=3,fixture=True)['items']}
    assert items['lc_ready_count']['text']=='2' and items['lc_waiting_name']['text']=='Alex'
    for ready in (False,True):
        items={e['name']:e for e in O.lobby_layout('join',members=1,ready=ready,fixture=True)['items']}
        assert items['lc_ready_solo']['hidden'] is not ready
        assert items['lc_ready_waiting']['hidden'] is ready


def test_lobby_render_states_do_not_claim_pending_admission():
    for count in (1, 3, 4):
        for role in ('host', 'join'):
            for ready in (False, True):
                screen = O.lobby_layout(role, members=count, ready=ready, fixture=True)
                assert not O.layout_problems(screen)
                assert O.render(screen, size=(640,480), text=False).size == (640,480)
    screen = O.lobby_layout('host')
    assert 'Measuring' in str(screen) and 'Hero assigned at start' in str(screen)
    assert 'next area' in str(screen)


def test_060s_lobby_words_use_native_text_in_front_of_card_models():
    # Live 060s: the facts said HOST READY YOU while only a panel opening revealed HOST.
    # Software previews composite alpha without the retail depth test, so they missed overlapping model glyph surfaces.
    for role in ('host','join'):
        screen=O.lobby_layout(role)
        tree=O.lobby_tree(native(role),screen)
        by={e['name']:e for e in screen['items']}
        for n in range(1,5):
            for suffix in ('host','ready','not_ready','same_build','checking_build','other_build','you'):
                key=f'lc_p{n}_{suffix}'
                e=tree.find(f"item[@name='{key}']")
                assert e.get('type')=='MENU_ITEM_TEXT' and e.get('text')
                assert e.get('enabled')=='false' and e.get('neverfocus')=='true'
                assert e.get('text').startswith('~')  # explicit authored colour survives the engine's disabled style
                assert by[key]['plane'] < by[f'lc_p{n}_card'].get('plane',-150)


def test_060s_browse_refresh_has_own_bar_and_rows_are_the_main_navigation_target():
    screen=O.runtime_layout('lc_browse')
    assert screen['focus']=='prompt_refresh'
    by={e['name']:e for e in screen['items']}
    target,owner,rect,_,relative=O.focus_placement(screen,by['prompt_refresh'])
    assert target==O.SHARED_FOCUS and owner is by['prompt_refresh']
    sx,sy,sz=O.scene_layout(screen)[target][0]
    assert (sx,sy,sz)==O.SHARED_FOCUS_ORIGIN
    ax,ay,az=O._anchor(owner);assert ay==sy
    assert all(abs(got-(local+offset))<1e-3 for got,local,offset in zip(rect,relative,(ax-sx,az-sz,ax-sx,az-sz)))
    assert by['prompt_join']['down']=='room_0_0'


def test_060s_party_invite_hint_has_a_navy_focus_twin():
    from xml1build import online_party as P
    screen=P.party_layout('host')
    by={e['name']:e for e in screen['items']}
    assert by['lc_party_invite_hint']['rect']==by['lc_party_invite_hint_on']['rect']
    assert by['lc_party_invite_hint_on']['color']==0 and by['lc_party_invite_hint_on']['hidden']
