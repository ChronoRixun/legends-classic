"""Late joining (the host's next-area reload of everyone) is the 0.6.0 default; a tester's explicit value survives."""
import unittest
from xml1build import fix_ini as F, online_menus as O


def test_release_admits_late_joiners_at_the_next_area_by_default():
    keys = F.online_keys(port_identity=True, balance=False)
    assert keys['JoinInProgress'] == '1'  # retain solo spectators / host lifecycle
    assert keys['LateJoin'] == '1'        # p060fix/AE: everyone reloads from the host's image at the next zone load


def test_player_explicit_late_join_survives_rebuild_and_repair():
    keys = {'Online': {'JoinInProgress': '1', 'LateJoin': '1'}, 'Game': {'Xtract': '0'}}
    kept = F.keep_player_late_join('[Online]\r\nLateJoin=0\r\n', keys)
    assert kept['Online']['LateJoin'] == '0' and kept['Game'] == keys['Game'] and keys['Online']['LateJoin'] == '1'
    assert F.keep_player_late_join('[online]\r\nlatejoin = 0\r\n', keys)['Online']['LateJoin'] == '0'
    assert F.keep_player_late_join('[Online]\r\nLateJoin=1\r\n', keys) is keys
    assert F.keep_player_late_join('[Online]\r\nLateJoin=maybe\r\n', keys) is keys   # junk: the default wins
    assert F.keep_player_late_join('', keys) is keys
    assert F.keep_player_late_join('[Online]\r\nLateJoin=0\r\n', {'Online': {'JoinInProgress': '1'}})['Online'] == {'JoinInProgress': '1'}
    with_zero = {'Online': {'JoinInProgress': '1', 'LateJoin': '0'}}
    assert F.keep_player_late_join('[Online]\r\nLateJoin=1\r\n', with_zero)['Online']['LateJoin'] == '1'


def test_legacy_dll_cannot_silently_ignore_the_policy_key():
    keys = {'Online': {'JoinInProgress': '1', 'LateJoin': '1'}}
    legacy = b'\0'.join(O.DLL_PROBES)
    with unittest.TestCase().assertRaisesRegex(F.FixTooOld, 'LateJoin'):
        F.check_online_dll(legacy, keys)
    F.check_online_dll(legacy + b'\0LateJoinPolicyV1\0', keys)


def test_started_notice_is_available_on_each_join_screen():
    assert O.NOTICE_TEXT['lc_notice_started'] == 'This session has started. Ask the host to start a new session.'
    for name in ('lc_code', 'lc_browse'):
        tree = O.menu_tree(O.runtime_layout(name))
        assert tree.find("item[@name='lc_notice_started']") is not None


def test_offline_dll_check_preserves_the_no_read_path():
    F.check_online_dll(None, {})
    F.check_online_dll(None, {'Online': {'Menus': '0'}})
    with unittest.TestCase().assertRaisesRegex(F.FixTooOld, 'LateJoin'):
        F.check_online_dll(None, {'Online': {'JoinInProgress': '1', 'LateJoin': '1'}})


def test_host_drop_in_row_is_keyboard_and_mouse_actionable():
    screen = O.runtime_layout('lc_host')
    items = {e.get('name'): e for e in O.menu_tree(screen).findall('item')}
    assert items['drop_in'].get('usecmd') == 'runscript lcOnlineIntent(75)'
    assert 'drop_in' in {row[0] for row in O.hit_rows(screen)}
    settings = {e['name']: e for e in screen['items']}
    assert settings['campaign']['down'] == 'drop_in'
    assert 'lc_host_marker_drop' in items
    assert O.BROKER_SCOPE[75] == ('lc_host',)
    assert b'lc-online-drop-in/1' in O.DLL_PROBES
