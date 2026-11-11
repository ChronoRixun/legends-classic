"""A plain mission start from the map folder of the zone it loads must not clear that folder's mission flags.

XML1 beginmission (xbe 0x18da90) clears no mission var or flag; the store is cleared only when a zone of another map
folder loads (0x99b90) and in restartMission (0x9a734). The converted start cleared every var of the started
mission's folders, so a start inside one folder (mansion4_grso from subbasement4, sewers_hub from sewers1_1_2,
mansion3_uniform from subbasement3b) wiped flags XML1 keeps: questions already asked came back (review 11-11, after
the muir2_reboot black screen fixed for side missions)."""
import collections

from xml1build.lib.bescript import parse_line
from xml1build.prepare import scripts as P3


def rewriter():
    r = P3.Rewriter.__new__(P3.Rewriter)
    r.MISSIONS = {'home': {'act': 5, 'attrs': {'mapload': 'house/h4/back'}},
                  'away': {'act': 6, 'attrs': {'mapload': 'trip/t1/start'}},
                  'twice': {'act': 5, 'attrs': {'mapload': 'house/h4/raid', 'scriptstart': ''}}}
    r.MISSION_DIRS = {'home': {'house/h4'}, 'away': {'trip/t1'}, 'twice': {'house/h4'}}
    r.SIDE_CALLS = collections.defaultdict(set)
    r.INLINE_BEGINS = collections.defaultdict(list)
    r.HELPER_REFS = collections.defaultdict(set)
    r.STATS = collections.Counter()
    r._BEGIN_CACHE = {}
    r.SCRIPT_BY_REL = {}
    r.PROBLEMS = []
    asked, trip = P3.VarInfo('h4'), P3.VarInfo('t1')
    asked.kinds, asked.bits = {'mflag'}, {2, 5}
    trip.kinds, trip.bits = {'mflag'}, {1}
    r.VARS = {('m', 'h4'): asked, ('m', 't1'): trip}
    r.STORAGE = {('m', 'h4'): P3.Storage('flag', 'h4', 0, 5), ('m', 't1'): P3.Storage('flag', 't1', 0, 1)}
    r.VAR_DIRS = {('m', 'h4'): ['house/h4'], ('m', 't1'): ['trip/t1']}
    return r


def clears(lines):
    return sorted(x for x in lines if x.startswith('setGameFlag('))


def begin(r, m, zones):
    return r.rewrite_call(parse_line(0, f'beginMission("{m}" )').call, None, set(zones), 'w', '"', 0)


def test_a_script_start_inside_the_loaded_folder_keeps_its_flags():
    r = rewriter()
    got = begin(r, 'twice', {'house/h4/basement'})
    assert clears(got) == []
    assert 'setCurrentAct(5 )' in got


def test_a_start_from_another_folder_still_clears_as_the_folder_change_does():
    r = rewriter()
    assert clears(begin(r, 'twice', {'briefing/b6/room'})) == ['setGameFlag("h4", 2, 0 )', 'setGameFlag("h4", 5, 0 )']
    assert clears(begin(r, 'away', {'trip/t1/x', 'house/h4/basement'})) == ['setGameFlag("t1", 1, 0 )']


def test_mixed_or_unknown_callers_keep_the_clearing_start():
    r = rewriter()
    assert clears(begin(r, 'twice', {'house/h4/basement', 'briefing/b6/room'})) != []
    assert clears(begin(r, 'twice', set())) != []


def test_the_shared_begin_file_keeps_only_when_every_inline_site_is_in_the_folder():
    r = rewriter()
    assert r.rewrite_inline("beginMission('twice')", 'conv a', frozenset({'house/h4/basement'})) == \
        'x1/missions/begin_twice'
    assert clears(r.mission_begin_lines('twice', keep_dirs=r.begin_file_keep('twice'))) == []
    r.rewrite_inline("beginMission('twice')", 'popup b', frozenset())
    assert clears(r.mission_begin_lines('twice', keep_dirs=r.begin_file_keep('twice'))) != []
    assert r.begin_file_keep('home') == frozenset()          # no inline site: menus get the clearing start


def test_the_cached_prepare_output_is_rebuilt():
    assert P3.VERSION >= 10


def test_later_passes_match_an_inlined_copy_that_keeps_its_flags():
    from xml1build import scripts_transform as T
    body = ['# ( "XML1 beginMission(twice)" )', 'setGameFlag("h4", 2, 0 )', 'setGameFlag("h4", 5, 0 )',
            'setCurrentAct(5 )', 'loadMapKeepTeam("house/h4/raid" )']
    kept = ['x = 1', '# ( "XML1 beginMission(twice)" )', 'setCurrentAct(5 )', 'loadMapKeepTeam("house/h4/raid" )', 'y = 2']
    got, ch = T.choose_team_in_bodies(kept, {'twice': body})
    assert got[3] == 'loadMapChooseTeam("house/h4/raid" )' and got[4] == 'y = 2' and len(ch) == 1
    other = kept[:2] + ['objective("z", "EOBJCMD_SHOW" )'] + kept[2:]
    assert T.choose_team_in_bodies(other, {'twice': body})[1] == []     # any other header difference still mismatches
    assert T.choose_team_in_bodies(body, {'twice': body})[0][-1] == 'loadMapChooseTeam("house/h4/raid" )'
