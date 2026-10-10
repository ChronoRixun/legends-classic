"""Export invented conversation migration vectors for the native parity gate."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from test_lcsave_conversations import fixture
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
             ('zero_inferred', ('middle',), (0, 0, 0, 0, 0))]
    for name, current, words in cases:
        folder = out / name
        env, saved, _ = fixture(str(folder), current=current, words=words)
        if name == 'zero_inferred':
            f = container.read_file(saved); f['sections']['META']['data']['origin'] = 0
            r = f['sections']['ZONE']['data']['records'][0]
            r['capture_flags'] = 0; r['conversation_digest'] = bytes(32)
            saved = container.write_file(L.KIND_CAMPAIGN, _secs(f), f['header'])
        write(folder / 'input.lcsave', saved)
        if name == 'missing_bit':
            write(folder / 'expected.error', b'conversation mapping: set bit has no historical identity')
            lines.append(f'{name}\t{name}/build\trefuse\t0\n')
            continue
        restored, _ = convert.reverse_slot(saved, env)
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
