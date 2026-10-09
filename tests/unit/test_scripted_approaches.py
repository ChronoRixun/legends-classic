"""Scripted encounter placement compatibility, using invented actors and scripts."""
from xml1build import scripted_approaches as A
import xml.etree.ElementTree as ET


def test_spawn_placement_waits_for_birth_and_keeps_original_sequence():
    text = 'cameraBegin()\nact("guardian_spawn", "guardian_spawn" )\nraiseBarrier()\n'
    result = A.place_after_spawn(text, 'guardian_spawn', 'guardian', 'arrival_marker')
    assert result == ('cameraBegin()\r\nact("guardian_spawn", "guardian_spawn" )\r\n'
                      'waittimed ( 0.100 )\r\n'
                      'copyOriginAndAngles("guardian", "arrival_marker" )\r\nraiseBarrier()\r\n')
    assert A.place_after_spawn(result, 'guardian_spawn', 'guardian', 'arrival_marker') == result


def test_spawn_placement_preserves_conditional_scope_and_ignores_comments():
    text = ('# act("guardian_spawn", "guardian_spawn")\nif phase == 1\n'
            "     act ( 'guardian_spawn', 'guardian_spawn' )\nendif\n")
    result = A.place_after_spawn(text, 'guardian_spawn', 'guardian', 'arrival_marker')
    assert '     waittimed ( 0.100 )\r\n     copyOriginAndAngles(' in result
    assert result.endswith('\r\nendif\r\n')


def test_spawn_placement_rejects_missing_or_ambiguous_source_anchor():
    for text in ('act("other", "other")', 'act("guardian_spawn","guardian_spawn")\n' * 2):
        try:
            A.place_after_spawn(text, 'guardian_spawn', 'guardian', 'arrival_marker')
        except ValueError:
            pass
        else:
            raise AssertionError('unreviewed source shape must fail closed')


def test_approach_rule_detects_missing_wait_wrong_marker_and_wrong_order():
    original = 'act("guardian_spawn","guardian_spawn")\nraiseBarrier()\n'
    good = A.place_after_spawn(original, 'guardian_spawn', 'guardian', 'arrival_marker')
    assert A.placement_problems(good, 'guardian_spawn', 'guardian', 'arrival_marker') == []
    for text in (original, good.replace('waittimed ( 0.100 )\r\n', ''),
                 good.replace('arrival_marker', 'other_marker'),
                 good.replace('waittimed ( 0.100 )\r\ncopyOriginAndAngles("guardian", "arrival_marker" )',
                              'copyOriginAndAngles("guardian", "arrival_marker" )\r\nwaittimed ( 0.100 )')):
        assert A.placement_problems(text, 'guardian_spawn', 'guardian', 'arrival_marker')


def test_rewrite_is_scoped_to_the_configured_intro():
    old = A.APPROACHES
    try:
        A.APPROACHES = {'test/intro': ('test/arena', 'guardian_spawn', 'guardian', 'arrival_marker')}
        text = 'act("guardian_spawn","guardian_spawn")\r\n'
        assert A.rewrite_script('unrelated/intro', text) == text
        fixed = A.rewrite_script('Scripts/TEST/intro.py', text)
        assert fixed != text and A.rewrite_script('test/intro', fixed) == fixed
    finally:
        A.APPROACHES = old


def test_validator_checks_the_written_intro_and_a_usable_marker():
    class Validator:
        def __init__(self, data, root):
            self.data, self.root = data, root
        def is_x1(self, rel):
            return rel == 'scripts/test/intro.py'
        def read(self, rel):
            return self.data
        def tree(self, rel):
            return self.root
    class Check:
        def __init__(self):
            self.errors, self.counts = [], {}
        def error(self, text):
            self.errors.append(text)
        def count(self, key):
            self.counts[key] = self.counts.get(key, 0) + 1
    old = A.APPROACHES
    try:
        A.APPROACHES = {'test/intro': ('test/arena', 'guardian_spawn', 'guardian', 'arrival_marker')}
        good = A.place_after_spawn('act("guardian_spawn","guardian_spawn")\n',
                                  'guardian_spawn', 'guardian', 'arrival_marker').encode()
        root = ET.Element('world')
        group = ET.SubElement(root, 'entinst', {'type': 'arrival_type'})
        marker = ET.SubElement(group, 'inst', {'name': 'arrival_marker', 'pos': '10 20 0'})
        check = Check()
        A.validate(Validator(good, root), check)
        assert not check.errors and check.counts['intros_checked'] == 1
        for data, coords in ((None, '10 20 0'), (b'act("guardian_spawn","guardian_spawn")', '10 20 0'),
                             (good, ''), (good, '10 nan 0'), (good, '10 20'), (good, 'unknown')):
            marker.set('pos', coords)
            check = Check()
            A.validate(Validator(data, root), check)
            assert check.errors, (data, coords)
    finally:
        A.APPROACHES = old
