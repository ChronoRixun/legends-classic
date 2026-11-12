"""A Danger Room course with hero= must not carry singleplayer: XMen2.exe's singleplayer branch (0x4d1f7a ->
0x4d1f84) keeps the party leader (xml2-fix fallback: Cyclops) and ignores hero=, so "Challenge - Beast" played
Cyclops. The hero branch (0x4d207b) seats the course hero. Invented course fixtures; no game data."""
import contextlib
import xml.etree.ElementTree as ET

from xml1build import frontend as F


def x1_table(smuggle=False):
    root = ET.Element('DANGERROOM')
    ET.SubElement(root, 'ARENA', title='Snow Courtyard', zone='arena/arena_snow')
    grade = ET.SubElement(root, 'GRADE', name='Freshman')
    hero = ET.SubElement(grade, 'COURSE', name='CHTEST', title='Challenge - Test', arena='Snow Courtyard',
                         hero='BeAst', reclevel='8', killlimit='20')
    if smuggle:
        hero.set('singleplayer', 'true')
    ET.SubElement(grade, 'COURSE', name='FRTEST', title='Free Practice', arena='Snow Courtyard', reclevel='1')
    return root


@contextlib.contextmanager
def patched(table):
    saved = [(F, '_x1_dr', F._x1_dr), (F, 'xp_curve', F.xp_curve), (F, 'course_reward_xp', F.course_reward_xp),
             (F.DR, 'plan', F.DR.plan), (F.C, 'xp_curve_mode', F.C.xp_curve_mode)]
    F._x1_dr = lambda ctx: table
    F.xp_curve = lambda ctx: {}
    F.course_reward_xp = lambda ctx, curve, rl: 0
    F.DR.plan = lambda ctx: {}
    F.C.xp_curve_mode = lambda ctx: 'xml1'
    try:
        yield
    finally:
        for obj, name, value in saved:
            setattr(obj, name, value)


def test_hero_course_keeps_hero_lowercase_and_never_singleplayer():
    with patched(x1_table()):
        root, rep = F.dangerroom_tree(object())
    courses = {c.get('name'): c for c in root.iter('COURSE')}
    assert courses['CHTEST'].get('hero') == 'beast'
    assert courses['CHTEST'].get('singleplayer') is None
    assert courses['FRTEST'].get('singleplayer') is None
    assert rep['counts']['forced_hero_courses'] == 1


def test_a_source_course_cannot_carry_singleplayer_next_to_hero():
    with patched(x1_table(smuggle=True)):
        root, _ = F.dangerroom_tree(object())
    assert next(root.iter('COURSE')).get('singleplayer') is None
