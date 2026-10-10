"""Heard-mark migration uses invented file names; no game data."""
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from test_lcsave import make_build, make_old_save, _era_model, _xmlb
from lcsave import binds, catalogue, convert, container, conversations, keys, lcfiles, legacy, oldsave


def _package(build, names):
    root = ET.Element('packagedef')
    for name in names: ET.SubElement(root, 'xml', filename='conversations/' + name)
    _xmlb(os.path.join(build, 'Packages', 'generated', 'maps', 'zone', 'x', 'y.pkgb'), root)


def fixture(root, names=('middle', 'zulu'), current=('alpha', 'middle', 'zulu'), words=(0x90, 0, 0, 0, 0), change_conversation=True):
    build = make_build(os.path.join(root, 'build'))
    _package(build, names)
    b = binds.Binds(build)
    model = _era_model(b, b)
    cat = catalogue.Catalogue()
    cat.update(catalogue.tables_from_hashes(legacy.Era(model, '13').tables), 13)
    ep, cp = os.path.join(root, 'eras.json'), os.path.join(root, 'cat.json')
    with open(ep, 'w') as f: json.dump(model, f)
    cat.save(cp)
    env = convert.Environment(build, eras_path=ep, catalogue_path=cp)
    native = make_old_save(def_count=len(b.item)); native['zones'][0]['conversation'] = list(words)
    saved = convert.convert_slot(oldsave.write_slot(native), 'synthetic.save', env, now=0)
    assert saved.refused is None, saved.refused
    _package(build, current)
    # A new writer has changed dialogue content, as in an actual builder-era migration.
    if change_conversation:
        with open(os.path.join(build, 'Conversations', 'c.engb'), 'wb') as f: f.write(b'changed invented conversation')
    for rel, blob in lcfiles.write_build_files(build, 13, cat=cat, model=model)[0].items():
        path = os.path.join(build, rel); os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f: f.write(blob)
        assert open(path, 'rb').read() == blob
    return env, saved.file_bytes, model


def test_heard_marks_move_with_file_identity_and_all_four_lanes():
    with tempfile.TemporaryDirectory() as d:
        env, saved, _ = fixture(d, words=(0xf0, 0, 0, 0, 0))
        restored, notes = convert.reverse_slot(saved, env)
        assert restored['zones'][0]['conversation'] == [0xf00, 0, 0, 0, 0]
        assert not any('heard mark dropped' in n for n in notes)


def test_removed_file_gets_specific_ledger_note_and_survivor_is_kept():
    with tempfile.TemporaryDirectory() as d:
        env, saved, _ = fixture(d, current=('middle',), words=(0x11, 0, 0, 0, 0))
        restored, notes = convert.reverse_slot(saved, env)
        assert restored['zones'][0]['conversation'] == [1, 0, 0, 0, 0]
        assert sum('absent in current package: heard mark dropped' in n for n in notes) == 1


def test_metadata_rebases_digest_for_two_consecutive_saves():
    with tempfile.TemporaryDirectory() as d:
        env, saved, _ = fixture(d)
        for _ in range(2):
            restored, _ = convert.reverse_slot(saved, env)
            assert restored['zones'][0]['conversation'] == [0x900, 0, 0, 0, 0]
            captures = convert.loaded_zone_metadata(saved, env)
            assert captures[0]['conversation_digest'] == bytes.fromhex(conversations.zone_digest(env.binds.build, 'zone/x/y'))
            result = convert.old_stream_to_new(oldsave.write_slot(restored), env, now=0, retained_file=saved,
                                               zone_captures=captures, require_capture_metadata=True)
            assert result.refused is None, result.refused
            saved = result.file_bytes


def test_unknown_or_unassigned_heard_marks_drop_with_notes_without_mutating_source():
    with tempfile.TemporaryDirectory() as d:
        env, saved, _ = fixture(d, words=(0, 0, 0, 0, 1))
        original = saved
        restored, notes = convert.reverse_slot(saved, env)
        assert restored['zones'][0]['conversation'] == [0] * 5
        assert any('historical identity unknown: heard mark dropped' in n for n in notes)
        assert saved == original
        from test_lcsave_durable import _secs
        from lcsave import layout as L
        f = container.read_file(saved)
        f['sections']['ZONE']['data']['records'][0]['conversation_digest'] = b'x' * 32
        unknown = container.write_file(L.KIND_CAMPAIGN, _secs(f), f['header'])
        restored, notes = convert.reverse_slot(unknown, env)
        assert restored['zones'][0]['conversation'] == [0] * 5
        assert any('conversation provenance unknown: heard marks dropped' in n for n in notes)
        assert saved == original


def test_sidecar_bounds_crc_duplicates_and_era_conflicts():
    with tempfile.TemporaryDirectory() as d:
        _, _, model = fixture(d)
        raw = lcfiles.write_conversation_lcm(model)
        assert lcfiles.read_conversation_lcm(raw) == conversations.historical_tables(model)
        for bad in (raw[:-1], raw[:24] + bytes([raw[24] ^ 1]) + raw[25:]):
            try: lcfiles.read_conversation_lcm(bad)
            except lcfiles.LCFileError: pass
            else: assert False, 'damaged mapping accepted'
        model['eras']['5']['conversation_bits'][keys.key_hash('zone/x/y')] = [keys.key_hash('other', str(k)) for k in range(4)]
        try: lcfiles.write_conversation_lcm(model)
        except ValueError as e: assert 'conflicting eras' in str(e)
        else: assert False, 'ambiguous digest mapping accepted'


def test_zero_unknown_provenance_rebases_metadata_as_inferred():
    from test_lcsave_durable import _secs
    from lcsave import layout as L
    with tempfile.TemporaryDirectory() as d:
        env, saved, _ = fixture(d, words=(0, 0, 0, 0, 0))
        f = container.read_file(saved)
        f['sections']['META']['data']['origin'] = 0
        r = f['sections']['ZONE']['data']['records'][0]
        r['conversation_digest'] = bytes(32); r['capture_flags'] = 0
        saved = container.write_file(L.KIND_CAMPAIGN, _secs(f), f['header'])
        captures = convert.loaded_zone_metadata(saved, env)
        assert captures[0]['capture_flags'] == 2
        assert captures[0]['conversation_digest'] == bytes.fromhex(conversations.zone_digest(env.binds.build, 'zone/x/y'))


def test_package_only_change_remaps_native_saved_marks():
    with tempfile.TemporaryDirectory() as d:
        env, saved, _ = fixture(d, current=('middle', 'zulu'), words=(0xf0, 0, 0, 0, 0), change_conversation=False)
        restored, _ = convert.reverse_slot(saved, env)
        captures = convert.loaded_zone_metadata(saved, env)
        result = convert.old_stream_to_new(oldsave.write_slot(restored), env, now=0,
            zone_captures=captures, require_capture_metadata=True)
        assert result.refused is None, result.refused
        digest = env.binds.conversation_digest()
        _package(env.binds.build, ('alpha', 'middle', 'zulu'))
        assert env.binds.conversation_digest() == digest
        restored, notes = convert.reverse_slot(result.file_bytes, env)
        assert restored['zones'][0]['conversation'] == [0xf00, 0, 0, 0, 0], restored['zones'][0]['conversation']
        assert any('remapped to current package' in n for n in notes)


def test_package_only_change_remaps_legacy_global_provenance():
    with tempfile.TemporaryDirectory() as d:
        env, saved, _ = fixture(d, words=(0xf0, 0, 0, 0, 0), change_conversation=False)
        old_digest = container.read_file(saved)['sections']['ZONE']['data']['records'][0]['conversation_digest'].hex()
        assert env.binds.conversation_digest() == old_digest
        restored, _ = convert.reverse_slot(saved, env)
        assert restored['zones'][0]['conversation'] == [0xf00, 0, 0, 0, 0]


def test_package_snapshot_carries_native_layout_beyond_legacy_eras():
    with tempfile.TemporaryDirectory() as d:
        env, saved, _ = fixture(d, words=(0xf0, 0, 0, 0, 0), change_conversation=False)
        native, _ = convert.reverse_slot(saved, env)
        assert native['zones'][0]['conversation'] == [0xf00, 0, 0, 0, 0]
        captures = convert.loaded_zone_metadata(saved, env)
        saved = convert.old_stream_to_new(oldsave.write_slot(native), env, now=0,
            zone_captures=captures, require_capture_metadata=True).file_bytes
        original_digest = env.binds.conversation_digest()
        _package(env.binds.build, ('alpha', 'beta', 'middle', 'zulu'))
        assert original_digest == env.binds.conversation_digest()
        fresh = convert.Environment(env.binds.build, eras_path=os.path.join(d, 'eras.json'), catalogue_path=os.path.join(d, 'cat.json'))
        restored, _ = convert.reverse_slot(saved, fresh)
        assert restored['zones'][0]['conversation'] == [0xf000, 0, 0, 0, 0]


def rebuild_metadata(env, model):
    # A new process must discover previous snapshots from disk, not cached tables.
    root = os.path.dirname(env.binds.build)
    fresh = convert.Environment(env.binds.build, eras_path=os.path.join(root, 'eras.json'),
        catalogue_path=os.path.join(root, 'cat.json'))
    cat = catalogue.Catalogue.load(os.path.join(root, 'cat.json'))
    files, problems = lcfiles.write_build_files(fresh.binds.build, 13, cat=cat, model=model)
    assert not problems, problems
    for rel, blob in files.items():
        path = os.path.join(fresh.binds.build, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f: f.write(blob)
        assert open(path, 'rb').read() == blob
    return fresh


def test_metadata_rebuild_preserves_previous_native_package_snapshots():
    with tempfile.TemporaryDirectory() as d:
        env, saved, model = fixture(d, words=(0xf0, 0, 0, 0, 0), change_conversation=False)
        native, _ = convert.reverse_slot(saved, env)
        saved = convert.old_stream_to_new(oldsave.write_slot(native), env, now=0,
            zone_captures=convert.loaded_zone_metadata(saved, env), require_capture_metadata=True).file_bytes
        path = os.path.join(env.binds.build, lcfiles.CONVERSATION_LCM)
        previous = lcfiles.read_conversation_lcm(open(path, 'rb').read())
        recorded = container.read_file(saved)['sections']['ZONE']['data']['records'][0]
        key = (recorded['conversation_digest'].hex(), keys.key_hash('zone/x/y'))
        assert key in previous and key not in conversations.historical_tables(model)
        for names, expected in [(('alpha', 'beta', 'middle', 'zulu'), 0xf000),
                                (('alpha', 'beta', 'gamma', 'middle', 'zulu'), 0xf0000)]:
            _package(env.binds.build, names)
            rebuild_metadata(env, model)
            tables = lcfiles.read_conversation_lcm(open(path, 'rb').read())
            assert all(tables.get(key) == bits for key, bits in previous.items()), 'metadata rebuild discarded recorded snapshots'
            previous = tables
            snapshot = open(path, 'rb').read()
            rebuild_metadata(env, model)
            assert open(path, 'rb').read() == snapshot, 'unchanged rebuild is not deterministic'
            fresh = convert.Environment(env.binds.build, eras_path=os.path.join(d, 'eras.json'), catalogue_path=os.path.join(d, 'cat.json'))
            restored, notes = convert.reverse_slot(saved, fresh)
            assert restored['zones'][0]['conversation'] == [expected, 0, 0, 0, 0]
            assert not any('provenance unknown' in n for n in notes)


def test_metadata_rebuild_rejects_damaged_or_conflicting_prior_sidecar():
    with tempfile.TemporaryDirectory() as d:
        env, _, model = fixture(d)
        path = os.path.join(env.binds.build, lcfiles.CONVERSATION_LCM)
        original = open(path, 'rb').read()
        tables = lcfiles.read_conversation_lcm(original)
        key = next(iter(tables))
        tables[key] = [keys.key_hash('conflicting', str(k)) for k in range(4)]
        conflict = lcfiles.write_conversation_lcm({'eras': {}}, previous=tables)
        for bad in (original[:-1], conflict):
            with open(path, 'wb') as f: f.write(bad)
            assert open(path, 'rb').read() == bad
            try: rebuild_metadata(env, model)
            except lcfiles.LCFileError: pass
            else: assert False, 'invalid prior history silently overwritten'
            assert open(path, 'rb').read() == bad
