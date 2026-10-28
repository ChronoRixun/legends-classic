"""Rule 46 bits 512 / 1024 (TelekinesisRule, GuardDecideRule), [Game] Xml1FlyingCarry and the LAA DLL gate. Synthetic
metadata only."""
import json
import tempfile
from pathlib import Path

import build_xml1
from xml1build import common as C
from xml1build import exe_flags as EF
from xml1build import fix_ini as FI


def _record(out: Path, grab_carry, **opts):
    meta = out / '_build'
    meta.mkdir(exist_ok=True)
    record = {'build': {key: default for key, (_, default) in build_xml1.CONTENT_OPTS.items()}}
    if grab_carry:
        record['build']['grab_carry'] = grab_carry
    else:
        record['build'].pop('grab_carry')
    for key, value in opts.items():
        if value is None:
            record['build'].pop(key)
        else:
            record['build'][key] = value
    (meta / 'report.json').write_text(json.dumps(record), encoding='utf-8')


def test_tk_guard_written_only_with_grab_carry():
    # beta 8: the telekinesis and the flying carry (080h) and the guard decide (080i: a real Guard press did nothing)
    # were off; telekinesis and the flying carry on by default since 0.5.0-beta.1, the guard decide still off (Owen
    # 10-28, the 082f real-pad check), and each is written only with the grab
    assert FI.TK_GUARD == {'TelekinesisRule': 'xml1', 'GuardDecideRule': 'xml1'}
    assert FI.TELEKINESIS == {'TelekinesisRule': 'xml1'} and FI.GUARD_DECIDE == {'GuardDecideRule': 'xml1'}
    assert FI.FLYING_CARRY_OFF == {'Xml1FlyingCarry': '0'}
    assert all(k in FI.PORT_OWNED['Game'] and k in FI.RELEASE_18_KEYS['Game'] for k in (*FI.TK_GUARD, 'Xml1FlyingCarry'))
    args = build_xml1.parse_args(['--out', '.'])
    assert args.telekinesis == 'xml1' and args.guard_decide == 'off' and args.flying_carry == 'xml1'
    args = build_xml1.parse_args(['--out', '.', '--guard-decide', 'xml1'])
    assert args.telekinesis == 'xml1' and args.guard_decide == 'xml1' and args.flying_carry == 'xml1'
    assert all(build_xml1.CONTENT_OPTS[k] == ((), 'off') for k in ('telekinesis', 'guard_decide', 'flying_carry'))  # an absent record key
    args = build_xml1.parse_args(['--out', '.', '--grab-carry', 'xml2'])         # their defaults follow the grab
    assert args.telekinesis == 'off' and args.guard_decide == 'off' and args.flying_carry == 'off'
    for bad in (['--telekinesis', 'xml1'], ['--guard-decide', 'xml1'], ['--flying-carry', 'xml1']):
        try:
            build_xml1.parse_args(['--out', '.', '--grab-carry', 'xml2', *bad])
        except SystemExit:
            pass
        else:
            raise AssertionError(bad)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        for value in ('xml1', 'xml2', None):
            for tk in ('off', 'xml1', None):
              for gd in ('off', 'xml1', None):
                for fc in ('off', 'xml1', None):
                    _record(out, value, telekinesis=tk, guard_decide=gd, flying_carry=fc)
                    keys = FI.port_keys(out)
                    game, dropped = keys['Game'], FI.dropped_keys(keys).get('Game', [])
                    grab = value == 'xml1'
                    guard = grab and gd == 'xml1'
                    telekinesis = grab and tk == 'xml1'
                    carry_off = grab and fc != 'xml1'
                    assert (game.get('Xml1GrabCarry') == 'xml1') == grab
                    assert (game.get('GuardDecideRule') == 'xml1') == guard and ('GuardDecideRule' in dropped) == (not guard)
                    assert (game.get('TelekinesisRule') == 'xml1') == telekinesis
                    assert ('TelekinesisRule' in dropped) == (not telekinesis)
                    assert (game.get('Xml1FlyingCarry') == '0') == carry_off and ('Xml1FlyingCarry' in dropped) == (not carry_off)
                    merged = FI.merge_text('[Game]\nTelekinesisRule=xml1\nGuardDecideRule=xml1\nXml1FlyingCarry=0\nKeepMe=7\n',
                                           keys, FI.dropped_keys(keys))
                    assert ('TelekinesisRule=xml1' in merged) == telekinesis
                    assert ('GuardDecideRule=xml1' in merged) == guard
                    assert ('Xml1FlyingCarry=0' in merged) == carry_off
                    assert 'KeepMe=7' in merged
                    if value == 'xml1' and tk is None and gd is None and fc is None:
                        # a record without the keys (beta 8's profile): the grab, no telekinesis, no guard decide, carry off
                        assert getattr(C.args_for_out(out), 'telekinesis', 'off') == 'off'
                        assert getattr(C.args_for_out(out), 'guard_decide', 'off') == 'off'
                        assert 'GuardDecideRule' not in game and 'TelekinesisRule' not in game
        # an ini-only option re-runs no module when toggled
        _record(out, 'xml1', telekinesis='off', guard_decide='off', flying_carry='off')
        args = build_xml1.parse_args(['--out', td, '--save-layout', 'retail',          # the record's (CONTENT_OPTS) layout
                                      '--telekinesis', 'xml1', '--guard-decide', 'xml1', '--flying-carry', 'xml1'])
        assert build_xml1.plan_content_opts(out, args, []) == []


def test_flying_carry_dll_gate():
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        keys = {'Game': dict(FI.FLYING_CARRY_OFF)}
        # 080g's DLL: no Xml1FlyingCarry key, it would install the flying carry
        dll.write_bytes(b'MZ' + 'Xml1GrabCarry'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[Game] Xml1FlyingCarry', '[Game] Xml1FlyingCarry (flying carry off)']
        dll.write_bytes(b'MZ' + 'Xml1FlyingCarry'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[Game] Xml1FlyingCarry (flying carry off)']
        dll.write_bytes(b'MZ' + 'Xml1FlyingCarry'.encode('utf-16le') + FI.FLYING_CARRY_OFF_MARKER)
        assert FI.old_fix_keys(dll, keys) == []


def test_tk_guard_dll_gate():
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        keys = {'Game': dict(FI.TK_GUARD)}
        dll.write_bytes(b'MZ' + 'Xml1GrabCarry'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[Game] TelekinesisRule', '[Game] GuardDecideRule',
                                              '[Game] TelekinesisRule (PC audio slot 38)',
                                              '[Game] TelekinesisRule (still throw)', '[Game] GuardDecideRule (tap exit)',
                                              '[Game] TelekinesisRule (throw damage, beta 9)', '[Game] GuardDecideRule (decided at entry, beta 9)',
                                              '[Game] TelekinesisRule (082d: stunned-only ground grab, held telekinesis retry)', '[Game] GuardDecideRule (082d: stunned-only ground grab, held telekinesis retry)',
                                              '[Game] TelekinesisRule (082e: timed-stun guard pickup, TK ownership through power1)', '[Game] GuardDecideRule (082e: timed-stun guard pickup, TK ownership through power1)']
        # 080d's DLL knows both keys but resolves the telekinesis sounds through slot 0x34: refused by marker
        dll.write_bytes(b'MZ' + '\0'.join(FI.TK_GUARD).encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[Game] TelekinesisRule (PC audio slot 38)',
                                              '[Game] TelekinesisRule (still throw)', '[Game] GuardDecideRule (tap exit)',
                                              '[Game] TelekinesisRule (throw damage, beta 9)', '[Game] GuardDecideRule (decided at entry, beta 9)',
                                              '[Game] TelekinesisRule (082d: stunned-only ground grab, held telekinesis retry)', '[Game] GuardDecideRule (082d: stunned-only ground grab, held telekinesis retry)',
                                              '[Game] TelekinesisRule (082e: timed-stun guard pickup, TK ownership through power1)', '[Game] GuardDecideRule (082e: timed-stun guard pickup, TK ownership through power1)']
        # 080e / 080f's DLL: a still telekinesis throw divides zero by zero and a tapped guard never exits
        dll.write_bytes(b'MZ' + '\0'.join(FI.TK_GUARD).encode('utf-16le') + FI.TK_AUDIO_MARKER)
        assert FI.old_fix_keys(dll, keys) == ['[Game] TelekinesisRule (still throw)', '[Game] GuardDecideRule (tap exit)',
                                              '[Game] TelekinesisRule (throw damage, beta 9)', '[Game] GuardDecideRule (decided at entry, beta 9)',
                                              '[Game] TelekinesisRule (082d: stunned-only ground grab, held telekinesis retry)', '[Game] GuardDecideRule (082d: stunned-only ground grab, held telekinesis retry)',
                                              '[Game] TelekinesisRule (082e: timed-stun guard pickup, TK ownership through power1)', '[Game] GuardDecideRule (082e: timed-stun guard pickup, TK ownership through power1)']
        dll.write_bytes(b'MZ' + '\0'.join(FI.TK_GUARD).encode('utf-16le') + FI.TK_AUDIO_MARKER + FI.TK_STILL_MARKER)
        assert FI.old_fix_keys(dll, keys) == ['[Game] GuardDecideRule (tap exit)', '[Game] TelekinesisRule (throw damage, beta 9)', '[Game] GuardDecideRule (decided at entry, beta 9)',
                                              '[Game] TelekinesisRule (082d: stunned-only ground grab, held telekinesis retry)', '[Game] GuardDecideRule (082d: stunned-only ground grab, held telekinesis retry)',
                                              '[Game] TelekinesisRule (082e: timed-stun guard pickup, TK ownership through power1)', '[Game] GuardDecideRule (082e: timed-stun guard pickup, TK ownership through power1)']
        dll.write_bytes(b'MZ' + '\0'.join(FI.TK_GUARD).encode('utf-16le') + FI.TK_AUDIO_MARKER + FI.TK_STILL_MARKER
                        + FI.GUARD_TAP_MARKER)
        # 1.9.0-beta.1 / beta.2 (beta 8): both keys and every beta 8 marker, but beta 9's guard entry and TK arming missing
        assert FI.old_fix_keys(dll, keys) == ['[Game] TelekinesisRule (throw damage, beta 9)', '[Game] GuardDecideRule (decided at entry, beta 9)',
                                              '[Game] TelekinesisRule (082d: stunned-only ground grab, held telekinesis retry)', '[Game] GuardDecideRule (082d: stunned-only ground grab, held telekinesis retry)',
                                              '[Game] TelekinesisRule (082e: timed-stun guard pickup, TK ownership through power1)', '[Game] GuardDecideRule (082e: timed-stun guard pickup, TK ownership through power1)']
        dll.write_bytes(b'MZ' + '\0'.join(FI.TK_GUARD).encode('utf-16le') + FI.TK_AUDIO_MARKER + FI.TK_STILL_MARKER
                        + FI.GUARD_TAP_MARKER + FI.TK_ARMING_MARKER + FI.GUARD_ENTRY_MARKER)
        # 082c (beta 9 round 2): the guard grabs untouched enemies and telekinesis tries its acquisition once
        assert FI.old_fix_keys(dll, keys) == ['[Game] TelekinesisRule (082d: stunned-only ground grab, held telekinesis retry)', '[Game] GuardDecideRule (082d: stunned-only ground grab, held telekinesis retry)',
                                              '[Game] TelekinesisRule (082e: timed-stun guard pickup, TK ownership through power1)', '[Game] GuardDecideRule (082e: timed-stun guard pickup, TK ownership through power1)']
        dll.write_bytes(dll.read_bytes() + FI.TK_GUARD_082D_MARKER)
        # 082d: a timed-stunned enemy is never picked up; a power1-start TK victim can be released by its callback
        assert FI.old_fix_keys(dll, keys) == ['[Game] TelekinesisRule (082e: timed-stun guard pickup, TK ownership through power1)', '[Game] GuardDecideRule (082e: timed-stun guard pickup, TK ownership through power1)']
        dll.write_bytes(dll.read_bytes() + FI.TK_GUARD_082E_MARKER)
        assert FI.old_fix_keys(dll, keys) == []


def test_flying_carry_on_needs_beta9_dll():
    # --flying-carry xml1 leaves Xml1FlyingCarry out (the DLL's flying carry on): beta 8's DLL installs it with 0-damage
    # throws, so the beta 9 carry-throw registration marker is required; with the key written (=0, the default) it is not
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        dll.write_bytes(b'MZ' + 'Xml1GrabCarry'.encode('utf-16le'))
        assert FI.FLYING_CARRY_ON_NAME in FI.old_fix_keys(dll, {'Game': {'Xml1GrabCarry': 'xml1'}})
        assert FI.FLYING_CARRY_ON_NAME not in FI.old_fix_keys(dll, {'Game': {'Xml1GrabCarry': 'xml1', **FI.FLYING_CARRY_OFF}})
        dll.write_bytes(b'MZ' + 'Xml1GrabCarry'.encode('utf-16le') + FI.CARRY_THROW_MARKER)
        assert FI.FLYING_CARRY_ON_NAME not in FI.old_fix_keys(dll, {'Game': {'Xml1GrabCarry': 'xml1'}})


def _pe32(laa: bool) -> bytes:
    data = bytearray(0x200)
    data[:2] = b'MZ'
    data[0x3C:0x40] = (0x80).to_bytes(4, 'little')
    data[0x80:0x84] = b'PE\0\0'
    data[0x84:0x86] = (0x14C).to_bytes(2, 'little')
    data[0x96:0x98] = (0x012F if laa else 0x010F).to_bytes(2, 'little')
    data[0x98:0x9A] = (0x10B).to_bytes(2, 'little')
    return bytes(data)


def test_laa_build_needs_the_address_space_dll():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        dll = out / 'dinput.dll'
        dll.write_bytes(b'MZ old fix')
        assert FI.old_fix_keys(dll, {}) == []                       # no exe beside it: nothing to check
        (out / 'XMen2.exe').write_bytes(b'not a PE')
        assert FI.old_fix_keys(dll, {}) == []
        (out / 'XMen2.exe').write_bytes(_pe32(False))
        assert EF.laa_state((out / 'XMen2.exe').read_bytes()) == 'off'
        assert FI.old_fix_keys(dll, {}) == []                       # --laa off
        (out / 'XMen2.exe').write_bytes(_pe32(True))
        assert EF.laa_state((out / 'XMen2.exe').read_bytes()) == 'on'
        assert FI.old_fix_keys(dll, {}) == ['XMen2.exe large-address-aware (address space guard)']
        dll.write_bytes(b'MZ' + FI.ADDRESS_SPACE_MARKER + b'; top %s')
        assert FI.old_fix_keys(dll, {}) == []
