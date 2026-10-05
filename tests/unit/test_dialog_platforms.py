"""Synthetic regressions for popup dialogs that only have console variants (issue #50)."""
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

from xml1build import common as C, x1schema as S
from xml1build.validate import Check, Validator


def dialogs(*variants, wrapper='xmlb_multiple_roots'):
    root = ET.Element(wrapper)
    for attrs in variants:
        ET.SubElement(root, 'dialog', attrs)
    return root


def console_tip():
    return dialogs({'text': 'Pull the invented trigger.', 'platform': 'xbox', 'cancancel': 'false'},
                   {'text': 'Press the invented button.', 'platform': 'ps2', 'cancancel': 'false'},
                   {'text': 'Squeeze the invented stick.', 'platform': 'gc', 'cancancel': 'false'})


def test_platform_test_matches_the_engine_rule():
    for value in (None, '', 'PC', 'pc', 'xbox,PC', 'ps2 pc', 'gc\tPC'):
        assert S.dialog_platform_accepted(value), value
    for value in ('xbox', 'ps2', 'gc', 'xbox,ps2', 'PCX', 'notpc'):
        assert not S.dialog_platform_accepted(value), value


def test_console_only_dialog_gets_an_untagged_copy_of_the_ps2_variant():
    root = console_tip()
    before = [dict(d.attrib) for d in root]
    assert S.dialog_platform_problems(root) == [('', ['xbox', 'ps2', 'gc'])]
    changes = S.convert(root, 'dialogs/invented_tip.eng')
    assert changes['dialog_pc_variant_added'] == 1
    assert [dict(d.attrib) for d in root][:3] == before          # console variants untouched
    added = list(root)[3]
    assert 'platform' not in added.attrib
    assert added.attrib == {k: v for k, v in before[1].items() if k != 'platform'}
    assert S.dialog_platform_problems(root) == []
    assert not S.convert(root, 'dialogs/invented_tip.eng')       # idempotent
    assert len(root) == 4


def test_fallbacks_when_no_ps2_variant_exists():
    root = dialogs({'text': 'a', 'platform': 'gc'}, {'text': 'b', 'platform': 'xbox'})
    S.convert_dialog_platforms(root)
    assert list(root)[-1].get('text') == 'b'
    root = dialogs({'text': 'only', 'platform': 'gc'}, wrapper='dialog_def')
    S.convert_dialog_platforms(root)
    assert [d.get('text') for d in root] == ['only', 'only'] and 'platform' not in list(root)[1].attrib
    lone = ET.Element('dialog', {'text': 'single', 'platform': 'xbox'})
    assert S.convert_dialog_platforms(lone) == 1 and 'platform' not in lone.attrib


def test_dialogs_already_readable_on_pc_and_other_files_are_unchanged():
    cases = [
        (dialogs({'text': 'plain'}), 'dialogs/invented_plain.eng'),
        (dialogs({'text': 'x', 'platform': 'xbox'}, {'text': 'p'}), 'dialogs/invented_split.eng'),
        (dialogs({'text': 'x', 'platform': 'xbox'}, {'text': 'p', 'platform': 'PC'}), 'dialogs/invented_pc.eng'),
        (console_tip(), 'conversations/invented/talk.eng'),
    ]
    for root, rel in cases:
        before = ET.tostring(root)
        S.convert(root, rel)
        assert ET.tostring(root) == before, rel


def test_each_filter_value_gets_its_own_pc_variant():
    root = dialogs({'text': 'one x', 'platform': 'xbox', 'filter': '1'},
                   {'text': 'one p', 'platform': 'ps2', 'filter': '1'},
                   {'text': 'two x', 'platform': 'xbox', 'filter': '2'},
                   {'text': 'three', 'filter': '3'})
    assert [f for f, _ in S.dialog_platform_problems(root)] == ['1', '2']
    assert S.convert_dialog_platforms(root) == 2
    assert [(d.get('filter'), d.get('platform'), d.get('text')) for d in root] == [
        ('1', 'xbox', 'one x'), ('1', 'ps2', 'one p'), ('1', None, 'one p'),
        ('2', 'xbox', 'two x'), ('2', None, 'two x'), ('3', None, 'three')]
    # an unfiltered accepted variant serves every filter value (0x5ec003)
    shared = dialogs({'text': 'f', 'platform': 'xbox', 'filter': '1'}, {'text': 'any'})
    assert S.dialog_platform_problems(shared) == []


def check_fixture(folder, root):
    validator = Validator.__new__(Validator)
    validator._scan = None
    validator.reg = {}
    data = C.encode_xmlb(root)
    for suffix in ('.xmlb', '.engb'):
        name = 'dialogs/invented_tip' + suffix
        (folder / ('invented_tip' + suffix)).write_bytes(data)
        validator.reg[name] = dict(rel=name, owner='zones', source='invented')
    validator.idx = SimpleNamespace(path=lambda name: folder / Path(name).name)
    validator.is_x1_source = lambda value: value == 'invented'
    check = Check('V-TBD', 'dialog platforms')
    validator.dialog_platforms(check)
    return check


def test_validator_rejects_console_only_dialogs_once_per_twin_pair():
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        root = console_tip()
        bad = check_fixture(folder, root)
        assert len(bad.errors) == 1 and 'invented_tip.engb' in bad.errors[0]
        S.convert(root, 'dialogs/invented_tip.eng')
        good = check_fixture(folder, root)
        assert not good.errors and good.counts['dialog_files_checked'] == 1
