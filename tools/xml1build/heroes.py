"""xml1build.heroes - XML1's playable roster on XMen2.exe (tools/xml1build/SPEC_heroes.md; design in
research/heroes/DESIGN.md).

Runs after `characters` and before `scripts` / `zones` / `media` (common.MODULE_ORDER). What run(ctx) produces:

  * Data/herostat.{XMLB,engb}: exactly 21 entries (D1): XML2's `default` verbatim, the 15 XML1 heroes in XML1
    herostat order, a hidden `Magneto` placeholder (startFirstMission seats that name, 0x4a7b41), three hidden
    pads x1pad1..3 (clones of `default`, no team / playable, so the team menu never lists them) and ProfXGladiator,
    the XML1 npcstat hero astral_sk / boss_shadowking seat (ROSTER_NPC, in the fourth pad's slot);
    --hero-roster 17 drops the pads, 21xml2 replaces them (and the gladiator) by XML2's Deadpool / Ironman /
    Professorx / Sunfire;
  * Data/talents/<name>.{XMLB,engb} per hero: the XML1 inline talent trees in XML2 talent-file form (explicit
    <level>s, <talentvalues> for every attribute the XML1 power rungs changed per rank, activepowerups as
    <powerup>/<affecter>), plus the hero-only passives under hero-prefixed names (x1_<hero>_<name>);
  * Data/powerstyles/<mapped>.{XMLB,engb} (over the names characters wrote): every XML1 power chain (root +
    inherit/fallback rungs) collapsed into ONE FightMove named power1/power2/power3/power9 whose per-rank numbers
    are %talentvalue references; non-power moves kept; value codes resolved to XML1's numbers; XML1 powerup
    triggers rewritten to XML2's <affecter> form;
  * Packages/generated/characters/<name>_<skin>[_nc].PKGB for every costume, <name>_xml.PKGB, placeholder
    packages, and menus/characters_heads(.PKGB|_pc.PKGB);
  * Data/npcstat.{XMLB,engb} patched: the 6 hero-as-NPC entries removed (a name registers once, 0x44c3c9) and
    <talent> children naming dropped shared talents removed; one speaker entry <hero>_x1double per renamed NPC
    double that speaks in a conversation, and one per NPC that speaks under its own XML1 name (SPEC 18.1,
    scripts_transform.speaker_stats_entries);
  * Data/shared_talents.{XMLB,engb} pruned 88 -> 47 so that shared + the 4 party files stay under XMen2.exe's
    100 registered-talent pool (0x4bdfe4 / 0x4be7e4 / 0x4be044 cmp ecx,0x64; silent drop at 0x4c0080);
    toughness / mutantmastery / acrobatics get XML1's real definitions.

Every XMen2.exe fact used here is cited in DESIGN.md section 2 (E1..E20) and research/heroes/engine.md. Nothing
here launches the game. Provider: hero_plan(ctx) is pure (cached in ctx.shared['heroes_plan']).
"""
from __future__ import annotations

import collections
import copy
import json
import os
import re
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

from . import common as C
from . import combat_events as CE
from . import npc_values as NV     # SPEC 24: value codes, the NPC energy talent
from . import scripts_transform as ST   # SPEC 18.1: the renamed NPC doubles that speak (NPC_DOUBLE_SPEAKERS)
from .lib import x1names as N   # the XML1 namespace (was research/characters/x1names.py)

# ------------------------------------------------------------------------------------------------ constants
ROSTER_X1 = ('Beast', 'Colossus', 'Cyclops', 'Frost', 'Gambit', 'Iceman', 'Jubilee', 'Magma', 'Nightcrawler',
             'Phoenix', 'ProfXAstral', 'Psylocke', 'Rogue', 'Storm', 'Wolverine')      # XML1 herostat.eng order
PLACEHOLDER = 'Magneto'                        # startFirstMission seats the *name* magneto (0x4a7b41 push 0x682504)
PADS = ('x1pad1', 'x1pad2', 'x1pad3', 'x1pad4')
# XML1 npcstat entries the port makes playable herostat heroes (FORCED_TEAMS_DESIGN 7.3). XML1 seated ProfXGladiator
# (astral_sk / boss_shadowking REQUIREDHERO) straight from its npcstat; XMen2.exe seats herostat names only (a party
# name resolves through the herostat table; an unknown one reaches the fallback CStats, engine.md 2.1). Each takes the
# LAST pad slot (ProfXGladiator: stats index 21), so every other stats index, talent base and save record stays
# where it was (saves are positional, R25). Not in --hero-roster 21xml2 (its four XML2 pads fill the 21 slots).
ROSTER_NPC = ('ProfXGladiator',)
# their inline talents carry ProfXAstral's names (profx_*); a talent name must be defined by one file only (shared +
# hero files, V-H3), so the promoted hero's talents get their own prefix (the style's requires are added with them)
NPC_TALENT_RENAME = {'profxgladiator': ('profx_', 'pxg_')}
# NPC-only stats attributes (XML2 retail: npcstat only, never herostat): not copied into a herostat entry
NPC_ONLY_ATTRS = ('npchealthscale',)
# the talent-icon atlas textures/ui/<atlas>_all a hero's packages load (the gladiator's XML1 bundle and talents use
# ProfXAstral's; there is no profxgladiator_all on the disc)
ICON_ATLAS = {'profxgladiator': 'profxastral'}
# XML1 top power move -> XML1 power index (the talent whose power= gates it; TOP_NAMES gives the XML2 FightMove)
TOP_POWER_INDEX = {'power_attack': '0', 'power_smash': '1', 'power_boost': '2', 'power_xtreme': '3'}
XML2_PADS = ('Deadpool', 'Ironman', 'Professorx', 'Sunfire')     # --hero-roster 21xml2 (A/B only)
ROSTER_MODES = ('21', '17', '21xml2')
HERO_COUNT = 21              # 0x44bb13 cmp esi,0x15; roster list 0x5db5fd; persistence records for index < 22
TALENT_POOL = 100            # 0x4bdfe4 / 0x4be7e4 / 0x4be044 cmp ecx,0x64 (registered talents at once)
SHARED_CAP = 99              # 0x4c05d0 push 0x63: shared ids 0..98
FILE_CAP = 100               # per-hero file ids (idx+1)*100 .. +99 (0x4bdc00)
FILE_TALENT_MAX = 8          # DESIGN 4.2: <= 8 talents per hero file
STATS_TALENT_MAX = 19        # a CStats holds <= 19 <talent> children (FUN_0043bb80, == 0x13)
STATS_CAP = 296              # 0x44c1a7 cmp eax,0x129
NAME_MAX_ROSTER = 18         # < 19 chars to appear in the roster screen (0x5db590 < 0x13)
# talentvalue names: the registrar (talent-value manager vt+0x1c = 0x4c1860) refuses a name of 20+ chars
# (0x4c188c `cmp eax,0x14; jae` -> id 0), and '%name' attribute references (vt+0x18 = 0x4c1580) and the talent
# apply (0x4bf77b -> vt+0x24 = 0x4c16b0) look names up truncated to 19 chars; an unknown reference parses as a
# literal 0. XML2 retail: 1075 names, max 19. The manager holds 300 names (0x4c18d9 cmp 0x12c).
TALENTVALUE_NAME_MAX = 19
TALENTVALUE_NAMES_CAP = 300
TALENTVALUE_CODES = {'beast': 'xbe', 'colossus': 'xco', 'cyclops': 'xcy', 'frost': 'xfr', 'gambit': 'xga',
                     'iceman': 'xic', 'jubilee': 'xju', 'magma': 'xmg', 'nightcrawler': 'xnc', 'phoenix': 'xph',
                     'profxastral': 'xpx', 'psylocke': 'xps', 'rogue': 'xro', 'storm': 'xst', 'wolverine': 'xwo',
                     'profxgladiator': 'xpg'}
DANGER_ROOM_MARGIN = 8       # one danger-room talent file kept free of the pool
POWER_SLOT = {'0': 'power1', '1': 'power2', '2': 'power3', '3': 'power9'}    # XML1 power index -> FightMove
POWER_TYPE = {'2': 'boost', '3': 'xtreme'}                                   # table 0x6d9910
TOP_NAMES = {'power_attack': 'power1', 'power_smash': 'power2', 'power_boost': 'power3', 'power_xtreme': 'power9'}
HEROSTAT_POWERS = {'power1': 'power1', 'power2': 'power2', 'power3': 'power3', 'power4': 'power9'}
# D13: XML1 RatingMelee/Ranged/Support/Durability (ignored by XMen2.exe) -> XML2 autospend class
# XML1 rates hero stats on a ~2..7 scale, XML2 on ~8..28 (the 9 heroes both games ship: XML1 body 3-5 vs XML2
# 12-20, mind 3-7 vs 8-28, strength 2-7 vs 8-24, speed 2-7 vs 16-20). XMen2.exe derives health, energy and damage
# from these on its own scale, so unscaled XML1 heroes had a fraction of the health XML2's formulas expect and died
# within seconds in nyc1_1_1 (Owen, 2026-09-27: "man they were difficult on normal"; in-game: XML1 Cyclops killed
# ~12 s after the zone loaded while standing still). Body/mind/strength x4 keeps XML1's relative balance between
# heroes; speed maps into XML2's narrow band (animation and movement speed).
STAT_SCALE = 4
STAT_X1_MAX = 10                 # XML1 hero stats above this are not on the 1..10 scale (ProfXAstral) and stay
SPEED_MAP = (10, 2, 14, 22)      # speed = clamp(10 + 2 * x1, 14, 22): 2 -> 14, 5 -> 20, 7 -> 22


def rescale_x1_hero_stats(attrs):
    """{stat: new value} for the XML1 hero stat attributes present in attrs (strings in, strings out)."""
    out = {}
    for k in ('body', 'mind', 'strength'):
        try:
            v = float(attrs[k])
        except (KeyError, ValueError):
            continue
        if v > STAT_X1_MAX:
            continue       # already beyond XML1's hero scale (ProfXAstral: a level-40 form with 40/80/35): kept
        out[k] = str(int(round(v * STAT_SCALE)))
    try:
        s = float(attrs['speed'])
        if s > STAT_X1_MAX:
            return out
        base, mul, lo, hi = SPEED_MAP
        out['speed'] = str(int(min(hi, max(lo, round(base + mul * s)))))
    except (KeyError, ValueError):
        pass
    return out


AUTOSPEND = {'wolverine': 'bruiser', 'rogue': 'bruiser', 'colossus': 'bruiser',
             'beast': 'bruiser_light', 'nightcrawler': 'bruiser_light', 'psylocke': 'bruiser_light',
             'frost': 'support', 'phoenix': 'support', 'storm': 'support', 'profxastral': 'support',
             'profxgladiator': 'support',
             'cyclops': 'support_heavy', 'gambit': 'support_heavy', 'iceman': 'support_heavy',
             'jubilee': 'support_heavy', 'magma': 'support_heavy'}
# D14: XML2's portrait cells for the same characters; 63 = the engine's own "locked / no portrait" cell (0x5b3bb0)
TEXTUREICON = {'cyclops': '0', 'phoenix': '1', 'wolverine': '2', 'storm': '3', 'nightcrawler': '4', 'rogue': '5',
               'iceman': '6', 'colossus': '7', 'profxastral': '9', 'gambit': '11', 'profxgladiator': '9'}
TEXTUREICON_NONE = '63'
HERO_ONLY_PASSIVES = ('accuracy', 'pointblank', 'grappling', 'healing_factor', 'knockback')   # -> per-hero files
SHARED_REAL_DEFS = ('toughness', 'mutantmastery', 'acrobatics',
                    'critical', 'might', 'leadership', 'flight')       # XML1 definitions replace the XML2 ones
SPECIAL_TALENT_NAMES = ('flight', 'ice_skating', 'night_faith')          # cached by name, 0x4be130 (E13)
# Engine-form bodies for the four converted passives whose effects XML1's xbe hardcoded (no <activepowerup> in
# XML1 data) or that the engine reads as a keyed talentvalue (audit xml1_combat_gaps_2026-10-01.md G6; the
# affecter ids are combat_events.AFFECTERS, verified against XMen2.exe's table):
#  critical: XML1 +2/4/6/8/10 % melee critical chance -> the `critical` affecter (id 70), the same affecter
#    XML2's own critical definition uses, as fractions per rank;
#  might: XML1 lifting Heavy -> Massive -> Gigantic -> might_heaviness 1/2/3 (id 37) with might_structure 1
#    (id 38), the affecter pair XML2's own might carries and DESIGN 4.6's might_mode mapping produces. XML1's
#    +5/10/15 % melee damage and +3/6/8 Destruction have no faithful engine expression (the `damage` affecter
#    has no melee-only scope, and the `damagelevel` affecter's passive use is unverified), so they are declared
#    losses - the rank descriptions keep XML1's text;
#  flight: XML1 40/30/20/10/5 energy per second -> the flight_pwr talentvalue, which is how XML2's own flight
#    expresses the drain and which the exe reads by name (flight pickup stays the engine's own rank-3 behaviour).
SHARED_REAL_POWERUPS = {
    'critical': [[('critical', '0.02')], [('critical', '0.04')], [('critical', '0.06')],
                 [('critical', '0.08')], [('critical', '0.10')]],
    'might': [[('might_heaviness', '1'), ('might_structure', '1')],
              [('might_heaviness', '2'), ('might_structure', '1')],
              [('might_heaviness', '3'), ('might_structure', '1')]],
}
SHARED_REAL_TALENTVALUES = {
    'flight': {'flight_pwr': {1: '40', 2: '30', 3: '20', 4: '10', 5: '5'}},
}
DROP_STATS_ATTRS = ('ratingmelee', 'ratingranged', 'ratingsupport', 'ratingdurability')
COSTUME_RENAME = {'skin_magmacivilian': 'skin_civilian'}                  # D6: slot 8 is free for Magma
COSTUMES_X2 = ('astonishing', 'aoa', '60s', '70s', 'weaponx', 'future', 'winter', 'civilian')  # table 0x6d8aa0
GENERIC_ICONS = 'textures/ui/talent_icons.png'          # XML2's generic talent sheet (--hero-icons generic)
GENERIC_PASSIVE_ICON = '4'
GENERIC_POWER_ICON = {'power1': '0', 'power2': '1', 'power3': '2', 'power9': '3'}
HEAVY_PARTY = ('iceman', 'nightcrawler', 'magma', 'gambit')            # DESIGN 6.3: 4 + 4 + 3 + 2 actor slots
OPENING_PARTY = ('wolverine', 'cyclops', 'storm', 'rogue')
NEW_GAME_NAMES = ('magneto', 'cyclops', 'wolverine', 'storm')          # startFirstMission (0x4a7b41..0x4a7bfe)
HEADS_FALLBACK = 'ui/models/characters/9999'
HEADS_SCREEN = 'ui/models/m_team_roster_screen'
HEADS_PKG = 'Packages/generated/maps/package/menus/characters_heads.PKGB'
HEADS_PC_PKG = 'Packages/generated/maps/package/menus/characters_heads_pc.PKGB'
# attributes XML2 retail styles / talent files reference through %talentvalue (every XML2 style and talent file
# scanned): a % reference anywhere else falls back to the top rung's literal (DESIGN 4.4 rule 5)
VALUE_REF_ATTRS = frozenset({
    ('affecter', 'level'), ('event', 'damage'), ('event', 'knockback'), ('event', 'life'), ('event', 'maxrange'),
    ('event', 'powerusage'), ('fightmove', 'energypersecond'), ('fightmove', 'playspeed'), ('level', 'description'),
    ('powerup', 'chance'), ('powerup', 'damagepercent'), ('powerup', 'life'), ('require', 'level'),
    ('trigger', 'apply_chance'), ('trigger', 'chance'), ('trigger', 'count'), ('trigger', 'damage'),
    ('trigger', 'damageamount'), ('trigger', 'damagepercent'), ('trigger', 'explodedamage'),
    ('trigger', 'explosion_damage'), ('trigger', 'explosion_knockback'), ('trigger', 'health'),
    ('trigger', 'healthpct'), ('trigger', 'heaviness'), ('trigger', 'impactdamage'), ('trigger', 'knockback'),
    ('trigger', 'life'), ('trigger', 'maxhealthpercent'), ('trigger', 'maxinstances'), ('trigger', 'maxrange'),
    ('trigger', 'numblasts'), ('trigger', 'numbounces'), ('trigger', 'numtargets'), ('trigger', 'piercechance'),
    ('trigger', 'powerusage'), ('trigger', 'targethealthpct'), ('trigger', 'value')})
# affecter attribute names XML2 retail data uses (inventory.json xml2_contract + every XML2 style / talent file)
AFFECTER_VOCAB = frozenset({
    'all_talents', 'atk_attack_rating', 'atk_critical', 'atk_damage', 'atk_vampire', 'atk_vampire_energy',
    'attack_rating', 'body', 'combo_damage', 'combo_xp', 'confused', 'critical', 'damage', 'def_absorb_damage',
    'def_damage', 'def_damage_scope',
    'def_dodge', 'def_finisher', 'def_grab', 'def_knockback', 'def_mind_control', 'def_pain', 'def_pickup',
    'def_reflect_pain', 'def_stun', 'defense_rating', 'deflect_damage', 'energy_regen', 'extra_money',
    'extra_potions', 'fear', 'frozen', 'health_regen', 'health_regen_pct', 'invisible', 'jump', 'maxenergy',
    'maxhealth', 'might_heaviness', 'might_structure', 'mind', 'move', 'move_attack', 'no_iceshell', 'nullify',
    'power_cost', 'powerup_scope', 'reflect_damage', 'resist_cold', 'resist_elemental', 'resist_energy',
    'resist_fire', 'resist_mental', 'resist_physical', 'resist_radiation', 'reveal_hidden', 'scale_factor',
    'slow_immune', 'special', 'speed', 'spend_damage', 'stolen_damage', 'strength', 'talent', 'team_switch',
    'traits', 'xp'})
# XML1 powerup names in XMen2.exe's affecter table (combat_events.AFFECTERS, 0x6ddb18) that no XML2 retail style
# uses (DESIGN 4.5/4.6: kept, warned). atk_damage_scale is NOT in the table: combat_events.AFFECTER_RENAME makes it
# XML2's scale-type atk_damage before the collapse (SPEC 22).
AFFECTER_UNVERIFIED = frozenset({'damagelevel', 'atk_knockback', 'drain_victim', 'stun_lock'})
# affecter scopes besides scope_damage / scope_attack that XMen2.exe's affecter parser reads (0x535150..0x5351aa); an
# XML1 powerup trigger's scope_node / scope_race (ps_havok, ps_sentinel_leader) move onto its affecter
AFFECTER_EXTRA_SCOPES = ('scope_node', 'scope_talent', 'scope_race', 'scope_character', 'scope_powers',
                         'scope_non_powers')
# <special_fx how_used>: XMen2.exe knows primary / activation / deactivation / custom (table 0x6de16c, parser
# 0x53c1f0); any other word parses as custom (3), so 'deactivate' never played at the end of the powerup
FX_DEACTIVATION = 'deactivation'
# XML1 script-callback attributes (absent from XMen2.exe as strings): dropped from converted triggers/powerups
FUNC_ATTR = re.compile(r'^func_')
DROP_TRIGGER_ATTRS = ('fallback', 'life_max', 'level_max')
# XML1 combat handlers XMen2.exe never registers (research/characters/combat_compat.json; 0x4fd975-0x4fe88a)
UNREGISTERED_HANDLERS_DEFAULT = ('ch_weapon_semi_auto', 'ch_grenade', 'ch_throw', 'ch_grab_attack', 'ch_roguedecide',
                                 'ch_air_grab_pickup', 'ch_air_grab_idle', 'ch_air_grab_throw', 'ch_clingwall',
                                 'ch_clingwall_idle', 'ch_clingwall_jump', 'ch_clingwall_land', 'ch_fly_guard_decide',
                                 'ch_stun')
# 4.4 short names of overridden attributes in talentvalue names
SHORT = {'damage': 'dmg', 'powerusage': 'pwr', 'knockback': 'kb', 'damagelevel': 'dlv', 'fxlevel': 'fxl',
         'radius': 'rad', 'life': 'lif', 'level': 'lvl', 'maxrange': 'rng', 'count': 'cnt', 'pierce': 'pierce',
         'explosion_damage': 'xdmg', 'explosion_knockback': 'xkb', 'chance': 'chn'}
_CODE_RE = re.compile(r'^(L\d\+?-?|M\d\+?|H\d\+?|K\d+\+?|P\d+\+?|BST\d|A\d+|XTL\d|XLT\d)$')
_REF_RE = re.compile(r'%([A-Za-z0-9_]+)')            # %talentvalue references (also inside level descriptions)
_NUM_RE = re.compile(r'^-?\d+(\.\d+)?$')
_RANGE_RE = re.compile(r'^-?\d+(\.\d+)?\s+-?\d+(\.\d+)?$')
_SKIN4 = re.compile(r'^\d{4}$')
_BUNDLE = re.compile(r'packages/generated/characters/(.+)_(\d{4})(_nc)?\.fb')
FORCE_PREFIXES = ('conversations/', 'dialogs/', 'subtitles/', 'data/entities/', 'motionpaths/')   # SPEC 4.4
PATCH_DATA = 'heroes.data'


def roster_mode(ctx) -> str:
    m = str(ctx.opt('hero_roster') or os.environ.get('XML1BUILD_HERO_ROSTER') or '21').lower()
    return m if m in ROSTER_MODES else '21'


def icons_mode(ctx) -> str:
    m = str(ctx.opt('hero_icons') or os.environ.get('XML1BUILD_HERO_ICONS') or 'xml1').lower()
    return m if m in ('xml1', 'generic') else 'xml1'


def bleed_mode(ctx) -> str:
    m = str(ctx.opt('hero_bleed') or os.environ.get('XML1BUILD_HERO_BLEED') or 'on').lower()
    return m if m in ('on', 'off') else 'on'


def _lower_attrs(el):
    return {k.lower(): v for k, v in el.attrib.items()}


def _stats_list(root):
    return [s for s in root.iter() if s.tag.lower() == 'stats' and s.get('name')]


def _talent_children(el):
    return [c for c in el if c.tag.lower() == 'talent']


def is_inline_talent(t):
    """an XML1 <Talent> that defines the talent (levels / power index / descname) rather than referencing it."""
    a = _lower_attrs(t)
    return len(t) > 0 or 'power' in a or 'descname' in a


def talentvalue_code(hero):
    """the per-hero prefix of talentvalue names: 'x' + two letters, distinct per XML1 hero and from every XML2
    retail prefix (XML2 names start cyc_/wolv_/mag_/...; none starts with x + 2 letters + '_')."""
    h = hero.lower()
    return TALENTVALUE_CODES.get(h) or f'x{h[:2]}'


def talentvalue_name(hero, talent, short, used):
    """<code>_<talent>_<short> (e.g. xcy_beam_dmg, xwo_frenzy_dmg_t1), <= TALENTVALUE_NAME_MAX = 19 chars, unique
    within `used` (a set, updated). The talent part drops a leading token the hero name starts with
    (cyclops_beam -> beam, wolv_frenzy -> frenzy, night_shadow -> shadow, ice_skating -> skating) and is truncated;
    a clash gets a digit. The engine refuses longer names (research/heroes/powers_debug.md, 0x4c188c)."""
    hero, talent, short = hero.lower(), talent.lower(), short.lower()
    code = talentvalue_code(hero)
    head, sep, rest = talent.partition('_')
    if sep and rest and len(head) >= 3 and hero.startswith(head):
        talent = rest
    short = short[:TALENTVALUE_NAME_MAX - len(code) - 2 - 2]        # keep >= 2 chars for the talent part
    room = TALENTVALUE_NAME_MAX - len(code) - 2 - len(short)
    name = f'{code}_{talent[:room]}_{short}'
    i = 2
    while name in used:
        suf = str(i)
        name = f'{code}_{talent[:max(1, room - len(suf))]}{suf}_{short}'
        i += 1
    assert len(name) <= TALENTVALUE_NAME_MAX, name
    used.add(name)
    return name


# ------------------------------------------------------------------------------------------------ value codes
class Values:
    """xml1_loose/data/values.xml: code -> ('min', 'max'|None). resolve(v) turns a code into XML1's number(s);
    typos XLT2..6 (Frost, Nightcrawler, Rogue, Storm) resolve to the XTL value (DESIGN 4.5)."""

    def __init__(self, root):
        self.table = {}
        for v in root.iter():
            if v.tag.lower() == 'value' and v.get('name'):
                self.table[v.get('name')] = (v.get('min'), v.get('max'))
        for k in list(self.table):
            if k.startswith('XTL'):
                self.table.setdefault('XLT' + k[3:], self.table[k])

    def is_code(self, v):
        return isinstance(v, str) and (v in self.table or bool(_CODE_RE.match(v)))

    def resolve(self, v, single=False):
        """code -> 'min' or 'min max' (single=True: one number, the mean of a range). Non-codes unchanged.
        Raises KeyError for an unknown code."""
        if not isinstance(v, str) or v not in self.table:
            if isinstance(v, str) and _CODE_RE.match(v):
                raise KeyError(f'unknown value code {v!r}')
            return v
        lo, hi = self.table[v]
        if hi is None or hi == lo:
            return lo
        if single:
            m = (float(lo) + float(hi)) / 2
            return str(int(m)) if m == int(m) else f'{m:g}'
        return f'{lo} {hi}'

    def level_of(self, code):
        """XTL2..6 (character level) -> int; None otherwise."""
        m = re.match(r'^X[TL][LT](\d)$', code or '')
        if m and code in self.table:
            return int(self.table[code][0])
        return None

    def resolve_text(self, text):
        """XML1 description: ^CODE -> its number(s), ^word -> word, ^ removed; a bare % is escaped as %% (the XML2
        formatter FUN_004c0e40 substitutes %name tokens only, E19; XML2's own team_bonus uses %%)."""
        if not text:
            return text

        def sub(m):
            tok = m.group(1)
            if tok in self.table:
                return self.resolve(tok).replace(' ', '-')          # ^L2 -> 9-11
            return tok
        out = re.sub(r'\^([A-Za-z0-9+.\-]+)', sub, text)
        out = out.replace('^', '')
        out = re.sub(r'%(?!%)', '%%', out)
        return out


def _numeric(v):
    return isinstance(v, str) and (bool(_NUM_RE.match(v.strip())) or bool(_RANGE_RE.match(v.strip())))


# ------------------------------------------------------------------------------------------------ provider
_PLAN_LOCK = threading.Lock()


_BADREF = re.compile(r'^BADREF:@[A-Za-z_]*@(?P<key>[A-Za-z0-9_]+)$')


def badref_text(text):
    """XML1's unresolved string reference 'BADREF:@DATA@H1_DAMAGE_K6_KNOCKBACK' (npcstat talents: the key names the
    text) -> '^H1 damage ^K6 knockback' (value codes keep their ^ for Values.resolve_text, which reads a code up
    to the next space - so no closing period); other text unchanged."""
    m = _BADREF.match((text or '').strip())
    if not m:
        return text
    words = ['^' + t if _CODE_RE.match(t) else t.lower() for t in m.group('key').split('_') if t]
    out = ' '.join(words)
    return out[:1].upper() + out[1:]


def promote_npc_stats(st, name=None):
    """an XML1 npcstat hero entry (ROSTER_NPC) as the builder reads a herostat one: a deep copy named `name` (the
    ROSTER_NPC spelling; XML1's npcstat writes it lowercase) whose inline talents carry the hero's own names
    (NPC_TALENT_RENAME) and whose BADREF: descriptions read as text (badref_text)."""
    e = copy.deepcopy(st)
    if name:
        e.set(next((k for k in e.attrib if k.lower() == 'name'), 'name'), name)
    old, new = NPC_TALENT_RENAME.get((e.get('name') or '').lower(), ('', ''))
    for t in _talent_children(e):
        if not is_inline_talent(t):
            continue
        k = next((k for k in t.attrib if k.lower() == 'name'), None)
        if old and k and t.attrib[k].lower().startswith(old):
            t.attrib[k] = new + t.attrib[k][len(old):]
        for el in t.iter():
            for a, v in list(el.attrib.items()):
                if a.lower() == 'description':
                    el.attrib[a] = badref_text(v)
    # A fixed-level form (the gladiator is level 40 in XML1's npcstat) keeps its level the way ProfXAstral's
    # herostat entry does in XML1's own data (xpexempt="true"): an NPC entry never needed the flag.
    try:
        fixed_level = int(e.get(next((k for k in e.attrib if k.lower() == 'level'), 'level'), '1') or 1) > 1
    except ValueError:
        fixed_level = False
    if fixed_level and not any(k.lower() == 'xpexempt' for k in e.attrib):
        e.set('xpexempt', 'true')
    return e


def gate_npc_style(root, talents):
    """XML1 npcstat heroes' styles (ps_profxgladiator) leave the power moves ungated (the NPC AI picks them), while a
    herostat hero's power slot needs its FightMove to require the talent (StyleCollapse's power root, V-H5). Each
    XML1 top move (power_attack/smash/boost/xtreme) without a skill / talent require gets <require cat="talent"
    item=<the talent with that XML1 power index> level="1"/> first: the form of ProfXAstral's own style. talents:
    {lname: {'power', 'levels'}} (HeroBuilder._talents_info). In place; returns [(move, talent)]."""
    by_power = {i.get('power'): t for t, i in talents.items() if i.get('power') in POWER_SLOT}
    added = []
    for m in root:
        if m.tag != 'FightMove':
            continue
        idx = TOP_POWER_INDEX.get((m.get('name') or '').lower())
        if idx is None or idx not in by_power:
            continue
        if any(r.tag.lower() == 'require' and (_lower_attrs(r).get('cat') or '').lower() in ('skill', 'talent')
               for r in m):
            continue
        m.insert(0, ET.Element('require', {'cat': 'talent', 'item': by_power[idx], 'level': '1'}))
        added.append((m.get('name'), by_power[idx]))
    return added


def hero_plan(ctx) -> dict:
    """Pure (reads only; cached in ctx.shared['heroes_plan']): the roster plan.
    {'mode', 'order': [21 names], 'index': {lname: statsIdx}, 'talent_base': {lname: (idx+1)*100},
     'heroes': [the playable names: ROSTER_X1 + the promoted npcstat heroes], 'npc_heroes': [ROSTER_NPC in this
     mode], 'x1': {lname: XML1 <stats> Element (npc heroes: promote_npc_stats)}, 'costumes': {lname: [(attr, xml1
     skin4, mapped skin)]}, 'style': {lname: mapped powerstyle name}, 'placeholders': [names], 'xml2_pads': [names]}"""
    with _PLAN_LOCK:
        p = ctx.shared.get('heroes_plan')
        if p is not None:
            return p
        mode = roster_mode(ctx)
        x1 = {s.get('name').lower(): s for s in _stats_list(ctx.read_x1_xml('data/herostat.eng'))}
        missing = [h for h in ROSTER_X1 if h.lower() not in x1]
        if missing:
            raise KeyError(f'XML1 herostat.eng lacks {missing}')
        npc_heroes = [] if mode == '21xml2' else list(ROSTER_NPC)
        if npc_heroes:
            npc = {s.get('name').lower(): s for s in _stats_list(ctx.read_x1_xml('data/npcstat.eng'))}
            missing = [h for h in npc_heroes if h.lower() not in npc]
            if missing:
                raise KeyError(f'XML1 npcstat.eng lacks {missing}')
            for h in npc_heroes:
                x1[h.lower()] = promote_npc_stats(npc[h.lower()], h)
        heroes = list(ROSTER_X1) + npc_heroes
        order = ['default'] + list(ROSTER_X1) + [PLACEHOLDER]
        placeholders = [PLACEHOLDER]
        xml2_pads = []
        if mode == '21':
            pads = list(PADS[:len(PADS) - len(npc_heroes)])      # the promoted heroes take the last pad slots
            order += pads
            placeholders += pads
        elif mode == '21xml2':
            order += list(XML2_PADS)
            xml2_pads = list(XML2_PADS)
        order += npc_heroes
        index = {n.lower(): i + 1 for i, n in enumerate(order)}
        costumes, style = {}, {}
        for h in heroes:
            st = x1[h.lower()]
            a = _lower_attrs(st)
            skin = a['skin']
            cs = [('skin', skin, C.map_skin(skin))]
            for k, v in sorted(a.items()):
                if k.startswith('skin_') and re.fullmatch(r'\d{1,2}', v.strip()):
                    k2 = COSTUME_RENAME.get(k, k)
                    s4 = skin[:-2] + v.strip().zfill(2)
                    cs.append((k2, s4, C.map_skin(s4)))
            costumes[h.lower()] = cs
            style[h.lower()] = C.map_powerstyle(a['powerstyle'].lower())
        p = {'mode': mode, 'order': order, 'index': index,
             'talent_base': {n.lower(): (index[n.lower()] + 1) * 100 for n in order},
             'heroes': heroes, 'npc_heroes': npc_heroes,
             'x1': {h.lower(): x1[h.lower()] for h in heroes}, 'costumes': costumes, 'style': style,
             'placeholders': placeholders, 'xml2_pads': xml2_pads}
        ctx.shared['heroes_plan'] = p
        return p


# ------------------------------------------------------------------------------------------------ trigger fixups
# attribute names whose values are never value codes (kept out of the code resolver)
_NAME_LIKE_ATTRS = frozenset({'name', 'tag', 'item', 'result', 'action', 'nodename', 'inherit', 'fallback', 'animenum',
                              'skinsegment', 'bolt', 'boltslot', 'effect', 'effect_cust1', 'effect_cust2', 'sound',
                              'model', 'handler', 'filename', 'entity', 'powerup_tag', 'combotextstarter',
                              'combotextfinisher', 'description', 'attachpoint', 'class', 'shared_tag', 'powerup',
                              'beameffect', 'hiteffect', 'hitenemyeffect', 'spawneffect', 'dasheffect', 'beambolt',
                              'skin', 'bolton', 'cat', 'attacktype', 'damagetype', 'how_used', 'attribute',
                              'scope_damage', 'scope_attack', 'scope_node', 'apply_ally', 'apply_enemy'})


def resolve_codes(el, values, where, problems):
    """Resolve every value code in the attributes of `el` and its descendants (trigger/event/require/FightMove
    attributes; 'min max' for damage-like ranges). Unknown codes are reported and left in place."""
    for e in el.iter():
        for k, v in list(e.attrib.items()):
            if k in _NAME_LIKE_ATTRS or not values.is_code(v):
                continue
            try:
                single = e.tag == 'affecter' or k in ('level', 'chance', 'radius', 'life')
                e.set(k, values.resolve(v, single=single and k != 'level'))
            except KeyError:
                problems.append(f'{where}: <{e.tag} {k}="{v}"> unknown value code')


def _special_fx(effect, how_used, bolt=None, extra=None):
    a = {'effect': effect, 'how_used': how_used}
    if bolt:
        a['bolt'] = bolt
    if extra:
        a.update(extra)
    return ET.Element('special_fx', a)


def _affecter(attribute, level=None, affect_type=None, scope_damage=None, scope_attack=None, scope_node=None,
              **scopes):
    """scopes: further affecter scopes XMen2.exe's affecter parser reads (0x535124..0x5351bc: scope_talent,
    scope_race, scope_character, scope_powers, scope_non_powers), given as keyword arguments."""
    a = {'attribute': attribute}
    if level is not None:
        a['level'] = level
    if affect_type:
        a['affect_type'] = affect_type
    if scope_damage:
        a['scope_damage'] = scope_damage
    if scope_attack:
        a['scope_attack'] = scope_attack
    if scope_node:
        a['scope_node'] = scope_node
    for k, v in scopes.items():
        if v:
            a[k] = v
    return ET.Element('affecter', a)


def _scope_affecter(scopes):
    """<affecter attribute="powerup_scope"><scope scope_attack=.../>...</affecter> (XML2 form for several scopes)."""
    aff = ET.Element('affecter', {'attribute': 'powerup_scope'})
    for k, v in scopes:
        ET.SubElement(aff, 'scope', {k: v})
    return aff


def _powerup_fx(a, funcs):
    """pop an XML1 powerup trigger's effect / effect_cust1 / effect_cust2 from the attribute dict `a` and return the
    <special_fx> children XMen2.exe gives those attributes itself (base powerup setter 0x53ea60): effect = the
    primary fx, its bolt = bolt or fx_bolt (one field, 0x53f1a0); effect_cust1 = custom fx tag 1 (0x53f212) or, with
    XML1's customeffect1deactivate callback, the deactivation fx; effect_cust2 = custom fx tag 2 (0x53f243)."""
    effect = a.pop('effect', None)
    cust1 = a.pop('effect_cust1', None)
    cust2 = a.pop('effect_cust2', None)
    kids = []
    if effect:
        kids.append(_special_fx(effect, 'primary', a.get('bolt') or a.get('fx_bolt')))
    if cust1:
        if funcs.get('func_deactivate', '').lower() == 'customeffect1deactivate':
            kids.append(_special_fx(cust1, FX_DEACTIVATION))
        else:
            kids.append(_special_fx(cust1, 'custom', None, {'tag': '1'}))
    if cust2:
        kids.append(_special_fx(cust2, 'custom', None, {'tag': '2'}))
    return kids


def convert_powerup_trigger(t, where, report):
    """XML1 <trigger name="powerup" powerup="X" level= affect_type= scope_* func_* effect= ...> -> XML2's
    <trigger name="powerup" ...><special_fx/><affecter/></trigger> (DESIGN 4.5; retail forms where XML2 has one:
    rogue_drained / shared_stunned / shared_bleed / chill / freeze / time_bomb / charged / add_attack).
    Attribute values may already be %talentvalue references; they travel with the attribute. In place."""
    if (t.get('name') or '').lower() != 'powerup':
        return
    a = dict(t.attrib)
    funcs = {k: v for k, v in a.items() if FUNC_ATTR.match(k)}
    for k in list(a):
        if FUNC_ATTR.match(k) or k in DROP_TRIGGER_ATTRS:
            del a[k]
    level_max = t.get('level_max')
    pu = a.pop('powerup', None)
    if pu is None:                       # e.g. Iceman's ice-blade bolton trigger: kept verbatim minus func_*
        t.attrib.clear()
        t.attrib.update(a)
        return
    pul = pu.lower()
    level = a.pop('level', None)
    affect = a.pop('affect_type', None)
    scope_damage = a.pop('scope_damage', None)
    scope_attack = a.pop('scope_attack', None)
    scopes = {k: a.pop(k) for k in AFFECTER_EXTRA_SCOPES if a.get(k)}
    user1 = a.pop('user1', None)
    a.pop('user2', None)
    effect, cust1 = a.get('effect'), a.get('effect_cust1')
    kids = _powerup_fx(a, funcs)
    damagetype = a.get('damagetype')
    lost = []
    if pul == 'special' or (pul == 'damage' and funcs.get('func_damage', '').lower() == 'damageaddattack'):
        if damagetype and not (funcs.get('func_deactivate', '').lower() == 'timebomb_deactivate'):
            a['class'] = 'add_attack'
            a['damagepercent'] = '0.5'
            if scope_attack:
                kids.append(_scope_affecter([('scope_attack', scope_attack)]))
            if level is not None:
                lost.append(f'level={level} (XML2 add_attack is percentage based)')
        elif funcs.get('func_deactivate', '').lower() == 'timebomb_deactivate' or 'timebomb' in ''.join(funcs.values()).lower():
            a['class'] = 'time_bomb'
            if level is not None:
                a['explosion_damage'] = level
            if user1 is not None:
                a['explosion_knockback'] = user1
                user1 = None
            a['explosion_radius'] = level_max if level_max and _numeric(level_max) else '144'
            a.pop('damagetype', None)
            kids = []
            if effect:
                kids.append(_special_fx(effect, 'primary', None, {'center_bolt': 'true'}))
            if cust1:
                kids.append(_special_fx(cust1, 'custom', None, {'tag': '1'}))
        elif a.get('apply_held') or 'charged' in ''.join(funcs.values()).lower():
            a['class'] = 'charged'
            if level is not None:
                a['explosion_damage'] = level
            a['life'] = '99'                 # XML2 charged_throw form (life 0 would expire on the same frame)
        else:
            report.setdefault('warnings', []).append(f'{where}: powerup="special" without damagetype kept verbatim')
            if level is not None:
                a['level'] = level
    elif pul == 'might_mode':
        kids.append(_affecter('might_heaviness', level or '1'))
        kids.append(_affecter('might_structure', level or '1'))
    elif pul == 'drain_victim':
        a['class'] = 'rogue_drained'
        user1 = None
    elif pul == 'stun_lock':
        a['shared_tag'] = 'shared_stunned'
        a.pop('no_stack', None)
    elif pul == 'none':
        if 'bleed' in ''.join(funcs.values()).lower():
            a['shared_tag'] = 'shared_bleed'
        else:
            report.setdefault('warnings', []).append(f'{where}: powerup="none" without a known callback kept as a plain powerup')
    elif pul == 'move' and 'frozen' in funcs.get('func_activate', '').lower():
        a['class'] = 'freeze'
        a['renderfx'] = 'chilled'
        a['user1'] = '2'
        kids.append(_affecter('frozen', '1'))
    elif pul == 'move' and 'chilled' in funcs.get('func_activate', '').lower():
        a['class'] = 'chill'
        kids.append(_affecter('move', level, affect or 'scale'))
    elif pul == 'invisible':
        kids.append(_affecter('invisible'))
    elif pul == 'def_damage' and damagetype:
        a.pop('damagetype', None)
        kids.append(_affecter('def_damage', level, affect, scope_damage or damagetype, scope_attack, **scopes))
    else:
        if pul not in AFFECTER_VOCAB:
            report.setdefault('unverified_affecters', []).append(f'{where}: {pu}')
        lvl = level if level is not None else ('1' if pul in ('confused', 'fear', 'nullify', 'team_switch') else None)
        kids.append(_affecter(pu, lvl, affect, scope_damage, scope_attack, **scopes))
    if user1 is not None:
        lost.append(f'user1={user1}')
    if lost:
        report.setdefault('losses', []).append(f'{where}: powerup {pu}: {"; ".join(lost)}')
    t.attrib.clear()
    t.attrib.update(a)
    for k in list(t):
        if k.tag in ('special_fx', 'affecter'):
            t.remove(k)
    for k in kids:
        t.append(k)


def fixup_move(m, values, where, report):
    """DESIGN 4.5 on one output FightMove (collapsed or kept): value codes resolved, powerup triggers rewritten,
    require cat talent -> skill, func_* / fallback / life_max / level_max dropped."""
    problems = []
    resolve_codes(m, values, where, problems)
    for p in problems:
        report.setdefault('errors', []).append(p)
    for r in m.iter('require'):
        if (r.get('cat') or '').lower() == 'talent':
            r.set('cat', 'skill')
    for t in m.iter('trigger'):
        if (t.get('name') or '').lower() == 'powerup':
            convert_powerup_trigger(t, f'{where} <trigger tag={t.get("tag")}>', report)
        else:
            for k in list(t.attrib):
                if FUNC_ATTR.match(k) or k in DROP_TRIGGER_ATTRS:
                    del t.attrib[k]
    for e in m.iter('event'):
        for k in list(e.attrib):
            if FUNC_ATTR.match(k):
                del e.attrib[k]
    for k in ('fallback',):
        m.attrib.pop(k, None)


# ------------------------------------------------------------------------------------------------ NPC powerups
# SPEC 22.7. XMen2.exe builds a powerup trigger's buff only from <affecter> children: the ce_powerup event (factory
# 0x4fb104, parse 0x4e7f00) hands the trigger to its powerup template, whose parser 0x53df10 (vt+0x40) passes every
# attribute to the class setter (base 0x53ea60 and 17 class overrides - none reads powerup / level / affect_type /
# scope_* / remove) and then reads the <affecter> (0x534d90), <special_fx> and <bolton> children. XML1's form
# (default.xbe 0x9565c: powerup="X" level= on the trigger) therefore builds an empty powerup on XMen2.exe: its effect,
# skin and life play, the buff does nothing. The heroes' triggers are converted by convert_powerup_trigger (DESIGN
# 4.5); convert_npc_powerups applies the same converter to the NPC styles characters writes, plus the NPC-only forms:
#  * remove="true" (default.xbe 0x95bd3, flag +0x72 bit 4): XML1's trigger REMOVES the actor's powerups of attribute
#    X instead of applying one (0xd7668 -> 0x2b100, every powerup whose attribute id matches). XMen2.exe has no such
#    flag; it removes by tag name: remove_tag (0x4e7e79) makes the trigger's execute (0x4e8387) drop the owner's
#    powerups whose tag_name (base setter 0x53ea6e) matches (0x54f7b0), XML2 retail's <trigger name="powerup"
#    remove_tag="invisible" time="0"/>. A tag-only update (<trigger tag="1" remove="true"/> in a move inheriting a
#    powerup trigger: Blob, Juggernaut, Magneto, Pyro) is XML1's removal too (the update re-parses the inherited
#    trigger, 0x4f6a1f -> vt+0xc).
#  * XML1's invisibility callbacks (invisible_activate ...): XML2's class="invisible" (vtable 0x697aec, setter 0x548340
#    no_think / no_hurt), exactly XML2's own spawn_invis talent form.
#  * damagetouch (Master Mold's shock shield): class="touch_damage" (vtable 0x698104, setter 0x54ae00 damage /
#    damageType), damage = XML1's rand(level, level_max) (0x2c970).
NPC_REMOVE_TAG = '{attr}'        # tag_name / remove_tag for XML1 attribute X ('invisible' = XML2's spawn_invis tag)
# value codes the NPC powerup conversion leaves as they are: none. XMen2.exe reads a style value code as 0 unless it
# is DMG2/3/4, K2 or K3 (0x4c1580 -> 0x4c4870, npc_values), and XML1 NPCs had an energy pool they spent and waited for
# (npc_values: XML1 0xcde90 / 0xe1a20 / 0xee37a), so powerusage resolves to XML1's P number like every other code;
# characters gives each converted NPC XML1's pool and regeneration (npc_values.ENERGY_TALENT, SPEC 24).
NPC_KEEP_CODE_ATTRS = ()
# XML1 powerup callbacks (func_*: default.xbe 0x2d9xx name -> C function) the XML2 form covers
NPC_CALLBACKS = {
    'invisible_activate': 'class="invisible" (XML2 retail cloaks: undercloak, sinisteragent, garokk, spawn_invis)',
    'invisideactivate': 'class="invisible" ends the cloak with the powerup',
    'invisideath': 'class="invisible" (the powerup ends with the actor)',
    'invisihurt': 'class="invisible" reacts to hurt (no no_hurt; 0x5486b0 tests it)',
    'customeffect1deactivate': 'effect_cust1 -> special_fx how_used="deactivation"',
    'frozenactivate': 'class="freeze" (convert_powerup_trigger)',
    'frozendeactivate': 'the frozen / move affecter ends with the powerup',
    'frozenhurt': 'class="freeze"', 'frozenthink': 'class="freeze"',
    'immobolizeactivate': 'move scale 0 affecter + the skin swap (XML1 held the victim in place, no ice)',
    'bleedactivate': 'shared_tag="shared_bleed" (convert_powerup_trigger)', 'bleedthink': 'shared_bleed',
    'damagetouch': 'class="touch_damage"',
}
# XML1 callbacks with no XML2 counterpart: the powerup keeps its affecters and effects, the callback's logic is lost
NPC_CALLBACK_LOSSES = {
    'magnetohurt': 'the shield-hit flash (effect_cust1 on hurt) becomes a custom fx tag 1, which only class logic plays',
    'mindfry_activate': "the mind-fry victim logic (Phoenix dopple); the strength affecter stays",
    'revcontrols_activate': 'reversed controls on the hit hero (Sentinel spider); the effect plays',
    'revcontrols_deactivate': 'reversed controls end',
    'atthitslashsound': 'a slash sound on each hit (Wolverine dopple rage)',
    'damagegrowlsound': 'a growl sound when hurt (Wolverine dopple rage)',
}
# XML1 powerup attributes default.xbe's own name table lacks (0x44e8c8, 59 names; 0x946f0 returns 0 = none): the
# buff did nothing in XML1 either, so no affecter is written (the powerup keeps its effect / life / bolt-on)
NPC_AFFECTER_NONE = {
    'fighting': "ps_marrow power_smash: 'fighting' is no default.xbe powerup name, XML1 parsed it as none",
}


def _first_number(v):
    m = re.match(r'\s*(-?\d+(?:\.\d+)?)', v or '')
    return m.group(1) if m else None


def is_x1_powerup_apply(el):
    """an XML1-form powerup trigger that applies a powerup: a powerup= attribute, no <affecter> child, no
    remove="true" (default.xbe reads powerup= at 0x9565c; XMen2.exe never does)."""
    return (el.tag.lower() in ('trigger', 'event') and el.get('powerup') is not None
            and (el.get('remove') or '').strip().lower() != 'true'
            and not any(isinstance(k.tag, str) and k.tag.lower() == 'affecter' for k in el))


def npc_removals(root):
    """[(move, trigger, XML1 attribute)] of every XML1 removal in one style: a powerup trigger with remove="true", or
    a tag-only update with remove="true" of an inherited XML1 powerup trigger (combat_events.inherited_trigger)."""
    moves = CE.style_moves(root)
    out = []
    for m in moves.values():
        for t in m:
            if not isinstance(t.tag, str) or t.tag.lower() != 'trigger' or \
                    (t.get('remove') or '').strip().lower() != 'true':
                continue
            name = (t.get('name') or '').lower()
            if name == 'powerup' and t.get('powerup'):
                out.append((m, t, t.get('powerup').lower()))
            elif not name and t.get('tag') is not None:
                p = CE.inherited_trigger(moves, m, t.get('tag'))
                if p is not None and (p.get('name') or '').lower() == 'powerup' and p.get('powerup'):
                    out.append((m, t, p.get('powerup').lower()))
    return out


def convert_npc_powerups(root, values, where=''):
    """SPEC 22.7: every XML1-form powerup trigger of one NPC style tree -> XML2's form, in place, table-driven and
    idempotent (a second call finds nothing). Value codes on the converted triggers are resolved to XML1's numbers
    (values: Values of XML1's data/values.xml), so the buff keeps XML1's balance (NPC_KEEP_CODE_ATTRS: none kept;
    npc_values.resolve_style resolves the rest of the style). Returns (Counter of change kinds,
    report {'losses', 'notes', 'warnings', 'errors', 'unverified_affecters'})."""
    c = collections.Counter()
    report = {'losses': [], 'notes': [], 'warnings': [], 'errors': [], 'unverified_affecters': []}
    if root is None:
        return c, report
    removals = npc_removals(root)
    removed = {attr for _m, _t, attr in removals}
    removal_ids = {id(t) for _m, t, _a in removals}
    moves = CE.style_moves(root)
    owner = {id(t): m for m in moves.values() for t in m.iter()}
    tagged = set()
    for t in [e for e in root.iter() if isinstance(e.tag, str) and id(e) not in removal_ids and is_x1_powerup_apply(e)]:
        m = owner.get(id(t))
        w = f'{where}{(m.get("name") if m is not None else "<style>")} <trigger tag={t.get("tag")}>'
        problems = []
        kept = {k: t.attrib.pop(k) for k in list(t.attrib) if k.lower() in NPC_KEEP_CODE_ATTRS}
        resolve_codes(t, values, w, problems)
        t.attrib.update(kept)
        report['errors'] += problems
        funcs = {k: (v or '').lower() for k, v in t.attrib.items() if FUNC_ATTR.match(k)}
        pu = t.get('powerup').lower()
        for f in sorted(set(funcs.values())):
            if f in NPC_CALLBACK_LOSSES:
                report['losses'].append(f'{w}: powerup {pu}: XML1 callback {f} has no XML2 counterpart - '
                                        f'{NPC_CALLBACK_LOSSES[f]}')
            elif f not in NPC_CALLBACKS:
                report['warnings'].append(f'{w}: powerup {pu}: XML1 callback {f} not assessed (heroes.NPC_CALLBACKS)')
        if pu == 'special' and funcs.get('func_touch') == 'damagetouch':
            _touch_damage(t, funcs)
            kind = 'touch_damage'
        else:
            kind = pu
            if pu == 'invisible' and 'invisible_activate' in funcs.values():
                t.set('class', 'invisible')
                if 'func_think' not in funcs:
                    t.set('no_think', 'true')
                if 'func_hurt' not in funcs:
                    t.set('no_hurt', 'true')
                kind = 'invisible_class'
            rep = {}
            convert_powerup_trigger(t, w, rep)
            if pu in NPC_AFFECTER_NONE:
                for k in [k for k in t if k.tag == 'affecter' and (k.get('attribute') or '').lower() == pu]:
                    t.remove(k)
                report['losses'].append(f'{w}: powerup {pu} dropped: {NPC_AFFECTER_NONE[pu]}')
                kind = 'none_attribute'
            report['losses'] += rep.get('losses', [])
            report['unverified_affecters'] += [u for u in rep.get('unverified_affecters', [])
                                               if u.rsplit(': ', 1)[-1].lower() not in NPC_AFFECTER_NONE]
            # 'plain powerup' warnings of the heroes rule: an NPC's powerup="none" is XML1's fx-only powerup
            report['notes'] += rep.get('warnings', [])
        if t.get('bolton'):
            report['losses'].append(f'{w}: bolton={t.get("bolton")} (XML1 powerup bolt-on model, default.xbe 0x95747) '
                                    f'has no XMen2.exe powerup attribute; kept, unread')
        if pu in removed and not t.get('tag_name') and not t.get('shared_tag'):
            t.set('tag_name', NPC_REMOVE_TAG.format(attr=pu))
            tagged.add(pu)
            c['npc_powerup_tag_name'] += 1
        c[f'npc_powerup:{kind}'] += 1
    for m, t, attr in removals:
        w = f'{where}{m.get("name")} <trigger tag={t.get("tag")}>'
        keep = {k: t.get(k) for k in ('name', 'tag', 'time', 'powerusage') if t.get(k) is not None}
        dropped = sorted(k for k in t.attrib if k not in keep and k != 'remove')
        t.attrib.clear()
        t.attrib.update(keep)
        t.set('remove_tag', NPC_REMOVE_TAG.format(attr=attr))
        for k in [k for k in t if isinstance(k.tag, str) and k.tag.lower() in ('special_fx', 'affecter')]:
            t.remove(k)
        how = 'tag update' if 'name' not in keep else 'trigger'
        c[f'npc_powerup_remove:{attr}'] += 1
        report['notes'].append(f'{w}: XML1 remove="true" ({how}, attribute {attr}) -> remove_tag="{attr}"'
                               + (f'; apply-only attributes dropped {dropped}' if dropped else ''))
        if attr not in tagged and attr != 'invisible':
            report['warnings'].append(f'{w}: removes tag_name {attr!r} but no powerup of this style carries it')
    _npc_powerup_updates(root, values, where, c, report)
    return c, report


def _npc_powerup_updates(root, values, where, c, report):
    """SPEC 22.7 / 24: XML1's tag-only update of an inherited powerup trigger that changes the buff (level,
    affect_type, level_max, scope_*: Juggernaut power_boost A6 -> A8 and armor_start's 60 s immunity, Marrow's
    A2 -> A4, Avalanche's stronger quake slow) re-parsed the whole XML1 trigger (default.xbe); XMen2.exe reads
    those terms only on the <affecter> (0x534d90) and re-parses an updated powerup trigger's own attributes
    (0x4f6a1f -> vt+0xc), so the update was dropped. XML2's form: the update becomes <trigger tag=N time="-1"/>
    (the inherited trigger never fires; XML2 retail's own way, e.g. ps_beast) and a copy of the inherited powerup
    with the new terms on its affecters (and the update's other attributes: life, time, powerusage) is added
    under a fresh tag (>= CE.NEW_TAG_BASE). A later move's update of tag N (life, remove_tag, more terms) is
    retargeted to that copy. Parent-first, idempotent. Counts 'npc_powerup_update:<attr>', 'npc_powerup_retag'."""
    moves = CE.style_moves(root)
    used = {int(t.get('tag')) for t in root.iter() if isinstance(t.tag, str) and t.tag.lower() == 'trigger'
            and (t.get('tag') or '').strip().isdigit()}
    fresh = [max([CE.NEW_TAG_BASE - 1] + list(used)) + 1]
    new_tag = {}                      # (move lname, tag) -> tag of the replacement trigger that move added
    order, seen = [], set()

    def visit(n, stack=()):
        if n in seen or n in stack or n not in moves:
            return
        visit((moves[n].get('inherit') or '').lower(), stack + (n,))
        seen.add(n)
        order.append(n)
    for n in list(moves):
        visit(n)

    def named(m, tag):
        return next((t for t in m if isinstance(t.tag, str) and t.tag.lower() == 'trigger' and
                     t.get('tag') == tag and t.get('name')), None)
    for n in order:
        m = moves[n]
        for u in [t for t in m if isinstance(t.tag, str) and t.tag.lower() == 'trigger']:
            tag = u.get('tag')
            if u.get('name') or tag is None:
                continue
            eff_tag, eff, a = None, None, moves.get((m.get('inherit') or '').lower())
            hops = set()
            while a is not None and id(a) not in hops:
                hops.add(id(a))
                an = (a.get('name') or '').lower()
                if (an, tag) in new_tag:
                    eff_tag = new_tag[(an, tag)]
                    eff = named(a, eff_tag)
                    break
                eff = named(a, tag)
                if eff is not None:
                    eff_tag = tag
                    break
                a = moves.get((a.get('inherit') or '').lower())
            if eff is None or (eff.get('name') or '').lower() != 'powerup':
                continue
            w = f'{where}{m.get("name")} <trigger tag={tag}>'
            if eff_tag != tag:
                u.set('tag', eff_tag)
                c['npc_powerup_retag'] += 1
                report['notes'].append(f'{w}: retargeted to tag {eff_tag}, the replacement its parent added')
            terms = {k.lower(): v for k, v in u.attrib.items() if k.lower() in CE.UPDATE_AFFECTER_ATTRS
                     or k.lower().startswith('scope_')}
            if not terms or (u.get('remove') or '').strip().lower() == 'true' or u.get('remove_tag'):
                continue
            new = copy.deepcopy(eff)
            for k, v in u.attrib.items():
                kl = k.lower()
                if kl == 'tag' or kl in terms:
                    continue
                new.set(kl, values.resolve(v, single=True) if values.is_code(v) else v)
            affs = [x for x in new.iter() if isinstance(x.tag, str) and x.tag.lower() == 'affecter']
            if affs and all(x.get(k) == (values.resolve(v, single=True) if values.is_code(v) else v)
                            for x in affs for k, v in terms.items() if k != 'level_max'):
                for k in [k for k in u.attrib if k.lower() in terms]:
                    del u.attrib[k]                    # the inherited buff already has these terms (Mystique)
                c['npc_powerup_update_same'] += 1
                continue
            if not affs:
                report['losses'].append(f'{w}: {terms} update a powerup without an <affecter> ({new.attrib}); kept '
                                        f'as the inherited buff')
                continue
            for x in affs:
                for k, v in terms.items():
                    if k == 'level_max':
                        continue                       # a range bound XML1 read with level; XML2 has one level
                    x.set(k, values.resolve(v, single=True) if values.is_code(v) else v)
            nt = str(fresh[0])
            fresh[0] += 1
            new.set('tag', nt)
            u.attrib.clear()
            u.set('tag', eff_tag)
            u.set('time', '-1')
            m.insert(list(m).index(u) + 1, new)
            new_tag[(n, tag)] = nt
            for k in terms:
                c[f'npc_powerup_update:{k}'] += 1
            report['notes'].append(f'{w}: XML1 update {terms} of the inherited powerup -> tag {eff_tag} time="-1" + '
                                   f'the updated powerup under tag {nt} {[x.attrib for x in affs]}')


def _touch_damage(t, funcs):
    """XML1 powerup="special" + func_touch="damagetouch" -> XML2 class="touch_damage" (XML2 retail ps_storm form):
    damage = XML1's rand(level, level_max) (default.xbe 0x2c970: the lower numbers of the resolved codes)."""
    a = {k: v for k, v in t.attrib.items() if not FUNC_ATTR.match(k)}
    lo = _first_number(a.pop('level', None))
    hi = _first_number(a.pop('level_max', None)) or lo
    a.pop('powerup', None)
    kids = _powerup_fx(a, funcs)
    a['class'] = 'touch_damage'
    if lo is not None:
        a['damage'] = lo if hi == lo else f'{lo} {hi}'
    t.attrib.clear()
    t.attrib.update(a)
    for k in kids:
        t.append(k)


# ------------------------------------------------------------------------------------------------ style collapse
class StyleCollapse:
    """One XML1 hero powerstyle -> the XML2 form (DESIGN 4.3 / 4.4). Usage:
        sc = StyleCollapse(hero_lname, root, values, talents, unregistered)
        out_root = sc.run()   # sc.talentvalues: {talent: {tv_name: {rank: value}}}, sc.report
    talents: {talent lname: {'power': '0'..'5'|None, 'levels': n}} of the hero's inline talents."""

    def __init__(self, hero, root, values, talents, unregistered, icons='xml1'):
        self.hero = hero
        self.src = root
        self.values = values
        self.talents = talents
        self.unregistered = set(unregistered)
        self.icons = icons
        self.report = {'chain_map': {}, 'kept': [], 'dropped': [], 'collapsed': {}, 'renamed': {},
                       'enum_top_rung': [], 'added_triggers': [], 'nonref_top_rung': [], 'losses': [],
                       'warnings': [], 'errors': [], 'unverified_affecters': [], 'unregistered_handlers': [],
                       'transplanted': []}
        self.talentvalues = {}       # talent -> {tv_name: {rank: value}}
        self.tv_top = {}             # tv_name -> value at the top rank (fallback literal)
        self.tv_used = set()
        self.moves = collections.OrderedDict()
        self.xtreme_talent = next((t for t, i in talents.items() if i.get('power') == '3'), None)

    # ---------------------------------------------------------------- classification
    def _reqs(self, m):
        return [(_lower_attrs(r).get('cat', '').lower(), _lower_attrs(r).get('item', ''),
                 _lower_attrs(r).get('level', '')) for r in m if r.tag.lower() == 'require']

    def _skill_req(self, m):
        for cat, item, lvl in self._reqs(m):
            if cat in ('skill', 'talent') and item:
                return item.lower(), lvl
        return None, None

    def _xtl_rank(self, m):
        for cat, item, lvl in self._reqs(m):
            if cat == 'level' and re.match(r'^X[TL][LT]\d$', lvl or ''):
                return int(lvl[-1])
        return None

    def _is_rung(self, m):
        inh = m.get('inherit')
        if not inh or inh not in self.moves:
            return False
        item, lvl = self._skill_req(m)
        if item and str(lvl).isdigit() and int(lvl) > 1:
            return True
        if self._xtl_rank(m):
            return True
        return m.get('name', '').lower() in TOP_NAMES

    def _rank(self, m, is_root):
        if is_root:
            return 1
        item, lvl = self._skill_req(m)
        if item and str(lvl).isdigit():
            return int(lvl)
        x = self._xtl_rank(m)
        if x:
            return x
        return None

    def _root_of(self, name, seen=None):
        seen = seen or set()
        m = self.moves[name]
        inh = m.get('inherit')
        if inh and inh in self.moves and name not in seen and self._is_rung(m):
            seen.add(name)
            return self._root_of(inh, seen)
        return name

    # ---------------------------------------------------------------- effective (inherit-resolved) moves
    def _effective(self, name, memo):
        if name in memo:
            return memo[name]
        m = self.moves[name]
        inh = m.get('inherit')
        if inh and inh in self.moves and inh != name:
            base = copy.deepcopy(self._effective(inh, memo))
            for k, v in m.attrib.items():
                if k not in ('name', 'inherit', 'fallback'):
                    base.set(k, v)
            base.attrib.pop('inherit', None)
            for c in m:
                tag = c.tag.lower()
                if tag == 'trigger':
                    t = c.get('tag')
                    target = next((x for x in base if x.tag.lower() == 'trigger' and t is not None and x.get('tag') == t), None)
                    if target is None:
                        base.append(copy.deepcopy(c))
                    else:
                        for k, v in c.attrib.items():
                            target.set(k, v)
                        for sub in c:
                            if not any(x.tag == sub.tag and x.attrib == sub.attrib for x in target):
                                target.append(copy.deepcopy(sub))
                elif tag == 'chain':
                    act = (c.get('action') or '').lower()
                    target = next((x for x in base if x.tag.lower() == 'chain' and (x.get('action') or '').lower() == act), None)
                    if target is None:
                        base.append(copy.deepcopy(c))
                    else:
                        target.set('result', c.get('result'))
                elif tag == 'event':
                    nm = c.get('name')
                    target = next((x for x in base if x.tag.lower() == 'event' and x.get('name') == nm), None)
                    if target is None:
                        base.append(copy.deepcopy(c))
                    else:
                        for k, v in c.attrib.items():
                            target.set(k, v)
                elif tag == 'require':
                    pass                                   # the rung's own gate: rank only (DESIGN 4.4 rule 4)
                else:
                    base.append(copy.deepcopy(c))
        else:
            base = copy.deepcopy(m)
            base.attrib.pop('inherit', None)
        base.set('name', name)
        memo[name] = base
        return base

    # ---------------------------------------------------------------- talentvalues
    def _tv(self, talent, attr, tagsuffix, per_rank, n):
        """register a talentvalue for `talent` with values per rank (dict rank->value, gaps carried forward);
        returns the %reference."""
        short = SHORT.get(attr, attr)
        if tagsuffix:
            short = f'{short}_t{tagsuffix}'
        name = talentvalue_name(self.hero, talent, short, self.tv_used)
        table = {}
        last = None
        for r in range(1, n + 1):
            if r in per_rank and per_rank[r] is not None:
                last = per_rank[r]
            table[r] = last if last is not None else '0'
        self.talentvalues.setdefault(talent, {})[name] = table
        self.tv_top[name] = table[n]
        return '%' + name

    def _resolved(self, v, attr):
        try:
            return self.values.resolve(v, single=attr in ('level', 'chance', 'radius', 'life', 'count', 'maxrange'))
        except KeyError:
            return v

    # ---------------------------------------------------------------- collapse of one chain
    def _collapse(self, root_name, rungs, out_name, talent, memo):
        """rungs: [(rank, name)] sorted; returns the output FightMove."""
        ranks = {1: root_name}
        for rk, nm in rungs:
            if rk in ranks and ranks[rk] != nm:
                self.report['errors'].append(f'{root_name}: two rungs claim rank {rk} ({ranks[rk]}, {nm})')
            ranks[rk] = nm
        n = max(ranks)
        missing = [r for r in range(1, n + 1) if r not in ranks]
        if missing:
            self.report['errors'].append(f'{root_name}: ranks {missing} have no rung (talent {talent})')
            for r in missing:                                 # carry the previous rung forward
                ranks[r] = ranks[r - 1]
        eff = {r: self._effective(ranks[r], memo) for r in range(1, n + 1)}
        out = copy.deepcopy(eff[1])
        out.set('name', out_name)
        for k in ('fallback', 'inherit'):
            out.attrib.pop(k, None)
        where = f'{self.hero}:{out_name}'
        # -- FightMove attributes
        keys = set()
        for e in eff.values():
            keys |= set(e.attrib)
        for k in sorted(keys - {'name', 'inherit', 'fallback'}):
            vals = {r: eff[r].get(k) for r in eff}
            if len({v for v in vals.values()}) == 1:
                continue
            res = {r: self._resolved(v, k) for r, v in vals.items() if v is not None}
            if all(_numeric(v) for v in res.values()) and ('fightmove', k) in VALUE_REF_ATTRS and talent:
                out.set(k, self._tv(talent, k, None, res, n))
            else:
                top = vals[n] if vals[n] is not None else next(v for r in sorted(vals, reverse=True) for v in [vals[r]] if v is not None)
                out.set(k, top)
                self.report['enum_top_rung'].append(f'{where} @{k}: {vals} -> {top}')
        # -- triggers by tag
        def trig(e, tag):
            return next((x for x in e if x.tag.lower() == 'trigger' and x.get('tag') == tag), None)
        root_tags = [x.get('tag') for x in eff[1] if x.tag.lower() == 'trigger' and x.get('tag') is not None]
        all_tags = []
        for r in range(1, n + 1):
            for x in eff[r]:
                if x.tag.lower() == 'trigger' and x.get('tag') is not None and x.get('tag') not in all_tags:
                    all_tags.append(x.get('tag'))
        multi = collections.Counter()
        for tag in all_tags:
            attrs = set()
            for r in eff:
                x = trig(eff[r], tag)
                if x is not None:
                    attrs |= set(x.attrib)
            for k in attrs:
                vals = [trig(eff[r], tag).get(k) if trig(eff[r], tag) is not None else None for r in range(1, n + 1)]
                if len({v for v in vals if v is not None}) > 1:
                    multi[k] += 1
        for tag in all_tags:
            first = next(r for r in range(1, n + 1) if trig(eff[r], tag) is not None)
            present = tag in root_tags
            src = trig(eff[first], tag)
            if present:
                tgt = trig(out, tag)
            else:
                tgt = copy.deepcopy(src)
                out.append(tgt)
                self.report['added_triggers'].append(f'{where}: trigger tag {tag} ({src.get("name")}) from rank {first}')
            attrs = set()
            for r in eff:
                x = trig(eff[r], tag)
                if x is not None:
                    attrs |= set(x.attrib)
            for k in sorted(attrs):
                if k in ('name', 'tag'):
                    continue
                vals = {r: (trig(eff[r], tag).get(k) if trig(eff[r], tag) is not None else None) for r in range(1, n + 1)}
                distinct = {v for v in vals.values() if v is not None}
                if k == 'powerup' and len(distinct) > 1 and talent:
                    continue                                    # split into life-gated triggers below
                gate_needed = (not present) and k == 'life'
                if len(distinct) <= 1 and not gate_needed:
                    if k in tgt.attrib or vals[first] is not None:
                        tgt.set(k, vals[first] if vals[first] is not None else next(iter(distinct)))
                    continue
                suffix = tag if multi[k] > 1 else None
                if k == 'pierce':
                    per = {r: ('1' if (vals[r] or '').lower() == 'true' else '0') for r in range(1, n + 1)}
                    tgt.attrib.pop('pierce', None)
                    tgt.set('piercechance', self._tv(talent, 'pierce', suffix, per, n) if talent else '1')
                    self.report['losses'].append(f'{where}: pierce from rank {min(r for r, v in per.items() if v == "1")} -> piercechance talentvalue (UNVERIFIED on beams)')
                    continue
                res = {r: self._resolved(v, k) for r, v in vals.items() if v is not None}
                numeric = all(_numeric(v) for v in res.values())
                if numeric and talent:
                    per = dict(res)
                    if not present:
                        for r in range(1, first):
                            per[r] = '0' if k == 'life' else res[first]
                    tgt.set(k, self._tv(talent, k, suffix, per, n))
                else:
                    top = next(vals[r] for r in range(n, 0, -1) if vals[r] is not None)
                    tgt.set(k, top)
                    self.report['enum_top_rung'].append(f'{where} trigger {tag} @{k}: {vals} -> {top}')
            if not present and 'life' not in attrs:
                self.report['added_triggers'].append(f'{where}: trigger tag {tag} has no life to gate it (active from rank 1, UNGATED)')
            # a victim event tag that changes with the rank (Iceman's beam: chill tag 10, frozen tag 20 from rank
            # 6): XML2's victimeventtag1/2 apply both powerups; the later one is life-gated to 0 below its rank
            vals = {r: (trig(eff[r], tag).get('victimeventtag') if trig(eff[r], tag) is not None else None) for r in range(1, n + 1)}
            vts = []
            for r in range(1, n + 1):
                if vals[r] is not None and vals[r] not in vts:
                    vts.append(vals[r])
            if len(vts) > 1:
                tgt.attrib.pop('victimeventtag', None)
                for i, v in enumerate(vts, 1):
                    tgt.set(f'victimeventtag{i}', v)
                self.report['losses'].append(f'{where}: trigger {tag} victimeventtag {vts} -> victimeventtag1..{len(vts)} (all applied; the later powerups are life-gated)')
            # a powerup whose kind changes with the rank (Frost/Jubilee: confused -> team_switch at rank 6): one
            # life-gated trigger per kind
            if (tgt.get('name') or '').lower() == 'powerup':
                pus = {r: (trig(eff[r], tag).get('powerup') if trig(eff[r], tag) is not None else None) for r in range(1, n + 1)}
                kinds = []
                for r in range(1, n + 1):
                    if pus[r] is not None and pus[r] not in kinds:
                        kinds.append(pus[r])
                if len(kinds) > 1 and talent:
                    used_tags = {x.get('tag') for x in out if x.tag.lower() == 'trigger'}
                    for i, kind in enumerate(kinds):
                        life = {r: (self._resolved(trig(eff[r], tag).get('life'), 'life') if trig(eff[r], tag) is not None and pus[r] == kind else '0') for r in range(1, n + 1)}
                        if i == 0:
                            t2 = tgt
                        else:
                            t2 = copy.deepcopy(tgt)
                            nt = next(str(j) for j in range(200, 400) if str(j) not in used_tags)
                            used_tags.add(nt)
                            t2.set('tag', nt)
                            out.append(t2)
                        t2.set('powerup', kind)
                        t2.set('life', self._tv(talent, 'life', f'{tag}{kind[:4]}', life, n))
                    self.report['losses'].append(f'{where}: trigger {tag} powerup kinds {kinds} split into life-gated triggers')
            # children added by rungs (damageMod) travel to the output trigger
            for r in range(1, n + 1):
                x = trig(eff[r], tag)
                if x is None:
                    continue
                for sub in x:
                    if not any(y.tag == sub.tag and y.attrib == sub.attrib for y in tgt):
                        tgt.append(copy.deepcopy(sub))
                        if r > 1:
                            self.report['losses'].append(f'{where}: trigger {tag} <{sub.tag} {sub.attrib}> added at rank {r} is active from rank 1')
        # -- chains: the top rung's set
        for c in list(out):
            if c.tag.lower() == 'chain':
                out.remove(c)
        seen = set()
        for r in range(1, n + 1):
            for c in eff[r]:
                if c.tag.lower() == 'chain' and (c.get('action') or '').lower() not in seen:
                    seen.add((c.get('action') or '').lower())
                    out.append(copy.deepcopy(c))
        for c in out:
            if c.tag.lower() == 'chain':
                act = (c.get('action') or '').lower()
                for r in range(n, 0, -1):
                    x = next((y for y in eff[r] if y.tag.lower() == 'chain' and (y.get('action') or '').lower() == act), None)
                    if x is not None:
                        c.set('result', x.get('result'))
                        break
        # -- requires: the root's, cat talent -> skill; a root without a gate gets one
        reqs = [x for x in out if x.tag.lower() == 'require']
        if talent and not any((r.get('cat') or '').lower() in ('skill', 'talent') for r in reqs):
            out.insert(0, ET.Element('require', {'cat': 'skill', 'item': talent, 'level': '1'}))
        self.report['collapsed'][out_name] = {'root': root_name, 'ranks': {r: ranks[r] for r in range(1, n + 1)},
                                              'talent': talent}
        for r in range(1, n + 1):
            self.report['chain_map'][ranks[r]] = out_name
        return out, n

    # ---------------------------------------------------------------- the run
    def run(self):
        src = self.src
        for m in src:
            if m.tag == 'FightMove' and m.get('name'):
                self.moves[m.get('name')] = m
        memo = {}
        rungs_of = collections.defaultdict(list)
        rung_names = set()
        for name, m in self.moves.items():
            if self._is_rung(m):
                root = self._root_of(name)
                if root == name:
                    continue
                rk = self._rank(m, False)
                if rk is None:
                    self.report['errors'].append(f'{self.hero}: rung {name} has no rank')
                    continue
                rungs_of[root].append((rk, name))
                rung_names.add(name)
        # plan: root -> (out_name, talent, handler)
        plan = {}
        for name, m in self.moves.items():
            if name in rung_names:
                continue
            rungs = sorted(rungs_of.get(name, []))
            item, lvl = self._skill_req(m)
            gate = item
            if gate is None and rungs:
                for _, rn in rungs:
                    gi, _ = self._skill_req(self.moves[rn])
                    if gi:
                        gate = gi
                        break
            if gate is None and rungs and any(self._xtl_rank(self.moves[rn]) for _, rn in rungs):
                gate = self.xtreme_talent
            tinfo = self.talents.get(gate or '')
            power = tinfo.get('power') if tinfo else None
            xtl_chain = bool(rungs) and all(self._xtl_rank(self.moves[rn]) for _, rn in rungs)
            # a power root carries the gate itself at rank 1 (or, like Gambit's card_throw1 / Phoenix's
            # telekinesis_start1, no gate but the power's icon); an XTL-gated sub-chain (Rogue xtreme_contact1,
            # Wolverine xtreme_frenzy_dash1) is not the xtreme's root move
            is_power_root = bool(tinfo) and power in POWER_SLOT and (
                (item is not None and lvl in (None, '', '1')) or
                (item is None and m.get('icon') is not None and not xtl_chain))
            if is_power_root:
                out_name = POWER_SLOT[power]
            elif rungs:
                top = rungs[-1][1]
                out_name = top if top.lower() not in TOP_NAMES else name
            else:
                out_name = f'{self.hero}_decide' if name.lower() in TOP_NAMES else name
            plan[name] = [out_name, gate if (rungs or is_power_root) else None, (m.get('handler') or '').lower(), rungs]
        # power-slot conflicts: two chains gated by the same power talent (Rogue decide + drain): drop the one whose
        # root handler XMen2.exe never registers and transplant its powerusage trigger (D15)
        by_out = collections.defaultdict(list)
        for name, (out_name, gate, handler, rungs) in plan.items():
            by_out[out_name].append(name)
        transplants = {}
        dropped_roots = set()
        for out_name, names in by_out.items():
            if len(names) < 2:
                continue
            bad = [nm for nm in names if plan[nm][2] in self.unregistered]
            keep = [nm for nm in names if nm not in bad]
            if len(keep) != 1:
                self.report['errors'].append(f'{self.hero}: moves {names} all collapse to {out_name}')
                continue
            for nm in bad:
                dropped_roots.add(nm)
                transplants[keep[0]] = nm
                self.report['dropped'].append(f'{nm} (+{len(plan[nm][3])} rungs): handler {plan[nm][2]} is not '
                                              f'registered in XMen2.exe; power slot {out_name} goes to {keep[0]}')
                self.report['unregistered_handlers'].append(plan[nm][2])
        name_map = {}
        out_moves = []
        for name, (out_name, gate, handler, rungs) in plan.items():
            if name in dropped_roots:
                name_map[name] = plan[transplants_inv(transplants, name)][0] if name in transplants.values() else out_name
                for _, rn in rungs:
                    name_map[rn] = name_map[name]
                continue
            if rungs or (gate and plan[name][0] in POWER_SLOT.values()):
                mv, n = self._collapse(name, rungs, out_name, gate, memo)
                if name in transplants:
                    self._transplant(mv, transplants[name], plan[transplants[name]][3], n, gate, memo)
                if out_name in POWER_SLOT.values() and self.icons == 'generic':
                    mv.set('icon', GENERIC_POWER_ICON[out_name])
            else:
                mv = copy.deepcopy(self._effective(name, memo)) if m_has_inherit(self.moves[name]) else copy.deepcopy(self.moves[name])
                mv.set('name', out_name)
                mv.attrib.pop('fallback', None)
                if 'icon' in mv.attrib and out_name not in POWER_SLOT.values():
                    mv.attrib.pop('icon')
                self.report['kept'].append(name if name == out_name else f'{name} -> {out_name}')
                if handler in self.unregistered:
                    self.report['unregistered_handlers'].append(handler)
            if out_name != name:
                self.report['renamed'][name] = out_name
            name_map[name] = out_name
            for _, rn in rungs:
                name_map[rn] = out_name
            out_moves.append(mv)
        # remap chain results / inherits; every reference to a source move must land on an output move
        out_names = {mv.get('name') for mv in out_moves}
        dangling = []
        for mv in out_moves:
            inh = mv.get('inherit')
            if inh:
                new = name_map.get(inh, inh)
                mv.set('inherit', new)
                if inh in self.moves and new not in out_names:
                    dangling.append(f'{mv.get("name")} inherit {inh}')
            for c in mv:
                if c.tag.lower() == 'chain':
                    res = c.get('result') or ''
                    new = name_map.get(res, res)
                    c.set('result', new)
                    if res in self.moves and new not in out_names:
                        dangling.append(f'{mv.get("name")} chain {c.get("action")} -> {res}')
        for d in dangling:
            self.report['errors'].append(f'{self.hero}: dangling move reference {d}')
        # fixups + vocabulary check
        out = ET.Element(src.tag, {k: v for k, v in src.attrib.items() if k not in ('iconcolumns', 'iconrows', 'exclusive')})
        if self.icons == 'generic' and 'iconfile' in out.attrib:
            out.set('iconfile', GENERIC_ICONS)
        for e in src:
            if e.tag != 'FightMove':
                ee = copy.deepcopy(e)
                probs = []
                resolve_codes(ee, self.values, f'{self.hero}:<{e.tag} {e.get("name")}>', probs)
                self.report['errors'] += probs
                for k in list(ee.attrib):
                    if FUNC_ATTR.match(k):
                        del ee.attrib[k]
                out.append(ee)
        for mv in out_moves:
            fixup_move(mv, self.values, f'{self.hero}:{mv.get("name")}', self.report)
            self._vocab_check(mv)
            out.append(mv)
        used = set()
        for e in out.iter():
            for v in e.attrib.values():
                if isinstance(v, str) and '%' in v:
                    used |= set(_REF_RE.findall(v))
        for tal in list(self.talentvalues):
            for tvn in list(self.talentvalues[tal]):
                if tvn not in used:
                    del self.talentvalues[tal][tvn]           # superseded by a split / top-rung literal
            if not self.talentvalues[tal]:
                del self.talentvalues[tal]
        C.normalize_attrs(out)
        return out

    def _transplant(self, mv, donor_root, donor_rungs, n, talent, memo):
        """the dropped chain's powerusage trigger (per rank) joins the surviving collapsed move."""
        ranks = {1: donor_root}
        for rk, nm in donor_rungs:
            ranks[rk] = nm
        per = {}
        for r in range(1, n + 1):
            nm = ranks.get(r) or ranks[max(k for k in ranks if k <= r)]
            e = self._effective(nm, memo)
            t = next((x for x in e if x.tag.lower() == 'trigger' and (x.get('name') or '').lower() == 'powerusage'), None)
            if t is not None and t.get('powerusage'):
                per[r] = self._resolved(t.get('powerusage'), 'powerusage')
        if not per:
            return
        if any(x.tag.lower() == 'trigger' and (x.get('name') or '').lower() == 'powerusage' for x in mv):
            return
        used = {x.get('tag') for x in mv if x.tag.lower() == 'trigger'}
        tag = next(str(i) for i in range(90, 200) if str(i) not in used)
        ref = self._tv(talent, 'powerusage', None, per, n) if talent else per[max(per)]
        mv.insert(next((i for i, x in enumerate(mv) if x.tag.lower() == 'trigger'), len(mv)),
                  ET.Element('trigger', {'name': 'powerusage', 'powerusage': ref, 'tag': tag, 'time': '0'}))
        self.report['transplanted'].append(f'{mv.get("name")}: powerusage from {donor_root} ({per})')

    def _vocab_check(self, mv):
        for e in mv.iter():
            for k, v in list(e.attrib.items()):
                if isinstance(v, str) and v.startswith('%'):
                    if (e.tag.lower(), k) not in VALUE_REF_ATTRS:
                        top = self.tv_top.get(v[1:])
                        e.set(k, top if top is not None else '0')
                        self.report['nonref_top_rung'].append(f'{self.hero}:{mv.get("name")} <{e.tag} {k}> -> {top}')
                        for tal, tvs in self.talentvalues.items():
                            tvs.pop(v[1:], None)


def m_has_inherit(m):
    return bool(m.get('inherit'))


def transplants_inv(transplants, donor):
    for k, v in transplants.items():
        if v == donor:
            return k
    return donor


# ------------------------------------------------------------------------------------------------ talent files
def elemental_percent(rank):
    """DESIGN 4.6: XML2's add_attack percentage curve 0.5 .. 2.6 (iceman_ice_combat / bishop_combat) per rank."""
    return f'{min(2.6, 0.5 + 0.35 * (rank - 1)):g}'


def convert_activepowerups(apus, values, rank, where, report, bleed='on'):
    """XML1 <activepowerup> elements of one talent level -> XML2 <powerup> elements (DESIGN 4.6). Returns a list."""
    out = []
    generic = ET.Element('powerup', {'life': '-1'})
    for apu in apus:
        a = _lower_attrs(apu)
        pu = (a.get('powerup') or '').lower()
        funcs = {k: v.lower() for k, v in a.items() if FUNC_ATTR.match(k)}
        level = a.get('level')
        try:
            lvl = values.resolve(level, single=True) if level is not None else None
        except KeyError:
            report.setdefault('errors', []).append(f'{where}: activepowerup level {level!r} unknown code')
            lvl = level
        affect = a.get('affect_type')
        scopes = [(k, a[k]) for k in ('scope_damage', 'scope_attack', 'scope_node') if a.get(k)]
        for sc in apu:
            if sc.tag.lower() == 'scope':
                for k, v in _lower_attrs(sc).items():
                    scopes.append((k, v))
        if pu == 'special' and a.get('damagetype'):
            p = ET.Element('powerup', {'class': 'add_attack', 'damagepercent': elemental_percent(rank),
                                       'damagetype': a['damagetype'], 'life': '-1'})
            if a.get('effect_cust1'):
                p.append(_special_fx(a['effect_cust1'], 'custom'))
            p.append(_scope_affecter([('scope_attack', 'punch'), ('scope_attack', 'kick')]))
            out.append(p)
            report.setdefault('losses', []).append(f'{where}: elemental melee level {level} -> add_attack {elemental_percent(rank)} (percentage curve, DESIGN Q6)')
            continue
        if pu == 'none' and funcs.get('func_damage') == 'damageaddbleed':
            if bleed == 'off':
                report.setdefault('losses', []).append(f'{where}: bleed dropped (--hero-bleed off)')
                continue
            p = ET.Element('powerup', {'class': 'add_harming', 'damagepercent': '0.2', 'damagetype': 'dmg_physical',
                                       'life': a.get('user1') or '5'})
            p.append(_scope_affecter([('scope_attack', a.get('scope_attack') or 'punch')]))
            out.append(p)
            report.setdefault('unverified', []).append(f'{where}: add_harming bleed (UNVERIFIED)')
            continue
        if pu == 'reflect_damage':
            chance = a.get('user1')
            p = ET.Element('powerup', {'life': '-1'})
            if chance and _numeric(chance):
                p.set('chance', f'{float(chance) / 100:g}')
            aff = _affecter('reflect_damage', lvl, affect)
            sd = [v for k, v in scopes if k == 'scope_damage']
            if sd:
                aff.set('scope_damage', sd[0])
            p.append(aff)
            sa = [(k, v) for k, v in scopes if k == 'scope_attack']
            if sa:
                p.append(_scope_affecter(sa))
            out.append(p)
            continue
        if pu == 'might_mode_mod':
            generic.append(_affecter('might_heaviness', lvl or '1'))
            generic.append(_affecter('might_structure', '1'))
            continue
        if pu == 'none':
            report.setdefault('losses', []).append(f'{where}: activepowerup none ({funcs}) dropped')
            continue
        attr = a.get('powerup')                    # XML1's spelling (damageLevel) - the exe string has that case
        if pu not in AFFECTER_VOCAB:
            report.setdefault('unverified_affecters', []).append(f'{where}: {pu}')
        aff = _affecter(attr, lvl, affect)
        if len(scopes) == 1:
            aff.set(scopes[0][0], scopes[0][1])
            generic.append(aff)
        elif scopes:
            generic.append(aff)
            generic.append(_scope_affecter(scopes))
        else:
            generic.append(aff)
        if a.get('user1') and pu != 'health_regen':
            report.setdefault('losses', []).append(f'{where}: {pu} user1={a["user1"]} dropped')
    if len(generic):
        out.insert(0, generic)
    return out


class TalentFile:
    """Data/talents/<hero>.{XMLB,engb} content for one hero (DESIGN 4.2)."""

    def __init__(self, hero, values, icons='xml1', bleed='on'):
        self.hero = hero
        self.values = values
        self.icons = icons
        self.bleed = bleed
        self.root = ET.Element('talents')
        self.names = []
        self.levels = {}            # talent -> number of <level> elements
        self.report = {'losses': [], 'warnings': [], 'errors': [], 'unverified_affecters': [], 'unverified': []}

    def _icon(self, t, power_out):
        a = _lower_attrs(t)
        if self.icons == 'generic':
            return GENERIC_ICONS, GENERIC_POWER_ICON.get(power_out, GENERIC_PASSIVE_ICON)
        if a.get('icon_texture'):
            return a['icon_texture'], a.get('icon', '0')
        return GENERIC_ICONS, GENERIC_PASSIVE_ICON

    def add_inline(self, t, out_name=None, talentvalues=None, extra_ranks=None):
        """t: an XML1 inline <Talent> (herostat) or <Talent> definition (shared_talents.eng). talentvalues:
        {tv_name: {rank: value}} from the style collapse. extra_ranks: [(rank, char_level, description)] for the
        xtreme talents whose XML1 rungs were gated on character level (XTL2..6 -> talent ranks 2..6)."""
        a = _lower_attrs(t)
        name = out_name or a['name']
        pidx = a.get('power')
        power_out = POWER_SLOT.get(pidx) if pidx is not None else None
        attrs = {'name': name}
        for k in ('descname', 'description'):
            if a.get(k):
                attrs[k] = self.values.resolve_text(a[k]) if k == 'description' else a[k]
        tex, icon = self._icon(t, power_out)
        attrs['icon_texture'] = tex
        attrs['icon'] = icon
        if power_out:
            attrs['power'] = power_out
            if pidx in POWER_TYPE:
                attrs['type'] = POWER_TYPE[pidx]
        if (a.get('hidden') or '').lower() == 'true':
            attrs['hidden'] = 'true'
        tal = ET.Element('talent', attrs)
        if talentvalues:
            tvs = ET.SubElement(tal, 'talentvalues')
            for tvn, table in talentvalues.items():
                for r in sorted(table):
                    ET.SubElement(tvs, 'talentvalue', {'level': str(r), 'name': tvn, 'value': str(table[r])})
        levels = [c for c in t if c.tag.lower() == 'level']
        rank = 0
        for lv in levels:
            rank += 1
            la = _lower_attrs(lv)
            # XML2 talent files give every <level> a `count` (ranks it covers); without it the engine
            # counts 0 ranks and the power can never be learned or used (in game: empty power wheel)
            le = ET.Element('level', {'count': '1'})
            if la.get('description'):
                le.set('description', self.values.resolve_text(la['description']))
            for k in ('cost', 'descname'):
                if la.get(k):
                    le.set(k, la[k])
            reqs = [c for c in lv if c.tag.lower() == 'require']
            has_level_req = False
            for r in reqs:
                ra = _lower_attrs(r)
                cat = (ra.get('cat') or '').lower()
                if cat == 'talent':
                    ra['cat'] = 'skill'
                if cat == 'level':
                    has_level_req = True
                    try:
                        ra['level'] = self.values.resolve(ra.get('level'), single=True)
                    except KeyError:
                        self.report['errors'].append(f'{self.hero}:{name} level {rank}: require level {ra.get("level")!r}')
                le.append(ET.Element('require', ra))
            if not has_level_req:
                le.insert(0, ET.Element('require', {'cat': 'level', 'level': '1'}))
            apus = [c for c in lv if c.tag.lower() == 'activepowerup']
            for p in convert_activepowerups(apus, self.values, rank, f'{self.hero}:{name} level {rank}', self.report, self.bleed):
                le.append(p)
            tal.append(le)
        for rk, char_level, desc in (extra_ranks or []):
            le = ET.Element('level', {'count': '1', 'description': desc})
            le.append(ET.Element('require', {'cat': 'level', 'level': str(char_level)}))
            tal.append(le)
            rank += 1
        self.root.append(tal)
        self.names.append(name.lower())
        self.levels[name.lower()] = rank
        return tal

    def check(self):
        if len(self.names) > FILE_TALENT_MAX:
            self.report['errors'].append(f'{self.hero}: {len(self.names)} talents in the file (> {FILE_TALENT_MAX})')
        dup = [n for n, c in collections.Counter(self.names).items() if c > 1]
        if dup:
            self.report['errors'].append(f'{self.hero}: duplicate talents {dup}')


def convert_shared_real(name, src, values, icons='xml1', bleed='on'):
    """one SHARED_REAL_DEFS definition: XML1's <talent> from data/shared_talents.eng in XML2 form. toughness /
    mutantmastery / acrobatics carry their powerups in XML1 data and convert as-is; critical / might had their
    effects hardcoded in XML1's xbe (descriptions only), so their engine-form powerups are injected from
    SHARED_REAL_POWERUPS, flight's drain is the engine-keyed flight_pwr talentvalue (SHARED_REAL_TALENTVALUES),
    and leadership's combo_damage / combo_xp activepowerups convert through the generic path now that the two
    affecters are known to the engine (ids 76/77). Returns (<talent>, report)."""
    tf = TalentFile('shared', values, icons, bleed)
    tal = tf.add_inline(src, talentvalues=SHARED_REAL_TALENTVALUES.get(name))
    tal.attrib.pop('power', None)
    for lv, powerups in zip([c for c in tal if c.tag == 'level'], SHARED_REAL_POWERUPS.get(name, [])):
        p = ET.SubElement(lv, 'powerup', {'life': '-1'})
        for attr, lvl in powerups:
            p.append(_affecter(attr, lvl))
    return tal, tf.report


# ------------------------------------------------------------------------------------------------ builder
# DESIGN 4.7: the shared_talents keep list the rule-based prune must reproduce (a delta is a warning)
SHARED_KEEP_EXPECTED = frozenset("""
fightstyle_finesse1 fightstyle_hero fightstyle_wrestling fightstyle_psionic fightstyle_gun_rifle fightstyle_gun_hip
fightstyle_baton fightstyle_huge fightstyle_nonhuman fightstyle_villain leadership grab critical might flight
energy_resistant mental_resistant physical_resistant energy_resistant_share mental_resistant_share
physical_resistant_share spawn_invis dr_stun sentinel_special boss_resistances monst_dmg_high aval_crack aval_quake
blob_butt blob_belly havok_beam havok_nova jug_punch jug_slam jug_armor marrow_shards marrow_armor marrow_xtreme
steal_form pyro_flame pyro_firering pyro_firebat sabre_spin sabre_claw acrobatics toughness mutantmastery
x1_npc_energy""".split())
# DESIGN 4.7 also listed `grab` (47); in the built data nothing references it once XML2's heroes are gone (no
# style <require>, no stats entry: XML2's fightstyle grab moves are not talent-gated), so the rule drops it (46).
# In --hero-roster 21xml2 the XML2 pads reference it again and the rule keeps it. x1_npc_energy (SPEC 24) is the
# characters module's NPC energy talent (npc_values.ENERGY_TALENT): kept while a stats entry names it (47).
# SPEC 30: characters emits XML1's 14 distinct inline NPC immunity bodies as shared talents in XML2's boss_resistances
# form (npc_values.immunity_plan names each body after the XML1 talent name most entries used); kept while a stats
# entry names one (npc_values.is_immunity_talent): 47 -> 61.
SHARED_KEEP_IMMUNITIES = frozenset("""
as_special avalanche_special blob_special forge_special havok_special juggernaut_special magnetoboss_special
mastermold_special physical_res sabre_special sabretooth_special sentspider_special shadow_special toad_special
""".split())
SHARED_KEEP_EXPECTED = SHARED_KEEP_EXPECTED | SHARED_KEEP_IMMUNITIES
TV_LABEL = {'dmg': 'Damage', 'kb': 'Knockback', 'dlv': 'Destruction', 'lif': 'Seconds', 'pwr': 'Energy',
            'rng': 'Range', 'cnt': 'Count', 'lvl': 'Level', 'xdmg': 'Explosion Damage', 'xkb': 'Explosion Knockback'}


class HeroBuilder:
    def __init__(self, ctx):
        self.ctx = ctx
        self.plan = hero_plan(ctx)
        self.icons = icons_mode(ctx)
        self.bleed = bleed_mode(ctx)
        self.values = Values(ctx.read_x1_xml('data/values.xml'))
        x1sh = ctx.read_x1_xml('data/shared_talents.eng')
        self.x1_shared = {t.get('name', '').lower(): t for t in x1sh.iter() if t.tag.lower() == 'talent'}
        self.base_hero = {e: ctx.read_base_xmlb(f'Data/herostat.{e}') for e in ('XMLB', 'engb')}
        self.autospend = {c.get('name', '').lower() for c in ctx.read_base_xmlb('Data/autospend.XMLB').iter('CharacterClass')}
        self.x2_shared_names = {t.get('name', '').lower() for t in ctx.read_base_xmlb('Data/shared_talents.engb').iter('talent')}
        try:
            cc = ctx.research_json('characters/combat_compat.json')
            self.unregistered = set(cc.get('unknown_handlers', {}).keys()) or set(UNREGISTERED_HANDLERS_DEFAULT)
        except (FileNotFoundError, KeyError, ValueError, AttributeError):
            self.unregistered = set(UNREGISTERED_HANDLERS_DEFAULT)
        from . import characters as CH
        self.bolton_slots = CH.BOLTON_SLOTS
        self._rewrite = CH._rewrite_data_tree_fn(ctx)
        self.entries = {'XMLB': [], 'engb': []}          # herostat elements in order
        self.talent_files = {}                            # lname -> TalentFile
        self.styles = {}                                  # lname -> (mapped name, root)
        self.style_reports = {}
        self.packages = {}                                # rel -> root
        self.detail = {'heroes': {}, 'packages': [], 'npcstat_removed': [], 'npc_talent_refs_dropped': [],
                       'shared_keep': [], 'shared_drop': {}, 'heads': [], 'placeholders': [], 'notes': []}
        self.hero_talent_refs = set()                     # plain <talent> names the 15 heroes reference
        self.hero_file_names = collections.defaultdict(set)
        self.import_stats = collections.defaultdict(set)
        self.counts = collections.Counter()

    # ---------------------------------------------------------------- helpers
    def exists(self, rel):
        return rel in self.ctx.base_index or rel in self.ctx.registry

    def pkg_entry_exists(self, kind, fn):
        c = C.package_entry_files(kind, fn)
        return True if c is None else any(self.exists(x) for x in c)

    def _data_patch(self, n):
        def patch(root, n=n):
            C.map_tree_refs(root)
            if self._rewrite is not None:
                self._rewrite(self.ctx, root, n)
        return patch

    def _asset(self, rel, why):
        """import a generic XML1 asset under the SPEC 4.4 policy exactly as characters._asset does (an asset another
        module already wrote from the same source is reused, never re-imported)."""
        ctx = self.ctx
        n = C.norm(rel)
        stem, ext = C.split_ext(n)
        if n.startswith(FORCE_PREFIXES):
            exts = C.TEXT_OUT.get(ext) or ('.IGB' if ext == '.igb' else ext,)
            prior = [ctx.registry.get(stem + e) for e in exts]
            src = ctx.x1_path(n)
            if src is not None and all(prior) and all(p['source'] == str(src) for p in prior):
                res = C.ImportResult(n, 'written', stem, [p['rel'] for p in prior])
            elif ext in C.TEXT_OUT:
                res = ctx.import_x1_asset(n, force=True, patch=self._data_patch(n), patch_key=PATCH_DATA)
            else:
                res = ctx.import_x1_asset(n, force=True)
        else:
            res = ctx.import_x1_asset(n)
        self.import_stats[res.status].add(n)
        if res.status in ('missing', 'empty'):
            ctx.warn(f'{why}: {rel} is {res.status} on the XML1 disc')
        return res

    def _talents_info(self, st):
        info = {}
        for t in _talent_children(st):
            if is_inline_talent(t):
                a = _lower_attrs(t)
                info[a['name'].lower()] = {'power': a.get('power'), 'levels': sum(1 for c in t if c.tag.lower() == 'level')}
        return info

    # ---------------------------------------------------------------- herostat entries
    def default_entry(self, ext):
        for st in self.base_hero[ext].iter('stats'):
            if (st.get('name') or '').lower() == 'default':
                return copy.deepcopy(st)
        raise KeyError(f'XML2 herostat.{ext} has no default entry')

    def placeholder_entry(self, name, ext):
        """D2: a clone of XML2's `default` (skin 0002, 00_testguy, no team / playable) under another name."""
        e = self.default_entry(ext)
        e.set('name', name)
        for k in ('team', 'playable', 'powerstyle', 'power1', 'power2', 'power3', 'power4'):
            e.attrib.pop(k, None)
        C.normalize_attrs(e)
        return e

    # SPEC 18.1: a speaker stats entry per renamed NPC double that speaks (scripts_transform.NPC_DOUBLE_SPEAKERS).
    # A conversation's %NAME% token is looked up twice: the stats entry of that name gives the line's name label and
    # portrait (0x456d00 registry vt+0x3c/+0x64, 0x5d59d0 -> 0x5f4ec0 skin -> hud/hud_head_<skin>), and the zone
    # entity of that name gets the talk animation (0x45bd1e -> 0x4c6f20, the entity name table). The double is named
    # <hero>_x1double, so its lines say %<HERO>_X1DOUBLE% and need a stats entry of that name that shows the hero:
    # XML2's own NPC-version pattern (npcstat CyclopsSimple / Cyclops_MC: characteranims, charactername, skin, team,
    # no talents). Never spawned (the spawner keeps its character), so no character package. The same entry serves an
    # NPC that keeps XML1's own name (NPC_SPEAKER_CONVERSATIONS: Mystique as Cyclops, "cyclops_scripted", the NPC
    # Alison "alison" / "alison_scripted", the NPC Emma "emma", 2026-09-29). The name label is the hero's charactername
    # unless ST.SPEAKER_DISPLAY_NAMES gives XML1's own label (the NPC Alison: "Alison", default.xbe string 503).
    SPEAKER_ATTRS = ('characteranims', 'charactername', 'skin')

    def add_double_speakers(self, roots):
        """-> [names added]: npcstat <stats name=n> for n, h in ST.speaker_stats_entries() (join_double(h) for
        NPC_DOUBLE_SPEAKERS, the NPC names of NPC_SPEAKER_CONVERSATIONS), from h's final herostat entry of the same
        variant (XMLB / engb); also registered in ctx.shared['stats'] by run's hand-over."""
        ctx = self.ctx
        added, missing = [], []
        for ext in ('XMLB', 'engb'):
            heroes = {(s.get('name') or '').lower(): s for s in roots[ext].iter('stats')}
            new = []
            for name, h in sorted(ST.speaker_stats_entries().items()):
                src = heroes.get(h)
                if src is None:
                    missing.append(f'{h} ({ext})')
                    continue
                e = ET.Element('stats', {'name': name, 'playable': 'false', 'team': 'none'})
                for a in self.SPEAKER_ATTRS:
                    if src.get(a):
                        e.set(a, src.get(a))
                if name in ST.SPEAKER_DISPLAY_NAMES:
                    e.set('charactername', ST.SPEAKER_DISPLAY_NAMES[name])
                C.normalize_attrs(e)
                new.append(e)

            def add(root, new=new):
                have = {(s.get('name') or '').lower() for s in root.iter('stats')}
                todo = [e for e in new if e.get('name') not in have]
                root.extend(copy.deepcopy(todo))
                return bool(todo)
            ctx.patch_out_xmlb('Data/npcstat', add, exts=('.' + ext,))
            if ext == 'engb':
                added = [e.get('name') for e in new]
                self.speaker_entries = {e.get('name'): dict(e.attrib) for e in new}
        if missing:
            ctx.error(f'SPEC 18.1: no herostat entry for the speaking NPCs {missing} (npcstat speaker entry '
                      f'not added: their conversation lines would show the raw %NAME% token)')
        return added

    def xml2_entry(self, name, ext):
        for st in self.base_hero[ext].iter('stats'):
            if (st.get('name') or '').lower() == name.lower():
                return copy.deepcopy(st)
        raise KeyError(f'XML2 herostat.{ext} has no {name}')

    def hero_entry(self, h):
        """DESIGN 4.1: the XML2 herostat <stats> of XML1 hero h (same tree for XMLB and engb)."""
        ctx = self.ctx
        st = self.plan['x1'][h]
        a = _lower_attrs(st)
        name = a['name']
        out = {}
        for k, v in a.items():
            if k in DROP_STATS_ATTRS or k in NPC_ONLY_ATTRS or v == '':
                continue
            k = COSTUME_RENAME.get(k, k)
            if k.startswith('skin_') and k[5:] not in COSTUMES_X2:
                ctx.warn(f'{name}: costume {k} has no XML2 slot (table 0x6d8aa0); dropped')
                continue
            out[k] = v
        out['skin'] = C.map_skin(out['skin'])
        out['characteranims'] = C.map_animdb(out['characteranims'])
        out['powerstyle'] = C.map_powerstyle(out['powerstyle'].lower())
        if out['powerstyle'] != self.plan['style'][h]:
            ctx.error(f'{name}: powerstyle {out["powerstyle"]} != planned {self.plan["style"][h]}')
        if out.get('moveset1'):
            out['moveset1'] = C.map_fightstyle(out['moveset1'])
        for k, v in rescale_x1_hero_stats(out).items():          # XML1 stat scale -> XML2's (see STAT_SCALE)
            if out.get(k) != v:
                self.detail.setdefault('stats_rescaled', {}).setdefault(name, {})[k] = f'{out.get(k)} -> {v}'
            out[k] = v
        out['autospend'] = AUTOSPEND[h]
        if out['autospend'] not in self.autospend:
            ctx.error(f'{name}: autospend class {out["autospend"]} is not in Data/autospend.XMLB')
        out.update(HEROSTAT_POWERS)
        out['textureicon'] = TEXTUREICON.get(h, TEXTUREICON_NONE)
        out['playable'] = 'true'
        out.setdefault('scriptlevel', '3')
        out['team'] = 'hero'
        e = ET.Element('stats', out)
        ET.SubElement(e, 'Race', {'name': 'Mutant'})
        ET.SubElement(e, 'Race', {'name': 'XMen'})
        for c in st:
            tag = c.tag.lower()
            ca = _lower_attrs(c)
            if tag == 'flyeffect':
                ET.SubElement(e, 'FlyEffect', ca)
                if ca.get('effect'):
                    eff = C.norm(ca['effect']).removesuffix('.xml')
                    if not self.pkg_entry_exists('effect', eff):
                        self._asset(f'effects/{eff}.xml', f'{name} FlyEffect')
            elif tag == 'bolton':
                if len(c):
                    self.detail['notes'].append(f'{name}: BoltOn {ca.get("model")} is talent-gated (<require>): dropped (D15, UNVERIFIED)')
                    continue
                m = ca.get('model', '')
                if _SKIN4.match(m):
                    ca['model'] = C.map_skin(m)
                    if not self.exists(f"actors/{ca['model']}.igb"):
                        ctx.error(f"{name}: BoltOn actor actors/{ca['model']}.igb does not exist")
                elif m:
                    mm = C.norm(m).removesuffix('.igb')
                    if not self.exists(mm + '.igb') and not self._asset(mm + '.igb', f'{name} BoltOn').ok:
                        ctx.error(f'{name}: BoltOn model {m} exists neither in XML2 nor on the XML1 disc')
                if ca.get('anim'):
                    ca['anim'] = C.map_animdb(ca['anim'])
                    if not self.exists(f"actors/{ca['anim']}.igb"):
                        ctx.error(f"{name}: BoltOn anim actors/{ca['anim']}.igb does not exist")
                if (ca.get('slot') or '').lower() not in self.bolton_slots:
                    ctx.warn(f'{name}: BoltOn slot {ca.get("slot")!r} is not in the XMen2.exe slot table')
                ET.SubElement(e, 'BoltOn', ca)
        n_tal = 0
        for t in _talent_children(st):
            ta = _lower_attrs(t)
            tn = ta['name']
            lvl = (ta.get('level') or '').strip()
            if is_inline_talent(t):
                if lvl.isdigit() and int(lvl) >= 1:
                    ET.SubElement(e, 'talent', {'level': lvl, 'name': tn})
                    n_tal += 1
                continue
            if tn.lower() in HERO_ONLY_PASSIVES:
                tn = f'x1_{h}_{tn.lower()}'
            else:
                self.hero_talent_refs.add(tn.lower())
            attrs = {'name': tn}
            if lvl:
                attrs['level'] = lvl
            ET.SubElement(e, 'talent', attrs)
            n_tal += 1
        if n_tal > STATS_TALENT_MAX:
            ctx.error(f'{name}: {n_tal} <talent> children (> {STATS_TALENT_MAX}, FUN_0043bb80)')
        C.normalize_attrs(e)
        return e

    # ---------------------------------------------------------------- one hero
    def convert_hero(self, h):
        ctx = self.ctx
        st = self.plan['x1'][h]
        name = st.get('name')
        det = {'name': name}
        entry = self.hero_entry(h)
        self.entries['XMLB'].append(entry)
        self.entries['engb'].append(copy.deepcopy(entry))
        # style collapse
        rel = f"data/powerstyles/{_lower_attrs(st)['powerstyle'].lower()}.eng"
        sroot = ctx.read_x1_xml(rel)
        schema = ctx.x1_schema(sroot, rel)            # incl. the combat rewrite (SPEC 22) before the collapse
        combat = {k: v for k, v in sorted(schema.items()) if k.startswith('combat_')}
        if combat:
            det['combat_rewrites'] = combat
            for k, v in combat.items():
                if k.startswith('combat_event:'):
                    self.counts['combat_events_rebased'] += v
                elif k.startswith('combat_handler:'):
                    self.counts['combat_handlers_renamed'] += v
                elif k.startswith('combat_event_damagemod:'):
                    self.counts['combat_damagemods_added'] += v
                elif k.startswith('combat_event_attr:'):
                    self.counts['combat_event_attrs_added'] += v
                elif k.startswith('combat_affecter:'):
                    self.counts['combat_affecters_renamed'] += v
        tinfo = self._talents_info(st)
        if name.lower() in {n.lower() for n in self.plan['npc_heroes']}:
            det['gates_added'] = gate_npc_style(sroot, tinfo)        # an npcstat style: power moves ungated
        sc = StyleCollapse(h, sroot, self.values, tinfo, self.unregistered, self.icons)
        out_style = sc.run()
        C.map_tree_refs(out_style)
        for msg in sc.report['errors']:
            ctx.error(f'style {rel}: {msg}')
        for msg in sc.report['warnings']:
            ctx.warn(f'style {rel}: {msg}')
        mapped = self.plan['style'][h]
        self.styles[h] = (mapped, out_style)
        self.style_reports[h] = sc.report
        # per-talent rank counts vs chain lengths (DESIGN 4.4 rule 6); XTL chains -> extra xtreme ranks
        chain_n = {}
        extra = {}
        for out_name, info in sc.report['collapsed'].items():
            t = info['talent']
            if not t:
                continue
            n = len(info['ranks'])
            chain_n.setdefault(t, set()).add(n)
        for t, ns in chain_n.items():
            multi = {n for n in ns if n > 1}          # a rung-less root (Rogue's / Wolverine's power9) carries no ranks
            if len(multi) > 1:
                ctx.error(f'{name}: chains of talent {t} disagree on rank count {sorted(ns)}')
            n = max(ns)
            lv = tinfo.get(t, {}).get('levels', 0)
            if n == lv:
                continue
            if tinfo.get(t, {}).get('power') == '3' and lv == 1 and n > 1:
                # XML1 xtreme rungs are gated on character level (XTL2..6): they become talent ranks 2..n whose
                # <level> requires that character level (XML2's own xtremes have several ranks the same way)
                labels = []
                for tvn in sc.talentvalues.get(t, {}):
                    short = tvn.rsplit('_', 1)[1] if '_' in tvn else tvn
                    short = re.sub(r'_t\w+$', '', short)
                    if short in TV_LABEL:
                        labels.append(f'%{tvn} {TV_LABEL[short]}.')
                desc = ' '.join(labels) or 'Improves this ability.'
                extra[t] = [(r, self.values.level_of(f'XTL{r}') or (10 + 5 * r), desc) for r in range(2, n + 1)]
                det.setdefault('xtreme_ranks', {})[t] = n
            else:
                ctx.error(f'{name}: talent {t} has {lv} levels but its power chain has {n} rungs')
        # talent file
        tf = TalentFile(h, self.values, self.icons, self.bleed)
        for t in _talent_children(st):
            if is_inline_talent(t):
                tn = _lower_attrs(t)['name'].lower()
                tf.add_inline(t, talentvalues=sc.talentvalues.get(tn), extra_ranks=extra.get(tn))
        for t in _talent_children(st):
            ta = _lower_attrs(t)
            if not is_inline_talent(t) and ta['name'].lower() in HERO_ONLY_PASSIVES:
                src = self.x1_shared.get(ta['name'].lower())
                if src is None:
                    ctx.error(f'{name}: XML1 shared_talents.eng has no definition of {ta["name"]}')
                    continue
                tf.add_inline(src, out_name=f'x1_{h}_{ta["name"].lower()}')
        # talentvalues of talents that got no file entry (should not happen) and unused chains
        for t in sc.talentvalues:
            if t not in tf.names:
                ctx.error(f'{name}: style talentvalues reference talent {t}, which is not in the file')
        tf.check()
        for msg in tf.report['errors']:
            ctx.error(f'talents/{h}: {msg}')
        self.talent_files[h] = tf
        self.hero_file_names[h] = set(tf.names)
        # power slot / talent power cross-check
        style_moves = {m.get('name') for m in out_style if m.tag == 'FightMove'}
        for tal in tf.root.iter('talent'):
            p = tal.get('power')
            if p and p not in style_moves:
                ctx.error(f'{name}: talent {tal.get("name")} power={p} names no FightMove of {mapped}')
        for pn in ('power1', 'power2', 'power3', 'power9'):
            if pn not in style_moves:
                ctx.error(f'{name}: style {mapped} has no FightMove {pn}')
        det.update({'style': mapped, 'moves_out': len(style_moves), 'moves_in': sum(1 for m in sroot if m.tag == 'FightMove'),
                    'collapsed': sc.report['collapsed'], 'chain_map': sc.report['chain_map'], 'kept': sc.report['kept'],
                    'dropped': sc.report['dropped'], 'renamed': sc.report['renamed'],
                    'enum_top_rung': sc.report['enum_top_rung'], 'added_triggers': sc.report['added_triggers'],
                    'nonref_top_rung': sc.report['nonref_top_rung'], 'losses': sc.report['losses'] + tf.report['losses'],
                    'unverified_affecters': sc.report['unverified_affecters'] + tf.report['unverified_affecters'],
                    'unregistered_handlers': sorted(set(sc.report['unregistered_handlers'])),
                    'transplanted': sc.report['transplanted'],
                    'talents': tf.names, 'talent_levels': tf.levels,
                    'talentvalues': {t: {n: v for n, v in tvs.items()} for t, tvs in sc.talentvalues.items()}})
        self.detail['heroes'][h] = det
        self.counts['moves_collapsed'] += sum(len(i['ranks']) for i in sc.report['collapsed'].values())
        self.counts['moves_kept'] += len(sc.report['kept'])
        self.counts['moves_dropped'] += sum(1 + int(re.search(r'\+(\d+) rungs', d).group(1)) if re.search(r'\+(\d+) rungs', d) else 1
                                            for d in sc.report['dropped'])
        self.counts['enum_top_rung'] += len(sc.report['enum_top_rung'])
        self.counts['added_triggers'] += len(sc.report['added_triggers'])
        self.counts['talentvalues'] += sum(len(v) for v in sc.talentvalues.values())
        self.counts['hero_talents_total'] += len(tf.names)
        for hd in sc.report['unregistered_handlers']:
            ctx.defer(f'{name}: FightMove handler {hd} is not registered in XMen2.exe (runs as %default%, 0x4fd860)')
        # packages
        self._packages(h, entry, out_style)

    # ---------------------------------------------------------------- packages (4.8)
    def _map_entry(self, kind, path, who):
        k = (kind or '').lower()
        p = C.norm(path)
        stem, ext = C.split_ext(p)
        if ext in ('.fre', '.ger'):
            return None
        if k in ('actorskin', 'actoranimdb'):
            kind2, fn = C.map_package_entry(kind, p)
            if not self.pkg_entry_exists(kind2, fn):
                self.ctx.warn(f'{who}: {kind} {path} -> actors/{fn}.igb does not exist; entry dropped')
                return None
            return kind2, fn
        if k in C.NO_FILE_KINDS:
            return C.map_package_entry(kind, p)
        if k == 'fightstyle' or (k in ('xml', 'xml_resident') and stem.startswith(('data/powerstyles/', 'data/fightstyles/'))):
            kind2, fn = C.map_package_entry('fightstyle' if k != 'xml' else kind, p)
            if not self.pkg_entry_exists(kind2, fn):
                self.ctx.warn(f'{who}: {kind} {path} -> {fn} does not exist; entry dropped')
                return None
            return kind2, fn
        if k == 'model' and re.match(r'(hud/hud_head_|ui/hud/characters/|ui/models/characters/)\d{4}', stem):
            kind2, fn = C.map_package_entry(kind, p)
            if not self.pkg_entry_exists(kind2, fn):
                self.ctx.note(f'{who}: {kind} {path} -> {fn} not on the disc / not written; entry dropped')
                return None
            return kind2, fn
        if k == 'texture' and re.fullmatch(r'textures/loading/\d{4}', stem):
            kind2, fn = C.map_package_entry(kind, p)
            return (kind2, fn) if self.pkg_entry_exists(kind2, fn) else None
        if k in ('effect', 'model', 'texture', 'xml', 'xml_resident', 'motionpath'):
            kind2, fn = C.map_package_entry(kind, p)
            if not self.pkg_entry_exists(kind2, fn):
                res = self._asset(p, who)
                if not res.ok:
                    return None
            if not self.pkg_entry_exists(kind2, fn):
                self.ctx.error(f'{who}: {kind} {path} imported but entry {fn} does not resolve')
                return None
            return kind2, fn
        self.ctx.warn(f'{who}: package entry kind {kind!r} ({path}) not handled; dropped')
        return None

    def _pkg(self, entries, who):
        root = ET.Element('packagedef')
        seen = []
        for path, kind in entries:
            e = self._map_entry(kind, path, who)
            if e and e not in seen:
                seen.append(e)
                ET.SubElement(root, e[0], {'filename': e[1]})
        return root, seen

    @staticmethod
    def _add(root, seen, kind, fn):
        if (kind, fn) not in seen:
            seen.append((kind, fn))
            ET.SubElement(root, kind, {'filename': fn})

    @staticmethod
    def _styles_last(root):
        """move every <fightstyle> to the end of the package, keeping their order (XML2 retail form).
        XMen2.exe loads a packagedef entry by entry in document order (FUN_00561d40) and parses a style on its first
        load only (fightstyle mgr vt+0x1c = 0x4ffb30; a loaded name is not re-parsed). While parsing, a FightMove
        `<require cat="skill" item=T>` stores T's talent id (FUN_004ac470: an unregistered T -> id 0 = shared
        fightstyle_finesse1, never owned -> the power is never available) and a '%name' attribute stores the
        talentvalue id (0x4c1580: unregistered -> literal 0). So `xml_talents` (and data/entities) must come before
        the hero's style: XML2 retail lists xml_talents before every fightstyle in 380/380 packages. The XML1 bundles
        list the style first (research/heroes/powers_debug.md)."""
        styles = [c for c in root if c.tag == 'fightstyle']
        for c in styles:
            root.remove(c)
            root.append(c)

    def _packages(self, h, entry, out_style):
        ctx = self.ctx
        bundles = {}
        for k, v in ctx.manifest.items():
            m = _BUNDLE.fullmatch(k)
            if m and m.group(1) == h:
                bundles.setdefault(m.group(2), {})[m.group(3) or ''] = v
        mapped = self.plan['style'][h]
        talents_fn = f'data/talents/{h}'
        # every effect the collapsed style names must be loadable (XML1's bundle is the source of truth; a
        # reference the bundle lacks is imported and appended to the combat packages)
        style_effects = []
        for el in out_style.iter():
            for a, v in el.attrib.items():
                if re.search(r'(?:effect|effect_cust\d|footstepfx)$', a.lower()) and v and v.lower() not in ('true', 'false', 'none'):
                    e = C.norm(v).removesuffix('.xml')
                    e = e[len('effects/'):] if e.startswith('effects/') else e
                    if e not in style_effects:
                        style_effects.append(e)
        extra_effects = []
        for e in style_effects:
            if not self.pkg_entry_exists('effect', e):
                if self._asset(f'effects/{e}.xml', f'{h} style').ok:
                    extra_effects.append(e)
                else:
                    ctx.warn(f'{h}: style effect {e} exists neither in XML2 nor on the XML1 disc (dead in XML1 too)')
        entity_files = []
        written = []
        for attr, s4, skin in self.plan['costumes'][h]:
            by = bundles.get(s4, {})
            if not by:
                ctx.warn(f'{h}: no XML1 bundle for costume {attr} skin {s4}; package synthesized from the default costume bundle')
                base4 = self.plan['costumes'][h][0][1]
                by = {}
                for suf, ents in bundles.get(base4, {}).items():
                    by[suf] = [[(f'actors/{s4}.igb' if C.norm(p) == f'actors/{base4}.igb' else
                                 (f'ui/hud/characters/{s4}.igb' if C.norm(p) == f'ui/hud/characters/{base4}.igb' and ctx.x1_path(f'ui/hud/characters/{s4}.igb') else p)), k]
                               for p, k in ents]
            for suffix in ('', '_nc'):
                ents = by.get(suffix)
                if ents is None:
                    ctx.warn(f'{h}: no XML1 bundle {h}_{s4}{suffix}.fb; package derived from the combat bundle')
                    ents = [[p, k] for p, k in by.get('', []) if k.lower() in ('actorskin', 'actoranimdb', 'model', 'texture')
                            and (k.lower() != 'model' or re.match(r'(hud|ui)/', C.norm(p)))]
                who = f'{h}_{skin}{suffix}'
                root, seen = self._pkg(ents, who)
                self._add(root, seen, 'actorskin', skin) if ('actorskin', skin) not in seen else None
                if ('actoranimdb', entry.get('characteranims')) not in seen:
                    self._add(root, seen, 'actoranimdb', entry.get('characteranims'))
                atlas = ICON_ATLAS.get(h, h)
                self._add(root, seen, 'texture', f'textures/ui/{atlas}_all')
                if not self.pkg_entry_exists('texture', f'textures/ui/{atlas}_all'):
                    self._asset(f'textures/ui/{atlas}_all.igb', who)
                self._add(root, seen, 'xml_talents', talents_fn)
                for b in entry.iter('BoltOn'):
                    m = b.get('model', '')
                    e = ('actorskin', m) if N.is_skin_id(m) else ('model', C.norm(m).removesuffix('.igb'))
                    if self.pkg_entry_exists(*e):
                        self._add(root, seen, *e)
                    if b.get('anim') and self.pkg_entry_exists('actoranimdb', b.get('anim')):
                        self._add(root, seen, 'actoranimdb', b.get('anim'))
                if suffix == '':
                    for fe in entry.iter('FlyEffect'):
                        eff = C.norm(fe.get('effect') or '').removesuffix('.xml')
                        eff = eff[len('effects/'):] if eff.startswith('effects/') else eff
                        if eff and self.pkg_entry_exists('effect', eff):
                            self._add(root, seen, 'effect', eff)
                    for e in extra_effects:
                        self._add(root, seen, 'effect', e)
                    self._add(root, seen, 'fightstyle', f'data/powerstyles/{mapped}')
                    for k, fn in seen:
                        if k == 'xml' and fn.startswith('data/entities/') and fn not in entity_files:
                            entity_files.append(fn)
                else:
                    for c in list(root):
                        if c.tag == 'fightstyle' or c.tag == 'effect':
                            root.remove(c)               # XML2 _nc packages carry no styles / effects
                self._styles_last(root)
                rel = C.char_package_rel(h, skin, suffix == '_nc')
                if rel in ctx.base_index:
                    ctx.error(f'{rel}: collides with an XML2 package (skin mapping broken?)')
                    continue
                self.packages[rel] = root
                written.append(rel)
        # <name>_xml (XML2 cyclops_xml form: talents + entities + style)
        xr = ET.Element('packagedef')
        ET.SubElement(xr, 'xml_talents', {'filename': talents_fn})
        for fn in entity_files:
            ET.SubElement(xr, 'xml', {'filename': fn})
        ET.SubElement(xr, 'fightstyle', {'filename': f'data/powerstyles/{mapped}'})
        rel = f'Packages/generated/characters/{h}_xml.PKGB'
        self.packages[rel] = xr
        written.append(rel)
        self.detail['heroes'][h]['packages'] = written
        self.detail['heroes'][h]['style_effects_imported'] = extra_effects

    def placeholder_packages(self, name):
        for nc in (False, True):
            root = ET.Element('packagedef')
            ET.SubElement(root, 'actorskin', {'filename': '0002'})
            ET.SubElement(root, 'actoranimdb', {'filename': '00_testguy'})
            rel = C.char_package_rel(name, '0002', nc)
            if rel in self.ctx.base_index:
                self.ctx.error(f'{rel}: collides with an XML2 package')
                continue
            self.packages[rel] = root

    # ---------------------------------------------------------------- heads (4.9)
    def heads(self):
        listed = []
        for h in self.plan['heroes']:
            lh = h.lower()
            skin4 = self.plan['costumes'][lh][0][1]
            head = f'ui/models/characters/{C.map_skin(skin4[:2] + "01")}'
            if head in listed:
                continue                                  # ProfXGladiator shares ProfXAstral's prefix (151 -> 15101)
            if self.exists(head + '.igb'):
                listed.append(head)
            else:
                self.detail['notes'].append(f'{h}: no menu head model {head} on the disc (engine fallback {HEADS_FALLBACK})')
        root = ET.Element('packagedef')
        for m in listed + [HEADS_FALLBACK, HEADS_SCREEN]:
            ET.SubElement(root, 'model', {'filename': m})
        pc = ET.Element('packagedef')
        ET.SubElement(pc, 'model', {'filename': HEADS_FALLBACK})
        self.detail['heads'] = listed
        return root, pc

    # ---------------------------------------------------------------- shared talents (4.7) and npcstat (4.10)
    def shared_keep(self, hero_names, npc_root):
        """the rule-based keep list, computed from the build (DESIGN 4.7)."""
        ctx = self.ctx
        stats_refs = set()
        styles, fightstyles = set(), set()
        for e in self.entries['engb']:
            for t in e.iter('talent'):
                stats_refs.add((t.get('name') or '').lower())
            if e.get('powerstyle'):
                styles.add(e.get('powerstyle').lower())
        for st in npc_root.iter('stats'):
            if (st.get('name') or '').lower() in hero_names:
                continue
            for t in st.iter('talent'):
                n = (t.get('name') or '').lower()
                stats_refs.add(n)
                if n.startswith('fightstyle_'):
                    fightstyles.add(n)
            if st.get('powerstyle'):
                styles.add(st.get('powerstyle').lower())
            if st.get('moveset1'):
                fightstyles.add(st.get('moveset1').lower())
        for e in self.entries['engb']:
            if e.get('moveset1'):
                fightstyles.add(e.get('moveset1').lower())
            for t in e.iter('talent'):
                if (t.get('name') or '').lower().startswith('fightstyle_'):
                    fightstyles.add(t.get('name').lower())
        style_reqs = set()
        for kind, names in (('powerstyles', styles), ('fightstyles', fightstyles)):
            for n in sorted(names):
                root = None
                for ext in ('.XMLB', '.engb'):
                    if ctx.out_exists(f'Data/{kind}/{n}{ext}'):
                        try:
                            root = ctx.read_out_xmlb(f'Data/{kind}/{n}{ext}')
                        except Exception:      # noqa: BLE001 - reported by V3
                            root = None
                        break
                if root is None:
                    continue
                for r in root.iter():
                    if r.tag.lower() == 'require' and (r.get('cat') or '').lower() in ('skill', 'talent') and r.get('item'):
                        style_reqs.add(r.get('item').lower())
        hero_files = set().union(*self.hero_file_names.values()) if self.hero_file_names else set()
        keep, drop = [], {}
        cur_defs = [(t.get('name'), t) for t in ctx.read_out_xmlb('Data/shared_talents.engb').iter('talent')]
        for n, tdef in cur_defs:
            ln = n.lower()
            why = None
            if ln.startswith('fightstyle_') and (ln in stats_refs or ln in style_reqs):
                why = 'fightstyle named by a stats entry / style'
            elif ln in style_reqs and ln not in hero_files:
                why = 'named by a style <require>'
            elif ln in stats_refs and ln in self.x2_shared_names:
                why = 'XML2 definition referenced by a stats entry'
            elif ln in self.hero_talent_refs:
                why = 'XML1 hero plain reference'
            elif ln in SHARED_REAL_DEFS:
                why = 'XML1 real definition (SHARED_REAL_DEFS)'
            elif ln in SPECIAL_TALENT_NAMES and ln in self.hero_talent_refs:
                why = 'engine special name'
            elif ln == NV.ENERGY_TALENT and ln in stats_refs:
                why = "XML1 NPC energy pool (npc_values, SPEC 24) named by a stats entry"
            elif ln in stats_refs and ln not in self.x2_shared_names and NV.is_immunity_talent(tdef):
                why = 'XML1 NPC immunity body (npc_values, SPEC 30) named by a stats entry'
            if why:
                keep.append(ln)
            else:
                drop[ln] = ('empty NPC definition (references removed)' if ln in stats_refs else 'unreferenced')
        return keep, drop, stats_refs, style_reqs

    def shared_definition(self, name):
        """SHARED_REAL_DEFS: XML1's real definition in XML2 form (convert_shared_real)."""
        tal, report = convert_shared_real(name, self.x1_shared.get(name), self.values, self.icons, self.bleed)
        for msg in report['errors']:
            self.ctx.error(f'shared_talents {name}: {msg}')
        return tal

    # ---------------------------------------------------------------- write everything
    def write_all(self):
        ctx = self.ctx
        plan = self.plan
        hero_names = {h.lower() for h in plan['heroes']}
        # herostat: default (from each base file) + heroes + placeholders / XML2 pads
        roots = {}
        for ext in ('XMLB', 'engb'):
            root = ET.Element('characters')
            # plan order: the promoted npcstat heroes come after the placeholders (the last pad slots, hero_plan)
            heroes_by = {(e.get('name') or '').lower(): e for e in self.entries[ext]}
            ph = {p.lower() for p in plan['placeholders']}
            pads = {p.lower() for p in plan['xml2_pads']}
            for n in plan['order']:
                ln = n.lower()
                if ln == 'default':
                    root.append(self.default_entry(ext))
                elif ln in heroes_by:
                    root.append(heroes_by[ln])
                elif ln in ph:
                    root.append(self.placeholder_entry(n, ext))
                elif ln in pads:
                    root.append(self.xml2_entry(n, ext))
                else:
                    ctx.error(f'herostat.{ext}: planned entry {n} was not built')
            names = [s.get('name') for s in root.iter('stats')]
            if [n.lower() for n in names] != [n.lower() for n in plan['order']]:
                ctx.error(f'herostat.{ext} order {names} != plan {plan["order"]}')
            roots[ext] = root
        ctx.write_xmlb_pair('Data/herostat', roots['XMLB'], roots['engb'], source='xml1build.heroes', replace=True)
        # talent files + styles
        for h, tf in self.talent_files.items():
            ctx.write_xmlb(f'Data/talents/{h}', tf.root, ('.XMLB', '.engb'), source='xml1build.heroes', replace=True)
        for h, (mapped, root) in self.styles.items():
            ctx.write_xmlb(f'Data/powerstyles/{mapped}', root, ('.XMLB', '.engb'), source='xml1build.heroes', replace=True)
        # npcstat: remove the hero names (a name registers once, 0x44c3c9)
        removed = []

        def strip_heroes(root):
            changed = False
            for st in list(root):
                if (st.get('name') or '').lower() in hero_names:
                    root.remove(st)
                    removed.append(st.get('name'))
                    changed = True
            return changed
        ctx.patch_out_xmlb('Data/npcstat', strip_heroes, exts=('.XMLB', '.engb'))
        self.detail['npcstat_removed'] = sorted(set(removed))
        # shared talents: prune to the rule-based keep list, real definitions for the three passives
        npc_root = ctx.read_out_xmlb('Data/npcstat.engb')
        keep, drop, stats_refs, style_reqs = self.shared_keep(hero_names, npc_root)
        keep_set = set(keep)
        delta_extra = sorted(keep_set - SHARED_KEEP_EXPECTED)
        delta_missing = sorted(SHARED_KEEP_EXPECTED - keep_set)
        if delta_extra or delta_missing:
            ctx.warn(f'shared_talents keep list differs from DESIGN 4.7: extra {delta_extra}, missing {delta_missing} '
                     f'(the computed list is written)')
        real_defs = {n: self.shared_definition(n) for n in SHARED_REAL_DEFS if n in keep_set and n in self.x1_shared}

        def prune(root):
            changed = False
            for t in list(root):
                if t.tag != 'talent':
                    continue
                ln = (t.get('name') or '').lower()
                if ln not in keep_set:
                    root.remove(t)
                    changed = True
                elif ln in real_defs:
                    idx = list(root).index(t)
                    root.remove(t)
                    root.insert(idx, copy.deepcopy(real_defs[ln]))
                    changed = True
            return changed
        ctx.patch_out_xmlb('Data/shared_talents', prune, exts=('.XMLB', '.engb'))
        hero_files = set().union(*self.hero_file_names.values()) if self.hero_file_names else set()
        dropped_refs = []

        def strip_refs(root):
            changed = False
            for st in root.iter('stats'):
                for t in list(st):
                    if t.tag == 'talent':
                        ln = (t.get('name') or '').lower()
                        # a dropped shared talent (also the profx_* now defined only in ProfXAstral's file: an NPC
                        # cannot reach a per-hero file, and ps_profxgladiator's moves carry no talent requires)
                        if ln in drop:
                            st.remove(t)
                            dropped_refs.append((st.get('name'), ln))
                            changed = True
            return changed
        ctx.patch_out_xmlb('Data/npcstat', strip_refs, exts=('.XMLB', '.engb'))
        self.detail['npc_talent_refs_dropped'] = [list(x) for x in dropped_refs]
        speakers = self.add_double_speakers(roots)
        self.detail['npc_double_speakers'] = speakers
        self.detail['shared_keep'] = keep
        self.detail['shared_drop'] = drop
        # packages
        for p in plan['placeholders']:
            self.placeholder_packages(p.lower())
        for rel, root in sorted(self.packages.items()):
            if len(root) == 0:
                ctx.error(f'{rel}: package would be empty')
                continue
            ctx.write_bytes(rel, C.encode_xmlb(root), source='xml1build.heroes', replace=True)
            self.detail['packages'].append([rel, len(root)])
        heads, heads_pc = self.heads()
        ctx.write_bytes(HEADS_PKG, C.encode_xmlb(heads), source='xml1build.heroes', replace=True)
        ctx.write_bytes(HEADS_PC_PKG, C.encode_xmlb(heads_pc), source='xml1build.heroes', replace=True)
        # ctx.shared hand-over (4.10)
        stats = ctx.shared.get('stats') or {}
        for n in removed:
            stats.pop(n.lower(), None)
        for st in roots['engb'].iter('stats'):
            ln = st.get('name').lower()
            origin = 'xml2' if ln == 'default' or ln in {p.lower() for p in plan['xml2_pads']} else \
                ('x1_placeholder' if ln in {p.lower() for p in plan['placeholders']} else 'xml1_hero')
            stats[ln] = {'name': st.get('name'), 'file': 'herostat', 'skin': st.get('skin'),
                         'characteranims': st.get('characteranims'), 'powerstyle': st.get('powerstyle'),
                         'sounddir': st.get('sounddir'), 'origin': origin}
        for ln in list(stats):
            if stats[ln]['file'] == 'herostat' and ln not in {n.lower() for n in plan['order']}:
                del stats[ln]                                # XML2 heroes replaced
        for n, a in getattr(self, 'speaker_entries', {}).items():     # SPEC 18.1 speaker entries (npcstat)
            stats[n.lower()] = {'name': n, 'file': 'npcstat', 'skin': a.get('skin'),
                                'characteranims': a.get('characteranims'), 'powerstyle': None, 'sounddir': None,
                                'origin': 'x1_double_speaker'}
        ctx.shared['stats'] = stats
        ctx.shared['stats_names'] = set(stats)
        cp = set(ctx.shared.get('char_packages') or set())
        cp |= {C.norm(r) for r in self.packages}
        ctx.shared['char_packages'] = cp
        # counts / notes
        shared_after = len(list(ctx.read_out_xmlb('Data/shared_talents.engb').iter('talent')))
        ctx.set_count('heroes_converted', len(self.talent_files))
        ctx.set_count('hero_talent_files', len(self.talent_files))
        ctx.set_count('styles_collapsed', len(self.styles))
        ctx.set_count('shared_talents_after', shared_after)
        ctx.set_count('shared_talents_dropped', len(drop))
        ctx.set_count('npc_talent_refs_dropped', len(dropped_refs))
        ctx.set_count('npcstat_heroes_removed', len(set(removed)))
        ctx.set_count('npc_double_speakers', len(speakers))
        ctx.set_count('hero_packages', len(self.packages))
        ctx.set_count('stats_names', len(stats))
        ctx.set_count('herostat_entries', len(plan['order']))
        for k, v in self.counts.items():
            ctx.set_count(k, v)
        for k, v in sorted(self.import_stats.items()):
            ctx.set_count(f'assets_{k}', len(v))
        worst = sorted((len(v) for v in self.hero_file_names.values()), reverse=True)[:4]
        ctx.set_count('talent_pool_worst_party', shared_after + sum(worst))
        if shared_after + sum(worst) > TALENT_POOL - DANGER_ROOM_MARGIN:
            ctx.error(f'registered talents worst party {shared_after} + {worst} > {TALENT_POOL - DANGER_ROOM_MARGIN}')
        ctx.note(f'herostat: {plan["order"]} (mode {plan["mode"]}); npcstat entries removed {sorted(set(removed))}; '
                 f'shared_talents {shared_after} kept ({len(drop)} dropped: {sorted(drop)}); worst-party registered '
                 f'talents {shared_after} + {worst} = {shared_after + sum(worst)} / {TALENT_POOL}')
        for h, det in self.detail['heroes'].items():
            ctx.note(f'{det["name"]}: {det["moves_in"]} -> {det["moves_out"]} moves, {len(det["talents"])} talents '
                     f'{det["talents"]}, chains {sorted(det["collapsed"])}, dropped {det["dropped"]}, '
                     f'{len(det["enum_top_rung"])} enum/top-rung attrs, {len(det["nonref_top_rung"])} non-%-vocabulary attrs'
                     + (f', combat rewrites (SPEC 22) {det["combat_rewrites"]}' if det.get('combat_rewrites') else ''))
            for x in det['dropped']:
                ctx.defer(f'{det["name"]}: {x}')
        for n in self.detail['notes']:
            ctx.note(n)
        unver = collections.defaultdict(set)
        for h, det in self.detail['heroes'].items():
            for u in det['unverified_affecters']:
                unver[u.rsplit(': ', 1)[-1]].add(u.split(':', 1)[0])
        for attr, who in sorted(unver.items()):
            if attr.lower() in CE.AFFECTERS:
                ctx.warn(f'affecter attribute {attr!r} is registered (XMen2.exe affecter table 0x{CE.AFFECTER_TABLE:x}, id '
                         f'{CE.AFFECTERS[attr.lower()][0]}) but used by no XML2 retail style (effect UNVERIFIED): '
                         f'{sorted(who)}')
            else:
                ctx.error(f'affecter attribute {attr!r} is not in XMen2.exe\'s affecter table 0x{CE.AFFECTER_TABLE:x} '
                          f'(0x{CE.AFFECTER_PARSER:x} parses it as none; add it to combat_events.AFFECTER_RENAME): '
                          f'{sorted(who)}')
        ctx.defer('D15 (v1 scope): Rogue\'s decide step (ch_roguedecide) is dropped (Gambit/Jubilee charged_throw: '
                  'ch_throw -> ch_pickup_throw, SPEC 22); astral solo mode (T10), XML1 Danger Room courses, XML1 '
                  'team bonuses, talent icon re-atlassing, Psylocke blades 2/3 (BoltOn <require>), NPC-vs-hero balance '
                  '(flashback party save+restore: SPEC 19 popParty; mission-start unlocks: scripts.mission_start_unlocks)')
        ctx.write_meta('heroes_detail.json', self.detail)


def run(ctx):
    """xml1build step `heroes`."""
    if 'characters' not in (ctx.shared.get('selected_modules') or ['characters']) and not ctx.out_exists('Data/npcstat.engb'):
        ctx.error('heroes needs the characters output (Data/npcstat, shared_talents, styles) in <out>')
        return
    b = HeroBuilder(ctx)
    for h in b.plan['heroes']:
        b.convert_hero(h.lower())
    b.write_all()
    ctx.log(f'{len(b.talent_files)} heroes converted, {len(b.packages)} packages, herostat {len(b.plan["order"])} entries '
            f'(mode {b.plan["mode"]}), icons {b.icons}, bleed {b.bleed}')


# ------------------------------------------------------------------------------------------------ validate_out
class _Out:
    """read-only view of <out> for validate_out / check (no ctx.shared)."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.idx = ctx.out_index
        self._cache = {}

    def exists(self, rel):
        return self.idx.get(rel) is not None

    def tree(self, rel):
        n = C.norm(rel)
        if n not in self._cache:
            p = self.idx.path(rel)
            try:
                self._cache[n] = C.decode_xmlb(p.read_bytes()) if p is not None else None
            except Exception:      # noqa: BLE001 - V3 reports undecodable files
                self._cache[n] = None
        return self._cache[n]

    def tree2(self, rel_noext):
        for e in ('.XMLB', '.engb', '.PKGB'):
            t = self.tree(rel_noext + e)
            if t is not None:
                return t
        return None

    def registered_owner(self, rel):
        e = self.ctx.registry.get(rel)
        return e['owner'] if e else None


class Check:
    def __init__(self, cid):
        self.id = cid
        self.errors, self.warnings, self.notes, self.counts = [], [], [], {}

    def error(self, m):
        self.errors.append(f'{self.id}: {m}')

    def warn(self, m):
        self.warnings.append(f'{self.id}: {m}')

    def note(self, m):
        self.notes.append(f'{self.id}: {m}')


def _validate(ctx, report=None):
    """V-H1..V-H13 (DESIGN 5.2; V-H13 the unlock points) over <out>. Returns (checks list, budgets dict)."""
    o = _Out(ctx)
    plan = hero_plan(ctx)
    checks = []
    hero_l = [h.lower() for h in plan['heroes']]
    ph_l = [p.lower() for p in plan['placeholders']]
    budgets = {}

    # ---- V-H1 herostat
    ck = Check('V-H1')
    checks.append(ck)
    heros = {}
    for ext in ('XMLB', 'engb'):
        t = o.tree(f'Data/herostat.{ext}')
        if t is None:
            ck.error(f'Data/herostat.{ext} missing / undecodable')
            continue
        lst = [s for s in t.iter('stats')]
        heros[ext] = lst
        names = [s.get('name') or '' for s in lst]
        want = len(plan['order'])
        if len(lst) != want:
            ck.error(f'herostat.{ext}: {len(lst)} entries, plan has {want} (--hero-roster {plan["mode"]})')
        if [n.lower() for n in names] != [n.lower() for n in plan['order']]:
            ck.error(f'herostat.{ext} order {names} != plan {plan["order"]}')
        low = [n.lower() for n in names]
        if len(set(low)) != len(low):
            ck.error(f'herostat.{ext}: duplicate names')
        for s in lst:
            n = (s.get('name') or '')
            ln = n.lower()
            if len(n) > NAME_MAX_ROSTER:
                ck.error(f'herostat.{ext} {n}: name longer than {NAME_MAX_ROSTER} (dropped from the roster screen, 0x5db590)')
            skin = s.get('skin') or ''
            if not re.fullmatch(r'\d{4,5}', skin) or int(skin[:-2]) > 255:
                ck.error(f'herostat.{ext} {n}: skin {skin!r}')
            elif not o.exists(f'actors/{skin}.igb'):
                ck.error(f'herostat.{ext} {n}: Actors/{skin}.IGB missing')
            ca = s.get('characteranims') or ''
            if not o.exists(f'actors/{ca}.igb'):
                ck.error(f'herostat.{ext} {n}: characteranims actors/{ca}.igb missing')
            asp = (s.get('autospend') or '').lower()
            aut = o.tree('Data/autospend.XMLB')
            classes = {c.get('name', '').lower() for c in aut.iter('CharacterClass')} if aut is not None else set()
            if asp and asp not in classes:
                ck.error(f'herostat.{ext} {n}: autospend {asp!r} not in Data/autospend.XMLB')
            if ln in hero_l:
                for k, v in (('team', 'hero'), ('playable', 'true')):
                    if (s.get(k) or '').lower() != v:
                        ck.error(f'herostat.{ext} {n}: {k}={s.get(k)!r} (want {v})')
                for k, v in HEROSTAT_POWERS.items():
                    if s.get(k) != v:
                        ck.error(f'herostat.{ext} {n}: {k}={s.get(k)!r} (want {v})')
                if not s.get('textureicon'):
                    ck.error(f'herostat.{ext} {n}: no textureicon')
                ps = s.get('powerstyle') or ''
                if not (o.exists(f'data/powerstyles/{ps}.xmlb') or o.exists(f'data/powerstyles/{ps}.engb')):
                    ck.error(f'herostat.{ext} {n}: powerstyle {ps} missing')
                if len([c for c in s if c.tag == 'talent']) > STATS_TALENT_MAX:
                    ck.error(f'herostat.{ext} {n}: more than {STATS_TALENT_MAX} talents')
            if ln in ph_l and (s.get('team') or s.get('playable')):
                ck.error(f'herostat.{ext} {n}: placeholder must have no team / playable (hidden from the roster, E4)')
    ck.counts['herostat_entries'] = len(heros.get('engb', []))

    # ---- V-H2 npcstat
    ck = Check('V-H2')
    checks.append(ck)
    npc = {}
    for ext in ('XMLB', 'engb'):
        t = o.tree(f'Data/npcstat.{ext}')
        if t is None:
            ck.error(f'Data/npcstat.{ext} missing')
            continue
        npc[ext] = [s for s in t.iter('stats')]
        hn = {(s.get('name') or '').lower() for s in heros.get(ext, [])}
        nn = [(s.get('name') or '').lower() for s in npc[ext]]
        both = sorted(hn & set(nn))
        if both:
            ck.error(f'npcstat.{ext}: names also in herostat {both}')
        total = len(hn | set(nn))
        ck.counts[f'stats_names_{ext}'] = total
        budgets['stats_names'] = total
        if total > STATS_CAP:
            ck.error(f'{ext}: {total} stats names > {STATS_CAP}')

    # ---- V-H3 talent files
    ck = Check('V-H3')
    checks.append(ck)
    shared = {}
    for ext in ('XMLB', 'engb'):
        t = o.tree(f'Data/shared_talents.{ext}')
        shared[ext] = [(x.get('name') or '').lower() for x in t.iter('talent')] if t is not None else None
    shared_names = set(shared.get('engb') or [])
    file_names = {}
    file_sizes = {}
    all_defined = collections.Counter(shared_names)
    tv_files = {}
    styles = {}
    for h in hero_l:
        names = {}
        for ext in ('XMLB', 'engb'):
            t = o.tree(f'Data/talents/{h}.{ext}')
            if t is None:
                ck.error(f'Data/talents/{h}.{ext} missing')
                continue
            names[ext] = [(x.get('name') or '').lower() for x in t.iter('talent')]
        if not names:
            continue
        if len(names) == 2 and names['XMLB'] != names['engb']:
            ck.error(f'talents/{h}: XMLB and engb define different talents')
        t = o.tree(f'Data/talents/{h}.engb')
        if t is None:
            t = o.tree(f'Data/talents/{h}.XMLB')
        lst = names.get('engb') or names.get('XMLB')
        file_names[h] = set(lst)
        file_sizes[h] = len(lst)
        for nm in lst:
            all_defined[nm] += 1
        if len(lst) > FILE_TALENT_MAX:
            ck.error(f'talents/{h}: {len(lst)} talents (> {FILE_TALENT_MAX})')
        st = next((s for s in heros.get('engb', []) if (s.get('name') or '').lower() == h), None)
        ps = st.get('powerstyle') if st is not None else None
        sroot = o.tree2(f'Data/powerstyles/{ps}') if ps else None
        styles[h] = (ps, sroot)
        moves = {m.get('name') for m in sroot} if sroot is not None else set()
        tvs = collections.defaultdict(dict)
        for tal in t.iter('talent'):
            for tv in tal.iter('talentvalue'):
                tvs[tv.get('name')][int(tv.get('level') or 0)] = tv.get('value')
            p = tal.get('power')
            if p and p not in moves:
                ck.error(f'talents/{h}: {tal.get("name")} power={p} names no FightMove of {ps}')
            for r in tal.iter('require'):
                if (r.get('cat') or '').lower() in ('skill', 'talent'):
                    it = (r.get('item') or '').lower()
                    if it not in shared_names and it not in file_names[h]:
                        ck.error(f'talents/{h}: {tal.get("name")} requires talent {it!r}, defined nowhere')
        refs = set()
        for root in (t, sroot):
            if root is None:
                continue
            for e in root.iter():
                for v in e.attrib.values():
                    if isinstance(v, str) and '%' in v:
                        refs |= {r for r in _REF_RE.findall(v.replace('%%', ''))}
        for ref in sorted(refs):
            if ref not in tvs:
                ck.error(f'talents/{h}: %{ref} has no talentvalue')
                continue
            lv = sorted(tvs[ref])
            if lv != list(range(1, len(lv) + 1)):
                ck.error(f'talents/{h}: talentvalue {ref} ranks {lv} not contiguous from 1')
        for tvn in tvs:
            if len(tvn) > TALENTVALUE_NAME_MAX:
                ck.error(f'talents/{h}: talentvalue name {tvn} longer than {TALENTVALUE_NAME_MAX}')
            tv_files.setdefault(tvn, set()).add(h)
        ck.counts[f'talents_{h}'] = len(lst)
    dups = sorted(n for n, c in all_defined.items() if c > 1)
    if dups:
        ck.error(f'talent names registered more than once (shared + hero files): {dups}')
    # talentvalue names live in one global registry (name -> id): a name two files define would share one id
    st_root = o.tree('Data/shared_talents.engb')
    if st_root is not None:
        for tv in st_root.iter('talentvalue'):
            tv_files.setdefault(tv.get('name'), set()).add('shared_talents')
    tv_dups = sorted(n for n, fs in tv_files.items() if len(fs) > 1)
    if tv_dups:
        ck.error(f'talentvalue names defined by more than one file: {tv_dups[:10]}')
    tv_long = sorted(n for n in tv_files if len(n) > TALENTVALUE_NAME_MAX)
    if tv_long:
        ck.error(f'talentvalue names longer than {TALENTVALUE_NAME_MAX}: {tv_long[:10]}')
    ck.counts['talentvalue_names'] = len(tv_files)
    budgets['talentvalue_names'] = len(tv_files)
    if len(tv_files) > TALENTVALUE_NAMES_CAP:
        ck.error(f'{len(tv_files)} talentvalue names (shared + every XML1 hero file) > {TALENTVALUE_NAMES_CAP}')
    budgets['file_sizes'] = file_sizes

    # ---- V-H4 shared talents
    ck = Check('V-H4')
    checks.append(ck)
    if shared.get('XMLB') is not None and shared.get('engb') is not None:
        if set(shared['XMLB']) != set(shared['engb']):
            ck.error('shared_talents XMLB and engb differ')
        if len(shared['engb']) > SHARED_CAP:
            ck.error(f'shared_talents: {len(shared["engb"])} > {SHARED_CAP}')
        ck.counts['shared_talents'] = len(shared['engb'])
        budgets['shared_talents'] = len(shared['engb'])
        delta = sorted(set(shared['engb']) ^ SHARED_KEEP_EXPECTED)
        if delta:
            ck.warn(f'shared_talents differ from DESIGN 4.7: {delta}')
        for st in heros.get('engb', []):
            for tc in st.iter('talent'):
                tn = (tc.get('name') or '').lower()
                ln = (st.get('name') or '').lower()
                if tn in SPECIAL_TALENT_NAMES and tn not in shared_names and tn not in file_names.get(ln, set()):
                    ck.error(f'{st.get("name")}: special talent {tn} (0x4be130) defined nowhere')
        # SPEC 50 (SPEC_heroes.md: the first game's shared hero passives): the kept definitions of
        # critical / might / leadership / flight carry XML1's rank counts, level gates and engine-form bodies
        # (SHARED_REAL_POWERUPS / SHARED_REAL_TALENTVALUES), not XML2's 15/2/15-rank versions
        st_root = o.tree('Data/shared_talents.engb')
        real_want = {
            'critical': (5, ['1', '7', '12', '17', '22'],
                         [[('critical', '0.02')], [('critical', '0.04')], [('critical', '0.06')],
                          [('critical', '0.08')], [('critical', '0.10')]]),
            'might': (3, ['1', '1', '1'],
                      [[('might_heaviness', '1'), ('might_structure', '1')],
                       [('might_heaviness', '2'), ('might_structure', '1')],
                       [('might_heaviness', '3'), ('might_structure', '1')]]),
            'leadership': (5, ['4', '9', '14', '19', '24'],
                           [[('combo_damage', '1.25'), ('combo_xp', '1.05')],
                            [('combo_damage', '1.5'), ('combo_xp', '1.1')],
                            [('combo_damage', '1.75'), ('combo_xp', '1.15')],
                            [('combo_damage', '2'), ('combo_xp', '1.2')],
                            [('combo_damage', '2.5'), ('combo_xp', '1.25')]]),
            'flight': (5, ['1', '1', '1', '1', '1'], [[]] * 5),
        }
        for tn, (ranks, gates, affecters) in real_want.items():
            tal = next((t for t in st_root.iter('talent') if (t.get('name') or '').lower() == tn), None) \
                if st_root is not None else None
            if tal is None:
                ck.error(f'shared_talents: {tn} (XML1 real definition) missing')
                continue
            levels = [c for c in tal if c.tag == 'level']
            if len(levels) != ranks:
                ck.error(f'shared_talents {tn}: {len(levels)} ranks != XML1 {ranks}')
                continue
            for i, lv in enumerate(levels, 1):
                req = next((r.get('level') for r in lv if r.tag == 'require' and
                            (r.get('cat') or '').lower() == 'level'), None)
                if req != gates[i - 1]:
                    ck.error(f'shared_talents {tn} rank {i}: level gate {req!r} != XML1 {gates[i - 1]!r}')
                got = [(a.get('attribute'), a.get('level'))
                       for p in lv.iter('powerup') for a in p.iter('affecter')]
                if got != affecters[i - 1]:
                    ck.error(f'shared_talents {tn} rank {i}: affecters {got} != {affecters[i - 1]}')
            if tn == 'flight':
                pwr = {int(tv.get('level')): tv.get('value')
                       for tv in tal.iter('talentvalue') if tv.get('name') == 'flight_pwr'}
                if pwr != {1: '40', 2: '30', 3: '20', 4: '10', 5: '5'}:
                    ck.error(f'shared_talents flight: flight_pwr {pwr} != XML1 40/30/20/10/5')
        worst = sorted(file_sizes.values(), reverse=True)[:4]
        pool = len(shared['engb']) + sum(worst)
        budgets['talent_pool_worst_party'] = pool
        budgets['talent_pool_worst_party_files'] = worst
        ck.counts['talent_pool_worst_party'] = pool
        if pool > TALENT_POOL - DANGER_ROOM_MARGIN:
            ck.error(f'registered talents worst party {pool} > {TALENT_POOL - DANGER_ROOM_MARGIN}')
    else:
        ck.error('shared_talents missing')

    # ---- V-H5 styles
    ck = Check('V-H5')
    checks.append(ck)
    shared_events = CE.event_table(o.tree(CE.SHARED_EVENTS_REL))
    if not shared_events:
        ck.error(f'{CE.SHARED_EVENTS_REL} missing in <out>: hero triggers cannot resolve (0x50111e)')
    for h, (ps, sroot) in styles.items():
        if sroot is None:
            ck.error(f'{h}: style {ps} missing')
            continue
        # every trigger / event resolves to a registered ce_* type (0x501630; else dropped silently), <= 19 triggers
        # per move, names <= 31 chars (SPEC 22); unregistered handlers are the warnings below
        for f in CE.style_findings(sroot, shared_events):
            if f.kind in ('handler', 'affecter'):
                continue                                # the move loop below reports these
            why = CE.allowed(ps.lower(), f)
            if why:
                ck.note(f'{h}: {f.text(ps)} [allowlisted: {why}]')
            elif f.kind == 'ignored_tag':
                ck.note(f'{h}: {f.text(ps)}')
            else:
                ck.error(f'{h}: {f.text(ps)}')
        moves = {m.get('name'): m for m in sroot if m.tag == 'FightMove'}
        t = o.tree(f'Data/talents/{h}.engb')
        power_of = {tal.get('power'): tal.get('name') for tal in t.iter('talent') if tal.get('power')} if t is not None else {}
        for pn in ('power1', 'power2', 'power3', 'power9'):
            m = moves.get(pn)
            if m is None:
                ck.error(f'{h}: {ps} has no FightMove {pn}')
                continue
            want = power_of.get(pn)
            reqs = [(r.get('cat') or '').lower() + ':' + (r.get('item') or '') for r in m if r.tag == 'require']
            if want and f'skill:{want}' not in reqs:
                ck.error(f'{h}: {pn} requires {reqs}, talent {want} expected')
        for nm, m in moves.items():
            if nm.lower() in TOP_NAMES or m.get('fallback') is not None:
                ck.error(f'{h}: move {nm} is an XML1 top name / carries fallback')
            inh = m.get('inherit')
            if inh and inh not in moves:
                ck.error(f'{h}: {nm} inherits unknown move {inh}')
            for c in m:
                if c.tag == 'chain' and (c.get('result') or '') and c.get('result') not in moves and \
                        re.fullmatch(r'(bowl|prop|boost|optic|cyc_|ability_drain|sstrike|card_throw|StaffSlam|kinetic_boost|pick_up_|time_bomb\d|tele_strike|power_frenzy|shadow_arts|master_chaos_start|skate\d|chargeforward\d|fire_|fissure|xtreme\d|xtreme_contact\d|xtreme_frenzy_dash\d|eviscerate|clawfrenzy\d|berserk|MindFry|psychicshield|telekinesis_start|psy_|lnstrike|whirlwind|stormshield|cnfuse|fear\d|frost_shield|ppunch|cslam|colossus_steelskin|ice_|firework|flash\d|taunt\d|independence|beast_xtreme|power_(attack|smash|boost|xtreme)).*', c.get('result')):
                    ck.error(f'{h}: {nm} chains to dropped rung {c.get("result")}')
            hd = (m.get('handler') or '').lower()
            if hd and hd not in CE.FM_HANDLERS:
                ck.warn(f'{h}: {nm} handler {hd} is not registered in XMen2.exe (runs as {CE.DEFAULT_HANDLER}, '
                        f'0x4fd860)')
            for e in m.iter():
                for k, v in e.attrib.items():
                    if k in _NAME_LIKE_ATTRS:
                        continue
                    if NV.is_code(v):
                        ck.error(f'{h}: {nm} <{e.tag} {k}="{v}"> value code left')
                    if isinstance(v, str) and v.startswith('%') and (e.tag.lower(), k) not in VALUE_REF_ATTRS:
                        ck.error(f'{h}: {nm} <{e.tag} {k}> carries a % reference outside XML2\'s vocabulary')
                if e.tag == 'affecter' and (e.get('attribute') or '').lower() not in CE.AFFECTERS:
                    ck.error(f'{h}: {nm} affecter {e.get("attribute")} is not in XMen2.exe\'s affecter table '
                             f'0x{CE.AFFECTER_TABLE:x} (parses as none)')
                elif e.tag == 'affecter' and (e.get('attribute') or '').lower() not in AFFECTER_VOCAB:
                    ck.warn(f'{h}: {nm} affecter {e.get("attribute")} is not in XML2\'s affecter vocabulary (UNVERIFIED)')
        ck.counts[f'moves_{h}'] = len(moves)

    # ---- V-H6 packages
    ck = Check('V-H6')
    checks.append(ck)
    npkg = 0
    for st in heros.get('engb', []):
        ln = (st.get('name') or '').lower()
        if ln == 'default' or ln in {p.lower() for p in plan['xml2_pads']}:
            continue
        skin = st.get('skin') or ''
        skins = [skin]
        for k, v in st.attrib.items():
            if k.startswith('skin_') and re.fullmatch(r'\d{1,2}', v.strip()):
                skins.append(skin[:-2] + v.strip().zfill(2))
        for sk in skins:
            for nc in (False, True):
                rel = C.char_package_rel(ln, sk, nc)
                t = o.tree(rel)
                if t is None:
                    ck.error(f'{rel} missing')
                    continue
                npkg += 1
                ents = [(e.tag.lower(), C.norm(e.get('filename') or '')) for e in t]
                if ('actorskin', sk) not in ents:
                    ck.error(f'{rel}: no actorskin {sk}')
                if ('actoranimdb', (st.get('characteranims') or '').lower()) not in ents:
                    ck.error(f'{rel}: no actoranimdb {st.get("characteranims")}')
                if ln in hero_l:
                    if ('xml_talents', f'data/talents/{ln}') not in ents:
                        ck.error(f'{rel}: no xml_talents data/talents/{ln}')
                    if not nc and ('fightstyle', f'data/powerstyles/{(st.get("powerstyle") or "").lower()}') not in ents:
                        ck.error(f'{rel}: no fightstyle data/powerstyles/{st.get("powerstyle")}')
                    # the style is parsed when its entry is reached: talents / entities after it resolve to id 0
                    first_style = next((i for i, (k, _) in enumerate(ents) if k == 'fightstyle'), None)
                    if first_style is not None:
                        late = [f'{k} {fn}' for k, fn in ents[first_style + 1:] if k in ('xml_talents', 'xml')]
                        if late:
                            ck.error(f'{rel}: {late} after the first fightstyle (must precede it)')
                for kind, fn in ents:
                    cands = C.package_entry_files(kind, fn)
                    if cands is not None and not any(o.exists(c) for c in cands):
                        ck.error(f'{rel}: <{kind} {fn}> does not resolve')
        if ln in hero_l and o.tree(f'Packages/generated/characters/{ln}_xml.PKGB') is None:
            ck.error(f'{ln}_xml.PKGB missing')
    ck.counts['hero_packages'] = npkg

    # ---- V-H7 heads
    ck = Check('V-H7')
    checks.append(ck)
    t = o.tree(HEADS_PKG)
    if t is None:
        ck.error(f'{HEADS_PKG} missing')
    else:
        listed = [C.norm(e.get('filename') or '') for e in t]
        want = []
        for h in hero_l:
            st = next((s for s in heros.get('engb', []) if (s.get('name') or '').lower() == h), None)
            if st is None:
                continue
            head = f'ui/models/characters/{(st.get("skin") or "")[:-2]}01'
            if o.exists(head + '.igb'):
                want.append(head)
        for w in want:
            if w not in listed:
                ck.error(f'{HEADS_PKG}: head {w} not listed')
        for x in (HEADS_FALLBACK, HEADS_SCREEN):
            if x not in listed:
                ck.error(f'{HEADS_PKG}: {x} not listed')
        for m in listed:
            if not o.exists(m + '.igb'):
                ck.error(f'{HEADS_PKG}: {m}.igb missing')
        ck.counts['heads'] = len(want)
    t = o.tree(HEADS_PC_PKG)
    if t is None or [C.norm(e.get('filename') or '') for e in t] != [HEADS_FALLBACK]:
        ck.error(f'{HEADS_PC_PKG} must list exactly {HEADS_FALLBACK}')

    # ---- V-H8 HUD / UI assets
    ck = Check('V-H8')
    checks.append(ck)
    for st in heros.get('engb', []):
        ln = (st.get('name') or '').lower()
        if ln not in hero_l:
            continue
        skin = st.get('skin') or ''
        skins = [skin] + [skin[:-2] + v.strip().zfill(2) for k, v in st.attrib.items()
                          if k.startswith('skin_') and re.fullmatch(r'\d{1,2}', v.strip())]
        for sk in skins:
            # FUN_005f4ec0 tries the costume skin, the default costume and variant 01 (engine.md 3.2)
            cands = [f'hud/hud_head_{sk}.igb', f'hud/hud_head_{skin}.igb', f'hud/hud_head_{skin[:-2]}01.igb']
            if not any(o.exists(c) for c in cands):
                ck.error(f'{ln}: no HUD head for skin {sk} (nor a fallback candidate)')
            ui = [f'ui/hud/characters/{sk}.igb', f'ui/hud/characters/{skin}.igb', f'ui/hud/characters/{skin[:-2]}01.igb']
            if not o.exists(ui[0]):
                if any(o.exists(c) for c in ui[1:]):
                    ck.note(f'{ln}: UI/HUD/characters/{sk}.IGB missing on the XML1 disc; the engine falls back to the default costume / variant 01')
                else:
                    ck.warn(f'{ln}: UI/HUD/characters/{sk}.IGB missing and no fallback candidate (engine shows nothing)')
        if not any(o.exists(f'textures/loading/{skin[:-2]}{v:02d}.igb') for v in (1, 2, 3)):
            ck.note(f'{ln}: no loading screen textures/loading/{skin[:-2]}01..03 (engine picks another hero)')

    # ---- V-H9 actor slots with the heaviest XML1 party
    ck = Check('V-H9')
    checks.append(ck)
    try:
        detail = json.loads((ctx.build_dir / 'zones_detail.json').read_text(encoding='utf-8'))
        converted = list(detail.get('converted') or [])
    except (OSError, ValueError):
        converted = []
    if converted:
        from . import actor_budget as AB

        class _Reader:
            def tree(self, rel_noext, exts=('.engb', '.xmlb', '.pkgb', '.chrb')):
                for e in exts:
                    tt = o.tree(rel_noext + e)
                    if tt is not None:
                        return tt
                return None

        class _HeavyBudget(AB.Budget):
            def party(self):
                st = self.stats()
                return {n: ((st.get(n) or {}).get('skin') or '', (st.get(n) or {}).get('characteranims') or '')
                        for n in HEAVY_PARTY}
        try:
            x1h = ctx.read_x1_xml('data/herostat.eng')
        except Exception:      # noqa: BLE001
            x1h = None
        rd = _Reader()
        b = _HeavyBudget(rd, x1h)
        worst = (0, None)
        over, warn = [], []
        for z in converted:
            ents_root = rd.tree(f'packages/generated/maps/{z}', ('.pkgb',))
            if ents_root is None:
                continue
            ents = [(e.tag, e.get('filename')) for e in ents_root]
            rep = AB.zone_report(b, rd, z, ents)
            n = rep['total']
            if n > worst[0]:
                worst = (n, z)
            if n > AB.ACTOR_ERROR:
                over.append((z, n))
            elif n > AB.ACTOR_WARN:
                warn.append((z, n))
        for z, n in over:
            ck.error(f'{z}: {n} actor slots with the party {HEAVY_PARTY} (> {AB.ACTOR_ERROR}, section 14)')
        for z, n in warn:
            ck.warn(f'{z}: {n} actor slots with the party {HEAVY_PARTY} (> {AB.ACTOR_WARN})')
        ck.counts['actor_slots_max'] = worst[0]
        ck.counts['actor_slots_max_zone'] = worst[1]
        ck.counts['zones_checked'] = len(converted)
        budgets['actor_slots_heavy_party'] = worst
    else:
        ck.note('no zones_detail.json (zones did not run): actor budget with the XML1 party not checked')

    # ---- V-H10 scripts: New Game hook
    ck = Check('V-H10')
    checks.append(ck)
    newgame = str(ctx.opt('newgame') or 'chooseteam').lower()
    if newgame == 'keepteam':
        ck.note('--newgame keepteam: XML1 opening (Wolverine alone) - needs xml2-fix 1.2+ with [Game] NewGameTeam='
                'wolverine and ResetUnlocks=0 in xml2-fix.ini (roster.md option C; tools/harness.py writes them). '
                'Without the patch New Game seats the hidden Magneto placeholder instead (no crash).')
    hn = {(s.get('name') or '').lower() for s in heros.get('engb', [])}
    for ref in ('menus/new_game', 'menus/new_game_hard'):
        p = o.idx.path(C.script_rel(ref))
        if p is None:
            continue
        text = p.read_bytes().decode('latin-1')
        if re.search(r'\bloadMapKeepTeam\s*\(', text) and not re.search(r'\bloadMapChooseTeam\s*\(', text):
            missing = [n for n in NEW_GAME_NAMES if n not in hn]
            if missing:
                ck.error(f'Scripts/{ref}.py loads with loadMapKeepTeam but startFirstMission\'s names {missing} are not herostat names (fallback CStats, engine.md 2.1)')
            else:
                ck.note(f'Scripts/{ref}.py: loadMapKeepTeam hook; the seated names {NEW_GAME_NAMES} are all herostat names')
        elif not re.search(r'\bloadMapChooseTeam\s*\(', text) and newgame == 'chooseteam':
            ck.error(f'Scripts/{ref}.py: neither loadMapChooseTeam nor loadMapKeepTeam')

    # ---- V-H11 ctx.shared agrees with <out>
    ck = Check('V-H11')
    checks.append(ck)
    sh = ctx.shared.get('stats')
    if sh:
        for s in heros.get('engb', []):
            ln = (s.get('name') or '').lower()
            e = sh.get(ln)
            if e is None or e.get('file') != 'herostat':
                ck.warn(f'ctx.shared stats lacks herostat entry {ln}')
            elif ln in hero_l and e.get('origin') != 'xml1_hero':
                ck.warn(f'ctx.shared stats {ln}: origin {e.get("origin")!r} (want xml1_hero)')
        for ln, e in sh.items():
            if e.get('file') == 'herostat' and ln not in hn:
                ck.warn(f'ctx.shared stats has herostat entry {ln} that <out> lacks')

    # ---- V-H12 T7 join_hero
    ck = Check('V-H12')
    checks.append(ck)
    for ref, zone_ref in (('nyc/alison/add_cyclops', 'nyc/alison/nyc1_1_3'),
                          ('mansion/dr_mag2/blob/add_cyclops', 'x1/zones/mansion/dr_mag2/mag_nyc4')):
        p = o.idx.path(C.script_rel(ref))
        if p is None:
            continue
        text = p.read_bytes().decode('latin-1')
        if 'extractionPointLite' in text:
            ck.error(f'Scripts/{ref}.py: addHero emulation still uses extractionPointLite (danv hint gate, T7)')
        if 'extractionPointChange' not in text or 'x1join' not in text:
            ck.error(f'Scripts/{ref}.py: T7 join_hero pattern missing')
        zp = o.idx.path(C.script_rel(zone_ref))
        if zp is None:
            ck.error(f'Scripts/{zone_ref}.py (zone guard) missing')
        elif 'x1join' not in zp.read_bytes().decode('latin-1'):
            ck.error(f'Scripts/{zone_ref}.py: T7 zone guard (getGameFlag x1join) missing')

    # ---- V-H13 mission-start unlocks (issue #55: XML1's missions.xml charunlock + default.xbe's cumulative table)
    ck = Check('V-H13')
    checks.append(ck)
    from . import scripts as S                              # noqa: WPS433 - the unlock table's owner
    from . import scripts_transform as ST                   # noqa: WPS433
    unlocks = S.mission_start_unlocks(ctx)['missions']
    for m, hs in sorted(unlocks.items()):
        for h in hs:
            if h.lower() not in hero_l:
                ck.error(f'unlock point {m}: {h} is not a playable herostat hero of this build')
    markers = tuple(f'XML1 beginMission({m})' for m in unlocks)
    copies = collections.Counter()
    for rel in o.idx.under('scripts/'):
        if not rel.lower().endswith('.py'):
            continue
        text = o.idx.path(rel).read_bytes().decode('latin-1')
        if not any(mk in text for mk in markers):
            continue
        lines = text.split('\r\n')
        probs, _ = ST.unlock_problems(lines, unlocks)
        for p in probs:
            ck.error(f'{rel}: {p}')
        for i, l in enumerate(lines):
            mm = ST.BEGIN_MARKER.match(l.strip())
            if mm and mm.group('m').strip().lower() in unlocks:
                copies[mm.group('m').strip().lower()] += 1
    for m in sorted(unlocks):
        ref = f'x1/missions/begin_{m}'
        if o.idx.path(C.script_rel(ref)) is not None and not copies.get(m):
            ck.error(f'Scripts/{ref}.py has no begin-body marker for mission {m} (its unlocks cannot be checked)')
    ck.counts['unlock_missions'] = len(unlocks)
    ck.counts['unlock_begin_copies'] = sum(copies.values())

    # ---- V-TBD (issue #55): a seated forced mission never unlocks the REQUIRED heroes XML1 only seats (Magma before
    # her milestone, the Professor X forms) outside the team-menu branch
    ck = Check('V-TBD')
    checks.append(ck)
    only = S.menu_only_unlock_map(ctx) if C.forced_teams_mode(ctx) == 'seat' else {}
    marks = tuple(f'XML1 beginMission({m})' for m in only)
    n = 0
    for rel in o.idx.under('scripts/'):
        if not marks or not rel.lower().endswith('.py'):
            continue
        text = o.idx.path(rel).read_bytes().decode('latin-1')
        if not any(mk in text for mk in marks):
            continue
        n += 1
        for p in ST.menu_only_problems(text.split('\r\n'), only):
            ck.error(f'{rel}: {p}')
    ck.counts['seat_only_missions'] = len(only)
    ck.counts['seat_only_scripts_checked'] = n
    return checks, budgets


def validate_out(ctx):
    """build step `heroes_validate` (build_xml1.py, after validate.run): V-H1..V-H13 on <out>."""
    checks, budgets = _validate(ctx)
    summary = {}
    for ck in checks:
        for m in ck.errors:
            ctx.error(m)
        for m in ck.warnings:
            ctx.warn(m)
        for m in ck.notes:
            ctx.note(m)
        summary[ck.id] = {'errors': ck.errors, 'warnings': ck.warnings, 'notes': ck.notes, 'counts': ck.counts}
        for k, v in ck.counts.items():
            if isinstance(v, int):
                ctx.set_count(k, v)
    ctx.write_meta('heroes_validate.json', {'checks': summary, 'budgets': budgets})
    ne = sum(len(c.errors) for c in checks)
    nw = sum(len(c.warnings) for c in checks)
    ctx.log(f'{"PASS" if not ne else "FAIL"}: {ne} errors, {nw} warnings; budgets {budgets}')


def check(out, base=None):
    """CLI: python -m xml1build.heroes check <out>: the same checks without ctx.shared; returns (rc, budgets)."""
    args = C.default_args(out=str(out), base=str(base or C.DEFAULT_BASE))
    ctx = C.BuildContext(out, base or C.DEFAULT_BASE, args=args, registry=C.Registry.load(Path(out) / '_build' / 'registry.json'))
    try:
        rep = json.loads((Path(out) / '_build' / 'report.json').read_text(encoding='utf-8')).get('build', {})
        for k in ('hero_roster', 'hero_icons', 'hero_bleed', 'newgame'):
            if rep.get(k) is not None:
                setattr(ctx.args, k, rep[k])
    except (OSError, ValueError):
        pass
    checks, budgets = _validate(ctx)
    ne = 0
    for ck in checks:
        for m in ck.errors:
            print('ERROR', m)
            ne += 1
        for m in ck.warnings:
            print('warn ', m)
        for m in ck.notes:
            print('note ', m)
        if ck.counts:
            print(f'{ck.id} counts: {ck.counts}')
    print(f'budgets: {budgets}')
    print('RESULT:', 'PASS' if not ne else f'FAIL ({ne} errors)')
    return (1 if ne else 0), budgets


if __name__ == '__main__':
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == 'check':
        sys.exit(check(sys.argv[2])[0])
    print(__doc__)
