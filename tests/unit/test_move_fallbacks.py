"""Invented move graphs exercise exits after rank collapse; no game data."""
import xml.etree.ElementTree as ET

import xmlb
from xml1build import heroes as H


def fixture():
    source = ET.fromstring('''<PowerStyle>
      <FightMove name="begin" icon="3" fallback="idle">
        <require cat="skill" item="invented_dash" level="1"/>
        <chain action="idle" result="dash2"/>
      </FightMove>
      <FightMove name="dash1" fallback="finish1" handler="ch_teleport_frenzy_dash">
        <require cat="counter" level="1"/>
        <trigger name="count" count="add" value="-1" time="0"/>
        <chain action="idle" result="dash2"/>
      </FightMove>
      <FightMove name="dash2" inherit="dash1" fallback="dash1">
        <require cat="level" level="XTL2"/>
      </FightMove>
      <FightMove name="finish1">
        <require cat="skill" item="invented_finish" level="1"/>
        <trigger name="xtreme_start" end="true" time="0.2"/>
        <chain action="idle" result="idle"/>
      </FightMove>
      <FightMove name="finish2" inherit="finish1" fallback="finish1">
        <require cat="skill" item="invented_finish" level="2"/>
      </FightMove>
    </PowerStyle>''')
    sc = H.StyleCollapse('wolverine', source, H.Values(ET.Element('values')),
                         {'invented_dash': {'power': '3', 'levels': 2},
                          'invented_finish': {'power': '0', 'levels': 2}}, set())
    style = xmlb.decode(xmlb.encode(sc.run()))
    assert not sc.report['errors'], sc.report['errors']
    return source, style, sc


def test_collapsed_dash_reaches_cleanup_after_counter_exhaustion():
    _, style, _ = fixture()
    moves = {m.get('name'): m for m in style.findall('FightMove')}
    for targets in (0, 1, 7):
        current, remaining = moves['dash2'], targets
        for _ in range(targets + 1):
            if remaining < 1:
                destination = current.get('fallback')
                assert destination == 'power1', 'exhausted dash must reach its cleanup move'
                assert moves[destination].find('trigger').get('end') == 'true'
                break
            remaining -= 1
            current = moves[current.find('chain').get('result')]
        else:
            raise AssertionError('dash did not terminate')


def test_kept_fallback_and_external_base_move_survive_but_rank_self_fallback_does_not():
    _, style, _ = fixture()
    moves = {m.get('name'): m for m in style.findall('FightMove')}
    assert moves['power9'].get('fallback') == 'idle'
    assert moves['power1'].get('fallback') is None
    assert all(m.get('fallback') != name for name, m in moves.items())


def test_validator_catches_missing_and_wrong_exit_in_serialized_output():
    from xml1build import move_fallbacks as F
    source, style, sc = fixture()
    mapping = dict(sc.report['chain_map']) | sc.report['renamed']
    mapping.update({n: n for n in sc.report['kept'] if ' -> ' not in n})
    assert not F.problems(source, style, mapping)
    dash = next(m for m in style.findall('FightMove') if m.get('name') == 'dash2')
    for bad in (None, 'dash2', 'finish1', 'idle'):
        if bad is None:
            dash.attrib.pop('fallback', None)
        else:
            dash.set('fallback', bad)
        assert F.problems(source, xmlb.decode(xmlb.encode(style)), mapping), bad


def test_kept_counter_loop_retains_its_exit():
    source = ET.fromstring('''<PowerStyle>
      <FightMove name="loop" fallback="cleanup">
        <require cat="counter" level="1"/><chain action="idle" result="loop"/>
      </FightMove>
      <FightMove name="cleanup"><chain action="idle" result="idle"/></FightMove>
    </PowerStyle>''')
    sc = H.StyleCollapse('wolverine', source, H.Values(ET.Element('values')), {}, set())
    output = sc.run()
    assert not sc.report['errors'], sc.report['errors']
    assert output.find('FightMove').get('fallback') == 'cleanup'


def test_validator_rejects_conflicting_or_cyclic_source_fallbacks():
    from xml1build import move_fallbacks as F
    source, style, sc = fixture()
    mapping = F.name_map(sc.report)
    dash = next(m for m in source.findall('FightMove') if m.get('name') == 'dash2')
    dash.set('fallback', 'idle')
    assert any('conflicting' in e for e in F.problems(source, style, mapping))
    dash.set('fallback', 'dash2')
    assert any('cyclic' in e for e in F.problems(source, style, mapping))


def test_dropped_roots_cannot_donate_fallbacks_to_a_surviving_power():
    from xml1build import move_fallbacks as F
    source, style, sc = fixture()
    dropped = ET.SubElement(source, 'FightMove', name='unused_decision', fallback='walk')
    ET.SubElement(dropped, 'require', cat='skill', item='invented_dash', level='1')
    sc.report['dropped'].append('unused_decision (+0 rungs): intentionally omitted')
    mapping = F.name_map(sc.report, source)
    assert 'unused_decision' not in mapping
    assert not F.problems(source, style, mapping)


def test_missing_source_mapping_is_an_error_even_when_the_output_also_lost_the_exit():
    from xml1build import move_fallbacks as F
    source, _, sc = fixture()
    for key in ('chain_map', 'renamed'):
        sc.report[key].clear()
    sc.report['kept'].clear()
    try:
        F.name_map(sc.report, source)
    except ValueError as exc:
        assert 'mapping missing source move' in str(exc)
    else:
        raise AssertionError('empty mapping must not suppress source-derived checks')


def test_separately_kept_move_inherits_fallback_but_can_override_it():
    source = ET.fromstring('''<PowerStyle>
      <FightMove name="base" fallback="idle"/>
      <FightMove name="inherited" inherit="base"/>
      <FightMove name="override" inherit="base" fallback="walk"/>
    </PowerStyle>''')
    sc = H.StyleCollapse('wolverine', source, H.Values(ET.Element('values')), {}, set())
    output = sc.run()
    assert not sc.report['errors'], sc.report['errors']
    moves = {m.get('name'): m for m in output.findall('FightMove')}
    assert moves['inherited'].get('fallback') == 'idle'
    assert moves['override'].get('fallback') == 'walk'


def test_validator_rejects_missing_local_fallback_destination():
    from xml1build import move_fallbacks as F
    source, style, sc = fixture()
    style.remove(next(m for m in style.findall('FightMove') if m.get('name') == 'power1'))
    assert any('destination' in e for e in F.problems(source, style, F.name_map(sc.report, source)))
