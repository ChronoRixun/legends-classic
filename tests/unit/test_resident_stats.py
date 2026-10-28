"""ResidentStats headroom accompanies the XML1 animation/sound cache limits (rule 50)."""
import json
import tempfile
from pathlib import Path
from xml1build import fix_ini as FI


def test_resident_stats_follows_xml1_animation_limits_and_drops_on_off_rebuild():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        (out / '_build').mkdir()
        for value in ('xml1', 'off', None):
            record = {'build': {'anim_enums': value}} if value else {'build': {}}
            (out / '_build/report.json').write_text(json.dumps(record), encoding='utf-8')
            keys = FI.port_keys(out)
            assert (keys['Limits'].get('ResidentStats') == '320') == (value == 'xml1')
            assert ('ResidentStats' in FI.dropped_keys(keys).get('Limits', [])) == (value != 'xml1')
            text = FI.merge_text('[Limits]\nResidentStats=320\nKeep=3\n', keys, FI.dropped_keys(keys))
            assert ('ResidentStats=320' in text) == (value == 'xml1')
            assert 'Keep=3' in text
    assert 'ResidentStats' in FI.PORT_OWNED['Limits']
    assert 'ResidentStats' in FI.RELEASE_18_KEYS['Limits']


def test_resident_stats_dll_gate_requires_key_and_rule50_registration():
    keys = {'Limits': {'ResidentStats': '320'}}
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        assert FI.old_fix_keys(dll, keys) == []
        dll.write_bytes(b'MZ' + 'CharSounds'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[Limits] ResidentStats', '[Limits] ResidentStats (rule 50)']
        dll.write_bytes(b'MZ' + 'ResidentStats'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, keys) == ['[Limits] ResidentStats (rule 50)']
        dll.write_bytes(dll.read_bytes() + FI.RESIDENT_STATS_MARKER)
        assert FI.old_fix_keys(dll, keys) == []
        assert FI.old_fix_keys(dll, {'Limits': {}}) == []
