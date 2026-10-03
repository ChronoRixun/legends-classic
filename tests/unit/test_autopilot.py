"""Synthetic autopilot regression tests. No engine, assets, saves or game text."""
import copy
import json
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET

import autopilot_core as a


def scene():
    root = ET.Element('map')
    def entity(name, cls, pos, **attrs):
        ET.SubElement(root, 'entity', name=name, classname=cls, **attrs)
        group = ET.SubElement(root, 'entinst', type=name)
        ET.SubElement(group, 'inst', name=name, pos=pos)
    entity('start_test', 'playerstartent', '0 0 0')
    entity('touch_test', 'gameent', '10 0 0', actontouch='true', actscript='fake/on_touch')
    entity('switch_test', 'gameent', '20 0 0', actonuse='true', actscript='fake/on_use')
    entity('exit_test', 'zonelinkent', '30 0 0', actonuse='true', nextzone='next_test')
    entity('hazard_test', 'affectableharment', '5 0 -100', actontouch='true')
    entity('pickup_test', 'inventoryent', '2 0 0', actontouch='true')
    return root


def snapshot(ms=0, zone='fake/room', z=0):
    hero = {'name': 'hero_test', 'entity_id': 3, 'x': 0., 'y': 0., 'z': float(z),
            'health': 10., 'max_health': 10., 'alive': True, 'z_velocity': 0.}
    return {'schema': 1, 'sampled_ms': ms, 'zone': zone, 'mode': 'in-zone', 'loading': False,
            'conversation': {'open': False, 'line_id': 0}, 'party': [hero], 'actors': []}


def observe(m, t, s, goal=None, plan=None, objectives=None, events=None):
    return m.observe(t, s, objectives or {'objectives': []}, events or {'events': []}, goal, plan or {})


def kinds(findings):
    return {f['kind'] for f in findings}


def test_autopilot_goal_extraction_and_link_order():
    plan = a.zone_plan('fake/room', scene(), {'fake/on_touch': 'objective("obj_test","COMPLETE")'})
    assert [g['name'] for g in plan['goals']] == ['touch_test', 'exit_test', 'switch_test']
    assert plan['goals'][0]['objectives'] == ['obj_test']
    assert plan['goals'][1]['next_zone'] == 'fake/next_test'
    assert plan['floor_lower_bound'] == -512
    assert 'hazard_test' not in json.dumps(plan)


def test_autopilot_script_graph_cycles_and_conditional_followups():
    scripts = {'fake/a': 'runscript("fake/b")\nstartConversation("conv_test")\nloadZone("fake/next","")',
               'fake/b': 'runscript("fake/a")\nobjective("obj_test","COMPLETE")'}
    seen, objs, _, _, followup = a.script_effects(['fake/a'], scripts)
    assert seen == {'fake/a', 'fake/b'} and objs == {'obj_test'} and followup == 'fake/next'
    scripts['fake/b'] += '\nif candidate == 1\n loadZone("fake/next", "")'
    assert a.script_effects(['fake/a'], scripts)[-1] is None


def test_autopilot_identifier_and_hint_safety():
    for value in ('../fake', 'x" )', 'a\nb', '', 'contains space'):
        try:
            a.identifier(value)
        except ValueError:
            pass
        else:
            assert False, value
    plan = a.zone_plan('fake/room', scene(), {})
    a.apply_hints(plan, {'order': ['exit_test'], 'responses': {'switch_test': 1}})
    assert plan['goals'][0]['name'] == 'exit_test'
    for hint in ({'script': 'anything'}, {'order': ['missing']}, {'responses': {'switch_test': -1}},
                 {'responses': {'switch_test': True}}):
        try:
            a.apply_hints(plan, hint)
        except ValueError:
            pass
        else:
            assert False, hint


def test_autopilot_outputs_refuse_git_ancestors():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / '.git').mkdir()
        try:
            a.external(root / 'nested' / 'future')
        except ValueError:
            pass
        else:
            assert False


def test_autopilot_cache_identity_tracks_map_and_script_content():
    import xmlb
    with tempfile.TemporaryDirectory() as d:
        root = Path(d);build = root / 'build'
        (build / 'Maps/fake').mkdir(parents=True);(build / 'Scripts/fake').mkdir(parents=True)
        (build / 'Maps/fake/room.XMLB').write_bytes(xmlb.encode(scene()))
        script = build / 'Scripts/fake/on_touch.py';script.write_text('objective("obj_test","COMPLETE")')
        p1, c1 = a.generate_cache(build, root / 'cache')
        p2, c2 = a.generate_cache(build, root / 'cache')
        assert p1 == p2 and c1 == c2 and len(c1['plans']) == 1
        script.write_text('objective("different_test","COMPLETE")')
        p3, c3 = a.generate_cache(build, root / 'cache')
        assert p3 != p1 and c3['fingerprint'] != c1['fingerprint']


def test_autopilot_cache_floor_includes_deep_navigation_cells():
    import xmlb
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        build = root / 'build'
        maps = build / 'Maps/fake'
        maps.mkdir(parents=True)
        zone_file = maps / 'room.XMLB'
        zone_file.write_bytes(xmlb.encode(scene()))
        nav = ET.Element('nav', cellsize='40')
        ET.SubElement(nav, 'c', p='0 0 -1000')
        nav_file = maps / 'room.NAVB'
        nav_file.write_bytes(xmlb.encode(nav))
        _, cache = a.generate_cache(build, root / 'cache')
        assert not cache['errors']
        plan = cache['plans']['fake/room']
        # An authored floor well below entity origins must not end the run.
        assert 'out_of_bounds' not in kinds(observe(a.Monitor(), 0, snapshot(z=-1000), plan=plan))
        assert 'out_of_bounds' in kinds(observe(a.Monitor(), 0, snapshot(z=-1600), plan=plan))
        assert plan['floor_lower_bound'] == -1512
        assert 'navigation' in plan['floor_source']
        # NAV heights work without selected map entities, too.
        zone_file.write_bytes(xmlb.encode(ET.Element('map')))
        _, cache = a.generate_cache(build, root / 'cache')
        assert cache['plans']['fake/room']['floor_lower_bound'] == -1512
        # Missing NAV retains the entity fallback and labels it honestly.
        zone_file.write_bytes(xmlb.encode(scene()))
        nav_file.unlink()
        _, cache = a.generate_cache(build, root / 'cache')
        fallback = cache['plans']['fake/room']
        assert fallback['floor_lower_bound'] == -512
        assert 'navigation' not in fallback['floor_source']


def test_autopilot_hang_is_not_masked_by_pipe_responses():
    m = a.Monitor(a.Thresholds(stale=3))
    observe(m, 0, snapshot(10))
    assert 'hang' in kinds(observe(m, 4, snapshot(10)))
    assert not observe(m, 5, snapshot(10))  # report once, don't flood


def test_autopilot_softlock_ignores_unproductive_motion():
    m = a.Monitor(a.Thresholds(stall=5));g = {'name': 'goal_test', 'pos': [100, 0, 0]}
    observe(m, 0, snapshot(0), g)
    s = snapshot(1);s['party'][0]['x'] = -10
    assert 'softlock' in kinds(observe(m, 6, s, g))
    m = a.Monitor(a.Thresholds(stall=5));observe(m, 0, snapshot(0), g)
    s['party'][0]['x'] = 30
    assert 'softlock' not in kinds(observe(m, 6, s, g))


def test_autopilot_falling_threshold_and_zone_reset():
    m = a.Monitor(a.Thresholds(falling=2));s = snapshot(0);s['party'][0]['z_velocity'] = -60
    observe(m, 0, s)
    s = copy.deepcopy(s);s['sampled_ms'] = 1;s['party'][0]['z'] = -50
    assert 'falling' in kinds(observe(m, 3, s))
    s['zone'] = 'fake/other';s['sampled_ms'] = 2
    assert 'falling' not in kinds(observe(m, 4, s))
    s['party'][0]['z'] = -600
    assert 'out_of_bounds' in kinds(observe(m, 5, s, plan={'floor_lower_bound': -512}))


def test_autopilot_missing_data_is_not_death_or_fall():
    m = a.Monitor();s = snapshot(0);s['party'][0].update(alive=None, health=None, z=None, z_velocity=None)
    assert not observe(m, 0, s)
    s['sampled_ms'] = 1
    assert not observe(m, 1, s)
    assert a.position(s['party'][0]) is None


def test_autopilot_death_and_history_window():
    m = a.Monitor();observe(m, 0, snapshot(0))
    s = snapshot(1);s['party'][0].update(alive=False, health=0)
    assert {'hero_death', 'game_over'} <= kinds(observe(m, 1, s))
    m.note(0, {'type': 'old_test'});m.note(31, {'type': 'new_test'})
    assert [e for _, e in m.history] == [{'type': 'new_test'}]


def test_autopilot_conversation_budget_and_followup():
    m = a.Monitor(a.Thresholds(conversation=3, followup=2))
    s = snapshot(0);s['conversation']['open'] = True
    g = {'name': 'goal_test', 'pos': [0, 0, 0], 'followup_zone': 'fake/next'}
    observe(m, 0, s, g)
    s = copy.deepcopy(s);s['sampled_ms'] = 1
    assert 'conversation_stall' in kinds(observe(m, 4, s, g))
    s['conversation']['open'] = False;s['sampled_ms'] = 2
    observe(m, 5, s, g)
    s['sampled_ms'] = 3
    assert 'conversation_followup_missing' in kinds(observe(m, 8, s, g))


def test_autopilot_objective_and_boss_stalls():
    m = a.Monitor(a.Thresholds(stall=4, boss=4))
    s = snapshot(0);s['actors'] = [{'name': 'boss_test', 'entity_id': 8, 'health': 30, 'alive': True, 'x': 10, 'y': 0, 'z': 0}]
    goal = {'name': 'goal_test', 'pos': [0, 0, 0], 'objectives': ['obj_test']}
    obj = {'objectives': [{'name': 'obj_test', 'shown': True, 'complete': False, 'count': 0}]}
    plan = {'boss_stats': ['boss_test']}
    observe(m, 0, s, goal, plan, obj)
    s = copy.deepcopy(s);s['sampled_ms'] = 1
    found = kinds(observe(m, 5, s, goal, plan, obj))
    assert {'objective_stall', 'boss_stall'} <= found


def test_autopilot_event_overflow_is_a_finding():
    assert 'observation_gap' in kinds(observe(a.Monitor(), 0, snapshot(), events={'events': [], 'dropped': 1}))


def test_autopilot_player_like_rejects_teleport_or_damage():
    import autopilot
    driver = autopilot.Driver.__new__(autopilot.Driver)
    class Options:
        mode = 'player-like'
    driver.opt = Options()
    for command in ('script copyOriginAndAngles("hero_test","goal_test")',
                    'script damage("boss_test",999)', 'script setInvulnerable("hero_test","TRUE")',
                    'console loadmap fake/other', 'script controlPlayerHeroWithAI(-1);damage("boss_test",9)'):
        try:
            driver.command(command)
        except ValueError:
            pass
        else:
            assert False


def test_autopilot_finding_kind_is_logged_without_argument_collision():
    import io
    import time
    import autopilot
    driver = autopilot.Driver.__new__(autopilot.Driver)
    class Options:
        mode = 'player-like'
    driver.opt = Options();driver.run_id = 'synthetic';driver.started = time.monotonic();driver.log = io.StringIO()
    driver.record('finding', kind='softlock', detail='synthetic')
    row = json.loads(driver.log.getvalue())
    assert row['type'] == 'finding' and row['kind'] == 'softlock'


def test_autopilot_popup_fallback_and_first_response():
    s = snapshot();s['popup'] = True
    assert a.ui_action(s, 0) == 'ENTER' and a.ui_action(s, 5) == 'ESCAPE'
    s['popup'] = False;s['conversation'] = {'open': True, 'responses': 3, 'selected': 2}
    assert a.ui_action(s) == 'UP'
    s['conversation']['selected'] = 0
    assert a.ui_action(s) == 'ENTER' and a.ui_action(s, desired=2) == 'DOWN'
    s['conversation']['selected'] = None
    try:
        a.ui_action(s)
    except ValueError:
        pass
    else:
        assert False


def test_autopilot_informational_popups_follow_progression_goals():
    plan = a.zone_plan('fake/room', scene(), {'fake/on_use': 'createPopupDialogXML("fake_tip")'})
    assert plan['goals'][-1]['name'] == 'switch_test' and plan['goals'][-1]['optional']
    assert next(i for i, g in enumerate(plan['goals']) if g['kind'] == 'link') < len(plan['goals']) - 1


def test_autopilot_distant_or_paused_boss_does_not_stall():
    m = a.Monitor(a.Thresholds(boss=2));s = snapshot(0)
    s['actors'] = [{'name': 'boss_test', 'entity_id': 8, 'health': 30, 'alive': True, 'x': 2000, 'y': 0, 'z': 0}]
    plan = {'boss_stats': ['boss_test']}
    observe(m, 0, s, plan=plan);s['sampled_ms'] = 1
    assert 'boss_stall' not in kinds(observe(m, 4, s, plan=plan))
    s['actors'][0]['x'] = 10;s['popup'] = True;s['sampled_ms'] = 2
    assert 'boss_stall' not in kinds(observe(m, 8, s, plan=plan))


def test_autopilot_exception_evidence_without_a_live_game():
    import io
    import time
    import autopilot
    with tempfile.TemporaryDirectory() as d:
        driver = autopilot.Driver.__new__(autopilot.Driver)
        class Options:
            mode = 'player-like'
        driver.opt = Options();driver.run_id = 'synthetic';driver.started = time.monotonic()
        driver.log = io.StringIO();driver.output = Path(d);driver.pid = None
        driver.findings = [];driver.goal = {'name': 'goal_test'};driver.state = snapshot()
        driver.monitor = a.Monitor();driver.monitor.note(time.monotonic(), {'type': 'synthetic_event'})
        driver.finding({'kind': 'softlock', 'detail': 'synthetic'})
        rows = [json.loads(x) for x in driver.log.getvalue().splitlines()]
        assert rows[0]['type'] == 'finding' and rows[0]['screenshot'] is None
        assert rows[0]['events_30s'] == [{'type': 'synthetic_event'}]
        exception = json.loads((Path(d) / 'exception-001.json').read_text())
        assert exception['model_called'] is False and exception['candidate_actions']


def test_autopilot_silent_event_history_expires():
    m = a.Monitor();m.note(0, {'type': 'old_test'})
    observe(m, 31, snapshot(31000))
    assert m.recent(31) == []
    observe(m, 40, snapshot(40000), events={'events': [{'type': 'stale_test', 'ms': 1000}]})
    assert m.recent(40) == []


def test_autopilot_approach_uses_only_plausible_existing_entities():
    goal = {'name': 'exit_test', 'pos': [1000, 0, 0]}
    anchors = [{'name': 'near_test', 'pos': [300, 0, 0]},
               {'name': 'high_test', 'pos': [400, 0, 150]},
               {'name': 'behind_test', 'pos': [-200, 0, 0]}]
    assert a.approach_target((0, 0, 0), goal, anchors)['name'] == 'near_test'
    assert a.approach_target((0, 0, 0), goal, anchors, {'near_test'}) == goal
    assert a.approach_target((900, 0, 0), goal, anchors) == goal


def test_autopilot_fixinput_observation_schema_and_errors():
    import os
    if os.name != 'nt':
        return  # the existing fixinput transport is Windows-only
    import fixinput
    old = fixinput._pipe
    class Stub:
        reply = '{"schema":1,"error":"synthetic unavailable"}'
        commands = []
        def ask(self, command):
            self.commands.append(command)
            return self.reply
    stub = Stub();fixinput._pipe = stub
    try:
        assert fixinput.state()['error'] == 'synthetic unavailable'
        assert stub.commands == ['state']
        for value in ('not json', '[]', '{"schema":9}'):
            stub.reply = value
            try:
                fixinput.events()
            except fixinput.PipeError:
                pass
            else:
                assert False
    finally:
        fixinput._pipe = old


def test_autopilot_workspace_run_lock_excludes_second_runner():
    import os
    if os.name != 'nt':
        return
    import autopilot
    from types import SimpleNamespace
    with tempfile.TemporaryDirectory() as d:
        root = Path(d);(root / 'build/_build').mkdir(parents=True)
        (root / 'build/_build/manifest.json').write_text('{}')
        (root / autopilot.MARKER).write_text(json.dumps({'schema': 1, 'id': 'synthetic', 'build': 'build'}))
        options = SimpleNamespace(workspace=root, mode='player-like', stall=90, conversation_timeout=60, boss_timeout=90)
        first = autopilot.Driver(options)
        try:
            try:
                second = autopilot.Driver(options)
            except RuntimeError:
                pass
            else:
                second.log.close();second.run_lock.close()
                assert False
        finally:
            first.log.close();first.run_lock.close()
