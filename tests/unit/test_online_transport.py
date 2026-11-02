"""[Online] Transport=gns comes with the new online screens (Menus=1), never without them; rebuilds are idempotent.
Invented folders and a synthetic DLL only: no game, network or desktop."""
import os
from pathlib import Path

import unittest

from xml1build import fix_ini as FI, online_menus as O

MENUS = {'Online': {'JoinInProgress': '1', 'LateJoin': '1', **FI.online_menus_keys()},
         'Game': {'LegendsClassicFonts': '1'}, 'Limits': {'ScriptFunctions': '1024'}}
PLAIN = {'Online': {'JoinInProgress': '1', 'LateJoin': '1'}, 'Game': {'Xtract': '0'}}


def folder(out, ini=None):
    """a build folder with a DLL that has every capability these keys need (online menus, LateJoin policy, key names)"""
    out.mkdir()
    names = {k for keys in (MENUS, PLAIN) for values in keys.values() for k in values}
    dll = b'\0'.join(O.DLL_PROBES) + b'\0LateJoinPolicyV1\0' + b''.join(n.encode('utf-16le') + b'\0\0' for n in names)
    (out / 'dinput.dll').write_bytes(dll)
    if ini is not None:
        (out / 'xml2-fix.ini').write_bytes(ini)
    return out


def online(out):
    """[Online] of the folder's ini, key names lower-cased (GetPrivateProfileString matches them in any case)"""
    values = next((v for s, v in FI.read_ini(out / 'xml2-fix.ini').items() if s.lower() == 'online'), {})
    return {k.lower(): v for k, v in values.items()}


def test_online_menus_bring_the_gns_transport_and_nothing_else_does():
    assert FI.online_menus_keys() == {'Menus': '1', 'Transport': 'gns'}
    assert FI.ONLINE_TRANSPORT == 'gns'
    assert 'Transport' in FI.PORT_OWNED['Online'] and 'Transport' in FI.port_owned()['Online']
    assert 'Transport' not in FI.online_keys(port_identity=True, balance=False)   # every port build: no transport
    assert 'Transport' not in FI.online_keys(port_identity=False)


def test_new_ini_gets_transport_gns_with_the_menus(tmp_path):
    out = folder(tmp_path / 'b')
    FI.write_port_keys(out, MENUS)
    values = online(out)
    assert values['menus'] == '1' and values['transport'] == 'gns'
    assert (out / 'xml2-fix.ini').read_bytes().count(b'Transport=') == 1


def test_rebuild_over_an_old_ini_without_the_key_adds_it_and_keeps_the_player_keys(tmp_path):
    old = b'[Display]\r\nMode=borderless\r\n\r\n[Online]\r\nMenus=1\r\nLateJoin=0\r\nJoinHoldSeconds=12\r\nServer=127.0.0.1\r\n'
    out = folder(tmp_path / 'b', old)
    FI.write_port_keys(out, MENUS)
    raw = (out / 'xml2-fix.ini').read_bytes()
    values = online(out)
    assert values['transport'] == 'gns' and values['menus'] == '1'
    assert values['latejoin'] == '0'                          # the one kept [Online] player choice (keep_player_late_join)
    assert values['joinholdseconds'] == '12' and values['server'] == '127.0.0.1'   # not port-owned: untouched
    assert raw.startswith(b'[Display]\r\nMode=borderless\r\n') and b'\n' not in raw.replace(b'\r\n', b'')


def test_rebuild_over_an_ini_with_the_key_is_idempotent(tmp_path):
    out = folder(tmp_path / 'b')
    FI.write_port_keys(out, MENUS)
    first = (out / 'xml2-fix.ini').read_bytes()
    FI.write_port_keys(out, MENUS)
    assert (out / 'xml2-fix.ini').read_bytes() == first
    assert not FI.merge_ini(out / 'xml2-fix.ini', MENUS, FI.dropped_keys(MENUS))   # nothing left to change
    for n, spelled in enumerate((b'transport = GNS', b'Transport=gns')):  # an existing key in any spelling: set in place, once
        other = folder(tmp_path / f'c{n}', b'[Online]\r\nMenus=1\r\n' + spelled + b'\r\n')
        FI.write_port_keys(other, MENUS)
        raw = (other / 'xml2-fix.ini').read_bytes()
        assert raw.lower().count(b'transport') == 1 and online(other)['transport'] == 'gns'


def test_port_owned_rule_replaces_another_value_and_menus_off_drops_it(tmp_path):
    out = folder(tmp_path / 'b', b'[Online]\r\nMenus=1\r\nTransport=native\r\n')
    FI.write_port_keys(out, MENUS)
    assert online(out)['transport'] == 'gns'                  # the menus cannot run on another transport
    FI.write_port_keys(out, PLAIN)                            # rebuilt with --online-menus off
    values = online(out)
    assert 'transport' not in values and 'menus' not in values and values['latejoin'] == '1'


def test_built_output_ini_has_the_transport_with_the_menus():
    """The BUILT output (XML1_BUILT_OUT): a Menus=1 player INI must carry Transport=gns (release round 7 blocker)."""
    out = os.environ.get('XML1_BUILT_OUT')
    if not out or not (Path(out) / 'xml2-fix.ini').is_file():
        raise unittest.SkipTest('no built output (set XML1_BUILT_OUT)')
    values = online(Path(out))
    if values.get('menus') != '1':
        raise unittest.SkipTest('built without the online menus')
    assert values.get('transport', '').lower() == 'gns', values
