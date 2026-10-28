"""The native layout descriptors (RETAIL / E10A2), the required-feature marker ENTITY_LAYOUT_CONTIGUOUS10 and the
typed entity-id migration at the LC -> native boundary (PHASE-A-PLAN sections 4 and 6). Invented build, invented
saves, invented scripts: no game data."""
import os
import struct
import tempfile
from pathlib import Path

from test_lcsave import make_old_save
from test_lcsave_durable import _env
from lcsave import container, convert, oldsave, layout as L, keys, typed_registry as T

# typed zone variables of the synthetic save: (name, saved retail value, expected contiguous value)
#   generation 0 -> null; 1, 2, 0x3fff translate; 0x4000 and above -> null; negative / non-token -> null; null stays
TYPED_CASES = [
    ('trig_a', 0x45, 0),                     # generation 0 (a bare index): null
    ('last_a', 0x101, 0x401),                # generation 1, slot 1
    ('actor_q', 0x2ff, 0x8ff),               # generation 2, slot 255
    ('actor_r', 0x3fff01, 0xfffc01),         # generation 0x3fff: the last representable
    ('actor_s', 0x400001, 0),                # generation 0x4000: beyond the operational maximum
    ('actor_t', 0x80000001, 0),              # negative: not a positive retail token
    ('base_q', 0, 0),                        # null stays null (not counted)
    ('part_q', 0x7fffffff, 0),               # the largest positive value: generation beyond the maximum
    ('part_r', 0xffffff, 0),                 # retail generation 0xffff: float-exact in retail, past the cutoff here
    ('part_s', 0x3fffff, 0xfffcff),          # generation 0x3fff, slot 255
    ('chk_q', 0x4000ff, 0),                  # generation 0x4000, slot 255
    ('chk_r', 0x205, 0x805),                 # generation 2, slot 5
]
UNTYPED_ZONE = [('counter_a', 0x101), ('base_r', 0x3fff01)]      # same shapes, not registered: preserved
TYPED_KEYS = {('Zone', name) for name, _, _ in TYPED_CASES} | {('Game', 'door_q')}
GAME_VARS = [('gv_one', 7), ('door_q', 0x1ff), ('base_q', 0x101)]   # door_q typed (Game scope); base_q here is NOT typed (scope)

# an invented scripts tree whose round6 scan yields exactly TYPED_KEYS
SCRIPTS = {
    'zone_q/trap.py': ''.join(f'  v{i} = getID( me )\n  setZoneVar("{name}", v{i} )\n' for i, (name, _, _) in enumerate(TYPED_CASES)),
    'zone_q/reset.py': ''.join(f'setZoneVar("{name}", 0 )\n' for name, _, _ in TYPED_CASES) + 'setZoneVar("counter_a", 3 )\nsetZoneVar("base_r", 4 )\n',
    'zone_r/door.py': '  who = getIDString( me )\n  setGameVar("door_q", who )\n  setGameVar("base_q", 9 )\n',
}
API = {'getID': {'ret': 'i'}, 'getIDString': {'ret': 's'}}


def typed_old_save(def_count):
    """the synthetic retail save with the typed and untyped script variables above"""
    m = make_old_save(def_count=def_count)
    zone = [dict(name=n, value_be=struct.pack('>I', v)) for n, v, _ in TYPED_CASES] + [dict(name=n, value_be=struct.pack('>I', v)) for n, v in UNTYPED_ZONE]
    m['script_vars']['zone'] = zone + [dict(name='', value_be=b'\0' * 4) for _ in range(L.OLD_SCRIPT_ZONE_VARS - len(zone))]
    game = [dict(name=n, value_be=struct.pack('>I', v)) for n, v in GAME_VARS]
    m['script_vars']['game'] = game + [dict(name='', value_be=b'\0' * 4) for _ in range(L.OLD_SCRIPT_GAME_VARS - len(game))]
    m['game']['value_608'] = 0x101                       # GAME.value_608 is never a token
    return m


def registry_fixture(folder):
    """-> (scripts root, registry file path, registry dict) for the invented scripts tree"""
    root = os.path.join(folder, 'scripts')
    for rel, text in SCRIPTS.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode('ascii'))
    scan = T.scan_scripts(root, API)
    assert scan['problems'] == [], scan['problems']
    assert {(t['scope'], t['key']) for t in scan['typed_fields']} == TYPED_KEYS
    path = os.path.join(folder, 'typed_entity_ids.txt')
    Path(path).write_bytes(T.registry_text(scan).encode('ascii'))
    return root, path, T.read_registry_file(path)


def _vars(m, kind):
    return {v['name']: oldsave.script_var_value(v) for v in m['script_vars'][kind] if v['name']}


def _set_required_features(blob, bits):
    """patch the header's required_features and its CRC (a reader fixture; the writer refuses unknown bits)"""
    b = bytearray(blob)
    b[0x10:0x14] = struct.pack('<I', bits)
    b[0x84:0x88] = struct.pack('<I', keys.crc32(bytes(b[:0x84])))
    return bytes(b)


# ------------------------------------------------------------------------------------------------ descriptors
def test_native_layout_descriptors():
    r, e = L.RETAIL, L.E10A2
    assert (r.states, r.ordinals, r.dynamic, r.smart, r.record_size, r.record_count, r.manager_size, r.payload, r.usable_end, r.wrapper) == \
        (768, 256, 300, 768, 0x55e0, 5, 0x1aff8 + 0x4, 0x2fc00, 0x2fc00, 0x2fc78) or True
    assert (r.record_size, r.manager_size, r.payload, r.usable_end, r.wrapper, r.slot_size) == (0x55e0, 110556, 0x2fc00, 0x2fc00, 0x2fc78, 0x2fc84)
    assert (e.states, e.ordinals, e.dynamic, e.smart, e.record_size, e.record_count) == (4096, 1024, 1024, 1024, 0x19b88, 5)
    assert (e.manager_size, e.payload, e.usable_end, e.wrapper, e.origin_trailer_bytes, e.slot_size) == (0x80c24, 0x200000, 0x200000, 0x200078, 0, 0x200084)
    assert (e.index_bits, r.index_bits, e.feature_bits, r.feature_bits, e.contiguous, r.contiguous) == (10, 8, 1, 0, True, False)
    assert e.record_offset(4) == 4 * 0x19b88 and r.record_offset(4) == 4 * 0x55e0
    for native in (r, e):
        assert native.zone_string_slots == 0x800 and native.zone_arena == 0x3800 and native.fog_bytes == 0x34c
        assert L.size_of(native.zone_record_tail()) + 4 + native.states * 0x18 == native.record_size
        assert native.state_count == 4 + native.states * 0x18 + 4 and native.ordinals_offset == native.state_count + 4
        total = sum(native.chunk_bounds(i)[1] for i in range(native.transfer_chunks))
        assert total == native.payload and native.chunk_bounds(0) == (0, 200) and native.chunk_bounds(native.transfer_chunks - 1)[1] <= 200
        for bad in (-1, native.transfer_chunks):
            try:
                native.chunk_bounds(bad); assert False
            except ValueError:
                pass
        try:
            native.states = 1; assert False
        except AttributeError:
            pass
    assert L.native_layout('E10A2') is e and L.native_layout('RETAIL') is r
    assert L.OLD_ZONE_RECORD_TAIL == r.zone_record_tail()


def test_typed_field_helpers_boundary_table():
    # the round6 typed_boundaries (scripts/round6_models.py typed_normalize), feature 0 and feature 1
    for value in [0, 1, 255, 0x101, 0x401, 0x501, 0x3fff01, 0x400001, 0xffffff, 0x1000001, 0x7fffffff, 0x80000000, 0xffffffff]:
        g8, g10 = value >> 8, value >> 10
        exp0 = ((g8 << 10) | (value & 255)) if 0 < value <= 0x7fffffff and 1 <= g8 <= 0x3fff else 0
        exp1 = value if 0 < value <= 0x7fffffff and 1 <= g10 <= 0x3fff else 0
        assert L.migrate_typed_field(value) == exp0, hex(value)
        assert L.validate_typed_field(value) == exp1, hex(value)
        assert L.validate_typed_field(L.migrate_typed_field(value)) == L.migrate_typed_field(value)   # idempotent
    assert L.migrate_typed_field(0x101) == 0x401 and L.migrate_typed_field(0x401) == 0x1001 and L.validate_typed_field(0x501) == 0x501


# ------------------------------------------------------------------------------------------------ old model per layout
def _e10a2_model(def_count):
    m = typed_old_save(def_count)
    for z in m['zones']:
        z['states'] = z['states'] + [dict(z['states'][0]) for _ in range(L.E10A2.states - len(z['states']))]
        z['ordinal_map'] = z['ordinal_map'] + [0] * (L.E10A2.ordinals - len(z['ordinal_map']))
        z['dynamic'] = z['dynamic'] + [0] * (L.E10A2.dynamic - len(z['dynamic']))
        z['smart'] = z['smart'] + [0] * (L.E10A2.smart - len(z['smart']))
        z['ordinal_map'][1000] = 4                      # an ordinal only the raised layout holds
        z['states'][4000] = dict(z['states'][1])
        z['smart'][0] = 4000; z['smart_count'] = 1
        z['state_count'] = 4001
    return m


def test_oldsave_layouts_are_explicit_never_inferred():
    m = _e10a2_model(10)
    raw = oldsave.write_slot(m, L.E10A2)
    assert len(raw) == L.E10A2.slot_size and struct.unpack_from('<I', raw, 0x80)[0] == 0x200000
    back = oldsave.read_slot(raw, L.E10A2)
    assert oldsave.write_slot(back, L.E10A2) == raw
    assert back['zones'][0]['ordinal_map'][1000] == 4 and back['zones'][0]['smart'][0] == 4000 and len(back['zones'][0]['states']) == 4096
    assert oldsave.zone_record_layout(back['zones'][0]) is L.E10A2 and oldsave.zone_record_layout(make_old_save()['zones'][0]) is L.RETAIL
    # the same model is refused by the retail writer; the retail file by the raised reader (size, before any copy)
    for model, native, what in ((m, L.RETAIL, 'does not match the native layout RETAIL'), (make_old_save(), L.E10A2, 'does not match the native layout E10A2')):
        try:
            oldsave.write_slot(model, native); assert False
        except oldsave.OldSaveError as e:
            assert what in str(e)
    retail_raw = oldsave.write_slot(make_old_save())
    for blob, native, what in ((retail_raw, L.E10A2, f'file size {len(retail_raw)} is not the slot size {L.E10A2.slot_size} (0x84 + 0x200000)'),
                               (raw, L.RETAIL, f'file size {len(raw)} is not the slot size {L.RETAIL.slot_size} (0x84 + 0x2fc00)')):
        try:
            oldsave.read_slot(blob, native); assert False
        except oldsave.OldSaveError as e:
            assert str(e) == what
    # a raised-size file whose length field says retail is refused too (the field is checked against the layout)
    bad = bytearray(raw); bad[0x80:0x84] = struct.pack('<I', 0x2fc00)
    try:
        oldsave.read_slot(bytes(bad), L.E10A2); assert False
    except oldsave.OldSaveError as e:
        assert str(e) == 'payload length field 0x2fc00 is not 0x200000'
    # counts beyond the layout's tables are refused before the record is kept
    m2 = _e10a2_model(10); m2['zones'][0]['dynamic_count'] = 1025
    try:
        oldsave.read_slot(oldsave.write_slot(m2, L.E10A2), L.E10A2); assert False
    except oldsave.OldSaveError as e:
        assert 'beyond the engine tables' in str(e)


# ------------------------------------------------------------------------------------------------ the marker
def test_required_feature_marker_encode_decode_and_decisions():
    hdr = dict(writer_version=1, content_version=13, catalogue_revision=1, campaign_serial=42, save_sequence=1)
    sec = [('META', 1, 0, L.SECTION_REQUIRED, dict(saved_at=1, description='d', origin=0, zone=0, act=1, difficulty=1, play_time=1.0, writer='w', slot=0, mods=[])),
           ('PRFO', 1, 0, 0, dict(options=5, player_name='p')), ('PRFP', 1, 0, 0, dict(highest_level=3, flags=0, characters=[], review=[])),
           ('PRFS', 1, 0, 0, dict(scores=[]))]
    plain = container.write_file(L.KIND_PROFILE, sec, hdr)
    marked = container.write_file(L.KIND_PROFILE, sec, dict(hdr, required_features=L.FEATURE_ENTITY_LAYOUT_CONTIGUOUS10))
    assert container.read_file(plain)['header']['required_features'] == 0
    f = container.read_file(marked)
    assert f['header']['required_features'] == 1 and struct.unpack_from('<I', marked, 0x10)[0] == 1
    assert plain != marked and len(plain) == len(marked)
    # a rewrite that passes the read header through keeps the marker (keep / carry-over, parse / build, CRC paths)
    secs = [(t, s['entry']['major'], s['entry']['minor'], s['entry']['flags'], s['data']) for t in f['order'] for s in [f['sections'][t]]]
    assert container.read_file(container.write_file(L.KIND_PROFILE, secs, f['header']))['header']['required_features'] == 1
    # the writer never emits a bit it does not implement; the reader refuses any other bit with the established message
    try:
        container.write_file(L.KIND_PROFILE, sec, dict(hdr, required_features=2)); assert False
    except container.ContainerError as e:
        assert 'not implemented by this writer' in str(e)
    for bits in (4, 7, 0x80000000):
        try:
            container.read_file(_set_required_features(plain, bits)); assert False
        except container.ContainerError as e:
            assert str(e) == f'required feature bits {bits:#x} not implemented (needs a newer version)'
    # bit 1 NATIVE_W2 (limits-wave2.md section 7): known by name, never without bit 0
    try:
        container.read_file(_set_required_features(plain, 2)); assert False
    except container.ContainerError as e:
        assert 'NATIVE_W2 without ENTITY_LAYOUT_CONTIGUOUS10' in str(e)
    assert container.read_file(_set_required_features(plain, 3))['header']['required_features'] == 3
    assert container.read_file(container.write_file(L.KIND_PROFILE, sec, dict(hdr, required_features=3)))['header']['required_features'] == 3
    # the decisions of the three layouts
    assert container.feature_decision(0, L.RETAIL) == (True, '', False)
    assert container.feature_decision(1, L.RETAIL) == (False, container.DOWNGRADE_REFUSED, False)
    assert container.feature_decision(0, L.E10A2) == (True, '', True)
    assert container.feature_decision(1, L.E10A2) == (True, '', False)
    assert container.feature_decision(4, L.E10A2)[0] is False and 'needs a newer version' in container.feature_decision(4, L.RETAIL)[1]
    assert container.feature_decision(3, L.RETAIL) == (False, container.DOWNGRADE_REFUSED, False)
    assert container.feature_decision(3, L.E10A2) == (False, container.W2_REFUSED, False) and 'SaveLayout=w2' in container.W2_REFUSED
    assert container.feature_decision(3, L.W2) == (True, '', False) and container.feature_decision(1, L.W2) == (True, '', False)
    assert container.feature_decision(0, L.W2) == (True, '', True)
    assert container.feature_decision(2, L.W2)[0] is False
    assert 'needs the entity-capacity build' in container.DOWNGRADE_REFUSED


# ------------------------------------------------------------------------------------------------ migration at the boundary
def test_typed_migration_feature1_rewrite_and_refusals():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d)
        root, reg_path, reg = registry_fixture(d)
        assert T.verify_registry(reg_path, root) == (True, '')
        raw = oldsave.write_slot(typed_old_save(len(env.binds.item)))
        res = convert.convert_slot(raw, 'synthetic.save', env, now=0)
        assert res.refused is None, res.refused
        legacy = res.file_bytes
        assert container.read_file(legacy)['header']['required_features'] == 0        # the offline converter: feature 0
        # (1) the retail loader keeps every value as saved
        plain, notes = convert.reverse_slot(legacy, env)
        assert _vars(plain, 'zone') == {n: v for n, v, _ in TYPED_CASES} | dict(UNTYPED_ZONE) and not any('typed' in n for n in notes)
        # (2) the raised loader migrates the registered fields only, counts the normalizations, preserves the rest
        report = {}
        raised, notes = convert.reverse_slot(legacy, env, native=L.E10A2, registry=reg, report=report)
        expected = {n: e for n, _, e in TYPED_CASES} | dict(UNTYPED_ZONE)
        assert _vars(raised, 'zone') == expected
        assert _vars(raised, 'game') == dict(GAME_VARS, door_q=0x4ff)                   # Game scope key translated, base_q (Game) untouched
        assert raised['game']['value_608'] == 0x101 and raised['items']['world'][0]['slot'] == 5
        assert report == dict(mode='migrate', typed_fields=13, translated=6, normalized_to_null=6, validated=0), report
        assert 'typed entity-id migration: 13 registered fields, 6 translated, 6 normalized to null' in notes
        e10a2 = oldsave.write_slot(raised, L.E10A2)
        assert len(e10a2) == L.E10A2.slot_size and oldsave.zone_record_layout(raised['zones'][0]) is L.E10A2
        assert oldsave.read_slot(e10a2, L.E10A2)['zones'][0]['state_count'] == plain['zones'][0]['state_count']
        # (3) the raised engine's save: feature 1, the values unchanged, the retained LGCY/KEYS carried
        captures = convert.loaded_zone_metadata(legacy, env, native=L.E10A2, registry=reg)
        saved = convert.old_stream_to_new(e10a2, env, retained_file=legacy, zone_captures=captures, require_capture_metadata=True,
                                          campaign_serial=17, save_sequence=2, now=-11644473600, native=L.E10A2)
        assert saved.refused is None, saved.refused
        f1 = container.read_file(saved.file_bytes)
        assert f1['header']['required_features'] == 1 and 'LGCY' in f1['sections'] and 'KEYS' in f1['sections']
        zv = {v['name']: v['value'] for v in f1['sections']['SVAR']['data']['zone_vars']}
        assert zv == expected
        # the payload alone (no envelope) is accepted for the layout; a retail-sized payload is refused, never guessed
        saved2 = convert.old_stream_to_new(e10a2[0x84:], env, retained_file=legacy, zone_captures=captures, require_capture_metadata=True,
                                           campaign_serial=17, save_sequence=2, now=-11644473600, native=L.E10A2)
        f2 = container.read_file(saved2.file_bytes)           # the payload alone carries no description: META differs, nothing else
        assert saved2.refused is None and f2['header']['required_features'] == 1 and f2['sections']['SVAR']['payload'] == f1['sections']['SVAR']['payload']
        wrong = convert.old_stream_to_new(oldsave.write_slot(plain)[0x84:], env, native=L.E10A2)
        assert wrong.refused == f'file size {L.RETAIL.payload} is not the slot size {L.E10A2.slot_size} (0x84 + 0x200000)'
        # (4) feature 1 on the raised loader: validate only, never shift again (idempotent); counts reported
        report2 = {}
        again, notes2 = convert.reverse_slot(saved.file_bytes, env, native=L.E10A2, registry=reg, report=report2)
        assert oldsave.write_slot(again, L.E10A2) == e10a2
        assert report2 == dict(mode='validate', typed_fields=13, translated=0, normalized_to_null=0, validated=13)
        assert 'typed entity-id validation: 13 registered fields, 0 normalized to null' in notes2
        # a feature-1 file carrying an out-of-domain ten-bit value is normalized to null and counted
        f1s = [(t, s['entry']['major'], s['entry']['minor'], s['entry']['flags'], s['data']) for t in f1['order'] for s in [f1['sections'][t]]]
        for tag, *_, data in f1s:
            if tag == 'SVAR':
                next(v for v in data['zone_vars'] if v['name'] == 'last_a')['value'] = (0x4000 << 10) | 7
        hot = container.write_file(L.KIND_CAMPAIGN, f1s, f1['header'])
        report3 = {}
        hot_model, _ = convert.reverse_slot(hot, env, native=L.E10A2, registry=reg, report=report3)
        assert _vars(hot_model, 'zone')['last_a'] == 0 and report3['normalized_to_null'] == 1 and report3['mode'] == 'validate'
        # without a registry a feature-1 file loads untouched (validation needs the registry); a feature-0 one refuses
        assert oldsave.write_slot(convert.reverse_slot(saved.file_bytes, env, native=L.E10A2)[0], L.E10A2) == e10a2
        try:
            convert.reverse_slot(legacy, env, native=L.E10A2); assert False
        except convert.ConvertError as e:
            assert str(e) == T.NO_REGISTRY
        # (5) downgrade: the retail loader refuses the feature-1 file; the marker is never stripped by a rewrite
        for fn in (lambda: convert.reverse_slot(saved.file_bytes, env), lambda: convert.loaded_zone_metadata(saved.file_bytes, env)):
            try:
                fn(); assert False
            except convert.ConvertError as e:
                assert str(e) == container.DOWNGRADE_REFUSED
        retail_resave = convert.old_stream_to_new(oldsave.write_slot(plain), env, retained_file=saved.file_bytes, native=L.RETAIL)
        assert retail_resave.refused == 'retained file: ' + container.DOWNGRADE_REFUSED
        # (6) an unknown required bit refuses everywhere with the established message
        unknown = _set_required_features(legacy, 4)
        for native in (L.RETAIL, L.E10A2):
            try:
                convert.reverse_slot(unknown, env, native=native, registry=reg); assert False
            except (convert.ConvertError, container.ContainerError) as e:
                assert str(e) == 'required feature bits 0x4 not implemented (needs a newer version)'
        # (7) the registry must verify against the scripts the build was made from
        (Path(root) / 'zone_q' / 'trap.py').write_bytes(b'# edited\n')
        ok, reason = T.verify_registry(reg_path, root)
        assert not ok and 'regenerated registry' in reason


def test_e10a2_native_transfer_metadata_and_raised_ordinals():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d)
        root, reg_path, reg = registry_fixture(d)
        raw = oldsave.write_slot(typed_old_save(len(env.binds.item)))
        legacy = convert.convert_slot(raw, 'synthetic.save', env, now=0).file_bytes
        raised, _ = convert.reverse_slot(legacy, env, native=L.E10A2, registry=reg)
        e10a2 = oldsave.write_slot(raised, L.E10A2)
        captures = convert.native_zone_metadata(e10a2, env, native=L.E10A2)
        assert [c['zone'] for c in captures] == ['zone/x/y'] and [e['ordinal'] for e in captures[0]['entities']] == [1, 2, 3]
        retail_captures = convert.native_zone_metadata(oldsave.write_slot(convert.reverse_slot(legacy, env)[0]), env)
        assert captures[0]['entities'] == retail_captures[0]['entities']
        try:
            convert.native_zone_metadata(e10a2, env); assert False                      # a retail reader given the raised stream
        except convert.ConvertError as e:
            assert 'is not the slot size' in str(e)
        # validate_native_sections bounds ordinals by the layout: 300 is an ordinal only the raised layout accepts
        f = container.read_file(legacy)
        S = {t: s['data'] for t, s in f['sections'].items() if s['data'] is not None}
        S['ZONE']['records'][0]['states'][0]['ordinal'] = 300
        try:
            convert.validate_native_sections(S, env); assert False
        except convert.ConvertError as e:
            assert 'ordinal outside native range 1..256' in str(e)
        convert.validate_native_sections(S, env, native=L.E10A2)
