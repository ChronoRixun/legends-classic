"""Synthetic regressions for editable mission parties (#76) and empty popup answers (#77)."""
import collections
import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from xml1build import common as C, scripts as S, scripts_transform as T
from xml1build.prepare import scripts as P3
from xml1build.validate import Check, Validator

PARTY = ['alpha', 'bravo', 'charlie', 'delta']
MENU = 'blackbirdMenu("FALSE", "loadMapKeepTeam(\'sample/outside\')", "TRUE" )'
BODY = ['# ( "XML1 beginMission(sample)" )', 'setCurrentAct(1 )', MENU]
INFO = {'act': 1, 'attrs': {'maxheros': '4', 'keepheroes': 'false', 'teamselect': 'true'},
        'required': [], 'recommended': [h.upper() for h in PARTY], 'restricted': []}
ROW = {'status': 'free', 'menu_seed': PARTY, 'seat': [], 'costume': 'default', 'heroes': '',
       'load': 'blackbirdMenu', 'zone': 'sample/outside'}


def test_menu_seed_comes_from_data_and_keeps_continuations_and_partial_lists():
    assert S._menu_seed_list(INFO, 'blackbirdMenu') == PARTY
    assert S._menu_seed_list(INFO, 'loadMapChooseTeam') == PARTY
    for field, value in [('keepheroes', 'true'), ('keepheroes', ''), ('maxheros', '3')]:
        info = copy.deepcopy(INFO)
        info['attrs'][field] = value
        assert S._menu_seed_list(info, 'blackbirdMenu') == []
    for field, value in [('recommended', PARTY[:3]), ('restricted', ['alpha'])]:
        info = copy.deepcopy(INFO)
        info[field] = value
        assert S._menu_seed_list(info, 'blackbirdMenu') == []
    assert S._menu_seed_list(INFO, 'loadMapKeepTeam') == []


def test_plan_seeds_a_free_mission_without_forcing_or_locking_it():
    class Context:
        def research_json(self, rel):
            return {'missions': {'sample': INFO}}

        def x1_zones(self):
            return ['sample/outside']

    ctx = Context()
    with patch.object(S, '_port_heroes', return_value=dict.fromkeys(PARTY)), \
            patch.object(S, '_mission_bodies', return_value={'sample': BODY}), \
            patch.object(S, 'skinset_args', return_value=('default', '')), \
            patch.object(S, '_x1_zone_convertible', return_value=True):
        plan = S.forced_party_plan(ctx)
        assert plan['sample']['status'] == 'free' and plan['sample']['seat'] == []
        assert plan['sample']['menu_seed'] == PARTY
        assert S.team_lock_plan(ctx)['missions']['sample'] == 0
    S._CACHES.pop(ctx)
    with patch.object(S, '_port_heroes', return_value=dict.fromkeys(PARTY[:3])), \
            patch.object(S, '_mission_bodies', return_value={'sample': BODY}), \
            patch.object(S, 'skinset_args', return_value=('default', '')), \
            patch.object(S, '_x1_zone_convertible', return_value=True):
        assert S.forced_party_plan(ctx)['sample']['menu_seed'] == []


def test_every_copy_seeds_before_the_editable_menu_with_safe_feature_fallback():
    nested = ['if answer == 1'] + ['     ' + line for line in BODY] + ['endif']
    src = BODY + nested
    got, changes = T.forced_party_in_bodies(src, {'sample': BODY}, {'sample': ROW})
    assert len(changes) == 2
    assert not T.menu_seed_problems(got, {'sample': ROW})
    assert T.forced_party_in_bodies(got, {'sample': BODY}, {'sample': ROW}) == (got, [])
    assert not T.xml2fix_guard_problems(got)
    single, _ = T.forced_party_in_bodies(BODY, {'sample': BODY}, {'sample': ROW})
    for present, enabled in [(True, True), (True, False), (False, False)]:
        trace = []
        T.run_pack_ops(single if present else T._drop_xml2fix(single), {},
                       funcs={'xml2fixFeature': lambda args: int(enabled)}, trace=trace)
        calls = [fn for fn, args in trace]
        assert calls.count('blackbirdMenu') == 1
        assert calls.count('seatParty') == int(present and enabled)
        assert 'loadMapKeepTeam' not in calls and 'loadMapChooseTeam' not in calls
        if enabled:
            # Read the party passed to the menu; actual replacement needs the runtime release check.
            args = next(args for fn, args in trace if fn == 'seatParty')
            slots = [s.strip().strip('"') for s in args.split(',')]
            assert slots == PARTY


def test_choose_team_fallback_is_seeded_and_validated_too():
    src, _ = T.blackbird_to_choose_team(BODY)
    row = dict(ROW, load='loadMapChooseTeam')
    got, _ = T.forced_party_in_bodies(src, {'sample': src}, {'sample': row})
    assert not T.menu_seed_problems(got, {'sample': row})
    assert T._run_forced(got)[0][-1] == 'loadMapChooseTeam'


def test_validator_rejects_missing_wrong_duplicate_and_guarded_menu_seeds():
    got, _ = T.forced_party_in_bodies(BODY, {'sample': BODY}, {'sample': ROW})
    seat = next(line for line in got if line.strip().startswith('seatParty('))
    defects = [BODY, [line for line in got if line != seat],
               [line.replace('"alpha"', '"wrong"') for line in got],
               got[:-1] + [seat, got[-1]], got + [seat],
               [line.replace('if x1ft == 1', 'if x1ft == 0') for line in got],
               got[:-2] + [got[-1], got[-2]]]
    for bad in defects:
        assert T.menu_seed_problems(bad, {'sample': ROW}), bad
    validator = Validator.__new__(Validator)
    stm = validator._statements(got)
    k = next(k for k, (_, line) in enumerate(stm) if line.startswith('seatParty('))
    ck = Check('V-TBD', 'recommended party')
    validator._v14c_seat(ck, S, {'sample': ROW}, dict.fromkeys(PARTY), got, stm, k,
                         'scripts/sample.py', 'sample', collections.Counter())
    assert not ck.errors


def test_empty_decline_action_survives_popup_conversion_and_binary_roundtrip():
    # XML1's empty option action is already faithfully represented by the generated PC dialog.
    # This protects the observed data contract; it is not a reproduction of the reported runtime failure.
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        loose, assets = folder / 'loose', folder / 'assets'
        source = ('createPopupDialog("Enter the invented outpost?")\r\n'
                  'addPopupDialogOption("Accept", "beginMission(\'sample\')")\r\n'
                  'addPopupDialogOption("Decline", "")\r\n'
                  'canCancelDialog("FALSE")\r\nshowPopupDialog()\r\n')
        files = {loose / '_fb_manifest.json': json.dumps({}),
                 loose / 'scripts/sample/prompt.py': source,
                 assets / 'data/strings.eng': '<strings/>'}
        for path, value in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value.encode('latin-1'))
        plan = {'missions': {'sample': {'act': 1, 'attrs': {'mapload': 'sample/interior'},
                                       'objectives': [], 'required': []}}}
        api1, api2 = P3.load_api()
        rw = P3.Rewriter(loose, assets, plan, api1, api2)
        lines, changed = rw.rewrite_script_lines(P3.parse_file(loose / 'scripts/sample/prompt.py'),
                                                 'scripts/sample/prompt.py')
        assert sum('createPopupDialogXml(' in line for line in lines) == 1
        assert not any('loadMap' in line or 'beginMission(' in line for line in lines)
        root = next(el for key, (ref, el) in rw.DIALOGS.items())
    decoded = C.decode_xmlb(C.encode_xmlb(root))
    options = list(decoded)
    assert decoded.get('cancancel') == 'false'
    assert options[0].get('script') == 'x1/missions/begin_sample'
    assert options[1].get('script', '') == ''
    assert decoded.get('scriptok', '') == decoded.get('scriptcancel', '') == ''
    assert [opt.get('script', '') for opt in options] == ['x1/missions/begin_sample', '']
