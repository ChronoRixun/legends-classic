"""0.6 preview fix L (060r live failures 5, 6, 7): copy, lobby cards and presentation. Invented trees only; no game, network or desktop."""
import xml.etree.ElementTree as ET
from xml1build import online_menus as O


def _tree(name):
    screen = O.runtime_layout(name)
    return screen, O.menu_tree(screen), {e.get('name'): e for e in O.menu_tree(screen).findall('item')}


def _styles(colors=None, styles=None):
    colors = colors if colors is not None else ET.Element('colors')
    styles = styles if styles is not None else ET.Element('styles')
    for i in range(40):
        ET.SubElement(colors, 'color', id=str(i), value='0.%d 0 0 1' % (i % 10 + 1))
    _, table, _ = O.theme(colors, styles)
    return {e.get('name'): e for e in table}


# --- failure 5: Host with the service down ------------------------------------------------------------------------------------------
def test_the_service_that_never_answered_has_its_own_notice_and_is_only_authored_where_it_can_show():
    assert O.NOTICE_TEXT['lc_notice_service_silent'] == 'The online service did not answer. Try again.'
    assert O.NOTICE_TEXT['lc_notice_service_silent'] != O.NOTICE_TEXT['lc_notice_service_lost']  # nothing was lost: no room existed yet
    assert 'lost' not in O.NOTICE_TEXT['lc_notice_service_silent'].lower()
    assert 'lc_notice_service_silent' in O.BROWSE_UNREACHABLE_NOTICES  # Browse never opens a room: no anchor spent there (174 of 175)
    for name in O.MENUS:
        _, _, items = _tree(name)
        if name == 'lc_browse':
            assert 'lc_notice_service_silent' not in items
            continue
        node = items['lc_notice_service_silent']
        assert node.get('hide') == 'true' and node.get('type') == 'MENU_ITEM_TEXT' and O._plain(node.get('text')) == O.NOTICE_TEXT['lc_notice_service_silent'], name


# --- failure 6: header / campaign line / badge ---------------------------------------------------------------------------------------
def test_no_lobby_text_says_pending_where_the_dll_names_the_room_and_the_badge_word_fits_its_field():
    for role in O.LOBBIES:
        items = {e['name']: e for e in O.lobby_layout(role)['items']}
        assert 'pending' not in items['lc_room_name']['text'].lower() and 'pending' not in items['lc_campaign_summary']['text'].lower(), role
        assert 'next area' in items['lc_campaign_summary']['text']
    guest = {e['name']: e for e in O.lobby_layout('join')['items']}['lc_campaign_summary']['text']
    assert 'host' in guest  # the guest does not choose the campaign
    # 060r live: "Room connected" did not fit the 67-unit badge field ("Room connecte"). The DLL binds ROOM_BADGE_TEXT (pinned there).
    assert O.ROOM_BADGE_TEXT == 'In a room'
    longest_that_fit = 'Not connected'  # the longest word the field has always held
    assert len(O.ROOM_BADGE_TEXT) <= len(longest_that_fit)
    for name in ('lc_host', 'lc_code', 'lc_browse'):
        raw = {e['name']: e for e in O.runtime_layout(name)['items']}
        assert raw['self_state']['rect'][2] == 67


# --- failure 7: pale text on amber -----------------------------------------------------------------------------------------------------
def test_no_style_a_focus_bar_can_sit_under_blends_toward_green_or_blue_and_every_palette_entry_stays_allocated():
    styles = _styles()
    palette = {i: None for i in range(8)}
    for role in ('row', 'body', 'label'):
        s = styles['lc_o_' + role]
        assert s.get('color_highlight') == s.get('color_focus'), (role, 'a focused item must stay navy')
    # the two never-focused alias styles keep green (6) and blue (2) allocated
    assert styles['lc_o_compact_title'].get('color_highlight') != styles['lc_o_compact_title'].get('color_focus')
    assert styles['lc_o_card_name'].get('color_highlight') != styles['lc_o_card_name'].get('color_focus')
    used = set()
    for e in styles.values():
        if e.get('name', '').startswith('lc_o_'):
            used |= {e.get(k) for k in ('color_nofocus', 'color_focus', 'color_highlight', 'color_disabled')}
    assert len(used) >= 7  # all eight online colours are referenced (equal values share one native id)
    del palette


def test_focusable_labels_at_the_styles_resting_colour_carry_no_inline_colour_that_would_beat_the_focus_colour():
    # 060r live: Next page / Previous page were authored colour 3 (the label style's own resting colour) and got a ~NN prefix, which wins over
    # the style's focus colour: pale blue on their own amber bar.
    _, _, items = _tree('lc_browse')
    for key in ('scroll', 'scroll_up'):
        assert not items[key].get('text').startswith('~'), key
    for name in O.MENUS:
        _, _, items = _tree(name)
        assert not items['retry'].get('text').startswith('~')
    # a deliberate colour still travels with the item (the white OPEN bar's navy label, the status words)
    _, _, host = _tree('lc_host')
    assert host['open'].get('text').startswith('~')


def test_the_host_setup_side_marker_follows_the_focused_row_instead_of_being_baked_beside_campaign():
    fixture = O.layout('lc_host')
    assert any(q['kind'] == 'slash' and q['rect'] == (31, 248, 4, 45) for q in fixture['shapes'])  # the design preview keeps its baked marker
    screen = O.runtime_layout('lc_host')
    assert not [q for q in screen['shapes'] if q['kind'] == 'slash' and q['rect'][0] == 31]
    markers = {e['name']: e for e in screen['items'] if e['name'].startswith('lc_host_marker_')}
    assert set(markers) == {'lc_host_marker_visibility', 'lc_host_marker_room_name', 'lc_host_marker_campaign'}
    raw = {e['name']: e for e in screen['items']}
    for key, e in markers.items():
        assert e['hidden'] and e['variant'] and e['parts'] and not e['intent'], key
    # each sits beside its own settings row (the campaign one exactly where the design bakes it)
    assert markers['lc_host_marker_campaign']['rect'][1] == 248
    assert markers['lc_host_marker_visibility']['rect'][1] < markers['lc_host_marker_room_name']['rect'][1] < 248
    _, _, items = _tree('lc_host')
    for key in markers:
        assert items[key].get('type') == 'MENU_ITEM_MODEL' and items[key].get('hide') == 'true' and items[key].get('neverfocus') == 'true'
    # the DLL's focus -> marker table names the rows the Host screen can focus
    for focusable in ('visibility', 'room_name', 'edit_room', 'campaign'):
        assert raw[focusable]['intent'], focusable
    assert not raw['drop_in']['intent']  # read-only: never focused, so no marker


def test_the_unselected_visibility_chip_is_a_navy_chip_not_pale_text_on_the_amber_bar():
    screen = O.runtime_layout('lc_host')
    for key in ('lc_host_private', 'lc_host_public'):
        parts = next(e for e in screen['items'] if e['name'] == key)['parts']
        rects = [p for p in parts if p.get('kind') == 'rect']
        assert [p['color'] for p in rects] == [4, 0], key  # the selected chip white, the other filled navy (its pale outline / text unchanged)
