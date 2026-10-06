"""xml1build.validate - offline validation of the final <out> tree (SPEC.md section 5.6, checks V1..V11).

Runs last (after the sweep), reads only <out>, ctx.registry, the research files and ctx.args, and never writes
game files. Every fact is re-derived from the <out> files; ctx.shared is only cross-checked (mismatches are
warnings). Output:
  <out>/_build/validate.json   {checks: {id: {title, status, seconds, counts, errors, warnings, notes, allowed,
                                details}}, summary}
  ctx.error / ctx.warn         the first MAX_REPORTED findings per check (all of them are in the JSON)
  ctx counts                   files_checked, pkg_entries_checked, script_statements, sound_names,
                               sound_resolved, movies_missing (+ <id>_errors / <id>_warnings)

Checks (severity per SPEC 4.6: error = will not load or silently misbehaves; warn = degraded / unverified):
  V1 proxy      no xml2-fix proxy (dinput.dll, mods/, xml2-fix.*) in <out> (builder mode, C.builder_mode: allowed,
                never registered); XMen2.exe present and unpatched
  V2 registry   registered files exist with the recorded size, none is 0 bytes; ownership overrides (zones'
                forced re-imports of SPEC 4.4 trees are expected); no stale/missing files; replaced XML2 banks come
                from research/sound/out/merged; no XML2 movie or character asset replaced
  V3 xmlb       every registered XMLB-family file decodes, re-encodes byte-identically, attrs lowercase+sorted,
                > 8 bytes; no XMLB/engb pair where only one half was rewritten; localized XML1 .eng -> both halves
  V4 packages   every entry of every registered PKGB resolves; zone packages have zonexml/characters/boy/map;
                characters/zones packages carry no unmapped XML1 skin / anim DB / HUD / loading / style name
  V5 stats      herostat/npcstat caps and cross-references (XML1-origin = error, XML2-origin = warn); XML1-origin
                skin/characteranims/powerstyle equal the mapped XML1 values; a gun-armed XML1 entry has its gun's
                fighting style as its only one (SPEC 57, issue #52); every XML1-sourced data file is
                idempotent under C.map_attr (no unmapped reference); every XML1 character-namespace IGB exists under
                its mapped name with the in-IGB rename done
  V6 zones      per converted zone: CHRB/spawner names, world, zonescript, soundfile + banks, links, zoneinfo, owner
  V7 scripts    exact-case registration, argc, literal types, forbidden XML1 calls, CRLF, inline data code,
                runscript/blackbird console limits, game-flag/zone-var stores, per-zone engine pools, zone loads,
                popup dialogs and conversations
  V8 sounds     strict ZSND parse, no stereo in .zsm, the sound plan (incl. media's 22.05 kHz music), per-zone
                name resolution (simlookup) and coverage, char/ engine-event aliases
  V9 movies     startMovie targets, XML1 movie copies, subtitle pairs
  V10 new game  Scripts/menus/new_game(_hard).py exist, pass V7, and load an existing zone
  V11 tour      _tour.json stops consistent with their scripts, zones and packages
  V12 igb cache per converted zone: the IGB-cache records its package creates (distinct model names + motion-path
                files) against XMen2.exe's 200-record CIGBInfoCache2 (SPEC 13: > 149 cannot load with the New
                Game party = error, > 128 = warn); tile entries equal the tiles the zone's instances can name
  V14 forced teams (SPEC 19): xml2-fix calls only in --forced-teams seat builds (a) and only behind their
                xml2fixFeature guard (b); seat blocks = scripts.forced_party_plan with herostat heroes and existing
                zones (c); setSkinset costumes / heroes valid, one per begin body (d); pushParty / popParty paired per
                side mission, popParty last in its branch and alone in the console queue (e); addHero / joinHero
                only in the join scripts, after the join bit, before the T7 fallback, joinHero right after the NPC
                double's remove, last in its branch and alone in the console queue (f); unseatable / cut missions
                (g, warn); a join script's popup before the join with a waittimed after it, the join zone's
                script ending with the late removes of the NPC double (h, every build)
  V15 front end (SPEC 21, validate_frontend.py): --frontend xml1: XML1's menu/main_back converted, the MAIN_MENU
                file / renamed IGB / package and XMen2.exe's item-name contract, usecmd console commands, the intro,
                the XML1 menu music; --frontend xml2: the XML2 front-end files untouched
  V16 danger room (SPEC 21): the XML1 course table against XMen2.exe's loader limits and the build (arenas,
                spawner / hero names, rewards, reward items as equipment, exams, loadDangerRoomCourse literals)
  V17 review (SPEC 21): review_paths (caps, textures, movies, imageViewer literals, loading screens), codex,
                trivia, credits
  V18 combat events (SPEC 22, combat_events.v18): style triggers / events / handlers / affecters against XMen2.exe
  V19 npc values (SPEC 24, npc_values.v19): no style value code XMen2.exe reads as 0; the NPC energy talent and
                every XML1-origin npcstat entry's rank (= its mind)
  V20 automaps (SPEC 26, automaps.v20): a .zam and one last <zam> entry for every converted zone with an XML1
                automap texture (none elsewhere, no textures/automap entries); every zam parses as the loader
                reads it, keeps its vertices in their cells and fits the automap's 0x2000-vertex builder
  V21 skins     (SPEC 25, skins.validate): every XML1-origin stats skin (and costume) against its anim DB: weight /
                index counts equal, indices inside the blend palette, palette entries on skeleton bones, weights
                summing to 1 (errors); every bone the skin's vertices use in the anim DB skeleton (skin / skeleton
                mismatch: error, warning when the XML1 disc has it too); 1-2 blend weights noted
  V26 fall kill volumes (SPEC 52): XML1 map lethal-touch boxes have boxcollision=true and smartent=false
  V28 dialog platforms (SPEC 54, x1schema.dialog_platform_problems): every registered
                Dialogs/ file has, for each filter value, a variant XMen2.exe's platform test (0x4bd650) accepts -
                else the popup opens an empty panel (issue #50)
  V29 codex icons (SPEC 55, validate_frontend.v_codex_icons): --frontend xml1:
                UI/menus/codex (both halves) written by frontend, its MENU_ITEM_LISTCODEX without icons / icons_cols /
                icons_rows and no mini_convo_icons precache
  V30 personal items (SPEC 56, validate_frontend.v_personal_items): every personalItem literal has
                Data/personal/<item> from the first game (frontend), with text and a texture IGB in <out>
  V31 save positions (SPEC 61): shared_talents in the save-stable order of
                save_positions (new talents appended); no enabled fall kill volume numbered before another entinst
  V23 fight styles (SPEC 43, style_budget.validate): per converted zone the distinct style files of the permanent
                packages, the zone package, its CHRB characters' packages and the worst four-hero party against
                the registry the shipped ini asks xml2-fix for ([Limits] FightStyles, else XMen2.exe's 19): more
                is an error (the hero seated last has no powers), exactly full a warning
  V25 harm loops (SPEC 51): no delayed start-on ordinary harm loops that XML2 disables

Inherited defects. Many findings are defects of the XML1 disc itself (a zone, conversation, dialog, script or
sound bank XML1 references but never shipped; a line default.xbe already dropped). They are re-derived, not
allowlisted: a reference is an ERROR only when the target exists on the XML1 disc (or is generated by the build)
and is missing from <out>; when the XML1 disc lacks it too it is a WARNING marked 'inherited'. A dropped script
line is inherited only when the statement is verbatim XML1 text AND XML1's own table (research/scripts/
xml1_api.json) drops it as well; anything the rewrite generated is never inherited. Sound-name misses are split
the same way by resolving every name against the ORIGINAL Xbox banks (xml1_xbox/sounds/zsds).
"""
from __future__ import annotations

import collections
import functools
import hashlib
import json
import os
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import common as C
import xmlb                                   # noqa: E402  tools/xmlb.py
from .lib import x1names                      # noqa: E402  the XML1 namespace (was research/characters)
from .lib.x1names import is_fightstyle_name   # noqa: E402  fightstyle_* / x1_fightstyle_* (issue #52)
from . import validate_script as VS
from . import validate_sound as VSND
from . import x1schema as XS
from . import scripts_transform as ST      # section 18: the join zones' NPC double; V14 forced teams
from . import scripts_lint as L            # V14e: branch-aware console queue walk
from . import validate_frontend as VF      # V15-V17 (SPEC 21): front end, Danger Room, Review / codex / trivia / credits
from . import combat_events as CE        # V18 (SPEC 22): style triggers / events / FightMove handlers
from . import npc_values as NV           # V19 (SPEC 24): value codes XMen2.exe reads as 0, the NPC energy talent
from . import buoys as BY
from . import automaps as AM             # V20 (SPEC 26): XML1 automaps as .zam
from . import skins as SK                # V21 (SPEC 25): skin blend weights / skeleton against the anim DB
from . import style_budget as SB         # V23 (SPEC 43): the fighting / power style registry per zone
from . import weapons as W              # V5 (SPEC 57, issue #52): a gun-armed entry carries its gun's fighting style
from . import save_positions as SP      # V31: identities a save keeps by position

MAX_REPORTED = 50                             # per check and severity, into ctx.error / ctx.warn
CONTENT_OWNERS = tuple(C.MODULE_ORDER)        # characters, scripts, zones, media
X1_OWNERS = CONTENT_OWNERS + ('testhooks',)   # files that are "XML1 output"
KNOWN_OWNERS = X1_OWNERS + (C.BUILD_OWNER,)
EXPECTED_OVERRIDES = {('scripts', 'testhooks'), ('zones', 'testhooks')}   # testhooks may override (SPEC 5.5)
# SPEC 4.4: zones re-imports these XML1 trees with force=True (patched with map_tree_refs + rewrite_data_tree), so a
# shared import another module made first legitimately changes owner to zones
FORCE_PREFIXES = ('conversations/', 'dialogs/', 'subtitles/', 'data/entities/', 'motionpaths/')
XMLB_FAMILY = C.XMLB_FAMILY
PKG_KINDS = {'actorskin', 'actoranimdb', 'bigconvmap', 'boy', 'characters', 'combat_is', 'effect', 'fightstyle',
             'model', 'motionpath', 'nav', 'script', 'sound', 'texture', 'xml', 'xml_resident', 'xml_talents',
             'zam', 'zonexml'}        # every kind used by XML2's 2,261 packages (none other occurs)
ON_OFF_KINDS = {'combat_is', 'bigconvmap'}
# package kinds whose filename carries an XML1 character-namespace name (C.map_package_entry maps them)
NAMESPACE_KINDS = {'actorskin', 'actoranimdb', 'model', 'texture', 'fightstyle'}
# XML1 character-namespace IGB directories (characters module, SPEC 5.1.1)
X1_NAMESPACE_DIRS = ('actors/', 'hud/', 'ui/hud/characters/', 'ui/models/characters/', 'textures/loading/')
SCRIPT_ATTR_RE = re.compile(r'(script|scriptfile|scriptok|scriptcancel|scriptcommand)$')
INLINE_EXTRA_ATTRS = {'onactivate'}           # items.engb onactivate="restoreHealth(...)" (XML2 data)
# attributes whose name ends in 'script' but that hold a flag, not a script reference (XML1 data/entities
# missilelauncher_ents: launchedfromscript="true"); boolean-looking values are never script refs either
NOT_SCRIPT_REF_ATTRS = {'launchedfromscript'}
BOOL_VALUES = {'', 'true', 'false', '0', '1', 'none', 'null', 'yes', 'no'}
HERO_COSTUMES = {'astonishing', 'aoa', '60s', '70s', 'weaponx', 'future', 'winter', 'civilian'}  # 0x6d8aa0
ITEM_ATTRS_XML2 = ('name', 'displayname', 'description', 'model', 'cost', 'onactivate', 'activateonpickup', 'type',
                   'enemy_level', 'class', 'quality', 'heft', 'unique')   # attributes XML2 retail items use
                                                                          # (non-equipment + equipment)
STATS_CAP = 296                               # 0x44c1a7 cmp count,0x129 (index 0 unused)
HERO_COUNT = 21                               # 0x44bb13 cmp esi,0x15
TALENT_CAP = 99                               # 0x4c05d0 ids 0..98
NAME_MAX = 31                                 # strncpy 0x20 (0x4b9c40)
SOUNDFILE_MAX = 9                             # 0x5920cb: strlen >= 10 aborts zone sound loading
COVERAGE_MIN = 0.94                           # research baseline 94.8 % (misses absent from XML1 too)
CHAR_EVENTS = ('pain', 'death', 'jump', 'land')   # engine-built char/<sounddir>/<event> names (shared_sounds)
POPUP_PATH_MAX = 63                           # 0x5ebc57 createPopupDialogXml path < 64
MISSION_FILES_MAX = 25                        # 0x48908a cmp [0x72b56c],0x19
OBJECTIVES_MAX = 299                          # 0x4885c0 cmp idx,0x12b
OBJECTIVES_PER_ACT = 75                       # 0x4899e0 cmp [edi+0x7d78],0x4b
OBJECTIVE_FUNCS = ('objective', 'getObjective', 'immediateObjective', 'disallowResponseOnObjective')
# conversation speaker tokens: XMen2.exe's built-in ones (strings 0x685d18..0x685d5c + %BLANK%); any other %NAME%
# is looked up in the stats table (a miss gives index 0: no name / portrait, 0x44acc0 -> 0x44ad7e)
XML2_SPEAKER_TOKENS = {'%player%', '%x-team%', '%null%', '%end%', '%more%', '%continue%', '%blank%'}
XML1_SPEAKER_ALIASES = {'%alison%': 'magma'}        # default.xbe 0x61bc6 (the build rewrites it to %MAGMA%)
SPEAKER_ATTRS = ('text', 'textb')
SPEAKER_RE = re.compile(r'%[^%\s]+%')
# animation enums: XMen2.exe resolves 'EA_*' names (playanim / FightMove animenum) against its own enum strings
ANIM_ENUM_RE = re.compile(r'(?i)\bEA_[A-Z0-9_]+\b')
# enums XML1 data uses that XMen2.exe lacks and that belong to the powers rework (shared_nodes / fightstyles:
# flying carry and Juggernaut grab moves); reported as deferred warnings, not errors
DEFERRED_ANIM_ENUMS = re.compile(r'(?i)^ea_(flyingcarry_|jug_grab_)')
# zoneinfo attributes of XML2's Xtraction network (zones.XTRACTION_ATTRS; 0x468130 / 0x467f60)
XTRACTION_ATTRS = ('extraction', 'towncenter', 'mapx', 'mapy')

# ---- allowlists (named constants with reasons) ---------------------------------------------------------
# V4/V6/V7: references that are dead on the XML1 disc itself (research/sweep/aggregate.json refs.missing,
# 29 occurrences across the zone data); nothing can be converted for them. norm() stems without extension.
DEAD_ON_XML1_DISC = {
    'effects/weapons/smoke/trail',                        # loopfx
    'conversations/common/game/complete',                 # precache conversation
    'effects/powers/dangerrobot_forcefield_charge',       # precache fx
    'scripts/man1a/1_2_10_cam_start', 'scripts/man2/1_4_3_3_cam_start', 'scripts/man2/1_4_3_cam_start',
    'scripts/man2/1_4_9_cam_start', 'scripts/mansion/man1a/hangar', 'scripts/mansion/man3/2_1_12_5_cam_start',
    'scripts/mansion/man3/2_1_5_14_cam_start', 'scripts/nuke_plant/nuke/coolantvalves',
    'scripts/scripts/sewers/healer/2_9_4_cam_start', 'scripts/sewers/healer/2_9_4_cam_start',  # precache script
    'scripts/arb/a_int/welder', 'scripts/arbiter/a_int/chec_timer', 'scripts/astral/ast3/astral3_3',
    'scripts/astral/ast3/astral3_5', 'scripts/enable_flameguy_a_trigger', 'scripts/false', 'scripts/hive/h_int/2_2_1',
    'scripts/mocap/mocap1/brief_me', 'scripts/nyc/fb/secondsentinel', 'scripts/object_ambi/sewers/grso_slide_down',
    'scripts/release_flameguy_a', 'scripts/release_flameguy_c', 'scripts/sewers/grso/sewers_marrow',
    'scripts/sewers/hub/mor_talking01', 'scripts/sewers/hub/mor_talking02', 'scripts/sewers/hub/mor_talking03',
}
COMPUTER_SKIN = '21501'   # npcstat 'Computer': XML1 actors/7501.igb is 0 bytes, no actor written (SPEC 4.5/5.1)
# V6: prevzone values that point at zones XML1 itself never shipped (research/sweep/zones.json, 20 links);
# a player_start whose prevzone never matches is just never chosen.
KNOWN_UNRESOLVED_PREVZONE = {
    ('astral/ast1/astral4_3', 'astral4_2'), ('mansion/man2/subbasement2', 'hangar2'),
    ('mansion/man3/mansion3_1', 'mansion_back3'), ('mansion/man4/mansion4_1', 'mansion2'),
    ('mansion/man4/mansion4_1', 'mansion4_2a'), ('mansion/man4/subbasement4', 'hangar4'),
    ('mansion/man4/subbasement4', 'mansion4_2a'), ('mansion/man5/mansion5_1', 'mansion_back5'),
    ('mansion/man5/mansion_front5', 'mansion_back5'), ('mansion/man5/subbasement5', 'hangar5'),
    ('mansion/man6/mansion6_1', 'mansion_back6'), ('mansion/man6/mansion6_1', 'mansion_front6'),
    ('mansion/man6/subbasement6', 'hangar6'), ('mansion/man7/mansion7_1', 'mansion_front7'),
    ('mansion/man7/mansion7_1', 'mansion_back7'), ('mansion/man7/subbasement7', 'hangar7'),
    ('mansion/man8/mansion8_1', 'mansion_front8'), ('mansion/man8/mansion8_1', 'mansion_back8'),
}
# demo copy with a prevzone that matches 3 zones in different directories (zones.json 'ambiguous')
KNOWN_AMBIGUOUS_PREVZONE = {('demo/deck/arb_fd1', 'arb_fd2')}
# V7: the 14 lines XML1 itself already dropped, all in dead developer scripts (scripts research VERIFICATION:
# 7 unknown + 6 argc in missions/*_start.py + the mis-cased beginmissionhack in the uninstalled intro_demo)
KNOWN_DEAD_SCRIPT_FINDINGS = {
    ('missions/mansion_start', 'unknown function', 'begin'),
    ('missions/muirisland_start', 'unknown function', 'depart'), ('missions/muirisland_start', 'argc', 'startMovie'),
    ('missions/nuke_start', 'unknown function', 'depart'), ('missions/nuke_start', 'argc', 'startMovie'),
    ('missions/sewers_intro', 'unknown function', 'begin'), ('missions/sewers_intro', 'argc', 'startMovie'),
    ('missions/sewers_start', 'unknown function', 'depart'), ('missions/sewers_start', 'argc', 'startMovie'),
    ('missions/sewers_start', 'console queue', 'startMovie'),
    ('missions/testcollect_start', 'unknown function', 'depart'),
    ('missions/testcollect_start', 'argc', 'startMovie'),
    ('missions/wx_fb_start', 'unknown function', 'depart'),
    ('menus/intro_demo', 'wrong case', 'beginmissionhack'),
    ('missions/sentinels_attack_mansion', 'literal assignment', ''),   # unreferenced dev script
}
# V9: startMovie names in dead missions/*_start.py that never existed on the XML1 disc
KNOWN_MISSING_MOVIES = {'test1', 'test3', 'blackbird_leave_mansion'}
# V8: XML2 ships this bank malformed (track offset 0x01000000, last sample 68 bytes past EOF)
KNOWN_BAD_BANKS = {'sounds/eng/b/o/boss4_m.zsm'}
# V9: XML1 movies on the Xbox disc: xml1_xbox/movies/ntsc/<c1>/<c2>/<name>.sfd
X1_MOVIE_ROOT = 'movies/ntsc'


# ---------------------------------------------------------------------------------------------- helpers
def _ext(rel):
    return os.path.splitext(str(rel))[1].lower()


def _stem(rel):
    return os.path.splitext(C.norm(rel))[0]


def _canon(el):
    return (el.tag, tuple(sorted(el.attrib.items())), tuple(_canon(c) for c in el))


def _short(v, n=90):
    s = str(v)
    return s if len(s) <= n else s[:n] + '...'


def _is_skin(s):
    return bool(re.fullmatch(r'\d{4,5}', s or ''))


def _fold(p):
    return str(p).replace('\\', '/').casefold()


@functools.lru_cache(maxsize=8192)
def _realdir(d):
    return os.path.realpath(d)


class PathRoots:
    """Folders that absolute file paths (registry 'source' values) are tested against, the way the file system sees
    them: both sides as given (made absolute) AND with junctions / symlinks resolved, '/' separators, case folded.

    Why both: a build made from a git worktree whose gitignored input folders (xml1_loose, xml1_assets, xml1_xbox)
    are directory junctions to the main tree records its sources under the worktree path, while resolving gives the
    main tree's; comparing only one spelling (the old resolve()d roots vs the raw sources) made validate miss every
    XML1 source there and turn the inherited V7 man1a/1_2_37 disallowResponse warning into 36 errors. Now either
    spelling of a source matches either spelling of a root, so worktree and main-tree builds validate identically.
    A source's folder is resolved once per folder (cached); files themselves are never junctions."""

    def __init__(self, roots):
        keys = set()
        for r in roots:
            if r is None:
                continue
            a = os.path.abspath(str(r))
            keys.update(_fold(k).rstrip('/') + '/' for k in (a, _realdir(a)))
        self.keys = tuple(sorted(keys, key=len, reverse=True))

    def rel(self, path):
        """the path below a root (case folded, '/'), or None when it is not under any (or not an absolute path)."""
        if not path or not os.path.isabs(str(path)):
            return None
        a = os.path.abspath(str(path))
        head, tail = os.path.split(a)
        for cand in (_fold(a), _fold(_realdir(head)).rstrip('/') + '/' + tail.casefold()):
            for k in self.keys:
                if cand.startswith(k):
                    return cand[len(k):]
        return None

    def contains(self, path):
        return self.rel(path) is not None


def _script_ref(value):
    """script-file reference value -> norm ref ('Arbiter\\Foo.py' -> 'arbiter/foo')."""
    r = C.norm(value).strip()
    if r.startswith('scripts/'):
        r = r[len('scripts/'):]
    if r.endswith('.py'):
        r = r[:-3]
    return r


class Check:
    """One validator check's findings."""

    def __init__(self, cid, title):
        self.id, self.title = cid, title
        self.status = 'pending'
        self.errors, self.warnings, self.notes, self.allowed = [], [], [], []
        self.counts, self.details = {}, {}
        self.seconds = 0.0

    def error(self, m):
        self.errors.append(str(m))

    def warn(self, m):
        self.warnings.append(str(m))

    def note(self, m):
        self.notes.append(str(m))

    def allow(self, m, why):
        self.allowed.append(f'{m}  [allowlisted: {why}]')

    def count(self, k, n=1):
        self.counts[k] = self.counts.get(k, 0) + n

    def set(self, k, v):
        self.counts[k] = v

    def to_json(self):
        return {'title': self.title, 'status': self.status, 'seconds': round(self.seconds, 2),
                'counts': self.counts, 'errors': self.errors, 'warnings': self.warnings, 'notes': self.notes,
                'allowed': self.allowed, 'details': self.details}


class Scan:
    """Facts from one pass over every registered XMLB-family file (V3 reports; V4-V9 consume)."""

    def __init__(self):
        self.files = {}          # norm rel -> {rel, owner, ok, root, size, problems[]}
        self.pkg = {}            # norm rel -> [(kind, filename)]
        self.inline = {}         # norm rel -> [(tag, attr, value)]  (script attrs whose value contains '(')
        self.refs = {}           # norm rel -> [(tag, attr, value)]  (script attrs naming a script file)
        self.runscripts = {}     # norm rel -> [value]               (dialog <option script=...>)
        self.sounds = {}         # norm rel -> [sound names]
        self.twins = set()       # norm '.xmlb' rels byte-identical to their registered '.engb' (scanned once)
        self.unmapped = {}       # norm rel -> [(tag, attr, value, mapped)]: XML1-sourced values map_attr still changes
        self.x1_sourced = 0      # registered XMLB-family files converted from an XML1 source file
        self.unknown_classes = {}  # norm rel -> [(entity name, classname)] XMen2.exe does not register (0x461080)
        self.color_channels = {}   # norm rel (effects/) -> [(tag, name)] still carrying XML1 red/green/blue
        self.fall_kill_volumes = {}  # map rel -> [(name, missing XML2 flags, deferred, player-only state)]
        self.entinst_tail = {}       # map rel -> [message] (V31: an enabled fall volume numbered before others)
        self.items = {}            # norm rel (data/items.*) -> root
        self.inv_items = {}        # norm rel -> [inventoryitem values]
        self.turret_mount = {}     # norm rel -> [(entity name, missing flags)] remapped scan turrets not fixed-mount
        self.delayed_harm_loops = {}  # norm rel -> [(entity name, loop effect, firstact)]
        self.physics_scale = {}    # norm rel -> [(entity name, attribute, value)] XML1-scale object physics left
        self.speakers = {}         # norm rel (conversations/) -> [(attr, %TOKEN%)]
        self.anim_enums = {}       # norm rel -> [(tag, attr, enum literal)]  animenum values + EA_* in any value
        self.zoneinfo_xtraction = {}   # norm rel (data/zoneinfo.*) -> [(zone, [attrs])] Xtraction network entries
        self.dialog_platforms = {}     # norm rel (dialogs/) -> [(filter, [platforms])] groups with no PC variant


# ---------------------------------------------------------------------------------------------- validator
class Validator:
    def __init__(self, ctx):
        self.ctx = ctx
        self.reg = ctx.registry.entries
        self.idx = ctx.out_index
        self.no_movies = bool(ctx.opt('no_movies'))
        self.checker = VS.ScriptChecker(ctx.xml2_api)
        self.checks = {}
        self._scan = None
        self._scripts = {}
        self._stats = None
        self._zones = None
        self._banks = None
        self._x1stats = None
        self._weapon_fire_cache = {}    # powerstyle (lower) -> weapons.weapon_fire_left (SPEC 29.3)
        self._weapon_types = None
        self._zoneinfo = None
        self._zone_ids = None
        self._x1checker = None
        self._x1weapons = None
        self._obj_refs = collections.defaultdict(set)      # objective name -> files (XML1 code)
        self._act_refs = collections.defaultdict(set)      # setCurrentAct literal -> files (XML1 code)
        self._x1_zone_set = None
        self._x1banks = None
        self._tour_stops = None
        self._zs_provider = None
        self._x1_roots = PathRoots((ctx.x1_loose, ctx.x1_assets, ctx.x1_xbox))

    # ------------------------------------------------------------------ small helpers
    def exists(self, rel):
        return self.idx.get(rel) is not None

    def entry(self, rel):
        return self.reg.get(C.norm(rel))

    def is_x1(self, rel):
        e = self.entry(rel)
        return e is not None and e['owner'] in X1_OWNERS

    def read(self, rel):
        p = self.idx.path(rel)
        return p.read_bytes() if p is not None else None

    def tree(self, rel):
        data = self.read(rel)
        if data is None:
            return None
        try:
            return xmlb.decode(data)
        except Exception:        # noqa: BLE001 - reported by V3 for registered files
            return None

    def is_x1_source(self, source):
        """a registry 'source' that is an XML1 disc file (xml1_loose / xml1_assets / xml1_xbox), junctions or not
        (PathRoots)."""
        return self._x1_roots.contains(source)

    def dead_on_disc(self, stems):
        return any(s in DEAD_ON_XML1_DISC for s in stems)

    def zone_exists(self, z):
        return self.exists(f'maps/{z}.xmlb') or self.exists(f'maps/{z}.engb')

    @property
    def zone_ids(self):
        if self._zone_ids is None:
            ids = set()
            for k in self.idx.keys():
                if k.startswith('maps/') and k.endswith(('.xmlb', '.engb')) and not k.startswith('maps/package/'):
                    ids.add(k[len('maps/'):-5])
            self._zone_ids = ids
        return self._zone_ids

    def script(self, rel):
        """ScriptResult of an out script file (cached), None if absent."""
        n = C.norm(rel)
        if n not in self._scripts:
            data = self.read(n)
            self._scripts[n] = None if data is None else \
                self.checker.check_file_bytes(data, x1_output=self.is_x1(n))
        return self._scripts[n]

    def script_set(self):
        """norm rels of every script the build ships or a registered package lists -> set of listing pkgs."""
        rels = {n: set() for n in self.reg if n.endswith('.py')}
        for pn, ents in self.scan.pkg.items():
            for kind, fn in ents:
                if kind == 'script' and fn:
                    rels.setdefault(f'scripts/{_script_ref(fn)}.py', set()).add(pn)
        return rels

    def x1_script_exists(self, ref):
        return self.ctx.x1_path(f'scripts/{ref}.py') is not None

    @property
    def banks(self):
        if self._banks is None:
            self._banks = VSND.BankTable(self.ctx)
        return self._banks

    # ------------------------------------------------------------------ scan (one pass over registered XMLB)
    @property
    def scan(self):
        if self._scan is not None:
            return self._scan
        sc = Scan()
        digests = {}
        for n, e in sorted(self.reg.items()):
            if _ext(n) not in XMLB_FAMILY:
                continue
            f = {'rel': e['rel'], 'owner': e['owner'], 'ok': False, 'root': None, 'size': 0, 'problems': []}
            sc.files[n] = f
            p = self.idx.path(n)
            if p is None or not p.is_file():
                f['problems'].append('file missing')
                continue
            data = p.read_bytes()
            f['size'] = len(data)
            digests[n] = hashlib.sha1(data).digest()
            if len(data) <= 8:
                f['problems'].append(f'{len(data)} bytes: header-only / empty XMLB (xmlb.decode fails on it)')
                continue
            try:
                root = xmlb.decode(data)
            except Exception as ex:        # noqa: BLE001
                f['problems'].append(f'does not decode: {type(ex).__name__}: {ex}')
                continue
            f['root'] = root.tag
            try:
                if xmlb.encode(root) != data:
                    f['problems'].append('re-encode differs from the file (not written by encode_xmlb?)')
            except Exception as ex:        # noqa: BLE001
                f['problems'].append(f're-encode failed: {ex}')
            f['problems'] += C.xmlb_attr_problems(root)
            f['ok'] = not f['problems']
            if not n.endswith('.pkgb'):
                uc = XS.unknown_classes(root)
                if uc:
                    sc.unknown_classes[n] = uc
                if n.startswith('effects/'):
                    cc = XS.color_channel_elements(root)
                    if cc:
                        sc.color_channels[n] = cc
                volumes = XS.fall_kill_volumes(root, n)
                if volumes:
                    # player-only state: (listed in FALL_KILL_LEADER_ONLY, carries every leader flag,
                    # carries any leader flag)
                    sc.fall_kill_volumes[n] = [
                        (el.get('name'), [k for k, v in XS.FALL_KILL_FLAGS.items() if el.get(k) != v],
                         XS.fall_kill_volume_deferred(el, n),
                         (XS.fall_kill_volume_leader_only(el, n),
                          all(el.get(k) == v for k, v in XS.FALL_KILL_LEADER_FLAGS.items()),
                          any(el.get(k, '').lower() == 'true' for k in XS.FALL_KILL_LEADER_FLAGS)))
                        for el in volumes]
                    tail = XS.numbered_entinst_tail_problems(root, n)
                    if tail:
                        sc.entinst_tail[n] = tail
                if n in ('data/items.xmlb', 'data/items.engb'):
                    sc.items[n] = root
                inv = [el.get('inventoryitem') for el in root.iter() if el.get('inventoryitem')]
                if inv:
                    sc.inv_items[n] = inv
                tm = XS.turret_mount_problems(root)
                if tm:
                    sc.turret_mount[n] = tm
                loops = XS.delayed_harm_loops(root)
                if loops:
                    sc.delayed_harm_loops[n] = loops
                if n.startswith('dialogs/'):
                    dp = XS.dialog_platform_problems(root)
                    if dp:
                        sc.dialog_platforms[n] = dp
                if self.is_x1_source(e.get('source')):
                    ps = XS.physics_scale_problems(root)
                    if ps:
                        sc.physics_scale[n] = ps
                if n.startswith('conversations/'):
                    sp = [(k, t) for el in root.iter() for k in SPEAKER_ATTRS for t in SPEAKER_RE.findall(el.get(k) or '')]
                    if sp:
                        sc.speakers[n] = sp
                en = [(el.tag, k, t) for el in root.iter() for k, v in el.attrib.items()
                      if v and (k == 'animenum' or 'anim' in k or '(' in v)
                      for t in ([v.strip()] if k == 'animenum' else ANIM_ENUM_RE.findall(v))]
                if en:
                    sc.anim_enums[n] = en
                if n in ('data/zoneinfo.xmlb', 'data/zoneinfo.engb'):
                    sc.zoneinfo_xtraction[n] = [(z.get('name'), [k for k in XTRACTION_ATTRS if k in z.attrib])
                                                for z in root.iter('zone')
                                                if any(k in z.attrib for k in XTRACTION_ATTRS)]
            if n.endswith('.pkgb'):
                sc.pkg[n] = [(el.tag, el.get('filename')) for el in root]
                continue
            if self.is_x1_source(e.get('source')):
                # every XML1 character reference must already be in the XML2 namespace: C.map_attr is idempotent on
                # mapped values (5-digit skins, x1_ anim DBs / styles), so any value it still changes is unmapped
                sc.x1_sourced += 1
                bad = []
                for el in root.iter():
                    for k, v in el.attrib.items():
                        if v and C.map_attr(k, v) != v:
                            bad.append((el.tag, k, v, C.map_attr(k, v)))
                if bad:
                    sc.unmapped[n] = bad
            inl, refs, rs = [], [], []
            for el in root.iter():
                for k, v in el.attrib.items():
                    if not v:
                        continue
                    if el.tag == 'option' and k == 'script':
                        rs.append(v)
                    elif (SCRIPT_ATTR_RE.search(k) or k in INLINE_EXTRA_ATTRS) and k not in NOT_SCRIPT_REF_ATTRS:
                        if '(' in v:
                            inl.append((el.tag, k, v))
                        elif v.strip().lower() not in BOOL_VALUES:
                            refs.append((el.tag, k, v))
            if inl:
                sc.inline[n] = inl
            if refs:
                sc.refs[n] = refs
            if rs:
                sc.runscripts[n] = rs
            snd = VSND.names_from_tree(root)
            if snd:
                sc.sounds[n] = snd
        for n, dg in digests.items():
            if n.endswith('.xmlb') and digests.get(n[:-5] + '.engb') == dg:
                sc.twins.add(n)
        self._scan = sc
        return sc

    def data_items(self, table):
        """(norm rel, items) of a Scan table (inline / refs / runscripts), skipping .XMLB twins of an identical
        registered .engb so every data finding is reported once (the message names the .engb)."""
        return [(n, lst) for n, lst in sorted(table.items()) if n not in self.scan.twins]

    # ------------------------------------------------------------------ converted zones
    def converted_zones(self):
        if self._zones is not None:
            return self._zones
        zs = []
        for z in self.ctx.x1_zones():
            if z in C.frontend_zones(self.ctx):  # XML2 front end (--frontend xml2): never converted (V6 checks it)
                continue
            for ext in ('.xmlb', '.engb'):
                e = self.entry(f'maps/{z}{ext}')
                if e and (e['owner'] == 'zones' or 'zones' in e.get('history', [])):
                    zs.append(z)
                    break
        self._zones = zs
        return zs

    def zone_pkg(self, z):
        n = C.norm(f'packages/generated/maps/{z}.pkgb')
        if n in self.scan.pkg:
            return self.scan.pkg[n]
        t = self.tree(n)
        return [(el.tag, el.get('filename')) for el in t] if t is not None else None

    def zone_world(self, z):
        """(world attrib dict, {variant: world or None}) from Maps/<z>.engb (English) else .XMLB."""
        worlds = {}
        for ext in ('.engb', '.xmlb'):
            rel = f'maps/{z}{ext}'
            if self.exists(rel):
                t = self.tree(rel)
                worlds[ext] = (C.find_world(t) if t is not None else None, t)
        for ext in ('.engb', '.xmlb'):
            if ext in worlds and worlds[ext][0] is not None:
                return dict(worlds[ext][0].attrib), worlds
        return None, worlds

    # ------------------------------------------------------------------ stats
    def stats(self):
        """{'variants': {ext: {'herostat': [el], 'npcstat': [el]}}, 'by_name': {lower: (file, el_engb|el_xmlb)},
        'talents': {ext: [names]}}"""
        if self._stats is not None:
            return self._stats
        st = {'variants': {}, 'by_name': {}, 'talents': {}, 'errors': []}
        for ext in ('.engb', '.xmlb'):
            v = {}
            for f in ('herostat', 'npcstat'):
                t = self.tree(f'data/{f}{ext}')
                if t is None:
                    st['errors'].append(f'data/{f}{ext} missing or undecodable')
                    v[f] = []
                    continue
                v[f] = [el for el in t.iter('stats')]
            st['variants'][ext] = v
            t = self.tree(f'data/shared_talents{ext}')
            st['talents'][ext] = [el.get('name', '') for el in t.iter('talent')] if t is not None else None
        for ext in ('.xmlb', '.engb'):                      # engb (English) wins in by_name
            for f in ('herostat', 'npcstat'):
                for el in st['variants'][ext][f]:
                    st['by_name'][(el.get('name') or '').lower()] = (f, el)
        self._stats = st
        return st

    def stats_names(self):
        return set(self.stats()['by_name'])

    def x1_stats(self):
        """XML1 stats: lower name -> (file, element) from xml1 herostat.eng / npcstat.eng."""
        if self._x1stats is None:
            d = {}
            for f in ('herostat', 'npcstat'):
                try:
                    root = self.ctx.read_x1_xml(f'data/{f}.eng')
                except KeyError:
                    root = None
                if root is None:
                    continue
                for el in root.iter('stats'):
                    d[(el.get('name') or '').lower()] = (f, el)
            self._x1stats = d
        return self._x1stats

    def x1_weapons(self):
        """XML1 weapons: lower name -> {lower attr: value} from data/weapons/weapons.eng ({} when unreadable)."""
        if self._x1weapons is None:
            try:
                root = self.ctx.read_x1_xml('data/weapons/weapons.eng')
            except KeyError:
                root = None
            self._x1weapons = {} if root is None else {
                w.get('name').lower(): {k.lower(): v for k, v in w.attrib.items()}
                for w in root.iter() if w.tag.lower() == 'weapon' and w.get('name')}
        return self._x1weapons

    # ------------------------------------------------------------------ running / reporting
    def run_all(self):
        for cid, title, fn in (('V1', 'proxy', self.v1_proxy), ('V2', 'registry', self.v2_registry),
                               ('V3', 'xmlb', self.v3_xmlb), ('V4', 'packages', self.v4_packages),
                               ('V5', 'stats', self.v5_stats), ('V6', 'zones', self.v6_zones),
                               ('V7', 'scripts', self.v7_scripts), ('V8', 'sounds', self.v8_sounds),
                               ('V9', 'movies', self.v9_movies), ('V10', 'new game', self.v10_new_game),
                               ('V11', 'tour', self.v11_tour), ('V12', 'igb cache', self.v12_igb_cache),
                               ('V13', 'actor slots', self.v13_actor_slots),
                               ('V14', 'forced teams', self.v14_forced_teams),
                               ('V15', 'front end', lambda ck: VF.v15_front_end(self, ck)),
                               ('V16', 'danger room', lambda ck: VF.v16_danger_room(self, ck)),
                               ('V17', 'review', lambda ck: VF.v17_review(self, ck)),
                               ('V18', 'combat events', lambda ck: CE.v18(self, ck)),
                               ('V19', 'npc values', lambda ck: NV.v19(self, ck)),
                               ('V20', 'automaps', lambda ck: AM.v20(self, ck)),
                               ('V21', 'skins', lambda ck: SK.validate(self, ck)),
                               ('V22', 'buoys', lambda ck: BY.validate(self, ck)),
                               ('V23', 'fight styles', lambda ck: SB.validate(self, ck)),
                               ('V24', 'conversation portraits', self.conversation_portraits),
                               ('V25', 'harm loop startup', self.harm_loop_startup),
                               ('V26', 'fall kill volumes', self.fall_kill_volumes),
                               ('V27', 'voice lines', self.voice_lines),
                               ('V28', 'dialog platforms', self.dialog_platforms),
                               ('V29', 'codex icons', lambda ck: VF.v_codex_icons(self, ck)),
                               ('V30', 'personal items', lambda ck: VF.v_personal_items(self, ck)),
                               ('V31', 'save positions', self.save_positions)):
            ck = Check(cid, title)
            self.checks[cid] = ck
            t0 = time.time()
            self.ctx.log(f'{cid} {title} ...')
            try:
                fn(ck)
                if ck.status == 'pending':
                    ck.status = 'error' if ck.errors else ('warn' if ck.warnings else 'ok')
            except Exception as ex:        # noqa: BLE001 - one check crashing must not hide the others
                ck.status = 'crashed'
                ck.error(f'validator crashed: {type(ex).__name__}: {ex}')
                ck.details['traceback'] = traceback.format_exc()
            ck.seconds = time.time() - t0
            self.ctx.log(f'{cid} {ck.status}: {len(ck.errors)} errors, {len(ck.warnings)} warnings '
                         f'({ck.seconds:.1f}s)')
        if self._banks is not None:
            try:
                self._banks.save()
            except OSError as ex:
                self.ctx.note(f'sound cache not saved: {ex}')

    def report(self):
        ctx = self.ctx
        summary = {'errors': 0, 'warnings': 0, 'allowed': 0, 'status': {}}
        for cid, ck in self.checks.items():
            summary['errors'] += len(ck.errors)
            summary['warnings'] += len(ck.warnings)
            summary['allowed'] += len(ck.allowed)
            summary['status'][cid] = ck.status
            for m in ck.errors[:MAX_REPORTED]:
                ctx.error(f'{cid} {ck.title}: {m}')
            if len(ck.errors) > MAX_REPORTED:
                ctx.error(f'{cid} {ck.title}: ... {len(ck.errors) - MAX_REPORTED} more errors in _build/validate.json')
            for m in ck.warnings[:MAX_REPORTED]:
                ctx.warn(f'{cid} {ck.title}: {m}')
            if len(ck.warnings) > MAX_REPORTED:
                ctx.note(f'{cid} {ck.title}: ... {len(ck.warnings) - MAX_REPORTED} more warnings in _build/validate.json')
            ctx.set_count(f'{cid}_errors', len(ck.errors))
            ctx.set_count(f'{cid}_warnings', len(ck.warnings))
        spec_counts = {}
        for key, cid in (('files_checked', 'V3'), ('pkg_entries_checked', 'V4'), ('script_statements', 'V7'),
                         ('sound_names', 'V8'), ('sound_resolved', 'V8'), ('movies_missing', 'V9')):
            v = self.checks.get(cid).counts.get(key, 0) if cid in self.checks else 0
            spec_counts[key] = v
            ctx.set_count(key, v)
        summary['counts'] = spec_counts
        summary['result'] = 'FAIL' if summary['errors'] else 'PASS'
        doc = {'version': 1, 'out': ctx.out.as_posix(),
               'args': {k: getattr(ctx.args, k, None) for k in ('start_zone', 'tour', 'no_movies', 'only',
                                                                 'forced_teams', 'start_party', 'frontend')},
               'checks': {cid: ck.to_json() for cid, ck in self.checks.items()}, 'summary': summary}
        ctx.write_meta('validate.json', doc)
        ctx.note(f'validate: {summary["result"]}: {summary["errors"]} errors, {summary["warnings"]} warnings, '
                 f'{summary["allowed"]} allowlisted; details in _build/validate.json')
        return doc

    # ================================================================== V1 proxy
    def v1_proxy(self, ck):
        out = self.ctx.out
        for p in out.iterdir():
            if C.is_proxy_name(p.name):
                if C.builder_mode(self.ctx.args):
                    # builder mode (BUILDER_DESIGN.md F3): the launcher's / player's xml2-fix files stay in <out>
                    ck.allow(f'{p.name}: xml2-fix proxy file/dir in <out>', 'builder mode keeps the proxy files')
                else:
                    ck.error(f'{p.name}: xml2-fix proxy file/dir in <out> (never copied; the sweep should delete it)')
        base = PathRoots((self.ctx.base,))
        for n, e in self.reg.items():
            top = n.split('/', 1)[0]
            if C.is_proxy_name(top):
                ck.error(f'{e["rel"]}: registered file in proxy location (owner {e["owner"]})')
            below = base.rel(e.get('source'))
            if below is not None and C.is_proxy_name(below.split('/', 1)[0]):
                ck.error(f'{e["rel"]}: copied from the xml2-fix proxy ({e.get("source")})')
        exe_out, exe_base = out / 'XMen2.exe', self.ctx.base / 'XMen2.exe'
        if not exe_out.is_file():
            ck.error('XMen2.exe missing from <out>')
        elif exe_base.is_file() and exe_out.stat().st_size != exe_base.stat().st_size:
            ck.error('XMen2.exe differs in size from the base install (the build never patches the exe)')
        ck.set('root_entries', sum(1 for _ in out.iterdir()))

    # ================================================================== V2 registry
    def v2_registry(self, ck):
        ctx = self.ctx
        by_owner = collections.Counter()
        overwrote = collections.Counter()
        merged_root = ctx.research_path('sound/out/merged')
        base_bank_stems = {Path(k).stem for k in ctx.base_index.keys()
                           if k.startswith('sounds/eng/') and k.endswith(('.zsm', '.zss'))}
        # SPEC 21 A.4.4: with --frontend xml1, XML1's menu music replaces XML2's menu_a / menu_c (V15 checks them)
        fe_music = set(C.FRONTEND_MUSIC) if C.frontend_mode(ctx) == 'xml1' else set()
        for n, e in sorted(self.reg.items()):
            by_owner[e['owner']] += 1
            if e['owner'] not in KNOWN_OWNERS:
                ck.warn(f'{e["rel"]}: unknown owner {e["owner"]!r}')
            p = ctx.out / e['rel']
            if not p.is_file():
                ck.error(f'{e["rel"]}: registered by {e["owner"]} but missing from <out>')
                continue
            st = p.stat()
            if st.st_size != e.get('size'):
                ck.error(f'{e["rel"]}: size {st.st_size} != registered {e.get("size")} (changed after {e["owner"]} wrote it)')
            elif e.get('mtime') and abs(st.st_mtime - float(e['mtime'])) > 2.0:
                ck.warn(f'{e["rel"]}: mtime differs from the registry (rewritten outside the ctx writers?)')
            if e.get('overwrote_base'):
                overwrote[e['owner']] += 1
            ext = _ext(n)
            if st.st_size == 0:
                # 0-byte XML1 sources must be skipped or substituted (SPEC 4.5): an empty IGB / XMLB never loads
                (ck.error if ext in ('.igb',) + XMLB_FAMILY else ck.warn)(
                    f'{e["rel"]}: 0-byte file written by {e["owner"]} (source {e.get("source")})')
            for prev in e.get('history', []):
                ck.count('ownership_overrides')
                if (prev, e['owner']) in EXPECTED_OVERRIDES:
                    ck.note(f'{e["rel"]}: {prev} -> {e["owner"]}')
                elif e['owner'] == 'zones' and prev in CONTENT_OWNERS and e.get('shared') and \
                        n.startswith(FORCE_PREFIXES):
                    ck.count('forced_reimports')
                    ck.details.setdefault('forced_reimports', []).append(f'{e["rel"]}: {prev} -> zones')
                elif e['owner'] == 'heroes' and prev == 'characters':
                    # SPEC_heroes.md: heroes rewrites the characters outputs of the hero roster (npcstat,
                    # shared_talents, the 15 hero powerstyles, the hero-as-NPC packages)
                    ck.count('heroes_overrides')
                    ck.details.setdefault('heroes_overrides', []).append(e['rel'])
                else:
                    ck.warn(f'{e["rel"]}: owner changed {prev} -> {e["owner"]} (unexpected override)')
            # replaced XML2 sound banks must be the merged versions (XML2 entries win); SPEC 4.4 / 5.4
            if n.startswith('sounds/') and ext in ('.zsm', '.zss'):
                stem = Path(n).stem
                src = e.get('source') or ''
                if stem in fe_music and n.endswith('.zss'):
                    ck.count('frontend_music_banks')
                    ck.note(f'{e["rel"]}: XML1 menu music replaces XML2\'s bank (--frontend xml1, '
                            f'{C.FRONTEND_MUSIC[stem]})')
                elif stem in base_bank_stems or e.get('overwrote_base'):
                    if not src or not VSND.is_under(src, merged_root):
                        ck.error(f'{e["rel"]}: replaces/shadows XML2 bank {stem!r} but source is {src or "none"} '
                                 f'(must come from research/sound/out/merged)')
                    else:
                        ck.count('merged_banks')
            if ext == '.sfd' and e.get('overwrote_base'):
                ck.error(f'{e["rel"]}: an XML1 movie replaced XML2 movie (collisions must get the x prefix)')
            if e['owner'] == 'characters' and e.get('overwrote_base') and \
                    re.match(r'(actors|hud|ui/hud/characters|ui/models/characters|textures/loading)/', n):
                ck.error(f'{e["rel"]}: characters replaced an XML2 character asset (SPEC 5.1 forbids it)')
            if n.startswith('data/herostat.') and e['owner'] != 'heroes':
                ck.warn(f'{e["rel"]}: herostat rewritten by {e["owner"]} (only the heroes module owns it; SPEC_heroes.md)')
        if ck.counts.get('forced_reimports'):
            ck.note(f'{ck.counts["forced_reimports"]} shared XML1 imports under {FORCE_PREFIXES} were re-imported by '
                    f'zones with force=True (SPEC 4.4; list in details.forced_reimports)')
        for owner, k in sorted(by_owner.items()):
            ck.set(f'files_{owner}', k)
        for owner, k in sorted(overwrote.items()):
            ck.set(f'overwrote_base_{owner}', k)
            ck.note(f'{owner} replaced {k} XML2 base files')
        # base files missing from <out> / files that are neither base nor registered
        skip_sfd = self.no_movies
        missing = [a for k, a in ((k, ctx.base_index.get(k)) for k in ctx.base_index.keys())
                   if not (skip_sfd and k.endswith('.sfd')) and not self.exists(k)]
        for a in missing[:200]:
            ck.error(f'{a}: XML2 base file missing from <out>')
        if len(missing) > 200:
            ck.error(f'... {len(missing) - 200} more base files missing')
        stale = [a for k, a in ((k, self.idx.get(k)) for k in self.idx.keys())
                 if k not in self.reg and (k not in ctx.base_index or (skip_sfd and k.endswith('.sfd')))]
        # builder mode: a file the sweep could not delete (another program has it open; the builder's sweep lists
        # them in ctx.shared['sweep_kept']) is not part of the build - the builder names it (W_EXTRA_FILES)
        kept = {C.norm(r) for r in ctx.shared.get('sweep_kept') or ()} if C.builder_mode(ctx.args) else set()
        for a in [a for a in stale if C.norm(a) in kept]:
            ck.allow(f'{a}: neither an XML2 base file nor registered this build, and the sweep could not delete it',
                     'builder mode: the builder reports it (W_EXTRA_FILES)')
        stale = [a for a in stale if C.norm(a) not in kept]
        for a in stale[:200]:
            ck.error(f'{a}: neither an XML2 base file nor registered this build (stale; the sweep deletes these)')
        if len(stale) > 200:
            ck.error(f'... {len(stale) - 200} more stale files')
        ck.set('registered', len(self.reg))
        ck.set('base_missing', len(missing))
        ck.set('stale', len(stale))
        # cross-check the documented hand-over sets
        sh = ctx.shared.get('char_packages')
        if sh:
            miss = [p for p in sh if not self.exists(p)]
            for p in miss[:20]:
                ck.warn(f'ctx.shared char_packages lists {p} but it is not in <out>')

    # ================================================================== V3 xmlb
    def v3_xmlb(self, ck):
        sc = self.scan
        for n, f in sc.files.items():
            ck.count('files_checked')
            for p in f['problems']:
                ck.error(f'{f["rel"]}: {p}')
        # localized pairs: a rewritten .XMLB next to an untouched XML2 .engb (or vice versa) splits the file:
        # English reads .engb for localized files, so one half would still be XML2's content.
        for n, f in sc.files.items():
            stem, ext = os.path.splitext(n)
            other = {'.xmlb': '.engb', '.engb': '.xmlb'}.get(ext)
            if not other:
                continue
            o = stem + other
            if self.exists(o) and o not in self.reg:
                ck.error(f'{f["rel"]}: rewritten by {f["owner"]} but {self.idx.get(o)} is still the XML2 file '
                         f'(write both halves of a localized pair)')
                ck.count('pairs_split')
            src = (self.reg.get(n) or {}).get('source') or ''
            if self.is_x1_source(src) and src.lower().endswith('.eng') and o not in self.reg:
                # localized XML1 text (.eng) -> .XMLB + .engb (SPEC 4.2; English reads the .engb)
                ck.error(f'{f["rel"]}: converted from the localized XML1 {Path(src).name} but {o} was not written')
                ck.count('localized_half_missing')
        ck.set('xmlb_ok', sum(1 for f in sc.files.values() if f['ok']))
        # entity classes: XMen2.exe registers exactly 27 (0x461080); an unknown classname silently becomes the bare
        # 0x70-byte 'ent' (0x4611a0 falls back to 0x718444): no health, damage or deathscript (x1schema.CLASS_REMAP)
        for n, lst in sorted(sc.unknown_classes.items()):
            if n in sc.twins:
                continue
            for name, cls in lst:
                ck.error(f'{sc.files[n]["rel"]}: entity {name!r} classname={cls!r} is not an XMen2.exe entity class '
                         f'(becomes a bare ent: no health/damage/deathscript)')
                ck.count('unknown_entity_classes')
        # effect colours: XMen2.exe reads only startColor1/2, midColor1/2, endColor1/2 (0x681ca4..0x681cbc)
        for n, lst in sorted(sc.color_channels.items()):
            f = sc.files[n]
            if self.is_x1_source((self.reg.get(n) or {}).get('source')):
                ck.error(f'{f["rel"]}: {len(lst)} primitive(s) still use XML1 red/green/blue colour curves, which '
                         f'XMen2.exe never reads (x1schema.convert_effect_colors), e.g. {lst[:2]}')
                ck.count('effects_unconverted_colours')
        ck.set('effect_files_checked', sum(1 for n in sc.files if n.startswith('effects/')))
        # remapped XML1 scan turrets (physent + turretweapon) keep XML1's fixed mount (x1schema.TURRET_MOUNT_FLAGS):
        # a plain physent falls / is pushed / can be picked up once setNoClip(..., 'FALSE') runs, while the turret's
        # deathscript gates progression (haarp tank_destroyed, haarp3, hive turret_death)
        n_turrets = 0
        for n, lst in sorted(sc.turret_mount.items()):
            if n in sc.twins:
                continue
            for name, miss in lst:
                ck.error(f'{sc.files[n]["rel"]}: turret physent {name!r} lacks {miss}=true (XML1 scanturretent was a '
                         f'fixed mount; x1schema.TURRET_MOUNT_FLAGS)')
                n_turrets += 1
        ck.set('turrets_not_fixed_mount', n_turrets)
        # SPEC 59 (issue #51): XML1-sourced entity definitions carry XMen2.exe's object physics scales
        # (x1schema.convert_physics). An XML1 value above the engine's range means the conversion did not run, and
        # then every XML1 heaviness-1 object needs Might (0x427f60).
        n_scale = 0
        for n, lst in sorted(sc.physics_scale.items()):
            if n in sc.twins:
                continue
            ck.error(f'{sc.files[n]["rel"]}: {len(lst)} entity definition(s) keep XML1 object physics values '
                     f'XMen2.exe clamps (x1schema.convert_physics), e.g. {lst[:2]}')
            n_scale += len(lst)
        ck.set('x1_physics_scale_left', n_scale)

    def fall_kill_volumes(self, ck):
        """V26: converted fall kill volumes must be active collision boxes; the listed player-only
        volumes, and no others, carry the leader gate."""
        sc = self.scan
        for n, volumes in sorted(sc.fall_kill_volumes.items()):
            if n in sc.twins or not self.is_x1_source((self.reg.get(n) or {}).get('source')):
                continue
            ck.count('files_checked')
            for name, missing, deferred, (leader_listed, leader_set, leader_any) in volumes:
                if leader_listed and not deferred:
                    ck.count('volumes_player_only')
                    if not leader_set:
                        ck.error(f'{sc.files[n]["rel"]}: player-only fall kill volume {name!r} lacks '
                                 f'{", ".join(k + "=" + v for k, v in XS.FALL_KILL_LEADER_FLAGS.items())}'
                                 f' (it would kill AI followers again)')
                elif leader_any:
                    ck.error(f'{sc.files[n]["rel"]}: fall kill volume {name!r} carries the player-only gate '
                             f'but is not listed in x1schema.FALL_KILL_LEADER_ONLY')
                if deferred:
                    ck.count('volumes_deferred')
                    if 'smartent' not in missing:        # boxcollision alone is inert (SPEC 52) and one source
                        #                                   box carries it itself; smartent=false makes it live
                        ck.error(f'{sc.files[n]["rel"]}: deferred fall kill volume {name!r} was reactivated '
                                 f'before issue #5 party handling was validated')
                    else:
                        ck.allow(f'{sc.files[n]["rel"]}: fall kill volume {name!r} remains deferred',
                                 'issue #5: AI follows the player into this hazard')
                    continue
                ck.count('volumes_checked')
                if missing:
                    ck.error(f'{sc.files[n]["rel"]}: fall kill volume {name!r} lacks '
                             f'{", ".join(k + "=" + XS.FALL_KILL_FLAGS[k] for k in missing)}')

    def save_positions(self, ck):
        """V31 (SPEC 61): what a save names by position stays where earlier releases put it.
        (a) shared_talents (both halves) in save_positions.SHARED_TALENT_ORDER, new talents after it: a saved
        hero's talent id below 100 is the position. (b) no enabled fall kill volume numbered before another
        entinst (x1schema.numbered_entinst_tail_problems): a zone record finds an entity by its ordinal."""
        talents = self.stats()['talents']
        for ext in ('.engb', '.xmlb'):
            names = talents.get(ext)
            if names is None:
                ck.error(f'data/shared_talents{ext} missing or undecodable')
                continue
            errors, warnings = SP.shared_order_problems(names, f'data/shared_talents{ext}')
            for m in errors:
                ck.error(m)
            for m in warnings:
                ck.warn(m)
            ck.set(f'shared_talents{ext}_pinned', sum(1 for n in names if n.lower() in SP.SHARED_TALENT_SLOTS))
        if talents.get('.engb') and talents.get('.xmlb') and \
                [n.lower() for n in talents['.engb']] != [n.lower() for n in talents['.xmlb']]:
            ck.error('shared_talents XMLB and engb list their talents in different orders')
        sc = self.scan
        ck.set('zones_with_fall_volumes', len(sc.fall_kill_volumes))
        for n, msgs in sorted(sc.entinst_tail.items()):
            if n in sc.twins:
                continue
            for m in msgs:
                ck.error(m)

    def harm_loop_startup(self, ck):
        """V25 (SPEC 51): no dead ordinary harm loops."""
        sc = self.scan
        count = 0
        for n, loops in sorted(sc.delayed_harm_loops.items()):
            if n in sc.twins:
                continue
            for name, effect, delay in loops:
                ck.error(f'V25: {sc.files[n]["rel"]}: entity {name!r} has loopfx={effect!r}, '
                         f'loopfxstarton=true and firstact={delay!r}; the XML2 harm parser '
                         'clears the loop-on bit (invisible hazard)')
                count += 1
        ck.set('dead_harm_loops', count)

    def dialog_platforms(self, ck):
        """V28 (issue #50; SPEC 54): a popup dialog with only console variants (XML1's xbox / ps2 / gc) opens an empty
        panel on PC, so every registered Dialogs/ file needs an accepted variant per filter value."""
        sc = self.scan
        n_files = 0
        for n, f in sorted(sc.files.items()):
            if n.startswith('dialogs/') and f['root'] is not None and n not in sc.twins:
                n_files += 1
        ck.set('dialog_files_checked', n_files)
        for n, groups in self.data_items(sc.dialog_platforms):
            for flt, platforms in groups:
                ck.error(f'{sc.files[n]["rel"]}: no variant XMen2.exe accepts on PC'
                         f'{f" for filter {flt}" if flt else ""} (platforms {", ".join(platforms)}): '
                         f'the popup opens empty (x1schema.convert_dialog_platforms)')

    # ================================================================== V4 packages
    def v4_packages(self, ck):
        sc = self.scan
        zones = set(self.converted_zones())
        for n, entries in sorted(sc.pkg.items()):
            f = sc.files[n]
            if f['root'] != 'packagedef':
                ck.error(f'{f["rel"]}: root <{f["root"]}> is not <packagedef>')
            ck.count('packages_checked')
            if f['owner'] == 'characters':
                self._v4_style_package_target(ck, n, entries)
            seen = set()
            is_nc = n.endswith('_nc.pkgb') and n.startswith('packages/generated/characters/')
            x1_pkg = f['owner'] in ('characters', 'zones', 'testhooks')
            base_entries = self._base_pkg_entries(n) if x1_pkg else set()
            native_heads = self.native_conversation_heads(entries) if f['owner'] == 'zones' else set()
            for kind, fn in entries:
                ck.count('pkg_entries_checked')
                if kind not in PKG_KINDS:
                    ck.error(f'{f["rel"]}: unknown entry kind <{kind} filename="{fn}"> (XML2 uses {len(PKG_KINDS)} kinds)')
                    continue
                if not fn:
                    ck.error(f'{f["rel"]}: <{kind}> without filename')
                    continue
                if (kind, fn.lower()) in seen:
                    ck.count('duplicate_entries')
                seen.add((kind, fn.lower()))
                if (x1_pkg and kind in NAMESPACE_KINDS and (kind, C.norm(fn)) not in base_entries
                        and not (kind == 'model' and C.norm(fn) in native_heads)):
                    mapped = C.map_package_entry(kind, fn)[1]
                    cur = C.pkg_name(fn)
                    if kind in ('actorskin', 'actoranimdb') and cur.startswith('actors/'):
                        cur = cur[len('actors/'):]
                    if mapped != cur:
                        ck.error(f'{f["rel"]}: <{kind} filename="{fn}"> is an unmapped XML1 reference (XML2 namespace '
                                 f'name {mapped!r}; SPEC 3.5 map_package_entry)')
                        ck.count('unmapped_entries')
                if '\\' in fn:
                    ck.warn(f'{f["rel"]}: <{kind} filename="{fn}"> uses backslashes')
                if kind in ('actorskin', 'actoranimdb') and 'actors/' not in fn and fn.lower().startswith('actors/'):
                    ck.error(f'{f["rel"]}: <{kind} filename="{fn}">: the engine only recognises a lowercase '
                             f'"actors/" prefix (0x592520 strstr) and would load actors/{fn}.igb')
                if kind in ON_OFF_KINDS:
                    if fn.lower() not in ('on', 'off'):
                        ck.warn(f'{f["rel"]}: <{kind} filename="{fn}"> is not on/off')
                    continue
                if is_nc and kind == 'fightstyle' and fn.lower().startswith('data/powerstyles/'):
                    ck.warn(f'{f["rel"]}: _nc package lists powerstyle {fn} (none of XML2\'s 742 _nc packages do)')
                cands = C.package_entry_files(kind, fn)
                if cands is None:
                    ck.count('entries_no_file')
                    continue
                if any(self.exists(c) for c in cands):
                    continue
                stems = {_stem(c) for c in cands}
                if self.dead_on_disc(stems):
                    ck.allow(f'{f["rel"]}: <{kind} filename="{fn}"> unresolved', 'dead on the XML1 disc')
                elif kind == 'actorskin' and C.norm(fn).rsplit('/', 1)[-1] == COMPUTER_SKIN:
                    ck.allow(f'{f["rel"]}: <actorskin filename="{fn}"> unresolved', 'Computer: XML1 actors/7501.igb is empty')
                else:
                    ck.error(f'{f["rel"]}: <{kind} filename="{fn}"> resolves to none of {cands}')
                    ck.count('unresolved_entries')
        # zone packages: the loader needs zonexml / characters / boy and the map model
        for z in sorted(zones):
            ents = self.zone_pkg(z)
            if ents is None:
                ck.error(f'Packages/generated/maps/{z}.PKGB missing for converted zone {z}')
                continue
            kinds = collections.defaultdict(set)
            for kind, fn in ents:
                kinds[kind].add(C.norm(fn or ''))
            mz = f'maps/{z}'
            for k in ('zonexml', 'characters', 'boy'):
                if mz not in kinds.get(k, set()):
                    ck.error(f'{z}: zone package has no <{k} filename="{mz}">')
            if mz not in kinds.get('model', set()):
                ck.error(f'{z}: zone package has no <model filename="{mz}"> (the map geometry; XML2 zones all list it)')
            has_navb = self.exists(f'{mz}.navb')
            if has_navb and mz not in kinds.get('nav', set()):
                ck.warn(f'{z}: Maps/{z}.NAVB exists but the package has no <nav> entry')
            if 'combat_is' not in kinds:
                ck.warn(f'{z}: zone package has no <combat_is> flag (character _nc packages are chosen by it)')
            self._v4_styles_named_by_stats(ck, z, kinds.get('fightstyle', set()))
        self._v4_character_packages_name_the_style(ck, sc)

    def _zone_chr_powerstyles(self, z):
        """{lower powerstyle} of the zone's CHRB characters (herostat / npcstat entries)."""
        t = self.tree(f'maps/{z}.chrb')
        if t is None:
            return set()
        by = self.stats()['by_name']
        out = set()
        for c in t.iter('character'):
            e = by.get((c.get('name') or '').lower())
            if e is not None and (e[1].get('powerstyle') or '').strip():
                out.add(e[1].get('powerstyle').strip().lower())
        return out

    def _v4_styles_named_by_stats(self, ck, z, pkg_styles):
        """SPEC 29.1: a power style the engine loads on demand (named by a stats entry, listed by no package) breaks
        the party's power wheels (the third and fourth heroes seated had none in haarp_ext01 on 0.1.2). A zone
        package that lists a weapon-variant BASE style (x1_<base>_<weapon> exists among the stats powerstyles) while
        none of the zone's characters uses the base itself is the 0.1.2 shape of that: error."""
        used = self._zone_chr_powerstyles(z)
        all_ps = {(e[1].get('powerstyle') or '').strip().lower() for e in self.stats()['by_name'].values()}
        for fn in sorted(pkg_styles):
            if not fn.startswith('data/powerstyles/'):
                continue
            base = fn[len('data/powerstyles/'):]
            stem = base[3:] if base.startswith('x1_') else base
            variants = {v for v in used if v.startswith(f'x1_{stem}_') and v != base}
            if variants and base not in used:
                ck.error(f'{z}: zone package lists {fn} but the characters of the zone use its weapon variant(s) '
                         f'{sorted(variants)} - a style loaded outside the packages breaks the power wheels of the party '
                         f'(SPEC 29.1)')
            elif base not in used and base not in all_ps and any(v.startswith(f'x1_{stem}_') for v in all_ps):
                ck.warn(f'{z}: zone package lists {fn}, a base style no stats entry uses (its weapon variants exist)')

    def _v4_character_packages_name_the_style(self, ck, sc):
        """SPEC 29.1: every (non-_nc) character package of a stats entry that lists power styles lists the entry's
        own powerstyle - the engine must find the style in a package, not load it on demand."""
        by = self.stats()['by_name']
        for n, entries in sorted(sc.pkg.items()):
            m = re.fullmatch(r'packages/generated/characters/(.+)_(\d{4,5})\.pkgb', n)
            if not m:
                continue
            e = by.get(m.group(1).lower())
            if e is None:
                continue
            ps = (e[1].get('powerstyle') or '').strip().lower()
            listed = {C.norm(fn or '')[len('data/powerstyles/'):] for kind, fn in entries
                      if kind == 'fightstyle' and C.norm(fn or '').startswith('data/powerstyles/')}
            if ps and listed and ps not in listed:
                ck.error(f'{sc.files[n]["rel"]}: lists powerstyle(s) {sorted(listed)} but the stats entry '
                         f'{e[1].get("name")} uses {ps} - the engine would load it on demand, which breaks the '
                         f'power wheels of the party (SPEC 29.1)')

    @staticmethod
    def _v4_style_package_target(ck, rel, entries):
        """A generated style package must load the style its own filename advertises (SPEC 29.2)."""
        match = re.fullmatch(r'packages/generated/(powerstyles|fightstyles)/([^/]+)\.pkgb', C.norm(rel))
        if match is None:
            return
        target = f'data/{match[1]}/{match[2]}'
        listed = {C.norm(fn or '') for kind, fn in entries if kind.lower() in ('xml', 'xml_resident', 'fightstyle')}
        if target not in listed:
            ck.error(f'{rel}: style package does not load its own style {target} (SPEC 29.2)')
        ck.count('style_package_targets_checked')

    def _base_pkg_entries(self, n):
        """{(kind, norm filename)} of the XML2 package at the same path (empty when the base has none)."""
        if n not in self.ctx.base_index:
            return set()
        try:
            return {(el.tag, C.norm(el.get('filename') or '')) for el in self.ctx.read_base_xmlb(n)}
        except Exception:        # noqa: BLE001
            return set()

    # ================================================================== V5 stats
    def v5_stats(self, ck):
        st = self.stats()
        for m in st['errors']:
            ck.error(m)
        names_by_ext = {}
        for ext, v in st['variants'].items():
            hero = [(el.get('name') or '') for el in v['herostat']]
            npc = [(el.get('name') or '') for el in v['npcstat']]
            for fname, lst in (('herostat', hero), ('npcstat', npc)):
                dup = [k for k, c in collections.Counter(x.lower() for x in lst).items() if c > 1]
                for d in dup:
                    ck.error(f'data/{fname}{ext}: name {d!r} appears more than once (second registration ignored)')
                for x in lst:
                    if not x:
                        ck.error(f'data/{fname}{ext}: stats entry without a name')
                    elif len(x) > NAME_MAX:
                        ck.error(f'data/{fname}{ext}: name {x!r} longer than {NAME_MAX} chars (strncpy 0x20)')
            both = {x.lower() for x in hero} & {x.lower() for x in npc}
            for b in sorted(both):
                ck.error(f'{ext}: {b!r} is in herostat and npcstat (the npcstat entry is never registered)')
            active = [el for el in v['herostat'] + v['npcstat']
                      if (el.get('platform') or 'pc').lower() in ('pc', '')]
            uniq = {(el.get('name') or '').lower() for el in active}
            ck.set(f'stats_names{ext}', len(uniq))
            if len(uniq) > STATS_CAP:
                ck.error(f'{ext}: {len(uniq)} unique stats names > {STATS_CAP} slots (0x44c1a7); later names are silently skipped')
            hero_owner = (self.entry(f'data/herostat{ext}') or {}).get('owner')
            if hero_owner == 'heroes' and str(self.ctx.opt('hero_roster') or '21') != '21':
                if not 1 <= len(hero) <= HERO_COUNT:      # --hero-roster 17: fewer heroes is memory-safe (engine.md 1.5)
                    ck.error(f'data/herostat{ext}: {len(hero)} heroes, XMen2.exe maps at most {HERO_COUNT} (0x44bb13)')
            elif len(hero) != HERO_COUNT:
                ck.error(f'data/herostat{ext}: {len(hero)} heroes, XMen2.exe maps exactly {HERO_COUNT} (0x44bb13)')
            names_by_ext[ext] = ({x.lower() for x in hero}, {x.lower() for x in npc})
        if len(names_by_ext) == 2 and names_by_ext['.xmlb'] != names_by_ext['.engb']:
            h1, n1 = names_by_ext['.xmlb']
            h2, n2 = names_by_ext['.engb']
            ck.error(f'herostat/npcstat XMLB and engb list different names: only XMLB {sorted((h1 | n1) - (h2 | n2))[:10]}, '
                     f'only engb {sorted((h2 | n2) - (h1 | n1))[:10]}')
        talents = st['talents']
        for ext, t in talents.items():
            if t is None:
                ck.error(f'data/shared_talents{ext} missing or undecodable')
                continue
            ck.set(f'shared_talents{ext}', len(t))
            if len(t) > TALENT_CAP:
                ck.error(f'data/shared_talents{ext}: {len(t)} talents > {TALENT_CAP} (ids 0..98, 0x4c05d0); extras dropped')
        if talents.get('.xmlb') is not None and talents.get('.engb') is not None and \
                {x.lower() for x in talents['.xmlb']} != {x.lower() for x in talents['.engb']}:
            ck.error('shared_talents XMLB and engb define different talents')
        shared_t = {x.lower() for t in talents.values() if t for x in t}
        # names XMen2.exe references as strings (research/characters/x2_stats_refs.json in_exe)
        names = self.stats_names()
        try:
            refs = self.ctx.research_json('characters/x2_stats_refs.json')
            exe_names = sorted({r['name'].lower() for r in refs if r.get('in_exe')})
            exe_names += [f'_hero{i}_mc_' for i in range(1, 5)]
        except (OSError, ValueError, KeyError):
            exe_names = []
            ck.warn('research/characters/x2_stats_refs.json unreadable: keep-list not checked')
        # with the XML1 roster (herostat owned by heroes) XML2's own hero names are gone by design: the exe uses
        # them only in resetgame's default-unlock list, builddefaultteam and the danger-room defaults, where an
        # unknown name is a no-op (engine.md 2.2 / 2.3); startFirstMission's four names are covered by V-H10
        x2_hero_names = set()
        if (self.entry('data/herostat.engb') or {}).get('owner') == 'heroes':
            try:
                x2_hero_names = {(r['name'] or '').lower() for r in refs if r.get('file') == 'herostat'}
            except (NameError, KeyError, TypeError):
                x2_hero_names = set()
        for nm in exe_names:
            if nm not in names:
                if nm in x2_hero_names:
                    ck.note(f'XML2 hero {nm!r} is named by XMen2.exe (unlock / default-team lists) but not in the XML1 '
                            f'roster: those uses are no-ops for an unknown name (engine.md 2.2)')
                else:
                    ck.error(f'stats name {nm!r} is referenced by XMen2.exe / XML2 maps but missing from herostat+npcstat')
        # per-entry cross references
        base = {}
        for f in ('herostat', 'npcstat'):
            try:
                for el in self.ctx.read_base_xmlb(f'Data/{f}.engb').iter('stats'):
                    base[(el.get('name') or '').lower()] = _canon(el)
            except (KeyError, ValueError):
                pass
        x1 = self.x1_stats()
        hero_talent_files = {}
        origins = collections.Counter()
        xmlb_by = {(el.get('name') or '').lower(): el for f in ('herostat', 'npcstat')
                   for el in st['variants'].get('.xmlb', {}).get(f, [])}
        shared_stats = self.ctx.shared.get('stats') or {}
        for name, (fname, el) in sorted(st['by_name'].items()):
            if name in base and _canon(el) == base[name]:
                derived = 'xml2'
            elif name in x1 and fname == 'npcstat' and name not in base:
                derived = 'xml1'
            elif name in x1 and fname == 'npcstat' and self._matches_x1(el, x1[name][1]):
                derived = 'xml1'                         # XML1 wins on the same name (beast, profx, forge, ...)
            else:
                derived = 'xml2_modified'
            sh = shared_stats.get(name)
            origin = derived
            if sh and sh.get('origin'):
                origin = 'xml1' if str(sh['origin']).startswith('xml1') else derived
                if (origin == 'xml1') != (derived == 'xml1'):
                    ck.note(f'{name}: ctx.shared origin {sh.get("origin")!r}, derived from <out> {derived!r}')
            origins[origin] += 1
            if origin == 'xml1':
                for m in self._namespace_problems(el, x1[name][1] if name in x1 else None):
                    ck.error(f'{fname}:{el.get("name")} (xml1): namespace: {m}')
                # V5 (SPEC 57, issue #52): a gun-armed entry carries its gun's fighting style instead of its own
                wname = (x1[name][1].get('weapon') or '').strip().lower() if name in x1 else ''
                if wname:
                    fs = [t.get('name') or '' for t in el if t.tag == 'talent'
                          and is_fightstyle_name(t.get('name'))]
                    for m in W.fightstyle_problems(fs, self.x1_weapons().get(wname), C.map_fightstyle):
                        ck.error(f'{fname}:{el.get("name")} (xml1): fighting style: {m}')
                    if W.gun_fightstyle(self.x1_weapons().get(wname)):
                        ck.count('gun_entries_with_weapon_fightstyle')
            xe = xmlb_by.get(name)
            if xe is not None:
                for a in ('skin', 'characteranims', 'powerstyle', 'sounddir', 'moveset1'):
                    if (xe.get(a) or '') != (el.get(a) or ''):
                        ck.error(f'{fname}:{name}: {a} differs between XMLB ({xe.get(a)!r}) and engb ({el.get(a)!r})')
            for p in self._entry_problems(name, fname, el, shared_t, hero_talent_files):
                msg = f'{fname}:{el.get("name")} ({origin}): {p[1]}'
                if p[0] == 'allow':
                    ck.allow(msg, p[2])
                elif p[0] == 'warn':
                    ck.warn(msg)
                elif p[0] == 'hard' or origin == 'xml1':
                    ck.error(msg)
                else:
                    ck.warn(msg)
        for k, v in origins.items():
            ck.set(f'origin_{k}', v)
        sh_names = self.ctx.shared.get('stats_names')
        if sh_names is not None and {x.lower() for x in sh_names} != names:
            ck.warn(f'ctx.shared stats_names ({len(sh_names)}) differs from <out> herostat+npcstat ({len(names)})')
        # every XML1-sourced data file: character references in the XML2 namespace (skin +14000, x1_ anim DBs
        # and powerstyles, HUD/UI/loading paths); SPEC hard constraint "every reference must be rewritten"
        sc = self.scan
        ck.set('x1_sourced_files', sc.x1_sourced)
        n_bad = 0
        for n, bad in sorted(sc.unmapped.items()):
            if n in sc.twins:
                continue
            for tag, attr, v, mapped in bad:
                n_bad += 1
                ck.error(f'{sc.files[n]["rel"]}: <{tag} {attr}="{v}"> is an unmapped XML1 reference (the XML2 '
                         f'namespace name is {mapped!r}; XML2 would load its own same-named asset or nothing)')
        ck.set('unmapped_x1_refs', n_bad)
        self._x1_namespace_files(ck)

    def _x1_namespace_files(self, ck):
        """SPEC 5.1.1: every non-empty XML1 character-namespace IGB exists in <out> under its mapped name (numeric
        actors / HUD heads / UI character models / numeric loading screens +14000, clashing anim DBs x1_), and
        a renamed skin IGB carries the new '<id>', '<id>_outline', '<id>_skel' strings (x1names.igb_rename: the
        engine finds the skin and its cel outline by those names, 0x5775b0 / 0x4ea590)."""
        ctx = self.ctx
        jobs = []
        for rel in ctx.x1_rels(''):
            if not rel.endswith('.igb') or not rel.startswith(X1_NAMESPACE_DIRS):
                continue
            stem = rel[:-4]
            name = stem.rpartition('/')[2]
            numeric = False
            if rel.startswith('actors/'):
                if x1names.shares_xml2_animdb(name):
                    ck.count('x1_animdb_shared_xml2')          # common / fightstyle_* / moveset_*: XML2's used
                    continue
                mapped, numeric = C.map_actor_path(stem), bool(re.fullmatch(r'\d{4}', name))
            elif rel.startswith('textures/loading/'):
                if not re.fullmatch(r'\d{4}', name):
                    continue                                   # named loading screens are zone assets
                mapped, numeric = C.map_loading_texture(stem), True
            elif re.fullmatch(r'(hud_head_)?\d{4}', name):
                mapped, numeric = C.map_ui_path(stem), True
            else:
                continue
            if ctx.x1_is_empty(rel):
                ck.count('x1_namespace_empty')                 # actors/7501.igb (Computer), SPEC 4.5
                continue
            jobs.append((rel, mapped, numeric, name[-4:] if numeric else None))

        def one(job):
            rel, mapped, numeric, old = job
            out_rel = mapped + '.igb'
            p = self.idx.path(out_rel)
            if p is None:
                return ('error', f'XML1 {rel} -> {out_rel} is not in <out> (SPEC 5.1: every XML1 character-namespace '
                                 f'file is emitted under its mapped name)')
            if C.norm(out_rel) not in self.reg:
                return ('error', f'XML1 {rel} -> {self.idx.get(out_rel)} is an XML2 base file, not the XML1 asset '
                                 f'(namespace collision)')
            if not numeric:
                return None
            new = C.map_skin(old)
            src = ctx.x1_path(rel).read_bytes()
            n_src = x1names.igb_rename(src, old, new)[1]
            if not n_src:
                return None
            data = p.read_bytes()
            left = x1names.igb_rename(data, old, new)[1]
            have = x1names.igb_rename(data, new, new)[1]
            if left or have < n_src:
                return ('error', f'{self.idx.get(out_rel)}: in-IGB rename incomplete: {left} string(s) still named '
                                 f'{old}[_outline|_skel], {have}/{n_src} named {new} (x1names.igb_rename)')
            return ('renamed', n_src)

        workers = max(1, min(8, int(self.ctx.opt('jobs', 1) or 1)))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(one, jobs))
        for r in results:
            ck.count('x1_namespace_files')
            if r is None:
                continue
            if r[0] == 'renamed':
                ck.count('igb_names_renamed', r[1])
            else:
                ck.error(r[1])

    def _x1_weapon_types(self):
        """{lower weapon name: lower type} of XML1's data/weapons/weapons.eng (SPEC 29.3 check)."""
        if self._weapon_types is None:
            try:
                root = self.ctx.read_x1_xml('data/weapons/weapons.eng')
            except KeyError:
                root = None
            self._weapon_types = {} if root is None else {
                (w.get('name') or '').lower(): (w.get('type') or '').lower()
                for w in root.iter() if w.tag.lower() == 'weapon' and w.get('name')}
        return self._weapon_types

    @staticmethod
    def _matches_x1(el, x1el):
        """an <out> stats entry that carries the XML1 entry's mapped skin (so it came from XML1, not XML2)."""
        s = (x1el.get('skin') or '').strip()
        return bool(s) and (el.get('skin') or '').strip() == C.map_skin(s)

    @staticmethod
    def _namespace_problems(el, x1el):
        """XML1-origin stats entry vs its XML1 source: skin / characteranims / powerstyle must be the mapped
        XML1 values (map_skin +14000, map_animdb x1_, map_powerstyle x1_)."""
        out = []
        if x1el is None:
            return out
        for attr, fn in (('skin', C.map_skin), ('characteranims', C.map_animdb), ('powerstyle', C.map_powerstyle)):
            src = (x1el.get(attr) or '').strip()
            if not src:
                continue
            want = fn(src)
            have = (el.get(attr) or '').strip()
            if attr == 'powerstyle' and (x1el.get('weapon') or '').strip():
                # SPEC 29: a soldier with an XML1 gun is pointed at the weapon variant of his style
                from . import weapons as W
                want = W.variant_name(want, (x1el.get('weapon') or '').strip())
                if have == fn(src):
                    continue                        # a melee weapon: the plain mapped style
            if have != want:
                out.append(f'{attr}={have!r}, but XML1 {attr}={src!r} maps to {want!r}')
        return out

    def _entry_problems(self, name, fname, el, shared_t, hero_talent_files):
        """[(kind, msg[, reason])]: kind 'soft' (error for XML1-origin, warn otherwise), 'hard' (always error),
        'warn' (always a warning), 'allow' (allowlisted)."""
        out = []
        skin = (el.get('skin') or '').strip()
        is_mc = name.startswith('_hero') and name.endswith('_mc_')
        if not skin:
            if not is_mc:
                out.append(('soft', 'no skin attribute'))
        elif not _is_skin(skin) or int(skin[:-2]) > 255:
            out.append(('hard', f'skin {skin!r} is not 4-5 digits with prefix <= 255 (byte at +0x254, 0x4b9c40)'))
        else:
            if not self.exists(f'actors/{skin}.igb'):
                if skin == COMPUTER_SKIN:
                    out.append(('allow', f'actors/{skin}.igb missing', 'Computer: XML1 actors/7501.igb is empty'))
                else:
                    out.append(('soft', f'skin actor Actors/{skin}.IGB missing'))
            speaker = name in ST.speaker_stats_entries()
            for pk in (C.char_package_rel(name, skin), C.char_package_rel(name, skin, nc=True)):
                if not self.exists(pk):
                    msg = f'character package {pk} missing (generated/characters/%s_%s%s, 0x68e508)'
                    out.append(('allow', msg, 'SPEC 18.1 speaker entry of a speaking NPC: never spawned (its '
                                              'spawner keeps the hero character), only the conversation label / '
                                              'portrait read it') if speaker else ('soft', msg))
        for k, v in el.attrib.items():
            if k.startswith('skin_'):
                costume = k[len('skin_'):]
                if costume not in HERO_COSTUMES:
                    out.append(('soft', f'{k}: costume {costume!r} is not in XMen2.exe\'s table (0x6d8aa0); ignored'))
                elif _is_skin(skin) and not self.exists(f'actors/{skin[:-2]}{v.strip().zfill(2)}.igb'):
                    out.append(('soft', f'{k}={v}: Actors/{skin[:-2]}{v.strip().zfill(2)}.IGB missing'))
        ca = el.get('characteranims')
        if ca and not self.exists(f'actors/{ca}.igb'):
            out.append(('soft', f'characteranims Actors/{ca}.IGB missing'))
        ps = el.get('powerstyle')
        if ps and not (self.exists(f'data/powerstyles/{ps}.xmlb') or self.exists(f'data/powerstyles/{ps}.engb')):
            out.append(('soft', f'powerstyle Data/powerstyles/{ps} missing'))
        elif ps:
            # V5 (SPEC 29.3): XMen2.exe builds XML1's weapon_fire as a SOUND event, so a style a stats entry uses
            # must not fire it, directly or through an event of its own (weapons.apply / rewrite_weapon_events)
            from . import weapons as W
            key = ps.lower()
            if key not in self._weapon_fire_cache:
                t = self.tree(f'data/powerstyles/{ps}.xmlb')
                self._weapon_fire_cache[key] = W.weapon_fire_left(t) if t is not None else []
            left = self._weapon_fire_cache[key]
            x1 = self.x1_stats().get(name.lower())
            wname = (x1[1].get('weapon') or '').strip().lower() if x1 is not None else ''
            wtype = self._x1_weapon_types().get(wname, '')
            named = [w for w, has_weapon in left if has_weapon]
            plain = [w for w, has_weapon in left if not has_weapon]
            if named or (plain and wtype in W.WEAPON_TYPES):
                out.append(('soft', f'powerstyle {ps}: {len(named) + len(plain)} trigger(s) still fire XML1 '
                                    f'weapon_fire, a sound event in XMen2.exe (no shot, no damage): '
                                    f'{(named + plain)[:4]}'))
            elif plain and wname:
                out.append(('warn', f'powerstyle {ps}: {len(plain)} weapon_fire trigger(s) with the melee weapon '
                                    f'{wname}: no shot in XMen2.exe (what XML1 did with them is not established)'))
            elif plain:
                out.append(('allow', f'powerstyle {ps}: {len(plain)} weapon_fire trigger(s), no shot in XMen2.exe',
                            'the XML1 entry has no weapon: its weapon_fire had nothing to fire in XML1 either'))
        ms = el.get('moveset1')
        if ms and not (self.exists(f'data/fightstyles/{ms}.xmlb') or self.exists(f'data/fightstyles/{ms}.engb')):
            out.append(('soft', f'moveset1 Data/fightstyles/{ms} missing'))
        sd = el.get('sounddir')
        if sd and self.banks.resolve_bank(sd) is None:
            out.append(('soft', f'sounddir {sd!r}: no Sounds/eng/{sd[:1]}/{sd[1:2]}/{sd}.zsm|zss'))
        if name not in hero_talent_files:
            t = self.tree(f'data/talents/{name}.xmlb')
            if t is None:
                t = self.tree(f'data/talents/{name}.engb')
            hero_talent_files[name] = {x.get('name', '').lower() for x in t.iter('talent')} if t is not None else set()
        own_t = hero_talent_files[name]
        for c in el:
            if c.tag == 'talent':
                tn = (c.get('name') or '').lower()
                if tn and tn not in shared_t and tn not in own_t:
                    out.append(('soft', f'talent {tn!r} is neither in shared_talents nor in data/talents/{name}'))
                if is_fightstyle_name(tn) and not (self.exists(f'data/fightstyles/{tn}.xmlb') or
                                                        self.exists(f'data/fightstyles/{tn}.engb')):
                    out.append(('soft', f'fightstyle talent {tn}: Data/fightstyles/{tn} missing'))
            elif c.tag.lower() == 'bolton':
                m = (c.get('model') or '').strip()
                if m:
                    ok = self.exists(f'actors/{m}.igb') if _is_skin(m) else self.exists(f'{m}.igb')
                    if not ok:
                        out.append(('soft', f'BoltOn model {m!r} missing'))
                a = (c.get('anim') or '').strip()
                if a and not self.exists(f'actors/{a}.igb'):
                    out.append(('soft', f'BoltOn anim Actors/{a}.IGB missing'))
        return out

    # ================================================================== V6 zones
    def zoneinfo(self):
        if self._zoneinfo is None:
            zi = {}
            for ext in ('.xmlb', '.engb'):
                t = self.tree(f'data/zoneinfo{ext}')
                zi[ext] = None if t is None else collections.defaultdict(list)
                if t is not None:
                    for z in t.iter('zone'):
                        zi[ext][(z.get('name') or '').replace('\\', '/').lower()].append(z)
            self._zoneinfo = zi
        return self._zoneinfo

    def x1_zone_skip_reason(self, z):
        """why an XML1 zone cannot be converted (0-byte zonexml / map IGB), or None."""
        zx = self.ctx.x1_path(f'maps/{z}.eng') or self.ctx.x1_path(f'maps/{z}.xml')
        if zx is None:
            return 'no zonexml on the XML1 disc'
        if self.ctx.x1_is_empty(f'maps/{z}.eng') or self.ctx.x1_is_empty(f'maps/{z}.xml'):
            return 'empty zonexml on the XML1 disc'
        igb = self.ctx.x1_path(f'maps/{z}.igb')
        if igb is None or igb.stat().st_size == 0:
            return 'missing/empty map IGB on the XML1 disc'
        return None

    def _x1_zone_root(self, z):
        for ext in ('.eng', '.xml'):
            try:
                r = self.ctx.read_x1_xml(f'maps/{z}{ext}')
            except KeyError:
                continue
            except Exception:        # noqa: BLE001 - an unparsable source counts as "no world"
                return None
            return r
        return None

    def _x1_world(self, z):
        r = self._x1_zone_root(z)
        return C.find_world(r) if r is not None else None

    def x1_zone_has_world(self, z):
        return self._x1_world(z) is not None

    def expected_zonescript(self, z):
        """the zonescript ref the build should have set: x1/tour/<z> for a tour stop, else the scripts module's
        pure provider zone_script_ref (SPEC 5.0); Ellipsis when it cannot be determined."""
        if self._tour_stops is None:
            doc = self._tour_doc()
            self._tour_stops = {s.get('zone'): s.get('script') for s in (doc or {}).get('stops') or []} \
                if doc and not doc.get('_invalid') else {}
        if z in self._tour_stops:
            return C.norm(self._tour_stops[z] or '')
        if self._zs_provider is None:
            try:
                from . import scripts as S                 # noqa: WPS433 - optional provider module
                self._zs_provider = getattr(S, 'zone_script_ref', False)
            except Exception:        # noqa: BLE001 - scripts.py missing or broken: skip the comparison
                self._zs_provider = False
        if not self._zs_provider:
            return ...
        try:
            r = self._zs_provider(self.ctx, z)
        except Exception:        # noqa: BLE001
            return ...
        return _script_ref(r) if r else None

    def x1_chr_names(self, z):
        """lowercase character names of the XML1 zone's .chr (empty set for a missing / 0-byte .chr)."""
        try:
            r = self.ctx.read_x1_xml(f'maps/{z}.chr')
        except KeyError:
            return set()
        except Exception:        # noqa: BLE001
            return set()
        return {(c.get('name') or '').lower() for c in r.iter('character')} - {''} if r is not None else set()

    def x1_nav_nonempty(self, z):
        p = self.ctx.x1_path(f'maps/{z}.nav')
        return p is not None and not self.ctx.x1_is_empty(f'maps/{z}.nav')

    @property
    def x1banks(self):
        if self._x1banks is None:
            self._x1banks = VSND.X1Banks(self.banks, self.ctx.x1_xbox / 'sounds' / 'zsds')
        return self._x1banks

    def resolve_link(self, zone, value):
        v = value.strip().replace('\\', '/').lower()
        if not v:
            return 'empty', None
        if '/' in v:
            return ('full', v) if self.zone_exists(v) else ('unresolved', None)
        d = zone.rsplit('/', 1)[0]
        if self.zone_exists(f'{d}/{v}'):
            return 'same_dir', f'{d}/{v}'
        others = sorted(z for z in self.zone_ids if z.rsplit('/', 1)[-1] == v)
        if others:
            return 'cross_dir_short', others
        return 'unresolved', None

    def _act_plan(self):
        """scripts.act_on_entry_plan (pure provider) or None when scripts.py is unavailable."""
        try:
            from . import scripts as S                     # noqa: WPS433 - optional provider module
            return S.act_on_entry_plan(self.ctx)
        except Exception:        # noqa: BLE001
            return None

    def _v6_act_on_entry(self, ck, no_act, reachable):
        """reachable converted zones whose zone script sets no act (setCurrentAct): an error where the scripts
        module's act plan says the zone sets one (generated / injected / research-injected), otherwise one
        aggregated warning (the deferred multi-act zones) - tour stops are skipped (tour mode runs no zone script)."""
        reach = set(reachable)
        plan = self._act_plan()
        rows = (plan or {}).get('zones') or {}
        missing = sorted(z for z in no_act if z in reach)
        ck.set('zones_no_act_on_entry_reachable', len(missing))
        ck.set('zones_no_act_on_entry', len(no_act))
        ck.details['zones_no_act_on_entry'] = no_act
        bad = [z for z in missing if (rows.get(z) or {}).get('status') in
               ('sets_act', 'sets_act_later', 'inject', 'x1_act_entry', 'x1_act_wrapper')]
        for z in bad:
            ck.error(f'{z}: the scripts act plan gives it an act on entry ({rows[z]["status"]}, act '
                     f'{rows[z].get("entry_act")}) but its world zonescript sets none')
        rest = [z for z in missing if z not in bad]
        if rest:
            why = {z: ((rows.get(z) or {}).get('status'), (rows.get(z) or {}).get('acts')) for z in rest}
            ck.warn(f'{len(rest)} zones reachable from New Game set no act on entry (deferred by scripts: visited in '
                    f'several campaign acts, so the act comes from the mission start only): {why}')

    def _v6_zoneinfo_xtraction(self, ck, conv):
        """XML1 mode: no zoneinfo entry may register an XML2 zone in the Xtraction network (extraction /
        towncenter / mapx / mapy, 0x468130 / 0x467f60): the world map would offer XML2 hubs."""
        n_x = 0
        for n, lst in sorted(self.scan.zoneinfo_xtraction.items()):
            for name, attrs in lst:
                z = C.norm(name or '')
                n_x += 1
                if z not in conv:
                    # kept on purpose: stripping them crashes the game at boot (zones.STRIP_XTRACTION)
                    ck.warn(f'{self.scan.files[n]["rel"]}: zone {name!r} (not an XML1 zone) keeps Xtraction attributes '
                            f'{attrs}; XML1 Xtraction points offer it on the world map (known limitation)')
        ck.set('zoneinfo_xtraction_entries', n_x)
        if not self.scan.zoneinfo_xtraction:
            ck.warn('Data/zoneinfo is not a registered build output (Xtraction network not checked)')

    # ---- section 15: act town centres
    def _v6_act_towncenters(self, ck):
        """Every act the build can select has a registered zoneinfo town centre. XMen2.exe registers the first 31
        zoneinfo entries with extraction="true" (0x468130, cap 0x46817d); entering any zone (0x4867e0) passes the town
        centre of the current act (0x4682b0: first registered entry with that act and towncenter="true", else NULL)
        to _stricmp at 0x486844 with no NULL test (the pause menu too, 0x5cc0f0), so a selectable act without one
        crashes the game (menu/main_back at boot with every town centre stripped; nyc/riots/nyc3_1_1 under act 7).
        Selectors: setCurrentAct literals in every installed script (zone entry, mission starts, New Game hook) and
        the act of every listed mission file."""
        cap = 31

        def true(el, k):                                   # XMen2.exe: _stricmp(value, "true") == 0
            return (el.get(k) or '').strip().lower() == 'true'

        sel = collections.defaultdict(set)
        for r in sorted(self.script_set()):
            res = self.script(r)
            if res is None:
                continue
            for c in res.calls:
                if c.name == 'setCurrentAct' and c.args and c.args[0].kind == 'num':
                    try:
                        sel[int(float(str(c.args[0].value)))].add(self.idx.get(r) or r)
                    except ValueError:
                        pass
        lst = self.tree('data/missions/missions.xmlb')
        for m in ([e.get('name') or '' for e in lst if e.tag.upper() == 'MISSION'] if lst is not None else []):
            t = self.tree(f'data/missions/{m.lower()}.xmlb') or self.tree(f'data/missions/{m.lower()}.engb')
            a = (t.get('act') or '').strip() if t is not None else ''
            if a.isdigit():
                sel[int(a)].add(f'Data/missions/{m}')
        ck.set('acts_selectable', len(sel))
        ck.details['acts_selectable'] = {a: sorted(s)[:6] for a, s in sorted(sel.items())}
        checked = 0
        for ext in ('.xmlb', '.engb'):
            t = self.tree(f'data/zoneinfo{ext}')
            if t is None:
                continue
            checked += 1
            rel = f'Data/zoneinfo{ext.upper() if ext == ".xmlb" else ext}'
            entries = [z for z in t.iter('zone') if true(z, 'extraction')]
            if len(entries) > cap:
                ck.error(f'{rel}: {len(entries)} extraction="true" entries; XMen2.exe registers only the first {cap} '
                         f'(0x46817d), never {[z.get("name") for z in entries[cap:]]}')
            tc = {}
            for z in entries[:cap]:
                if true(z, 'towncenter'):
                    a = (z.get('act') or '').strip()
                    tc.setdefault(int(a) if a.isdigit() else 1, C.norm(z.get('name') or ''))   # 0x4680a0: act 1 default
            for a, zone in sorted(tc.items()):
                if not self.zone_exists(zone):
                    ck.error(f'{rel}: act {a} town centre {zone!r} has no Maps/{zone}.XMLB in <out> (loadextraction / '
                             f'world map target)')
            for a in sorted(sel):
                if a not in tc:
                    ck.error(f'{rel}: act {a} has no registered town centre (extraction="true" towncenter="true" '
                             f'act="{a}" among the first {cap} extraction entries): entering any zone in act {a} crashes '
                             f'XMen2.exe (0x4867e0 -> 0x4682b0 NULL -> _stricmp 0x486844); act {a} is selected by '
                             f'{sorted(sel[a])[:4]}')
            ck.details[f'towncenters{ext}'] = {a: z for a, z in sorted(tc.items())}
            ck.set(f'zoneinfo{ext}_extraction_entries', len(entries))
        if not checked:
            ck.warn('Data/zoneinfo missing from <out>: act town centres not checked')
    # ---- end section 15

    # ---- section 16: per-zone animation DB
    def _v6_zone_animdbs(self, ck):
        """XMen2.exe attaches to every actor of a zone the anim DB resource named "zone_<last path component>"
        (0x486710: "zone_%s" 0x688d78 -> actor manager vfunc +0xc; else "zone_shared" 0x681968). XML1's per-area
        mission_<area> DBs are never attached, so their EA_ZONEn clips are unreachable: a converted zone package
        must not list one, and a zone_* entry must be this zone's own name with Actors/zone_<leaf>.igb present and
        its clips renamed to zoneN (characters.rename_mission_anims_igb)."""
        sc = self.scan
        shared = self.ctx.shared.get('zone_animdbs') or {}
        own = fallback = 0
        lost, no_file, bad_clips = [], [], []
        for z in self.converted_zones():
            pn = f'packages/generated/maps/{z}.pkgb'
            ents = sc.pkg.get(pn)
            if ents is None:
                continue
            leaf = z.rsplit('/', 1)[-1]
            want = f'zone_{leaf}'
            stems = set()
            for kind, fn in ents:
                if (kind or '').lower() != 'actoranimdb' or not fn:
                    continue
                s = C.norm(fn)
                s = s[len('actors/'):] if s.startswith('actors/') else s
                s = s[:-4] if s.endswith('.igb') else s
                stems.add(s)
                if s.startswith('mission_'):
                    ck.error(f'{pn}: actoranimdb {fn!r}: XMen2.exe never attaches a mission_* DB (it asks for '
                             f'"{want}", 0x486710); the zone\'s EA_ZONE clips would be unreachable (zones section 16)')
                elif s.startswith('zone_') and s not in (want, 'zone_shared'):
                    ck.error(f'{pn}: actoranimdb {fn!r} is not this zone\'s "{want}" (0x486710 derives the name from '
                             f'the last path component of the zone name; a package lists only its own)')
                elif '/' in s and s.rsplit('/', 1)[-1].startswith('zone_'):
                    ck.error(f'{pn}: actoranimdb {fn!r}: the zone DB is keyed by the bare name; a path entry loads '
                             f'but is never matched (in-game test, section 16)')
            if want in stems:
                own += 1
                rel = f'actors/{want}.igb'
                data = self.read(rel)
                if data is None:
                    no_file.append(z)
                    ck.error(f'{pn}: actoranimdb {want!r} but Actors/{want}.IGB is missing from <out>')
                    continue
                if re.search(rb'mission\d+\x00', data) or not re.search(rb'zone\d+\x00', data):
                    bad_clips.append(z)
                    ck.error(f'Actors/{want}.IGB: clips are not renamed to zoneN (still missionN, or no zone clip); '
                             f'EA_ZONEn would resolve to nothing')
            else:
                fallback += 1
                x1_mission = None
                try:
                    bundle = self.ctx.zone_bundle(z)
                except KeyError:
                    bundle = ()
                for p, kind in bundle:
                    if (kind or '').lower() == 'actoranimdb':
                        s = C.pkg_name(p)
                        s = s[len('actors/'):] if s.startswith('actors/') else s
                        if s.startswith('mission_'):
                            x1_mission = s
                            break
                if x1_mission:
                    lost.append(z)
                    st = (shared.get(z) or {}).get('status')
                    if st is None and self._zone_animdb_owned_elsewhere(z, want):
                        st = 'lost'           # standalone validation (no ctx.shared): another zone owns the name
                    (ck.warn if st == 'lost' else ck.error)(
                        f'{pn}: XML1 listed {x1_mission} but the package has no "{want}" entry: the zone keeps '
                        f'XMen2.exe\'s zone_shared and its EA_ZONE clips are missing'
                        + (' (known: another XML1 area owns this leaf name; a zone rename would fix it)' if st == 'lost'
                           else ' (zones section 16 should have written it)'))
        ck.set('zone_animdb_own', own)
        ck.set('zone_animdb_fallback', fallback)
        ck.details['zone_animdb_lost'] = lost
        if lost:
            ck.note(f'{len(lost)} converted zones fall back to zone_shared although XML1 gave them mission anims: '
                    f'{lost}')

    # ---- section 17: instance extents are entity-local (XMen2.exe inst parser 0x461e3e; XML2 retail 7,782/7,782)
    def _v6_inst_extents(self, ck):
        """no <inst extents> of a converted zone is still an XML1 world-space box (absolute coordinates): such a box
        makes triggers and zone links unreachable (zones section 17). A box that contains the entity's world `pos`
        but not its own origin is flagged; a few XML1 boxes are authored offset from the entity (kill volumes above
        a marker) and legitimately contain neither - those are counted, not errors."""
        bad, offset_boxes, checked = [], 0, 0
        for z in self.converted_zones():
            t = self.tree(f'maps/{z}.xmlb')
            if t is None:
                continue
            for inst in t.iter('inst'):
                ext = inst.get('extents')
                if not ext:
                    continue
                try:
                    e = [float(v) for v in ext.split()]
                except ValueError:
                    bad.append((z, inst.get('name'), ext))
                    continue
                checked += 1
                if len(e) != 6:
                    bad.append((z, inst.get('name'), ext))
                    continue
                if all(e[i] - 1.0 <= 0.0 <= e[i + 3] + 1.0 for i in range(3)):
                    continue
                try:
                    p = [float(v) for v in (inst.get('pos') or '').split()]
                except ValueError:
                    p = []
                if len(p) == 3 and all(e[i] - 1.0 <= p[i] <= e[i + 3] + 1.0 for i in range(3)):
                    bad.append((z, inst.get('name'), ext))
                else:
                    offset_boxes += 1
        ck.set('inst_extents_checked', checked)
        ck.set('inst_extents_offset_boxes', offset_boxes)
        ck.details['inst_extents_not_local'] = bad[:50]
        if bad:
            ck.error(f'{len(bad)} zone instance boxes do not contain their own origin (XML1 world-space extents left '
                     f'unconverted? zones section 17): {bad[:5]}')
    # ---- end section 17

    # ---- section 25
    def _v6_allinone_starts(self, ck):
        """every hero start of a converted zone can take the whole party (zones section 25): a playerstartent with no
        slot and at most one <inst> carries allinone="true" (XMen2.exe spawns hero n at the n-th inst otherwise, so
        the party's other heroes never appear)."""
        bad, marked = [], 0
        for z in self.converted_zones():
            t = self.tree(f'maps/{z}.xmlb')
            if t is None:
                continue
            insts = collections.Counter((i.get('name') or '').lower() for i in t.iter('inst'))
            for e in t.iter('entity'):
                if (e.get('classname') or '').lower() != 'playerstartent' or e.get('slot') is not None:
                    continue
                if (e.get('allinone') or '').lower() == 'true':
                    marked += 1
                elif insts[(e.get('name') or '').lower()] <= 1:
                    bad.append((z, e.get('name')))
        ck.set('starts_allinone', marked)
        ck.details['starts_one_hero_only'] = bad[:50]
        if bad:
            ck.error(f'{len(bad)} one-position hero starts without allinone="true" spawn only the party leader '
                     f'(zones section 25): {bad[:5]}')
    # ---- end section 25

    # ---- section 18
    def _v6_join_doubles(self, ck):
        """the join zones' NPC double has its own name (zones section 18): the spawner's monster_name is the double's,
        and no join script or zone guard removes the hero's own name (remove() removes every entity of a name, the
        party's hero included)."""
        bad = []
        for zone, (spawner, hero) in ST.JOIN_DOUBLE_SPAWNERS.items():
            t = self.tree(f'maps/{zone}.xmlb')
            if t is None:
                continue
            names = [e.get('monster_name') for e in t.iter('entity') if (e.get('name') or '').lower() == spawner]
            if names != [ST.join_double(hero)]:
                bad.append(f'{zone}: {spawner} monster_name {names} (want {ST.join_double(hero)!r})')
        hero_remove = re.compile(r'''^\s*remove\s*\(\s*"(%s)"''' % '|'.join(sorted({h for _, h in ST.JOIN_DOUBLE_SPAWNERS.values()})),
                                 re.I | re.M)
        for rel in sorted(self.idx.keys()):
            if not rel.startswith('scripts/') or not rel.endswith('.py'):
                continue
            data = self.read(rel)
            text = data.decode('latin-1') if data else ''
            if ST.JOIN_FLAG in text and hero_remove.search(text):
                bad.append(f'{rel}: a join script removes the hero\'s own name')
        ck.details['join_doubles'] = bad
        if bad:
            ck.error(f'join zones: the NPC double shares the joining hero\'s name (zones section 18): {bad[:5]}')
        # the joined hero's start: a slot-2..4 start the zone disables would leave him unspawned at every load after
        # the join but the trigger's own (in game 2026-09-28 night); zones.enable_join_starts
        starts = []
        for zone in sorted(ST.JOIN_DOUBLE_SPAWNERS):
            t = self.tree(f'maps/{zone}.xmlb')
            if t is None:
                continue
            found = [e for e in t.iter('entity') if (e.get('classname') or '').lower() == 'playerstartent' and
                     (e.get('slot') or '').strip() not in ('', '0', '1')]
            if not found:
                starts.append(f'{zone}: no slot-2 player start')
            starts += [f'{zone}: {e.get("name")} (slot {e.get("slot")}) startenabled="false"' for e in found
                       if (e.get('startenabled') or '').strip().lower() == 'false']
        ck.details['join_starts'] = starts
        if starts:
            ck.error(f'join zones: the joined hero has no enabled start after the join (zones section 18): {starts[:5]}')

    def _zone_script_lines(self, z):
        """{where: [lines]} of every script the zone runs (its world zonescript + the scripts its package lists) and
        its inline zone-data code (one line per code string)."""
        world, _ = self.zone_world(z)
        refs = {_script_ref(fn) for k, fn in (self.zone_pkg(z) or []) if k == 'script' and fn}
        if (world or {}).get('zonescript'):
            refs.add(_script_ref(world['zonescript']))
        out = {}
        for ref in sorted(r for r in refs if r):
            data = self.read(f'scripts/{ref}.py')
            if data:
                out[f'Scripts/{ref}.py'] = data.decode('latin-1').split('\r\n')
        for n in (f'maps/{z}.engb', f'maps/{z}.xmlb'):
            codes = [code for _, _, code in self.scan.inline.get(n, [])]
            if codes:
                out[f'{n} (inline)'] = codes
        return out

    def _zone_conversations(self, z):
        """[(rel, root)] of the conversations the zone's package lists (English .engb, else .XMLB)."""
        out = []
        for kind, fn in self.zone_pkg(z) or ():
            f = C.norm(fn or '')
            if (kind or '').lower() != 'xml' or not f.startswith('conversations/'):
                continue
            for ext in ('.engb', '.xmlb'):
                t = self.tree(f + ext)
                if t is not None:
                    out.append((self.entry(f + ext)['rel'] if self.entry(f + ext) else f + ext, t))
                    break
        return out

    def _zone_hero_npcs(self, z, heroes):
        """{entity name: character} of the zone's spawner NPCs whose character is a playable hero (monster_name,
        else the character, lower case)."""
        t = self.tree(f'maps/{z}.engb')
        t = t if t is not None else self.tree(f'maps/{z}.xmlb')
        out = {}
        for e in (t.iter('entity') if t is not None else ()):
            if (e.get('classname') or '').lower() == 'monsterspawnerent':
                ch = (e.get('character') or '').lower()
                if ch in heroes:
                    out[(e.get('monster_name') or ch).lower()] = ch
        return out

    def _v6_hero_speakers(self, ck, heroes, reach, packaged, names, bad):
        """section 18.1 (2026-09-29), the speakers. (c) NPC_SPEAKER_CONVERSATIONS: packaged by their zone, which spawns
        the NPC (that entity name, the hero's character); the hero's lines say %NPC% (at least one) and none keeps
        %HERO%; the NPC name has a speaker stats entry. (d) every reachable zone that spawns an NPC of a playable hero
        under another entity name: each conversation it packages with a %HERO% line of that hero is renamed (c) or
        reviewed in HERO_SPEAKER_REVIEW ('party': only the party's hero speaks it there; 'open': the NPC speaks it
        without a talk animation - warned). The talk animation goes to the entity named after the token (0x45bd1e ->
        0x4c6f20), the name label and portrait to the stats entry of that name (0x456d00)."""
        def conv_tree(conv):
            for ext in ('.engb', '.xmlb'):
                t = self.tree(f'conversations/{conv}{ext}')
                if t is not None:
                    return t
            return None

        def line_tokens(root):
            for el in root.iter():
                for k in SPEAKER_ATTRS:
                    for tok in SPEAKER_RE.findall(el.get(k) or ''):
                        yield k, tok.strip('%').lower()
        n_npc_tok = 0
        for conv, (zone, speakers) in sorted(ST.NPC_SPEAKER_CONVERSATIONS.items()):
            zs = packaged.get(conv, set())
            if zone not in zs:
                bad.append(f'conversations/{conv}: not packaged by {zone} (NPC_SPEAKER_CONVERSATIONS)')
            root = conv_tree(conv)
            if root is None:
                bad.append(f'conversations/{conv}: missing (NPC_SPEAKER_CONVERSATIONS)')
                continue
            toks = collections.Counter(t for _, t in line_tokens(root))
            for z in sorted(zs | {zone}):
                npcs = self._zone_hero_npcs(z, heroes)
                for h, npc in speakers.items():
                    if npcs.get(npc.lower()) != h.lower():
                        bad.append(f'{z}: packages conversations/{conv}, whose {h} lines {ST.NPC_SPEAKER_CONVERSATIONS[conv][1]} '
                                   f'name the NPC "{npc}", but spawns no NPC of that name with character {h}')
            for h, npc in speakers.items():
                n_npc_tok += toks.get(npc.lower(), 0)
                if toks.get(h.lower()):
                    bad.append(f'conversations/{conv}: speaker %{h.upper()}% ({toks[h.lower()]}x) names the hero, not '
                               f'the NPC "{npc}" that speaks there (want %{npc.upper()}%)')
                if not toks.get(npc.lower()):
                    bad.append(f'conversations/{conv}: no line of the NPC %{npc.upper()}% (NPC_SPEAKER_CONVERSATIONS)')
                if npc.lower() not in names:
                    bad.append(f'conversations/{conv}: speaker %{npc.upper()}% has no stats entry '
                               f'(heroes add_double_speakers, scripts_transform.speaker_stats_entries)')
        ck.set('hero_npc_speaker_tokens', n_npc_tok)
        # the speaker entries' name label: XML1's own where it differs from the hero's (SPEAKER_DISPLAY_NAMES: the NPC
        # Alison, default.xbe string 503 "Alison"), else the hero's; the portrait is the hero's skin
        heroes_by = {}
        for ext, v in self.stats()['variants'].items():
            for el in v['herostat']:
                heroes_by[(ext, (el.get('name') or '').lower())] = el
        for ext, v in self.stats()['variants'].items():
            entries = {(el.get('name') or '').lower(): el for el in v['npcstat']}
            for npc, h in sorted(ST.speaker_stats_entries().items()):
                el, src = entries.get(npc), heroes_by.get((ext, h))
                if el is None or src is None:
                    continue                                   # a missing entry is reported below / by V5
                want = ST.SPEAKER_DISPLAY_NAMES.get(npc, src.get('charactername'))
                if el.get('charactername') != want or el.get('skin') != src.get('skin'):
                    bad.append(f'npcstat{ext} speaker entry {npc}: charactername {el.get("charactername")!r} / skin '
                               f'{el.get("skin")!r}, want {want!r} / {h}\'s skin {src.get("skin")!r} (XML1\'s label '
                               f'and portrait; scripts_transform.SPEAKER_DISPLAY_NAMES)')
        renamed = {(c, h) for c, (_, sp) in ST.NPC_SPEAKER_CONVERSATIONS.items() for h in sp}
        used, reviewed, opened, unreviewed = set(), collections.defaultdict(list), [], []
        for z in sorted(self.converted_zones()):
            if z not in reach:
                continue
            others = collections.defaultdict(set)          # hero -> the NPC entity names of that hero, not the hero's
            for npc, ch in self._zone_hero_npcs(z, heroes).items():
                if npc != ch:
                    others[ch].add(npc)
            if not others:
                continue
            for kind, fn in self.zone_pkg(z) or ():
                f = C.norm(fn or '')
                if (kind or '').lower() != 'xml' or not f.startswith('conversations/'):
                    continue
                conv = f[len('conversations/'):]
                root = conv_tree(conv)
                if root is None:
                    continue
                for h in sorted({t for _, t in line_tokens(root)} & set(others)):
                    key = (conv, h)
                    if key in renamed:
                        continue
                    why = ST.HERO_SPEAKER_REVIEW.get(key)
                    what = f'{z}: conversations/{conv} %{h.upper()}% (NPC {sorted(others[h])})'
                    if why in ST.HERO_SPEAKER_REVIEW_REASONS:
                        used.add(key)
                        (opened.append(what) if why == 'open' else reviewed[why].append(what))
                    else:
                        unreviewed.append(what + (f' reviewed as {why!r}, which is no reason' if why else ''))
        ck.details['hero_speakers'] = {'renamed': sorted(f'{c}:{h}' for c, h in renamed), 'reviewed': dict(reviewed),
                                       'open': opened, 'unreviewed': unreviewed}
        ck.set('hero_speakers_reviewed', sum(len(v) for v in reviewed.values()))
        ck.set('hero_speakers_open', len(opened))
        for what in unreviewed:
            bad.append(f'speaker review (18.1): {what}: a hero token where an NPC of that hero stands under another '
                       f'name - rename (scripts_transform.NPC_SPEAKER_CONVERSATIONS) or review (HERO_SPEAKER_REVIEW)')
        stale = sorted(set(ST.HERO_SPEAKER_REVIEW) - used)
        if stale:
            ck.warn(f'section 18.1 HERO_SPEAKER_REVIEW entries that match no packaged line of a reachable zone: {stale}')
        if opened:
            ck.warn(f'{len(opened)} conversations: an NPC speaks under its hero\'s token, so it gets no talk animation '
                    f'(name label and portrait right; HERO_SPEAKER_REVIEW open, SPEC 18.1): {opened}')

    def _v6_hero_npcs(self, ck, reachable):
        """section 18, the other same-name NPCs. (a) NPC_DOUBLE_SPAWNERS: the zone's spawner has monster_name
        join_double(hero) and no script, inline code or packaged conversation of the zone addresses the hero's own
        name in an entity call or as a %HERO% speaker (18.1); NPC_DOUBLE_CONVERSATIONS are packaged by their zone
        only; every double speaker token has a stats entry (NPC_DOUBLE_SPEAKERS); (b) every other
        reachable converted zone whose spawner NPC is named after a playable herostat hero (monster_name, else its
        character) and whose scripts address that name must be reviewed in HERO_NPC_REVIEW (why the party cannot
        hold the hero there): remove / setEnable / playanim ... on that name would hit the party's hero too."""
        heroes = set()
        st = self.stats()['variants']
        for ext in ('.xmlb', '.engb'):
            for el in (st.get(ext) or {}).get('herostat', []):
                if (el.get('team') or '').lower() == 'hero':
                    heroes.add((el.get('name') or '').lower())
        bad, unreviewed, reviewed = [], [], {}
        for zone, spec in ST.NPC_DOUBLE_SPAWNERS.items():
            t = self.tree(f'maps/{zone}.engb')
            t = t if t is not None else self.tree(f'maps/{zone}.xmlb')
            if t is None:
                bad.append(f'{zone}: zone missing')
                continue
            names = {(e.get('name') or '').lower(): (e.get('monster_name') or '').lower() for e in t.iter('entity')}
            for sp, hero in spec.items():
                if names.get(sp) != ST.join_double(hero):
                    bad.append(f'{zone}: {sp} monster_name {names.get(sp)!r} (want {ST.join_double(hero)!r})')
            own = {h.lower() for h in spec.values()}
            for where, lines in self._zone_script_lines(zone).items():
                for i, l in enumerate(lines, 1):
                    for fn, nm in ST.entity_name_refs(l, own):
                        bad.append(f'{where}:{i}: {fn}("{nm}") addresses the hero, not the renamed NPC')
            # section 18.1: the zone's conversations talk to the double (a %HERO% speaker's talk animation goes to the
            # entity named HERO: the party's hero, 0x45bd1e -> 0x4c6f20), and their inline code addresses it
            for rel, root in self._zone_conversations(zone):
                for el in root.iter():
                    for k, v in el.attrib.items():
                        if not v:
                            continue
                        if k.lower() in SPEAKER_ATTRS:
                            for tok in SPEAKER_RE.findall(v):
                                if tok.strip('%').lower() in own:
                                    bad.append(f'{rel} {k}: speaker {tok} names the hero, not the renamed NPC '
                                               f'(want {ST.double_speaker_token(tok.strip("%"))})')
                        elif '(' in v:
                            for fn, nm in ST.entity_name_refs(v, own):
                                bad.append(f'{rel} {k}: {fn}("{nm}") addresses the hero, not the renamed NPC')
        # the conversations the doubles speak in: each is packaged by its zone only (another zone would talk-animate
        # nothing, or the party's hero there), and every double's speaker token has a stats entry (name label and
        # portrait, 0x456d00: without one the raw token shows)
        packaged = collections.defaultdict(set)
        for z in self.converted_zones():
            for kind, fn in self.zone_pkg(z) or ():
                f = C.norm(fn or '')
                if (kind or '').lower() == 'xml' and f.startswith('conversations/'):
                    packaged[f[len('conversations/'):]].add(z)
        for conv, zone in sorted(ST.NPC_DOUBLE_CONVERSATIONS.items()):
            zs = packaged.get(conv, set())
            if zone not in zs:
                bad.append(f'conversations/{conv}: not packaged by {zone} (NPC_DOUBLE_CONVERSATIONS)')
            heroes_here = set(ST.NPC_DOUBLE_SPAWNERS.get(zone, {}).values())
            for other in sorted(zs - {zone}):
                if not heroes_here <= set(ST.NPC_DOUBLE_SPAWNERS.get(other, {}).values()):
                    bad.append(f'conversations/{conv}: also packaged by {other}, which keeps the NPCs '
                               f'{sorted(heroes_here)} under the heroes\' names')
        names = self.stats_names()
        double_tokens = {ST.double_speaker_token(h).lower() for zs in ST.NPC_DOUBLE_SPAWNERS.values() for h in zs.values()}
        double_tokens |= {ST.double_speaker_token(h).lower() for _, h in ST.JOIN_DOUBLE_SPAWNERS.values()}
        double_tokens |= {f'%{npc}%' for npc in ST.speaker_stats_entries()}      # the NPCs' own names (18.1)
        n_double_tok = 0
        for n, lst in self.data_items(self.scan.speakers):
            for attr, tok in lst:
                if tok.lower() in double_tokens:
                    n_double_tok += 1
                    if tok.strip('%').lower() not in names:
                        bad.append(f'{self.scan.files[n]["rel"]} {attr}: speaker {tok} has no stats entry '
                                   f'(heroes add_double_speakers, scripts_transform.NPC_DOUBLE_SPEAKERS)')
        for npc, h in sorted(ST.speaker_stats_entries().items()):
            if npc not in names:
                bad.append(f'npcstat: no speaker entry {npc} ({h}; scripts_transform.speaker_stats_entries)')
        ck.set('hero_npc_double_speaker_tokens', n_double_tok)
        reach = set(reachable)
        self._v6_hero_speakers(ck, heroes, reach, packaged, names, bad)
        for z in self.converted_zones():
            if z not in reach or z in ST.JOIN_DOUBLE_SPAWNERS:
                continue
            t = self.tree(f'maps/{z}.engb')
            t = t if t is not None else self.tree(f'maps/{z}.xmlb')
            if t is None:
                continue
            npcs = set()
            for e in t.iter('entity'):
                if (e.get('classname') or '').lower() == 'monsterspawnerent':
                    nm = (e.get('monster_name') or e.get('character') or '').lower()
                    if nm in heroes:
                        npcs.add(nm)
            if not npcs:
                continue
            hits = collections.defaultdict(list)
            for where, lines in self._zone_script_lines(z).items():
                for i, l in enumerate(lines, 1):
                    for fn, nm in ST.entity_name_refs(l, npcs):
                        hits[nm].append(f'{where}:{i} {fn}')
            rev = ST.HERO_NPC_REVIEW.get(z, {})
            for nm, where in sorted(hits.items()):
                why = rev.get(nm) or rev.get('*')
                if why in ST.HERO_NPC_REVIEW_REASONS:
                    reviewed.setdefault(why, []).append(f'{z}:{nm}')
                elif why:
                    # section 18.1: e.g. "not unlocked yet" - the profile keeps unlocks from game to game
                    unreviewed.append(f'{z}: NPC "{nm}" reviewed as {why!r}, which is no reason (want one of '
                                      f'{ST.HERO_NPC_REVIEW_REASONS}); addressed by {where[:3]}')
                else:
                    unreviewed.append(f'{z}: NPC "{nm}" addressed by {where[:3]}')
        ck.details['hero_npcs'] = {'renamed': {z: dict(s) for z, s in ST.NPC_DOUBLE_SPAWNERS.items()},
                                   'reviewed': reviewed, 'bad': bad, 'unreviewed': unreviewed}
        ck.set('hero_npc_doubles_renamed', sum(len(s) for s in ST.NPC_DOUBLE_SPAWNERS.values()))
        ck.set('hero_npcs_reviewed', sum(len(v) for v in reviewed.values()))
        for b in bad[:20]:
            ck.error(f'same-name NPC doubles (zones section 18): {b}')
        if len(bad) > 20:
            ck.error(f'same-name NPC doubles (zones section 18): {len(bad) - 20} more (details hero_npcs.bad)')
        if unreviewed:
            ck.error(f'{len(unreviewed)} NPCs of reachable zones are named after a playable hero and addressed by that '
                     f'name in the zone\'s scripts (zones section 18: rename like NPC_DOUBLE_SPAWNERS, or review in '
                     f'scripts_transform.HERO_NPC_REVIEW): {unreviewed[:5]}')
        ck.note(f'section 18 same-name NPCs: renamed {ck.details["hero_npcs"]["renamed"]}; kept after review '
                f'{ {k: len(v) for k, v in reviewed.items()} }')
    # ---- end section 18

    def _zone_animdb_owned_elsewhere(self, zone, want):
        """True when another converted zone with the same last path component lists `want` (zones section 16
        gave the shared name to the other XML1 area): the same verdict zones.py records as status 'lost'."""
        leaf = zone.rsplit('/', 1)[-1]
        for other in self.converted_zones():
            if other == zone or other.rsplit('/', 1)[-1] != leaf:
                continue
            for kind, fn in self.scan.pkg.get(f'packages/generated/maps/{other}.pkgb') or ():
                if (kind or '').lower() == 'actoranimdb' and fn and C.norm(fn).split('/')[-1] == want:
                    return True
        return False
    # ---- end section 16

    def _v6_speakers(self, ck, names):
        """every %TOKEN% speaker of a registered (XML1) conversation is an XMen2.exe built-in token or a stats
        name; a token XML1 itself could not resolve either (no XML1 stats name / built-in) is inherited (warn)."""
        x1names = set(self.x1_stats())
        inherited = collections.Counter()
        n_tok = 0
        # SPEC 18.1: the NPC Alison's own conversations name her speaker entry "alison", which the alias spells too
        npc_tokens = {(c, f'%{npc.lower()}%') for c, (_, sp) in ST.NPC_SPEAKER_CONVERSATIONS.items() for npc in sp.values()}
        for n, lst in self.data_items(self.scan.speakers):
            rel = self.scan.files[n]['rel']
            r = C.norm(rel)
            conv = C.split_ext(r[len('conversations/'):])[0] if r.startswith('conversations/') else None
            for attr, tok in lst:
                n_tok += 1
                t = tok.lower()
                if t in XML1_SPEAKER_ALIASES and (conv, t) not in npc_tokens:
                    ck.error(f'{rel} {attr}: XML1-only speaker alias {tok} (default.xbe resolved it to '
                             f'{XML1_SPEAKER_ALIASES[t]!r}; XMen2.exe cannot) - scripts.SPEAKER_TOKEN_ALIASES (only '
                             f'the NPC\'s own conversations, scripts_transform.NPC_SPEAKER_CONVERSATIONS, name her '
                             f'speaker entry {t.strip("%")!r})')
                    continue
                if t in XML2_SPEAKER_TOKENS or t.strip('%') in names:
                    continue
                if t.strip('%') in x1names:
                    ck.error(f'{rel} {attr}: speaker {tok} is an XML1 stats name missing from the build\'s '
                             f'herostat/npcstat (line plays without speaker name/portrait)')
                else:
                    inherited[tok] += 1
        ck.set('speaker_tokens', n_tok)
        ck.set('speaker_tokens_inherited', sum(inherited.values()))
        ck.details['speaker_tokens_inherited'] = dict(inherited)
        if inherited:
            ck.warn(f'{sum(inherited.values())} conversation speaker tokens ({len(inherited)} distinct) name no stats '
                    f'entry in XML1 either (inherited: no speaker name/portrait there too): {dict(inherited)}')

    def native_conversation_heads(self, entries):
        """Final conversation heads of same-name/same-skin native XML2 stats.

        These already use the destination namespace even when their number also
        names an XML1 skin. Only exempt heads required by this package's actual
        conversations from V4's source-namespace test; file checks still apply.
        """
        from . import conversations as CV
        final = {name: value[1] for name, value in self.stats()['by_name'].items()}
        if not hasattr(self, '_native_portrait_stats'):
            native = {}
            for name in ('herostat', 'npcstat'):
                rel = self.ctx.base_index.find(f'data/{name}', ('.engb', '.xmlb'))
                if rel:
                    for entry in self.ctx.read_base_xmlb(rel).iter('stats'):
                        key = (entry.get('name') or '').lower()
                        current = final.get(key)
                        if current is not None and current.get('skin') == entry.get('skin'):
                            native[key] = current
            self._native_portrait_stats = native
        heads = set()
        for kind, name in entries:
            if kind not in ('xml', 'xml_resident') or not C.norm(name).startswith('conversations/'):
                continue
            rel = self.idx.find(name, ('.engb', '.xmlb'))
            root = self.tree(rel) if rel else None
            if root is not None:
                heads.update(h for h in CV.portrait_requirements(root, self._native_portrait_stats).values() if h)
        return heads

    def conversation_portraits(self, ck):
        """Cold no-party head coverage; stricter than relying on a forced party.

        Read final English conversations/stats and package models independently
        of the builder's counts. Existing unavailable source assets are warnings;
        an available head without permanent/zone coverage is an error.
        """
        from . import conversations as CV
        stats = {name: value[1] for name, value in self.stats()['by_name'].items()}
        source_heads = {}
        for _, entry in self.x1_stats().values():
            if entry.get('skin'):
                source = f'hud/hud_head_{entry.get("skin")}'
                source_heads[C.map_package_entry('model', source)[1]] = source + '.igb'
        permanent = {C.norm(f) for k, f in (self.zone_pkg('package/permanent') or []) if k == 'model'}
        requirements = {}
        gaps, unavailable = [], []
        for zone in self.converted_zones():
            entries = self.zone_pkg(zone) or []
            covered = permanent | {C.norm(f) for k, f in entries if k == 'model'}
            ck.count('zones')
            for kind, name in entries:
                name = C.norm(name)
                if kind not in ('xml', 'xml_resident') or not name.startswith('conversations/'):
                    continue
                if name not in requirements:
                    rel = self.idx.find(name, ('.engb', '.xmlb'))
                    tree = self.tree(rel) if rel else None
                    if tree is None:
                        ck.error(f'{name}: cannot read final conversation for portrait coverage')
                    requirements[name] = CV.portrait_requirements(tree, stats) if tree is not None else {}
                for speaker, head in requirements[name].items():
                    ck.count('speaker_zone_occurrences')
                    if head in covered:
                        ck.count('covered')
                        continue
                    finding = {'zone': zone, 'conversation': name, 'speaker': speaker, 'head': head}
                    if head and self.exists(head + '.igb'):
                        gaps.append(finding)
                        ck.error(f'{zone}: {name} speaker {speaker}: {head} has no permanent/zone precache')
                        continue
                    # V5/V6 already diagnose missing stats. For an unavailable
                    # head, only tolerate a source defect, never a lost import.
                    # Match by mapped asset, not speaker name: final speaker-only
                    # aliases need not exist as stats names in the source table.
                    source_head = source_heads.get(head)
                    if head and (self.ctx.base_index.path(head + '.igb') or
                                 (source_head and self.ctx.x1_path(source_head))):
                        ck.error(f'{zone}: {name} speaker {speaker}: source head exists but {head} is missing')
                        gaps.append(finding)
                    else:
                        unavailable.append(finding)
        ck.set('uncovered', len(gaps))
        ck.set('unavailable', len(unavailable))
        ck.details['uncovered'] = gaps
        ck.details['unavailable'] = unavailable
        if unavailable:
            ck.warn(f'{len(unavailable)} speaker/zone occurrences lack stats/heads in available source data; '
                    'see unavailable details (inherited; stats also checked by V5/V6)')
        ck.note('Coverage requires permanent/zone models even with forced parties enabled; no particular party is assumed.')

    def v6_zones(self, ck):
        ctx = self.ctx
        zones = self.converted_zones()
        ck.set('zones_converted', len(zones))
        if not zones:
            ck.error('no converted XML1 zone in <out> (zones module missing or failed)')
            return
        sh = ctx.shared.get('zones_converted')
        if sh is not None and set(sh) != set(zones):
            ck.warn(f'ctx.shared zones_converted ({len(sh)}) differs from the zone files registered in <out> '
                    f'({len(zones)}): only shared {sorted(set(sh) - set(zones))[:5]}, '
                    f'only <out> {sorted(set(zones) - set(sh))[:5]}')
        conv = set(zones)
        skipped = {}
        for z in ctx.x1_zones():
            if z in conv:
                continue
            if z in C.frontend_zones(ctx):
                # XML2 front end kept (--frontend xml2, C.FRONTEND_ZONES): XMen2.exe loads it at boot; its files
                # must be XML2's. With --frontend xml1 (SPEC 21) the rule inverts: XML1's backdrop must be converted
                # (a menu zone that is not is reported below as convertible-but-not-converted, and by V15)
                bad = [e['rel'] for n, e in self.reg.items() if n.startswith(C.FRONTEND_ZONES[z])]
                for rel in bad:
                    ck.error(f'{rel}: XML2 front-end file of {z} was rewritten (owner {self.entry(rel)["owner"]}); '
                             f'the boot-time main-menu backdrop must stay XML2\'s')
                for p in C.FRONTEND_ZONES[z]:
                    if not any(k.startswith(p) for k in ctx.base_index.under(p.rsplit('/', 1)[0] + '/')):
                        continue
                    for k in ctx.base_index.under(p.rsplit('/', 1)[0] + '/'):
                        if C.norm(k).startswith(p) and not self.exists(k):
                            ck.error(f'{k}: XML2 front-end file missing from <out>')
                ck.note(f'{z}: XML2 front end kept (not converted from XML1)')
                skipped[z] = 'XML2 front end kept'
                continue
            why = self.x1_zone_skip_reason(z)
            if why:
                skipped[z] = why
            else:
                ck.error(f'{z}: XML1 zone is convertible but was not converted')
        ck.set('zones_skipped', len(skipped))
        ck.details['skipped'] = skipped
        try:
            reachable = ctx.tour_order()
        except (OSError, KeyError, ValueError):
            reachable = []
        for z in reachable:
            if z not in conv:
                (ck.warn if z not in skipped else ck.note)(
                    f'{z}: reachable from New Game (graph.json) but not converted'
                    + (f' ({skipped[z]})' if z in skipped else ''))
        names = self.stats_names()
        zi = self.zoneinfo()
        for ext, d in zi.items():
            if d is None:
                ck.error(f'Data/zoneinfo{ext} missing or undecodable')
                continue
            for n, lst in d.items():
                if len(lst) > 1 and n in conv:
                    ck.warn(f'zoneinfo{ext}: zone {n!r} listed {len(lst)} times')
        details = {}
        no_nav, no_zonescript, no_act = [], [], []
        self._known_prevzone = []
        for z in zones:
            det = details[z] = {}
            ownere = self.entry(f'maps/{z}.xmlb') or self.entry(f'maps/{z}.engb')
            if ownere and not (ownere['owner'] == 'zones' or
                               (ownere['owner'] == 'testhooks' and 'zones' in ownere.get('history', []))):
                ck.error(f'{z}: Maps/{z} zone file owned by {ownere["owner"]}, not zones')
            world, worlds = self.zone_world(z)
            for ext, (w, t) in worlds.items():
                if t is None:
                    ck.error(f'{z}: Maps/{z}{ext} does not decode')
                elif w is None:
                    if self.x1_zone_has_world(z):
                        ck.error(f'{z}: Maps/{z}{ext} has no <entity name="world"> (the XML1 zone has one)')
                    else:
                        ck.warn(f'{z}: Maps/{z}{ext} has no <entity name="world">; the XML1 zone has none either '
                                f'(inherited: no zonescript/soundfile; load is an in-game check)')
            if len(worlds) == 2 and all(w is not None for w, _ in worlds.values()):   # (Elements are falsy when childless)
                a, b = worlds['.engb'][0].attrib, worlds['.xmlb'][0].attrib
                for k in ('zonescript', 'soundfile'):
                    if a.get(k) != b.get(k):
                        ck.error(f'{z}: world {k} differs between .engb ({a.get(k)!r}) and .XMLB ({b.get(k)!r})')
            if not self.exists(f'maps/{z}.igb'):
                ck.error(f'{z}: map geometry Maps/{z}.IGB missing')
            if not self.exists(f'maps/{z}.boyb'):
                ck.error(f'{z}: Maps/{z}.BOYB missing (XML2 zones all carry a buoy file)')
            # characters
            chr_names = []
            t = self.tree(f'maps/{z}.chrb')
            if t is None:
                ck.error(f'{z}: Maps/{z}.CHRB missing or undecodable')
            else:
                chr_names = [(c.get('name') or '') for c in t.iter('character')]
                for c in chr_names:
                    if c.lower() not in names:
                        ck.error(f'{z}: CHRB character {c!r} is not a herostat/npcstat name')
                lost = sorted(self.x1_chr_names(z) - {c.lower() for c in chr_names})
                if lost:
                    ck.error(f'{z}: CHRB lost XML1 .chr character(s) {lost} (their spawners never spawn)')
            det['chr'] = chr_names
            if not self.exists(f'maps/{z}.navb'):
                no_nav.append((z, len(chr_names)))
                if self.x1_nav_nonempty(z):
                    ck.error(f'{z}: no Maps/{z}.NAVB although the XML1 .nav is not empty')
            if world is None:
                continue
            # zonescript
            zs = (world.get('zonescript') or '').strip()
            det['zonescript'] = zs
            ents = self.zone_pkg(z) or []
            pkg_scripts = {C.norm(fn or '') for k, fn in ents if k == 'script'}
            if zs:
                ref = _script_ref(zs)
                if zs != ref:
                    ck.warn(f'{z}: world zonescript {zs!r} is not normalised (lowercase, "/", no .py)')
                if not self.exists(f'scripts/{ref}.py'):
                    ck.error(f'{z}: world zonescript {zs!r} -> Scripts/{ref}.py is not installed')
                elif f'scripts/{ref}' not in pkg_scripts:
                    ck.warn(f'{z}: zonescript scripts/{ref} is not listed in the zone package')
            else:
                no_zonescript.append(z)
            want_zs = self.expected_zonescript(z)
            if want_zs is not ... and (_script_ref(zs) if zs else None) != want_zs:
                ck.warn(f'{z}: world zonescript {zs or None!r}, but scripts.zone_script_ref gives {want_zs!r} '
                        f'(SPEC 5.3.2c)')
                ck.count('zonescript_mismatch')
            # act on entry (XML2 zone scripts call setCurrentAct first): re-derived from the installed zone script
            if z not in (self._tour_stops or {}):
                txt = (self.read(f'scripts/{_script_ref(zs)}.py') or b'').decode('latin-1') if zs else ''
                if not re.search(r'\bsetCurrentAct\s*\(', txt):
                    no_act.append(z)
            # soundfile
            sf = (world.get('soundfile') or '').strip()
            det['soundfile'] = sf
            x1w = self._x1_world(z)
            x1sf = ((x1w.get('soundfile') if x1w is not None else '') or '').strip()
            if x1sf and sf.lower() != x1sf.lower():
                x1_had = [f'{x1sf}_{s}' for s in VSND.SUFFIXES if self.x1banks.resolve_bank(f'{x1sf}_{s}')]
                if x1_had:
                    ck.error(f'{z}: world soundfile {sf!r} but the XML1 zone has soundfile={x1sf!r}, whose banks '
                             f'{x1_had} exist (zone sounds and music are chosen by it)')
                else:
                    ck.count('soundfile_substituted')
                    ck.note(f'{z}: soundfile {x1sf!r} (no bank on the XML1 disc) replaced by {sf!r}')
            if not sf:
                if not x1sf:
                    ck.warn(f'{z}: world entity has no soundfile, as in XML1 (inherited: no zone sounds or music)')
            else:
                if len(sf) > SOUNDFILE_MAX:
                    ck.error(f'{z}: soundfile {sf!r} is {len(sf)} chars; XMen2.exe aborts zone sound loading at >= 10 (0x5920cb)')
                if len(sf) >= 2 and sf[-2] == '_' and 'a' <= sf[-1].lower() <= 'v':
                    ck.warn(f'{z}: soundfile {sf!r} ends in _<letter>: only that one bank is loaded (0x59210e)')
                else:
                    for suf in VSND.SUFFIXES:
                        if self.banks.resolve_bank(f'{sf}_{suf}') is not None:
                            continue
                        ck.count(f'zones_without_bank_{suf}')
                        x1b = self.x1banks.resolve_bank(f'{sf}_{suf}')
                        if x1b is not None:
                            ck.error(f'{z}: soundfile {sf!r}: bank {sf}_{suf} is on the XML1 disc ({x1b.name}) but '
                                     f'Sounds/eng/{sf[:1].lower()}/{sf[1:2].lower()}/{sf.lower()}_{suf}.zsm|zss is not '
                                     f'installed')
                        elif suf == 'm':
                            ck.warn(f'{z}: soundfile {sf!r}: no {sf}_m bank, and XML1 never had one either '
                                    f'(inherited: no zone sound effects)')
            for k in ('ambientmusic', 'combatmusic'):
                if world.get(k):
                    ck.note(f'{z}: world {k}={world.get(k)!r} is ignored by XMen2.exe (plays {sf}_a/_c instead)')
            # every entity: links, spawner characters, monster skins, precaches, loading textures
            zt = next((t for ext in ('.engb', '.xmlb') for (_w, t) in [worlds.get(ext, (None, None))]
                       if t is not None), None)
            self._zone_entities(ck, z, zt, names, conv, skipped)
            # zoneinfo
            for ext, d in zi.items():
                if d is None:
                    continue
                ents_zi = d.get(z)
                if not ents_zi:
                    ck.error(f'{z}: no <zone name="{z}"> in Data/zoneinfo{ext}')
                    continue
                zel = ents_zi[0]
                if zel.get('name') != z:
                    ck.warn(f'zoneinfo{ext}: name {zel.get("name")!r} is not the lowercase "/" zone id {z!r}')
                act = zel.get('act')
                if act is not None and not (act.isdigit() and 1 <= int(act) <= 9):
                    ck.warn(f'zoneinfo{ext}: {z} act={act!r} outside 1..9')
                lt = zel.get('loading')
                if lt and not (self.exists(f'{lt}.igb') or self.exists(f'{lt}.png')):
                    ck.warn(f'zoneinfo{ext}: {z} loading texture {lt} missing (engine skips it)')
        ck.details['zones'] = details
        # aggregated known / deferred conditions (one warning each; full lists in details)
        ck.set('zones_without_nav', len(no_nav))
        ck.details['zones_without_nav'] = {z: n for z, n in no_nav}
        if no_nav:
            with_npcs = sorted(z for z, n in no_nav if n)
            ck.warn(f'{len(no_nav)} converted zones have no NAVB because their XML1 .nav is empty (SPEC 4.5; XML2 '
                    f'tolerates missing nav only in non-combat zones): {len(with_npcs)} of them list characters, '
                    f'NPC pathing there is an in-game check, e.g. {with_npcs[:6]}')
        ck.set('zones_without_zonescript', len(no_zonescript))
        ck.details['zones_without_zonescript'] = no_zonescript
        if no_zonescript:
            ck.note(f'{len(no_zonescript)} converted zones have no world zonescript: {no_zonescript}')
        self._v6_act_on_entry(ck, no_act, reachable)
        self._v6_zoneinfo_xtraction(ck, conv)
        self._v6_act_towncenters(ck)                       # section 15
        self._v6_zone_animdbs(ck)                          # section 16
        self._v6_inst_extents(ck)                          # section 17
        self._v6_allinone_starts(ck)                       # section 25
        self._v6_join_doubles(ck)                          # section 18
        self._v6_hero_npcs(ck, reachable)                  # section 18, the other same-name NPCs
        self._v6_speakers(ck, names)
        ck.set('prevzone_known_unresolved', len(self._known_prevzone))
        ck.details['prevzone_known_unresolved'] = self._known_prevzone
        if self._known_prevzone:
            ck.warn(f'{len(self._known_prevzone)} prevzone values name zones XML1 itself never shipped (known, '
                    f'research zones.json; such a player_start is never chosen): {self._known_prevzone[:4]}')
        self._items_check(ck)

    ITEM_TYPES = ('item', 'potion', 'equipment', 'money')      # XMen2.exe item parser 0x47af1a..0x47af85

    def _items_check(self, ck):
        """Data/items (zones world-table merge): XML1 items are appended only when converted content names them
        (inventoryitem), in XML2 schema: a type XMen2.exe parses, no XML1 <activepowerup>, no dead XML1
        attributes; every inventoryitem in registered data names an item (XML1's own dead names are inherited)."""
        ctx = self.ctx
        sc = self.scan
        if not sc.items:
            return
        base_names = set()
        for ext in ('.engb', '.XMLB'):
            if ctx.base_exists(f'Data/items{ext}'):
                base_names |= {(c.get('name') or '').lower() for c in C.iter_roots(ctx.read_base_xmlb(f'Data/items{ext}'))[0]
                               if c.get('name')}
        names = set()
        for n, root in sorted(sc.items.items()):
            rel = sc.files[n]['rel']
            top = C.iter_roots(root)[0]
            for el in root.iter():
                if el.tag.lower() == 'activepowerup':
                    ck.error(f'{rel}: XML1 <activepowerup> in the items table (XMen2.exe never reads it)')
            added = []
            for c in top:
                nm = (c.get('name') or '').lower()
                if nm:
                    names.add(nm)
                if c.tag != 'item' or not nm or nm in base_names:
                    continue
                added.append(nm)
                t = (c.get('type') or '').lower()
                if t not in self.ITEM_TYPES:
                    ck.error(f'{rel}: XML1 item {c.get("name")!r} type={c.get("type")!r} is not an XMen2.exe item type '
                             f'{self.ITEM_TYPES} (0x47af1a)')
                extra = sorted(set(c.attrib) - set(ITEM_ATTRS_XML2))
                if extra:
                    ck.warn(f'{rel}: XML1 item {c.get("name")!r} keeps attributes XML2 items never use: {extra}')
            ck.set(f'items_added_{n.rsplit(".", 1)[1]}', len(added))
            ck.details[f'items_added_{n.rsplit(".", 1)[1]}'] = added
        used = collections.defaultdict(set)
        for n, vals in sc.inv_items.items():
            for v in vals:
                used[v.strip().lower()].add(sc.files[n]['rel'])
        dr = self.tree('data/dangerroom.engb') if self.entry('data/dangerroom.engb') else None
        for r in (dr.iter('REWARD') if dr is not None else ()):      # SPEC 21: challenge rewards (V16 checks them)
            if r.get('rewarditem'):
                used[r.get('rewarditem').strip().lower()].add('Data/dangerroom.engb')
        try:
            x1root = ctx.read_x1_xml('data/items.eng')
            x1names_ = {(c.get('name') or '').lower() for c in x1root.iter() if c.get('name')} if x1root is not None else set()
        except KeyError:
            x1names_ = set()
        for v, files in sorted(used.items()):
            if v in names:
                continue
            if v not in x1names_:
                ck.count('inventoryitem_inherited_dead')
                ck.warn(f'inventoryitem {v!r} names no item in the XML1 items table either (inherited): '
                        f'{sorted(files)[:3]}')
            else:
                ck.error(f'inventoryitem {v!r} ({sorted(files)[:3]}) names an XML1 item missing from Data/items')
        for n in sc.items:
            for nm in ck.details.get(f'items_added_{n.rsplit(".", 1)[1]}', []):
                if nm not in used:
                    ck.warn(f'Data/items: XML1 item {nm!r} was added but nothing references it')

    def _zone_entities(self, ck, z, t, names, conv, skipped):
        if t is None:
            return
        for el in t.iter():
            for k in ('nextzone', 'prevzone'):
                v = el.get(k)
                if v is None or not v.strip():
                    continue
                raw_l = v.strip().replace('\\', '/').lower()
                if v.strip() != raw_l:
                    ck.warn(f'{z}: {k}={v!r} is not lowercase with "/"')
                how, tgt = self.resolve_link(z, v)
                if how in ('full', 'same_dir'):
                    ck.count(f'{k}_ok')
                    continue
                target_zone = raw_l if '/' in raw_l else f'{z.rsplit("/", 1)[0]}/{raw_l}'
                if k == 'nextzone':
                    if target_zone in skipped:
                        ck.error(f'{z}: nextzone {v!r} -> {target_zone} was skipped ({skipped[target_zone]})')
                    elif how == 'cross_dir_short':
                        ck.error(f'{z}: nextzone {v!r} only exists in another directory ({tgt[:3]}); XML2 resolves '
                                 f'short names in the zone\'s own directory only - write the full path')
                    else:
                        ck.error(f'{z}: nextzone {v!r} resolves to no zone in <out>')
                else:
                    key = (z, raw_l.rsplit('/', 1)[-1])
                    if key in KNOWN_UNRESOLVED_PREVZONE:
                        self._known_prevzone.append(f'{z}: {v}')
                    elif key in KNOWN_AMBIGUOUS_PREVZONE or how == 'cross_dir_short':
                        ck.warn(f'{z}: prevzone {v!r} is a cross-directory short name ({tgt if tgt else "ambiguous"}); '
                                f'not rewritten to a full path')
                    elif target_zone in skipped:
                        ck.warn(f'{z}: prevzone {v!r} -> {target_zone} was skipped ({skipped[target_zone]})')
                    else:
                        ck.error(f'{z}: prevzone {v!r} resolves to no zone in <out>')
            ch = el.get('character')
            if ch and ch.strip() and ch.strip().lower() not in names:
                ck.error(f'{z}: <{el.tag} name="{el.get("name")}"> character={ch!r} is not a herostat/npcstat name')
            ms = el.get('monster_skin')
            if ms and ms.strip():
                m = ms.strip()
                if not _is_skin(m) or int(m[:-2]) > 255:
                    ck.error(f'{z}: monster_skin {m!r} is not 4-5 digits with prefix <= 255')
                elif not self.exists(f'actors/{m}.igb'):
                    ck.error(f'{z}: monster_skin {m}: Actors/{m}.IGB missing')
            lt = el.get('loading')
            if lt and lt.strip() and el.tag == 'entity' and not (self.exists(f'{lt.strip()}.igb') or
                                                                 self.exists(f'{lt.strip()}.png')):
                ck.warn(f'{z}: loading texture {lt!r} missing')
            if el.tag == 'precache':
                self._precache(ck, z, el.get('type') or '', el.get('filename') or '')

    def _precache(self, ck, z, typ, fn):
        typ = typ.lower()
        f = C.norm(fn).strip()
        if not f:
            return
        if typ == 'script':
            ref = _script_ref(f)
            cands = [f'scripts/{ref}.py']
        elif typ == 'conversation':
            cands = [f'conversations/{f}.xmlb', f'conversations/{f}.engb']
        elif typ == 'dialog':
            d = f if f.startswith('dialogs/') else f'dialogs/{f}'
            cands = [f'{d}.xmlb', f'{d}.engb']
        elif typ in ('model', 'texture'):
            cands = [f'{f}.igb']
        elif typ == 'fx':
            cands = [f'effects/{f}.xmlb', f'effects/{f}.engb']
        else:
            return
        if any(self.exists(c) for c in cands):
            return
        stems = {_stem(c) for c in cands}
        if self.dead_on_disc(stems):
            ck.allow(f'{z}: precache {typ} {fn!r} unresolved', 'dead on the XML1 disc')
        else:
            hint = ''
            if typ == 'model' and self.exists(f'models/{f}.igb'):
                hint = (f'; only Models/{f}.IGB exists (XML2 retail precache models are root-relative, e.g. '
                        f'hud/hud_head_*; the XML1 disc has no root {f}.igb either), so this precache finds no file')
            ck.warn(f'{z}: precache {typ} {fn!r} resolves to none of {cands}{hint}')
            ck.count('precache_unresolved')

    # ================================================================== V7 scripts
    @property
    def x1checker(self):
        """XML1's own registration table (research/scripts/xml1_api.json): recognises lines XML1 dropped too."""
        if self._x1checker is None:
            try:
                self._x1checker = VS.ScriptChecker(self.ctx.research_json('scripts/xml1_api.json'))
            except (OSError, ValueError):
                self._x1checker = False
        return self._x1checker

    def inherited_drop(self, p, verbatim):
        """True when problem `p` (a call XMen2.exe drops) is a line default.xbe dropped as well: the statement is
        verbatim XML1 content (`verbatim(p)`: the same statement is in the original XML1 script, or the whole
        inline value is in the XML1 source file) AND its function is not in XML1's table (any case) or its argc /
        literal types do not fit XML1's signature either. Such lines behave exactly as in XML1 (silently
        skipped): inherited defects, not regressions. Anything the rewrite generated is never inherited."""
        if p.call is None or p.kind not in ('unknown function', 'wrong case', 'argc', 'type') or not self.x1checker:
            return False
        if verbatim is None or not verbatim(p):
            return False
        c = p.call
        right = self.x1checker.by_lower.get(c.name.lower())
        if right is None:
            return True
        probe = VS.Call(right, c.args, c.line)
        return self.x1checker.signature_problem(probe) is not None

    @staticmethod
    def _stmt_key(s):
        return re.sub(r'\s+', '', s or '')

    def x1_script_statements(self, ref):
        """whitespace-free statements of the ORIGINAL XML1 script scripts/<ref>.py (xml1_loose / assets)."""
        cache = self.__dict__.setdefault('_x1_stmts', {})
        if ref not in cache:
            p = self.ctx.x1_path(f'scripts/{ref}.py')
            lines = set()
            if p is not None:
                text = p.read_bytes().decode('latin-1')
                lines = {self._stmt_key(x) for x in re.split(r'\r\n|\r|\n', text) if x.strip()}
            cache[ref] = lines
        return cache[ref]

    def x1_source_values(self, n):
        """every attribute value of the XML1 source file a registered XMLB was converted from (or empty)."""
        cache = self.__dict__.setdefault('_x1_vals', {})
        e = self.entry(n)
        src = (e or {}).get('source')
        if not self.is_x1_source(src):
            return set()
        if src not in cache:
            vals = set()
            try:
                root = C.parse_x1_text(src)
                if root is not None:
                    vals = {v for el in root.iter() for v in el.attrib.values()}
            except Exception:        # noqa: BLE001
                pass
            cache[src] = vals
        return cache[src]

    def _report_problem(self, ck, where, p, x1, rel=None, verbatim=None):
        """one validate_script Problem -> allow / error / warn, per SPEC 4.6 and the allowlists."""
        text = p.text(where)
        if rel is not None and (C.script_ref(rel), p.kind, p.func) in KNOWN_DEAD_SCRIPT_FINDINGS:
            ck.allow(text, 'line XML1 itself dropped, in a dead developer script')
        elif p.severity == 'error' and x1 and self.inherited_drop(p, verbatim):
            ck.count('inherited_dropped_lines')
            ck.warn(text + ' [inherited: default.xbe drops this line too]')
        elif p.severity == 'error' and x1:
            ck.error(text)
        elif p.severity == 'error':
            ck.warn(text + ' (XML2 base content)')
        else:
            ck.warn(text)

    def _report_script(self, ck, rel, res, x1):
        where = self.idx.get(rel) or rel
        ref = C.script_ref(rel)

        def verbatim(p):
            return p.call is not None and self._stmt_key(p.call.text) in self.x1_script_statements(ref)
        for p in res.problems:
            self._report_problem(ck, where, p, x1, rel=rel, verbatim=verbatim)

    def v7_scripts(self, ck):
        sc = self.scan
        # the script set: registered .py + every script a registered package lists
        rels = set(self.script_set())
        game_flags = collections.Counter()
        total = 0
        load_targets = []
        for r in sorted(rels):
            res = self.script(r)
            if res is None:
                continue                                   # missing: V4 reports the package entry
            x1 = self.is_x1(r)
            ck.count('scripts_checked')
            total += res.statements
            self._report_script(ck, r, res, x1)
            self._store_checks(ck, r, res, game_flags, x1)
            self._console_checks(ck, r, res, x1)
            for c in res.calls:
                if c.name in VS.LOAD_FUNCS and c.args and c.args[0].kind == 'str':
                    load_targets.append((r, c.name, str(c.args[0].value), x1))
                elif c.name in ('cinematicStart', 'restorelastzone') and x1:
                    for a in c.args:
                        if a.kind == 'str' and str(a.value) != C.norm(str(a.value)):
                            ck.warn(f'{self.idx.get(r) or r}:{c.line}: {c.name} path {a.value!r} is not normalised '
                                    f'(lowercase, "/")')
                            ck.count('zone_literals_not_normalised')
        ck.set('script_statements', total)
        # inline data code in registered XMLB (attribute values containing '(', 0x4a11f9)
        n_inline = 0
        for n, lst in self.data_items(sc.inline):
            x1 = self.is_x1(n)
            for tag, attr, code in lst:
                n_inline += 1
                res = self.checker.check_inline(code, x1_output=x1)
                where = f'{sc.files[n]["rel"]} <{tag} {attr}="{_short(code, 60)}">'
                in_src = code in self.x1_source_values(n)
                for p in res.problems:
                    self._report_problem(ck, where, p, x1, verbatim=lambda _p, v=in_src: v)
                self._store_checks(ck, n, res, game_flags, x1)
                self._console_checks(ck, n, res, x1)
                for c in res.calls:
                    if c.name in VS.LOAD_FUNCS and c.args and c.args[0].kind == 'str':
                        load_targets.append((n, c.name, str(c.args[0].value), x1))
        ck.set('inline_scripts', n_inline)
        # dialog options run as 'runscript <code>' through the console
        n_rs = 0
        for n, lst in self.data_items(sc.runscripts):
            x1 = self.is_x1(n)
            for code in lst:
                n_rs += 1
                where = f'{sc.files[n]["rel"]} <option script="{code}">'
                res = self.checker.check_console_code(code, x1_output=x1)
                for p in res.problems:
                    self._report_problem(ck, where, p, x1)
                if '(' not in code:
                    ref = _script_ref(code)
                    if not self.exists(f'scripts/{ref}.py'):
                        (ck.error if x1 else ck.warn)(
                            f'{where}: runscript target Scripts/{ref}.py does not exist (dead-end option)')
                self._store_checks(ck, n, res, game_flags, x1)
                self._console_checks(ck, n, res, x1)
        ck.set('runscript_options', n_rs)
        # data -> script file references (script attrs without '(': 'scripts/'+name+'.py', 0x4a11f9)
        n_refs = 0
        dead = collections.defaultdict(set)                 # inherited dead refs: ref -> files
        not_norm = []
        for n, lst in self.data_items(sc.refs):
            x1 = self.is_x1(n)
            for tag, attr, v in lst:
                vs = v.strip()
                if not vs or vs.startswith('%'):
                    continue
                n_refs += 1
                ref = _script_ref(vs)
                where = f'{sc.files[n]["rel"]} <{tag} {attr}="{_short(v, 70)}">'
                if x1 and vs != ref and attr != 'zonescript' and VS.INLINE_SEP not in vs:
                    not_norm.append(where)
                if self.exists(f'scripts/{ref}.py'):
                    continue
                if self.dead_on_disc({f'scripts/{ref}'}):
                    ck.allow(f'{where}: Scripts/{ref}.py missing', 'dead on the XML1 disc')
                elif x1 and self.x1_script_exists(ref):
                    ck.error(f'{where}: Scripts/{ref}.py exists on the XML1 disc but is not installed')
                elif x1:
                    dead[ref].add(sc.files[n]['rel'])
                else:
                    ck.warn(f'{where}: Scripts/{ref}.py missing (XML2 base content)')
        ck.set('data_script_refs', n_refs)
        ck.set('dead_script_refs', sum(len(v) for v in dead.values()))
        ck.details['dead_script_refs'] = {k: sorted(v) for k, v in sorted(dead.items())}
        if dead:
            ck.warn(f'{sum(len(v) for v in dead.values())} XML1 data script references ({len(dead)} distinct scripts, '
                    f'e.g. {sorted(dead)[:4]}) name scripts that are absent on the XML1 disc too (inherited dead '
                    f'references: the engine finds no file, as in XML1); list in details.dead_script_refs')
        ck.set('script_refs_not_normalised', len(not_norm))
        ck.details['script_refs_not_normalised'] = not_norm
        if not_norm:
            ck.warn(f'{len(not_norm)} XML1 data script references are not normalised (lowercase, "/", no .py) and '
                    f'rely on case-insensitive file lookup: {not_norm[:3]}')
        # game-flag store: 100 names incl. the engine's 4 (0x4d7130); SPEC: <= 96 free for the build
        names = set(game_flags) | set(VS.ENGINE_GAME_FLAGS)
        ck.set('game_flag_names', len(names))
        ck.details['game_flags'] = sorted(game_flags)
        if len(names) > VS.GAME_STORE_NAMES:
            ck.error(f'{len(names)} distinct game-flag names (incl. XMen2.exe\'s 4) > {VS.GAME_STORE_NAMES}: '
                     f'setGameFlag silently fails for the rest (0x4d7130)')
        # mission files / objectives
        self._missions(ck)
        # per-zone engine pools
        self._zone_pools(ck)
        # zone loads: an XML1 zone the build lost is an error; a zone XML1 never shipped is inherited
        ck.details['load_targets'] = sorted({t for _, _, t, _ in load_targets})
        for r, fn, tgt, x1 in load_targets:
            self._check_load_target(ck, f'{sc.files[r]["rel"] if r in sc.files else (self.idx.get(r) or r)}: {fn}',
                                    tgt, x1)
        self._v7_anim_enums(ck, rels)
        self._v7_unwakeable_loops(ck, rels)

    def _enum_strings(self, path):
        data = Path(path).read_bytes().lower()
        return {m.group(1).decode('latin-1') for m in re.finditer(rb'(?<![a-z0-9_])(ea_[a-z0-9_]+)\x00', data)}

    def _v7_anim_enums(self, ck, rels):
        """every animation enum literal (EA_* string arguments in scripts, animenum values and EA_* literals in
        inline data code) is a whole ea_* string of XMen2.exe: XML1's EA_MISSIONn must have become EA_ZONEn
        (scripts_transform.rename_mission_anims). An enum default.xbe lacks too is inherited; the XML1-only
        flying-carry / Juggernaut-grab enums of the added shared nodes are deferred to the powers rework."""
        exe = self.idx.path('xmen2.exe') or (self.ctx.base / 'XMen2.exe')
        x2 = self._enum_strings(exe)
        xbe = self.ctx.x1_xbox / 'default.xbe'
        x1 = self._enum_strings(xbe) if xbe.is_file() else set()
        found = collections.defaultdict(set)
        for r in sorted(rels):
            res = self.script(r)
            if res is None:
                continue
            for c in res.calls:
                for a in c.args:
                    if a.kind == 'str' and re.fullmatch(r'(?i)ea_[a-z0-9_]+', str(a.value or '')):
                        found[str(a.value)].add(self.idx.get(r) or r)
        for n, lst in self.data_items(self.scan.anim_enums):
            for _tag, attr, t in lst:
                found[t].add(f'{self.scan.files[n]["rel"]} @{attr}')
        ck.set('anim_enum_literals', sum(len(v) for v in found.values()))
        ck.set('anim_enums_distinct', len(found))
        deferred, inherited = {}, {}
        for t, where in sorted(found.items()):
            tl = t.lower()
            if tl in x2:
                continue
            if re.fullmatch(r'ea_mission\d+', tl):
                ck.error(f'animation enum {t} is XML1\'s (XMen2.exe has ea_zone1..20, no ea_mission*): '
                         f'{sorted(where)[:4]} (scripts_transform.rename_mission_anims)')
            elif DEFERRED_ANIM_ENUMS.match(tl):
                deferred[t] = sorted(where)[:3]
            elif tl not in x1:
                inherited[t] = sorted(where)[:3]
            else:
                ck.error(f'animation enum {t} exists in default.xbe but not in XMen2.exe: {sorted(where)[:4]}')
        ck.details['anim_enums_deferred'] = deferred
        ck.details['anim_enums_inherited'] = inherited
        if deferred:
            ck.warn(f'{len(deferred)} XML1-only animation enums of the flying-carry / Juggernaut-grab moves (added '
                    f'shared nodes / styles) are not XMen2.exe enums: deferred to the powers rework: {sorted(deferred)}')
        if inherited:
            ck.warn(f'{len(inherited)} animation enums are in neither exe (inherited XML1 defects): {inherited}')

    # ======================================================= npc-loop fix: LOOP_WAKE on NPCs XMen2.exe cannot wake
    # (scripts.spawner_unwakeable / scripts_transform.bound_unwakeable_loops; evidence in scripts_transform.py)
    NONCOMBAT_TEAMS = frozenset({'', 'none', 'neutral'})    # 0x45fbd0: only hero/enemy/altenemy are teams; else 0x1c

    def _v7_unwakeable_loops(self, ck, rels):
        """playanim(<EA_*>, "_OWNER_", "LOOP_WAKE", ..) in a spawn script or inline spawn code loops until the
        XMen2.exe combat AI wakes the NPC (0x5100d0 after target acquisition in 0x514080, 0x513ff3 in the alert
        scan). That AI never runs for team none (0x41a220 == 0x1c) or willflee NPCs (cmp byte [ai+0x46d],1 at
        0x51410c) and the engine has no flee behaviour (AI fleedistance +0x470 is never read), so on such an NPC
        the loop never ends: error for XML1 output (the scripts module bounds it), note for XML2's own. Also notes
        the XML1 stats that still carry willflee/fleedistance and the non-combatant XML1 NPCs whose fightstyle
        talents XMen2.exe will never use (they cannot attack: gates 0x514080 / 0x507925 / 0x51dfe0)."""
        by_name = self.stats()['by_name']
        x1names = set(self.x1_stats())

        def team_of(attrs, character):
            t = (attrs.get('monster_team') or '').strip().lower()
            if not t:
                ent = by_name.get((character or '').lower())
                t = ((ent[1].get('team') if ent else '') or '').strip().lower()
            return t

        owners = collections.defaultdict(list)       # script ref -> [(zone, spawner, character, team, has_act)]
        inline_loops = []
        for z in self.converted_zones():
            n = f'maps/{z}.engb' if f'maps/{z}.engb' in self.scan.files else f'maps/{z}.xmlb'
            t = self.tree(n)
            if t is None:
                continue
            for el in t.iter('entity'):
                if (el.get('classname') or '').strip().lower() != 'monsterspawnerent':
                    continue
                ss = (el.get('monster_spawnscript') or '').strip()
                if not ss:
                    continue
                ch = el.get('character') or ''
                info = (z, el.get('name'), ch, team_of(el.attrib, ch),
                        bool((el.get('monster_actscript') or '').strip()))
                if '(' in ss:
                    if re.search(r'(?i)loop_wake', ss):
                        inline_loops.append(info + (ss,))
                else:
                    owners[_script_ref(ss)].append(info)
        loop_scripts = {}                            # norm rel -> [anim]
        for r in sorted(rels):
            res = self.script(r)
            if res is None:
                continue
            anims = [str(c.args[0].value) for c in res.calls
                     if c.name.lower() == 'playanim' and len(c.args) >= 3
                     and all(a.kind == 'str' for a in c.args[:3])
                     and str(c.args[1].value).lower() == '_owner_' and str(c.args[2].value).lower() == 'loop_wake']
            if anims:
                loop_scripts[r] = anims
        ck.set('loop_wake_spawn_scripts', len(loop_scripts))
        ck.set('loop_wake_inline', len(inline_loops))
        unwakeable = 0
        for r, anims in sorted(loop_scripts.items()):
            ref = _script_ref(r)
            os_ = owners.get(ref, [])
            stuck = [o for o in os_ if o[3] in self.NONCOMBAT_TEAMS and not o[4]]
            where = self.idx.get(r) or r
            if os_ and len(stuck) == len(os_):
                unwakeable += 1
                msg = (f'{where}: LOOP_WAKE {sorted(set(anims))} on an NPC XMen2.exe can never wake (spawners: '
                       f'{sorted({(o[0], o[2], o[3] or "<none>") for o in os_})[:6]}): the loop plays forever '
                       f'(scripts_transform.bound_unwakeable_loops bounds it to LOOP + waittimed + STOP)')
                (ck.error if self.is_x1(r) else ck.note)(msg)
            elif stuck:
                ck.warn(f'{where}: LOOP_WAKE {sorted(set(anims))} runs for combatants and non-combatants alike; '
                        f'the non-combatant spawners loop forever: {sorted({(o[0], o[2]) for o in stuck})[:6]}')
            else:
                ck.count('loop_wake_scripts_wakeable')
        for z, name, ch, team, has_act, code in inline_loops:
            if team in self.NONCOMBAT_TEAMS and not has_act:
                unwakeable += 1
                msg = (f'maps/{z}: <entity {name}> character {ch} (team {team or "<none>"}): inline spawn code loops '
                       f'LOOP_WAKE that XMen2.exe can never wake: {_short(code, 80)}')
                (ck.error if self.is_x1(f'maps/{z}.engb') or self.is_x1(f'maps/{z}.xmlb') else ck.note)(msg)
            else:
                ck.count('loop_wake_inline_wakeable')
        ck.set('loop_wake_unwakeable', unwakeable)
        flee, inert = [], []
        for name, (f, el) in sorted(by_name.items()):
            if f != 'npcstat' or name not in x1names:
                continue
            if el.get('willflee') is not None or el.get('fleedistance') is not None:
                flee.append(name)
            team = (el.get('team') or '').strip().lower()
            fs = [t.get('name') for t in el.iter() if t.tag.lower() == 'talent'
                  and is_fightstyle_name(t.get('name'))]
            if team in self.NONCOMBAT_TEAMS and fs:
                inert.append((name, fs[0]))
        ck.set('x1_npcs_willflee', len(flee))
        ck.set('x1_noncombat_npcs_with_fightstyle', len(inert))
        if flee:
            ck.note(f'{len(flee)} XML1 npcstat entries keep willflee/fleedistance; XMen2.exe never reads the AI '
                    f'fleedistance (+0x470) and uses willflee only to suppress attacking (no flee behaviour; XML2 '
                    f'retail ships none): {flee[:12]}')
        if inert:
            ck.note(f'{len(inert)} XML1 non-combatant (team none) npcstat entries carry a fightstyle talent the '
                    f'XMen2.exe AI can never use (team none never attacks): {inert[:10]}')

    def _check_load_target(self, ck, where, tgt, x1):
        """a loadMapKeepTeam/loadZone/... literal: an XML1 zone the build lost is an error; a zone the XML1 disc
        never shipped is an inherited defect (warn)."""
        z = C.norm(tgt).removeprefix('maps/')
        if x1 and tgt != C.norm(tgt):
            # SPEC 4.1: zone ids in load calls are lowercase with '/' (XML2's own data never uses mixed case, so the
            # engine's case handling of loaded zone names - zoneinfo, prevzone start, save names - is unexercised)
            ck.warn(f'{where}("{tgt}"): zone literal is not normalised (lowercase, "/"); scripts.normalise_zone_'
                    f'literals should have rewritten it to "{C.norm(tgt)}"')
            ck.count('zone_literals_not_normalised')
        if self.zone_exists(z):
            return
        if self._x1_zone_set is None:
            self._x1_zone_set = set(self.ctx.x1_zones())
        msg = f'{where}("{tgt}")'
        if not x1:
            ck.warn(f'{msg} -> no Maps/{z}.XMLB in <out> (XML2 base content)')
        elif z in self._x1_zone_set and self.x1_zone_skip_reason(z):
            ck.count('load_targets_empty_on_disc')
            ck.warn(f'{msg} -> no Maps/{z}.XMLB: XML1 zone skipped ({self.x1_zone_skip_reason(z)}; inherited)')
        elif z in self._x1_zone_set:
            ck.error(f'{msg} -> XML1 zone {z} is convertible but not in <out>')
        else:
            ck.count('load_targets_not_on_disc')
            ck.warn(f'{msg} -> no Maps/{z}.XMLB: the zone is not on the XML1 disc either (inherited)')

    def _missions(self, ck):
        """Data/missions (scripts module): XMen2.exe caps (research/_summaries/scripts.md) - at most 25 mission
        files (0x48908a), 299 objectives in total (0x4885c0), 75 for the current act (0x4899e0); every listed
        file present; objective names used by XML1 code defined; every setCurrentAct literal has missions."""
        t = self.tree('data/missions/missions.xmlb')
        if t is None:
            ck.error('Data/missions/missions.XMLB missing or undecodable (no objectives at all)')
            return
        names = [m.get('name') or '' for m in t.iter('MISSION')]
        ck.set('mission_files', len(names))
        if len(names) > MISSION_FILES_MAX:
            ck.error(f'missions.XMLB lists {len(names)} mission files > {MISSION_FILES_MAX} (0x48908a); the rest never load')
        defined = collections.defaultdict(set)              # objective name -> acts
        per_act = collections.Counter()
        total = 0
        for nm in names:
            mt = None
            for ext in ('.engb', '.xmlb'):
                mt = self.tree(f'data/missions/{nm}{ext}')
                if mt is not None:
                    break
            if mt is None:
                ck.error(f'missions.XMLB lists {nm!r} but Data/missions/{nm}.engb/.XMLB is missing')
                continue
            for mis in ([mt] if mt.tag == 'MISSION' else list(mt.iter('MISSION'))):
                act = (mis.get('act') or '').strip()
                objs = [o.get('name') or '' for o in mis.iter('OBJECTIVE')]
                total += len(objs)
                per_act[act] += len(objs)
                for o in objs:
                    defined[o.lower()].add(act)
        ck.set('objectives_total', total)
        ck.details['objectives_per_act'] = dict(sorted(per_act.items()))
        if total > OBJECTIVES_MAX:
            ck.error(f'{total} objectives in the listed mission files > {OBJECTIVES_MAX} (state bytes 0x72b118, 0x4885c0)')
        for act, n in sorted(per_act.items()):
            if n > OBJECTIVES_PER_ACT:
                ck.error(f'act {act}: {n} objectives > {OBJECTIVES_PER_ACT} loadable for the current act (0x4899e0)')
        missing = {o: sorted(f) for o, f in self._obj_refs.items() if o not in defined}
        ck.set('objective_refs', len(self._obj_refs))
        ck.set('objective_refs_undefined', len(missing))
        ck.details['objective_refs_undefined'] = missing
        if missing:
            ck.warn(f'{len(missing)} objective names used by XML1 code are defined in no listed mission file (the call '
                    f'does nothing): {sorted(missing)[:8]}')
        acts = set(per_act)
        for act, files in sorted(self._act_refs.items()):
            if act not in acts:
                ck.warn(f'setCurrentAct({act}) in {sorted(files)[:3]}: no listed mission file has act="{act}"')

    def _mission_refs(self, rel, res, x1):
        if not x1:
            return
        where = self.idx.get(rel) or rel
        for c in res.calls:
            if c.name in OBJECTIVE_FUNCS and c.args and c.args[0].kind == 'str':
                self._obj_refs[str(c.args[0].value).lower()].add(where)
            elif c.name == 'setCurrentAct' and c.args and c.args[0].kind == 'num':
                self._act_refs[str(int(float(c.args[0].value)))].add(where)

    def _store_checks(self, ck, rel, res, game_flags, x1):
        """setGameFlag / setZoneVar / setZoneFlag literals: names < 12 chars, bits 1..32."""
        sev = ck.error if x1 else ck.warn
        where = self.idx.get(rel) or rel
        self._mission_refs(rel, res, x1)
        for c in res.calls:
            if c.name in ('setGameFlag', 'getGameFlag', 'setZoneFlag', 'getZoneFlag', 'setZoneVar', 'getZoneVar',
                          'getGameVarBitCount', 'allowResponseOnGameVarCount', 'disallowResponseOnVar'):
                if not c.args or c.args[0].kind != 'str':
                    continue
                nm = str(c.args[0].value)
                if len(nm) > VS.GAME_STORE_NAMELEN:
                    sev(f'{where}:{c.line}: {c.name}("{nm}"): name longer than {VS.GAME_STORE_NAMELEN} chars '
                        f'(store setters require len < 12: 0x4d7060 / 0x4d7130)')
                if c.name == 'setGameFlag':
                    game_flags[nm.lower()] += 1
                if c.name in ('setGameFlag', 'getGameFlag', 'setZoneFlag', 'getZoneFlag') and len(c.args) >= 2 \
                        and c.args[1].kind == 'num':
                    try:
                        bit = int(float(c.args[1].value))
                    except ValueError:
                        continue
                    if not 1 <= bit <= 32:
                        sev(f'{where}:{c.line}: {c.name}("{nm}", {bit}): bit index outside 1..32')

    def _x1_text_exists(self, stem):
        return bool(self.ctx.x1_path(f'{stem}.eng') or self.ctx.x1_path(f'{stem}.xml'))

    def _console_checks(self, ck, rel, res, x1):
        """blackbirdMenu -> console 'setblackbirdparms %s %s %s FALSE FALSE'; createPopupDialogXml paths;
        startConversation targets."""
        sev = ck.error if x1 else ck.warn
        where = (self.scan.files[rel]['rel'] if rel in self.scan.files else None) or self.idx.get(rel) or rel
        for c in res.calls:
            if c.name == 'blackbirdMenu' and len(c.args) == 3:
                vals = [str(a.value) if a.kind in ('str', 'num') else None for a in c.args]
                if None in vals:
                    continue
                cmd = 'setblackbirdparms %s %s %s FALSE FALSE' % tuple(vals)
                if len(cmd) > VS.CONSOLE_MAX:
                    sev(f'{where}:{c.line}: blackbirdMenu command is {len(cmd)} chars > {VS.CONSOLE_MAX} (0x55c42f)')
                for v in vals:
                    if re.search(r'[\x00-\x20;]', v):
                        sev(f'{where}:{c.line}: blackbirdMenu arg {v!r} contains whitespace/";" (console tokens)')
                    if len(v) > VS.BLACKBIRD_TOKEN_MAX:
                        sev(f'{where}:{c.line}: blackbirdMenu arg {len(v)} chars > {VS.BLACKBIRD_TOKEN_MAX} (0x5f2408)')
                code = vals[1]
                if '(' in code:                  # stored, later run as 'runscript <code>' (scripts summary)
                    sub = self.checker.check_inline(code, x1_output=x1)
                    for p in sub.problems:
                        self._report_problem(ck, f'{where}:{c.line}: blackbirdMenu code', p, x1)
                    for sc_ in sub.calls:
                        if sc_.name in VS.LOAD_FUNCS and sc_.args and sc_.args[0].kind == 'str':
                            self._check_load_target(ck, f'{where}:{c.line}: blackbirdMenu {sc_.name}',
                                                    str(sc_.args[0].value), x1)
            elif c.name in ('createPopupDialogXml', 'createPopupDialogXmlFilter') and c.args and c.args[0].kind == 'str':
                p = str(c.args[0].value)
                if len(p) > POPUP_PATH_MAX:
                    sev(f'{where}:{c.line}: {c.name} path {p!r} >= 64 chars (0x5ebc57)')
                d = C.norm(p)
                d = d if d.startswith('dialogs/') else f'dialogs/{d}'
                if self.exists(f'{d}.engb') or self.exists(f'{d}.xmlb'):
                    continue
                if not x1:
                    ck.warn(f'{where}:{c.line}: {c.name}("{p}"): {d}.engb/.XMLB missing (XML2 base content)')
                elif d.startswith('dialogs/x1/') or self._x1_text_exists(d):
                    ck.error(f'{where}:{c.line}: {c.name}("{p}"): {d}.engb/.XMLB missing (generated / on the XML1 '
                             f'disc, but not in <out>)')
                else:
                    ck.warn(f'{where}:{c.line}: {c.name}("{p}"): {d} is absent on the XML1 disc too (inherited; '
                            f'the popup never showed in XML1 either)')
            elif c.name in ('startConversation', 'startCharConversation'):
                idx = 0 if c.name == 'startConversation' else 2
                if len(c.args) > idx and c.args[idx].kind == 'str':
                    p = C.norm(str(c.args[idx].value))
                    if not p:
                        continue
                    d = p if p.startswith('conversations/') else f'conversations/{p}'
                    if self.exists(f'{d}.engb') or self.exists(f'{d}.xmlb'):
                        continue
                    if self.dead_on_disc({d}):
                        ck.allow(f'{where}:{c.line}: {c.name}: {d} missing', 'dead on the XML1 disc')
                    elif x1 and self._x1_text_exists(d):
                        ck.error(f'{where}:{c.line}: {c.name}("{p}"): {d} exists on the XML1 disc but not in <out>')
                    elif x1:
                        ck.count('conversations_not_on_disc')
                        ck.warn(f'{where}:{c.line}: {c.name}("{p}"): {d} is absent on the XML1 disc too (inherited)')
                    else:
                        ck.warn(f'{where}:{c.line}: {c.name}("{p}"): {d}.engb/.XMLB missing (XML2 base content)')

    def _zone_pools(self, ck):
        """zone script + scripts its package lists: statements vs the 620-node pool (0x4d7e6e), literals vs
        the 1,556-value pool, scripts vs 120 script objects, distinct zone-var names vs 32 slots."""
        det = {}
        for z in self.converted_zones():
            world, _ = self.zone_world(z)
            ents = self.zone_pkg(z) or []
            refs = {_script_ref(fn) for k, fn in ents if k == 'script' and fn}
            zs = (world or {}).get('zonescript')
            if zs:
                refs.add(_script_ref(zs))
            stm = lits = nsc = 0
            zvars = set()
            for ref in sorted(refs):
                res = self.script(f'scripts/{ref}.py')
                if res is None:
                    continue
                nsc += 1
                stm += res.statements
                lits += res.literals
                for c in res.calls:
                    if c.name in ('setZoneVar', 'setZoneFlag') and c.args and c.args[0].kind == 'str':
                        zvars.add(str(c.args[0].value).lower())
            # inline zone-data code shares the zone-var store
            for n in (f'maps/{z}.engb', f'maps/{z}.xmlb'):
                for _, _, code in self.scan.inline.get(n, []):
                    r = self.checker.check_inline(code)
                    for c in r.calls:
                        if c.name in ('setZoneVar', 'setZoneFlag') and c.args and c.args[0].kind == 'str':
                            zvars.add(str(c.args[0].value).lower())
            det[z] = {'scripts': nsc, 'statements': stm, 'literals': lits, 'zone_vars': len(zvars)}
            if stm > VS.NODE_POOL:
                ck.warn(f'{z}: {stm} statements in the zone script + packaged scripts > {VS.NODE_POOL}-node pool '
                        f'(0x4d7e6e; per-zone residency unverified, test in game)')
                ck.count('zones_over_node_pool')
            if lits > VS.VALUE_POOL:
                ck.warn(f'{z}: {lits} literals in its scripts > {VS.VALUE_POOL}-value pool (0x4d6578; unverified)')
            if nsc > VS.SCRIPT_OBJECTS:
                ck.warn(f'{z}: {nsc} scripts packaged > {VS.SCRIPT_OBJECTS} script objects (0x4d86d1; unverified)')
            if len(zvars) > VS.ZONE_STORE_NAMES:
                ck.error(f'{z}: {len(zvars)} distinct zone-var names > {VS.ZONE_STORE_NAMES} slots (0x4d7060)')
        ck.details['zone_pools'] = det
        if det:
            top = max(det.items(), key=lambda kv: kv[1]['statements'])
            ck.set('max_zone_statements', top[1]['statements'])
            ck.note(f'largest zone script load: {top[0]} with {top[1]["statements"]} statements')

    # ================================================================== V8 sounds
    def v8_sounds(self, ck):
        ctx = self.ctx
        table = self.banks
        banks = sorted(k for k in self.idx.keys() if k.startswith('sounds/') and k.endswith(('.zsm', '.zss')))
        jobs = max(1, int(ctx.opt('jobs', 1) or 1))
        with ThreadPoolExecutor(max_workers=min(jobs, 8)) as ex:
            list(ex.map(table.facts, banks))
        stems9 = collections.defaultdict(set)
        for b in banks:
            f = table.facts(b)
            ck.count('banks_checked')
            if f.get('error'):
                (ck.warn if b in KNOWN_BAD_BANKS else ck.error)(f'{self.idx.get(b)}: does not parse: {f["error"]}')
                continue
            if f['platform'] != 'pc':
                ck.error(f'{self.idx.get(b)}: {f["platform"]} bank (magic must be "ZSNDPC  ")')
            if f['problems']:
                if b in KNOWN_BAD_BANKS:
                    ck.allow(f'{self.idx.get(b)}: {f["problems"][:2]}', 'XML2 ships this bank malformed')
                else:
                    ck.error(f'{self.idx.get(b)}: strict parse fails: {f["problems"][:3]}')
            if f['stereo_zsm']:
                ck.error(f'{self.idx.get(b)}: {len(f["stereo_zsm"])} stereo sample(s) in a .zsm '
                         f'(the loader forces nBlockAlign=2, 0x5950c3)')
            if f['zss_non_ima']:
                ck.error(f'{self.idx.get(b)}: {len(f["zss_non_ima"])} file(s) with format != 0x6a in a .zss '
                         f'(streams are always IMA-decoded, 0x595aa0)')
            stems9[Path(b).stem[:9]].add(Path(b).stem)
        for k, s in stems9.items():
            if len(s) > 1:
                ck.warn(f'banks {sorted(s)} share the first 9 characters (already-loaded check 0x5913c4)')
        self._v8_plan(ck)
        # globals
        glob = []
        for g in VSND.GLOBAL_BANKS:
            r = table.resolve_bank(g)
            if r is None:
                ck.error(f'global bank {g} missing')
            else:
                glob.append(table.lookup_tuple(r))
        self._v8_zones(ck, glob)
        self._v8_char_events(ck)
        # package 'sound' entries (preloaded sound names) must exist in some bank
        allsnd, alltrk = set(), set()
        for b in banks:
            f = table.facts(b)
            allsnd |= f['sounds']
            alltrk |= f['tracks']
        every = [('*', allsnd, alltrk)]
        for pn, ents in sorted(self.scan.pkg.items()):
            for kind, fn in ents:
                if kind == 'sound' and fn:
                    ck.count('pkg_sound_entries')
                    if not VSND.resolve(fn, None, every)[1]:
                        ck.warn(f'{self.scan.files[pn]["rel"]}: <sound filename="{fn}"> is in no installed bank')

    def _v8_plan(self, ck):
        """the sound plan (media installs exactly this, SPEC 3.6) against <out> and the registry."""
        ctx, table = self.ctx, self.banks
        try:
            plan = ctx.planned_sound_banks()
        except Exception as ex:        # noqa: BLE001
            ck.warn(f'sound plan unavailable: {ex}')
            return
        n_x1 = n_merged = 0
        subst = []
        for rel, pe in sorted(plan.items()):
            if pe['kind'] == 'base':
                if not self.exists(rel):
                    ck.error(f'{rel}: planned XML2 bank missing')
                continue
            e = self.entry(rel)
            if e is None:
                ck.error(f'{rel}: planned {pe["kind"]} bank not installed')
                continue
            if pe['kind'] == 'x1':
                n_x1 += 1
            else:
                n_merged += 1
            src, want = e.get('source'), pe.get('src')
            if not src or not want or Path(src).resolve() == Path(want).resolve():
                continue
            # media may install a re-encoded variant of a planned bank (22.05 kHz music from
            # <out>/_build/media_cache, fixed-layout 0x20 combat music, XML1BUILD_MUSIC_DIR, ...): allowed as long
            # as it carries exactly the planned research bank's sound and track keys (every name still resolves)
            fo = table.facts(rel)
            fr = table.facts_file(f'{VSND.EXT_PREFIX}src/{rel}', want)
            if fo.get('error') or fr.get('error'):
                if fr.get('error'):
                    ck.error(f'{rel}: planned research bank {want} unreadable: {fr["error"]}')
                continue                                       # an <out> parse error is reported above
            if fo['sounds'] != fr['sounds'] or fo['tracks'] != fr['tracks']:
                ck.error(f'{rel}: installed from {src} (not the planned {want}) and its keys differ '
                         f'({len(fo["sounds"])}/{len(fr["sounds"])} sounds, {len(fo["tracks"])}/{len(fr["tracks"])} '
                         f'tracks; missing {len(fr["sounds"] - fo["sounds"]) + len(fr["tracks"] - fo["tracks"])})')
            else:
                subst.append(f'{rel} <- {src}')
        ck.set('banks_x1', n_x1)
        ck.set('banks_merged', n_merged)
        ck.set('banks_substituted', len(subst))
        ck.details['banks_substituted'] = subst
        if subst:
            roots = sorted({str(Path(s.split(' <- ', 1)[1]).parent.parent.parent.parent) for s in subst})
            ck.note(f'{len(subst)} planned banks were installed from a re-encoded variant with identical keys '
                    f'(media music handling; sources under {roots[:3]}); list in details.banks_substituted')
        planned = {r for r, pe in plan.items() if pe['kind'] != 'base'}
        for n, e in self.reg.items():
            if n.startswith('sounds/') and n.endswith(('.zsm', '.zss')) and n not in planned:
                ck.warn(f'{e["rel"]}: registered bank not in ctx.planned_sound_banks()')
        sh = ctx.shared.get('sound_banks_installed')
        if sh is not None and {C.norm(x) for x in sh} != planned:
            ck.warn(f'ctx.shared sound_banks_installed ({len(sh)}) differs from the x1+merged plan ({len(planned)})')

    def _v8_zones(self, ck, glob):
        """per converted zone: resolve every sound name the zone can play with XMen2.exe's lookup (simlookup)
        against the banks it loads; a miss that XML1's own banks resolved for the same zone is a regression of
        the conversion, one XML1 missed too is inherited."""
        table, x1b = self.banks, self.x1banks
        st = self.stats()
        sounddir = {n: (el.get('sounddir') or '').strip() for n, (_, el) in st['by_name'].items()}
        x1_sd = {n: (el.get('sounddir') or '').strip() for n, (_, el) in self.x1_stats().items()}
        tot_names = tot_ok = tot_inh = tot_ok_x1 = 0
        per_zone, regress_all = {}, collections.Counter()
        inherited_all = collections.Counter()
        for z in self.converted_zones():
            world, _ = self.zone_world(z)
            if world is None:
                continue
            sf = (world.get('soundfile') or '').strip()
            zone_rels, _missing = VSND.zone_banks(table, sf)
            tuples = [table.lookup_tuple(r) for r in zone_rels] + list(glob)
            t = self.tree(f'maps/{z}.chrb')
            chars = [(c.get('name') or '').lower() for c in t.iter('character')] if t is not None else []
            for ch in chars:
                sd = sounddir.get(ch)
                r = table.resolve_bank(sd) if sd else None
                if r is not None:
                    tuples.append(table.lookup_tuple(r))
            x1_tuples = x1b.zone_tuples(sf, [x1_sd.get(ch, '') for ch in chars])
            names = self._zone_sound_names(z, world)
            seen, ok, ok_x1, regress, inherited = set(), 0, 0, [], []
            for nm in names:
                key = nm.replace('\\', '/').lower()
                if key in seen:
                    continue
                seen.add(key)
                in_out = bool(VSND.resolve(nm, sf, tuples)[1])
                in_x1 = bool(VSND.resolve(nm, sf, x1_tuples)[1])
                ok += in_out
                ok_x1 += in_x1
                if in_out:
                    continue
                if in_x1:
                    regress.append(nm)
                    regress_all[key] += 1
                else:
                    inherited.append(nm)
                    inherited_all[key] += 1
            tot_names += len(seen)
            tot_ok += ok
            tot_ok_x1 += ok_x1
            tot_inh += len(inherited)
            per_zone[z] = {'soundfile': sf, 'banks': len(tuples), 'names': len(seen), 'resolved': ok,
                           'regressions': sorted(regress), 'inherited_misses': sorted(inherited)}
            if regress:
                ck.warn(f'{z}: {len(regress)}/{len(seen)} sound names resolve against XML1\'s own banks but not in '
                        f'<out> (conversion lost them): {sorted(regress)[:8]}' + (' ...' if len(regress) > 8 else ''))
        ck.set('sound_names', tot_names)
        ck.set('sound_resolved', tot_ok)
        ck.set('sound_resolved_by_xml1_banks', tot_ok_x1)      # positive control of the XML1-side lookup
        ck.set('sound_misses_inherited', tot_inh)
        if tot_names and tot_ok_x1 == 0:
            ck.warn('no sound name resolves against the original XML1 banks: xml1_xbox/sounds/zsds missing or '
                    'unreadable, so misses cannot be classified (all are reported as inherited)')
        ck.set('sound_misses_regressed', sum(len(v['regressions']) for v in per_zone.values()))
        cov = tot_ok / tot_names if tot_names else 1.0
        cov_x1 = tot_ok / (tot_names - tot_inh) if tot_names - tot_inh else 1.0
        ck.set('sound_coverage_pct', round(100.0 * cov, 2))
        ck.set('sound_coverage_vs_xml1_pct', round(100.0 * cov_x1, 2))
        ck.details['zones'] = per_zone
        ck.details['most_regressed'] = regress_all.most_common(40)
        ck.details['most_inherited'] = inherited_all.most_common(40)
        if tot_inh:
            zs = sorted(z for z, v in per_zone.items() if v['inherited_misses'])
            ck.warn(f'{tot_inh} sound names in {len(zs)} zones resolve neither in <out> nor against XML1\'s own banks '
                    f'(inherited misses, e.g. {[k for k, _ in inherited_all.most_common(4)]}; per zone in '
                    f'details.zones)')
        if tot_names and cov < COVERAGE_MIN:
            ck.warn(f'sound name coverage {100 * cov:.1f}% < {100 * COVERAGE_MIN:.0f}% (research baseline 94.8% loaded '
                    f'every XML1 character bank at once, an upper bound); {tot_inh} of the '
                    f'{tot_names - tot_ok} misses are inherited from XML1, coverage of what XML1 itself resolved is '
                    f'{100 * cov_x1:.1f}%')
        ck.note(f'sound coverage over {len(per_zone)} zones: {tot_ok}/{tot_names} = {100 * cov:.1f}% '
                f'({100 * cov_x1:.1f}% of the names XML1 itself resolved)')

    def _v8_char_events(self, ck):
        """engine-generated character events: XML2 builds 'char/<sounddir>/<event>' (0x438d67) where XML1 built
        'character/<sounddir>/...', so converted banks need the char/ aliases."""
        table, x1b = self.banks, self.x1banks
        st = self.stats()
        x1s = self.x1_stats()
        for name, (fname, el) in sorted(st['by_name'].items()):
            sd = (el.get('sounddir') or '').strip()
            if not sd or name not in x1s:
                continue
            r = table.resolve_bank(sd)
            if r is None:
                continue
            tup = [table.lookup_tuple(r)]
            if any(VSND.resolve(f'char/{sd}/{ev}', None, tup)[1] for ev in CHAR_EVENTS):
                continue
            x1sd = (x1s[name][1].get('sounddir') or '').strip() or sd
            p = x1b.resolve_bank(x1sd)
            had = p is not None and any(VSND.resolve(f'character/{x1sd}/{ev}', None, [x1b.lookup_tuple(p)])[1]
                                        for ev in CHAR_EVENTS)
            if had:
                ck.warn(f'{fname}:{el.get("name")}: bank {sd} resolves none of char/{sd}/{"|".join(CHAR_EVENTS)} '
                        f'although XML1\'s {x1sd} has character/{x1sd}/... events (char/ aliases missing)')
            else:
                ck.count('char_events_inherited')
                ck.details.setdefault('char_events_inherited', []).append(f'{name}: {sd}')
        if ck.counts.get('char_events_inherited'):
            ck.note(f'{ck.counts["char_events_inherited"]} XML1 characters have no pain/death/jump/land sounds '
                    f'in XML1\'s own bank either (details.char_events_inherited)')

    def voice_lines(self, ck):
        """V27 (issue #49; SPEC 53): the voice lines of XML1's characters. XMen2.exe looks
        a character's voice events up as 'char/<voice folder>/<event>' in the global x_voice bank (simlookup.voice_dir:
        wolver_m -> wolver_v), where XML1 looked up 'character/<voice folder>/<event>' in its own x_voice. Every such
        name XML1's bank answers for an XML1 stats entry must answer in <out>'s x_voice (error: the line is silent),
        and with XML1's audio: the merge appends XML1's files after XML2's, so an answer whose file index is below
        the retail x_voice's file count is XML2's line playing in its place (error)."""
        from .lib.simlookup import voice_dir
        table, x1b = self.banks, self.x1banks
        out_rel, x1_path = table.resolve_bank('x_voice'), x1b.resolve_bank('x_voice')
        if out_rel is None or x1_path is None:
            ck.warn(f'x_voice missing ({"<out>" if out_rel is None else "XML1 disc"}): voice lines not checked')
            return
        try:
            root = self.ctx.read_x1_xml('data/shared_sounds.xml')
        except KeyError:
            root = None
        events = sorted({v.strip().lower() for el in (root.iter() if root is not None else ())
                         for v in el.attrib.values() if v.strip()})
        if not events:
            ck.warn('XML1 data/shared_sounds.xml has no event names: voice lines not checked')
            return
        out_files = VSND.sound_files(self.ctx.out_index.path(out_rel))
        base_path = self.ctx.base_index.path(out_rel)
        base_files = VSND.file_count(base_path) if base_path is not None else 0
        out_tup, x1_tup = [table.lookup_tuple(out_rel)], [x1b.lookup_tuple(x1_path)]
        st, x1s = self.stats(), self.x1_stats()
        folders = {}                                  # out voice folder -> (XML1 voice folder, first stats name)
        for name, (_, el) in sorted(st['by_name'].items()):
            sd = (el.get('sounddir') or '').strip()
            if not sd or name not in x1s:
                continue
            x1sd = (x1s[name][1].get('sounddir') or '').strip() or sd
            folders.setdefault(voice_dir(sd), (voice_dir(x1sd), name))
        silent, xml2_wins = collections.defaultdict(list), collections.defaultdict(list)
        for vd, (x1vd, name) in sorted(folders.items()):
            ck.count('voice_folders')
            for ev in events:
                if not VSND.resolve(f'character/{x1vd}/{ev}', None, x1_tup)[1]:
                    continue
                ck.count('voice_names')
                full, bank, _ = VSND.resolve(f'char/{vd}/{ev}', None, out_tup)
                if not bank:
                    silent[vd].append(ev)
                    continue
                fi = VSND.answer_file(out_files, full)
                if fi is not None and fi < base_files:
                    xml2_wins[vd].append(ev)
                else:
                    ck.count('voice_names_xml1')
        for vd, evs in sorted(silent.items()):
            ck.error(f'{folders[vd][1]}: x_voice answers none of char/{vd}/{"|".join(evs[:6])}'
                     f'{" ..." if len(evs) > 6 else ""} ({len(evs)} events) although the XML1 x_voice has '
                     f'character/{folders[vd][0]}/... (the voice lines are silent)')
        for vd, evs in sorted(xml2_wins.items()):
            ck.error(f'{folders[vd][1]}: char/{vd}/{"|".join(evs[:6])}{" ..." if len(evs) > 6 else ""} '
                     f'({len(evs)} events) answer with the X-Men Legends II line, not the XML1 one')
        ck.note(f'{ck.counts.get("voice_names_xml1", 0)}/{ck.counts.get("voice_names", 0)} XML1 voice names in '
                f'{len(folders)} voice folders answer with the XML1 line')

    def _zone_sound_names(self, z, world):
        """names the zone can play: 'sound' attributes of the zone file and the registered conversations its
        package lists (the research baseline), and sound("PLAY_SOUND", name, ...) / playBossSound literals in
        its zone script, packaged scripts and inline zone code."""
        names = []
        zf = f'maps/{z}.engb' if f'maps/{z}.engb' in self.scan.files else f'maps/{z}.xmlb'
        names += self.scan.sounds.get(zf, [])
        ents = self.zone_pkg(z) or []
        refs = set()
        for kind, fn in ents:
            if not fn:
                continue
            if kind in ('xml', 'xml_resident'):
                for c in (C.package_entry_files(kind, fn) or []):
                    n = C.norm(c)
                    if n in self.scan.sounds and n.startswith('conversations/'):
                        names += self.scan.sounds[n]
                        break
            elif kind == 'script':
                refs.add(_script_ref(fn))
        zs = world.get('zonescript')
        if zs:
            refs.add(_script_ref(zs))
        for ref in refs:
            res = self.script(f'scripts/{ref}.py')
            if res is not None:
                names += VSND.script_sound_names(res)
        for code in self._zone_inline_code(z):
            names += VSND.script_sound_names(self.checker.check_inline(code))
        return names

    def _zone_inline_code(self, z):
        n = f'maps/{z}.engb' if f'maps/{z}.engb' in self.scan.files else f'maps/{z}.xmlb'
        return [code for _, _, code in self.scan.inline.get(n, [])]

    # ================================================================== V9 movies
    def movie_name(self, x1_name):
        """media.movie_name if media.py exists, else the SPEC 5.4 rule: 'x' + name when XML2 ships
        Movies/ntsc/eng/**/<name>.sfd (i101-i105, i107)."""
        try:
            from . import media                        # noqa: WPS433 - optional provider
            fn = getattr(media, 'movie_name', None)
            if fn is not None:
                return fn(self.ctx, x1_name)
        except ImportError:
            pass
        n = x1_name.lower()
        hit = any(k.startswith('movies/ntsc/eng/') and k.endswith(f'/{n}.sfd') for k in self.ctx.base_index.keys())
        return 'x' + n if hit else n

    @staticmethod
    def movie_rel(name):
        n = name.lower()
        return f'movies/ntsc/eng/{n[:1]}/{n[1:2]}/{n}.sfd'

    def v9_movies(self, ck):
        ctx = self.ctx
        sev = ck.warn if self.no_movies else ck.error
        # startMovie literals in installed scripts (+ inline data code)
        uses = collections.defaultdict(set)
        for n in sorted(self.script_set()):
            res = self.script(n)
            if res is None:
                continue
            for c in res.calls:
                if c.name == 'startMovie' and c.args and c.args[0].kind == 'str':
                    uses[str(c.args[0].value)].add((n, self.is_x1(n)))
        for n, lst in self.scan.inline.items():
            for _, _, code in lst:
                for c in self.checker.check_inline(code).calls:
                    if c.name == 'startMovie' and c.args and c.args[0].kind == 'str':
                        uses[str(c.args[0].value)].add((n, self.is_x1(n)))
        renames = {}
        x1_movies = {}
        from . import media as M                      # the .sfd files, or the prepared disc's movies.json
        for p in sorted(M.x1_movie_files(ctx)):
            x1_movies[p.stem.lower()] = p
        for m in x1_movies:
            nm = self.movie_name(m)
            if nm != m:
                renames[m] = nm
        missing = 0
        for name, where in sorted(uses.items()):
            ck.count('movie_refs')
            nl = name.lower()
            srcs = sorted(self.idx.get(w) or w for w, _ in where)
            if nl in renames and any(x1 for _, x1 in where):
                ck.error(f'startMovie("{name}") in XML1 script(s) {srcs[:3]}: XML1\'s {nl} was renamed '
                         f'{renames[nl]} - this plays XML2\'s movie')
            if self.exists(self.movie_rel(nl)):
                continue
            if nl in KNOWN_MISSING_MOVIES:
                ck.allow(f'startMovie("{name}") in {srcs[:3]}: no movie', 'dead missions/*_start.py, never on the XML1 disc')
                continue
            missing += 1
            base_has = self.movie_rel(nl) in ctx.base_index
            sev(f'startMovie("{name}") in {srcs[:3]}: {self.movie_rel(nl)} missing'
                + (' (--no-movies)' if self.no_movies else '') + ('' if base_has or nl in x1_movies or
                                                                  nl in renames.values() else
                                                                  ' and not on the XML1 disc'))
        ck.set('movies_missing', missing)
        # XML1 movie copies (byte-for-byte, C1 stream intact) and XML2's own movies
        if self.no_movies:
            sfd = [k for k in self.idx.keys() if k.endswith('.sfd')]
            for k in sfd[:20]:
                ck.error(f'{self.idx.get(k)}: .sfd present in a --no-movies build')
        else:
            for m, src in sorted(x1_movies.items()):
                rel = self.movie_rel(self.movie_name(m))
                if not self.exists(rel):
                    ck.error(f'XML1 movie {m} -> {rel} missing')
                    continue
                ck.count('x1_movies_present')
                p = self.idx.path(rel)
                if p.stat().st_size != src.stat().st_size:
                    ck.error(f'{self.idx.get(rel)}: size differs from the XML1 source {src} (must be a byte copy)')
                else:
                    with open(p, 'rb') as fh:
                        head = fh.read(0x10000)
                    if b'SofdecStream' not in head:
                        ck.warn(f'{self.idx.get(rel)}: no "SofdecStream" marker in the first 64 KB')
            for k in ctx.base_index.keys():
                if k.endswith('.sfd') and not self.exists(k):
                    ck.error(f'XML2 movie {ctx.base_index.get(k)} missing')
        sh = ctx.shared.get('movie_renames')
        if sh is not None and {k.lower(): v.lower() for k, v in sh.items()} != renames:
            ck.warn(f'ctx.shared movie_renames {sh} differs from the rule-derived {renames}')
        ck.details['renames'] = renames
        # subtitles: xml1_assets/movies/<name>.eng -> Movies/<movie_name>.{XMLB,engb}
        subs = sorted(ctx.x1_rels('movies/'))
        n_sub = 0
        for s in subs:
            if not s.endswith('.eng'):
                continue
            n_sub += 1
            name = self.movie_name(Path(s).stem)
            for ext in ('.xmlb', '.engb'):
                rel = f'movies/{name}{ext}'
                if not self.exists(rel):
                    ck.error(f'subtitles {s} -> Movies/{name}{ext} missing')
                elif rel not in self.reg:
                    ck.error(f'Movies/{name}{ext} is XML2\'s file, not the XML1 subtitles from {s}')
        ck.set('subtitles_expected', n_sub)
        for n in self.reg:
            if n.startswith('movies/') and n.count('/') == 1 and n.endswith(('.xmlb', '.engb')):
                o = n[:-5] + ('.engb' if n.endswith('.xmlb') else '.xmlb')
                if not self.exists(o):
                    ck.error(f'{self.reg[n]["rel"]}: subtitle pair incomplete ({o} missing)')

    # ================================================================== V10 new game
    def v10_new_game(self, ck):
        ctx = self.ctx
        tour = self._tour_doc()
        want = None
        if tour is not None and ctx.opt('tour'):
            want = tour.get('start')
        elif ctx.opt('start_zone'):
            want = C.norm(ctx.opt('start_zone')).removeprefix('maps/')
        for name in ('new_game', 'new_game_hard'):
            rel = f'scripts/menus/{name}.py'
            if not self.exists(rel):
                ck.error(f'Scripts/menus/{name}.py missing (XMen2.exe startFirstMission runs it, 0x4a7c42)')
                continue
            e = self.entry(rel)
            if e is None:
                ck.error(f'Scripts/menus/{name}.py is still XML2\'s (loads the XML2 tutorial); scripts must replace it')
            res = self.checker.check_file_bytes(self.read(rel), x1_output=True)
            for p in res.problems:
                (ck.error if p.severity == 'error' else ck.warn)(p.text(self.idx.get(rel)))
            loads = [c for c in res.calls if c.name in VS.LOAD_FUNCS]
            if not loads:
                ck.error(f'Scripts/menus/{name}.py loads no zone (no loadMapKeepTeam/loadZone call)')
                continue
            last = loads[-1]
            if not last.args or last.args[0].kind != 'str':
                ck.error(f'Scripts/menus/{name}.py: {last.name} target is not a string literal')
                continue
            z = C.norm(str(last.args[0].value)).removeprefix('maps/')
            if not self.exists(f'maps/{z}.xmlb'):
                ck.error(f'Scripts/menus/{name}.py: {last.name}("{z}") but Maps/{z}.XMLB is not in <out>')
            if last.name != 'loadMapKeepTeam':
                ck.note(f'Scripts/menus/{name}.py loads with {last.name} (XML1 loadMap == loadMapKeepTeam)')
            if want and z != want:
                ck.error(f'Scripts/menus/{name}.py loads {z!r}, but the build was asked to start at {want!r}')
            if not any(c.name == 'setCurrentAct' for c in res.calls):
                ck.warn(f'Scripts/menus/{name}.py never calls setCurrentAct (act objectives will not load)')
            ck.details[name] = {'target': z, 'owner': e['owner'] if e else None, 'statements': res.statements}

    # ================================================================== V11 tour
    def _tour_doc(self):
        p = self.ctx.out / '_tour.json'
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {'_invalid': True}

    def v11_tour(self, ck):
        doc = self._tour_doc()
        want = self.ctx.opt('tour')
        if doc is None:
            if want:
                ck.error('--tour given but <out>/_tour.json is missing')
            else:
                ck.status = 'skipped'
            return
        if doc.get('_invalid'):
            ck.error('_tour.json does not parse')
            return
        if not want:
            ck.error('_tour.json exists but this build was not run with --tour (stale tour list)')
        stops = doc.get('stops') or []
        if doc.get('count') != len(stops):
            ck.error(f'_tour.json count {doc.get("count")} != {len(stops)} stops')
        if [s.get('zone') for s in stops] != list(doc.get('order') or []):
            ck.error('_tour.json order[] does not match stops[]')
        if stops and doc.get('start') != stops[0].get('zone'):
            ck.error(f'_tour.json start {doc.get("start")!r} is not the first stop')
        dwell = doc.get('dwell_seconds')
        for i, s in enumerate(stops):
            z, ref, nxt = s.get('zone'), s.get('script'), s.get('next')
            ck.count('stops_checked')
            if s.get('i') != i:
                ck.error(f'stop {i}: i={s.get("i")}')
            exp_next = stops[i + 1]['zone'] if i + 1 < len(stops) else None
            if nxt != exp_next:
                ck.error(f'stop {i} {z}: next {nxt!r} != following stop {exp_next!r}')
            rel = f'scripts/{C.norm(ref or "")}.py'
            if not ref or not self.exists(rel):
                ck.error(f'stop {i} {z}: script Scripts/{ref}.py missing')
                continue
            res = self.script(rel)
            loads = [c for c in res.calls if c.name == 'loadZone']
            if nxt:
                if not loads or not loads[-1].args or str(loads[-1].args[0].value).lower() != nxt:
                    ck.error(f'stop {i} {z}: Scripts/{ref}.py does not loadZone("{nxt}")')
                if not self.zone_exists(nxt):
                    ck.error(f'stop {i} {z}: next zone {nxt} not in <out>')
            elif loads:
                ck.error(f'stop {i} {z}: last stop still calls loadZone')
            waits = [c for c in res.calls if c.name == 'waittimed']
            if not waits:
                ck.error(f'stop {i} {z}: Scripts/{ref}.py has no waittimed')
            elif dwell is not None and waits[0].args and waits[0].args[0].kind == 'num' and \
                    abs(float(waits[0].args[0].value) - float(dwell)) > 1e-3:
                ck.warn(f'stop {i} {z}: waittimed({waits[0].args[0].value}) != dwell {dwell}')
            world, worlds = self.zone_world(z)
            for ext, (w, _) in worlds.items():
                if w is None:
                    ck.error(f'stop {i} {z}: Maps/{z}{ext} has no world entity')
                elif C.norm(w.get('zonescript') or '') != C.norm(ref):
                    ck.error(f'stop {i} {z}: Maps/{z}{ext} zonescript {w.get("zonescript")!r} != {ref!r}')
            if not worlds:
                ck.error(f'stop {i} {z}: Maps/{z} zone file missing')
            ents = self.zone_pkg(z)
            if ents is None:
                ck.error(f'stop {i} {z}: zone package missing')
            elif f'scripts/{C.norm(ref)}' not in {C.norm(fn or '') for k, fn in ents if k == 'script'}:
                ck.error(f'stop {i} {z}: zone package does not list scripts/{ref}')


    # ================================================================== V14 forced teams (SPEC 19)
    _XFIX_CALL = re.compile(r'\b(%s)\s*\(' % '|'.join(sorted(ST.XML2FIX_API)))
    _STR_ARGS = re.compile(r'"([^"]*)"')

    @staticmethod
    def _statements(lines):
        """[(index, stripped statement)] of the non-blank, non-comment lines."""
        out = []
        for i, l in enumerate(lines):
            s = ST._strip_comment(l).strip()
            if s:
                out.append((i, s))
        return out

    def v14_forced_teams(self, ck):
        ctx = self.ctx
        from . import scripts as S                         # noqa: WPS433 - the plan's provider
        mode = C.forced_teams_mode(ctx)
        ck.set('mode', mode)
        # ---- V14a: the API file, and xml2-fix names only in seat builds
        try:
            fns = ctx.research_json(C.XML2FIX_API_JSON)['functions']
        except (OSError, ValueError, KeyError) as e:
            ck.error(f'research/{C.XML2FIX_API_JSON} unreadable ({e})')
            fns = {}
        for name, (ret, args) in ST.XML2FIX_API.items():
            e = fns.get(name)
            if e is None or e.get('ret') != ret or e.get('args') != args:
                ck.error(f'V14a: research/{C.XML2FIX_API_JSON} {name}: {e} (scripts_transform.XML2FIX_API: {ret}({args}))')
            elif mode == 'seat' and ctx.xml2_api.get(name, {}).get('args') != args:
                ck.error(f'V14a: {name} is not merged into the script API of this seat build')
        rels = sorted(r for r in self.script_set() if self.exists(r) and self.is_x1(r))
        texts = {r: self.read(r).decode('latin-1').split('\r\n') for r in rels}
        uses = {r: [(i + 1, m.group(1)) for i, s in self._statements(ls) for m in self._XFIX_CALL.finditer(s)]
                for r, ls in texts.items()}
        uses = {r: u for r, u in uses.items() if u}
        ck.set('scripts_with_xml2fix_calls', len(uses))
        if mode != 'seat':
            for r, u in sorted(uses.items()):
                menu_only = [(ln, fn) for ln, fn in u if fn not in ST.XML2FIX_DATA_FUNCS]
                if menu_only:
                    ck.error(f'V14a: {self.idx.get(r)}:{menu_only[0][0]}: {menu_only[0][1]}() in a --forced-teams menu build')
        uses = {r: [(ln, fn) for ln, fn in u if fn not in ST.XML2FIX_DATA_FUNCS] for r, u in uses.items()}
        uses = {r: u for r, u in uses.items() if u}
        sc = self.scan
        for table in (sc.inline, sc.runscripts):
            for n, lst in self.data_items(table):
                for item in lst:
                    code = item[2] if isinstance(item, tuple) else item
                    for m in self._XFIX_CALL.finditer(code or ''):
                        if m.group(1) in ST.XML2FIX_DATA_FUNCS:
                            continue             # SPEC 32: the SKILL item's addSkillPoints (inert without the DLL)
                        ck.error(f'V14a: {sc.files[n]["rel"]}: xml2-fix call in inline data code {code[:80]!r} (the '
                                 f'pipeline only emits them in script files, behind their guard)')
        plan = S.forced_party_plan(ctx)
        unseat = sorted(m for m, r in plan.items() if r['status'] == 'menu')
        cut = sorted(m for m, r in plan.items() if r['status'] == 'cut')
        ck.set('forced_party_unseatable', len(unseat))
        ck.set('forced_party_cut_zone', len(cut))
        ck.details['plan'] = {m: {k: r[k] for k in ('status', 'seat', 'costume', 'heroes', 'zone')}
                              for m, r in plan.items() if r['forced']}
        self._v14g_cut_starts(ck, S, cut, texts)
        self._v14h_join_popups(ck, S, texts)
        if unseat or cut:
            ck.warn(f'V14g: {len(unseat)} forced missions keep the team menu (a seat name is not a herostat hero): '
                    f'{unseat}; {len(cut)} forced missions load a zone XML1 never shipped: {cut}')
        if mode != 'seat':
            return
        # ---- V14b: every xml2-fix call behind its guard
        for r in sorted(uses):
            for ln, d in ST.xml2fix_guard_problems(texts[r]):
                ck.error(f'V14b: {self.idx.get(r)}:{ln}: {d}')
        # ---- V14c / V14d: seat blocks and skinsets
        herostat = {}
        st = self.stats()['variants']
        for ext in ('.xmlb', '.engb'):                    # engb wins
            for el in (st.get(ext) or {}).get('herostat', []):
                herostat[(el.get('name') or '').lower()] = el
        costumes = ('default',) + tuple(sorted(HERO_COSTUMES))
        seat_count, skin_count = collections.Counter(), collections.Counter()
        for r in sorted(uses):
            lines = texts[r]
            stm = self._statements(lines)
            where = self.idx.get(r) or r
            ref = C.script_ref(r)
            for k, (i, s) in enumerate(stm):
                if s.startswith('setSkinset('):
                    a = self._STR_ARGS.findall(s)
                    mis = self._marker_before(lines, i)
                    if ref == S.SIDE_BEGIN_REF.format(mis or ''):
                        skin_count[mis] += 1
                    if len(a) != 2 or a[0] not in costumes:
                        ck.error(f'V14d: {where}:{i + 1}: {s}: costume must be one of {costumes}')
                        continue
                    for h in [x for x in a[1].split(',') if x]:
                        el = herostat.get(h)
                        if el is None:
                            ck.error(f'V14d: {where}:{i + 1}: {s}: {h} is not a herostat hero of this build')
                        elif a[0] != 'default' and not (el.get(f'skin_{a[0]}') or '').strip():
                            ck.error(f'V14d: {where}:{i + 1}: {s}: {h} has no skin_{a[0]} in this build\'s herostat')
                    p = plan.get(mis or '')
                    if p is not None and ref != 'menus/new_game' and self._v14_in_body(stm, k) and \
                            (a[0], a[1]) != (p['costume'], p['heroes']):
                        ck.error(f'V14d: {where}:{i + 1}: {s} in the start of {mis}: the plan says '
                                 f'setSkinset("{p["costume"]}", "{p["heroes"]}")')
                if s.startswith('seatParty('):
                    self._v14c_seat(ck, S, plan, herostat, lines, stm, k, where, ref, seat_count)
        for m, r in sorted(plan.items()):
            ref = S.SIDE_BEGIN_REF.format(m)
            if not self.exists(f'scripts/{ref}.py'):
                continue
            if skin_count.get(m, 0) != 1:
                ck.error(f'V14d: Scripts/{ref}.py has {skin_count.get(m, 0)} setSkinset for its own start (want 1)')
            if (seat_count.get(ref, 0) == 1) != (r['status'] == 'seat'):
                ck.error(f'V14c: Scripts/{ref}.py has {seat_count.get(ref, 0)} seat blocks; plan status {r["status"]}')
        ck.set('seat_blocks', sum(seat_count.values()))
        self._v14e_sides(ck, S, texts, uses)
        self._v14f_joins(ck, S, texts, uses)

    def _marker_before(self, lines, i):
        """the mission of the nearest '# ( "XML1 beginMission(m)" )' at or above line index i."""
        for j in range(i, -1, -1):
            m = ST.BEGIN_MARKER.match(lines[j].strip())
            if m:
                return m.group('m').strip().lower()
        return None

    @staticmethod
    def _v14_in_body(stm, k):
        """statement k belongs to a forced-team block of a begin body (seat / skinset block), not a pop block."""
        return not any(s.startswith('popParty(') for _, s in stm[k + 1:k + 3])

    def _v14c_seat(self, ck, S, plan, herostat, lines, stm, k, where, ref, seat_count):
        i, s = stm[k]
        prev = [x for _, x in stm[max(0, k - 3):k]]
        nxt = [x for _, x in stm[k + 1:k + 6 + 16]]
        # issue #55: the team-menu branch may first unlock the REQUIRED heroes XML1 only seats (menu_only_unlocks)
        while len(nxt) > 3 and nxt[2] == 'else' and re.fullmatch(r'unlockCharacter\("\w+", "" \)', nxt[3]):
            del nxt[3]
        nxt = nxt[:5]
        want_prev = [f'{ST.FT_VAR} = iadd(0, 0 )', f'{ST.FT_VAR} = xml2fixFeature("{ST.FT_FEATURE}" )',
                     f'if {ST.FT_VAR} == 1']
        z = re.fullmatch(r'loadMapKeepTeam\("([^"]+)" \)', nxt[1]) if len(nxt) > 1 else None
        z2 = re.fullmatch(r'loadMapChooseTeam\("([^"]+)" \)', nxt[3]) if len(nxt) > 3 else None
        if [ST._canon(x) for x in prev] != want_prev or len(nxt) < 5 or not nxt[0].startswith('setSkinset(') or \
                z is None or nxt[2] != 'else' or z2 is None or nxt[4] != 'endif' or z.group(1) != z2.group(1):
            ck.error(f'V14c: {where}:{i + 1}: {s} is not in the seat block shape (feature detect; seatParty, setSkinset, '
                     f'loadMapKeepTeam(z); else loadMapChooseTeam(z); endif)')
            return
        names = self._STR_ARGS.findall(s)
        zone = C.norm(z.group(1))
        filled = [n for n in names if n]
        if len(names) != 4 or not filled or names[:len(filled)] != filled or len(set(filled)) != len(filled):
            ck.error(f'V14c: {where}:{i + 1}: {s}: 4 names, compact, no duplicates, at least one')
        for n in filled:
            if n not in herostat:
                ck.error(f'V14c: {where}:{i + 1}: {s}: {n} is not a herostat hero of this build (seatParty would '
                         f'refuse the whole party)')
        if not self.exists(f'maps/{zone}.xmlb'):
            ck.error(f'V14c: {where}:{i + 1}: the seat block loads {zone}, which has no Maps/{zone}.XMLB')
        if ref in ('menus/new_game', 'menus/new_game_hard'):
            want = [h.strip().lower() for h in str(self.ctx.opt('start_party') or '').split(',') if h.strip()]
            if filled != want:
                ck.error(f'V14c: {where}:{i + 1}: {s}: the --start-party hook asked for {want}')
            # as the begin bodies do (decision 7.4), the hook unlocks every seated hero before seating it
            unlocked = {m.group(1).lower() for _, x in stm[:k]
                        for m in [re.fullmatch(r'unlockCharacter\("(\w+)", "" \)', x)] if m}
            locked = [n for n in filled if n not in unlocked]
            if locked:
                ck.error(f'V14c: {where}:{i + 1}: {s}: the --start-party hook seats {locked} without an '
                         f'unlockCharacter("<h>", "" ) above the seat block')
            return
        mis = self._marker_before(lines, i)
        p = plan.get(mis or '')
        if p is None:
            ck.error(f'V14c: {where}:{i + 1}: {s} outside a begin body (no XML1 beginMission marker above it)')
            return
        if p['status'] != 'seat' or filled != p['seat'] or zone != p['zone']:
            ck.error(f'V14c: {where}:{i + 1}: {mis} seats {filled} -> {zone}; the plan says {p["status"]} '
                     f'{p["seat"]} -> {p["zone"]}')
        seat_count[ref] += 1

    def _v14e_sides(self, ck, S, texts, uses):
        """V14e: pushParty / popParty per side mission; popParty last in its branch, alone in the console queue."""
        pushes, pops = collections.defaultdict(list), collections.defaultdict(list)
        senders = tuple(VS.CONSOLE_SENDERS)
        for r, u in sorted(uses.items()):
            lines = texts[r]
            where = self.idx.get(r) or r
            stm = self._statements(lines)
            for k, (i, s) in enumerate(stm):
                if s.startswith('pushParty('):
                    side = next((ST.BEGIN_MARKER.match(lines[j].strip()).group('m').strip().lower()
                                 for j in range(i, len(lines)) if ST.BEGIN_MARKER.match(lines[j].strip())), None)
                    pushes[side].append(where)
                elif s.startswith('popParty('):
                    side = next((ST.SIDE_END_MARKER.match(lines[j]).group('s').strip().lower()
                                 for j in range(i, -1, -1) if ST.SIDE_END_MARKER.match(lines[j])), None)
                    pops[side].append(where)
                    a = self._STR_ARGS.findall(s)
                    if not a or not self.exists(f'maps/{C.norm(a[0])}.xmlb'):
                        ck.error(f'V14e: {where}:{i + 1}: {s}: the fallback zone has no Maps/<zone>.XMLB')
                    if k + 1 >= len(stm) or stm[k + 1][1] not in ('else', 'endif'):
                        ck.error(f'V14e: {where}:{i + 1}: popParty is not the last statement of its branch')
            if any(n == 'popParty' for _, n in u):
                for ln, fn, cnt in L.console_overflows(lines, senders, limit=1):
                    if fn == 'popParty':
                        ck.error(f'V14e: {where}:{ln}: popParty is console command #{cnt} of its script run (the '
                                 f'queue holds 2; the design keeps popParty alone)')
        sides = S._side_plan(self.ctx)
        for s, sp in sorted(sides.items()):
            if sp['push'] and (not pushes.get(s) or not pops.get(s)):
                ck.error(f'V14e: side mission {s}: push sites {pushes.get(s, [])}, pop sites {pops.get(s, [])} '
                         f'(both needed)')
        for s in sorted(set(pushes) | set(pops)):
            if s not in sides or not sides[s]['push']:
                ck.error(f'V14e: {s}: pushParty {pushes.get(s, [])} / popParty {pops.get(s, [])} for a side mission '
                         f'the plan does not seat')
        ck.set('push_sites', sum(len(v) for v in pushes.values()))
        ck.set('pop_sites', sum(len(v) for v in pops.values()))
        ck.details['side_sites'] = {s: {'push': pushes.get(s, []), 'pop': pops.get(s, [])}
                                    for s in sorted(set(pushes) | set(pops))}

    def _v14f_joins(self, ck, S, texts, uses):
        """V14f: addHero / joinHero only in the join scripts, after setGameFlag("x1join", bit, 1 ), before the T7
        fallback ("if x1ah == 0" ... extractionPointChange). joinHero (it queues the reload, restorelastzone 0) is
        assigned to x1ah (the fallback's variable), right after the NPC double's remove, the last statement of its
        branch and the only console command of its run; every join script of a seat build has it."""
        n = collections.Counter()
        senders = tuple(VS.CONSOLE_SENDERS)
        for r, u in sorted(uses.items()):
            names = {name for _, name in u}
            ref = C.script_ref(r)
            where = self.idx.get(r) or r
            bit = S.JOIN_HERO_SCRIPTS.get(ref)
            for fn in ('addHero', 'joinHero'):
                if fn not in names:
                    continue
                if bit is None:
                    ck.error(f'V14f: {where}: {fn} outside the join scripts {sorted(S.JOIN_HERO_SCRIPTS)}')
                    continue
                stm = [s for _, s in self._statements(texts[r])]
                k = next(i for i, s in enumerate(stm) if f'{fn}(' in s)
                if f'setGameFlag("{ST.JOIN_FLAG}", {bit}, 1 )' not in stm[:k]:
                    ck.error(f'V14f: {where}: {fn} before setGameFlag("{ST.JOIN_FLAG}", {bit}, 1 )')
                rest = stm[k + 1:]
                t7 = next((i for i, s in enumerate(rest) if s == f'if {ST.AH_VAR} == 0' and
                           any(x.startswith('extractionPointChange(') for x in rest[i:])), None)
                if t7 is None:
                    ck.error(f'V14f: {where}: {fn} without the "if {ST.AH_VAR} == 0" T7 fallback after it')
                if fn == 'joinHero':
                    hero = (self._STR_ARGS.findall(stm[k]) or [''])[0].lower()
                    d = ST.join_double(hero)
                    if not re.fullmatch(rf'{ST.AH_VAR} = joinHero\("\w+" \)', stm[k]):
                        ck.error(f'V14f: {where}: {stm[k]}: joinHero must set {ST.AH_VAR} (the T7 fallback runs on 0)')
                    if k == 0 or stm[k - 1] != f'remove ( "{d}", "{d}" )':
                        ck.error(f'V14f: {where}: joinHero is not right after remove ( "{d}", "{d}" ) (the reload '
                                 f'respawns the zone; the double must go first)')
                    if not rest or rest[0] != 'endif':
                        ck.error(f'V14f: {where}: joinHero is not the last statement of its branch (it queues the '
                                 f'reload)')
                    for ln, f2, cnt in L.console_overflows(texts[r], senders, limit=1):
                        if f2 == 'joinHero':
                            ck.error(f'V14f: {where}:{ln}: joinHero is console command #{cnt} of its script run '
                                     f'(its reload must be the only command waiting)')
                n[fn] += 1
        by_ref = {C.script_ref(r): r for r in texts}
        for ref in sorted(S.JOIN_HERO_SCRIPTS):
            r = by_ref.get(ref)
            if r is not None and 'joinHero' not in {name for _, name in uses.get(r, ())}:
                ck.error(f'V14f: {self.idx.get(r) or r}: the join has no joinHero branch in this seat build')
        ck.set('addhero_sites', n['addHero'])
        ck.set('joinhero_sites', n['joinHero'])

    def _v14h_join_popups(self, ck, S, texts):
        """V14h (every build): a join script's popup comes before the join (before its setGameFlag("x1join", bit, 1 ))
        with a waittimed as its next statement - the wait runs out only once the player has closed it, so the reload
        or the team menu never has it pending; the join zone's script ends with the late removes of the NPC double
        (if x1j == 1: waittimed / remove, the spawner's instant spawn comes after the guard's own removes)."""
        by_ref = {C.script_ref(r): r for r in texts}
        popup_start = tuple(f'{c}(' for c in VS.POPUP_CALLS)
        for ref, bit in sorted(S.JOIN_HERO_SCRIPTS.items()):
            r = by_ref.get(ref)
            if r is None:
                continue
            where = self.idx.get(r) or r
            stm = [s for _, s in self._statements(texts[r])]
            flag = f'setGameFlag("{ST.JOIN_FLAG}", {bit}, 1 )'
            k = stm.index(flag) if flag in stm else len(stm)
            for i, s in enumerate(stm):
                if not s.startswith(popup_start):
                    continue
                if i > k:
                    ck.error(f'V14h: {where}: {s} after the join bit (show it before the join, then wait)')
                if i + 1 >= len(stm) or not stm[i + 1].startswith('waittimed'):
                    ck.error(f'V14h: {where}: {s} is not followed by a waittimed (the join would run with it up)')
        for zref, bit in sorted(S.JOIN_HERO_ZONE_SCRIPTS.items()):
            zr = by_ref.get(zref)
            if zr is None:
                continue
            zwhere = self.idx.get(zr) or zr
            zst = [s for _, s in self._statements(texts[zr])]
            doubles = sorted({ST.join_double(h) for _, h in ST.JOIN_DOUBLE_SPAWNERS.values()})
            want = ['if x1j == 1'] + [x for w in ST.JOIN_LATE_REMOVE_WAITS for x in
                                      [f'waittimed ( {w} )'] + [f'remove ( "{d}", "{d}" )' for d in doubles]] + ['endif']
            if f'x1j = getGameFlag("{ST.JOIN_FLAG}", {bit} )' not in zst or zst[-len(want):] != want:
                ck.error(f'V14h: {zwhere}: the zone script does not end with the late removes of the NPC double '
                         f'(if x1j == 1 / waittimed / remove ... / endif; the spawner spawns it after the guard)')

    def _v14g_cut_starts(self, ck, S, cut, texts):
        """V14g: conversations / scripts that can start a cut mission (warn)."""
        starts = {S.SIDE_BEGIN_REF.format(m) for m in cut}
        found = []
        for n, lst in self.data_items(self.scan.refs):
            for tag, attr, v in lst:
                if _script_ref(v.strip()) in starts:
                    found.append(f'{self.scan.files[n]["rel"]} <{tag} {attr}="{v}">')
        for r, lines in texts.items():
            ref = C.script_ref(r)
            if ref in starts:
                continue
            text = '\r\n'.join(lines)
            for m in cut:
                if S.SIDE_BEGIN_REF.format(m) in text or f'XML1 beginMission({m})' in text:
                    found.append(f'{self.idx.get(r)} starts {m}')
        ck.set('cut_mission_starts', len(found))
        ck.details['cut_mission_starts'] = found
        if found:
            ck.warn(f'V14g: {len(found)} places can start a cut mission (its zone was never shipped): {found[:6]}')

    # ================================================================== V12 IGB info cache (SPEC 13)
    def v13_actor_slots(self, ck):
        """XMen2.exe keeps every loaded actor skin and animation database in one 40-slot table (0x56ac10; 0x56b1c0
        refuses further loads at 0x56b2c3 without reporting). A character whose own anim DB was refused crashes on
        its first animation (0x5743bb; section 14). Per converted zone the resident estimate (permanent + party +
        zone package + CHRB packages + fightstyle DBs) must stay within what XML2's own zones use (37), and no zone
        package may precache XML1 hero actors that no CHRB character or spawner of the zone uses."""
        from . import actor_budget as AB
        AB.validate(self, ck)

    def v12_igb_cache(self, ck):
        """XMen2.exe keeps every precached IGB in one 200-record CIGBInfoCache2 (ctor 0x56e9c0; precache 0x56ede5
        returns NULL silently when full). A zone package's own map IGB is its last 'model' entry, so a package
        needing more free records than the cache has never loads (the zone bounces back to the previous one).
        With the New Game party ~51 records are resident (permanent 16, items 20, 4 hero packages 15) and the
        zone's NPC packages add 1-8 more before the map model (not counted here; igb_budget.py check reports them):
        > 149 records = error, > 128 = warn. Tile entries must be exactly the tiles the zone's instances name."""
        from . import zones as Z
        ck.set('limit_records', Z.IGB_CACHE_RECORDS)
        ck.set('error_over', Z.IGB_ZONE_ERROR)
        ck.set('warn_over', Z.IGB_ZONE_WARN)
        tile_files = {}

        def folder_files(folder):
            folder = C.norm(folder).strip('/')
            if folder not in tile_files:
                pre = f'models/{folder}/'
                stems = set()
                for a in self.ctx.out_index.under(pre):
                    n = C.norm(a)
                    if n.endswith('.igb') and '/' not in n[len(pre):]:
                        stems.add(n[len(pre):-4])
                for r in self.ctx.x1_rels(pre):
                    if r.endswith('.igb') and '/' not in r[len(pre):]:
                        stems.add(r[len(pre):-4])
                tile_files[folder] = stems
            return tile_files[folder]

        counts = {}
        for z in self.converted_zones():
            ents = self.zone_pkg(z)
            if ents is None:
                continue
            n = Z.igb_records(ents)
            counts[z] = n
            ck.count('zones_checked')
            if n > Z.IGB_ZONE_ERROR:
                ck.error(f'{z}: package precaches {n} IGBs (> {Z.IGB_ZONE_ERROR}); the zone cannot load: XMen2.exe '
                         f'has {Z.IGB_CACHE_RECORDS} IGB-cache records in all and ~51 are resident with the New Game '
                         f'party (SPEC 13)')
            elif n > Z.IGB_ZONE_WARN:
                ck.warn(f'{z}: package precaches {n} IGBs (> {Z.IGB_ZONE_WARN}: little IGB-cache headroom; SPEC 13)')
            # tile entries vs the tiles the zone's tile instances can name (engine naming rule, zones.tile_models_used)
            world_attrs, worlds = self.zone_world(z)
            t = next((tree for w, tree in worlds.values() if tree is not None), None)
            if t is None:
                continue
            tiles = Z.tile_models_used(t, folder_files)
            if not tiles['folders']:
                continue
            listed = {C.norm(fn) for k, fn in ents if k == 'model' and C.norm(fn or '').startswith('models/tiles/')}
            used = set().union(*tiles['used'].values()) if tiles['used'] else set()
            missing = sorted(used - listed)
            extra = sorted(listed - used)
            if missing:
                ck.error(f'{z}: {len(missing)} tile models its instances name are not in the package (loaded on '
                         f'demand into the never-freed group 1): {missing[:5]}')
            if extra and tiles['insts']:
                ck.warn(f'{z}: {len(extra)} tile models in the package that no instance can name (IGB-cache waste, '
                        f'--tiles folder?): {extra[:4]}')
            elif extra:
                ck.note(f'{z}: tileent without parsable instances: whole folder listed ({len(extra)} tiles)')
            ck.count('tile_models_listed', len(listed))
            ck.count('tile_models_used', len(used))
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:10]
        ck.details['largest'] = top
        ck.set('max_records', top[0][1] if top else 0)
        ck.note(f'largest zone packages (IGB-cache records): {top}')


def run(ctx):
    """xml1build step 'validate' (build_xml1.py runs it after the sweep)."""
    v = Validator(ctx)
    v.run_all()
    doc = v.report()
    s = doc['summary']
    ctx.log(f'{s["result"]}: {s["errors"]} errors, {s["warnings"]} warnings, {s["allowed"]} allowlisted '
            f'-> {ctx.build_dir / "validate.json"}')
    return doc


def main(argv=None):
    """Standalone: python -m xml1build.validate --out <dir> [--base ...] [--no-movies] [--tour N] ...
    Validates an existing build using its _build/registry.json (writes _build/validate.json only)."""
    import argparse
    ap = argparse.ArgumentParser(description='validate an existing xml1build output tree')
    ap.add_argument('--out', required=True)
    ap.add_argument('--base', default=str(C.DEFAULT_BASE))
    ap.add_argument('--no-movies', dest='no_movies', action='store_true')
    ap.add_argument('--start-zone', dest='start_zone')
    ap.add_argument('--tour', type=float)
    ap.add_argument('--forced-teams', dest='forced_teams', choices=C.FORCED_TEAMS_MODES, default='seat')
    ap.add_argument('--start-party', dest='start_party')
    ap.add_argument('--frontend', choices=C.FRONTEND_MODES,
                    help='front end the build was made with (default: from its _build/report.json)')
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) // 2))
    a = ap.parse_args(argv)
    recorded = C.args_for_out(a.out, a.base)
    frontend = a.frontend or getattr(recorded, 'frontend', None)
    args = C.default_args(out=a.out, base=a.base, no_movies=a.no_movies, start_zone=a.start_zone, tour=a.tour,
                          jobs=a.jobs, forced_teams=a.forced_teams, start_party=a.start_party, frontend=frontend,
                          buoys=getattr(recorded, 'buoys', None))   # SPEC 42: V22 checks the mode the build used
    reg = C.Registry.load(Path(a.out) / '_build' / 'registry.json')
    ctx = C.BuildContext(a.out, a.base, args=args, registry=reg)
    ok = C.run_step(ctx, 'validate', run)
    ctx.report.print_summary()
    return 0 if ok and not ctx.report.error_total() else 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
