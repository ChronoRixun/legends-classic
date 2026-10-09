"""Legacy streamed placements promoted only when their current identity is unique."""
import copy
import tempfile
from test_lcsave_durable import _env, _converted, _secs
from lcsave import container, convert, layout as L


def fixture(env, kind=3):
    _, saved = _converted(env)
    f = container.read_file(saved)
    r = f['sections']['ZONE']['data']['records'][0]
    target = next(s for s in r['states'] if s['list'] == 1)
    ordinal, placement = target['ordinal'], target['placement_index']
    target.update(list=kind, ordinal=0, placement_index=0, flags_b=3)
    return f, r, target, ordinal, placement


def packed(f):
    return container.write_file(L.KIND_CAMPAIGN, _secs(f), f['header'])


def test_legacy_streamed_placement_restores_alive_and_metadata():
    for kind in (2, 3):
        with tempfile.TemporaryDirectory() as d:
            env = _env(d)
            f, r, target, ordinal, placement = fixture(env, kind)
            saved = packed(f)
            native, notes = convert.reverse_slot(saved, env)
            z = native['zones'][0]
            idx = z['ordinal_map'][ordinal - 1]
            assert idx and z['states'][idx]['flags_b'] == 11
            assert idx not in z['smart'][:z['smart_count']]
            assert idx not in z['dynamic'][:z['dynamic_count']]
            assert z['states'][idx]['payload'] == target['payload']
            assert any('legacy unnumbered state restored' in n for n in notes)
            metadata = convert.loaded_zone_metadata(saved, env)[0]
            assert any(e['ordinal'] == ordinal and e['placement_index'] == placement for e in metadata['entities'])
            assert saved == packed(f), 'load must not rewrite the LC file'


def test_observed_capture_does_not_promote_streamed_state():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d)
        f, r, _, ordinal, _ = fixture(env)
        r['capture_flags'] = 0
        f['sections']['META']['data']['origin'] = 0
        native, _ = convert.reverse_slot(packed(f), env)
        assert native['zones'][0]['ordinal_map'][ordinal - 1] == 0


def test_explicit_tombstone_wins_over_streamed_duplicate():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d)
        f, r, target, ordinal, placement = fixture(env)
        tombstone = copy.deepcopy(target)
        tombstone.update(list=1, ordinal=ordinal, placement_index=placement, flags_b=0)
        r['states'].append(tombstone)
        native, _ = convert.reverse_slot(packed(f), env)
        z = native['zones'][0]
        assert z['states'][z['ordinal_map'][ordinal - 1]]['flags_b'] == 0


def test_duplicate_streamed_names_do_not_guess_identity():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d)
        f, r, target, ordinal, _ = fixture(env)
        r['states'].append(copy.deepcopy(target))
        native, _ = convert.reverse_slot(packed(f), env)
        assert native['zones'][0]['ordinal_map'][ordinal - 1] == 0


def test_earlier_import_without_capture_status_still_promotes():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d)
        f, r, _, ordinal, _ = fixture(env)
        r['capture_flags'] = 0
        assert f['sections']['META']['data']['origin'] == 1
        native, _ = convert.reverse_slot(packed(f), env)
        assert native['zones'][0]['ordinal_map'][ordinal - 1]


def test_ambiguous_current_placements_do_not_promote():
    with tempfile.TemporaryDirectory() as d:
        env = _env(d)
        _, r, _, _, _ = fixture(env)
        numbered = env.binds.zone_numbering('zone/x/y')['numbered']
        assert not convert._legacy_pinned_states(r, [numbered[0], numbered[0]], set())


def test_promoted_placement_survives_resave_as_numbered():
    from lcsave import oldsave
    with tempfile.TemporaryDirectory() as d:
        env = _env(d)
        f, _, _, ordinal, _ = fixture(env)
        saved = packed(f)
        native, _ = convert.reverse_slot(saved, env)
        result = convert.old_stream_to_new(oldsave.write_slot(native), env, retained_file=saved,
                    zone_captures=convert.loaded_zone_metadata(saved, env), require_capture_metadata=True, now=0)
        assert result.refused is None, result.refused
        record = container.read_file(result.file_bytes)['sections']['ZONE']['data']['records'][0]
        assert any(s['list'] == 1 and s['ordinal'] == ordinal and s['flags_b'] & 8 for s in record['states'])
        back, _ = convert.reverse_slot(result.file_bytes, env)
        assert back['zones'][0]['ordinal_map'][ordinal - 1]
