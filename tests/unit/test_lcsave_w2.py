"""Limits wave 2 (xml2-fix docs/limits-wave2.md, design revision 3): the W2 native layout descriptor, the W2 stream
in both directions and the target-aware representability probe that decides required-feature bit 1 (NATIVE_W2).
Invented build, invented saves: no game data. The same cases run in C++ (xml2-fix test/lcsave_vectors.cpp, test_w2_*)
and byte for byte through export_lcsave_typed_vectors.py (w2-reverse, w2-bit1)."""
import copy
import tempfile

from test_lcsave_native_layout import typed_old_save, registry_fixture, _set_required_features
from test_lcsave_durable import _env
from lcsave import container, convert, oldsave, layout as L, typed_registry as T


def test_w2_descriptor():
    w = L.native_layout('W2')
    assert w is L.W2 and w.feature_bits == 3 and w.contiguous and w.w2 and not L.E10A2.w2 and not L.RETAIL.w2
    assert (w.states, w.ordinals, w.dynamic, w.smart, w.record_count, w.state_record_size) == (4096, 4096, 2048, 2048, 8, 0x20)
    assert (w.record_size, w.manager_size, w.mission, w.payload, w.wrapper, w.transfer_chunks) == (0x24388, 0x122190, 0x121c48, 0x200000, 0x200078, 10486)
    assert (w.definitions, w.item_head_size, w.instance_fixed, w.snapshot_size, w.side_block) == (1024, 0x826, 6, 0x540, 0xa88)
    assert (w.enhancement_records, w.attached_enhancements, w.instances, w.world_slots) == (4096, 4096, 1024, 1024)
    assert (w.objectives, w.objectives_per_act, w.objective_files, w.talent_multiplier, w.talent_pool) == (1024, 127, 64, 200, 256)
    assert (w.zone_string_slots, w.zone_arena, w.zone_strings_size) == (0x2000, 0x20000, 0x28008)
    for n in (L.RETAIL, L.E10A2):
        assert (n.definitions, n.instances, n.world_slots, n.attached_enhancements, n.snapshot_size, n.talent_multiplier) == (160, 256, 150, 375, 0x26c, 100)
    # the talent id space (4.7): position < M, shared position < M - 1
    assert w.talent_id(22, 10) == 4410 and L.talent_engine_id(L.talent_code(22, 199), w) == 4599
    for code, layout in ((L.talent_code(22, 200), w), (L.talent_code(0, 199), w), (L.talent_code(2, 100), L.E10A2), (L.talent_code(0, 99), L.RETAIL)):
        try:
            L.talent_engine_id(code, layout); assert False
        except ValueError as e:
            assert 'does not fit the native layout' in str(e)
    assert L.talent_engine_id(L.talent_code(0, 198), w) == 198 and L.talent_engine_id(L.talent_code(2, 99), L.E10A2) == 299


def _w2_fixture(d):
    env = _env(d)
    root, reg_path, reg = registry_fixture(d)
    raw = oldsave.write_slot(typed_old_save(len(env.binds.item)))
    legacy = convert.convert_slot(raw, 'synthetic.save', env, now=0).file_bytes
    model, _ = convert.reverse_slot(legacy, env, native=L.W2, registry=reg)
    captures = convert.loaded_zone_metadata(legacy, env, native=L.W2, registry=reg)
    return env, reg, legacy, model, captures


def test_w2_stream_round_trip_and_boundaries():
    with tempfile.TemporaryDirectory() as d:
        env, reg, legacy, model, _ = _w2_fixture(d)
        m = copy.deepcopy(model)
        m['items']['def_count'] = 1024
        m['items']['def_state'][2 * 1023:2 * 1023 + 2] = [7, 1]
        m['items']['carried'][0]['definition'] = 1023
        m['mission']['objectives'][1023] = 0x45
        m['mission']['objectives'][300] = 2
        z = m['zones'][0]
        st = next(s for s in z['states'] if s['def_name'])
        st['position'] = [0.5, -32768.5, 40000.0]
        z['states'][4095] = dict(z['states'][1])
        z['ordinal_map'][4095] = 4095
        z['state_count'] = 4096
        while len(m['zones']) < 8:
            m['zones'].append(copy.deepcopy(m['zones'][0]))
        raw = oldsave.write_slot(m, L.W2)
        back = oldsave.read_slot(raw, L.W2)
        assert len(raw) == L.W2.slot_size and oldsave.write_slot(back, L.W2) == raw
        assert back['items']['def_count'] == 1024 and back['items']['carried'][0]['definition'] == 1023
        assert back['mission']['objectives'][1023] == 0x45 and len(back['zones']) == 8 and back['zones'][0]['state_count'] == 4096
        assert next(s for s in back['zones'][0]['states'] if s['def_name'])['position'] == [0.5, -32768.5, 40000.0]
        bad = copy.deepcopy(m); bad['zones'].append(copy.deepcopy(m['zones'][0]))
        try:
            oldsave.write_slot(bad, L.W2); assert False
        except oldsave.OldSaveError as e:
            assert 'zone record count 9 > 8' in str(e)
        bad = copy.deepcopy(m); bad['items']['world'] = [dict(slot=k, instance=m['items']['carried'][1]) for k in range(1025)]
        try:
            oldsave.write_slot(bad, L.W2); assert False
        except oldsave.OldSaveError as e:
            assert 'world item count 1025 > 1024' in str(e)
        # the world-item slot lives in the W2 record's own u16; payload byte 0 stays 0
        owner = [s for s in model['zones'][0]['states'] if s['flags_a'] & 1]
        assert owner and all(s['world_slot'] == model['items']['world'][0]['slot'] and s['payload'][0] == 0 for s in owner)
        assert all(s['world_slot'] == L.WORLD_SLOT_NONE for s in model['zones'][0]['states'] if not s['flags_a'] & 1)


def test_w2_saver_and_the_probe_oracle():
    with tempfile.TemporaryDirectory() as d:
        env, reg, legacy, model, captures = _w2_fixture(d)
        e10a2 = oldsave.write_slot(convert.reverse_slot(legacy, env, native=L.E10A2, registry=reg)[0], L.E10A2)

        def save(edit=None):
            m = copy.deepcopy(model)
            if edit:
                edit(m)
            r = convert.old_stream_to_new(oldsave.write_slot(m, L.W2), env, retained_file=legacy, zone_captures=captures,
                                          require_capture_metadata=True, campaign_serial=17, save_sequence=2, now=0, native=L.W2)
            assert r.refused is None, r.refused
            return r.file_bytes, container.read_file(r.file_bytes)['header']['required_features']

        plain, bits = save()
        assert bits == 1 and convert.representable(plain, env, L.E10A2) == ''
        # the pre-W2 build loads the representable W2 save to its own stream (talent ids re-based to M = 100)
        assert oldsave.write_slot(convert.reverse_slot(plain, env, native=L.E10A2, registry=reg)[0], L.E10A2) == e10a2

        def first_state(m):
            return next(s for s in m['zones'][0]['states'] if s['def_name'])

        def position(m): first_state(m)['position'][0] = 0.5

        def big(m): first_state(m)['position'][1] = 40000.0

        def handle(value):
            def edit(m):
                old = m['items']['world'][0]['slot']
                for s in m['zones'][0]['states']:
                    if s['flags_a'] & 1 and s['world_slot'] == old:
                        s['world_slot'] = value
                m['items']['world'][0]['slot'] = value
            return edit

        def instances(n):
            def edit(m):
                bare = dict(copy.deepcopy(m['items']['carried'][0]), prefixes=[], own=[], suffixes=[])
                total = len(m['items']['carried']) + len(m['items']['world']) + sum(len(h['equipment']['equipped']) for h in m['heroes'] + m['restore'])
                m['items']['carried'] += [copy.deepcopy(bare) for _ in range(n - total)]
            return edit

        for edit, marks, what in ((position, True, 'state position not representable'), (big, True, 'state position not representable'),
                                  (handle(150), True, 'world handle'), (handle(149), False, ''),
                                  (instances(257), True, 'instance pool'), (instances(256), False, '')):
            f, bits = save(edit)
            why = convert.representable(f, env, L.E10A2)
            assert bool(bits & 2) == marks and (what in why if marks else why == ''), (what, bits, why)
            if marks:
                try:
                    convert.reverse_slot(f, env, native=L.E10A2, registry=reg); assert False
                except convert.ConvertError as e:
                    assert str(e) == container.W2_REFUSED
                m2, _ = convert.reverse_slot(f, env, native=L.W2, registry=reg)    # the W2 build loads it
                assert m2['zones']
        f, _ = save(position)
        assert next(s for s in convert.reverse_slot(f, env, native=L.W2, registry=reg)[0]['zones'][0]['states'] if s['def_name'])['position'][0] == 0.5
        # a bit-1 file is refused by name on E10A2 and as a feature-1 file on RETAIL; bit 1 never without bit 0
        assert container.feature_decision(3, L.E10A2) == (False, container.W2_REFUSED, False)
        assert container.feature_decision(3, L.RETAIL) == (False, container.DOWNGRADE_REFUSED, False)
        try:
            container.read_file(_set_required_features(plain, 2)); assert False
        except container.ContainerError as e:
            assert 'damaged marker' in str(e)
