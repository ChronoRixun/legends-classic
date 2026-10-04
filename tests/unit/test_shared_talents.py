"""SPEC 50: the first game's shared hero passives (critical / might / leadership /
flight) ship XML1's definitions in the engine's form, like toughness / mutantmastery / acrobatics already do
(xml1build.heroes SHARED_REAL_DEFS). XML1 <Talent> trees and descriptions are built in code with invented text -
no game data; only the engine's affecter attribute and talentvalue names appear.
"""
import xml.etree.ElementTree as ET

from xml1build import heroes as H


def values():
    return H.Values(ET.Element('values'))


def x1_talent(name, levels):
    """an XML1 shared_talents-style <Talent>: levels = [(description, [(require attr dict)], [(activepowerup attr dict)])]"""
    t = ET.Element('Talent', {'name': name, 'descname': name.title(),
                              'description': f'Synthetic stand-in for {name}.'})
    for desc, reqs, apus in levels:
        lv = ET.SubElement(t, 'level', {'description': desc} if desc else {})
        for r in reqs:
            ET.SubElement(lv, 'require', r)
        for a in apus:
            ET.SubElement(lv, 'activepowerup', a)
    return t


def affecters(level_el):
    return [(a.get('attribute'), a.get('level'), a.get('affect_type'))
            for p in level_el.iter('powerup') for a in p.iter('affecter')]


def gates(tal):
    out = []
    for lv in tal:
        if lv.tag != 'level':
            continue
        out.append(next((r.get('level') for r in lv if r.tag == 'require' and
                         (r.get('cat') or '').lower() == 'level'), None))
    return out


def test_shared_real_defs_covers_the_four_passives():
    for n in ('critical', 'might', 'leadership', 'flight', 'toughness', 'mutantmastery', 'acrobatics'):
        assert n in H.SHARED_REAL_DEFS


def test_critical_five_ranks_gates_and_affecters():
    src = x1_talent('critical', [('A small bonus.', [], []), ('A medium bonus.', [{'cat': 'level', 'level': '7'}], []),
                                 ('A bigger bonus.', [{'cat': 'level', 'level': '12'}], []),
                                 ('A large bonus.', [{'cat': 'level', 'level': '17'}], []),
                                 ('The largest bonus.', [{'cat': 'level', 'level': '22'}], [])])
    tal, report = H.convert_shared_real('critical', src, values())
    assert not report['errors'] and not report['losses'], report
    levels = [c for c in tal if c.tag == 'level']
    assert len(levels) == 5
    assert gates(tal) == ['1', '7', '12', '17', '22']
    assert [affecters(lv) for lv in levels] == [[('critical', '0.02', None)], [('critical', '0.04', None)],
                                                [('critical', '0.06', None)], [('critical', '0.08', None)],
                                                [('critical', '0.10', None)]]
    for lv in levels:
        assert all(p.get('life') == '-1' for p in lv.iter('powerup'))


def test_might_three_ranks_heaviness_and_structure():
    src = x1_talent('might', [('Lifts small things.', [], []), ('Lifts medium things.', [], []),
                              ('Lifts big things.', [], [])])
    tal, report = H.convert_shared_real('might', src, values())
    assert not report['errors'] and not report['losses'], report
    levels = [c for c in tal if c.tag == 'level']
    assert len(levels) == 3
    assert gates(tal) == ['1', '1', '1']          # XML1 gates none of the three ranks
    assert [affecters(lv) for lv in levels] == [
        [('might_heaviness', '1', None), ('might_structure', '1', None)],
        [('might_heaviness', '2', None), ('might_structure', '1', None)],
        [('might_heaviness', '3', None), ('might_structure', '1', None)]]


def test_leadership_combo_powerups_survive_conversion():
    src = x1_talent('leadership', [
        ('First rung.', [{'cat': 'level', 'level': '4'}],
         [{'powerup': 'combo_damage', 'level': '1.25', 'affect_type': 'scale', 'life': '-1'},
          {'powerup': 'combo_xp', 'level': '1.05', 'affect_type': 'scale', 'life': '-1'}]),
        ('Top rung.', [{'cat': 'level', 'level': '9'}],
         [{'powerup': 'combo_damage', 'level': '1.6', 'affect_type': 'scale', 'life': '-1'},
          {'powerup': 'combo_xp', 'level': '1.12', 'affect_type': 'scale', 'life': '-1'}])])
    tal, report = H.convert_shared_real('leadership', src, values())
    assert not report['errors'] and not report['losses'], report
    levels = [c for c in tal if c.tag == 'level']
    assert len(levels) == 2
    assert gates(tal) == ['4', '9']
    assert [affecters(lv) for lv in levels] == [
        [('combo_damage', '1.25', 'scale'), ('combo_xp', '1.05', 'scale')],
        [('combo_damage', '1.6', 'scale'), ('combo_xp', '1.12', 'scale')]]


def test_combo_affecters_are_engine_known():
    assert 'combo_damage' in H.AFFECTER_VOCAB and 'combo_xp' in H.AFFECTER_VOCAB


def test_flight_five_ranks_and_engine_keyed_drain():
    src = x1_talent('flight', [('Drains a lot.', [], []), ('Drains less.', [], []),
                               ('Drains little and unlocks pickup.', [], []),
                               ('Drains barely anything.', [], []), ('Almost free.', [], [])])
    tal, report = H.convert_shared_real('flight', src, values())
    assert not report['errors'] and not report['losses'], report
    levels = [c for c in tal if c.tag == 'level']
    assert len(levels) == 5
    assert gates(tal) == ['1', '1', '1', '1', '1']
    pwr = {int(tv.get('level')): tv.get('value')
           for tv in tal.iter('talentvalue') if tv.get('name') == 'flight_pwr'}
    assert pwr == {1: '40', 2: '30', 3: '20', 4: '10', 5: '5'}
    assert not list(tal.iter('powerup'))          # the drain is the keyed talentvalue, not a powerup


def test_convert_activepowerups_keeps_combo_scales():
    apu = ET.Element('activepowerup', {'powerup': 'combo_damage', 'level': '1.3', 'affect_type': 'scale',
                                       'life': '-1'})
    report = {'losses': [], 'warnings': [], 'errors': [], 'unverified_affecters': [], 'unverified': []}
    out = H.convert_activepowerups([apu], values(), 1, 'synthetic:test rank 1', report)
    assert report['losses'] == [] and report['unverified_affecters'] == [], report
    assert len(out) == 1 and out[0].get('life') == '-1'
    aff = list(out[0].iter('affecter'))
    assert [(a.get('attribute'), a.get('level'), a.get('affect_type')) for a in aff] == \
        [('combo_damage', '1.3', 'scale')]
