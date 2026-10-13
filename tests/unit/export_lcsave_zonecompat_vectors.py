"""Export synthetic append compatibility and cache-resave byte parity cases."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from test_lcsave_zonecompat import fixture
from lcsave import convert, oldsave


def main(destination):
    out = Path(destination)
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    for variant in ('append', 'tailstate', 'position', 'definition', 'reorder'):
        folder = out / variant
        folder.mkdir()
        env, saved, _ = fixture(str(folder), variant)
        (folder / 'input.lcsave').write_bytes(saved)
        restored, _ = convert.reverse_slot(saved, env)
        (folder / 'expected.old').write_bytes(oldsave.write_slot(restored))
        lines.append(f'{variant}\t{variant}/build\treverse\t0\n')
        if variant not in ('append', 'tailstate'): continue
        for sequence in (2, 3):
            row = out / f'{variant}_save{sequence}'
            row.mkdir()
            (row / 'input.lcsave').write_bytes(saved)
            restored, _ = convert.reverse_slot(saved, env)
            result = convert.old_stream_to_new(oldsave.write_slot(restored), env, now=-11644473600,
                retained_file=saved, zone_captures=convert.loaded_zone_metadata(saved, env),
                require_capture_metadata=True, campaign_serial=17, save_sequence=sequence)
            assert result.refused is None, result.refused
            (row / 'expected.lcsave').write_bytes(result.file_bytes)
            lines.append(f'{row.name}\t{variant}/build\tcampaign\t{sequence}\n')
            saved = result.file_bytes
    (out / 'cases.tsv').write_text(''.join(lines))
    print('Verified', len(lines), 'zone prefix parity vectors')


if __name__ == '__main__':
    main(sys.argv[1])
