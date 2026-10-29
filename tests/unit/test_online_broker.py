"""Round-5 broker bridge authoring (docs/online-menus.md): invented trees only, no game, network or desktop."""
import copy
import re
from xml1build import online_menus as O, online_fonts as F, fix_ini as FI
from test_main_appearance import raises


def tree(name):
    screen = O.runtime_layout(name)
    return screen, O.menu_tree(screen), {e.get('name'): e for e in O.menu_tree(screen).findall('item')}


def test_broker_probe_is_required_and_intents_18_to_31_are_exact_constants():
    assert b'lc-online-broker/2' in O.DLL_PROBES
    data = b'\0'.join(O.DLL_PROBES)
    assert not O.capability_problems(data)
    assert O.capability_problems(data.replace(b'lc-online-broker/2', b'lc-online-broker/0'))
    keys = {'Online': {'Menus': '1'}, 'Game': {'LegendsClassicFonts': '1'}, 'Limits': {'ScriptFunctions': '1024'}}
    FI.check_online_dll(data, keys)
    raises(FI.FixTooOld, lambda: FI.check_online_dll(data.replace(b'lc-online-broker/2', b'x'), keys))
    for number in range(18, 32):
        assert O.command(number) == f'runscript lcOnlineIntent({number})'
    for number in (0, 1, 15, 68, 70, 75, 76):  # 63..74 (except the reserved 68, 70) are the round-8 party intents
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
    assert seen['lc_host'] == {'open': 19, 'prompt_open': 19, 'campaign': 19, 'visibility': 21, 'retry': 20}
    assert seen['lc_online'] == {'retry': 20} and seen['lc_code'] == {'retry': 20}
    browse = seen['lc_browse']
    assert browse['prompt_refresh'] == 18 and browse['scroll_up'] == 22 and browse['scroll'] == 23 and browse['prompt_join'] == 31 and browse['retry'] == 20
    # one page holds BROWSE_ROWS rows (engine scene anchor capacity); commands 24..30 stay reserved for seven
    assert {browse[f'room_{r}_{c}'] for r in range(O.BROWSE_ROWS) for c in O.ROW_COLUMNS} == set(range(24, 24 + O.BROWSE_ROWS))
    assert all(browse[f'room_{r}_{c}'] == 24 + r for r in range(O.BROWSE_ROWS) for c in O.ROW_COLUMNS)
    assert f'room_{O.BROWSE_ROWS}_0' not in browse
    # a mutated scope or number is refused by the validator
    screen, root, items = tree('lc_host')
    bad = copy.deepcopy(root); next(e for e in bad if e.get('name') == 'open').set('usecmd', O.command(18))
    assert O.runtime_problems(bad, screen)
    bad = copy.deepcopy(root); next(e for e in bad if e.get('name') == 'open').set('usecmd', 'openmenu online')
    assert O.runtime_problems(bad, screen)
    screen, root, _ = tree('lc_browse')
    bad = copy.deepcopy(root); next(e for e in bad if e.get('name') == 'room_4_3').set('usecmd', O.command(31))
    assert O.runtime_problems(bad, screen)


def test_status_and_error_variants_exist_hidden_with_exact_localized_copy():
    for name in O.MENUS:
        screen, root, items = tree(name)
        for key in O.BROKER_SCREENS[name]:
            assert items[key].get('hide') == 'true', (name, key)
            if key.startswith('lc_broker_err_'):
                # 060q live: a hidden MENU_ITEM_MODEL never drew when un-hidden, so the cause copy is a plain text item
                assert items[key].get('type') == 'MENU_ITEM_TEXT', (name, key)
                assert re.sub(r'^~\d\d', '', items[key].get('text')) == O.ERROR_COPY[key[len('lc_broker_err_'):]]
                continue
            assert re.sub(r'^~\d\d', '', items[key].get('text')) == O.broker_copy(name, key)
        assert not set(items) & (set(O.BROKER_VARIANTS) - set(O.BROKER_SCREENS[name]))
    # the doc's exact sentences
    assert O.BROKER_COPY['lc_broker_auth'] == 'Connecting to Online service...'
    assert O.BROKER_COPY['lc_broker_list'] == 'Finding public games...'
    assert O.BROKER_COPY['lc_broker_host'] == 'Opening your room...'
    assert O.BROKER_COPY['lc_broker_resolve'] == 'Looking up room code...'
    assert O.BROKER_COPY['lc_broker_empty'] == 'No public games right now. Host a game or go Back.'
    assert O.BROKER_COPY['lc_broker_stale'] == 'Games may be out of date. Refresh to try again.'
    assert O.ERROR_COPY['generic'] == 'Online service request failed. Retry or go Back.'
    assert 'lc_broker_error' not in O.BROKER_VARIANTS
    assert 'Editing the code leaves this room' in O.BROKER_ROOM_COPY['lc_code']
    assert 'native lobby setup is the next step' in O.BROKER_ROOM_COPY['lc_host'].lower()
    assert O.BROKER_COPY['lc_broker_offline_room'].startswith('Online service unavailable. Existing connections stay open')


def test_retry_is_visible_disabled_and_diagnostic_error_is_data_only():
    for name in O.MENUS:
        screen, root, items = tree(name)
        retry = items['retry']
        # Hidden AND disabled until the DLL selects a retryable cause scene (it hides, not just disables, otherwise).
        assert retry.get('usecmd') == O.command(20) and retry.get('enabled') == 'false' and retry.get('hide') == 'true'
        assert retry.get('neverfocus') == 'false'
        diag = items['broker_error']
        assert diag.get('clamp') == 'true' and diag.get('usecmd') is None and not any('gamevar' in k.lower() for k in diag.attrib)
        assert diag.get('neverfocus') == 'true'
        # retry keeps closed focus links and its own focus resource even while disabled
        assert all(retry.get(d) in items for d in ('left', 'right', 'up', 'down'))
        focus = O.SHARED_FOCUS if name in O.SHARED_FOCUS_SCREENS else 'retry_focus'  # 060q: Browse shares one focus model item
        assert any(e.get('item') == focus and e.get('type') == 'focus' for e in retry.findall('onfocus'))
        raw = next(e for e in screen['items'] if e['name'] == 'retry')
        hit = raw['hit_rect']
        assert hit[2] >= 56 and hit[3] >= 15 and not O.layout_problems(screen)
        assert raw['text'] == 'RETRY' and raw.get('align') is None and hit[0] <= raw['rect'][0] and raw['rect'][0] + raw['rect'][2] <= hit[0] + hit[2]  # the label is the item's own text, in front of the focus bar


def test_browse_rows_exist_for_an_empty_list_with_row_commands_and_closed_grid():
    screen, root, items = tree('lc_browse')
    for r in range(O.BROWSE_ROWS):
        assert 'room_%d_4' % r not in items  # the status word belongs to the row scenes
        assert items['room_%d_5' % r].get('neverfocus') == 'true' and not items['room_%d_5' % r].get('usecmd')  # round 7: measured RTT, DATA only
        for ci, c in enumerate(O.ROW_COLUMNS):
            e = items[f'room_{r}_{c}']
            assert e.get('usecmd') == O.command(24 + r) and e.get('enabled') == 'false' and e.get('clamp') == 'true'
            assert e.get('text') in ('', None) or e.get('text').startswith('~')
            assert not any('gamevar' in k.lower() for k in e.attrib)
            assert e.get('left') == f'room_{r}_{O.ROW_COLUMNS[max(0, ci - 1)]}' and e.get('right') == f'room_{r}_{O.ROW_COLUMNS[min(4, ci + 1)]}'
            assert e.get('up') == (f'room_{r - 1}_{c}' if r else 'prompt_refresh')
            assert e.get('down') == (f'room_{r + 1}_{c}' if r < O.BROWSE_ROWS - 1 else 'scroll')
            # mouse/focus rectangle kept while disabled; every Browse focus bar is carried by the one shared model item
            # X1 gain-only replacement fits the native 75-record budget; native
            # focus loss stops the outgoing gain before the next one replaces it.
            assert [(f.get('item'), f.get('type')) for f in e.findall('onfocus')] == [(O.SHARED_FOCUS, 'focus')]
            assert f'room_{r}_{c}_focus' not in items and f'room_{r}_focus' not in items
        models = {f.get('model') for c in O.ROW_COLUMNS for f in items[f'room_{r}_{c}'].findall('onfocus') if f.get('type') == 'focus'}
        assert len(models) == 1, models  # one row-wide focus bar, whichever cell has focus
    raw = {e['name']: e for e in screen['items']}
    for r in range(O.BROWSE_ROWS):
        rects = {raw[f'room_{r}_{c}']['rect'][1] for c in O.ROW_COLUMNS}
        assert len(rects) == 1 and not any(raw[f'room_{r}_{c}']['rect'][3] < 20 for c in O.ROW_COLUMNS)
    for r in range(O.BROWSE_ROWS):
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
        diag = raw['broker_error']['rect']
        for cause in O.BROKER_CAUSES[name]:
            node = raw['lc_broker_err_' + cause]['rect']
            # the cause copy never sits on the Retry control or the diagnostic that shares its row
            if cause in O.RETRYABLE_CAUSES:  # the DLL hides Retry for every other cause, so only then does it share the row
                assert node[0] + node[2] <= retry[0] or retry[0] + retry[2] <= node[0] or node[1] + node[3] <= retry[1] or retry[1] + retry[3] <= node[1], (name, cause)
            assert node[0] + node[2] <= diag[0] + (14 if name == 'lc_code' else 0) or node[1] + node[3] <= diag[1] or diag[1] + diag[3] <= node[1], (name, cause)
    # X1 puts paging in its own footer row. Require separation on either
    # axis, including wide status copy that now extends past the page x origin.
    raw = {e['name']: e for e in O.runtime_layout('lc_browse')['items']}
    bands = ['lc_broker_err_' + cause for cause in O.BROKER_CAUSES['lc_browse']]
    bands += ['lc_broker_cancel', 'lc_broker_empty', 'lc_broker_room', 'broker_error']
    for key in bands:
        x, y, w, h = raw[key]['rect']
        for control in ('scroll_up', 'scroll'):
            px, py, pw, ph = raw[control]['rect']
            assert x + w <= px or px + pw <= x or y + h <= py or py + ph <= y, (key, control)


def test_status_nodes_the_dll_can_show_together_never_overlap():
    def hit(a, b):
        return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
    for name in O.MENUS:
        raw = {e['name']: e for e in O.runtime_layout(name)['items']}
        exclusive = [k for k in O.BROKER_SCREENS[name] if k not in ('lc_broker_stale', 'lc_broker_offline_room')]
        # stale accompanies a failed or pending refresh; offline_room accompanies the room line (the DLL never shows
        # stale then). Both live in the Browse list header and must clear the count and the age.
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


def test_round_5b_cause_scenes_retry_bar_only_for_retryable_causes_and_exact_copy():
    assert set(O.ERROR_CAUSES) == {'code_not_found', 'room_full', 'version_mismatch', 'rate_limited', 'timeout', 'offline', 'refused', 'generic',
                                   'pin_mismatch', 'code_expired', 'room_closed', 'test_mode', 'unsupported', 'busy', 'invalid_name', 'too_many_public_rooms', 'too_many_joins'}
    assert set(O.RETRYABLE_CAUSES) == {'rate_limited', 'timeout', 'offline', 'generic', 'room_closed'}  # same set the DLL's cause_retryable() allows
    for name in O.MENUS:
        screen, root, items = tree(name)
        raw = {e['name']: e for e in screen['items']}
        assert set(O.BROKER_CAUSES[name]) <= set(O.ERROR_CAUSES)
        for cause in O.ERROR_CAUSES:
            key = 'lc_broker_err_' + cause
            assert (key in items) == (cause in O.BROKER_CAUSES[name]), (name, key)
            if key not in items: continue
            assert items[key].get('hide') == 'true' and items[key].get('type') == 'MENU_ITEM_TEXT'
            assert not raw[key].get('parts') and raw[key]['text'] == O.ERROR_COPY[cause]  # one plain text item, no model scene
            assert raw[key]['color'] == (5 if cause in O.AMBER_CAUSES else 7), (name, cause)
            if cause in O.RETRYABLE_CAUSES:
                assert raw['retry']['hit_rect'] == O.RETRY_RECT.get(name, O.RETRY_DEFAULT), name
    assert O.ERROR_COPY['code_not_found'].startswith('Code not found') and 'new code' in O.ERROR_COPY['room_full']
    assert 'same build' in O.ERROR_COPY['version_mismatch'] and 'LAN and IP' in O.ERROR_COPY['offline']
    assert O.ERROR_COPY['room_full'] != O.ERROR_COPY['generic'] and len(set(O.ERROR_COPY.values())) == len(O.ERROR_CAUSES)


def test_round_5b_browse_row_scenes_header_nodes_and_shared_models():
    screen, root, items = tree('lc_browse')
    raw = {e['name']: e for e in screen['items']}
    models = set()
    for r in range(O.BROWSE_ROWS):
        y = 178 + 31 * r
        want = [f'lc_row{r}_st_{k}' for k in O.STATUS_KINDS] + [f'lc_row{r}_pips_{n}' for n in range(5)] + \
            [f'lc_row{r}_build_{k}' for k in O.BUILD_KINDS] + [f'lc_row{r}_dim']
        for key in want:
            e = items[key]
            assert e.get('hide') == 'true' and e.get('type') == 'MENU_ITEM_MODEL' and e.get('neverfocus') == 'true', key
            models.add(e.get('model'))
            rect = raw[key]['rect']
            assert 44 <= rect[0] and rect[0] + rect[2] <= 596 and y <= rect[1] and rect[1] + rect[3] <= y + 31, key
        # model vertices sit +40 behind their anchor: the veil (-160) is nearer than the text (-150), the scenes (-130) behind it
        assert raw[f'lc_row{r}_dim']['plane'] + 40 < -150 < raw[f'lc_row{r}_st_lobby']['plane'] + 40
    # identical relative art shares one model per kind (13 row models, not 91)
    assert len(models) == 4 + 5 + 3 + 1
    assert [k for k in O.STATUS_KINDS] == ['lobby', 'progress', 'closed', 'full']  # no "loading": the broker sends no such state
    assert list(O.BUILD_KINDS) == ['same', 'other', 'check']
    for k in range(1, 6):
        assert items[f'lc_age_fill{k}'].get('hide') == 'true'
    for key in ('list_count', 'list_age'):
        assert items[key].get('clamp') == 'true' and raw[key]['data']
    assert raw['list_header']['text'] == 'PUBLIC GAMES' and raw['details']['text'] == ''  # the empty message is lc_broker_empty's alone
    # header zones never collide: label+count | stale/offline line | age
    def span(key): x, y, w, h = raw[key]['rect']; return x, x + w
    assert span('list_header')[1] <= span('list_count')[0] and span('list_count')[1] <= span('lc_broker_stale')[0]
    assert span('lc_broker_stale')[1] <= span('list_age')[0] and span('lc_broker_offline_room') == span('lc_broker_stale')
    assert span('list_age')[1] <= 546  # the refresh bar track starts after the age
    # status words are drawn by the scenes; the data cell for the status/ping columns stays a hit target only
    assert raw['room_0_6']['color'] == 7


def test_round_5b_service_scene_on_every_screen_and_last_game_binding():
    for name in O.MENUS:
        screen, root, items = tree(name)
        assert items['lc_service_ok'].get('hide') == 'true' and items['lc_service_ok'].get('type') == 'MENU_ITEM_MODEL'
    screen, root, items = tree('lc_online')
    assert items['last_code'].get('clamp') == 'true' and 'last_code' in O.DATA_NAMES
    raw = {e['name']: e for e in screen['items']}
    assert raw['last_code']['rect'][2] >= 200  # "Code K7QN-2X9M, 2 hours ago" is one bound line


def test_round_5b_every_cause_copy_fits_its_scene_text_box_without_ellipsis():
    metrics = F.metrics()
    glyphs = metrics['lc_body']
    scale = F.SCALES['body']
    for name in O.MENUS:
        screen = O.runtime_layout(name)
        for cause in O.BROKER_CAUSES[name]:
            scene = next(e for e in screen['items'] if e['name'] == 'lc_broker_err_' + cause)
            w = sum(float(glyphs.get(ord(c), glyphs.get(63))['horizadvance']) for c in scene['text']) * scale
            assert w <= scene['rect'][2] * .8, (name, cause, w)
            diag = next(e for e in screen['items'] if e['name'] == 'broker_error')['rect']
            sx, sy, _, _ = scene['rect']
            # the copy never reaches the right-aligned diagnostic field
            assert sx + w / .8 <= diag[0] + (4 if name == 'lc_code' else 0), (name, cause)


def test_round_5b_scene_anchor_budget_and_ping_text_live_in_the_pip_scenes():
    from xml1build import menu_scene
    for name in O.MENUS:
        screen = O.bound_layout(O.runtime_layout(name), F.metrics())
        # The engine's per-scene capacity (0x5882e0), not the old 256: seven Browse rows authored 241 and crashed 060p.
        assert len(O.scene_layout(screen)) <= O.engine_scene_anchors(O.ANCHOR_CAPABILITY), (name, len(O.scene_layout(screen)))
    raw = {e['name']: e for e in O.runtime_layout('lc_browse')['items']}
    for r in range(O.BROWSE_ROWS):
        for n in range(5):
            scene = raw[f'lc_row{r}_pips_{n}']
            assert [p['text'] for p in scene['parts'] if 'text' in p] == ['--']  # never a number: no ping is measured
            assert scene['rect'][0] + scene['rect'][2] <= raw[f'lc_row{r}_build_same']['rect'][0]
