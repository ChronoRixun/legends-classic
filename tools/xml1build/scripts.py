"""xml1build.scripts - XML1 scripts, generated popup dialogs and mission files (SPEC.md section 5.2).

run(ctx) installs the scripts research outputs (research/scripts/out, deterministic, never re-generated here):
  * Scripts/**            every rewritten XML1 script (1,536 incl. 128 generated x1/*), CRLF re-normalised.
                          The 22 XML2 common/* collisions are overwritten (reported). --frontend xml2: XML2's
                          front end (menus/intro_normal, main_back_main, main_back_debug) is kept; --frontend
                          xml1 (SPEC 21): XML1's main_back_main is installed and menus/intro_normal is generated
                          (XML1's logos, then mainMenuExit). XML1's dead menus/intro_demo and intro_e3 are left
                          out. x1/menus/postgame (r505, then the main menu; xml2-fix PostgameScript) is always
                          generated.
  * Scripts/menus/new_game.py + new_game_hard.py
                          = body of x1/missions/begin_alison (XMen2.exe startFirstMission runs
                          'runscript menus/new_game[_hard]' at 0x4a7c42/0x4a7c57 after setting up its own
                          magneto/cyclops/wolverine/storm roster). No exe patch. testhooks may override them.
  * Dialogs/x1/p001..p092.{XMLB,engb}
                          popups generated from XML1 createPopupDialog sequences. p091/p092 (Forge,
                          spokewithforge.py) point at scripts that exist nowhere; they are retargeted to
                          targets derived from the XML1 data (see _dialog_retargets).
  * Data/missions/missions.XMLB + x1_act01..09.{XMLB,engb}
                          XML1's 101 missions packed into 9 acts (replaces XML2's mission list).
  * Forced teams (SPEC 19, --forced-teams seat, the default): forced_party_plan(ctx) gives every mission XML1's
    party / skinset; the begin bodies get the xml2-fix seat or skinset block (team menu = else branch), side
    missions push / pop the party, the joins try xml2-fix addHero and joinHero before T7, and x1/missions/end_jug_fb is
    generated for the jug_fb exit dialog. --forced-teams menu emits no xml2-fix call.

Provider functions for zones / validate (pure: read-only, cached per ctx, work without run()):
  rewrite_data_tree(ctx, root, rel) -> int, zone_script_ref(ctx, zone), zone_package_extras(ctx, zone),
  zone_act(ctx, zone), script_exists(ctx, ref).
Extra helpers other modules may use: planned_script_refs(ctx), dialog_exists(ctx, name), dialog_source(ctx, name).

Checks run on what is installed (errors unless the finding is XML1's own defect in unreferenced dead code):
every statement registered exact-case with matching argc / literal types (scripts_lint, XMen2.exe 0x4d8970),
CRLF, no XML1-only / no-op call, <= 2 pending console commands between waits (0x55c426, branch-aware),
runscript code whitespace-free and <= 127 chars (0x55b670 / 0x55c42f), blackbirdMenu tokens < 64 chars
(0x5f2408), popup paths < 64 chars (0x5ebc57), game flag names < 12 chars and <= 96 names (0x4d7130),
mission caps 25 files / 299 objectives / 75 per act, startMovie names that clash with XML2's movies, inline
rewrite values valid, and the per-zone statement estimate against the 620-node pool (0x4d7e6e).
Standalone verification of a build: tools/xml1build/scripts_selftest.py --out <dir>.
"""
from __future__ import annotations

import collections
import os
import re
import threading
import weakref
from pathlib import Path

from . import common as C
from . import conversations as CV
from . import scripts_lint as L
from . import boss_phases as BP
from . import start_fixes as SF
from . import scripts_transform as T

# ----------------------------------------------------------------------------------------------- constants
RESEARCH_OUT = 'scripts/out'                      # under ctx.research
FRONTEND_KEEP_XML2 = ('menus/intro_normal', 'menus/main_back_main', 'menus/main_back_debug')   # --frontend xml2
# SPEC 21 (--frontend xml1): XML1's main_back_main (byte-identical to XML2's) is installed with XML1's backdrop;
# XML2's main_back_debug stays (nothing runs it); intro_normal is generated (FRONTEND_INTRO)
FRONTEND_KEEP_XML2_X1 = ('menus/main_back_debug',)
FRONTEND_DEAD_X1 = ('menus/intro_demo', 'menus/intro_e3')
# SPEC 21 A.4.3: XMen2.exe always runs 'runscript menus/intro_normal' at boot (0x402cd1). XML1's order (xml1_assets
# scripts/menus/intro_normal.py): i102 Activision, i101 Marvel, i103 Raven, i104 Vicarious Visions, i105 Sofdec, then
# mainMenuExit() (not XML1's openmenu("main"): mainmenuexit is what loads menu/main_back, 0x5f27a0). Movie names
# through media.movie_name (XML2 ships i101-i105 itself, so XML1's are installed as xi101...). A missing movie
# signals at once (in game, 2026-09-28), so --no-movies builds keep the same script.
FRONTEND_INTRO = 'menus/intro_normal'
FRONTEND_INTRO_MOVIES = ('i102', 'i101', 'i103', 'i104', 'i105')
# SPEC 21 D.1: after XML2's endgame credits (credits_end, endgame="true") XMen2.exe runs saveloadProcess(2) and then
# loadZone('act5/egypt/egypt6','') (0x5b1df4 / 0x5b1cbf), an XML2 zone whose NPCs XML1 mode dropped. xml2-fix
# [Game] PostgameScript=x1/menus/postgame (tools/harness.py) makes it run this script instead: XML1's order after
# its credits, the r505 "Final Newscast" (default.xbe string beside data/credits.xml), then the main menu. Written
# in both front ends (it is the campaign's ending, not the front end); without the ini key nothing runs it.
POSTGAME_REF = 'x1/menus/postgame'
POSTGAME_MOVIE = 'r505'
NEW_GAME_REFS = ('menus/new_game', 'menus/new_game_hard')
NEW_GAME_BODY = 'x1/missions/begin_alison'        # XML1 New Game = 'beginmission alison' (xbe 0x18d118)
TOUR_PREFIX = 'x1/tour/'                          # owned by testhooks
DIALOG_DIR = 'Dialogs/x1'
MISSION_DIR = 'Data/missions'

# XML2 mission system hard caps (scripts VERIFICATION): 25 listed mission files (0x48908a), 299 objectives
# in total (0x4885c0), 75 objectives loaded for the current act (0x4899e0).
MAX_MISSION_FILES, MAX_OBJECTIVES, MAX_OBJECTIVES_PER_ACT = 25, 299, 75
# XML2 game store: 100 names < 12 chars (0x4d7130); XMen2.exe itself uses 4 (pushes before 0x4a1670).
ENGINE_GAME_FLAGS = ('danv', 'r_d_disc', 'r_imarmor', 'r_t_station')
MAX_GAME_FLAG_NAMES, MAX_FLAG_NAME_LEN = 100 - len(ENGINE_GAME_FLAGS), 11
STATEMENT_POOL = 620                              # script instruction nodes (0x4d7e6e)

# Packed XML1 mission counters narrowed from rewrite_scripts' 8-bit COUNTER_BITS to their real range
# (scripts_transform.narrow_packed; research var_storage.json key -> (bits, evidence)). Both are read in the
# final zones, where the 8-bit code pushed mastermold2 to 907 statements (pool 620, 0x4d7e6e).
NARROW_PACKED = {
    'm:corecount': (3, 'unsigned 0..7: +1 only in mastermold/core_on1..3, -1 in core_off1..3 (each switch alternates '
                       'on / off after actdelay 90), read only by checkcore (>= 3); 3 switches in mastermold1 and 3 in '
                       'mastermold2 and the mission var carries over, so at most 6'),
    'm:stage': (5, 'signed -16..15: literal values -1..8 (var_storage literal_values; setMissionVar("stage", 8) is the '
                   'largest), every variable write is iadd(stage, 1) guarded by the boss health thresholds (stage < 3/4/6, '
                   '<= 4/5: mmpain, mystique_pain, magneto_pain, sk1pain, sk2pain, blobpain; avalanche_pain stops at '
                   '5 because hthresh = 1 - 0.2*stage <= 0; spawnfiredemons ends the pyro fight at stage >= 3)'),
}
BLACKBIRD_MODES = ('menu', 'chooseteam')          # --blackbird: keep blackbirdMenu (default) / loadMapChooseTeam
# forced heroes (review round 2): an XML1 mission with REQUIREDHERO entries or maxheros below a full party starts
# with loadMapChooseTeam (XML2 cannot add/remove a party member from a script)
FORCED_HERO_MAX = 4
# act-on-entry plan: missions that never set the campaign act (22 boss rush / demo / test missions of act 9)
NONCAMPAIGN_MISSION = re.compile(r'^(boss_|demo$)|test')
# conversation speaker tokens default.xbe resolves itself: 0x61bc6 _stricmp(token, "%ALISON%") -> the stats entry
# "Magma" (strings 0x3cc014 / 0x3cc00c). XMen2.exe has no such alias (no '%ALISON%' string; its built-in tokens are
# %PLAYER% %X-TEAM% %NULL% %END% %MORE% %CONTINUE% %BLANK%), so the token is rewritten to the stats name. (default.xbe
# labelled the line with its string 503 "Alison", 0x61c88; the NPC Alison's lines then go to her own speaker entries,
# scripts_transform.NPC_SPEAKER_CONVERSATIONS / SPEAKER_DISPLAY_NAMES, SPEC 18.1.)
SPEAKER_TOKEN_ALIASES = {'%alison%': '%MAGMA%'}
SPEAKER_ATTRS = ('text', 'textb')
# T7 join_hero (research/heroes/roster.md 5; SPEC_heroes.md): XML1 addHero("cyclops") sites -> game flag bit;
# the zone whose script guards the reload; the owning mission whose start clears the bit
JOIN_HERO_SCRIPTS = {'nyc/alison/add_cyclops': 1, 'mansion/dr_mag2/blob/add_cyclops': 2}
JOIN_HERO_ZONE_SCRIPTS = {'nyc/alison/nyc1_1_3': 1, 'x1/zones/mansion/dr_mag2/mag_nyc4': 2}
JOIN_HERO_MISSIONS = {'alison': 1, 'dr_mag2': 2}
# Mission-start unlocks (issue #55, SPEC section "number assigned at merge"; xml1build.unlocks). XML1 unlocks, at
# every beginmission (side missions included), every hero of its cumulative table up to the mission's
# missions.xml charunlock milestone; mission_start_unlocks(ctx) reads both from the player's copy and
# scripts_transform.unlock_at_mission_starts puts the lines in every copy of every begin body (the same lines in each,
# so the later body matching still sees identical bodies); heroes V-H13 checks it. It replaced the hand-placed
# Jubilee / Colossus / Psylocke unlock points of 2026-09-28, which stood in for this table.


def mission_start_unlocks(ctx) -> dict:
    """Pure (cached): {'missions': {mission: (hero, ...)}, 'cumulative': {mission: (hero, ...)}, 'dropped':
    {mission: (non-playable hero, ...)}, 'errors': [str]}, limited to the playable heroes of this build's herostat.
    cumulative = XML1's unlock set of every mission in missions.xml (all rows up to its milestone); missions = the
    lines each begin body writes: the milestone's own group (the rows after the previous milestone). XMen2.exe keeps
    unlocks in the profile and nothing clears them, so every story path, which starts each milestone's missions in
    table order, ends each mission start with XML1's cumulative set; the full cumulative set in every copy pushed the
    act-3 hubs (nyc3_2_1, muir_in3: four begin-body copies each) past the 620-statement pool (0x4d7e6e). Saves from
    earlier builds get the cumulative set from their zone script on load (catchup_unlock_plan). Any problem reading the table or the milestones is an error (the build fails
    in run(); the map is then empty - never a guess)."""
    def build():
        from . import unlocks as U                     # noqa: WPS433
        errors = []
        xbe = Path(ctx.x1_xbox) / 'default.xbe'
        try:
            rows = U.read_xbe_table(xbe)
        except U.UnlockTableError as e:
            errors.append(f'default.xbe: {e}. XML1\'s per-mission hero unlocks cannot be read from this executable, '
                          f'so the build stops instead of guessing them (issue #55)')
            rows = None
        try:
            root = ctx.read_x1_xml('data/missions/missions.xml')
        except KeyError as e:
            errors.append(f'{e}: the per-mission unlock milestones (charunlock) are missing')
            root = None
        milestones, missing = U.mission_milestones(root) if root is not None else ({}, [])
        for m in missing:
            errors.append(f'missions.xml: mission {m} has no charunlock milestone')
        if rows is None or errors:
            return {'missions': {}, 'cumulative': {}, 'dropped': {}, 'errors': errors, 'rows': len(rows or ())}
        playable = set(_port_heroes(ctx))
        cum, drop = U.mission_unlocks(milestones, rows, playable)
        grp, _ = U.mission_unlocks(milestones, rows, playable, fn=U.group)
        return {'missions': grp, 'cumulative': cum, 'dropped': drop, 'errors': errors, 'rows': len(rows)}
    return _cached(ctx, 'mission_start_unlocks', build)


def _mission_start_unlock_map(ctx) -> dict:
    return mission_start_unlocks(ctx)['missions']


def _mission_cumulative_map(ctx) -> dict:
    return mission_start_unlocks(ctx)['cumulative']


def menu_only_unlock_map(ctx) -> dict:
    """{mission: (hero, ...)} (pure, cached): the REQUIRED heroes of each seated forced mission (forced_party_plan
    status 'seat') that are playable and outside the mission's cumulative unlock set. XML1 only seats them (Magma
    before her milestone, the Professor X forms, Cyclops at the two joins); scripts_transform.menu_only_unlocks moves
    their header unlock into the team-menu branch of the seat block."""
    def build():
        cum = _mission_cumulative_map(ctx)
        heroes = _port_heroes(ctx)
        out = {}
        plan = {k.lower(): v for k, v in _mission_plan(ctx).items()}
        for m, row in forced_party_plan(ctx).items():
            if row.get('status') != 'seat':
                continue
            req = [h.lower() for h in (plan.get(m) or {}).get('required') or [] if h]
            only = tuple(dict.fromkeys(h for h in req if h in heroes and h not in cum.get(m, ())))
            if only:
                out[m] = only
        return out
    return _cached(ctx, 'menu_only_unlocks', build)


# Zones whose catch-up unlocks (issue #55) would push the zone's script set past XMen2.exe's 620-node statement pool
# (0x4d7e6e): zone -> why. A save there keeps the unlocks it had; the mission starts before it apply the table.
CATCHUP_SKIP_ZONES = {'mastermold/mastermold2': '613 of 620 statements already (NARROW_PACKED)',
                      'nyc/riots/nyc3_2_1': '610 of 620 statements with its four act-3 begin bodies (measured '
                                            '2026-10-04)'}


def _x1_world_mission(ctx, zone):
    """the XML1 world entity's mission attribute (lowercase) or ''."""
    def build():
        for ext in ('.eng', '.xml'):
            rel = f'maps/{zone}{ext}'
            if ctx.x1_path(rel) is None:
                continue
            try:
                root = ctx.read_x1_xml(rel)
            except Exception:          # noqa: BLE001 - a broken zone file is the zones module's error
                return ''
            w = C.find_world(root) if root is not None else None
            return ((w.get('mission') if w is not None else '') or '').strip().lower()
        return ''
    return _cached(ctx, ('world_mission', zone), build)


def catchup_unlock_plan(ctx) -> dict:
    """Pure (cached): {'scripts': {zone script ref: (hero, ...)}, 'zones': {zone: (mission, ref)}, 'skipped':
    {zone: why}}. Every converted XML1 zone whose world entity names a mission gets that mission's cumulative unlock
    set in its zone script (scripts_transform.catchup_unlocks), so a save made inside the mission by an earlier build
    catches up on load; a zone script shared by zones of several missions gets the heroes common to all of them (it
    never unlocks beyond any of its zones' milestones)."""
    def build():
        cum = _mission_cumulative_map(ctx)
        per_ref, zones, skipped = {}, {}, {}
        for z in ctx.x1_zones():
            if z in C.MENU_ZONES or not _x1_zone_convertible(ctx, z):
                continue
            m = _x1_world_mission(ctx, z)
            if not m or m not in cum:
                continue
            ref = zone_script_ref(ctx, z)
            if ref is None:
                skipped[z] = f'mission {m}: no zone script'
                continue
            if z in CATCHUP_SKIP_ZONES:
                skipped[z] = CATCHUP_SKIP_ZONES[z]
                per_ref[ref] = None
                continue
            zones[z] = (m, ref)
            if ref in per_ref and per_ref[ref] is None:
                continue
            hs = list(cum[m])
            per_ref[ref] = hs if ref not in per_ref else [h for h in per_ref[ref] if h in hs]
        return {'scripts': {r: tuple(hs) for r, hs in per_ref.items() if hs}, 'zones': zones, 'skipped': skipped}
    return _cached(ctx, 'catchup_unlocks', build)

# Forced teams (SPEC 19, research/heroes/FORCED_TEAMS_DESIGN.md). XML1's team builder (xbe 0x18d6d0, run by
# beginmission unless keepheroes) seats REQUIRED, then RECOMMENDED, clears RESTRICTED and caps at maxheros.
FORCED_PARTY_SLOTS = 4
# heroes XML1 lists as REQUIRED but whose content spawns them as an NPC who joins later (addHero at nyc1_1_3 /
# mag_nyc4, T7): they are not seated at the mission start (design 1.4, "content contradiction")
JOIN_LATER = {'alison': ('cyclops',), 'dr_mag2': ('cyclops',)}
# side missions (XML1 beginSideMission / endSideMission) -> the mission whose zone starts them, whose skinset the
# return restores (research rewrite_scripts SIDE_CALLS / SIDE_PARENT, evaluated in the design 3.4)
SIDE_MISSIONS = {'jug_fb': 'mansion2', 'sent_fb': 'mansion2', 'dr_mag1': 'mansion2', 'wx_fb_start': 'mansion3',
                 'muir2_reboot': 'muir2', 'astral_sk': 'astral3', 'nyc_rooftops': 'riots'}
# XML1 endSideMission in DATA (not a script): the research's inline rewrite value -> side mission. The only one is
# the jug_fb flashback's exit, XML1 dialogs/jugdead.eng option "Return to Beast" (script="endSideMission('true')";
# the research resolved it from the jugrnt zone to setCurrentAct(1) + loadZone(subbasement2)). A dialog option runs
# one console token ('runscript <code>'), which cannot hold the if/else block, so seat builds point the option at a
# generated script x1/missions/end_<side> (SIDE_END_REF).
INLINE_SIDE_ENDS = {"endSideMission('true')": 'jug_fb'}
SIDE_END_REF = 'x1/missions/end_{}'
SIDE_BEGIN_REF = 'x1/missions/begin_{}'
CRLF = '\r\n'

# research-confirmed droppable lines: XML1's own defects in unreferenced developer scripts (scripts
# VERIFICATION: "14 remain, all pre-existing XML1 defects in dead developer scripts"; none is referenced by a
# zone bundle, mission file or other script). Their problem lines are reported as notes, not errors.
DEAD_DEV_SCRIPTS = {
    'missions/mansion_start': "unregistered 'begin' (XML1 defect)",
    'missions/muirisland_start': "1-arg startMovie + unregistered 'depart' (XML1 defect)",
    'missions/nuke_start': "1-arg startMovie + unregistered 'depart' (XML1 defect)",
    'missions/sewers_intro': "1-arg startMovie + unregistered 'begin' (XML1 defect)",
    'missions/sewers_start': "1-arg startMovie x2 + unregistered 'depart' (XML1 defect)",
    'missions/testcollect_start': "1-arg startMovie + unregistered 'depart' (XML1 defect)",
    'missions/wx_fb_start': "unregistered 'depart' (XML1 defect)",
    'missions/sentinels_attack_mansion': 'literal assignment (unreferenced XML1 test script)',
}

# attribute names that hold a script reference or inline script (SPEC 5.2 rule: actscript, deathscript,
# chosenscriptfile, scriptfile, script, zonescript and any name ending in 'script' / 'scriptfile')
SCRIPT_REF_ATTRS = {'actscript', 'deathscript', 'chosenscriptfile', 'scriptfile', 'script', 'zonescript'}
NOT_SCRIPT_ATTRS = {'launchedfromscript'}         # boolean flag (XML1 data: launchedFromScript="true")
CONSOLE_ATTRS = {'script', 'scriptok', 'scriptcancel'}   # run as 'runscript <code>' in dialogs/ and ui/
BOOL_VALUES = {'true', 'false'}

# ----------------------------------------------------------------------------------------------- caches
_CACHES: 'weakref.WeakKeyDictionary' = weakref.WeakKeyDictionary()
_LOCK = threading.RLock()


def _cache(ctx) -> dict:
    with _LOCK:
        c = _CACHES.get(ctx)
        if c is None:
            c = _CACHES[ctx] = {}
        return c


def _cached(ctx, key, fn):
    """per-ctx memo; fn() runs outside the lock (pure, so a rare double computation is harmless)."""
    c = _cache(ctx)
    with _LOCK:
        if key in c:
            return c[key]
    val = fn()
    with _LOCK:
        return c.setdefault(key, val)


def _once(ctx, bucket, key) -> bool:
    """True the first time (bucket, key) is seen for this ctx (dedupe of provider warnings/notes)."""
    c = _cache(ctx)
    with _LOCK:
        s = c.setdefault(('once', bucket), set())
        if key in s:
            return False
        s.add(key)
        return True


# ----------------------------------------------------------------------------------------------- research data
def _out_dir(ctx) -> Path:
    return ctx.research_path(RESEARCH_OUT)


def _rjson(ctx, name):
    return ctx.research_json(f'{RESEARCH_OUT}/{name}')


def _inline_map(ctx) -> dict:
    return _rjson(ctx, 'inline_rewrites.json')


def _zone_acts(ctx) -> dict:
    return _rjson(ctx, 'zone_acts.json')


def _zone_extra(ctx) -> dict:
    return _rjson(ctx, 'zone_extra_files.json')


def _xml1_api(ctx) -> dict:
    """default.xbe's registered script functions (research/scripts/xml1_api.json), for telling XML1's own
    defects apart from conversion damage."""
    try:
        return ctx.research_json('scripts/xml1_api.json')
    except FileNotFoundError:
        return {}


def _research_scripts(ctx) -> dict:
    """script ref -> Path of every research/scripts/out/scripts/**.py."""
    def build():
        root = _out_dir(ctx) / 'scripts'
        refs = {}
        for dirpath, _, files in os.walk(root):
            for f in files:
                if f.lower().endswith('.py'):
                    p = Path(dirpath) / f
                    refs[C.script_ref(p.relative_to(root).as_posix())] = p
        return refs
    return _cached(ctx, 'research_scripts', build)


def frontend_keep_xml2(ctx) -> tuple:
    """research front-end scripts NOT installed because XML2's base file is kept: all three with --frontend xml2,
    only main_back_debug with xml1 (SPEC 21)."""
    return FRONTEND_KEEP_XML2 if C.frontend_mode(ctx) == 'xml2' else FRONTEND_KEEP_XML2_X1


def frontend_scripts_replacing_base(ctx) -> tuple:
    """XML2 base scripts the XML1 front end replaces on purpose (--frontend xml1): the generated intro and XML1's
    main_back_main (byte-identical to XML2's). Nothing with --frontend xml2."""
    return (FRONTEND_INTRO, 'menus/main_back_main') if C.frontend_mode(ctx) == 'xml1' else ()


def frontend_scripts(ctx) -> dict:
    """Scripts this module generates for the front end / the campaign's end (SPEC 21), pure:
    {ref: {'lines': [...], 'why': str}}: menus/intro_normal (--frontend xml1 only) and x1/menus/postgame (always)."""
    def build():
        from . import media as M
        out = {}
        if C.frontend_mode(ctx) == 'xml1':
            # plain comment text (no quotes / brackets), like the New Game hook's header
            lines = ['# xml1-port intro - SPEC 21 A.4.3 - XMen2.exe runs menus/intro_normal at boot, 0x402cd1',
                     '# XML1 logo order - Activision Marvel Raven Vicarious-Visions Sofdec - then the main menu']
            for i, m in enumerate(FRONTEND_INTRO_MOVIES, 1):
                name = M.movie_name(ctx, m)
                lines += [f'startMovie("{name}", "afterMovie{i}")', f'waitsignal("afterMovie{i}")']
            lines.append('mainMenuExit()')
            out[FRONTEND_INTRO] = {'lines': lines, 'why': "XML1's intro logos (--frontend xml1)"}
        name = M.movie_name(ctx, POSTGAME_MOVIE)
        out[POSTGAME_REF] = {'lines': [
            '# xml1-port end of campaign - SPEC 21 D.1 - the xml2-fix Game PostgameScript key runs this after the',
            '# endgame credits instead of the XML2 load of act5/egypt/egypt6 - XML1 played r505 then the main menu',
            f'startMovie("{name}", "postgame")', 'waitsignal("postgame")', 'mainMenuExit()'],
            'why': 'end of campaign (xml2-fix PostgameScript)'}
        return out
    return _cached(ctx, 'frontend_scripts', build)


def _installable_refs(ctx) -> dict:
    """research scripts this module installs (front end and hook/tour paths excluded)."""
    def build():
        skip = set(frontend_keep_xml2(ctx)) | set(FRONTEND_DEAD_X1) | set(NEW_GAME_REFS) | set(frontend_scripts(ctx))
        return {r: p for r, p in _research_scripts(ctx).items() if r not in skip and not r.startswith(TOUR_PREFIX)}
    return _cached(ctx, 'installable', build)


def _narrow_specs(ctx):
    """scripts_transform.NarrowSpec for every NARROW_PACKED var (layout from research var_storage.json)."""
    def build():
        try:
            vs = _rjson(ctx, 'var_storage.json')
        except FileNotFoundError:
            return []
        out = []
        for key, (bits, _why) in NARROW_PACKED.items():
            v = vs.get(key)
            if not v or v.get('kind') != 'pack' or bits >= int(v['nbits']):
                continue
            out.append(T.NarrowSpec(key, v['gamevar'], int(v['first_bit']), int(v['nbits']), bits, bool(v['signed'])))
        return out
    return _cached(ctx, 'narrow_specs', build)


def blackbird_mode(ctx) -> str:
    m = (ctx.opt('blackbird') or os.environ.get('XML1BUILD_BLACKBIRD') or 'menu').lower()
    return m if m in BLACKBIRD_MODES else 'menu'


def _raw_lines(ctx, ref):
    """CRLF-split lines of a research script, or of a zone-entry script this module generates (act plan), or
    None."""
    gen = frontend_scripts(ctx).get(ref)                   # SPEC 21: generated front-end / postgame scripts win
    if gen is not None:
        return list(gen['lines'])
    p = _research_scripts(ctx).get(ref)
    if p is not None:
        return C.to_crlf(p.read_bytes().decode('latin-1')).split('\r\n')
    gen = _generated_zone_scripts(ctx).get(ref) or _forced_generated_scripts(ctx).get(ref)
    return list(gen['lines']) if gen is not None else None


def _base_text(ctx, ref):
    """(CRLF text, info): the research output (or generated zone-entry script) with the text post-passes that do
    not depend on other scripts: packed-counter narrowing, the --blackbird chooseteam fallback, zone-literal
    normalisation and the XML1 mission-anim enum rename. Pure and cached."""
    def build():
        lines = _raw_lines(ctx, ref)
        if lines is None:
            return None, {}
        info = {}
        specs = _narrow_specs(ctx)
        if specs:
            lines, ch, probs = T.narrow_packed(lines, specs)
            info['narrow'] = ch
            info['narrow_problems'] = probs
        if blackbird_mode(ctx) == 'chooseteam':
            lines, zs = T.blackbird_to_choose_team(lines)
            info['blackbird'] = zs
        # XML1's mission-start unlocks (issue #55): every copy of a begin body gets the same lines, so the body
        # matching of the later passes (choose_team_in_bodies, forced_party_in_bodies) still sees identical bodies
        lines, ul = T.unlock_at_mission_starts(lines, _mission_start_unlock_map(ctx))
        if ul:
            info['mission_unlocks'] = ul
        text, zl = T.normalise_zone_literals('\r\n'.join(lines))
        info['zone_literals'] = zl
        text, ea = T.rename_mission_anims(text)
        info['mission_anims'] = ea
        if C.frontend_mode(ctx) == 'xml1' and 'imageviewer' in text.lower():
            # SPEC 21 C.4.2 (no installed XML1 script calls imageViewer today; the zone data does)
            text, iv = T.rewrite_image_viewer(text, lambda p: C.map_review_texture(ctx, p))
            info['image_viewer'] = iv
        # npc-loop fix: a LOOP_WAKE animation on a non-combatant NPC never ends in XMen2.exe (see
        # scripts_transform.bound_unwakeable_loops); bounded when every spawner running this script is one
        if unwakeable_owner(ctx, ref):
            stmts, bl, sk = T.bound_unwakeable_loops(text.split('\r\n'))
            if bl or sk:
                text = '\r\n'.join(stmts)
                info['bounded_loops'] = bl
                info['bounded_loops_skipped'] = sk
        text = BP.rewrite_script(ref, text)
        return text, info
    return _cached(ctx, ('base_text', ref), build)


# ------------------------------------------------------------------- unwakeable LOOP_WAKE owners (npc-loop fix)
# XMen2.exe 0x45fbd0: a team string other than hero / enemy / altenemy is team none (0x1c), as is a missing team
# (stats default at 0x4bce9b). Its combat AI - the only code that ends a LOOP_WAKE - never runs for team none or
# for a willflee NPC (attack gate 0x514080: 0x41a220 != 0x1c and cmp byte [ai+0x46d],1), and the engine has no
# flee behaviour (AI fleedistance +0x470 is never read). Such an NPC's LOOP_WAKE spawn animation loops forever.
NONCOMBAT_TEAMS = frozenset({'', 'none', 'neutral'})
_ENTITY_RE = re.compile(r'<entity\b[^>]*>', re.I)
_ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


def _x1_stats_teams(ctx) -> dict:
    """lower stats name -> lower team ('' when the XML1 entry has none) from xml1 data/npcstat.eng + herostat.eng."""
    def build():
        teams = {}
        for f in ('data/npcstat.eng', 'data/herostat.eng'):
            try:
                root = ctx.read_x1_xml(f)
            except KeyError:
                root = None
            if root is None:
                continue
            for st in root.iter('stats'):
                teams[(st.get('name') or '').lower()] = (st.get('team') or '').strip().lower()
        return teams
    return _cached(ctx, 'x1_stats_teams', build)


def spawner_unwakeable(ctx, attrs) -> bool:
    """attrs: the (lowercase) attributes of an XML1 monsterspawnerent. True when XMen2.exe can never wake a
    LOOP_WAKE loop on the NPC it spawns: effective team none (monster_team, else the XML1 stats team, else none)
    and no act script of its own (an actscript such as nyc/riots/mutant_rescue ends the loop itself with
    loopCombatNode(..., "stop") when the player uses the NPC, XML1's intended end for those loops)."""
    if (attrs.get('classname') or '').strip().lower() != 'monsterspawnerent':
        return False
    if (attrs.get('monster_actscript') or '').strip():
        return False
    team = (attrs.get('monster_team') or '').strip().lower()
    if not team:
        team = _x1_stats_teams(ctx).get((attrs.get('character') or '').strip().lower(), '')
    return team in NONCOMBAT_TEAMS


def _spawn_script_owners(ctx) -> dict:
    """script ref -> [(zone, character, unwakeable)] for every XML1 monsterspawnerent (English zone files) whose
    monster_spawnscript names a script file. Inline spawn code is decided in rewrite_data_tree instead, where the
    spawner element is at hand."""
    def build():
        owners = collections.defaultdict(list)
        rels = set(ctx.x1_rels('maps/'))
        for rel in sorted(rels):
            # the zone XML: the English .eng, else the language-neutral .xml (e.g. nyc/riots/nyc3_2_1.xml)
            if not (rel.endswith('.eng') or (rel.endswith('.xml') and rel[:-4] + '.eng' not in rels)):
                continue
            text = ctx.x1_path(rel).read_bytes().decode('latin-1')
            for m in _ENTITY_RE.finditer(text):
                attrs = {k.lower(): v for k, v in _ATTR_RE.findall(m.group(0))}
                ss = (attrs.get('monster_spawnscript') or '').strip()
                if not ss or '(' in ss or (attrs.get('classname') or '').lower() != 'monsterspawnerent':
                    continue
                owners[C.script_ref(_clean_ref(ss))].append(
                    (rel[len('maps/'):-len('.eng')], (attrs.get('character') or '').lower(),
                     spawner_unwakeable(ctx, attrs)))
        return dict(owners)
    return _cached(ctx, 'spawn_script_owners', build)


def unwakeable_owner(ctx, ref) -> bool:
    """True when script `ref` is the spawn script of at least one XML1 spawner and of no spawner whose NPC the
    XMen2.exe AI could wake (see spawner_unwakeable)."""
    owners = _spawn_script_owners(ctx).get(C.script_ref(ref or ''))
    return bool(owners) and all(u for _, _, u in owners)


def owners_with_loop_wake(ctx):
    """[(script ref, [(zone, character, unwakeable)])] of the XML1 spawn scripts (files) that play a LOOP_WAKE
    animation, whatever runs them."""
    scripts = _research_scripts(ctx)
    out = []
    for ref, owners in sorted(_spawn_script_owners(ctx).items()):
        p = scripts.get(ref)
        if p is not None and re.search(r'(?i)loop_wake', p.read_bytes().decode('latin-1')):
            out.append((ref, owners))
    return out


def _script_text(ctx, ref, mode=None):
    """(CRLF text, info) of script `ref` as this module installs it: _base_text plus the passes that need the
    whole script set: forced-hero mission starts load with loadMapChooseTeam (T.choose_team_in_bodies), in a
    --forced-teams seat build the forced-team blocks (SPEC 19: seat / skinset blocks in every begin body, side-
    mission push / pop, the addHero / joinHero branches of the joins) and the act-on-entry injection
    (act_on_entry_plan).
    mode: 'seat' / 'menu' (default: the build's --forced-teams; the New Game hook uses 'menu'). info: {'narrow':
    Counter, 'narrow_problems': [...], 'zone_literals': [(old, new)], 'blackbird': [zone], 'mission_anims':
    [(old, new)], 'choose_team': [(mission, line)], 'forced_party': [(mission, kind, zone)], 'side_push': [side],
    'side_end': [(side, zone, kind)], 'act_injected': act|None}. Pure and cached."""
    mode = mode or C.forced_teams_mode(ctx)

    def build():
        text, info = _base_text(ctx, ref)
        if text is None:
            return None, {}
        info = dict(info)
        lines = text.split('\r\n')
        bodies = _forced_hero_bodies(ctx)
        if bodies:
            lines, ch = T.choose_team_in_bodies(lines, bodies)
            info['choose_team'] = ch
        if mode == 'seat':
            # SPEC 19 (design 3.2-3.5): every begin body (and its inlined copies) gets the seat block (forced
            # missions) or the skinset block (the others); side missions push at their begin site and pop at
            # their end site. The team-menu load stays as the else branch (no DLL / ForcedTeams=0).
            lines, fp = T.forced_party_in_bodies(lines, _mission_bodies_final(ctx), forced_party_plan(ctx))
            info['forced_party'] = fp
            # issue #55: XML1 only seats these REQUIRED heroes; the team-menu branch still unlocks them
            lines, mo = T.menu_only_unlocks(lines, menu_only_unlock_map(ctx))
            if mo:
                info['menu_only_unlocks'] = mo
            sides = _side_plan(ctx)
            lines, pushed = T.side_push_at_markers(lines, {s for s, r in sides.items() if r['push']})
            side = _inline_side_begins(ctx).get(ref)
            if side is not None:
                lines, ins = T.side_push_before_marker(lines, side)
                if ins:
                    pushed.append(side)
            info['side_push'] = pushed
            lines, ends, probs = T.side_end_at_markers(lines, {s: r['end'] for s, r in sides.items()
                                                               if r['end'] != 'keep'})
            info['side_end'] = ends
            info['side_end_problems'] = probs
        act = act_on_entry_plan(ctx)['inject'].get(ref)
        if act is not None:
            lines = T.inject_act(lines, act)
            info['act_injected'] = act
        # issue #55: saves made inside a mission by an earlier build get its unlocks when they are loaded
        cu = catchup_unlock_plan(ctx)['scripts'].get(ref)
        if cu:
            lines, ch = T.catchup_unlocks(lines, cu)
            if ch:
                info['catchup_unlocks'] = ch
        # T7 join_hero (research/heroes/roster.md; SPEC_heroes.md): the two addHero(cyclops) scripts, their zone
        # scripts' guards and the owning missions' start bodies (every inlined copy carries the marker); seat builds
        # try xml2-fix addHero, then joinHero first (SPEC 19.7, design 3.6) and keep T7 as the fallback. The join
        # script's popup comes first, with a wait the player's closing it ends (never pending across the reload or
        # the team menu); the zone guard removes the double again once the spawner has spawned it
        if ref in JOIN_HERO_SCRIPTS:
            lines, heroes, popups = T.join_hero(lines, JOIN_HERO_SCRIPTS[ref], add_hero=(mode == 'seat'))
            info['join_hero'] = heroes
            info['join_popups'] = popups
        if ref in JOIN_HERO_ZONE_SCRIPTS:
            lines, ins = T.join_hero_zone_guard(lines, JOIN_HERO_ZONE_SCRIPTS[ref])
            info['join_hero_guard'] = ins
        lines, reset = T.join_hero_mission_reset(lines, JOIN_HERO_MISSIONS)
        if reset:
            info['join_hero_reset'] = reset
        # the team lock (xml2-fix teamlock; research/online/online_forced_parties.md): every mission start of a seat
        # build says whether its party is fixed, and a side mission's return restores its caller's; keyed on the
        # BUILD's mode, so the New Game hook (a 'menu' text of begin_alison) gets alison's value too
        if C.forced_teams_mode(ctx) == 'seat':
            locks = team_lock_plan(ctx)
            lines, lk = T.team_lock_at_markers(lines, locks['missions'])
            lines, lks = T.team_lock_at_side_ends(lines, locks['sides'])
            if lk:
                info['team_lock'] = lk
            if lks:
                info['team_lock_return'] = lks
        # SPEC 18, the other same-name NPCs: this script's entity references follow the renamed NPCs of its zone
        zone = T.NPC_DOUBLE_SCRIPTS.get(ref)
        if zone is not None:
            lines, n = T.rename_npc_refs(lines, set(T.NPC_DOUBLE_SPAWNERS[zone].values()))
            info['npc_double_refs'] = n
        if lines and lines[-1] != '' and (ref in _generated_zone_scripts(ctx) or ref in _forced_generated_scripts(ctx)
                                          or ref in frontend_scripts(ctx)):
            lines.append('')                                   # final CRLF, like every research script
        from .fire_wall_scripts import rewrite as rewrite_fire_wall
        lines = rewrite_fire_wall(ref, lines)
        return '\r\n'.join(lines), info
    return _cached(ctx, ('text', ref, mode), build)


def script_text(ctx, ref):
    """the text Scripts/<ref>.py gets from this module (None if it installs no such script)."""
    return _script_text(ctx, ref)[0]


def _base_script_refs(ctx) -> set:
    return _cached(ctx, 'base_scripts', lambda: {C.script_ref(a) for a in ctx.base_index.under('scripts/')
                                                  if a.lower().endswith('.py')})


def planned_script_refs(ctx) -> set:
    """every script ref <out> will contain after this module: installed XML1 scripts, the generated zone-entry
    scripts (act plan), the New Game hook and every XML2 base script (the base install is copied into <out>)."""
    return _cached(ctx, 'planned', lambda: set(_installable_refs(ctx)) | set(_generated_zone_scripts(ctx)) |
                   set(_forced_generated_scripts(ctx)) | _base_script_refs(ctx) | set(NEW_GAME_REFS) |
                   set(frontend_scripts(ctx)))


def _exists_base(ctx, ref) -> bool:
    """script_exists without the generated zone-entry scripts (used while the act plan is being computed)."""
    if not ref:
        return False
    r = C.script_ref(_clean_ref(ref))
    if not r or '(' in r:
        return False
    if r in _installable_refs(ctx) or r in _base_script_refs(ctx) or r in NEW_GAME_REFS:
        return True
    return ctx.out_exists(C.script_rel(r)) and not r.startswith('x1/zones/')


def _research_dialogs(ctx) -> dict:
    """dialog name ('p001') -> {'xmlb': Path, 'engb': Path|None} from research/scripts/out/dialogs/x1."""
    def build():
        d = _out_dir(ctx) / 'dialogs' / 'x1'
        out = {}
        if d.is_dir():
            for p in sorted(d.iterdir()):
                stem, ext = p.stem.lower(), p.suffix
                if ext == '.XMLB':
                    out.setdefault(stem, {'xmlb': None, 'engb': None})['xmlb'] = p
                elif ext == '.engb':
                    out.setdefault(stem, {'xmlb': None, 'engb': None})['engb'] = p
        return {k: v for k, v in out.items() if v['xmlb'] is not None}
    return _cached(ctx, 'dialogs', build)


def _dialog_key(name) -> str:
    """createPopupDialogXml / package form -> path under Dialogs/ without extension. XMen2.exe prefixes
    'dialogs/' only when it is absent (0x5ebc57 strnicmp)."""
    n = C.norm(name)
    n = n[len('dialogs/'):] if n.startswith('dialogs/') else n
    return re.sub(r'\.(xmlb|engb|eng|xml)$', '', n)


def dialog_source(ctx, name):
    """where Dialogs/<name> comes from: 'x1gen' (generated, installed by this module), 'out' / 'base' (in
    <out> / the XML2 install), 'xml1' (a non-empty XML1 dialogs/<name>.eng|.xml that zones imports when a zone
    bundle lists it), or None (exists nowhere)."""
    n = _dialog_key(name)
    if n.startswith('x1/') and n[3:] in _research_dialogs(ctx):
        return 'x1gen'
    if ctx.out_exists(f'Dialogs/{n}.XMLB'):
        return 'out'
    if ctx.base_exists(f'Dialogs/{n}.XMLB'):
        return 'base'
    for ext in ('.eng', '.xml'):
        if ctx.x1_path(f'dialogs/{n}{ext}') is not None and not ctx.x1_is_empty(f'dialogs/{n}{ext}'):
            return 'xml1'
    return None


def dialog_exists(ctx, name) -> bool:
    """'x1/p001' | 'dialogs/x1/p001' | 'tut1' -> True if the dialog is (or will be) in <out>."""
    return dialog_source(ctx, name) is not None


def _bundled_dialogs(ctx) -> set:
    """Dialogs/ keys that some XML1 zone bundle lists (so zones imports them)."""
    def build():
        out = set()
        for b, files in ctx.manifest.items():
            if b.startswith('packages/generated/maps/'):
                for f, _ in files:
                    f = C.norm(f)
                    if f.startswith('dialogs/') and f.endswith(('.eng', '.xml')):
                        out.add(_dialog_key(f))
        return out
    return _cached(ctx, 'bundled_dialogs', build)


# ----------------------------------------------------------------------------------------------- providers
def _clean_ref(ref) -> str:
    """script reference as the engine resolves it ('scripts/' + name + '.py'): '/' separators, lower
    case, no '.py', no surrounding whitespace."""
    r = str(ref).strip().replace('\\', '/')
    if r.lower().endswith('.py'):
        r = r[:-3]
    return r.lower()


def script_exists(ctx, ref) -> bool:
    """True if Scripts/<ref>.py is installed / planned by this module, is an XML2 base script (copied into
    <out>), or exists in <out> (e.g. testhooks tour scripts). Accepts refs in any case, with '\\', '.py' or a
    leading 'scripts/'."""
    if not ref:
        return False
    r = C.script_ref(_clean_ref(ref))
    if not r or '(' in r:
        return False
    if r in planned_script_refs(ctx) or r in (ctx.shared.get('scripts_installed') or ()):
        return True
    return ctx.out_exists(C.script_rel(r))


def _zone_id(zone) -> str:
    z = C.norm(zone)
    if z.startswith('maps/'):
        z = z[len('maps/'):]
    return re.sub(r'\.(xmlb|engb|eng|xml|igb|chrb|navb|boyb|pkgb)$', '', z)


def _x1_world_zonescript(ctx, zone):
    """the XML1 world entity's zonescript attribute (raw) or None."""
    def build():
        for ext in ('.eng', '.xml'):
            rel = f'maps/{zone}{ext}'
            if ctx.x1_path(rel) is None:
                continue
            try:
                root = ctx.read_x1_xml(rel)
            except Exception:          # noqa: BLE001 - a broken zone file is the zones module's error
                return None
            if root is None:
                return None
            w = C.find_world(root)
            return w.get('zonescript') if w is not None else None
        return None
    return _cached(ctx, ('world_zs', zone), build)


def _zone_script_choice(ctx, zone):
    """(ref or None, how) - see zone_script_ref."""
    z = _zone_id(zone)
    plan = act_on_entry_plan(ctx)
    gen = plan['zone_script'].get(z)
    if gen is not None:
        return gen, plan['zones'][z]['how']
    return _zone_script_choice_base(ctx, z)


def _zone_script_choice_base(ctx, zone):
    """(ref or None, how): the zone script choice without the generated zone-entry scripts of the act plan."""
    z = _zone_id(zone)

    def build():
        info = _zone_acts(ctx).get(z) or {}
        zs = info.get('zonescript')
        if zs and _exists_base(ctx, zs):
            return C.script_ref(_clean_ref(zs)), 'zone_acts'
        gen = f'x1/zones/{z}'
        if gen in _installable_refs(ctx):
            return gen, 'x1_zones'
        raw = _x1_world_zonescript(ctx, z)
        if raw and '(' not in raw and _exists_base(ctx, raw):
            return C.script_ref(_clean_ref(raw)), 'world_attr'
        # XML1 convention (research zone_acts.json, tools/convert_zone.py - proven in-game for nyc1_1_1): a
        # zone without a usable zonescript runs scripts/<zone>.py. Only used when the XML1 zone bundle
        # packages that script (Raven's packager lists the zone script with the zone), which covers the 13
        # mocap briefings, the blackbird/status-meeting zones (all .xml zones not in zone_acts.json) and
        # hive/h_int/hive2_2_1 (world zonescript 'hive/h_int/2_2_1' exists nowhere).
        if z in _installable_refs(ctx):
            try:
                bundle = ctx.zone_bundle(z)
            except KeyError:
                bundle = []
            if any(C.norm(f) == f'scripts/{z}.py' for f, _ in bundle):
                return z, 'own_name'
        return None, ('dead_ref:' + _clean_ref(zs or raw)) if (zs or raw) else 'none'
    return _cached(ctx, ('zone_script_base', z), build)


def zone_script_ref(ctx, zone):
    """The world entity's zonescript for a converted XML1 zone, in this order:
      0. x1/zones/<zone> generated by the act-on-entry plan (act_on_entry_plan: a zone with a single campaign act
         whose zone script sets none: setCurrentAct only, or setCurrentAct + a copy of its zone script);
      1. zone_acts.json[zone]['zonescript'] (XML1 world attribute, else the zone's own-name script) if it
         exists (for 79 zones that script carries the setCurrentAct injected by the rewrite);
      2. x1/zones/<zone> if generated by the research (27 zones without any zone script: setCurrentAct only);
      3. the XML1 world zonescript attribute, normalised, if that script exists (zones not in zone_acts.json);
      4. the zone's own-name script <zone> if installed and packaged by the XML1 zone bundle (extension of
         SPEC 5.2: XML1 runs it by convention; mocap briefings, hive2_2_1, ...);
      5. None."""
    return _zone_script_choice(ctx, zone)[0]


def zone_act(ctx, zone):
    """Act of an XML1 zone: the act-on-entry plan's campaign act when it is a single act; else zone_acts.json
    inject_act, else the first of its acts; for zones zone_acts.json does not cover (.xml zones), the act of the
    first planned mission whose mapload is this zone; else None."""
    z = _zone_id(zone)
    pz = act_on_entry_plan(ctx)['zones'].get(z) or {}
    if pz.get('entry_act') is not None:
        return int(pz['entry_act'])
    if len(pz.get('acts') or ()) == 1:
        return int(pz['acts'][0])
    info = _zone_acts(ctx).get(z)
    if info:
        if info.get('inject_act'):
            return int(info['inject_act'])
        acts = info.get('acts') or []
        return int(acts[0]) if acts else None
    return _mapload_acts(ctx).get(z)


def _mapload_acts(ctx) -> dict:
    def build():
        try:
            plan = ctx.research_json('scripts/mission_plan.json')['missions']
        except (FileNotFoundError, KeyError):
            return {}
        out = {}
        for m, info in plan.items():
            ml = _zone_id(((info.get('attrs') or {}).get('mapload') or '').strip())
            if ml and ml not in out and info.get('act') is not None:
                out[ml] = int(info['act'])
        return out
    return _cached(ctx, 'mapload_acts', build)


# ----------------------------------------------------------------------------------------------- forced heroes
def _mission_plan(ctx) -> dict:
    try:
        return ctx.research_json('scripts/mission_plan.json')['missions']
    except (FileNotFoundError, KeyError):
        return {}


def forced_hero_missions(ctx) -> dict:
    """{mission: why} for the XML1 missions that force their heroes: REQUIREDHERO entries or maxheros < 4
    (research mission_plan.json, the XML1 mission files). Retail XML2 has no script function that adds or removes a
    party member (loadMapChooseTeam / isActorOnTeam / setTeamInvisible / swapInStump / extractionPointLite only), so
    without xml2-fix [Game] ForcedTeams their starts load with loadMapChooseTeam and the player can at least pick a
    matching party; seat builds seat XML1's party through xml2-fix (forced_party_plan, SPEC 19)."""
    def build():
        out = {}
        for m, info in _mission_plan(ctx).items():
            attrs = info.get('attrs') or {}
            req = [h for h in (info.get('required') or []) if h]
            try:
                mx = int(str(attrs.get('maxheros') or '').strip())
            except ValueError:
                mx = None
            why = []
            if req:
                why.append('REQUIREDHERO ' + '/'.join(h.lower() for h in req))
            if mx is not None and mx < FORCED_HERO_MAX:
                why.append(f'maxheros={mx}')
            if why:
                out[m.lower()] = ', '.join(why)
        return out
    return _cached(ctx, 'forced_hero_missions', build)


def _forced_hero_bodies(ctx) -> dict:
    """{mission: stripped body lines (marker first)} of x1/missions/begin_<m> for every forced-hero mission,
    after the _base_text passes (the same passes every inlined copy of the body gets)."""
    def build():
        out = {}
        for m in forced_hero_missions(ctx):
            ref = f'x1/missions/begin_{m}'
            if ref not in _installable_refs(ctx):
                continue
            lines = [l.strip() for l in _base_text(ctx, ref)[0].split('\r\n')]
            k = next((i for i, l in enumerate(lines) if T.BEGIN_MARKER.match(l)), None)
            if k is None:
                continue
            body = lines[k:]
            while body and not body[-1]:
                body.pop()
            out[m] = body
        return out
    return _cached(ctx, 'forced_hero_bodies', build)


# ----------------------------------------------------------------------------------------------- forced teams
def _mission_bodies(ctx) -> dict:
    """{mission: stripped body lines (marker first)} of x1/missions/begin_<m> for EVERY mission (after the
    _base_text passes, as _forced_hero_bodies)."""
    def build():
        out = {}
        for m in _mission_plan(ctx):
            ref = SIDE_BEGIN_REF.format(m.lower())
            if ref not in _installable_refs(ctx):
                continue
            lines = [l.strip() for l in _base_text(ctx, ref)[0].split('\r\n')]
            k = next((i for i, l in enumerate(lines) if T.BEGIN_MARKER.match(l)), None)
            if k is None:
                continue
            body = lines[k:]
            while body and not body[-1]:
                body.pop()
            out[m.lower()] = body
        return out
    return _cached(ctx, 'mission_bodies', build)


def _mission_bodies_final(ctx) -> dict:
    """_mission_bodies as every copy looks after choose_team_in_bodies (what forced_party_in_bodies matches)."""
    def build():
        forced = _forced_hero_bodies(ctx)
        return {m: T.choose_team_in_bodies(b, forced)[0] if m in forced else list(b)
                for m, b in _mission_bodies(ctx).items()}
    return _cached(ctx, 'mission_bodies_final', build)


def _port_heroes(ctx) -> dict:
    """lower name -> XML1 <stats> element of the XML1 heroes in this build's herostat (heroes.hero_plan)."""
    def build():
        try:
            from . import heroes as H                          # noqa: WPS433 - provider of the content module
            return dict(H.hero_plan(ctx)['x1'])
        except Exception as e:          # noqa: BLE001 - no roster plan: no hero can be seated
            ctx.warn(f'forced teams: heroes.hero_plan unavailable ({type(e).__name__}: {e}); no party is seated')
            return {}
    return _cached(ctx, 'port_heroes', build)


def skinset_args(ctx, skinset):
    """XML1 mission skinset -> setSkinset (costume, heroes) (design 3.5): default / none -> ('default', ''); else the
    XML2 costume name of the variant (Magma's skin_magmacivilian is the port's skin_civilian, heroes.COSTUME_RENAME)
    and the comma list (sorted) of the port's heroes whose XML1 herostat entry has skin_<skinset> - the DLL cannot
    tell Magma's civilian slot from Iceman's otherwise."""
    s = (skinset or '').strip().lower()
    if s in ('', 'default', 'none'):
        return 'default', ''
    try:
        from . import heroes as H                              # noqa: WPS433
        rename = H.COSTUME_RENAME
    except Exception:          # noqa: BLE001
        rename = {}
    attr = f'skin_{s}'
    costume = rename.get(attr, attr)[len('skin_'):]
    heroes = sorted(h for h, st in _port_heroes(ctx).items()
                    if any(k.lower() == attr and (v or '').strip() for k, v in st.attrib.items()))
    return costume, ','.join(heroes)


def _xml1_seat_list(info):
    """XML1's team builder (xbe 0x18d6d0, design 1.4): REQUIRED in file order, then RECOMMENDED into the free slots
    (4), RESTRICTED cleared, capped at maxheros (no maxheros: 4), lowercase, compact."""
    req = [h.lower() for h in info.get('required') or [] if h]
    rec = [h.lower() for h in info.get('recommended') or [] if h]
    res = {h.lower() for h in info.get('restricted') or [] if h}
    try:
        mx = int(str((info.get('attrs') or {}).get('maxheros') or '').strip())
    except ValueError:
        mx = FORCED_PARTY_SLOTS
    slots = []
    for h in req + rec:
        if h not in slots and len(slots) < FORCED_PARTY_SLOTS:
            slots.append(h)
    return [h for h in slots if h not in res][:max(0, min(mx, FORCED_PARTY_SLOTS))]


def forced_party_plan(ctx) -> dict:
    """Pure (cached): the forced-team plan of all 101 XML1 missions (SPEC 19, design 3.1/3.3/3.5).
    {mission: {'act', 'forced': bool, 'seat': [names] (the XML1 builder's party minus JOIN_LATER), 'unseatable':
    [names not in this build's herostat], 'skinset': XML1 skinset, 'costume', 'heroes' (setSkinset args),
    'load': the body's load function, 'zone': its zone, 'status'}} with status
      'seat'   a forced mission whose party is seated (seat block),
      'menu'   forced, but a name is not a herostat hero of this build (profxgladiator in --hero-roster 21xml2,
               heroes.ROSTER_NPC): keeps the team menu (skinset block),
      'cut'    forced, its zone does not exist in XML1's data (skinset block; nothing may start it),
      'free'   not forced (skinset block)."""
    def build():
        forced = forced_hero_missions(ctx)
        heroes = _port_heroes(ctx)
        zones = set(ctx.x1_zones())
        bodies = _mission_bodies(ctx)
        out = {}
        for m, info in _mission_plan(ctx).items():
            ml = m.lower()
            body = bodies.get(ml) or []
            k = T.body_load_index(body)
            fn, zone = T.body_load(body[k]) if k is not None else (None, None)
            zone = _zone_id(zone) if zone else None
            costume, hs = skinset_args(ctx, (info.get('attrs') or {}).get('skinset'))
            row = {'act': info.get('act'), 'forced': ml in forced, 'skinset': (info.get('attrs') or {}).get('skinset'),
                   'costume': costume, 'heroes': hs, 'load': fn, 'zone': zone, 'seat': [], 'unseatable': [],
                   'cut': bool(zone) and (zone not in zones or not _x1_zone_convertible(ctx, zone))}
            if ml in forced:
                seat = [h for h in _xml1_seat_list(info) if h not in JOIN_LATER.get(ml, ())]
                row['seat'] = seat
                row['unseatable'] = [h for h in seat if h not in heroes]
                if row['cut'] or not zone:
                    row['status'] = 'cut'
                elif row['unseatable'] or not seat or fn not in ('loadMapKeepTeam', 'loadMapChooseTeam'):
                    row['status'] = 'menu'
                else:
                    row['status'] = 'seat'
            else:
                row['status'] = 'free'
            out[ml] = row
        return out
    return _cached(ctx, 'forced_party_plan', build)


def cut_missions(ctx) -> set:
    """forced missions whose start loads a zone XML1's data does not have (status 'cut': nyc_rooftops,
    boss_sabreroof, ice_wolverine; design 3.3). Free missions with such a load (muir, muir_int, sewers_hub2,
    boss_multipleman, nyctest2: forced_party_plan 'cut' True) are pre-existing and left to their own review."""
    return {m for m, r in forced_party_plan(ctx).items() if r['status'] == 'cut'}


def _side_plan(ctx) -> dict:
    """{side: {'parent', 'status', 'push': bool, 'end': (costume, heroes) | None | 'keep'}} (design 3.4): a seated
    side mission pushes at its begin site and pops at its end sites (restoring the parent mission's skinset); an
    unseatable one (astral_sk) keeps its team-menu start and returns through the team menu (T9 simple, end None);
    a cut one is left alone ('keep')."""
    def build():
        plan = forced_party_plan(ctx)
        out = {}
        for s, parent in SIDE_MISSIONS.items():
            st = (plan.get(s) or {}).get('status', 'cut')
            p = plan.get(parent) or {}
            if st == 'seat':
                end = (p.get('costume', 'default'), p.get('heroes', ''))
            elif st == 'menu':
                end = None
            else:
                end = 'keep'
            out[s] = {'parent': parent, 'status': st, 'push': st == 'seat', 'end': end}
        return out
    return _cached(ctx, 'side_plan', build)


def team_lock_plan(ctx) -> dict:
    """{'missions': {mission: 1 | 0}, 'sides': {side: 1 | 0}} (pure, cached): the team lock each mission start sets -
    1 for a seated forced mission (XML1 REQUIREDHERO / maxheros: its Xtraction Points keep the party), 0 for every
    other (free, keep, team-menu starts) - and the one each seated side mission's return (popParty) restores: its
    caller mission's (SIDE_MISSIONS)."""
    def build():
        plan = forced_party_plan(ctx)
        missions = {m: int(r['status'] == 'seat') for m, r in plan.items()}
        sides = {s: missions.get(r['parent'], 0) for s, r in _side_plan(ctx).items() if r['end'] != 'keep'}
        return {'missions': missions, 'sides': sides}
    return _cached(ctx, 'team_lock_plan', build)


def _inline_side_begins(ctx) -> dict:
    """{x1/missions/begin_<s>: s} for the seated side missions a DATA beginSideMission starts (conversation
    chosenscriptfile -> research inline rewrite to begin_<s>: dr_mag1, wx_fb_start, muir2_reboot). Their begin
    script carries the push block itself (before its marker); the design generated a side_<s> copy instead, which is
    equivalent because nothing else runs begin_<s> - checked here: every inline rewrite to it is a beginSideMission
    and no installed script names it."""
    def build():
        sides = _side_plan(ctx)
        refs = collections.defaultdict(set)
        for key, val in _inline_map(ctx).items():
            if '(' not in val:
                refs[C.script_ref(_clean_ref(val))].add(key)
        out = {}
        for s, r in sides.items():
            ref = SIDE_BEGIN_REF.format(s)
            keys = refs.get(ref)
            if not r['push'] or not keys or not all('beginsidemission' in k.lower() for k in keys):
                continue
            named = [x for x, p in _research_scripts(ctx).items() if x != ref and ref in
                     p.read_bytes().decode('latin-1').lower()]
            if named:
                if _once(ctx, 'inline_side_named', ref):
                    ctx.error(f'forced teams: {ref} is also named by {named[:3]}; its push block would run for them')
                continue
            out[ref] = s
        return out
    return _cached(ctx, 'inline_side_begins', build)


def _inline_end_refs(ctx) -> dict:
    """{research inline value of an XML1 data endSideMission: generated end script ref} (seat builds; design 3.4)."""
    return {k: ref for ref, g in _forced_generated_scripts(ctx).items() for k in [g['inline_key']]}


def _forced_generated_scripts(ctx) -> dict:
    """ref -> {side, inline_key, lines} of the end scripts a --forced-teams seat build generates for an XML1 DATA
    endSideMission (INLINE_SIDE_ENDS): the research's inline value (setCurrentAct(n) + loadZone(caller, '')) under
    the endSideMission marker, which _script_text then turns into the pop block like a script end site."""
    if C.forced_teams_mode(ctx) != 'seat':
        return {}

    def build():
        out = {}
        rw = _inline_map(ctx)
        sides = _side_plan(ctx)
        for key, s in INLINE_SIDE_ENDS.items():
            val = rw.get(key)
            if val is None or sides.get(s, {}).get('end') in ('keep',):
                continue
            stmts = [p.strip() for p in L.split_inline(val) if p.strip()]
            body = []
            for p in stmts:
                p = p.replace("'", '"')
                m = re.fullmatch(r'(\w+)\((.*)\)', p)
                body.append(f'{m.group(1)}({m.group(2).replace(",", ", ")} )' if m else p)
            out[SIDE_END_REF.format(s)] = {
                'side': s, 'inline_key': key,
                'lines': ['# Generated by xml1build (scripts forced teams, SPEC 19)',
                          f'# XML1 endSideMission of side mission {s} from data ({key}): a dialog option runs one '
                          f'console token, so the return block lives in this script',
                          f'# ( "XML1 endSideMission from side mission {s}" )'] + body}
        return out
    return _cached(ctx, 'forced_generated', build)


# ----------------------------------------------------------------------------------------------- act on entry
def _campaign_missions(ctx):
    """({mission: act} of the missions that can set the act in the campaign, {mission: why excluded})."""
    def build():
        reach = set(ctx.graph.get('reachable_missions') or ())
        acts, excluded = {}, {}
        for m, info in _mission_plan(ctx).items():
            if info.get('act') is None:
                continue
            if NONCAMPAIGN_MISSION.search(m):
                excluded[m] = 'boss / demo / test mission (act-9 extras)'
            elif reach and m not in reach:
                excluded[m] = 'not started from New Game (graph.json reachable_missions: only the XML1 debug ' \
                              'level list ui/menus/map_list, missions.xml or its own files name it)'
            else:
                acts[m] = int(info['act'])
        return acts, excluded
    return _cached(ctx, 'campaign_missions', build)


def _x1_zone_convertible(ctx, z) -> bool:
    """the zones module's skip rule (SPEC 5.3.1): zonexml and map IGB present and non-empty."""
    zx = next((f'maps/{z}{e}' for e in ('.eng', '.xml') if ctx.x1_path(f'maps/{z}{e}') is not None), None)
    igb = f'maps/{z}.igb'
    return bool(zx) and not ctx.x1_is_empty(zx) and ctx.x1_path(igb) is not None and not ctx.x1_is_empty(igb)


def _script_mentions(ctx) -> collections.Counter:
    """normalised script ref -> number of places that can RUN it besides a world zonescript: XML1 text attribute
    values (English/neutral files; the world zonescript attribute itself is counted separately), quoted literals
    in the research scripts, generated dialog options and inline-rewrite targets."""
    def build():
        c = collections.Counter()
        val = re.compile(r'([\w]+)\s*=\s*"([^"(]{3,})"')
        for rel in ctx.x1_rels(''):
            if rel.startswith(('scripts/', 'packages/')) or not rel.endswith(('.eng', '.xml', '.chr')):
                continue
            for m in val.finditer(ctx.x1_path(rel).read_bytes().decode('latin-1')):
                a = m.group(1).lower()
                if a == 'zonescript' or not (_is_script_attr(a) or a in CONSOLE_ATTRS):
                    continue
                c[C.script_ref(_clean_ref(m.group(2)))] += 1
        lit = re.compile(r'["\']([A-Za-z0-9_/\\.]+)["\']')
        for ref, p in _research_scripts(ctx).items():
            # a zone literal of a load call names a zone, not a script (own-name zone scripts share its path)
            text = T._ZONE_CALL.sub('', p.read_bytes().decode('latin-1'))
            for m in lit.finditer(text):
                c[C.script_ref(_clean_ref(m.group(1)))] += 1
        for paths in _research_dialogs(ctx).values():
            for opt in C.decode_xmlb(paths['xmlb'].read_bytes()).iter():
                s = opt.get('script') or ''
                if s and '(' not in s:
                    c[C.script_ref(s)] += 1
        for v in _inline_map(ctx).values():
            if '(' not in v:
                c[C.script_ref(_clean_ref(v))] += 1
        return c
    return _cached(ctx, 'script_mentions', build)


def act_on_entry_plan(ctx) -> dict:
    """Pure (cached): which XML1 zones set their act on entry and how (scripts plan step 6, completed).

    XML2 zone scripts call setCurrentAct(n) first so the act's objectives are loaded after a save/load or a zone
    hop (150 calls in XML2's own scripts). The research injected it into 73 zone scripts and generated 27
    x1/zones scripts, but only for zones whose owning missions (zone_acts.json, by directory) all share one act,
    counting the 22 boss_*/demo/test missions packed into act 9 and the missions nothing in the campaign starts.
    Here a zone's campaign acts are the acts of
      * its zone_acts.json missions, minus boss_*/demo/*test* and minus missions graph.json proves are not
        started from New Game (_campaign_missions),
      * the campaign missions that start in it (graph.json mission_start_zones: mapload / loads),
      * for a zone with neither, the union of its predecessors' acts (graph.json zone_edges, to a fixed point).
    A zone whose chosen zone script contains no setCurrentAct and which has exactly one campaign act gets it:
      'x1_act_entry'     no zone script: generated x1/zones/<zone> = setCurrentAct(n) only;
      'inject'           the zone script is used as zonescript only by zones of that act and nothing else runs
                         it: setCurrentAct(n) injected as its first statement (rewrite_scripts' format);
      'x1_act_wrapper'   otherwise: generated x1/zones/<zone> = setCurrentAct(n) + a copy of the zone script (the
                         original stays installed for its other users).
    Zones with several campaign acts or none stay deferred.

    Returns {'zones': {zone: {acts, sources, script, how, entry_act, status}}, 'inject': {ref: act},
             'zone_script': {zone: generated ref}, 'generated': {ref: {zone, act, kind, copy_of}},
             'excluded_missions': {m: why}}."""
    def build():
        camp, excluded = _campaign_missions(ctx)
        za = _zone_acts(ctx)
        g = ctx.graph
        starts = g.get('mission_start_zones') or {}
        edges = g.get('zone_edges') or {}
        # the menu backdrop is never a campaign zone (either front end, SPEC 21): no act on entry
        zones = [z for z in ctx.x1_zones() if z not in C.MENU_ZONES and _x1_zone_convertible(ctx, z)]
        acts, sources = {}, {}
        for z in zones:
            s, src = set(), []
            info = za.get(z)
            if info:
                own = {camp[m] for m in info.get('missions') or () if m in camp}
                if own:
                    s |= own
                    src.append('zone_acts missions ' + ','.join(m for m in info['missions'] if m in camp))
            st = {camp[m] for m, zl in starts.items() if m in camp and z in {_zone_id(x) for x in zl}}
            if st:
                s |= st
                src.append('mission start ' + ','.join(sorted(m for m, zl in starts.items()
                                                              if m in camp and z in {_zone_id(x) for x in zl})))
            if s:
                acts[z], sources[z] = s, src
        pred = collections.defaultdict(set)
        for a, bs in edges.items():
            for b in bs:
                pred[_zone_id(b)].add(_zone_id(a))
        derived = {}
        changed = True
        while changed:
            changed = False
            for z in zones:
                if z in sources:
                    continue
                u = set()
                for p in pred.get(z, ()):
                    u |= acts.get(p, set())
                if u and u != acts.get(z):
                    acts[z] = u
                    derived[z] = sorted(p for p in pred.get(z, ()) if p in acts)
                    changed = True
        for z, ps in derived.items():
            sources[z] = ['predecessors ' + ','.join(ps)]
        # the zone script each zone would run without this plan, and whether it sets an act. Only zones reachable
        # from New Game (graph.json) are changed; the others keep the research state (their act is never needed).
        try:
            reach = set(ctx.tour_order())
        except (OSError, KeyError, ValueError):
            reach = set(zones)
        rows, cand = {}, {}
        users = collections.defaultdict(list)
        for z in zones:
            ref, how0 = _zone_script_choice_base(ctx, z)
            raw = _raw_lines_base(ctx, ref) if ref else None
            text = '\r\n'.join(raw) if raw else ''
            has_act = bool(re.search(r'\bsetCurrentAct\s*\(', text))
            entry = T.first_statement_act(raw) if raw else None
            a = sorted(acts.get(z, ()))
            row = {'acts': a, 'sources': sources.get(z, []), 'script': ref, 'script_how': how0,
                   'entry_act': entry, 'how': None, 'reachable': z in reach}
            if ref:
                users[ref].append(z)
            if has_act:
                row['status'] = 'sets_act' if entry is not None else 'sets_act_later'
            elif z not in reach:
                row['status'] = 'unreachable_no_act'
            elif not a:
                row['status'] = 'deferred_no_act'
            elif len(a) > 1:
                row['status'] = 'deferred_multi_act'
            else:
                row['status'] = 'planned'
                cand[z] = a[0]
            rows[z] = row
        mentions = _script_mentions(ctx)
        inject, zone_script, generated = {}, {}, {}
        for z, n in sorted(cand.items()):
            row = rows[z]
            ref = row['script']
            if ref is None:
                gref = f'x1/zones/{z}'
                if gref in _installable_refs(ctx):          # (cannot happen: the research ones all set an act)
                    row['status'] = 'deferred_research_x1_zones_script_without_act'
                    continue
                generated[gref] = {'zone': z, 'act': n, 'kind': 'x1_act_entry', 'copy_of': None,
                                   'lines': ['# Generated by xml1build (scripts.act_on_entry_plan)',
                                             f'# zone entry act for {z} (no XML1 zone script)']}
                inject[gref] = n
                zone_script[z] = gref
                row.update(how='x1_act_entry', entry_act=n)
                continue
            same = all(cand.get(u) == n for u in users[ref])
            if same and mentions.get(ref, 0) == 0 and ref in _installable_refs(ctx):
                inject[ref] = n
                row.update(how='inject', entry_act=n)
                continue
            gref = f'x1/zones/{z}'
            base = _raw_lines_base(ctx, ref)
            if gref in _installable_refs(ctx) or base is None:
                row['status'] = 'deferred_no_wrapper'
                continue
            generated[gref] = {'zone': z, 'act': n, 'kind': 'x1_act_wrapper', 'copy_of': ref,
                               'lines': ['# Generated by xml1build (scripts.act_on_entry_plan)',
                                         f'# zone entry act for {z} plus a copy of its zone script {ref}'] +
                                        [l for l in base if not l.startswith('# Generated by')]}
            inject[gref] = n
            zone_script[z] = gref
            row.update(how='x1_act_wrapper', entry_act=n)
        for z, row in rows.items():
            if row['how'] and row['status'] == 'planned':
                row['status'] = row['how']
        return {'zones': rows, 'inject': inject, 'zone_script': zone_script, 'generated': generated,
                'excluded_missions': excluded}
    return _cached(ctx, 'act_plan', build)


def _raw_lines_base(ctx, ref):
    """research script lines (no generated scripts): used while the act plan is being built."""
    p = _research_scripts(ctx).get(ref)
    return C.to_crlf(p.read_bytes().decode('latin-1')).split('\r\n') if p is not None else None


def _generated_zone_scripts(ctx) -> dict:
    """ref -> {zone, act, kind, copy_of, lines} of the zone-entry scripts the act plan generates."""
    return act_on_entry_plan(ctx)['generated']


def zone_package_extras(ctx, zone):
    """[(kind, filename)] the zone PKGB must list besides its XML1 bundle: zone_extra_files.json
    (dialogs/x1/pNNN -> xml_resident, scripts/x1/... -> script) plus the scripts the retargeted dialog
    options run. Filenames are lowercase, extensionless, relative to the game root."""
    z = _zone_id(zone)

    def build():
        out, seen = [], set()

        def add(kind, fn):
            if (kind, fn) not in seen:
                seen.add((kind, fn))
                out.append((kind, fn))

        retargets = _dialog_retargets(ctx)['changes']
        for e in _zone_extra(ctx).get(z, []):
            e = C.norm(e)
            if e.startswith('dialogs/'):
                if dialog_exists(ctx, e):
                    add('xml_resident', e)
                name = e.rpartition('/')[2]
                if e.startswith('dialogs/x1/') and name in retargets:
                    for ch in retargets[name]:
                        if ch['script_ref']:
                            add('script', f"scripts/{ch['script_ref']}")
            elif e.startswith('scripts/'):
                if script_exists(ctx, e):
                    add('script', e)
        return out
    return list(_cached(ctx, ('extras', z), build))


_SPEAKER_TOKEN = re.compile(r'%[^%\s]+%')


def rewrite_speaker_tokens(text):
    """conversation text: XML1-only speaker aliases (SPEAKER_TOKEN_ALIASES, matched case-insensitively) -> the
    stats name token XMen2.exe resolves."""
    return _SPEAKER_TOKEN.sub(lambda m: SPEAKER_TOKEN_ALIASES.get(m.group(0).lower(), m.group(0)), text)


def _is_script_attr(a: str) -> bool:
    a = a.lower()
    return a not in NOT_SCRIPT_ATTRS and (a in SCRIPT_REF_ATTRS or a.endswith('script') or a.endswith('scriptfile'))


def rewrite_data_tree(ctx, root, rel) -> int:
    """Rewrite the script content of one XML1 data tree (zone XML, conversation, dialog, data/entities,
    world table) in place; returns the number of attribute values changed.
      * exact-value replacement from research/scripts/out/inline_rewrites.json (129 inline scripts that call
        XML1-only functions: mission vars -> game flags, beginMission -> x1/missions/begin_*, ...);
      * script-reference attributes (actscript, deathscript, chosenscriptfile, scriptfile, script, zonescript,
        any name ending in 'script'/'scriptfile') without '(': '\\' -> '/', lower case, no '.py';
      * console attributes (script/scriptok/scriptcancel in dialogs/ and ui/ files) are compacted to one
        whitespace-free token ('runscript <code>');
      * inline scripts (value with '(') in script attributes are checked like XMen2.exe does: > 255 bytes, an
        unregistered / mis-cased function, wrong argc or literal type -> warning (deduplicated per build).
    Pure apart from the tree it is given (no files written)."""
    if root is None:
        return 0
    rw = _inline_map(ctx)
    api = ctx.xml2_api
    r = C.norm(rel or '')
    console_file = r.startswith(('dialogs/', 'ui/'))
    conversation = r.startswith('conversations/')
    # SPEC 18.1: a conversation whose speakers are renamed NPC doubles (T.NPC_DOUBLE_CONVERSATIONS) names them by the
    # double's name - its %HERO% speaker tokens and the entity literals of its inline code
    conv_ref = C.split_ext(r[len('conversations/'):])[0] if conversation else ''
    doubles = T.npc_double_conversation_heroes(conv_ref) if conversation else set()
    # SPEC 18.1: hero NPCs with XML1's own entity name speak under that name (T.NPC_SPEAKER_CONVERSATIONS)
    npc_speakers = T.npc_speaker_renames(conv_ref) if conversation else {}
    n = BP.rewrite_data(root, r)
    n += SF.fix_player_starts(root, r)   # SPEC 41: starts that land outside the walkable area
    if conversation:
        n += CV.resolve_cross_file_tagjumps(ctx, root, rel)   # SPEC 39: first, so the copy is marked/rewritten too
        n += _drop_cut_mission_responses(ctx, root, rel)
        n += CV.mark_auto_advance(root)   # SPEC 34: runWithoutUser lines -> a negative timeDelay (xml2-fix AutoAdvance)
    inline_ends = _inline_end_refs(ctx)            # SPEC 19: data endSideMission -> generated end script (seat)
    x1_front = C.frontend_mode(ctx) == 'xml1'      # SPEC 21: imageViewer literals follow the review namespace
    for el in root.iter():
        for k, v in list(el.attrib.items()):
            if v is None or v == '':
                continue
            kl = k.lower()
            new = rw.get(v, v)
            if v in inline_ends and (_is_script_attr(kl) or kl in CONSOLE_ATTRS):
                new = inline_ends[v]
                if _once(ctx, 'inline_side_end', (r, v)):
                    ctx.note(f'{rel}: {k}={v!r} -> {new} (XML1 endSideMission: the forced-teams return block, SPEC 19; '
                             f'a dialog option runs one console token)')
            if conversation and kl in SPEAKER_ATTRS and '%' in new:
                new = rewrite_speaker_tokens(new)
                if doubles:
                    new = T.rename_speaker_tokens(new, doubles)[0]
                if npc_speakers:
                    new = T.rename_speaker_tokens(new, npc_speakers)[0]
            if doubles and '(' in new and (_is_script_attr(kl) or kl in CONSOLE_ATTRS):
                new = T.rename_npc_refs([new], doubles)[0][0]
            if 'mission' in new.lower():
                # XML1 EA_MISSIONn enums (playanim in inline code, FightMove animenum) -> XML2's EA_ZONEn
                new = T.rename_mission_anims(new)[0]
            if kl == 'monster_spawnscript' and 'loop_wake' in new.lower() and '(' in new \
                    and spawner_unwakeable(ctx, {a.lower(): b for a, b in el.attrib.items()}):
                # npc-loop fix: inline LOOP_WAKE spawn animation on an NPC XMen2.exe cannot wake (see
                # scripts_transform.bound_unwakeable_loops); same statements, INLINE_SEP-separated like XML2's own
                stmts, bl, _sk = T.bound_unwakeable_loops(new.split(L.INLINE_SEP), inline=True)
                if bl:
                    new = L.INLINE_SEP.join(stmts)
                    if _once(ctx, 'unwakeable_inline', (r, el.get('name'))):
                        ctx.note(f'{rel}: <{el.tag} {el.get("name")}> {k}: LOOP_WAKE {bl[0][0]} on '
                                 f'{el.get("character")} bounded to {T.UNWAKEABLE_LOOP_SECONDS:g} s then STOP '
                                 f'(non-combatant: XMen2.exe never wakes it)')
            script_attr = _is_script_attr(kl)
            if new == v and '(' in v and (script_attr or kl in CONSOLE_ATTRS):
                ms = _mission_start_ref(ctx, v)
                if ms:
                    new = ms
                    if _once(ctx, 'mission_start', v):
                        ctx.note(f'{rel}: {k}={v!r} -> {ms} (inline mission start the research rewrite map lacks, '
                                 'e.g. a single-quoted attribute; same rule as rewrite_scripts.rewrite_inline)')
            if x1_front and 'imageviewer' in new.lower() and '(' in new:
                # SPEC 21 C.4.2: comic / concept pickups name the XML1 textures under their x1/ namespace (the
                # Review value they unlock, 0x49e440 / 0x4ae530)
                nn, iv = T.rewrite_image_viewer(new, lambda p: C.map_review_texture(ctx, p))
                if iv:
                    new = nn
                    if _once(ctx, 'image_viewer', (r, v)):
                        ctx.note(f'{rel}: imageViewer {iv} (SPEC 21 review namespace)')
            console = console_file and kl in CONSOLE_ATTRS
            if (script_attr or console) and new.strip().lower() not in BOOL_VALUES:
                if '(' not in new and L.INLINE_SEP not in new:
                    new = _clean_ref(new)
                    if not script_exists(ctx, new) and _once(ctx, 'dead_ref', new):
                        ctx.note(f'{rel}: {k}="{v}": script {new} exists in neither XML1 nor XML2 '
                                 '(dead reference on the XML1 disc)')
                elif '(' not in new:
                    if _once(ctx, 'degenerate', new):
                        ctx.note(f'{rel}: {k}="{v}": inline script without a call (XML1 defect; kept)')
                else:
                    if console:
                        c = L.compact(new)
                        if c != new:
                            new = c
                        bad = L.console_problems(new)
                        if bad and _once(ctx, 'console', new):
                            ctx.warn(f'{rel}: {k}="{new}": ' + '; '.join(bad))
                    probs, _ = L.lint_inline(new, api)
                    if probs and _once(ctx, 'inline', new):
                        # XML1 would have dropped the same statement if it fails XML1's own table too
                        x1probs = L.lint_inline(v, _xml1_api(ctx), forbidden=False)[0] if new == v else []
                        shown = new if len(new) <= 120 else new[:117] + '...'
                        msg = f'{rel}: {k} inline script {shown!r}: ' + \
                              '; '.join(f'{kind}: {d}' for _, kind, d in probs[:4])
                        if x1probs and not any(kind == 'size' for _, kind, _ in probs):
                            ctx.note(msg + ' (XML1 drops it too: XML1 defect, unchanged)')
                        else:
                            ctx.warn(msg)
            if '(' in new and (script_attr or console):
                # SPEC 4.1: zone ids in load calls lowercase with '/' (same pass as installed scripts)
                nn, zl = T.normalise_zone_literals(new)
                if zl:
                    new = nn
            if new != v:
                el.set(k, new)
                n += 1
    return n


def _drop_cut_mission_responses(ctx, root, rel) -> int:
    """Owen's decision (FORCED_TEAMS_DESIGN 7.7): a conversation response whose chosenscriptfile starts a mission
    whose zone XML1's data does not have (cut_missions: XML1 conversations/nyc/riots/3_2_6 offers
    beginSideMission('nyc_rooftops'), zone nyc/riots/nyc_roof1 exists in neither XML1 tree) is removed - it was a
    live load of a missing zone. A line keeps at least one response (else the response stays, warned)."""
    starts = {SIDE_BEGIN_REF.format(m) for m in cut_missions(ctx)}
    if not starts:
        return 0
    rw = _inline_map(ctx)
    n = 0
    for parent in list(root.iter()):
        resp = [c for c in parent if c.tag.lower() == 'response']
        for ch in resp:
            v = next((val for key, val in ch.attrib.items() if key.lower() == 'chosenscriptfile'), None)
            if not v:
                continue
            new = rw.get(v, v)
            target = C.script_ref(_clean_ref(new)) if '(' not in new else (_mission_start_ref(ctx, new) or '')
            if target not in starts:
                continue
            if len([c for c in parent if c.tag.lower() == 'response']) <= 1:
                if _once(ctx, 'cut_response_kept', (rel, v)):
                    ctx.warn(f'{rel}: the only response of a line starts cut mission {target} ({v!r}); kept')
                continue
            parent.remove(ch)
            n += 1
            if _once(ctx, 'cut_response', (rel, v)):
                ctx.note(f'{rel}: response {ch.get("text")!r} ({v!r} -> {target}) removed: it starts a mission '
                         f'whose zone XML1 never shipped (FORCED_TEAMS_DESIGN 7.7)')
    return n


_MISSION_START = re.compile(r'''^\s*(?:game\.)?(beginMission|beginSideMission|beginMissionHack)\s*\(\s*'''
                            r'''(['"])([^'"]+)\2\s*\)\s*$''')


def _mission_start_ref(ctx, code):
    """inline code that is exactly one XML1 mission start ('beginMission("m")', optionally with 'game.' and a
    trailing literal \\n\\r) -> 'x1/missions/begin_<m>' if that generated script exists, else None. Mirrors
    research/scripts/rewrite_scripts.rewrite_inline for values its double-quote-only scan missed."""
    pieces = [p for p in L.split_inline(code) if p.strip()]
    if len(pieces) != 1:
        return None
    m = _MISSION_START.match(pieces[0])
    if not m:
        return None
    ref = f'x1/missions/begin_{m.group(3).lower()}'
    return ref if ref in _installable_refs(ctx) else None


# ----------------------------------------------------------------------------------------------- dead-end dialogs
def _chooser_missions(ctx):
    """missions offered by XML1 conversations/mansion/man2/chose_mission.eng (the Sewers-or-Muir chooser):
    [(mission, response text, rewritten chosenscriptfile)]."""
    try:
        root = ctx.read_x1_xml('conversations/mansion/man2/chose_mission.eng')
    except KeyError:
        return []
    if root is None:
        return []
    rw = _inline_map(ctx)
    out = []
    for el in root.iter():
        v = el.get('chosenscriptfile') or ''
        m = re.search(r"beginMission\(\s*['\"]([^'\"]+)['\"]", v)
        if m:
            out.append((m.group(1).lower(), el.get('text') or '', rw.get(v)))
    return out


# graph.json as the frozen builder packages it (tools/freeze_builder.py, BUILDER_DESIGN.md 5.2: a release carries no
# game text) has this top-level key and no mission descname / description: the texts come from the user's disc
PACKAGED_MARK = '_packaged'


def _mission_texts(ctx, missions, m):
    """(description, descname) of XML1 mission m: graph.json's; from a packaged graph.json (no texts) the mission
    plan's instead - the same XML1 data/missions/<m>.eng attributes, made from the disc by prepare stage P2."""
    g = missions.get(m, {})
    if PACKAGED_MARK in ctx.graph and m in missions:
        plan = ctx.research_json('scripts/mission_plan.json').get('missions', {})
        g = (plan.get(m) or {}).get('attrs') or {}
    return g.get('description', ''), g.get('descname', '')


def _derive_find_hero_branch(ctx, option_text):
    """'Find Gambit' (p091, Muir Island done, sewers not yet): the chooser that offers 'muir' also offers the
    sewers mission; take the offered non-muir mission whose XML1 description names the hero. The target is
    that mission's generated start script (x1/missions/begin_<m>)."""
    hero = option_text.split()[-1].lower() if option_text.split() else ''
    offered = _chooser_missions(ctx)
    names = [m for m, _, _ in offered]
    if 'muir' not in names or not hero:
        return None
    missions = ctx.graph.get('missions', {})
    texts = {m: _mission_texts(ctx, missions, m) for m, _, _ in offered}
    cands = [(m, new) for m, _, new in offered
             if m != 'muir' and hero in (texts[m][0] + ' ' + texts[m][1]).lower()]
    if len(cands) != 1:
        return None
    m, new = cands[0]
    ref = new if new and '(' not in new else f'x1/missions/begin_{m}'
    if not script_exists(ctx, ref):
        return None
    return {'value': ref, 'script_ref': ref,
            'evidence': f"XML1 conversations/mansion/man2/chose_mission.eng offers beginMission('muir') and "
                        f"beginMission('{m}'); graph.json mission {m}: "
                        f"{texts[m][0]!r}"}


def _derive_post_branch_step(ctx, hero):
    """'Return to the Blackbird' (p092, both branches done): the step XML1 takes when the other branch (the
    one that frees `hero`) is finished - the zone the hero-freeing script loads (sewers/quest/fadegambit.py:
    setInCampaign('gambit') then loadMap('mocap/mocap4/Briefing_1_7_1'), 'Prof X on the Blackbird', whose
    zone script begins the next mission, arbiter)."""
    targets = set()
    pat_unlock = re.compile(r'unlockCharacter\(\s*["\']%s["\']' % re.escape(hero), re.I)
    pat_load = re.compile(r'loadMapKeepTeam\(\s*["\']([^"\']+)["\']')
    for ref, p in _installable_refs(ctx).items():
        if ref.startswith('x1/'):
            continue                                   # generated mission starts are not branch ends
        # XML1's own unlock sites only: not the mission-start / catch-up unlocks this module adds (issue #55)
        t = CRLF.join(T.strip_generated_unlocks((script_text(ctx, ref) or '').split(CRLF)))
        mu = pat_unlock.search(t)
        if not mu:
            continue
        for ml in pat_load.finditer(t, mu.end()):
            targets.add(_zone_id(ml.group(1)))
    if len(targets) != 1:
        return None
    zone = targets.pop()
    if zone not in set(ctx.x1_zones()):
        return None
    zref, _ = _zone_script_choice(ctx, zone)
    zp = script_text(ctx, zref) if zref and zref in _installable_refs(ctx) else None
    if zp is None or 'XML1 beginMission(' not in zp:
        return None
    code = f"loadMapKeepTeam('{zone}')"
    if L.console_problems(code):
        return None
    nxt = re.search(r'XML1 beginMission\((\w+)\)', zp).group(1)
    return {'value': code, 'script_ref': None,
            'evidence': f"the script that frees {hero} loads {zone}; its zone script {zref} begins "
                        f"mission {nxt} (XML1 loadMap == XML2 loadMapKeepTeam)"}


def _sibling_find_hero(ctx, name):
    """The hero of the 'Find <Hero>' option in a sibling popup created by the same script as x1/<name>
    (spokewithforge.py: questDone == 2 -> p091 'Find Gambit', else -> p092), if that option derives."""
    dialogs = _research_dialogs(ctx)
    for ref, p in sorted(_installable_refs(ctx).items()):
        t = script_text(ctx, ref)
        if f'createPopupDialogXml("x1/{name}"' not in t:
            continue
        for sib in re.findall(r'createPopupDialogXml\("x1/(p\d+)"', t):
            if sib == name or sib not in dialogs:
                continue
            for opt in C.decode_xmlb(dialogs[sib]['xmlb'].read_bytes()).iter():
                text = (opt.get('text') or '').strip()
                if opt.tag.lower() == 'option' and re.fullmatch(r'Find \w+', text) and \
                        _derive_find_hero_branch(ctx, text):
                    return text.split()[-1].lower()
    return None


def _dialog_retargets(ctx):
    """{'changes': {dialog: [{'index', 'text', 'old', 'value', 'script_ref', 'evidence'}]},
        'unresolved': [(dialog, index, text, old)]} for every generated dialog option whose script reference
    exists nowhere (only x1/p091 and p092 today)."""
    def build():
        changes, unresolved = {}, []
        for name, paths in sorted(_research_dialogs(ctx).items()):
            root = C.decode_xmlb(paths['xmlb'].read_bytes())
            for i, opt in enumerate(e for e in root.iter() if e.tag.lower() == 'option'):
                s = opt.get('script') or ''
                if not s or '(' in s or script_exists(ctx, s):
                    continue
                text = opt.get('text') or ''
                t = None
                if re.fullmatch(r'Find \w+', text.strip()):
                    # x1/p091 'Find Gambit' (dead muir_is/muir1/loadSewers)
                    t = _derive_find_hero_branch(ctx, text)
                elif text.strip().lower() == 'return to the blackbird':
                    # x1/p092 (dead muir_is/muir1/loadBlackbird): the else-branch of the same popup choice
                    hero = _sibling_find_hero(ctx, name)
                    t = _derive_post_branch_step(ctx, hero) if hero else None
                if t is None:
                    unresolved.append((name, i, text, s))
                else:
                    changes.setdefault(name, []).append({'index': i, 'text': text, 'old': s, **t})
        return {'changes': changes, 'unresolved': unresolved}
    return _cached(ctx, 'retargets', build)


# ----------------------------------------------------------------------------------------------- run helpers
def _xml1_objective_names(ctx) -> set:
    """lowercase OBJECTIVE names of every XML1 data/missions/*.eng|.xml."""
    def build():
        names = set()
        for rel in ctx.x1_rels('data/missions/'):
            if not rel.endswith(('.eng', '.xml')):
                continue
            try:
                root = ctx.read_x1_xml(rel)
            except Exception:          # noqa: BLE001
                continue
            if root is not None:
                names |= {(e.get('name') or '').lower() for e in root.iter() if e.tag.upper() == 'OBJECTIVE'}
        return names
    return _cached(ctx, 'x1_objectives', build)


def _statement_count(ctx, ref):
    if _installable_refs(ctx).get(ref) is None and ref not in _generated_zone_scripts(ctx) and \
            ref not in _forced_generated_scripts(ctx):
        return 0
    return _cached(ctx, ('stmts', ref), lambda: sum(1 for _ in L.iter_statements(
        script_text(ctx, ref).split('\r\n'))))


def _referenced_script_refs(ctx) -> set:
    """script refs something can run: XML1 zone bundles, zone scripts, generated extras / helpers / mission
    starts, inline rewrite targets, dialog options, and string literals naming a script inside any of those
    scripts (transitively)."""
    def build():
        inst = _installable_refs(ctx)
        refs = set(NEW_GAME_REFS) | {NEW_GAME_BODY} | set(_forced_generated_scripts(ctx))
        for b, files in ctx.manifest.items():
            for f, k in files:
                if (k or '').lower() == 'script':
                    refs.add(C.script_ref(f))
        for z in ctx.x1_zones():
            r = zone_script_ref(ctx, z)
            if r:
                refs.add(r)
            refs |= {C.script_ref(fn) for kind, fn in zone_package_extras(ctx, z) if kind == 'script'}
        try:
            refs |= {C.script_ref(h) for h in _rjson(ctx, 'helper_refs.json')}
        except FileNotFoundError:
            pass
        refs |= {C.script_ref(v) for v in _inline_map(ctx).values() if '(' not in v}
        try:
            for info in ctx.research_json('scripts/mission_plan.json')['missions'].values():
                ss = ((info.get('attrs') or {}).get('scriptstart') or '').strip()
                if ss:
                    refs.add(C.script_ref(_clean_ref(ss)))
        except (FileNotFoundError, KeyError):
            pass
        # attribute values in XML1 data (English / neutral text files) that name an installed script
        val = re.compile(r'=\s*"([^"(]{3,})"')
        for rel in ctx.x1_rels(''):
            if rel.startswith(('scripts/', 'packages/')) or not rel.endswith(('.eng', '.xml', '.chr')):
                continue
            p = ctx.x1_path(rel)
            for m in val.finditer(p.read_bytes().decode('latin-1')):
                c = C.script_ref(_clean_ref(m.group(1)))
                if c in inst:
                    refs.add(c)
        for paths in _research_dialogs(ctx).values():
            for opt in C.decode_xmlb(paths['xmlb'].read_bytes()).iter():
                s = opt.get('script') or ''
                if s and '(' not in s:
                    refs.add(C.script_ref(s))
        # transitive: quoted literals in reachable scripts that name an installed script
        todo = [r for r in refs if r in inst]
        seen = set(todo)
        lit = re.compile(r'["\']([A-Za-z0-9_/\\.]+)["\']')
        while todo:
            r = todo.pop()
            for m in lit.finditer(script_text(ctx, r)):
                c = C.script_ref(_clean_ref(m.group(1)))
                if c in inst and c not in seen:
                    seen.add(c)
                    refs.add(c)
                    todo.append(c)
        return refs
    return _cached(ctx, 'referenced', build)


def _console_senders(ctx):
    """script functions that queue a console command (research/scripts/verify/console_senders.json, else the
    same list built into scripts_lint), restricted to names XMen2.exe registers."""
    def build():
        try:
            names = ctx.research_json('scripts/verify/console_senders.json')
        except (FileNotFoundError, ValueError):
            names = L.CONSOLE_SENDERS_DEFAULT
        api = ctx.xml2_api
        out = tuple(n for n in names if n in api) or L.CONSOLE_SENDERS_DEFAULT
        # xml2-fix popParty queues one command (restorelastzone 0 / loadmap <z> 0 1, 0x55c410); pushParty runs its
        # pushsidemission at once (0x55beb0), like extractionPointChange's first half (SPEC 19)
        return out + tuple(n for n in L.XML2FIX_CONSOLE_SENDERS if n in api and n not in out)
    return _cached(ctx, 'console_senders', build)


def _queue_check(ctx, det, installed, new_game_lines):
    """<= 2 pending console commands (0x55c426): no script path may queue a 3rd command before a wait."""
    senders = _console_senders(ctx)
    refs = _installable_refs(ctx)
    bad, dead = [], []
    for ref in sorted(installed):
        lines = script_text(ctx, ref).split('\r\n')
        for ln, fn, n in L.console_overflows(lines, senders):
            msg = (f'scripts/{ref}.py:{ln}: {fn} can be console command #{n} with no wait in between; the console '
                   f'queue drops it when {L.CONSOLE_PENDING_MAX} are pending (0x55c426)')
            (dead if ref in DEAD_DEV_SCRIPTS or ref not in _referenced_script_refs(ctx) else bad).append(msg)
    for ln, fn, n in L.console_overflows(new_game_lines or [], senders):
        bad.append(f'menus/new_game.py:{ln}: {fn} can be console command #{n} with no wait in between')
    retarget = {(n, ch['index']): ch['value'] for n, chs in _dialog_retargets(ctx)['changes'].items() for ch in chs}
    for name, paths in sorted(_research_dialogs(ctx).items()):
        for i, opt in enumerate(e for e in C.decode_xmlb(paths['xmlb'].read_bytes()).iter()
                                if e.tag.lower() == 'option'):
            s = retarget.get((name, i), opt.get('script') or '')
            if '(' in s:
                for ln, fn, n in L.console_overflows(L.split_inline(s), senders):
                    bad.append(f'Dialogs/x1/{name} option {i}: {fn} is console command #{n} of one runscript')
    for m in bad:
        ctx.error(m)
    if dead:
        ctx.note(f'{len(dead)} console-queue overflows in XML1 scripts nothing references (XML1 dead code, '
                 f'allowlisted): {dead}')
    det['console_queue'] = {'errors': bad, 'dead_code': dead, 'senders': list(senders)}
    ctx.set_count('console_queue_overflows', len(bad))


def _blackbird_problems(args, api):
    """blackbirdMenu(a, code, b) sends 'setblackbirdparms %s %s %s FALSE FALSE' (xbe 0x9a3c7 / XML2 the same
    format): each token goes into a 64-byte buffer (0x5f2408), the command through the 127-char console
    queue, and `code` later runs as 'runscript <code>' (0x5e08d4)."""
    out = []
    if len(args) != 3 or any(v is None for v in args):
        return ['arguments are not three string literals']
    cmd = 'setblackbirdparms {} {} {} FALSE FALSE'.format(*args)
    if len(cmd) > L.CONSOLE_MAX:
        out.append(f'console command is {len(cmd)} chars (> {L.CONSOLE_MAX})')
    for t in args:
        if len(t) >= 64:
            out.append(f'token {t!r} >= 64 chars (0x5f2408)')
        if re.search(r'[\s;]', t):
            out.append(f'token {t!r} contains whitespace or ";"')
    code = args[1]
    out += L.console_problems(code)
    if '(' in code:
        out += [f'{kind}: {d}' for _, kind, d in L.lint_inline(code, api)[0]]
    return out


def _literal_calls(lines, api, names):
    """[(name, [literal values or None])] for calls to any of `names` (exact case) in lines."""
    _, info = L.lint_lines(lines, api)
    out = []
    for _, n, args in info['calls']:
        n = n[5:] if n.startswith('game.') else n
        if n in names:
            out.append((n, [L.literal_value(a) for a in args]))
    return out


def _install_scripts(ctx, det):
    installed, overwrote, skipped = [], [], []
    api = ctx.xml2_api
    lint_bad, lint_allowed = [], []
    fe_scripts = frontend_scripts(ctx)
    for ref, p in sorted(_research_scripts(ctx).items()):
        if ref in frontend_keep_xml2(ctx):
            skipped.append((ref, 'XML2 front end kept'))
            continue
        if ref in fe_scripts:
            skipped.append((ref, f'generated instead: {fe_scripts[ref]["why"]} (SPEC 21)'))
            continue
        if ref in FRONTEND_DEAD_X1:
            skipped.append((ref, "XML1's dead front end (not installed)"))
            continue
        if ref in NEW_GAME_REFS or ref.startswith(TOUR_PREFIX):
            ctx.error(f'research output contains {ref}, a path reserved for the New Game hook / testhooks')
            continue
        text, info = _script_text(ctx, ref)
        for prob in info.get('narrow_problems') or ():
            ctx.error(f'scripts/{ref}.py: packed-counter narrowing refused ({prob}); installed unnarrowed')
        ctx.write_script(C.script_rel(ref), text, source=p)
        installed.append(ref)
        if ctx.base_exists(C.script_rel(ref)):
            b = ctx.base_index.path(C.script_rel(ref)).read_bytes()
            same = C.to_crlf(b.decode('latin-1')).rstrip('\r\n') == C.to_crlf(text).rstrip('\r\n')
            overwrote.append((ref, 'identical' if same else 'differs'))
        probs, info = L.lint_script_bytes(C.to_crlf(text).encode('latin-1'), api)
        probs += L.roster_problems(C.to_crlf(text).split('\r\n'))               # T13 roster-flow rules
        for ln, kind, d in probs:
            (lint_allowed if ref in DEAD_DEV_SCRIPTS else lint_bad).append(f'scripts/{ref}.py:{ln}: {kind}: {d}')
    # zone-entry scripts generated by the act plan (x1/zones/<zone>: setCurrentAct [+ a copy of the zone script])
    for ref, gen in sorted(_generated_zone_scripts(ctx).items()):
        if ctx.base_exists(C.script_rel(ref)):
            ctx.error(f'generated zone-entry script scripts/{ref}.py would overwrite an XML2 base script')
            continue
        text, info = _script_text(ctx, ref)
        for prob in info.get('narrow_problems') or ():
            ctx.error(f'scripts/{ref}.py: packed-counter narrowing refused ({prob}); installed unnarrowed')
        ctx.write_script(C.script_rel(ref), text, source=f'xml1build.scripts:act_on_entry_plan ({gen["kind"]})')
        installed.append(ref)
        probs, _ = L.lint_script_bytes(C.to_crlf(text).encode('latin-1'), api)
        for ln, kind, d in probs:
            lint_bad.append(f'scripts/{ref}.py:{ln}: {kind}: {d}')
    # end scripts of XML1 data endSideMission sites (--forced-teams seat, SPEC 19)
    for ref, gen in sorted(_forced_generated_scripts(ctx).items()):
        if ctx.base_exists(C.script_rel(ref)) or ref in _installable_refs(ctx):
            ctx.error(f'generated forced-teams script scripts/{ref}.py would overwrite an existing script')
            continue
        text, info = _script_text(ctx, ref)
        ctx.write_script(C.script_rel(ref), text, source=f'xml1build.scripts:forced teams (end of {gen["side"]})')
        installed.append(ref)
        probs, _ = L.lint_script_bytes(C.to_crlf(text).encode('latin-1'), api)
        for ln, kind, d in probs:
            lint_bad.append(f'scripts/{ref}.py:{ln}: {kind}: {d}')
    # SPEC 21: the generated intro (--frontend xml1) and the end-of-campaign script
    for ref, gen in sorted(fe_scripts.items()):
        if ctx.base_exists(C.script_rel(ref)) and ref not in frontend_scripts_replacing_base(ctx):
            ctx.error(f'generated front-end script scripts/{ref}.py would overwrite an XML2 base script')
            continue
        text, _ = _script_text(ctx, ref)
        ctx.write_script(C.script_rel(ref), text, source=f'xml1build.scripts:{gen["why"]}')
        installed.append(ref)
        if ctx.base_exists(C.script_rel(ref)):
            overwrote.append((ref, 'differs'))
        probs, _ = L.lint_script_bytes(C.to_crlf(text).encode('latin-1'), api)
        for ln, kind, d in probs:
            lint_bad.append(f'scripts/{ref}.py:{ln}: {kind}: {d}')
        ctx.note(f'scripts/{ref}.py generated: {gen["why"]} ({len([l for l in gen["lines"] if not l.startswith("#")])} '
                 f'statements)')
    # SPEC 19: every xml2-fix call is behind its xml2fixFeature guard (validate V14b re-checks <out>)
    guard_bad = []
    if C.forced_teams_mode(ctx) == 'seat':
        for ref in installed:
            for ln, d in T.xml2fix_guard_problems(script_text(ctx, ref).split('\r\n')):
                guard_bad.append(f'scripts/{ref}.py:{ln}: {d}')
    for msg in guard_bad:
        ctx.error(f'forced teams: xml2-fix call outside its guard (it would run with ForcedTeams=0): {msg}')
    det['forced_guard_problems'] = guard_bad
    det['installed'] = len(installed)
    det['base_overwritten'] = overwrote
    det['frontend_skipped'] = skipped
    det['lint_allowlisted'] = lint_allowed
    det['lint_problems'] = lint_bad
    for msg in lint_bad:
        ctx.error(f'script line XMen2.exe would drop: {msg}')
    if lint_allowed:
        ctx.note(f'{len(lint_allowed)} droppable lines left in {len({m.split(":")[0] for m in lint_allowed})} '
                 f'unreferenced XML1 developer scripts (XML1 defects, allowlisted): '
                 + ', '.join(sorted({m.split(':')[0] for m in lint_allowed})))
    common_ow = [r for r, _ in overwrote if r.startswith('common/')]
    other_ow = [r for r, _ in overwrote if not r.startswith('common/') and r not in frontend_scripts_replacing_base(ctx)]
    ctx.note(f'{len(overwrote)} XML2 base scripts overwritten by their XML1 rewrites '
             f'({sum(1 for _, s in overwrote if s == "differs")} differ in content): '
             + ', '.join(f'{r} ({s})' for r, s in overwrote))
    if other_ow:
        ctx.warn(f'XML2 base scripts outside common/ overwritten: {other_ow}')
    for ref, why in skipped:
        ctx.note(f'scripts/{ref}.py not installed: {why}')
    ctx.set_count('scripts_installed', len(installed))
    ctx.set_count('common_overwritten', len(common_ow))
    ctx.set_count('base_scripts_overwritten', len(overwrote))
    ctx.set_count('frontend_skipped', len(skipped))
    ctx.set_count('lint_problems', len(lint_bad))
    ctx.set_count('lint_allowlisted', len(lint_allowed))
    return installed


def _new_game(ctx, det):
    """Scripts/menus/new_game.py + new_game_hard.py = body of x1/missions/begin_alison."""
    src = _research_scripts(ctx).get(NEW_GAME_BODY)
    if src is None:
        ctx.error(f'research output has no scripts/{NEW_GAME_BODY}.py; New Game hook not written')
        return []
    # the body as a menu-mode script: the hook keeps XML1's opening through xml2-fix [Game] NewGameTeam plus
    # loadMapKeepTeam (T8), not through the SPEC 19 seat block (design 3.2)
    body = _script_text(ctx, NEW_GAME_BODY, mode='menu')[0].split('\r\n')
    while body and not body[-1].strip():
        body.pop()
    body = [l for l in body if not l.startswith('# Generated by')]
    dropped = []                    # --no-movies: the intro movie start and its waitsignal
    dropped_keepteam = []           # keepteam: the cyclops unlock (he joins in nyc1_1_3)
    if ctx.opt('no_movies'):
        # --no-movies removes every .sfd: do not make New Game wait for a signal from a movie that is absent
        signals = set()
        keep = []
        for l in body:
            m = re.match(r'\s*startMovie\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"', l)
            if m:
                signals.add(m.group(2).lower())
                dropped.append(l.strip())
                continue
            m = re.match(r'\s*waitsignal\s*\(\s*"([^"]+)"', l)
            if m and m.group(1).lower() in signals:
                dropped.append(l.strip())
                continue
            keep.append(l)
        body = keep
    keepteam = str(ctx.opt('newgame') or 'chooseteam').lower() == 'keepteam'
    if keepteam:
        # XML1's exact opening (roster.md option C): xml2-fix seats Wolverine alone in startFirstMission and clears
        # resetgame's default unlocks, so the hook keeps that party and must not unlock Cyclops - he joins by
        # script in nyc1_1_3 (add_cyclops, T7).
        kept = []
        for l in body:
            if re.match(r'\s*unlockCharacter\s*\(\s*"cyclops"', l, re.I):
                dropped_keepteam.append(l.strip())
                continue
            kept.append(re.sub(r'\bloadMapChooseTeam\s*\(', 'loadMapKeepTeam(', l))
        body = kept
    else:
        # chooseteam: the player picks the opening party at the team menu, so the hook fixes no party (team lock 0)
        body = [l[:len(l) - len(l.lstrip())] + T.team_lock_line(0) if l.strip() == T.team_lock_line(1) else l for l in body]
    # plain comment text (no quotes / parentheses / semicolons), like BehavEd's own header line
    head = ['# xml1-port New Game hook - XMen2.exe startFirstMission runs this script at 0x4a7c42 and 0x4a7c57',
            '# after setting up its own four-hero roster',
            f'# body = Scripts/{NEW_GAME_BODY}.py - XML1 New Game runs beginmission alison at xbe 0x18d118']
    if keepteam:
        head.append('# keepteam - xml2-fix NewGameTeam seats Wolverine alone and Cyclops joins in nyc1_1_3 as in XML1')
    if dropped:
        head.append('# no-movies build - the intro movie start and its waitsignal were removed')
    lines = head + body
    probs, _ = L.lint_lines(lines, ctx.xml2_api)
    for ln, kind, d in probs:
        ctx.error(f'new_game.py line {ln}: {kind}: {d}')
    targets = [a[0] for n, a in _literal_calls(lines, ctx.xml2_api,
                                               {'loadMapKeepTeam', 'loadMapChooseTeam', 'loadZone'}) if a and a[0]]
    zones = set(ctx.x1_zones())
    if not targets:
        ctx.error('New Game hook body loads no zone (no loadMapKeepTeam/loadMapChooseTeam/loadZone)')
    for t in targets:
        if _zone_id(t) not in zones:
            ctx.error(f'New Game hook loads {t}, which is not an XML1 zone')
    written = []
    for ref in NEW_GAME_REFS:
        ctx.write_script(C.script_rel(ref), lines, source=src)
        written.append(ref)
    det['new_game'] = {'lines': lines, 'targets': targets, 'dropped_for_no_movies': dropped,
                       'dropped_for_keepteam': dropped_keepteam}
    ctx.note(f'menus/new_game.py and new_game_hard.py = {NEW_GAME_BODY} body ({len(body)} lines) -> '
             f'{", ".join(targets)}' + (f'; --no-movies: dropped {dropped}' if dropped else '') +
             (f'; keepteam: dropped {dropped_keepteam}' if dropped_keepteam else ''))
    if dropped:
        ctx.note('--no-movies: New Game skips the r102 intro movie (startMovie/waitsignal removed from the hook '
                 'only; a full build keeps them). Other mission scripts keep their startMovie + waitsignal pairs: '
                 'XMen2.exe startMovie (0x49f7e0) only stores the name/signal and sends "openmenu movie", so whether '
                 'the signal fires for a missing .sfd is an in-game question for --no-movies builds')
    return written


def _check_dialog(ctx, name, root, problems):
    """console / reference checks of one generated dialog's options."""
    api = ctx.xml2_api
    for i, opt in enumerate(e for e in root.iter() if e.tag.lower() == 'option'):
        s = opt.get('script')
        if not s:
            continue
        where = f'Dialogs/x1/{name} option {i} ({opt.get("text")!r})'
        for b in L.console_problems(s):
            problems.append(f'{where}: {b}')
        if '(' in s:
            probs, _ = L.lint_inline(s, api)
            problems += [f'{where}: {kind}: {d}' for _, kind, d in probs]
        elif not script_exists(ctx, s):
            problems.append(f'{where}: runs script {s}, which exists nowhere')


def _install_dialogs(ctx, det):
    dialogs = _research_dialogs(ctx)
    rt = _dialog_retargets(ctx)
    written, rewritten, problems = [], [], []
    for name, paths in dialogs.items():
        xb = paths['xmlb'].read_bytes()
        root = C.decode_xmlb(xb)
        attr_probs = C.xmlb_attr_problems(root)
        reenc = C.encode_xmlb(C.decode_xmlb(xb))
        changes = rt['changes'].get(name)
        if changes:
            opts = [e for e in root.iter() if e.tag.lower() == 'option']
            for ch in changes:
                opts[ch['index']].set('script', ch['value'])
                ctx.note(f"Dialogs/x1/{name} option {ch['text']!r}: script {ch['old']} (exists nowhere) -> "
                         f"{ch['value']} ({ch['evidence']})")
            written += ctx.write_xmlb(f'{DIALOG_DIR}/{name}', root, ('.XMLB', '.engb'), source=paths['xmlb'])
            rewritten.append(name)
        elif attr_probs or reenc != xb or len(xb) <= 8:
            ctx.warn(f'Dialogs/x1/{name}: research XMLB not canonical ({attr_probs[:2]}); re-encoded')
            written += ctx.write_xmlb(f'{DIALOG_DIR}/{name}', root, ('.XMLB', '.engb'), source=paths['xmlb'])
            rewritten.append(name)
        else:
            written.append(ctx.copy_file(paths['xmlb'], f'{DIALOG_DIR}/{name}.XMLB'))
            eb = paths['engb'].read_bytes() if paths['engb'] is not None else None
            if eb == xb:
                written.append(ctx.copy_file(paths['engb'], f'{DIALOG_DIR}/{name}.engb'))
            else:
                ctx.warn(f'Dialogs/x1/{name}: research engb missing or different from XMLB; engb written from XMLB')
                written += ctx.write_xmlb(f'{DIALOG_DIR}/{name}', root, ('.engb',), source=paths['xmlb'])
        _check_dialog(ctx, name, root, problems)
    for name, i, text, old in rt['unresolved']:
        ctx.error(f'Dialogs/x1/{name} option {i} ({text!r}) runs {old}, which exists nowhere, and no XML1 '
                  f'target could be derived: the dialog is installed unchanged and dead-ends progression')
    for p in problems:
        ctx.error(p)
    det['dialogs'] = {'count': len(dialogs), 'rewritten': rewritten, 'problems': problems,
                      'retargets': rt['changes'], 'unresolved': rt['unresolved']}
    ctx.set_count('dialogs_x1', len(dialogs))
    ctx.set_count('dialogs_retargeted', sum(len(v) for v in rt['changes'].values()))
    return written


def _install_missions(ctx, det):
    mdir = _out_dir(ctx) / 'data' / 'missions'
    files = sorted(p for p in mdir.iterdir() if p.suffix in ('.XMLB', '.engb')) if mdir.is_dir() else []
    if not files:
        ctx.error(f'research output has no mission files in {mdir}')
        return [], set()
    written, trees = [], {}
    for p in files:
        data = p.read_bytes()
        try:
            root = C.decode_xmlb(data)
        except Exception as e:      # noqa: BLE001
            ctx.error(f'{p.name}: does not decode ({e})')
            continue
        probs = C.xmlb_attr_problems(root)
        if probs or len(data) <= 8 or C.encode_xmlb(C.decode_xmlb(data)) != data:
            ctx.warn(f'Data/missions/{p.name}: research file not canonical ({probs[:2]}); re-encoded')
            written += ctx.write_xmlb(f'{MISSION_DIR}/{p.stem}', root, (p.suffix,), source=p)
        else:
            written.append(ctx.copy_file(p, f'{MISSION_DIR}/{p.name}'))
        trees[(p.stem.lower(), p.suffix.lower())] = root
    # structure checks against XMen2.exe's hard caps
    lst = trees.get(('missions', '.xmlb'))
    listed = [e.get('name') for e in lst if e.tag.upper() == 'MISSION'] if lst is not None else []
    if not listed:
        ctx.error('Data/missions/missions.XMLB lists no missions')
    if len(listed) > MAX_MISSION_FILES:
        ctx.error(f'missions.XMLB lists {len(listed)} missions (> {MAX_MISSION_FILES}, 0x48908a)')
    if ctx.base_exists('Data/missions/missions.engb'):
        ctx.error('the base install has Data/missions/missions.engb, which would shadow missions.XMLB')
    per_act, total, obj_names = collections.Counter(), 0, set()
    for m in listed:
        for ext in ('.xmlb', '.engb'):
            if (m.lower(), ext) not in trees:
                ctx.error(f'missions.XMLB lists {m} but research has no {m}{ext}')
        t = trees.get((m.lower(), '.engb')) or trees.get((m.lower(), '.xmlb'))
        if t is None:
            continue
        act = t.get('act')
        objs = [e for e in t if e.tag.upper() == 'OBJECTIVE']
        per_act[act] += len(objs)
        total += len(objs)
        obj_names |= {(e.get('name') or '').lower() for e in objs}
    for act, n in per_act.items():
        if n > MAX_OBJECTIVES_PER_ACT:
            ctx.error(f'act {act}: {n} objectives (> {MAX_OBJECTIVES_PER_ACT}, 0x4899e0)')
    if total > MAX_OBJECTIVES:
        ctx.error(f'{total} objectives in total (> {MAX_OBJECTIVES}, 0x4885c0)')
    base_missions = [C.split_ext(a)[0].rpartition('/')[2] for a in ctx.base_index.under('data/missions/')
                     if a.lower().endswith('.xmlb') and C.norm(a) != 'data/missions/missions.xmlb']
    ctx.note(f'Data/missions/missions.XMLB replaced: lists {listed} ({total} objectives, per act '
             f'{dict(sorted(per_act.items()))}); XML2\'s {len(base_missions)} act mission files stay on disk, unlisted')
    if any(a and a.isdigit() and int(a) > 5 for a in per_act):
        ctx.note('mission acts 6..9 are used (XML2 itself uses 1..5; in-game check: setCurrentAct 6..9)')
    det['missions'] = {'listed': listed, 'objectives': total, 'per_act': dict(per_act)}
    ctx.set_count('mission_files', len(files))
    ctx.set_count('objectives', total)
    return written, obj_names


def _x1_movie_names(ctx) -> set:
    """lowercase stems of the XML1 NTSC movies (xml1_xbox/movies/ntsc/<c1>/<c2>/*.sfd, or the prepared disc's
    movies.json when it was made without the files: media.x1_movie_files)."""
    def build():
        from . import media as M
        return {p.stem.lower() for p in M.x1_movie_files(ctx)}
    return _cached(ctx, 'x1_movies', build)


def _movie_clash_check(ctx, movies):
    """startMovie literals in installed scripts that name a movie both games ship (media installs the XML1 file
    as 'x' + name, SPEC 5.4): such a call would play XML2's movie. Only XML1's front end (not installed) uses
    the clashing i1xx names today."""
    base = {C.split_ext(a)[0].rpartition('/')[2].lower() for a in ctx.base_index.under('movies/')
            if a.lower().endswith('.sfd')}
    x1 = _x1_movie_names(ctx)
    clash = {m: sorted(r)[:3] for m, r in movies.items() if m in base and m in x1}
    for m, rs in sorted(clash.items()):
        ctx.error(f'startMovie("{m}") in {rs}: both XML1 and XML2 ship {m}.sfd; media installs the XML1 one as '
                  f'x{m}, so this call would play the XML2 movie')
    missing = {m: sorted(r)[:3] for m, r in movies.items() if m not in base and m not in x1}
    ctx.set_count('movie_names_referenced', len(movies))
    if missing:
        ctx.note(f'{len(missing)} startMovie names exist in neither XML1 nor XML2 (XML1 dead code/defects; validate V9 '
                 f'allowlists them): {missing}')


def _global_checks(ctx, det, installed, obj_names):
    """cross-checks of what was installed (reported; validate re-derives the same facts from <out>)."""
    api = ctx.xml2_api
    refs = _installable_refs(ctx)
    inst = set(installed)
    # --- literal uses in installed scripts
    flags, objectives, popups = set(), collections.defaultdict(set), collections.defaultdict(set)
    movies = collections.defaultdict(set)
    n_bb, dead_bb = 0, []
    for ref in sorted(inst):
        lines = script_text(ctx, ref).split('\r\n')
        for n, a in _literal_calls(lines, api, {'setGameFlag', 'getGameFlag', 'objective', 'createPopupDialogXml',
                                               'createPopupDialogXmlFilter', 'blackbirdMenu', 'startMovie'}):
            if n == 'startMovie':
                if a and a[0]:
                    movies[a[0].lower()].add(ref)
                continue
            if n == 'blackbirdMenu':
                n_bb += 1
                probs = _blackbird_problems(a, api)
                if len(a) == 3 and a[1] and '(' not in a[1] and not script_exists(ctx, a[1]):
                    probs.append(f'runs script {a[1]}, which exists nowhere')
                for p in probs:
                    msg = f'scripts/{ref}.py: blackbirdMenu{tuple(a)}: {p}'
                    if ref in DEAD_DEV_SCRIPTS or ref not in _referenced_script_refs(ctx):
                        dead_bb.append(msg)
                    else:
                        ctx.error(msg)
                continue
            if not a or a[0] is None:
                continue
            if n in ('setGameFlag', 'getGameFlag'):
                flags.add(a[0].lower())
            elif n == 'objective':
                objectives[a[0].lower()].add(ref)
            else:
                popups[a[0]].add(ref)
    ctx.set_count('blackbird_menus', n_bb)
    _movie_clash_check(ctx, movies)
    if dead_bb:
        ctx.note(f'{len(dead_bb)} blackbirdMenu problems in XML1 scripts nothing references (no zone bundle, mission, '
                 f'dialog, data or other script runs them; XML1 dead code): {dead_bb}')
    rw = _inline_map(ctx)
    for new in rw.values():
        if '(' in new:
            for m in re.finditer(r"(?:set|get)GameFlag\(\s*'([^']+)'", new):
                flags.add(m.group(1).lower())
    # inline rewrite values must be valid (they are pasted into data by zones)
    for old, new in rw.items():
        if '(' in new:
            probs, _ = L.lint_inline(new, api)
            for _, kind, d in probs:
                ctx.error(f'inline_rewrites.json value {new!r}: {kind}: {d}')
        elif not script_exists(ctx, new):
            ctx.error(f'inline_rewrites.json value {new!r} (for {old!r}) is a script that does not exist')
    x1_flags = sorted(flags - set(ENGINE_GAME_FLAGS))
    long_names = [f for f in x1_flags if len(f) > MAX_FLAG_NAME_LEN]
    if long_names:
        ctx.error(f'game flag names >= 12 chars (setter 0x4d7130 rejects them): {long_names}')
    if len(x1_flags) > MAX_GAME_FLAG_NAMES:
        ctx.error(f'{len(x1_flags)} distinct game flag names (> {MAX_GAME_FLAG_NAMES} free of 100)')
    ctx.set_count('game_flag_names', len(x1_flags))
    # objective names are matched case-insensitively (mission manager lookup 0x488d90 uses _stricmp 0x672562)
    missing_obj = {o: sorted(r)[:3] for o, r in objectives.items() if o not in obj_names}
    x1_obj = _xml1_objective_names(ctx)
    lost = {o: r for o, r in missing_obj.items() if o in x1_obj}
    x1_defect = {o: r for o, r in missing_obj.items() if o not in x1_obj}
    if lost:
        ctx.warn(f'{len(lost)} objective names used by scripts exist in XML1 mission files but in no x1_act '
                 f'file (objective() on them does nothing): {lost}')
    if x1_defect:
        ctx.note(f'{len(x1_defect)} objective names used by scripts exist in no XML1 mission file either '
                 f'(XML1 defect, objective() is a no-op in both games): {x1_defect}')
    popup_src = collections.Counter()
    for d, rs in sorted(popups.items()):
        if len(d) >= 64:
            ctx.error(f'createPopupDialogXml("{d}") path >= 64 chars (0x5ebc57)')
        src = dialog_source(ctx, d)
        popup_src[src or 'missing'] += 1
        if src is None:
            ctx.warn(f'createPopupDialogXml("{d}") in {sorted(rs)[:3]}: Dialogs/{_dialog_key(d)} exists nowhere '
                     '(missing on the XML1 disc too: that popup never showed in XML1 either)')
        elif src == 'xml1' and _dialog_key(d) not in _bundled_dialogs(ctx):
            ctx.warn(f'createPopupDialogXml("{d}") in {sorted(rs)[:3]}: XML1 dialog exists but no zone bundle lists '
                     'it, so the zones module will not import it')
    det['popup_dialog_sources'] = dict(popup_src)
    # --- helper refs (report) and zone extras
    try:
        helpers = _rjson(ctx, 'helper_refs.json')
    except FileNotFoundError:
        helpers = {}
    bad_helpers = [h for h in helpers if not script_exists(ctx, h)]
    for h in bad_helpers:
        ctx.error(f'helper script {h} (referenced by {helpers[h][:2]}) is not installed')
    ctx.set_count('helper_scripts', len(helpers))
    extras_total, extras_bad = 0, []
    for z, entries in _zone_extra(ctx).items():
        for e in entries:
            extras_total += 1
            ok = dialog_exists(ctx, e) if C.norm(e).startswith('dialogs/') else script_exists(ctx, e)
            if not ok:
                extras_bad.append((z, e))
    for z, e in extras_bad:
        ctx.error(f'zone_extra_files.json: {z} needs {e}, which is not installed')
    ctx.set_count('zone_extra_zones', len(_zone_extra(ctx)))
    ctx.set_count('zone_extra_entries', extras_total)
    ctx.set_count('inline_rewrites_available', len(rw))
    # --- zone scripts, acts and per-zone statement estimate
    how_count = collections.Counter()
    zone_rows, dead = {}, []
    over_pool = []
    for z in ctx.x1_zones():
        ref, how = _zone_script_choice(ctx, z)
        how_count[how.split(':')[0]] += 1
        if how.startswith('dead_ref:'):
            dead.append((z, how.split(':', 1)[1]))
        try:
            bundle = ctx.zone_bundle(z)
        except KeyError:
            bundle = []
        pkg_scripts = {C.script_ref(f) for f, k in bundle if (k or '').lower() == 'script'}
        pkg_scripts |= {C.script_ref(fn) for kind, fn in zone_package_extras(ctx, z) if kind == 'script'}
        if ref:
            pkg_scripts.add(ref)
        stmts = sum(_statement_count(ctx, r) for r in pkg_scripts if r in inst)
        zone_rows[z] = {'zonescript': ref, 'how': how, 'act': zone_act(ctx, z), 'package_scripts': len(pkg_scripts),
                        'statements': stmts}
        if stmts > STATEMENT_POOL:
            over_pool.append((z, stmts))
    if dead:
        ctx.note(f'{len(dead)} XML1 zones name a zone script that exists nowhere, on the XML1 disc too (no zone '
                 f'script is set; XML1 defect): {dead}')
    own = sorted(z for z, r in zone_rows.items() if r['how'] == 'own_name')
    if own:
        ctx.note(f'{len(own)} zones get their own-name script as zonescript (XML1 convention; not in '
                 f'zone_acts.json or dead world attribute): {own}')
    over_pool.sort(key=lambda t: -t[1])
    ctx.note(f'estimated statements per zone (zone script + packaged scripts, rewritten): '
             f'{len(over_pool)} zones above the {STATEMENT_POOL}-node pool (0x4d7e6e): {over_pool}; '
             f'largest: {sorted(((v["statements"], z) for z, v in zone_rows.items()), reverse=True)[:5]}')
    ctx.set_count('zones_over_statement_pool', len(over_pool))
    ctx.set_count('zones_with_zonescript', sum(1 for r in zone_rows.values() if r['zonescript']))
    det['zones'] = zone_rows
    det['zonescript_sources'] = dict(how_count)
    det['game_flags'] = x1_flags
    det['objectives_missing'] = missing_obj
    return zone_rows


def _act_plan_report(ctx, det):
    """report the act-on-entry plan (counts, deferred zones) and return the zones still without an entry act."""
    plan = act_on_entry_plan(ctx)
    rows = plan['zones']
    by = collections.Counter(r['status'] for r in rows.values())
    for k in ('x1_act_entry', 'inject', 'x1_act_wrapper'):
        ctx.set_count(f'act_entry_{k}', by.get(k, 0))
    deferred = {z: r for z, r in rows.items() if r['status'].startswith('deferred')}
    reach = {z for z, r in rows.items() if r.get('reachable')}
    unreach = sorted(z for z, r in rows.items() if r['status'] == 'unreachable_no_act')
    ctx.set_count('zones_no_act_on_entry', len(deferred) + len(unreach))
    ctx.set_count('zones_no_act_on_entry_reachable', len(deferred))
    if unreach:
        ctx.note(f'{len(unreach)} zones not reachable from New Game (graph.json) set no act on entry and are left as '
                 f'they are (their act is never needed in the campaign): {unreach}')
    ctx.set_count('zones_multi_act', sum(1 for r in rows.values() if r['status'] == 'deferred_multi_act'))
    changed = {z: (r['how'], r['entry_act'], r['script']) for z, r in sorted(rows.items()) if r['how']}
    ctx.note(f'act on zone entry: {len(changed)} more zones set their campaign act first thing '
             f'({by.get("x1_act_entry", 0)} generated x1/zones scripts, {by.get("inject", 0)} zone scripts injected '
             f'in place, {by.get("x1_act_wrapper", 0)} generated wrappers = act + a copy of a shared zone script): '
             f'{changed}')
    excl = plan['excluded_missions']
    ctx.note(f'act plan: {len(excl)} XML1 missions do not count as campaign acts: '
             f'{sorted(m for m, w in excl.items() if w.startswith("boss"))} (boss/demo/test) and '
             f'{sorted(m for m, w in excl.items() if not w.startswith("boss"))} (not started from New Game)')
    det['act_on_entry'] = {'zones': rows, 'excluded_missions': excl,
                           'generated': {r: {k: v for k, v in g.items() if k != 'lines'}
                                         for r, g in plan['generated'].items()}}
    return deferred, reach


def _defer(ctx, zone_rows, det=None):
    deferred, reach = _act_plan_report(ctx, det if det is not None else {})
    multi = sorted(z for z, r in deferred.items() if r['status'] == 'deferred_multi_act')
    noev = sorted(z for z, r in deferred.items() if r['status'] != 'deferred_multi_act')
    fh = forced_hero_missions(ctx)
    if C.forced_teams_mode(ctx) == 'seat':
        plan = forced_party_plan(ctx)
        ctx.defer(f'forced parties (SPEC 19): {len(fh)} XML1 missions force heroes; XML1\'s party is seated only '
                  f'with xml2-fix [Game] ForcedTeams=1 (the scripts\' else branch is the team menu). Unseatable (a '
                  f'seat name is not a herostat hero of this build): '
                  f'{sorted(m for m, r in plan.items() if r["status"] == "menu")}; cut zones (XML1 never shipped '
                  f'them): {sorted(m for m, r in plan.items() if r["forced"] and r["status"] == "cut")}. In-game '
                  f'checks: FORCED_TEAMS_DESIGN.md section 6')
        ctx.defer('addHero (XML1 party join mid-mission): xml2-fix joinHero (the spot saved, the hero added to the '
                  'saved party, the zone reloaded there - no team menu; [Game] JoinHero, on with ForcedTeams=1) and, '
                  'before it, xml2-fix addHero (the dormant 0x46c9f0) behind [Game] '
                  'AddHero=1, experimental; T7 (unlock + extractionPointChange team menu) stays the fallback')
        ctx.defer('side-mission return (T9): popParty returns to the pushing spot with the saved party (XML1 '
                  'endSideMission); without xml2-fix the team menu opens at the caller zone, as it does after a side '
                  'mission that is not seated')
    else:
        ctx.defer(f'forced per-mission heroes: {len(fh)} XML1 missions force heroes (REQUIREDHERO / maxheros < 4). '
                  f'--forced-teams menu: their starts use loadMapChooseTeam and the player picks the party (the '
                  f'default seat build seats XML1\'s party through xml2-fix, SPEC 19)')
        ctx.defer('addHero (XML1 party join mid-mission): emulated by unlock + team menu (T7)')
        ctx.defer('side-mission return point: endSideMission returns to the caller zone default start via '
                  "loadZone(zone,'') (jug_fb/dr_mag1 -> mansion/man2/subbasement2), not the exact position "
                  '(--forced-teams seat: xml2-fix popParty)')
    if str(ctx.opt('newgame') or 'chooseteam').lower() != 'keepteam':
        ctx.defer('New Game roster: XMen2.exe startFirstMission sets up magneto/cyclops/wolverine/storm (0x4a7b41-'
                  '0x4a7bef) while XML1 alison starts with Wolverine alone; --newgame chooseteam loads nyc1_1_1 with '
                  'loadMapChooseTeam (the default keepteam uses xml2-fix [Game] NewGameTeam)')
    ctx.defer('solo mode: 18 inline enterSoloMode and 4 exitSoloMode removed (debug no-op); may change '
              'astral/arbiter bridge puzzles')
    ctx.defer('conversation speaker markup (%X-TEAM%text vs %Name%: text) is not converted (the XML1-only speaker '
              'alias %ALISON% is: -> %MAGMA%, the stats entry default.xbe keyed it to; default.xbe labelled those '
              'lines "Alison" (string 503), the port\'s party-Magma lines say "Magma" - one key gives XMen2.exe both '
              'the label and the talk-animation entity, so only an engine alias could show "Alison" there; the NPC '
              'Alison\'s own lines use speaker entries labelled "Alison", SPEC 18.1)')
    ctx.defer(f'{len(deferred)} zones still set no act on entry ({sum(1 for z in deferred if z in reach)} reachable '
              f'from New Game): {len(multi)} are visited in several campaign acts {multi} (their act comes from the '
              f'mission start only, so it can be wrong after loading a save there; deriving it from the active '
              f'mission\'s game flags is left for later), {len(noev)} have no campaign act evidence {noev}')
    ctx.defer('XML1 mission-var lifetime: packed game flags are cleared at owning-mission start, single-zone '
              'counters are XML2 zone vars (cleared on every zone load); exact XML1 semantics need the optional '
              'exe patch at 0x49fe70 (clear zone vars only on directory change)')


def _forced_teams_report(ctx, det, installed):
    """SPEC 19: what the forced-team passes emitted (counts, notes); a planned block that is missing is an error."""
    mode = C.forced_teams_mode(ctx)
    plan = forced_party_plan(ctx)
    by = collections.Counter(r['status'] for r in plan.values())
    forced = {m: r for m, r in plan.items() if r['forced']}
    unseat = sorted(m for m, r in forced.items() if r['status'] == 'menu')
    cut = sorted(m for m, r in forced.items() if r['status'] == 'cut')
    ctx.set_count('forced_party_unseatable', len(unseat))
    ctx.set_count('forced_party_cut_zone', len(cut))
    ctx.set_count('forced_party_seat_missions', by.get('seat', 0))
    rep = {'mode': mode, 'plan': plan, 'unseatable': unseat, 'cut': cut}
    if mode != 'seat':
        for k in ('forced_party_seat_blocks', 'forced_party_skinset_blocks', 'side_push_sites', 'side_pop_sites',
                  'join_addhero_branches'):
            ctx.set_count(k, 0)
        ctx.note('--forced-teams menu: no xml2-fix call is emitted; forced-hero missions start with the team menu '
                 '(SPEC 12.6), side missions return with loadZone as the research wrote them')
        det['forced_teams'] = rep
        return
    blocks = collections.defaultdict(lambda: collections.Counter())      # mission -> Counter(kind)
    pushes, ends, join = collections.defaultdict(list), collections.defaultdict(list), []
    for ref in sorted(installed):
        _, info = _script_text(ctx, ref)
        for m, kind, _z in info.get('forced_party') or ():
            blocks[m][kind] += 1
        for s in info.get('side_push') or ():
            pushes[s].append(ref)
        for s, z, kind in info.get('side_end') or ():
            ends[s].append((ref, z, kind))
        for p in info.get('side_end_problems') or ():
            ctx.error(f'scripts/{ref}.py: forced teams: {p}')
        if info.get('join_hero'):
            join.append(ref)
    for m, r in sorted(plan.items()):
        ref = SIDE_BEGIN_REF.format(m)
        if ref not in _installable_refs(ctx):
            continue
        _, info = _script_text(ctx, ref)
        own = collections.Counter(k for mm, k, _ in info.get('forced_party') or () if mm == m)
        want = 'seat' if r['status'] == 'seat' else 'skinset'
        if own != collections.Counter({want: 1}):
            ctx.error(f'scripts/{ref}.py: forced teams: expected one {want} block for {m} ({r["status"]}), got '
                      f'{dict(own)}')
    for s, sp in sorted(_side_plan(ctx).items()):
        if sp['push'] and not pushes.get(s):
            ctx.error(f'forced teams: side mission {s} is seated but no begin site pushes the party')
        if sp['push'] and not any(k == 'pop' for _, _, k in ends.get(s, ())):
            ctx.error(f'forced teams: side mission {s} pushes the party but no end site pops it')
        if not sp['push'] and any(k == 'pop' for _, _, k in ends.get(s, ())):
            ctx.error(f'forced teams: side mission {s} pops a party it never pushed')
    n_seat = sum(c['seat'] for c in blocks.values())
    n_skin = sum(c['skinset'] for c in blocks.values())
    ctx.set_count('forced_party_seat_blocks', n_seat)
    ctx.set_count('forced_party_skinset_blocks', n_skin)
    ctx.set_count('side_push_sites', sum(len(v) for v in pushes.values()))
    ctx.set_count('side_pop_sites', sum(1 for v in ends.values() for _, _, k in v if k == 'pop'))
    ctx.set_count('join_addhero_branches', len(join))
    seat = {m: (r['seat'], f'{r["costume"]}:{r["heroes"]}', r['zone']) for m, r in sorted(forced.items())
            if r['status'] == 'seat'}
    ctx.note(f'forced teams (SPEC 19, --forced-teams seat): {len(seat)} of {len(forced)} forced missions seat XML1\'s '
             f'party behind xml2fixFeature("forcedteams") in {n_seat} starts (else branch: the team menu); '
             f'{n_skin} other starts set only the mission skinset; unseatable (team menu kept, a seat name is not '
             f'a herostat hero of this build): {unseat}; cut zones: {cut}; side missions push/pop: '
             f'{ {s: (pushes.get(s, []), [(r, k) for r, _, k in ends.get(s, [])]) for s in sorted(SIDE_MISSIONS)} }; '
             f'addHero / joinHero branches (+ T7 fallback) in {join}; parties: {seat}')
    rep.update(blocks={m: dict(c) for m, c in blocks.items()}, pushes=dict(pushes), ends=dict(ends), join=join)
    det['forced_teams'] = rep


def _transform_report(ctx, det, installed):
    """what scripts_transform changed in the installed scripts (counts, notes; problems are errors)."""
    fails = T.selftest()
    for f in fails:
        ctx.error(f'scripts_transform selftest: {f}')
    narrow = collections.Counter()
    narrowed_files = collections.defaultdict(list)
    zl, bb, ea, ct, acts, bl_all, bl_skip, unlocks = [], [], [], [], [], [], [], []
    for ref in sorted(installed):
        _, info = _script_text(ctx, ref)
        for k, v in (info.get('narrow') or {}).items():
            narrow[k] += v
            narrowed_files[k.split(':', 1)[1]].append(ref)
        zl += [(ref, o, nw) for o, nw in info.get('zone_literals') or ()]
        bb += [(ref, z) for z in info.get('blackbird') or ()]
        ea += [(ref, o, nw) for o, nw in info.get('mission_anims') or ()]
        ct += [(ref, m, l) for m, l in info.get('choose_team') or ()]
        if info.get('act_injected') is not None:
            acts.append((ref, info['act_injected']))
        bl_all += [(ref, a) for a, _ in info.get('bounded_loops') or ()]
        bl_skip += [(ref, a) for a, _ in info.get('bounded_loops_skipped') or ()]
        unlocks += [(ref, m, h) for m, h in info.get('mission_unlocks') or ()]
    # npc-loop fix report (scripts_transform.bound_unwakeable_loops; inline spawn code is counted by zones' notes)
    ctx.set_count('unwakeable_loops_bounded', len(bl_all))
    if bl_all:
        owners = _spawn_script_owners(ctx)
        ctx.note(f'{len(bl_all)} LOOP_WAKE spawn animations on non-combatant NPCs bounded to '
                 f'{T.UNWAKEABLE_LOOP_SECONDS:g} s then STOP (XMen2.exe ends a LOOP_WAKE only from its combat AI, '
                 f'which never runs for team none / willflee, and has no flee AI - AI fleedistance +0x470 is never '
                 f'read): ' + '; '.join(f'{r} ({a}; spawners: {sorted({z for z, _, _ in owners.get(r, ())})})'
                                       for r, a in bl_all))
    for r, a in bl_skip:
        ctx.warn(f'{r}: LOOP_WAKE {a} on a non-combatant NPC is not the last statement; left unbounded (the NPC '
                 f'will loop it forever)')
    unbounded = [(r, o) for r, o in owners_with_loop_wake(ctx) if not unwakeable_owner(ctx, r)]
    ctx.set_count('loop_wake_spawn_scripts_kept', len(unbounded))
    if unbounded:
        ctx.note(f'{len(unbounded)} LOOP_WAKE spawn scripts kept as XML1 wrote them (a combatant runs them, so the '
                 f'XMen2.exe AI wakes the loop): {unbounded}')
    ctx.set_count('mission_anim_enums_renamed', len(ea))
    ctx.set_count('mission_anim_scripts', len({r for r, _, _ in ea}))
    if ea:
        ctx.note(f'{len(ea)} XML1 EA_MISSIONn / combat-node "missionN" literals in {len({r for r, _, _ in ea})} '
                 f'scripts renamed to XML2\'s EA_ZONEn / "zoneN" (XMen2.exe has no ea_mission* enum; the XML1 '
                 f'mission_* anim DBs are renamed to match by characters): e.g. {sorted({(o, n) for _, o, n in ea})[:6]}')
    fh = forced_hero_missions(ctx)
    ctx.set_count('forced_hero_missions', len(fh))
    ctx.set_count('forced_hero_starts_choose_team', len(ct))
    missing_ct = sorted(m for m in fh if f'x1/missions/begin_{m}' in _installable_refs(ctx) and
                        not any(r == f'x1/missions/begin_{m}' for r, _, _ in ct) and
                        re.search(r'^\s*loadMapKeepTeam\(', _script_text(ctx, f'x1/missions/begin_{m}', 'menu')[0],
                                  re.M))
    for m in missing_ct:
        ctx.error(f'x1/missions/begin_{m}: forced-hero mission still loads with loadMapKeepTeam')
    _forced_teams_report(ctx, det, installed)
    ctx.note(f'{len(fh)} XML1 missions force their heroes (REQUIREDHERO or maxheros < {FORCED_HERO_MAX}); their '
             f'{len(ct)} loadMapKeepTeam starts in {len({r for r, _, _ in ct})} scripts (x1/missions/begin_* and '
             f'the inlined copies in briefings / zone scripts) now use loadMapChooseTeam so the player can pick a '
             f'matching party; blackbirdMenu starts already open the team menu: '
             f'{sorted(fh.items())}')
    ctx.set_count('act_on_entry_injected', len(acts))
    # XML1's mission-start unlocks (issue #55): every installed copy of every begin body unlocks its mission's
    # cumulative set once
    msu = mission_start_unlocks(ctx)
    for e in msu['errors']:
        ctx.error(f'mission-start unlocks: {e}')
    ul_map = msu['missions']
    ctx.set_count('mission_start_unlocks', len(unlocks))
    ctx.set_count('mission_start_unlock_missions', len(ul_map))
    no_begin = sorted(m for m in ul_map if SIDE_BEGIN_REF.format(m) not in _installable_refs(ctx))
    for ref in sorted(installed):
        text = _script_text(ctx, ref)[0] or ''
        probs, _ = T.unlock_problems(text.split('\r\n'), ul_map)
        for p in probs:
            ctx.error(f'scripts/{ref}.py: mission-start unlock: {p}')
        for p in T.menu_only_problems(text.split('\r\n'), menu_only_unlock_map(ctx)):
            ctx.error(f'scripts/{ref}.py: {p}')
    mo = sorted({(m, h) for ref in installed for m, h in _script_text(ctx, ref)[1].get('menu_only_unlocks') or ()})
    ctx.set_count('menu_only_unlocks', len(mo))
    ctx.note(f'issue #55: REQUIRED heroes XML1 only seats (their unlock moved into the team-menu branch of the seat '
             f'block): {dict(sorted(menu_only_unlock_map(ctx).items()))}')
    cu_plan = catchup_unlock_plan(ctx)
    cu_done = sorted(ref for ref in installed if _script_text(ctx, ref)[1].get('catchup_unlocks'))
    missing_cu = sorted(set(cu_plan['scripts']) - set(cu_done))
    for ref in missing_cu:
        if ref in installed:
            ctx.error(f'scripts/{ref}.py: zone-entry catch-up unlocks planned but not written')
    ctx.set_count('catchup_unlock_scripts', len(cu_done))
    ctx.note(f'issue #55 catch-up for saves in progress: {len(cu_done)} zone scripts unlock their zone\'s mission set '
             f'on entry / load ({len(cu_plan["zones"])} zones); skipped: {cu_plan["skipped"]}; planned for scripts '
             f'this module does not install: {[r for r in missing_cu if r not in installed]}')
    # SPEC 18: the scripts that address the renamed same-name NPCs (scripts_transform.NPC_DOUBLE_SCRIPTS)
    nd = {}
    for ref in sorted(T.NPC_DOUBLE_SCRIPTS):
        if ref not in installed:
            ctx.error(f'SPEC 18: {ref} (addresses the renamed NPCs of {T.NPC_DOUBLE_SCRIPTS[ref]}) is not installed')
            continue
        nd[ref] = _script_text(ctx, ref)[1].get('npc_double_refs', 0)
        if not nd[ref]:
            ctx.error(f'SPEC 18: scripts/{ref}.py names none of the renamed NPCs of {T.NPC_DOUBLE_SCRIPTS[ref]}')
    ctx.set_count('npc_double_refs', sum(nd.values()))
    ctx.note(f'SPEC 18 same-name NPCs renamed <hero>_x1double: {T.NPC_DOUBLE_SPAWNERS}; entity references rewritten: '
             f'{nd}')
    ctx.note(f'mission-start unlocks (issue #55: XML1\'s cumulative table, {msu.get("rows", 0)} rows of default.xbe, '
             f'at each missions.xml charunlock milestone): {len(ul_map)} missions, {len(unlocks)} unlock lines added '
             f'in {len({r for r, _, _ in unlocks})} scripts; XML1 rows that are no playable hero of this build: '
             f'{sorted({h for hs in msu["dropped"].values() for h in hs})}; missions without an installed begin '
             f'script (nothing starts them): {no_begin}')
    specs = _narrow_specs(ctx)
    for sp in specs:
        files = sorted(set(narrowed_files.get(sp.key, [])))
        ctx.note(f'packed counter {sp.key} ({sp.g} bits {sp.b}..{sp.b + sp.n - 1}) narrowed {sp.n} -> {sp.k} bits in '
                 f'{len(files)} scripts ({narrow.get("read:" + sp.key, 0)} reads, {narrow.get("write:" + sp.key, 0)} '
                 f'variable writes, {narrow.get("literal:" + sp.key, 0)} literal writes/clears): '
                 f'{NARROW_PACKED[sp.key][1]}')
    missing = sorted(set(NARROW_PACKED) - {sp.key for sp in specs})
    if missing:
        ctx.warn(f'NARROW_PACKED vars not narrowed (absent from var_storage.json or already narrow): {missing}')
    ctx.set_count('packed_vars_narrowed', len(specs))
    ctx.set_count('packed_blocks_narrowed', sum(narrow.values()))
    ctx.set_count('zone_literals_normalised', len(zl))
    if zl:
        ctx.note(f'{len(zl)} zone / cinematic path literals normalised to lowercase "/" (SPEC 4.1), '
                 f'{len({o for _, o, _ in zl})} distinct, e.g. {sorted({(o, nw) for _, o, nw in zl})[:6]}')
    mode = blackbird_mode(ctx)
    ctx.set_count('blackbird_to_choose_team', len(bb))
    if mode == 'chooseteam':
        ctx.note(f'--blackbird chooseteam: {len(bb)} blackbirdMenu(..., "loadMapKeepTeam(\'z\')", ...) calls replaced by '
                 f'loadMapChooseTeam("z") in {len({r for r, _ in bb})} scripts')
    else:
        ctx.note('blackbirdMenu calls kept (XML1 flow; XMen2.exe 0x4a0640 sends "setblackbirdparms <a> <code> <b> '
                 'FALSE FALSE" and opens the team menu like "opencharactersmenu" 0x5f1cd0; XML2 retail never calls '
                 'blackbirdMenu from a script). In-game check right after mansion1a: HAARP briefing -> team menu -> '
                 'haarp/ext/haarp_ext01 loads. Fallback if the menu never runs the stored code: rebuild with '
                 '--blackbird chooseteam (loadMapChooseTeam, as XML2\'s new_game_hard.py)')
    det['transforms'] = {'narrow': dict(narrow), 'narrowed_files': {k: sorted(set(v)) for k, v in narrowed_files.items()},
                         'zone_literals': zl, 'blackbird_mode': mode, 'blackbird_replaced': bb, 'selftest_fails': fails}


# ----------------------------------------------------------------------------------------------- run
def run(ctx):
    out_dir = _out_dir(ctx)
    if not (out_dir / 'scripts').is_dir():
        ctx.error(f'scripts research output missing: {out_dir / "scripts"}')
        return
    det = {}
    installed = _install_scripts(ctx, det)
    _transform_report(ctx, det, installed)
    ng = _new_game(ctx, det)
    ctx.shared['scripts_installed'] = set(installed) | set(ng)
    _install_dialogs(ctx, det)
    _, obj_names = _install_missions(ctx, det)
    zone_rows = _global_checks(ctx, det, installed, obj_names)
    _queue_check(ctx, det, installed, det.get('new_game', {}).get('lines'))
    _defer(ctx, zone_rows, det)
    det['counts'] = dict(ctx.report.mod(ctx.module)['counts'])
    ctx.write_meta('scripts_detail.json', det)
    ctx.log(f"{len(installed)} scripts, {det['dialogs']['count']} dialogs "
            f"({len(det['dialogs']['rewritten'])} rewritten), {len(det.get('missions', {}).get('listed', []))} "
            f"mission acts, New Game -> {', '.join(det.get('new_game', {}).get('targets', []))}")
