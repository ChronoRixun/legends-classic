"""Export invented unnamed-placement input for lcsave_durable_parity.exe."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from test_lcsave_pinned_legacy import unnamed_fixture, packed
from lcsave import convert, lcfiles, oldsave


def main(destination):
    out = Path(destination)
    out.mkdir(parents=True, exist_ok=True)
    env, file, _, _, _, _ = unnamed_fixture(str(out / 'unnamed'))
    files, problems = lcfiles.write_build_files(env.binds.build, 13, env.catalogue,
                                               json.loads((out / 'unnamed/eras.json').read_text()))
    assert not problems, problems
    for relative, blob in files.items():
        path = Path(env.binds.build) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        assert path.read_bytes() == blob
    saved = packed(file)
    native, _ = convert.reverse_slot(saved, env)
    metadata = convert.loaded_zone_metadata(saved, env)
    text = ''.join(f"{c['zone']}\t{e['ordinal']}\t{e['placement_index']}\t{e['definition_name']}\t{e['instance_name']}\n"
                   for c in metadata for e in c['entities'])
    for name, blob in [('input.lcsave', saved), ('expected.old', oldsave.write_slot(native)),
                       ('expected.metadata', text.encode())]:
        path = out / 'unnamed' / name
        path.write_bytes(blob)
        assert path.read_bytes() == blob
    path = out / 'cases.tsv'
    text = 'unnamed\tunnamed/build\treverse\t0\n'
    path.write_text(text)
    assert path.read_text() == text


if __name__ == '__main__':
    main(sys.argv[1])
