"""Round-7 card fields and round-8 Party screen / pause rename authoring: invented trees only, no game or network."""
import copy
import xml.etree.ElementTree as ET
from xml1build import online_menus as O, online_fonts as F


def native_lobby(role):
    """Invented stand-in for the native host/join definition: the items the adapter depends on, nothing decoded."""
    root = ET.Element('menu', name=role, type='HOST_MENU' if role == 'host' else 'JOIN_MENU', igb='x2m_' + role)
    for key in ('text_startgame', 'text_readygame', 'text_kickplayer', 'text_leaveroom'):
        ET.SubElement(root, 'item', name=key, type='MENU_ITEM_TEXT', text='X', style='STYLE_MENU_WHITE_MED', usecmd='', neverfocus='false')
    for key in ('text_playername1', 'text_readycheck1'):
        ET.SubElement(root, 'item', name=key, type='MENU_ITEM_LISTBOX', style='STYLE_NORMAL')
    ET.SubElement(root, 'item', name='data_name', type='MENU_ITEM_TEXT', text='')
    return root


def lobby(role, **kw):
    screen = O.lobby_layout(role, **kw)
    native = native_lobby(role)
    return screen, native, O.lobby_tree(native, screen)


CARD_DATA = ('phase', 'route')
CARD_SCENES = ('to_host', 'other_build', 'pending')


def test_every_lobby_card_authors_the_round7_fields_hidden_or_data_and_never_focusable():
    for role in O.LOBBIES:
        screen, native, tree = lobby(role)
        items = {e.get('name'): e for e in tree.findall('item')}
        for n in range(1, 5):
            for key in CARD_DATA:
                e = items[f'lc_p{n}_{key}']
                assert e.get('type') == 'MENU_ITEM_TEXT' and e.get('clamp') == 'true' and e.get('neverfocus') == 'true', (role, n, key)
                assert not e.get('usecmd') and e.get('text') in ('', None), (role, n, key)
            for key in CARD_SCENES:
                e = items[f'lc_p{n}_{key}']
                assert e.get('type') == 'MENU_ITEM_MODEL' and e.get('hide') == 'true' and e.get('neverfocus') == 'true', (role, n, key)
                assert not e.get('usecmd'), (role, n, key)
        assert not O.lobby_problems(tree, native, screen), role


def test_round7_card_fields_sit_inside_their_card_clear_of_the_other_card_parts():
    screen = O.lobby_layout('host', members=3, fixture=True)
    raw = {e['name']: e for e in screen['items']}
    for n in range(1, 5):
        x = 43 + (n - 1) * 141
        for key in (*CARD_DATA, 'to_host'):
            ex, ey, ew, eh = raw[f'lc_p{n}_{key}']['rect']
            assert x <= ex and ex + ew <= x + 132 and 189 <= ey and ey + eh <= 189 + 165, (n, key)
        # the phase and route words never share a line with the build badge
        assert raw[f'lc_p{n}_phase']['rect'][1] >= raw[f'lc_p{n}_same_build']['rect'][1] + raw[f'lc_p{n}_same_build']['rect'][3]
        assert raw[f'lc_p{n}_other_build']['rect'] == raw[f'lc_p{n}_same_build']['rect']
        assert raw[f'lc_p{n}_other_build']['rect'][:2] == raw[f'lc_p{n}_checking_build']['rect'][:2]


def test_lobby_validator_rejects_a_missing_or_visible_round7_node():
    for role in O.LOBBIES:
        screen, native, tree = lobby(role)
        for key in ('lc_p2_other_build', 'lc_p3_pending', 'lc_p1_to_host', 'lc_p4_phase', 'lc_p2_route'):
            bad = copy.deepcopy(tree)
            bad.remove(next(e for e in bad if e.get('name') == key))
            assert O.lobby_problems(bad, native, screen), (role, key)
        bad = copy.deepcopy(tree)
        next(e for e in bad if e.get('name') == 'lc_p2_pending').attrib.pop('hide')
        assert O.lobby_problems(bad, native, screen)
        bad = copy.deepcopy(tree)
        next(e for e in bad if e.get('name') == 'lc_p2_phase').set('gamevar', 'phase')
        assert O.lobby_problems(bad, native, screen)


def test_lobby_scene_anchor_budget_holds_with_the_round7_nodes():
    for role in O.LOBBIES:
        for kw in ({}, {'members': 4, 'fixture': True}):
            screen = O.bound_layout(O.lobby_layout(role, **kw), F.metrics())
            assert len(O.scene_layout(screen)) <= 256, role


def test_browse_rows_author_the_measured_ping_text_over_the_neutral_dash_cell():
    screen = O.runtime_layout('lc_browse')
    root = O.menu_tree(screen)
    items = {e.get('name'): e for e in root.findall('item')}
    raw = {e['name']: e for e in screen['items']}
    for r in range(O.BROWSE_ROWS):
        e = items[f'room_{r}_5']
        assert e.get('type') == 'MENU_ITEM_TEXT' and e.get('clamp') == 'true' and e.get('neverfocus') == 'true'
        assert not e.get('usecmd') and e.get('text') in ('', None), r
        # over the '--' of the row's neutral-ping scene, inside the PING column, left of the build badge
        x, y, w, h = raw[f'room_{r}_5']['rect']
        assert x == 495 and y == 178 + 31 * r + 8 and x + w <= 552, r
    assert not O.runtime_problems(root, screen)
    # the status and build words stay row scenes, never cells
    for r in range(O.BROWSE_ROWS):
        for c in (4,):
            assert f'room_{r}_{c}' not in items
    bad = copy.deepcopy(root)
    bad.remove(next(e for e in bad if e.get('name') == 'room_3_5'))
    assert O.runtime_problems(bad, screen)
    bad = copy.deepcopy(root)
    next(e for e in bad if e.get('name') == 'room_3_5').set('usecmd', O.command(24))
    assert O.runtime_problems(bad, screen)
    assert 'room_0_5' in O.DATA_NAMES
