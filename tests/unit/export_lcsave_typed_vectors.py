"""Export the typed entity-id / native layout parity vectors for xml2-fix's lcsave_durable_parity (PHASE-A-PLAN
sections 4 and 6): an invented build, an invented feature-0 campaign whose script variables hold typed values at
every boundary (generations 0, 1, 2, 0x3fff, 0x4000, a negative value, a non-token), an invented scripts tree with
its registry, the expected E10A2 native stream, the expected feature-1 rewrite, and the refusal cases. No game data.

    python tests/unit/export_lcsave_typed_vectors.py DEST      (then: lcsave_durable_parity DEST)

cases.tsv rows: name<TAB>build<TAB>mode<TAB>sequence. Modes (the C++ harness documents the same):
  e10a2-reverse     input.lcsave (feature 0) + registry.txt + scripts/: the registry verifies; the E10A2 loader's
                    stream == expected.e10a2.old with expected.report; the E10A2 saver's rewrite (retained input,
                    serial 17, sequence) == expected.feature1.lcsave; loading that again gives the same stream
                    (validate mode, never shifted again)
  refuse-downgrade  input.lcsave (feature 1): the retail loader refuses with expected.error
  refuse-unknown    input.lcsave (required bit 1): both layouts refuse with expected.error
  refuse-noregistry input.lcsave (feature 0): the E10A2 loader without a registry refuses with expected.error
  refuse-stream     input.raw (a retail-size payload): the E10A2 saver refuses with expected.error
  registry-mismatch registry.txt + scripts/ (edited): verify refuses with expected.error
"""
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
from test_lcsave_native_layout import typed_old_save, registry_fixture, _env, _set_required_features  # noqa: E402
from lcsave import container, convert, lcfiles, oldsave, layout as L, typed_registry as T  # noqa: E402


def _write(path, blob):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    assert path.read_bytes() == blob


def report_line(report):
    return (f"mode={report['mode']} typed_fields={report['typed_fields']} translated={report['translated']} "
            f"normalized_to_null={report['normalized_to_null']} validated={report['validated']}")


def main(destination):
    out = Path(destination)
    out.mkdir(parents=True, exist_ok=True)
    env = _env(str(out))                                       # <out>/build, eras.json, cat.json
    files, problems = lcfiles.write_build_files(env.binds.build, 13, env.catalogue, env.model)
    assert not problems, problems
    for relative, blob in files.items():
        _write(Path(env.binds.build) / relative, blob)
    root, reg_path, reg = registry_fixture(str(out / 'registry'))
    registry = Path(reg_path).read_bytes()
    raw = oldsave.write_slot(typed_old_save(len(env.binds.item)))
    legacy = convert.convert_slot(raw, 'synthetic.save', env, now=0)
    assert legacy.refused is None, legacy.refused
    legacy = legacy.file_bytes
    report = {}
    raised, notes = convert.reverse_slot(legacy, env, native=L.E10A2, registry=reg, report=report)
    e10a2 = oldsave.write_slot(raised, L.E10A2)
    captures = convert.loaded_zone_metadata(legacy, env, native=L.E10A2, registry=reg)
    saved = convert.old_stream_to_new(e10a2, env, retained_file=legacy, zone_captures=captures, require_capture_metadata=True,
                                      campaign_serial=17, save_sequence=2, now=-11644473600, native=L.E10A2)
    assert saved.refused is None, saved.refused
    report2 = {}
    again, notes2 = convert.reverse_slot(saved.file_bytes, env, native=L.E10A2, registry=reg, report=report2)
    assert oldsave.write_slot(again, L.E10A2) == e10a2 and report2['mode'] == 'validate'
    note = T.migration_note(report)
    assert note in notes
    lines = []

    def case(name, mode, sequence=0):
        lines.append(f'{name}\tbuild\t{mode}\t{sequence}\n')
        return out / name

    folder = case('typed_e10a2', 'e10a2-reverse', 2)
    _write(folder / 'input.lcsave', legacy)
    _write(folder / 'registry.txt', registry)
    shutil.copytree(root, folder / 'scripts', dirs_exist_ok=True)
    _write(folder / 'expected.e10a2.old', e10a2)
    _write(folder / 'expected.report', (report_line(report) + '\n' + note + '\n' + report_line(report2) + '\n' + T.migration_note(report2) + '\n').encode())
    _write(folder / 'expected.feature1.lcsave', saved.file_bytes)
    folder = case('refuse_downgrade', 'refuse-downgrade')
    _write(folder / 'input.lcsave', saved.file_bytes)
    _write(folder / 'expected.error', container.DOWNGRADE_REFUSED.encode())
    folder = case('refuse_unknown', 'refuse-unknown')
    _write(folder / 'input.lcsave', _set_required_features(legacy, 2))
    _write(folder / 'expected.error', b'required feature bits 0x2 not implemented (needs a newer version)')
    folder = case('refuse_noregistry', 'refuse-noregistry')
    _write(folder / 'input.lcsave', legacy)
    _write(folder / 'expected.error', T.NO_REGISTRY.encode())
    folder = case('refuse_stream', 'refuse-stream')
    plain, _ = convert.reverse_slot(legacy, env)
    _write(folder / 'input.raw', oldsave.write_slot(plain)[0x84:])
    _write(folder / 'expected.error', f'file size {L.RETAIL.payload} is not the slot size {L.E10A2.slot_size} (0x84 + 0x200000)'.encode())
    folder = case('registry_mismatch', 'registry-mismatch')
    _write(folder / 'registry.txt', registry)
    shutil.copytree(root, folder / 'scripts', dirs_exist_ok=True)
    _write(folder / 'scripts' / 'zone_q' / 'trap.py', b'# edited\n')
    ok, reason = T.verify_registry(reg_path, folder / 'scripts')
    assert not ok
    _write(folder / 'expected.error', reason.encode())
    path = out / 'cases.tsv'
    path.write_text(''.join(lines))
    assert path.read_text() == ''.join(lines)
    print(f'{len(lines)} cases under {out}')


if __name__ == '__main__':
    main(sys.argv[1])
