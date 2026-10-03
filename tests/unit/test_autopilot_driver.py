"""Synthetic driver tests: launch, processes and pipe I/O are always mocked."""
import copy
import io
import json
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import autopilot


def observations():
    return [
        {'schema': 1, 'script_controls_locked': False, 'mode': 'menu',
         'menu': 'synthetic_menu', 'zone': None},
        {'schema': 1, 'objectives': []},
        {'schema': 1, 'events': []},
    ]


@contextmanager
def simulated_run(setup_seconds=0, seconds=2):
    clock = SimpleNamespace(now=100.)
    def advance(seconds):
        clock.now += seconds
    driver = autopilot.Driver.__new__(autopilot.Driver)
    driver.opt = SimpleNamespace(hints=None, expect_zone=[], entry_mission=None,
                                 seconds=seconds, poll=.5, mode='player-like')
    driver.started = clock.now
    driver.workspace = Path('synthetic_workspace')
    driver.build = driver.workspace / 'build'
    driver.process = Mock(poll=Mock(return_value=None))
    driver.pid = 123
    driver.last_zone = None
    driver.state = {}
    driver.goal = None
    driver.plan = {}
    driver.findings = []
    driver.finding = driver.findings.append
    driver.monitor = Mock(observe=Mock(return_value=[]))
    driver.record = Mock()
    driver.debug_events = Mock(return_value=[])
    driver.launch = Mock(side_effect=lambda: advance(setup_seconds / 2))
    cache = {'fingerprint': 'synthetic', 'errors': [], 'plans': {}}
    def generate_cache(*_):
        advance(setup_seconds / 2)
        return None, cache
    with patch.dict('sys.modules', {'current_zone': SimpleNamespace(build_pids=lambda _: [123])}), \
         patch.object(autopilot, 'generate_cache', side_effect=generate_cache), \
         patch.object(autopilot, 'active_session', return_value=True), \
         patch.object(autopilot, 'request', side_effect=lambda *_: copy.deepcopy(observations())) as request, \
         patch.object(autopilot.time, 'monotonic', side_effect=lambda: clock.now), \
         patch.object(autopilot.time, 'sleep', side_effect=advance):
        yield driver, clock, request


def test_autopilot_driver_rejects_each_observation_error_and_schema():
    # Positive control: healthy responses are sampled without findings.
    with simulated_run() as (driver, _, _):
        driver.run()
        assert driver.outcome == 'time_budget' and not driver.findings
        assert driver.monitor.observe.called
    for index, command in ((1, 'objectives'), (2, 'events'), (0, 'state')):
        for failure in ({'schema': 1, 'error': 'unsupported synthetic sample'}, {'schema': 2}):
            with simulated_run() as (driver, _, request):
                responses = observations()
                responses[index] = failure
                request.side_effect = lambda *_: copy.deepcopy(responses)
                driver.run()
                assert driver.outcome == 'harness_blocked', (command, failure, driver.outcome)
                assert command in driver.findings[0]['detail']
                assert not driver.monitor.observe.called


def test_autopilot_driver_waits_for_all_observers_at_startup():
    for index in range(3):
        with simulated_run() as (driver, _, request):
            first = observations()
            first[index] = {'schema': 1, 'error': 'no game-thread sample'}
            request.side_effect = [first] + [observations() for _ in range(4)]
            driver.run()
            assert driver.outcome == 'time_budget' and not driver.findings
            assert driver.monitor.observe.call_count == 3


def test_autopilot_driver_startup_grace_is_bounded_and_cannot_hide_other_errors():
    with simulated_run(seconds=41) as (driver, clock, request):
        missing = [{'schema': 1, 'error': 'no game-thread sample'}] * 3
        request.side_effect = lambda *_: copy.deepcopy(missing)
        driver.run()
        assert driver.outcome == 'harness_blocked'
        assert clock.now - driver.started == 40
        assert not driver.monitor.observe.called
    with simulated_run() as (driver, _, request):
        responses = observations()
        responses[0] = {'schema': 1, 'error': 'no game-thread sample'}
        responses[2] = {'schema': 1, 'error': 'unsupported synthetic sample'}
        request.side_effect = lambda *_: copy.deepcopy(responses)
        driver.run()
        assert driver.outcome == 'harness_blocked' and request.call_count == 1
        assert 'events' in driver.findings[0]['detail']
        assert not driver.monitor.observe.called


def test_autopilot_driver_setup_does_not_consume_live_budget_or_grace():
    with simulated_run(setup_seconds=120) as (driver, clock, request):
        request.side_effect = [RuntimeError('synthetic pipe not ready')] + [observations() for _ in range(4)]
        driver.run()
        assert driver.outcome == 'time_budget' and not driver.findings
        assert driver.monitor.observe.call_count == 3
        assert clock.now - driver.started == 122
    with simulated_run(setup_seconds=120) as (driver, _, request):
        first = observations()
        first[2] = {'schema': 1, 'error': 'no game-thread sample'}
        request.side_effect = [first] + [observations() for _ in range(4)]
        driver.run()
        assert driver.outcome == 'time_budget' and not driver.findings
        assert driver.monitor.observe.call_count == 3


def test_autopilot_driver_no_observation_is_never_a_clean_budget_exit():
    for response in (RuntimeError('synthetic pipe not ready'),
                     [{'schema': 1, 'error': 'no game-thread sample'}] * 3):
        with simulated_run() as (driver, _, request):
            request.side_effect = ([response] * 5)
            driver.run()
            assert driver.outcome == 'harness_blocked'
            assert driver.findings and not driver.monitor.observe.called


def test_autopilot_driver_pipe_failures_do_not_serialize_helper_paths():
    private = str(Path('synthetic_private_workspace').resolve())
    for failure in (subprocess.TimeoutExpired(['python', private, '_pipe', private], 8),
                    RuntimeError('helper failed in ' + private)):
        with simulated_run(seconds=41) as (driver, _, request):
            request.side_effect = failure
            driver.run()
            assert driver.outcome == 'findings' and driver.findings[0]['kind'] == 'hang'
            assert private not in driver.findings[0]['detail'].replace('\\\\', '\\')
            assert type(failure).__name__ in driver.findings[0]['detail']


def test_autopilot_driver_action_timeout_is_redacted_by_top_level_handler():
    private = str(Path('synthetic_private_workspace').resolve())
    failure = subprocess.TimeoutExpired(['python', private, '_pipe', private, 'tap E'], 8)
    findings = []
    driver = SimpleNamespace(run=Mock(side_effect=failure), finish=Mock(), finding=findings.append,
                             findings=findings, outcome='not_started')
    with patch.object(autopilot, 'Driver', return_value=driver), patch.object(autopilot.os, 'name', 'nt'):
        assert autopilot.main(['run', 'synthetic_workspace', '--dll', 'synthetic.dll']) == 1
    assert findings[0]['kind'] == 'harness_error' and driver.finish.called
    assert private not in findings[0]['detail'].replace('\\\\', '\\')
    assert 'TimeoutExpired' in findings[0]['detail']


def test_autopilot_driver_uses_use_activated_fight_and_boss_triggers():
    import xml.etree.ElementTree as ET
    from autopilot_core import zone_plan
    from test_autopilot import snapshot
    for boss in (False, True):
        for activation in ('actonuse', 'actontouch'):
            root = ET.Element('map')
            ET.SubElement(root, 'entity', name='switch_type', classname='gameent',
                          actscript='fake/trigger', **{activation: 'true'})
            group = ET.SubElement(root, 'entinst', type='switch_type')
            ET.SubElement(group, 'inst', name='switch_test', pos='0 0 0')
            ET.SubElement(root, 'entity', name='spawn_type', classname='monsterspawner', character='enemy_test')
            group = ET.SubElement(root, 'entinst', type='spawn_type')
            ET.SubElement(group, 'inst', name='spawn_test', pos='100 0 0')
            source = 'spawn("spawn_test")'
            if boss:
                source += '\nshowHealthBar("spawn_test")'
            plan = zone_plan('fake/room', root, {'fake/trigger': source})
            assert plan['goals'][0]['kind'] == ('boss_trigger' if boss else 'fight_trigger')
            with simulated_run() as (driver, _, request):
                driver.opt.goal_timeout = 120
                driver.opt.use_key = 'E'
                driver.command = Mock()
                driver.last_zone = 'fake/room'
                driver.plan = plan
                state = {**snapshot(), 'script_controls_locked': False}
                request.side_effect = lambda *_: [copy.deepcopy(state), observations()[1], observations()[2]]
                with patch('sys.stdout', new_callable=io.StringIO):
                    driver.run()
                commands = [call.args[0] for call in driver.command.call_args_list]
                assert ('tap E' in commands) == (activation == 'actonuse'), (boss, activation, commands)
                assert not driver.findings


def test_autopilot_driver_invalid_requested_hints_block_before_launch():
    import xmlb
    from autopilot_core import generate_cache
    from test_autopilot import scene
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        build = root / 'build'
        (build / 'Maps/fake').mkdir(parents=True)
        (build / 'Maps/fake/room.XMLB').write_bytes(xmlb.encode(scene()))
        hints = root / 'hints'
        (hints / 'fake').mkdir(parents=True)
        hint_file = hints / 'fake/room.json'
        for content in ('{', '{"order":["absent_test"]}', '{"responses":{"switch_test":-1}}',
                        '{"order":"exit_test"}', '{"order":["exit_test"]}'):
            hint_file.write_text(content)
            valid = content == '{"order":["exit_test"]}'
            with simulated_run() as (driver, _, request), \
                 patch.object(autopilot, 'generate_cache', side_effect=generate_cache):
                driver.workspace, driver.build, driver.opt.hints = root, build, hints
                driver.run()
                if valid:
                    assert driver.outcome == 'time_budget' and driver.launch.called
                    _, cache = generate_cache(build, root / 'cache', hints)
                    assert cache['plans']['fake/room']['goals'][0]['name'] == 'exit_test'
                else:
                    assert driver.outcome == 'harness_blocked'
                    assert driver.findings and not driver.launch.called and not request.called
                    assert str(root) not in driver.findings[0]['detail']
        for unavailable in (root / 'absent_hints', hint_file):
            with simulated_run() as (driver, _, _), \
                 patch.object(autopilot, 'generate_cache', side_effect=generate_cache):
                driver.workspace, driver.build, driver.opt.hints = root, build, unavailable
                driver.run()
                assert driver.outcome == 'harness_blocked' and not driver.launch.called
        read_bytes = Path.read_bytes
        def unreadable_hint(path):
            if path == hint_file:
                raise PermissionError('synthetic unreadable hint: ' + str(path))
            return read_bytes(path)
        with simulated_run() as (driver, _, _), \
             patch.object(autopilot, 'generate_cache', side_effect=generate_cache), \
             patch.object(Path, 'read_bytes', unreadable_hint):
            driver.workspace, driver.build, driver.opt.hints = root, build, hints
            driver.run()
            assert driver.outcome == 'harness_blocked' and not driver.launch.called
            assert 'PermissionError' in driver.findings[0]['detail']
            assert str(root) not in driver.findings[0]['detail']


def test_autopilot_driver_recovery_accepts_verified_transition_without_loading_sample():
    from test_autopilot import snapshot
    dead = snapshot(1000)
    dead['party'][0].update(alive=False, health=0)
    live = snapshot(2000)
    loading = {**snapshot(2500), 'loading': True}
    survivor = {**dead['party'][0], 'name': 'survivor_test', 'entity_id': 4, 'alive': True, 'health': 10}
    partial = copy.deepcopy(dead)
    partial['party'].append(survivor)
    revived = copy.deepcopy(live)
    revived['party'].append(survivor)
    for before, samples, expected in (
        (dead, [live], True),
        (partial, [revived], True),
        (live, [{**snapshot(3000), 'zone': 'fake/next'}], True),
        (live, [loading, snapshot(3000)], True),
        (partial, [{**partial, 'sampled_ms': 2000}], False),
        (live, [snapshot(3000)], False),
        (dead, [snapshot(1000)], False),
        (dead, [snapshot(500)], False),
        (dead, [{**live, 'mode': 'menu', 'menu_open': True}], False),
        (dead, [{**live, 'error': 'unsupported synthetic sample'}], False),
    ):
        with simulated_run() as (driver, _, request):
            driver.state = copy.deepcopy(before)
            driver.monitor = autopilot.Monitor()
            driver.saved_games = Mock(return_value=[Path('saveslot1.save')])
            driver.command = Mock()
            responses = iter(samples)
            last = samples[-1]
            request.side_effect = lambda *_: [copy.deepcopy(next(responses, last))]
            assert driver.recover() is expected, (before, samples)
            if expected:
                assert driver.state == last
                assert driver.command.call_args_list[-1].args[0] in ('console loadgame', 'tap ENTER')
                assert driver.command.call_count == len(samples)
                assert not driver.findings
            else:
                assert driver.findings[-1]['kind'] == 'recovery_failed'


def test_autopilot_driver_evidence_uses_relative_screenshot_paths():
    for capture in ('success', 'timeout', 'error'):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as folder:
            output = Path(folder).resolve()
            driver = autopilot.Driver.__new__(autopilot.Driver)
            driver.opt = SimpleNamespace(mode='player-like', expect_zone=[])
            driver.run_id = 'synthetic'
            driver.started = autopilot.time.monotonic()
            driver.output = output
            driver.build = output / 'build'
            driver.pid = 123
            driver.process = None
            driver.state, driver.goal = {}, None
            driver.findings, driver.visits = [], []
            driver.zones, driver.seen_zones, driver.assists = {}, set(), {}
            driver.last_zone = None
            driver.start_context = {}
            driver.outcome = 'findings'
            driver.monitor = autopilot.Monitor()
            driver.run_lock = io.StringIO()
            driver.log = (output / 'run.jsonl').open('w', encoding='utf-8')
            def screenshot(build, commands):
                assert build == driver.build
                target = Path(commands[0].removeprefix('screenshot '))
                assert target.is_absolute() and target.parent == output
                if capture == 'timeout':
                    raise subprocess.TimeoutExpired(commands, 8)
                if capture == 'error':
                    raise RuntimeError('synthetic capture failed: ' + str(target))
                target.write_bytes(b'synthetic capture')
            with patch.object(autopilot, 'request', side_effect=screenshot), \
                 patch.dict('sys.modules', {'current_zone': SimpleNamespace(build_pids=lambda _: [])}), \
                 patch('sys.stdout', new_callable=io.StringIO):
                try:
                    driver.finding({'kind': 'synthetic', 'detail': 'synthetic finding'})
                    driver.finish()
                finally:
                    driver.log.close()
            expected = 'finding-001.png' if capture == 'success' else None
            records = [json.loads(line) for line in (output / 'run.jsonl').read_text().splitlines()]
            evidence = [row for row in records if row['type'] in ('finding', 'exception')]
            evidence += [json.loads((output / 'exception-001.json').read_text()),
                         json.loads((output / 'summary.json').read_text())['findings'][0]]
            assert len(evidence) == 4
            for item in evidence:
                assert item['screenshot'] == expected
            for artifact in ('run.jsonl', 'summary.json', 'summary.md', 'exception-001.json'):
                text = (output / artifact).read_text()
                assert str(output) not in text and json.dumps(str(output))[1:-1] not in text

