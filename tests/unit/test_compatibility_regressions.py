"""Regressions for XML1 entity codes and per-weapon style-package contents (synthetic data)."""
import copy
import threading
import types
import xml.etree.ElementTree as ET
from unittest.mock import patch

from xml1build import characters as CH, zones as Z


def test_zone_entity_patch_preserves_character_value_resolution():
    source = ET.fromstring('<entities><entity name="test_shot" classname="projectileent" '
                           'damage="L3" knockback="K10" explodedamage="L4" model="effects/test_shot"/></entities>')
    values = ET.fromstring('<values><value name="L3" min="15" max="18"/>'
                           '<value name="K10" min="500" max="500"/><value name="L4" min="25" max="31"/></values>')
    ctx = types.SimpleNamespace(read_x1_xml=lambda _: copy.deepcopy(values), error=lambda msg: None)
    b = CH._Builder.__new__(CH._Builder)
    b.ctx, b.lock, b.x1_values, b.npc_codes = ctx, threading.RLock(), None, {}
    z = Z.Zones.__new__(Z.Zones)
    z.ctx = ctx
    z.prov = types.SimpleNamespace(rewrite_data_tree=lambda *args: None)
    character_tree, zone_tree = copy.deepcopy(source), copy.deepcopy(source)
    with patch.object(CH, '_rewrite_data_tree_fn', return_value=None):
        b._data_patch('data/entities/test_shot.xml')(character_tree)
    z._data_patch('data/entities/test_shot.xml')(zone_tree)
    # Zones compares its newly converted source with the earlier characters output. Different bytes
    # mean a forced overwrite, so both import paths must perform exactly the same conversion.
    assert character_tree[0].get('damage') == '15 18'
    assert character_tree[0].get('knockback') == '500'
    assert character_tree[0].get('explodedamage') == '25 31'
    assert ET.tostring(zone_tree) == ET.tostring(character_tree)


def _style_package_from_bundle(bundle):
    captured = {}
    ctx = types.SimpleNamespace(
        manifest={} if bundle is None else {'packages/generated/powerstyles/ps_test.fb': bundle},
        base_index={}, count=lambda *args: None, set_count=lambda *args: None,
        warn=lambda *args: None, defer=lambda *args: None)
    b = CH._Builder.__new__(CH._Builder)
    b.ctx = ctx
    b.styles_written = {('powerstyles', 'x1_ps_test_testgun'): 'data/powerstyles/ps_test.xml'}
    b.variant_base = {'x1_ps_test_testgun': 'ps_test'}
    b.detail = {'packages': [], 'notes': []}
    def build_pkg(entries, who):
        root = ET.Element('packagedef')
        for path, kind in entries:
            ET.SubElement(root, kind, {'filename': path.rsplit('.', 1)[0]})
        return root, set()
    def write_pkg(rel, root):
        captured[rel] = root
        return rel
    b.build_pkg, b.write_pkg = build_pkg, write_pkg
    b.style_packages()
    return captured['Packages/generated/powerstyles/x1_ps_test_testgun.PKGB']


def test_weapon_style_package_loads_its_variant_and_preserves_dependencies():
    root = _style_package_from_bundle([
        ['data/powerstyles/ps_test.xml', 'xml'],
        ['data/powerstyles/ps_helper.xml', 'fightstyle'],
        ['effects/test/flash.xml', 'effect']])
    entries = [(e.tag, e.get('filename')) for e in root]
    assert ('xml', 'data/powerstyles/x1_ps_test_testgun') in entries
    assert ('xml', 'data/powerstyles/ps_test') not in entries
    assert ('fightstyle', 'data/powerstyles/ps_helper') in entries
    assert ('effect', 'effects/test/flash') in entries


def test_weapon_style_package_without_bundle_also_loads_its_variant():
    root = _style_package_from_bundle(None)
    assert [(e.tag, e.get('filename')) for e in root] == [('xml', 'data/powerstyles/x1_ps_test_testgun')]


def test_entity_code_validator_checks_single_roots_and_ignores_retail():
    from xml1build import npc_values as NV, validate as V
    trees = {
        'data/entities/test.xmlb': ET.fromstring('<entity name="test" damage="L3" knockback="K10"/>'),
        'data/entities/test.engb': ET.fromstring('<entity name="test" damage="L3" knockback="K10"/>'),
        'data/entities/retail.xmlb': ET.fromstring('<entities><entity name="retail" damage="L3"/></entities>')}
    v = types.SimpleNamespace(idx=types.SimpleNamespace(under=lambda _: trees), tree=trees.get,
                              entry=lambda rel: None if 'retail' in rel else {'owner': 'zones'})
    ck = V.Check('test', 'entity codes')
    NV.validate_entity_codes(v, ck)
    assert len(ck.errors) == 2                       # localized twin is deduplicated
    assert ck.counts['entity_value_codes_left'] == 2
    for rel, tree in trees.items():
        if 'retail' not in rel:
            tree.set('damage', '15 18'); tree.set('knockback', '500')
    fixed = V.Check('test', 'entity codes')
    NV.validate_entity_codes(v, fixed)
    assert not fixed.errors


def test_style_package_validator_rejects_the_source_style_in_a_variant_package():
    from xml1build import validate as V
    rel = 'Packages/generated/powerstyles/x1_ps_test_testgun.PKGB'
    ck = V.Check('test', 'style target')
    V.Validator._v4_style_package_target(ck, rel, [('xml', 'data/powerstyles/ps_test')])
    assert len(ck.errors) == 1
    fixed = V.Check('test', 'style target')
    V.Validator._v4_style_package_target(fixed, rel, [('xml_resident', 'data/powerstyles/x1_ps_test_testgun')])
    assert not fixed.errors


def test_unknown_entity_value_is_a_build_error_and_nonentity_files_are_untouched():
    from xml1build import npc_values as NV
    errors = []
    ctx = types.SimpleNamespace(error=errors.append, read_x1_xml=lambda _: ET.Element('values'))
    root = ET.fromstring('<entity name="test" damage="L999"/>')
    NV.resolve_entity_codes(ctx, root, 'data/entities/test.xml')
    assert len(errors) == 1 and 'L999' in errors[0]
    errors.clear()
    assert NV.resolve_entity_codes(ctx, root, 'dialogs/test.xml') is None
    assert not errors


def test_bind_style_package_is_idempotent_and_handles_assets_only_bundles():
    from xml1build import weapons as W
    root = ET.fromstring('<packagedef><effect filename="test/flash"/></packagedef>')
    W.bind_style_package(root, 'ps_test', 'x1_ps_test_testgun')
    first = ET.tostring(root)
    W.bind_style_package(root, 'ps_test', 'x1_ps_test_testgun')
    assert ET.tostring(root) == first and len(root) == 2


def test_projectile_trigger_declares_projectile_attack_type():
    from xml1build import weapons as W
    weapon = {'type': 'projectile', 'projectileent': 'test_shot', 'entfile': 'test_entities',
              'projectilespeed': '400', 'damage': 'L3'}
    trigger = W.shot_triggers(weapon, '0.25')[0]
    # ce_atk_spawn_proj inherits the attack-data parser's punch default. The shared
    # projectile event only selects the spawn class; it does not set attacktype.
    assert trigger.get('attacktype') == 'projectile'
