"""Append-only map compatibility uses synthetic maps and saves exclusively."""
import copy
import shutil
import tempfile
from pathlib import Path

import xmlb
from test_lcsave import _xmlb
from test_lcsave_durable import _env, _converted, _secs
from lcsave import zonecompat as Z, binds, container, convert, oldsave, layout as L, lcfiles


def fixture(folder, variant='append'):
    env = _env(folder)
    _, saved = _converted(env)
    captures = convert.loaded_zone_metadata(saved, env)
    captures[0]['capture_flags'] = 0
    native, _ = convert.reverse_slot(saved, env)
    # Preserve a real removal in the original prefix, not just an unchanged map.
    idx = native['zones'][0]['ordinal_map'][0]
    native['zones'][0]['states'][idx]['flags_b'] &= ~8
    result = convert.old_stream_to_new(oldsave.write_slot(native), env, now=0, zone_captures=captures, require_capture_metadata=True)
    assert result.refused is None, result.refused
    saved = result.file_bytes
    if variant == 'tailstate':
        f = container.read_file(saved)
        record = f['sections']['ZONE']['data']['records'][0]
        state = copy.deepcopy(next(s for s in record['states'] if s['list'] != 1))
        record['states'] = [s for s in record['states'] if s['list'] == 1]
        state.update(list=3, def_name=len(record['names']), inst_name=len(record['names'])+1)
        record['names'].extend(['crate', 'crate01'])
        record['states'].append(state)
        saved = container.write_file(L.KIND_CAMPAIGN, _secs(f), f['header'])
    previous = Path(folder) / 'previous'
    shutil.copytree(env.binds.build, previous)
    path = Path(env.binds.zone_file('zone/x/y'))
    root = xmlb.decode(path.read_bytes())
    group = next(e for e in root if e.tag == 'entinst' and e.get('type') == 'crate')
    definition = next(e for e in root if e.tag == 'entity' and e.get('name') == 'crate')
    definition.set('smartent', 'false')
    root.remove(group); root.append(group)
    if variant == 'position':
        next(e for e in root.iter('inst') if e.get('name') == 'gate01').set('origin', '1 2 3')
    elif variant == 'definition':
        next(e for e in root.iter('entity') if e.get('name') == 'gate').set('health', '99')
    elif variant == 'reorder':
        gate = next(e for e in root if e.tag == 'entinst' and e.get('type') == 'gate')
        first = gate[0]; gate.remove(first); gate.append(first)
    _xmlb(str(path), root)
    report = Z.generate(previous, env.binds.build)
    env.binds._zones.clear()
    env.binds.zone_prefixes = Z.load(env.binds.build)
    # Synthetic public-code fixtures can ship their own tables for C++ byte parity.
    for rel, blob in lcfiles.write_build_files(env.binds.build, 13, cat=env.catalogue, model=env.model)[0].items():
        p = Path(env.binds.build) / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(blob)
    return env, saved, report


def test_append_preserves_removed_prefix_and_tail_starts_fresh():
    with tempfile.TemporaryDirectory() as folder:
        env, saved, report = fixture(folder)
        assert report['accepted'] == ['zone/x/y'] and not report['rejected']
        restored, notes = convert.reverse_slot(saved, env)
        assert len(restored['zones']) == 1 and any('prefix retained' in n for n in notes)
        first = restored['zones'][0]['states'][restored['zones'][0]['ordinal_map'][0]]
        assert not first['flags_b'] & 8
        capture, = convert.loaded_zone_metadata(saved, env)
        assert capture['source_placement_sha1'] != capture['placement_sha1']
        assert capture['fresh_entities'][-1]['instance_name'] == 'crate01'
        assert restored['zones'][0]['ordinal_map'][capture['fresh_entities'][-1]['ordinal']-1] == 0
        # Historical placement indices changed, while resident ordinals stayed fixed.
        assert any(e['placement_index'] != e['source_placement_index'] for e in capture['entities'])
        original_hash = capture['source_placement_sha1']
        for _ in range(2):
            result = convert.old_stream_to_new(oldsave.write_slot(restored), env, now=0, retained_file=saved,
                zone_captures=convert.loaded_zone_metadata(saved, env), require_capture_metadata=True)
            assert result.refused is None, result.refused
            saved = result.file_bytes
            assert container.read_file(saved)['sections']['ZONE']['data']['records'][0]['content_hash'] == original_hash
            restored, notes = convert.reverse_slot(saved, env)
            assert len(restored['zones']) == 1 and any('prefix retained' in n for n in notes)


def test_real_prefix_changes_and_missing_or_stale_attestations_discard():
    for variant in ('position', 'definition', 'reorder'):
        with tempfile.TemporaryDirectory() as folder:
            env, saved, report = fixture(folder, variant)
            assert not report['accepted'] and report['rejected'] == ['zone/x/y']
            restored, notes = convert.reverse_slot(saved, env)
            assert not restored['zones'] and any('record not applied' in n for n in notes)
    with tempfile.TemporaryDirectory() as folder:
        env, saved, _ = fixture(folder)
        for rows in ([], [dict(env.binds.zone_prefixes[0], current=b'X'*20)]):
            env.binds.zone_prefixes = rows
            restored, notes = convert.reverse_slot(saved, env)
            assert not restored['zones'] and any('record not applied' in n for n in notes)


def test_sidecar_damage_duplicates_and_incomplete_capture_fail_closed():
    with tempfile.TemporaryDirectory() as folder:
        env, saved, _ = fixture(folder)
        raw = (Path(env.binds.build) / Z.REL).read_bytes()
        for bad in (raw[:-1], raw[:24]+b'X'+raw[25:], b'bad'):
            try: Z.decode(bad)
            except binds.BindError: pass
            else: assert False, 'damaged sidecar accepted'
        row = env.binds.zone_prefixes[0]
        try: Z.encode([row,row])
        except binds.BindError: pass
        else: assert False, 'duplicate source accepted'
        f = container.read_file(saved)
        f['sections']['ZONE']['data']['records'][0]['capture_flags'] = 1
        bad = container.write_file(L.KIND_CAMPAIGN, _secs(f), f['header'])
        restored, notes = convert.reverse_slot(bad, env)
        assert not restored['zones'] and any('incomplete capture' in n for n in notes)


def test_former_smart_tail_and_exclusive_world_dependency_start_fresh():
    with tempfile.TemporaryDirectory() as folder:
        env, saved, report = fixture(folder, 'tailstate')
        assert report['accepted'] == ['zone/x/y']
        restored, _ = convert.reverse_slot(saved, env)
        assert restored['zones'][0]['smart_count'] == 0
        assert restored['zones'][0]['state_count'] == 4
        assert all(w['slot'] != 5 for w in restored['items']['world'])
        capture, = convert.loaded_zone_metadata(saved, env)
        assert capture['fresh_entities']
