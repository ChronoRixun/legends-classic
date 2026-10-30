"""Release fallback must be effective with the companion DLL actually supplied."""
import pytest
from xml1build import fix_ini as F, online_menus as O


def test_release_admits_at_lobby_start_by_default():
    keys = F.online_keys(port_identity=True, balance=False)
    assert keys['JoinInProgress'] == '1'  # retain solo spectators / host lifecycle
    assert keys['LateJoin'] == '0'


def test_legacy_dll_cannot_silently_ignore_the_safe_default():
    keys = {'Online': {'JoinInProgress': '1', 'LateJoin': '0'}}
    legacy = b'\0'.join(O.DLL_PROBES)
    with pytest.raises(F.FixTooOld, match='LateJoin'):
        F.check_online_dll(legacy, keys)
    F.check_online_dll(legacy + b'\0LateJoinPolicyV1\0', keys)


def test_started_notice_is_available_on_each_join_screen():
    assert O.NOTICE_TEXT['lc_notice_started'] == 'This session has started; ask the host to return to the lobby'
    for name in ('lc_code', 'lc_browse'):
        tree = O.menu_tree(O.runtime_layout(name))
        assert tree.find("item[@name='lc_notice_started']") is not None


def test_offline_dll_check_preserves_the_no_read_path():
    F.check_online_dll(None, {})
    F.check_online_dll(None, {'Online': {'Menus': '0'}})
    with pytest.raises(F.FixTooOld, match='LateJoin'):
        F.check_online_dll(None, {'Online': {'JoinInProgress': '1', 'LateJoin': '0'}})


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
