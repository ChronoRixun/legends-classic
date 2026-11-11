"""A side mission played in its caller's map folder must not clear the caller's mission flags at its start.

XML1 beginsidemission (xbe 0x18dd70) = pushsidemission + beginmission (0x18da90); neither clears mission vars or
flags (only restartMission 0x9a734 and a zone load in another map folder, 0x99b90, do). The converted start of
muir2_reboot cleared muir2 flag 6, so muir_in2's return script took its first-visit branch, faded to black and
never faded back in (Owen 11-11)."""
import collections

from xml1build.prepare import scripts as P3


def rewriter(side_calls):
    r = P3.Rewriter.__new__(P3.Rewriter)
    r.MISSIONS = {'caller': {'act': 4}, 'side': {'act': 5}, 'away': {'act': 5}}
    r.MISSION_DIRS = {'caller': {'isle/m2'}, 'side': {'isle/m2'}, 'away': {'isle/m2', 'elsewhere/fb'}}
    r.SIDE_CALLS = collections.defaultdict(set, side_calls)
    r._BEGIN_CACHE = {}
    r.SCRIPT_BY_REL = {}
    r.PROBLEMS = []
    caller_flag, side_var, shared_var = P3.VarInfo('m2'), P3.VarInfo('aligned'), P3.VarInfo('visit')
    caller_flag.kinds, caller_flag.bits = {'mflag'}, {6}
    side_var.kinds, shared_var.kinds = {'mvar'}, {'mvar'}
    r.VARS = {('m', 'm2'): caller_flag, ('m', 'aligned'): side_var, ('m', 'visit'): shared_var}
    r.STORAGE = {('m', 'm2'): P3.Storage('flag', 'm2', 0, 6), ('m', 'aligned'): P3.Storage('pack', 'x1v05', 19, 2),
                 ('m', 'visit'): P3.Storage('pack', 'x1v05', 30, 1)}
    r.VAR_DIRS = {('m', 'm2'): ['isle/m2'], ('m', 'aligned'): ['elsewhere/fb'], ('m', 'visit'): ['elsewhere/fb', 'isle/m2']}
    return r


def clears(lines):
    return sorted(x for x in lines if x.startswith('setGameFlag('))


def test_same_folder_side_mission_keeps_the_callers_flags():
    r = rewriter({'side': {'isle/m2/inside'}})
    assert clears(r.mission_begin_lines('side')) == []
    assert any('setCurrentAct' in x for x in r.mission_begin_lines('side'))


def test_a_plain_mission_start_still_clears_its_folder_vars():
    r = rewriter({'side': {'isle/m2/inside'}})
    assert 'setGameFlag("m2", 6, 0 )' in clears(r.mission_begin_lines('caller'))


def test_a_side_mission_clears_only_vars_of_folders_its_caller_never_uses():
    r = rewriter({'away': {'isle/m2/inside'}})
    got = clears(r.mission_begin_lines('away'))
    assert got == ['setGameFlag("x1v05", 20, 0 )', 'setGameFlag("x1v05", 21, 0 )']   # 'aligned' only


def test_the_cached_prepare_output_is_rebuilt():
    assert P3.VERSION >= 9
