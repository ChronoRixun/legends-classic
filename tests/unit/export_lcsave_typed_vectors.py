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
  w2-reverse        (limits-wave2.md section 10 G1) input.lcsave (feature 0) + registry.txt + scripts/: the W2 loader's
                    stream == expected.w2.old with expected.report; the W2 saver's rewrite (retained input, serial 17,
                    sequence) == expected.w2.lcsave and carries bit 0 only (representable); loading it again on W2 gives
                    the same stream; the E10A2 loader applies it to expected.e10a2.old (the pre-W2 build loads it)
  w2-bit1           input.w2.old (a W2 stream with a state position of 0.5): the W2 saver's file == expected.bit1.lcsave
                    with required bits 0 | 1; the E10A2 loader refuses it with expected.error; the W2 loader gives
                    input.w2.old back
"""
import copy
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
    # ---- W2 (limits-wave2.md section 10 G1): both directions at W2, the representable rewrite and the bit-1 case
    w2_report = {}
    w2_model, _ = convert.reverse_slot(legacy, env, native=L.W2, registry=reg, report=w2_report)
    w2_stream = oldsave.write_slot(w2_model, L.W2)
    assert len(w2_stream) == L.W2.slot_size and w2_report == report
    w2_captures = convert.loaded_zone_metadata(legacy, env, native=L.W2, registry=reg)
    w2_saved = convert.old_stream_to_new(w2_stream, env, retained_file=legacy, zone_captures=w2_captures, require_capture_metadata=True,
                                         campaign_serial=17, save_sequence=2, now=-11644473600, native=L.W2)
    assert w2_saved.refused is None, w2_saved.refused
    assert container.read_file(w2_saved.file_bytes)['header']['required_features'] == 1
    assert convert.representable(w2_saved.file_bytes, env, L.E10A2) == ''
    w2_again, _ = convert.reverse_slot(w2_saved.file_bytes, env, native=L.W2, registry=reg)
    assert oldsave.write_slot(w2_again, L.W2) == w2_stream
    w2_on_e10a2 = oldsave.write_slot(convert.reverse_slot(w2_saved.file_bytes, env, native=L.E10A2, registry=reg)[0], L.E10A2)
    assert w2_on_e10a2 == e10a2
    folder = case('typed_w2', 'w2-reverse', 2)
    _write(folder / 'input.lcsave', legacy)
    _write(folder / 'registry.txt', registry)
    shutil.copytree(root, folder / 'scripts', dirs_exist_ok=True)
    _write(folder / 'expected.w2.old', w2_stream)
    _write(folder / 'expected.report', (report_line(w2_report) + '\n' + note + '\n').encode())
    _write(folder / 'expected.w2.lcsave', w2_saved.file_bytes)
    _write(folder / 'expected.e10a2.old', w2_on_e10a2)
    half = copy.deepcopy(w2_model)
    state = next(st for st in half['zones'][0]['states'] if st['def_name'])
    state['position'][0] = 0.5
    half_stream = oldsave.write_slot(half, L.W2)
    bit1 = convert.old_stream_to_new(half_stream, env, retained_file=legacy, zone_captures=w2_captures, require_capture_metadata=True,
                                     campaign_serial=17, save_sequence=2, now=-11644473600, native=L.W2)
    assert bit1.refused is None, bit1.refused
    assert container.read_file(bit1.file_bytes)['header']['required_features'] == 3
    assert 'state position not representable' in convert.representable(bit1.file_bytes, env, L.E10A2)
    try:
        convert.reverse_slot(bit1.file_bytes, env, native=L.E10A2, registry=reg); assert False
    except convert.ConvertError as e:
        assert str(e) == container.W2_REFUSED
    assert oldsave.write_slot(convert.reverse_slot(bit1.file_bytes, env, native=L.W2, registry=reg)[0], L.W2) == half_stream
    folder = case('w2_bit1', 'w2-bit1', 2)
    _write(folder / 'input.lcsave', legacy)
    _write(folder / 'registry.txt', registry)
    shutil.copytree(root, folder / 'scripts', dirs_exist_ok=True)
    _write(folder / 'input.w2.old', half_stream)
    _write(folder / 'expected.bit1.lcsave', bit1.file_bytes)
    _write(folder / 'expected.error', container.W2_REFUSED.encode())
    folder = case('refuse_downgrade', 'refuse-downgrade')
    _write(folder / 'input.lcsave', saved.file_bytes)
    _write(folder / 'expected.error', container.DOWNGRADE_REFUSED.encode())
    folder = case('refuse_unknown', 'refuse-unknown')
    _write(folder / 'input.lcsave', _set_required_features(legacy, 4))
    _write(folder / 'expected.error', b'required feature bits 0x4 not implemented (needs a newer version)')
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
