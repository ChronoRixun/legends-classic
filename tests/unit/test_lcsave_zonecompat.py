"""Append-only map compatibility uses synthetic maps and saves exclusively."""
import copy
import shutil
import tempfile
from pathlib import Path

import xmlb
from test_lcsave import _xmlb
from test_lcsave_durable import _env, _converted, _secs
from lcsave import zonecompat as Z, binds, container, convert, oldsave, layout as L, lcfiles, keys


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
    if variant in ('tailstate','renamed','ambiguous'):
        f = container.read_file(saved)
        record = f['sections']['ZONE']['data']['records'][0]
        state = copy.deepcopy(next(s for s in record['states'] if s['list'] != 1))
        record['states'] = [s for s in record['states'] if s['list'] == 1]
        state.update(list=3, def_name=len(record['names']), inst_name=len(record['names'])+1)
        record['names'].extend(['crate', 'crate01'])
        record['states'].append(state)
        saved = container.write_file(L.KIND_CAMPAIGN, _secs(f), f['header'])
    previous = Path(folder) / 'previous'
    if variant == 'xmlbonly':
        path = Path(env.binds.zone_file('zone/x/y'))
        path.rename(path.with_suffix('.xmlb'))
    path = Path(env.binds.zone_file('zone/x/y'))
    root = xmlb.decode(path.read_bytes())
    if variant == 'escaped':
        # Digest parity must include authored whitespace, escapes, latin-1 and child order.
        definition = next(e for e in root.iter('entity') if e.get('name') == 'gate')
        definition.set('note', 'quote " slash \\ newline\n tab\t café')
        definition.set('é', 'high attribute')
        definition.set('z', 'ascii attribute')
        import xml.etree.ElementTree as ET
        ET.SubElement(definition, 'synthetic_child', value='\x01\r\b\f')
        _xmlb(str(path), root)
        f = container.read_file(saved)
        f['sections']['ZONE']['data']['records'][0]['content_hash'] = __import__('hashlib').sha1(path.read_bytes()).digest()
        saved = container.write_file(L.KIND_CAMPAIGN, _secs(f), f['header'])
    if variant == 'ambiguous':
        group = next(e for e in root if e.tag == 'entinst' and e.get('type') == 'crate')
        extra = copy.deepcopy(group[0]);extra.set('pos','1000 0 0');group.append(extra)
        _xmlb(str(path),root)
        # The original save's provenance names this map with indistinguishable smart twins.
        f=container.read_file(saved);record=f['sections']['ZONE']['data']['records'][0];record['content_hash']=__import__('hashlib').sha1(path.read_bytes()).digest()
        for state in record['states']:
            if state['list']==1 and state['placement_index']>=3: state['placement_index']+=1
        saved=container.write_file(L.KIND_CAMPAIGN,_secs(f),f['header'])
    shutil.copytree(env.binds.build, previous)
    group = next(e for e in root if e.tag == 'entinst' and e.get('type') == 'crate')
    definition = next(e for e in root if e.tag == 'entity' and e.get('name') == 'crate')
    if variant in ('renamed','ambiguous'):
        definition=copy.deepcopy(definition);definition.set('name','crate_appended');root.append(definition)
        if variant=='ambiguous':
            promoted=copy.deepcopy(group);promoted.remove(promoted[1]);group.remove(group[0]);group=promoted
        else:root.remove(group)
        group.set('type','crate_appended');root.append(group)
    definition.set('smartent', 'false')
    root.remove(group); root.append(group)
    if variant == 'position':
        next(e for e in root.iter('inst') if e.get('name') == 'gate01').set('origin', '1 2 3')
    elif variant == 'definition':
        next(e for e in root.iter('entity') if e.get('name') == 'gate').set('health', '99')
    elif variant == 'world':
        root.set('gravity','2')
    elif variant == 'smartdefinition':
        next(e for e in root.iter('entity') if e.get('name')=='lamp').set('health','99')
    elif variant == 'reorder':
        gate = next(e for e in root if e.tag == 'entinst' and e.get('type') == 'gate')
        first = gate[0]; gate.remove(first); gate.append(first)
    _xmlb(str(path), root)
    report = Z.generate(previous, env.binds.build)
    if variant in ('bad_digest', 'rebound_prefix'):
        rows = Z.load(env.binds.build)
        row = next(r for r in rows if r['zone'] == Z.zone_hash('zone/x/y'))
        if variant == 'bad_digest':
            row['digest'] = bytes(32)
        else:
            next(e for e in root.iter('entity') if e.get('name') == 'gate').set('health', '99')
            _xmlb(str(path), root)
            row['current'] = __import__('hashlib').sha1(path.read_bytes()).digest()
        # Recompute a valid CRC: framing checks alone cannot catch these edits.
        (Path(env.binds.build) / Z.REL).write_bytes(Z.encode(rows))
    elif variant == 'past_prefix':
        f = container.read_file(saved)
        state = next(s for s in f['sections']['ZONE']['data']['records'][0]['states'] if s['list'] == 1)
        state['ordinal'] = len(Z.load(env.binds.build)[-1]['placements']) + 1
        saved = container.write_file(L.KIND_CAMPAIGN, _secs(f), f['header'])
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
    for variant in ('position', 'definition', 'reorder', 'world', 'smartdefinition'):
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


def test_xmlb_only_zone_attests_and_current_digest_validation_fails_closed():
    with tempfile.TemporaryDirectory() as folder:
        env, saved, report = fixture(folder, 'xmlbonly')
        assert report['accepted'] == ['zone/x/y']
        restored, _ = convert.reverse_slot(saved, env)
        assert len(restored['zones']) == 1
        assert Z.validate_current(env.binds.build) == 1
        rows = Z.load(env.binds.build)
        next(r for r in rows if r['zone'] == bytes.fromhex(keys.key_hash('zone/x/y')))['digest'] = bytes(32)
        (Path(env.binds.build)/Z.REL).write_bytes(Z.encode(rows))
        try: Z.validate_current(env.binds.build)
        except binds.BindError: pass
        else: assert False, 'incorrect active prefix digest accepted'


def test_renamed_resident_tail_drops_old_smart_alias_without_duplication():
    with tempfile.TemporaryDirectory() as folder:
        env,saved,report=fixture(folder,'renamed')
        assert report['accepted']==['zone/x/y']
        restored,_=convert.reverse_slot(saved,env)
        assert restored['zones'][0]['smart_count']==0
        assert all(w['slot']!=5 for w in restored['items']['world'])
        capture,=convert.loaded_zone_metadata(saved,env)
        assert capture['fresh_entities'][0]['definition_name']=='crate_appended'


def test_ambiguous_old_smart_twins_reject_without_resetting_an_untouched_twin():
    with tempfile.TemporaryDirectory() as folder:
        env,saved,report=fixture(folder,'ambiguous')
        assert report['accepted']==['zone/x/y']
        restored,notes=convert.reverse_slot(saved,env)
        assert not restored['zones']
        assert any('aliases both new tail and retained placement' in n for n in notes)


def test_zone_key_mixed_case_uses_numbering_normalization():
    with tempfile.TemporaryDirectory() as folder:
        env, saved, _ = fixture(folder)
        record = container.read_file(saved)['sections']['ZONE']['data']['records'][0]
        lower = env.binds.zone_numbering('zone/x/y')
        mixed = env.binds.zone_numbering('ZoNe/X/Y')
        assert lower is mixed
        assert Z.match(env.binds.zone_prefixes, 'ZoNe/X/Y', record['content_hash'], mixed)
        assert Z.zone_hash('ZONE/Étage') == Z.zone_hash('zone/étage')


def test_runtime_digest_checks_valid_crc_edits_and_rebound_prefix():
    for variant in ('bad_digest', 'rebound_prefix', 'escaped'):
        with tempfile.TemporaryDirectory() as folder:
            env, saved, _ = fixture(folder, variant)
            restored, notes = convert.reverse_slot(saved, env)
            assert bool(restored['zones']) == (variant == 'escaped')
            assert bool(convert.loaded_zone_metadata(saved, env)) == (variant == 'escaped')
            if variant != 'escaped':
                assert any('record not applied' in n for n in notes)


def test_saved_ordinal_past_attested_prefix_discards_cleanly():
    with tempfile.TemporaryDirectory() as folder:
        env, saved, _ = fixture(folder, 'past_prefix')
        restored, notes = convert.reverse_slot(saved, env)
        assert not restored['zones'] and any('record not applied' in n for n in notes)
        assert convert.loaded_zone_metadata(saved, env) == []


def test_generate_rejects_one_unmodelled_zone_and_keeps_valid_history():
    with tempfile.TemporaryDirectory() as folder:
        env, _, _ = fixture(folder)
        previous = Path(folder) / 'previous'
        # Copy a changed zone with duplicate definitions; numbering is unsafe there.
        for build in (previous, Path(env.binds.build)):
            source = build / 'Maps/zone/x/y.engb'
            destination = build / 'Maps/zone/x/unmodelled.engb'
            root = xmlb.decode(source.read_bytes())
            root.append(copy.deepcopy(next(e for e in root if e.tag == 'entity')))
            _xmlb(str(destination), root)
        history = Z.load(env.binds.build)
        report = Z.generate(previous, env.binds.build)
        assert report['accepted'] == ['zone/x/y']
        assert report['rejected'] == ['zone/x/unmodelled']
        assert Z.load(env.binds.build) == history


def test_native_transfer_retains_fresh_tail_without_receiver_sidecar():
    for native in (L.RETAIL, L.E10A2):
        with tempfile.TemporaryDirectory() as folder:
            env, saved, _ = fixture(folder)
            restored, _ = convert.reverse_slot(saved, env, native=native, registry={"keys": set()})
            expected, = convert.loaded_zone_metadata(saved, env, native=native, registry={"keys": set()})
            env.binds.zone_prefixes = []
            stream = oldsave.write_slot(restored, native=native)
            for image in (stream, stream[L.OLD_ENVELOPE:]):
                actual, = convert.native_zone_metadata(image, env, native=native)
                for key in ('entities', 'fresh_entities', 'placement_sha1', 'source_placement_sha1'):
                    assert actual[key] == expected[key], key
            # Saving an unvisited cached record preserves its original source hash.
            result = convert.old_stream_to_new(stream, env, now=0, native=native,
                zone_captures=[actual], require_capture_metadata=True)
            assert result.refused is None, result.refused
            record, = container.read_file(result.file_bytes)['sections']['ZONE']['data']['records']
            assert record['content_hash'] == expected['source_placement_sha1']
            assert not next(s for s in record['states'] if s['ordinal'] == 1)['flags_b'] & 8
            env.binds.zone_prefixes = Z.load(env.binds.build)
            again, = convert.loaded_zone_metadata(result.file_bytes, env, native=native)
            assert again['fresh_entities'] == expected['fresh_entities']


def test_unmarked_native_zeros_are_still_removals_and_missing_host_sidecar_resets():
    with tempfile.TemporaryDirectory() as folder:
        env, saved, _ = fixture(folder)
        restored, _ = convert.reverse_slot(saved, env)
        restored['zones'][0]['states'][0]['payload'] = bytes(8)
        capture, = convert.native_zone_metadata(oldsave.write_slot(restored), env)
        assert not capture.get('fresh_entities')
        env.binds.zone_prefixes = []
        reset, _ = convert.reverse_slot(saved, env)
        assert not reset['zones']
        assert convert.native_zone_metadata(oldsave.write_slot(reset), env) == []


def test_native_fresh_tail_rejects_invalid_or_stale_provenance():
    with tempfile.TemporaryDirectory() as folder:
        env, saved, _ = fixture(folder)
        restored, _ = convert.reverse_slot(saved, env)
        for mutation in ('alive', 'dynamic', 'tailstate', 'wrong_zone', 'wrong_map', 'duplicate_placement', 'empty_prefix', 'overflow', 'leading_zero'):
            broken = copy.deepcopy(restored)
            record = broken['zones'][0]
            sentinel = record['states'][0]
            if mutation == 'alive': sentinel['flags_b'] = 8
            elif mutation == 'dynamic': record['dynamic'][0] = 0; record['dynamic_count'] = 1
            elif mutation == 'tailstate': record['ordinal_map'][3] = record['ordinal_map'][0]
            else:
                table = broken['zone_strings']; offset = table['offsets'][sentinel['def_name'] & 0xffffff]
                fields = oldsave.zone_string(table, sentinel['def_name']).split('|')
                if mutation == 'wrong_zone': fields[1] = '0'*64
                elif mutation == 'wrong_map': fields[3] = '0'*40
                elif mutation == 'duplicate_placement': fields[4] = '0,0,0'
                elif mutation == 'overflow': fields[4] = '4294967296'
                elif mutation == 'leading_zero': fields[4] = '01'
                else: fields[4] = ''
                text = '|'.join(fields).encode() + b'\0'
                arena = bytearray(table['arena']); arena[offset:offset+len(text)] = text; table['arena'] = bytes(arena)
            try:
                convert.native_zone_metadata(oldsave.write_slot(broken), env)
            except ValueError:
                pass
            else:
                assert False, mutation
