"""Limits wave 2, step 8, builder side: [Limits] SaveLayout=w2 (the opt-in `--save-layout w2` option) and the W2 data
limits. Synthetic inputs only. The DLL contract is limits-wave2.md "Step 8: DLL selection, admission and builder
contract": the four keys are written together ([Save] Format=lc, EntityCapacity=1, SaveLayout=w2, ItemEnhancements=4096),
every other combination is refused, a DLL without the key is refused, and the validator's rows follow the W2 descriptor."""
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import builder_stub as B
import harness
from test_builder_cli import build_argv, check_stream, run, setup
from xml1build import fix_ini as FI
from xml1build import talent_budget as TB
from xml1build import validate as V
from xml1build import w2_limits as WL
from xml1build import zones as Z

W2_KEY = 'SaveLayout'.encode('utf-16le')
W2_DLL = b'MZ ' + 'EntityCapacity'.encode('utf-16le') + b'\x00\x00' + 'SaveLayout\0'.encode('utf-16le') + b''.join(marker for marker, _name in FI.W2_LAYOUT_MARKERS)   # 082c: boot / save fixes


def dll_knowing(keys, *, save_layout=True):
    """bytes of a DLL that recognizes every key (and revision marker) of `keys`, SaveLayout only when asked"""
    data = b'MZ '
    for section, names in keys.items():
        for key in names:
            if key == 'SaveLayout' and not save_layout:
                continue
            data += (key + '\0').encode('utf-16le')
    # every install-line marker the release gate may ask of a current DLL (beta 8's 080e..080h lines, wave 3's rows):
    # this synthetic DLL stands for one that knows everything, so only SaveLayout / Xml1Economy decide the cases below
    data += b''.join(marker for marker, _name in FI.RELEASE_MARKERS.values())
    data += b''.join(marker for _key, marker, _name in FI.EXTRA_MARKERS)
    data += b''.join(marker for _stock, marker, _name in FI.VALUE_MARKERS.values())
    if save_layout:
        data += b''.join(marker for marker, _name in FI.W2_LAYOUT_MARKERS)          # 082c: W2's boot / save fixes
    data += b''.join(FI.MARKERS_082D)                                               # 082d: digest / moves fixes
    data += b''.join(FI.MARKERS_082E)                                               # 082e: moves round 3
    return data + b'NPR14 NSA4'


def raises(exc, fn, *needles):
    try:
        fn()
    except exc as e:
        for needle in needles:
            assert needle in str(e), (needle, str(e))
        return e
    raise AssertionError(f'{getattr(fn, "__name__", fn)} did not raise {exc.__name__}')


def lc_keys(**limits):
    """a key set as port_keys writes it, [Limits] overridden/extended by `limits` (a None value drops the key)"""
    keys = {'Limits': FI.limits_for('w2'), 'Save': {'Format': 'lc'}}
    for k, v in limits.items():
        if v is None:
            keys['Limits'].pop(k, None)
        else:
            keys['Limits'][k] = v
    return keys


def w2_build(root, *, postgame=True, option='w2'):
    """a synthetic build folder: a report.json recording the option, and (postgame) the port identity's script"""
    out = Path(root)
    (out / '_build').mkdir(parents=True, exist_ok=True)
    (out / '_build' / 'report.json').write_text(json.dumps({'build': {'save_layout': option, 'forced_teams': 'seat'}}))
    if postgame:
        (out / 'Scripts' / 'x1' / 'menus').mkdir(parents=True, exist_ok=True)
        (out / 'Scripts' / 'x1' / 'menus' / 'postgame.py').write_bytes(b'x')
    return out


# ------------------------------------------------------------------------------------------------ the keys
def test_limits_for_the_baseline_is_unchanged_and_w2_adds_the_pair():
    assert FI.limits_for() == FI.LIMITS and FI.limits_for('retail') == FI.LIMITS and FI.limits_for(None) == FI.LIMITS
    assert FI.limits_for() is not FI.LIMITS                       # a copy: callers may edit it
    w2 = FI.limits_for('w2')
    assert w2['SaveLayout'] == 'w2' and w2['EntityCapacity'] == '1'
    assert w2['ItemEnhancements'] == '4096'                       # B1: never the default 512 beside SaveLayout=w2
    assert {k: v for k, v in w2.items() if k not in ('SaveLayout', 'ItemEnhancements')} == \
        {k: v for k, v in FI.LIMITS.items() if k != 'ItemEnhancements'}
    assert FI.LIMITS['ItemEnhancements'] == '512' and 'SaveLayout' not in FI.LIMITS
    keys = list(w2)
    assert keys.index('SaveLayout') == keys.index('EntityCapacity') + 1
    raises(ValueError, lambda: FI.limits_for('e10a2'), 'unknown save layout')
    assert 'SaveLayout' in FI.PORT_OWNED['Limits']                 # dropped again when a rebuild stops asking for it


def test_contract_table_write_and_refuse_every_combination():
    """limits-wave2 section 3 "Supported combinations" and the step 8 prerequisites, from the builder's side"""
    ok = FI.check_save_layout_keys
    # [Save] Format absent / off: SaveLayout=w2 is refused whatever EntityCapacity says (B3), the DLL would ignore it
    for fmt in (None, 'off', '', '0', 'LC'):
        for ec in (None, '0', '1'):
            keys = lc_keys(EntityCapacity=ec)
            keys['Save'] = {} if fmt is None else {'Format': fmt}
            raises(ValueError, lambda: ok(keys), 'Format=lc')
    raises(ValueError, lambda: ok({'Limits': {'SaveLayout': 'w2', 'EntityCapacity': '1'}}), 'Format=lc')   # no [Save] at all
    # lc + EntityCapacity absent / 0 + w2: "SaveLayout=w2 needs EntityCapacity=1"
    for ec in (None, '0', '2', ''):
        raises(ValueError, lambda ec=ec: ok(lc_keys(EntityCapacity=ec)), 'EntityCapacity=1')
    # lc + 1 + w2 (ItemEnhancements 4096 or omitted): written
    ok(lc_keys())
    ok(lc_keys(ItemEnhancements=None))
    ok(lc_keys(ItemEnhancements='4096'))
    # the DLL refuses ItemEnhancements=anything else under W2, so the builder never writes it
    for value in ('512', '375', '1024', '4095', '8192', ''):
        raises(ValueError, lambda value=value: ok(lc_keys(ItemEnhancements=value)), 'ItemEnhancements=4096')
    # only the exact value w2; an empty SaveLayout= is never written
    for value in ('', 'W2', ' w2', 'w2 ', 'e10a2', 'retail', 'RETAIL', 'native', '1'):
        raises(ValueError, lambda value=value: ok(lc_keys(SaveLayout=value)), 'SaveLayout must be w2')
    # no SaveLayout key: the configured baseline, any combination passes (E10A2 / RETAIL / stock bytes)
    for fmt in (None, 'lc'):
        for ec in (None, '0', '1'):
            keys = {'Limits': dict(FI.LIMITS), 'Save': {} if fmt is None else {'Format': fmt}}
            if ec is None:
                del keys['Limits']['EntityCapacity']
            else:
                keys['Limits']['EntityCapacity'] = ec
            if not (fmt is None and ec == '1'):               # EntityCapacity without Format=lc is a separate refusal
                ok(keys)
    ok({})


def test_the_four_keys_are_written_together_and_a_rebuild_without_the_option_drops_them():
    with tempfile.TemporaryDirectory() as td:
        out = w2_build(Path(td) / 'w2')
        keys = FI.port_keys(out)
        assert keys['Save'] == {'Format': 'lc'}
        assert keys['Limits']['EntityCapacity'] == '1' and keys['Limits']['SaveLayout'] == 'w2'
        assert keys['Limits']['ItemEnhancements'] == '4096' and '' not in keys['Limits'].values()
        (out / 'dinput.dll').write_bytes(dll_knowing(keys, save_layout=False))
        raises(FI.FixTooOld, lambda: FI.write_port_keys(out, keys, old_fix_ok=True), 'SaveLayout')   # B2 on the real key set
        assert not (out / 'xml2-fix.ini').exists()
        (out / 'dinput.dll').write_bytes(dll_knowing(keys))
        FI.write_port_keys(out, keys)
        ini = FI.read_ini(out / 'xml2-fix.ini')
        assert ini['Save']['Format'] == 'lc'
        assert {k: ini['Limits'][k] for k in ('EntityCapacity', 'SaveLayout', 'ItemEnhancements')} == \
            {'EntityCapacity': '1', 'SaveLayout': 'w2', 'ItemEnhancements': '4096'}
        # the same folder rebuilt without the option: the record says retail, the keys go back (512, no SaveLayout)
        (out / '_build' / 'report.json').write_text(json.dumps({'build': {'save_layout': 'retail', 'forced_teams': 'seat'}}))
        plain = FI.port_keys(out)
        assert 'SaveLayout' not in plain['Limits'] and plain['Limits'] == FI.LIMITS
        # SaveLayout is dropped (with beta 8's and wave 3's other port-owned [Limits] keys this record does not ask for)
        dropped = FI.dropped_keys(plain)['Limits']
        assert 'SaveLayout' in dropped and not set(dropped) & set(plain['Limits'])
        FI.write_port_keys(out, plain)
        ini = FI.read_ini(out / 'xml2-fix.ini')
        assert 'SaveLayout' not in ini['Limits'] and ini['Limits']['ItemEnhancements'] == '512'


def test_the_default_build_writes_no_save_layout_key():
    with tempfile.TemporaryDirectory() as td:
        out = w2_build(Path(td) / 'a', option='retail')
        keys = FI.port_keys(out)
        assert keys['Limits'] == FI.LIMITS and 'SaveLayout' not in keys['Limits']
        bare = Path(td) / 'b'
        (bare / '_build').mkdir(parents=True)
        (bare / '_build' / 'report.json').write_text(json.dumps({'build': {'xp_curve': 'xml1'}}))   # a build from before the option
        assert FI.build_save_layout(bare) is None and FI.port_keys(bare)['Limits'] == FI.LIMITS
        assert FI.build_save_layout(Path(td) / 'missing') is None
        for spelling in ('W2', ' w2 '):
            out = w2_build(Path(td) / f's{len(spelling)}', option=spelling)
            assert FI.build_save_layout(out) == 'w2'
        assert FI.build_save_layout(w2_build(Path(td) / 'c', option='native')) is None


def test_w2_without_the_lc_save_identity_is_refused():
    """B3: a build with no port identity writes no [Save] Format=lc; SaveLayout=w2 on it would be ignored by the DLL"""
    with tempfile.TemporaryDirectory() as td:
        out = w2_build(td, postgame=False)
        raises(ValueError, lambda: FI.port_keys(out), 'Format=lc')


# ------------------------------------------------------------------------------------------------ the DLL probe
def test_a_dll_without_the_key_is_refused_and_the_cli_warning_path_does_not_write_it():
    """B2: probed as EntityCapacity is, as the UTF-16 key name; refused even on the old_fix_ok path"""
    keys = lc_keys()
    older = dll_knowing(keys, save_layout=False)                              # pre-step8: knows every other key
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        FI.check_save_layout_dll(dll, keys)                                   # no DLL: a source-only build
        dll.write_bytes(older)
        e = raises(FI.FixTooOld, lambda: FI.check_save_layout_dll(dll, keys), 'SaveLayout')
        assert e.missing == ['[Limits] SaveLayout'] and isinstance(e, ValueError)
        # (082c) a pre-W2 DLL also lacks W2's boot / save fix markers
        assert FI.old_fix_keys(dll, keys) == ['[Limits] SaveLayout'] + [name for _marker, name in FI.W2_LAYOUT_MARKERS]
        # a message that merely starts with the key (not the key itself) is not support
        dll.write_bytes(older + 'SaveLayout=w2 needs'.encode('utf-16le'))
        raises(FI.FixTooOld, lambda: FI.check_save_layout_dll(dll, keys))
        dll.write_bytes(older + 'SaveLayoutX\0'.encode('utf-16le'))
        raises(FI.FixTooOld, lambda: FI.check_save_layout_dll(dll, keys))
        dll.write_bytes(older)
        raises(FI.FixTooOld, lambda: FI.write_port_keys(td, lc_keys()), 'SaveLayout')
        raises(FI.FixTooOld, lambda: FI.write_port_keys(td, lc_keys(), old_fix_ok=True), 'not written')
        assert not (Path(td) / 'xml2-fix.ini').exists()
        # an older fix that lacks other keys too: the others may be a warning, SaveLayout never is
        dll.write_bytes(b'MZ')
        e = raises(FI.FixTooOld, lambda: FI.write_port_keys(td, lc_keys(), old_fix_ok=True), 'not written')
        assert e.missing == ['[Limits] SaveLayout'] and not (Path(td) / 'xml2-fix.ini').exists()
        dll.write_bytes(dll_knowing(keys))
        FI.check_save_layout_dll(dll, keys)
        assert FI.old_fix_keys(dll, keys) == []
        FI.write_port_keys(td, lc_keys())
        assert FI.read_ini(Path(td) / 'xml2-fix.ini')['Limits']['SaveLayout'] == 'w2'
        # without SaveLayout the probe asks for nothing, whatever the DLL
        dll.write_bytes(b'MZ')
        FI.check_save_layout_dll(dll, {'Limits': dict(FI.LIMITS), 'Save': {'Format': 'lc'}})
        # the key set is checked before the DLL: an unsupported combination is a ValueError, not FixTooOld
        e = raises(ValueError, lambda: FI.check_save_layout_dll(dll, lc_keys(ItemEnhancements='512')), 'ItemEnhancements')
        assert not isinstance(e, FI.FixTooOld)
        e = raises(ValueError, lambda: FI.old_fix_keys(dll, lc_keys(EntityCapacity=None)), 'EntityCapacity')
        assert not isinstance(e, FI.FixTooOld)


def test_the_cli_refuses_a_w2_build_over_an_older_fix_instead_of_warning():
    w2 = lc_keys()
    w2['Game'] = {'NewGameTeam': 'wolverine'}
    saved = B.StubPipeline.port_keys
    B.StubPipeline.port_keys = lambda self, out: {s: dict(v) for s, v in w2.items()}
    try:
        with tempfile.TemporaryDirectory() as td:
            xml2, iso, out, cache = setup(td)
            out.mkdir()
            old = b'MZ an older fix ' + 'EntityCapacity'.encode('utf-16le')
            (out / 'dinput.dll').write_bytes(old)
            code, evs, err = run(build_argv(xml2, iso, out, cache, '--save-layout', 'w2'))
            errors = [e for e in evs if e['ev'] == 'error']
            assert code != 0 and errors and errors[-1]['code'] == 'E_XML2FIX_OLD', (code, errors, err[-400:])
            assert errors[-1]['detail']['missing'] == ['[Limits] SaveLayout']
            assert not (out / 'xml2-fix.ini').exists()
            (out / 'dinput.dll').write_bytes(W2_DLL)                      # the fix that knows it: the four keys land
            code, evs, err = run(build_argv(xml2, iso, out, cache, '--save-layout', 'w2'))
            last = check_stream(evs)
            assert code == 0 and last['result']['ok'], (last.get('error'), err[-400:])
            ini = FI.read_ini(out / 'xml2-fix.ini')
            assert (ini['Save']['Format'], ini['Limits']['EntityCapacity'], ini['Limits']['SaveLayout'],
                    ini['Limits']['ItemEnhancements']) == ('lc', '1', 'w2', '4096')
    finally:
        B.StubPipeline.port_keys = saved


# ------------------------------------------------------------------------------------------------ the option
def test_the_option_defaults_w2_and_reaches_every_parser_and_record():
    import build_xml1
    from xml1build import common as C
    from xml1builder.cli import make_parser
    assert build_xml1.parse_args(['--out', 'x']).save_layout == 'w2'                # default since 0.5.0-beta.1
    assert build_xml1.parse_args(['--out', 'x', '--save-layout', 'retail']).save_layout == 'retail'
    raises(SystemExit, lambda: build_xml1.parse_args(['--out', 'x', '--save-layout', 'e10a2']))
    assert make_parser().parse_args(['build']).save_layout == 'w2'
    assert make_parser().parse_args(['build', '--save-layout', 'retail']).save_layout == 'retail'
    assert build_xml1.CONTENT_OPTS['save_layout'] == ('zones', 'retail')            # a 0.4.1 record has no key
    # standalone checks over a finished build see the option it was made with
    with tempfile.TemporaryDirectory() as td:
        out = w2_build(td)
        assert C.args_for_out(out).save_layout == 'w2'
        assert WL.selected(C.args_for_out(out)) and WL.limits(C.args_for_out(out)).name == 'w2'
        out2 = w2_build(Path(td) / 'old', option='retail')
        assert C.args_for_out(out2).save_layout == 'retail'
        # changing it re-runs the module whose output depends on it (the talent precache budget)
        # a build from before the option (no save_layout key) and without the economy (no loot keys: off / noop)
        carried = {opt: default for opt, (_mods, default) in build_xml1.CONTENT_OPTS.items()
                   if opt not in ('save_layout', 'loot', 'loot_def_damage_scale')}
        plain = Path(td) / 'carried'
        (plain / '_build').mkdir(parents=True)
        (plain / '_build' / 'report.json').write_text(json.dumps({'build': carried}))
        assert build_xml1.plan_content_opts(plain, build_xml1.parse_args(['--out', 'x', '--save-layout', 'retail']), []) == []
        assert build_xml1.plan_content_opts(plain, build_xml1.parse_args(['--out', 'x', '--loot', 'off']), []) == ['zones']
        # the 0.5.0 default build (w2 + the economy) over a 0.4.1 build re-runs zones and the front end
        assert build_xml1.plan_content_opts(plain, build_xml1.parse_args(['--out', 'x']), []) == ['zones', 'frontend']
        (plain / '_build' / 'report.json').write_text(json.dumps({'build': {**carried, 'save_layout': 'w2'}}))
        assert build_xml1.plan_content_opts(plain, build_xml1.parse_args(['--out', 'x', '--save-layout', 'retail']), []) == ['zones']
        assert build_xml1.plan_content_opts(plain, build_xml1.parse_args(['--out', 'x', '--loot', 'off']), []) == []


def test_the_harness_ini_follows_the_build_record():
    base = dict(limits=True, port_identity=True, postgame=FI.POSTGAME_SCRIPT)
    plain = FI.parse_ini(harness.ini_text('windowed', 1, 1, False, **base))
    assert plain['Limits'] == FI.LIMITS and plain['Save'] == {'Format': 'lc'}
    w2 = FI.parse_ini(harness.ini_text('windowed', 1, 1, False, save_layout='w2', **base))
    assert w2['Limits'] == FI.limits_for('w2') and w2['Save'] == {'Format': 'lc'}
    assert w2['Limits']['ItemEnhancements'] == '4096'
    raises(ValueError, lambda: harness.ini_text('windowed', 1, 1, False, save_layout='w2', limits=True), 'port identity')
    raises(ValueError, lambda: harness.ini_text('windowed', 1, 1, False, save_layout='w2', port_identity=True), 'port identity')


# ------------------------------------------------------------------------------------------------ the validator
def test_limits_follow_the_descriptor_and_retail_keeps_the_released_numbers():
    from lcsave import layout as L
    r, w = WL.RETAIL_LIMITS, WL.W2_LIMITS
    assert (r.mission_files, r.objectives, r.objectives_per_act, r.talent_pool, r.talent_files, r.shared_talents) == \
        (25, 299, 75, 100, 9, 99)
    assert V.MISSION_FILES_MAX == 25 and V.OBJECTIVES_MAX == 299 and V.OBJECTIVES_PER_ACT == 75 and V.TALENT_CAP == 99
    assert (w.mission_files, w.objectives, w.objectives_per_act) == (64, 1024, 127)
    assert (w.talent_pool, w.talent_files, w.shared_talents, w.talent_positions) == (256, 9, 199, 200)
    assert (w.definitions, w.enhancement_records, w.attached_enhancements, w.instances, w.world_slots) == \
        (1024, 4096, 4096, 1024, 1024)
    assert (w.placements, w.zone_names, w.zone_arena, w.resident_zones) == (1024, 8191, 0x1ffff, 8)
    assert w.talent_pool == L.W2.talent_pool and w.mission_files == L.W2.objective_files
    for none in ('definitions', 'enhancement_records', 'placements', 'zone_names', 'talent_positions'):
        assert getattr(r, none) is None                 # retail checks only the numbers it always checked
    # the selection: a context, its args, a validator, or nothing
    assert WL.limits(SimpleNamespace(args=SimpleNamespace(save_layout='w2'))).name == 'w2'
    assert WL.limits(SimpleNamespace(save_layout='w2')).name == 'w2'
    assert WL.limits(SimpleNamespace(ctx=SimpleNamespace(args=SimpleNamespace(save_layout='w2')))).name == 'w2'
    assert WL.limits(SimpleNamespace(args=SimpleNamespace(save_layout='retail'))).name == 'retail'
    assert WL.limits(SimpleNamespace(args=SimpleNamespace())).name == 'retail'
    assert WL.limits(SimpleNamespace(ctx=SimpleNamespace(args=SimpleNamespace()))).name == 'retail'


def _mission_validator(layout, shape):
    """a stand-in for Validator._missions: shape = {mission file: (act, objective count)}"""
    files = ET.Element('MISSIONS')
    trees = {'data/missions/missions.xmlb': files}
    for name, (act, n) in shape.items():
        ET.SubElement(files, 'MISSION', name=name)
        mission = ET.Element('MISSION', name=name, act=str(act))
        for i in range(n):
            ET.SubElement(mission, 'OBJECTIVE', name=f'{name}_{i}')
        trees[f'data/missions/{name}.engb'] = mission
    return SimpleNamespace(ctx=SimpleNamespace(args=SimpleNamespace(save_layout=layout)), tree=trees.get,
                           _obj_refs={}, _act_refs={})


def _mission_errors(layout, shape):
    ck = V.Check('V', 'missions')
    V.Validator._missions(_mission_validator(layout, shape), ck)
    return ck.errors


def test_the_mission_rows_take_their_caps_from_the_layout():
    files = {f'm{i}': (1 + i % 9, 1) for i in range(40)}                 # 40 files: over 25, under 64
    assert any('> 25' in e for e in _mission_errors('retail', files))
    assert _mission_errors('w2', files) == []
    assert not any('mission files' in e for e in _mission_errors('w2', {f'm{i}': (1, 1) for i in range(64)}))
    assert any('65 mission files > 64' in e for e in _mission_errors('w2', {f'm{i}': (1, 1) for i in range(65)}))
    assert any('> 75' in e for e in _mission_errors('retail', {'a': (1, 80)}))        # 80 in one act
    assert _mission_errors('w2', {'a': (1, 80)}) == []
    assert _mission_errors('w2', {'a': (1, 127)}) == []
    assert any('128 objectives > 127' in e for e in _mission_errors('w2', {'a': (1, 128)}))
    many = {f'm{i}': (1 + i % 9, 29) for i in range(36)}                 # 36 x 29 = 1044 over 9 acts, 116 per act
    assert any('1044 objectives' in e and '> 1024' in e for e in _mission_errors('w2', many))
    assert any('> 299' in e for e in _mission_errors('retail', {f'm{i}': (1 + i, 40) for i in range(8)}))
    assert _mission_errors('w2', {f'm{i}': (1 + i, 40) for i in range(8)}) == []


def test_the_talent_registry_rows_use_the_layout_pool_and_positions():
    total = {'talents': 200, 'files': 9}
    assert TB.problems(total) and TB.problems(total, WL.RETAIL_LIMITS)           # 200 > 100
    assert TB.problems(total, WL.W2_LIMITS) == []                                # 200 <= 256
    assert TB.problems({'talents': 256, 'files': 9}, WL.W2_LIMITS) == []
    assert any('> 256' in p for p in TB.problems({'talents': 257, 'files': 9}, WL.W2_LIMITS))
    assert any('> 9' in p for p in TB.problems({'talents': 10, 'files': 10}, WL.W2_LIMITS))   # file slots stay 9
    counts = {'base': frozenset({'a'}), 'prop': frozenset({f'p{i}' for i in range(100)}),
              'hero': frozenset({f'h{i}' for i in range(100)})}
    heroes = {'hero': {'hero'}}
    # the reviewed-prop pruning happens only while the layout's pool overflows: 201 names overflow the retail pool of
    # 100 (the prop goes) and fit the W2 pool of 256 (it stays)
    kept, dropped = TB.prune_props({'base', 'prop'}, {'prop': 'scene prop'}, heroes, counts, WL.RETAIL_LIMITS)
    assert dropped == {'prop': 'scene prop'}
    kept, dropped = TB.prune_props({'base', 'prop'}, {'prop': 'scene prop'}, heroes, counts, WL.W2_LIMITS)
    assert dropped == {} and kept == {'base', 'prop'}


def test_hero_and_shared_talent_positions_stay_below_the_multiplier():
    w = WL.W2_LIMITS
    assert WL.talent_position_problems(w, {'data/talents/a': 200}, 199) == []
    assert any('201' in p and 'data/talents/a' in p for p in WL.talent_position_problems(w, {'data/talents/a': 201}, 0))
    assert any('200' in p and 'shared' in p for p in WL.talent_position_problems(w, {}, 200))
    assert WL.talent_position_problems(WL.RETAIL_LIMITS, {'data/talents/a': 5000}, 5000) == []   # not this layout's row
    # and the id the multiplier makes still fits the saved u16 for the largest stats index (296 entries)
    assert 297 * w.talent_positions + (w.talent_positions - 1) <= 0xffff


def _tree(tag, *children, **attrs):
    el = ET.Element(tag, **attrs)
    el.extend(children)
    return el


def _zone(insts, names=None):
    root = ET.Element('map')
    group = ET.SubElement(root, 'entinst', type='box')
    for i in range(insts):
        ET.SubElement(group, 'inst', name=f'i{i}' if names is None else names[i])
    return root


class _Idx:
    def __init__(self, trees):
        self.trees = trees

    def under(self, prefix):
        return [rel for rel in self.trees if rel.startswith(prefix + '/')]


def _w2_validator(layout='w2', zones=None, items=None, shared=None):
    trees = {f'maps/{name}.xmlb': tree for name, tree in (zones or {}).items()}
    lookup = dict(trees)
    if items is not None:
        lookup['data/items.xmlb'] = items
    for rel, tree in (shared or {}).items():
        lookup[rel] = tree
    return SimpleNamespace(ctx=SimpleNamespace(args=SimpleNamespace(save_layout=layout)), idx=_Idx(trees), tree=lookup.get)


def _items(definitions, enhancements_per_item):
    root = ET.Element('items')
    for i in range(definitions):
        item = ET.SubElement(root, 'item', name=f'item{i}')
        for _ in range(enhancements_per_item):
            ET.SubElement(item, 'enhancement', name='e')
    return root


def _v67(validator):
    ck = V.Check('V67', 'W2 data limits')
    WL.check(validator, ck)
    return ck


def test_v67_is_silent_without_w2_whatever_the_data_holds():
    ck = _v67(_w2_validator('retail', zones={'big': _zone(5000)}, items=_items(5000, 5)))
    assert ck.errors == [] and ck.counts == {'layout': 'retail'}
    ck = _v67(_w2_validator(None, zones={'big': _zone(5000)}))
    assert ck.errors == []


def test_v67_item_definitions_and_enhancement_records():
    assert _v67(_w2_validator(items=_items(1024, 4))).errors == []                         # 1024 defs, 4096 records
    errors = _v67(_w2_validator(items=_items(1025, 1))).errors
    assert len(errors) == 1 and '1025 item definitions > 1024' in errors[0]
    assert _v67(_w2_validator(items=_items(1000, 4))).errors == []                         # 4000 records: fine
    assert _v67(_w2_validator(items=ET.Element('items'))).errors == []                    # an empty table: nothing over
    over = _items(1000, 4)
    ET.SubElement(over, 'prefix_enh').extend([ET.Element('enhancement') for _ in range(97)])     # 4097 records
    errors = _v67(_w2_validator(items=over)).errors
    assert any('4097 enhancement records > 4096' in e for e in errors) and any('attached' in e for e in errors)
    ck = _v67(_w2_validator(items=None))
    assert any('Data/items missing' in e for e in ck.errors)
    # the same name defined twice is one definition
    twice = _items(3, 0)
    ET.SubElement(twice, 'item', name='ITEM0')
    assert WL.item_counts(twice) == (3, 0)


def test_v67_zone_placements_are_counted_recursively_and_capped_at_1024():
    nested = ET.Element('map')
    group = ET.SubElement(nested, 'entinst', type='box')
    parent = ET.SubElement(group, 'inst', name='p')
    ET.SubElement(parent, 'inst', name='child')                    # a recursive <inst> counts
    assert WL.placements(nested) == 2
    assert _v67(_w2_validator(zones={'act1/ok': _zone(1024)}, items=_items(1, 0))).errors == []
    ck = _v67(_w2_validator(zones={'act1/ok': _zone(1024), 'act1/big': _zone(1025)}, items=_items(1, 0)))
    placement = [e for e in ck.errors if 'placements' in e and 'world' not in e]
    assert placement == ['act1/big: 1025 placements > 1024 (W2 limit)'], ck.errors
    assert ck.counts['placements_max'] == 1025 and ck.counts['zones_checked'] == 2


def test_v67_world_items_resident_zones_and_zone_string_names():
    pickups = _tree('entities', _tree('entity', name='gold', classname='inventoryent'),
                    _tree('entity', name='key', classname='physent', inventoryitem='keycard'),
                    _tree('entity', name='crate', classname='physent'))
    def zone(world, crates):
        root = ET.Element('map')
        for typ, n in (('gold', world // 2), ('key', world - world // 2), ('crate', crates)):
            group = ET.SubElement(root, 'entinst', type=typ)
            for i in range(n):
                ET.SubElement(group, 'inst', name=f'{typ}{i}')
        return root
    assert WL.world_item_placements(zone(10, 50), ()) == 0                                # not defined in the zone: unknown
    assert WL.world_item_placements(zone(10, 50), {'gold', 'KEY'}) == 10
    local = zone(4, 3)
    local.insert(0, pickups)
    assert WL.world_item_placements(local) == 4
    # 8 heaviest zones x 128 world items = 1024: fits; one more does not; a ninth zone never counts
    shared = {'data/item_ents.xmlb': pickups}
    zones = {f'z{i}': zone(128, 5) for i in range(8)}
    assert _v67(_w2_validator(zones=zones, items=_items(1, 0), shared=shared)).errors == []
    zones['z0'] = zone(129, 5)
    errors = _v67(_w2_validator(zones=zones, items=_items(1, 0), shared=shared)).errors
    assert len(errors) == 2 and all('1025 world-item placements' in e for e in errors), errors
    zones = {f'z{i}': zone(128, 5) for i in range(12)}                                   # 12 zones, only 8 resident
    assert _v67(_w2_validator(zones=zones, items=_items(1, 0), shared=shared)).errors == []
    # the zone-string table: 8191 usable names, 0x1ffff bytes, over the 8 zones with the most distinct names
    def named(prefix, n):
        return _zone(n, [f'{prefix}{i}' for i in range(n)])
    # the placement cap (1024) bounds one zone, so 8 zones x 1023 names ~ 8184 < 8191: just fits...
    fits = {f'f{i}': named(f'f{i}_', 1023) for i in range(8)}
    ck = _v67(_w2_validator(zones=fits, items=_items(1, 0)))
    assert ck.errors == [] and ck.counts['zone_string_names'] == 8184
    # ... and one more zone with distinct names beyond the resident 8 is not counted
    fits['f8'] = named('g_', 1000)
    assert _v67(_w2_validator(zones=fits, items=_items(1, 0))).counts['zone_string_names'] == 8184
    # the descriptor arithmetic itself: 8191 names fit, the 8192nd does not; the arena likewise
    names = {'z': {f'n{i}' for i in range(8192)}}
    assert WL.data_problems(WL.W2_LIMITS, names=WL.zone_string_demand(names, 8)[:2]) and \
        '8192 distinct zone-string names > 8191' in WL.data_problems(WL.W2_LIMITS, names=WL.zone_string_demand(names, 8)[:2])[0]
    assert WL.data_problems(WL.W2_LIMITS, names=(8191, 10)) == []
    assert WL.data_problems(WL.W2_LIMITS, names=(1, 0x1ffff)) == []
    assert 'arena bytes' in WL.data_problems(WL.W2_LIMITS, names=(1, 0x20000))[0]
    assert WL.data_problems(WL.RETAIL_LIMITS, definitions=10**6, enhancements=10**6, zone_placements={'z': 10**6},
                            world_items={'z': 10**6}, names=(10**6, 10**7)) == []


def test_v67_is_registered_in_the_validator_run():
    import inspect
    assert "('V67', 'W2 data limits'" in inspect.getsource(V.Validator.run_all)


# ------------------------------------------------------------------------------------------------ the item pool
def test_the_item_enhancement_pool_follows_the_ini_the_build_asks_for():
    assert Z.item_enhancement_pool(SimpleNamespace(args=SimpleNamespace(save_layout='retail'))) == 512 == Z.ITEM_ENHANCEMENT_POOL
    assert Z.item_enhancement_pool(SimpleNamespace(args=SimpleNamespace())) == 512
    assert Z.item_enhancement_pool(SimpleNamespace(args=SimpleNamespace(save_layout='w2'))) == 4096
    root = _items(40, 100)                                                       # 4000 enhancements
    assert Z.enhancement_pool_cut(root, 4096) == [] and len(Z.enhancement_pool_cut(root)) > 0


def test_a_w2_build_refuses_the_w2_dlls_that_crash_at_boot_or_on_save():
    """082c: 082a / 082b's W2 DLLs know SaveLayout but crash (boot: shared pool helpers widened in place; first save:
    the restore map overran the save statics). The fixes' own guard descriptions are required for SaveLayout=w2."""
    keys = lc_keys()
    current = dll_knowing(keys)
    boot_only = current.replace(FI.W2_SAVE_MARKER, b'')                      # 651011f without 5420671 (a81e8f94)
    neither = boot_only.replace(FI.W2_BOOT_MARKER, b'')                     # 082a / 082b (053581ca / 699bbc82)
    assert FI.W2_BOOT_MARKER in boot_only and FI.W2_SAVE_MARKER not in boot_only and FI.W2_BOOT_MARKER not in neither
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        dll.write_bytes(current)
        assert FI.old_fix_keys(dll, keys) == []
        dll.write_bytes(boot_only)
        assert FI.old_fix_keys(dll, keys) == [FI.W2_LAYOUT_MARKERS[1][1]]
        dll.write_bytes(neither)
        assert FI.old_fix_keys(dll, keys) == [name for _marker, name in FI.W2_LAYOUT_MARKERS]
        # without the option nothing more is asked of the DLL (a retail-layout build keeps the published DLLs)
        retail = {sec: {k: v for k, v in names.items() if k != 'SaveLayout'} for sec, names in keys.items()}
        assert FI.old_fix_keys(dll, retail) == []
