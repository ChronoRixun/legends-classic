"""Invented power chains, with the two XML1 control powers' duration facts as expectations. No game data."""
import copy
import xml.etree.ElementTree as ET

import xmlb
from xml1build import heroes as H
from xml1build import mind_control as MC
from xml1build import fix_ini as FI


BOUNDS = ((1, 3), (1, 4), (1, 5), (1, 6), (1, 7),
          (2, 10), (2, 11), (2, 12), (2, 13), (2, 14), (5, 20))


def fixture(hero='frost', skill='frost_confuse', power='0'):
    root = ET.Element('PowerStyle')
    previous = None
    for rank, (lo, hi) in enumerate(BOUNDS, 1):
        name = f'invented_control_{rank}'
        attrs = {'name': name}
        if previous:
            attrs.update(inherit=previous, fallback=previous)
        else:
            attrs.update(animenum='ea_power1', icon='0')
        move = ET.SubElement(root, 'FightMove', attrs)
        ET.SubElement(move, 'require', cat='talent', item=skill, level=str(rank))
        attrs = {'tag': '7', 'life': str(lo), 'life_max': str(hi)}
        if rank == 1:
            attrs.update(name='powerup', time='0.25', powerup='confused', apply_self='false', apply_enemy='near')
        elif rank == 6:
            attrs['powerup'] = 'team_switch'
        ET.SubElement(move, 'trigger', attrs)
        previous = name
    sc = H.StyleCollapse(hero, root, H.Values(ET.Element('values')),
                         {skill: {'power': power, 'levels': len(BOUNDS)}}, set())
    style = sc.run()
    assert not sc.report['errors'], sc.report['errors']
    talents = ET.Element('talents')
    talent = ET.SubElement(talents, 'talent', name=skill)
    for name, table in sc.talentvalues[skill].items():
        for rank, value in table.items():
            ET.SubElement(talent, 'talentvalue', name=name, level=str(rank), value=value)
    # The engine reads the serialized trees. Exercise range strings and negative gates through XMLB too.
    return root, xmlb.decode(xmlb.encode(style)), xmlb.decode(xmlb.encode(talents)), sc


def check(source, style, talents):
    return MC.problems(source, style, talents, H.Values(ET.Element('values')))


def value(tree, ref, rank):
    if not ref.startswith('%'):
        return ref
    return next(v.get('value') for v in tree.iter('talentvalue')
                if v.get('name') == ref[1:] and v.get('level') == str(rank))


def test_every_control_rank_keeps_xml1_duration_and_only_the_correct_kind_applies():
    for hero, skill, power in (('frost', 'frost_confuse', '0'), ('jubilee', 'photo_flash', '1')):
        source, style, talents, sc = fixture(hero, skill, power)
        assert not check(source, style, talents)
        triggers = list(style.iter('trigger'))
        assert len(triggers) == 2
        for rank, (lo, hi) in enumerate(BOUNDS, 1):
            active = []
            for t in triggers:
                assert value(talents, t.get('life'), rank) == f'{lo} {hi}'
                assert t.get('xml1_life_range') == t.get('life')
                gate = float(value(talents, t.get('apply_chance'), rank))
                # XML2 rejects only if chance < random. Check the zero-RNG boundary as well as ordinary draws.
                for draw in (0.0, 0.5, 1.0):
                    applies = not (gate < 1 and gate < draw)
                    assert applies == (t.find('affecter').get('attribute') ==
                                       ('confused' if rank < 6 else 'team_switch'))
                if gate == 1:
                    active.append(t.find('affecter').get('attribute'))
            assert active == ['confused' if rank < 6 else 'team_switch']
        assert all(len(name) <= H.TALENTVALUE_NAME_MAX for tables in sc.talentvalues.values() for name in tables)
        assert not any(t.get('life_max') is not None for t in triggers)


def test_validator_rejects_beta3_zero_life_gate_at_every_affected_rank():
    source, style, talents, _ = fixture()
    for t in style.iter('trigger'):
        kind = t.find('affecter').get('attribute')
        t.attrib.pop('apply_chance')
        ref = t.get('life')[1:]
        # Give each kind its old independent life table.
        new_ref = ref + kind[:1]
        t.set('life', '%' + new_ref)
        for rank, (lo, _hi) in enumerate(BOUNDS, 1):
            active = (rank < 6) == (kind == 'confused')
            ET.SubElement(talents, 'talentvalue', name=new_ref, level=str(rank), value=str(lo if active else 0))
    errors = check(source, style, talents)
    assert len(errors) == 11, errors
    assert all('non-expiring' in e for e in errors)


def test_validator_rejects_lost_upper_bound_and_missing_or_nonfinite_duration():
    for replacement in ('2', '0', '-1', 'nan', '2 inf', '%missing'):
        source, style, talents, _ = fixture()
        team = next(t for t in style.iter('trigger') if t.find('affecter').get('attribute') == 'team_switch')
        team.set('life', replacement)
        errors = check(source, style, talents)
        assert len(errors) == 6, (replacement, errors)
        assert all(f'rank {r}:' in ' '.join(errors) for r in range(6, 12))


def test_validator_rejects_an_ungated_or_zero_chance_inactive_team_branch():
    for gate in (None, '0', '1'):
        source, style, talents, _ = fixture()
        team = next(t for t in style.iter('trigger') if t.find('affecter').get('attribute') == 'team_switch')
        if gate is None:
            team.attrib.pop('apply_chance')
        else:
            team.set('apply_chance', gate)
        assert check(source, style, talents), gate


def test_non_split_powerup_preserves_random_duration_without_rewriting_fixed_or_infinite_life():
    for kind in ('team_switch', 'confused', 'fear'):
        t = ET.Element('trigger', name='powerup', powerup=kind, life='3', life_max='17')
        H.convert_powerup_trigger(t, 'invented', {})
        assert t.get('life') == '3 17'
        assert t.find('affecter').get('attribute') == kind
    for life in ('9', '-1', '0', '%invented_time'):
        t = ET.Element('trigger', name='powerup', powerup='team_switch', life=life)
        H.convert_powerup_trigger(t, 'invented', {})
        assert t.get('life') == life


def test_explicit_bounds_use_xml1_value_code_lower_numbers_and_do_not_mutate_source():
    values = H.Values(ET.fromstring('<values><value name="L1" min="3" max="7"/>'
                                  '<value name="L2" min="12" max="19"/></values>'))
    t = ET.Element('trigger', name='powerup', powerup='team_switch', life='L1', life_max='L2')
    original = copy.deepcopy(t)
    assert H.powerup_life_range(t, values) == '3 12'
    assert ET.tostring(t) == ET.tostring(original)
    move = ET.Element('FightMove', name='invented')
    move.append(t)
    H.fixup_move(move, values, 'invented', {})
    assert t.get('life') == '3 12'


def test_validator_detects_missing_power_and_unexpected_team_switch():
    source, style, talents, _ = fixture()
    empty = ET.Element('PowerStyle')
    assert check(source, empty, talents)
    assert check(empty, style, talents)


def test_template_range_and_companion_are_required(tmp_path):
    source, style, talents, _ = fixture()
    team = next(t for t in style.iter('trigger') if t.find('affecter').get('attribute') == 'team_switch')
    team.attrib.pop('xml1_life_range')
    assert len(check(source, style, talents)) == 6
    assert FI.game_keys()['MindControlLife'] == 'xml1'
    assert 'MindControlLife' in FI.PORT_OWNED['Game']
    assert 'MindControlLife' not in FI.game_keys(xml1_opening=False)
    dll = tmp_path / 'synthetic.bin'
    dll.write_bytes(b'invented older companion')
    try:
        FI.check_release_dll(dll, {'Game': {'MindControlLife': 'xml1'}})
    except FI.FixTooOld as exc:
        assert 'MindControlLife' in str(exc)
    else:
        raise AssertionError('older companion admitted')
    dll.write_bytes(FI.CONTROL_LIFE_MARKER)
    FI.check_release_dll(dll, {'Game': {'MindControlLife': 'xml1'}})
