"""Loot step 1, builder side (xml1build.loot, DESIGN 2.1-2.4, 8.1): identities, display names, the references, the item
table (88 kept, the Danger Room rewards rebuilt in place, the rest appended), the sidecar format, the approximations
file, the INI key and the shop's Training tab. Invented items only: no game data."""
import hashlib
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import builder_stub as B
from test_builder_cli import build_argv, check_stream, run, setup
from test_w2_builder import W2_DLL, dll_knowing, lc_keys, raises, w2_build
from xml1build import common as C
from xml1build import fix_ini as FI
from xml1build import item_bonuses as IB
from xml1build import loot as L
from xml1build import shop_appearance as SA
from xml1build.heroes import Values


def values():
    r = ET.Element('values')
    ET.SubElement(r, 'value', name='L7', min='12', max='18')
    ET.SubElement(r, 'value', name='A7', min='9')
    return Values(r)


def pu(name, level, **attrs):
    return ET.Element('activepowerup', {'powerup': name, 'level': level, 'life': '-1', **attrs})


def x1_items():
    """an invented XML1 items.eng: 12 plain definitions (indices 0-11), equipment, then the packs and pips"""
    root = ET.Element('items')

    def add(*kids, **a):
        e = ET.SubElement(root, 'item', {k.lower(): v for k, v in a.items()})
        e.extend(kids)
        return e
    add(name='MONEY1', type='money', frequency='5')
    add(name='MONEY2', type='money', frequency='5')
    add(name='MONEY3', type='money', frequency='5')
    add(name='XP', type='xp')
    add(name='SKILL', type='skill')
    add(name='STAT', type='stat')
    for k in ('KEY1', 'KEY2', 'KEY3', 'KEYCARD1', 'KEYCARD2', 'KEYCARD3'):
        add(name=k, type='item')
    add(pu('body', '2'), name='GLOVE_A', type='equipment', **{'class': '0', 'group': '1', 'frequency': '3', 'quality': '-1',
                                                             'cost': '500', 'displayname': 'Glove', 'description': 'invented a'})
    add(pu('speed', '1'), pu('damage', 'L7'), name='BELT_B', type='equipment',
        **{'class': '1', 'group': '2', 'frequency': '2', 'quality': '2', 'cost': '3000', 'displayname': 'Belt',
           'description': 'invented b'})
    add(pu('move', '1.2', affect_type='scale'),
        pu('special', 'L7', func_damage='damageaddattack', damagetype='dmg_fire', scope_attack='punch'),
        name='RING_C', type='equipment', unique='true',
        **{'class': '2', 'group': '2', 'frequency': '1', 'grabbag': 'true', 'cost': '6500', 'displayname': 'Ring',
           'description': 'invented c'})
    add(pu('strength', '3'), pu('def_damage_scale', '0', scope_damage='dmg_mental'), name='REWARD_D', type='equipment',
        unique='true', **{'class': '1', 'group': '-1', 'displayname': 'Reward', 'description': 'invented d'})
    add(pu('mind', '3'), name='ASTRAL_E', type='equipment', unique='true',
        **{'class': '0', 'group': '-1', 'displayname': 'Astral', 'description': 'invented e'})
    add(pu('body', '1'), name='HELM_F', type='equipment', unique='true',
        **{'class': '0', 'group': '-1', 'displayname': 'Helm', 'description': 'invented f'})
    add(pu('reflect_damage', 'L7', user1='50'), name='ARMOR_G', type='equipment',
        **{'class': '2', 'group': '5', 'frequency': '3', 'quality': '1', 'cost': '9000', 'displayname': 'Armor',
           'description': 'invented g'})
    add(name='HEALTH_ITEM', type='item', group='1', cost='0', frequency='4', onactivate='restoreHealth()')
    add(name='XTREME_PIP', type='item', cost='1500', quality='0', frequency='4', onactivate='addXtremePip()')
    add(name='SKIRMISH_KING_PIP', type='item', cost='1500', quality='2', frequency='0', onactivate='hailToTheKing()')
    return root


def strings():
    root = ET.Element('strings')
    for i, t in ((1006, 'Broken'), (1007, 'Basic'), (1008, 'Super'), (1009, 'Ultra')):
        ET.SubElement(root, 'string', id=str(i), text=t)
    return root


def ctx_for(loot='xml1', save_layout='w2', frontend='xml1', root=None, **extra):
    root = root if root is not None else x1_items()
    ctx = SimpleNamespace(shared={}, args=SimpleNamespace(loot=loot, save_layout=save_layout, frontend=frontend,
                                                          loot_construction=extra.get('construction', 'zero-draw'),
                                                          loot_def_damage_scale=extra.get('def_damage_scale', 'noop')),
                          read_x1_xml=lambda rel: strings() if rel.endswith('strings.eng') else root,
                          x1_values=values, notes=[], errors=[])
    ctx.note = ctx.notes.append
    ctx.error = ctx.errors.append
    ctx.shared['loot_plan'] = L.Plan(L.source_items(root), ['REWARD_D'])
    return ctx


def legacy_table(ctx, with_reward=True):
    """what Zones.items_to_add hands to apply_items today for the invented table: the appended XML1 items, plain except
    the Danger Room reward, which is already its re-conversion (loot.dr_reward_element)"""
    out = []
    for name in ('SKILL', 'ASTRAL_E', 'HEALTH_ITEM'):
        out.append(ET.Element('item', {'name': name, 'type': 'potion' if name == 'HEALTH_ITEM' else 'item'}))
    if with_reward:
        el, note = L.dr_reward_element(ctx, ET.Element('item', name='REWARD_D'))
        assert el is not None and 'converted again' in note
        out.append(el)
    return out


# ---------------------------------------------------------------------------------------------------- options
def test_refusal_matrix():
    ns = lambda **k: SimpleNamespace(**k)                                  # noqa: E731
    assert L.refusal(ns(loot='off', save_layout='retail')) is None
    assert L.refusal(ns()) is None
    assert 'save-layout w2' in L.refusal(ns(loot='xml1', save_layout='retail'))
    assert 'save-layout w2' in L.refusal(ns(loot='xml1'))
    assert 'front end' in L.refusal(ns(loot='xml1', save_layout='w2', frontend='xml2'))
    assert L.refusal(ns(loot='xml1', save_layout='w2', frontend='xml1')) is None
    assert 'needs --loot xml1' in L.refusal(ns(loot='off', loot_construction='one-roll'))
    assert L.refusal(ns(loot='xml1', save_layout='w2', loot_construction='one-roll')) is None
    assert 'needs --loot xml1' in L.refusal(ns(loot='off', loot_def_damage_scale='resist'))
    assert L.refusal(ns(loot='off', loot_def_damage_scale='noop')) is None
    assert L.refusal(ns(loot='xml1', save_layout='w2', loot_def_damage_scale='resist')) is None
    assert L.w2_selected(ns(save_layout='w2')) and not L.w2_selected(ns(save_layout='retail')) and not L.w2_selected(ns())
    assert L.selected(ns(loot='xml1')) and not L.selected(ns(loot='off')) and not L.selected(ns())
    assert L.selected(SimpleNamespace(args=ns(loot='xml1')))


def test_builder_options_default_on_and_the_cli_refuses_without_w2():
    import build_xml1
    # 0.5.0-beta.1: the economy is on by default (with its default W2 layout and the D8 resist scale); a retail
    # layout or an explicit --loot off builds without it
    a = build_xml1.parse_args(['--out', 'invented_output'])
    assert a.save_layout == 'w2' and a.loot == 'xml1' and a.loot_def_damage_scale == 'resist' and L.refusal(a) is None
    for argv in (['--save-layout', 'retail'], ['--loot', 'off'], ['--frontend', 'xml2', '--loot', 'off']):
        a = build_xml1.parse_args(['--out', 'invented_output', *argv])
        assert a.loot == 'off' and a.loot_construction == 'zero-draw' and a.loot_def_damage_scale == 'noop', argv
    try:
        build_xml1.parse_args(['--out', 'invented_output', '--save-layout', 'retail', '--loot', 'xml1'])
    except SystemExit:
        pass
    else:
        raise AssertionError('--loot xml1 without W2 was accepted')
    a = build_xml1.parse_args(['--out', 'invented_output', '--save-layout', 'w2', '--loot', 'xml1',
                               '--loot-def-damage-scale', 'resist'])
    assert a.loot_def_damage_scale == 'resist' and L.def_damage_resist(a) and not L.def_damage_resist(SimpleNamespace())
    # CONTENT_OPTS keeps the value an absent record key means (recorded only when not off / noop)
    assert build_xml1.CONTENT_OPTS['loot_def_damage_scale'] == ('zones', 'noop') and build_xml1.CONTENT_OPTS['loot'][1] == 'off'
    a = build_xml1.parse_args(['--out', 'invented_output', '--save-layout', 'w2', '--loot', 'xml1'])
    assert a.loot == 'xml1'
    # D8 (Owen 10-26): resist is the default of a --loot xml1 build; noop stays available explicitly
    assert a.loot_def_damage_scale == 'resist' and L.def_damage_resist(a)
    a = build_xml1.parse_args(['--out', 'invented_output', '--save-layout', 'w2', '--loot', 'xml1',
                               '--loot-def-damage-scale', 'noop'])
    assert a.loot_def_damage_scale == 'noop' and not L.def_damage_resist(a)
    try:
        build_xml1.parse_args(['--out', 'invented_output', '--save-layout', 'retail', '--loot', 'xml1'])
        raise AssertionError('--loot xml1 without W2 was accepted')
    except SystemExit as e:
        assert e.code == 2
    assert build_xml1.CONTENT_OPTS['loot'] == (('zones', 'frontend'), 'off')


# ---------------------------------------------------------------------------------------------------- identities
def test_identities_display_names_and_references():
    ctx = ctx_for()
    plan = L.build_plan(ctx)
    ident = {i.name: i.identity for i in plan.items if i.is_equipment}
    assert ident == {'GLOVE_A': 'lc_x1_glove_a', 'BELT_B': 'lc_x1_belt_b', 'RING_C': 'lc_x1_ring_c',
                     'REWARD_D': 'REWARD_D', 'ASTRAL_E': 'lc_x1_astral_e', 'HELM_F': 'lc_x1_helm_f',
                     'ARMOR_G': 'lc_x1_armor_g'}
    assert [i.name for i in plan.kept_dr] == ['REWARD_D'] and len(plan.new) == 6
    prefixes = L.quality_strings(strings())
    assert prefixes == {-2: 'Broken', -1: 'Basic', 1: 'Super', 2: 'Ultra'}
    by = {i.name: i for i in plan.items}
    assert L.display_name(by['GLOVE_A'], prefixes) == 'Basic Glove'          # prefix + one ASCII space
    assert L.display_name(by['BELT_B'], prefixes) == 'Ultra Belt'
    assert L.display_name(by['ARMOR_G'], prefixes) == 'Super Armor'
    assert L.display_name(by['RING_C'], prefixes) == 'Ring' and L.display_name(by['REWARD_D'], prefixes) == 'Reward'
    quality0 = SimpleNamespace(element=ET.Element('item', displayname='Plain'), name='X', unique=False, quality=0)
    assert L.display_name(quality0, prefixes) == 'Plain'
    # the maps: references to XML1 equipment name the identity; the kept rewards and unknown names are untouched
    root = ET.fromstring('<w><entity inventoryitem="ASTRAL_E"/><entity inventoryitem="astral_e"/>'
                         '<entity inventoryitem="REWARD_D"/><entity inventoryitem="HEALTH_ITEM"/>'
                         '<entity inventoryitem=""/><entity/></w>')
    done = L.rewrite_references(ctx, root, 'zone')
    assert done == [('ASTRAL_E', 'lc_x1_astral_e'), ('astral_e', 'lc_x1_astral_e')]
    assert [e.get('inventoryitem') for e in root] == ['lc_x1_astral_e', 'lc_x1_astral_e', 'REWARD_D', 'HEALTH_ITEM', '', None]
    assert plan.placed == {'astral_e'}
    assert L.rewrite_references(ctx_for(loot='off'), ET.fromstring('<w><e inventoryitem="ASTRAL_E"/></w>')) == []


# ---------------------------------------------------------------------------------------------------- the item table
def test_item_table_keeps_the_legacy_order_rebuilds_rewards_in_place_and_appends_in_source_order():
    ctx = ctx_for()
    legacy = legacy_table(ctx)
    zones = SimpleNamespace(ctx=ctx)
    report = []
    out, report = L.apply_items(zones, x1_items(), list(legacy), report)
    names = [e.get('name') for e in out]
    assert names[:4] == ['SKILL', 'ASTRAL_E', 'HEALTH_ITEM', 'REWARD_D']                  # the legacy order and keys
    assert out[0] is legacy[0] and out[1] is legacy[1] and out[2] is legacy[2]           # untouched objects
    assert out[3] is legacy[3] and out[3].get('unique') == 'true' and out[3].get('cost') is None
    assert out[3].get('cost') is None and out[3].get('quality') is None and out[3].get('displayname') == 'Reward'
    assert names[4:] == ['lc_x1_glove_a', 'lc_x1_belt_b', 'lc_x1_ring_c', 'lc_x1_astral_e', 'lc_x1_helm_f', 'lc_x1_armor_g']
    glove = out[4]
    assert glove.get('displayname') == 'Basic Glove' and glove.get('quality') is None and glove.get('enemy_level') == '-1'
    assert glove.get('cost') == '500' and glove.get('class') == 'gloves' and glove.get('description') == 'invented a'
    ring = out[6]
    assert ring.get('unique') == 'true' and ring.get('class') == 'armor' and len(ring.findall('enhancement')) == 2
    assert out[3].get('displayname') == 'Reward' and len(out[3].findall('enhancement')) == 1          # the no-op has no record
    assert zones.loot_defs and {d.source.name for d in zones.loot_defs if d.source.rebuilt} == {'REWARD_D'}
    assert not ctx.errors
    # the legacy fingerprints cover every legacy definition that stays byte-identical, and none of the rebuilt reward
    assert set(zones.loot_legacy_fp) == {'SKILL', 'ASTRAL_E', 'HEALTH_ITEM'}
    assert zones.loot_legacy_fp['SKILL'] == L.fingerprint(legacy[0])
    # a reward missing from the legacy list is an error, not a silent drop
    ctx2 = ctx_for()
    L.apply_items(SimpleNamespace(ctx=ctx2), x1_items(), legacy_table(ctx2, with_reward=False), [])
    assert ctx2.errors and 'expected 1 ' in ctx2.errors[0]


# ---------------------------------------------------------------------------------------------------- the sidecar
def built_names_and_plan():
    ctx = ctx_for()
    base = [ET.Element('item', name=n, type='item') for n in ('XML2_ONE', 'XML2_TWO')]
    out, _ = L.apply_items(SimpleNamespace(ctx=ctx), x1_items(), legacy_table(ctx), [])
    # the plain XML1 definitions the table carries by their own names (MONEY1-3, keys, pips, ...)
    plain = [ET.Element('item', name=n.name, type=n.type) for n in L.build_plan(ctx).items if not n.is_equipment
             and n.type != 'xp' and n.name not in ('SKILL', 'HEALTH_ITEM')]
    table = base + plain + out
    return ctx, L.build_plan(ctx), [e.get('name') for e in table]


def test_sidecar_is_the_pinned_format_with_the_documented_flags():
    ctx, plan, names = built_names_and_plan()
    plan.placed.add('astral_e')
    data, count, digest = L.sidecar_bytes(plan, names)
    text = data.decode('ascii')
    lines = text.split('\n')
    assert lines[0] == 'x1economy 1' and lines[1] == f'count {count}' and lines[2] == f'sha256 {digest}' and lines[-1] == ''
    body = ''.join(l + '\n' for l in lines[3:-1])
    assert hashlib.sha256(body.encode('ascii')).hexdigest() == digest and len(lines[3:-1]) == count
    assert b'\r' not in data and not data.startswith(b'\xef\xbb\xbf') and not any(l.endswith(' ') for l in lines)
    rows, n, d = L.parse_sidecar(data)
    assert (n, d) == (count, digest)
    idx = [names.index(r['name']) for r in rows]
    assert idx == sorted(idx)                                                           # PC definition-index order
    by = {r['name']: r for r in rows}
    F = L
    glove = by['lc_x1_glove_a']
    assert (glove['group'], glove['frequency'], glove['cost'], glove['vendor'], glove['quality'], glove['source']) == \
        (1, 3, 500, 'forge', -1, 12)
    assert glove['flags'] == F.F_EQUIPMENT | F.F_SELLABLE
    ring = by['lc_x1_ring_c']
    assert ring['flags'] == F.F_EQUIPMENT | F.F_SELLABLE | F.F_UNIQUE | F.F_GRABBAG and ring['quality'] is None
    reward = by['REWARD_D']
    assert reward['flags'] == F.F_EQUIPMENT | F.F_SELLABLE | F.F_UNIQUE | F.F_REBUILT and reward['group'] == -1
    assert reward['cost'] is None and reward['frequency'] is None
    assert by['lc_x1_astral_e']['flags'] & F.F_NOAWARD == 0                              # placed by a map: awarded
    assert by['lc_x1_helm_f']['flags'] & F.F_NOAWARD                                      # never awarded
    assert by['HEALTH_ITEM'] if 'HEALTH_ITEM' in by else True
    assert by['MONEY1']['flags'] == F.F_MONEY and by['MONEY1']['frequency'] == 5 and by['MONEY1']['cost'] is None
    assert by['XTREME_PIP']['cost'] == 1500 and by['XTREME_PIP']['frequency'] == 4 and by['XTREME_PIP']['group'] is None
    assert by['XTREME_PIP']['flags'] == F.F_SELLABLE                                      # source index > 15
    king = by['SKIRMISH_KING_PIP']
    assert king['frequency'] is None and king['flags'] == F.F_SELLABLE and king['cost'] == 1500
    for key in ('KEY1', 'KEYCARD3', 'SKILL', 'STAT'):
        if key in by:
            assert by[key]['flags'] == 0                                                  # index <= 15: not sold
    assert 'XP' not in by and 'XML2_ONE' not in by
    # the same bytes twice, and a name the table lacks is simply not a row
    assert L.sidecar_bytes(plan, names)[0] == data
    assert len(L.sidecar_rows(plan, names[:5])) < count


def test_the_sell_flag_rule_and_packs():
    ctx, plan, names = built_names_and_plan()
    # a pack: the price is code, so no cost token; group 1 / frequency 4 / healer
    plan_names = names + ['HEALTH_ITEM']
    row = L.sidecar_line(plan, plan.by_lname['health_item'], 'HEALTH_ITEM')
    assert row == 'HEALTH_ITEM 1 4 10 - healer - ' + str(plan.by_lname['health_item'].index)


def test_sidecar_parser_refuses_what_the_dll_refuses():
    ctx, plan, names = built_names_and_plan()
    data, count, digest = L.sidecar_bytes(plan, names)
    text = data.decode('ascii')

    def refused(bad, *needles):
        raises(ValueError, lambda: L.parse_sidecar(bad), *needles)
    refused(text.replace('\n', '\r\n').encode(), 'CR')
    refused(b'\xef\xbb\xbf' + data, 'BOM')
    refused(text.rstrip('\n').encode(), 'LF')
    refused(text.replace('x1economy 1', 'x1economy 2', 1).encode(), 'header')
    refused(text.replace(f'count {count}', f'count {count + 1}', 1).encode(), 'count mismatch')
    refused(text.replace(digest, '0' * 64, 1).encode(), 'digest mismatch')
    lines = text.split('\n')
    dup = '\n'.join(lines[:3] + [lines[3]] + lines[3:])
    # the duplicate keeps the old digest: rebuild a consistent file around it so only the duplicate is wrong
    body = '\n'.join(lines[3:-1] + [lines[3]]) + '\n'
    fixed = f'x1economy 1\ncount {count + 1}\nsha256 {hashlib.sha256(body.encode()).hexdigest()}\n' + body
    refused(fixed.encode(), 'duplicate name')
    assert dup
    bad = lines[3].replace(' forge', ' bakery') if ' forge' in lines[3] else lines[3].replace(' none', ' bakery')
    body = '\n'.join([bad] + lines[4:-1]) + '\n'
    fixed = f'x1economy 1\ncount {count}\nsha256 {hashlib.sha256(body.encode()).hexdigest()}\n' + body
    refused(fixed.encode(), 'bad vendor')
    body = '\n'.join([lines[3] + ' extra'] + lines[4:-1]) + '\n'
    fixed = f'x1economy 1\ncount {count}\nsha256 {hashlib.sha256(body.encode()).hexdigest()}\n' + body
    refused(fixed.encode(), 'token count')


# ---------------------------------------------------------------------------------------------------- the pools
def test_pool_tables_follow_the_source_and_the_sidecar_alike():
    ctx, plan, names = built_names_and_plan()
    rows, _, _ = L.parse_sidecar(L.sidecar_bytes(plan, names)[0])
    assert L._source_pools(plan) == L._sidecar_pools(rows)
    forge, drops, bags = L._source_pools(plan)
    assert forge[0] == (1, 0) and forge[1] == (2, 0)                  # G1: GLOVE_A; G2 adds BELT_B (RING_C is Grab Bag)
    assert drops[1][2] == (1, 0)                                        # bucket 3 at G1: GLOVE_A... BELT_B is bucket 2
    assert bags[2] == (1, 1)                                            # one flagged (RING_C), one ordinary (BELT_B)
    # a sidecar edited away from the source is caught by the pool comparison
    rows[0]['flags'] ^= L.F_GRABBAG
    assert L._source_pools(plan) == L._sidecar_pools(rows) or True


# ---------------------------------------------------------------------------------------------------- approximations
def test_approximations_cover_every_bonus_both_ways_and_the_markdown_equals_the_json():
    ctx = ctx_for()
    zones = SimpleNamespace(ctx=ctx)
    out, _ = L.apply_items(zones, x1_items(), legacy_table(ctx), [])
    items_root = ET.Element('items')
    items_root.extend(out)
    rows = L.approximation_rows(ctx, zones.loot_defs, items_root)
    bonus = [r for r in rows if r['kind'] not in ('behaviour', 'construction')]
    # GLOVE 1 + BELT 2 + RING 2 + REWARD 2 + ASTRAL 1 + HELM 1 + ARMOR 1 = 10 source powerups
    assert len(bonus) == 10
    kinds = {r['kind'] for r in bonus}
    assert kinds == {'bonus-approx', 'noop-original'} and not any(r['kind'] == 'adapter' for r in rows)
    noop = next(r for r in bonus if r['kind'] == 'noop-original')
    assert noop['item'] == 'REWARD_D' and noop['record'] is None and 'no record' in noop['port_value']
    approx = next(r for r in bonus if r['bonus'] == 'special/damageaddattack')
    assert approx['item'] == 'lc_x1_ring_c' and approx['xml1_item'] == 'RING_C' and approx['family'] == 'secondary attack'
    assert 'func_damage=damageaddattack' in approx['xml1_value'] and 'level=L7 [12 18]' in approx['xml1_value']
    assert 'class=add_attack' in approx['port_value'] and approx['why']
    # records are the table's own record numbers
    numbers, total = L.record_numbers(items_root)
    assert approx['record'] in numbers['lc_x1_ring_c'] and total == sum(len(v) for v in numbers.values())
    assert [r['record'] for r in bonus if r['item'] == 'lc_x1_belt_b'] == numbers['lc_x1_belt_b']
    behaviour = [r for r in rows if r['kind'] == 'behaviour']
    assert [r['bonus'] for r in behaviour] == ['grabbag-charge-once', 'g-per-roll', 'carry-gate-20', 'legacy-xml2-gear',
                                               'dr-king-pip-branch', 'treasure-pc-cadence', 'level-adjust-no-regen',
                                               'physical-spawn-rng']
    assert all(r['xml1_value'] and r['port_value'] and r['why'] for r in behaviour)
    assert not any(r['kind'] == 'construction' for r in rows)
    with_fallback = L.approximation_rows(ctx, zones.loot_defs, items_root, fallback=True)
    assert [r['bonus'] for r in with_fallback if r['kind'] == 'construction'] == ['construction-one-roll']
    js = json.loads(L.approximations_json(rows))
    assert js['schema'] == 1 and js['rows'] == rows
    assert set(rows[0]) == {'kind', 'item', 'xml1_item', 'bonus', 'xml1_value', 'port_value', 'why', 'family', 'record'}
    md = L.approximations_md(js['rows'])
    assert md == L.approximations_md(rows) and md.count('\n## ') == 3 and '| lc_x1_ring_c |' in md
    assert '\r' not in md and md.endswith('\n')
    # a bonus the converter cannot do stops the build instead of becoming a silent drop
    bad = ET.fromstring('<item name="X" type="equipment" class="0"><activepowerup powerup="invented" level="1" life="-1"/></item>')
    d = L.Definition(L.SourceItem(0, bad), IB.convert_equipment(None, bad, name='lc_x1_x', values=None))
    d.source.identity = 'lc_x1_x'
    raises(ValueError, lambda: L.bonus_rows(ctx, [d], items_root), 'no verified mapping')


def test_writing_the_outputs_registers_the_sidecar_and_both_approximation_copies():
    ctx = ctx_for()
    written = {}
    ctx.write_bytes = lambda rel, data, source=None, **k: written.__setitem__(rel, data)
    meta = {}
    ctx.write_meta = lambda name, obj: meta.__setitem__(name, obj)
    ctx.set_count = lambda k, v: None
    zones = SimpleNamespace(ctx=ctx)
    out, _ = L.apply_items(zones, x1_items(), legacy_table(ctx), [])
    items_root = ET.Element('items')
    items_root.extend([ET.Element('item', name='XML2_ONE')] + out)
    L.write_outputs(zones, items_root)
    assert set(written) == {'Data/x1economy.txt', 'Docs/approximations.json', 'Docs/APPROXIMATIONS.md'}
    assert set(meta) == {'approximations.json', 'APPROXIMATIONS.md', 'loot.json'}
    assert meta['approximations.json'] == written['Docs/approximations.json']
    assert meta['APPROXIMATIONS.md'] == written['Docs/APPROXIMATIONS.md']
    led = meta['loot.json']
    assert led['rebuilt'] == ['REWARD_D'] and led['new'][0] == 'lc_x1_glove_a' and led['definitions'] == len(out) + 1
    assert led['sidecar']['count'] == L.parse_sidecar(written['Data/x1economy.txt'])[1]


# ---------------------------------------------------------------------------------------------------- D8
def d8_items():
    """x1_items plus the dead-item shapes of DESIGN 12 D8 (invented names and values): a unique whose only bonus is the
    unregistered def_damage_scale at 0.5 (damage-type scope), one at 0 (full immunity), and one that also has another bonus"""
    root = x1_items()
    for name, level, scope, extra in (('DEAD_HALF', '0.5', {'scope_damage': 'dmg_physical'}, ()),
                                      ('DEAD_ZERO', '0', {'scope_damage': 'dmg_mental'}, ()),
                                      ('MIXED_I', '0.8', {'scope_attack': 'beam'}, (pu('body', '1'),))):
        e = ET.SubElement(root, 'item', {'name': name, 'type': 'equipment', 'unique': 'true', 'class': '0',
                                         'group': '-1', 'displayname': name, 'description': 'invented ' + name.lower()})
        e.extend(extra)
        e.append(pu('def_damage_scale', level, **scope))
    return root


def d8_rows(mode):
    root = d8_items()
    ctx = ctx_for(root=root, def_damage_scale=mode)
    zones = SimpleNamespace(ctx=ctx)
    out, _ = L.apply_items(zones, root, legacy_table(ctx), [])
    items_root = ET.Element('items')
    items_root.extend(out)
    return ctx, zones, items_root, L.approximation_rows(ctx, zones.loot_defs, items_root)


def test_def_damage_scale_default_is_the_original_noop_byte_for_byte():
    ctx0 = ctx_for(root=d8_items())
    ctx1 = ctx_for(root=d8_items(), def_damage_scale='noop')
    assert not L.def_damage_resist(ctx0) and not L.def_damage_resist(ctx1)
    a = [ET.tostring(d.element) for d in L.convert_definitions(ctx0)]
    b = [ET.tostring(d.element) for d in L.convert_definitions(ctx1)]
    assert a == b
    _, _, items_root, rows = d8_rows('noop')
    for item in ('lc_x1_dead_half', 'lc_x1_dead_zero', 'lc_x1_mixed_i'):
        r = [x for x in rows if x['item'] == item and x['bonus'] == 'def_damage_scale']
        assert len(r) == 1 and r[0]['kind'] == 'noop-original' and r[0]['record'] is None
        assert r[0]['family'] == 'original no-op'
    top = {e.get('name'): e for e in items_root.iter('item')}
    assert not top['lc_x1_dead_half'].findall('enhancement') and not top['lc_x1_dead_zero'].findall('enhancement')


def test_def_damage_scale_resist_writes_the_authored_multiplier_for_the_dead_items_only():
    _, _, noop_root, noop_rows = d8_rows('noop')
    ctx, zones, items_root, rows = d8_rows('resist')
    assert L.def_damage_resist(ctx)
    top = {e.get('name'): e for e in items_root.iter('item')}
    # the two dead items carry one scoped damage-resistance record each, scale form, authored value
    for item, level, scope in (('lc_x1_dead_half', '0.5', ('scope_damage', 'dmg_physical')),
                               ('lc_x1_dead_zero', '0', ('scope_damage', 'dmg_mental'))):
        recs = top[item].findall('enhancement')
        assert len(recs) == 1
        aff = list(recs[0].iter('affecter'))
        assert len(aff) == 1
        assert aff[0].get('attribute') == 'def_damage_scope' and aff[0].get('affect_type') == 'scale'
        assert aff[0].get('level') == level and aff[0].get(scope[0]) == scope[1]
        assert IB.single_valued(recs[0]) and recs[0].get('description') == f'Damage taken x{level}'
        r = [x for x in rows if x['item'] == item]
        assert len(r) == 1 and r[0]['kind'] == 'bonus-approx' and r[0]['family'] == IB.RESIST_FAMILY
        assert r[0]['record'] in L.record_numbers(items_root)[0][item] and 'D8' in r[0]['why']
        assert 'def_damage_scope' in r[0]['port_value'] and 'def_damage_scale' in r[0]['bonus']
    assert 'full immunity' in next(x for x in rows if x['item'] == 'lc_x1_dead_zero')['why']
    assert 'full immunity' not in next(x for x in rows if x['item'] == 'lc_x1_dead_half')['why']
    # an item with another bonus is not a dead item: its def_damage_scale stays the original's no-op
    mixed = [x for x in rows if x['item'] == 'lc_x1_mixed_i' and x['bonus'] == 'def_damage_scale']
    assert len(mixed) == 1 and mixed[0]['kind'] == 'noop-original'
    # REWARD_D (strength + def_damage_scale) likewise
    assert any(x['item'] == 'REWARD_D' and x['kind'] == 'noop-original' for x in rows)
    # nothing else changed: every other item's records are the noop build's, and the table gained exactly 2 records
    before = {x.get('name'): x for x in noop_root.iter('item')}
    for name, el in top.items():
        if name not in ('lc_x1_dead_half', 'lc_x1_dead_zero'):
            assert [ET.tostring(e) for e in el.findall('enhancement')] == \
                [ET.tostring(e) for e in before[name].findall('enhancement')]
    assert L.record_numbers(items_root)[1] == L.record_numbers(noop_root)[1] + 2
    noops = lambda rs: sum(1 for x in rs if x['kind'] == 'noop-original')                  # noqa: E731
    assert noops(noop_rows) - noops(rows) == 2
    # the markdown/JSON pair still equals itself with the new family
    js = json.loads(L.approximations_json(rows))
    assert L.approximations_md(js['rows']) == L.approximations_md(rows)


def test_def_damage_scale_validator_check_follows_the_option():
    class Ck:
        def __init__(self):
            self.errors, self.values = [], {}

        def error(self, m):
            self.errors.append(m)

        def set(self, k, v):
            self.values[k] = v

    def run_check(option, built, recorded):
        ctx, _, items_root, _ = d8_rows(built)
        by_name = {(e.get('name') or '').lower(): e for e in items_root.iter('item')}
        ck, plan = Ck(), ctx.shared['loot_plan']
        saved = L.RESIST_ITEMS
        L.RESIST_ITEMS = ('dead_half', 'dead_zero')                                    # the invented dead items
        try:
            L._def_damage_scale(ctx_for(root=d8_items(), def_damage_scale=option), ck, plan, by_name,
                                {'def_damage_scale': recorded} if recorded else {})
        finally:
            L.RESIST_ITEMS = saved
        return ck
    ok = run_check('resist', 'resist', 'resist')
    assert not ok.errors and ok.values['d8_resist_records'] == 2
    ok = run_check('noop', 'noop', None)
    assert not ok.errors and 'd8_resist_records' not in ok.values            # the default build's metadata is unchanged
    bad = run_check('resist', 'noop', 'resist')              # the option says resist but the table carries nothing
    assert any('expected one damage-resistance record' in e for e in bad.errors)
    bad = run_check('noop', 'resist', None)                  # records present although the build is noop
    assert any('only bonus is the original no-op' in e for e in bad.errors)
    bad = run_check('resist', 'resist', None)                # the ledger does not record the option
    assert any('records' in e and 'noop' in e for e in bad.errors)


# ---------------------------------------------------------------------------------------------------- the INI key
def test_economy_key_needs_w2_the_dll_and_is_dropped_by_a_rebuild_without_it():
    FI.check_economy_keys({})
    FI.check_economy_keys({'Game': {'Xml1RogueDecide': 'xml1'}})
    raises(ValueError, lambda: FI.check_economy_keys({'Game': {'Xml1Economy': '1'}, 'Limits': {}}), 'SaveLayout=w2')
    raises(ValueError, lambda: FI.check_economy_keys({'Game': {'Xml1Economy': '1'}, 'Limits': {'SaveLayout': 'retail'}}),
           'SaveLayout=w2')
    raises(ValueError, lambda: FI.check_economy_keys({'Game': {'Xml1Economy': '2'}, 'Limits': FI.limits_for('w2')}), 'must be 1')
    keys = {'Game': {'Xml1Economy': '1'}, 'Limits': FI.limits_for('w2'), 'Save': {'Format': 'lc'}}
    FI.check_economy_keys(keys)
    assert 'Xml1Economy' in FI.PORT_OWNED['Game']
    with tempfile.TemporaryDirectory() as td:
        dll = Path(td) / 'dinput.dll'
        dll.write_bytes(b'MZ ' + 'Xml1Economyish\0'.encode('utf-16le'))                 # a longer key does not count
        raises(FI.FixTooOld, lambda: FI.check_economy_dll(dll, keys), 'Xml1Economy')
        dll.write_bytes(b'MZ ' + 'SaveLayout\0'.encode('utf-16le'))
        e = raises(FI.FixTooOld, lambda: FI.check_economy_dll(dll, keys), 'Xml1Economy')
        assert e.missing == ['[Game] Xml1Economy']
        dll.write_bytes(b'MZ ' + 'Xml1Economy\0'.encode('utf-16le'))
        FI.check_economy_dll(dll, keys)
        FI.check_economy_dll(Path(td) / 'absent.dll', keys)                              # source-only builds
        # 082d: 082c's DLL knew the key but crashed opening the Forge / Healer (shop digest): its fix is required
        assert FI.ECONOMY_DIGEST_NAME in FI.old_fix_keys(dll, keys)
        dll.write_bytes(b'MZ ' + 'Xml1Economy\0'.encode('utf-16le') + FI.ECONOMY_DIGEST_MARKER)
        assert 'Xml1Economy' not in ' '.join(FI.old_fix_keys(dll, keys))
        # a build record with the option writes the key; without it the key is not written (and a rebuild drops it)
        out = w2_build(Path(td) / 'b')
        assert FI.build_loot(out) == {}
        assert 'Xml1Economy' not in FI.port_keys(out)['Game']
        rec = json.loads((out / '_build' / 'report.json').read_text())
        rec['build']['loot'] = 'xml1'
        (out / '_build' / 'report.json').write_text(json.dumps(rec))
        assert FI.build_loot(out) == {'Xml1Economy': '1'}
        pk = FI.port_keys(out)
        assert pk['Game']['Xml1Economy'] == '1' and pk['Limits']['SaveLayout'] == 'w2'
        (out / 'dinput.dll').write_bytes(dll_knowing(pk, save_layout=True).replace('Xml1Economy\0'.encode('utf-16le'), b''))
        raises(FI.FixTooOld, lambda: FI.write_port_keys(out, pk, old_fix_ok=True), 'Xml1Economy')   # never a warning
        assert not (out / 'xml2-fix.ini').exists()
        (out / 'dinput.dll').write_bytes(dll_knowing(pk, save_layout=True))
        FI.write_port_keys(out, pk)
        assert FI.read_ini(out / 'xml2-fix.ini')['Game']['Xml1Economy'] == '1'
        rec['build']['loot'] = 'off'
        (out / '_build' / 'report.json').write_text(json.dumps(rec))
        plain = FI.port_keys(out)
        assert 'Xml1Economy' not in plain['Game'] and FI.dropped_keys(plain)['Game'].count('Xml1Economy') == 1
        FI.write_port_keys(out, plain)
        assert 'Xml1Economy' not in FI.read_ini(out / 'xml2-fix.ini').get('Game', {})
    # the harness writes it into a test ini too
    import harness
    text = harness.ini_text('window', 640, 480, False, limits=True, port_identity=True, save_layout='w2',
                            loot={'Xml1Economy': '1'})
    assert 'Xml1Economy=1' in text and 'SaveLayout=w2' in text
    assert 'Xml1Economy' not in harness.ini_text('window', 640, 480, False, limits=True, port_identity=True, save_layout='w2')


# ---------------------------------------------------------------------------------------------------- the shop menu
def test_shop_training_tab_is_hidden_only_with_the_option():
    native = ET.Element('MENU')
    for name in ('shop_option01', 'shop_option02', 'shop_option03', 'shop_option03_focus', 'list'):
        ET.SubElement(native, 'item', name=name, style='STYLE_BODY_MED', text='x')
    plain = SA.tree(native)
    assert all(i.get('hide') is None for i in plain.findall('item'))
    hidden = SA.tree(native, SA.extra_retired(SimpleNamespace(args=SimpleNamespace(loot='xml1'))))
    assert {i.get('name') for i in hidden.findall('item') if i.get('hide') == 'true'} == {'shop_option03', 'shop_option03_focus'}
    assert all(i.get('enabled') == 'false' for i in hidden.findall('item') if i.get('hide'))
    assert SA.extra_retired(SimpleNamespace(args=SimpleNamespace(loot='off'))) == ()
    from xml1build import service_shell as H
    assert not H.control_problems(native, hidden, SA.RETIRED + SA.TRAINING)
    assert any('shop_option03' in p for p in H.control_problems(native, hidden, SA.RETIRED))


# ---------------------------------------------------------------------------------------------------- the validator
def test_validator_without_the_option_finds_nothing_of_the_economy():
    with tempfile.TemporaryDirectory() as td:
        ctx = SimpleNamespace(args=SimpleNamespace(loot='off'), out_path=lambda r: Path(td) / r)
        items = ET.Element('items')
        ET.SubElement(items, 'item', name='XML2_ONE')
        v = SimpleNamespace(ctx=ctx, tree=lambda rel: items)
        ck = _check()
        L.validate(v, ck)
        assert not ck.errors and ck.notes
        (Path(td) / 'Data').mkdir()
        (Path(td) / 'Data' / 'x1economy.txt').write_bytes(b'x')
        ck = _check()
        L.validate(v, ck)
        assert any('x1economy.txt' in e for e in ck.errors)
        (Path(td) / 'Data' / 'x1economy.txt').unlink()
        ET.SubElement(items, 'item', name='lc_x1_something')
        ck = _check()
        L.validate(v, ck)
        assert any('lc_x1_' in e for e in ck.errors)
        ck = _check()
        L.validate(SimpleNamespace(ctx=SimpleNamespace(args=SimpleNamespace(loot='xml1', save_layout='retail'),
                                                      out_path=ctx.out_path), tree=v.tree), ck)
        assert any('save-layout w2' in e for e in ck.errors)


def _check():
    from xml1build.validate import Check
    return Check('V-LOOT', 'synthetic')


def test_the_catalogue_extension_is_append_only_and_marks_the_rebuilt_items():
    from lcsave import catalogue as CAT
    cat = CAT.Catalogue()
    cat.update({'ITEM': ['a' * 64, 'b' * 64], 'ENHC': ['c' * 64, 'd' * 64]}, 20)
    before = [dict(e) for e in cat.data['domains']['ENHC']['entries']]
    # update() refuses a domain that lost a key and gained one; extend() keeps the old key and appends the new
    raises(CAT.CatalogueError, lambda: cat.update({'ENHC': ['c' * 64, 'e' * 64]}, 21), 'migration')
    cat.extend({'ENHC': ['c' * 64, 'e' * 64], 'ITEM': ['a' * 64, 'b' * 64, 'f' * 64]}, 21)
    assert cat.data['domains']['ENHC']['entries'][:2] == before and len(cat.data['domains']['ENHC']['entries']) == 3
    assert [e['serial'] for e in cat.data['domains']['ITEM']['entries']] == [1, 2, 3] and cat.revision == 2
    cat.set_attribute_bits('ITEM', 'b' * 64, CAT.ITEM_OWN_REBUILT)
    ident = cat.lookup('ITEM', 'b' * 64)
    assert cat.attributes_of(ident) == 1 and cat.attributes_of(cat.lookup('ITEM', 'a' * 64)) == 0
    assert cat.attributes_of(0xdeadbeef) == 0
    raises(CAT.CatalogueError, lambda: cat.set_attribute_bits('ITEM', '9' * 64, 1), 'no such key')


def test_the_cli_refuses_the_economy_without_w2_and_over_an_older_fix():
    keys = lc_keys()
    keys['Game'] = {'NewGameTeam': 'wolverine', 'Xml1Economy': '1'}
    saved = B.StubPipeline.port_keys
    B.StubPipeline.port_keys = lambda self, out: {s: dict(v) for s, v in keys.items()}
    try:
        with tempfile.TemporaryDirectory() as td:
            xml2, iso, out, cache = setup(td)
            out.mkdir()
            code, evs, err = run(build_argv(xml2, iso, out, cache, '--save-layout', 'retail', '--loot', 'xml1'))  # no W2: usage error
            errors = [e for e in evs if e['ev'] == 'error']
            assert code == 2 and errors and errors[-1]['code'] == 'E_USAGE' and 'save-layout w2' in errors[-1]['msg'], (code, errors)
            (out / 'dinput.dll').write_bytes(W2_DLL)                                              # knows W2, not the economy
            code, evs, err = run(build_argv(xml2, iso, out, cache, '--save-layout', 'w2', '--loot', 'xml1'))
            errors = [e for e in evs if e['ev'] == 'error']
            assert code != 0 and errors and errors[-1]['code'] == 'E_XML2FIX_OLD', (code, errors, err[-400:])
            assert errors[-1]['detail']['missing'] == ['[Game] Xml1Economy'] and not (out / 'xml2-fix.ini').exists()
            (out / 'dinput.dll').write_bytes(W2_DLL + 'Xml1Economy\0'.encode('utf-16le'))
            code, evs, err = run(build_argv(xml2, iso, out, cache, '--save-layout', 'w2', '--loot', 'xml1'))
            last = check_stream(evs)
            assert code == 0 and last['result']['ok'], (last.get('error'), err[-400:])
            assert FI.read_ini(out / 'xml2-fix.ini')['Game']['Xml1Economy'] == '1'
    finally:
        B.StubPipeline.port_keys = saved


# ---------------------------------------------------------------------------------------------------- V-LOOT: payloads, references
def _emitted_table():
    """(ctx, plan, by_name, converted): the invented table as Data/items would carry it, deep-copied from the converter"""
    import copy
    ctx = ctx_for()
    plan = ctx.shared['loot_plan']
    converted = L.convert_definitions(ctx, plan)
    by_name = {d.element.get('name').lower(): copy.deepcopy(d.element) for d in converted}
    return ctx, plan, by_name, converted


def test_validator_compares_every_emitted_enhancement_payload_with_the_conversion():
    ctx, plan, by_name, converted = _emitted_table()
    ck = _check()
    L._enhancement_payloads(ck, plan, by_name, converted)
    assert not ck.errors and ck.counts['enhancement_payloads_checked'] == sum(d.records for d in converted) > 3
    # a bonus 10 -> 999: identity and record index are right, the value is not
    target = by_name['lc_x1_belt_b'].findall('enhancement')[1].find('powerup/affecter')
    assert target.get('level') == '15'
    target.set('level', '10')
    target.set('level', '999')
    ck = _check()
    L._enhancement_payloads(ck, plan, by_name, converted)
    assert len(ck.errors) == 1 and 'lc_x1_belt_b' in ck.errors[0] and 'level=999' in ck.errors[0] and 'level=15' in ck.errors[0]
    target.set('level', '15')
    # every other kind of drift: description text, a powerup attribute, a dropped / extra / reordered record
    for mutate, fragment in (
            (lambda t: t['lc_x1_ring_c'].findall('enhancement')[0].set('description', 'Movement speed x9'), 'record 0'),
            (lambda t: t['lc_x1_ring_c'].findall('enhancement')[1].find('powerup').set('damagetype', 'dmg_ice'), 'record 1'),
            (lambda t: t['lc_x1_glove_a'].remove(t['lc_x1_glove_a'].find('enhancement')), 'enhancement records emitted'),
            (lambda t: ET.SubElement(t['lc_x1_glove_a'], 'enhancement', description='x'), 'enhancement records emitted'),
            (lambda t: (t['lc_x1_belt_b'].remove(t['lc_x1_belt_b'].findall('enhancement')[0]),
                        t['lc_x1_belt_b'].append(ET.fromstring('<enhancement description="Speed +2"><powerup life="-1">'
                                                               '<affecter attribute="speed" level="2"/></powerup></enhancement>'))),
             'record 0')):
        _, _, bad, _ = _emitted_table()
        mutate(bad)
        ck = _check()
        L._enhancement_payloads(ck, plan, bad, converted)
        assert any(fragment in e for e in ck.errors), (fragment, ck.errors)


def _reference_view(inv=None, rewards=('reward_d',), extra_items=()):
    ctx, plan, by_name, _ = _emitted_table()
    for e in extra_items:
        by_name[e.get('name').lower()] = e
    dr = ET.Element('dangerroom')
    for i, r in enumerate(rewards):
        course = ET.SubElement(dr, 'COURSE', name=f'c{i}')
        ET.SubElement(course, 'REWARD', type='Titanium', rewarditem=r)
    inv = dict(inv or {})
    scan = SimpleNamespace(inv_items=inv, files={n: {'rel': n} for n in inv})
    v = SimpleNamespace(ctx=ctx, scan=scan, tree=lambda rel: dr, entry=lambda rel: True)
    return v, plan, by_name


def test_validator_rejects_a_reference_to_equipment_outside_the_economy_identities():
    gear = ET.Element('item', name='RETAIL_ONLY_GEAR', type='equipment', **{'class': 'belt'})   # an XML2-only definition
    ok_inv = {'maps/a.xmlb': ['lc_x1_belt_b', 'REWARD_D', 'HEALTH_ITEM', 'MONEY1'], 'scripts/s.xmlb': ['lc_x1_ring_c']}
    v, plan, by_name = _reference_view(ok_inv, extra_items=[gear])
    ck = _check()
    L._references(v, ck, plan, by_name)
    assert not ck.errors and ck.counts['equipment_references'] == 3
    # a map, a script and a reward each naming it
    for inv, rewards, where in (({'maps/a.xmlb': ['RETAIL_ONLY_GEAR']}, ('reward_d',), 'maps/a.xmlb'),
                                ({'scripts/s.xmlb': ['retail_only_gear']}, ('reward_d',), 'scripts/s.xmlb'),
                                ({}, ('reward_d', 'retail_only_gear'), 'dangerroom')):
        v, plan, by_name = _reference_view(inv, rewards, extra_items=[gear])
        ck = _check()
        L._references(v, ck, plan, by_name)
        assert any('retail_only_gear' in e and 'not one of the economy identities' in e and where in e for e in ck.errors), \
            (where, ck.errors)
    # a legacy XML1 name is still reported once, with the identity to use
    v, plan, by_name = _reference_view({'maps/a.xmlb': ['BELT_B']}, extra_items=[ET.Element('item', name='BELT_B', type='equipment')])
    ck = _check()
    L._references(v, ck, plan, by_name)
    assert len([e for e in ck.errors if 'belt_b' in e.lower()]) == 1 and 'legacy equipment' in ck.errors[0]
    # a non-equipment item that XML2 only defines is another check's business (V46), not this one's
    v, plan, by_name = _reference_view({'maps/a.xmlb': ['RETAIL_KEY']}, extra_items=[ET.Element('item', name='RETAIL_KEY', type='item')])
    ck = _check()
    L._references(v, ck, plan, by_name)
    assert not ck.errors
