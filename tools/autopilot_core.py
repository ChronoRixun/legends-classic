"""Portable planning and observation rules for the opt-in player-like test driver.

Only invented fixtures belong in tests. Decoded maps, plans, run states and images
belong in a non-repository workspace selected by the caller.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import struct
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

SCHEMA = 1
IDENTIFIER = re.compile(r'[A-Za-z0-9_./-]{1,80}\Z')
CALL = re.compile(r'\b([A-Za-z_]\w*)\s*\(([^()\r\n]*)\)')
STRING = re.compile(r"""["']([^"'\r\n]*)["']""")


def external(path):
    """Reject output anywhere inside a Git checkout, including through junctions."""
    path = Path(path).resolve()
    for parent in (path, *path.parents):
        if (parent / '.git').exists():
            raise ValueError('generated output must be outside every Git checkout')
    return path


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value) or '..' in value.split('/'):
        raise ValueError('unsafe or missing engine identifier')
    return value


def vector(value):
    try:
        v = tuple(float(x) for x in value.split()) if isinstance(value, str) else tuple(value)
        return v if len(v) == 3 and all(math.isfinite(x) for x in v) else None
    except (ValueError, TypeError):
        return None


def position(actor):
    return vector(tuple(actor.get(k) for k in ('x', 'y', 'z')))


def distance(a, b):
    return math.dist(a, b) if a is not None and b is not None else math.inf


def calls(source):
    """Conservative literal-call inspection; never execute game scripts."""
    # Drop comments; a hash inside a quoted script argument is not a goal identifier.
    for line in source.splitlines():
        for match in CALL.finditer(line.split('#', 1)[0]):
            yield match[1].lower(), STRING.findall(match[2])


@dataclass
class Goal:
    name: str
    kind: str
    pos: tuple[float, float, float]
    radius: float = 65.0
    next_zone: str | None = None
    objectives: list[str] = field(default_factory=list)
    followup_zone: str | None = None
    sources: list[str] = field(default_factory=list)
    optional: bool = False
    requires_use: bool = False


def script_effects(refs, scripts):
    pending = list(refs)
    seen, objectives, targets, bosses, destinations = set(), set(), set(), set(), set()
    conversation = False
    conditional = False
    while pending and len(seen) < 128:
        ref = pending.pop().lower().removesuffix('.py').replace('\\', '/')
        if ref in seen:
            continue
        seen.add(ref)
        source = scripts.get(ref, '')
        conditional |= bool(re.search(r'^\s*(?:if|else|while)\b', source, re.M))
        for fn, args in calls(source):
            if fn == 'runscript' and args:
                pending.append(args[0])
            elif fn in ('objective', 'immediateobjective') and len(args) > 1 and args[1].lower() == 'complete':
                objectives.add(args[0])
            elif fn in ('activate', 'deactivate', 'spawn', 'setactive', 'setenabled') and args:
                targets.add(args[0].lower())
            elif fn in ('setdefaulttarget', 'showhealthbar') and args and args[0]:
                bosses.add(args[0].lower())
            elif fn.startswith('startconversation'):
                conversation = True
            elif fn in ('loadzone', 'loadmapkeepteam', 'loadmapchooseteam') and args:
                destinations.add(args[0])
    followup = next(iter(destinations)) if conversation and not conditional and len(destinations) == 1 else None
    return seen, objectives, targets, bosses, followup


def zone_plan(zone, root, scripts):
    """Derive candidates, not a proof of reachability or puzzle solvability."""
    zone = identifier(zone)
    definitions = {e.get('name', '').lower(): {k.lower(): v for k, v in e.attrib.items()}
                   for e in root.iter('entity')}
    instances, merged_instances = [], []
    for group in root.iter('entinst'):
        base = definitions.get(group.get('type', '').lower(), {})
        for inst in group:
            if inst.tag.lower() == 'inst':
                attrs = {**base, **{k.lower(): v for k, v in inst.attrib.items()}}
                if attrs.get('name'):
                    merged_instances.append(attrs)
                pos = vector(attrs.get('pos', ''))
                if pos and attrs.get('name'):
                    instances.append((attrs, pos))
    instance_counts = Counter(a['name'].lower() for a in merged_instances)
    by_instance = {a['name'].lower(): a for a in merged_instances if instance_counts[a['name'].lower()] == 1}
    name_counts = Counter(a['name'].lower() for a, _ in instances)
    anchors = [{'name': a['name'], 'pos': p} for a, p in instances
               if name_counts[a['name'].lower()] == 1 and IDENTIFIER.fullmatch(a['name'])
               and a.get('classname', '').lower() in ('ent', 'waypointent', 'gameent', 'playerstartent')]
    barriers = []
    for attrs, pos in instances:
        gate = any(word in (attrs.get('classname', '') + ' ' + attrs['name']).lower()
                   for word in ('door', 'elevator', 'bridge', 'lift', 'gate'))
        gate |= any(k.endswith('script') and v for k, v in attrs.items())
        gate |= attrs.get('actontouch', '').lower() == 'true' and bool(attrs.get('target'))
        if gate:
            try:
                ext = [float(v) for v in attrs.get('extents', '-72 -72 -64 72 72 160').split()]
                angle = vector(attrs.get('orient', '0 0 0'))[2]
                if len(ext) != 6 or not all(math.isfinite(v) for v in ext):
                    raise ValueError('invalid extents')
                corners = [(x*math.cos(angle)-y*math.sin(angle), x*math.sin(angle)+y*math.cos(angle))
                           for x in (ext[0], ext[3]) for y in (ext[1], ext[4])]
                bounds = [pos[0]+min(v[0] for v in corners), pos[1]+min(v[1] for v in corners), pos[2]+ext[2],
                          pos[0]+max(v[0] for v in corners), pos[1]+max(v[1] for v in corners), pos[2]+ext[5]]
                barriers.append({'name': attrs['name'], 'bounds': bounds})
            except (ValueError, TypeError):
                barriers.append({'name': attrs['name'], 'bounds': [pos[0]-96,pos[1]-96,pos[2]-96,pos[0]+96,pos[1]+96,pos[2]+160]})
    spawners = {a['name'].lower(): a for a, _ in instances if 'spawner' in a.get('classname', '').lower()}
    enemy_stats = sorted({a['character'].lower() for a in spawners.values()
                          if a.get('character') and a.get('monster_team', '').lower() not in ('hero', 'none')})
    goal_candidates, starts, heights, boss_stats = [], [], [], set()
    transitions = []
    by_name = {a['name'].lower(): p for a, p in instances if name_counts[a['name'].lower()] == 1}
    # Scope ambient scripts to this zone's own directory plus explicitly referenced scripts.
    prefix = zone.rsplit('/', 1)[0] + '/'
    ambient = [k for k in scripts if k.startswith(prefix) or k.startswith('x1/' + prefix)]
    _, _, _, ambient_bosses, _ = script_effects(ambient, scripts)
    for attrs, pos in instances:
        cls = attrs.get('classname', '').lower()
        if cls == 'playerstartent':
            starts.append(pos)
        if cls in ('playerstartent', 'waypointent', 'zonelinkent', 'gameent'):
            heights.append(pos[2])
        name = attrs['name']
        try:
            identifier(name)
        except ValueError:
            continue
        refs = [v for k, v in attrs.items() if k.endswith('script') and v and '(' not in v]
        # Follow relay targets offline as well as script calls; cycles stay bounded.
        relay_queue = [attrs.get('target', '')]
        relays = set()
        while relay_queue and len(relays) < 128:
            target = relay_queue.pop().lower()
            if not target or target in relays:
                continue
            relays.add(target)
            linked = by_instance.get(target, {})
            refs.extend(v for k, v in linked.items() if k.endswith('script') and v and '(' not in v)
            relay_queue.append(linked.get('target', ''))
        seen, objectives, targets, bosses, followup = script_effects(refs, scripts)
        targets |= relays
        # Literal, unconditional party moves are engine-owned transitions, not assists.
        if not any(re.search(r'^\s*(?:if|else|while)\b', scripts.get(ref, ''), re.M) for ref in seen):
            for ref in seen:
                for fn, args in calls(scripts.get(ref, '')):
                    dst = None
                    if fn == 'copyoriginandangles' and len(args) > 1 and args[0].upper() in ('_HERO1_', '_ACTIVE_HERO_', '_ALL_HEROES_'):
                        dst = args[1]
                    elif fn == 'moveheroestoent' and args:
                        dst = args[0]
                    if dst and dst.lower() in by_name:
                        transitions.append({'name': name, 'src': pos, 'dest': by_name[dst.lower()],
                                            'use': attrs.get('actonuse', '').lower() == 'true'})
        bosses |= ambient_bosses
        for target, spawn in spawners.items():
            if target in bosses or spawn.get('monster_name', '').lower() in bosses or spawn.get('monstername', '').lower() in bosses:
                if spawn.get('character'):
                    boss_stats.add(spawn['character'].lower())
        touch = attrs.get('actontouch', '').lower() == 'true'
        use = attrs.get('actonuse', '').lower() == 'true'
        next_zone = attrs.get('nextzone')
        # Exclude contact-damage props and inventory pickups from progression goals.
        if cls == 'zonelinkent' and next_zone:
            kind = 'link'
            if '/' not in next_zone:
                next_zone = str(Path(zone).parent / next_zone).replace('\\', '/')
        elif targets & spawners.keys() and (touch or use):
            kind = 'boss_trigger' if bosses else 'fight_trigger'
        elif objectives and not (touch or use) and cls in ('physent', 'actor', 'gameent'):
            kind = 'combat_objective'
        elif objectives and (touch or use):
            kind = 'objective_use' if use else 'objective_touch'
        elif touch and cls in ('gameent', 'actionent', 'triggerent'):
            kind = 'touch'
        elif use and (refs or attrs.get('target')):
            kind = 'use'
        else:
            continue
        # Keep only identifiers/coordinates, never dialog/objective/hint text.
        functions = [fn for ref in seen for fn, _ in calls(scripts.get(ref, ''))]
        optional = bool(functions) and set(functions) <= {'createpopupdialogxml', 'runscript'}
        goal_candidates.append(Goal(name, kind, pos, next_zone=next_zone,
                                    objectives=sorted(objectives), followup_zone=followup,
                                    sources=sorted(seen), optional=optional, requires_use=use))
    # Stable nearest-neighbour order from the spawn; zone links are tried after local actions.
    ordered, here = [], starts[0] if starts else (0., 0., 0.)
    while goal_candidates:
        candidate = min(goal_candidates, key=lambda g: (3 if g.optional else 0 if g.objectives or g.kind in ('boss_trigger', 'fight_trigger') else 1 if g.kind == 'link' else 2, distance(here, g.pos), g.name))
        goal_candidates.remove(candidate)
        ordered.append(asdict(candidate))
        here = candidate.pos
    return {'zone': zone, 'goals': ordered, 'anchors': anchors, 'starts': starts, 'script_transitions': transitions, 'barriers': barriers, 'enemy_stats': enemy_stats,
            'boss_stats': sorted(boss_stats), 'floor_lower_bound': min(heights) - 512 if heights else None,
            'floor_source': 'lowest start/waypoint/zone-link/game entity origin minus 512; heuristic',
            'limitations': ['Candidates may be disabled, inaccessible, or require a hero power; visiting is not completion.']}


def apply_hints(plan, hints):
    """Hints hold only entity identifiers and response indices, never script text."""
    if not isinstance(hints, dict) or set(hints) - {'order', 'responses'}:
        raise ValueError('hints allow only order and responses')
    order, responses = hints.get('order', []), hints.get('responses', {})
    if not isinstance(order, list) or not isinstance(responses, dict):
        raise ValueError('invalid hint types')
    names = {g['name'] for g in plan['goals']}
    for name in order:
        identifier(name)
        if name not in names:
            raise ValueError('hint names an entity absent from generated goals')
    for name, reply in responses.items():
        identifier(name)
        if name not in names or type(reply) is not int or not 0 <= reply <= 31:
            raise ValueError('invalid response hint')
    rank = {name: i for i, name in enumerate(order)}
    plan['goals'].sort(key=lambda g: rank.get(g['name'], len(rank)))
    plan['responses'] = responses
    return plan


class HintError(ValueError):
    """An explicitly requested hint cannot be used; do not run an unhinted plan."""


def generate_cache(build, output, hints=None):
    import xmlb
    from autopilot_nav import nav_data, Routes
    build, output = Path(build).resolve(), external(output)
    hint_root = Path(hints) if hints is not None else None
    if hint_root is not None and not hint_root.is_dir():
        raise HintError('requested hints directory is unavailable')
    inputs = sorted([*build.glob('Maps/**/*.XMLB'), *build.glob('Maps/**/*.xmlb'), *build.glob('Scripts/**/*.py'), *build.glob('Maps/**/*.NAVB'), *build.glob('Maps/**/*.navb')])
    # Windows glob is case-insensitive; do not hash/decode each file twice.
    inputs = sorted(set(inputs))
    digest = hashlib.sha256(b'autopilot-goals-v1')
    digest.update(Path(__file__).read_bytes())
    digest.update(Path(__file__).with_name('autopilot_nav.py').read_bytes())
    scripts, maps, navs = {}, [], {}
    for path in inputs:
        data = path.read_bytes()
        rel = path.relative_to(build).as_posix()
        digest.update(rel.lower().encode()); digest.update(hashlib.sha256(data).digest())
        if path.suffix.lower() == '.py':
            scripts[rel.split('/', 1)[1].removesuffix('.py').lower()] = data.decode('latin-1')
        elif path.suffix.lower() == '.navb':
            navs[rel.split('/', 1)[1].rsplit('.', 1)[0].lower()] = data
        else:
            maps.append((rel, data))
    plans, errors = {}, []
    for rel, data in maps:
        zone = rel.split('/', 1)[1].rsplit('.', 1)[0].lower()
        try:
            root = xmlb.decode(data)
            plans[zone] = zone_plan(zone, root, scripts)
            plan = plans[zone]
            plan['navigation'] = {'source': 'missing_nav', 'cells': [], 'links': []}
            if zone in navs:
                try:
                    world = next((e for e in root.iter('entity') if e.get('name', '').lower() == 'world'), None)
                    plan['navigation'] = nav_data(xmlb.decode(navs[zone]), world)
                except (ValueError, IndexError, struct.error, RecursionError):
                    plan['navigation']['source'] = 'invalid_or_empty_nav'
            cells = plan['navigation']['cells']
            if cells:
                nav_floor = min(cell[2] for cell in cells) - 512
                entity_floor = plan['floor_lower_bound']
                plan['floor_lower_bound'] = min(entity_floor, nav_floor) if entity_floor is not None else nav_floor
                plan['floor_source'] = 'lowest navigation cell or selected entity origin minus 512; heuristic'
            plan['navigation']['script_transitions'] = plan['script_transitions']
            graph = Routes(plan['navigation'], plan['anchors'])
            plan['routes_from_start'] = {}
            if plan['starts']:
                for goal in plan['goals']:
                    try:
                        plan['routes_from_start'][goal['name']] = {'points': graph.route(plan['starts'][0], goal['pos'])}
                    except ValueError as exc:
                        plan['routes_from_start'][goal['name']] = {'error': str(exc)}
            if hint_root is not None:
                try:
                    raw = (hint_root / (zone + '.json')).read_bytes()
                    plans[zone] = apply_hints(plans[zone], json.loads(raw))
                    digest.update(zone.encode());digest.update(raw)
                except FileNotFoundError:
                    pass  # Per-zone hints are optional within the requested directory.
                except (OSError, ValueError, TypeError, RecursionError) as exc:
                    raise HintError(f'{zone}: invalid requested hint ({type(exc).__name__})') from None
        except HintError:
            raise
        except (ValueError, IndexError, KeyError, RecursionError, struct.error) as exc:
            errors.append({'zone': zone, 'error': type(exc).__name__})
    cache = {'schema': SCHEMA, 'fingerprint': digest.hexdigest(), 'plans': plans, 'errors': errors}
    output.mkdir(parents=True, exist_ok=True)
    target = output / ('goals-' + cache['fingerprint'] + '.json')
    encoded = json.dumps(cache, sort_keys=True)
    target.write_text(encoded, encoding='utf-8')
    if target.read_text(encoding='utf-8') != encoded:
        raise OSError('goal cache verification failed')
    return target, cache


def approach_target(here, goal, anchors, blocked=()):
    """Use an existing nearby map entity as an intermediate engine pathfinding goal.

    Never invent/move an entity or a coordinate. A direct target remains the fallback
    when the data has no plausible same-height step closer to it.
    """
    if here is None or distance(here, goal['pos']) <= 600:
        return goal
    candidates = [a for a in anchors if a['name'] not in blocked and a['name'] != goal['name']
                  and 90 <= distance(here, a['pos']) <= 600 and abs(here[2] - a['pos'][2]) <= 72
                  and distance(a['pos'], goal['pos']) + 20 < distance(here, goal['pos'])]
    return min(candidates, key=lambda a: (distance(a['pos'], goal['pos']), a['name'])) if candidates else goal


def ui_action(state, popup_age=0., desired=0):
    """Normal input only: modal popups take priority over underlying conversations."""
    if state.get('popup') is True:
        return 'ESCAPE' if popup_age >= 4 else 'ENTER'
    conv = state.get('conversation') or {}
    if conv.get('open'):
        selected, count = conv.get('selected'), conv.get('responses')
        if count is None or count <= 0:
            return None
        if not 0 <= desired < count:
            raise ValueError('hint response is outside the visible menu')
        if count > 1 and (type(selected) is not int or not 0 <= selected < count):
            raise ValueError('cannot select the first response without a valid cursor')
        if count > 1 and selected != desired:
            return 'UP' if selected > desired else 'DOWN'
        return 'ENTER'
    if state.get('mode') == 'movie' or (state.get('menu') or '').lower() in ('team', 'team_menu', 'characters'):
        return 'ENTER'
    return None


@dataclass
class Thresholds:
    stall: float = 90.
    conversation: float = 60.
    boss: float = 90.
    falling: float = 3.
    followup: float = 30.
    stale: float = 8.


class Monitor:
    def __init__(self, limits=None):
        self.limits = limits or Thresholds()
        self.last = None
        self.last_progress = None
        self.sample_changed = None
        self.conversation_since = None
        self.objective_since = {}
        self.falling_since = {}
        self.boss_health = {}
        self.followup = None
        self.locked_since = None
        self.best_distance = math.inf
        self.last_goal = None
        self.reported = set()
        self.history = deque()

    def note(self, now, event):
        self.history.append((now, event))
        while self.history and self.history[0][0] < now - 30:
            self.history.popleft()

    def recent(self, now):
        while self.history and self.history[0][0] < now - 30:
            self.history.popleft()
        return [e for _, e in self.history]

    def observe(self, now, state, objectives, events, goal, plan):
        self.recent(now)
        findings = []
        def finding(kind, detail):
            key = (state.get('zone'), kind, detail)
            if key not in self.reported:
                self.reported.add(key)
                findings.append({'kind': kind, 'detail': detail})
        old = self.last
        zone_changed = old is None or old.get('zone') != state.get('zone')
        if zone_changed:
            self.last_progress = now
            self.best_distance = math.inf
            self.falling_since.clear();self.boss_health.clear();self.objective_since.clear()
            self.conversation_since = None
        if old is None or old.get('sampled_ms') != state.get('sampled_ms'):
            self.sample_changed = now
        elif now - self.sample_changed >= self.limits.stale:
            finding('hang', 'game-thread sample stopped advancing')
        for event in events.get('events', []):
            stamp = event.get('ms')
            sample = state.get('sampled_ms')
            age = max(0., (sample - stamp) / 1000) if isinstance(stamp, (int, float)) and isinstance(sample, (int, float)) else 0.
            self.note(now - age, event)
            if event.get('type') in ('hero_death', 'game_over', 'script_error'):
                finding(event['type'], event.get('detail', ''))
            if event.get('type') in ('objectives_changed', 'zone_changed', 'conversation_start', 'conversation_end'):
                self.last_progress = now
        if events.get('dropped'):
            finding('observation_gap', 'engine event queue overflowed')
        if self.followup and state.get('zone') == self.followup[0]:
            self.followup = None
        elif self.followup and now >= self.followup[1]:
            finding('conversation_followup_missing', self.followup[0]);self.followup = None
        if state.get('script_controls_locked') is True:
            if self.locked_since is None:
                self.locked_since = now
            if now - self.locked_since >= self.limits.stall:
                finding('script_lock_stall', 'script control lock did not clear; navigation assists prohibited')
        else:
            self.locked_since = None
        conv = state.get('conversation', {})
        active = conv.get('open') is True
        if active:
            if self.conversation_since is None:
                self.conversation_since = now
            if old and old.get('conversation', {}).get('line_id') != conv.get('line_id'):
                self.last_progress = now
            if now - self.conversation_since > self.limits.conversation:
                finding('conversation_stall', 'conversation remained open past its time budget')
        elif self.conversation_since is not None:
            if goal and goal.get('followup_zone'):
                self.followup = (goal['followup_zone'], now + self.limits.followup)
            self.conversation_since = None
        party = state.get('party', [])
        lead = next((h for h in party if h.get('alive') is True), None)
        if not zone_changed and old:
            previous = {h.get('entity_id'): h for h in old.get('party', []) if h.get('entity_id')}
            for hero in party:
                before = previous.get(hero.get('entity_id'))
                if before and before.get('alive') is True and hero.get('alive') is False:
                    finding('hero_death', hero.get('name', ''))
        living_or_dead = [h for h in party if h.get('name') and h.get('alive') is not None]
        if living_or_dead and all(h.get('alive') is False for h in living_or_dead):
            finding('game_over', 'all observed party bodies are dead')
        if state.get('loading') is not False:
            self.falling_since.clear()
        else:
            for hero in party:
                pos = position(hero); identity = hero.get('entity_id')
                if not identity or pos is None:
                    continue
                floor = plan.get('floor_lower_bound')
                if floor is not None and pos[2] < floor:
                    finding('out_of_bounds', f'{hero.get("name")}: below conservative zone floor bound')
                velocity = hero.get('z_velocity')
                if isinstance(velocity, (float, int)) and velocity < -40:
                    self.falling_since.setdefault(identity, now)
                    if now - self.falling_since[identity] >= self.limits.falling:
                        finding('falling', f'{hero.get("name")}: sustained downward motion; flight/lift context needs review')
                else:
                    self.falling_since.pop(identity, None)
        if goal:
            key = (state.get('zone'), goal['name'])
            if key != self.last_goal:
                self.best_distance = math.inf
                self.last_goal = key
            d = distance(position(lead) if lead else None, goal.get('pos'))
            if d + 12 < self.best_distance:
                self.best_distance = d;self.last_progress = now
            for obj in objectives.get('objectives') or []:
                if obj['name'] not in goal.get('objectives', []):
                    continue
                if obj.get('complete'):
                    self.objective_since.pop(obj['name'], None)
                elif obj.get('shown'):
                    prev = self.objective_since.get(obj['name'])
                    if prev is None or prev[0] != obj.get('count'):
                        self.objective_since[obj['name']] = (obj.get('count'), now)
                    elif now - prev[1] >= self.limits.stall:
                        finding('objective_stall', obj['name'])
        old_actors = {a.get('entity_id'): a for a in (old or {}).get('actors', [])}
        for actor in state.get('actors', []):
            if actor.get('alive') is not True:
                continue
            identity = actor.get('entity_id')
            nearby = lead is not None and distance(position(actor), position(lead)) <= 900
            active_fight = nearby and state.get('loading') is False and not active and not state.get('popup') and not state.get('menu_open')
            if not active_fight:
                self.boss_health.pop(identity, None)
                continue
            before = old_actors.get(actor.get('entity_id'), {})
            if before.get('health') != actor.get('health'):
                self.last_progress = now
            if (actor.get('name') or '').lower() not in plan.get('boss_stats', []):
                continue
            identity = actor['entity_id']; hp = actor.get('health')
            if hp is None:
                continue
            if identity not in self.boss_health or self.boss_health[identity][0] != hp:
                self.boss_health[identity] = (hp, now)
            elif now - self.boss_health[identity][1] >= self.limits.boss:
                finding('boss_stall', actor.get('name', ''))
        if self.last_progress is not None and now - self.last_progress >= self.limits.stall:
            finding('softlock', 'no goal-distance, objective, conversation, zone or combat-health progress')
        self.last = copy.deepcopy(state)
        return findings
