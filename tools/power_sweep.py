r"""Fire every playable hero's powers in a running game, unattended, and report which ones work.

usage: power_sweep.py <build_dir> <results_dir> [--heroes a,b] [--zone Z] [--level auto|N] [--no-level]
                      [--xp-mode auto|set|award] [--quick fallback|always|off] [--retries N] [--frames 30]
                      [--frame-gap 0.06] [--post-wait 2.5] [--keep-full] [--teleport ENTITY] [--unlock] [--resume]
                      [--no-launch] [--no-relaunch] [--close-at-end] [--slow F] [--load-timeout S] ...
       power_sweep.py <build_dir> --dry-run [--json] [--heroes a,b] [--zone Z] [--level auto|N] [--no-level]

--dry-run only parses the build and the registry and prints the plan: the heroes (herostat entries with
team="hero"; placeholders such as defaultman / Magneto / x1pad* are listed as skipped), each hero's four wheel slots
with their key, FightMove, talent (Data/talents/<hero>), name and required level, the test zone's player start and
enemy spawners, the keys and a time estimate. It never looks for the game, the pipe or its memory.

Needs: the xml2-fix test harness in the build (tools/harness.py install <build>: [Test] InputPipe=1, [Game]
ForcedTeams=1, windowed + RunInBackground) and an xml2-fix with seatParty and getPartyMember (branch display
7b457dc+). The pipe takes ONE client: while this runs, don't use fixinput.py, campaign_walk.py or tour_runner.py on
the same game. The game handling is campaign_walk.py's (Walker): an XMen2.exe from <build_dir> with the pipe up is
attached to (New Game from the main menu: Enter, Enter), none running -> <build_dir>\XMen2.exe is launched under
tools/gamedbg.py (log <results>/gamedbg_<time>_NN.log) and a New Game started. Only <build_dir>'s XMen2.exe is ever
found, driven or killed; other folders' games are left alone (the sweep stops if one of them serves the same pipe).
The pipe is the one the build's xml2-fix.ini names ([Test] PipeName; fixinput.use_build: no XML2FIX_PIPE needed).

Keys (XML2 PC). The Player 1 keyboard bindings are read from HKCU\Software\Activision\X-Men Legends 2\Controls\
Player1 (<Action>1 / <Action>2, (device << 16) | DIK code, device 1 = keyboard); an action without a keyboard binding
there gets XMen2.exe's default (action table 0x6EE1F0). Power = NUMPAD5, held: the power wheel. Its four slots are
the four face actions, as igct.bnx labels them ("Attack / Power 1", "Smash / Power 2", "Use / Boost", "Jump /
Xtreme"; UsePowerDown = Power 1, UsePowerRight = Power 2, UsePowerLeft = Power Boost, UsePowerUp = Power Xtreme)
and as the console pad's A / B / X / Y sit:
    bottom  LowAttack  NUMPAD4   herostat power1   (verified in game: Wolverine, Cyclops)
    right   HighAttack NUMPAD6   herostat power2
    left    Guard      E         herostat power3   (the boost slot; XML1's power3 talents are the boosts)
    top     Jump       SPACE     herostat power4   (the Xtreme slot; every hero's power4 is power9 = the Xtreme)
Quick powers QuickPower01..11 = 1..9, 0, MINUS are tried as FightMove power1..power11 (an assumption: --quick).

Levels. XML1 heroes start at level 1 with power1 only; power2/power3 need level 5 and the Xtreme level 15 (the
talent's first <require cat="level">). XML2 has no setLevel / talent script function; it has setXP(entity, xp)
(0x4a8660: adds xp to the actor, then the level check 0x421610), awardXPToPlayable(xp) (0x49d9d0: the whole roster;
retail scripts use it), setAutoSpend(stats, skills) (0x4a02c0: every herostat hero; the first level-up popup
0x41ca40 offers (1,1) / (1,0) / (0,1) = strings 177-179 (auto-spend stat and skill points / stats only / skills only)
after its first option, 181 (leave the hero's settings as they are), which runs
nothing), restoreEnergy(entity, n) (0x4a2c20 -> 0x42cb70: adds n energy) and addXtremePip() (0x4a0240). XP per level
is XMen2.exe's table (0x448a90): T(1) = 0, T(L) = T(L-1) + (730 + 65 (L - 2)) L + 1500 - level 5 = 17910, level 15 =
172935; when the build's xml2-fix.ini has [Game] XPCurve=xml1 (harness.py writes it for XML1 builds; SPEC 23), the
DLL has the game use XML1's (default.xbe 0x541e0: T1(L) = T1(L-1) + 5 (L + 8) trunc(2.5 (4/3)^(L - 2)), cap 45) -
level 5 = 830, level 15 = 41265 - and the sweep computes its XP from that one. So: after the level-1 slots,
setAutoSpend(1,1), then T(--level) + 1 XP (--level auto = the highest level the hero's untested slots need), Enter
for that popup (its first option keeps the (1,1)), and the wheel is looked at again: which slots are filled now.
--xp-mode auto tries setXP("_ACTIVE_HERO_", xp) first (only the tested hero levels, the others keep level 1 for
their own level-1 test) and awardXPToPlayable if no new slot filled; the method that worked is used first for the
next heroes.

Per hero (all of it logged to stdout as it happens):
  1. wait until no conversation is up (Walker.quiet), then `script seatParty("<hero>","","","")\n\r
     loadMapKeepTeam("<zone>")` and wait for the zone (the reload of the zone it is in counts once the HUD went down
     and came back), settle, click through conversations;
  2. read the party (getPartyMember 0..3 + the xml2-fix.log "forced teams:" lines): the hero must be seated;
  3. setInvulnerable("_ACTIVE_HERO_","TRUE") (enemies stay near but can't end the test), optional --teleport;
     screenshot; the wheel with Power held (slot fill: an empty slot is uniform dark, a filled one differs from the
     frame before the wheel);
  4. the slots the hero has at its start level (power1; all four for ProfXAstral / ProfXGladiator, level 40):
     restoreEnergy + restoreHealth("_ACTIVE_HERO_",10000) and a wait until the energy bar is full or holds still
     (--restore-timeout), (top slot: addXtremePip() x --xtreme-pips), a frame, then Power down,
     a wheel frame, the slot key down --tap-ms, up, Power up, --frames screenshots --frame-gap s apart, a frame
     --post-wait s later. Energy = the blue bar in the bottom-left HUD (fill / (fill + empty) of the bar rows,
     median over the rows; calibrated on build/walk1 + build/_pf_shots: 137 px long at 1280x720, fill
     (40,130,186), empty (64,64,64), rows 637-647). A drop of --min-drop (0.025 = 2.5 % of the bar) from the frame
     before to the lowest burst frame = fired. Not fired -> --retries more tries, then (--quick fallback) the quick
     power key. The burst defaults (--frames 30 --frame-gap 0.06 --post-wait 2.5, about 2 s of frames and the after
     frame 2.5 s later) are the re-run options of the baseline sweeps (build/powers_redo, powers_nb2) and of the
     2026-09-29 regression's 64/64: with the old 14 / 0.04 / 1.2 a boost slot (left: Beastial Feats, Bait,
     Telekinetic Shield, Psychic Defense, Bullet Proof) read no-energy-change - the HUD still showed the spent energy
     as a grey trail in the "after" frame. --keep-full only changes what is kept, not what is measured;
  5. the level-up (above), a new wheel frame, then the other slots as in 4;
  6. the new xml2-fix.log lines of every attempt (the pipe's own "test:" lines left out), and any crash: the
     attempt that was running is marked crash, the game is relaunched (New Game) and the hero's remaining slots
     go on (--max-crashes per hero).

Statuses (per slot): fired (the energy dropped), no-energy-change, empty-slot (no energy change and the wheel showed
the slot empty: the power is not in the wheel), no-hud (the bar could not be read), crash (the game went while this
power was fired), untested (the plan never reaches its level: --no-level, or --level N below its requirement),
not-run (the hero failed before this slot: load-failed / not-seated / stalled / crash limit). A leveled slot is
fired even when the level-up filled no new slot (the hero record says so: level-up "nothing filled"). An Xtreme may
cost no energy in XML2 (it spends the Xtreme pips): a top-slot no-energy-change needs a look at its frames.

Output: <results>/powers.json (the plan, the keys, one record per hero: party, wheel states, level-up steps, one
record per slot with every attempt - energy before / lowest / after, drop, the burst's energies and timings, wheel
state, frames, xml2-fix.log lines, status; rewritten after every hero, --resume skips the finished heroes),
<results>/powers.md (tables: hero, slot, keys, power (move / talent / name), level, wheel, energy before -> lowest
-> after, status, notes, frame links), <results>/shots/<NN>_<hero>/ (seated.png, wheel_start.png,
levelup_<method>.png, wheel_leveled_<method>.png; per attempt <phase>_<slot>[_quick][_tryN]: _hud.png (portrait +
bars of the frame before, the lowest-energy burst frame and the frame after, stacked), _min.jpg (that burst frame,
full size), _wheel.png (the wheel, cropped), _pre.jpg / _fNN.jpg (the burst) / _post.jpg at half size; --keep-full
keeps them all as full-size PNGs; a crash's last grabs are kept as PNGs and linked from the Crashes section).

Test zone (--zone, default nyc/alison/nyc1_1_1): XML1's opening zone - the zone every in-game power check so far used
(Wolverine's claw power fired there, the energy calibration shots are from it), no conversation or modal popup on
entry by loadMapKeepTeam (its zone script only sets AI flags; the tutorial tips are "?" pickups that need Use), and
14 grso_riot monster spawners with instantspawn / aggression 3, the nearest ~610 units from player_start01 (the
dry run prints the distances): enemies walk up within seconds, so targeted powers have targets.

Timeouts (seconds; --slow F multiplies them all and the waits between steps): --boot-timeout 300, --load-timeout 240,
--settle-timeout 90, --no-hud-settle 45, --conv-open 6, --conv-timeout 180, --party-timeout 6, --hud-timeout 30
(HUD back before an attempt), --levelup-wait 4, --restore-timeout 4. Waits: --wheel-open 0.35, --tap-ms 150,
--restore-wait 0.8, --post-wait 2.5, --poll 1.0, --conv-gap 1.3, --quiet 2.0, --press-every 5.

examples:
  python tools/power_sweep.py build/_heroes --dry-run
  python tools/power_sweep.py build/_heroes build/powers1 --heroes wolverine,cyclops
  python tools/power_sweep.py build/_heroes build/powers_all --resume       (about 30 min: run it in the background)
"""
import argparse
import json
import math
import os
import re
import statistics
import sys
import time
import traceback
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import xmlb  # noqa: E402
from campaign_walk import (GameGone, PROBLEM, REAL_INSTALL, SEATED, Stop, Walker, load_json, md_cell,  # noqa: E402
                           norm_zone, party_text, read_ini)

DEFAULT_ZONE = 'nyc/alison/nyc1_1_1'

# The wheel: slot, herostat attribute index (power<i>), the action whose key picks it while Power is held.
SLOTS = (('bottom', 1, 'LowAttack'), ('right', 2, 'HighAttack'), ('left', 3, 'Guard'), ('top', 4, 'Jump'))

# Screen geometry at 1280x720 (the harness window; scaled for other sizes). From build/_pf_shots/wheel.png and
# build/walk1/shots/001_alison.png: the wheel's slot centres (empty slot = uniform (11,12,12)), the bars' rows.
REF_W, REF_H = 1280, 720
SLOT_CENTRE = {'top': (138, 75), 'left': (78, 135), 'right': (198, 135), 'bottom': (138, 195)}
SLOT_R = 18
BAR_X = (175, 350)          # both bars' fill + empty span lies inside (parallelograms, 1 px per 2 rows)
BAR_LEN = 137               # fill + empty pixels per row
ENERGY_ROWS = (638, 646)    # blue bar rows 637-647
HEALTH_ROWS = (624, 633)    # red bar rows 623-634
HUD_BOX = (90, 505, 400, 668)
WHEEL_BOX = (30, 20, 250, 250)

# XMen2.exe's keyboard defaults (action table 0x6EE1F0, player 1, slot 1) for the actions the sweep uses.
DEFAULT_DIK = {'LowAttack': 0x4B, 'HighAttack': 0x4D, 'Guard': 0x12, 'Jump': 0x39, 'Power': 0x4C}
DEFAULT_DIK.update({f'QuickPower{n:02d}': code for n, code in zip(range(1, 12), list(range(0x02, 0x0C)) + [0x0C])})
DIK_NAME = {0x02: '1', 0x03: '2', 0x04: '3', 0x05: '4', 0x06: '5', 0x07: '6', 0x08: '7', 0x09: '8', 0x0A: '9',
            0x0B: '0', 0x0C: 'MINUS', 0x10: 'Q', 0x11: 'W', 0x12: 'E', 0x13: 'R', 0x14: 'T', 0x15: 'Y', 0x16: 'U',
            0x17: 'I', 0x18: 'O', 0x19: 'P', 0x1C: 'RETURN', 0x1D: 'LCONTROL', 0x1E: 'A', 0x1F: 'S', 0x20: 'D',
            0x21: 'F', 0x22: 'G', 0x23: 'H', 0x24: 'J', 0x25: 'K', 0x26: 'L', 0x29: 'GRAVE', 0x2A: 'LSHIFT',
            0x2C: 'Z', 0x2D: 'X', 0x2E: 'C', 0x2F: 'V', 0x30: 'B', 0x31: 'N', 0x32: 'M', 0x39: 'SPACE', 0x3B: 'F1',
            0x47: 'NUMPAD7', 0x48: 'NUMPAD8', 0x49: 'NUMPAD9', 0x4B: 'NUMPAD4', 0x4C: 'NUMPAD5', 0x4D: 'NUMPAD6',
            0x4F: 'NUMPAD1', 0x50: 'NUMPAD2', 0x51: 'NUMPAD3', 0x52: 'NUMPAD0', 0x9C: 'NUMPADENTER', 0x9D: 'RCONTROL',
            0xC8: 'UP', 0xCB: 'LEFT', 0xCD: 'RIGHT', 0xD0: 'DOWN'}
CONTROLS_KEY = r'Software\Activision\X-Men Legends 2\Controls\Player1'

HERO = '_ACTIVE_HERO_'
SCRIPT_MAX = 127            # the console queue keeps 127 characters, "runscript " included


MAX_LEVEL = {'xml2': 99, 'xml1': 45}   # XMen2.exe 0x44b690; with xml2-fix [Game] XPCurve=xml1, default.xbe 0x56c80


def xp_curve(ini):
    """'xml1' when the build's xml2-fix.ini has [Game] XPCurve=xml1 (tools/harness.py writes it for XML1 builds; the
    DLL then uses XML1's level table, SPEC 23), else 'xml2' (the game's own)."""
    value = (ini.get('xp_curve') or '').split(';')[0].strip().lower()
    return 'xml1' if value == 'xml1' else 'xml2'


def xml1_kill_xp(level):
    """default.xbe 0x54800, XML1's kill XP and the step of its level table: trunc(2.5 (4/3)^(level - 1)), exactly."""
    return math.floor(Fraction(5, 2) * Fraction(4, 3) ** (level - 1))


def xp_for_level(level, curve='xml2'):
    """The XP a hero needs for `level` (level 1 = 0) on the build's curve: XMen2.exe 0x448a90 (T(L) = T(L-1) +
    (730 + 65 (L - 2)) L + 1500, cap 99) or, with XPCurve=xml1, XML1's table the DLL reads instead (default.xbe
    0x541e0: T1(L) = T1(L-1) + 5 (L + 8) f(L-1), cap 45; xml2-fix xp_curve_rules.hpp has the same numbers)."""
    top = max(1, min(int(level), MAX_LEVEL[curve]))
    total = 0
    if curve == 'xml1':
        for lv in range(2, top + 1):
            total += 5 * (lv + 8) * xml1_kill_xp(lv - 1)
        return total
    step = 730
    for lv in range(2, top + 1):
        total += step * lv + 1500
        step += 65
    return total


# ================================================================================================ plan (offline)
def dik_name(code):
    return DIK_NAME.get(code, f'0x{code:02X}')


def read_bindings():
    """{action: {'code', 'key', 'source'}} from the registry (keyboard bindings only), else XMen2.exe's defaults."""
    values, err = {}, None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CONTROLS_KEY) as k:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(k, i)
                except OSError:
                    break
                values[name] = value
                i += 1
    except (OSError, ImportError) as e:
        err = str(e)
    out = {}
    for action, default in DEFAULT_DIK.items():
        got = None
        for slot in ('1', '2'):
            v = values.get(action + slot)
            if isinstance(v, int) and (v >> 16) == 1 and (v & 0xFFFF) not in (0, 0xFFFF):
                got = (v & 0xFFFF, f'registry {action}{slot}')
                break
        if got is None:
            why = 'no registry key' if err else ('not bound to a key' if any(action + s in values for s in '12')
                                                 else 'not in the registry')
            got = (default, f'default ({why})')
        out[action] = {'code': got[0], 'key': dik_name(got[0]), 'source': got[1]}
    return out


def decode(path):
    with open(path, 'rb') as f:
        return xmlb.decode(f.read())


def first_file(*paths):
    return next((p for p in paths if os.path.isfile(p)), None)


def talent_values(t):
    return {tv.get('name'): tv.get('value') for tv in t.iter('talentvalue') if tv.get('level') == '1'}


def required_level(t):
    """The talent's first <level>'s <require cat="level"> (a %talentvalue resolved at rank 1), or None."""
    lv = t.find('level')
    if lv is None:
        return None
    vals = talent_values(t)
    for rq in lv.findall('require'):
        if rq.get('cat') == 'level':
            v = rq.get('level', '')
            if v.startswith('%'):
                v = vals.get(v[1:], '')
            try:
                return int(float(str(v).split()[0]))
            except (ValueError, IndexError):
                return None
    return None


def load_heroes(build, keys):
    """(heroes, skipped) from the build's herostat + talent files."""
    path = first_file(os.path.join(build, 'Data', 'herostat.engb'), os.path.join(build, 'Data', 'herostat.XMLB'))
    if not path:
        sys.exit(f'{build}: no Data/herostat.engb or .XMLB')
    root = decode(path)
    heroes, skipped = [], []
    for st in root:
        if st.tag != 'stats':
            continue
        name = st.get('name', '')
        if st.get('team') != 'hero':
            skipped.append({'name': name, 'charactername': st.get('charactername'),
                            'why': f'team={st.get("team") or "-"}, skin {st.get("skin")} (hidden placeholder / pad)'})
            continue
        key = name.lower()
        start_level = int(st.get('level', '1') or 1)
        ranks = {t.get('name'): int(float(t.get('level', '0') or 0)) for t in st.findall('talent')}
        tpath = first_file(*(os.path.join(build, 'Data', 'talents', key + ext) for ext in ('.engb', '.XMLB', '.xmlb')))
        talents = {}
        if tpath:
            for t in decode(tpath):
                if t.tag == 'talent' and t.get('name'):
                    talents[t.get('name')] = t
        by_power = {}
        for t in talents.values():
            if t.get('power'):
                by_power.setdefault(t.get('power'), t)
        slots = []
        for slot, n, action in SLOTS:
            move = st.get(f'power{n}')
            t = by_power.get(move) if move else None
            req = required_level(t) if t is not None else None
            rank = ranks.get(t.get('name'), 0) if t is not None else 0
            m = re.match(r'power(\d+)$', move or '')
            qn = int(m.group(1)) if m else None
            qaction = f'QuickPower{qn:02d}' if qn and 1 <= qn <= 11 else None
            slots.append({
                'slot': slot, 'action': action, 'key': keys[action]['key'], 'move': move,
                'talent': t.get('name') if t is not None else None,
                'descname': t.get('descname') if t is not None else None,
                'type': t.get('type') if t is not None else None,
                'req_level': req, 'herostat_rank': rank,
                'at_start': bool(rank) or (req is not None and req <= start_level),
                'quick_action': qaction, 'quick_key': keys[qaction]['key'] if qaction else None,
                'problem': None if t is not None else (f'no talent with power="{move}" in {os.path.basename(tpath)}'
                                                       if tpath and move else
                                                       'no talent file' if not tpath else 'no power%d attribute' % n)})
        heroes.append({'name': name, 'key': key, 'charactername': st.get('charactername'), 'start_level': start_level,
                       'xpexempt': st.get('xpexempt') == 'true', 'powerstyle': st.get('powerstyle'),
                       'talent_file': os.path.relpath(tpath, build).replace('\\', '/') if tpath else None,
                       'slots': slots})
    return heroes, skipped, os.path.relpath(path, build).replace('\\', '/')


def zone_info(build, zone):
    """The test zone: player starts, enemy spawners (character, instances, distance to the first start)."""
    path = os.path.join(build, 'Maps', *zone.split('/')) + '.XMLB'
    if not os.path.isfile(path):
        return {'zone': zone, 'exists': False}
    root = decode(path)
    classes, insts = {}, {}
    for c in root:
        if c.tag == 'entity' and c.get('name'):
            classes[c.get('name')] = c.attrib
        elif c.tag == 'entinst':
            for i in c:
                try:
                    pos = tuple(float(v) for v in i.get('pos', '').split()[:3])
                except ValueError:
                    continue
                if len(pos) == 3:
                    insts.setdefault(c.get('type'), []).append((i.get('name'), pos))
    starts = [p for t, lst in insts.items() if (classes.get(t) or {}).get('classname') == 'playerstartent'
              for _, p in lst]
    spawners = []
    for t, lst in insts.items():
        a = classes.get(t) or {}
        if a.get('classname') == 'monsterspawnerent':
            for name, p in lst:
                d = min((((p[0] - s[0]) ** 2 + (p[1] - s[1]) ** 2) ** 0.5 for s in starts), default=None)
                spawners.append({'type': t, 'character': a.get('character'), 'distance': round(d) if d else None,
                                 'instantspawn': a.get('instantspawn') == 'true'})
    spawners.sort(key=lambda s: s['distance'] if s['distance'] is not None else 1e9)
    script = os.path.join(build, 'Scripts', *zone.split('/')) + '.py'
    conv = False
    if os.path.isfile(script):
        with open(script, encoding='latin-1') as f:
            conv = 'startConversation' in f.read()
    return {'zone': zone, 'exists': True, 'player_starts': len(starts), 'spawners': len(spawners),
            'instant': sum(1 for s in spawners if s['instantspawn']),
            'characters': sorted({s['character'] for s in spawners if s['character']}),
            'nearest': [s['distance'] for s in spawners[:5]], 'zone_script_conversation': conv}


def select_heroes(heroes, spec):
    if not spec:
        return heroes
    want = [w.strip().lower() for w in spec.split(',') if w.strip()]
    out = []
    for w in want:
        h = next((h for h in heroes if w in (h['key'], (h['charactername'] or '').lower())), None)
        if not h:
            sys.exit(f'--heroes: no playable hero "{w}" (have: {", ".join(x["key"] for x in heroes)})')
        if h not in out:
            out.append(h)
    return out


def level_target(h, opt, max_level=99):
    """The level the hero is raised to for its untested slots (0 = none), at most the build's cap."""
    if opt.no_level or h['xpexempt']:
        return 0
    later = [s for s in h['slots'] if not s['at_start'] and s['move']]
    if not later:
        return 0
    if opt.level != 'auto':
        return max(0, min(int(opt.level), max_level))
    return max(min(max((s['req_level'] or 1) for s in later), max_level), 2)


def build_plan(build, opt):
    keys = read_bindings()
    heroes, skipped, herostat = load_heroes(build, keys)
    heroes = select_heroes(heroes, opt.heroes)
    ini = read_ini(build)
    curve = xp_curve(ini)   # the XP that lands a hero on its level depends on the table the DLL has the game use
    for i, h in enumerate(heroes, 1):
        h['index'] = i
        h['level_to'] = level_target(h, opt, MAX_LEVEL[curve])
        h['xp'] = xp_for_level(h['level_to'], curve) + 1 if h['level_to'] else 0
        for s in h['slots']:
            if s['at_start'] or not s['move']:
                s['plan'] = 'start' if s['move'] else 'none'
            elif h['level_to'] and (s['req_level'] or 1) <= h['level_to']:
                s['plan'] = 'leveled'
            else:
                s['plan'] = 'untested'
    return {'heroes': heroes, 'skipped': skipped, 'herostat': herostat, 'keys': keys, 'ini': ini, 'xp_curve': curve,
            'zone': zone_info(build, norm_zone(opt.zone))}


def estimate_seconds(plan, opt):
    t = 0
    for h in plan['heroes']:
        n = sum(1 for s in h['slots'] if s['plan'] in ('start', 'leveled'))
        t += 45 + 6 + n * (9 + (4 if opt.quick == 'always' else 0))
        if h['level_to']:
            t += 20
    return t


def print_plan(build, plan, opt):
    ini, keys, z = plan['ini'], plan['keys'], plan['zone']
    print(f'build {build}')
    print(f'  xml2-fix.ini: InputPipe={ini["input_pipe"]} ForcedTeams={ini["forced_teams"]} Mode={ini["mode"]} '
          f'SaveFolder={ini["save_folder"]} XPCurve={ini.get("xp_curve")} (level-ups on the {plan["xp_curve"]} table); '
          f'dinput.dll {"present" if ini["dll"] else "MISSING"}')
    if ini['input_pipe'] != '1' or not ini['dll']:
        print('  !! the sweep needs the harness: python tools/harness.py install <build>')
    if ini['forced_teams'] != '1':
        print('  !! [Game] ForcedTeams is not 1: seatParty reports off and seats nobody')
    print('  keys: ' + ', '.join(f'{a} {keys[a]["key"]} ({keys[a]["source"]})'
                                 for a in ('Power', 'LowAttack', 'HighAttack', 'Guard', 'Jump')))
    q = [keys[f'QuickPower{n:02d}'] for n in range(1, 12)]
    print(f'  quick powers 1-11: {" ".join(k["key"] for k in q)}'
          f'{"" if all(k["source"].startswith("registry") for k in q) else " (some are defaults)"}')
    if z.get('exists'):
        print(f'  zone {z["zone"]}: {z["player_starts"]} player start(s), {z["spawners"]} enemy spawner instances '
              f'({z["instant"]} instantspawn; {", ".join(z["characters"]) or "-"}), nearest to the start '
              f'{", ".join(str(d) for d in z["nearest"])}; zone script conversation: '
              f'{"yes" if z["zone_script_conversation"] else "no"}')
    else:
        print(f'  !! zone {z["zone"]} is not in the build (Maps/{z["zone"]}.XMLB)')
    print(f'  herostat {plan["herostat"]}: {len(plan["heroes"])} heroes to test'
          + (f' (--heroes {opt.heroes})' if opt.heroes else '') + f', {len(plan["skipped"])} entries skipped:')
    for s in plan['skipped']:
        print(f'      skip {s["name"]:16} {s["why"]}')
    print()
    for h in plan['heroes']:
        lvl = (f'level {h["start_level"]} -> {h["level_to"]} ({h["xp"]} XP)' if h['level_to']
               else f'level {h["start_level"]}' + (' (xpexempt)' if h['xpexempt'] else ''))
        print(f'{h["index"]:3} {h["key"]:16} {h["charactername"] or "":18} {lvl}; style {h["powerstyle"]}, '
              f'talents {h["talent_file"]}')
        for s in h['slots']:
            quick = f'quick {s["quick_key"]}' if s['quick_key'] else 'no quick key'
            name = f'{s["talent"]} "{s["descname"]}"' if s['talent'] else f'!! {s["problem"]}'
            print(f'        {s["slot"]:6} Power+{s["key"]:8} {s["move"] or "-":8} {name:44} '
                  f'req {s["req_level"] if s["req_level"] is not None else "?":>2}'
                  f'{" rank %d" % s["herostat_rank"] if s["herostat_rank"] else "":8} {quick:9} -> {s["plan"]}')
    n = sum(1 for h in plan['heroes'] for s in h['slots'] if s['plan'] in ('start', 'leveled'))
    un = sum(1 for h in plan['heroes'] for s in h['slots'] if s['plan'] == 'untested')
    est = estimate_seconds(plan, opt)
    print(f'\n{len(plan["heroes"])} heroes, {n} slots to fire, {un} untested; rough time {est // 60} min '
          f'(x{opt.slow} slow factor not included)')


# ================================================================================================ frames (pure)
def _box(img, box):
    w_, h_ = img.size
    return (int(round(box[0] * w_ / REF_W)), int(round(box[1] * h_ / REF_H)),
            int(round(box[2] * w_ / REF_W)), int(round(box[3] * h_ / REF_H)))


def _is_empty_bar(r, g, b):
    return abs(r - 64) <= 14 and abs(g - 64) <= 14 and abs(b - 64) <= 14 and max(r, g, b) - min(r, g, b) <= 8


def _is_energy(r, g, b):
    return b >= 140 and 90 <= g <= 175 and r <= 95


def _is_health(r, g, b):
    return r >= 190 and g <= 120 and b <= 70


def bar_fraction(img, rows, is_fill):
    """fill / (fill + empty) of the bar, median over its rows; None if the bar isn't there. Per row the bar is the
    longest unbroken run of fill pixels followed by empty ones, 0.8-1.25 bar lengths long (the black frame ends it,
    so the gray behind the level box doesn't count)."""
    w_, h_ = img.size
    x0, y0, x1, y1 = _box(img, (BAR_X[0], rows[0], BAR_X[1], rows[1]))
    lo, hi = 0.8 * BAR_LEN * w_ / REF_W, 1.25 * BAR_LEN * w_ / REF_W
    px = img.load()
    fracs = []
    for y in range(y0, min(y1, h_ - 1) + 1):
        best = None
        fill = empty = 0
        for x in range(x0, min(x1, w_) + 1):
            c = px[x, y][:3] if x < min(x1, w_) else (255, 255, 255)
            if is_fill(*c) and not empty:
                fill += 1
                continue
            if _is_empty_bar(*c):
                empty += 1
                continue
            if lo <= fill + empty <= hi and (best is None or fill + empty > sum(best)):
                best = (fill, empty)
            fill, empty = (1, 0) if is_fill(*c) else (0, 0)
        if best:
            fracs.append(best[0] / (best[0] + best[1]))
    if len(fracs) < max(3, (y1 - y0 + 1) // 2):
        return None
    return round(statistics.median(fracs), 4)


def measure(path):
    """{'energy', 'health'} of a frame (fractions of the bars; energy None when the HUD isn't there)."""
    if not path or not os.path.isfile(path):
        return {'energy': None, 'health': None}
    from PIL import Image
    try:
        with Image.open(path) as im:
            img = im.convert('RGB')
    except OSError:
        return {'energy': None, 'health': None}
    health = bar_fraction(img, HEALTH_ROWS, _is_health)
    energy = bar_fraction(img, ENERGY_ROWS, _is_energy) if health is not None else None
    return {'energy': energy, 'health': health, 'banner': banner_fraction(img)}


# The Xtreme name banner ("SAVAGE RAMPAGE", "OPTIC RAGE") is white text centred above the hero while the Xtreme
# plays; Xtremes spend Xtreme pips, not energy, so the banner is what shows one fired. Calibrated on the first
# in-game run (build/powers1): 0.07-0.12 in every frame of an Xtreme, other powers' effects only flash it.
BANNER_BOX = (480, 215, 800, 280)
BANNER_MIN = 0.05
BANNER_SHARE = 0.6


def banner_fraction(img):
    x0, y0, x1, y1 = _box(img, BANNER_BOX)
    px = img.load()
    n = total = 0
    for y in range(y0, y1):
        for x in range(x0, x1, 2):
            total += 1
            if min(px[x, y][:3]) > 200:
                n += 1
    return n / total if total else 0.0


def slot_state(img, pre, slot):
    """'empty' (the wheel's uniform dark slot), 'filled' (an icon: textured and unlike the frame before the wheel)
    or '?' (looks like the scene: no wheel)."""
    from PIL import ImageChops, ImageStat
    cx, cy = SLOT_CENTRE[slot]
    box = _box(img, (cx - SLOT_R, cy - SLOT_R, cx + SLOT_R, cy + SLOT_R))
    a = img.crop(box)
    st = ImageStat.Stat(a)
    sd = sum(st.stddev) / 3
    if all(4 <= m <= 24 for m in st.mean) and sd < 4.5:
        return 'empty'
    if pre is not None:
        d = sum(ImageStat.Stat(ImageChops.difference(a, pre.crop(box))).mean) / 3
        return 'filled' if d >= 18 and sd >= 8 else '?'
    return 'filled' if sd >= 14 else '?'


def wheel_state(wheel_path, pre_path):
    """{'up': the wheel was seen, 'slots': {slot: state}} from a frame with Power held and one before it."""
    from PIL import Image
    try:
        with Image.open(wheel_path) as im:
            img = im.convert('RGB')
    except (OSError, AttributeError, TypeError):
        return {'up': False, 'slots': {s: '?' for s, _, _ in SLOTS}}
    pre = None
    if pre_path:
        try:
            with Image.open(pre_path) as im:
                pre = im.convert('RGB')
        except OSError:
            pre = None
    slots = {s: slot_state(img, pre, s) for s, _, _ in SLOTS}
    return {'up': sum(1 for v in slots.values() if v != '?') >= 3, 'slots': slots}


def save_png(src, dst, box=None):
    from PIL import Image
    try:
        with Image.open(src) as im:
            img = im.convert('RGB')
            (img.crop(_box(img, box)) if box else img).save(dst)
        return dst
    except (OSError, TypeError, AttributeError):
        return None


def save_jpg(src, dst, half=True):
    from PIL import Image
    try:
        with Image.open(src) as im:
            img = im.convert('RGB')
            if half:
                img = img.resize((max(1, img.width // 2), max(1, img.height // 2)))
            img.save(dst, quality=82 if half else 90)
        return dst
    except (OSError, TypeError, AttributeError):
        return None


def hud_stack(paths, dst):
    """The portrait + bars of several frames, stacked (pre / lowest / post)."""
    from PIL import Image
    crops = []
    for p in paths:
        try:
            with Image.open(p) as im:
                img = im.convert('RGB')
                crops.append(img.crop(_box(img, HUD_BOX)))
        except (OSError, TypeError, AttributeError):
            continue
    if not crops:
        return None
    out = Image.new('RGB', (max(c.width for c in crops), sum(c.height + 4 for c in crops)), (255, 255, 255))
    y = 0
    for c in crops:
        out.paste(c, (0, y))
        y += c.height + 4
    out.save(dst)
    return dst


# ================================================================================================ game (online)
PIPE_NOISE = re.compile(r'^test: (pipe client|screenshot|tap |down |up |release|hold |script |console )')


class Sweeper(Walker):
    def __init__(self, build, results, opt, ini, plan):
        super().__init__(build, results, opt, ini)
        self.plan = plan
        self.keys = plan['keys']
        self.power = self.keys['Power']['key']
        self.zone_name = norm_zone(opt.zone)
        self.xp_first = None            # 'set' / 'award': the XP method that filled a slot last time
        self.hero_dir = self.shots
        self.firing = None               # (slot record, label) while an attempt runs: a crash lands on it

    # ---------------------------------------------------------------- helpers
    def script(self, stmt):
        if len(f'runscript {stmt}') > SCRIPT_MAX:
            raise RuntimeError(f'script line over {SCRIPT_MAX} characters: {stmt[:60]}...')
        return self.ask(f'script {stmt}')

    def pause(self, seconds):
        """A wait between steps (scaled by --slow), watching the process."""
        self.wait(seconds * self.opt.slow)

    def release_all(self):
        try:
            self._ask('release')
        except BaseException:  # noqa: BLE001 - best effort, the game may be gone
            pass

    def path(self, name):
        return os.path.join(self.hero_dir, name)

    def fix_lines(self, start):
        """The new xml2-fix.log lines without the pipe's own traffic (its errors stay)."""
        return [l for l in self.log_lines(start)
                if (not PIPE_NOISE.match(l) and 'getPartyMember' not in l)
                or (l.startswith('test:') and re.search(r'error|reject|didn.t', l, re.I))][:40]

    def wait_hud(self):
        """HUD up (clicking through a conversation that came up), up to --hud-timeout s. True / False."""
        t0 = self.clock()
        while self.clock() - t0 < self.t(self.opt.hud_timeout):
            c = self.conv()
            if c.get('active'):
                self.conversations(0)
                continue
            if self.hud():
                return True
            self.sleep(self.opt.poll)
        return False

    def finish_frame(self, bmp, png=None, jpg=None):
        """A .bmp grab -> the kept file(s); the .bmp goes. Returns the kept path (png first)."""
        kept = None
        if bmp and os.path.isfile(bmp):
            if png:
                kept = save_png(bmp, png) or kept
            if jpg:
                kept = kept or save_jpg(bmp, jpg)
            try:
                os.remove(bmp)
            except OSError:
                pass
        return kept

    def keep(self, bmp, stem):
        """A burst / pre / post grab: half-size JPEG, or a full-size PNG with --keep-full."""
        if self.opt.keep_full:
            return self.finish_frame(bmp, png=self.path(stem + '.png'))
        return self.finish_frame(bmp, jpg=self.path(stem + '.jpg'))

    def salvage(self):
        """The grabs a crash or an error left as .bmp -> full-size PNGs (the evidence). Returns their paths."""
        out = []
        try:
            names = sorted(os.listdir(self.hero_dir))
        except OSError:
            return out
        for n in names:
            if n.lower().endswith('.bmp'):
                p = os.path.join(self.hero_dir, n)
                kept = self.finish_frame(p, png=p[:-4] + '.png')
                if kept:
                    out.append(self.rel(kept))
        return out

    # ---------------------------------------------------------------- wheel
    def wheel_probe(self, name):
        """Hold Power, grab the wheel. {'up', 'slots', 'shot'}"""
        pre, wh = self.path(f'{name}_nowheel.bmp'), self.path(f'{name}.bmp')
        self.shot(pre)
        try:
            self.ask(f'down {self.power}')
            self.sleep(self.opt.wheel_open)
            self.shot(wh)
        finally:
            try:
                self.ask(f'up {self.power}')
            except (RuntimeError, GameGone):
                self.release_all()
                raise
        st = wheel_state(wh, pre)
        kept = save_png(wh, self.path(f'{name}.png'), None if self.opt.keep_full else WHEEL_BOX)
        self.finish_frame(wh)
        self.finish_frame(pre)
        st['shot'] = self.rel(kept)
        self.say(f'  wheel ({name}): ' + ', '.join(f'{k} {v}' for k, v in st['slots'].items())
                 + ('' if st['up'] else ' - the wheel was not seen'))
        return st

    # ---------------------------------------------------------------- one attempt
    def restore_energy(self):
        """restoreEnergy + restoreHealth, then wait until the energy bar is full or holds still (restoreEnergy may
        refill over time: a bar still rising would hide the drop). Returns the last reading."""
        if self.opt.restore > 0:
            self.script(f'restoreEnergy("{HERO}",{self.opt.restore})\\n\\rrestoreHealth("{HERO}",{self.opt.restore})')
        self.pause(self.opt.restore_wait)
        probe = self.path('_energy.bmp')
        last, t0 = None, self.clock()
        while True:
            e = measure(self.shot(probe))['energy']
            if e is None or e >= 0.99 or (last is not None and abs(e - last) < 0.005) \
                    or self.clock() - t0 > self.t(self.opt.restore_timeout):
                break
            last = e
            self.sleep(0.5)
        self.finish_frame(probe)
        return e

    def attempt(self, s, phase, via, n):
        """Fire slot `s` once: via 'wheel' (hold Power, press the slot key) or 'quick' (the quick-power key)."""
        tag = f'{phase}_{s["slot"]}' + ('_quick' if via == 'quick' else '') + (f'_try{n}' if n > 1 else '')
        key = s['key'] if via == 'wheel' else s['quick_key']
        a = {'via': via, 'try': n, 'keys': f'{self.power}+{key}' if via == 'wheel' else key,
             'time': time.strftime('%H:%M:%S'), 'notes': []}
        if not self.wait_hud():
            a['notes'].append(f'HUD not up after {self.opt.hud_timeout * self.opt.slow:.0f} s')
        self.restore_energy()
        if self.opt.xtreme_pips and (s['slot'] == 'top' or s['move'] == 'power9' or s['type'] == 'xtreme'):
            self.script(r'\n\r'.join(['addXtremePip()'] * self.opt.xtreme_pips))
            self.sleep(0.5)
        pre = self.path(f'{tag}_pre.bmp')
        self.shot(pre)
        m0 = measure(pre)
        a['energy_before'], a['health_before'] = m0['energy'], m0['health']
        log_from = self.log_size()
        wheel = None
        t0 = self.clock()
        try:
            if via == 'wheel':
                self.ask(f'down {self.power}')
                self.sleep(self.opt.wheel_open)
                wheel = self.path(f'{tag}_wheel.bmp')
                self.shot(wheel)
                t0 = self.clock()
                self.ask(f'down {key}')
                self.sleep(self.opt.tap_ms / 1000)
                self.ask(f'up {key}')
                self.ask(f'up {self.power}')
            else:
                t0 = self.clock()
                self.ask(f'tap {key} {self.opt.tap_ms}')
        except (RuntimeError, GameGone):
            self.release_all()
            raise
        burst = []
        for i in range(self.opt.frames):
            tt = self.clock()
            p = self.path(f'{tag}_f{i:02d}.bmp')
            got = self.shot(p)
            burst.append({'t': round(tt - t0, 3), 'bmp': got})
            left = self.opt.frame_gap - (self.clock() - tt)
            if left > 0:
                self.sleep(left)
        self.pause(self.opt.post_wait)
        post = self.path(f'{tag}_post.bmp')
        self.shot(post)
        self.release_all()
        a['log'] = self.fix_lines(log_from)
        a['log_problems'] = [l for l in a['log'] if PROBLEM.search(l)]
        # measure, then keep what's worth keeping
        for f in burst:
            f.update(measure(f['bmp']))
        m1 = measure(post)
        a['energy_after'], a['health_after'] = m1['energy'], m1['health']
        seen = [f for f in burst if f['energy'] is not None]
        low = min(seen, key=lambda f: f['energy']) if seen else None
        a['energy_min'] = low['energy'] if low else None
        a['energy_burst'] = [f['energy'] for f in burst]
        a['burst_t'] = [f['t'] for f in burst]
        if wheel:
            ws = wheel_state(wheel, pre)
            a['wheel_up'], a['wheel_slot'] = ws['up'], ws['slots'][s['slot']]
        if a['energy_before'] is not None and low is not None:
            a['drop'] = round(a['energy_before'] - low['energy'], 4)
        else:
            a['drop'] = None
        xtreme = s['slot'] == 'top' or s['move'] == 'power9' or s['type'] == 'xtreme'
        banners = [f.get('banner') or 0.0 for f in burst]
        a['banner_frames'] = sum(1 for b in banners if b >= BANNER_MIN)
        banner_up = xtreme and banners and a['banner_frames'] >= BANNER_SHARE * len(banners) and             (m0.get('banner') or 0.0) < BANNER_MIN
        if banner_up:
            a['status'] = 'fired'
            a['notes'].append(f'Xtreme banner in {a["banner_frames"]}/{len(banners)} frames')
        elif a['energy_before'] is not None and a['energy_after'] is not None and                 a['energy_before'] - a['energy_after'] >= self.opt.min_drop:
            # the cost can land after the burst (the boost slot hides the HUD while it plays; in game Cyclops's
            # and Beast's left slot read '-' in the burst and 0.72 after)
            a['status'] = 'fired'
            a['notes'].append('energy dropped after the burst')
        elif a['energy_before'] is None or low is None:
            a['status'] = 'no-hud'
        elif a['drop'] >= self.opt.min_drop:
            a['status'] = 'fired'
        elif via == 'wheel' and a.get('wheel_slot') == 'empty':
            a['status'] = 'empty-slot'
        else:
            a['status'] = 'no-energy-change'
        # kept: the HUD stack (pre / lowest / post) and the lowest frame full size, the wheel crop, the rest half
        # size JPEG (--keep-full: full-size PNGs)
        a['hud'] = self.rel(hud_stack([p for p in (pre, low and low['bmp'], post) if p],
                                      self.path(f'{tag}_hud.png')))
        a['min_frame'] = None
        if low and low['bmp']:
            a['min_frame'] = self.rel(save_png(low['bmp'], self.path(f'{tag}_min.png')) if self.opt.keep_full
                                      else save_jpg(low['bmp'], self.path(f'{tag}_min.jpg'), half=False))
            a['min_t'] = low['t']
        a['pre'] = self.rel(self.keep(pre, f'{tag}_pre'))
        a['wheel'] = None
        if wheel:
            a['wheel'] = self.rel(save_png(wheel, self.path(f'{tag}_wheel.png'), None if self.opt.keep_full
                                           else WHEEL_BOX))
            self.finish_frame(wheel)
        a['frames'] = [self.rel(self.keep(f['bmp'], f'{tag}_f{i:02d}')) for i, f in enumerate(burst)]
        a['post'] = self.rel(self.keep(post, f'{tag}_post'))
        e = lambda v: '-' if v is None else f'{v:.2f}'  # noqa: E731
        self.say(f'    {tag}: {a["keys"]} energy {e(a["energy_before"])} -> {e(a["energy_min"])} -> '
                 f'{e(a["energy_after"])} ({a["status"]}'
                 + (f', wheel slot {a["wheel_slot"]}' if 'wheel_slot' in a else '') + ')'
                 + (f'; {len(a["log_problems"])} log problem lines' if a['log_problems'] else ''))
        return a

    def fire_slot(self, h, srec, phase):
        """All tries for one slot (retries, the quick-key fallback); fills srec['attempts'] / srec['status']."""
        self.firing = (srec, phase)
        srec['phase'] = phase
        srec.setdefault('attempts', [])
        wheel = []
        for n in range(1, self.opt.retries + 2):
            a = self.attempt(srec, phase, 'wheel', n)
            srec['attempts'].append(a)
            wheel.append(a)
            if a['status'] in ('fired', 'empty-slot'):
                break
        wheel_fired = any(a['status'] == 'fired' for a in wheel)
        if srec['quick_key'] and (self.opt.quick == 'always' or (self.opt.quick == 'fallback' and not wheel_fired)):
            a = self.attempt(srec, phase, 'quick', 1)
            srec['attempts'].append(a)
            srec['quick_status'] = a['status']
        self.firing = None
        fired = [x for x in srec['attempts'] if x['status'] == 'fired']
        rank = ('fired', 'empty-slot', 'no-energy-change', 'no-hud')
        srec['status'] = min((x['status'] for x in srec['attempts']), key=rank.index)
        srec['fired_via'] = sorted({x['via'] for x in fired})
        return srec

    # ---------------------------------------------------------------- level-up
    def level_up(self, h, rec, before):
        """setAutoSpend(1,1) + XP for h['level_to']; Enter for the first level-up popup; the wheel again."""
        out = {'target_level': h['level_to'], 'xp': h['xp'], 'steps': []}
        filled0 = sum(1 for v in (before or {}).get('slots', {}).values() if v == 'filled')
        self.script('setAutoSpend(1,1)')
        self.sleep(0.3)
        if self.opt.xp_mode == 'auto':
            methods = [self.xp_first] + [m for m in ('set', 'award') if m != self.xp_first] if self.xp_first \
                else ['set', 'award']
        else:
            methods = [self.opt.xp_mode]
        probe = before
        for m in methods:
            stmt = f'setXP("{HERO}",{h["xp"]})' if m == 'set' else f'awardXPToPlayable({h["xp"]})'
            log_from = self.log_size()
            self.say(f'  level-up: {stmt} (level {h["level_to"]}, setAutoSpend(1,1))')
            self.script(stmt)
            self.pause(self.opt.levelup_wait)
            shot = self.rel(self.shot(self.path(f'levelup_{m}.png')))
            self.tap('RETURN')          # the first level-up popup: its leave-as-is option (string 181)
            self.pause(1.5)
            probe = self.wheel_probe(f'wheel_leveled_{m}')
            for _ in range(2):
                if probe['up']:
                    break
                self.say('  no wheel after the level-up: a popup still up? Enter')
                self.tap('RETURN')
                self.pause(1.5)
                probe = self.wheel_probe(f'wheel_leveled_{m}')
            filled = sum(1 for v in probe['slots'].values() if v == 'filled')
            out['steps'].append({'method': m, 'statement': stmt, 'shot': shot, 'wheel': probe,
                                 'filled_before': filled0, 'filled_after': filled, 'log': self.fix_lines(log_from)})
            if filled > filled0:
                self.xp_first = m
                out['worked'] = m
                break
        out['wheel'] = probe
        if not out.get('worked'):
            self.say('  level-up: no new wheel slot filled (the slots are fired anyway)')
        return out

    # ---------------------------------------------------------------- one hero
    def seat(self, h, rec):
        key = h['key']
        self.quiet()
        if self.opt.unlock:
            self.script(f'unlockCharacter("{key}","")')
            self.sleep(0.3)
        stmt = f'seatParty("{key}","","","")\\n\\rloadMapKeepTeam("{self.zone_name}")'
        if len(f'runscript {stmt}') > SCRIPT_MAX:
            self.script(f'seatParty("{key}","","","")')
            self.sleep(0.3)
            stmt = f'loadMapKeepTeam("{self.zone_name}")'
        st = self.step('script', stmt, self.zone_name, None, f'seat {key}')
        rec['load'] = {k: st.get(k) for k in ('reached', 'zone', 'hud')}
        rec['load']['seconds'] = (st.get('load') or {}).get('seconds')
        lines = self.log_lines(st['log_from'])
        seated = [m for m in (SEATED.search(l) for l in lines) if m]
        rec['seated_log'] = seated[-1].group(0) if seated else None
        if not st['reached']:
            return 'load-failed'
        party = self.read_party()
        rec['party'] = party
        if party is None:
            rec['notes'].append('party unread (no getPartyMember lines): going on')
        elif key not in [p for p in party if p]:
            return 'not-seated'
        elif [p for p in party if p] != [key]:
            rec['notes'].append(f'party is {party_text(party)}, not {key} alone')
        if not self.wait_hud():
            rec['notes'].append('HUD not up after the load')
        self.script(f'setInvulnerable("{HERO}","TRUE")')
        if self.opt.teleport:
            self.script(f'copyOriginAndAngles("_HERO1_","{self.opt.teleport}")')
        self.pause(1.0)
        rec['seated_shot'] = self.rel(self.shot(self.path('seated.png')))
        return None

    def run_hero(self, h, rec):
        self.cur = rec
        self.hero_dir = os.path.join(self.shots, f'{h["index"]:02d}_{h["key"]}')
        os.makedirs(self.hero_dir, exist_ok=True)
        pending = [s for s in rec['slots'] if s['plan'] in ('start', 'leveled') and not s.get('status')]
        if not pending:
            return
        rec['phase'] = 'seat'
        rec['runs'] = rec.get('runs', 0) + 1
        why = self.seat(h, rec)
        if why:
            rec['status'] = why
            for s in pending:
                s['status'] = 'not-run'
            self.say(f'    {h["key"]}: {why}')
            return
        rec['phase'] = 'wheel'
        rec['wheel_start'] = self.wheel_probe('wheel_start')
        for s in [s for s in pending if s['plan'] == 'start']:
            rec['phase'] = f'start {s["slot"]}'
            self.fire_slot(h, s, 'start')
        later = [s for s in pending if s['plan'] == 'leveled']
        if later:
            rec['phase'] = 'level-up'
            rec['level'] = self.level_up(h, rec, rec['wheel_start'])
            wheel = rec['level']['wheel'] or {}
            for s in later:
                rec['phase'] = f'leveled {s["slot"]}'
                s['wheel_after_level'] = (wheel.get('slots') or {}).get(s['slot'])
                self.fire_slot(h, s, 'leveled')
        rec['phase'] = 'done'


# ================================================================================================ report
def hero_status(rec):
    if rec.get('status') in ('load-failed', 'not-seated', 'stalled', 'tool-error', 'crash-limit'):
        return rec['status']
    st = [s.get('status') for s in rec['slots'] if s['plan'] in ('start', 'leveled')]
    if any(x == 'crash' for x in st):
        return 'crash'
    if st and all(x == 'fired' for x in st):
        return 'ok'
    return 'partial' if any(x == 'fired' for x in st) else 'none-fired'


def fmt(v):
    return '-' if v is None else f'{v:.2f}'


def write_reports(results, state):
    with open(os.path.join(results, 'powers.json'), 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=1)
    recs = sorted(state['heroes'], key=lambda r: r.get('index') or 0)
    counts, hcounts = {}, {}
    for r in recs:
        hcounts[r.get('status', '?')] = hcounts.get(r.get('status', '?'), 0) + 1
        for s in r['slots']:
            if s['plan'] != 'none':
                k = s.get('status') or 'pending'
                counts[k] = counts.get(k, 0) + 1
    keys = state['keys']
    L = [f'# XML1 power sweep: {os.path.basename(os.path.normpath(state["build"]))}', '',
         f'Build `{state["build"]}`; zone `{state["zone"]["zone"]}`; started {state["started"]}'
         + (f', finished {state["finished"]}' if state.get('finished') else ' (running)') + '.',
         'Keys: Power ' + keys['Power']['key'] + ' held + ' + ', '.join(
             f'{slot} {keys[action]["key"]}' for slot, _, action in SLOTS)
         + f' ({keys["Power"]["source"]}). Level-up: setAutoSpend(1,1) + XP via '
         + (state.get('xp_method') or 'no method filled a slot yet') + '.', '',
         'Slots: ' + ', '.join(f'{k} {v}' for k, v in sorted(counts.items())) + '. Heroes: '
         + ', '.join(f'{k} {v}' for k, v in sorted(hcounts.items())) + '.', '',
         '| # | hero | slot | keys | power (move / talent / name) | req lv | phase | wheel | energy before -> lowest '
         '-> after | drop | status | notes | frames |', '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for r in recs:
        for s in r['slots']:
            if s['plan'] == 'none':
                continue
            atts = s.get('attempts') or []
            best = next((a for a in atts if a['status'] == 'fired'), atts[-1] if atts else None)
            wheel = (best or {}).get('wheel_slot') or s.get('wheel_after_level') or ''
            energy = (f'{fmt(best.get("energy_before"))} -> {fmt(best.get("energy_min"))} -> '
                      f'{fmt(best.get("energy_after"))}' if best else '')
            notes = []
            if s.get('problem'):
                notes.append(s['problem'])
            if len(atts) > 1:
                notes.append('tries: ' + ', '.join(f'{a["via"]} {a["status"]}' for a in atts))
            if s.get('untested_why'):
                notes.append(s['untested_why'])
            if s.get('crash'):
                notes.append(f'CRASH: {s["crash"].get("why")}')
            if best and best.get('log_problems'):
                notes.append(f'{len(best["log_problems"])} log problem lines')
            if best:
                notes += best.get('notes') or []
            links = ''
            if best:
                links = ' '.join(f'[{lbl}]({best[k]})' for k, lbl in (('pre', 'pre'), ('wheel', 'wheel'),
                                                                      ('min_frame', 'low'), ('hud', 'hud'),
                                                                      ('post', 'post')) if best.get(k))
            name = f'{s["move"]} / {s["talent"] or "-"} / {s["descname"] or "-"}'
            L.append('| ' + ' | '.join(md_cell(x) for x in (
                r.get('index'), r['key'], s['slot'], (best or {}).get('keys') or f'{keys["Power"]["key"]}+{s["key"]}',
                name, s.get('req_level'), s.get('phase') or s['plan'], wheel, energy,
                fmt(best.get('drop')) if best else '', s.get('status') or 'pending', '; '.join(notes), links)) + ' |')
    L += ['', '## Heroes', '', '| # | hero | status | party | load s | wheel at start | level-up | wheel after | notes |'
          ' shots |', '|---|---|---|---|---|---|---|---|---|---|']
    for r in recs:
        ws = r.get('wheel_start') or {}
        lv = r.get('level') or {}
        wl = lv.get('wheel') or {}
        wtxt = lambda w: ' '.join(f'{k[0]}:{v}' for k, v in (w.get('slots') or {}).items())  # noqa: E731
        lvl = (f'L{lv.get("target_level")} ({lv.get("xp")} XP) via {lv.get("worked") or "nothing filled"}; '
               + ', '.join(f'{st["method"]} {st["filled_before"]}->{st["filled_after"]}' for st in lv.get('steps', []))
               if lv else '-')
        shots = ' '.join(f'[{lbl}]({p})' for lbl, p in (('seated', r.get('seated_shot')), ('wheel', ws.get('shot')),
                                                        ('leveled', wl.get('shot'))) if p)
        L.append('| ' + ' | '.join(md_cell(x) for x in (
            r.get('index'), r['key'], r.get('status'), party_text(r.get('party')) if 'party' in r else '',
            (r.get('load') or {}).get('seconds'), wtxt(ws), lvl, wtxt(wl), '; '.join(r.get('notes') or []),
            shots)) + ' |')
    if state.get('skipped'):
        L += ['', 'Not tested (herostat entries without team="hero"): '
              + ', '.join(f'{s["name"]} ({s["why"]})' for s in state['skipped']) + '.']
    crashes = [(r, s) for r in recs for s in r['slots'] if s.get('crash')] + \
              [(r, c) for r in recs for c in r.get('crashes', []) if not c.get('slot')]
    if crashes:
        L += ['', '## Crashes', '']
        for r, c in crashes:
            c = c.get('crash', c)
            L.append(f'### {r["key"]} ({c.get("phase") or c.get("label") or ""})')
            L += ['```'] + (c.get('first_exception') or c.get('gamedbg') or [c.get('why', '')]) + ['```']
            if c.get('frames'):
                L.append('frames before the crash: ' + ' '.join(f'[{os.path.basename(p)}]({p})' for p in c['frames']))
            if c.get('fix_log_tail'):
                L += ['xml2-fix.log tail:', '```'] + c['fix_log_tail'] + ['```']
    probs = [(r, s, a) for r in recs for s in r['slots'] for a in s.get('attempts') or [] if a.get('log_problems')]
    if probs:
        L += ['', '## xml2-fix.log errors / warnings', '']
        for r, s, a in probs:
            L.append(f'- **{r["key"]} {s["slot"]} ({a["via"]} try {a["try"]})**')
            L += [f'  - `{l[:220]}`' for l in a['log_problems'][:8]]
    if state.get('launches'):
        L += ['', '## Launches', '']
        for la in state['launches']:
            L.append(f'- {la["n"]} at {la["time"]}: {la["reason"]} (gamedbg: `{la["gamedbg_log"]}`)')
    if state.get('stopped'):
        L += ['', f'Stopped: {state["stopped"]}']
    with open(os.path.join(results, 'powers.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')


# ================================================================================================ main
def new_record(h, opt):
    rec = {k: h[k] for k in ('index', 'name', 'key', 'charactername', 'start_level', 'level_to', 'xp')}
    rec.update(status='running', notes=[], slots=[dict(s) for s in h['slots']])
    for s in rec['slots']:
        if s['plan'] == 'untested':
            s['status'] = 'untested'
            s['untested_why'] = ('--no-level' if opt.no_level else
                                 f'needs level {s["req_level"]}, --level {h["level_to"]}')
    return rec


def sweep(build, results, plan, opt, sweeper=None):
    os.makedirs(os.path.join(results, 'shots'), exist_ok=True)
    state_path = os.path.join(results, 'powers.json')
    state = None
    if opt.resume and os.path.isfile(state_path):
        state = load_json(state_path)
        if state:
            state.pop('finished', None)
            state.pop('stopped', None)
    if not state:
        state = {'build': os.path.abspath(build), 'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'heroes': [],
                 'launches': [], 'ini': plan['ini'], 'keys': plan['keys'], 'zone': plan['zone'],
                 'herostat': plan['herostat'], 'skipped': plan['skipped'],
                 'options': {k: v for k, v in vars(opt).items()},
                 'plan': [{'index': h['index'], 'hero': h['key'], 'level_to': h['level_to'],
                           'slots': {s['slot']: s['plan'] for s in h['slots']}} for h in plan['heroes']]}
    done = {r['key'] for r in state['heroes'] if r.get('status') not in (None, 'running')}
    wk = sweeper or Sweeper(build, results, opt, plan['ini'], plan)
    earlier_launches = list(state.get('launches') or [])
    tool_errors = 0

    def save():
        state['launches'] = earlier_launches + wk.launches
        if wk.xp_first:
            state['xp_method'] = {'set': f'setXP("{HERO}",xp)', 'award': 'awardXPToPlayable(xp)'}[wk.xp_first]
        write_reports(results, state)

    def put(rec):
        state['heroes'] = [r for r in state['heroes'] if r['key'] != rec['key']] + [rec]
        save()

    try:
        for h in plan['heroes']:
            if h['key'] in done:
                continue
            rec = next((r for r in state['heroes'] if r['key'] == h['key']), None) or new_record(h, opt)
            rec['started'] = time.strftime('%H:%M:%S')
            t0 = time.time()
            wk.say(f'--- {h["index"]} {h["key"]} ({h["charactername"]}): '
                   + ', '.join(f'{s["slot"]} {s["move"]} {s["plan"]}' for s in h['slots']))
            crashes = 0
            while True:
                try:
                    wk.ensure_game()
                    wk.run_hero(h, rec)
                    tool_errors = 0
                    break
                except GameGone as ex:
                    crashes += 1
                    info = wk.crash_info(ex)
                    info['phase'] = rec.get('phase')
                    info['frames'] = wk.salvage()
                    if wk.firing:
                        srec, phase = wk.firing
                        srec['status'] = 'crash'
                        srec['crash'] = info
                        srec['phase'] = phase
                        info['slot'] = srec['slot']
                        wk.firing = None
                    rec.setdefault('crashes', []).append(info)
                    wk.say(f'    {h["key"]}: CRASH in {rec.get("phase")} ({ex})')
                    wk.pid = None
                    if crashes > opt.max_crashes:
                        rec['status'] = 'crash-limit'
                        break
                except RuntimeError as ex:
                    rec['status'] = 'stalled'
                    rec['notes'].append(f'{rec.get("phase")}: {ex}')
                    wk.say(f'    {h["key"]}: stalled in {rec.get("phase")} ({ex})')
                    try:
                        wk.restart(f'{h["key"]} stalled')
                    except (GameGone, RuntimeError) as ex2:
                        wk.say(f'restart failed: {ex2}')
                        wk.pid = None
                    break
                except Exception as ex:  # noqa: BLE001 - a bug in this tool: record it, go on, stop after 3
                    rec['status'] = 'tool-error'
                    rec['notes'].append(f'{type(ex).__name__}: {ex}')
                    rec['traceback'] = traceback.format_exc().splitlines()[-12:]
                    wk.say(f'    {h["key"]}: TOOL ERROR in {rec.get("phase")}: {type(ex).__name__}: {ex}')
                    wk.release_all()
                    tool_errors += 1
                    if tool_errors >= 3:
                        put(rec)
                        raise Stop('3 tool errors in a row (a bug in power_sweep.py; see the tracebacks in '
                                   'powers.json)')
                    break
            left = wk.salvage()
            if left:
                rec.setdefault('leftover_frames', []).extend(left)
            for s in rec['slots']:
                if s['plan'] in ('start', 'leveled') and not s.get('status'):
                    s['status'] = 'not-run'
            rec['status'] = hero_status(rec)
            rec['seconds'] = round(time.time() - t0, 1)
            if rec['status'] == 'ok' and not opt.keep_trace:
                rec.pop('trace', None)
            wk.cur = None
            put(rec)
            fired = sum(1 for s in rec['slots'] if s.get('status') == 'fired')
            tried = sum(1 for s in rec['slots'] if s['plan'] in ('start', 'leveled'))
            wk.say(f'    {h["key"]}: {rec["status"]} - {fired}/{tried} slots fired, {rec["seconds"]:.0f} s')
    except Stop as ex:
        state['stopped'] = str(ex)
        print(f'STOP: {ex}', flush=True)
    except KeyboardInterrupt:
        state['stopped'] = 'interrupted'
        wk.release_all()
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
    for r in state['heroes']:
        for s in r['slots']:
            if s['plan'] != 'none':
                counts[s.get('status')] = counts.get(s.get('status'), 0) + 1
    print('done', counts, '->', os.path.join(results, 'powers.md'), flush=True)
    return state


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('build')
    ap.add_argument('results', nargs='?')
    ap.add_argument('--dry-run', action='store_true', help='parse the build and print the plan; never touch the game')
    ap.add_argument('--json', action='store_true', help='with --dry-run: the plan as JSON')
    ap.add_argument('--heroes', help='comma list of herostat names (or character names), in this order')
    ap.add_argument('--zone', default=DEFAULT_ZONE, help=f'test zone (default {DEFAULT_ZONE})')
    ap.add_argument('--level', default='auto', help='level for the slots a hero lacks at its start: auto (the '
                                                    'highest level they need) or a number')
    ap.add_argument('--no-level', action='store_true', help='no level-up: only the slots of the start level')
    ap.add_argument('--xp-mode', choices=('auto', 'set', 'award'), default='auto',
                    help='setXP on the active hero, awardXPToPlayable (the roster), or set then award (default)')
    ap.add_argument('--quick', choices=('fallback', 'always', 'off'), default='fallback',
                    help='also try the quick-power key: when the wheel did not fire (default), always, never')
    ap.add_argument('--retries', type=int, default=1, help='wheel tries after the first one when it did not fire')
    ap.add_argument('--frames', type=int, default=30, help='burst frames after the key (was 14 before 2026-09-29)')
    ap.add_argument('--frame-gap', type=float, default=0.06, help='seconds between burst frames (was 0.04)')
    ap.add_argument('--keep-full', action='store_true', help='keep every burst frame as a full-size PNG')
    ap.add_argument('--min-drop', type=float, default=0.025, help='energy drop (fraction of the bar) = fired')
    ap.add_argument('--restore', type=int, default=10000, help='restoreEnergy amount before each try (0 = off)')
    ap.add_argument('--xtreme-pips', type=int, default=5, help='addXtremePip() calls before an Xtreme try')
    ap.add_argument('--teleport', help='copyOriginAndAngles("_HERO1_", ENTITY) after seating (e.g. a spawner)')
    ap.add_argument('--unlock', action='store_true', help='unlockCharacter the hero before seating it')
    ap.add_argument('--max-crashes', type=int, default=2, help='relaunches per hero before it is given up')
    ap.add_argument('--resume', action='store_true', help='keep <results>/powers.json and skip finished heroes')
    ap.add_argument('--no-launch', action='store_true', help='only attach to a running game')
    ap.add_argument('--no-relaunch', action='store_true', help='stop at the first crash')
    ap.add_argument('--max-launches', type=int, default=12)
    ap.add_argument('--close-at-end', action='store_true', help='close the game at the end if this sweep launched it')
    ap.add_argument('--keep-trace', action='store_true', help='keep the progress lines of ok heroes in the JSON too')
    ap.add_argument('--slow', type=float, default=1.0, help='multiply every timeout and step wait')
    for name, default in (('boot-timeout', 300), ('load-timeout', 240), ('settle-timeout', 90),
                          ('no-hud-settle', 45), ('conv-open', 6), ('conv-timeout', 180), ('party-timeout', 6),
                          ('zone-timeout', 150), ('post', 8), ('hud-timeout', 30), ('levelup-wait', 4)):
        ap.add_argument(f'--{name}', type=float, default=default)
    ap.add_argument('--wheel-open', type=float, default=0.35, help='seconds between Power down and the slot key')
    ap.add_argument('--tap-ms', type=int, default=150, help='how long the slot / quick key is held')
    ap.add_argument('--restore-wait', type=float, default=0.8)
    ap.add_argument('--restore-timeout', type=float, default=4, help='wait this long at most for a full energy bar')
    ap.add_argument('--post-wait', type=float, default=2.5,
                    help='seconds after the burst for the post frame (was 1.2: too early for the boost slots)')
    ap.add_argument('--boot-wait', type=float, default=30, help='seconds after launch before the first Enter')
    ap.add_argument('--poll', type=float, default=1.0)
    ap.add_argument('--conv-gap', type=float, default=1.3)
    ap.add_argument('--quiet', type=float, default=2.0)
    ap.add_argument('--press-every', type=float, default=5.0)
    ap.add_argument('--wrong-grace', type=float, default=30)
    ap.add_argument('--max-presses', type=int, default=12)
    opt = ap.parse_args(argv)
    opt.no_skip_movies = False
    if opt.level != 'auto':
        try:
            opt.level = int(opt.level)
        except ValueError:
            sys.exit('--level: auto or a number')
        if opt.level <= 1:
            opt.no_level = True
    build = os.path.abspath(opt.build)
    if os.path.normcase(build).startswith(REAL_INSTALL):
        sys.exit('refusing the real XML2 install')
    if not os.path.isfile(os.path.join(build, 'XMen2.exe')) or not os.path.isdir(os.path.join(build, 'Data')):
        sys.exit(f'{build}: not a build directory (XMen2.exe, Data)')
    plan = build_plan(build, opt)
    if opt.dry_run:
        if opt.json:
            print(json.dumps({'build': build, **plan}, indent=1))
        else:
            print_plan(build, plan, opt)
        return 0
    if not opt.results:
        sys.exit('results directory missing (or pass --dry-run)')
    ini = plan['ini']
    if ini.get('input_pipe') != '1' or not ini.get('dll'):
        sys.exit(f'{build}: no pipe harness (python tools/harness.py install {opt.build})')
    if ini.get('forced_teams') != '1':
        sys.exit(f'{build}: [Game] ForcedTeams is not 1 - seatParty would seat nobody '
                 f'(python tools/harness.py install {opt.build})')
    if not plan['zone'].get('exists'):
        sys.exit(f'zone {plan["zone"]["zone"]} is not in the build')
    import fixinput
    fixinput.use_build(build)  # the build's own pipe; SystemExit if XML2FIX_PIPE names another game's
    state = sweep(build, os.path.abspath(opt.results), plan, opt)
    return 0 if not state.get('stopped') or state['stopped'] == 'interrupted' else 1


if __name__ == '__main__':
    sys.exit(main())
