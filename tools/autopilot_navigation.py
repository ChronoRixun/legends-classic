"""Runtime adapter for route feedback; only normal inputs plus explicitly counted assists."""
import math
import time
from autopilot_core import position
from autopilot_nav import Routes, calibrated, movement, assist_refusal


class Interrupted(Exception):
    pass


class Navigator:
    def __init__(self, driver, state):
        self.driver = driver
        self.zone = state['zone']
        self.graph = Routes(driver.plan.get('navigation'), driver.plan.get('anchors', []))
        self.mapping = None
        self.route = []
        self.index = 0
        self.goal_name = None
        self.best = math.inf
        self.progress_at = time.monotonic()
        self.recovery = 0
        self.used = set()
        self.wait_since = None

    def read(self):
        from autopilot import request
        s = request(self.driver.build, ['state'])[0]
        self.driver.state = s
        hero = next((h for h in s.get('party', []) if h.get('alive') and position(h)), None)
        if s.get('zone') != self.zone or not hero or s.get('script_controls_locked') is not False or s.get('popup') or s.get('menu_open') or s.get('conversation', {}).get('open'):
            raise Interrupted('zone, party or modal state changed')
        return s, position(hero)

    def key(self, keys, ms, restore=True):
        self.driver.command('script controlPlayerHeroWithAI(0)')
        self.driver.command(f'hold {keys} {int(ms)}')
        time.sleep(.12)
        try:
            return self.read()
        finally:
            if restore and self.driver.state.get('script_controls_locked') is False and self.driver.state.get('loading') is False:
                self.driver.command('script controlPlayerHeroWithAI(-1)')

    def calibrate(self):
        samples = {}
        try:
            for key in ('W', 'S', 'A', 'D'):
                _, before = self.read()
                _, after = self.key(key, 220, restore=False)
                samples[key] = (before, after, .22)
            self.mapping = calibrated(samples)
            self.driver.record('calibration', zone=self.zone, vectors=self.mapping, samples=samples)
        finally:
            if self.driver.state.get('script_controls_locked') is False and self.driver.state.get('loading') is False:
                self.driver.command('script controlPlayerHeroWithAI(-1)')

    def plan(self, here, goal):
        self.route = self.graph.route(here, goal['pos'])
        self.index = 0
        self.goal_name = goal['name']
        self.best = math.inf
        self.progress_at = time.monotonic()
        self.recovery = 0
        self.wait_since = None
        self.driver.record('route', zone=self.zone, goal=goal['name'], source=self.graph.source, points=self.route)

    def fail(self, kind, detail):
        self.driver.finding({'kind': kind, 'detail': detail})
        return False

    def teleport(self, state, here, target):
        from autopilot import request
        d = self.driver
        if d.opt.mode != 'assisted':
            return self.fail('assist_refused', 'assisted mode is not enabled')
        state, here = self.read()
        reason = assist_refusal(state, here, target, d.plan.get('barriers', []), self.used)
        if reason:
            return self.fail('assist_refused', reason)
        if d.assists.get(self.zone, 0) >= d.opt.max_assists:
            return self.fail('assist_limit', 'per-zone assist budget exhausted')
        # All axes run in one engine script frame. Three separate requests could fall
        # through the world between X and Y. Numeric arguments are generated locally.
        xyz = [round(v) for v in target['pos']]
        xyz[2] += 4
        script = r'\n\r'.join(f'setPos{axis}("_HERO1_",{v})' for axis, v in zip('XYZ', xyz))
        if len('runscript ' + script) > 127:
            return self.fail('assist_refused', 'coordinate command exceeds engine queue limit')
        d.assists[self.zone] = d.assists.get(self.zone, 0) + 1
        self.used.add(target['node'])
        d.record('assist', zone=self.zone, reason='blocked navigation step after feedback and sidestep',
                 start=here, destination=xyz, route_node=target['node'], count=d.assists[self.zone], command=script)
        request(d.build, ['script ' + script])
        time.sleep(.3)
        _, after = self.read()
        if math.dist(after, xyz) > 90:
            return self.fail('assist_failed', 'teleport did not reach the next route point')
        self.index += 1
        self.best = math.inf
        self.progress_at = time.monotonic()
        self.recovery = 0
        return True

    def step(self, state, hero, goal):
        d = self.driver
        try:
            here = position(hero)
            if self.goal_name != goal['name']:
                self.plan(here, goal)
            if self.mapping is None:
                retry = self.recovery >= 2
                stalled_since = self.progress_at
                self.calibrate()
                _, calibrated_here = self.read()
                if retry:
                    # Measuring input is not route progress. Preserve the stalled-step
                    # budget so calibration cannot postpone a finding/assist forever.
                    self.progress_at = stalled_since
                    self.recovery = 2
                else:
                    self.plan(calibrated_here, goal)
                return True
            # Engine-owned transitions may fire before the trigger centre is reached.
            for j in range(self.index, min(len(self.route), self.index + 4)):
                edge = self.route[j]
                if isinstance(edge['transition'], dict) and math.dist(here, edge['transition']['dest']) < 85:
                    d.record('script_transition_observed', transition=edge['transition'])
                    self.index = j + 1
                    self.mapping = None
                    self.best = math.inf
                    self.wait_since = None
                    self.progress_at = time.monotonic()
                    d.monitor.last_progress = self.progress_at
                    return True
            if self.index >= len(self.route):
                return True  # the ordinary use/goal handler owns activation
            target = self.route[self.index]
            if isinstance(target['transition'], dict):
                if self.wait_since is None:
                    self.wait_since = time.monotonic()
                if time.monotonic() - self.wait_since > 30:
                    return self.fail('script_transition_stall', 'walked to a transition trigger, but its follow-up did not occur')
                if target['transition']['use']:
                    d.command('script controlPlayerHeroWithAI(0)')
                    d.command('tap ' + d.opt.use_key)
                    d.command('script controlPlayerHeroWithAI(-1)')
                return True
            # Combat AI and engine-owned scripts can carry the party ahead of the
            # planned cursor. Replan from feedback instead of walking back or assisting.
            if math.dist(here, target['pos']) > 240:
                self.plan(here, goal)
                self.mapping = None
                d.record('navigation_recovery', action='replan_after_displacement', position=here)
                return True
            distance = math.dist(here, target['pos'])
            horizontal = math.dist(here[:2], target['pos'][:2])
            if horizontal <= 22 and abs(here[2]-target['pos'][2]) <= 65:
                d.record('route_point_reached', node=target['node'], position=here)
                self.index += 1
                self.best = math.inf
                self.recovery = 0
                self.progress_at = time.monotonic()
                d.monitor.last_progress = self.progress_at
                return True
            now = time.monotonic()
            if distance + 5 < self.best:
                self.best, self.progress_at = distance, now
            blocked = now - self.progress_at
            if blocked > 18:
                if d.opt.mode == 'assisted':
                    return self.teleport(state, here, target)
                return self.fail('navigation_stall', 'route step blocked after ordinary movement and sidestep attempts')
            if blocked > 6 and self.recovery == 0:
                # Measured perpendicular step, never a guessed world-to-camera direction.
                keys = list(self.mapping)
                desired = (target['pos'][0]-here[0], target['pos'][1]-here[1])
                side = min(keys, key=lambda k: abs(sum(x*y for x,y in zip(self.mapping[k], desired))))
                self.key(side, 180)
                self.recovery = 1
                d.record('navigation_recovery', action='sidestep', key=side, node=target['node'])
                return True
            if blocked > 10 and self.recovery == 1:
                # Re-measure if the camera changed or the original calibration was constrained.
                self.mapping = None
                self.recovery = 2
                return True
            move = movement(self.mapping, here, target['pos'])
            if move:
                keys, ms = move
                if target['transition'] == 4 or (blocked > 3 and target['pos'][2]-here[2] > 24):
                    keys += '+SPACE'
                self.key(keys, ms)
            return True
        except Interrupted:
            return True  # let the observer/UI/death handler see the next complete snapshot
        except ValueError as exc:
            return self.fail('route_unavailable', str(exc))
