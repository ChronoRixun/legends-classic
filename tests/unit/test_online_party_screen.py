"""Round-8 Party screen (lc-online-party/1) and the pause-menu rename: invented trees only, no game or network."""
import copy
import xml.etree.ElementTree as ET
from xml1build import online_menus as O, online_fonts as F, online_party as PT, pause_appearance as PA, fix_ini as FI
from test_pause_appearance import native_menu
from test_main_appearance import raises

NATIVE_RAIL = {'lc_rail_team': 'openmenu team', 'lc_rail_options': 'options', 'lc_rail_quit': 'mainmenuexit'}


def pda_with_routes():
    """The invented native PDA with the three rows the rail copies routes from."""
    root = native_menu()
    for name, route in (('label_option02', 'openmenu team'), ('label_option06', 'options'), ('label_option09', 'mainmenuexit')):
        root.find(f"item[@name='{name}']").set('usecmd', route)
    return root


def party(role='host'):
    screen = PT.party_layout(role, native=PT.native_rail_commands(pda_with_routes()))
    return screen, O.menu_tree(screen)


def test_party_probe_is_required_and_old_dlls_are_refused():
    assert PT.PROBE in O.DLL_PROBES
    data = b'\0'.join(O.DLL_PROBES)
    assert not O.capability_problems(data)
    assert O.capability_problems(data.replace(PT.PROBE, b'lc-online-party/0'))
    keys = {'Online': {'Menus': '1'}, 'Game': {'LegendsClassicFonts': '1'}, 'Limits': {'ScriptFunctions': '1024'}}
    FI.check_online_dll(data, keys)
    raises(FI.FixTooOld, lambda: FI.check_online_dll(data.replace(PT.PROBE, b'x'), keys))


def test_party_commands_are_the_exact_manifest_and_the_rail_uses_the_native_routes():
    screen, root = party()
    assert not PT.party_problems(root, screen, NATIVE_RAIL), PT.party_problems(root, screen, NATIVE_RAIL)
    items = {e.get('name'): e for e in root.findall('item')}
    expected = {'lc_rail_resume': 63, 'lc_party_invite': 64, 'lc_party_propose': 65, 'lc_party_leave': 66, 'lc_party_leave_yes': 67,
                'lc_party_kick_yes': 69, 'lc_party_cancel': 8, 'lc_p1_kick': 71, 'lc_p2_kick': 72, 'lc_p3_kick': 73, 'lc_p4_kick': 74}
    assert PT.COMMANDS == expected
    for key, number in expected.items():
        assert items[key].get('usecmd') == O.command(number), key
    for key, route in NATIVE_RAIL.items():
        assert items[key].get('usecmd') == route, key
    assert items['lc_rail_codex'].get('usecmd') == 'runscript codexMenu(0)'
    assert items['lc_rail_party'].get('usecmd') == '' and items['lc_rail_party'].get('neverfocus') == 'false'
    assert items['lc_rail_party'].get('startactive') == 'true'
    scripted = {k for k, e in items.items() if (e.get('usecmd') or '').startswith('runscript lcOnlineIntent(')}
    assert scripted == set(expected)
    # reserved numbers are not public commands, and party numbers exist on lc_party only
    for number in (68, 70, 75):
        raises(ValueError, lambda n=number: O.command(n))
    for name in O.MENUS:
        hub = O.runtime_layout(name)
        bad = O.menu_tree(hub)
        ET.SubElement(bad, 'item', name='x', type='MENU_ITEM_TEXT', text='x', usecmd=O.command(66))
        assert any('outside lc_party' in p for p in O.runtime_problems(bad, hub)), name


def test_party_rail_routes_come_from_the_native_tree_and_a_missing_route_is_a_build_error():
    assert PT.native_rail_commands(pda_with_routes()) == NATIVE_RAIL
    native = pda_with_routes()
    native.find("item[@name='label_option09']").attrib.pop('usecmd')
    raises(ValueError, lambda: PT.native_rail_commands(native))
    native = pda_with_routes()
    native.find("item[@name='label_option06']").set('usecmd', O.command(7))
    raises(ValueError, lambda: PT.native_rail_commands(native))
    screen, root = party()
    bad = copy.deepcopy(root)
    next(e for e in bad if e.get('name') == 'lc_rail_quit').set('usecmd', 'openmenu main')
    assert PT.party_problems(bad, screen, NATIVE_RAIL)


def test_party_validator_catches_mutations():
    screen, root = party()
    for key in ('lc_party_invite', 'lc_party_confirm_leave_host', 'lc_p3_phase', 'lc_notice_name', 'lc_party_propose_host_only', 'lc_p2_kick'):
        bad = copy.deepcopy(root)
        bad.remove(next(e for e in bad if e.get('name') == key))
        assert PT.party_problems(bad, screen, NATIVE_RAIL), key
    for key, attr, value in (('lc_party_invite', 'usecmd', O.command(65)), ('lc_party_leave', 'usecmd', 'openmenu online'),
                             ('lc_party_confirm_kick', 'hide', 'false'), ('lc_p4_kick', 'hide', 'false'),
                             ('lc_party_propose', 'enabled', 'true'), ('lc_p1_phase', 'gamevar', 'x'),
                             ('lc_rail_party', 'usecmd', O.command(66)), ('lc_party_cancel', 'usecmd', O.command(6))):
        bad = copy.deepcopy(root)
        next(e for e in bad if e.get('name') == key).set(attr, value)
        assert PT.party_problems(bad, screen, NATIVE_RAIL), (key, attr)
    bad = copy.deepcopy(root)
    bad.set('menu_cancel', O.command(6))   # a second Back: the DLL routes Back, exactly once
    assert PT.party_problems(bad, screen, NATIVE_RAIL)
    bad = copy.deepcopy(root)
    ET.SubElement(bad, 'item', name='label_option07', type='MENU_ITEM_TEXT', text='x')
    assert PT.party_problems(bad, screen, NATIVE_RAIL)


def test_party_screen_fits_its_budgets_and_every_copy_fits_its_field():
    metrics = F.metrics()
    for role in ('host', 'guest'):
        for kw in ({}, {'fixture': True, 'notice': 'lc_party_receiving', 'confirm': 'lc_party_confirm_kick', 'copied': 'lc_party_copied'}):
            screen = PT.party_layout(role, **kw)
            assert not O.layout_problems(screen), (role, O.layout_problems(screen))
            bounded = O.bound_layout(screen, metrics)
            assert [e['text'] for e in screen['items']] == [e['text'] for e in bounded['items']], (role, 'ellipsized')
            assert len(O.scene_layout(bounded)) <= 256


def test_party_scene_parts_text_fits_without_ellipsis():
    metrics = F.metrics()

    def width(style, text):
        role, scale, _ = O.font_binding({'name': 'probe', 'style': style, 'rect': (0, 0, 1, 1)})
        glyphs = metrics['lc_' + role]
        return sum(float(glyphs.get(ord(c), glyphs.get(63))['horizadvance']) for c in text) * scale
    for e in PT.party_layout('host', fixture=True)['items']:
        for part in e.get('parts', []):
            if 'text' in part:
                assert width(part.get('style', 'body'), part['text']) <= part['rect'][2] * .8, (e['name'], part['text'])


def test_party_selection_shows_kick_to_the_host_only_for_other_admitted_members():
    roster = [dict(name='Logan', host=True, phase='playing'), dict(name='Kitty', phase='playing', rtt=41, route='direct'),
              dict(name='Alex', phase='waiting for next area', build='checking'), dict(name='Sam', pending=True, phase='connecting')]
    shown, texts, kicks = PT.party_selection('host', roster=roster, local=0)
    assert kicks == [2, 3] and shown['lc_p2_kick'] and shown['lc_p3_kick'] and not shown['lc_p1_kick'] and not shown['lc_p4_kick']
    assert shown['lc_party_propose_soon'] and not shown['lc_party_propose_host_only']
    assert shown['lc_p3_hero_next'] and not shown['lc_p3_hero_fallback'] and shown['lc_p4_pending']
    shown, texts, kicks = PT.party_selection('guest', roster=roster, local=1)
    assert kicks == [] and not any(shown[f'lc_p{n}_kick'] for n in range(1, 5))
    assert shown['lc_party_propose_host_only'] and not shown['lc_party_propose_soon']
    assert shown['lc_p2_you'] and not shown['lc_p1_you'] and texts['lc_p2_ping'] == ''      # own card: no RTT
    # a host with a confirmation open offers no second kick
    shown, texts, kicks = PT.party_selection('host', roster=roster, local=0, confirm='lc_party_confirm_kick')
    assert kicks == [] and shown['lc_party_confirm_kick']


def test_party_leave_confirms_with_the_role_copy_and_departs_once():
    host = PT.PartyFixture('host')
    host.dispatch('party-leave')
    assert host.confirm == 'lc_party_confirm_leave_host' and PT.CONFIRM_COPY[host.confirm][0] == 'End for everyone?'
    host.dispatch('dismiss')
    assert not host.confirm and not host.departures
    host.dispatch('party-leave'); host.dispatch('party-leave-yes'); host.dispatch('party-leave-yes')
    assert host.departures == [('end', 1)]
    guest = PT.PartyFixture('guest', local=2)
    guest.dispatch('party-leave-yes')                                  # no confirmation open: nothing
    assert not guest.departures
    guest.dispatch('party-leave')
    assert guest.confirm == 'lc_party_confirm_leave_guest'
    guest.dispatch('party-leave-yes'); guest.dispatch('party-leave-yes')
    assert guest.departures == [('leave', 1)]
    other = PT.PartyFixture('host'); other.dispatch('party-propose'); other.dispatch('party-resume')
    assert not other.departures and other.confirm == '' and other.resumed == 1


def test_party_kick_refuses_self_host_spoof_and_stale_targets_and_removes_once():
    f = PT.PartyFixture('host')
    for card in (1, 5):                                                # the host's own card / out of range
        f.dispatch(f'party-kick:{card}')
        assert not f.confirm, card
    f.dispatch('party-kick-yes')
    assert not f.departures                                            # a Yes without a chosen target does nothing
    f.dispatch('party-kick:2')
    assert f.confirm == 'lc_party_confirm_kick' and f.target == (2, 1)
    f.dispatch('party-kick:3')
    assert f.target == (2, 1)                                          # a second pick cannot retarget an open confirmation
    f.generation += 1                                                  # the roster changed under the confirmation: stale
    f.dispatch('party-kick-yes')
    assert not f.departures and len(f.roster) == 4 and not f.confirm
    f.dispatch('party-kick:2'); f.dispatch('party-kick-yes'); f.dispatch('party-kick-yes')
    assert [d[0] for d in f.departures] == [2] and len(f.roster) == 3
    g = PT.PartyFixture('guest', local=1)
    g.dispatch('party-kick:3'); g.dispatch('party-kick-yes')
    assert not g.confirm and not g.departures and len(g.roster) == 4  # a guest's kick intent is ignored
    me = PT.PartyFixture('host', roster=[dict(name='Logan', host=True), dict(name='Me'), dict(name='Kit')], local=1)
    me.dispatch('party-kick:2')
    assert not me.confirm                                              # never the local card
    pending = PT.PartyFixture('host', roster=[dict(name='Logan', host=True), dict(name='Kit', pending=True)])
    pending.dispatch('party-kick:2')
    assert not pending.confirm                                         # a broker-only member has no native row to remove


def test_party_screen_never_borrows_the_old_players_row_or_a_second_back():
    screen, root = party()
    names = {e.get('name') for e in root.iter('item')}
    assert not [n for n in names if 'label_option' in n] and PA.PLAYERS_ROW not in ET.tostring(root, encoding='unicode')
    assert root.get('menu_cancel') is None and root.get('type') is None and root.get('igb') == 'lc_party'
    assert not [e for e in root.iter('item') if (e.get('usecmd') or '') == 'openmenu lc_party']


# ------------------------------------------------------------------------------------------------ the pause rename
def test_pause_players_row_is_renamed_with_both_halves_closed_and_the_old_name_gone():
    native = native_menu()
    for half in (native, copy.deepcopy(native)):
        root = PA.pause_tree(half, party_link=True)
        assert not PA.party_link_problems(half, root), PA.party_link_problems(half, root)
        assert not PA.native_text_problems(half, root, PA.party_link_contract())
        items = {e.get('name'): e for e in root.findall('item')}
        assert PA.PLAYERS_ROW not in items and PA.PARTY_LINK in items
        assert items[PA.PARTY_LINK].get('usecmd') == 'openmenu lc_party' and items[PA.PARTY_LINK].get('text') == 'Party'
        assert PA.PLAYERS_ROW not in ET.tostring(root, encoding='unicode')
        current, seen = PA.rows(True)[0], []
        while current not in seen:
            seen.append(current)
            nxt = items[current].get('down')
            assert items[nxt].get('up') == current
            current = nxt
        assert tuple(seen) == PA.rows(True) and current == PA.rows(True)[0]
        # the focus models keep the native slot names
        assert [(c.get('item'), c.get('type')) for c in items[PA.PARTY_LINK].findall('onfocus')] == [('option07_focus', 'focus'), ('option07_focus', 'nofocus')]
        # every other native route/mode/text is untouched
        for old in native.findall('item'):
            if old.get('name') in PA.ROWS and old.get('name') != PA.PLAYERS_ROW:
                assert items[old.get('name')].get('usecmd') == old.get('usecmd') and items[old.get('name')].get('text') == old.get('text')


def test_pause_without_the_online_build_keeps_the_native_players_row_exactly():
    native = native_menu()
    off = PA.pause_tree(native)
    assert ET.tostring(off) == ET.tostring(PA.pause_tree(native, party_link=False))
    assert PA.PARTY_LINK not in ET.tostring(off, encoding='unicode') and off.find(f"item[@name='{PA.PLAYERS_ROW}']") is not None
    assert not PA.native_text_problems(native, off) and PA.rows(False) == PA.ROWS
    assert PA.party_link_problems(native, off)      # the online validator would refuse an un-renamed pause


def test_pause_native_text_check_stays_strict_without_the_explicit_contract_and_catches_extra_changes():
    native = native_menu()
    root = PA.pause_tree(native, party_link=True)
    assert PA.native_text_problems(native, root)    # no contract: the rename is a native-text violation
    for key, attr in (('label_option02', 'text'), ('label_option09', 'desctext2'), (None, 'desctext1'), ('players_help', 'text')):
        bad = copy.deepcopy(root)
        target = bad if key is None else bad.find(f"item[@name='{key}']")
        target.set(attr, 'Changed')
        assert PA.native_text_problems(native, bad, PA.party_link_contract()), (key, attr)
    for text in ('Players', 'PARTY', '', None):
        bad = copy.deepcopy(root)
        link = bad.find(f"item[@name='{PA.PARTY_LINK}']")
        if text is None:
            link.attrib.pop('text')
        else:
            link.set('text', text)
        assert PA.native_text_problems(native, bad, PA.party_link_contract()), text


def test_pause_rename_validator_catches_leftovers_wrong_route_and_a_missing_rename():
    native = native_menu()
    good = PA.pause_tree(native, party_link=True)
    bad = copy.deepcopy(good)
    ET.SubElement(bad, 'item', name=PA.PLAYERS_ROW, text='Invented 6', usecmd='synth_action_6', mode='0 2')
    assert PA.party_link_problems(native, bad) or PA.native_text_problems(native, bad, PA.party_link_contract())
    assert PA.native_text_problems(native, bad, PA.party_link_contract())
    bad = copy.deepcopy(good)
    bad.find(f"item[@name='{PA.PARTY_LINK}']").set('usecmd', 'openmenu players')
    assert PA.party_link_problems(native, bad)
    bad = copy.deepcopy(good)
    bad.find("item[@name='label_option06']").set('down', PA.PLAYERS_ROW)       # a dangling reference to the old name
    assert PA.party_link_problems(native, bad)
    bad = copy.deepcopy(good)
    bad.find(f"item[@name='{PA.PARTY_LINK}']").set('mode', '0')
    assert PA.party_link_problems(native, bad)
    assert PA.party_link_problems(native, PA.pause_tree(native))               # online on but nothing renamed
    gone = native_menu()
    gone.remove(gone.find(f"item[@name='{PA.PLAYERS_ROW}']"))
    raises(ValueError, lambda: PA.pause_tree(gone, party_link=True))


def test_classic_pause_validator_knows_the_party_rename():
    from test_pause_appearance import validator_fixture
    from xml1build import validate_frontend as V
    from xml1build.validate import Check
    validator, trees = validator_fixture(party=True)
    ck = Check('V-TBD', 'classic pause')
    V.v_classic_pause(validator, ck)
    assert not ck.errors, ck.errors
    item = next(e for e in trees['UI/menus/pda.engb'] if e.get('name') == PA.PARTY_LINK)
    item.set('usecmd', 'openmenu online')
    ck = Check('V-TBD', 'classic pause')
    V.v_classic_pause(validator, ck)
    assert any(PA.PARTY_LINK in error for error in ck.errors)
    validator, trees = validator_fixture(party=False)       # online off: the unchanged native row passes
    ck = Check('V-TBD', 'classic pause')
    V.v_classic_pause(validator, ck)
    assert not ck.errors, ck.errors


def test_pause_scene_retires_the_native_anchors_not_the_renamed_item():
    # Found by the owned-input build: retiring the aliased names asked the retail scene for an anchor lc_party_link that it
    # never had ("scene alias needs a transform"); the OFF selftest then showed the retired table must stay byte-identical
    # to the original (label, slot, slot focus per row, then the description anchors).
    retired = PA.retired_native_anchors()
    assert PA.PLAYERS_ROW in retired and PA.PARTY_LINK not in retired and 'debug_text' in retired
    assert set(PA.ROWS) <= set(retired) and {'desctext1', 'desctext2', 'option07', 'option07_focus'} <= set(retired)
    assert len(retired) == len(set(retired)) == 3 * (len(PA.ROWS) + 1) + 2
    assert retired[:3] == ['label_option01', 'option01', 'option01_focus'] and retired[-2:] == ['desctext1', 'desctext2']


def test_party_validator_uses_the_builds_palette_ids():
    # Found by the owned-input build: the colour prefixes carry the build's allocated palette ids, not 0..7.
    ids = {i: 40 + i for i in range(8)}
    screen = PT.party_layout('host', native=NATIVE_RAIL)
    root = O.menu_tree(screen, ids)
    assert not PT.party_problems(root, screen, NATIVE_RAIL, ids), PT.party_problems(root, screen, NATIVE_RAIL, ids)
    assert PT.party_problems(root, screen, NATIVE_RAIL)           # default ids disagree with this tree
