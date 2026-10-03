"""Player-like, opt-in Legends Classic test driver. See docs/AUTOPILOT.md.

prepare copies a completed build into a new, non-repository workspace. run only
accepts such an owned copy, uses a unique save folder, and never attaches to an
existing game. Findings and decoded goal caches stay in that workspace.
"""
from __future__ import annotations

import argparse
import configparser
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

from autopilot_core import (Monitor, Thresholds, distance, external, generate_cache,
                            identifier, position, ui_action)

HERE = Path(__file__).resolve().parent
MARKER = '.autopilot-owner.json'


def verified_json(path, data):
    encoded = json.dumps(data, indent=2, sort_keys=True)
    path.write_text(encoded, encoding='utf-8')
    if path.read_text(encoding='utf-8') != encoded:
        raise OSError('file verification failed')


def prepare(source, workspace):
    source, workspace = Path(source).resolve(), external(workspace)
    if workspace == source or source in workspace.parents or workspace in source.parents:
        raise ValueError('source and destination must not overlap')
    if not (source / '_build/manifest.json').is_file() or not (source / 'XMen2.exe').is_file():
        raise ValueError('source must be a completed builder output')
    if workspace.exists():
        raise ValueError('workspace must be new; refusing to overwrite an existing directory')
    workspace.mkdir(parents=True)
    shutil.copytree(source, workspace / 'build')
    owner = {'schema': 1, 'id': uuid.uuid4().hex, 'build': 'build', 'source_manifest':
             json.loads((source / '_build/manifest.json').read_text(encoding='utf-8')).get('digest')}
    verified_json(workspace / MARKER, owner)
    if not (workspace / 'build/XMen2.exe').is_file():
        raise OSError('copied build verification failed')
    print(str(workspace), flush=True)


def owned(workspace):
    workspace = external(workspace)
    marker = json.loads((workspace / MARKER).read_text(encoding='utf-8'))
    if marker.get('schema') != 1 or marker.get('build') != 'build' or not isinstance(marker.get('id'), str):
        raise ValueError('invalid ownership marker')
    build = (workspace / 'build').resolve()
    if build.parent != workspace or not (build / '_build/manifest.json').is_file():
        raise ValueError('owned build escaped the workspace or has no builder manifest')
    return workspace, build


def active_session():
    """WTS session state, not a guess based on quser's localized output."""
    if os.name != 'nt':
        return False
    import ctypes.wintypes as w
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    wt = ctypes.WinDLL('wtsapi32', use_last_error=True)
    wt.WTSQuerySessionInformationW.argtypes = [w.HANDLE, w.DWORD, ctypes.c_int,
                                               ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.DWORD)]
    wt.WTSFreeMemory.argtypes = [ctypes.c_void_p]
    session, size, ptr = w.DWORD(), w.DWORD(), ctypes.c_void_p()
    if not k.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)):
        return False
    if not wt.WTSQuerySessionInformationW(None, session.value, 8, ctypes.byref(ptr), ctypes.byref(size)):
        return False
    try:
        return size.value >= 4 and ctypes.cast(ptr, ctypes.POINTER(ctypes.c_int))[0] == 0
    finally:
        wt.WTSFreeMemory(ptr)


def pipe_worker(build, commands):
    import fixinput
    if not fixinput.use_build(build):
        raise ValueError('build has no enabled test pipe')
    try:
        result = []
        for command in commands:
            result.append(fixinput.observe(command) if command in ('state', 'objectives', 'events') else fixinput.pipe().ask(command))
        return result
    finally:
        fixinput.pipe().close()


def request(build, commands, timeout=8):
    """Isolate blocking Win32 pipe I/O in a killable helper; never hang the monitor."""
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '_pipe', str(build),
                             json.dumps(commands)], capture_output=True, text=True, timeout=timeout,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'pipe helper failed')
    return json.loads(result.stdout)


class Driver:
    def __init__(self, options):
        self.opt = options
        self.workspace, self.build = owned(options.workspace)
        # An OS lock releases on crashes; concurrent runners cannot overwrite this build's pipe/save settings.
        import msvcrt
        self.run_lock = (self.workspace / '.autopilot-run.lock').open('a+b')
        self.run_lock.write(b'1');self.run_lock.flush();self.run_lock.seek(0)
        try:
            msvcrt.locking(self.run_lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.run_lock.close()
            raise RuntimeError('another autopilot run owns this workspace') from None
        self.run_id = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
        self.output = self.workspace / 'runs' / self.run_id
        self.output.mkdir(parents=True)
        self.log = (self.output / 'run.jsonl').open('x', encoding='utf-8', buffering=1)
        self.monitor = Monitor(Thresholds(stall=options.stall, conversation=options.conversation_timeout,
                                          boss=options.boss_timeout))
        self.findings, self.visits, self.zones, self.seen_zones = [], [], {}, set()
        self.state, self.goal, self.plan = {}, None, {}
        self.started = time.monotonic()
        self.live_started = None
        self.process = None
        self.pid = None
        self.last_zone = None
        self.zone_started = self.started
        self.debug_offset = 0
        self.outcome = 'not_started'
        self.recoveries = 0
        self.assists = {}
        self.start_context = {'kind': 'new_game', 'requested_mission': getattr(options, 'entry_mission', None), 'queued': False, 'confirmed_zone': None}
        self.save_folder = 'Autopilot-' + self.run_id

    def record(self, event_type, **data):
        self.log.write(json.dumps({'type': event_type, 'mode': self.opt.mode, 'run_id': self.run_id,
                                   'elapsed': round(time.monotonic() - self.started, 3), **data}) + '\n')

    def command(self, command):
        if any(part in command for part in ('\n', '\r', ';', r'\n', r'\r')):
            raise ValueError('only one input command is allowed')
        if command.startswith('console ') and command != 'console loadgame':
            raise ValueError('only the normal load UI is allowed through the console')
        if command.startswith('script '):
            if command.count('(') != 1 or command.count(')') != 1 or not command.endswith(')'):
                raise ValueError('only one approved script call is allowed')
            fn = command[7:].split('(', 1)[0]
            allowed = {'controlPlayerHeroWithAI', 'moveToEntity', 'setAutoSpend', 'setAIActive'}
            if self.opt.mode == 'fast':
                allowed.add('copyOriginAndAngles')
            if fn not in allowed:
                raise ValueError('script not allowed in this test mode')
        self.record('action', command=command, goal=self.goal)
        return request(self.build, [command])[0]

    def finding(self, item):
        shot = self.output / ('finding-%03d.png' % (len(self.findings) + 1))
        screenshot, error = None, None
        if self.pid is not None:
            try:
                request(self.build, ['screenshot ' + str(shot)])
                if shot.is_file() and shot.stat().st_size:
                    screenshot = shot.relative_to(self.output).as_posix()
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                # Helper exceptions can include the command's absolute output path.
                error = f'screenshot request failed ({type(exc).__name__})'
        data = {**item, 'zone': self.state.get('zone'), 'state': self.state,
                'last_goal': self.goal, 'events_30s': self.monitor.recent(time.monotonic()),
                'screenshot': screenshot, 'screenshot_error': error}
        self.findings.append(data)
        self.record('finding', **data)
        exception = {'state': self.state, 'finding': item, 'screenshot': screenshot,
                     'goal': self.goal, 'candidate_actions': ['retry_current_goal', 'inspect_generated_goals',
                                                              'inspect_script_trace', 'stop_run'],
                     'model_called': False}
        self.record('exception', **exception)
        verified_json(self.output / ('exception-%03d.json' % len(self.findings)), exception)
        print(json.dumps({'finding': item, 'zone': self.state.get('zone'), 'mode': self.opt.mode}), flush=True)

    def debug_events(self):
        path = self.output / 'debugger.log'
        if not path.exists():
            return []
        with path.open('r', encoding='latin-1') as f:
            f.seek(self.debug_offset)
            lines = f.readlines()
            self.debug_offset = f.tell()
        events = []
        for line in lines:
            low = line.lower()
            if ('script' in low and ('error' in low or 'failed' in low)) or 'second-chance' in low:
                event = {'type': 'script_error' if 'second-chance' not in low else 'process_exception',
                         'detail': line.strip()[:1000], 'source': 'gamedbg'}
                self.record('debug_event', **event)
                events.append(event)
        return events

    def saved_games(self):
        import ctypes.wintypes as w
        buf = ctypes.create_unicode_buffer(260)
        shell = ctypes.WinDLL('shell32')
        if shell.SHGetFolderPathW(None, 5, None, 0, buf) != 0:
            return []
        folder = Path(buf.value) / 'Activision' / self.save_folder / 'Save'
        return sorted(folder.glob('saveslot*.save'), key=lambda p: p.stat().st_mtime, reverse=True)

    def recover(self):
        """Open the game's load UI; do not synthesize or copy player save data."""
        saves = self.saved_games()
        if not saves:
            self.finding({'kind': 'recovery_unavailable', 'detail': 'no save exists in this run\'s isolated save folder'})
            return False
        if len(saves) != 1:
            # UI slot/date ordering is not yet observed. Do not claim an arbitrary slot is latest.
            self.finding({'kind': 'recovery_unavailable', 'detail': 'multiple saves: newest-slot UI selection is not verified'})
            return False
        self.record('recovery_attempt', save=saves[0].name)
        self.command('console loadgame')
        # A single owned slot is unambiguous; menu acceptance remains normal input.
        deadline = time.monotonic() + 35
        saw_load = False
        while time.monotonic() < deadline:
            state = request(self.build, ['state'])[0]
            if state.get('loading') is True:
                saw_load = True
            if saw_load and state.get('loading') is False and any(h.get('alive') for h in state.get('party', [])):
                self.record('recovery_complete')
                self.monitor = Monitor(self.monitor.limits)
                return True
            self.command('tap ENTER')
            time.sleep(1.5)
        self.finding({'kind': 'recovery_failed', 'detail': 'load UI did not produce a live party'})
        return False

    def launch(self):
        import current_zone
        if not active_session():
            raise RuntimeError('interactive session is disconnected or unavailable')
        if current_zone.build_pids(self.build):
            raise RuntimeError('owned build already has a running game; refusing to attach')
        # Each run starts with its own save/profile directory; always start New Game from the menu.
        subprocess.run([sys.executable, str(HERE / 'harness.py'), 'install', str(self.build),
                        '--dll', str(Path(self.opt.dll).resolve()), '--mode', 'windowed', '--width', '1280',
                        '--height', '720', '--save-folder', self.save_folder,
                        '--pipe-name', 'autopilot-' + self.run_id, '--limits'], check=True, capture_output=True)
        cp = configparser.ConfigParser();cp.read(self.build / 'xml2-fix.ini')
        # The virtual test pad ignores physical pad input while this window is in
        # the background. Keyboard pulses still go through this build's own pipe.
        cp['Test']['VirtualPads'] = '1'
        cp['Game']['WindowTitle'] = 'Autopilot ' + self.opt.mode + ' ' + self.run_id
        with (self.build / 'xml2-fix.ini').open('w', encoding='utf-8') as stream:
            cp.write(stream)
        verified = configparser.ConfigParser();verified.read(self.build / 'xml2-fix.ini')
        if verified['Test'].get('VirtualPads') != '1' or verified['Game'].get('WindowTitle') != cp['Game']['WindowTitle']:
            raise RuntimeError('test input/title isolation did not persist')
        if (cp['Game']['SaveFolder'] != self.save_folder or cp['Display']['Mode'] != 'windowed'
                or cp['Display']['Width'] != '1280' or cp['Display']['Height'] != '720'):
            raise RuntimeError('harness installation verification failed')
        self.process = subprocess.Popen([sys.executable, str(HERE / 'gamedbg.py'), str(self.output / 'debugger.log'),
                                         str(self.build / 'XMen2.exe')], stdout=subprocess.DEVNULL,
                                        stderr=(self.output / 'debugger-stderr.log').open('w'),
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            # gamedbg records the exact CreateProcess PID; never choose an arbitrary process by image name.
            import re
            debug_path = self.output / 'debugger.log'
            if debug_path.exists():
                first_line = debug_path.read_text(encoding='latin-1').splitlines()[:1]
                match = re.search(r'started pid (\d+)', first_line[0] if first_line else '')
                if match and int(match[1]) in current_zone.build_pids(self.build):
                    self.pid = int(match[1])
            if self.pid:
                self.record('launched', pid=self.pid, save_folder=self.save_folder)
                return
            if self.process.poll() is not None:
                raise RuntimeError('debugger/game exited at launch')
            time.sleep(.25)
        raise RuntimeError('owned game PID did not appear')

    def run(self):
        import current_zone
        _, cache = generate_cache(self.build, self.workspace / 'cache', self.opt.hints)
        self.record('start', fingerprint=cache['fingerprint'], expected_zones=self.opt.expect_zone,
                    cache_errors=cache['errors'], no_model_api=True)
        self.launch()
        self.live_started = time.monotonic()
        entry_targets = set()
        if self.opt.entry_mission:
            from autopilot_core import calls
            entry = identifier(self.opt.entry_mission)
            if not entry.startswith('x1/missions/begin_') or '/' in entry[len('x1/missions/begin_'):]:
                raise ValueError('entry must name a generated begin-mission script')
            source = self.build / 'Scripts' / (entry + '.py')
            for fn, args in calls(source.read_text(encoding='latin-1')):
                if fn in ('loadmapkeepteam', 'loadmapchooseteam', 'loadzone') and args:
                    entry_targets.add(args[0].lower())
            if not entry_targets:
                raise ValueError('mission entry has no inspectable initial zone')
            self.start_context['kind'] = 'mission_start'
        entered_game, last_input, last_move, goal_since, visited = False, 0., 0., None, set()
        arrival_since, handed_party = None, None
        navigator = None
        failures_at_start = 0
        popup_since = None
        samples = 0
        while time.monotonic() - self.live_started < self.opt.seconds:
            now = time.monotonic()
            if not active_session():
                self.finding({'kind': 'environment_unavailable', 'detail': 'interactive session disconnected'})
                self.outcome = 'interrupted';return
            if self.process.poll() is not None or self.pid not in current_zone.build_pids(self.build):
                self.finding({'kind': 'process_exit', 'detail': 'owned game or debugger exited unexpectedly'})
                self.outcome = 'findings';return
            try:
                state, objectives, events = request(self.build, ['state', 'objectives', 'events'])
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                if not entered_game and now - self.live_started < 40:
                    time.sleep(.5);continue
                self.finding({'kind': 'hang', 'detail': str(exc)})
                self.outcome = 'findings';return
            waiting_for_sample = False
            for command, response in zip(('state', 'objectives', 'events'), (state, objectives, events)):
                error = response.get('error')
                if response.get('schema') != 1:
                    error = 'unexpected API schema'
                elif error == 'no game-thread sample' and not entered_game and now - self.live_started < 40:
                    waiting_for_sample = True
                    continue
                if error:
                    self.finding({'kind': 'api_unavailable', 'detail': f'{command}: {error}'})
                    self.outcome = 'harness_blocked';return
            if waiting_for_sample:
                time.sleep(.5);continue
            if 'script_controls_locked' not in state:
                self.finding({'kind': 'api_unavailable', 'detail': 'companion API lacks the required script-control-lock observation'})
                self.outcome = 'harness_blocked';return
            self.state = state
            events.setdefault('events', []).extend(self.debug_events())
            self.record('sample', state=state, objectives=objectives, events=events)
            samples += 1
            zone = state.get('zone')
            if zone != self.last_zone:
                if self.last_zone:
                    self.zones[self.last_zone] = self.zones.get(self.last_zone, 0) + now - self.zone_started
                self.last_zone, self.zone_started = zone, now
                self.plan = cache['plans'].get((zone or '').lower(), {})
                self.goal = None;goal_since = None;arrival_since = None;handed_party = None
                navigator = None
                if zone:
                    self.seen_zones.add(zone.lower())
                print(json.dumps({'zone': zone, 'mode': self.opt.mode, 'goals': len(self.plan.get('goals', []))}), flush=True)
            found = self.monitor.observe(now, state, objectives, events, self.goal, self.plan)
            if found:
                for item in found:
                    self.finding(item)
                if all(f['kind'] in ('hero_death', 'game_over') for f in found) and self.recoveries < self.opt.reloads:
                    self.recoveries += 1
                    if self.recover():
                        self.goal = None;goal_since = None;handed_party = None;navigator = None;continue
                self.outcome = 'findings';return
            mode = state.get('mode')
            conv = state.get('conversation', {})
            menu = (state.get('menu') or '').lower()
            if state.get('popup'):
                if popup_since is None:
                    popup_since = now
            else:
                popup_since = None
            if now - last_input >= 1.5:
                desired = self.plan.get('responses', {}).get((self.goal or {}).get('name'), 0)
                action = ui_action(state, now - popup_since if popup_since is not None else 0, desired)
                if action:
                    self.command('tap ' + action);last_input = now
                elif mode == 'menu' and not entered_game and menu == 'main':
                    self.command('tap ENTER');last_input = now
            if mode != 'in-zone' or state.get('loading') or conv.get('open') or state.get('popup') or state.get('menu_open'):
                time.sleep(self.opt.poll);continue
            if self.opt.entry_mission and not self.start_context['queued']:
                self.record('mission_start_requested', script=self.opt.entry_mission, source_zone=zone)
                request(self.build, ['script ' + self.opt.entry_mission])
                self.start_context['queued'] = True
                time.sleep(.5);continue
            if self.opt.entry_mission and self.start_context['confirmed_zone'] is None:
                if (zone or '').lower() not in entry_targets:
                    time.sleep(.5);continue
                self.start_context['confirmed_zone'] = zone
                self.record('mission_start_confirmed', **self.start_context)
            if state.get('script_controls_locked') is not False:
                time.sleep(self.opt.poll);continue
            entered_game = True
            party = tuple((h.get('name'), h.get('entity_id')) for h in state.get('party', []) if h.get('name'))
            if party != handed_party:
                self.command('script setAutoSpend(1,1)')
                self.command('script setAIActive("_ALL_HEROES_","TRUE")')
                self.command('script controlPlayerHeroWithAI(-1)')
                handed_party = party
            lead = next((h for h in state.get('party', []) if h.get('alive') is True and position(h)), None)
            if lead is None:
                failures_at_start += 1
                if failures_at_start >= 10:
                    self.finding({'kind': 'harness_blocked', 'detail': 'no readable live party position'})
                    self.outcome = 'harness_blocked';return
                time.sleep(self.opt.poll);continue
            failures_at_start = 0
            if self.goal is None:
                self.goal = next((g for g in self.plan.get('goals', []) if (zone, g['name']) not in visited), None)
                if self.goal is None:
                    self.finding({'kind': 'harness_blocked', 'detail': 'no unvisited generated goal; campaign completion is not established'})
                    self.outcome = 'harness_blocked';return
                goal_since, arrival_since = now, None
                self.record('goal_selected', goal=self.goal)
                print(json.dumps({'goal': self.goal['name'], 'kind': self.goal['kind'], 'zone': zone}), flush=True)
            if now - goal_since > self.opt.goal_timeout:
                self.finding({'kind': 'goal_stall', 'detail': 'goal not reached/activated through engine pathfinding before deadline'})
                self.outcome = 'findings';return
            d = distance(position(lead), self.goal['pos'])
            party_ids = {h.get('entity_id') for h in state.get('party', [])}
            enemies = [a for a in state.get('actors', []) if a.get('alive') is True and a.get('entity_id') not in party_ids
                       and (a.get('name') or '').lower() in self.plan.get('enemy_stats', [])
                       and distance(position(a), position(lead)) < 120]
            # Proximity across a street/wall is not evidence of an active fight.
            if enemies:
                # AI owns combat. Health changes are observed; no damage/kill script calls.
                self.record('combat', enemy_ids=[a['entity_id'] for a in enemies])
                time.sleep(self.opt.poll);continue
            if d <= self.goal.get('radius', 65):
                if arrival_since is None:
                    arrival_since = now
                if self.goal['kind'] in ('use', 'objective_use', 'link') and now - last_input > 1.5:
                    self.command('script controlPlayerHeroWithAI(0)')
                    self.command('tap ' + self.opt.use_key)
                    self.command('script controlPlayerHeroWithAI(-1)');last_input = now
                if self.goal['kind'] == 'combat_objective' and now - last_input > 2:
                    self.command('script controlPlayerHeroWithAI(0)')
                    self.command('hold NUMPAD4 1000')
                    self.command('script controlPlayerHeroWithAI(-1)');last_input = now
                completed = {o['name'] for o in objectives.get('objectives') or [] if o.get('complete')}
                waiting_objective = bool(set(self.goal.get('objectives', [])) - completed)
                if now - arrival_since >= 3 and self.goal['kind'] != 'link' and not waiting_objective:
                    visited.add((zone, self.goal['name']))
                    self.visits.append({'zone': zone, 'goal': self.goal['name'], 'status': 'visited_not_proven_complete'})
                    self.record('goal_visited', goal=self.goal)
                    self.goal = None
            else:
                arrival_since = None
                if self.opt.mode == 'fast':
                    if now - last_move >= 3:
                        name = identifier(self.goal['name'])
                        self.command(f'script copyOriginAndAngles("_HERO1_","{name}")')
                        last_move = now
                else:
                    from autopilot_navigation import Navigator
                    if navigator is None:
                        navigator = Navigator(self, state)
                    if not navigator.step(state, lead, self.goal):
                        self.outcome = 'findings';return
            time.sleep(self.opt.poll)
        if not samples:
            self.finding({'kind': 'api_unavailable', 'detail': 'live budget expired without a complete observation'})
            self.outcome = 'harness_blocked';return
        self.outcome = 'time_budget'

    def finish(self):
        import current_zone
        # Only this launch's PID, checked against its owned build. Never close someone else's game.
        if self.pid and self.pid in current_zone.build_pids(self.build):
            subprocess.run(['taskkill', '/PID', str(self.pid), '/F'], capture_output=True)
        if self.process:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate()
        now = time.monotonic()
        if self.last_zone:
            self.zones[self.last_zone] = self.zones.get(self.last_zone, 0) + now - self.zone_started
        missing = [z for z in self.opt.expect_zone if z.lower() not in self.seen_zones]
        result = {'mode': self.opt.mode, 'outcome': self.outcome, 'zones_seconds': self.zones,
                  'start_context': self.start_context, 'assists_per_zone': {z:self.assists.get(z,0) for z in self.zones}, 'findings': self.findings, 'goals_visited': self.visits, 'expected_zones_not_reached': missing,
                  'acceptance': 'not established', 'elapsed': now - self.started}
        verified_json(self.output / 'summary.json', result)
        lines = ['# Autopilot run', '', f'Mode: {self.opt.mode}. Outcome: {self.outcome}.',
                 'Campaign acceptance: **not established**. Visiting an entity is not proof of completing its objective.', '',
                 '| Zone | Seconds |', '|---|---:|']
        lines += [f'| {z} | {seconds:.1f} |' for z, seconds in self.zones.items()]
        lines += ['', f'Findings: {len(self.findings)}.', 'Assists per zone: ' + json.dumps(result['assists_per_zone'], sort_keys=True), 'Start context: ' + json.dumps(self.start_context, sort_keys=True)]
        lines += [f'- {f["kind"]}: {f["detail"]} (zone: {f.get("zone")})' for f in self.findings]
        if missing:
            lines += ['', 'Requested coverage not reached: ' + ', '.join(missing)]
        lines += ['', 'Evidence: run.jsonl, summary.json, exception records and available screenshots in this folder.',
                  'No model API was called. Ground contact and engine script-error hooks are unavailable; debugger output supplements observations.']
        text = '\n'.join(lines) + '\n'
        (self.output / 'summary.md').write_text(text, encoding='utf-8')
        if (self.output / 'summary.md').read_text(encoding='utf-8') != text:
            raise OSError('summary verification failed')
        self.record('end', outcome=self.outcome, missing_coverage=missing)
        self.log.close()
        self.run_lock.close()
        print(str(self.output / 'summary.md'), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare');p.add_argument('--source-build', required=True);p.add_argument('--workspace', required=True)
    p = sub.add_parser('plan');p.add_argument('workspace');p.add_argument('--hints')
    p = sub.add_parser('run');p.add_argument('workspace');p.add_argument('--dll', required=True)
    p.add_argument('--mode', choices=('player-like', 'assisted', 'fast'), default='player-like')
    p.add_argument('--seconds', type=float, default=300);p.add_argument('--poll', type=float, default=.5)
    p.add_argument('--stall', type=float, default=90);p.add_argument('--goal-timeout', type=float, default=120)
    p.add_argument('--conversation-timeout', type=float, default=60);p.add_argument('--boss-timeout', type=float, default=90)
    p.add_argument('--entry-mission', help='explicit generated mission-start seed; always recorded')
    p.add_argument('--max-assists', type=int, default=8)
    p.add_argument('--reloads', type=int, default=1);p.add_argument('--use-key', default='E')
    p.add_argument('--hints');p.add_argument('--expect-zone', action='append', default=[])
    p = sub.add_parser('_pipe');p.add_argument('build');p.add_argument('commands')
    args = parser.parse_args(argv)
    if args.action == '_pipe':
        print(json.dumps(pipe_worker(args.build, json.loads(args.commands))));return 0
    if args.action == 'prepare':
        prepare(args.source_build, args.workspace);return 0
    if args.action == 'plan':
        workspace, build = owned(args.workspace)
        path, cache = generate_cache(build, workspace / 'cache', args.hints)
        print(json.dumps({'cache': str(path), 'zones': len(cache['plans']), 'errors': cache['errors']}));return 0
    if os.name != 'nt':
        parser.error('live driving requires Windows')
    import math
    if not all(math.isfinite(v) and v > 0 for v in (args.seconds, args.poll, args.stall, args.goal_timeout, args.conversation_timeout, args.boss_timeout)):
        parser.error('timeouts must be positive')
    import re
    if not re.fullmatch(r'[A-Za-z0-9_+]+', args.use_key):
        parser.error('use-key must be a DirectInput key name')
    if args.max_assists < 0:
        parser.error('max-assists must be nonnegative')
    driver = Driver(args)
    try:
        driver.run()
    except (Exception, KeyboardInterrupt) as exc:
        driver.outcome = 'harness_error'
        driver.finding({'kind': 'harness_error', 'detail': str(exc)})
    finally:
        driver.finish()
    return 0 if driver.outcome == 'time_budget' and not driver.findings else 1


if __name__ == '__main__':
    raise SystemExit(main())
