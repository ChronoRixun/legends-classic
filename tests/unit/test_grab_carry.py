"""Rule 45 ground-grab switch. Synthetic metadata only; no game inputs."""
import json
import tempfile
from pathlib import Path

import build_xml1
from xml1build import common as C
from xml1build import fix_ini as FI


def test_grab_carry_option_and_ini_coupled_with_stale_key_removal():
    assert build_xml1.parse_args(['--out', '.']).grab_carry == 'xml2'
    assert build_xml1.parse_args(['--out', '.', '--grab-carry', 'xml1']).grab_carry == 'xml1'
    assert build_xml1.CONTENT_OPTS['grab_carry'] == ('characters', 'xml2')
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        meta = out / '_build'
        meta.mkdir()
        for value in ('xml1', 'xml2', None):
            record = {'build': {key: default for key, (_, default) in build_xml1.CONTENT_OPTS.items()}}
            if value:
                record['build']['grab_carry'] = value
            else:
                record['build'].pop('grab_carry')
            (meta / 'report.json').write_text(json.dumps(record), encoding='utf-8')
            keys = FI.port_keys(out)
            assert (keys['Game'].get('Xml1GrabCarry') == 'xml1') == (value == 'xml1')
            assert ('Xml1GrabCarry' in FI.dropped_keys(keys).get('Game', [])) == (value != 'xml1')
            assert getattr(C.args_for_out(out), 'grab_carry', None) == value
            merged = FI.merge_text('[Game]\nXml1GrabCarry=xml1\nKeepMe=7\n', keys, FI.dropped_keys(keys))
            assert ('Xml1GrabCarry=xml1' in merged) == (value == 'xml1')
            assert 'KeepMe=7' in merged
            args = build_xml1.parse_args(['--out', td, '--grab-carry', 'xml2' if value == 'xml1' else 'xml1'])
            assert 'characters' in build_xml1.plan_content_opts(out, args, [])


def test_grab_carry_default_ini_bytes_equal_legacy_report():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        meta = out / '_build'
        meta.mkdir()
        record = {'build': {key: default for key, (_, default) in build_xml1.CONTENT_OPTS.items()}}
        record['build'].pop('grab_carry')
        report = meta / 'report.json'
        report.write_text(json.dumps(record), encoding='utf-8')
        old_keys = FI.port_keys(out)
        old = FI.merge_text('[Game]\nKeepMe=7\n', old_keys, FI.dropped_keys(old_keys))
        record['build']['grab_carry'] = 'xml2'
        report.write_text(json.dumps(record), encoding='utf-8')
        keys = FI.port_keys(out)
        new = FI.merge_text('[Game]\nKeepMe=7\n', keys, FI.dropped_keys(keys))
        assert old.encode('utf-8') == new.encode('utf-8')


def test_grab_carry_refuses_companion_without_requested_key_only():
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        dll.write_bytes(b'MZ' + 'Xml1RogueDecide'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, {'Game': {'Xml1GrabCarry': 'xml1'}}) == ['[Game] Xml1GrabCarry']
        assert FI.old_fix_keys(dll, {'Game': {}}) == []
        dll.write_bytes(b'MZ' + 'Xml1GrabCarry'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, {'Game': {'Xml1GrabCarry': 'xml1'}}) == []
