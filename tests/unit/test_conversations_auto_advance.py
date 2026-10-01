"""SPEC 34 (2026-10-01, audit W1) on a made-up conversation built in code - no game text, no decoded game data: a
runWithoutUser line, startCondition or single response becomes a negative timeDelay the xml2-fix AutoAdvance hook
reads (xml1build.conversations)."""
import copy
import xml.etree.ElementTree as ET

from xml1build import conversations as CV

# the made-up lines (speaker token + invented words); the tree below hangs them on each other
HELLO = '%GUIDE%Welcome to the testing hall, newcomer.'
HUB = '%GUIDE%'
WHAT = 'What is this place?'
HALL = '%GUIDE%A hall where testers test.'
SEE = '%NEWCOMER%I see.'
WHO = 'Who are you?'
GUIDE = '%GUIDE%The guide.'
BYE = 'Goodbye.'
LONG = '%GUIDE%Every line of this tree runs on its own, however long the sentence that it carries happens to be in the end.'
EVEN = '%NEWCOMER%Even this one.'


def node(parent, tag, text=None, **attrs):
    el = ET.SubElement(parent, tag, {k: v for k, v in attrs.items()})
    if text is not None:
        el.set('text', text)
    return el


def tree():
    """two startConditions: the first plain (a flagged opening line, a hub of three replies, flagged lines under
    one of them, a single flagged reply under another), the second flagged as a whole."""
    root = ET.Element('conversation')
    sc1 = node(root, 'startCondition', runOnce='true', conditionScriptFile='demo/intro_cam')
    p1 = node(sc1, 'participant', name='default')
    hello = node(p1, 'line', HELLO, soundToPlay='voice/guide/0001', runWithoutUser='true')
    blank = node(hello, 'response', '%BLANK%')
    hub = node(blank, 'line', HUB, tagIndex='hub')
    what = node(hub, 'response', WHAT, soundToPlay='voice/newcomer/0002')
    hall = node(what, 'line', HALL, soundToPlay='voice/guide/0003', runWithoutUser='true')
    hall_blank = node(hall, 'response', '%BLANK%', runWithoutUser='true')
    see = node(hall_blank, 'line', SEE, soundToPlay='voice/newcomer/0004')
    node(see, 'response', '%BLANK%', runWithoutUser='true')
    who = node(hub, 'response', WHO, soundToPlay='voice/newcomer/0005')
    guide = node(who, 'line', GUIDE, timeDelay='3')
    node(guide, 'response', '%END%')
    node(hub, 'response', BYE, runWithoutUser='true')
    sc2 = node(root, 'startCondition', runWithoutUser='true')
    p2 = node(sc2, 'participant', name='default')
    long_line = node(p2, 'line', LONG)
    long_blank = node(long_line, 'response', '%BLANK%')
    even = node(long_blank, 'line', EVEN, timedelay='2.5')
    node(even, 'response', '%END%')
    return root


def lines(root):
    return [l for l in root.iter() if l.tag == 'line']


def test_which_lines_are_marked_and_why():
    root = tree()
    why = {l.get('text'): w for l, w in CV.auto_lines(root)}
    assert why == {HELLO: 'line', HALL: 'line', SEE: 'response', LONG: 'startcondition', EVEN: 'startcondition'}
    # the hub menu (three replies, one of them flagged) and the plain reply's line are left to the player
    assert HUB not in why and GUIDE not in why


def test_marking_writes_a_negative_timedelay_once():
    root = tree()
    assert CV.mark_auto_advance(root) == 5
    by_text = {l.get('text'): l for l in lines(root)}
    assert by_text[HELLO].get('timeDelay') == '-3.3'      # 38 characters after the token
    assert by_text[SEE].get('timeDelay') == '-2'          # the 2 s floor
    assert by_text[LONG].get('timeDelay') == '-7.5'       # 108 characters
    assert by_text[EVEN].get('timeDelay') == '-2.5' and 'timedelay' not in by_text[EVEN].attrib   # XML1's own value, the engine's name
    assert by_text[GUIDE].get('timeDelay') == '3'         # not flagged: untouched
    assert by_text[HUB].get('timeDelay') is None
    assert [l.get('text') for l in CV.marked_lines(root)] == [l.get('text') for l, _ in CV.auto_lines(root)]
    again = copy.deepcopy(root)
    assert CV.mark_auto_advance(again) == 0 and ET.tostring(again) == ET.tostring(root)


def test_reading_time_bounds_and_token_stripping():
    assert CV.reading_seconds('%A%') == 2.0 and CV.reading_seconds('') == 2.0 and CV.reading_seconds(None) == 2.0
    assert CV.reading_seconds('%A%: ten chars') == 2.0 and CV.reading_seconds('%A%' + 'x' * 50) == 4.0
    assert CV.reading_seconds('%A%' + 'x' * 400) == 12.0
    assert CV.reading_seconds('x' * 20) == CV.reading_seconds('%LONG_SPEAKER_NAME%' + 'x' * 20)


def test_responses_and_empty_trees_are_left_alone():
    root = tree()
    CV.mark_auto_advance(root)
    assert all(r.get('timeDelay') is None for r in root.iter() if r.tag == 'response')
    assert CV.mark_auto_advance(None) == 0 and CV.mark_auto_advance(ET.Element('conversation')) == 0
    flagged = ET.Element('conversation')
    sc = node(flagged, 'startCondition', runwithoutuser='TRUE')
    node(node(sc, 'participant', name='default'), 'line', '%A%Hello there.', timeDelay='-9')
    assert CV.mark_auto_advance(flagged) == 0 and lines(flagged)[0].get('timeDelay') == '-9'
