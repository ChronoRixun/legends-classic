"""Export invented conversation migration vectors for the native parity gate."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from test_lcsave_conversations import fixture, _package, rebuild_metadata
from test_lcsave import make_old_save
from lcsave import convert, oldsave, container, layout as L
from test_lcsave_durable import _secs


def write(path, blob):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    assert path.read_bytes() == blob


def main(destination):
    out = Path(destination)
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    cases = [('shifted', ('alpha', 'middle', 'zulu'), (0xf0, 0, 0, 0, 0)),
             ('removed', ('middle',), (0x11, 0, 0, 0, 0)),
             ('missing_bit', ('middle',), (0, 0, 0, 0, 1)),
             ('zero_inferred', ('middle',), (0, 0, 0, 0, 0)),
             ('package_legacy', ('alpha', 'middle', 'zulu'), (0xf0, 0, 0, 0, 0)),
             ('package_native', ('middle', 'zulu'), (0xf0, 0, 0, 0, 0)),
             ('transfer_nonzero', ('middle', 'zulu'), (1, 0, 0, 0, 0)),
             ('package_snapshot', ('alpha', 'middle', 'zulu'), (0xf0, 0, 0, 0, 0)),
             ('package_rebuild', ('alpha', 'middle', 'zulu'), (0xf0, 0, 0, 0, 0))]
    for name, current, words in cases:
        folder = out / name
        env, saved, model = fixture(str(folder), current=current, words=words, change_conversation=not name.startswith('package_'))
        if name in ('package_native', 'package_snapshot', 'package_rebuild'):
            restored, _ = convert.reverse_slot(saved, env)
            result = convert.old_stream_to_new(oldsave.write_slot(restored), env, now=0,
                zone_captures=convert.loaded_zone_metadata(saved, env), require_capture_metadata=True)
            assert result.refused is None, result.refused
            saved = result.file_bytes
            before = env.binds.conversation_digest()
            _package(env.binds.build, ('alpha', 'beta', 'middle', 'zulu') if name in ('package_snapshot', 'package_rebuild') else ('alpha', 'middle', 'zulu'))
            assert env.binds.conversation_digest() == before
            if name == 'package_rebuild':
                rebuild_metadata(env, model)
                env = convert.Environment(env.binds.build, eras_path=str(folder / 'eras.json'),
                    catalogue_path=str(folder / 'cat.json'))
        if name == 'transfer_nonzero':
            native = make_old_save(def_count=len(env.binds.item)); native['zones'][0]['conversation'] = list(words)
            raw = oldsave.write_slot(native); captures = convert.native_zone_metadata(raw, env)
            assert captures[0]['conversation_digest'] == bytes(32)
            result = convert.old_stream_to_new(raw, env, now=-11644473600, zone_captures=captures,
                require_capture_metadata=True, campaign_serial=17, save_sequence=1)
            assert result.refused is None, result.refused
            row = out / 'transfer_recording'; write(row / 'input.raw', raw); write(row / 'expected.lcsave', result.file_bytes)
            lines.append(f'{row.name}\t{name}/build\tnative-transfer\t1\n')
            saved = result.file_bytes
        if name == 'zero_inferred':
            f = container.read_file(saved); f['sections']['META']['data']['origin'] = 0
            r = f['sections']['ZONE']['data']['records'][0]
            r['capture_flags'] = 0; r['conversation_digest'] = bytes(32)
            saved = container.write_file(L.KIND_CAMPAIGN, _secs(f), f['header'])
        write(folder / 'input.lcsave', saved)
        restored, notes = convert.reverse_slot(saved, env)
        if name.startswith('package_'): assert restored['zones'][0]['conversation'] == [0xf000 if name in ('package_snapshot', 'package_rebuild') else 0xf00, 0, 0, 0, 0]
        if name == 'transfer_nonzero':
            assert restored['zones'][0]['conversation'] == [0] * 5
            assert any('conversation provenance unknown: heard marks dropped' in n for n in notes)
        write(folder / 'expected.old', oldsave.write_slot(restored))
        lines.append(f'{name}\t{name}/build\treverse\t0\n')
        for sequence in (2, 3):
            row = out / f'{name}_save{sequence}'
            write(row / 'input.lcsave', saved)
            restored, _ = convert.reverse_slot(saved, env)
            captures = convert.loaded_zone_metadata(saved, env)
            result = convert.old_stream_to_new(oldsave.write_slot(restored), env, now=-11644473600, retained_file=saved,
                zone_captures=captures, require_capture_metadata=True, campaign_serial=17, save_sequence=sequence)
            assert result.refused is None, result.refused
            write(row / 'expected.lcsave', result.file_bytes)
            lines.append(f'{row.name}\t{name}/build\tcampaign\t{sequence}\n')
            saved = result.file_bytes
    text = ''.join(lines)
    (out / 'cases.tsv').write_text(text)
    assert (out / 'cases.tsv').read_text() == text
    print('Verified', len(lines), 'conversation parity vectors')


if __name__ == '__main__':
    main(sys.argv[1])
