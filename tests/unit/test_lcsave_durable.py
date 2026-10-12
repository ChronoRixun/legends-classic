"""Durable recording and native representability regressions; synthetic inputs only."""
import copy
import json
import os
import tempfile
import shutil
from test_lcsave import make_build, make_old_save, _era_model
from lcsave import binds, catalogue, legacy, container, convert, oldsave, layout as L, keys, conversations


def _env(d, zone_entities=None):
    root = make_build(os.path.join(d, 'build'), zone_entities=zone_entities)
    b = binds.Binds(root)
    model = _era_model(b, b)
    cat = catalogue.Catalogue()
    cat.update(catalogue.tables_from_hashes(legacy.Era(model, '13').tables), 13)
    ep, cp = os.path.join(d, 'eras.json'), os.path.join(d, 'cat.json')
    with open(ep, 'w') as f: json.dump(model, f)
    cat.save(cp)
    return convert.Environment(root, eras_path=ep, catalogue_path=cp)


def _secs(f):
    return [(t, s['entry']['major'], s['entry']['minor'], s['entry']['flags'], s['data'] if s['data'] is not None else s['payload']) for t in f['order'] for s in [f['sections'][t]]]


def _converted(env):
    raw = oldsave.write_slot(make_old_save(def_count=len(env.binds.item)))
    res = convert.convert_slot(raw, 'synthetic.save', env, now=0)
    assert res.refused is None, res.refused
    return raw, res.file_bytes


def test_canonical_keys_text():
    class Fake:
        stat = ['Shared/MixedCase']; item = []; enhancement = []; name_a = []
        name_b = {}; trit = []; shared_talent = []; hero_talent = {}; costume = {}
        mission_file = []; objective = []; course = []; grade = []; review = {}; xpoint = []
        trivia = {}; zone_names = []
        def key_stat(self, i): return ('Shared/MixedCase', '50%')
    assert convert._name_index(Fake())['STAT'][keys.key_hash('Shared/MixedCase', '50%')] == 'shared%2fmixedcase/50%25'


def test_capture_unknown_and_conversation_drops_nonzero():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d); raw, saved = _converted(env)
        f = container.read_file(saved)
        z = f['sections']['ZONE']['data']['records'][0]
        assert z['capture_flags'] == 2
        z['conversation_digest'] = bytes(32)
        patched = container.write_file(L.KIND_CAMPAIGN, _secs(f), f['header'])
        restored, notes = convert.reverse_slot(patched, env)
        assert restored['zones'][0]['conversation'] == [0] * 5
        assert any('conversation provenance unknown: heard marks dropped' in n for n in notes)


def test_native_rejects_quantity_stack_position_and_names():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d); raw, saved = _converted(env)
        cases = [lambda s: s['ITEM']['def_state'][0].update(quantity=256),
                 lambda s: s['MISS'].update(stack_depth=3),
                 lambda s: s['ZONE']['records'][0]['states'][0].update(position=[40000., 0., 0.]),
                 lambda s: s['ZONE']['records'][0]['states'][0].update(def_name=999)]
        for mutate in cases:
            f = container.read_file(saved)
            mutate({t: sec['data'] for t, sec in f['sections'].items()})
            bad = container.write_file(L.KIND_CAMPAIGN, _secs(f), f['header'])
            try: convert.reverse_slot(bad, env)
            except convert.ConvertError: pass
            else: assert False, 'unrepresentable input accepted'


def test_keep_twice_pins_keys_and_lgcy():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d); raw, saved = _converted(env)
        f = container.read_file(saved)
        original_keys = list(reversed(f['sections']['KEYS']['data']['keys']))
        f['sections']['KEYS']['data']['keys'] = original_keys
        opaque = b'opaque reference to index ' + bytes([3, 0, 0, 128])
        saved = container.write_file(L.KIND_CAMPAIGN, _secs(f) + [('FUTR', 1, 0, L.SECTION_KEEP, opaque)], f['header'])
        lgcy = container.read_file(saved)['sections']['LGCY']['payload']
        for _ in range(2):
            restored, _ = convert.reverse_slot(saved, env)
            res = convert.old_stream_to_new(oldsave.write_slot(restored), env, retained_file=saved, now=0,
                                             zone_captures=convert.loaded_zone_metadata(saved, env), require_capture_metadata=True)
            assert res.refused is None, res.refused
            saved = res.file_bytes
            f = container.read_file(saved)
            assert f['sections']['FUTR']['payload'] == opaque
            assert f['sections']['LGCY']['payload'] == lgcy
            assert f['sections']['KEYS']['data']['keys'][:len(original_keys)] == original_keys


def test_profile_import_and_retention():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d)
        raw = oldsave.write_profile_file('synthetic', make_old_save(def_count=len(env.binds.item))['profile'])
        r = convert.convert_profile(raw, 'settings.dat', env, now=0)
        assert r.refused is None, r.refused
        original = container.read_file(r.file_bytes)
        assert original['sections']['LGCY']['data']['sha1'] == __import__('hashlib').sha1(raw).digest()
        desc, p = convert.reverse_profile(r.file_bytes, env)
        res = convert.old_profile_to_new(oldsave.write_profile_file(desc, p), env, retained_file=r.file_bytes, now=0)
        assert res.refused is None, res.refused
        assert container.read_file(res.file_bytes)['sections']['LGCY']['payload'] == original['sections']['LGCY']['payload']

def test_observed_mapping_tombstone_and_cached_provenance():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d); raw, saved = _converted(env)
        captures = convert.loaded_zone_metadata(saved, env)
        assert captures
        captures[0]['capture_flags'] = 0
        captures[0]['conversation_digest'] = bytes.fromhex(conversations.zone_digest(env.binds.build, 'zone/x/y'))
        m = oldsave.read_slot(raw)
        # Native ordinal 1 is the second factory's instance, ordinal 2 is absent/dead.
        m['zones'][0]['ordinal_map'][0], m['zones'][0]['ordinal_map'][1] = m['zones'][0]['ordinal_map'][1], 0
        a, b = captures[0]['entities'][:2]
        a['ordinal'], b['ordinal'] = 2, 1
        result = convert.old_stream_to_new(oldsave.write_slot(m), env, zone_captures=captures, require_capture_metadata=True, now=0)
        assert result.refused is None, result.refused
        f = container.read_file(result.file_bytes)
        record = f['sections']['ZONE']['data']['records'][0]
        tombstone = next(s for s in record['states'] if s['ordinal'] == 2)
        assert tombstone['flags_b'] == 0 and tombstone['placement_index'] == a['placement_index']
        restored, _ = convert.reverse_slot(result.file_bytes, env)
        dead = restored['zones'][0]['ordinal_map'][0]
        assert dead and not restored['zones'][0]['states'][dead]['flags_b'] & 8
        cached = convert.loaded_zone_metadata(result.file_bytes, env)
        for _ in range(2):
            r = convert.old_stream_to_new(oldsave.write_slot(restored), env, zone_captures=cached, require_capture_metadata=True, now=0)
            assert r.refused is None, r.refused
            assert container.read_file(r.file_bytes)['sections']['ZONE']['data']['records'][0]['conversation_digest'] == bytes.fromhex(conversations.zone_digest(env.binds.build, 'zone/x/y'))
        assert convert.old_stream_to_new(raw, env, require_capture_metadata=True).refused
        captures[0]['capture_flags'] = 1
        assert convert.old_stream_to_new(raw, env, zone_captures=captures, require_capture_metadata=True).refused

def test_same_name_twins_with_skipped_factory_use_actual_placement():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d, [('gate', ['gate01', 'gate01']), ('crate', ['crate01']), ('crate_pinned', ['crate02']),
                       ('spawner_a', ['sp01']), ('spawner_b', ['sp02']), ('lamp', ['lamp01']), ('spot', ['spot01'])])
        m = make_old_save(def_count=len(env.binds.item))
        z = m['zones'][0]
        z['states'][2]['inst_name'] = z['states'][1]['inst_name']
        z['ordinal_map'][0], z['ordinal_map'][1], z['ordinal_map'][2] = 2, 3, 0
        num = env.binds.zone_numbering('zone/x/y')
        captures = [dict(zone='zone/x/y', time_stamp=z['time_stamp'], placement_sha1=bytes.fromhex(num['sha1']),
                         conversation_digest=bytes.fromhex(conversations.zone_digest(env.binds.build, 'zone/x/y')), capture_flags=0,
                         entities=[dict(ordinal=1, placement_index=1, definition_name='gate', instance_name='gate01'),
                                   dict(ordinal=2, placement_index=3, definition_name='crate_pinned', instance_name='crate02')])]
        res = convert.old_stream_to_new(oldsave.write_slot(m), env, zone_captures=captures, require_capture_metadata=True, now=0)
        assert res.refused is None, res.refused
        record = container.read_file(res.file_bytes)['sections']['ZONE']['data']['records'][0]
        assert record['states'][0]['placement_index'] == 1
        restored, _ = convert.reverse_slot(res.file_bytes, env)
        z = restored['zones'][0]
        assert z['ordinal_map'][0] == 0 and z['states'][z['ordinal_map'][1]]['payload'] == b'\x11' * 8
        cached = convert.loaded_zone_metadata(res.file_bytes, env)
        assert cached[0]['entities'][0]['ordinal'] == 2

def test_native_reference_positions_respect_current_budgets():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d); _, saved = _converted(env)
        item = container.read_file(saved)['sections']['ITEM']['data']['instances'][2]
        pos = convert.PositionTables(env)
        cases = [('flat names', lambda: pos._nama.update({item['name_a']: 32}), lambda: pos.instance(item)),
                 ('category names', lambda: pos._namb.update({item['name_b']: 4}), lambda: pos.instance(item)),
                 ('special items', lambda: pos._trit.update({item['special']: 128}), lambda: pos.instance(item)),
                 ('definition', lambda: pos._item.update({item['definition']: 160}), lambda: pos.item(item['definition'])),
                 ('costume', lambda: pos._cost.update({next(iter(pos._cost)): 10}), lambda: pos.costume_slot(next(iter(pos._cost)))),
                 ('stats', lambda: pos._stat.update({next(iter(pos._stat)): 297}), lambda: pos.stat(next(iter(pos._stat))))]
        for label, change, operation in cases:
            pos = convert.PositionTables(env)
            change()
            try: operation()
            except convert.ConvertError as e: assert 'native' in str(e), (label, str(e))
            else: assert False, label + ' native budget ignored'


def test_native_whole_build_counts_refuse_future_tables():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d)
        cases = [('definitions', env.binds, 'item', env.binds.item + ['future'] * (161 - len(env.binds.item))),
                 ('heroes', env.binds, 'hero_count', 22),
                 ('stats', env.binds, 'stat', env.binds.stat + ['future'] * (298 - len(env.binds.stat))),
                 ('flat names', env.binds, 'name_a', env.binds.name_a + ['future'] * (33 - len(env.binds.name_a))),
                 ('special items', env.binds, 'trit', env.binds.trit + ['future'] * (129 - len(env.binds.trit))),
                 ('category names', env.binds, 'name_b', {**env.binds.name_b, next(iter(env.binds.name_b)): ['future'] * 5}),
                 ('costumes', env.binds, 'costume', {**env.binds.costume, 'hero_a': {10: 'future'}})]
        for label, obj, attr, oversized in cases:
            original = getattr(obj, attr)
            setattr(obj, attr, oversized)
            try:
                try: convert.PositionTables(env)
                except convert.ConvertError as e: assert 'native' in str(e), (label, str(e))
                else: assert False, label + ' oversized build accepted'
            finally: setattr(obj, attr, original)


def test_review_discard_releases_exclusive_world_items():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d); _, saved = _converted(env)
        for reason in ('hash', 'names', 'incomplete'):
            f = container.read_file(saved)
            r = f['sections']['ZONE']['data']['records'][0]
            if reason == 'hash': r['content_hash'] = bytes(20)
            elif reason == 'names': r['states'][0]['placement_index'] = 999
            else: r['capture_flags'] = 1
            # A world item not owned by any record must remain intact.
            world = f['sections']['ITEM']['data']['world']
            extra = copy.deepcopy(world[0]); extra['handle'] = 6; world.append(extra)
            restored, notes = convert.reverse_slot(container.write_file(L.KIND_CAMPAIGN, _secs(f), f['header']), env)
            assert restored['zones'] == [], reason
            assert [w['slot'] for w in restored['items']['world']] == [6], reason
            assert any('record not applied' in n for n in notes), reason


def test_review_discard_preserves_shared_world_items():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d); _, saved = _converted(env)
        maps = os.path.join(env.binds.build, 'Maps', 'zone', 'x')
        shutil.copyfile(os.path.join(maps, 'y.engb'), os.path.join(maps, 'z.engb'))
        f = container.read_file(saved)
        records = f['sections']['ZONE']['data']['records']
        survivor = copy.deepcopy(records[0])
        survivor['zone'] = next(i for i, z in convert.PositionTables(env)._zone.items() if z == 'zone/x/z')
        survivor['content_hash'] = bytes.fromhex(env.binds.zone_numbering('zone/x/z')['sha1'])
        records.append(survivor); records[0]['capture_flags'] = 1
        restored, _ = convert.reverse_slot(container.write_file(L.KIND_CAMPAIGN, _secs(f), f['header']), env)
        assert len(restored['zones']) == 1
        assert [w['slot'] for w in restored['items']['world']] == [5]


def test_review_duplicate_destination_refuses_without_stream():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d); _, saved = _converted(env)
        f = container.read_file(saved)
        states = f['sections']['ZONE']['data']['records'][0]['states']
        duplicate = copy.deepcopy(states[0]); duplicate['ordinal'] = 4; duplicate['payload'] = b'\x99' * 8
        states.append(duplicate)
        try: convert.reverse_slot(container.write_file(L.KIND_CAMPAIGN, _secs(f), f['header']), env)
        except convert.ConvertError as e: assert 'duplicate destination placement' in str(e)
        else: assert False, 'two ordinals overwrote one destination'


def test_review_unknown_flags_refuse_even_with_changed_hash():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d); _, saved = _converted(env)
        f = container.read_file(saved)
        f['sections']['ZONE']['data']['records'][0].update(capture_flags=4, content_hash=bytes(20))
        try: convert.reverse_slot(container.write_file(L.KIND_CAMPAIGN, _secs(f), f['header']), env)
        except convert.ConvertError as e: assert 'unsupported capture status bits' in str(e)
        else: assert False, 'unknown flags discarded instead of refused'


def test_native_dangling_unnumbered_world_state_is_not_a_save_refusal():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d); _, saved = _converted(env)
        for kind in ('smart', 'dynamic'):
            native = make_old_save(def_count=len(env.binds.item))
            z = native['zones'][0]
            native['items']['world'] = [dict(slot=h, instance=copy.deepcopy(native['items']['world'][0]['instance'])) for h in range(13)]
            z['states'][4].update(payload=b'\x0d\x01'+bytes(6), flags_a=1, flags_b=7)
            z['dynamic_count'] = int(kind == 'dynamic')
            z['smart_count'] = int(kind == 'smart'); z['smart'][0] = 4
            result = convert.old_stream_to_new(oldsave.write_slot(native), env, zone_captures=convert.loaded_zone_metadata(saved, env), require_capture_metadata=True, now=0)
            assert result.refused is None, (kind, result.refused)
            assert not any(result.dropped.values()), result.dropped
            assert any('dangling world item slot 13' in n and 'native load' in n for n in result.notes)
            records = container.read_file(result.file_bytes)['sections']['ZONE']['data']['records']
            assert all(s['payload_kind'] != 2 for r in records for s in r['states'])
            rebuilt, _ = convert.reverse_slot(result.file_bytes, env)
            assert rebuilt['zones'][0]['dynamic_count'] == rebuilt['zones'][0]['smart_count'] == 0
            assert len(rebuilt['items']['world']) == 13
            imported = convert.convert_slot(oldsave.write_slot(native), 'synthetic.save', env, now=0)
            assert imported.refused is None and imported.dropped['states'] == 1
            assert container.read_file(imported.file_bytes)['sections']['LGCY']['data']['other_dropped'] == 1


def test_native_dangling_numbered_world_state_still_refuses():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d); _, saved = _converted(env)
        native = make_old_save(def_count=len(env.binds.item))
        native['zones'][0]['states'][1].update(payload=b'\x0d\x01'+bytes(6), flags_a=1)
        result = convert.old_stream_to_new(oldsave.write_slot(native), env, zone_captures=convert.loaded_zone_metadata(saved, env), require_capture_metadata=True, now=0)
        assert result.refused and result.file_bytes is None


def test_native_dead_numbered_missing_item_preserves_removed_identity():
    # Native factory gate 0x465c35 checks flags_b bit 8 before item restoration:
    # a dead numbered record removes the authored entity without reading its item slot.
    with tempfile.TemporaryDirectory() as d:
        env = _env(d); _, saved = _converted(env)
        captures = convert.loaded_zone_metadata(saved, env)
        for flags_b in (0, 7, 16, 23):
            native = make_old_save(def_count=len(env.binds.item))
            native['zones'][0]['states'][1].update(payload=b'\x0d\x01'+bytes(6), flags_a=1, flags_b=flags_b)
            raw = oldsave.write_slot(native)
            result = convert.old_stream_to_new(raw, env, zone_captures=captures, require_capture_metadata=True, now=0)
            assert result.refused is None, result.refused
            assert not any(result.dropped.values()), result.dropped
            assert any('dead numbered item' in n and 'slot 13' in n for n in result.notes)
            rec = next(s for s in container.read_file(result.file_bytes)['sections']['ZONE']['data']['records'][0]['states'] if s['ordinal'] == 1 and s['list'] == 1)
            assert rec['placement_index'] == captures[0]['entities'][0]['placement_index']
            assert rec['flags_b'] == flags_b and rec['flags_a'] == 0
            assert rec['payload_kind'] == 1 and rec['payload'] == bytes(8)
            rebuilt, _ = convert.reverse_slot(result.file_bytes, env)
            z = rebuilt['zones'][0]; tombstone = z['states'][z['ordinal_map'][0]]
            assert z['ordinal_map'][0] and not (tombstone['flags_b'] & 8)
            assert not (tombstone['flags_a'] & 1)
            assert z['states'][z['ordinal_map'][1]]['payload'] == b'\x11' * 8
            legacy = convert.convert_slot(raw, 'synthetic.save', env, now=0)
            assert legacy.refused is None and legacy.dropped['states'] == 1


def test_native_transfer_metadata_preserves_state_and_is_inferred():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d)
        native = make_old_save(def_count=len(env.binds.item))
        # Exercise the actual transfer path with earned heard marks, not a zero-only fixture.
        native['zones'][0]['conversation'] = [1, 0, 0, 0, 0]
        native['zones'][0]['states'][1]['payload'] = b'\xa5' * 8
        native['zones'][0]['fog'] = b'\x55' * L.OLD_FOG_BYTES
        raw = oldsave.write_slot(native)
        for stream in (raw, raw[0x84:]):
            captures = convert.native_zone_metadata(stream, env)
            assert len(captures) == 1 and captures[0]['capture_flags'] == 2
            assert captures[0]['conversation_digest'] == bytes(32)
            assert captures[0]['entities'][0]['ordinal'] == 1
            result = convert.old_stream_to_new(stream, env, zone_captures=captures, require_capture_metadata=True, now=0)
            assert result.refused is None, result.refused
            restored, notes = convert.reverse_slot(result.file_bytes, env)
            z = restored['zones'][0]
            assert z['conversation'] == [0] * 5
            assert any('conversation provenance unknown: heard marks dropped' in n for n in notes)
            assert z['states'][z['ordinal_map'][0]]['payload'] == b'\xa5' * 8
            assert z['fog'] == b'\x55' * L.OLD_FOG_BYTES
            assert oldsave.write_slot(native) == raw


def test_native_transfer_metadata_refuses_wrong_numbering():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d); native = make_old_save(def_count=len(env.binds.item))
        native['zones'][0]['states'][1]['def_name'] = native['zones'][0]['states'][3]['def_name']
        try: convert.native_zone_metadata(oldsave.write_slot(native), env)
        except convert.ConvertError: pass
        else: assert False, 'unverifiable native numbering accepted'


def test_native_transfer_metadata_does_not_hash_conversations():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d); native = make_old_save(def_count=len(env.binds.item))
        def forbidden_hash(): raise AssertionError('native transfer should not hash conversation files')
        env.binds.conversation_digest = forbidden_hash
        assert len(convert.native_zone_metadata(oldsave.write_slot(native), env)) == 1

def test_review_native_transfer_metadata_refuses_nonfinite_and_duplicate_zones():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d)
        for stamp in (float('nan'), float('inf'), -float('inf')):
            native = make_old_save(def_count=len(env.binds.item))
            native['zones'][0]['time_stamp'] = stamp
            try: convert.native_zone_metadata(oldsave.write_slot(native), env)
            except convert.ConvertError: pass
            else: assert False, 'nonfinite inferred timestamp accepted before native application'
        native = make_old_save(def_count=len(env.binds.item))
        native['zones'].append(copy.deepcopy(native['zones'][0]))
        try: convert.native_zone_metadata(oldsave.write_slot(native), env)
        except convert.ConvertError: pass
        else: assert False, 'duplicate inferred zone accepted before native application'


def test_fifth_level_optional_bits_written_and_ignored():
    """XML2 Fix 1.5's fifth-level catch-up marker: header optional bits 1 / 2 beside KEYS (bit 0); an import vouches for
    neither; the loader's direction ignores them."""
    assert (L.OPTIONAL_KEYS_PRESENT, L.OPTIONAL_LEVEL_SKILL_POINTS, L.OPTIONAL_LEVEL_STAT_POINTS) == (1, 2, 4)
    with tempfile.TemporaryDirectory() as d:
        env = _env(d); raw, saved = _converted(env)
        assert container.read_file(saved)['header']['optional_features'] & 6 == 0
        restored, _ = convert.reverse_slot(saved, env)
        captures = convert.loaded_zone_metadata(saved, env)
        plain = convert.old_stream_to_new(oldsave.write_slot(restored), env, retained_file=saved, zone_captures=captures,
                                          require_capture_metadata=True, now=0)
        marked = convert.old_stream_to_new(oldsave.write_slot(restored), env, retained_file=saved, zone_captures=captures,
                                           require_capture_metadata=True, now=0,
                                           optional_features=L.OPTIONAL_LEVEL_SKILL_POINTS | L.OPTIONAL_LEVEL_STAT_POINTS)
        assert plain.refused is None and marked.refused is None, (plain.refused, marked.refused)
        hp, hm = container.read_file(plain.file_bytes)['header'], container.read_file(marked.file_bytes)['header']
        assert hp['optional_features'] & 6 == 0 and hm['optional_features'] == hp['optional_features'] | 6
        assert oldsave.write_slot(convert.reverse_slot(plain.file_bytes, env)[0]) == oldsave.write_slot(convert.reverse_slot(marked.file_bytes, env)[0])
