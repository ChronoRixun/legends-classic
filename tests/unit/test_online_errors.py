"""Round-15 complete error table authoring (lc-online-errors/1): invented trees only, no game, network or desktop."""
import re
import xml.etree.ElementTree as ET
from xml1build import online_menus as O, online_fonts as F, fix_ini as FI
from test_main_appearance import raises


def tree(name):
    screen = O.runtime_layout(name)
    return screen, O.menu_tree(screen), {e.get('name'): e for e in O.menu_tree(screen).findall('item')}


# The DLL's online_menus_rules::error_cause_key / cause_table, mirrored here and pinned by the DLL's own table test
# (test/online_menus_errors.inl). Changing either side alone fails one of the two suites.
DLL_CAUSES = ('code_not_found', 'room_full', 'version_mismatch', 'rate_limited', 'timeout', 'offline', 'refused', 'generic',
              'pin_mismatch', 'code_expired', 'room_closed', 'test_mode', 'unsupported', 'busy', 'invalid_name')
DLL_NEXT = ('edit_code', 'browse', 'back', 'retry', 'retry', 'retry', 'back', 'retry', 'back', 'edit_code', 'retry', 'back', 'other_ways', 'wait', 'back')
DLL_RETRY = ('rate_limited', 'timeout', 'offline', 'generic', 'room_closed')


def test_errors_probe_is_required_and_the_contract_mirrors_the_dll_table():
    assert b'lc-online-errors/1' in O.DLL_PROBES
    data = b'\0'.join(O.DLL_PROBES)
    assert not O.capability_problems(data)
    assert O.capability_problems(data.replace(b'lc-online-errors/1', b'lc-online-errors/0'))
    keys = {'Online': {'Menus': '1'}, 'Game': {'LegendsClassicFonts': '1'}, 'Limits': {'ScriptFunctions': '1024'}}
    FI.check_online_dll(data, keys)
    raises(FI.FixTooOld, lambda: FI.check_online_dll(data.replace(b'lc-online-errors/1', b'x'), keys))
    assert O.ERROR_CAUSES == DLL_CAUSES
    assert tuple(O.NEXT_ACTION[c] for c in O.ERROR_CAUSES) == DLL_NEXT
    assert set(O.RETRYABLE_CAUSES) == set(DLL_RETRY) and all(O.NEXT_ACTION[c] == 'retry' for c in O.RETRYABLE_CAUSES)
    assert 'busy' not in O.RETRYABLE_CAUSES  # the refused phase has no Retry (online_room::retry() refuses it)
    assert set(O.ERROR_COPY) == set(O.ERROR_CAUSES) == set(O.NEXT_ACTION)


def test_every_cause_names_its_cause_and_its_next_action_in_one_line():
    metrics = F.metrics()
    glyphs = metrics['lc_body']
    scale = F.SCALES['body']
    seen = set()
    for cause in O.ERROR_CAUSES:
        text = O.ERROR_COPY[cause]
        low = text.lower()
        assert any(word in low for word in O.NEXT_WORD[O.NEXT_ACTION[cause]]), (cause, text)
        assert text not in seen and 'fixture' not in low and '%' not in text and '\n' not in text
        seen.add(text)
        assert len(text) <= 64, (cause, len(text))
        # a cause that offers Retry says so; one that cannot never tells the player to press it
        if cause not in O.RETRYABLE_CAUSES: assert 'retry' not in low and 'try again' not in low, (cause, text)
    # no copy promises what 0.6 does not do: no checkpoint, takeover or recovery wording, no insecure bypass
    for text in O.ERROR_COPY.values():
        for word in ('takeover', 'take over', 'recover', 'checkpoint', 'ignore', 'bypass', 'skip the check'):
            assert word not in text.lower(), text
    # the two causes that refuse the service never offer to continue without it
    assert 'Check its setting' in O.ERROR_COPY['pin_mismatch'] and 'Turn it off' in O.ERROR_COPY['test_mode']
    assert 'Other ways to play' in O.ERROR_COPY['unsupported'] and 'LAN and IP' in O.ERROR_COPY['offline']


def test_each_screen_authors_exactly_the_causes_it_can_reach_with_a_retry_bar_only_where_retryable():
    for name in O.MENUS:
        screen, root, items = tree(name)
        raw = {e['name']: e for e in screen['items']}
        for cause in O.ERROR_CAUSES:
            key = 'lc_broker_err_' + cause
            assert (key in items) == (cause in O.BROKER_CAUSES[name]), (name, cause)
            if key not in items: continue
            assert items[key].get('hide') == 'true' and items[key].get('type') == 'MENU_ITEM_TEXT', (name, cause)
            assert not raw[key].get('parts'), (name, cause)  # never a model scene (060q: those never drew when un-hidden)
        assert not O.broker_problems(root, screen), O.broker_problems(root, screen)
    # reachability: the Host screen alone can say a room name is invalid; Browse/Code resolve (and so see every code failure)
    assert 'invalid_name' in O.BROKER_CAUSES['lc_host'] and 'invalid_name' not in O.BROKER_CAUSES['lc_code']
    for cause in ('code_not_found', 'code_expired', 'room_full', 'room_closed', 'version_mismatch'):
        assert cause in O.BROKER_CAUSES['lc_code'] and cause in O.BROKER_CAUSES['lc_browse'] and cause not in O.BROKER_CAUSES['lc_host']
    for cause in ('pin_mismatch', 'test_mode', 'unsupported', 'busy', 'offline', 'timeout', 'rate_limited', 'refused', 'generic'):
        assert all(cause in O.BROKER_CAUSES[n] for n in O.MENUS), cause


def test_amber_for_waits_and_limits_red_for_failures():
    for name in O.MENUS:
        raw = {e['name']: e for e in O.runtime_layout(name)['items']}
        for cause in O.BROKER_CAUSES[name]:
            assert raw['lc_broker_err_' + cause]['color'] == (5 if cause in O.AMBER_CAUSES else 7), (name, cause)


def test_native_failure_notices_cover_every_step_and_the_refusal_names_its_rules():
    want = {'lc_notice_discovery', 'lc_notice_refused', 'lc_notice_refusal_rules', 'lc_notice_service_lost', 'lc_notice_timeout',
            'lc_notice_clipboard', 'lc_notice_admission'}
    assert want <= set(O.NOTICE_TEXT)
    for name in O.MENUS:
        screen, root, items = tree(name)
        for key in want:
            if name == 'lc_browse' and key in O.BROWSE_UNREACHABLE_NOTICES:
                assert key not in items  # 060q: Browse never reads the clipboard; the DLL falls back to lc_inline_error
                continue
            assert items[key].get('hide') == 'true' and items[key].get('type') == 'MENU_ITEM_TEXT', (name, key)
            assert O._plain(items[key].get('text')) == O.NOTICE_TEXT[key]
        rules = items['lc_refusal_rules']
        assert rules.get('clamp') == 'true' and not any('gamevar' in k.lower() for k in rules.attrib)
        raw = {e['name']: e for e in screen['items']}
        a, b = raw['lc_notice_refusal_rules']['rect'], raw['lc_refusal_rules']['rect']
        assert a[0] + a[2] > b[0] and b[0] >= a[0] + 150 and b[0] + b[2] <= 597  # the DATA follows its lead-in inside the safe area
    for key, text in O.NOTICE_TEXT.items():
        assert 'fixture' not in text.lower() and '%' not in text
    assert 'possibly' in O.NOTICE_TEXT['lc_notice_refusal_rules'].lower()
    assert 'build' in O.NOTICE_TEXT['lc_notice_refused'].lower() and 'settings' in O.NOTICE_TEXT['lc_notice_refused'].lower()
    assert 'clipboard' in O.NOTICE_TEXT['lc_notice_clipboard'].lower() and 'type' in O.NOTICE_TEXT['lc_notice_clipboard'].lower()


def test_lobby_inline_scenes_never_close_the_lobby_and_carry_their_cause():
    for role in O.LOBBIES:
        screen = O.lobby_layout(role)
        items = {e['name']: e for e in screen['items']}
        for key in ('lc_lobby_error', 'lc_lobby_error_copy', 'lc_lobby_error_target'):
            e = items[key]
            assert e.get('hidden') and e.get('parts') and e['parts'][0]['kind'] == 'panel', key
        # 060q live: the departed-guest and service-lost lines were hidden model scenes that never drew - plain text now
        for key, copy in (('lc_lobby_guest_left', O.LOBBY_TOAST_COPY), ('lc_lobby_service_lost', O.LOBBY_SERVICE_LOST_COPY)):
            e = items[key]
            assert e.get('hidden') and not e.get('parts') and e['text'] == copy, key
        toast = items['lc_toast_name']
        assert toast['data'] and not toast.get('hidden') and toast['text'] == ''
        assert items['lc_lobby_error_copy']['text'] == '' and any(p.get('text') == O.LOBBY_ERROR_COPY['copy'] for p in items['lc_lobby_error_copy']['parts'])
        assert any(p.get('text') == O.LOBBY_ERROR_COPY['target'] for p in items['lc_lobby_error_target']['parts'])
        assert 'rejoin with the code' in O.LOBBY_TOAST_COPY and 'new players cannot join' in O.LOBBY_SERVICE_LOST_COPY
        # the toast sits between the cards and the action bars: never over a button, never over the cards
        x, y, w, h = items['lc_lobby_guest_left']['rect']
        assert y >= 355 and y + h <= 391 and x + w <= 597
        # the service strip sits below the action bars and above the prompt row
        x, y, w, h = items['lc_lobby_service_lost']['rect']
        assert y >= 424 and y + h <= 455


def test_host_left_panel_is_a_hub_modal_that_claims_no_takeover_and_no_recovery():
    screen, root, items = tree('lc_online')
    raw = {e['name']: e for e in screen['items']}
    for key in ('lc_hub_host_left', 'lc_hub_host_left_veil'):
        assert items[key].get('hide') == 'true' and items[key].get('type') == 'MENU_ITEM_MODEL' and items[key].get('neverfocus') == 'true'
    again, back = items['lc_hostleft_again'], items['lc_hostleft_back']
    assert again.get('usecmd') == O.command(2) and back.get('usecmd') == O.command(8)
    for e in (again, back): assert e.get('hide') == 'true' and e.get('enabled') == 'false'
    # the veil is in front of the Hub's text, the card in front of the veil, the buttons in front of the card
    assert raw['lc_hub_host_left_veil']['plane'] < -150 and raw['lc_hub_host_left']['plane'] < raw['lc_hub_host_left_veil']['plane']
    assert raw['lc_hostleft_again']['plane'] < raw['lc_hub_host_left']['plane'] and raw['lc_hostleft_back']['plane'] < raw['lc_hub_host_left']['plane']
    # the card holds its buttons' bars exactly where the buttons are
    x, y, _, _ = raw['lc_hub_host_left']['rect']
    bars = [p for p in raw['lc_hub_host_left']['parts'] if p.get('kind') == 'bar']
    assert [(x + b['rect'][0], y + b['rect'][1], b['rect'][2], b['rect'][3]) for b in bars] == [raw['lc_hostleft_again']['hit_rect'], raw['lc_hostleft_back']['hit_rect']]
    words = ' '.join(p.get('text', '') for p in raw['lc_hub_host_left']['parts']) + ' ' + raw['lc_hostleft_again']['text'] + ' ' + raw['lc_hostleft_back']['text']
    low = words.lower()
    assert 'host again' in low and 'back to online' in low and 'the host disconnected' in low and 'save on this pc' in low
    for word in ('takes over', 'takeover', 'continue as party', 'checkpoint', 'recover', 'rollback', 'new host'):
        assert word not in low, word
    # the host-left panel belongs to the Hub alone
    for name in ('lc_host', 'lc_code', 'lc_browse'):
        assert 'lc_hub_host_left' not in tree(name)[2]
    # the Hub's own actions keep their intents so the DLL can disable them under the modal
    for key in ('host', 'code', 'browse', 'other', 'change_name', 'rejoin'):
        assert key in items, key


def test_round15_renders_are_real_frames_not_blank():
    from PIL import ImageChops
    base = O.render_native(O.runtime_layout('lc_online'), size=(1920, 1080)).convert('RGB')
    screen = O.runtime_layout('lc_online')
    for e in screen['items']:
        if e['name'] in ('lc_hub_host_left', 'lc_hub_host_left_veil', 'lc_hostleft_again', 'lc_hostleft_back'): e['hidden'] = False; e['enabled'] = True
    shown = O.render_native(screen, size=(1920, 1080)).convert('RGB')
    assert shown.size == (1920, 1080) and ImageChops.difference(base, shown).getbbox() is not None
    box = ImageChops.difference(base, shown).getbbox()
    assert box[0] >= 0 and box[2] <= 1920 and box[3] - box[1] > 300  # the modal covers the Hub, within the frame


def test_retry_is_a_plain_light_label_on_every_screen_and_every_message_is_a_plain_text_item():
    # 060q live: RETRY was authored dark (colour 0) for a baked amber bar that never drew, so on Browse it was invisible; the
    # per-cause scenes were hidden MENU_ITEM_MODELs that never drew when un-hidden, so only the diagnostic showed.
    for name in O.MENUS:
        screen, root, items = tree(name)
        raw = {e['name']: e for e in screen['items']}
        assert raw['retry']['color'] == 4 and raw['retry']['intent'] == 'retry' and raw['retry'].get('hit_rect'), name
        assert items['retry'].get('type') == 'MENU_ITEM_TEXT' and not O._plain(items['retry'].get('text')).startswith('~')
        for cause in O.BROKER_CAUSES[name]:
            node = items['lc_broker_err_' + cause]
            assert node.get('type') == 'MENU_ITEM_TEXT' and O._plain(node.get('text')) == O.ERROR_COPY[cause], (name, cause)
    # the same for the two lobby lines of this round (service lost, departed guest)
    for role in O.LOBBIES:
        screen = O.lobby_layout(role)
        for key in ('lc_lobby_service_lost', 'lc_lobby_guest_left'):
            e = next(e for e in screen['items'] if e['name'] == key)
            assert not e.get('parts') and e['text'], (role, key)
