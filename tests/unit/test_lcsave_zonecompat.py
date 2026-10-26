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


def _equivalence_case(folder, extra=None):
    """The converted save's exact-hash record, then the map gains xml1heaviness (and `extra`) on numbered and smart
    definitions; -> (env, saved, report, restored before the change)"""
    env = _env(folder)
    _, saved = _converted(env)
    before, _ = convert.reverse_slot(saved, env)
    previous = Path(folder) / 'previous'
    shutil.copytree(env.binds.build, previous)
    path = Path(env.binds.zone_file('zone/x/y'))
    root = xmlb.decode(path.read_bytes())
    for name in ('gate', 'lamp'):
        next(e for e in root.iter('entity') if e.get('name') == name).set('xml1heaviness', '4')
    if extra:
        extra(root)
    _xmlb(str(path), root)
    report = Z.generate(previous, env.binds.build)
    env.binds._zones.clear()
    env.binds.zone_prefixes = Z.load(env.binds.build)
    return env, saved, report, before


def test_equivalent_definition_attribute_keeps_exact_record():
    with tempfile.TemporaryDirectory() as folder:
        env, saved, report, before = _equivalence_case(folder)
        assert report['accepted'] == ['zone/x/y'] and not report['rejected']
        row, = [r for r in Z.load(env.binds.build) if r['zone'] == Z.zone_hash('zone/x/y')]
        assert len(row['placements']) == len(env.binds.zone_numbering('zone/x/y')['numbered'])
        assert Z.validate_current(env.binds.build) == 1
        restored, notes = convert.reverse_slot(saved, env)
        assert not any('record not applied' in n for n in notes), notes
        assert restored['zones'] == before['zones']
        # Without the sidecar the same save keeps the old whole-file guard.
        env.binds.zone_prefixes = []
        restored, notes = convert.reverse_slot(saved, env)
        assert not restored['zones'] and any('placement file changed' in n for n in notes)


def test_equivalence_rejects_any_other_definition_change():
    def health(root):
        next(e for e in root.iter('entity') if e.get('name') == 'lamp').set('health', '99')
    def moved(root):
        next(e for e in root.iter('inst') if e.get('name') == 'gate01').set('origin', '1 2 3')
    def numbering(root):
        next(e for e in root.iter('entity') if e.get('name') == 'crate').set('smartent', 'false')
    for extra in (health, moved, numbering):
        with tempfile.TemporaryDirectory() as folder:
            env, saved, report, _ = _equivalence_case(folder, extra)
            if extra is numbering:
                continue  # an append-only change: attest() decides; equivalence never sees it
            assert report['rejected'] == ['zone/x/y'], extra.__name__
            restored, notes = convert.reverse_slot(saved, env)
            assert not restored['zones'] and any('record not applied' in n for n in notes)


def test_equivalence_retargets_append_rows_of_the_previous_build():
    with tempfile.TemporaryDirectory() as folder:
        env, saved, report = fixture(folder)              # previous map -> appended map (prefix row)
        appended = Path(folder) / 'appended'
        shutil.copytree(env.binds.build, appended)
        before, _ = convert.reverse_slot(saved, env)
        path = Path(env.binds.zone_file('zone/x/y'))
        root = xmlb.decode(path.read_bytes())
        next(e for e in root.iter('entity') if e.get('name') == 'gate').set('xml1heaviness', '5')
        _xmlb(str(path), root)
        result = Z.generate(appended, env.binds.build)
        assert result['accepted'] == ['zone/x/y'] and result['retargeted'] == 1
        env.binds._zones.clear()
        env.binds.zone_prefixes = Z.load(env.binds.build)
        assert Z.validate_current(env.binds.build) == 2  # the equivalence row and the re-targeted row
        restored, notes = convert.reverse_slot(saved, env)
        assert any('prefix retained' in n for n in notes)
        # Same restored entities; only the fresh-tail sentinel (state 0) names the current map.
        strip = lambda z: dict(z, states=z['states'][1:])
        assert [strip(z) for z in restored['zones']] == [strip(z) for z in before['zones']]
        sentinel = oldsave.zone_string(restored['zone_strings'], restored['zones'][0]['states'][0]['def_name'])
        assert sentinel.split('|')[3] == env.binds.zone_numbering('zone/x/y')['sha1']


def _reviewed_maps(folder, change):
    """(env, saved, previous map bytes, current map bytes): two definitions carry a synthetic script attribute and the
    save's record is made on that map; `change(root)` then edits the current map."""
    env = _env(folder)
    path = Path(env.binds.zone_file('zone/x/y'))
    root = xmlb.decode(path.read_bytes())
    for name in ('gate', 'crate'):
        next(e for e in root.iter('entity') if e.get('name') == name).set('actscript', SCRIPT_BEFORE)
    _xmlb(str(path), root)
    env.binds._zones.clear()
    _, saved = _converted(env)
    previous = path.read_bytes()
    root = xmlb.decode(previous)
    change(root)
    _xmlb(str(path), root)
    env.binds._zones.clear()
    return env, saved, previous, path.read_bytes()


def _drop_guard(name):
    def change(root):
        next(e for e in root.iter('entity') if e.get('name') == name).set('actscript', SCRIPT_AFTER)
    return change


SCRIPT_BEFORE, SCRIPT_AFTER = 'synthetic_step()\\n\\rsynthetic_guard()', 'synthetic_step()'
OLD_SCRIPT, NEW_SCRIPT = Z.value_sha256(SCRIPT_BEFORE), Z.value_sha256(SCRIPT_AFTER)
GATE_EDIT = ('zone/x/y', 'gate', 'actscript', OLD_SCRIPT, NEW_SCRIPT)


def test_reviewed_actscript_edit_is_scoped_to_its_zone_definition_and_values():
    with tempfile.TemporaryDirectory() as folder:
        env, saved, old, new = _reviewed_maps(folder, _drop_guard('gate'))
        row = Z.attest_equivalent('zone/x/y', old, new, reviewed={GATE_EDIT})
        assert row and len(row['placements']) == len(env.binds.zone_numbering('zone/x/y')['numbered'])
        assert Z.attest_equivalent('ZoNe/X/Y', old, new, reviewed={GATE_EDIT}) == row  # zone keys are case-normalised
        # The shipped table (asteroid2_1 shieldup only) rejects the same edit in any other zone.
        assert Z.attest_equivalent('zone/x/y', old, new) is None
        for other in ({('zone/x/z', 'gate', 'actscript', OLD_SCRIPT, NEW_SCRIPT)},            # another zone
                      {('zone/x/y', 'crate', 'actscript', OLD_SCRIPT, NEW_SCRIPT)},           # another definition
                      {('zone/x/y', 'gate', 'note', OLD_SCRIPT, NEW_SCRIPT)},                 # another attribute
                      {('zone/x/y', 'gate', 'actscript', OLD_SCRIPT, Z.value_sha256('x'))},   # another new value
                      {('zone/x/y', 'gate', 'actscript', Z.value_sha256('x'), NEW_SCRIPT)}):  # another old value
            assert Z.attest_equivalent('zone/x/y', old, new, reviewed=other) is None, other
    with tempfile.TemporaryDirectory() as folder:
        # The reviewed edit on gate does not excuse the same edit on crate as well.
        def both(root):
            _drop_guard('gate')(root); _drop_guard('crate')(root)
        env, saved, old, new = _reviewed_maps(folder, both)
        assert Z.attest_equivalent('zone/x/y', old, new, reviewed={GATE_EDIT}) is None
        assert Z.attest_equivalent('zone/x/y', old, new, reviewed={GATE_EDIT, ('zone/x/y', 'crate', 'actscript', OLD_SCRIPT, NEW_SCRIPT)})
    with tempfile.TemporaryDirectory() as folder:
        # A reviewed edit plus xml1heaviness stays equivalent; plus any other definition edit does not.
        def heavy(root):
            _drop_guard('gate')(root); next(e for e in root.iter('entity') if e.get('name') == 'lamp').set('xml1heaviness', '4')
        env, saved, old, new = _reviewed_maps(folder, heavy)
        assert Z.attest_equivalent('zone/x/y', old, new, reviewed={GATE_EDIT})
        root = xmlb.decode(new)
        next(e for e in root.iter('entity') if e.get('name') == 'gate').set('health', '99')
        edited = Path(folder) / 'edited.engb'
        _xmlb(str(edited), root)
        assert Z.attest_equivalent('zone/x/y', old, edited.read_bytes(), reviewed={GATE_EDIT}) is None


def test_reviewed_edit_keeps_the_saved_record_and_other_zones_reject():
    shipped = Z.REVIEWED_CHANGES
    try:
        for zone, kept in (('zone/x/y', True), ('zone/x/z', False)):
            Z.REVIEWED_CHANGES = frozenset({(zone, 'gate', 'actscript', OLD_SCRIPT, NEW_SCRIPT)})
            with tempfile.TemporaryDirectory() as folder:
                env, saved, old, new = _reviewed_maps(folder, _drop_guard('gate'))
                before = Path(folder) / 'before'
                shutil.copytree(env.binds.build, before)
                (before / Path(env.binds.zone_file('zone/x/y')).relative_to(env.binds.build)).write_bytes(old)
                report = Z.generate(before, env.binds.build)
                assert report['accepted' if kept else 'rejected'] == ['zone/x/y'], report
                env.binds._zones.clear()
                env.binds.zone_prefixes = Z.load(env.binds.build)
                restored, notes = convert.reverse_slot(saved, env)
                if kept:
                    assert restored['zones'] and not any('record not applied' in n for n in notes), notes
                else:
                    assert not restored['zones'] and any('placement file changed' in n for n in notes), notes
    finally:
        Z.REVIEWED_CHANGES = shipped


def test_shipped_reviewed_changes_are_the_one_owner_reviewed_edit():
    assert len(Z.REVIEWED_CHANGES) == 1
    (zone, definition, attribute, old, new), = Z.REVIEWED_CHANGES
    assert (zone, definition, attribute) == ('astroid_m/visit1/asteroid2_1', 'shieldup', 'actscript')
    assert len(old) == len(new) == 64 and old != new and int(old, 16) and int(new, 16)
    assert 'actscript' not in Z.EQUIVALENT_ATTRIBUTES


def test_owned_asteroid2_1_magneto_edit_is_equivalent():
    import hashlib, os, unittest
    stable, candidate = os.environ.get('LC_OWNED_STABLE_BUILD'), os.environ.get('LC_OWNED_CANDIDATE_BUILD')
    if not (stable and candidate):
        raise unittest.SkipTest('LC_OWNED_STABLE_BUILD / LC_OWNED_CANDIDATE_BUILD not set (owned builds)')
    zone = 'astroid_m/visit1/asteroid2_1'
    old, new = (Path(binds.Binds(b).zone_file(zone)).read_bytes() for b in (stable, candidate))
    assert old != new
    row = Z.attest_equivalent(zone, old, new)
    assert row and row['current'] == hashlib.sha1(new).digest()
    assert Z.attest_equivalent(zone, old, new, reviewed=frozenset()) is None  # only the reviewed row accepts it
    assert Z.attest_equivalent('astroid_m/visit1/asteroid2_2', old, new) is None  # bound to its zone


def test_plan_against_stable_and_previous_beta_merges_and_writes_nothing():
    with tempfile.TemporaryDirectory() as folder:
        env, saved, report = fixture(folder)              # stable map -> appended map (the previous beta)
        stable, beta = Path(folder) / 'previous', Path(folder) / 'appended'
        shutil.copytree(env.binds.build, beta)
        path = Path(env.binds.zone_file('zone/x/y'))
        root = xmlb.decode(path.read_bytes())
        next(e for e in root.iter('entity') if e.get('name') == 'gate').set('xml1heaviness', '5')
        _xmlb(str(path), root)
        sidecar = (Path(env.binds.build) / Z.REL).read_bytes()
        ledger = Path(folder) / 'ledger.json'
        assert Z.main(['plan', '--previous', str(stable), '--previous', str(beta), env.binds.build,
                       '--ledger-out', str(ledger)]) == 0
        assert (Path(env.binds.build) / Z.REL).read_bytes() == sidecar  # plan writes only the ledger
        rows, accepted, rejected, retargeted, per_build = Z.plan_all([stable, beta], env.binds.build)
        assert ledger.read_text(encoding='utf-8') == Z.ledger_json(rows)
        # stable -> current is an append plus an equivalence edit (no single attestation); beta -> current is
        # equivalent and re-targets beta's stable -> beta row, so a stable save keeps its record.
        assert per_build[str(stable)][1] == ['zone/x/y'] and per_build[str(beta)][0] == ['zone/x/y']
        assert accepted == ['zone/x/y'] and rejected == [] and retargeted == ['zone/x/y']
        assert Z.main(['generate', '--previous', str(stable), '--previous', str(beta), env.binds.build]) == 0
        env.binds._zones.clear()
        env.binds.zone_prefixes = Z.load(env.binds.build)
        assert Z.ledger_json(env.binds.zone_prefixes) == Z.ledger_json(rows)
        restored, notes = convert.reverse_slot(saved, env)
        assert restored['zones'] and any('prefix retained' in n for n in notes), notes
