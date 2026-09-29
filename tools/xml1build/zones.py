"""xml1build.zones - convert every XML1 zone into the XML2 PC install (SPEC.md section 5.3).

A hardened port of tools/convert_zone.py (Converter.zone, proven in-game for nyc/alison/nyc1_1_1) that covers
all 210 XML1 zone bundles. Per zone:

  * zone XML (maps/<zone>.eng|.xml) -> Maps/<zone>.XMLB[+.engb] via ctx.import_x1_asset(force, patch):
      map_tree_refs (skins/HUD heads/loading), scripts.rewrite_data_tree (inline code, script refs), world entity
      (zonescript from scripts.zone_script_ref; soundfile < 10 chars - a soundfile none of whose banks exists on
      either disc takes the soundfile of the zone's campaign twin / same-directory zones; music overrides
      noted; a bare world entity is added to the 2 XML1 zones that have none), nextzone/prevzone (backslash ->
      '/', lower case, full path only for cross-directory targets), precache filenames (lowercase '/' paths as
      in XML2, script refs normalised, 'bolton/x' -> 'models/bolton/x'), tilemodelfolder lower case;
  * .chr -> .CHRB (an empty source gives a valid <characters/>), .nav -> .NAVB (empty -> no file, no entry),
    empty <buoy/> .BOYB, map .IGB;
  * Packages/generated/maps/<zone>.PKGB from the bundle entries (in order, de-duplicated) plus the scripts
    module's extras, the zone script and every file the zone XML (and the entity files / conversations it
    packages) references that the bundle lacks: models, effects (with the textures/models/sub-effects inside
    them), the tile models its tile instances can name (SPEC 13: only those, never the whole models/tiles/<x>
    folder - XMen2.exe caches at most 200 IGBs in all), motion paths (XML2 'dir/file/object' form), spawn-entity
    files, scripts, and the
    conversations / popup dialogs the packaged scripts and inline data code start (followed to a fixpoint).
After the zones: Data/zoneinfo.{XMLB,engb}, the world tables Data/{common_ents,item_ents,items,shared_nodes}
with their generated PKGBs, XML1-only additions to Packages/generated/maps/package/permanent.PKGB, and the
XML1 permanent_fightstyles entries XML2 lacks (fightstyle_villain) in maps/package/permanent_fightstyles.PKGB.

XML1-wins text imports (conversations/, dialogs/, subtitles/, data/entities/, motionpaths/) are patched; an
entity file the characters module already imported unpatched is shared when the patched bytes are identical
(all 24 today) and taken over (noted) otherwise.

Character-namespace files (actors, HUD/UI character models, power/fight styles, numeric loading screens) are
owned by the characters module: zones only writes their mapped package entries and checks at the end that
the files exist. Scripts and Dialogs/x1 are owned by the scripts module; zones uses its provider functions
(scripts.rewrite_data_tree / zone_script_ref / zone_package_extras / zone_act / script_exists) and falls back
to tools/xml1build/zones_providers.py when scripts.py is absent or lacks one of them.

SPEC 21 (--frontend xml1, the default): XML1's menu backdrop menu/main_back is converted like any zone (keeping
XML2's nosave / startblack world flags and bigconvmap / npcstat package entries), its zoneinfo entry shows XML1's
x_mansion screen, XML1 named loading screens XML2 also ships are installed as textures/loading/x1_<name>, arena
worlds get nosave, and the Danger Room's 19 reward items join Data/items as XML2 equipment (frontend.py).
--frontend xml2 keeps XML2's backdrop (C.FRONTEND_ZONES) and none of these.

Everything is written through ctx (registry, ownership, format rules). Zones are processed sequentially: every
import runs under ctx's writer lock anyway, and a fixed order keeps the import cache and outputs deterministic.
"""
from __future__ import annotations

import collections
import copy
import math
import os
import re
import types
import xml.etree.ElementTree as ET

from . import common as C
from . import zones_providers as FALLBACK
from . import actor_budget as AB          # section 14: XMen2.exe's 40-slot actor table (skins + anim DBs)
from . import scripts_transform as ST     # section 18: the join zones' NPC double
from . import automaps as AM              # section 26: XML1 automap textures -> Automaps/<zone>.zam

# ---------------------------------------------------------------------------------------------- constants
PATCH_ZONE = 'zones.zone'            # import_x1_asset patch keys (deterministic patches -> cacheable imports)
PATCH_DATA = 'zones.data'
PATCH_CHR = 'zones.chr'

# SPEC 4.4: XML1 wins for these (XML1-mode build; XML2's zones are not played)
FORCE_PREFIXES = ('conversations/', 'dialogs/', 'subtitles/', 'data/entities/', 'motionpaths/')
LANG_SKIP = ('.fre', '.ger')
BOOL_VALUES = frozenset({'', 'true', 'false', '0', '1', 'none', 'null', 'yes', 'no'})

EFFECT_ATTRS = frozenset({'acteffect', 'deatheffect', 'xdeatheffect', 'loopfx', 'ambienteffect', 'splasheffect',
                          'wakeeffect', 'trailfx', 'spawneffect', 'monster_spawneffect', 'monster_deatheffect'})
SPAWN_ATTRS = frozenset({'deathspawn', 'xdeathspawn', 'actspawn', 'monster_deathspawn'})
MUSIC_ATTRS = ('ambientmusic', 'combatmusic', 'intromusic')
# precache types whose filename is a file path (lowercased, '/'); 'sound' names are hashed, 'script' uses script_ref
PRECACHE_PATH_TYPES = frozenset({'motionpath', 'conversation', 'dialog', 'fx', 'model', 'texture', 'xml_resident',
                                 'xml', 'subtitle'})
LINK_ATTRS = ('nextzone', 'prevzone')
CORE_KINDS = frozenset({'characters', 'zonexml', 'nav'})
XML_KINDS = frozenset({'xml', 'xml_resident'})
# world attributes never carried over from a replaced XML2 zone (geometry/sound/script are XML1's)
BASE_WORLD_SKIP = frozenset({'name', 'extent_min', 'extent_max', 'zonescript', 'soundfile'})
# XML1 items appended to XML2's items table (only the ones converted content names in inventoryitem) keep only
# attributes XML2's own non-equipment items use; XML1 frequency / group / numeric class+quality / unique and the
# <activepowerup> children are never read by XMen2.exe (whole-string search; item parser 0x47aeff).
ITEM_KEEP_ATTRS = ('name', 'displayname', 'description', 'model', 'cost', 'onactivate', 'activateonpickup')
# XML1 pickup types XMen2.exe does not have (its types are item/potion/equipment/money, 0x47af1a..0x47af85):
# the pickup becomes an 'item' that activates on pickup and runs the XML2 script call closest to its XML1
# effect. XP / skill amounts are engine-defined in XML1 (not in data): 5000 XP is in the range XML2 retail
# scripts award (awardXPToPlayable 2000..40000) and is a tuning value, as is the stat XML2 boosts.
ITEM_TYPE_MAP = {
    'xp': ('item', {'activateonpickup': 'true', 'onactivate': 'awardXPToPlayable(5000)'},
           "XML1 'xp' pickup -> awardXPToPlayable(5000) (XML2 has no xp item type; --xp-curve xml2: an XML2-scaled "
           "tuning value; --xp-curve xml1 gives each pickup its own XP_<count> item, XP_PICKUP_SCRIPT)"),
    'stat': ('item', {'activateonpickup': 'true', 'onactivate': "permanentStatBoost('_ACTIVATOR_','body')"},
             "XML1 free stat point -> permanentStatBoost('_ACTIVATOR_','body'), XML2's stat-booster call "
             "(e.g. Maps/Act1/genosha/genosha3); XML2 has no stat item type or free-stat-point call"),
    'skill': ('item', {'activateonpickup': 'true', 'onactivate': 'awardXPToPlayable(5000)'},
              "XML1 free skill point -> awardXPToPlayable(5000): XML2 has no skill item type and no skill-point "
              "call ('skill' is not an XMen2.exe string); XP is what grants skill points in XML2"),
}
# SPEC 23.1: XML1's XP pickups (hive2_2_4 item_xp01 count 300000, wx2_1 count 30000). default.xbe reads the
# inventoryent's count as the amount (0x7d3c0 -> +0x2c8) and gives it as XP to the hero who picks it up (0x7dc41:
# 0x33170, the actor's own XP gain scaled by its xp affecter, then the "+N" popup 0x2fcf0) - not to the roster. With
# --xp-curve xml1 every XP pickup names its own item XP_<count> (items_to_add) whose onactivate gives that XP to the
# activator: setXP (0x4a8660) -> the actor's XP gain 0x422350 + the popup 0x41f5a0; '_ACTIVATOR_' in an item's
# onactivate is XML2 retail's own form (HEALTH_ITEM, SKIRMISH_KING_PIP). XMen2.exe reads inventoryent count as a
# 16-bit item quantity (0x47a970, default 1; 300000 wraps to -27680), so an XP pickup's count becomes 1 in both modes
# (XML1's count is XP, not a quantity). --xp-curve xml2 keeps the one XP item and ITEM_TYPE_MAP's 5000.
XP_PICKUP_ITEM = '{item}_{amount}'
XP_PICKUP_SCRIPT = "setXP('_ACTIVATOR_',{amount})"
SOUNDFILE_MAX = 10                   # XMen2.exe 0x5920cb: strlen >= 10 aborts zone sound loading
SAVENAME_MAX = 63                    # zoneinfo savename copied into a 0x40 buffer (0x4850d5)
# zoneinfo attributes of XML2's Xtraction network (0x468130 registers extraction="true", 0x467f60 parses the rest);
# stripped from every XML2 entry in XML1 mode (build_zoneinfo)
XTRACTION_ATTRS = ('extraction', 'towncenter', 'mapx', 'mapy')
# False: stripping them crashes XMen2.exe at boot (no town centre for the act; see build_zoneinfo)
STRIP_XTRACTION = False
# ---- section 15: act town centres. Entering any zone runs 0x4867e0 (world object 0x72a578), which passes the town
# centre of the current act (game+0x5e0 via vtbl 0x686e1c+0x274 = 0x469c30) - Xtraction table vtbl 0x686dac+0x14 =
# 0x4682b0: the first registered entry whose act byte (+8) matches and whose towncenter bit (+9 bit 1) is set, else
# NULL - straight to _stricmp (0x486844) against the zone name being entered (0x72a758); the pause menu compares the
# same pair without a NULL test (0x5cc0f0). So every act the game can select needs one zoneinfo entry with
# extraction="true" (0x468130 registers only those) and towncenter="true" (0x467f60), and the table holds at most 31
# entries (0x46817d: registration stops silently at count 0x1f). XML2's 5 town centres (acts 1-5) stay (boot proven);
# its 25 other destinations lose the network attributes to make room (XTRACTION_STRIP_XML2_DESTINATIONS), and every
# further selectable act (the mission plan uses 1..9) gets an XML1 hub zone as its town centre (act_towncenters).
XTRACTION_CAP = 31
XTRACTION_STRIP_XML2_DESTINATIONS = True
TOWNCENTER_HUB_RE = re.compile(r'^mansion/man\d+[a-z]?/mansion\d+[a-z]?_1$')   # X-Mansion ground floor of a visit
TOWNCENTER_MAP_XY = ('0.12', '0.11')  # where XML2 draws its own X-Mansion (act4/mansion/mansion1) on the world map
TOWNCENTER_SAVENAME = 'X-Mansion'     # XML1 zoneinfo.eng savename of the 11 mansion zones that carry one
# ---- end section 15
# ---- section 16: the per-zone animation DB. XMen2.exe attaches one extra anim DB to every actor of a zone: 0x486710
# takes the zone name (world+0x1e0), keeps the text after the last '/', formats "zone_%s" (0x688d78) into world+0x160
# and asks the actor manager (0x56b8e0, vfunc +0xc) whether a resource of exactly that name is resident (key "%i:%s",
# 0x5647f0); when it is not, the name falls back to "zone_shared" (0x681968, XML2's global DB). XML2 ships one
# Actors/zone_<leaf>.igb per zone (75 files). XML1 shipped one mission_<area>.igb per area, listed as actoranimdb by
# every zone of the area; XMen2.exe never attaches it, so every EA_ZONEn clip (XML1 EA_MISSIONn: sitting, talking,
# looting, briefing poses) resolved to nothing and the NPC played the wrong clip (the "punching" bystanders).
# The resource name must be the bare stem: an entry 'actors/zone_x/zone_<leaf>' loads but is keyed by that string and
# is not found (in-game A/B 2026-09-27: mansion4_1 civilians sit with 'zone_mansion4_1', crouch/lunge with
# 'mission_man4' or 'actors/zone_x/zone_mansion4_1'). Fix: the zone package lists 'zone_<leaf>' instead of
# 'mission_<area>' and Actors/zone_<leaf>.IGB is the area's mission DB with its clips renamed missionN -> zoneN
# (characters.rename_mission_anims_igb). Zones sharing a leaf AND an area (demo/ copies) share the file; zones sharing
# a leaf but not the area (astral1_1, astral1_3, muir_brig, subbasement4) cannot both be served by one file name: the
# zone whose bundle scripts use more zone animations wins, the other keeps the zone_shared fallback (warned; a zone
# rename would fix it). An XML1 leaf equal to an XML2 zone (dr_mag03) overwrites XML2's unreachable zone DB.
ZONE_ANIMDB_PREFIX = 'zone_'
MISSION_ANIMDB_RE = re.compile(r'^mission_[a-z0-9_]+$')
_EA_ZONE_USE = re.compile(r'\bEA_(?:ZONE|MISSION)\d+\b|\bEA_TALKING_\d+\b|[\'"](?:zone|mission)\d+[\'"]')
# ---- end section 16

# ---- IGB info cache (section 13). XMen2.exe keeps every precached IGB (package 'model' entries, motion-path files,
# effect models, HUD heads, on-demand model loads) in one global CIGBInfoCache2 pool of 200 records (ctor 0x56e9c0:
# 'mov edx,0xc7' / 'cmp eax,0xc8'; precache 0x56ede5: 'cmp [this+0x73ec],0xc8; jge -> return 0', no message).
# The zone's own map IGB is the last 'model' entry of its package, so a zone whose package needs more records
# than are free never gets its playfield: 'Loading Zone igb...' fails and CMap re-requests the previous zone
# (0x4854ac-0x4854c7). Records resident outside the zone group: maps/package/permanent (16), items (20) and the 4
# hero packages (3-5 each) = 51 with XML2's New Game party (observed budget: 145 loads, 153 fails).
IGB_CACHE_RECORDS = 200
IGB_ZONE_ERROR = 149          # > this: the zone cannot load with the New Game party (observed)
IGB_ZONE_WARN = 128           # > this: no headroom for bigger hero packages, the team menu (22 heads) or on-demand loads
# tile models (CTileEntity): an instance 'T_<folder>_<S><H><T>_<F|W>_<V><d>' is drawn with
# models/tiles/<folder>/<folder>_<sht>_<fw>_<v><d> (0x4c2460 sprintf "%s_%c%c%c_%c_%c%d"); a breakable tile also names
# the other variant letters of its shape (0x4c2b52-0x4c2ba4) and, for size letters C..E, the '<S>A<T>' shape
# (0x4c2400 / 0x4c2bc1). Nothing else names a tile model, so a zone package need list only these (XML1's bundles list
# whole letter sets, XML2's tool the whole folder: 23-30 files in XML2, up to 98 in XML1).
_TILE_INST = re.compile(r'^t_([a-z0-9]+)_([a-z0-9])([a-z0-9])([a-z0-9])_([fw])_([a-z])([0-9]+)$')
_TILE_FILE = re.compile(r'^([a-z0-9]+)_([a-z0-9])([a-z0-9])([a-z0-9])_([fw])_([a-z])([0-9]+)$')
TILE_MODES = ('used', 'folder')     # --tiles / XML1BUILD_TILES: 'folder' = the pre-section-13 whole-folder listing

_UI_CHAR_X1 = re.compile(r'^(?:hud/hud_head_|ui/hud/characters/|ui/models/characters/)\d{4}$')
_UI_CHAR_ANY = re.compile(r'(?i)^(?:.*/)?(?:hud_head_|ui/hud/characters/|ui/models/characters/)\d{4,5}$')
_LOADING_X1 = re.compile(r'^textures/loading/\d{4}$')
_LOADING_NUM = re.compile(r'^textures/loading/\d{4,5}$')
_SKIN = re.compile(r'^\d{4,5}$')
_PATHLIKE = re.compile(r'^[A-Za-z0-9_\-]+(?:[/\\][A-Za-z0-9_\-]+)*(?:\.py)?$')   # a script/file ref, not code
_QUOTED = re.compile(r'"([^"\r\n]*)"|\'([^\'\r\n]*)\'')
_CAM_MP = re.compile(r'cameraFollowMotionPath\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']', re.I)
# script calls whose first literal argument names a data file the zone package must list (XML2 retail packages
# every conversation its zone scripts start, 384 of 384): (regex, directory, package kind)
CALL_TARGETS = ((re.compile(r'startConversation\s*\(\s*["\']([^"\'()]+)["\']', re.I), 'conversations/', 'xml'),
                (re.compile(r'createPopupDialogXml\s*\(\s*["\']([^"\'()]+)["\']', re.I), 'dialogs/', 'xml_resident'))
_CALL_ANY = re.compile(r'startConversation|createPopupDialogXml', re.I)
_IGB_MP = re.compile(rb'([Mm][Pp]_[A-Za-z0-9_]{1,40})\x00')   # XML1 also has 'MP_table', 'MP_1_7_2'


# ---------------------------------------------------------------------------------------------- helpers
def load_providers(ctx):
    """scripts-module provider functions (SPEC 5.0), falling back to zones_providers per missing function."""
    try:
        from . import scripts as S                                   # noqa: F401 (written by the scripts owner)
    except ModuleNotFoundError as e:
        if e.name not in ('xml1build.scripts', __package__ + '.scripts'):
            raise
        S = None
    prov, used = types.SimpleNamespace(), {}
    for name in ('rewrite_data_tree', 'zone_script_ref', 'zone_package_extras', 'zone_act', 'script_exists'):
        fn = getattr(S, name, None) if S is not None else None
        used[name] = 'scripts' if callable(fn) else 'zones_providers (fallback)'
        setattr(prov, name, fn if callable(fn) else getattr(FALLBACK, name))
    return prov, used


# ---- section 17: instance extents. XML1 writes an <inst>'s `extents` as the WORLD-space axis-aligned box of the
# rotated entity (10,635 of 10,642 XML1 insts contain their own pos; the same entity type at 0 and 90 degrees has
# swapped dimensions in 106 of 122 cases). XMen2.exe reads `extents` as the box in the ENTITY's own frame, relative
# to pos and rotated with `orient` (inst parser 0x461e3e: "%f %f %f %f %f %f", then pos, then orient; XML2 retail:
# 7,782 relative / 0 absolute, and the same type keeps identical dimensions at 0 and 90 degrees in 92 of 93 cases).
# Unconverted, every XML1 trigger box (subway stairs, zone links, touch triggers) sat far outside the map, so
# walking into them did nothing (Owen, 2026-09-27: nyc1_1_1's subway "just looked dead"; zone exits never fire).
# Conversion: offset by -pos, rotate back by -orient z; half sizes recovered exactly from the world AABB of the
# rotated box (hx_w = hx|c| + hy|s|, hy_w = hx|s| + hy|c|) except near 45 degrees, where the world half sizes are
# kept (a slightly larger box). Insts rotated about x/y (189, props/effects) keep world half sizes, centre offset only.
EXTENTS_DET_MIN = 0.2      # |cos 2theta| below this (within ~6 degrees of 45) -> conservative fallback


def x1_extents_to_local(pos, orient, extents):
    """XML1 world-space `extents` of an inst at `pos`/`orient` -> XML2 entity-local `extents` (strings in, string
    out) plus the method used: 'offset' | 'rot90' | 'solved' | 'fallback45' | 'fallback_xy' | None (unparseable)."""
    try:
        p = [float(v) for v in pos.split()]
        e = [float(v) for v in extents.split()]
        o = [float(v) for v in (orient or '0 0 0').split()]
    except ValueError:
        return extents, None
    if len(p) != 3 or len(e) != 6 or len(o) != 3:
        return extents, None
    cw = [(e[i] + e[i + 3]) / 2 - p[i] for i in range(3)]
    hw = [(e[i + 3] - e[i]) / 2 for i in range(3)]
    if abs(o[0]) > 1e-3 or abs(o[1]) > 1e-3:
        lc, lh, how = cw, hw, 'fallback_xy'
    else:
        t = o[2]
        c, s = math.cos(t), math.sin(t)
        lc = [c * cw[0] + s * cw[1], -s * cw[0] + c * cw[1], cw[2]]          # Rz(-theta) . world offset
        ac, as_ = abs(c), abs(s)
        if as_ < 1e-4:
            lh, how = hw, 'offset'
        elif ac < 1e-4:
            lh, how = [hw[1], hw[0], hw[2]], 'rot90'
        else:
            det = ac * ac - as_ * as_
            hx = (ac * hw[0] - as_ * hw[1]) / det if abs(det) >= EXTENTS_DET_MIN else -1
            hy = (ac * hw[1] - as_ * hw[0]) / det if abs(det) >= EXTENTS_DET_MIN else -1
            if hx >= 0 and hy >= 0:
                lh, how = [hx, hy, hw[2]], 'solved'
            else:
                lh, how = hw, 'fallback45'
    out = [lc[i] - lh[i] for i in range(3)] + [lc[i] + lh[i] for i in range(3)]
    return ' '.join(f'{v:.6g}' for v in out), how


def convert_inst_extents(root):
    """Rewrite every <inst extents> of a zone tree in place (section 17). Returns Counter of methods."""
    counts = collections.Counter()
    for inst in root.iter():
        if inst.tag.lower() != 'inst':
            continue
        ext, pos = inst.get('extents'), inst.get('pos')
        if not ext or not pos:
            continue
        new, how = x1_extents_to_local(pos, inst.get('orient'), ext)
        counts[how or 'unparsed'] += 1
        if how:
            inst.set('extents', new)
    return counts
# ---- end section 17


# ---- section 18: the join zones' NPC double. nyc1_1_3 / mag_nyc4 spawn the hero who joins there (Cyclops) as an NPC
# named after the hero (monster_name=cyclops). The join reloads the zone with him in the party, and XML2 names party
# heroes after their herostat entry, so the respawned double and the hero shared a name: remove("cyclops") removed
# both (in game, 2026-09-28). The double gets its own name here; the join script and the zone guard remove it by it
# (scripts_transform.JOIN_DOUBLE_SPAWNERS / join_double).
def rename_join_double(zone, root):
    """-> number of spawners whose monster_name was renamed to the join double's name (0 outside the join zones)."""
    spec = ST.JOIN_DOUBLE_SPAWNERS.get(zone.lower())
    if not spec:
        return 0
    spawner, hero = spec
    n = 0
    for el in root.iter():
        if el.tag.lower() == 'entity' and (el.get('name') or '').lower() == spawner and \
                (el.get('classname') or '').lower() == 'monsterspawnerent' and (el.get('monster_name') or '').lower() == hero:
            el.set('monster_name', ST.join_double(hero))
            n += 1
    return n


# The join zones' per-hero starts: player_start01 (slot 2) is startenabled="false" and only the join trigger's
# acttargets enable_target01 enables it, for that load. Every later load of the zone (save/load, re-entry,
# loadMapKeepTeam) has it disabled again, so the joined hero had no start and did not spawn (in game, 2026-09-28
# night: Wolverine alone, Cyclops seated in slot 1). Before the join the party has one hero, so a slot-2 start is
# unused and can be enabled from the start (verified in game with startenabled=true edited into the zone).
def enable_join_starts(zone, root):
    """-> number of playerstartent entities with slot >= 2 and startenabled="false" set to "true" in a join zone
    (scripts_transform.JOIN_DOUBLE_SPAWNERS); 0 elsewhere."""
    if zone.lower() not in ST.JOIN_DOUBLE_SPAWNERS:
        return 0
    n = 0
    for el in join_hero_starts(root):
        if (el.get('startenabled') or '').strip().lower() == 'false':
            el.set('startenabled', 'true')
            n += 1
    return n


def join_hero_starts(root):
    """the playerstartent entities for a party member after the leader (slot 2..4)."""
    out = []
    for el in root.iter():
        if el.tag.lower() == 'entity' and (el.get('classname') or '').lower() == 'playerstartent':
            try:
                slot = int((el.get('slot') or '0').strip())
            except ValueError:
                continue
            if slot >= 2:
                out.append(el)
    return out


def rename_npc_doubles(zone, root):
    """section 18, the other same-name NPCs (scripts_transform.NPC_DOUBLE_SPAWNERS: zones whose party can hold the
    hero while a script addresses the NPC by that name) -> (spawners renamed, [(spawner, hero) not found]). The
    zone's scripts follow in scripts._script_text (scripts_transform.rename_npc_refs)."""
    spec = ST.NPC_DOUBLE_SPAWNERS.get(zone.lower())
    if not spec:
        return 0, []
    done = set()
    for el in root.iter():
        if el.tag.lower() != 'entity' or (el.get('classname') or '').lower() != 'monsterspawnerent':
            continue
        sp = (el.get('name') or '').lower()
        hero = spec.get(sp)
        if hero and (el.get('monster_name') or '').lower() == hero:
            el.set('monster_name', ST.join_double(hero))
            done.add(sp)
    return len(done), [(sp, h) for sp, h in sorted(spec.items()) if sp not in done]


def rename_npc_inline_refs(zone, root):
    """section 18.1: the zone's own inline code (spawnscripts, actscripts ...: any attribute value with a call) names
    the renamed NPCs by the double's name, like its scripts (scripts_transform.rename_npc_refs; muir_in2's
    sp_colossus01 monster_spawnscript setEnable('colossus', 'FALSE' )). Runs after rewrite_data_tree (whose exact-
    value inline rewrites are keyed by XML1's text). -> number of literals renamed (0 outside NPC_DOUBLE_SPAWNERS)."""
    spec = ST.NPC_DOUBLE_SPAWNERS.get(zone.lower())
    if not spec:
        return 0
    heroes = set(spec.values())
    n = 0
    for el in root.iter():
        for k, v in list(el.attrib.items()):
            if v and '(' in v:
                (nv,), m = ST.rename_npc_refs([v], heroes)
                if m:
                    el.set(k, nv)
                    n += m
    return n
# ---- end section 18


# ---- section 25: one-position hero starts spawn the whole party. XMen2.exe spawns party hero n at the n-th <inst> of
# a playerstartent, or at the start whose `slot` is n; a start marked allinone="true" takes the whole party at its one
# position (XML2's own zones: 209 one-inst starts, all allinone; its 18 unmarked starts have 4 insts). XML1 has no
# allinone and puts every hero at a one-inst start, so 233 of its starts spawned only the leader: in game (build/_nb2,
# 2026-09-28) Wolverine + Cyclops seated, nyc1_1_2 loaded Wolverine alone; with allinone both. Starts with a slot
# (per-hero starts: astral, nyc1_1_3, arenas) and starts with 2+ insts (sized for their mission's party: nyc1_1_4,
# wx3_*) stay as XML1 wrote them; nyc1_1_5's slot-1 start with 2 insts spawned both heroes.
def mark_allinone_starts(root):
    """-> number of playerstartent entities given allinone="true" (no slot, at most one <inst>)."""
    starts = [el for el in root.iter() if el.tag.lower() == 'entity' and
              (el.get('classname') or '').lower() == 'playerstartent' and el.get('slot') is None and
              el.get('allinone') is None]
    if not starts:
        return 0
    insts = collections.Counter((el.get('name') or '').lower() for el in root.iter() if el.tag.lower() == 'inst')
    n = 0
    for el in starts:
        if insts[(el.get('name') or '').lower()] <= 1:
            el.set('allinone', 'true')
            n += 1
    return n
# ---- end section 25


def tile_models_used(root, folder_files):
    """The tile models a zone can name (see _TILE_INST): {'folders': {tileent name: 'tiles/<x>'},
    'used': {folder: {'models/tiles/<x>/<stem>', ...}}, 'insts': n, 'bad': [(inst name, why)]}.
    folder_files(folder) -> set of lowercase stems that exist for 'tiles/<x>' (any source)."""
    folders = {}
    for el in root.iter():
        if el.tag.lower() != 'entity':
            continue
        a = {k.lower(): (v or '') for k, v in el.attrib.items()}
        if a.get('classname', '').lower() == 'tileent' and a.get('tilemodelfolder') and a.get('name'):
            folders[a['name'].lower()] = a['tilemodelfolder'].replace('\\', '/').lower().strip('/')
    used = {f: set() for f in folders.values()}
    bad, insts = [], 0
    by_shape = {}
    for ei in root.iter():
        if ei.tag.lower() != 'entinst':
            continue
        folder = folders.get((ei.get('type') or '').lower())
        if not folder:
            continue
        files = folder_files(folder)
        if folder not in by_shape:
            shapes = collections.defaultdict(set)
            for stem in files:
                m = _TILE_FILE.match(stem)
                if m:
                    shapes[m.group(1, 2, 3, 4, 5)].add(stem)
            by_shape[folder] = shapes
        shapes = by_shape[folder]
        for inst in ei.iter():
            if inst.tag.lower() != 'inst':
                continue
            n = (inst.get('name') or '').lower()
            m = _TILE_INST.match(n)
            if not m:
                bad.append((n, 'not a T_<folder>_<sht>_<f|w>_<v><d> name'))
                continue
            insts += 1
            pre, size, shape, third, fw, var, digit = m.groups()
            own = f'{pre}_{size}{shape}{third}_{fw}_{var}{int(digit)}'
            if own not in files and f'{pre}_{size}{shape}{third}_{fw}_{var}0' in files:
                own = f'{pre}_{size}{shape}{third}_{fw}_{var}0'    # XML1 names 'A01'..'A03' with only 'a0' files
            if own not in files and not shapes.get((pre, size, shape, third, fw)):
                bad.append((n, f'no models/{folder}/{own}.igb'))
                continue
            cands = {own} | shapes.get((pre, size, shape, third, fw), set())      # damage-stage variants
            if size in 'cde':                                                      # 0x4c2400: sizes 3..5
                cands |= shapes.get((pre, size, 'a', third, fw), set())
            used[folder] |= {f'models/{folder}/{s}' for s in cands if s in files}
    return {'folders': folders, 'used': used, 'insts': insts, 'bad': bad}


def igb_records(entries):
    """IGB-cache records a package's own entries create: distinct 'model' names + distinct motion-path files
    (0x57ae00 precaches 'motionpaths/<dir>' per file; effect models are listed as 'model' entries by this module)."""
    models = {C.norm(fn) for k, fn in entries if k == 'model'}
    mps = {C.norm(fn).rpartition('/')[0] for k, fn in entries if k == 'motionpath'}
    return len(models) + len(mps)


def strip_ext(v: str) -> str:
    s = C.norm(v)
    base, ext = C.split_ext(s)
    return base if ext in ('.igb', '.png', '.xml', '.eng', '.xmlb', '.engb', '.tga', '.py') else s


def norm_effect(v: str) -> str:
    """'Explode/car' | 'effects/explode/smexp1.xml' -> 'explode/car' | 'explode/smexp1' (relative to effects/)."""
    s = strip_ext(v)
    return s[len('effects/'):] if s.startswith('effects/') else s


def classify(zone: str) -> str:
    top = zone.split('/')[0]
    return {'mocap': 'briefing_mocap', 'cinematics': 'cinematic', 'arena': 'arena', 'demo': 'demo_copy',
            'menu': 'menu_background'}.get(top, 'campaign')


class Pkg:
    """An ordered, de-duplicated packagedef. Entries added with extra=True are inserted before the zone's core
    block (characters / zonexml / nav), matching both the XML1 bundle order and XML2's convention of listing the
    zone files last; 'boy' is appended at the very end by the caller."""

    def __init__(self, entries=()):
        self.main, self.extra, self.keys = [], [], set()
        for k, f in entries:
            self.add(k, f)

    @staticmethod
    def key(kind, fn):
        k = kind.lower()
        return ('xml' if k in XML_KINDS else k), C.norm(fn)

    def has(self, kind, fn):
        return self.key(kind, fn) in self.keys

    def add(self, kind, fn, extra=False):
        k = self.key(kind, fn)
        if k in self.keys:
            return False
        self.keys.add(k)
        (self.extra if extra else self.main).append((kind.lower(), C.norm(fn)))
        return True

    def entries(self, tail=()):
        core_at = next((i for i, (k, _) in enumerate(self.main) if k in CORE_KINDS), len(self.main))
        out = self.main[:core_at] + self.extra + self.main[core_at:]
        return out + [e for e in tail if self.key(*e) not in self.keys]

    def root(self, tail=()):
        root = ET.Element('packagedef')
        for k, f in self.entries(tail):
            ET.SubElement(root, k, {'filename': f})
        return root

    def __len__(self):
        return len(self.main) + len(self.extra)


# ---------------------------------------------------------------------------------------------- the converter
class Zones:
    def __init__(self, ctx, prov):
        self.ctx, self.prov = ctx, prov
        self.all_zones = ctx.x1_zones()
        self.zone_set = set(self.all_zones)
        self.by_base = collections.defaultdict(list)
        for z in self.all_zones:
            self.by_base[z.rsplit('/', 1)[-1]].append(z)
        self.converted, self.skipped, self.zone_info, self.detail = [], {}, {}, {}
        self.frontend = {}                                      # XML2 front-end zones kept (C.FRONTEND_ZONES)
        self.zone_acts = {}                                     # converted zone -> act (prov.zone_act; section 15)
        self.towncenters = {}                                   # act_towncenters() result (section 15)
        self._animdb_plan = None                                # zone -> plan (zone_animdb_plan; section 16)
        self.zone_animdbs = {}                                  # converted zone -> {'entry','mission','status'}
        self._zone_animdb_written = {}                          # 'zone_<leaf>' -> XML1 mission DB rel written
        self.item_refs = collections.defaultdict(set)           # inventoryitem value (lower) -> where
        self.xp_pickups = {}                                    # 'xp_300000' -> ('XP', 300000) (SPEC 23.1)
        self._x1_xp_items = None
        self.counts = collections.Counter()
        self.kept_files, self.written_x1 = set(), set()
        self.problems = collections.defaultdict(lambda: collections.defaultdict(set))   # kind -> item -> zones
        self.char_entries = collections.defaultdict(set)        # (kind, fn) -> packages listing it
        self.loading_numeric = collections.defaultdict(set)     # mapped numeric loading texture -> users
        self.pkgs = {}                                          # PKGB rel -> [(kind, fn)]
        self.music = {}
        self._effect_refs, self._data_refs, self._script_lits, self._script_ok = {}, {}, {}, {}
        self._script_text = {}
        self._entity_files = None
        self._global_ents = None
        self._item_names = None
        self._x1_sf = None
        self._forced = {}                                       # forced text import results (import_asset)
        self._tile_files = {}                                   # 'tiles/<x>' -> set of stems on either disc
        self.pruned_tiles = {}                                  # zone -> [bundle tile models the zone cannot name]
        self.pruned_actors = {}                                 # zone -> [(kind, name)] XML1 hero actors nobody spawns (s.14)
        self.igb = {}                                           # zone -> IGB-cache records its package creates
        self.automaps = {}                                      # zone -> automap info (section 26)
        self._automap_cache = {}                                # (texture rel, offset) -> (zam bytes | None, info)
        mode = (ctx.opt('tiles') or os.environ.get('XML1BUILD_TILES') or 'used').lower()
        if mode not in TILE_MODES:
            ctx.warn(f'--tiles {mode!r} unknown ({TILE_MODES}); using used')
            mode = 'used'
        self.tile_mode = mode
        self.stats_names, self.stats_source = self.load_stats_names()

    # ------------------------------------------------------------------ small utilities
    def load_stats_names(self):
        """lowercase herostat+npcstat names the CHR / spawner checks use: ctx.shared['stats_names'] (characters
        ran this build), else - for '--only zones' - the <out> stats tables when the registry says characters
        wrote them (carried over from the previous build). (None, reason) when neither is available: then the
        names are only checked by validate V5/V6."""
        ctx = self.ctx
        sh = ctx.shared.get('stats_names')
        if sh:
            return {str(n).lower() for n in sh}, 'ctx.shared stats_names'
        e = ctx.registry.get('Data/npcstat.engb') or ctx.registry.get('Data/npcstat.XMLB')
        if e is None or e.get('owner') != 'characters':
            return None, 'characters module outputs not in <out>'
        names = set()
        for f in ('herostat', 'npcstat'):
            for ext in ('.engb', '.XMLB'):
                if ctx.out_exists(f'Data/{f}{ext}'):
                    try:
                        names |= {(s.get('name') or '').lower() for s in ctx.read_out_xmlb(f'Data/{f}{ext}').iter('stats')}
                    except (KeyError, ValueError):
                        pass
        names.discard('')
        return (names or None), 'carried-over <out> herostat/npcstat (characters)'

    def problem(self, kind, item, where):
        self.problems[kind][item].add(where)

    def script_ok(self, ref) -> bool:
        r = C.script_ref(ref or '')
        if not r or r in BOOL_VALUES:
            return False
        if r not in self._script_ok:
            self._script_ok[r] = bool(self.prov.script_exists(self.ctx, r)) or self.ctx.base_exists(C.script_rel(r))
        return self._script_ok[r]

    def x1_nonempty(self, rel):
        p = self.ctx.x1_path(rel)
        if p is None:
            return None
        if p.stat().st_size == 0:
            return False
        if C.split_ext(C.norm(rel))[1] in C.TEXT_OUT:
            return not self.ctx.x1_is_empty(rel)
        return True

    def import_asset(self, x1_rel):
        """ctx.import_x1_asset under the SPEC 4.4 policy: XML1 wins (force, patched text) under FORCE_PREFIXES;
        everything else is XML2-wins and unpatched (shared, cacheable with other modules' imports)."""
        ctx = self.ctx
        n = C.norm(x1_rel)
        ext = C.split_ext(n)[1]
        # XML2's front-end files (--frontend xml2: C.FRONTEND_ZONES, menu/main_back) are never replaced, even in
        # XML1-wins areas; with --frontend xml1 XML1's backdrop replaces them (SPEC 21)
        forced = n.startswith(FORCE_PREFIXES) and not n.startswith(C.frontend_prefixes(ctx))
        if forced and ext in C.TEXT_OUT:
            res = self._forced_text_import(n, ext)
        else:
            res = ctx.import_x1_asset(n, force=forced)
        if res.status == 'kept_xml2':
            self.kept_files.add(n)
        elif res.status == 'written':
            self.written_x1.add(n)
            if ext == '.xml':
                self._shadow_fix(res)
        return res

    def _forced_text_import(self, n, ext):
        """XML1-wins text import (SPEC 4.4: conversations/, dialogs/, subtitles/, data/entities/, motionpaths/),
        patched with map_tree_refs + rewrite_data_tree. The characters module runs first and imports the
        data/entities files its character bundles list (96 entries) with the plain XML2-wins import, unpatched.
        If such a file is already in <out> from another module: when the patched encoding is byte-identical,
        share it as is (no ownership change); otherwise zones takes it over (forced re-import) and notes why,
        because an unpatched entity file would keep unmapped XML1 skins / script paths."""
        if n in self._forced:
            return self._forced[n]
        ctx = self.ctx
        stem = C.split_ext(n)[0]
        prior = [ctx.registry.get(stem + e) for e in C.TEXT_OUT[ext]]
        if all(prior) and any(p['owner'] != ctx.module for p in prior):
            src = ctx.x1_path(n)
            root = C.parse_x1_text(src) if src is not None else None
            if root is not None:
                ctx.x1_schema(root, n)                      # what import_x1_asset applies before any patch
                self._data_patch(n)(root)
                data = C.encode_xmlb(root)
                if all((ctx.out / p['rel']).is_file() and (ctx.out / p['rel']).read_bytes() == data for p in prior):
                    res = C.ImportResult(n, 'written', C.norm(stem), [p['rel'] for p in prior])
                    self.counts['forced_import_shared_identical'] += 1
                    self._forced[n] = res
                    return res
                owners = sorted({p['owner'] for p in prior})
                ctx.note(f'{n}: imported earlier by {owners} without the zones data patch (skin / script-path '
                         f'rewrites); zones re-imports it patched (XML1-wins category, SPEC 4.4)')
                self.counts['forced_import_took_over'] += 1
        res = ctx.import_x1_asset(n, force=True, patch=self._data_patch(n), patch_key=PATCH_DATA)
        self._forced[n] = res
        return res

    def _data_patch(self, n):
        def patch(root, n=n):
            C.map_tree_refs(root)
            self.prov.rewrite_data_tree(self.ctx, root, n)
        return patch

    def _shadow_fix(self, res):
        """A non-localized XML1 .xml is written as .XMLB only; if XML2 ships a same-named .engb (which the
        English game may prefer), write the same bytes there too so XML2's stale copy never wins."""
        ctx = self.ctx
        stem = res.pkg_name
        engb = ctx.base_index.get(stem + '.engb')
        if not engb or not res.out_rels:
            return
        prev = ctx.registry.get(engb)
        if prev and prev['owner'] == ctx.module and prev.get('source') == 'zones:shadow':
            return
        data = (ctx.out / res.out_rels[0]).read_bytes()
        ctx.write_bytes(engb, data, source='zones:shadow', replace=True)
        self.counts['engb_shadow_fixed'] += 1

    def char_entry(self, kind, x1_rel):
        """(kind, mapped filename) for character-namespace entries (files owned by the characters module)."""
        k = kind.lower()
        f = C.pkg_name(x1_rel)
        if k in ('actorskin', 'actoranimdb', 'fightstyle') or (k == 'model' and _UI_CHAR_X1.match(f)) or \
                (k == 'texture' and _LOADING_X1.match(f)):
            return C.map_package_entry(kind, x1_rel)
        return None

    # ---- section 16: per-zone animation DB (XMen2.exe "zone_%s", 0x486710)
    @staticmethod
    def mission_animdb_stem(kind, x1_rel):
        """'mission_<area>' when the bundle entry is an XML1 area mission anim DB, else None."""
        if kind.lower() != 'actoranimdb':
            return None
        f = C.pkg_name(x1_rel)
        stem = f[len('actors/'):] if f.startswith('actors/') else f
        return stem if MISSION_ANIMDB_RE.match(stem) else None

    def zone_animdb_plan(self):
        """{zone: {'leaf', 'entry': 'zone_<leaf>', 'mission': stem, 'x1_rel', 'ea_uses', 'status'}} for every XML1
        zone whose bundle lists a mission_* anim DB. status: 'own' (this zone's file), 'shared' (same area as the
        leaf's owner: same file), 'lost' (another area owns the leaf; the zone keeps XMen2.exe's zone_shared)."""
        if self._animdb_plan is not None:
            return self._animdb_plan
        plan, by_leaf = {}, collections.defaultdict(list)
        for zone in self.all_zones:
            if zone in C.frontend_zones(self.ctx):
                continue
            if self.skip_reason(zone, self.zone_sources(zone)[1]):
                continue          # never converted (e.g. astral/savepx/astral1_1: empty XML1 zone): no claim on a name
            try:
                bundle = self.ctx.zone_bundle(zone)
            except KeyError:
                continue
            mission, x1_rel, uses = None, None, 0
            for p, kind in bundle:
                stem = self.mission_animdb_stem(kind, p)
                if stem and mission is None:
                    mission, x1_rel = stem, C.norm(p)
            if mission is None:
                continue
            for p, kind in bundle:
                if kind.lower() == 'script':
                    text = self.script_text(C.script_ref(p)) or ''
                    uses += len(_EA_ZONE_USE.findall(text))
            for ext in ('.eng', '.xml'):                       # inline monster_spawnscript / combat-node literals
                mp = self.ctx.x1_path(f'maps/{zone}{ext}')
                if mp is not None and mp.is_file():
                    uses += len(_EA_ZONE_USE.findall(mp.read_text(encoding='latin-1', errors='replace')))
                    break
            leaf = zone.rsplit('/', 1)[-1]
            plan[zone] = {'leaf': leaf, 'entry': ZONE_ANIMDB_PREFIX + leaf, 'mission': mission, 'x1_rel': x1_rel,
                          'ea_uses': uses, 'status': 'own'}
            by_leaf[leaf].append(zone)
        for leaf, zones in by_leaf.items():
            areas = {plan[z]['mission'] for z in zones}
            if len(areas) == 1:
                for z in zones[1:]:
                    plan[z]['status'] = 'shared'
                continue
            # several areas want one file name: the area whose zones use the most zone animations owns it
            score = collections.Counter()
            for z in zones:
                score[plan[z]['mission']] += plan[z]['ea_uses']
            winner = max(sorted(score), key=lambda m: (score[m], m))
            first = True
            for z in sorted(zones):
                if plan[z]['mission'] != winner:
                    plan[z]['status'] = 'lost'
                elif first:
                    first = False
                else:
                    plan[z]['status'] = 'shared'
            self.ctx.warn(f'zone anim DB "{ZONE_ANIMDB_PREFIX}{leaf}" is wanted by {len(areas)} XML1 areas '
                          f'{ {z: plan[z]["mission"] for z in sorted(zones)} }: {winner} wins '
                          f'({dict(score)} zone-anim uses); the other zone(s) keep XMen2.exe\'s zone_shared fallback '
                          f'(their EA_ZONE clips are missing) until the zone is renamed (section 16)')
        self._animdb_plan = plan
        return plan

    def zone_animdb_entry(self, zone, kind, x1_rel):
        """Package entry replacing an XML1 mission_* anim DB: ('actoranimdb', 'zone_<leaf>') with the file written
        (once per name), or None when the zone lost its leaf to another area (entry dropped; zone_shared applies)."""
        stem = self.mission_animdb_stem(kind, x1_rel)
        if stem is None:
            return None
        plan = self.zone_animdb_plan().get(zone)
        if plan is None or plan['mission'] != stem:
            # a second mission DB in one bundle (XML1 ships none): keep the first only
            self.counts['zone_animdb_extra_dropped'] += 1
            return ()
        rec = {'entry': plan['entry'], 'mission': stem, 'status': plan['status'], 'ea_uses': plan['ea_uses']}
        self.zone_animdbs[zone] = rec
        if plan['status'] == 'lost':
            self.counts['zone_animdb_lost'] += 1
            return ()
        name = plan['entry']
        if name not in self._zone_animdb_written:
            from . import characters as CH
            data = self.ctx.x1_path(C.norm(x1_rel)).read_bytes()
            new, n, problems = CH.rename_mission_anims_igb(data)
            if problems:
                self.ctx.error(f'{zone}: {x1_rel} -> Actors/{name}.IGB: mission anim rename incomplete: {problems[:3]}')
            actual = self.ctx.write_bytes(f'Actors/{name}.IGB', new, source=f'zones:zone_animdb {C.norm(x1_rel)}')
            self._zone_animdb_written[name] = C.norm(x1_rel)
            self.counts['zone_animdb_files'] += 1
            self.counts['zone_animdb_clips_renamed'] += n
        self.counts['zone_animdb_entries'] += 1
        return ('actoranimdb', name)
    # ---- end section 16

    # ------------------------------------------------------------------ zone link resolution (sweep.py rules)
    def resolve_zone(self, cur, name):
        n = name.strip().replace('\\', '/').lower()
        if not n:
            return None, 'empty'
        if n in self.zone_set:
            return n, 'full'
        cands = self.by_base.get(n.rsplit('/', 1)[-1], [])
        cur_dir = cur.rsplit('/', 1)[0]
        same = [x for x in cands if x.rsplit('/', 1)[0] == cur_dir]
        if same:
            return same[0], 'same_dir'
        area = [x for x in cands if x.split('/')[0] == cur.split('/')[0]]
        if len(area) == 1:
            return area[0], 'same_area'
        nondemo = [x for x in cands if classify(x) == 'campaign']
        if len(nondemo) == 1:
            return nondemo[0], 'unique_campaign'
        if len(cands) == 1:
            return cands[0], 'unique'
        return None, ('ambiguous:' + ','.join(cands)) if cands else 'unresolved'

    # ------------------------------------------------------------------ indexes (lazy)
    def entity_files(self):
        """entity name (lower) -> XML1 data/entities files defining it."""
        if self._entity_files is None:
            idx = collections.defaultdict(set)
            for rel in self.ctx.x1_rels('data/entities/'):
                if C.split_ext(rel)[1] not in ('.xml', '.eng'):
                    continue
                try:
                    root = self.ctx.read_x1_xml(rel)
                except (KeyError, ValueError, SyntaxError):
                    continue
                if root is None:
                    continue
                for e in root.iter():
                    if e.tag.lower() == 'entity' and e.get('name'):
                        idx[e.get('name').lower()].add(rel)
            self._entity_files = idx
        return self._entity_files

    def x1_soundfiles(self):
        """zone -> the XML1 world soundfile (stripped) of every zone that has one (cached)."""
        if self._x1_sf is None:
            sf = {}
            for z in self.all_zones:
                zx = self.zone_sources(z)[1]
                if zx is None or self.ctx.x1_path(zx) is None or self.ctx.x1_is_empty(zx):
                    continue
                try:
                    root = self.ctx.read_x1_xml(zx)
                except (KeyError, ValueError, SyntaxError):
                    continue
                w = C.find_world(root) if root is not None else None
                v = (w.get('soundfile') or '').strip() if w is not None else ''
                if v:
                    sf[z] = v
            self._x1_sf = sf
        return self._x1_sf

    def soundfile_fallback(self, zone):
        """(soundfile, how) for a zone whose own soundfile has no planned <sf>_m bank: the one soundfile shared
        by its same-name campaign twins (the demo copies / junk duplicates are copies of those zones), else the
        one shared by its same-directory siblings; only soundfiles whose _m bank is planned count.
        (None, reason) when there is no unambiguous candidate."""
        sf = self.x1_soundfiles()
        ctx = self.ctx

        def usable(v):
            return bool(v) and len(v) < SOUNDFILE_MAX and ctx.sound_bank_rel(v + '_m') is not None

        base = zone.rsplit('/', 1)[-1]
        twins = {sf[t].lower() for t in self.by_base.get(base, ())
                 if t != zone and classify(t) == 'campaign' and usable(sf.get(t))}
        if len(twins) == 1:
            return twins.pop(), 'soundfile of its campaign twin'
        d = zone.rsplit('/', 1)[0]
        sibs = {v.lower() for z, v in sf.items() if z != zone and z.rsplit('/', 1)[0] == d and usable(v)}
        if len(sibs) == 1:
            return sibs.pop(), 'soundfile shared by its same-directory zones'
        return None, f'no unambiguous twin/sibling soundfile (twins {sorted(twins)}, siblings {sorted(sibs)})'

    def global_ents(self):
        """entity names defined by the global world tables (XML1 and XML2 common_ents / item_ents)."""
        if self._global_ents is None:
            names = set()
            for rel in ('data/common_ents.xml', 'data/item_ents.xml'):
                try:
                    root = self.ctx.read_x1_xml(rel)
                except KeyError:
                    root = None
                if root is not None:
                    names |= {e.get('name').lower() for e in root.iter() if e.get('name')}
            for rel in ('Data/common_ents.XMLB', 'Data/item_ents.XMLB'):
                if self.ctx.base_exists(rel):
                    names |= {e.get('name').lower() for e in self.ctx.read_base_xmlb(rel).iter() if e.get('name')}
            self._global_ents = names
        return self._global_ents

    def x1_xp_items(self):
        """{lower name: name} of XML1's items of type xp (data/items.eng: XP)."""
        if self._x1_xp_items is None:
            try:
                root = self.ctx.read_x1_xml('data/items.eng')
            except KeyError:
                root = None
            self._x1_xp_items = {e.get('name').lower(): e.get('name') for e in (root.iter() if root is not None else ())
                                 if e.tag.lower() == 'item' and e.get('name') and
                                 (e.get('type') or '').strip().lower() == 'xp'}
        return self._x1_xp_items

    def rewrite_xp_pickups(self, zone, root):
        """SPEC 23.1 (XP_PICKUP_ITEM): an entity naming an XML1 xp item gets count 1 (both curves) and, with
        --xp-curve xml1, the item XP_<count> that gives XML1's amount to the activator. Returns the rewrites."""
        items = self.x1_xp_items()
        xml1 = C.xp_curve_mode(self.ctx) == 'xml1'
        n = 0
        for el in root.iter():
            v = (el.get('inventoryitem') or '').strip()
            if not v or v.lower() not in items:
                continue
            raw = (el.get('count') or '').strip()
            amount = int(raw) if raw.isdigit() else 0
            if xml1:
                if amount <= 0:
                    self.problem('xp_pickup_without_amount', f'{el.get("name")}: count {raw!r} (XML1 gave 0 XP)', zone)
                else:
                    name = XP_PICKUP_ITEM.format(item=items[v.lower()], amount=amount)
                    el.set('inventoryitem', name)
                    self.xp_pickups[name.lower()] = (items[v.lower()], amount)
                    self.counts['xp_pickups_xml1_amount'] += 1
                    n += 1
            if raw and raw != '1':
                el.set('count', '1')
                self.counts['xp_pickup_count_set_1'] += 1
        return n

    def item_names(self):
        if self._item_names is None:
            names = set()
            try:
                root = self.ctx.read_x1_xml('data/items.eng')
            except KeyError:
                root = None
            if root is not None:
                names |= {e.get('name').lower() for e in root.iter() if e.get('name')}
            if self.ctx.base_exists('Data/items.XMLB'):
                names |= {e.get('name').lower() for e in self.ctx.read_base_xmlb('Data/items.XMLB').iter()
                          if e.get('name')}
            self._item_names = names
        return self._item_names

    # ------------------------------------------------------------------ script text (motion paths, call targets)
    def script_text(self, ref):
        """text of the script <out> will run for ref: this build's installed copy (scripts module) or the XML2
        base copy in <out>, else the research output the scripts module installs, else XML1's raw script."""
        r = C.script_ref(ref)
        if r in self._script_text:
            return self._script_text[r]
        ctx = self.ctx
        text = None
        out_rel = ctx.out_index.get(C.script_rel(r))
        reg = ctx.registry.get(C.script_rel(r)) if out_rel else None
        cands = []
        if out_rel and (reg is None or reg['owner'] == 'scripts'):
            cands.append(ctx.out / out_rel)
        cands.append(ctx.research_path('scripts/out/scripts') / (r + '.py'))
        p = ctx.x1_path(f'scripts/{r}.py')
        if p is not None:
            cands.append(p)
        for c in cands:
            if c.is_file():
                text = c.read_text(encoding='latin-1')
                break
        self._script_text[r] = text
        return text

    def script_literals(self, ref):
        r = C.script_ref(ref)
        if r in self._script_lits:
            return self._script_lits[r]
        text = self.script_text(r)
        lits = set()
        if text:
            for m in _QUOTED.finditer(text):
                s = (m.group(1) if m.group(1) is not None else m.group(2)).strip()
                if '/' in s or '\\' in s:
                    lits.add(s.replace('\\', '/').lower())
            for m in _CAM_MP.finditer(text):
                lits.add((m.group(1) + '/' + m.group(2)).replace('\\', '/').lower())
        self._script_lits[r] = lits
        return lits

    # ------------------------------------------------------------------ reference extraction
    def extract_refs(self, root, full=True):
        """(category, value, attr) for every file-ish reference in an entity-style tree. full=False only
        collects script references (conversations / dialogs / subtitles)."""
        refs = []
        for el in root.iter():
            tag = el.tag.lower()
            if full and tag == 'precache':
                t = (el.get('type') or '').lower()
                fn = (el.get('filename') or '').strip()
                if fn:
                    refs.append(('precache:' + t, fn, 'filename'))
                continue
            for k, v in el.attrib.items():
                if v is None:
                    continue
                kl = k.lower()
                s = v.strip()
                if not s:
                    continue
                if '(' in s and _CALL_ANY.search(s):
                    refs.append(('code', s, kl))            # inline code starting a conversation / popup dialog
                if FALLBACK.is_script_attr(kl):
                    if kl != 'zonescript' and s.lower() not in BOOL_VALUES and _PATHLIKE.match(s):
                        refs.append(('script', s, kl))
                    continue
                if not full:
                    continue
                if s.lower() in BOOL_VALUES:
                    continue
                if kl in EFFECT_ATTRS or (kl.endswith('effect') and kl not in ('acttogglesloopfx',)):
                    refs.append(('effect', s, kl))
                elif kl == 'model':
                    refs.append(('actorskin' if _SKIN.match(s) else 'model', s, kl))
                elif kl == 'skybox':
                    refs.append(('skybox', s, kl))
                elif kl == 'motionpath':
                    refs.append(('motionpath', s, kl))
                elif kl == 'texture' and tag == 'entity':
                    refs.append(('texture', s, kl))
                elif kl == 'tilemodelfolder':
                    refs.append(('tilefolder', s, kl))
                elif kl in SPAWN_ATTRS:
                    for tok in s.split():
                        refs.append(('spawn', tok, kl))
                elif kl in C.SKIN_ATTRS or kl.startswith('skin_'):
                    if _SKIN.match(s):
                        refs.append(('actorskin', s, kl))
                elif kl == 'loading':
                    refs.append(('loading', s, kl))
                elif kl == 'inventoryitem':
                    refs.append(('item', s, kl))
                elif kl == 'character':
                    refs.append(('character', s, kl))
        return refs

    # ------------------------------------------------------------------ zone XML
    def mutate_zone(self, zone, zx, root, st):
        ctx = self.ctx
        st['patched'] = True
        for how, n in convert_inst_extents(root).items():             # section 17: world -> entity-local boxes
            self.counts[f'inst_extents_{how}'] += n
        renamed = rename_join_double(zone, root)                        # section 18: the join double's own name
        if renamed:
            self.counts['join_doubles_renamed'] += renamed
        elif zone.lower() in ST.JOIN_DOUBLE_SPAWNERS:
            self.problem('join_double_missing', f'no spawner {ST.JOIN_DOUBLE_SPAWNERS[zone.lower()]} to rename', zone)
        enabled = enable_join_starts(zone, root)                        # section 18: the joined hero's start
        if enabled:
            self.counts['join_starts_enabled'] += enabled
        elif zone.lower() in ST.JOIN_DOUBLE_SPAWNERS and not join_hero_starts(root):
            self.problem('join_start_missing', 'no slot-2 playerstartent for the joined hero', zone)
        self.rewrite_xp_pickups(zone, root)                             # SPEC 23.1: XML1's XP pickup amounts
        renamed, missing = rename_npc_doubles(zone, root)                # section 18: the other same-name NPCs
        if renamed:
            self.counts['npc_doubles_renamed'] += renamed
        for sp, hero in missing:
            self.problem('npc_double_missing', f'no spawner {sp} with monster_name {hero} to rename', zone)
        allinone = mark_allinone_starts(root)                           # section 25: one-position starts
        if allinone:
            self.counts['starts_allinone'] += allinone
        st['mapped_refs'] = C.map_tree_refs(root)
        st['rewritten'] = self.prov.rewrite_data_tree(ctx, root, zx)
        inline = rename_npc_inline_refs(zone, root)                     # section 18.1: its inline code follows
        if inline:
            self.counts['npc_double_inline_refs'] += inline
        for el in root.iter():
            if el.tag.lower() == 'precache':
                t = (el.get('type') or '').lower()
                fn = el.get('filename')
                if not fn:
                    continue
                if t == 'script' and '(' not in fn:
                    nf = C.script_ref(fn)
                    if nf != fn:
                        el.set('filename', nf)
                        self.counts['precache_script_paths_normalised'] += 1
                elif t in PRECACHE_PATH_TYPES:
                    # XML2's own precache filenames are all lowercase '/' paths (e.g. 'hud/hud_head_1101'); XML1
                    # also writes 'Hud/hud_head_0201' and, for 7 bolt-on models, 'bolton/<x>' although the file is
                    # models/bolton/<x>.igb (XML2 precaches only full paths): give those the models/ prefix.
                    nf = fn.strip().replace('\\', '/').lower()
                    if t == 'model' and nf and not nf.startswith('models/') and \
                            not self.x1_nonempty(nf + '.igb') and not self.ctx.base_exists(nf + '.igb') and \
                            (self.x1_nonempty('models/' + nf + '.igb') or self.ctx.base_exists(f'models/{nf}.igb')):
                        nf = 'models/' + nf
                        self.counts['precache_model_models_prefixed'] += 1
                    if nf != fn:
                        el.set('filename', nf)
                        self.counts['precache_paths_normalised'] += 1
            v = el.get('tilemodelfolder')
            if v:
                nv = v.replace('\\', '/').lower()
                if nv != v:
                    el.set('tilemodelfolder', nv)
                    self.counts['tilemodelfolder_lowercased'] += 1
        self.fix_links(zone, root, st)
        tops = C.iter_roots(root)
        for top in tops:                          # beastlab2_cine is '<World/>'; XML2 zone roots are 'world'
            if top.tag != 'world' and top.tag.lower() == 'world':
                top.tag = 'world'
                self.counts['zone_root_tag_lowercased'] += 1
        world = C.find_world(root)
        if world is None:
            # 2 XML1 zones have no world entity (cinematics/beastlab2_cine, muir_is/muir2/muir_brig). Every XML2
            # zone has one (zonescript / soundfile / flags live there) and --tour needs it: add a bare one.
            top = next((t for t in tops if t.tag == 'world'), tops[0])
            world = ET.Element('entity', {'name': 'world'})
            top.insert(0, world)
            st['world_synthesized'] = True
            self.problem('world_synthesized', 'XML1 zone has no <entity name="world">; a bare one was added', zone)
        # zonescript (SPEC 5.3.2c): the scripts module is the single source of truth
        zs = self.prov.zone_script_ref(ctx, zone)
        how = 'scripts.zone_script_ref'
        if zs and not self.script_ok(zs):
            self.problem('zonescript_missing', zs, zone)
            zs = None
        old = world.get('zonescript')
        if zs:
            zs = C.script_ref(zs)
            world.set('zonescript', zs)
        elif old is not None:
            del world.attrib['zonescript']
            self.problem('zonescript_removed', old, zone)
        st['zonescript'], st['zonescript_how'] = zs, (how if zs else None)
        # soundfile: < 10 chars (0x5920cb). 6 XML1 zones name a soundfile none of whose banks exists on either
        # disc (5 demo copies: a_int, Deck, hub, man1b; the junk mansion/man5/subbasement4: main): use the
        # soundfile of the zone's campaign twin (the zone it is a copy of) or, failing that, the one all its
        # same-directory siblings share; otherwise drop it. A zone that has some but not all of its banks keeps
        # its soundfile: XML2 retail's own menu/main_back uses soundfile "menu" with only menu_a / menu_c, so
        # the loader tolerates a missing _m bank. The world entity synthesized for muir_brig gets the soundfile
        # of its directory the same way.
        raw_sf = world.get('soundfile')
        sf = (raw_sf or '').strip()
        if sf != (raw_sf or ''):
            world.set('soundfile', sf)
        any_bank = bool(sf) and any(ctx.sound_bank_rel(f'{sf}_{c}') is not None for c in 'macvd')
        if (sf and not any_bank) or (not sf and st.get('world_synthesized')):
            new, how_sf = self.soundfile_fallback(zone)
            if new:
                world.set('soundfile', new)
                what = f'{sf} (no {sf}_m/a/c/v/d bank on either disc)' if sf else '(no world entity)'
                self.problem('soundfile_substituted', f'{what} -> {new}: {how_sf}', zone)
                sf = new
            elif sf:
                del world.attrib['soundfile']
                self.problem('soundfile_dropped', f'{sf} (no {sf}_m/a/c/v/d bank on either disc; {how_sf})', zone)
                sf = ''
        st['soundfile'] = sf or None
        if sf:
            if len(sf) >= SOUNDFILE_MAX:
                ctx.error(f'{zone}: world soundfile {sf!r} has {len(sf)} chars (XMen2.exe needs < {SOUNDFILE_MAX})')
            if re.search(r'_[a-v]$', sf, re.I):
                ctx.warn(f'{zone}: soundfile {sf!r} ends in _<letter>: XMen2.exe then loads only that one bank')
            banks = [b for b in (f'{sf}_{c}' for c in 'macvd') if ctx.sound_bank_rel(b) is not None]
            st['sound_banks'] = banks
            for c in 'ac':
                if ctx.sound_bank_rel(f'{sf}_{c}') is None:
                    self.counts[f'zones_without_music_{c}'] += 1
        # music overrides (dropped silently by XML2)
        mus = {a: world.get(a) for a in MUSIC_ATTRS if world.get(a)}
        if mus:
            self.music[zone] = mus
        # a zone that replaces an XML2 zone (menu/main_back, the front-end backdrop) keeps XML2's world
        # behaviour flags XML1 lacks (nosave, startblack); geometry, sound and script stay XML1's
        base_rel = ctx.base_index.find(f'maps/{zone}', ('.XMLB', '.engb'))
        if base_rel:
            bw = C.find_world(ctx.read_base_xmlb(base_rel))
            if bw is not None:
                for k, v in bw.attrib.items():
                    if k not in world.attrib and k not in BASE_WORLD_SKIP:
                        world.set(k, v)
                        st['base_world_attrs'][k] = v
        # SPEC 21 B.4 (--frontend xml1): the XML1 Danger Room arenas get nosave="true" like every XML2 DR arena
        # (dr/dr_sewers1 ...): the course menu loads them as Danger Room zones, never as save points
        if classify(zone) == 'arena' and C.frontend_mode(ctx) == 'xml1' and 'nosave' not in world.attrib:
            world.set('nosave', 'true')
            st['arena_nosave'] = True
            self.counts['arena_worlds_nosave'] += 1

    def fix_links(self, zone, root, st):
        for el in root.iter():
            for a in LINK_ATTRS:
                raw = el.get(a)
                if raw is None or not raw.strip():
                    continue
                v = raw.strip().replace('\\', '/').lower()
                tgt, how = self.resolve_zone(zone, v)
                if how == 'full':
                    new = v
                elif how == 'same_dir':
                    new = v.rsplit('/', 1)[-1]
                elif tgt:
                    new = tgt
                    self.counts['crossdir_links_fixed'] += 1
                else:
                    new = v
                    self.problem(f'{a}_unresolved', f'{v} ({how})', zone)
                if new != raw:
                    el.set(a, new)
                st['links'].append({'attr': a, 'entity': el.get('name'), 'raw': raw, 'value': new, 'target': tgt,
                                    'how': how})
                if a == 'nextzone' and tgt:
                    st['nextzones'].append(tgt)

    def tile_folder_files(self, folder):
        """lowercase stems of models/<folder>/*.igb on the XML1 disc or in the XML2 base (either can serve)."""
        folder = C.norm(folder).strip('/')
        if folder not in self._tile_files:
            pre = f'models/{folder}/'
            stems = {r[len(pre):-4] for r in self.ctx.x1_rels(pre) if r.endswith('.igb') and '/' not in r[len(pre):]}
            for a in self.ctx.base_index.under(pre):
                n = C.norm(a)
                if n.endswith('.igb') and '/' not in n[len(pre):]:
                    stems.add(n[len(pre):-4])
            self._tile_files[folder] = stems
        return self._tile_files[folder]

    def analyse_zone(self, zone, root, st):
        st['entities'] = {e.get('name').lower() for e in root.iter()
                          if e.tag.lower() == 'entity' and e.get('name')}
        st['refs'] = self.extract_refs(root, full=True)
        st['tiles'] = tile_models_used(root, self.tile_folder_files)
        for n, why in st['tiles']['bad']:
            self.problem('tile_inst_unresolved', f'{n} ({why})', zone)
        mp = set()
        for cat, v, _ in st['refs']:
            if cat in ('motionpath', 'precache:motionpath'):
                mp.add(v.replace('\\', '/').lower())
        st['mp_lits'] = mp
        w = C.find_world(root)
        st['automap'] = (w.get('automap_texture'), w.get('automap_offset')) if w is not None else (None, None)
        if 'zonescript' not in st:
            st['zonescript'] = w.get('zonescript') if w is not None else None
            st['soundfile'] = w.get('soundfile') if w is not None else None
            st['no_world'] = w is None

    # ------------------------------------------------------------------ package helpers
    def global_keys(self):
        """Pkg keys of everything resident whenever a zone is loaded: XML2's permanent.PKGB and the world-table
        packages (XMen2.exe loads generated/common_ents with every zone package, 0x486576, and
        generated/items + item_ents at game start, 0x4802da), plus what build_permanent / build_world_tables
        append to them from the XML1 bundles. References to these are not repeated in zone packages."""
        if getattr(self, '_global_keys', None) is not None:
            return self._global_keys
        ctx = self.ctx
        keys = set()
        for rel in ('Packages/generated/maps/package/permanent.PKGB', 'Packages/generated/common_ents.PKGB',
                    'Packages/generated/item_ents.PKGB', 'Packages/generated/items.PKGB',
                    'Packages/generated/shared_nodes.PKGB'):
            if ctx.base_exists(rel):
                keys |= {Pkg.key(e.tag, e.get('filename', '')) for e in ctx.read_base_xmlb(rel)}
        for bundle, x1_only in (('packages/generated/maps/package/permanent.fb', True),
                                ('packages/generated/common_ents.fb', False), ('packages/generated/item_ents.fb', False),
                                ('packages/generated/items.fb', False), ('packages/generated/shared_nodes.fb', False)):
            for p, kind in ctx.manifest.get(bundle, []):
                k, n = kind.lower(), C.norm(p)
                stem, ext = C.split_ext(n)
                if ext in LANG_SKIP or k not in ('model', 'texture', 'effect') or self.char_entry(k, n):
                    continue
                if x1_only and ctx.base_index.find(stem, C.TEXT_OUT.get(ext, ('.IGB' if ext == '.igb' else ext,))):
                    continue
                if self.x1_nonempty(n):
                    keys.add(Pkg.key(*C.map_package_entry(kind, n)))
        self._global_keys = keys
        return keys

    def ensure_file(self, pkg, kind, rel_noext, exts, zone, why):
        """Make sure pkg lists the file rel_noext+ext (first existing ext). Imports XML1 files, accepts XML2
        base files; records a missing reference otherwise. Returns the status. Files already resident through
        the permanent / world-table packages are not repeated ('global')."""
        ctx = self.ctx
        rel_noext = C.norm(rel_noext)
        entry = C.map_package_entry(kind, rel_noext + exts[0])
        if pkg.has(*entry):
            return 'present'
        if Pkg.key(*entry) in self.global_keys():
            self.counts['refs_resident_global'] += 1
            return 'present'
        for e in exts:
            ok = self.x1_nonempty(rel_noext + e)
            if ok is None:
                continue
            if not ok:
                self.problem('ref_empty', f'{rel_noext}{e} ({why})', zone)
                return 'empty'
            res = self.import_asset(rel_noext + e)
            if res.ok:
                entry = C.map_package_entry(kind, rel_noext + e)
                pkg.add(*entry, extra=True)
                self.counts['refs_added_' + ('x1' if res.status == 'written' else 'xml2_kept')] += 1
                if entry[0] == 'effect':
                    self.effect_nested_into(pkg, entry[1], zone)
                return res.status
            self.problem('ref_' + res.status, f'{rel_noext}{e} ({why})', zone)
            return res.status
        out_exts = []
        for e in exts:
            out_exts += list(C.TEXT_OUT.get(e, ('.IGB' if e == '.igb' else e,)))
        if ctx.base_index.find(rel_noext, out_exts):
            pkg.add(*entry, extra=True)
            self.counts['refs_added_xml2_only'] += 1
            if entry[0] == 'effect':
                self.effect_nested_into(pkg, entry[1], zone)
            return 'xml2'
        self.problem('missing_ref', f'{rel_noext} ({why})', zone)
        return 'missing'

    @staticmethod
    def call_targets(text):
        """[(kind, 'conversations/<x>' | 'dialogs/<x>')] started by startConversation / createPopupDialogXml
        literals in script or inline code text."""
        out = []
        for rx, top, kind in CALL_TARGETS:
            for m in rx.finditer(text or ''):
                v = strip_ext(m.group(1).strip())
                if v:
                    out.append((kind, v if v.startswith(top) else top + v))
        return out

    def ensure_call_target(self, pkg, kind, rel, zone, why):
        """list a conversation / dialog a zone script or inline code starts in the zone package (importing it
        like any other bundle file); targets absent from both discs are reported, not listed."""
        ctx = self.ctx
        if pkg.has(kind, rel):
            return
        if rel.startswith('dialogs/x1/'):                   # generated popups: installed by the scripts module
            if (ctx.research_path('scripts/out') / (rel + '.XMLB')).is_file() or ctx.out_index.find(rel, ('.XMLB',)):
                pkg.add(kind, rel, extra=True)
                self.counts['call_targets_added'] += 1
            else:
                self.problem('call_target_missing', f'{rel} ({why})', zone)
            return
        if not any(ctx.x1_path(rel + e) for e in ('.eng', '.xml')) and \
                not ctx.base_index.find(rel, ('.XMLB', '.engb')):
            self.problem('call_target_missing', f'{rel} ({why}; absent on both discs)', zone)
            return
        if self.ensure_file(pkg, kind, rel, ('.eng', '.xml'), zone, why) not in ('present', 'missing', 'empty'):
            self.counts['call_targets_added'] += 1

    def effect_refs(self, eff):
        """nested references (texture / modelname / *fxfile) of the effect file that <out> will use:
        XML2's when the base has it (effects are XML2-wins), else XML1's."""
        eff = norm_effect(eff)
        if eff in self._effect_refs:
            return self._effect_refs[eff]
        ctx = self.ctx
        self._effect_refs[eff] = []
        root = None
        base = ctx.base_index.find(f'effects/{eff}', ('.XMLB', '.engb'))
        try:
            if base:
                root = ctx.read_base_xmlb(base)
            elif ctx.x1_path(f'effects/{eff}.xml') is not None:
                root = ctx.read_x1_xml(f'effects/{eff}.xml')
        except (KeyError, ValueError, SyntaxError):
            root = None
        refs = []
        if root is not None:
            for el in root.iter():
                for k, v in el.attrib.items():
                    kl, s = k.lower(), (v or '').strip()
                    if not s or s.lower() in BOOL_VALUES:
                        continue
                    if kl == 'texture':
                        t = strip_ext(s)
                        refs.append(('texture', t if '/' in t else 'textures/' + t, ('.igb',)))
                    elif kl == 'modelname':
                        m = strip_ext(s)
                        refs.append(('model', m if '/' in m else 'models/' + m, ('.igb',)))
                    elif kl.endswith('fxfile'):
                        refs.append(('effect', 'effects/' + norm_effect(s), ('.xml',)))
        self._effect_refs[eff] = refs
        return refs

    def effect_nested_into(self, pkg, eff, zone):
        for kind, rel, exts in self.effect_refs(eff):
            st = self.ensure_file(pkg, kind, rel, exts, zone, f'inside effect {eff}')
            if st not in ('present', 'missing', 'empty'):
                self.counts['effect_nested_added'] += 1

    def data_refs(self, kind, fn):
        """references inside a packaged XML1 data file as it is in <out> (conversations/dialogs/subtitles: script
        refs only; data/entities: everything)."""
        key = (kind, fn)
        if key in self._data_refs:
            return self._data_refs[key]
        ctx = self.ctx
        out_rel = ctx.out_index.find(fn, ('.engb', '.XMLB'))
        refs = []
        if out_rel:
            try:
                root = C.decode_xmlb((ctx.out / out_rel).read_bytes())
                refs = self.extract_refs(root, full=fn.startswith('data/entities/'))
            except (ValueError, OSError):
                refs = []
        self._data_refs[key] = refs
        return refs

    def motionpath_entries(self, x1_file, lits, zone):
        """XML2 motionpath entries 'dir/file/object' for motionpaths/<dir/file>.igb."""
        d = C.split_ext(C.norm(x1_file))[0][len('motionpaths/'):]
        names = sorted({l for l in lits if l.startswith(d + '/') and '/' not in l[len(d) + 1:]
                        and l[len(d) + 1:]})
        if not names:
            p = self.ctx.x1_path(x1_file)
            found = sorted({m.group(1).decode().lower() for m in _IGB_MP.finditer(p.read_bytes())}) if p else []
            names = [f'{d}/{o}' for o in found]
            if names:
                self.counts['motionpath_names_from_igb'] += len(names)
            else:
                self.problem('motionpath_no_object', d, zone)
                names = [d]
        return names

    # ------------------------------------------------------------------ one zone
    def zone_sources(self, zone):
        bundle = self.ctx.zone_bundle(zone)
        zx = None
        for p, k in bundle:
            if k.lower() == 'zonexml' and C.split_ext(C.norm(p))[1] in ('.eng', '.xml'):
                zx = C.norm(p)
                break
        if zx is None:
            for e in ('.eng', '.xml'):
                if self.ctx.x1_path(f'maps/{zone}{e}') is not None:
                    zx = f'maps/{zone}{e}'
                    break
        return bundle, zx

    def skip_reason(self, zone, zx):
        if zx is None or self.ctx.x1_path(zx) is None:
            return 'no zone XML (maps/<zone>.eng|.xml)'
        if self.ctx.x1_is_empty(zx):
            return f'empty zone XML ({zx})'
        igb = self.ctx.x1_path(f'maps/{zone}.igb')
        if igb is None:
            return 'no map IGB'
        if igb.stat().st_size == 0:
            return 'empty map IGB (0 bytes)'
        return None

    def convert(self, zone):
        ctx = self.ctx
        if zone in C.frontend_zones(ctx):              # --frontend xml2 only (SPEC 21: xml1 converts the backdrop)
            why = ('XML2 front end kept: XMen2.exe loads it at boot before New Game (0x6a3774); XML2 files '
                   f'{list(C.FRONTEND_ZONES[zone])}* stay the base install\'s')
            self.frontend[zone] = why
            self.detail[zone] = {'status': 'frontend_kept', 'reason': why}
            return
        bundle, zx = self.zone_sources(zone)
        why = self.skip_reason(zone, zx)
        if why:
            self.skipped[zone] = why
            self.detail[zone] = {'status': 'skipped', 'reason': why}
            return
        st = {'zone': zone, 'patched': False, 'links': [], 'nextzones': [], 'base_world_attrs': {}}
        stem = f'maps/{zone}'

        def patch(root):
            self.mutate_zone(zone, zx, root, st)
            self.analyse_zone(zone, root, st)

        res = ctx.import_x1_asset(zx, force=True, patch=patch, patch_key=PATCH_ZONE)
        if not res.ok:
            ctx.error(f'{zone}: zone XML {zx} not written ({res.status})')
            self.skipped[zone] = f'zone XML import {res.status}'
            self.detail[zone] = {'status': 'failed', 'reason': res.status}
            return
        if not st['patched']:                     # cached import (another run in this process): analyse output
            self.analyse_zone(zone, ctx.read_out_xmlb(res.out_rels[0]), st)
        if zx.endswith('.xml'):
            self._shadow_fix(res)                 # never leave a stale XML2 .engb next to an XMLB-only zone
        if st.get('no_world'):
            self.problem('no_world_entity', zone, zone)

        # characters
        chr_names = []

        def chr_patch(root):
            C.map_tree_refs(root)
            chr_names.extend(e.get('name') for e in root.iter() if e.tag.lower() == 'character' and e.get('name'))

        cres = ctx.import_x1_asset(f'{stem}.chr', force=True, patch=chr_patch, patch_key=PATCH_CHR)
        if cres.status == 'written' and not chr_names:
            chr_names = [e.get('name') for e in ctx.read_out_xmlb(f'{stem}.CHRB').iter()
                         if e.tag.lower() == 'character' and e.get('name')]
        if cres.status in ('empty', 'missing'):
            ctx.write_xmlb(stem, ET.Element('characters'), ('.CHRB',), source=f'zones:empty {stem}.chr')
            self.counts['chr_empty_written'] += 1
            if cres.status == 'missing':
                ctx.warn(f'{zone}: no {stem}.chr on the XML1 disc; wrote an empty <characters/>')
        elif not cres.ok:
            ctx.error(f'{zone}: {stem}.chr not written ({cres.status})')
        if self.stats_names is not None:
            for n in chr_names:
                if n.lower() not in self.stats_names:
                    ctx.error(f'{zone}: .chr character {n!r} is not a herostat/npcstat name')
        # nav / buoys / map
        nres = ctx.import_x1_asset(f'{stem}.nav', force=True)
        has_nav = nres.status == 'written'
        if not has_nav:
            self.counts['empty_nav'] += 1
            self.problem('nav_' + nres.status, zone, zone)
        ctx.write_xmlb(stem, ET.Element('buoy'), ('.BOYB',), source='zones:empty buoy network')
        ires = ctx.import_x1_asset(f'{stem}.igb', force=True)
        if not ires.ok:
            ctx.error(f'{zone}: map IGB not written ({ires.status})')

        pkg_entries = self.build_package(zone, bundle, st, has_nav, ires.ok)
        # ---- actor_budget (section 14): the XML1 bundle precaches the XML1 hero actors of its CHRB heroes; where
        # the name resolves to an XML2 herostat stand-in those skins/anim DBs are dead weight in XMen2.exe's
        # 40-slot actor table (mansion4_1 crash at 0x5743bb). Drops them; nothing else in the package changes.
        pkg_entries, ab_dropped = AB.prune_package_root(ctx, zone, pkg_entries, chr_names)
        if ab_dropped:
            self.pruned_actors[zone] = ab_dropped
            self.counts['actor_entries_pruned'] += len(ab_dropped)
        # ---- end actor_budget
        # ---- section 26: XML1's automap texture -> Automaps/<zone>.zam, listed last like XML2's own <zam> entries
        zam = self.automap(zone, st)
        if zam:
            ET.SubElement(pkg_entries, 'zam', {'filename': zam})
        # ---- end section 26
        pkg_rel = f'Packages/generated/maps/{zone}'
        written = ctx.write_xmlb(pkg_rel, pkg_entries, ('.PKGB',), source=f'zones:package {zone}')
        self.pkgs[written[0]] = [(e.tag, e.get('filename')) for e in pkg_entries]
        self.counts['pkg_entries'] += len(pkg_entries)
        # IGB info cache budget (section 13): records this package alone creates
        self.igb[zone] = igb_records(self.pkgs[written[0]])
        if self.igb[zone] > IGB_ZONE_ERROR:
            ctx.error(f'{zone}: package precaches {self.igb[zone]} IGBs; XMen2.exe keeps {IGB_CACHE_RECORDS} in all '
                      f'and the zone cannot load with more than {IGB_ZONE_ERROR} (section 13)')
        elif self.igb[zone] > IGB_ZONE_WARN:
            ctx.warn(f'{zone}: package precaches {self.igb[zone]} IGBs (> {IGB_ZONE_WARN}: little IGB-cache headroom '
                     f'for bigger hero packages, the team menu or on-demand loads; section 13)')
        self.converted.append(zone)
        self.zone_info[zone] = {'soundfile': st.get('soundfile'), 'zonescript': st.get('zonescript'),
                                'pkg': written[0], 'chr_names': chr_names, 'nextzones': sorted(set(st['nextzones'])),
                                'has_nav': has_nav}
        self.detail[zone] = {'status': 'converted', 'category': classify(zone), 'zonexml': zx,
                             'outputs': res.out_rels, 'zonescript': st.get('zonescript'),
                             'zonescript_how': st.get('zonescript_how'), 'soundfile': st.get('soundfile'),
                             'links': st['links'], 'chr': chr_names, 'has_nav': has_nav,
                             'no_world': bool(st.get('no_world')),
                             'world_synthesized': bool(st.get('world_synthesized')), 'pkg_entries': len(pkg_entries),
                             'igb_records': self.igb[zone],
                             'tiles': {'folders': st.get('tiles', {}).get('folders', {}),
                                       'instances': st.get('tiles', {}).get('insts', 0),
                                       'used': {f: sorted(m) for f, m in st.get('tiles', {}).get('used', {}).items()},
                                       'pruned_from_bundle': self.pruned_tiles.get(zone, [])},
                             'actors_pruned': self.pruned_actors.get(zone, []),
                             'automap': self.automaps.get(zone),
                             'base_world_attrs': st['base_world_attrs'], 'mapped_refs': st.get('mapped_refs'),
                             'rewritten': st.get('rewritten')}

    # ---- SPEC 21 (--frontend xml1): XML1's menu backdrop replaces XML2's menu/main_back
    MENU_ZONE_XML2_KINDS = ('bigconvmap',)                  # flag entries of the replaced XML2 package that are kept
    MENU_ZONE_XML2_XML = ('data/npcstat',)                  # data entries kept (XML2's menu zone preloads npcstat)

    def menu_zone_xml2_entries(self, zone):
        """[(kind, filename)] of XML2's own package of a menu backdrop zone (C.MENU_ZONES) that the converted XML1
        zone keeps: 'bigconvmap off' and 'xml data/npcstat' (M2_DESIGN A.4.1: keep XML2's bigconvmap; npcstat is
        what XML2's menu zone preloads for the menus it hosts). Nothing for any other zone."""
        if zone not in C.MENU_ZONES:
            return []
        rel = self.ctx.base_index.find(f'packages/generated/maps/{zone}', ('.PKGB',))
        if not rel:
            return []
        out = []
        for e in self.ctx.read_base_xmlb(rel):
            k, f = e.tag.lower(), C.norm(e.get('filename') or '')
            if k in self.MENU_ZONE_XML2_KINDS or (k == 'xml' and f in self.MENU_ZONE_XML2_XML):
                out.append((k, f))
        if out:
            self.counts['menu_zone_xml2_entries_kept'] += len(out)
        return out

    # ---- section 26: automaps
    def automap(self, zone, st):
        """Write Automaps/<zone>.zam from the zone's XML1 automap texture (world automap_texture /
        automap_offset; automaps.py has the XML1 and XMen2.exe mechanisms) and return the package name
        'automaps/<zone>', or None when XML1 showed no map there (no automap_texture) or the texture is missing /
        unreadable / empty (a problem is recorded). Zones sharing a texture and offset (the mansion hubs) convert
        it once."""
        tex, off = st.get('automap') or (None, None)
        tex = (tex or '').strip()
        if not tex:
            self.counts['automap_none'] += 1
            return None
        ctx = self.ctx
        rel = AM.texture_rel(tex)
        key = (rel, (off or '').strip())
        hit = self._automap_cache.get(key)
        if hit is None:
            src = ctx.x1_path(rel)
            data, info = None, {'texture': rel}
            if src is None:
                self.problem('automap_texture_missing', rel, zone)
            else:
                try:
                    data, conv = AM.convert(src.read_bytes(), off)
                    info.update(conv)
                except (AM.AutomapError, ValueError) as ex:      # IgbError is a ValueError
                    self.problem('automap_texture_unreadable', f'{rel}: {ex}', zone)
                if data is None and 'size' in info:
                    self.problem('automap_texture_empty', rel, zone)
                if info.get('offset_note'):
                    self.problem('automap_offset', f'{rel}: {info["offset_note"]}', zone)
            hit = self._automap_cache[key] = (data, info)
            if data is not None:
                self.counts['automap_textures_converted'] += 1
        data, info = hit
        if data is None:
            self.counts['automap_failed'] += 1
            return None
        ctx.write_bytes(f'Automaps/{zone}.zam', data, source=f'zones:automap {rel} offset {info["offset"]}')
        self.automaps[zone] = info
        self.counts['automaps_written'] += 1
        return f'automaps/{zone}'

    def build_package(self, zone, bundle, st, has_nav, igb_ok):
        ctx = self.ctx
        stem = f'maps/{zone}'
        pkg = Pkg()
        where = f'packages/generated/maps/{zone}'
        mp_files = []
        script_refs = set()
        for p, kind in bundle:
            if kind.lower() == 'script':
                script_refs.add(C.script_ref(p))
        if st.get('zonescript'):
            script_refs.add(st['zonescript'])
        lits = set(st.get('mp_lits', ()))
        for r in sorted(script_refs):
            lits |= self.script_literals(r)
        tiles = st.get('tiles') or {'folders': {}, 'used': {}, 'insts': 0, 'bad': []}
        tiles_used = set().union(*tiles['used'].values()) if tiles['used'] else set()

        for p, kind in bundle:
            k = kind.lower()
            n = C.norm(p)
            nstem, ext = C.split_ext(n)
            if k == 'combat_is':
                pkg.add('combat_is', n)
                for e in self.menu_zone_xml2_entries(zone):     # SPEC 21: XML2's menu-zone flags / stats table
                    pkg.add(*e)
                continue
            if ext in LANG_SKIP:
                self.counts['bundle_fre_ger_skipped'] += 1
                continue
            if nstem == stem:                                    # the zone's own files
                if k in ('zonexml', 'characters'):
                    pkg.add(k, stem)
                elif k == 'nav':
                    if has_nav:
                        pkg.add('nav', stem)
                elif k == 'model':
                    if igb_ok:
                        pkg.add('model', stem)
                else:
                    ctx.warn(f'{zone}: unexpected bundle entry {kind} {p} for the zone file; dropped')
                continue
            if k == 'script':
                ref = C.script_ref(n)
                if self.script_ok(ref):
                    pkg.add('script', f'scripts/{ref}')
                else:
                    self.problem('bundle_script_missing', ref, zone)
                continue
            if k == 'texture' and nstem.startswith(AM.TEXTURE_DIR):
                # section 26: the XML1 HUD's automap texture. XMen2.exe never reads textures/automap (its automap
                # is the <zam> entry convert() adds), so precaching it would only hold a 64-256 KB texture.
                self.counts['automap_textures_dropped'] += 1
                continue
            ce = self.char_entry(k, n)
            if ce:
                ok = self.x1_nonempty(n)
                if not ok:
                    self.problem('char_entry_' + ('missing' if ok is None else 'empty'), f'{kind} {n}', zone)
                    continue
                ze = self.zone_animdb_entry(zone, k, n)            # section 16: mission_<area> -> zone_<leaf>
                if ze is not None:
                    if ze:
                        pkg.add(*ze)
                    continue
                pkg.add(*ce)
                self.char_entries[ce].add(where)
                continue
            if k == 'motionpath':
                res = self.import_asset(n)
                if not res.ok:
                    self.problem('bundle_' + res.status, n, zone)
                    continue
                mp_files.append(n)
                for name in self.motionpath_entries(n, lits, zone):
                    pkg.add('motionpath', name)
                continue
            if k == 'model' and nstem.startswith('models/tiles/') and self.tile_mode == 'used':
                # XML1 bundles list whole tile letter sets (31-49 files per tileent); only the shapes the zone's
                # tile instances name are ever loaded (section 13), so the rest would only fill the IGB cache
                if nstem not in tiles_used:
                    self.pruned_tiles.setdefault(zone, []).append(nstem)
                    self.counts['tile_models_pruned'] += 1
                    continue
            res = self.import_asset(n)
            if res.ok or res.status == 'conflict':
                pkg.add(*C.map_package_entry(kind, n))
            elif res.status == 'skipped':
                continue
            else:
                self.problem('bundle_' + res.status, n, zone)

        # nested references of every packaged effect (textures / models / sub-effects inside the effect file)
        for k, f in list(pkg.main):
            if k == 'effect':
                self.effect_nested_into(pkg, f, zone)

        # scripts-module extras (generated dialogs / helper scripts this zone can run) and the zone script
        for kind, fn in self.prov.zone_package_extras(self.ctx, zone):
            fn = C.norm(fn)
            if kind == 'script':
                if self.script_ok(fn):
                    pkg.add('script', fn, extra=True)
                else:
                    self.problem('extra_script_missing', fn, zone)
            else:
                planned = (ctx.research_path('scripts/out') / (fn + '.XMLB')).is_file()
                if ctx.out_index.find(fn, ('.XMLB', '.engb')) or planned:
                    pkg.add(kind, fn, extra=True)
                else:
                    self.problem('extra_file_missing', fn, zone)
        if st.get('zonescript'):
            pkg.add('script', f'scripts/{st["zonescript"]}', extra=True)

        # everything the zone XML references that the bundle lacks
        self.resolve_refs(zone, pkg, st['refs'], st.get('entities', set()), lits, mp_files, tiles=tiles)

        # until nothing new is added: files referenced from the packaged XML1 data (conversations, dialogs,
        # entity files: scripts, inline code, effects, models...), and the conversations / popup dialogs the
        # packaged scripts start (a started conversation can name more scripts, which can start more)
        seen_data, seen_scripts = set(), set()
        for _ in range(8):
            todo_data = [(k, f) for k, f in pkg.main + pkg.extra
                         if k in XML_KINDS and f.startswith(FORCE_PREFIXES) and (k, f) not in seen_data]
            todo_scripts = [f for k, f in pkg.main + pkg.extra if k == 'script' and f not in seen_scripts]
            if not todo_data and not todo_scripts:
                break
            for k, f in todo_data:
                seen_data.add((k, f))
                self.resolve_refs(zone, pkg, self.data_refs(k, f), st.get('entities', set()), lits, mp_files,
                                  source=f)
            for f in todo_scripts:
                seen_scripts.add(f)
                for kind, rel in self.call_targets(self.script_text(f)):
                    self.ensure_call_target(pkg, kind, rel, zone, f'{f} call')
        else:
            ctx.warn(f'{zone}: package reference closure did not settle after 8 passes')
        return pkg.root(tail=[('boy', stem)])

    def resolve_refs(self, zone, pkg, refs, defined, lits, mp_files, source=None, tiles=None):
        ctx = self.ctx
        src = source or f'maps/{zone}'
        for cat, v, attr in refs:
            why = f'{src} @{attr}'
            if cat == 'code':
                for kind, rel in self.call_targets(v):
                    self.ensure_call_target(pkg, kind, rel, zone, why)
            elif cat == 'effect' or cat in ('precache:fx', 'precache:effect'):
                self.ensure_file(pkg, 'effect', 'effects/' + norm_effect(v), ('.xml',), zone, why)
            elif cat in ('model', 'precache:model'):
                m = strip_ext(v)
                if _UI_CHAR_ANY.match(m):                  # HUD/UI character model (already mapped +14000)
                    e = ('model', m)
                    if not pkg.has(*e):
                        pkg.add(*e, extra=True)
                        self.counts['char_refs_added'] += 1
                    self.char_entries[e].add(f'packages/generated/maps/{zone}')
                    continue
                if not m.startswith(('models/', 'maps/', 'skybox/', 'ui/', 'hud/')):
                    m = 'models/' + m
                self.ensure_file(pkg, 'model', m, ('.igb',), zone, why)
            elif cat == 'skybox':
                s = strip_ext(v)
                self.ensure_file(pkg, 'model', s if s.startswith('skybox/') else 'skybox/' + s, ('.igb',), zone,
                                 why)
            elif cat in ('texture', 'precache:texture'):
                t = strip_ext(v)
                self.ensure_file(pkg, 'texture', t if t.startswith('textures/') else 'textures/' + t, ('.igb',),
                                 zone, why)
            elif cat == 'tilefolder':
                tf = C.norm(v).strip('/')
                folder = 'models/' + tf + '/'
                if not self.tile_folder_files(tf):
                    self.problem('tilefolder_missing', folder, zone)
                    continue
                wanted = (tiles or {}).get('used', {}).get(tf)
                if self.tile_mode == 'used' and wanted is not None and (tiles or {}).get('insts'):
                    names = sorted(wanted)                    # only the tiles the zone's instances can name
                else:
                    # 'folder' mode, or a tileent without any parsable instance: the whole folder (XML2's rule)
                    if self.tile_mode == 'used':
                        self.problem('tilefolder_no_instances', folder, zone)
                    names = sorted(f'models/{tf}/{s}' for s in self.tile_folder_files(tf))
                for r in names:
                    if self.ensure_file(pkg, 'model', r, ('.igb',), zone, why) not in ('present', 'missing', 'empty'):
                        self.counts['tile_models_added'] += 1
            elif cat in ('script', 'precache:script'):
                ref = C.script_ref(v)
                if self.script_ok(ref):
                    if pkg.add('script', f'scripts/{ref}', extra=True):
                        self.counts['script_refs_added'] += 1
                else:
                    self.problem('script_ref_missing', f'{ref} ({why})', zone)
            elif cat in ('precache:conversation',):
                self.ensure_file(pkg, 'xml', 'conversations/' + strip_ext(v), ('.eng', '.xml'), zone, why)
            elif cat in ('precache:dialog',):
                self.ensure_file(pkg, 'xml_resident', 'dialogs/' + strip_ext(v), ('.eng', '.xml'), zone, why)
            elif cat in ('precache:xml_resident', 'precache:xml', 'precache:subtitle'):
                kind = 'xml' if cat == 'precache:xml' else 'xml_resident'
                rel = strip_ext(v)
                if '/' not in rel:          # bare name (haarp_ext01: xml_resident 'haarp_hint' = dialogs/haarp_hint)
                    for top in ('dialogs/', 'subtitles/', 'conversations/'):
                        if any(self.ctx.x1_path(top + rel + e) for e in ('.eng', '.xml')):
                            rel = top + rel
                            break
                self.ensure_file(pkg, kind, rel, ('.eng', '.xml'), zone, why)
            elif cat in ('motionpath', 'precache:motionpath'):
                mp = v.replace('\\', '/').lower()
                d = mp.rsplit('/', 1)[0]
                f = f'motionpaths/{d}.igb'
                if f in mp_files:
                    continue
                if self.x1_nonempty(f):
                    res = self.import_asset(f)
                    if res.ok:
                        mp_files.append(f)
                        for name in self.motionpath_entries(f, lits | {mp}, zone):
                            pkg.add('motionpath', name, extra=True)
                        self.counts['motionpath_files_added'] += 1
                        continue
                if ctx.base_exists(f'MotionPaths/{d}.IGB'):
                    pkg.add('motionpath', mp, extra=True)
                    continue
                self.problem('missing_ref', f'motionpaths/{d} ({why})', zone)
            elif cat == 'actorskin':
                s = str(v).strip()
                e = ('actorskin', s)
                if pkg.has(*e):
                    continue
                n = int(s)
                if len(s) == 5 and 14000 <= n <= 23999 and n // 100 != 200:
                    x1 = f'actors/{n - 14000:04d}.igb'
                    ok = self.x1_nonempty(x1)
                    if not ok:
                        self.problem('skin_actor_' + ('missing' if ok is None else 'empty'), f'{s} ({why})', zone)
                        continue
                elif not ctx.base_exists(f'actors/{s}.igb'):
                    self.problem('missing_ref', f'actors/{s} ({why})', zone)
                    continue
                pkg.add(*e, extra=True)
                self.char_entries[e].add(f'packages/generated/maps/{zone}')
                self.counts['skin_refs_added'] += 1
            elif cat == 'loading':
                self.loading_ref(v, f'{zone} @{attr}')
            elif cat == 'spawn':
                t = v.lower()
                if t in defined or t in self.global_ents():
                    continue
                files = self.entity_files().get(t)
                if not files:
                    self.problem('spawn_entity_unresolved', t, zone)
                    continue
                for fr in sorted(files):
                    self.ensure_file(pkg, 'xml', C.split_ext(fr)[0], (C.split_ext(fr)[1],), zone, why)
            elif cat == 'item':
                self.item_refs[v.strip().lower()].add(zone)
                if v.lower() not in self.item_names() and v.strip().lower() not in self.xp_pickups:
                    self.problem('inventoryitem_unknown', v, zone)
            elif cat == 'character':
                if self.stats_names is not None and v.lower() not in self.stats_names:
                    self.problem('spawner_character_not_in_stats', v, zone)
            elif cat.startswith('precache:'):
                self.counts['precache_' + cat.split(':', 1)[1] + '_not_packaged'] += 1

    def loading_ref(self, v, where):
        n = C.norm(v)
        if not n:
            return
        if _LOADING_NUM.match(n):
            self.loading_numeric[C.map_loading_texture(n)].add(where)
            return
        x1n = C.x1_loading_source(n) if C.frontend_mode(self.ctx) == 'xml1' else None
        if x1n:
            # SPEC 21 C.4.2: textures/loading/x1_<name> = XML1's <name> under a name XML2 does not ship
            res = self.ctx.import_x1_asset(x1n + '.igb', out_rel_noext=n)
            if res.ok:
                self.written_x1.add(C.norm(x1n + '.igb'))
                self.counts['loading_textures_renamed_' + res.status] += 1
                return
            self.problem('loading_texture_missing', f'{n} (XML1 {x1n}: {res.status})', where)
            return
        ok = self.x1_nonempty(n + '.igb')
        if ok:
            res = self.import_asset(n + '.igb')
            if res.ok:
                self.counts['loading_textures_' + res.status] += 1
                return
        if self.ctx.base_index.find(n, ('.IGB', '.png')):
            return
        self.problem('loading_texture_missing', n, where)

    # ------------------------------------------------------------------ zoneinfo
    def build_zoneinfo(self):
        ctx = self.ctx
        x1 = {}
        try:
            root = ctx.read_x1_xml('data/zoneinfo.eng')
        except KeyError:
            root = None
            ctx.error('XML1 data/zoneinfo.eng not found')
        if root is not None:
            for e in root.iter():
                if e.tag.lower() == 'zone' and e.get('name'):
                    x1[C.norm(e.get('name'))] = dict(e.attrib)
        unknown = sorted(set(x1) - set(self.converted))
        if unknown:
            ctx.note(f'zoneinfo: {len(unknown)} XML1 zoneinfo names are not converted zones (not added): '
                     f'{unknown[:12]}')
        trees = {}
        added = updated = 0
        stripped = {}
        for ext in ('.XMLB', '.engb'):
            tree = ctx.read_base_xmlb(f'Data/zoneinfo{ext}')
            top = C.iter_roots(tree)[0]
            # XML1 mode: XML2's Xtraction network is switched off. XMen2.exe registers every zoneinfo entry with
            # extraction="true" (0x468130: _stricmp at 0x468155, at most 31 at 0x46817d) and parses its towncenter /
            # act / savename / description / mapx / mapy (0x467f60); XML1 zones' xtraction_point entities call
            # extractionPoint('_OWNER_'), whose menu (0x4a6b50) offers openmenu('worldmap') over that list - XML2's
            # hub zones (whose NPC stats XML1 mode dropped) - besides the team change (extractionPointChange) and save.
            # XML1's own menu (default.xbe 0x9f110) had no world map (team change / save / load / danger room /
            # shop), and no XML1 zoneinfo entry has extraction/towncenter/mapx, so none is registered.
            # DISABLED (in-game 2026-09-27): with every towncenter stripped XMen2.exe crashes at boot while loading
            # menu/main_back (_stricmp on a null town-centre name, call at 0x486844 in 0x4867e0). XML2's Xtraction
            # entries therefore stay until XML1 hubs replace them; XML1 Xtraction points still offer XML2's world map.
            for z in top if STRIP_XTRACTION else ():
                if z.tag.lower() != 'zone':
                    continue
                gone = [k for k in XTRACTION_ATTRS if k in z.attrib]
                for k in gone:
                    del z.attrib[k]
                if gone:
                    stripped.setdefault(C.norm(z.get('name', '')), set()).update(gone)
            index = {C.norm(z.get('name', '')): z for z in top if z.tag.lower() == 'zone'}
            x1_front = C.frontend_mode(ctx) == 'xml1'
            for zone in self.converted:
                src = x1.get(zone, {})
                loading = (src.get('loading') or '').strip()
                if x1_front and not loading and zone in C.MENU_ZONES:
                    loading = C.FRONTEND_MENU_LOADING           # SPEC 21 A.4.1: XML1 has no entry for its backdrop
                if x1_front and loading:
                    # SPEC 21 C.4.2: numeric +14000 as before; an XML1 named screen XML2 also ships (x_jet,
                    # characters_menu) gets x1_<name>, so the XML1 zone shows XML1's image (and Review lists it)
                    loading = C.map_review_texture(ctx, loading)
                else:
                    loading = C.map_loading_texture(loading.replace('\\', '/')) if loading else None
                savename = src.get('savename')
                if savename and len(savename.encode('latin-1', 'replace')) > SAVENAME_MAX:
                    ctx.warn(f'zoneinfo {zone}: savename longer than {SAVENAME_MAX} bytes is truncated in-game')
                act = self.prov.zone_act(ctx, zone)
                self.zone_acts[zone] = act                                          # section 15
                el = index.get(zone)
                if el is None:
                    attrs = {'name': zone, 'act': str(act or 1), 'build': 'normal', 'state': '1'}
                    if loading:
                        attrs['loading'] = loading
                    if savename:
                        attrs['savename'] = savename
                    ET.SubElement(top, 'zone', attrs)
                    added += ext == '.XMLB'
                else:                                  # an XML2 entry of the same zone (menu/main_back)
                    if loading:
                        el.set('loading', loading)
                    if savename:
                        el.set('savename', savename)
                    if act:
                        el.set('act', str(act))
                    updated += ext == '.XMLB'
                if loading:
                    self.loading_ref(loading, f'zoneinfo {zone}')
            # ---- section 15: one registered town centre per selectable act, within the 31-entry table
            tc = self.act_towncenters(top, ext)
            # ---- end section 15
            trees[ext] = tree
        ctx.write_xmlb_pair('Data/zoneinfo', trees['.XMLB'], trees['.engb'], source='zones:zoneinfo')
        self.counts['zoneinfo_added'] = added
        self.counts['zoneinfo_updated'] = updated
        self.counts['zoneinfo_xtraction_entries_stripped'] = len(stripped)
        self.counts['zoneinfo_towncenters_stripped'] = sum(1 for v in stripped.values() if 'towncenter' in v)
        # ---- section 15: counts and notes (both trees get the same change; tc is the .engb result)
        self.towncenters = tc
        self.counts['zoneinfo_towncenters_added'] = len(tc['added'])
        self.counts['zoneinfo_xml2_destinations_stripped'] = len(tc['stripped'])
        self.counts['zoneinfo_xtraction_entries'] = tc['entries']
        ctx.note(f'zoneinfo: act town centres (XMen2.exe 0x4867e0 -> 0x4682b0 -> _stricmp 0x486844 crashes on an act '
                 f'without one): {tc["towncenters"]}; added {len(tc["added"])} at XML1 hubs {tc["added"]}; XML2\'s '
                 f'{len(tc["stripped"])} non-town-centre destinations lost {"/".join(XTRACTION_ATTRS)} (table cap '
                 f'{XTRACTION_CAP}, 0x46817d); {tc["entries"]} extraction entries registered. An XML1 Xtraction point '
                 f'(extractionPoint menu 0x4a6b50) offers team change, save and a world map listing the act\'s town centre')
        ctx.defer('XML1 Xtraction menu extras (load game, danger room, item shop via healer/forge, default.xbe '
                  '0x9f110) are not offered by XMen2.exe\'s extractionPoint menu; in-game check: the world map in an '
                  'act 6-9 zone (worldmap.XMLB has act tabs 1-5 only) and the PDA (package menus/pda_act<act> exists '
                  'for acts 0-5 only)')
        # ---- end section 15

    # ------------------------------------------------------------------ act town centres (section 15)
    def selectable_acts(self):
        """Acts the built game can select (setCurrentAct): the entry act of every converted zone (zone scripts,
        prov.zone_act), every act in research zone_acts.json (the --start-zone / --tour hooks pick from it), the
        mission plan's act groups (Data/missions/x1_act*.XMLB; every rewritten mission start sets one) and act 1
        (XMen2.exe's default, 0x468e50). Pure; cached."""
        if getattr(self, '_selectable_acts', None) is not None:
            return self._selectable_acts
        ctx = self.ctx
        acts = {1} | {int(a) for a in self.zone_acts.values() if a}
        try:
            za = ctx.research_json('scripts/out/zone_acts.json')
        except FileNotFoundError:
            za = {}
        for d in za.values():
            acts |= {int(a) for a in (d.get('acts') or ()) if str(a).isdigit()}
            if d.get('inject_act'):
                acts.add(int(d['inject_act']))
        try:
            groups = ctx.research_json('scripts/mission_plan.json').get('groups') or ()
        except FileNotFoundError:
            groups = ()
        acts |= {int(g['act']) for g in groups if str(g.get('act', '')).isdigit()}
        self._selectable_acts = acts
        return acts

    def act_towncenters(self, top, ext):
        """Section 15 (see the constants): on the zoneinfo tree `top`, strip the Xtraction attributes of XML2's
        non-town-centre destinations, then give every selectable act without a registered town centre one at an
        XML1 hub: the converted zone of that act matching TOWNCENTER_HUB_RE (X-Mansion ground floor), else a
        mansion/* zone of the act, else the act's first zone in New Game reach order; a zone of another act only
        when the act has none (warned). Returns {'stripped': [zones], 'added': {act: zone}, 'towncenters':
        {act: zone}, 'entries': registered extraction entries}."""
        ctx = self.ctx
        conv = set(self.converted)

        def true(el, k):                                   # XMen2.exe: _stricmp(value, "true") == 0
            return (el.get(k) or '').strip().lower() == 'true'

        zones = [z for z in top if z.tag.lower() == 'zone']
        stripped = []
        if XTRACTION_STRIP_XML2_DESTINATIONS:
            for el in zones:
                name = C.norm(el.get('name', ''))
                if name in conv or not true(el, 'extraction') or true(el, 'towncenter'):
                    continue
                for k in XTRACTION_ATTRS:
                    el.attrib.pop(k, None)
                stripped.append(name)
        have = {}
        for el in zones:
            if true(el, 'extraction') and true(el, 'towncenter'):
                a = (el.get('act') or '').strip()
                have.setdefault(int(a) if a.isdigit() else 1, C.norm(el.get('name', '')))   # 0x4680a0: act defaults to 1
        index = {C.norm(el.get('name', '')): el for el in zones}
        try:
            reach = {z: i for i, z in enumerate(ctx.tour_order())}
        except (OSError, KeyError, ValueError):
            reach = {}
        added = {}
        for act in sorted(self.selectable_acts() - set(have)):
            cands = [z for z in self.converted if self.zone_acts.get(z) == act and z in index]
            own = bool(cands)
            if not cands:
                cands = [z for z in self.converted if z in index]
            if not cands:
                ctx.error(f'Data/zoneinfo{ext}: act {act} has no town centre and no converted zone to make one of; '
                          f'entering any zone in act {act} crashes XMen2.exe (0x4867e0 -> 0x4682b0 NULL -> _stricmp '
                          f'0x486844)')
                continue
            cands.sort(key=lambda z: (0 if TOWNCENTER_HUB_RE.match(z) else 1 if z.startswith('mansion/') else 2,
                                      reach.get(z, len(reach)), z))
            zone = cands[0]
            el = index[zone]
            el.set('extraction', 'true')
            el.set('towncenter', 'true')
            el.set('act', str(act))
            if not (el.get('mapx') or '').strip():
                el.set('mapx', TOWNCENTER_MAP_XY[0])
            if not (el.get('mapy') or '').strip():
                el.set('mapy', TOWNCENTER_MAP_XY[1])
            if not (el.get('savename') or '').strip():                  # 0x467fe0 returns NULL without one
                el.set('savename', TOWNCENTER_SAVENAME if zone.startswith('mansion/')
                       else zone.rsplit('/', 1)[0].rsplit('/', 1)[-1])
            added[act] = have[act] = zone
            if not own:
                ctx.warn(f'Data/zoneinfo{ext}: act {act} has no converted zone of its own; {zone} (act '
                         f'{self.zone_acts.get(zone)}) is registered as its town centre')
        entries = [C.norm(el.get('name', '')) for el in zones if true(el, 'extraction')]
        if len(entries) > XTRACTION_CAP:
            ctx.error(f'Data/zoneinfo{ext}: {len(entries)} extraction entries > {XTRACTION_CAP} (0x46817d); XMen2.exe '
                      f'never registers {entries[XTRACTION_CAP:]}')
        return {'stripped': stripped, 'added': added, 'towncenters': dict(sorted(have.items())),
                'entries': len(entries)}

    # ------------------------------------------------------------------ items (XML1 -> XML2 schema)
    def translate_item(self, c):
        """XML1 <item> -> XML2 schema (XMen2.exe item parser 0x47aeff..0x47af96: type is one of item(0) potion(1)
        equipment(2) money(3); frequency / group / activepowerup / numeric class+quality are never read). Returns
        (element, note) or (None, reason)."""
        t = (c.get('type') or 'item').strip().lower()
        keep = {k: c.get(k) for k in ITEM_KEEP_ATTRS if c.get(k) is not None}
        note = None
        if t in ITEM_TYPE_MAP:
            new_t, extra, note = ITEM_TYPE_MAP[t]
            keep['type'] = new_t
            keep.update(extra)
        elif t == 'equipment':
            # XML2 equipment needs class armor/gloves/belt + <enhancement><powerup><affecter> (XML1: numeric class
            # + <activepowerup>, never read by XMen2.exe): a referenced XML1 equipment pickup becomes a plain
            # inventory item; its bonus is part of the deferred powers/items rework
            keep['type'] = 'item'
            note = 'equipment -> item (its activepowerup bonus is deferred to the powers/items rework)'
        elif t in ('item', 'potion', 'money'):
            keep['type'] = t
        else:
            return None, f'type {t!r} has no XML2 equivalent'
        if keep.get('activateonpickup') is not None:
            keep['activateonpickup'] = keep['activateonpickup'].strip().lower()
        return ET.Element('item', keep), note

    def items_to_add(self, x1top, have):
        """XML1 items the converted content references by name (inventoryitem) that XML2 lacks, translated."""
        out, report = [], []
        dr_items = self.dr_reward_items()
        for c in x1top:
            nm = (c.get('name') or '').strip()
            if c.tag.lower() != 'item' or not nm or nm.lower() in have:
                continue
            if nm.lower() not in self.item_refs:
                self.counts['items_x1_unreferenced_not_added'] += 1
                continue
            if nm.lower() in dr_items:
                # SPEC 21 B.4: a Danger Room challenge reward keeps its XML1 bonus as XML2 equipment
                from . import frontend as FE
                el, note = FE.translate_equipment(self.ctx, c)
                if el is not None:
                    self.counts['items_dr_equipment'] += 1
            else:
                el, note = self.translate_item(c)
            if el is None:
                report.append(f'{nm}: not added ({note})')
                continue
            out.append(el)
            report.append(f'{nm} (type {c.get("type")!r} -> {el.get("type")!r}'
                          + (f', onactivate {el.get("onactivate")!r}' if el.get('onactivate') else '')
                          + (f'; {note}' if note else '') + f'; used by {sorted(self.item_refs[nm.lower()])[:3]})')
        # SPEC 23.1: one item per XML1 XP pickup amount (--xp-curve xml1), from XML1's own XP item
        by_name = {(c.get('name') or '').lower(): c for c in x1top}
        for low, (base, amount) in sorted(self.xp_pickups.items()):
            if low in have or low not in self.item_refs:
                continue
            src = by_name.get(base.lower())
            el = self.translate_item(src)[0] if src is not None else None
            if el is None:
                report.append(f'{low}: not added (XML1 item {base} missing)')
                continue
            el.set('name', XP_PICKUP_ITEM.format(item=base, amount=amount))
            el.set('onactivate', XP_PICKUP_SCRIPT.format(amount=amount))
            out.append(el)
            have.add(low)
            self.counts['items_xp_pickup_amounts'] += 1
            report.append(f'{el.get("name")} (XML1 {base} pickup of {amount} XP -> onactivate {el.get("onactivate")!r}: '
                          f'XML1 gives the pickup\'s count to the hero who takes it; used by '
                          f'{sorted(self.item_refs[low])[:3]})')
        return out, report

    def dr_reward_items(self):
        """lowercase XML1 item names the XML1 Danger Room courses award (--frontend xml1, SPEC 21 B.4;
        frontend.dr_reward_items), else empty."""
        if C.frontend_mode(self.ctx) != 'xml1':
            return {}
        if getattr(self, '_dr_items', None) is None:
            from . import frontend as FE
            self._dr_items = {n.lower(): n for n in FE.dr_reward_items(self.ctx)}
        return self._dr_items

    # ------------------------------------------------------------------ world tables
    def build_world_tables(self):
        ctx = self.ctx
        for low, name in sorted(self.dr_reward_items().items()):
            self.item_refs[low].add('data/dangerroom (SPEC 21 challenge reward)')
        tables = (('common_ents', 'data/common_ents.xml'), ('item_ents', 'data/item_ents.xml'),
                  ('items', 'data/items.eng'), ('shared_nodes', 'data/shared_nodes.eng'))
        for name, x1rel in tables:
            try:
                x1root = ctx.read_x1_xml(x1rel)
            except KeyError:
                x1root = None
            if x1root is None:
                ctx.error(f'world table {x1rel}: missing or empty on the XML1 disc')
                continue
            ctx.x1_schema(x1root, x1rel)
            C.map_tree_refs(x1root)
            self.prov.rewrite_data_tree(ctx, x1root, x1rel)
            x1top = C.iter_roots(x1root)[0]
            if name == 'items':
                have = set()
                for ext in ('.XMLB', '.engb'):
                    if ctx.base_exists(f'Data/items{ext}'):
                        have |= {(c.get('name') or '').lower() for c in C.iter_roots(ctx.read_base_xmlb(
                            f'Data/items{ext}'))[0] if c.get('name')}
                x1top, item_report = self.items_to_add(x1top, have)
                ctx.note(f'Data/items: XML1 items appended only when converted content references them by name '
                         f'(inventoryitem), translated to XML2 item schema: {item_report or "none"}; '
                         f'{self.counts.get("items_x1_unreferenced_not_added", 0)} unreferenced XML1 items (equipment '
                         f'with <activepowerup>, which XMen2.exe never reads) not added - deferred with the powers/'
                         f'items rework, so XML2\'s random-drop pool is unchanged')
            exts = [e for e in ('.XMLB', '.engb') if ctx.base_exists(f'Data/{name}{e}')]
            if not exts:
                ctx.error(f'world table Data/{name}: not in the base install')
                continue
            trees, added_names, xml2_wins, unnamed = {}, [], 0, 0
            for ext in exts:
                tree = ctx.read_base_xmlb(f'Data/{name}{ext}')
                top = C.iter_roots(tree)[0]
                have = {(c.get('name') or '').lower() for c in top if c.get('name')}
                for c in x1top:
                    nm = c.get('name')
                    if not nm:
                        unnamed += ext == exts[0]
                        continue
                    if nm.lower() in have:
                        xml2_wins += ext == exts[0]
                        continue
                    top.append(copy.deepcopy(c))
                    have.add(nm.lower())
                    if ext == exts[0]:
                        added_names.append(nm)
                trees[ext] = tree
            if len(exts) == 2:
                ctx.write_xmlb_pair(f'Data/{name}', trees['.XMLB'], trees['.engb'], source=f'zones:{x1rel}')
            else:
                ctx.write_xmlb(f'Data/{name}', trees[exts[0]], tuple(exts), source=f'zones:{x1rel}')
            self.counts[f'{name}_added'] = len(added_names)
            ctx.note(f'Data/{name}: {len(added_names)} XML1 entries added, {xml2_wins} same-name entries kept '
                     f'as XML2, {unnamed} unnamed XML1 children skipped')
            # package: XML2's generated PKGB + missing entries of the XML1 bundle + files the added entries use
            added = [c for c in x1top if c.get('name') in set(added_names)]
            if name in ('common_ents', 'item_ents'):
                for c in added:                     # world-table pickups name items too (items table is next)
                    for el in c.iter():
                        v = (el.get('inventoryitem') or '').strip()
                        if v:
                            self.item_refs[v.lower()].add(f'data/{name}')
            only_files = None
            if name == 'items':                     # only the pickup models of the items actually appended
                only_files = {C.norm('models/' + strip_ext(c.get('model'))) for c in added if c.get('model')}
            self.merge_package(f'Packages/generated/{name}', f'packages/generated/{name}.fb',
                               skip={f'data/{name}'}, extra_refs=[r for c in added for r in self.extract_refs(c)],
                               label=name, only_files=only_files)
            if name == 'items':
                self._item_names = None

    def merge_package(self, pkg_rel, bundle_key, skip=(), extra_refs=(), only_kinds=None, x1_only=False,
                      label='', only_files=None):
        ctx = self.ctx
        base = ctx.read_base_xmlb(pkg_rel + '.PKGB')
        pkg = Pkg((e.tag, e.get('filename', '')) for e in base)
        before = len(pkg)
        bundle = ctx.manifest.get(bundle_key, [])
        kept = 0
        for p, kind in bundle:
            k = kind.lower()
            n = C.norm(p)
            nstem, ext = C.split_ext(n)
            if ext in LANG_SKIP or nstem in skip or k == 'combat_is':
                continue
            if only_kinds and k not in only_kinds:
                continue
            if only_files is not None and nstem not in only_files:
                continue
            if self.char_entry(k, n):
                continue                               # character namespace / XML2-shared anim DBs
            if k == 'script':
                ref = C.script_ref(n)
                if self.script_ok(ref):
                    pkg.add('script', f'scripts/{ref}', extra=True)
                continue
            res = self.import_asset(n)
            if res.status == 'kept_xml2':
                kept += 1
                if x1_only:
                    continue
            if res.ok:
                if pkg.add(*C.map_package_entry(kind, n), extra=True) and k == 'effect':
                    self.effect_nested_into(pkg, C.map_package_entry(kind, n)[1], label)
            elif res.status != 'skipped':
                self.problem('bundle_' + res.status, n, label)
        if extra_refs:
            self.resolve_refs(label, pkg, extra_refs, set(), set(), [], source=bundle_key)
        # nested refs of XML1 effects appended
        for k, f in list(pkg.extra):
            if k == 'effect':
                self.effect_nested_into(pkg, f, label)
        root = pkg.root()
        ctx.write_xmlb(pkg_rel, root, ('.PKGB',), source=f'zones:{bundle_key}')
        self.pkgs[C.norm(pkg_rel + '.PKGB')] = [(e.tag, e.get('filename')) for e in root]
        n_added = len(pkg) - before
        self.counts[f'{label}_pkg_appended'] = n_added
        ctx.note(f'{pkg_rel}.PKGB: {n_added} entries appended ({kept} bundle files kept as XML2)')
        return n_added

    def build_permanent(self):
        n = self.merge_package('Packages/generated/maps/package/permanent',
                               'packages/generated/maps/package/permanent.fb',
                               only_kinds={'model', 'texture', 'effect'}, x1_only=True, label='permanent')
        self.counts['permanent_appended'] = n
        self.build_permanent_fightstyles()

    def build_permanent_fightstyles(self):
        """XML1 keeps fightstyle_villain resident through maps/package/permanent_fightstyles (37 XML1 NPCs have
        the fightstyle_villain talent and their character bundles do not list it); XML2's
        permanent_fightstyles (XMen2.exe string 'maps/package/permanent_fightstyles') has no villain entries and
        no XML2 NPC package loads it. Append the XML1 entries XML2's package lacks. Fightstyles and fightstyle_*
        anim DBs are shared with XML2 by name (SPEC 4.4: XML2's files are used), so nothing is imported: an
        entry is appended only if its file is in <out> / the base install."""
        ctx = self.ctx
        rel = 'Packages/generated/maps/package/permanent_fightstyles'
        bundle = ctx.manifest.get('packages/generated/maps/package/permanent_fightstyles.fb', [])
        if not ctx.base_exists(rel + '.PKGB') or not bundle:
            ctx.warn(f'{rel}.PKGB or the XML1 permanent_fightstyles bundle is missing; not merged')
            return
        pkg = Pkg((e.tag, e.get('filename', '')) for e in ctx.read_base_xmlb(rel + '.PKGB'))
        before = len(pkg)
        for p, kind in bundle:
            n = C.norm(p)
            if C.split_ext(n)[1] in LANG_SKIP:
                continue
            entry = C.map_package_entry(kind, n)
            if pkg.has(*entry):
                continue
            cands = C.package_entry_files(*entry) or []
            if any(c in ctx.out_index or c in ctx.base_index for c in cands):
                pkg.add(*entry, extra=True)
            else:
                self.problem('permanent_fightstyles_unresolved', f'{entry[0]} {entry[1]}', 'permanent_fightstyles')
        added = len(pkg) - before
        if added:
            root = pkg.root()
            ctx.write_xmlb(rel, root, ('.PKGB',), source='zones:packages/generated/maps/package/permanent_fightstyles.fb')
            self.pkgs[C.norm(rel + '.PKGB')] = [(e.tag, e.get('filename')) for e in root]
        self.counts['permanent_fightstyles_appended'] = added
        ctx.note(f'{rel}.PKGB: {added} XML1 entries appended ({[e for e in pkg.extra]})')

    # ------------------------------------------------------------------ final checks
    def final_checks(self):
        ctx = self.ctx
        reg = ctx.registry
        owners = collections.Counter(e['owner'] for e in reg.entries.values())
        selected = set(ctx.shared.get('selected_modules') or ())
        chars_active = 'characters' in selected or owners.get('characters', 0) > 0
        scripts_active = 'scripts' in selected or owners.get('scripts', 0) > 0
        unresolved = collections.defaultdict(set)
        pending = collections.Counter()
        checked = 0
        for rel, entries in self.pkgs.items():
            for kind, fn in entries:
                cands = C.package_entry_files(kind, fn)
                if cands is None:
                    continue
                checked += 1
                if any(c in ctx.out_index for c in cands):
                    continue
                k = kind.lower()
                owner = 'characters' if (k in ('actorskin', 'actoranimdb', 'fightstyle') or
                                         (k == 'model' and _UI_CHAR_ANY.match(fn))) else \
                    'scripts' if (k == 'script' or fn.startswith('dialogs/x1/')) else 'zones'
                if owner == 'characters' and not chars_active:
                    pending['characters'] += 1
                elif owner == 'scripts' and not scripts_active:
                    pending['scripts'] += 1
                else:
                    unresolved[(owner, kind, fn)].add(rel)
        self.counts['pkg_entries_checked'] = checked
        for (owner, kind, fn), rels in sorted(unresolved.items()):
            msg = (f'package entry {kind} {fn!r} resolves to no file in <out> (owner {owner}); listed by '
                   f'{len(rels)} package(s), e.g. {sorted(rels)[0]}')
            if owner == 'zones':
                ctx.error(msg)
            else:
                ctx.warn(msg)
        self.counts['pkg_entries_unresolved'] = len(unresolved)
        for owner, n in pending.items():
            ctx.note(f'{n} package entries point at {owner}-module files that are not in <out> because that module '
                     f'did not run in this build (checked by validate V4 in a full build)')
            self.counts[f'pkg_entries_pending_{owner}'] = n
        for tex, users in sorted(self.loading_numeric.items()):
            if ctx.out_index.find(tex, ('.IGB', '.png')) is None and ctx.base_index.find(tex, ('.IGB',)) is None:
                if chars_active:
                    ctx.warn(f'numeric loading screen {tex} (characters module) is not in <out>; used by '
                             f'{sorted(users)[:3]}')
                else:
                    self.counts['loading_textures_pending_characters'] += 1

    def report_problems(self):
        ctx = self.ctx
        levels = {
            'no_world_entity': 'error', 'zonescript_missing': 'warn', 'zonescript_removed': 'warn',
            'soundfile_banks_missing': 'warn', 'nav_empty': 'warn', 'nav_missing': 'warn',
            'prevzone_unresolved': 'warn', 'nextzone_unresolved': 'warn', 'missing_ref': 'warn',
            'script_ref_missing': 'warn', 'bundle_script_missing': 'warn', 'extra_script_missing': 'error',
            'extra_file_missing': 'error', 'bundle_missing': 'warn', 'bundle_empty': 'warn',
            'bundle_conflict': 'error', 'char_entry_missing': 'warn', 'char_entry_empty': 'warn',
            'ref_empty': 'warn', 'ref_conflict': 'error', 'ref_missing': 'warn', 'ref_skipped': 'warn',
            'spawn_entity_unresolved': 'warn', 'inventoryitem_unknown': 'warn', 'tilefolder_missing': 'warn',
            'tilefolder_no_instances': 'warn', 'tile_inst_unresolved': 'warn',
            'motionpath_no_object': 'warn', 'skin_actor_missing': 'warn', 'skin_actor_empty': 'warn',
            'loading_texture_missing': 'warn', 'spawner_character_not_in_stats': 'error',
            'world_synthesized': 'warn', 'soundfile_substituted': 'warn', 'soundfile_dropped': 'warn',
            'call_target_missing': 'warn',
            'permanent_fightstyles_unresolved': 'error'}
        summary = {}
        for kind, items in sorted(self.problems.items()):
            lvl = levels.get(kind, 'warn')
            summary[kind] = {item: sorted(zs) for item, zs in sorted(items.items())}
            fn = ctx.error if lvl == 'error' else ctx.warn
            for item, zs in sorted(items.items()):
                zs = sorted(zs)
                fn(f'{kind}: {item} [{len(zs)} zone(s): {", ".join(zs[:4])}{" ..." if len(zs) > 4 else ""}]')
        return summary


# ---------------------------------------------------------------------------------------------- hero NPC zones
NEW_GAME_PARTY = ('magneto', 'cyclops', 'wolverine', 'storm')   # XMen2.exe startFirstMission (0x4a7b41-0x4a7bef)


def _hero_npc_zones(ctx, Z):
    """{zone: [XML2 herostat names its CHRB lists]} for the reachable converted zones that spawn an XML2 stand-in
    hero as an NPC (XML1 hub zones place the X-Men as NPCs). With XML2's New Game party (magneto / cyclops /
    wolverine / storm) in play, a script addressing e.g. 'cyclops' may hit the player's hero instead of the NPC:
    an in-game check (SPEC 12)."""
    try:
        heroes = {(s.get('name') or '').lower() for s in ctx.read_base_xmlb('Data/herostat.engb').iter('stats')}
    except KeyError:
        return {}
    try:
        reach = set(ctx.tour_order())
    except (OSError, KeyError, ValueError):
        reach = set(Z.converted)
    out = {}
    for z in Z.converted:
        names = sorted({n.lower() for n in (Z.zone_info.get(z) or {}).get('chr_names') or ()} & heroes - {'default'})
        if names and z in reach:
            out[z] = names
    per_hero = collections.Counter(n for v in out.values() for n in v)
    party = {z: [n for n in v if n in NEW_GAME_PARTY] for z, v in out.items()}
    party = {z: v for z, v in party.items() if v}
    ctx.set_count('zones_spawning_xml2_hero_npcs', len(out))
    ctx.note(f'{len(out)} reachable zones spawn XML2 stand-in heroes as NPCs ({dict(per_hero)}); {len(party)} of them '
             f'spawn a hero of XML2\'s New Game party (magneto/cyclops/wolverine/storm), where scripts addressing that '
             f'name may hit the player\'s hero: {party}')
    return out


# ---------------------------------------------------------------------------------------------- entry point
def run(ctx):
    prov, used = load_providers(ctx)
    for name, src in used.items():
        if src != 'scripts':
            ctx.note(f'provider {name}: using {src} (tools/xml1build/scripts.py does not define it)')
    Z = Zones(ctx, prov)
    zones = Z.all_zones
    ctx.log(f'{len(zones)} XML1 zones; providers: {sorted(set(used.values()))}; stats names: '
            f'{len(Z.stats_names) if Z.stats_names else "not checked"} ({Z.stats_source})')
    if Z.stats_names is None:
        ctx.note(f'CHR / spawner character names not checked by zones ({Z.stats_source}); validate V6 checks them')
    for i, zone in enumerate(zones, 1):
        Z.convert(zone)
        if i % 25 == 0 or i == len(zones):
            ctx.log(f'{i}/{len(zones)} zones ({len(Z.converted)} converted, {len(Z.skipped)} skipped)')
    for z, why in sorted(Z.skipped.items()):
        ctx.note(f'zone skipped: {z}: {why}')

    Z.build_zoneinfo()
    Z.build_world_tables()
    Z.build_permanent()

    if Z.music:
        ctx.defer(f'{len(Z.music)} zones set XML1 per-zone music (ambientmusic/combatmusic) that XMen2.exe ignores; '
                  f'they play <soundfile>_a/_c instead: {sorted(Z.music)}')
    # section 26: automaps
    if Z.automaps:
        worst = max(Z.automaps.items(), key=lambda kv: kv[1].get('window', 0))
        ctx.note(f'{len(Z.automaps)} zones got Automaps/<zone>.zam from their XML1 automap texture '
                 f'({Z.counts["automap_textures_converted"]} texture/offset pairs converted); largest draw window '
                 f'{worst[1].get("window")} strip vertices ({worst[0]}; builder {AM.VB_CAPACITY})')
        ctx.set_count('automaps_written', len(Z.automaps))
        ctx.set_count('automap_max_window', worst[1].get('window', 0))
    ctx.note(f'{Z.counts["automap_none"]} converted zones have no XML1 automap_texture (no map in XML1; no .zam); '
             f'{Z.counts["automap_textures_dropped"]} textures/automap package entries dropped (XMen2.exe reads '
             f'only .zam; world automap_texture / automap_offset stay, read into dead fields at 0x4c7f90)')
    for z, why in sorted(Z.frontend.items()):
        ctx.note(f'{z}: not converted - {why} (the proven test copy xml2_test ran with them; XML1\'s backdrop was '
                 f'never loaded by XMen2.exe and carries no campaign content)')
        for p in C.FRONTEND_ZONES[z]:
            for a in ctx.base_index.under(p.rstrip('.').rsplit('/', 1)[0] + '/'):
                if C.norm(a).startswith(p) and ctx.registry.get(a) is not None:
                    ctx.error(f'{a}: XML2 front-end file of {z} was written this build (must stay XML2\'s)')
    ctx.set_count('frontend_zones_kept_xml2', len(Z.frontend))
    # XML1 -> XML2 schema conversions (x1schema via import_x1_asset / world tables), all modules of this build
    slog = ctx.schema_log
    for kind in sorted(slog):
        files = slog[kind]
        ctx.set_count('x1schema_' + re.sub(r'[^a-z0-9]+', '_', kind.lower()).strip('_'), sum(files.values()))
    for kind in sorted(k for k in slog if k.startswith('class:')):
        old, new = kind[len('class:'):].split('->')
        from . import x1schema as XS
        zs = sorted({f for f in slog[kind]})
        ctx.note(f'entity class {old} -> {new} (XMen2.exe does not register {old}; unknown classes become the bare '
                 f'0x70-byte ent via 0x4611a0/0x718444): {sum(slog[kind].values())} entities in {len(zs)} files, '
                 f'e.g. {zs[:6]}; lost: {XS.CLASS_REMAP_LOSSES.get(old)}')
    if 'turret_model' in slog:
        ctx.note(f'{sum(slog["turret_model"].values())} remapped scan turrets got their turretweapon model '
                 f'(XML1 draws the turret with it): {sorted(slog["turret_model"])}')
    mount = {k: v for k, v in slog.items() if k.startswith('turret_mount:')}
    if mount:
        flags = ', '.join('%s x%d' % (k.split(':', 1)[1], sum(v.values())) for k, v in sorted(mount.items()))
        mfiles = sorted({f for v in mount.values() for f in v})
        ctx.note(f'remapped scan turrets keep XML1\'s fixed mount: {flags} set (x1schema.TURRET_MOUNT_FLAGS, as on '
                 f'every XML1 physent of the same tanks) in {mfiles}')
    if any(k.startswith('attr:') for k in slog):
        ctx.note('renamed entity attributes: ' + ', '.join(f'{k[5:]} x{sum(v.values())}' for k, v in sorted(slog.items())
                                                           if k.startswith('attr:')))
    if 'effect_files_recoloured' in slog:
        ctx.note(f'{sum(slog["effect_primitives_recoloured"].values())} primitives in '
                 f'{len(slog["effect_files_recoloured"])} XML1 effect files converted from red/green/blue curves to '
                 f'XML2 start/mid/endColor1/2 (sampled at t=0/0.5/1; ABGR; constant alpha folded into A, varying '
                 f'alpha kept with A=0xFF; exact on XML2\'s own converted test effects). Varying-colour curves are '
                 f'approximated by 3 keys: in-game check')
    ctx.defer('XML1 scan turrets (scanturretent) are physents in XML2: they can be destroyed (deathscripts fire) '
              'but no longer aim or fire; a turret needs an XML2 AI/NPC stand-in (powers rework)')
    unconverted_links = sorted({(z, l['target']) for z in Z.converted for l in Z.detail[z]['links']
                                if l['target'] and l['target'] in Z.skipped})
    for z, t in unconverted_links:
        ctx.warn(f'{z}: links to skipped zone {t} ({Z.skipped[t]})')

    Z.final_checks()
    problems = Z.report_problems()
    dup_heroes = _hero_npc_zones(ctx, Z)
    # IGB info cache (section 13)
    top = sorted(Z.igb.items(), key=lambda kv: -kv[1])[:8]
    ctx.set_count('igb_records_max', top[0][1] if top else 0)
    ctx.set_count('zones_over_igb_warn', sum(1 for v in Z.igb.values() if v > IGB_ZONE_WARN))
    ctx.set_count('zones_over_igb_error', sum(1 for v in Z.igb.values() if v > IGB_ZONE_ERROR))
    ctx.note(f'IGB info cache (XMen2.exe: {IGB_CACHE_RECORDS} records in all, ~51 resident with the New Game party): '
             f'tiles={Z.tile_mode}; {Z.counts.get("tile_models_pruned", 0)} bundle tile models pruned in '
             f'{len(Z.pruned_tiles)} zones; largest zone packages: {top}')

    ctx.shared['zones_converted'] = list(Z.converted)
    ctx.shared['zones_skipped'] = {**Z.skipped, **Z.frontend}
    ctx.shared['zone_info'] = Z.zone_info
    ctx.shared['zone_animdbs'] = Z.zone_animdbs                                          # section 16
    lost = sorted(z for z, r in Z.zone_animdbs.items() if r['status'] == 'lost')
    ctx.set_count('zone_animdb_zones', sum(1 for r in Z.zone_animdbs.values() if r['status'] != 'lost'))
    ctx.note(f'zone anim DBs (XMen2.exe attaches "zone_<leaf>" per zone, never XML1\'s mission_<area>): '
             f'{Z.counts.get("zone_animdb_entries", 0)} zone packages list their zone_<leaf> DB, '
             f'{len(Z._zone_animdb_written)} files written from {len(set(Z._zone_animdb_written.values()))} XML1 '
             f'mission DBs; {len(lost)} zones lost their leaf to another area and keep zone_shared: {lost}')

    owned = ctx.registry.owned_by(ctx.module)
    ctx.set_count('zones_converted', len(Z.converted))
    ctx.set_count('zones_skipped', len(Z.skipped))
    ctx.set_count('files_written', len(owned))
    ctx.set_count('kept_xml2', len(Z.kept_files))
    ctx.set_count('missing_refs', sum(len(v) for k, v in Z.problems.items()
                                      if k in ('missing_ref', 'ref_missing', 'ref_empty', 'script_ref_missing',
                                               'bundle_missing', 'bundle_empty', 'spawn_entity_unresolved',
                                               'call_target_missing')))
    ctx.set_count('empty_nav', Z.counts.pop('empty_nav', 0))
    ctx.set_count('crossdir_links_fixed', Z.counts.pop('crossdir_links_fixed', 0))
    ctx.set_count('pkg_entries', Z.counts.pop('pkg_entries', 0))
    for k, v in sorted(Z.counts.items()):
        ctx.set_count(k, v)
    ctx.write_meta('zones_detail.json', {'providers': used, 'converted': Z.converted, 'skipped': Z.skipped,
                                         'frontend_kept_xml2': Z.frontend,
                                         'zones': Z.detail, 'zone_info': Z.zone_info, 'problems': problems,
                                         'music_overrides': Z.music, 'kept_xml2': sorted(Z.kept_files),
                                         'hero_npc_zones': dup_heroes,
                                         'towncenters': Z.towncenters,                   # section 15
                                         'zone_animdbs': Z.zone_animdbs,                 # section 16
                                         'counts': dict(ctx.report.mod(ctx.module)['counts'])})
    ctx.log(f'done: {len(Z.converted)} zones converted, {len(Z.skipped)} skipped, {len(owned)} files owned')
