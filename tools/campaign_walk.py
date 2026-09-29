r"""Walk the XML1 campaign's mission starts in a running game, unattended, and report what each start did.

usage: campaign_walk.py <build_dir> <results_dir> [--missions a,b,c] [--from M] [--to M] [--limit N]
                        [--extras] [--reachable-only] [--include-cut] [--zones] [--no-sides] [--side-parent]
                        [--no-launch] [--no-relaunch] [--no-skip-movies] [--resume] [--close-at-end] [--mortal]
                        [--slow F] [--load-timeout S] [--settle-timeout S] [--conv-timeout S] [--quiet S] ...
       campaign_walk.py <build_dir> --dry-run [--json] [same filters]

--dry-run only parses the build and prints the plan (order, start script, expected party, target zone, side-mission
begin/end sites, zones with --zones, a time estimate). It never looks for the game, the pipe or its memory.

Needs: the xml2-fix test harness in the build (tools/harness.py install <build>: [Test] InputPipe=1, [Game]
ForcedTeams=1, windowed + RunInBackground) and an xml2-fix with the forced-teams script functions including
getPartyMember (branch display 7b457dc+). The pipe takes ONE client: while this runs, don't use fixinput.py,
tour_runner.py or a prototype on the same game (fixinput calls wait, then fail with "error 231").

The game: if an XMen2.exe from <build_dir> is running with the pipe up, the walk attaches to it (at the main menu
it starts a New Game first: Enter, Enter). If none is running it launches <build_dir>\XMen2.exe under
tools/gamedbg.py (log <results>/gamedbg_<time>_NN.log: exceptions, exit code) and starts a New Game. Only the
XMen2.exe of <build_dir> is ever found, driven or killed (current_zone.game_pid(build)); games from other folders
(a second test window, Owen's play build) are left alone. The walk talks to the pipe the build's xml2-fix.ini names
([Test] PipeName, harness.py --pipe-name; fixinput.use_build - XML2FIX_PIPE is not needed, and one naming another
pipe is refused), and stops if another folder's game serves that same pipe (the keys could land in either game).

Keep-alive (default; --mortal turns it off): since SPEC 24 NPC attacks do XML1's damage, and an idle hero dies in
hostile start zones (the 2026-09-29 regression: a lone Magma killed by mansion_front5's Sentinels during
sentinels_mansion, then every later start of that session inherited the dead party). So before every start and after
every settle the pipe runs setInvulnerable("_ACTIVE_HERO_","TRUE") + restoreHealth("_ACTIVE_HERO_",10000) (a zone
load or reload makes a new, unprotected actor; invulnerability after settle alone was not enough).

Order: research/scripts/mission_plan.json "groups" - XML1's data/missions/missions.xml act files x1_act01..09 in
file order (the order XML1 lists its missions; side missions sit near their parents, e.g. jug_fb before mansion2).
Left out unless --extras: the act-9 Danger Room disc replays (xml1build.scripts.NONCAMPAIGN_MISSION: boss_*, demo,
*test*; plus ice_wolverine and status_meeting, forced-teams-census.md 0). --reachable-only keeps only
research/sweep/graph.json reachable_missions (63). --from / --to cut the order; --missions replaces it (any
mission, in the given order). The forced-party tables (FORCED_TEAMS_DESIGN.md 3.3, forced-teams-census.md 1) list
only the 49 forced missions, so they are not the order; the expected parties come from the build's own generated
scripts (below), and --dry-run cross-checks them against the build's _build/scripts_detail.json forced_teams plan
(what table 3.3 was generated from).

Per mission (all of it logged to stdout as it happens):
  1. wait until no conversation has been active for --quiet s (a mission start queued behind an opening
     conversation waits behind it: the lesson from the prototype), click through one if it is up;
  2. `console runscript <start>`: x1/missions/begin_<m>, or a side mission's pushParty begin site (see 6);
  3. wait for the zone the begin body loads (Scripts/x1/missions/begin_<m>.py: the loadMapKeepTeam after seatParty,
     the last loadMap*/loadZone, or the code of blackbirdMenu), read from memory (current_zone.py). Enter is
     pressed every few seconds while the HUD is down and no conversation is up - it accepts a team menu (free and
     menu starts) and skips a movie (unless --no-skip-movies; a missing movie signals at once anyway). A start
     that reloads the zone it is in counts once the HUD went down and came back;
  4. settle (HUD up or a conversation; a HUD-less zone such as a mocap briefing after --no-hud-settle s), click
     through the conversations (conv_probe.py: Enter; Down first when the reply cursor sits past the last visible
     response; Down after 3 presses on one line), then follow what the conversation did (a zone change, or a team
     menu: Enter again);
  5. read the party: `script getPartyMember(0..3)` and the "forced teams: getPartyMember(i) -> "x"" lines of
     xml2-fix.log; compare with the begin body's seatParty (seat starts), with the party before the start
     (loadMapKeepTeam starts), or record it (team-menu starts). Screenshot + HUD crop, the new xml2-fix.log lines
     ("forced teams:" results, errors, warnings);
  6. side missions (FORCED_TEAMS_DESIGN 3.4; found in the build: the script with pushParty and the "XML1
     beginSideMission(s)" marker or begin_<s>, and the "XML1 endSideMission from side mission s" end sites): the
     party and zone before the push, the pushParty record from the log, then the end site - run as a file when its
     pop block is top level (end_jug_fb, fmvexit, end_fb, endreboot), else its setCurrentAct/setSkinset/popParty
     statements through `script` (nycfb4_finish's block sits under "if iDone == 1") - and check that the zone and
     the party came back to the pushed record. --side-parent starts the parent mission (mansion2, mansion3,
     muir2, ...) first so the push saves the party and hub the player would have;
  7. --zones: every zone of the mission (research/scripts/out/zone_acts.json, zones in the build, BFS order along
     _build/zones_detail.json nextzones from the start zone) by `script loadMapKeepTeam("<zone>")`, a screenshot each.

Statuses: ok, party-mismatch, party-unread (a seat start whose party the log never gave), party-empty (every
getPartyMember reads "" after the start: a dead or dropped party - a keep start keeping an empty party is no pass;
the game is restarted before the next mission), conv-stuck (still in a
conversation after --conv-timeout), restore-failed (side mission), bounced (the zone came, then the game was
somewhere else without a conversation taking it there), wrong-zone (another zone loaded and settled for
--wrong-grace s), load-timeout (the zone never came), stalled (pipe trouble, or a conversation that never ends
before a start), crash (the process went; the next mission starts after a relaunch + New Game, like tour_runner),
skipped (no begin script / its zone is not in the build: cut, unless --include-cut). The game is restarted
before the next mission after conv-stuck / stalled / party-empty (or any start whose party read empty), and after
--restart-after (2) failed starts in a row (wrong-zone, bounced, load-timeout). The walk only ever kills an XMen2.exe
from <build_dir>.

Output: <results>/campaign.json (plan + one record per mission; rewritten after every mission, --resume skips
the recorded ones), <results>/campaign.md (tables: mission, expected party, actual party, zone, status, notes,
screenshot link; side missions; zones), <results>/shots/ (NNN_<mission>.png, _hud.png, _conv.png, _return.png,
_zNN_<zone>.png).

Timeouts (seconds; --slow F multiplies them all): --boot-timeout 300 (launch to in game), --load-timeout 240
(start to the zone, movies and menus included), --settle-timeout 90, --no-hud-settle 45, --conv-open 6 (after
settling, wait this long for an opening conversation), --conv-timeout 180, --party-timeout 6, --zone-timeout 150.
Gaps: --poll 1.0, --conv-gap 1.3, --quiet 2.0, --press-every 5.

examples:
  python tools/campaign_walk.py build/_ft_hub --dry-run
  python tools/campaign_walk.py build/_ft_hub build/walk1 --from mansion1 --to mansion2 --side-parent
  python tools/campaign_walk.py build/_ft_hub build/walk_sides --missions jug_fb,sent_fb,dr_mag1 --side-parent
  python tools/campaign_walk.py build/_ft_hub build/walk_all --zones --resume     (long: run it in the background)
"""
import argparse
import configparser
import ctypes
import ctypes.wintypes as w
import json
import os
import re
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import local_paths  # noqa: E402
REAL_INSTALL = os.path.normcase(os.path.abspath(local_paths.xml2_dir()))
MISSION_PLAN = os.path.join(REPO, 'research', 'scripts', 'mission_plan.json')
ZONE_ACTS = os.path.join(REPO, 'research', 'scripts', 'out', 'zone_acts.json')
GRAPH = os.path.join(REPO, 'research', 'sweep', 'graph.json')
MENU_ZONES = ('', 'menu/main_back')
HUD_CROP = (0.03125, 0.597, 0.211, 0.972)   # the party portraits + bars (mission_run.py's 40,430-270,700 at 1280x720)
STILL_ACTIVE = 259
# the keep-alive (Walker.keep_alive): one pipe script line, statements joined with the four characters \n\r
KEEP_ALIVE = r'setInvulnerable("_ACTIVE_HERO_","TRUE")\n\rrestoreHealth("_ACTIVE_HERO_",10000)'

try:  # the pipeline's own tables (read only)
    from xml1build.scripts import NONCAMPAIGN_MISSION, SIDE_MISSIONS  # noqa: E402
except Exception:  # noqa: BLE001 - a copy, so the dry run works without the pipeline package
    NONCAMPAIGN_MISSION = re.compile(r'^(boss_|demo$)|test')
    SIDE_MISSIONS = {'jug_fb': 'mansion2', 'sent_fb': 'mansion2', 'dr_mag1': 'mansion2', 'wx_fb_start': 'mansion3',
                     'muir2_reboot': 'muir2', 'astral_sk': 'astral3', 'nyc_rooftops': 'riots'}


# The act-9 Danger Room disc replays the pipeline's regex doesn't name (forced-teams-census.md 0: "boss/status
# Danger-Room-disc replays"): XML1 starts them from the Danger Room menu, not from the story.
DR_REPLAYS = frozenset({'ice_wolverine', 'status_meeting'})


def is_extra(m):
    return bool(NONCAMPAIGN_MISSION.search(m)) or m in DR_REPLAYS


# ================================================================================================ plan (offline)
CALL = re.compile(r'^(\w+)\s*\((.*)\)\s*$')
STRS = re.compile(r'"([^"]*)"')
BB_CODE = re.compile(r"""load\w*\(\s*['"]([^'"]+)['"]""")
SIDE_BEGIN_MARK = re.compile(r'beginSideMission\((\w+)\)')
SIDE_END_MARK = re.compile(r'#\s*\(\s*"XML1 endSideMission from side mission (\w+)"')
LOADS = ('loadMapKeepTeam', 'loadMapChooseTeam', 'loadMap', 'loadZone')


def norm_zone(z):
    return (z or '').strip().replace('\\', '/').lower()


def read_text(path):
    with open(path, encoding='latin-1') as f:
        return f.read()


def parse_body(text):
    """A begin script -> {'movies', 'seat' (names or None), 'skinset', 'load', 'zone', 'fallback', 'push', 'act'}.
    Tracks the `if x1ft == 1` blocks: a load in their else branch is the no-DLL team-menu fallback."""
    out = {'movies': [], 'seat': None, 'skinset': None, 'load': None, 'zone': None, 'fallback': None,
           'push': False, 'act': None}
    stack, loads = [], []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith('#'):
            continue
        if s.startswith('if '):
            stack.append([bool(re.match(r'if\s+x1\w*\s*==\s*1\b', s)), False])
            continue
        if s == 'else' or s.startswith('elif '):
            if stack:
                stack[-1][1] = True
            continue
        if s == 'endif':
            if stack:
                stack.pop()
            continue
        m = CALL.match(s)
        if not m:
            continue
        fn, args = m.group(1), m.group(2)
        strs = STRS.findall(args)
        in_else = any(x1 and els for x1, els in stack)
        if fn == 'startMovie' and strs:
            out['movies'].append(strs[0])
        elif fn == 'seatParty' and not in_else:
            out['seat'] = [a.strip().lower() for a in strs if a.strip()]
        elif fn == 'setSkinset' and len(strs) >= 2 and not in_else and out['skinset'] is None:
            out['skinset'] = [strs[0], strs[1]]
        elif fn == 'pushParty':
            out['push'] = True
        elif fn == 'setCurrentAct' and out['act'] is None:
            d = re.search(r'\d+', args)
            out['act'] = int(d.group()) if d else None
        elif fn in LOADS and strs:
            loads.append((fn, norm_zone(strs[0]), in_else))
        elif fn == 'blackbirdMenu':
            bb = BB_CODE.search(args)
            if bb:
                loads.append((fn, norm_zone(bb.group(1)), in_else))
    main = [ld for ld in loads if not ld[2]]
    out['fallback'] = next((z for _, z, e in loads if e), None)
    if main:
        out['load'], out['zone'] = main[-1][0], main[-1][1]
    return out


def start_kind(body):
    if body['seat'] is not None:
        return 'seat'
    if body['load'] in ('blackbirdMenu', 'loadMapChooseTeam'):
        return 'menu'
    if body['load']:
        return 'keep'
    return 'none'


def parse_end(text, side):
    """An end site -> {'top_level', 'act', 'skinset', 'pop_zone', 'movies', 'statements'} for side mission `side`."""
    lines = text.splitlines()
    k = next((i for i, l in enumerate(lines) if (m := SIDE_END_MARK.search(l)) and m.group(1).lower() == side), None)
    if k is None:
        return None
    top = not lines[k][:1].isspace()
    act, skin, pop = None, None, None
    movies = [STRS.findall(l)[0] for l in lines[:k]
              if top and l.strip().startswith('startMovie') and STRS.findall(l)]
    depth, in_x1, seen_x1 = 0, False, False
    for raw in lines[k + 1:]:
        s = raw.strip()
        if s.startswith('if '):
            depth += 1
            if not seen_x1 and re.match(r'if\s+x1\w*\s*==\s*1\b', s):
                in_x1, seen_x1 = True, True
            continue
        if s == 'else' and in_x1:
            break
        if s == 'endif':
            depth -= 1
            if in_x1:
                break
            if depth < 0:
                break
            continue
        m = CALL.match(s)
        if not m:
            continue
        fn, strs = m.group(1), STRS.findall(m.group(2))
        if fn == 'setCurrentAct' and act is None:
            d = re.search(r'\d+', m.group(2))
            act = int(d.group()) if d else None
        elif fn == 'setSkinset' and len(strs) >= 2 and in_x1:
            skin = [strs[0], strs[1]]
        elif fn == 'popParty' and strs:
            pop = norm_zone(strs[0])
            break
    stmts = []
    if act is not None:
        stmts.append(f'setCurrentAct({act})')
    if skin:
        stmts.append(f'setSkinset("{skin[0]}","{skin[1]}")')
    if pop:
        stmts.append(f'popParty("{pop}")')
    return {'top_level': top, 'act': act, 'skinset': skin, 'pop_zone': pop, 'movies': movies, 'statements': stmts}


def script_ref(scripts_root, path):
    ref = os.path.relpath(path, scripts_root).replace('\\', '/')
    return ref[:-3] if ref.lower().endswith('.py') else ref


def scan_sides(build):
    """{side: {'begin': ref, 'ends': [{'ref', ...parse_end}]}} from the build's scripts (pushParty / popParty sites)."""
    root = os.path.join(build, 'Scripts')
    sides = {}
    for dirpath, _, files in os.walk(root):
        for f in files:
            if not f.lower().endswith('.py'):
                continue
            p = os.path.join(dirpath, f)
            ref = script_ref(root, p)
            if ref.lower().startswith('x1/tour/'):
                continue
            try:
                text = read_text(p)
            except OSError:
                continue
            if 'pushParty' not in text and 'popParty' not in text:
                continue
            if re.search(r'^\s*pushParty\s*\(', text, re.M):
                m = SIDE_BEGIN_MARK.search(text)
                fm = re.match(r'begin_(\w+)$', os.path.basename(ref))
                side = (m.group(1) if m else fm.group(1) if fm else None)
                if side:
                    sides.setdefault(side.lower(), {'begin': None, 'ends': []})['begin'] = ref
            for m in SIDE_END_MARK.finditer(text):
                side = m.group(1).lower()
                end = parse_end(text, side)
                if end and end['pop_zone']:
                    end['ref'] = ref
                    ends = sides.setdefault(side, {'begin': None, 'ends': []})['ends']
                    if not any(e['ref'] == ref for e in ends):
                        ends.append(end)
    for s in sides.values():
        s['ends'].sort(key=lambda e: (not e['top_level'], e['ref']))
    return sides


def load_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def zone_in_build(build, zone):
    return bool(zone) and os.path.isfile(os.path.join(build, 'Maps', *zone.split('/')) + '.XMLB')


def mission_zone_lists(build, missions):
    """{mission: [zones of that mission in walk order]} (research zone_acts.json; BFS along the build's nextzones)."""
    za = load_json(ZONE_ACTS, {}) or {}
    info = (load_json(os.path.join(build, '_build', 'zones_detail.json'), {}) or {}).get('zone_info', {}) or {}
    nxt = {norm_zone(z): [norm_zone(n) for n in (v or {}).get('nextzones', []) or []] for z, v in info.items()}
    by_m = {}
    for z, v in za.items():
        for m in (v or {}).get('missions', []) or []:
            by_m.setdefault(m.lower(), set()).add(norm_zone(z))
    out = {}
    for m, start in missions.items():
        zs = {z for z in by_m.get(m, set()) if zone_in_build(build, z)}
        if start:
            zs.add(start)
        order, queue = [], [start] if start in zs else []
        while queue:
            z = queue.pop(0)
            if z in order:
                continue
            order.append(z)
            queue += [n for n in nxt.get(z, []) if n in zs and n not in order]
        order += sorted(zs - set(order))
        out[m] = order
    return out


def read_ini(build):
    cp = configparser.ConfigParser(strict=False, interpolation=None, comment_prefixes=(';', '#'))
    try:
        cp.read(os.path.join(build, 'xml2-fix.ini'), encoding='latin-1')
    except configparser.Error:
        pass

    def get(sec, key):
        try:
            return cp.get(sec, key).strip()
        except (configparser.Error, KeyError):
            return None
    return {'input_pipe': get('Test', 'InputPipe'), 'forced_teams': get('Game', 'ForcedTeams'),
            'mode': get('Display', 'Mode'), 'save_folder': get('Game', 'SaveFolder'),
            'xp_curve': get('Game', 'XPCurve'), 'dll': os.path.isfile(os.path.join(build, 'dinput.dll'))}


def build_plan(build, opt):
    """The walk: [entry] in order, each {'index', 'mission', 'act', 'start_ref', 'kind', 'expected', ...}."""
    mp = load_json(MISSION_PLAN)
    if not mp:
        sys.exit(f'cannot read {MISSION_PLAN}')
    info = {k.lower(): v for k, v in mp['missions'].items()}
    order = [m.lower() for g in mp['groups'] for m in g['missions']]
    order += [m for m in info if m not in order]
    if opt.missions:
        wanted = [m.strip().lower() for m in opt.missions.split(',') if m.strip()]
        unknown = [m for m in wanted if m not in info and not os.path.isfile(begin_path(build, m))]
        if unknown:
            sys.exit(f'unknown mission(s): {", ".join(unknown)}')
        order = wanted
    else:
        if not opt.extras:
            order = [m for m in order if not is_extra(m)]
        if opt.reachable_only:
            reach = set((load_json(GRAPH, {}) or {}).get('reachable_missions') or ())
            order = [m for m in order if m in reach]
        for flag, keep_from in (('from_', True), ('to', False)):
            name = getattr(opt, flag)
            if name:
                name = name.lower()
                if name not in order:
                    sys.exit(f'--{flag.rstrip("_")} {name}: not in the walk order')
                i = order.index(name)
                order = order[i:] if keep_from else order[:i + 1]
    if opt.limit:
        order = order[:opt.limit]

    sides = scan_sides(build) if not opt.no_sides else {}
    detail = (load_json(os.path.join(build, '_build', 'scripts_detail.json'), {}) or {}).get('forced_teams', {}) or {}
    dplan = detail.get('plan', {}) or {}
    ini = read_ini(build)
    forced_on = ini['forced_teams'] == '1'
    plan = []
    for i, m in enumerate(order):
        mi = info.get(m, {})
        e = {'index': i + 1, 'mission': m, 'act': mi.get('act'), 'group': mi.get('group_file'),
             'descname': (mi.get('attrs') or {}).get('descname'), 'begin_ref': f'x1/missions/begin_{m}',
             'start_ref': f'x1/missions/begin_{m}', 'skip': None, 'notes': []}
        path = begin_path(build, m)
        if not os.path.isfile(path):
            e.update(kind='none', expected=None, zone=None, movies=[], skinset=None, side=None, zones=[],
                     skip='no Scripts/x1/missions/begin_%s.py in the build' % m)
            plan.append(e)
            continue
        body = parse_body(read_text(path))
        kind = start_kind(body)
        e.update(kind=kind, load=body['load'], zone=body['zone'], fallback=body['fallback'], movies=body['movies'],
                 skinset=body['skinset'], expected=body['seat'] if kind == 'seat' else None, side=None, zones=[])
        if kind == 'seat' and not forced_on:
            e['notes'].append('ForcedTeams is not 1 in xml2-fix.ini: this forced start opens the team menu')
        if not body['zone']:
            e['notes'].append('the begin body loads no zone')
        elif not zone_in_build(build, body['zone']):
            e['zone_missing'] = True
            if not opt.include_cut:
                e['skip'] = f'its zone {body["zone"]} is not in the build (cut; --include-cut runs it anyway)'
        d = dplan.get(m)
        if d:
            dz = norm_zone(d.get('zone'))
            dseat = [h.lower() for h in d.get('seat') or []] if d.get('status') == 'seat' else None
            if body['zone'] and dz and dz != body['zone']:
                e['notes'].append(f'scripts_detail plan zone {dz} != begin body {body["zone"]}')
            if dseat != e['expected'] and not (dseat is None and e['expected'] is None):
                e['notes'].append(f'scripts_detail plan seat {dseat} != begin body {e["expected"]}')
        s = sides.get(m)
        if s and s.get('begin'):
            end = s['ends'][0] if s['ends'] else None
            e['start_ref'] = s['begin']
            e['side'] = {'begin': s['begin'], 'parent': SIDE_MISSIONS.get(m),
                         'end': end, 'other_ends': [x['ref'] for x in s['ends'][1:]]}
            if not end:
                e['notes'].append('side mission: pushParty begin site but no popParty end site in the build')
        elif m in SIDE_MISSIONS and not opt.no_sides:
            e['notes'].append('XML1 side mission without a pushParty begin site in this build (team menu flow)')
        plan.append(e)
    if opt.zones:
        lists = mission_zone_lists(build, {e['mission']: e.get('zone') for e in plan if not e['skip']})
        for e in plan:
            e['zones'] = [z for z in lists.get(e['mission'], []) if z != e.get('zone')]
    return plan, ini


def begin_path(build, m):
    return os.path.join(build, 'Scripts', 'x1', 'missions', f'begin_{m}.py')


def party_text(p):
    if p is None:
        return '?'
    names = [x for x in p if x]
    return ', '.join(names) if names else '(empty)'


def expected_text(e):
    if e.get('kind') == 'seat':
        return party_text(e['expected'])
    return {'menu': '(team menu)', 'keep': '(kept)', 'none': '-'}.get(e.get('kind'), '-')


def estimate_seconds(plan, opt):
    t = 0
    for e in plan:
        if e['skip']:
            continue
        t += 45 + (10 if e['movies'] else 0) + (15 if e['kind'] == 'menu' else 0)
        if e.get('side') and e['side'].get('end'):
            t += 60 + (60 if opt.side_parent else 0)
        t += 40 * len(e.get('zones') or [])
    return t


def print_plan(build, plan, ini, opt):
    print(f'build {build}')
    print(f'  xml2-fix.ini: InputPipe={ini["input_pipe"]} ForcedTeams={ini["forced_teams"]} Mode={ini["mode"]} '
          f'SaveFolder={ini["save_folder"]}; dinput.dll {"present" if ini["dll"] else "MISSING"}')
    if ini['input_pipe'] != '1' or not ini['dll']:
        print('  !! the walk needs the harness: python tools/harness.py install <build>')
    print(f'  order: research/scripts/mission_plan.json groups (XML1 missions.xml act files)'
          f'{"" if opt.extras or opt.missions else ", act-9 extras left out"}'
          f'{", graph reachable_missions only" if opt.reachable_only else ""}')
    print()
    for e in plan:
        side = ''
        if e.get('side'):
            end = e['side'].get('end')
            side = (f'\n        side: begin {e["side"]["begin"]} (parent {e["side"]["parent"]}); end '
                    + (f'{end["ref"]} ({"file" if end["top_level"] else "statements " + " ".join(end["statements"])})'
                       f' -> pop {end["pop_zone"]}' if end else 'NONE'))
        zones = f'\n        zones: {", ".join(e["zones"])}' if e.get('zones') else ''
        notes = ''.join(f'\n        note: {n}' for n in e['notes'])
        movies = f' movies {",".join(e["movies"])}' if e.get('movies') else ''
        head = f'{e["index"]:3} {e["mission"]:26} act {e["act"] or "-"} {e["kind"]:5}'
        if e['skip']:
            print(f'{head} SKIP: {e["skip"]}{notes}')
            continue
        print(f'{head} {expected_text(e):38} -> {e.get("zone")}{movies}\n        start: runscript {e["start_ref"]}'
              f'{side}{zones}{notes}')
    run = [e for e in plan if not e['skip']]
    kinds = {}
    for e in run:
        kinds[e['kind']] = kinds.get(e['kind'], 0) + 1
    est = estimate_seconds(plan, opt)
    print(f'\n{len(plan)} missions, {len(run)} to run ({", ".join(f"{k} {v}" for k, v in sorted(kinds.items()))}), '
          f'{sum(1 for e in run if e.get("side"))} side, {sum(len(e.get("zones") or []) for e in run)} extra zones; '
          f'rough time {est // 60} min (x{opt.slow} slow factor not included)')


# ================================================================================================ game (online)
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.OpenProcess.restype = w.HANDLE
k32.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
k32.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
k32.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
k32.CloseHandle.argtypes = [w.HANDLE]
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def proc_alive(pid):
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    try:
        code = w.DWORD()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def proc_path(pid):
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = w.DWORD(1024)
        return buf.value if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else None
    finally:
        k32.CloseHandle(h)


class GameGone(Exception):
    """The game process is not there any more (crash or exit)."""


class Stop(Exception):
    """The walk cannot go on (no game and launching is off, another game is running, the pipe is taken)."""


class Stalled(RuntimeError):
    """The game is stuck where the walk can't get it out (a conversation that never ends before a start)."""


LOG_TS = re.compile(r'^\[[\d:.]+\]\s*')
GPM = re.compile(r'forced teams: getPartyMember\((\d)\) -> "([^"]*)"')
SEATED = re.compile(r'forced teams: seatParty\((.*?)\) -> (.+?) \(was (.+?)\)')
PUSHED = re.compile(r'forced teams: pushParty\(.*?\) -> pushsidemission \d+: record (\d+) of \d+, (\S+) with '
                    r'(.+?)(?: \(below it|$)')
POPPED = re.compile(r'forced teams: popParty\(.*?\)(?: -> (.+?) queued, (.+)|: (.+))$')
PROBLEM = re.compile(r'\b(error|warning|exception|fault|faulted|refused|crash|crashed)\b', re.I)


def parse_party(text):
    """'a / b / - / -' -> ['a', 'b', '', '']"""
    parts = [p.strip() for p in text.split('/')]
    return [('' if p == '-' else p.lower()) for p in (parts + [''] * 4)[:4]]


def same_party(a, b):
    """Same heroes (slot order aside; order_differs tells), or None when either side is unknown."""
    if a is None or b is None:
        return None
    return sorted(x.lower() for x in a if x) == sorted(x.lower() for x in b if x)


def order_differs(a, b):
    return bool(same_party(a, b)) and [x.lower() for x in a if x] != [x.lower() for x in b if x]


class Walker:
    def __init__(self, build, results, opt, ini):
        self.build = build
        self.results = results
        self.shots = os.path.join(results, 'shots')
        self.opt = opt
        self.ini = ini
        self.forced_on = ini.get('forced_teams') == '1'
        self.exe = os.path.join(build, 'XMen2.exe')
        self.logpath = os.path.join(build, 'xml2-fix.log')
        self.live = os.path.join(self.shots, '_live.bmp')
        self.pid = None
        self.launched = False
        self.launches = []
        self.party_form = None
        self.cur = None
        self.clock = time.time
        self.sleep = time.sleep
        self.t = lambda s: s * opt.slow
        self.run_id = time.strftime('%H%M%S')

    # ---------------------------------------------------------------- low level (a test double replaces these)
    def _find_pid(self):
        """This build's XMen2.exe (another folder's game is never found, so never driven or killed)."""
        import current_zone
        return current_zone.game_pid(self.build)

    def _other_games(self):
        """[(pid, exe path, the pipe its folder's xml2-fix.ini serves or None)] of the XMen2.exe of other folders."""
        import current_zone
        import fixinput
        return [(pid, exe, fixinput.pipe_name_for(os.path.dirname(exe)) if exe else None)
                for pid, exe in current_zone.running() if not current_zone.in_build(exe, self.build)]

    def _pipe_name(self):
        import fixinput
        return fixinput.pipe_name()

    def _alive(self):
        return proc_alive(self.pid)

    def _exe_path(self, pid):
        return proc_path(pid)

    def _read_zone(self):
        import current_zone
        return current_zone.read_zone(self.pid)

    def _probe_conv(self):
        import conv_probe
        return conv_probe.probe(self.pid)

    def _hud(self):
        from PIL import Image
        from tour_runner import hud_visible
        try:
            self._ask(f'screenshot {self.live}')
            with Image.open(self.live) as img:
                return hud_visible(img.convert('RGB'))
        except (OSError, RuntimeError, SystemExit):
            return None

    def _ask(self, line):
        import fixinput
        return fixinput.pipe().ask(line)

    def _pipe_up(self):
        import fixinput
        return fixinput.available()

    def _spawn(self, log):
        flags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0)
        subprocess.Popen([sys.executable, os.path.join(HERE, 'gamedbg.py'), log, self.exe], creationflags=flags,
                         close_fds=True)

    def _kill(self, pid):
        subprocess.run(['taskkill', '/PID', str(pid), '/F'], capture_output=True)

    # ---------------------------------------------------------------- helpers
    def say(self, msg):
        line = f'[{time.strftime("%H:%M:%S")}] {msg}'
        print(line, flush=True)
        if self.cur is not None:
            self.cur.setdefault('trace', []).append(line)

    def alive(self):
        if self.pid is None:
            pid = self._find_pid()
            if pid is None:
                raise GameGone(f'no XMen2.exe from {self.build} is running')
            self.check_ours(pid)
            self.pid = pid
        if not self._alive():
            raise GameGone(f'XMen2.exe (pid {self.pid}) exited')

    def ours(self, pid):
        path = self._exe_path(pid)
        same = os.path.normcase(os.path.abspath(path or '')) == os.path.normcase(os.path.abspath(self.exe))
        return path is not None and same

    def check_ours(self, pid):
        if not self.ours(pid):
            raise Stop(f'the running XMen2.exe (pid {pid}, {self._exe_path(pid) or "path unreadable"}) is not '
                       f'{self.exe}: close it or walk its own build')

    def check_pipe_clash(self):
        """Other folders' games may run (they are left alone), but not one serving this walk's pipe: a pipe name
        served twice would hand our keys and scripts to either game."""
        mine = (self._pipe_name() or '').lower()
        for pid, exe, pipe in self._other_games():
            if pipe and pipe.lower() == mine:
                raise Stop(f'another XMen2.exe (pid {pid}, {exe}) serves this build\'s pipe "{pipe}" too: close it, '
                           f'or give one of the builds its own pipe (harness.py install <build> --pipe-name <name>)')

    def keep_alive(self, when):
        """Since SPEC 24 NPC attacks do XML1's damage and an idle hero dies in hostile start zones (mansion_front5's
        Sentinels kill a lone Magma in a minute or two); a dead party then poisons every later start of the session.
        So, unless --mortal: setInvulnerable + a full restoreHealth for the active hero before every start and after
        every settle (a zone load or reload makes a new, unprotected actor) - regwrap.py walkinv2, 2026-09-29."""
        if not getattr(self.opt, 'keep_alive', False):
            return
        try:
            self.ask(f'script {KEEP_ALIVE}', tries=2)
        except RuntimeError as e:
            self.say(f'  keep-alive ({when}) failed: {e}')
            if self.cur is not None:
                self.cur.setdefault('keep_alive_failed', []).append(f'{when}: {e}')

    def wait(self, seconds):
        end = self.clock() + seconds
        while True:
            self.alive()
            left = end - self.clock()
            if left <= 0:
                return
            self.sleep(min(0.5, left))

    def zone(self):
        self.alive()
        return norm_zone(self._read_zone())

    def conv(self):
        self.alive()
        try:
            c = self._probe_conv() or {}
        except OSError:
            c = {}
        return c

    def hud(self):
        """True (HUD up), False (HUD down: loading, movie, menu, HUD-less zone) or None (no frame)."""
        self.alive()
        h = self._hud()
        return None if h is None else bool(h)

    def ask(self, line, tries=4):
        import fixinput
        last = None
        for _ in range(tries):
            self.alive()
            try:
                return self._ask(line)
            except fixinput.PipeError as e:
                last = e
                if 'unknown command' in str(e):
                    raise Stop(f'the fix does not know "{line.split()[0]}": {e} (xml2-fix too old?)')
            except fixinput.PipeDown as e:
                if 'error 231' in str(e):  # ERROR_PIPE_BUSY for the whole connect timeout: someone else is on it
                    raise Stop('the pipe is taken by another client (fixinput.py, tour_runner.py, a prototype?): '
                               'the fix serves one at a time')
                last = e
            self.sleep(1.0)
        self.alive()
        raise RuntimeError(f'pipe: "{line[:80]}" failed: {last}')

    def tap(self, key, ms=120):
        return self.ask(f'tap {key} {ms}')

    def shot(self, path):
        try:
            self.ask(f'screenshot {os.path.abspath(path)}')
            return path if os.path.isfile(path) else None
        except RuntimeError:
            return None

    def hud_crop(self, src, dst):
        try:
            from PIL import Image
            with Image.open(src) as img:
                wd, ht = img.size
                box = tuple(int(round(f * (wd if i % 2 == 0 else ht))) for i, f in enumerate(HUD_CROP))
                img.crop(box).save(dst)
            return dst
        except (OSError, ValueError, ImportError):
            return None

    def log_size(self):
        try:
            return os.path.getsize(self.logpath)
        except OSError:
            return 0

    def log_lines(self, start):
        try:
            with open(self.logpath, 'rb') as f:
                f.seek(0, 2)
                if f.tell() < start:
                    start = 0  # a new game session rewrote the log
                f.seek(start)
                data = f.read()
        except OSError:
            return []
        return [LOG_TS.sub('', l).strip() for l in data.decode('utf-8', 'replace').splitlines() if l.strip()]

    def rel(self, path):
        return os.path.relpath(path, self.results).replace('\\', '/') if path else None

    # ---------------------------------------------------------------- conversations
    def conv_press(self, c, st):
        line = c.get('line_id')
        if line == st['last']:
            st['same'] += 1
        else:
            st['same'], st['last'] = 0, line
            st['lines'] += 1
        sel, cnt = c.get('selected'), c.get('visible_responses')
        if isinstance(sel, int) and isinstance(cnt, int) and cnt > 0 and sel >= cnt:
            self.tap('DOWN')
            st['downs'] += 1
            self.sleep(0.4)
        elif st['same'] >= 3:
            self.tap('DOWN')
            st['stuck'] += 1
            st['same'] = 0
            self.sleep(0.4)
        self.tap('RETURN')
        st['presses'] += 1

    def conversations(self, open_wait, shot=None):
        """Wait up to open_wait s for a conversation, click through every one that comes, return when none has been
        active for --quiet s. {'handled', 'presses', 'lines', 'downs', 'stuck', 'ended', 'seconds', 'zone_after'}"""
        st = {'handled': False, 'presses': 0, 'lines': 0, 'downs': 0, 'stuck': 0, 'ended': True, 'last': None,
              'same': 0, 'shot': None}
        t0 = self.clock()
        idle_since = None
        active_since = None
        while True:
            c = self.conv()
            now = self.clock()
            if c.get('active'):
                if not st['handled']:
                    self.say(f'  conversation (line {c.get("line_id")}): clicking through')
                    if shot:
                        st['shot'] = self.rel(self.shot(shot))
                st['handled'] = True
                idle_since = None
                active_since = active_since or now
                if now - active_since > self.t(self.opt.conv_timeout):
                    st['ended'] = False
                    self.say(f'  conversation still active after {self.opt.conv_timeout * self.opt.slow:.0f} s '
                             f'(line {c.get("line_id")}, cursor {c.get("selected")}/{c.get("visible_responses")})')
                    break
                self.conv_press(c, st)
                self.sleep(self.opt.conv_gap)
                continue
            active_since = None
            idle_since = idle_since if idle_since is not None else now
            quiet_enough = now - idle_since >= self.opt.quiet
            if quiet_enough and (st['handled'] or now - t0 >= open_wait):
                break
            self.sleep(0.25)
        st['seconds'] = round(self.clock() - t0, 1)
        st['zone_after'] = self.zone()
        for k in ('last', 'same'):
            st.pop(k)
        if st['handled']:
            self.say(f'  conversation over: {st["presses"]} presses, {st["lines"]} lines'
                     + (f', {st["downs"]} cursor fixes' if st['downs'] else '')
                     + (f', {st["stuck"]} stuck lines' if st['stuck'] else ''))
        return st

    def quiet(self):
        """Nothing may be queued while a conversation opens or runs: wait for --quiet s without one (clicking through
        any that is up) and for the zone name to hold still."""
        info = self.conversations(0)
        if not info['ended']:
            raise Stalled('a conversation that never ends is up: nothing can be started behind it')
        z, since, t0 = self.zone(), self.clock(), self.clock()
        while self.clock() - since < self.opt.quiet and self.clock() - t0 < self.t(30):
            self.sleep(0.25)
            z2 = self.zone()
            if z2 != z:
                z, since = z2, self.clock()
        return info if info['handled'] else None

    # ---------------------------------------------------------------- loading
    def wait_load(self, target, start_zone, press, timeout, log_from=None):
        """Wait until `target` is the current zone. Enter every --press-every s while `press` and the HUD is down and no
        conversation is up (team menu accept / movie skip); a conversation that comes up is clicked through (a
        queued load waits behind it). A start that reloads its own zone counts once the HUD went down and came back
        (or, reload too quick to see, once the log shows the begin ran and the HUD has been up for 15 s)."""
        res = {'reached': False, 'zones_seen': [], 'presses': 0, 'same_zone': bool(target) and target == start_zone,
               'conv_presses': 0}
        t0 = self.clock()
        last_press = t0
        hud_down = False
        hud_up = 0
        prev = start_zone
        other_since = None
        st = {'handled': False, 'presses': 0, 'lines': 0, 'downs': 0, 'stuck': 0, 'last': None, 'same': 0}
        while True:
            now = self.clock()
            z = self.zone()
            if z != prev:
                res['zones_seen'].append(z)
                self.say(f'  zone -> {z or "(none)"} after {now - t0:.0f} s')
                prev = z
            if target and z == target and not res['same_zone']:
                res['reached'] = True
                break
            c = self.conv()
            if c.get('active'):
                self.conv_press(c, st)
                res['conv_presses'] += 1
                self.sleep(self.opt.conv_gap)
                continue
            hud = self.hud()
            if res['same_zone'] and z == target:
                hud_up = hud_up + 1 if hud else 0
                if hud is False:
                    hud_down = True
                elif hud and hud_down and hud_up >= 2:  # two frames: not the one between a movie and its load
                    res['reached'], res['reload_seen'] = True, True
                    break
                elif hud is not False and now - t0 >= 15 and log_from is not None and any(
                        l.startswith('forced teams:') for l in self.log_lines(log_from)):
                    res['reached'], res['reload_seen'] = True, False
                    break
            if z not in (start_zone, target) and z not in MENU_ZONES and hud:
                other_since = other_since if other_since is not None else now
                if now - other_since > self.t(self.opt.wrong_grace):
                    self.say(f'  {z} loaded and settled instead of {target}')
                    break
            else:
                other_since = None
            # press: 'menu' (a team menu must be accepted: Enter unless the HUD is seen up) or 'movie' (skip it: Enter
            # only on a frame with the HUD down - never blind into gameplay)
            if (press and (hud is False or (press == 'menu' and hud is None)) and now - t0 >= 3
                    and now - last_press >= self.opt.press_every and res['presses'] < self.opt.max_presses):
                self.tap('RETURN')
                res['presses'] += 1
                last_press = now
            if now - t0 > timeout:
                break
            self.sleep(self.opt.poll)
        res['seconds'] = round(self.clock() - t0, 1)
        res['zone'] = self.zone()
        return res

    def settle(self, timeout, hudless=None):
        """After the zone name changed: HUD up, or a conversation; a zone with neither after `hudless` s (default
        --no-hud-settle; a mocap briefing without a conversation) counts as settled too."""
        t0 = self.clock()
        limit = min(timeout, hudless if hudless is not None else self.t(self.opt.no_hud_settle))
        while True:
            now = self.clock()
            if self.conv().get('active'):
                res = {'hud': False, 'conversation': True, 'seconds': round(now - t0, 1)}
                break
            if self.hud():
                res = {'hud': True, 'conversation': False, 'seconds': round(now - t0, 1)}
                break
            if now - t0 > limit:
                res = {'hud': False, 'conversation': False, 'seconds': round(now - t0, 1), 'timeout': True}
                break
            self.sleep(self.opt.poll)
        self.keep_alive('settle')
        return res

    def after_conversation(self):
        """What the conversations left: a zone change (settle it, click through its conversations) or, HUD down with
        nothing else going on, a team menu or a movie (Enter, 3 at most). Stops once the HUD is up."""
        out = {'presses': 0, 'zones': [], 'conversations': []}
        for _ in range(6):
            z0 = self.zone()
            t0 = self.clock()
            state = 'unknown'
            while self.clock() - t0 < self.t(self.opt.post):
                if self.conv().get('active'):
                    state = 'conversation'
                    break
                if self.zone() != z0:
                    state = 'moved'
                    break
                h = self.hud()
                if h:
                    state = 'hud'
                    break
                if h is False:
                    state = 'hud-down'
                self.sleep(self.opt.poll)
            if state == 'moved':
                z = self.zone()
                out['zones'].append(z)
                self.say(f'  after the conversation the game moved on to {z}')
                self.settle(self.t(self.opt.settle_timeout))
            elif state == 'hud-down':
                if out['presses'] >= 3:
                    break
                self.say('  HUD down after the conversation and nothing going on: Enter (team menu / movie?)')
                self.tap('RETURN')
                out['presses'] += 1
                self.wait(self.opt.press_every)
                continue
            elif state != 'conversation':
                break
            c = self.conversations(self.t(self.opt.conv_open))
            if c['handled']:
                out['conversations'].append(c)
                if not c['ended']:
                    break
            elif state != 'moved':
                break
        return out

    def step(self, how, text, target, press, label, conv_shot=None, timeout=None):
        """One load: keep-alive, quiet, send, wait for the zone, settle, conversations, what they left, quiet."""
        self.keep_alive('start')
        pre = self.quiet()
        start_zone = self.zone()
        rec = {'send': f'{how} {text}', 'target': target, 'from_zone': start_zone,
               'log_from': self.log_size(), 'time': time.strftime('%H:%M:%S')}
        if pre:
            rec['leftover_conversation'] = pre
        self.say(f'  {label}: {how} {text}' + (f' (-> {target})' if target else ' (no zone to wait for)'))
        self.ask(f'{how} {text}')
        if target:
            load = self.wait_load(target, start_zone, press, timeout or self.t(self.opt.load_timeout), rec['log_from'])
        else:
            self.wait(3)
            load = {'reached': True, 'zones_seen': [], 'presses': 0, 'seconds': 3, 'no_target': True,
                    'zone': self.zone()}
        rec['load'] = load
        rec['reached'] = load['reached']
        if not load['reached']:
            self.say(f'  {target} never came ({load["seconds"]:.0f} s; zone {load["zone"]})')
            rec['zone'] = load['zone']
            return rec
        rec['settle'] = self.settle(self.t(self.opt.settle_timeout))
        rec['conv'] = self.conversations(self.t(self.opt.conv_open), conv_shot)
        if not rec['conv']['ended']:
            rec['zone'] = self.zone()
            return rec
        rec['after'] = self.after_conversation()
        if not all(c.get('ended', True) for c in rec['after'].get('conversations', [])):
            rec['zone'] = self.zone()
            return rec
        self.quiet()
        rec['zone'] = self.zone()
        rec['hud'] = self.hud()
        if rec['zone'] != target and target and not rec['after'].get('zones'):
            self.say(f'  now in {rec["zone"]}, not {target} (the load bounced back?)')
        return rec

    # ---------------------------------------------------------------- party
    def read_party(self):
        """['a', 'b', '', ''] from script getPartyMember(0..3) + xml2-fix.log, or None."""
        forms = [self.party_form] if self.party_form is not None else ['', 'x1pm=']
        for form in forms:
            start = self.log_size()
            stmt = r'\n\r'.join(f'{form}getPartyMember({i})' for i in range(4))
            try:
                self.ask(f'script {stmt}')
            except RuntimeError as e:
                self.say(f'  party: {e}')
                return None
            got = {}
            t0 = self.clock()
            while self.clock() - t0 < self.t(self.opt.party_timeout):
                for line in self.log_lines(start):
                    m = GPM.search(line)
                    if m:
                        got[int(m.group(1))] = m.group(2).strip().lower()
                if len(got) == 4:
                    self.party_form = form
                    return [got[i] for i in range(4)]
                self.wait(0.5)
        self.say('  party: no getPartyMember lines in xml2-fix.log (a fix without getPartyMember, or no script ran)')
        return None

    # ---------------------------------------------------------------- game session
    def new_game(self, fresh=False):
        """From the front end into the game: Enter (New Game), Enter (Normal), then whatever the build starts
        (fresh: the game was just launched - boot movies first, so the first Enter waits --boot-wait s)."""
        self.say('new game: Enter on the main menu until a zone loads')
        t0 = self.clock()
        presses, last = 0, 0.0
        while True:
            now = self.clock()
            z = self.zone()
            if z not in MENU_ZONES:
                break
            if now - t0 > self.t(self.opt.boot_timeout):
                raise RuntimeError(f'new game: still in the front end after {now - t0:.0f} s')
            if now - t0 > (self.opt.boot_wait if fresh else 0) and now - last > 5 and presses < 16 \
                    and self._pipe_up():
                try:
                    self.tap('RETURN', 100)
                    presses += 1
                except RuntimeError:
                    pass
                last = now
            self.sleep(self.opt.poll)
        z = self.zone()
        self.say(f'new game: {z} after {self.clock() - t0:.0f} s ({presses} Enter)')
        self.settle(self.t(self.opt.settle_timeout), self.t(self.opt.settle_timeout))
        self.conversations(self.t(self.opt.conv_open))
        self.quiet()
        return {'zone': self.zone(), 'presses': presses, 'seconds': round(self.clock() - t0, 1)}

    def launch(self, reason):
        if self.opt.no_launch or (self.launches and self.opt.no_relaunch):
            raise Stop(f'{reason}; launching is off (--no-launch / --no-relaunch)')
        if len(self.launches) >= self.opt.max_launches:
            raise Stop(f'{reason}; {len(self.launches)} launches already (--max-launches)')
        if self.ini.get('input_pipe') != '1' or not self.ini.get('dll'):
            raise Stop('the build has no pipe harness (tools/harness.py install <build>)')
        self.check_pipe_clash()
        self.kill_ours()
        log = os.path.join(self.results, f'gamedbg_{self.run_id}_{len(self.launches) + 1:02d}.log')
        self.say(f'launch {len(self.launches) + 1} ({reason}): {self.exe} under gamedbg -> {os.path.basename(log)}')
        self._spawn(log)
        rec = {'n': len(self.launches) + 1, 'reason': reason, 'time': time.strftime('%H:%M:%S'), 'gamedbg_log':
               self.rel(log)}
        self.launches.append(rec)
        self.launched = True
        self.pid = None
        t0 = self.clock()
        while self.clock() - t0 < self.t(60):
            pid = self._find_pid()
            if pid and self.ours(pid):
                self.pid = pid
                break
            self.sleep(1.0)
        if self.pid is None:
            raise Stop('the game did not start (see the gamedbg log)')
        rec['new_game'] = self.new_game(fresh=True)
        return rec

    def kill_ours(self):
        """Close this build's game (by pid: another folder's game is never found here, so never killed)."""
        pid = self._find_pid()
        if pid is None:
            return
        if not self.ours(pid):
            raise Stop(f'the XMen2.exe found (pid {pid}, {self._exe_path(pid)}) is not {self.exe}; not touching it')
        self.say(f'closing XMen2.exe pid {pid}')
        self._kill(pid)
        t0 = self.clock()
        while self._find_pid() is not None and self.clock() - t0 < 20:
            self.sleep(1.0)
        self.pid = None

    def ensure_game(self):
        """Attach to this build's running game (New Game from the main menu) or launch it."""
        self.check_pipe_clash()
        try:
            self.alive()
        except GameGone as e:
            self.pid = None
            return self.launch(str(e) if not self.launches else 'the game is gone')
        if not self._pipe_up():
            t0 = self.clock()
            while not self._pipe_up():
                if self.clock() - t0 > self.t(60):
                    raise Stop('the game runs but the pipe is not up ([Test] InputPipe=1? an old dinput.dll?)')
                self.wait(1.0)
        if self.zone() in MENU_ZONES:
            self.new_game()
        return None

    def restart(self, reason):
        self.say(f'restart: {reason}')
        try:
            self.kill_ours()
        except Stop:
            raise
        self.pid = None
        return self.launch(reason)

    def crash_info(self, why):
        info = {'why': str(why)}
        if self.launches:
            path = os.path.join(self.results, os.path.basename(self.launches[-1]['gamedbg_log']))
            try:
                with open(path, encoding='latin-1') as f:
                    lines = [l.rstrip() for l in f]
                info['gamedbg'] = [l for l in lines if 'EXCEPTION' in l or 'EXIT' in l][-6:]
                k = max((i for i, l in enumerate(lines) if 'EXCEPTION' in l and 'first' in l), default=None)
                if k is not None:
                    info['first_exception'] = lines[k:k + 8]
            except OSError:
                pass
        info['fix_log_tail'] = [l for l in self.log_lines(max(0, self.log_size() - 6000))
                                if not l.startswith('test:') and 'getPartyMember' not in l][-12:]
        return info

    # ---------------------------------------------------------------- one mission
    def run_mission(self, e):
        m = e['mission']
        rec = {k: e.get(k) for k in ('index', 'mission', 'act', 'descname', 'kind', 'start_ref', 'expected', 'zone',
                                     'movies', 'skinset')}
        rec.update(status='running', notes=list(e.get('notes') or []), started=time.strftime('%H:%M:%S'))
        rec['target_zone'] = rec.pop('zone')
        self.cur = rec
        t0 = self.clock()
        base = os.path.join(self.shots, f'{e["index"]:03d}_{m}')
        self.say(f'--- {e["index"]} {m} ({e["kind"]}, expect {expected_text(e)} -> {e.get("zone")})')
        side = e.get('side')
        rec['phase'] = 'quiet'
        self.quiet()
        if side:
            rec['side'] = {'begin': side['begin'], 'parent': side['parent'],
                           'end': side['end']['ref'] if side.get('end') else None}
            parent = side.get('parent')
            if self.opt.side_parent and parent and os.path.isfile(begin_path(self.build, parent)):
                rec['phase'] = 'parent'
                pb = parse_body(read_text(begin_path(self.build, parent)))
                rec['side']['parent_step'] = self.step('console', f'runscript x1/missions/begin_{parent}', pb['zone'],
                                                       self.press_for(start_kind(pb), pb['movies']), f'parent {parent}')
        pre = None
        if e['kind'] == 'keep' or side:
            rec['phase'] = 'pre-party'
            pre = self.read_party()
            rec['pre_party'] = pre
            rec['pre_zone'] = self.zone()
        rec['phase'] = 'start'
        st = self.step('console', f'runscript {e["start_ref"]}', e.get('zone'), self.press_for(e['kind'], e['movies']),
                       'start', conv_shot=base + '_conv.png')
        rec['start'] = st
        rec['zone_reached'] = st['reached']
        rec['zone_now'] = st.get('zone')
        rec['phase'] = 'party'
        party = self.read_party()
        rec['actual'] = party
        rec['shot'] = self.rel(self.shot(base + '.png'))
        rec['hud_shot'] = self.rel(self.hud_crop(base + '.png', base + '_hud.png')) if rec['shot'] else None
        lines = self.log_lines(st['log_from'])
        rec['log'] = [l for l in lines if (l.startswith('forced teams:') and 'getPartyMember' not in l)
                      or (PROBLEM.search(l) and not (l.startswith('test:') and 'error' not in l.lower()))][:60]
        rec['log_problems'] = [l for l in rec['log'] if PROBLEM.search(l)]
        seated = [SEATED.search(l) for l in lines]
        seated = [s for s in seated if s]
        rec['seated'] = parse_party(seated[-1].group(2)) if seated else None
        rec['begin_ran'] = any('xml2fixFeature("forcedteams")' in l for l in lines)
        if not rec['begin_ran'] and self.forced_on:
            rec['notes'].append('no xml2fixFeature("forcedteams") line after the start: did the begin script run?')
        if st.get('conv') and st['conv'].get('shot'):
            rec['conv_shot'] = st['conv']['shot']
        if side:
            rec['phase'] = 'side'
            self.side_check(e, rec, lines, pre, base)
        if e.get('zones') and (st['reached'] or st['load'].get('zones_seen')):
            rec['phase'] = 'zones'
            rec['zones'] = self.visit_zones(e, base)
        elif e.get('zones'):
            rec['notes'].append('zones not visited: the start loaded nothing (stuck?)')
        if side and side.get('end') and (st['reached'] or rec['side'].get('pushed')):
            rec['phase'] = 'side end'
            self.side_end(e, rec, base)
        elif side and side.get('end'):
            rec['notes'].append('side end not run: the start neither loaded nor pushed')
        rec['phase'] = 'done'
        rec['seconds'] = round(self.clock() - t0, 1)
        rec['status'] = self.status_of(e, rec)
        self.say(f'    {m}: {rec["status"]} - party {party_text(party)}, zone {rec["zone_now"]}, '
                 f'{rec["seconds"]:.0f} s')
        return rec

    def press_for(self, kind, movies):
        if kind == 'menu' or (kind == 'seat' and not self.forced_on):
            return 'menu'
        return 'movie' if movies and not self.opt.no_skip_movies else None

    def status_of(self, e, rec):
        st = rec['start']
        if rec.get('actual') is not None and not any(rec['actual']):
            # every getPartyMember is "": a dead party (the team menu drops the dead) or a team never seated - the
            # 2026-09-29 regression's mount "passed" as a keep start with an empty party kept. Never ok, and the walk
            # restarts the game before the next mission (party_empty) whatever the status: a dead party poisons
            # every later start of the session
            rec['party_empty'] = True
            rec['notes'].append('the party reads empty after the start (dead or dropped heroes)')
        if not st['reached']:
            seen = [z for z in st['load']['zones_seen'] if z not in MENU_ZONES and z != st['from_zone']]
            return 'wrong-zone' if seen else 'load-timeout'
        status = 'ok'
        moved_on = (st.get('after') or {}).get('zones')
        if st.get('zone') and st.get('target') and st['zone'] != st['target'] and not moved_on:
            rec['notes'].append(f'reached {st["target"]} but ended up in {st["zone"]}')
            status = 'bounced'
        if e['kind'] == 'seat' and self.forced_on:
            ok = same_party(rec['actual'], e['expected'])
            if ok is None:
                status = 'party-unread' if status == 'ok' else status
            elif not ok:
                status = 'party-mismatch'
            elif order_differs(rec['actual'], e['expected']):
                rec['notes'].append(f'party order {party_text(rec["actual"])} (seatParty: {party_text(e["expected"])})')
        elif e['kind'] == 'keep' and rec.get('pre_party') is not None and rec.get('actual') is not None:
            if not same_party(rec['actual'], rec['pre_party']):
                rec['notes'].append(f'loadMapKeepTeam start changed the party: {party_text(rec["pre_party"])} -> '
                                    f'{party_text(rec["actual"])}')
                status = 'party-mismatch' if status == 'ok' else status
        convs = [st.get('conv')] + list((st.get('after') or {}).get('conversations') or [])
        if any(c and not c.get('ended', True) for c in convs):
            rec['notes'].append('a conversation never ended')
            status = 'conv-stuck' if status == 'ok' else status
        if rec.get('party_empty') and status in ('ok', 'party-mismatch'):
            status = 'party-empty'
        after = (st.get('after') or {}).get('zones')
        if after:
            rec['notes'].append('after the conversation: ' + ' -> '.join(after))
        if st['load'].get('reload_seen') is False:
            rec['notes'].append('same-zone start: the reload was not seen (the log shows the begin ran)')
        side = rec.get('side') or {}
        if self.forced_on and side.get('end') and side.get('status') not in (None, 'restored') and status == 'ok':
            status = 'restore-failed'
        if rec.get('zones'):
            bad = [z['zone'] for z in rec['zones'] if z['status'] != 'ok']
            if bad:
                rec['notes'].append(f'zones not reached: {", ".join(bad)}')
        if rec.get('log_problems'):
            rec['notes'].append(f'{len(rec["log_problems"])} error/warning lines in xml2-fix.log')
        return status

    # ---------------------------------------------------------------- side missions
    def side_check(self, e, rec, lines, pre, base):
        side = rec['side']
        side['pre_zone'] = rec.get('pre_zone')
        side['pre_party'] = pre
        pushes = [PUSHED.search(l) for l in lines]
        pushes = [p for p in pushes if p]
        if pushes:
            p = pushes[-1]
            side['pushed'] = {'record': int(p.group(1)), 'zone': norm_zone(p.group(2)),
                              'party': parse_party(p.group(3))}
        else:
            side['pushed'] = None
            fails = [l for l in lines if 'pushParty' in l]
            rec['notes'].append('no pushParty record in the log' + (f': {fails[-1]}' if fails else ''))

    def side_end(self, e, rec, base):
        side = rec['side']
        end = e['side']['end']
        side['ended'] = True
        pushed = side.get('pushed')
        # popParty returns to the pushed record's zone = where the begin site ran = the zone read before the start
        # (the same memory read the wait uses); no record: the team menu at the end site's fallback zone
        target = (side.get('pre_zone') or pushed['zone']) if pushed else end['pop_zone']
        if pushed and side.get('pre_zone') and pushed['zone'] != side['pre_zone']:
            rec['notes'].append(f'pushed record zone {pushed["zone"]} != zone before the start {side["pre_zone"]}')
        if end['top_level']:
            how, text, mode = 'console', f'runscript {end["ref"]}', 'file'
        else:
            how, text, mode = 'script', r'\n\r'.join(end['statements']), 'statements'
        side['end_mode'] = mode
        if len(f'runscript {text}') > 127:
            rec['notes'].append('side end statements are over 127 characters: sent one by one')
        press = 'menu' if not pushed else self.press_for('keep', end.get('movies'))
        if how == 'script' and len(f'runscript {text}') > 127:
            for s in end['statements'][:-1]:
                self.ask(f'script {s}')
                self.sleep(0.3)
            text = end['statements'][-1]
        st = self.step(how, text, target, press, f'side end ({mode})', conv_shot=base + '_return_conv.png')
        side['end_step'] = st
        lines = self.log_lines(st['log_from'])
        pops = [POPPED.search(l) for l in lines]
        pops = [p for p in pops if p]
        side['pop_log'] = pops[-1].group(0) if pops else None
        party = self.read_party()
        side['return_zone'] = st.get('zone')
        side['return_party'] = party
        side['return_shot'] = self.rel(self.shot(base + '_return.png'))
        want_party = pushed['party'] if pushed else side.get('pre_party')
        side['zone_ok'] = bool(st['reached'])
        side['party_ok'] = same_party(party, want_party)
        if not pushed:
            side['status'] = 'no-record'
        elif side['zone_ok'] and side['party_ok']:
            side['status'] = 'restored'
        elif not side['zone_ok']:
            side['status'] = 'zone-not-restored'
        elif side['party_ok'] is None:
            side['status'] = 'party-unread'
        else:
            side['status'] = 'party-not-restored'
        if side['party_ok'] and order_differs(party, want_party):
            rec['notes'].append(f'returned party order {party_text(party)} (pushed {party_text(want_party)})')
        if pushed and side.get('pre_party') is not None and not same_party(pushed['party'], side['pre_party']):
            rec['notes'].append(f'pushed party {party_text(pushed["party"])} != party before the start '
                                f'{party_text(side["pre_party"])}')
        self.say(f'  side end: {side["status"]} (zone {side["return_zone"]}, party {party_text(party)}; '
                 f'want {target} / {party_text(want_party)})')

    # ---------------------------------------------------------------- zones
    def visit_zones(self, e, base):
        out = []
        for n, z in enumerate(e['zones'], 1):
            leaf = z.replace('/', '_')
            if z == self.zone():
                out.append({'zone': z, 'status': 'ok', 'note': 'already there', 'hud': self.hud(),
                            'shot': self.rel(self.shot(f'{base}_z{n:02d}_{leaf}.png'))})
                continue
            st = self.step('script', f'loadMapKeepTeam("{z}")', z, False, f'zone {n}/{len(e["zones"])}',
                           timeout=self.t(self.opt.zone_timeout))
            shot = self.rel(self.shot(f'{base}_z{n:02d}_{leaf}.png')) if st['reached'] else None
            out.append({'zone': z, 'status': 'ok' if st['reached'] else 'not-reached', 'zone_now': st.get('zone'),
                        'load_s': st['load']['seconds'], 'hud': st.get('hud'),
                        'conversation': bool(st.get('conv') and st['conv']['handled']), 'shot': shot})
        return out


# ================================================================================================ report
def md_cell(x):
    return str(x if x is not None else '').replace('|', '\\|').replace('\n', ' ')


def write_reports(results, state):
    with open(os.path.join(results, 'campaign.json'), 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=1)
    recs = sorted(state['missions'], key=lambda r: (r.get('index') or 0, r.get('mission') or ''))
    counts = {}
    for r in recs:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    L = [f'# XML1 campaign walk: {os.path.basename(os.path.normpath(state["build"]))}', '',
         f'Build `{state["build"]}`; started {state["started"]}'
         + (f', finished {state["finished"]}' if state.get('finished') else ' (running)') + '.',
         f'Order: {state["order_source"]}. xml2-fix.ini: InputPipe={state["ini"].get("input_pipe")} '
         f'ForcedTeams={state["ini"].get("forced_teams")}, pipe {state["ini"].get("pipe") or "-"}. Party read: '
         f'{state.get("party_form") or "never answered"}. Keep-alive: '
         f'{"on" if (state.get("options") or {}).get("keep_alive") else "off (--mortal)"}.', '',
         'Status counts: ' + ', '.join(f'{k} {v}' for k, v in sorted(counts.items())), '',
         '| # | mission | act | start | expected party | actual party | zone | status | s | notes | shot |',
         '|---|---|---|---|---|---|---|---|---|---|---|']
    for r in recs:
        exp = expected_text(r) if r.get('kind') != 'keep' else f'(kept) {party_text(r.get("pre_party"))}'
        zone = r.get('zone_now') or r.get('target_zone') or ''
        if r.get('target_zone') and zone != r.get('target_zone'):
            zone = f'{zone} (want {r["target_zone"]})'
        shots = ' '.join(f'[{lbl}]({r[k]})' for k, lbl in (('shot', 'png'), ('hud_shot', 'hud'), ('conv_shot', 'conv'))
                         if r.get(k))
        notes = '; '.join(r.get('notes') or [])
        if r.get('crash'):
            notes = f'CRASH in {r.get("phase")}: {r["crash"].get("why")}; ' + notes
        if r.get('skip'):
            notes = r['skip']
        L.append('| ' + ' | '.join(md_cell(x) for x in (
            r.get('index'), r.get('mission'), r.get('act'), r.get('kind'), exp,
            party_text(r.get('actual')) if 'actual' in r else '', zone, r['status'], r.get('seconds', ''),
            notes, shots)) + ' |')
    sides = [r for r in recs if r.get('side')]
    if sides:
        L += ['', '## Side missions', '',
              '| mission | begin site | before (zone / party) | pushed record | end site | returned (zone / party) | '
              'status | shot |', '|---|---|---|---|---|---|---|---|']
        for r in sides:
            s = r['side']
            pushed = s.get('pushed')
            L.append('| ' + ' | '.join(md_cell(x) for x in (
                r['mission'], s.get('begin'), f'{s.get("pre_zone")} / {party_text(s.get("pre_party"))}',
                f'#{pushed["record"]} {pushed["zone"]} / {party_text(pushed["party"])}' if pushed else 'none',
                f'{s.get("end")} ({s.get("end_mode", "-")})',
                f'{s.get("return_zone")} / {party_text(s.get("return_party"))}' if s.get('ended') else '-',
                s.get('status', '-'), f'[png]({s["return_shot"]})' if s.get('return_shot') else '')) + ' |')
    zoned = [r for r in recs if r.get('zones')]
    if zoned:
        L += ['', '## Zones', '', '| mission | zone | status | load s | HUD | conversation | shot |',
              '|---|---|---|---|---|---|---|']
        for r in zoned:
            for z in r['zones']:
                L.append('| ' + ' | '.join(md_cell(x) for x in (
                    r['mission'], z['zone'], z['status'], z.get('load_s'), 'yes' if z.get('hud') else 'no',
                    'yes' if z.get('conversation') else '', f'[png]({z["shot"]})' if z.get('shot') else '')) + ' |')
    if state.get('launches'):
        L += ['', '## Launches', '']
        for la in state['launches']:
            L.append(f'- {la["n"]} at {la["time"]}: {la["reason"]} (gamedbg: `{la["gamedbg_log"]}`)')
    crashes = [r for r in recs if r.get('crash')]
    if crashes:
        L += ['', '## Crashes', '']
        for r in crashes:
            c = r['crash']
            L.append(f'### {r["mission"]} ({r.get("phase")})')
            L += ['```'] + (c.get('first_exception') or c.get('gamedbg') or []) + ['```']
            if c.get('fix_log_tail'):
                L += ['xml2-fix.log tail:', '```'] + c['fix_log_tail'] + ['```']
    probs = [r for r in recs if r.get('log_problems')]
    if probs:
        L += ['', '## xml2-fix.log errors / warnings', '']
        for r in probs:
            L.append(f'- **{r["mission"]}**')
            L += [f'  - `{l[:220]}`' for l in r['log_problems'][:10]]
    with open(os.path.join(results, 'campaign.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')


# ================================================================================================ main
STALLS = ('load-timeout', 'wrong-zone', 'bounced')      # restart after --restart-after of these in a row
RESTART_NOW = ('conv-stuck', 'stalled', 'party-empty')     # the game is stuck: restart before the next mission


def walk(build, results, plan, ini, opt, walker=None):
    os.makedirs(os.path.join(results, 'shots'), exist_ok=True)
    state_path = os.path.join(results, 'campaign.json')
    state = None
    if opt.resume and os.path.isfile(state_path):
        state = load_json(state_path)
        if state:
            state.pop('finished', None)
    if not state:
        state = {'build': os.path.abspath(build), 'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'missions': [],
                 'launches': [], 'ini': ini, 'options': {k: v for k, v in vars(opt).items()},
                 'order_source': ORDER_SOURCE + (' (--missions)' if opt.missions else ''),
                 'plan': [{k: e.get(k) for k in ('index', 'mission', 'kind', 'start_ref', 'expected', 'zone', 'skip')}
                          for e in plan]}
    state.setdefault('options', {})['keep_alive'] = bool(getattr(opt, 'keep_alive', False))  # this run's (--resume)
    done = {r['mission'] for r in state['missions']}
    wk = walker or Walker(build, results, opt, ini)
    earlier_launches = list(state.get('launches') or [])
    stalls = tool_errors = 0

    def save():
        state['launches'] = earlier_launches + wk.launches
        if wk.party_form is not None:  # which getPartyMember statement compiled: a bare call or an assignment
            state['party_form'] = f'{wk.party_form}getPartyMember(i)'
        write_reports(results, state)

    def put(rec):
        state['missions'] = [r for r in state['missions'] if r['mission'] != rec['mission']] + [rec]
        save()

    try:
        for e in plan:
            if e['mission'] in done:
                continue
            if e['skip']:
                put({'index': e['index'], 'mission': e['mission'], 'act': e['act'], 'kind': e['kind'],
                     'expected': e.get('expected'), 'target_zone': e.get('zone'), 'status': 'skipped',
                     'skip': e['skip'], 'notes': []})
                continue
            wk.cur = None

            def partial():
                return wk.cur or {'index': e['index'], 'mission': e['mission'], 'act': e['act'], 'kind': e['kind'],
                                  'expected': e.get('expected'), 'target_zone': e.get('zone'), 'notes': [],
                                  'phase': 'launch / new game'}
            try:
                wk.ensure_game()
                rec = wk.run_mission(e)
                tool_errors = 0
            except GameGone as ex:
                rec = partial()
                rec['status'] = 'crash'
                rec['crash'] = wk.crash_info(ex)
                wk.say(f'    {e["mission"]}: CRASH in {rec.get("phase")} ({ex})')
                wk.pid = None
            except RuntimeError as ex:  # pipe trouble, a stuck conversation, a front end that never let go
                rec = partial()
                rec['status'] = 'stalled'
                rec.setdefault('notes', []).append(str(ex))
                wk.say(f'    {e["mission"]}: stalled in {rec.get("phase")} ({ex})')
            except Exception as ex:  # noqa: BLE001 - a bug in this tool: record it, go on, stop after 3 in a row
                rec = partial()
                rec['status'] = 'tool-error'
                rec.setdefault('notes', []).append(f'{type(ex).__name__}: {ex}')
                rec['traceback'] = traceback.format_exc().splitlines()[-12:]
                wk.say(f'    {e["mission"]}: TOOL ERROR in {rec.get("phase")}: {type(ex).__name__}: {ex}')
                tool_errors += 1
                if tool_errors >= 3:
                    put(rec)
                    raise Stop('3 tool errors in a row (a bug in campaign_walk.py; see the tracebacks in campaign.json)')
            if rec.get('status') == 'ok' and not opt.keep_trace:
                rec.pop('trace', None)
            put(rec)
            stalls = stalls + 1 if rec['status'] in STALLS else 0
            if rec['status'] in RESTART_NOW or rec.get('party_empty') or stalls >= opt.restart_after:
                # an empty (dead) party poisons every later start of the session: seatParty re-seats the dead hero
                why = (f'{e["mission"]} {rec["status"]}' if rec['status'] in RESTART_NOW
                       else f'{e["mission"]}: the party reads empty' if rec.get('party_empty')
                       else f'{opt.restart_after} failed starts in a row')
                stalls = 0
                try:
                    wk.restart(why)
                except (GameGone, RuntimeError) as ex:
                    wk.say(f'restart failed: {ex}')
                    wk.pid = None
    except Stop as ex:
        state['stopped'] = str(ex)
        print(f'STOP: {ex}', flush=True)
    except KeyboardInterrupt:
        state['stopped'] = 'interrupted'
        print('interrupted', flush=True)
    finally:
        state['finished'] = time.strftime('%Y-%m-%d %H:%M:%S')
        save()
    if opt.close_at_end and wk.launched:
        try:
            wk.kill_ours()
        except Stop:
            pass
    counts = {}
    for r in state['missions']:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    print('done', counts, '->', os.path.join(results, 'campaign.md'), flush=True)
    return state


ORDER_SOURCE = 'research/scripts/mission_plan.json groups (XML1 data/missions/missions.xml act files, file order)'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('build')
    ap.add_argument('results', nargs='?')
    ap.add_argument('--dry-run', action='store_true', help='parse the build and print the plan; never touch the game')
    ap.add_argument('--json', action='store_true', help='with --dry-run: the plan as JSON')
    ap.add_argument('--missions', help='comma list, walked in this order (any mission, extras included)')
    ap.add_argument('--from', dest='from_', metavar='MISSION', help='start the campaign order here')
    ap.add_argument('--to', metavar='MISSION', help='stop the campaign order after this one')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--extras', action='store_true',
                    help='keep the act-9 Danger Room replays (boss_*, demo, *test*, ice_wolverine, status_meeting)')
    ap.add_argument('--reachable-only', action='store_true', help='only research/sweep/graph.json reachable_missions')
    ap.add_argument('--include-cut', action='store_true', help='also start missions whose zone is not in the build')
    ap.add_argument('--zones', action='store_true', help='also visit every zone of each mission (loadMapKeepTeam)')
    ap.add_argument('--no-sides', action='store_true', help='side missions as plain begins (no push/pop check)')
    ap.add_argument('--side-parent', action='store_true', help='start the parent mission before a side mission')
    ap.add_argument('--no-launch', action='store_true', help='only attach to a running game')
    ap.add_argument('--no-relaunch', action='store_true', help='stop at the first crash')
    ap.add_argument('--max-launches', type=int, default=12)
    ap.add_argument('--restart-after', type=int, default=2, help='restart the game after N stalls in a row')
    ap.add_argument('--no-skip-movies', action='store_true', help="don't press Enter through begin-body movies")
    ap.add_argument('--resume', action='store_true', help='keep <results>/campaign.json and skip recorded missions')
    ap.add_argument('--close-at-end', action='store_true', help='close the game at the end if this walk launched it')
    ap.add_argument('--keep-trace', action='store_true', help='keep the progress lines of ok missions in the JSON too')
    ap.add_argument('--mortal', action='store_true',
                    help='no keep-alive (setInvulnerable + restoreHealth before every start and after every settle)')
    ap.add_argument('--slow', type=float, default=1.0, help='multiply every timeout (slow PC / debug DLL)')
    for name, default in (('boot-timeout', 300), ('load-timeout', 240), ('settle-timeout', 90),
                          ('no-hud-settle', 45), ('conv-open', 6), ('conv-timeout', 180), ('party-timeout', 6),
                          ('zone-timeout', 150), ('post', 8)):
        ap.add_argument(f'--{name}', type=float, default=default)
    ap.add_argument('--boot-wait', type=float, default=30, help='seconds after launch before the first Enter')
    ap.add_argument('--poll', type=float, default=1.0)
    ap.add_argument('--conv-gap', type=float, default=1.3)
    ap.add_argument('--quiet', type=float, default=2.0, help='seconds without a conversation before a new start')
    ap.add_argument('--press-every', type=float, default=5.0)
    ap.add_argument('--wrong-grace', type=float, default=30,
                    help='another zone settled this long during a load wait = wrong-zone')
    ap.add_argument('--max-presses', type=int, default=12)
    opt = ap.parse_args(argv)
    opt.keep_alive = not opt.mortal
    build = os.path.abspath(opt.build)
    if os.path.normcase(build).startswith(REAL_INSTALL):
        sys.exit('refusing the real XML2 install')
    if not os.path.isfile(os.path.join(build, 'XMen2.exe')) or not os.path.isdir(os.path.join(build, 'Scripts')):
        sys.exit(f'{build}: not a build directory (XMen2.exe, Scripts)')
    plan, ini = build_plan(build, opt)
    if opt.dry_run:
        if opt.json:
            print(json.dumps({'build': build, 'ini': ini, 'order_source': ORDER_SOURCE, 'plan': plan}, indent=1))
        else:
            print_plan(build, plan, ini, opt)
        return 0
    if not opt.results:
        sys.exit('results directory missing (or pass --dry-run)')
    if ini.get('input_pipe') != '1' or not ini.get('dll'):
        sys.exit(f'{build}: no pipe harness (python tools/harness.py install {opt.build})')
    import fixinput
    ini['pipe'] = fixinput.use_build(build)  # the build's own pipe; SystemExit if XML2FIX_PIPE names another
    if ini.get('forced_teams') != '1':
        print('note: [Game] ForcedTeams is not 1 - forced starts open the team menu; parties are recorded, not checked')
    state = walk(build, os.path.abspath(opt.results), plan, ini, opt)
    return 0 if not state.get('stopped') or state['stopped'] == 'interrupted' else 1


if __name__ == '__main__':
    sys.exit(main())
