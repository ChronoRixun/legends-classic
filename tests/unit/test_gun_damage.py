"""XML1's gun damage draw in the builder (xml1build.weapons / npc_values) on made-up data - no game data.

XML1's weapon fire (default.xbe 0xbcc47-0xbcc99) rolls ONE integer draw between trunc(min x 0.7f) and
trunc(min x 1.3f) of the damage declaration's resolved MINIMUM (the parser stores only the minimum,
0xbc2ef-0xbc30d), and the entity parser reads explodedamage as one number (0x97940-0x97953). The builder's
weapon triggers must carry the draw's bounds and the entities the single minimum.
"""
import xml.etree.ElementTree as ET
from types import SimpleNamespace

from xml1build import heroes as H
from xml1build import npc_values as NV
from xml1build import weapons as W


def values():
    root = ET.Element('values')
    ET.SubElement(root, 'value', {'name': 'TZ5', 'min': '40', 'max': '52'})   # an invented code with a range
    ET.SubElement(root, 'value', {'name': 'TZ2', 'min': '12'})                 # single-valued invented code
    return H.Values(root)


ZAPPER = {'name': 'wp_toy_zapper', 'type': 'bullet', 'actorbolt': 'Bip01 R Hand', 'damage': 'TZ5',
          'range': '300', 'firesound': 'test/toy_bang', 'muzzlefx': 'test/toy_flash',
          'muzzleaccfx': 'test/toy_tracer', 'impactfx': 'test/toy_hit'}
LOBBER = {'name': 'wp_toy_lobber', 'type': 'projectile', 'damage': 'TZ5', 'projectileent': 'toy_blob',
          'projectilespeed': '250', 'firesound': 'test/toy_bloop'}
NUMBER_GUN = {'name': 'wp_toy_number', 'type': 'bullet', 'damage': '1000'}
TZ5_DRAW = '27 51'          # trunc(40 x 0.7f) .. trunc(40 x 1.3f)
NUMBER_DRAW = '699 1299'    # trunc(1000 x 0.7f) .. trunc(1000 x 1.3f)


def style(move='power_attack', shot=None):
    root = ET.Element('PowerStyle')
    m = ET.SubElement(root, 'FightMove', {'name': move, 'animenum': 'ea_power1'})
    ET.SubElement(m, 'trigger', {'name': 'stop', 'time': '0'})
    ET.SubElement(m, 'trigger', shot or {'name': 'weapon_fire', 'time': '0'})
    ET.SubElement(m, 'chain', {'action': 'idle', 'result': 'idle'})
    return root


def test_gun_draw_bounds_are_truncated_binary32_products_of_the_minimum():
    assert W.gun_damage_range(values(), 'TZ5') == TZ5_DRAW
    assert W.gun_damage_range(values(), '1000') == NUMBER_DRAW
    assert W.gun_damage_range(values(), 'TZ2') == '8 15'          # trunc(12 x 0.7f) .. trunc(12 x 1.3f)
    assert W.gun_damage_range(values(), 'NOPE') is None           # an unknown code: left for resolve_style to report
    assert W.gun_damage_range(values(), 'lots') is None           # not a number at all
    assert W.gun_damage_range(None, 'TZ5') is None


def test_apply_with_values_writes_the_draw_and_without_values_keeps_the_code():
    root = style()
    rep = W.apply(root, ZAPPER, values=values())
    beam = next(c for c in root.find('FightMove') if c.get('name') == 'beam')
    assert beam.get('damage') == TZ5_DRAW and rep['gun_damage_drawn'] == 1
    root = style()
    W.apply(root, ZAPPER)                                      # the old call: the code stands, resolved later
    beam = next(c for c in root.find('FightMove') if c.get('name') == 'beam')
    assert beam.get('damage') == 'TZ5'
    root = style()
    W.apply(root, LOBBER, values=values())                     # the projectile shot carries the draw too
    shot = next(c for c in root.find('FightMove') if c.get('name') == 'projectile')
    assert shot.get('damage') == TZ5_DRAW
    root = style()
    W.apply(root, NUMBER_GUN, values=values())                 # a literal number is a minimum of its own
    beam = next(c for c in root.find('FightMove') if c.get('name') == 'beam')
    assert beam.get('damage') == NUMBER_DRAW


def test_rewrite_weapon_events_with_values_writes_the_draw():
    root = ET.Element('PowerStyle')
    ET.SubElement(root, 'event', {'name': 'toy_pop', 'inherit': 'weapon_fire', 'weapon': 'wp_toy_zapper'})
    m = ET.SubElement(root, 'FightMove', {'name': 'power_attack', 'animenum': 'ea_power1', 'aitype': 'beam'})
    ET.SubElement(m, 'trigger', {'name': 'toy_pop', 'time': '0'})
    rep = W.rewrite_weapon_events(root, {'wp_toy_zapper': ZAPPER}, values=values())
    ev = root.find('event')
    assert ev.get('inherit') == 'beam' and ev.get('damage') == TZ5_DRAW and rep['gun_damage_drawn'] == 1


def test_collapse_single_value_entity_attrs_keeps_only_the_minimum():
    root = ET.fromstring('<entities><entity name="toy_bang" explodedamage="25 31" damage="25 31"/>'
                         '<entity name="toy_plain" explodedamage="25" damage="25 31"/>'
                         '<entity name="toy_odd" explodedamage="TZ5" damage="lots"/></entities>')
    NV.collapse_single_value_entity_attrs(root)
    by = {e.get('name'): e for e in root}
    assert by['toy_bang'].get('explodedamage') == '25' and by['toy_bang'].get('damage') == '25 31'
    assert by['toy_plain'].get('explodedamage') == '25'
    assert by['toy_odd'].get('explodedamage') == 'TZ5'          # a code / a non-range stays for other checks
    NV.collapse_single_value_entity_attrs(root)                  # idempotent
    assert by['toy_bang'].get('explodedamage') == '25'
    NV.collapse_single_value_entity_attrs(None)                  # tolerant


# ---- the validator (V45) on made-up built trees

def built_style(damage, as_event=False):
    if as_event:
        root = ET.Element('PowerStyle')
        ET.SubElement(root, 'event', {'name': 'toy_pop', 'inherit': 'beam', 'attacktype': 'beam',
                                      'damagescale': 'difficulty', 'damagelevel': '1', 'damage': damage})
        return root
    return style(shot={'name': 'beam', 'time': '0', 'attacktype': 'beam', 'damagescale': 'difficulty',
                       'damagelevel': '1', 'damage': damage})


def fake_v(style_rels, entity_rels, source_styles=None):
    x1 = {'data/values.xml': ET.Element('values'),
          'data/weapons/weapons.eng': ET.Element('weapons_list')}
    ET.SubElement(x1['data/values.xml'], 'value', {'name': 'TZ5', 'min': '40', 'max': '52'})
    w = ET.SubElement(x1['data/weapons/weapons.eng'], 'weapon', {'name': 'wp_toy_zapper'})
    w.set('type', 'bullet')
    w.set('damage', 'TZ5')
    x1.update(source_styles or {})
    trees = dict(style_rels)
    trees.update(entity_rels)
    return SimpleNamespace(
        ctx=SimpleNamespace(read_x1_xml=lambda rel: x1[rel], x1_path=lambda rel: rel if rel in x1 else None),
        idx=SimpleNamespace(under=lambda prefix: list(style_rels) if 'powerstyles' in prefix
                            else list(entity_rels)),
        entry=lambda rel: trees[rel],
        tree=lambda rel: trees[rel])


def check(v):
    errors, warnings, counts = [], [], {}
    ck = SimpleNamespace(error=errors.append, warn=warnings.append,
                         count=lambda k: counts.update({k: counts.get(k, 0) + 1}),
                         set=lambda k, val: counts.update({k: val}), note=lambda m: None)
    W.validate(v, ck)
    return errors, warnings, counts


def test_validator_accepts_the_draw_and_rejects_ranges_and_wrong_draws():
    good = {'data/powerstyles/x1_ps_toy_zapper.xmlb': built_style(TZ5_DRAW),
            'data/powerstyles/x1_ps_toy_agents.xmlb': built_style('34 64', as_event=True)}
    ents = {'data/entities/toy_ents.xmlb':
            ET.fromstring('<entities><entity name="toy_bang" explodedamage="15"/></entities>')}
    errors, warnings, counts = check(fake_v(good, ents))
    assert errors == [] and warnings == []
    assert counts['gun_variant_styles_checked'] == 1 and counts['gun_shot_triggers_checked'] == 2
    assert counts['entity_single_value_attrs_checked'] == 0

    bad = dict(good)
    bad['data/powerstyles/x1_ps_toy_zapper.xmlb'] = built_style('40 52')        # the old code range
    errors, _, _ = check(fake_v(bad, ents))
    assert any('not XML1' in e for e in errors)

    bad = dict(good)
    bad['data/powerstyles/x1_ps_toy_zapper.xmlb'] = built_style('34 64')        # another weapon's draw
    errors, _, _ = check(fake_v(bad, ents))
    assert any("'27 51' expected" in e for e in errors)

    bad = dict(good)
    bad['data/powerstyles/x1_ps_toy_agents.xmlb'] = built_style('40 52', as_event=True)
    errors, _, _ = check(fake_v(bad, ents))
    assert any('not XML1' in e for e in errors)

    bad_ents = {'data/entities/toy_ents.xmlb':
                ET.fromstring('<entities><entity name="toy_bang" explodedamage="15 18"/></entities>')}
    errors, _, counts = check(fake_v(good, bad_ents))
    assert any('explodedamage' in e and 'single minimum' in e for e in errors)
    assert counts['entity_single_value_attrs_checked'] == 1


def test_validator_rejects_added_gun_reaction_immunity_and_keeps_authored_priority():
    rel = 'data/powerstyles/x1_ps_example_toy_zapper.xmlb'
    source = style()
    built = built_style(TZ5_DRAW)
    v = fake_v({rel: built}, {}, {'data/powerstyles/ps_example.xml': source})
    errors, _, counts = check(v)
    assert errors == [] and counts['gun_priority_moves_checked'] == 1
    built.find('FightMove').set('priority', '5')
    assert any('weapon reaction priority' in e for e in check(v)[0])
    source.find('FightMove').set('Priority', '5')
    assert check(v)[0] == []
    built.find('FightMove').set('priority_override', '4')
    assert any('priority_override' in e for e in check(v)[0])
