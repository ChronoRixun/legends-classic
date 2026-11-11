"""Handler-requested loop actions after rank collapse (invented move graphs; no game data).

XML1's ch_skating asks its move for chain action `move` while jump is held; XMen2.exe's ch_skating asks for
`samepowerhold` (loop_triggers). Without the XML2 action the slide ends after one cycle whatever the player holds.
"""
import xml.etree.ElementTree as ET

import xmlb
from xml1build import heroes as H
from xml1build import loop_triggers as LT

SLIDE = '''<PowerStyle>
  <FightMove name="jump" handler="ch_move_jump">
    <chain action="move" result="skating"/><chain action="idle" result="jumploop"/>
  </FightMove>
  <FightMove name="jumploop" handler="ch_jump">
    <chain action="move" result="skating"/><chain action="idle" result="jumploop"/>
  </FightMove>
  <FightMove name="skate1" handler="ch_skating" lockchaining="true" fallback="jumploop">
    <require cat="talent" item="invented_slide" level="1"/>
    <require only_looped="true" cat="counter" level="1"/>
    <trigger time="0" tag="5" only_non_looped="true" name="count" count="set" value="1"/>
    <trigger time="0.5" tag="6" name="count" count="add" value="-1"/>
    <chain action="idle" result="skateend"/>
    <chain action="move" result="skate1"/>
    <chain action="touch" result="fastballhit"/>
  </FightMove>
  <FightMove name="skate2" inherit="skate1" fallback="skate1">
    <require cat="talent" item="invented_slide" level="2"/>
    <trigger tag="5" value="2"/>
    <chain action="move" result="skate2"/>
  </FightMove>
  <FightMove name="skating" inherit="skate2" fallback="skate2">
    <require cat="talent" item="invented_slide" level="3"/>
    <trigger tag="5" value="3"/>
    <chain action="move" result="skating"/>
  </FightMove>
  <FightMove name="skateend" handler="ch_jump"><chain action="idle" result="skateend"/></FightMove>
  <FightMove name="fastballhit"><chain action="idle" result="idle"/></FightMove>
  <FightMove name="charge1" handler="ch_charge_move"><chain action="move" result="charge1"/></FightMove>
</PowerStyle>'''


def convert(text=SLIDE):
    source = ET.fromstring(text)
    sc = H.StyleCollapse('iceman', source, H.Values(ET.Element('values')),
                         {'invented_slide': {'levels': 3}}, set())
    style = xmlb.decode(xmlb.encode(sc.run()))
    assert not sc.report['errors'], sc.report['errors']
    return style, sc


def chains(move):
    return [(c.get('action'), c.get('result')) for c in move.findall('chain')]


def loop_target(move, action):
    return next((r for a, r in chains(move) if a == action), None)


def test_collapsed_slide_loops_on_the_action_xmen2_ch_skating_requests():
    style, sc = convert()
    moves = {m.get('name'): m for m in style.findall('FightMove')}
    slide = moves['skating']
    assert slide.get('handler') == 'ch_skating'
    # XMen2.exe 0x4ec9e0 requests 0x1e samepowerhold while jump is held: it must lead back into the slide
    assert loop_target(slide, 'samepowerhold') == 'skating'
    # XML1's chain stays (the generic transition can still resolve it) and the end/touch exits are untouched
    assert loop_target(slide, 'move') == 'skating'
    assert loop_target(slide, 'idle') == 'skateend' and loop_target(slide, 'touch') == 'fastballhit'
    assert sc.report['loop_actions'] == ['skating: chain samepowerhold -> skating']
    assert LT.problems(style) == []


def test_held_jump_runs_the_rank_counter_down_to_the_fallback_exit():
    """simulate XMen2.exe's slide: held jump -> request samepowerhold each cycle; counter gate -> fallback."""
    style, _ = convert()
    moves = {m.get('name'): m for m in style.findall('FightMove')}
    current, counter, cycles = moves['skating'], 3, 0           # top rank: counter set to 3 on entry
    while True:
        cycles += 1
        counter -= 1                                              # count add -1 at 0.5
        nxt = loop_target(current, 'samepowerhold')               # the only id the XML2 handler asks for
        assert nxt is not None, 'held jump finds no continuation: the slide ends after one cycle'
        if counter < 1:                                           # only_looped counter >= 1 fails
            assert moves[nxt].get('fallback') == 'jumploop'
            break
        current = moves[nxt]
    assert cycles == 3


def test_only_the_mapped_handler_is_touched():
    style, _ = convert()
    moves = {m.get('name'): m for m in style.findall('FightMove')}
    for name in ('jump', 'jumploop', 'charge1'):
        assert loop_target(moves[name], 'samepowerhold') is None, name


def test_kept_inheriting_moves_resolve_the_handler_through_inherit():
    style = ET.fromstring('''<PowerStyle>
      <FightMove name="slidea" handler="ch_skating"><chain action="move" result="slidea"/></FightMove>
      <FightMove name="slideb" inherit="slidea"><chain action="move" result="slideb"/></FightMove>
    </PowerStyle>''')
    moves = style.findall('FightMove')
    assert LT.add_loop_actions(moves) == [('slidea', 'samepowerhold', 'slidea'), ('slideb', 'samepowerhold', 'slideb')]
    assert LT.add_loop_actions(moves) == []                       # idempotent
    assert LT.problems(style) == []


def test_validator_rejects_a_slide_without_the_xml2_loop_action():
    style, _ = convert()
    slide = next(m for m in style.findall('FightMove') if m.get('name') == 'skating')
    for c in list(slide.findall('chain')):
        if c.get('action') == 'samepowerhold':
            slide.remove(c)
    assert LT.problems(style) == ['skating: ch_skating loop chain to skating has no samepowerhold action '
                                  '(XMen2.exe requests samepowerhold, never move)']


def test_conflicting_existing_xml2_action_is_refused():
    style = ET.fromstring('''<PowerStyle><FightMove name="s" handler="ch_skating">
      <chain action="move" result="s"/><chain action="samepowerhold" result="other"/></FightMove></PowerStyle>''')
    try:
        LT.add_loop_actions(style.findall('FightMove'))
    except ValueError:
        return
    raise AssertionError('a conflicting samepowerhold chain was accepted')
