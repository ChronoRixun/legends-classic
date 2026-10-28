"""Limits wave 3 builder side (--limits-wave3): the [Limits] keys and their DLL gates, the OFF identity, and every counting
rule of the V-MOVES / V-EVENTS / V-EFFECT-FILES / V-PRIMITIVES / V-VECTORS / V-CURVES / V-SCRIPTS checks, on invented
styles, effects, packages and scripts built in code (no game content)."""
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import build_xml1
from xml1build import common as C
from xml1build import fix_ini as FI
from xml1build import limits_wave3 as L3
from xml1build import style_budget as SB
from xml1build import validate_script as VS
from xml1build.validate import Check


def X(tag, attrs=None, *children):
    el = ET.Element(tag, {k: str(v) for k, v in (attrs or {}).items()})
    for c in children:
        el.append(c)
    return el


# --------------------------------------------------------------------------------------------- keys, gates, OFF
WAVE3 = ('FightStyles', 'StyleEvents', 'FightMoves', 'EffectTemplates', 'PrimitiveDefs', 'EffectVectors',
         'PrimitivesPerEffect', 'AttachedPowerups', 'VFNodes')
LATE = ('ScriptPools', 'ParticleScratch')
BEFORE = {'ActorSlots': '127', 'ResourceNames': '2048', 'ItemEnhancements': '512', 'FightStyles': '32',
          'EffectCurves': '3600', 'MoveTriggers': '64', 'EntityCapacity': '1', 'ScriptFunctions': '1024',
          'IGBCache': '1024'}


def gate_keys(record):
    """port_keys of a build with the record, as the DLL gate sees them (the LC save format EntityCapacity needs)"""
    keys = port_keys_with(record)[0]
    keys['Save'] = {'Format': 'lc'}
    return keys


def port_keys_with(record):
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        (out / '_build').mkdir()
        (out / '_build/report.json').write_text(json.dumps({'build': record}), encoding='utf-8')
        return FI.port_keys(out), FI.dropped_keys(FI.port_keys(out))


def test_the_option_defaults_all_and_is_recorded_only_when_on():
    assert build_xml1.parse_args(['--out', '.']).limits_wave3 == 'all'          # default since 0.5.0-beta.1
    assert build_xml1.parse_args(['--out', '.', '--limits-wave3', 'off']).limits_wave3 == 'off'
    assert build_xml1.parse_args(['--out', '.', '--limits-wave3', 'on']).limits_wave3 == 'on'
    assert build_xml1.parse_args(['--out', '.', '--limits-wave3', 'all']).limits_wave3 == 'all'
    # not a content option: the stamp's profile (and so every existing build's state) stays what it was
    assert 'limits_wave3' not in build_xml1.CONTENT_OPTS
    assert dict(FI.LIMITS) == BEFORE                                  # the always-on section is untouched


def test_off_writes_exactly_todays_limits_and_an_off_rebuild_drops_the_wave3_keys():
    for record in ({}, {'limits_wave3': 'off'}, {'anim_enums': 'xml1'}):
        keys, dropped = port_keys_with(record)
        assert not (set(keys['Limits']) & (set(WAVE3) | set(LATE)) - {'FightStyles'})
        assert keys['Limits']['FightStyles'] == '32'                 # the value before the option existed
        assert {k: v for k, v in keys['Limits'].items() if k in BEFORE} == BEFORE
        assert set(dropped['Limits']) >= (set(WAVE3) | set(LATE)) - {'FightStyles'}
        assert 'FightStyles' not in dropped['Limits']
        text = FI.merge_text('[Limits]\nStyleEvents=4096\nFightStyles=64\nScriptPools=x1\nKeep=1\n', keys, dropped)
        assert 'StyleEvents' not in text and 'ScriptPools' not in text and 'FightStyles=32' in text and 'Keep=1' in text


def test_on_writes_the_nine_rows_at_the_design_values_and_all_adds_the_late_ones():
    on, _ = port_keys_with({'limits_wave3': 'on'})
    assert {k: on['Limits'][k] for k in WAVE3} == {'FightStyles': '64', 'StyleEvents': '4096', 'FightMoves': '1024',
                                                   'EffectTemplates': '512', 'PrimitiveDefs': '2048',
                                                   'EffectVectors': '4096', 'PrimitivesPerEffect': '32',
                                                   'AttachedPowerups': '256', 'VFNodes': '256'}
    assert not set(on['Limits']) & set(LATE)
    assert on['Limits']['EffectCurves'] == '3600' and on['Limits']['MoveTriggers'] == '64'     # the curves stay
    alls, dropped = port_keys_with({'limits_wave3': 'all'})
    assert alls['Limits']['ScriptPools'] == 'x1' and alls['Limits']['ParticleScratch'] == '40'
    assert not set(dropped['Limits']) & (set(WAVE3) | set(LATE))
    for key in WAVE3 + LATE:
        assert key in FI.PORT_OWNED['Limits']
    for key in WAVE3 + LATE:
        if key != 'FightStyles':
            assert key in FI.RELEASE_18_KEYS['Limits']
    assert FI.limits_in_use('on')['FightStyles'] == '64' and FI.limits_in_use('off') == FI.LIMITS
    try:
        FI.wave3_limits('maybe')
        raise AssertionError('an unknown level was accepted')
    except ValueError:
        pass


def test_rule_ids_and_markers_follow_the_rule_list():
    assert FI.WAVE3_RULES == {'FightStyles': 35, 'StyleEvents': 53, 'FightMoves': 54, 'EffectTemplates': 55,
                              'PrimitiveDefs': 56, 'EffectVectors': 57, 'PrimitivesPerEffect': 58, 'ScriptPools': 59,
                              'ParticleScratch': 60, 'AttachedPowerups': 61, 'VFNodes': 62}
    # The markers are the DLL's real install-line format strings (XML2 Fix 1.9.0, w3/integrated), no longer the
    # "<Key>: rule N" placeholders: one line per native owner (the style manager, the effect pools and the power pools
    # each own two rows).
    assert FI.WAVE3_MARKERS_ARE_PLACEHOLDERS is False
    assert set(FI.WAVE3_MARKERS) == set(FI.WAVE3_RULES)
    m = FI.WAVE3_MARKERS
    assert m['FightStyles'] == m['StyleEvents'] and m['PrimitiveDefs'] == m['EffectVectors']
    assert m['AttachedPowerups'] == m['VFNodes'] == b'limits: %s 256 (allocation 0x%X): %s; %s'
    owners = {m['FightStyles'], m['FightMoves'], m['EffectTemplates'], m['PrimitiveDefs'], m['PrimitivesPerEffect'],
              m['ScriptPools'], m['ParticleScratch'], m['AttachedPowerups']}
    assert len(owners) == 8 and all(isinstance(x, bytes) and len(x) >= 20 for x in owners)
    assert b'rule 59' in m['ScriptPools'] and b'rule 60' in m['ParticleScratch'] and b'FightMoves' in m['FightMoves']
    dll = os.environ.get('LC_W3_DLL')  # optional: the w3/integrated DLL carries every marker
    if dll:
        data = Path(dll).read_bytes()
        assert all(x in data for x in owners)


def test_dll_gate_refuses_a_dll_without_each_rules_marker_by_name():
    for key in (set(WAVE3) | set(LATE)) - {'FightStyles'}:
        keys = {'Limits': {key: FI.wave3_limits('all')[key]}}
        if key == 'PrimitivesPerEffect':
            keys['Limits']['EffectTemplates'] = '512'
        if key in LATE:
            keys['Limits'] = {k: v for k, v in FI.wave3_limits('all').items() if k != 'FightStyles'}
        rule = FI.WAVE3_RULES[key]
        with tempfile.TemporaryDirectory() as td:
            dll = Path(td) / 'dinput.dll'
            assert FI.old_fix_keys(dll, keys) == []                                  # no DLL: source-only build
            dll.write_bytes(b'MZ')
            assert f'[Limits] {key}' in FI.old_fix_keys(dll, keys)
            dll.write_bytes(b'MZ' + key.encode('utf-16le'))                         # the key's name alone is not enough
            assert FI.old_fix_keys(dll, keys).count(f'[Limits] {key} (rule {rule})') == 1
            assert f'[Limits] {key}' not in FI.old_fix_keys(dll, keys)
            dll.write_bytes(dll.read_bytes() + FI.WAVE3_MARKERS[key])
            assert f'[Limits] {key} (rule {rule})' not in FI.old_fix_keys(dll, keys)


def test_fight_styles_needs_rule_35_revision_2_only_above_32():
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        dll.write_bytes(b'MZ' + 'FightStyles'.encode('utf-16le'))
        assert FI.old_fix_keys(dll, {'Limits': {'FightStyles': '32'}}) == []         # today's key, any 1.3.1+ DLL
        assert FI.old_fix_keys(dll, {'Limits': {'FightStyles': '64'}}) == ['[Limits] FightStyles (rule 35 revision 2)']
        dll.write_bytes(dll.read_bytes() + FI.WAVE3_MARKERS['FightStyles'])
        assert FI.old_fix_keys(dll, {'Limits': {'FightStyles': '64'}}) == []


def test_the_whole_on_profile_against_a_beta8_dll_names_every_missing_rule():
    keys = gate_keys({'limits_wave3': 'all'})
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        names = b''.join((k + '\0').encode('utf-16le') for ks in FI.RELEASE_18_KEYS.values() for k in ks)
        dll.write_bytes(b'MZ' + names + b'NSA4' + b'NPR14' + FI.GRAB_CARRY_R3_MARKER)
        missing = FI.old_fix_keys(dll, keys)
        for key in (set(WAVE3) | set(LATE)):
            assert any(key in m and 'rule' in m for m in missing), key
        assert '[Limits] FightStyles' in missing and '[Limits] FightStyles (rule 35 revision 2)' in missing   # 64 > 32
        dll.write_bytes(dll.read_bytes() + 'FightStyles'.encode('utf-16le') + b''.join(FI.WAVE3_MARKERS.values()))
        assert not [m for m in FI.old_fix_keys(dll, keys) if any(k in m for k in (set(WAVE3) | set(LATE)))]


def test_dependent_rows_are_refused_without_their_base():
    for bad in ({'Limits': {'PrimitivesPerEffect': '32'}}, {'Limits': {'ScriptPools': 'x1', 'FightMoves': '1024'}}):
        try:
            FI.old_fix_keys('no-such.dll', bad)
            raise AssertionError('accepted')
        except ValueError:
            pass
    assert FI.old_fix_keys('no-such.dll', gate_keys({'limits_wave3': 'all'})) == []


# --------------------------------------------------------------------------------------------- capacities
def test_capacity_follows_the_value_the_build_asks_for_else_the_games_own():
    assert L3.capacity('FightMoves', {}) == 332 and L3.capacity('FightMoves', {'FightMoves': '1024'}) == 1024
    assert L3.capacity('FightMoves', {'FightMoves': '12'}) == 332 and L3.capacity('FightMoves', {'FightMoves': 'x'}) == 332
    assert L3.capacity('StyleEvents', FI.limits_in_use('on')) == 4096 and L3.capacity('StyleEvents', FI.LIMITS) == 1064
    assert L3.capacity('EffectCurves', FI.LIMITS) == 3600 and L3.capacity('EffectCurves', {}) == 900
    assert L3.script_capacity({}) == (620, 1556, 120, 30) and L3.script_capacity({'ScriptPools': 'x1'}) == (4096, 8192, 512, 128)
    assert SB.capacity(FI.limits_in_use('on')) == 64


def test_judge_fails_above_warns_at_equality_and_above_half():
    assert [L3.judge(n, 10) for n in (4, 5, 6, 9, 10, 11)] == [None, None, 'half', 'half', 'full', 'error']


# --------------------------------------------------------------------------------------------- style counting rules
def shared_events():
    return L3.CE.event_table(X('events', None, X('event', {'name': 'hit', 'type': 'ce_atk'})))


def move(name, *children, **attrs):
    return X('FightMove', {'name': name, **attrs}, *children)


def trig(name, tag=None, **extra):
    attrs = {'name': name, **extra}
    if tag is not None:
        attrs['tag'] = tag
    return X('trigger', attrs)


def style(*moves, events=()):
    return X('PowerStyle', None, *events, *moves)


def replay(root):
    return L3.replay_style(root, shared_events(), 'data/powerstyles/t', trigger_cap=64)


def test_a_move_counts_once_and_an_inherited_move_copies_events_but_not_moves():
    a = move('a', trig('hit', 1), trig('hit', 2))
    b = move('b', trig('hit', 3), inherit='a')
    info = replay(style(a, b))
    assert info.moves == 2                                  # two direct FightMove children, nothing for the inheritance
    assert info.events == 2 + (2 + 1)                       # b holds copies of a's two events and its own
    assert info.largest_move_events == 3 and info.peak >= info.events


def test_a_matching_tag_modifies_the_trigger_and_adds_nothing():
    a = move('a', trig('hit', 1), trig('hit', 2))
    b = move('b', trig('hit', 1), inherit='a')              # tag 1 exists in a: an update
    info = replay(style(a, b))
    assert info.events == 2 + 2


def test_reset_frees_the_inherited_copies_and_the_transient_peak_sees_them():
    a = move('a', trig('hit', 1), trig('hit', 2), trig('hit', 3))
    b = move('b', X('trigger', {'reset': 'true'}), trig('hit', 9), inherit='a')
    info = replay(style(a, b))
    assert info.events == 3 + 1
    assert info.peak == 3 + 3 + 1 - 0 or info.peak >= 6     # a's 3 + the 3 inherited copies were live together
    assert info.peak > info.events


def test_unresolvable_triggers_do_not_stay_resident_and_are_reported():
    a = move('a', trig('hit', 1), trig('no_such_event', 2), X('trigger', {'tag': 7}), X('trigger', {}))
    info = replay(style(a))
    assert info.events == 1 and info.unresolved == [('a', 'no_such_event')]


def test_style_and_move_local_events_resolve_triggers_but_are_not_resident():
    ev = X('event', {'name': 'mine', 'type': 'ce_sound'})
    a = move('a', X('event', {'name': 'local', 'inherit': 'mine'}), trig('local', 1), trig('mine', 2))
    info = replay(style(a, events=[ev]))
    assert info.events == 2 and not info.unresolved          # the two event definitions add nothing


def test_the_trigger_cap_frees_the_surplus_event():
    info = L3.replay_style(style(move('a', *[trig('hit', i) for i in range(1, 8)])), shared_events(), '', trigger_cap=5)
    assert info.events == 5


def test_a_missing_style_file_costs_nothing():
    info = L3.replay_style(None, shared_events(), 'data/powerstyles/gone')
    assert (info.present, info.moves, info.events) == (False, 0, 0)


def test_multiple_roots_count_every_direct_fightmove():
    root = X('xmlb_multiple_roots', None, style(move('a', trig('hit', 1))), style(move('b', trig('hit', 1))))
    info = replay(root)
    assert info.moves == 2 and info.events == 2


# --------------------------------------------------------------------------------------------- effect counting rules
PRESETS = L3.Presets([L3.vector_value('0 0 1 0 0 1')], [L3.curve_value('0 4 0 0 4 0')])


def effect(*prims, **root):
    return X('Effect', root, *prims)


def sprite(**attrs):
    return X('Sprite', {'name': 'p', **attrs})


def info_of(root, per=10):
    return L3.replay_effect(root, 'fx/test', PRESETS, per)


def test_sound_is_not_a_primitive_and_a_child_needs_attributes_and_a_recognised_type():
    fx = effect(sprite(), X('Sound', {'name': 'boom', 'soundfile': 'x'}), X('Line', {'name': 'l'}), X('Sprite'),
                X('Mystery', {'name': 'm'}))
    info = info_of(fx)
    assert info.ok and info.prims == 2                      # Sprite and Line; Sound, the bare Sprite and Mystery are not


def test_a_file_only_loads_when_it_is_a_non_empty_effect():
    assert info_of(None).reason == 'missing'
    assert info_of(X('Other', None, sprite())).reason == 'not an Effect'
    assert info_of(effect()).reason == 'empty'
    assert info_of(effect(sprite())).ok


def test_admission_per_effect_stops_at_primitives_per_effect_and_the_extras_are_reported():
    fx = effect(*[sprite() for _ in range(12)])
    info = info_of(fx, per=10)
    assert (info.prims, info.extra) == (10, 2)
    info = info_of(fx, per=32)
    assert (info.prims, info.extra) == (12, 0)


def test_vectors_are_min_and_range_and_reuse_a_preset_only_within_the_tolerance():
    assert L3.vector_value('1 2 3 4 6 8') == (1.0, 2.0, 3.0, 3.0, 4.0, 5.0)
    assert L3.vector_value('1 2 3') is None and L3.vector_value('a b c d e f') is None
    near = L3.vector_value('0 0 1.0004 0 0 1')              # squared distance 1.6e-7 from the preset
    far = L3.vector_value('0 0 1.04 0 0 1')                 # 1.6e-3: past 0.001
    assert L3.matches_preset(near, PRESETS.vectors) and not L3.matches_preset(far, PRESETS.vectors)
    assert L3.matches_preset(L3.vector_value('0 0 0 0 0 0'), PRESETS.vectors)       # the zero preset
    # both three-component distances must be small: a matching minimum with a different range is no preset
    assert not L3.matches_preset(L3.vector_value('0 0 1 0 0 5'), PRESETS.vectors)


def test_non_preset_vectors_are_not_deduplicated_and_every_attribute_takes_a_slot():
    odd = '5 6 7 8 9 10'
    fx = effect(sprite(origin=odd, velocity=odd), sprite(origin=odd), sprite(origin='0 0 1 0 0 1', velocity='0 0 0 0 0 0'))
    info = info_of(fx)
    assert info.prims == 3 and info.vectors == 3            # the same non-preset value three times = three slots; presets free


def test_curves_use_the_fourteen_attributes_and_their_own_presets():
    assert len(L3.CURVE_ATTRS) == 14 and len(L3.VECTOR_ATTRS) == 7
    fx = effect(sprite(alpha='0 4 0 0 4 0 10000 -10000', size='1 2 3 4 5 6', uvscale='9 9 9 9 9 9 10000 -10000', color='x'))
    info = info_of(fx)
    assert info.curves == 2                                  # alpha is the preset (clamps default to 10000 / -10000)


def test_death_and_interval_effects_are_recorded_for_the_recursive_load():
    info = info_of(effect(sprite(DeathFxFile='explode/big.xmlb', IntervalFxFile='Effects/Smoke')))
    assert info.deps == ('explode/big', 'smoke')


def test_effect_names_drop_the_prefix_and_the_extension():
    assert L3.effect_name('Effects\\Powers\\Foo.XMLB') == 'powers/foo' and L3.effect_name('explode/lrgexp1.xml') == 'explode/lrgexp1.xml'


# --------------------------------------------------------------------------------------------- scripts
def test_else_and_endif_are_temporaries_not_retained_nodes():
    text = '\r\n'.join(['# comment', 'a = 1', 'b = "x"', 'if a == 1', '  c = 2.5', 'else', '  d = 3', 'endif', 'def helper',
                         'wait(1)', ''])
    r = VS.count_script(text)
    assert r.statements == 9 and r.temporaries == 2 and r.skipped == 1 and r.retained == 6
    assert r.literals == 6 and r.locals == {'a', 'b', 'c', 'd'}


# --------------------------------------------------------------------------------------------- party scan
def test_scan_parties_finds_the_worst_party_in_name_order_ties_first():
    hero = {'a': {'x1'}, 'b': {'x2'}, 'c': {'x3', 'x4'}, 'd': {'x1', 'x2'}}
    w = {'n': {k: 1 for k in ('base', 'x1', 'x2', 'x3', 'x4')}}
    r = L3.scan_parties({'base'}, hero, w, size=2)
    assert r['max']['n'] == (5, ('c', 'd')) and r['parties'] == 6                 # c and d together hold four of the five
    tie = L3.scan_parties({'base'}, {'a': {'x1'}, 'b': {'x2'}, 'c': {'x3'}}, w, size=1)
    assert tie['max']['n'] == (2, ('a',))                                         # equal parties: the first in name order
    assert L3.scan_parties({'base'}, {}, w)['max']['n'] == (1, ())
    # fewer heroes than seats: the party is everyone
    assert L3.scan_parties(set(), {'a': {'x1'}}, w)['max']['n'] == (1, ('a',))


# --------------------------------------------------------------------------------------------- a whole synthetic build
class FakeReader:
    def __init__(self, trees):
        self.trees = {C.norm(k): v for k, v in trees.items()}

    def tree(self, rel, exts=None):
        return self.trees.get(C.norm(rel) + (exts[0] if exts else ''))


def pkg(*entries):
    return X('package', None, *[X(kind, {'filename': fn}) for kind, fn in entries])


def world(heroes=('alpha', 'beta', 'gamma'), extra_moves=0, prims=2, hero_prims=None, scripts=None):
    """one zone 'test/hall', permanent + zone + three heroes, styles with known costs, effects with known costs"""
    t = {'data/herostat': X('herostat', None, X('stats', {'name': 'default', 'skin': '1'}),
                            *[X('stats', {'name': h.title(), 'skin': str(10 + i), 'powerstyle': f'ps_{h}'})
                              for i, h in enumerate(heroes)],
                            X('stats', {'name': 'ProfXAstral', 'skin': '99', 'powerstyle': 'ps_x'})),
         'data/npcstat': X('npcstat', None, X('stats', {'name': 'Guard', 'skin': '50'})),
         'data/shared_combat_events': X('events', None, X('event', {'name': 'hit', 'type': 'ce_atk'})),
         'packages/generated/maps/package/permanent': pkg(('effect', 'effects/shared/glow')),
         'packages/generated/maps/package/permanent_fightstyles': pkg(('fightstyle', 'data/shared_nodes')),
         'data/shared_nodes': X('NodeList', None, *[move(f'n{i}', trig('hit', 1)) for i in range(4 + extra_moves)]),
         'packages/generated/maps/test/hall': pkg(('fightstyle', 'data/fightstyles/zone_style'), ('script', 'scripts/test/hall'),
                                                  ('effect', 'effects/zone/boom')),
         'data/fightstyles/zone_style': style(move('z1', trig('hit', 1), trig('hit', 2))),
         'maps/test/hall': X('world', {'zonescript': 'scripts/test/hall'}),
         'maps/test/hall.chrb': X('characters', None, X('character', {'name': 'Guard'}), X('character', {'name': 'Alpha'})),
         'packages/generated/characters/guard_50': pkg(('fightstyle', 'data/fightstyles/guard_style'), ('effect', 'effects/guard/hit')),
         'data/fightstyles/guard_style': style(move('g1', trig('hit', 1))),
         'effects/shared/glow': effect(sprite(), sprite()),
         'effects/zone/boom': effect(*[sprite() for _ in range(prims)]),
         'effects/guard/hit': effect(sprite(DeathFxFile='guard/spark')),
         'effects/guard/spark': effect(sprite(origin='5 6 7 8 9 10')),
         'effects/defaultvectors': X('vectors', None, X('vector', {'v': '0 0 1 0 0 1'})),
         'effects/defaultquads': X('quads', None, X('quad', {'q': '0 4 0 0 4 0'}))}
    for i, h in enumerate(heroes):
        n = (hero_prims or {}).get(h, 1)
        t[f'packages/generated/characters/{h}_{10 + i}'] = pkg(('fightstyle', f'data/powerstyles/ps_{h}'),
                                                               ('effect', f'effects/powers/{h}'))
        t[f'data/powerstyles/ps_{h}'] = style(move('p1', trig('hit', 1), trig('hit', 2)), move('p2', trig('hit', 3)))
        t[f'effects/powers/{h}'] = effect(*[sprite(origin=f'{i + 1} 2 3 4 5 {j + 6}') for j in range(n)])
    return t


def census(trees=None, limits=None, scripts=None, **kw):
    trees = trees or world(**kw)
    reader = FakeReader(trees)
    read = (lambda rel: (scripts or {}).get(rel))
    return L3.Census(reader, ['test/hall'], limits=limits if limits is not None else FI.limits_in_use('on'), read_text=read)


def run_check(fn, c, *args):
    ck = Check('V', 't')
    fn(c, ck, *args)
    return ck


def test_a_zone_counts_permanent_zone_npc_and_the_worst_party_but_not_the_excluded_form():
    c = census()
    base, hero = c.zone('test/hall')['styles']
    assert base == {'data/shared_nodes', 'data/fightstyles/zone_style', 'data/fightstyles/guard_style'}
    assert set(hero) == {'alpha', 'beta', 'gamma'}                                       # ProfXAstral is no party member
    rep = c.style_report()['zones']['test/hall']
    assert rep['styles'][0] == 3 + 3 and rep['moves'][0] == 4 + 1 + 1 + 3 * 2 and len(rep['moves'][1]) == 3
    # shared_nodes: 4 moves x 1 event; zone 2; guard 1; each hero style 3
    assert rep['events'][0] == 4 + 2 + 1 + 3 * 3


def test_v_moves_reports_the_zone_total_the_witness_and_the_largest_style_against_150():
    ck = run_check(L3.check_moves, census(extra_moves=200))
    assert ck.counts['capacity'] == 1024 and ck.counts['max_moves'] == 204 + 1 + 1 + 6
    assert ck.counts['max_moves_in_one_style'] == 204 and ck.counts['largest_style'] == 'data/shared_nodes'
    assert ck.counts['witness_zone'] == 'test/hall' and ck.details['witness']['party']
    assert any('204 FightMoves in one style' in m and '150' in m for m in ck.errors)      # past the per-style move map
    ck = run_check(L3.check_moves, census(extra_moves=170, limits={}))
    assert ck.counts['capacity'] == 332 and any('above half' in w or 'full' in w for w in ck.warnings)


def test_v_moves_fails_above_the_pool_and_warns_above_half_of_it():
    assert any('FightMoves' in e and '(> 332)' in e for e in run_check(L3.check_moves, census(extra_moves=330, limits={})).errors)
    ck = run_check(L3.check_moves, census(extra_moves=170, limits={}))             # 170 + 8 + 6 > half of 332
    assert not ck.errors or all('per-style' in e for e in ck.errors)
    assert any('above half of the table (332)' in w for w in ck.warnings)


def test_v_events_counts_final_and_transient_and_reports_unresolved_triggers():
    trees = world()
    trees['data/powerstyles/ps_alpha'] = style(move('p1', trig('hit', 1), trig('gone', 2)),
                                               move('p2', X('trigger', {'reset': 'true'}), trig('hit', 5), inherit='p1'))
    ck = run_check(L3.check_events, census(trees))
    assert ck.counts['capacity'] == 4096 and ck.counts['max_events'] > 0
    assert ck.counts['styles_with_unresolved_triggers'] == 1
    assert ck.details['unresolved_triggers']['data/powerstyles/ps_alpha'] == [['p1', 'gone']]
    assert ck.counts['max_events_transient_peak'] >= ck.counts['max_events']
    assert any('stay dropped' in n for n in ck.notes)


def test_v_effect_files_counts_recursive_loads_and_lists_unresolved_references():
    trees = world()
    trees['effects/zone/boom'] = effect(sprite(DeathFxFile='explode/lrgexp1.xml'))
    ck = run_check(L3.check_effect_files, census(trees))
    # glow, boom, guard/hit, guard/spark, 3 hero effects (+ the unresolved .xml reference counted nowhere)
    assert ck.counts['max_files'] == 7 and ck.counts['capacity'] == 512
    assert ck.details['unresolved_effects'] == {'explode/lrgexp1.xml': 'missing; named by the Death/Interval effect of zone/boom'}
    assert ck.counts['unresolved_effect_references'] == 1


def test_a_dot_xml_reference_is_not_guessed_but_the_strip_reading_is_available():
    trees = world()
    trees['effects/zone/boom'] = effect(sprite(DeathFxFile='explode/lrgexp1.xml'))
    trees['effects/explode/lrgexp1'] = effect(sprite())
    strict = census(trees)
    assert strict.effect('explode/lrgexp1.xml').reason == 'missing'
    strip = L3.Census(FakeReader(trees), ['test/hall'], limits=FI.limits_in_use('on'), xml_refs='strip')
    assert strip.effect('explode/lrgexp1.xml').ok


def test_the_scope_upper_bound_counts_an_effect_loaded_by_two_owners_twice():
    trees = world()
    for h in ('alpha', 'beta'):
        trees[f'packages/generated/characters/{h}_{10 if h == "alpha" else 11}'] = pkg(
            ('fightstyle', f'data/powerstyles/ps_{h}'), ('effect', 'effects/shared/glow'))
    c = census(trees)
    party = ('alpha', 'beta', 'gamma')
    shared_scope = c.effect_report()['test/hall']['max']['files'][0]
    scoped, keys = c.scoped_files('test/hall', party)
    assert scoped == shared_scope + 2                      # glow also loaded by alpha and beta under their own scopes
    assert L3.effect_key('permanent', 'shared/glow') in keys and 'alpha:shared/glow' in keys and 'beta:shared/glow' in keys
    assert L3.effect_key(L3.PACKAGE_SCOPE, 'a/b') == '0:a/b' and L3.effect_key(1, 'a/b') != L3.effect_key(2, 'a/b')


def test_scripted_effect_loads_count_when_a_script_names_the_effect_literally():
    script = {'scripts/test/hall.py': 'a = 1\r\nspawnEffect("_OWNER_", "effects/script/flash", "x", "y")\r\n'
                                      'spawnEffectBone(me, "script/bolt", "bone")\r\n'}
    trees = world()
    trees['effects/script/flash'] = effect(sprite())
    trees['effects/script/bolt'] = effect(sprite())
    c = census(trees, scripts=script)
    assert c.zone('test/hall')['scripted'] == ['script/bolt', 'script/flash']
    assert c.effect_report()['test/hall']['max']['files'][0] == census(trees).effect_report()['test/hall']['max']['files'][0] + 2


def test_v_primitives_v_vectors_v_curves_and_the_effect_budget_name_the_table_that_binds_first():
    trees = world(prims=40)                                    # one effect with 40 children
    c = census(trees)
    ck = run_check(L3.check_primitives, c)
    assert ck.counts['per_effect_capacity'] == 32 and ck.counts['effects_with_refused_children'] == 1
    assert any('past PrimitivesPerEffect=32' in e for e in ck.errors)                    # 40 recognised children, 32 admitted
    assert ck.counts['capacity'] == 2048 and ck.counts['max_primitives_in_one_effect'] == 32
    ck = run_check(L3.check_vectors, c)
    assert ck.counts['presets_reserved'] == 84 and ck.counts['max_vectors'] >= 84 and ck.counts['presets_found'] == 2
    ck = run_check(L3.check_curves, c)
    assert ck.counts['presets_reserved'] == 140 and ck.counts['max_curves'] >= 140 and ck.counts['presets_found'] == 2
    # the combined report names the table closest to its capacity; shrink one to see it bind
    c = census(trees)
    c.effect_capacities = lambda: {'files': 512, 'defs': 512, 'prims': 30, 'vectors': 4096, 'curves': 3600}
    ck = run_check(L3.check_curves, c)
    assert ck.counts['effect_budget_binding'] == 'prims' and ck.details['effect_budget']['tables']['prims']['capacity'] == 30
    assert any('primitive definitions' in e and 'binds first' in e for e in ck.errors)
    assert ck.details['effect_budget']['party'] and ck.counts['effect_budget_zone'] == 'test/hall'


def test_the_effect_budget_warns_above_half_and_stays_quiet_below():
    ck = run_check(L3.check_curves, census())
    assert not ck.errors and not [w for w in ck.warnings if 'effect budget' in w]
    trees = world()
    trees['packages/generated/maps/test/hall'] = pkg(('fightstyle', 'data/fightstyles/zone_style'), ('script', 'scripts/test/hall'),
                                                     *[('effect', f'effects/many/e{i}') for i in range(120)])
    for i in range(120):
        trees[f'effects/many/e{i}'] = effect(sprite())
    ck = run_check(L3.check_curves, census(trees, limits={}))                      # 120 + 7 effect files of the stock 220
    assert any('effect budget' in w and 'effect files binds first' in w for w in ck.warnings)
    ck = run_check(L3.check_effect_files, census(trees, limits={}))
    assert any('above half of the table (220)' in w for w in ck.warnings) and not ck.errors


def test_v_scripts_replaces_the_622_wording_with_retained_nodes_values_and_scripts():
    body = ['a = 1', 'if a == 1', '  b = "x"', 'else', '  c = 2', 'endif']
    scripts = {'scripts/test/hall.py': '\r\n'.join(body * 30) + '\r\n'}
    c = census(scripts=scripts, limits={})                                         # stock pools: 620 nodes
    rep = c.script_report(VS.count_script)['test/hall']
    assert rep['source_statements'] == 180 and rep['temporaries'] == 60 and rep['retained'] == 120
    assert rep['literals'] == 120 and rep['locals'] == 3 and rep['values'] == 120 + 3 + L3.VALUE_TEMPORARIES
    ck = run_check(L3.check_scripts, c, VS.count_script)
    assert not ck.errors and ck.counts['statements_capacity'] == 620 and ck.counts['max_retained_nodes'] == 120
    # 585 retained nodes of 622 source lines is below 620: no 'lines lost' alarm, only the half-full warning
    big = {'scripts/test/hall.py': '\r\n'.join(['x = 1'] * 548 + ['if x == 1', 'else', 'endif'] * 12 + ['y = 2'] * 1) + '\r\n'}
    ck = run_check(L3.check_scripts, census(scripts=big, limits={}), VS.count_script)
    assert not ck.errors and any('statement nodes' in w and 'above half' in w for w in ck.warnings)
    assert not any('622' in m or 'statements in the zone script' in m for m in ck.errors + ck.warnings)
    over = {'scripts/test/hall.py': '\r\n'.join(['x = 1'] * 625) + '\r\n'}
    ck = run_check(L3.check_scripts, census(scripts=over, limits={}), VS.count_script)
    assert any('statement nodes' in e and '(> 620)' in e for e in ck.errors)
    ck = run_check(L3.check_scripts, census(scripts=over, limits={'ScriptPools': 'x1'}), VS.count_script)
    assert not ck.errors and ck.counts['statements_capacity'] == 4096


def test_forced_missions_restrict_the_parties_the_scan_draws_on():
    trees = world(hero_prims={'alpha': 5, 'beta': 5, 'gamma': 1})
    free = census(trees)
    forced = L3.Census(FakeReader(trees), ['test/hall'], limits=FI.limits_in_use('on'),
                       party_filter=lambda zone, names: ['gamma'])
    a = free.effect_report()['test/hall']['max']['prims'][0]
    b = forced.effect_report()['test/hall']['max']['prims'][0]
    assert b < a and forced.effect_report()['test/hall']['max']['prims'][1] == ('gamma',)


def test_v23_follows_the_raised_registry_and_reports_a_witness_when_the_build_has_wave3():
    class V:
        def __init__(self, mode, extra):
            from test_style_budget import FakeValidator
            self.inner = FakeValidator(extra)
            self.ctx = SimpleNamespace(args=SimpleNamespace(limits_wave3=mode))

        def __getattr__(self, name):
            return getattr(self.inner, name)

    ck = Check('V23', 'fight styles')
    SB.validate(V('on', [f'z{i}' for i in range(40)]), ck)                     # 2 + 40 + 1 = 43 > 32, <= 64, above half
    assert not ck.errors and ck.counts['capacity'] == 64 and ck.details['witness']['party'] == ['hero_a']
    assert ck.counts['witness_zone'] == 'test/hall' and len(ck.warnings) == 1 and 'above half' in ck.warnings[0]
    ck = Check('V23', 'fight styles')
    SB.validate(V('off', [f'z{i}' for i in range(40)]), ck)                    # today's behaviour: 43 > 32
    assert ck.counts['capacity'] == 32 and len(ck.errors) == 1 and 'witness' not in ck.details


def test_the_wave3_checks_run_only_for_a_build_made_with_the_option():
    off = SimpleNamespace(ctx=SimpleNamespace(args=SimpleNamespace()))
    on = SimpleNamespace(ctx=SimpleNamespace(args=SimpleNamespace(limits_wave3='on')))
    assert not L3.enabled(off) and L3.enabled(on) and L3.mode_of(off) == 'off'
    ck = Check('V-MOVES', 'x')
    L3.run_check(off, ck, lambda c, k: (_ for _ in ()).throw(AssertionError('ran')))
    assert ck.status == 'skipped'
    assert [cid for cid, _, _ in L3.VALIDATORS] == ['V-MOVES', 'V-EVENTS', 'V-EFFECT-FILES', 'V-PRIMITIVES', 'V-VECTORS',
                                                    'V-CURVES', 'V-SCRIPTS']


class FakeValidatorObject:
    """The parts of validate.Validator the wave-3 hooks read (exists / tree / read / converted_zones / ctx.args)."""

    def __init__(self, trees, mode, scripts=None):
        self.rel = {(k if k.endswith('.chrb') else k + '.xmlb'): v for k, v in trees.items()}
        self.scripts = scripts or {}
        self.ctx = SimpleNamespace(args=SimpleNamespace(limits_wave3=mode))

    def exists(self, rel):
        return C.norm(rel) in {C.norm(k) for k in self.rel}

    def tree(self, rel):
        return {C.norm(k): v for k, v in self.rel.items()}.get(C.norm(rel))

    def converted_zones(self):
        return ['test/hall']

    def read(self, rel):
        return self.scripts[rel].encode('latin-1')


def test_the_validator_hooks_run_every_check_through_a_validator_object():
    import functools
    scripts = {'scripts/test/hall.py': 'a = 1\r\nif a == 1\r\nelse\r\nendif\r\n'}
    v = FakeValidatorObject(world(), 'on', scripts)
    seen = {}
    for cid, title, fn in L3.VALIDATORS:
        ck = Check(cid, title)
        functools.partial(fn, v)(ck)
        assert ck.status != 'skipped' and not ck.errors, (cid, ck.errors)
        seen[cid] = ck
    assert seen['V-MOVES'].counts['witness_zone'] == 'test/hall' and seen['V-EVENTS'].counts['capacity'] == 4096
    assert seen['V-EFFECT-FILES'].counts['max_files'] == 7 and seen['V-CURVES'].counts['effect_budget_binding']
    assert seen['V-SCRIPTS'].counts['max_retained_nodes'] == 2 and seen['V-SCRIPTS'].counts['scripts_capacity'] == 120
    off = FakeValidatorObject(world(), 'off', scripts)
    ck = Check('V-MOVES', 'x')
    functools.partial(L3.VALIDATORS[0][2], off)(ck)
    assert ck.status == 'skipped' and not ck.counts


def test_the_static_reports_witnesses_reproduce_on_a_finished_build():
    """env-gated (LC_W3_SELFTEST_OUT = a finished 080c-era build folder; never public CI): the replay gives the design's
    witnesses - styles 24, moves 306, largest style 108, events 831, Master Mold 2 at 585 retained nodes."""
    import os
    import unittest
    out = os.environ.get('LC_W3_SELFTEST_OUT')
    if not out or not (Path(out) / '_build' / 'zones_detail.json').is_file():
        raise unittest.SkipTest('LC_W3_SELFTEST_OUT (a finished build folder) is not set')
    assert L3.main(['--out', out]) == 0


def test_the_builder_report_records_the_option_so_the_ini_gets_the_keys():
    """xml1builder (prepared sources) writes report.json's build block itself: --limits-wave3 must be recorded there
    (only when on), or fix_ini.port_keys finds no option and the build's ini keeps FightStyles=32 and no wave 3 keys."""
    import build_xml1
    from xml1builder import pipeline as P
    for mode, expected in (('all', 'all'), ('on', 'on'), ('off', None)):
        with tempfile.TemporaryDirectory() as d:
            args = SimpleNamespace(limits_wave3=mode, **{o: v[1] for o, v in build_xml1.CONTENT_OPTS.items()})
            ctx = SimpleNamespace(report=SimpleNamespace(to_json=lambda: {}), registry=SimpleNamespace(entries=[]), shared={})
            job = SimpleNamespace(ctx=ctx, args=args, out=d, xml2=d, movies=True, t0=0)
            pipe = P.RealPipeline.__new__(P.RealPipeline); pipe.C = C
            (Path(d) / '_build').mkdir()
            path = pipe.write_report(job, {})
            build = json.loads(Path(path).read_text(encoding='utf-8'))['build']
            assert build.get('limits_wave3') == expected
            assert FI.build_record(d).get('limits_wave3') == expected
