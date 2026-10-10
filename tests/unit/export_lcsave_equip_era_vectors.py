"""Export invented mixed-era legacy imports for the native durable parity gate."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from test_lcsave_equip_era import mixed_fixture
from test_lcsave import _attr
from lcsave import convert, lcfiles, oldsave


def main(destination):
    out = Path(destination)
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    for name in ('hero_equipped', 'restore_equipped', 'restore_owner'):
        folder = out / name
        env, native = mixed_fixture(str(folder), restore=name == 'restore_equipped')
        if name == 'restore_owner':
            # Only bank 1 has era-discriminating evidence. Block 0 has stats index 1.
            for h in native['heroes']:
                h['attributes'] = _attr()
                h['equipment']['equipped'] = []
            native['restore'][1]['attributes'] = _attr(talents=[(2, 3)])
            model = env.model
            model['eras']['13']['hero_shared_holdable'][model['reference']['STAT'][2]] = [0, 2, 3, 4]
            model['eras']['5']['hero_shared_holdable'][model['reference']['STAT'][2]] = [0, 3]
            (folder / 'eras.json').write_text(json.dumps(model))
            assert json.loads((folder / 'eras.json').read_text()) == model
            env = convert.Environment(env.binds.build, eras_path=str(folder / 'eras.json'),
                                      catalogue_path=str(folder / 'cat.json'))
        files, problems = lcfiles.write_build_files(env.binds.build, 13, env.catalogue, env.model)
        assert not problems, problems
        for relative, blob in files.items():
            path = Path(env.binds.build) / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
            assert path.read_bytes() == blob
        raw = oldsave.write_slot(native)
        result = convert.convert_slot(raw, 'synthetic.save', env, now=-11644473600)
        assert result.refused is None, result.refused
        assert (result.era['start'], result.era['items']) == (5, 13), result.era
        for filename, blob in [('input.raw', raw), ('expected.lcsave', result.file_bytes)]:
            path = folder / filename
            path.write_bytes(blob)
            assert path.read_bytes() == blob
        lines.append(f'{name}\t{name}/build\tlegacy-import\t0\n')
    path = out / 'cases.tsv'
    path.write_text(''.join(lines))
    assert path.read_text() == ''.join(lines)


if __name__ == '__main__':
    main(sys.argv[1])
