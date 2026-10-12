"""Issue #5 solo mode: XML1's enterSoloMode / exitSoloMode become xml2-fix setSoloMode(actor, 1 / 0). Synthetic names."""
import json
from collections import Counter

from xml1build import common as C
from xml1build import fix_ini
from xml1build import scripts_transform as T
from xml1build.prepare import scripts as P3
from xml1build.sources import REPO_ROOT


def _rewrite(statement, quote='"'):
    rewriter = P3.Rewriter.__new__(P3.Rewriter)
    rewriter.STATS = Counter()
    return rewriter.rewrite_call(P3.parse_line(1, statement).call, None, (), 'invented', quote, 0), rewriter.STATS


def test_enter_and_exit_become_set_solo_mode():
    lines, stats = _rewrite("enterSoloMode('_ACTIVATOR_')", "'")
    assert lines == ["setSoloMode('_ACTIVATOR_', 1 )"]
    assert stats['rule enterSoloMode -> setSoloMode'] == 1
    lines, stats = _rewrite('exitSoloMode("_ACTIVE_HERO_")')
    assert lines == ['setSoloMode("_ACTIVE_HERO_", 0 )']
    assert stats['rule exitSoloMode -> setSoloMode'] == 1


def test_solo_calls_are_no_longer_dropped():
    assert 'enterSoloMode' not in P3.DROP and 'exitSoloMode' not in P3.DROP
    assert P3.SOLO == {'enterSoloMode': 1, 'exitSoloMode': 0}


def test_set_solo_mode_is_a_registered_always_function():
    # unguarded in map data (like addSkillPoints): without the DLL the engine drops the statement at compile
    assert 'setSoloMode' in C.XML2FIX_ALWAYS_FUNCS
    assert T.XML2FIX_API['setSoloMode'] == ('n', 'ai')
    api = json.loads((REPO_ROOT / 'research' / 'scripts' / 'xml2fix_api.json').read_text(encoding='utf-8'))
    assert api['functions']['setSoloMode'] == {'args': 'ai', 'ret': 'n', 'func': 'xml2-fix', 'table': 'xml2-fix'}
    assert T._drop_xml2fix(['debug("x")', "setSoloMode('_ACTIVATOR_', 1 )"]) == ['debug("x")']
    # a bridge script calls it unguarded; a guarded-only function there is still reported
    assert T.xml2fix_guard_problems(["setSoloMode('_ACTIVE_HERO_', 0 )"]) == []
    assert T.xml2fix_guard_problems(['seatParty("invented", "", "", "" )'])


def test_port_requests_solo_mode_only_for_the_xml1_opening():
    assert 'SoloMode' in fix_ini.PORT_OWNED['Game']
    assert fix_ini.game_keys()['SoloMode'] == '1'
    assert 'SoloMode' not in fix_ini.game_keys(xml1_opening=False)


def test_validator_counts_solo_calls_and_rejects_xml1_names():
    from types import SimpleNamespace
    from xml1build.validate import Check, Validator
    validator = Validator.__new__(Validator)
    path = 'maps/inv/gap.engb'
    validator._scan = SimpleNamespace(
        inline={path: [('entity', 'actscript', "setSoloMode('_ACTIVATOR_', 1 )"),
                       ('entity', 'actscript', "enterSoloMode('_ACTIVATOR_')"),
                       ('entity', 'actscript', "setSoloMode('_ACTIVATOR_')")]},
        runscripts={}, files={path: {'rel': path}})
    validator.is_x1 = lambda _: True
    validator.data_items = lambda table: list(table.items())
    validator.script_set = lambda: set()
    check = Check('V-TBD', 'invented solo')
    validator.solo_mode_calls(check)
    assert len(check.errors) == 2
    assert check.counts['solo_mode_data_calls'] == 2 and check.counts['solo_mode_script_calls'] == 0
