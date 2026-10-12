"""Inline map entities use XML1 values, without rewriting zone names or ordinals."""
import collections
import types
import xml.etree.ElementTree as ET
from xml1build import npc_values as NV, zones as Z, validate as V


def _values():
    return ET.fromstring('<values><value name="L1" min="4" max="5"/>'
                         '<value name="L2" min="9" max="11"/>'
                         '<value name="L3" min="15" max="18"/>'
                         '<value name="M2" min="100" max="125"/>'
                         '<value name="K10" min="620" max="620"/></values>')


def _source(wrapper='world'):
    return ET.fromstring(f'<{wrapper}><entity name="world"/>'
                         '<entity name="toy_rock" explodedamage="L3" damage="L2" knockback="K10"/>'
                         '<entity name="toy_prop" explodedamage="L1" model="L1"/>'
                         '<entity name="toy_weapon" explodedamage="M2"/>'
                         '<entinst name="toy_instance" type="A1"/>'
                         f'</{wrapper}>')


def test_inline_zone_patch_resolves_values_without_reordering():
    root = _source()
    errors = []
    ctx = types.SimpleNamespace(read_x1_xml=lambda _: _values(), error=errors.append,
                                x1_path=lambda _: None, base_index=types.SimpleNamespace(find=lambda *a: None),
                                args=types.SimpleNamespace(xp_curve='xml2', frontend='xml2'))
    z = Z.Zones.__new__(Z.Zones)
    z.ctx, z.counts, z.music, z.pinned = ctx, collections.Counter(), {}, {}
    z.prov = types.SimpleNamespace(rewrite_data_tree=lambda *a: None, zone_script_ref=lambda *a: None)
    z._x1_xp_items = {}
    z.zone_script_texts = lambda *a: {}
    z.fix_links = lambda *a: None
    before = [(e.tag, e.get('name')) for e in root]
    z.mutate_zone('toy/room', 'maps/toy/room.xml', root, {})
    assert not errors
    assert [(e.tag, e.get('name')) for e in root] == before
    assert root[1].get('explodedamage') == '15'
    assert root[1].get('damage') == '9 11'
    assert root[1].get('knockback') == '620'
    assert root[2].get('explodedamage') == '4' and root[2].get('model') == 'L1'
    assert root[3].get('explodedamage') == '100'
    assert root[4].get('type') == 'A1'


def test_inline_resolver_handles_multiple_roots_unknown_codes_and_idempotence():
    errors = []
    ctx = types.SimpleNamespace(read_x1_xml=lambda _: _values(), error=errors.append)
    root = _source('xmlb_multiple_roots')
    NV.resolve_entity_codes(ctx, root, 'Maps/Toy/Room.eng')
    assert root[1].get('explodedamage') == '15'
    first = ET.tostring(root)
    NV.resolve_entity_codes(ctx, root, 'maps/toy/room.eng')
    assert ET.tostring(root) == first and not errors
    root[1].set('explodedamage', 'L999')
    NV.resolve_entity_codes(ctx, root, 'maps/toy/room.xml')
    assert len(errors) == 1 and 'L999' in errors[0]
    assert root[1].get('explodedamage') == 'L999'


def test_inline_v19_checks_localized_maps_and_skips_retail_and_instance_names():
    trees = {'maps/toy/room.xmlb': _source(), 'maps/toy/room.engb': _source('xmlb_multiple_roots'),
             'maps/toy/retail.xmlb': _source()}
    v = types.SimpleNamespace(idx=types.SimpleNamespace(under=lambda prefix: trees), tree=trees.get,
                              entry=lambda rel: None if 'retail' in rel else {'owner': 'zones'})
    ck = V.Check('V19', 'inline entity codes')
    NV.validate_inline_entity_codes(v, ck)
    assert ck.counts['inline_entity_value_codes_left'] == 5
    assert len(ck.errors) == 5  # identical localization findings deduplicated
    assert not any('A1' in msg or 'model=' in msg for msg in ck.errors)
    errors = []
    ctx = types.SimpleNamespace(read_x1_xml=lambda _: _values(), error=errors.append)
    for rel, root in trees.items():
        if 'retail' not in rel:
            NV.resolve_entity_codes(ctx, root, rel)
    fixed = V.Check('V19', 'inline entity codes')
    NV.validate_inline_entity_codes(v, fixed)
    assert not fixed.errors and fixed.counts['inline_entity_value_codes_left'] == 0




def test_inline_v19_rejects_scalar_explosion_ranges():
    root = ET.fromstring('<world><entity name="toy_bang" explodedamage="15 18"/></world>')
    v = types.SimpleNamespace(idx=types.SimpleNamespace(under=lambda _: ['maps/toy/room.xmlb']),
                              tree=lambda _: root, entry=lambda _: {'owner': 'zones'})
    ck = V.Check('V19', 'inline entity codes')
    NV.validate_inline_entity_codes(v, ck)
    assert len(ck.errors) == 1 and 'single minimum' in ck.errors[0]
