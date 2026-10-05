"""Synthetic regressions for the first game's per-mission hero unlocks (issue #55). Invented names only."""
import hashlib
import struct
import xml.etree.ElementTree as ET

from xml1build import scripts_transform as T
from xml1build import unlocks as U

WALK = bytes(range(U.WALK_LEN))                       # invented "code" for the walk function


def image(rows, walk=WALK, call_target=U.WALK_VA, strings_at=0x500000):
    """a fake VA space {va: bytes} with the walk code, the caller's call and the table rows."""
    mem = {U.WALK_VA: walk}
    rel = (call_target - (U.CALLER_VA + 5)) & 0xffffffff
    mem[U.CALLER_VA] = b'\xe8' + struct.pack('<I', rel)
    table = b''
    va = strings_at
    for label, hero in rows:
        ptrs = []
        for s in (label, hero):
            mem[va] = s.encode() + b'\0'
            ptrs.append(va)
            va += 64
        table += struct.pack('<II', *ptrs)
    mem[U.TABLE_VA] = table + struct.pack('<II', 0, 0)

    def rd(addr, n):
        for base, data in mem.items():
            if base <= addr and addr + n <= base + len(data):
                return data[addr - base:addr - base + n]
        for base, data in mem.items():               # a string read past its terminator: pad like a section would
            if base <= addr < base + len(data):
                return (data[addr - base:] + b'\0' * n)[:n]
        return None
    return rd


ROWS = [('begin', 'alpha'), ('', 'bravo'), ('', 'npcguy'), ('Stage1', 'charlie'), ('', 'delta'), ('stage2', 'echo')]
SHA = hashlib.sha1(WALK).hexdigest()


def test_table_is_read_in_order_and_cumulative_by_first_matching_label():
    rows = U.read_table(image(ROWS), walk_sha1=SHA)
    assert rows == ROWS
    assert U.cumulative(rows, 'begin') == ['alpha']
    assert U.cumulative(rows, 'STAGE1') == ['alpha', 'bravo', 'npcguy', 'charlie']      # case-insensitive
    assert U.cumulative(rows, 'stage2') == ['alpha', 'bravo', 'npcguy', 'charlie', 'delta', 'echo']
    assert U.cumulative(rows, 'nowhere') == []                                            # no row: nobody
    assert U.cumulative(rows, '') == ['alpha', 'bravo']                                   # first unlabelled row


def test_unknown_executable_fails_instead_of_guessing():
    for rd in (image(ROWS, walk=bytes(U.WALK_LEN)), image(ROWS, call_target=U.WALK_VA + 4)):
        try:
            U.read_table(rd, walk_sha1=SHA)
        except U.UnlockTableError:
            continue
        raise AssertionError('a different executable was accepted')


def test_mission_map_limits_to_playable_heroes_and_reports_missing_milestones():
    root = ET.fromstring('<missions><mission name="Intro" charunlock="begin"/><mission name="hub" '
                         'charunlock="stage1"/><mission name="hub" charunlock="stage2"/><mission name="odd"/>'
                         '</missions>')
    ms, missing = U.mission_milestones(root)
    assert ms == {'intro': 'begin', 'hub': 'stage1'} and missing == ['odd']               # first entry wins
    keep, drop = U.mission_unlocks(ms, ROWS, {'alpha', 'bravo', 'charlie'})
    assert keep == {'intro': ('alpha',), 'hub': ('alpha', 'bravo', 'charlie')}
    assert drop == {'hub': ('npcguy',)}


SEAT_BODY = ['# ( "XML1 beginMission(hubtwo)" )', 'setCurrentAct(1 )', 'unlockCharacter("guest", "" )',
             'unlockCharacter("alpha", "" )', T.FT_SEAT_COMMENT, 'x1ft = iadd(0, 0 )',
             'x1ft = xml2fixFeature("forcedteams" )', 'if x1ft == 1', '     seatParty("guest", "", "", "" )',
             '     loadMapKeepTeam("zone/a" )', 'else', '     loadMapChooseTeam("zone/a" )', 'endif']


def test_seat_only_hero_moves_into_the_team_menu_branch_in_every_copy():
    nested = ['if y == 1'] + ['     ' + l for l in SEAT_BODY] + ['endif']
    menu_body = ['# ( "XML1 beginMission(hubtwo)" )', 'unlockCharacter("guest", "" )', 'loadMapChooseTeam("zone/a" )']
    src = SEAT_BODY + nested + menu_body
    got, done = T.menu_only_unlocks(src, {'hubtwo': ('guest',)})
    assert done == [('hubtwo', 'guest'), ('hubtwo', 'guest')]
    first = got[:len(SEAT_BODY) + 1]
    assert 'unlockCharacter("guest", "" )' not in first[:4] and 'unlockCharacter("alpha", "" )' in first[:4]
    els = first.index('else')
    assert first[els + 1] == '     ' + T.MENU_UNLOCK_COMMENT % 'guest'
    assert first[els + 2] == '     unlockCharacter("guest", "" )' and first[els + 3] == '     loadMapChooseTeam("zone/a" )'
    assert got[-3:] == menu_body                                # a team-menu-only start keeps its unlock
    assert T.menu_only_unlocks(got, {'hubtwo': ('guest',)}) == (got, [])
    assert not T.menu_only_problems(got, {'hubtwo': ('guest',)})
    assert T.menu_only_problems(src, {'hubtwo': ('guest',)})


def test_mission_start_unlocks_are_identical_in_every_copy():
    src = ['# ( "XML1 beginMission(hubtwo)" )', 'setCurrentAct(1 )', 'loadMapKeepTeam("zone/a" )',
           'if y == 1', '     # ( "XML1 beginMission(hubtwo)" )', '     setCurrentAct(1 )',
           '     loadMapKeepTeam("zone/a" )', 'endif']
    got, done = T.unlock_at_mission_starts(src, {'hubtwo': ('alpha', 'bravo')})
    assert len(done) == 4
    a = [l.strip() for l in got[:6]]
    b = [l.strip() for l in got[8:14]]
    assert a == b and T.unlock_problems(got, {'hubtwo': ('alpha', 'bravo')}) == ([], 2)


def test_catchup_unlocks_follow_the_act_entry_and_are_idempotent():
    src = ['# Generated by rewrite_scripts.py', 'setCurrentAct(2 )', 'act("thing", "thing" )']
    got, done = T.catchup_unlocks(src, ('alpha', 'bravo'))
    assert done == ['alpha', 'bravo']
    assert got == src[:2] + [T.CATCHUP_COMMENT, 'unlockCharacter("alpha", "" )', 'unlockCharacter("bravo", "" )',
                             T.CATCHUP_END_COMMENT] + src[2:]
    assert T.catchup_unlocks(got, ('alpha', 'bravo')) == (got, [])
    plain = ['act("thing", "thing" )']
    assert T.catchup_unlocks(plain, ('alpha',))[0][:2] == [T.CATCHUP_COMMENT, 'unlockCharacter("alpha", "" )']


def test_analysis_of_xml1_unlock_sites_ignores_the_generated_unlocks():
    src = ['# ( "XML1 beginMission(hubtwo)" )', 'unlockCharacter("guest", "" )', T.UNLOCK_COMMENT % 'alpha',
           'unlockCharacter("alpha", "" )', 'loadMapKeepTeam("zone/a" )']
    body, _ = T.catchup_unlocks(src, ('bravo',))
    assert T.strip_generated_unlocks(body) == [src[0], src[1], src[4]]
