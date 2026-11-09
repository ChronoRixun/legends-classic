"""Synthetic beam/flame trace contracts; source triggers retain full damage draws."""
import copy
import json
from types import SimpleNamespace
import xml.etree.ElementTree as ET

from xml1build import heroes as H, semi_auto as S, weapons as W, fix_ini as F


def fixture(tmp_path, kind='beam', named=False, grenade=False, interval='0.75'):
    weapon = dict(name='wp_toy_arc', type=kind, continuousbeam='true', tracetime=interval,
                  recoiltime='0.1', range='300', damage='TOY', powerstyle='ps_toy')
    values = ET.fromstring('<values><value name="TOY" min="40" max="52"/></values>')
    definitions = ET.Element('weapons_list')
    ET.SubElement(definitions, 'weapon', weapon)
    stats = ET.fromstring('<list><stats name="ToyGuard" weapon="wp_toy_arc"/></list>')
    source = ET.Element('PowerStyle')
    if named:
        ET.SubElement(source, 'event', name='toy_fire', inherit='weapon_fire', weapon='wp_toy_arc')
        ET.SubElement(source, 'event', name='toy_alias', inherit='toy_fire')
    for move in ('power_attack', 'crouch_pow_atk', 'power_boost', 'flame_sweep'):
        m = ET.SubElement(source, 'FightMove', name=move, handler='ch_weapon_semi_auto')
        times = ('.1', '.2', '.3', '.4', '.5', '.6', '.8') if move == 'power_boost' else ('0',)
        for time in times:
            a = dict(name='toy_alias' if named else 'weapon_fire', time=time)
            if move == 'flame_sweep':
                a.update(tag='150', time='-1')
            ET.SubElement(m, 'trigger', a)
    built = copy.deepcopy(source)
    W.rewrite_weapon_events(built, {'wp_toy_arc': weapon}, values=H.Values(values))
    W.apply(built, weapon, values=H.Values(values))
    variant = 'x1_ps_toy_toy_arc' + ('_toygrenade' if grenade else '')
    built_stats = ET.fromstring(f'<list><stats name="ToyGuard" powerstyle="{variant}"/></list>')
    contract = S.contract(stats, definitions, {'ps_toy': source})
    (tmp_path / '_build').mkdir(exist_ok=True)
    (tmp_path / '_build/semi_auto.json').write_text(json.dumps(contract), encoding='utf-8')
    (tmp_path / 'dinput.dll').write_bytes(b'lc-npc-beam-trace/1\0')
    source_trees = {'data/values.xml': values, 'data/weapons/weapons.eng': definitions,
                    'data/npcstat.eng': stats, 'data/powerstyles/ps_toy.eng': source}
    built_trees = {f'data/powerstyles/{variant}.xmlb': built, 'data/npcstat.xmlb': built_stats}
    ctx = SimpleNamespace(out=tmp_path, read_x1_xml=lambda p: source_trees[p],
                          x1_path=lambda p: p if p in source_trees else None)
    v = SimpleNamespace(ctx=ctx, idx=SimpleNamespace(under=lambda p: [r for r in built_trees if r.startswith(p)]),
                        entry=lambda p: built_trees.get(p), tree=lambda p: built_trees[p], trees=built_trees)
    return v, built, contract


def errors(v):
    found = []
    ck = SimpleNamespace(error=found.append, warn=lambda m: None, count=lambda k: None, set=lambda k, n: None)
    W.validate(v, ck)
    return found


def test_weapon_trace_marks_every_full_draw_and_preserves_tags(tmp_path):
    for kind in ('beam', 'flame'):
        v, built, _ = fixture(tmp_path, kind)
        beams = list(built.iter('trigger'))
        beams = [e for e in beams if e.get('name') == 'beam']
        assert len(beams) == 10
        assert all(e.get('split_damage') == '32765 32765' and e.get('split_count') == '0'
                   and e.get('damage') == '27 51' for e in beams)
        assert any(e.get('tag') == '150' and e.get('time') == '-1' for e in beams)
        assert errors(v) == []


def test_weapon_trace_validator_rejects_missing_marker_and_authored_calls(tmp_path):
    v, built, _ = fixture(tmp_path)
    assert errors(v) == []
    beam = next(e for e in built.iter('trigger') if e.get('name') == 'beam')
    beam.attrib.pop('split_damage', None)
    assert any('trace' in e.lower() for e in errors(v))
    v, built, _ = fixture(tmp_path)
    move = next(m for m in built.iter('FightMove') if m.get('name') == 'power_boost')
    move.remove(next(e for e in move if e.get('name') == 'beam'))
    assert any('trace' in e.lower() for e in errors(v))


def test_weapon_trace_validator_requires_complete_holder_metadata_and_companion(tmp_path):
    for mutation in ('old', 'missing', 'row', 'type', 'interval', 'holder'):
        v, built, contract = fixture(tmp_path)
        if mutation == 'old':
            (tmp_path / 'dinput.dll').write_bytes(b'NSA4\0')
        elif mutation == 'missing':
            (tmp_path / 'dinput.dll').unlink()
        elif mutation == 'holder':
            v.tree('data/npcstat.xmlb')[0].set('powerstyle', 'x1_other')
        else:
            if mutation == 'row':
                contract['records'] = []
            else:
                words = contract['records'][0].split('|')
                words[6 if mutation == 'type' else 7] = '00000000'
                contract['records'][0] = '|'.join(words)
            (tmp_path / '_build/semi_auto.json').write_text(json.dumps(contract), encoding='utf-8')
        assert errors(v), mutation


def test_weapon_trace_unsupported_positive_source_interval_cannot_fall_back_to_ungated_output(tmp_path):
    v, _, _ = fixture(tmp_path, interval='61')
    assert errors(v)


def test_weapon_trace_named_inheritance_and_grenade_variants(tmp_path):
    v, built, _ = fixture(tmp_path, named=True, grenade=True)
    event = next(e for e in built.iter('event') if e.get('name') == 'toy_alias')
    assert event.get('split_damage') == '32765 32765'
    assert errors(v) == []
    event.set('split_count', '1')
    assert errors(v)


def test_weapon_trace_keeps_bullet_and_zero_trace_nullifier():
    for kind, interval, expected in [('bullet', '0.5', '32766 32766'), ('beam', '0', None),
                                      ('projectile', '0.75', None)]:
        root = ET.fromstring('<PowerStyle><FightMove><trigger name="weapon_fire"/></FightMove></PowerStyle>')
        W.apply(root, dict(type=kind, tracetime=interval, damage='40'))
        shot = next(e for e in root.iter('trigger') if e.get('name') in ('beam', 'projectile'))
        assert shot.get('split_damage') == expected


def test_weapon_trace_companion_gate_refuses_schema4_only(tmp_path):
    _, _, contract = fixture(tmp_path)
    keys = S.ini_sections(contract)
    dll = tmp_path / 'old.dll'
    data = 'NpcSemiAuto NpcPowerRule'.encode('utf-16le') + b'NSA4 NPR14'
    dll.write_bytes(data)
    try:
        F.check_release_dll(dll, keys)
    except F.FixTooOld as e:
        assert 'trace' in str(e).lower()
    else:
        assert False, 'old companion silently accepts beam/flame output'
    dll.write_bytes(data + b'lc-npc-beam-trace/1\0')
    F.check_release_dll(dll, keys)


def test_weapon_trace_does_not_raise_companion_requirement_for_bullet_only_table(tmp_path):
    _, _, contract = fixture(tmp_path)
    parts = contract['records'][0].split('|')
    parts[6] = '00000000'  # original bullet type, same positive trace interval
    contract['records'][0] = '|'.join(parts)
    keys = S.ini_sections(contract)
    dll = tmp_path / 'bullet-only.dll'
    dll.write_bytes('NpcSemiAuto NpcPowerRule'.encode('utf-16le') + b'NSA4 NPR14')
    F.check_release_dll(dll, keys)


def test_weapon_trace_old_fix_warning_cannot_write_unsafe_ini(tmp_path):
    _, _, contract = fixture(tmp_path)
    keys = S.ini_sections(contract)
    (tmp_path / 'dinput.dll').write_bytes(b'NSA4')
    for present in (True, False):
        if not present:
            (tmp_path / 'dinput.dll').unlink()
        try:
            F.write_port_keys(tmp_path, keys, old_fix_ok=True)
        except F.FixTooOld as e:
            assert 'trace' in str(e).lower()
        else:
            assert False, 'old-fix warning bypassed a required runtime damage gate'
        assert not (tmp_path / 'xml2-fix.ini').exists()


def test_weapon_trace_shared_weapon_can_bind_default_and_grenade_variants(tmp_path):
    v, built, _ = fixture(tmp_path)
    stats = v.ctx.read_x1_xml('data/npcstat.eng')
    ET.SubElement(stats, 'stats', name='ToyGuard2', weapon='wp_toy_arc')
    ET.SubElement(v.tree('data/npcstat.xmlb'), 'stats', name='ToyGuard2', powerstyle='x1_ps_toy_toy_arc_toygrenade')
    v.trees['data/powerstyles/x1_ps_toy_toy_arc_toygrenade.xmlb'] = copy.deepcopy(built)
    contract = S.contract(stats, v.ctx.read_x1_xml('data/weapons/weapons.eng'),
                          {'ps_toy': v.ctx.read_x1_xml('data/powerstyles/ps_toy.eng')})
    (tmp_path / '_build/semi_auto.json').write_text(json.dumps(contract), encoding='utf-8')
    assert errors(v) == []


def test_weapon_trace_validates_length_shortened_grenade_variant(tmp_path):
    v, built, _ = fixture(tmp_path)
    old = 'x1_ps_toy_toy_arc'
    variant = W.variant_grenade_name(old, 'toygrenade_long')
    assert not variant.startswith(old + '_')
    assert len(variant) <= W.STYLE_NAME_MAX
    v.trees[f'data/powerstyles/{variant}.xmlb'] = v.trees.pop(f'data/powerstyles/{old}.xmlb')
    v.tree('data/npcstat.xmlb')[0].set('powerstyle', variant)
    assert errors(v) == []


def test_weapon_trace_named_trigger_cannot_override_its_definition_marker(tmp_path):
    for key, value in (('split_count', '1'), ('split_damage', '0 0')):
        v, built, _ = fixture(tmp_path, named=True)
        trigger = next(t for t in built.iter('trigger') if t.get('name') == 'toy_alias')
        trigger.set(key, value)
        assert errors(v), (key, value)
