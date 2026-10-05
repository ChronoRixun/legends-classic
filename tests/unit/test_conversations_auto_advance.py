"""SPEC 34 (2026-10-01, audit W1; XML1's rule 2026-10-04) on a made-up conversation built in code - no game text, no
decoded game data: a voiced line that XML1 runs without the user (its own runWithoutUser attribute, or the file's
last startCondition flagged) becomes a negative timeDelay the xml2-fix AutoAdvance hook reads
(xml1build.conversations)."""
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
QUIET = '%GUIDE%Off you go then.'
LONG = '%GUIDE%Every line of this tree runs on its own, however long the sentence that it carries happens to be in the end.'
EVEN = '%NEWCOMER%Even this one.'
MUTE = '%NEWCOMER%But not this silent one.'


def node(parent, tag, text=None, **attrs):
    el = ET.SubElement(parent, tag, {k: v for k, v in attrs.items()})
    if text is not None:
        el.set('text', text)
    return el


def tree():
    """two startConditions: the first flagged as a whole but NOT the last one (so its flag counts for nothing), the
    second plain - a flagged opening line, a hub of three replies, a line flagged 'false' under one of them, a line
    whose only flag is on its reply, a flagged line with an empty voice under a flagged reply."""
    root = ET.Element('conversation')
    sc1 = node(root, 'startCondition', runOnce='true', runWithoutUser='true')
    p1 = node(sc1, 'participant', name='default')
    long_line = node(p1, 'line', LONG, soundToPlay='voice/guide/0010')
    long_blank = node(long_line, 'response', '%BLANK%')
    even = node(long_blank, 'line', EVEN, soundToPlay='voice/newcomer/0011', timedelay='2.5')
    even_blank = node(even, 'response', '%BLANK%')
    mute = node(even_blank, 'line', MUTE)
    node(mute, 'response', '%END%')
    sc2 = node(root, 'startCondition', conditionScriptFile='demo/intro_cam')
    p2 = node(sc2, 'participant', name='default')
    hello = node(p2, 'line', HELLO, soundToPlay='voice/guide/0001', runWithoutUser='true')
    blank = node(hello, 'response', '%BLANK%')
    hub = node(blank, 'line', HUB, tagIndex='hub')
    what = node(hub, 'response', WHAT, soundToPlay='voice/newcomer/0002')
    hall = node(what, 'line', HALL, soundToPlay='voice/guide/0003', runWithoutUser='false')
    hall_blank = node(hall, 'response', '%BLANK%', runWithoutUser='true')
    see = node(hall_blank, 'line', SEE, soundToPlay='voice/newcomer/0004')
    node(see, 'response', '%BLANK%', runWithoutUser='true')
    who = node(hub, 'response', WHO, soundToPlay='voice/newcomer/0005')
    guide = node(who, 'line', GUIDE, timeDelay='3')
    node(guide, 'response', '%END%')
    bye = node(hub, 'response', BYE, runWithoutUser='true')
    quiet = node(bye, 'line', QUIET, soundToPlay='', runWithoutUser='true')
    node(quiet, 'response', '%END%', runWithoutUser='true')
    return root


def last_flagged(root):
    """the same tree with the flag moved from the first startCondition to the last."""
    first, last = [el for el in root if el.tag == 'startCondition']
    del first.attrib['runWithoutUser']
    last.set('runWithoutUser', 'true')
    return root


def lines(root):
    return [l for l in root.iter() if l.tag == 'line']


def why(root):
    return {l.get('text'): w for l, w in CV.auto_lines(root)}


def test_which_lines_are_marked_and_why():
    # a flag on an earlier startCondition, a reply's flag and a flag on a line without a voice count for nothing
    assert why(tree()) == {HELLO: 'line', HALL: 'line'}


def test_a_flagged_line_without_a_voice_waits():
    assert QUIET not in why(tree())                        # flagged, soundToPlay="" (and its reply flagged too)
    flagged_file = why(last_flagged(tree()))
    assert MUTE not in flagged_file and QUIET not in flagged_file   # no voice, in a flagged file


def test_a_flag_on_the_only_reply_does_not_advance_the_line():
    assert SEE not in why(tree())


def test_the_last_startcondition_decides_for_the_whole_file():
    assert not CV.file_flagged(tree()) and CV.file_flagged(last_flagged(tree()))
    assert not CV.file_flagged(ET.Element('conversation'))
    # every voiced line of the file, in either startCondition; a line's own flag still says 'line'
    assert why(last_flagged(tree())) == {HELLO: 'line', HALL: 'line', SEE: 'file', LONG: 'file', EVEN: 'file'}


def test_a_line_flag_counts_whatever_its_value():
    for value in ('true', 'false', '', '0', 'TRUE'):
        root = ET.Element('conversation')
        p = node(node(root, 'startCondition'), 'participant', name='default')
        line = node(p, 'line', '%A%Hello there.', soundToPlay='voice/a/0001', runwithoutuser=value)
        node(line, 'response', '%END%')
        assert why(root) == {'%A%Hello there.': 'line'}, value


def test_marking_writes_a_negative_timedelay_once():
    root = last_flagged(tree())
    assert CV.mark_auto_advance(root) == 5
    by_text = {l.get('text'): l for l in lines(root)}
    assert by_text[HELLO].get('timeDelay') == '-3.3'      # 38 characters after the token
    assert by_text[SEE].get('timeDelay') == '-2'          # the 2 s floor
    assert by_text[LONG].get('timeDelay') == '-7.5'       # 108 characters
    assert by_text[EVEN].get('timeDelay') == '-2.5' and 'timedelay' not in by_text[EVEN].attrib   # XML1's own value, the engine's name
    assert by_text[GUIDE].get('timeDelay') == '3'         # no voice: untouched
    assert by_text[HUB].get('timeDelay') is None and by_text[QUIET].get('timeDelay') is None
    assert by_text[MUTE].get('timeDelay') is None
    assert [l.get('text') for l in CV.marked_lines(root)] == [l.get('text') for l, _ in CV.auto_lines(root)]
    again = copy.deepcopy(root)
    assert CV.mark_auto_advance(again) == 0 and ET.tostring(again) == ET.tostring(root)


def test_reading_time_bounds_and_token_stripping():
    assert CV.reading_seconds('%A%') == 2.0 and CV.reading_seconds('') == 2.0 and CV.reading_seconds(None) == 2.0
    assert CV.reading_seconds('%A%: ten chars') == 2.0 and CV.reading_seconds('%A%' + 'x' * 50) == 4.0
    assert CV.reading_seconds('%A%' + 'x' * 400) == 12.0
    assert CV.reading_seconds('x' * 20) == CV.reading_seconds('%LONG_SPEAKER_NAME%' + 'x' * 20)


def test_responses_and_empty_trees_are_left_alone():
    root = last_flagged(tree())
    CV.mark_auto_advance(root)
    assert all(r.get('timeDelay') is None for r in root.iter() if r.tag == 'response')
    assert CV.mark_auto_advance(None) == 0 and CV.mark_auto_advance(ET.Element('conversation')) == 0
    flagged = ET.Element('conversation')
    sc = node(flagged, 'startCondition', runwithoutuser='TRUE')
    node(node(sc, 'participant', name='default'), 'line', '%A%Hello there.', soundToPlay='voice/a/0001',
         timeDelay='-9')
    assert CV.mark_auto_advance(flagged) == 0 and lines(flagged)[0].get('timeDelay') == '-9'
