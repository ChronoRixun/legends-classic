"""Synthetic equipment only: units, scopes, loss accounting and the build freeze."""
import copy
import json
import contextlib
import io
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import equipment_report
import xmlb
from xml1build import equipment as E, frontend as F
from xml1build.common import encode_xmlb
from xml1build.heroes import Values


def context():
    return SimpleNamespace(x1_values=lambda: Values(ET.fromstring(
        '<values><value name="ARMOR_TEST" min="7"/><value name="DAMAGE_TEST" min="11" max="15"/></values>')))


def item(*bonuses):
    root = ET.Element('item', {'name': 'SYNTHETIC_RELIC', 'type': 'equipment'})
    for bonus in bonuses:
        root.append(ET.fromstring(bonus))
    return root


def converted(*bonuses):
    result = E.convert_equipment(context(), item(*bonuses))
    assert result.item is not None, result.note
    return result


def attrs(result):
    return [a.attrib for a in result.item.iter('affecter')]


def test_equipment_default_remains_frozen_and_opt_in_does_not_mutate():
    source = item('<activepowerup powerup="critical" level="3" life="-1"/>')
    before = ET.tostring(source)
    assert F.translate_equipment(context(), source)[0] is None
    assert F.translate_equipment(context(), source, expanded=True)[0] is not None
    assert F.translate_equipment(context(), source)[0] is None
    assert ET.tostring(source) == before
    # Existing reward shape, description and note stay on the old implementation.
    source = item('<activepowerup powerup="body" level="3"/>',
                  '<activepowerup powerup="drain_time" level="1.2" affect_type="scale"/>')
    legacy, note = F.translate_equipment(context(), source)
    assert [a.attrib for a in legacy.iter('affecter')] == [{'attribute': 'body', 'level': '12'}]
    assert 'dropped' in note and 'drain_time' in note


def test_equipment_critical_ranks_are_probability_points_not_ratings():
    result = converted('<activepowerup powerup="critical" level="3"/>',
                       '<activepowerup powerup="accuracy" level="2"/>')
    affs = list(result.item.iter('affecter'))
    assert affs[0].attrib == {'attribute': 'critical', 'level': '0.06'}
    assert affs[1].attrib == {'attribute': 'atk_critical', 'level': '0.04'}
    attacks = {s.get('scope_attack') for s in affs[1]}
    assert attacks == {'direct', 'blast', 'projectile', 'beam', 'crush', 'psionic'}
    assert not attacks.intersection({'punch', 'kick', 'throw'})
    assert all(b.status == 'approximate' and 'structure' in b.reason for b in result.bonuses)


def test_equipment_flat_defense_and_contextual_defense_are_distinct():
    result = converted('<activepowerup powerup="def_damage" level="ARMOR_TEST"/>',
                       '<activepowerup powerup="def_damage" level="0.7" affect_type="scale" '
                       'scope_attack="beam"/>')
    affs = attrs(result)
    assert affs[0] == {'attribute': 'def_damage', 'level': '7'}
    assert affs[1] == {'attribute': 'def_damage_scope', 'level': '0.7',
                       'affect_type': 'scale', 'scope_attack': 'beam'}
    # These produce 13 HP for a 20 HP hit, then 9.1 if the beam predicate matches;
    # mapping the flat term to a percentage would instead produce 18.6 HP.
    assert (20 - float(affs[0]['level'])) * float(affs[1]['level']) == 9.1


def test_equipment_value_ranges_and_scope_intersections_survive():
    result = converted('<activepowerup powerup="damage" level="DAMAGE_TEST" scope_race="robot">'
                       '<scope scope_attack="punch"/><scope scope_attack="kick"/></activepowerup>')
    aff = next(result.item.iter('affecter'))
    assert aff.get('level') == '11 15'
    assert aff.get('scope_race') == 'robot'
    assert [s.attrib for s in aff] == [{'scope_attack': 'punch'}, {'scope_attack': 'kick'}]
    assert len(result.item.findall('enhancement')) == 1
    assert result.bonuses[0].status == 'approximate'


def test_equipment_health_cap_and_timing_loss_are_explicit():
    result = converted('<activepowerup powerup="health_regen" level="3" user1="40"/>')
    assert attrs(result) == [{'attribute': 'health_regen', 'level': '3'},
                             {'attribute': 'health_regen', 'affect_type': 'max', 'level': '0.4'}]
    assert result.bonuses[0].status == 'approximate'
    assert '5/regen-scale' in result.note and 'minimum instead of maximum' in result.note


def test_equipment_multipliers_do_not_become_percent_additions():
    result = converted(*[f'<activepowerup powerup="{name}" level="{level}" affect_type="scale"/>'
                         for name, level in [('energy_regen', '1.4'), ('move', '1.3'),
                                              ('def_knockback', '0.6'), ('drain_time', '1.2'), ('xp', '1.1')]])
    assert [a['level'] for a in attrs(result)] == ['1.4', '1.3', '0.6', '1.2', '1.1']
    assert all(a['affect_type'] == 'scale' for a in attrs(result))
    assert result.coverage == 'full'
    assert 'direct XP awards' in result.note and '2.5' in result.note


def test_equipment_deflection_probability_and_reflection_are_not_confused():
    result = converted('<activepowerup powerup="deflect_damage" level="35" scope_attack="beam"/>')
    assert attrs(result)[0]['level'] == '0.35'
    assert attrs(result)[0]['attribute'] == 'deflect_damage'
    blocked = E.map_bonus(ET.fromstring('<activepowerup powerup="reflect_damage" level="20" user1="35"/>'))
    assert blocked.status == 'unsupported' and 'probability gate' in blocked.reason
    fixed = converted('<activepowerup powerup="reflect_damage" level="20" user1="100"/>')
    assert attrs(fixed) == [{'attribute': 'reflect_damage', 'level': '20'},
                            {'attribute': 'reflect_damage', 'affect_type': 'scale', 'level': '0'}]


def test_equipment_unknown_details_are_losses_instead_of_silent_unscoping():
    bad = [dict(powerup='critical', level='nan'), dict(powerup='critical', level='inf'),
           dict(powerup='critical', level='1e39'), dict(powerup='body', level='1e38'),
           dict(powerup='critical', level='-1'), dict(powerup='damage', level='UNKNOWN_TEST'),
           dict(powerup='damage', level='5 2'), dict(powerup='damage', level='3', scope_race='made_up_race'),
           dict(powerup='damage', level='3', scope_damage='made_up_damage'),
           dict(powerup='damage', level='3', mystery='true'), dict(powerup='move', level='1.2', life='5'),
           dict(powerup='def_stun', level='0'), dict(powerup='def_damage_scale', level='0.5'),
           dict(powerup='special', level='5', func_damage='DamageAddAttack'),
           dict(powerup='none', level='5', func_damage='DamageAddBleed')]
    for attrib in bad:
        bonus = E.map_bonus(ET.Element('activepowerup', attrib), context().x1_values())
        assert bonus.status == 'unsupported' and not bonus.enhancements, attrib


def test_equipment_attack_modifier_uses_source_minimum_and_reports_stage_change():
    result = converted('<activepowerup powerup="atk_damage" level="DAMAGE_TEST"/>',
                       '<activepowerup powerup="atk_damage_scale" level="1.2"/>',
                       '<activepowerup powerup="atk_knockback_scale" level="1.3"/>')
    assert attrs(result) == [{'attribute': 'damage', 'level': '11'},
                             {'attribute': 'damage', 'level': '1.2', 'affect_type': 'scale'},
                             {'attribute': 'atk_knockback_scale', 'level': '1.3'}]
    assert '132 vs 130' in result.note


def test_equipment_coverage_counts_bonuses_not_just_nonempty_items():
    root = ET.Element('items')
    full = item('<activepowerup powerup="critical" level="2"/>')
    partial = copy.deepcopy(full)
    partial.append(ET.fromstring('<activepowerup powerup="made_up_bonus" level="7"/>'))
    none = item('<activepowerup powerup="made_up_bonus" level="7"/>')
    root.extend([full, partial, none, ET.Element('item', {'type': 'money'})])
    before = ET.tostring(root)
    report = E.audit_equipment(context(), root)
    assert report['counts'] == {'full': 1, 'partial': 1, 'none': 1}
    assert report['total'] == 3 and report['legacy_converts'] == 0
    assert report['builds_changed'] is False
    assert ET.tostring(root) == before


def test_equipment_report_cli_reads_only_the_supplied_synthetic_inputs():
    inputs = {'items.xml': b'<items><item name="SYNTHETIC_RING" type="equipment">'
                          b'<activepowerup powerup="critical" level="2"/></item></items>',
              'values.xml': b'<values/>'}
    reads = []

    def read(path):
        reads.append(str(path))
        return inputs[str(path)]

    output = io.StringIO()
    with patch.object(Path, 'read_bytes', read), patch.object(Path, 'write_bytes') as write, \
            patch.object(Path, 'write_text') as write_text, contextlib.redirect_stdout(output):
        assert equipment_report.main(['--items', 'items.xml', '--values', 'values.xml', '--json']) == 0
        write.assert_not_called()
        write_text.assert_not_called()
    assert reads == ['items.xml', 'values.xml']
    result = json.loads(output.getvalue())
    assert result['counts'] == {'full': 1, 'partial': 0, 'none': 0}


def test_equipment_scope_and_paired_affecters_survive_binary_serialization():
    source = item('<activepowerup powerup="health_regen" level="3" user1="40"/>',
                  '<activepowerup powerup="deflect_damage" level="20">'
                  '<scope scope_attack="punch"/><scope scope_attack="kick"/></activepowerup>')
    source.set('class', '2')
    # Deliberately contradict the old name heuristic. The expanded path uses the
    # source slot; the existing build behavior remains unchanged.
    source.set('name', 'SYNTHETIC_BELT')
    result = E.convert_equipment(context(), source)
    # Use the build writer: XML2 searches attributes in sorted order. The bare
    # format encoder can round-trip an unsorted tree that crashes the game.
    restored = xmlb.decode(encode_xmlb(result.item))
    assert all(list(e.attrib) == sorted(e.attrib) for e in restored.iter())
    assert restored.get('class') == 'armor'
    assert len(restored.findall('enhancement')) == 2
    assert len(list(restored.iter('affecter'))) == 3
    aff = restored.findall('enhancement')[1].find('powerup/affecter')
    assert [s.get('scope_attack') for s in aff] == ['punch', 'kick']
    assert restored.find('enhancement/powerup').get('life') == '-1'
