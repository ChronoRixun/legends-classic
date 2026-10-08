"""Synthetic release-identity and registry-demand regressions."""
from xml1build import fix_ini as FI
from xml1build import release_identity as RI
from xml1build import talent_budget as TB


def test_release_tokens_are_unique_four_characters():
    rows = RI.HISTORY
    RI.validate_history(rows)
    tokens = [r.token for r in rows]
    assert len(set(tokens)) == len(tokens)
    assert all(len(t) == 4 and t != '1.30' for t in tokens)
    assert FI.online_keys(port_identity=True)['GameVersion'] == RI.game_version()


def test_unassigned_release_refuses():
    try:
        RI.game_version(content_version=999999, catalogue_revision=7)
    except ValueError as e:
        assert 'unassigned' in str(e)
    else:
        assert False, 'an unassigned build must not reuse a lobby token'


def test_history_is_append_only():
    old = (RI.Identity('fictional-1', 901, 3, 'A901'),)
    later = old + (RI.Identity('fictional-2', 902, 4, 'A902'),)
    RI.validate_history(later, previous=old)
    for changed in ((later[1], later[0]), (later[1],), old + (RI.Identity('fictional-2', 902, 4, 'A901'),)):
        try:
            RI.validate_history(changed, previous=old)
        except ValueError:
            pass
        else:
            assert False, 'history mutation / token collision accepted'


def test_catalogue_identity_must_match_release():
    try:
        RI.game_version(content_version=16, catalogue_revision=999)
    except ValueError:
        pass
    else:
        assert False


def test_registry_boundaries_and_duplicate_files():
    counts = {'data/shared_talents': 92, 'data/talents/arena': 8, 'data/talents/extra': 1}
    assert TB.demand(['data/shared_talents', 'data/talents/arena'], counts)['talents'] == 100
    assert TB.demand(['data/shared_talents'] * 3, counts)['talents'] == 92
    assert not TB.problems(TB.demand(['data/shared_talents', 'data/talents/arena'], counts))
    assert TB.problems(TB.demand(list(counts), counts))
    assert not TB.problems({'talents': 99, 'files': 9})
    assert TB.problems({'talents': 99, 'files': 10})


def test_registry_accounts_for_zone_npc_and_party():
    counts = {'shared': 50, 'zone': 20, 'npc': 20, 'hero': 11, 'small': 1}
    total, party = TB.worst_party({'shared', 'zone', 'npc'}, {'large': {'hero'}, 'small': {'small'}}, counts, size=1)
    assert total['talents'] == 101 and party == ('large',)
    assert TB.problems(total)


def test_registry_missing_talent_file_is_error():
    try:
        TB.demand(['unknown'], {})
    except ValueError as e:
        assert 'unknown' in str(e)
    else:
        assert False

def test_registry_file_cap_has_its_own_worst_party():
    counts = {'base': 80, 'large': 20, **{f'tiny{i}': 1 for i in range(9)}}
    total, party = TB.worst_party({'base'}, {'large': {'large'}, 'many': {f'tiny{i}' for i in range(9)}}, counts, size=1)
    assert total['talents'] == 100 and party == ('large',)
    assert total['files'] == 10 and total['file_party'] == ('many',)
    assert any('talent files' in p for p in TB.problems(total))

def test_registry_names_shared_by_files_register_once():
    files = {'first': {'shared', 'alpha'}, 'second': {'shared', 'beta'}}
    assert TB.demand(files, files) == {'talents': 3, 'files': 2}

def test_issued_candidate_keeps_its_token():
    assert RI.game_version(content_version=16, catalogue_revision=2) == 'LC20'
