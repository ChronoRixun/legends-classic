"""Synthetic mission starts: whole roster reset, guarded and before seating/menu."""
from xml1build import scripts_transform as T


def starts():
    return ['# ( "XML1 beginMission(fresh)" )', 'seatParty("magma", "", "", "" )',
            'loadMapKeepTeam("invented/start" )', '# ( "XML1 beginMission(continuation)" )',
            'loadZone("invented/next", "" )']


def test_fresh_start_resets_benched_records_before_any_party_selection():
    lines, changed = T.mission_vitals_at_markers(starts(), {'fresh': {'reset_vitals': True},
                                                          'continuation': {'reset_vitals': False}})
    assert changed == ['fresh']
    assert lines.count('     resetHeroVitals()') == 1
    assert lines.index('     resetHeroVitals()') < lines.index('seatParty("magma", "", "", "" )')
    assert T.mission_vitals_at_markers(lines, {'fresh': {'reset_vitals': True}})[0] == lines
    for dll, features, expected in [(True, (T.FT_FEATURE,), 1), (True, (), 0), (False, (), 0)]:
        trace, _ = T._run_forced(T.mission_vitals_block(), dll=dll, features=features)
        assert trace.count('resetHeroVitals') == expected
    assert not T.xml2fix_guard_problems(T.mission_vitals_block())
    assert T.xml2fix_guard_problems(['resetHeroVitals()'])


def test_nested_start_and_side_snapshot_order_preserve_continuations():
    source = ['pushParty("_ACTIVE_HERO_" )', 'if synthetic == 1'] + ['     ' + s for s in starts()] + ['endif']
    got, changed = T.mission_vitals_at_markers(source, {'fresh': {'reset_vitals': True}})
    assert changed == ['fresh']
    assert got[0] == source[0]
    assert got.index('          resetHeroVitals()') > got.index(source[0])
    assert got[-3:] == source[-3:]
    assert T.XML2FIX_API['resetHeroVitals'] == ('n', '')


def test_mission_header_unlocks_survive_reset_before_party_or_menu():
    for tail in (['seatParty("alpha", "", "", "" )', 'loadMapKeepTeam("invented/start" )'],
                 ['loadMapChooseTeam("invented/start" )']):
        body = ['# ( "XML1 beginMission(fresh)" )', 'setCurrentAct(1 )',
                'unlockCharacter("alpha", "" )'] + tail
        got, changed = T.mission_vitals_at_markers(body, {'fresh': {'reset_vitals': True}})
        assert changed == ['fresh']
        assert T.unlock_problems(got, {'fresh': ('alpha',)}) == ([], 1)
        assert got.index('unlockCharacter("alpha", "" )') < got.index('     resetHeroVitals()') < got.index(tail[0])
        assert T.mission_vitals_at_markers(got, {'fresh': {'reset_vitals': True}}) == (got, [])
