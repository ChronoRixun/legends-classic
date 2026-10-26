"""Rule 46 bits 512 / 1024 (TelekinesisRule, GuardDecideRule) and the LAA DLL gate. Synthetic metadata only."""
import json
import tempfile
from pathlib import Path

import build_xml1
from xml1build import exe_flags as EF
from xml1build import fix_ini as FI


def _record(out: Path, grab_carry):
    meta = out / '_build'
    meta.mkdir(exist_ok=True)
    record = {'build': {key: default for key, (_, default) in build_xml1.CONTENT_OPTS.items()}}
    if grab_carry:
        record['build']['grab_carry'] = grab_carry
    else:
        record['build'].pop('grab_carry')
    (meta / 'report.json').write_text(json.dumps(record), encoding='utf-8')


def test_tk_guard_written_only_with_grab_carry():
    assert FI.TK_GUARD == {'TelekinesisRule': 'xml1', 'GuardDecideRule': 'xml1'}
    assert all(k in FI.PORT_OWNED['Game'] and k in FI.RELEASE_18_KEYS['Game'] for k in FI.TK_GUARD)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        for value in ('xml1', 'xml2', None):
            _record(out, value)
            keys = FI.port_keys(out)
            for k in FI.TK_GUARD:
                assert (keys['Game'].get(k) == 'xml1') == (value == 'xml1')
                assert (k in FI.dropped_keys(keys).get('Game', [])) == (value != 'xml1')
            merged = FI.merge_text('[Game]\nTelekinesisRule=xml1\nGuardDecideRule=xml1\nKeepMe=7\n', keys,
                                   FI.dropped_keys(keys))
            assert ('TelekinesisRule=xml1' in merged) == (value == 'xml1')
            assert ('GuardDecideRule=xml1' in merged) == (value == 'xml1')
            assert 'KeepMe=7' in merged


def test_tk_guard_dll_gate():
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        keys = {'Game': dict(FI.TK_GUARD)}
        dll.write_bytes(b'MZ' + 'Xml1GrabCarry'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[Game] TelekinesisRule', '[Game] GuardDecideRule',
                                              '[Game] TelekinesisRule (PC audio slot 38)',
                                              '[Game] TelekinesisRule (still throw)', '[Game] GuardDecideRule (tap exit)']
        # 080d's DLL knows both keys but resolves the telekinesis sounds through slot 0x34: refused by marker
        dll.write_bytes(b'MZ' + '\0'.join(FI.TK_GUARD).encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[Game] TelekinesisRule (PC audio slot 38)',
                                              '[Game] TelekinesisRule (still throw)', '[Game] GuardDecideRule (tap exit)']
        # 080e / 080f's DLL: a still telekinesis throw divides zero by zero and a tapped guard never exits
        dll.write_bytes(b'MZ' + '\0'.join(FI.TK_GUARD).encode('utf-16le') + FI.TK_AUDIO_MARKER)
        assert FI.old_fix_keys(dll, keys) == ['[Game] TelekinesisRule (still throw)', '[Game] GuardDecideRule (tap exit)']
        dll.write_bytes(b'MZ' + '\0'.join(FI.TK_GUARD).encode('utf-16le') + FI.TK_AUDIO_MARKER + FI.TK_STILL_MARKER)
        assert FI.old_fix_keys(dll, keys) == ['[Game] GuardDecideRule (tap exit)']
        dll.write_bytes(b'MZ' + '\0'.join(FI.TK_GUARD).encode('utf-16le') + FI.TK_AUDIO_MARKER + FI.TK_STILL_MARKER
                        + FI.GUARD_TAP_MARKER)
        assert FI.old_fix_keys(dll, keys) == []


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
