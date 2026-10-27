"""Round-5 broker bridge authoring (docs/online-menus.md): invented trees only, no game, network or desktop."""
import copy
import re
from xml1build import online_menus as O, online_fonts as F, fix_ini as FI
from test_main_appearance import raises


def tree(name):
    screen = O.runtime_layout(name)
    return screen, O.menu_tree(screen), {e.get('name'): e for e in O.menu_tree(screen).findall('item')}


def test_broker_probe_is_required_and_intents_18_to_31_are_exact_constants():
    assert b'lc-online-broker/1' in O.DLL_PROBES
    data = b'\0'.join(O.DLL_PROBES)
    assert not O.capability_problems(data)
    assert O.capability_problems(data.replace(b'lc-online-broker/1', b'lc-online-broker/0'))
    keys = {'Online': {'Menus': '1'}, 'Game': {'LegendsClassicFonts': '1'}, 'Limits': {'ScriptFunctions': '1024'}}
    FI.check_online_dll(data, keys)
    raises(FI.FixTooOld, lambda: FI.check_online_dll(data.replace(b'lc-online-broker/1', b'x'), keys))
    for number in range(18, 32):
        assert O.command(number) == f'runscript lcOnlineIntent({number})'
    for number in (0, 1, 15, 63, 64):
        raises(ValueError, lambda n=number: O.command(n))
    # the exact table of the DLL document
    assert [O.intent_number(i) for i in ('refresh', 'open-room', 'retry', 'visibility', 'page:-1', 'page:1', 'join')] == [18, 19, 20, 21, 22, 23, 31]
    assert [O.intent_number(f'select:{r}') for r in range(7)] == list(range(24, 31))
    assert O.intent_number('select:7') == 7  # unknown rows never alias a public command


def test_broker_intents_only_appear_on_their_allowed_screens_and_with_row_numbers():
    seen = {}
    for name in O.MENUS:
        _, _, items = tree(name)
        for key, e in items.items():
            m = re.fullmatch(r'runscript lcOnlineIntent\((\d+)\)', e.get('usecmd', ''))
            if m and 18 <= int(m.group(1)) <= 31: seen.setdefault(name, {})[key] = int(m.group(1))
    assert set(seen) == {'lc_host', 'lc_browse', 'lc_online', 'lc_code'}
    assert seen['lc_host'] == {'open': 19, 'prompt_open': 19, 'visibility': 21, 'retry': 20}
    assert seen['lc_online'] == {'retry': 20} and seen['lc_code'] == {'retry': 20}
    browse = seen['lc_browse']
    assert browse['prompt_refresh'] == 18 and browse['scroll_up'] == 22 and browse['scroll'] == 23 and browse['prompt_join'] == 31 and browse['retry'] == 20
    assert {browse[f'room_{r}_{c}'] for r in range(7) for c in range(7)} == set(range(24, 31))
    assert all(browse[f'room_{r}_{c}'] == 24 + r for r in range(7) for c in range(7))
    # a mutated scope or number is refused by the validator
    screen, root, items = tree('lc_host')
    bad = copy.deepcopy(root); next(e for e in bad if e.get('name') == 'open').set('usecmd', O.command(18))
    assert O.runtime_problems(bad, screen)
    bad = copy.deepcopy(root); next(e for e in bad if e.get('name') == 'open').set('usecmd', 'openmenu online')
    assert O.runtime_problems(bad, screen)
    screen, root, _ = tree('lc_browse')
    bad = copy.deepcopy(root); next(e for e in bad if e.get('name') == 'room_4_4').set('usecmd', O.command(31))
    assert O.runtime_problems(bad, screen)


def test_status_and_error_variants_exist_hidden_with_exact_localized_copy():
    for name in O.MENUS:
        screen, root, items = tree(name)
        for key in O.BROKER_SCREENS[name]:
            assert items[key].get('hide') == 'true', (name, key)
            if key == 'lc_broker_error':
                assert items[key].get('type') == 'MENU_ITEM_MODEL'
                continue
            want = O.BROKER_ROOM_COPY[name] if key == 'lc_broker_room' else O.BROKER_COPY[key]
            assert re.sub(r'^~\d\d', '', items[key].get('text')) == want
        assert not set(items) & (set(O.BROKER_VARIANTS) - set(O.BROKER_SCREENS[name]))
    # the doc's exact sentences
    assert O.BROKER_COPY['lc_broker_auth'] == 'Connecting to Online service...'
    assert O.BROKER_COPY['lc_broker_list'] == 'Finding public games...'
    assert O.BROKER_COPY['lc_broker_host'] == 'Opening your room...'
    assert O.BROKER_COPY['lc_broker_resolve'] == 'Looking up room code...'
    assert O.BROKER_COPY['lc_broker_empty'] == 'No public games right now. Host a game or go Back.'
    assert O.BROKER_COPY['lc_broker_stale'] == 'These games may be out of date. Refresh to try again.'
    assert O.BROKER_COPY['lc_broker_error'] == 'Online service could not complete the request. Retry or go Back.'
    assert 'Editing the code leaves this room' in O.BROKER_ROOM_COPY['lc_code']
    assert 'native lobby setup is the next step' in O.BROKER_ROOM_COPY['lc_host'].lower()
    assert O.BROKER_COPY['lc_broker_offline_room'].startswith('Online service unavailable. Existing connections stay open')


def test_retry_is_visible_disabled_and_diagnostic_error_is_data_only():
    for name in O.MENUS:
        screen, root, items = tree(name)
        retry = items['retry']
        assert retry.get('usecmd') == O.command(20) and retry.get('enabled') == 'false' and retry.get('hide') is None
        assert retry.get('neverfocus') == 'false'
        diag = items['broker_error']
        assert diag.get('clamp') == 'true' and diag.get('usecmd') is None and not any('gamevar' in k.lower() for k in diag.attrib)
        assert diag.get('neverfocus') == 'true'
        # retry keeps closed focus links and its own focus resource even while disabled
        assert all(retry.get(d) in items for d in ('left', 'right', 'up', 'down'))
        assert any(e.get('item') == 'retry_focus' for e in retry.findall('onfocus'))
        raw = next(e for e in screen['items'] if e['name'] == 'retry')
        hit = raw['hit_rect']
        assert hit[2] >= 56 and hit[3] >= 15 and not O.layout_problems(screen)
        assert raw['text'] == 'RETRY' and raw.get('align') is None and hit[0] <= raw['rect'][0] and raw['rect'][0] + raw['rect'][2] <= hit[0] + hit[2]  # the label is the item's own text, in front of the focus bar


def test_browse_rows_exist_for_an_empty_list_with_row_commands_and_closed_grid():
    screen, root, items = tree('lc_browse')
    for r in range(7):
        for c in range(7):
            e = items[f'room_{r}_{c}']
            assert e.get('usecmd') == O.command(24 + r) and e.get('enabled') == 'false' and e.get('clamp') == 'true'
            assert e.get('text') in ('', None) or e.get('text').startswith('~')
            assert not any('gamevar' in k.lower() for k in e.attrib)
            assert e.get('left') == f'room_{r}_{max(0, c - 1)}' and e.get('right') == f'room_{r}_{min(6, c + 1)}'
            assert e.get('up') == (f'room_{r - 1}_{c}' if r else 'prompt_refresh')
            assert e.get('down') == (f'room_{r + 1}_{c}' if r < 6 else 'scroll')
            assert any(f.get('item') == f'room_{r}_{c}_focus' for f in e.findall('onfocus'))  # mouse/focus rectangle kept while disabled
    raw = {e['name']: e for e in screen['items']}
    for r in range(7):
        rects = {raw[f'room_{r}_{c}']['rect'][1] for c in range(7)}
        assert len(rects) == 1 and not any(raw[f'room_{r}_{c}']['rect'][3] < 20 for c in range(7))
    for r in range(7):
        sel = items[f'lc_row{r}_selected']
        assert sel.get('hide') == 'true' and sel.get('type') == 'MENU_ITEM_MODEL' and sel.get('neverfocus') == 'true'
        assert raw[f'lc_row{r}_selected']['rect'] == (44, 178 + 31 * r, 552, 29)
    assert items['prompt_join'].get('enabled') == 'false' and items['prompt_refresh'].get('enabled') is None
    assert screen['focus'] == 'prompt_refresh' and items['prompt_refresh'].get('startactive') == 'true'
    for key in ('details_name', 'details'):
        assert items[key].get('clamp') == 'true'


def test_host_open_item_and_exclusive_visibility_scenes():
    screen, root, items = tree('lc_host')
    assert 'open_room' not in items and items['open'].get('usecmd') == O.command(19) and items['prompt_open'].get('usecmd') == O.command(19)
    assert items['visibility'].get('usecmd') == O.command(21) and items['visibility'].get('text') in ('', None)
    private, public = items['lc_host_private'], items['lc_host_public']
    assert private.get('hide') is None and public.get('hide') == 'true'  # exactly one at start (the DLL default is private)
    assert private.get('model') != public.get('model')
    raw = {e['name']: e for e in screen['items']}
    assert raw['lc_host_private']['rect'] == raw['lc_host_public']['rect']
    for key in ('room_name', 'preview_name', 'room_code'):
        assert items[key].get('clamp') == 'true'
    assert items['desctext1'].get('usecmd') == O.command(7)  # the generic Select prompt never opens a room
    bad = copy.deepcopy(root)
    next(e for e in bad if e.get('name') == 'lc_host_public').attrib.pop('hide')
    assert O.runtime_problems(bad, screen)


def test_production_assets_replace_the_resolving_fixture_wording():
    for name in O.MENUS:
        screen, root, items = tree(name)
        for key, e in items.items():
            assert 'fixture' not in (e.get('text') or '').lower(), (name, key)
        for e in screen['items']:
            for part in e.get('parts', []):
                assert 'fixture' not in part.get('text', '').lower()
    assert 'fixture' not in O.NOTICE_TEXT['lc_notice_resolving'].lower() and 'fixture' not in O.NOTICE_TEXT['lc_notice_fixture'].lower()


def test_all_round5_static_copy_fits_its_field_without_ellipsis():
    metrics = F.metrics()

    def width(item, text):
        role, scale, _ = O.font_binding(item)
        glyphs = metrics['lc_' + role]
        return sum(float(glyphs.get(ord(c), glyphs.get(63))['horizadvance']) for c in text) * scale
    for name in O.MENUS:
        screen = O.runtime_layout(name)
        bounded = O.bound_layout(screen, metrics)
        assert [e['text'] for e in screen['items']] == [e['text'] for e in bounded['items']], name
        for e in screen['items']:
            for part in e.get('parts', []):
                if 'text' in part:
                    probe = {'name': 'variant_part', 'style': part.get('style', 'body'), 'rect': part['rect']}
                    assert width(probe, part['text']) <= part['rect'][2] * .8, (name, e['name'], part['text'])


def test_variant_models_stay_inside_safe_bounds_and_do_not_overlap_unrelated_controls():
    for name in O.MENUS:
        screen = O.runtime_layout(name)
        assert not O.layout_problems(screen)
        raw = {e['name']: e for e in screen['items']}
        retry = raw['retry']['hit_rect']
        variant = raw['lc_broker_error']['rect']
        assert variant[0] <= retry[0] and retry[0] + retry[2] <= variant[0] + variant[2]
        assert variant[1] <= retry[1] and retry[1] + retry[3] <= variant[1] + variant[3]
    # the Browse retry/status band never reaches the page controls
    raw = {e['name']: e for e in O.runtime_layout('lc_browse')['items']}
    band = raw['lc_broker_error']['rect']
    assert band[0] + band[2] <= raw['scroll_up']['rect'][0]
    for key in ('lc_broker_cancel', 'lc_broker_empty', 'lc_broker_room'):
        r = raw[key]['rect']; assert r[0] + r[2] <= raw['scroll_up']['rect'][0], key


def test_status_nodes_the_dll_can_show_together_never_overlap():
    def hit(a, b):
        return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
    for name in O.MENUS:
        raw = {e['name']: e for e in O.runtime_layout(name)['items']}
        exclusive = [k for k in O.BROKER_SCREENS[name] if k not in ('lc_broker_stale', 'lc_broker_offline_room')]
        # stale accompanies a failed or pending refresh; offline_room accompanies the room line
        if 'lc_broker_stale' in raw:
            for key in exclusive + ['retry', 'broker_error']:
                assert not hit(raw['lc_broker_stale']['rect'], raw[key].get('hit_rect', raw[key]['rect'])), (name, key)
        if 'lc_broker_offline_room' in raw:
            # only ever shown in the room state, which excludes every other status node and the error bar
            assert not hit(raw['lc_broker_offline_room']['rect'], raw['lc_broker_room']['rect']), name
        # the diagnostic never sits on the message or the Retry bar it belongs to
        diag = raw['broker_error']['rect']
        assert not hit(diag, raw['retry']['hit_rect']), name


def test_native_play_online_fallback_and_off_are_unchanged_by_round_5():
    assert O.NATIVE_ENTRY == 'openmenu online'
    hub = tree('lc_online')[2]
    assert hub['other'].get('usecmd') == O.command(5)
    assert not [k for k, e in hub.items() if 'openmenu online' in (e.get('usecmd') or '')]
    screen = O.runtime_layout('lc_code')
    root = O.menu_tree(screen)
    assert root.get('menu_cancel') == O.command(6)
