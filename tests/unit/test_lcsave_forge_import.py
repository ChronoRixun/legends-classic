"""Legacy-only contact recovery; all save/build contents are invented."""
import os
import struct
import tempfile
import xml.etree.ElementTree as ET
from test_lcsave import make_build, make_old_save, _era_model, _xmlb
from lcsave import binds, catalogue, legacy, container, convert, oldsave, layout as L

NOTE = 'Forge contact unlock granted (0.1.x builds did not record it)'
ZONES = ('nyc/alison/early', 'mansion/man1a/first', 'haarp/ext/later',
         'mansion/man8/later', 'mansion/jugrnt/flashback', 'arena/training',
         'nyc/riots/later', 'haarp/extensive/unknown')


def environment(folder, shifted_era=False):
    root = make_build(os.path.join(folder, 'build'))
    zi = ET.Element('zoneinfo')
    for z in ('zone/x/y', 'zone/x/z') + ZONES:
        ET.SubElement(zi, 'zone', name=z)
    _xmlb(os.path.join(root, 'Data', 'zoneinfo.engb'), zi)
    b = binds.Binds(root)
    older = binds.Binds(make_build(os.path.join(folder, 'older'), shared=['sh_fight', 'sh_might', 'sh_acro', 'sh_tough'])) if shifted_era else b
    model = _era_model(b, older)
    cat = catalogue.Catalogue()
    cat.update(catalogue.tables_from_hashes(legacy.Era(model, '13').tables), 13)
    ep, cp = os.path.join(folder, 'eras.json'), os.path.join(folder, 'cat.json')
    import json
    with open(ep, 'w') as f: json.dump(model, f)
    cat.save(cp)
    return convert.Environment(root, eras_path=ep, catalogue_path=cp)


def saved(env, zone, value=None):
    old = make_old_save(def_count=len(env.binds.item))
    old['mission']['zone'] = zone
    if value is not None:
        old['script_vars']['game'][1] = dict(name='X1V03', value_be=struct.pack('>I', value))
    return old


def game_vars(result):
    assert not result.refused, result.refused
    return [dict(name=v['name'], value=v['value']) for v in container.read_file(result.file_bytes)['sections']['SVAR']['data']['game_vars']]


def test_forge_import_progress_and_native_isolation():
    with tempfile.TemporaryDirectory() as d:
        env = environment(d)
        for zone, grant in ((z, z in (ZONES[2], ZONES[3], ZONES[6])) for z in ZONES):
            old = saved(env, zone, 0x80000005)
            raw = oldsave.write_slot(old)
            r = convert.convert_slot(raw, 'synthetic.save', env, now=0)
            vs = game_vars(r)
            assert vs[1]['value'] == (0xc0000005 if grant else 0x80000005), zone
            assert r.notes.count(NOTE) == int(grant), (zone, r.notes)
            assert container.read_file(r.file_bytes)['sections']['LGCY']['data']['notes'].count(NOTE) == int(grant)
            # Normal native saving (including an LC resave with its bit clear) must not repair it.
            native = convert.old_stream_to_new(raw, env, now=0)
            assert game_vars(native)[1]['value'] == 0x80000005
            assert NOTE not in native.notes
            back, _ = convert.reverse_slot(r.file_bytes, env)
            assert oldsave.script_var_value(back['script_vars']['game'][1]) == vs[1]['value']
        old = saved(env, ZONES[2], 0xc0000005)
        r = convert.convert_slot(oldsave.write_slot(old), 'synthetic.save', env, now=0)
        assert game_vars(r)[1]['value'] == 0xc0000005 and NOTE not in r.notes


def test_forge_import_absent_var_and_side_frame():
    with tempfile.TemporaryDirectory() as d:
        env = environment(d)
        old = saved(env, ZONES[0])
        old['side']['count'] = 1
        old['side']['frames'][0]['zone'] = ZONES[2]
        r = convert.convert_slot(oldsave.write_slot(old), 'synthetic.save', env, now=0)
        assert game_vars(r) == [dict(name='gv_one', value=7), dict(name='x1v03', value=0x40000000)]
        assert r.notes.count(NOTE) == 1
        # An unused frame must not imply progress.
        old['side']['count'] = 0
        r = convert.convert_slot(oldsave.write_slot(old), 'synthetic.save', env, now=0)
        assert game_vars(r) == [dict(name='gv_one', value=7)]


def test_forge_import_retained_zone_and_capacity():
    with tempfile.TemporaryDirectory() as d:
        env = environment(d)
        old = saved(env, ZONES[1])
        # Retained history is consulted even if an obsolete record is discarded by import.
        arena = bytearray(old['zone_strings']['arena']); text = (ZONES[2] + '\0').encode()
        off = len(arena.rstrip(b'\0')) + 1
        arena[off:off + len(text)] = text
        old['zone_strings']['arena'] = bytes(arena)
        old['zone_strings']['offsets'][40] = off
        old['zones'][0]['name_handle'] = 40
        r = convert.convert_slot(oldsave.write_slot(old), 'synthetic.save', env, now=0)
        assert game_vars(r)[-1] == dict(name='x1v03', value=0x40000000)
        assert r.notes.count(NOTE) == 1
        old['script_vars']['game'] = [dict(name='v' + str(i), value_be=bytes(4)) for i in range(L.OLD_SCRIPT_GAME_VARS)]
        r = convert.convert_slot(oldsave.write_slot(old), 'synthetic.save', env, now=0)
        assert r.refused and 'Forge contact unlock: game-variable store is full' in r.refused


def test_forge_import_older_era_same_signal_and_already_unlocked():
    with tempfile.TemporaryDirectory() as d:
        env = environment(d, shifted_era=True)
        old = make_old_save(shared_ids=(0, 2, 3), def_count=len(env.binds.item))
        old['mission']['zone'] = ZONES[2]
        old['script_vars']['game'][1] = dict(name='X1V03', value_be=struct.pack('>I', 0x123))
        r = convert.convert_slot(oldsave.write_slot(old), 'synthetic.save', env, now=0)
        assert r.era['start'] == 5 and game_vars(r)[1]['value'] == 0x40000123
        assert r.notes.count(NOTE) == 1


def test_forge_verifier_accounts_only_for_recorded_repair():
    with tempfile.TemporaryDirectory() as d:
        env = environment(d)
        path = os.path.join(d, 'synthetic.save')
        with open(path, 'wb') as f: f.write(oldsave.write_slot(saved(env, ZONES[2], 5)))
        r = convert.verify_file(path, env)
        assert r['ok'], r
        assert r['legacy_repairs'] == [NOTE] and not r['reverse_expected_identical']
        assert not r['reverse_identical'] and not r['semantic_diff']


def test_forge_verifier_keeps_input_names_for_repaired_artifacts():
    with tempfile.TemporaryDirectory() as d:
        env = environment(d)
        output = os.path.join(d, 'verified')
        first_artifacts = {}
        for basename, value in (('first.save', 5), ('second.save', 9)):
            path = os.path.join(d, basename)
            with open(path, 'wb') as f:
                f.write(oldsave.write_slot(saved(env, ZONES[2], value)))
            result = convert.verify_file(path, env, out_dir=output)
            assert result['ok'] and result['legacy_repairs'] == [NOTE], result
            for suffix in ('.lcsave', '.old.json', '.new.json', '.report.json'):
                artifact = os.path.join(output, basename + suffix)
                assert os.path.isfile(artifact), artifact
                if basename == 'first.save':
                    with open(artifact, 'rb') as f:
                        first_artifacts[artifact] = f.read()
            with open(os.path.join(output, basename + '.lcsave'), 'rb') as f:
                variables = container.read_file(f.read())['sections']['SVAR']['data']['game_vars']
            assert variables[1]['value'] == value | 0x40000000
        assert len(os.listdir(output)) == 8
        for artifact, original_bytes in first_artifacts.items():
            with open(artifact, 'rb') as f:
                assert f.read() == original_bytes, artifact
