"""Character sound headroom accompanies XML1's expanded animation cache (rule 49)."""
import json
import tempfile
from pathlib import Path
from xml1build import fix_ini as FI


def test_char_sounds_follows_anim_enums_and_drops_on_off_rebuild():
    assert 'CharSounds' in FI.PORT_OWNED['Limits']
    assert 'CharSounds' in FI.RELEASE_18_KEYS['Limits']
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        (out / '_build').mkdir()
        for value in ('xml1', 'off', None):
            record = {'build': {'anim_enums': value}} if value else {'build': {}}
            (out / '_build/report.json').write_text(json.dumps(record), encoding='utf-8')
            keys = FI.port_keys(out)
            assert (keys['Limits'].get('CharSounds') == '127') == (value == 'xml1')
            assert ('CharSounds' in FI.dropped_keys(keys).get('Limits', [])) == (value != 'xml1')
            merged = FI.merge_text('[Limits]\nCharSounds=127\nKeep=7\n', keys, FI.dropped_keys(keys))
            assert ('CharSounds=127' in merged) == (value == 'xml1')
            assert 'Keep=7' in merged


def test_char_sounds_dll_gate_requires_key_and_rule49_marker():
    keys = {'Limits': {'CharSounds': '127'}}
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        assert FI.old_fix_keys(dll, keys) == []
        dll.write_bytes(b'MZ')
        assert FI.old_fix_keys(dll, keys) == ['[Limits] CharSounds', '[Limits] CharSounds (rule 49)']
        dll.write_bytes(b'MZ' + 'CharSounds'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[Limits] CharSounds (rule 49)']
        dll.write_bytes(b'MZ' + 'CharSounds'.encode('utf-16le') + FI.CHAR_SOUNDS_MARKER)
        assert FI.old_fix_keys(dll, keys) == []
        assert FI.old_fix_keys(dll, {'Limits': {}}) == []
