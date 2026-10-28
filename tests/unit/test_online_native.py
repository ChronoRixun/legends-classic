"""Round-6 native Host setup / room-only admission authoring (lc-online-native/1): invented trees only, no game or network."""
import copy
import xml.etree.ElementTree as ET
from xml1build import online_menus as O, online_fonts as F, fix_ini as FI
from test_main_appearance import raises


def tree(name):
    screen = O.runtime_layout(name)
    return screen, O.menu_tree(screen), {e.get('name'): e for e in O.menu_tree(screen).findall('item')}


HOST_NAMES = ('lc_host_settings_unknown', 'lc_host_new', 'lc_host_load', 'lc_host_campaign', 'lc_host_danger_room',
              'lc_host_easy', 'lc_host_normal', 'lc_host_hard', 'lc_host_drop_on', 'lc_host_drop_off', 'lc_host_drop_unknown')


def hit(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def test_native_probe_is_required_beside_the_broker_probe():
    assert b'lc-online-native/1' in O.DLL_PROBES and b'lc-online-broker/2' in O.DLL_PROBES
    data = b'\0'.join(O.DLL_PROBES)
    assert not O.capability_problems(data)
    assert O.capability_problems(data.replace(b'lc-online-native/1', b'lc-online-native/0'))
    keys = {'Online': {'Menus': '1'}, 'Game': {'LegendsClassicFonts': '1'}, 'Limits': {'ScriptFunctions': '1024'}}
    FI.check_online_dll(data, keys)
    raises(FI.FixTooOld, lambda: FI.check_online_dll(data.replace(b'lc-online-native/1', b'x'), keys))


def test_native_status_nodes_exist_hidden_per_screen_with_the_exact_copy_at_the_status_anchor():
    assert O.NATIVE_COPY == {'lc_native_tunnel': 'Connecting to the host...', 'lc_native_discovery': "Finding the host's game...",
                             'lc_native_admission': 'Requesting admission to the game...', 'lc_native_posting': 'Opening the game lobby...'}
    join = ('lc_native_tunnel', 'lc_native_discovery', 'lc_native_admission')
    for name, keys in {'lc_online': (), 'lc_host': ('lc_native_posting',), 'lc_code': join, 'lc_browse': join}.items():
        screen, root, items = tree(name)
        raw = {e['name']: e for e in screen['items']}
        for key in O.NATIVE_COPY:
            assert (key in items) == (key in keys), (name, key)
        for key in keys:
            assert items[key].get('hide') == 'true' and items[key].get('type') == 'MENU_ITEM_TEXT' and items[key].get('neverfocus') == 'true'
            assert O._plain(items[key].get('text')) == O.NATIVE_COPY[key]
            # exactly the status anchor: the DLL shows one of them, never the room line beside it
            assert raw[key]['rect'] == raw['lc_broker_auth']['rect'], (name, key)
    # a native node on a screen that never runs that step is a contract error
    screen, root, _ = tree('lc_online')
    bad = copy.deepcopy(root)
    ET.SubElement(bad, 'item', name='lc_native_tunnel', type='MENU_ITEM_TEXT', text='x', hide='true', neverfocus='true')
    assert O.runtime_problems(bad, screen)


def test_admission_notice_exists_hidden_on_every_screen():
    assert 'lc_notice_admission' in O.NOTICE_TEXT and 'fixture' not in O.NOTICE_TEXT['lc_notice_admission'].lower()
    for name in O.MENUS:
        screen, root, items = tree(name)
        assert items['lc_notice_admission'].get('hide') == 'true'
        assert O._plain(items['lc_notice_admission'].get('text')) == O.NOTICE_TEXT['lc_notice_admission']


def test_host_setting_nodes_are_the_documented_names_hidden_and_the_fixture_prose_is_gone():
    screen, root, items = tree('lc_host')
    for key in HOST_NAMES:
        assert items[key].get('hide') == 'true' and items[key].get('neverfocus') == 'true', key
    assert {k: O._plain(items[k].get('text')) for k in O.HOST_SETTING_COPY} == O.HOST_SETTING_COPY
    for key in ('lc_host_settings_unknown', 'lc_host_drop_on', 'lc_host_drop_off', 'lc_host_drop_unknown'):
        assert items[key].get('type') == 'MENU_ITEM_MODEL', key  # the two-line scenes
    for key in ('save', 'drop_hint', 'preview_save', 'preview_drop', 'preview_slots'):
        assert key not in items, key  # the DLL clears them; LC does not author them
    assert items['campaign'].get('usecmd') == O.command(19) and items['campaign'].get('text') in ('', None)
    assert not items['drop_in'].get('usecmd') and items['drop_in'].get('text') in ('', None)  # read-only policy row
    assert items['lc_host_max_players'].get('clamp') == 'true' and items['lc_host_max_players'].get('text') in ('', None)
    assert O._plain(items['lc_host_players_label'].get('text')) == 'MAX PLAYERS'
    assert 'lc_host_max_players' in O.DATA_NAMES
    # Open keeps intent 19 and the native entry route is untouched
    assert items['open'].get('usecmd') == O.command(19) and items['prompt_open'].get('usecmd') == O.command(19)
    assert not [k for k, e in items.items() if 'openmenu' in (e.get('usecmd') or '')]
    assert not O.runtime_problems(root, screen)


def test_host_setting_validator_catches_missing_mutated_and_fixture_nodes():
    screen, root, _ = tree('lc_host')
    for key in ('lc_host_new', 'lc_host_drop_on', 'lc_host_max_players', 'lc_host_settings_unknown'):
        bad = copy.deepcopy(root)
        bad.remove(next(e for e in bad if e.get('name') == key))
        assert O.runtime_problems(bad, screen), key
    bad = copy.deepcopy(root)
    next(e for e in bad if e.get('name') == 'lc_host_hard').attrib.pop('hide')
    assert O.runtime_problems(bad, screen)
    bad = copy.deepcopy(root)
    next(e for e in bad if e.get('name') == 'campaign').set('usecmd', O.command(7))
    assert O.runtime_problems(bad, screen)
    bad = copy.deepcopy(root)
    next(e for e in bad if e.get('name') == 'drop_in').set('usecmd', O.command(19))
    assert O.runtime_problems(bad, screen)
    bad = copy.deepcopy(root)
    ET.SubElement(bad, 'item', name='preview_save', type='MENU_ITEM_TEXT', text='Load: Mansion, Save 3')
    assert O.runtime_problems(bad, screen)


def test_host_setting_nodes_sit_on_the_approved_anchors_without_hitting_other_controls():
    screen = O.runtime_layout('lc_host')
    assert not O.layout_problems(screen)
    raw = {e['name']: e for e in screen['items']}
    row = raw['campaign']['rect']
    for key in ('lc_host_new', 'lc_host_load'):
        assert raw[key]['rect'] == row
    assert raw['lc_host_settings_unknown']['rect'][:3] == row[:3]
    assert raw['lc_host_campaign']['rect'][1] == raw['lc_host_danger_room']['rect'][1] == raw['lc_host_normal']['rect'][1]
    assert not hit(raw['lc_host_campaign']['rect'], raw['lc_host_normal']['rect'])
    assert not hit(raw['lc_host_danger_room']['rect'], raw['lc_host_hard']['rect'])
    assert raw['lc_host_drop_on']['rect'] == raw['lc_host_drop_off']['rect'] == raw['lc_host_drop_unknown']['rect']
    assert raw['lc_host_drop_on']['rect'][:2] == (164, 305)  # the approved DROP-IN row anchor
    for key in HOST_NAMES:
        x, y, w, h = raw[key]['rect']
        assert 43 <= x and x + w <= 380 and 133 <= y and y + h <= 340, key  # inside the settings panel
        assert not hit(raw[key]['rect'], raw['open']['rect']), key
    for key in ('lc_host_players_label', 'lc_host_max_players'):  # the preview panel, clear of its other text
        x, y, w, h = raw[key]['rect']
        assert 398 <= x and x + w <= 597 and 133 <= y and y + h <= 311, key
        for other in ('preview_name', 'lc_host_private', 'lc_host_public', 'room_code_label'):
            assert not hit(raw[key]['rect'], raw[other]['rect']), (key, other)
    assert not hit(raw['lc_host_players_label']['rect'], raw['lc_host_max_players']['rect'])


def test_every_round6_copy_fits_its_field_without_ellipsis():
    metrics = F.metrics()

    def width(style, text):
        role, scale, _ = O.font_binding({'name': 'probe', 'style': style, 'rect': (0, 0, 1, 1)})
        glyphs = metrics['lc_' + role]
        return sum(float(glyphs.get(ord(c), glyphs.get(63))['horizadvance']) for c in text) * scale
    for name in O.MENUS:
        screen = O.runtime_layout(name)
        bounded = O.bound_layout(screen, metrics)
        assert [e['text'] for e in screen['items']] == [e['text'] for e in bounded['items']], name  # nothing is ellipsized
        for e in screen['items']:
            for part in e.get('parts', []):
                if 'text' in part:
                    assert width(part.get('style', 'body'), part['text']) <= part['rect'][2] * .8, (name, e['name'], part['text'])
    raw = {e['name']: e for e in O.runtime_layout('lc_host')['items']}
    assert width('row', '444') <= raw['lc_host_max_players']['rect'][2] * .8  # a single digit today; three characters fit too


def test_round6_scene_anchor_budget_and_native_nodes_clear_the_offline_line():
    for name in O.MENUS:
        screen = O.bound_layout(O.runtime_layout(name), F.metrics())
        assert len(O.scene_layout(screen)) <= 256, name
    for name in ('lc_host', 'lc_code', 'lc_browse'):
        raw = {e['name']: e for e in O.runtime_layout(name)['items']}
        for key in O.NATIVE_SCREENS[name]:
            # (the diagnostic belongs to failed states, which never coexist with a native step)
            if 'lc_broker_offline_room' in raw:
                assert not hit(raw[key]['rect'], raw['lc_broker_offline_room']['rect']), (name, key)
