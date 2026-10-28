"""xml1build.fix_ini - the port's keys in xml2-fix.ini (BUILDER_DESIGN.md 3.5).

The xml2-fix DLL (dinput.dll) reads <game>/xml2-fix.ini. Two writers share that file and neither removes the other's
keys:

  the port (this module)  the content requirements of a build - [Game] NewGameTeam / ResetUnlocks / SaveFolder /
                          ForcedTeams / PostgameScript / WindowTitle / EndHeroUnlock / MainMenuItems / NewGamePlus /
                          ReviewStats / Xtract / XPCurve / GeometrySharingBlendIndices / CharacterLadderPaths /
                          ObjectiveDescriptions / BreakRule, [Limits]
                          ActorSlots / ResourceNames / ItemEnhancements / FightStyles / EffectCurves (and, with
                          --limits-wave3, StyleEvents / FightMoves / EffectTemplates / PrimitiveDefs / EffectVectors /
                          PrimitivesPerEffect / AttachedPowerups / VFNodes / ScriptPools / ParticleScratch), [Online]
                          GameVersion /
                          ContentFingerprint / FastTransfer / ReceiveValidation, [Save] Format. They are
                          functions of the build's content (the menus it wrote, its report.json, its scripts), so the
                          builder (tools/xml1builder) writes them after a build, and tools/harness.py takes its
                          [Game] / [Limits] / [Online] lines from here too (the harness and the shipped build cannot
                          drift);
  the launcher            the player's preferences - [Display], [Discord], [Online] LocalIP / Server, [Input] ... -
                          written key by key with WritePrivateProfileStringW.

merge_ini() therefore has WritePrivateProfileString semantics: it replaces or adds exactly the given keys (sections and
keys matched case-insensitively, the first matching section wins), deletes only the keys it is told to drop, and keeps
every other section, key, comment, blank line, the line endings and the file's encoding (UTF-16 with a BOM stays
UTF-16; anything else is kept byte for byte). The file is replaced atomically.

port_keys(out) is what a play build needs (the values tools/harness.py install --no-pipe --limits writes, for an
xml2-fix >= 1.2.0: MainMenuItems names the 8th mouse slot, Play Online). PORT_OWNED lists every key the port may write:
a key it owns but does not need for this build is dropped, so an update that stops needing a key removes it."""
from __future__ import annotations

import json
import os
import re
import struct
from pathlib import Path

from . import balance as BAL

# The port's own save folder (xml2-fix [Game] SaveFolder): saves and settings.dat - the profile that keeps hero
# unlocks from game to game, by herostat index - would otherwise be XML2's (Documents\Activision\X-Men Legends 2),
# so the real XML2's unlocks came up as XML1 heroes in the port's team menu. Test runs (tools/harness.py) get a folder
# of their own so tours and pipe tests never unlock heroes in the owner's play profile.
PLAY_SAVE_FOLDER = 'X-Men Legends'
TEST_SAVE_FOLDER = 'X-Men Legends (port tests)'

# xml2-fix [Game] PostgameScript (SPEC 21 D.1): XMen2.exe's endgame credits then run 'runscript <this>' instead of
# loadZone('act5/egypt/egypt6','') (an XML2 zone whose NPCs XML1 mode dropped). The build writes the script
# (scripts.POSTGAME_REF: r505, then the main menu); the key is written only when the build has it.
POSTGAME_SCRIPT = 'x1/menus/postgame'

# xml2-fix [Game] MainMenuItems (SPEC 21.2): XMen2.exe's MAIN_MENU finds its mouse items and its Quit item by XML2's
# names (label_option04..09, debug_text); the XML1 front end's main menu is XML1's, with its text on buttonN
# (xml1build.frontend.MAIN_MENU_ITEMS, the same list; frontend_selftest U2 compares them). The DLL points those name
# operands at ours in this order: label_option04..09's mouse slots, then debug_text (Quit). Without it the keys and
# the pad still work (every button has its usecmd), the mouse and Quit do not. The value is read off the build's
# menu (menu_items_for): its first 6 shown buttons with a usecmd, then the one without (Quit) - button1..7 in builds
# before Play Online (SPEC 21.2.4), button1..6 + button8 since (Play Online, button7, is keys / pad only: XMen2.exe
# clamps the mouse slots after the sixth to Quit, 0x5c944b).
MAIN_MENU_ITEMS = 'button1,button2,button3,button4,button5,button6,button8'
# xml2-fix [Game] DangerRoomGate (issue #63): the XML1 main menu's Danger Room item (frontend.MENU_BUTTONS, the item
# running "openmenu danger_room"), disabled until Phoenix has been in a campaign on the profile - the first game's
# gate (xbe 0x17e93c-0x17e975: profile bit of 'phoenix', button3), not XML2's story level 6. Written with
# MainMenuItems; an older DLL ignores the key (the item stays always open, as before).
DANGER_ROOM_GATE_ITEM = 'button3'
MAIN_MENU_MOUSE_SLOTS = 6
# xml2-fix a3b8567+ (in v1.2.0) takes an 8th name (after Quit): the mouse slot for a 7th usecmd item (Play Online,
# button7), the mouse clamp at 0x5c944b raised from 6 to 8. An older DLL quits when that slot is clicked, so the 8th
# name is only written for a DLL that has the feature (the harness: dll_has(MAIN_MENU_8TH_MARKER); the builder: its
# builds require xml2-fix >= REQUIRED_XML2FIX, which has it).
MAIN_MENU_8TH_MARKER = b'EndHeroUnlock'
MAIN_MENU_FILE = ('UI', 'menus', 'main.XMLB')

# The port's own identity in xml2-fix (a3b8567+), written for XML1 builds (the ones with PostgameScript): the window
# title (the exe says X-Men Legends 2), no XML2 hero unlock + popup after the credits (Deadpool, 0x5b1d4a), and a
# GameSpy game version of its own so port and XML2 lobbies never mix (research/online/port_online_test.md).
# GameVersion changes whenever the build's content version or its save / combat rules do (SPEC-new-save 6, decision
# D5: an append-only official identity history assigns each immutable content/catalogue envelope a unique
# four-character token. Historical X1.* tokens remain reserved (release_identity.py).
PORT_WINDOW_TITLE = 'X-Men Legends'
PORT_END_HERO_UNLOCK = '0'
from . import release_identity as RI
PORT_GAME_VERSION = RI.game_version()

# xml2-fix 1.4 [Save] Format (SPEC 70; SPEC-new-save 1.5 / A11): the LC save format. The fix reads the build's
# save tables (Data/lcsave/catalogue.lcc, legacy.lcm, the .lcbind files - xml1build.savefiles), converts the old
# saves once at start-up and saves into SaveLC; a build without the key keeps the old format. Port builds only.
SAVE_FORMAT = 'lc'

# xml2-fix [Game] NewGamePlus (SPEC 21.2.2): the XML1 front end's Begin Story runs XMen2.exe's New Game without the
# difficulty prompt (resetgame + setDifficultyLevel(1), xml1build.frontend.BEGIN_STORY_CMD), but once a win on Normal
# has unlocked Hard (the end credits, 0x5b1d44) setDifficultyLevel offers XML2's New Game+ choice (default or saved
# statistics, 0x4a099e) instead of starting. XML1 had none: '0' makes it start with the default statistics, as before
# Hard is unlocked. Written with MainMenuItems (the XML1 front end); --frontend xml2 builds keep XML2's New Game.
NEW_GAME_PLUS = '0'

# xml2-fix [Game] ReviewStats (SPEC 21.4.3): the XML1 front end's Review menu is XML2's without the Stats tab (XML1's
# Review had Screens / Cinematics / Comics / Concepts; XML2's Stats page lists its acts 1-5 from exe code); XMen2.exe's
# tab change (left / right, pad, mouse) wraps at 5, and ReviewStats=0 makes it wrap at 4 so the hidden tab can't be
# reached. Written when the build's UI/menus/review.XMLB is a REVIEW_PATHS_MENU without the Stats tab's label
# (xml1build.frontend.REVIEW_STATS_ITEMS); --frontend xml2 builds keep XML2's menu and get no key.
REVIEW_STATS = '0'
REVIEW_MENU_FILE = ('UI', 'menus', 'review.XMLB')
REVIEW_STATS_LABEL = 'option05_text'

# xml2-fix [Game] Xtract (xml2-fix 1.3.2; SPEC 66, issue #46): XMen2.exe's extractionPoint
# always adds an Xtract choice (id 2040, openmenu('worldmap')) that opens XML2's world map of its five town centres
# (which the port's zoneinfo keeps because the engine's extraction needs them there - SPEC 15); XML1's Xtraction
# menus had no world map. '0' jumps extractionPoint over the block that adds the choice, leaving the title, Change
# Team and Save. Written for every XML1 build (the ones with PostgameScript); an xml2-fix older than 1.3.2 ignores
# the key, and the menu keeps Xtract as before.
XTRACT = '0'

# xml2-fix [Game] XPCurve (SPEC 23, research/heroes/levels.md): the build's objectives, scripts and npcstat carry XML1's
# XP amounts (act 9's crystal objectives 2,000,000, asteroid_m's setXP 1,125,000), which on XMen2.exe's curve take a
# level-1 hero to 40; with XPCurve=xml1 the DLL uses XML1's level table (cap 45) and kill XP (half of each kill to
# every hero, the bench included). Written for every build_xml1.py build (its _build/report.json) - unless the build
# was made with --xp-curve xml2 (SPEC 23.1: XMen2.exe's own curve with the XML2-scaled amounts), which gets no key.
XP_CURVE = 'xml1'
BUILD_REPORT = ('_build', 'report.json')

# xml2-fix [Limits] (29938a0): actor table 40 -> 127, resource name table 450 -> 1024 (research/limits/);
# 1.3.0: the item manager's enhancement record pool 375 -> 512 (SPEC 32.1 / 32.3: XML2's own table uses 374, so the
# port's 19 Danger Room rewards with their 54 enhancements never loaded; saves store record numbers, so the pool can
# only grow). zones.ITEM_ENHANCEMENT_POOL reads this value: what the shipped ini asks the fix for is the pool the
# build is checked against.
# 1.3.1: the fighting / power style registry 19 -> 32 (SPEC 43, issue #31: XML1's zones need up to 22 styles with a
# four-hero party; the 20th was refused and the hero seated last had no powers). style_budget.capacity reads this
# value for V23.
# 1.3.2: the effect animation curve pool 900 -> 3600 (EffectCurves; xml2-fix docs/effect-curves.md): a zone's
# effects and a four-hero party's powers need more than 900 curves (943 at nyc1_1_2b's bench fire, up to about 1050
# in the heaviest zones), and past the pool XMen2.exe hands out empty curves - the effects loaded last lose their
# particles (the bench fire is a faint glow). Curves are not saved.
# MoveTriggers preserves all authored holster/redraw events and a flash/sound per gun shot.
# Requires the companion XML2 Fix move-trigger patch; absent key means stock 19.
# xml2-fix [Limits] ScriptFunctions (its docs/script-functions.md): XMen2.exe resolves script function names through a
# tree of 320; its own 308 (289 + 19 builtins) and xml2-fix's functions fill it, and a function registered past it is
# dropped together with every script line that calls it. The fix raises it to 1024 by default while ForcedTeams
# registers its functions; written here explicitly (validate V57 script function names checks the count against it).
# Nothing saved; online it is gameplay agreement rule 14.
# xml2-fix 1.9.0-beta.1 (limits wave 1, its docs/igb-cache.md) [Limits] IGBCache: XMen2.exe's IGB info cache holds 200
# records (every precached model file); full, a zone's map IGB fails and the game bounces back to the previous zone
# (the V12 budget, igb_budget.py, keeps every package under 200 - it stays the conversion's limit; 1024 is headroom
# for graphics mods). The fix moves the cache into its own memory at 1024 records and its name table with it
# (ResourceNames 2048). Online the cache is gameplay-agreement rule 31 (IGBCache) and the names rule 32.
LIMITS = {'ActorSlots': '127', 'ResourceNames': '2048', 'ItemEnhancements': '512', 'FightStyles': '32',
          'EffectCurves': '3600', 'MoveTriggers': '64', 'EntityCapacity': '1', 'ScriptFunctions': '1024',
          'IGBCache': '1024'}

# xml2-fix limits wave 3 (runtime-only; legends-classic tools/xml1build/limits_wave3.py, docs/limits-wave3.md): the style,
# move, event, effect, primitive, vector and script tables raised with headroom for graphics / character mods. Written
# ONLY with the builder option --limits-wave3 (default off; a build without it is byte-identical to one made before the
# option existed, ini included). The nine rows below ship together; each needs the companion DLL's rule (below).
#   FightStyles 32 -> 64      rule 35 revision 2  (the style registry's bitmaps grow to two dwords)
#   StyleEvents 1064 -> 4096  rule 53             (the style event pool shares one allocation with the registry)
#   FightMoves 332 -> 1024    rule 54             (+ the exhaustion guards)
#   EffectTemplates 220 -> 512 rule 55            (effect file table + definition table)
#   PrimitiveDefs 816 -> 2048 rule 56
#   EffectVectors 710 -> 4096 rule 57
#   PrimitivesPerEffect 10 -> 32 rule 58
#   AttachedPowerups 128 -> 256 rule 61          (W3-10; the DLL accepts only 256)
#   VFNodes 192 -> 256         rule 62           (W3-11, the powers' virtual-function callback nodes; only 256)
LIMITS_WAVE3 = {'FightStyles': '64', 'StyleEvents': '4096', 'FightMoves': '1024', 'EffectTemplates': '512',
                'PrimitiveDefs': '2048', 'EffectVectors': '4096', 'PrimitivesPerEffect': '32',
                'AttachedPowerups': '256', 'VFNodes': '256'}
# The two later rows (W3-8 script pools, W3-9 particle scratch) stay behind the second level of the option
# (--limits-wave3 all); XML2 Fix 1.9.0 (w3/integrated) carries both.
#   ScriptPools x1 (statements 4096 / values 8192 / compiled scripts 512 / running contexts 128)  rule 59
#   ParticleScratch 40 (the clamp; 256 only if the pool diagnostics show counts above 40)           rule 60
LIMITS_WAVE3_LATE = {'ScriptPools': 'x1', 'ParticleScratch': '40'}
LIMITS_WAVE3_MODES = ('off', 'on', 'all')
# gameplay-agreement rule ids (D:/Projects/agent-briefs/_rule-ids.md: 35 FightStyles, 53..62 assigned to wave 3)
WAVE3_RULES = {'FightStyles': 35, 'StyleEvents': 53, 'FightMoves': 54, 'EffectTemplates': 55, 'PrimitiveDefs': 56,
               'EffectVectors': 57, 'PrimitivesPerEffect': 58, 'ScriptPools': 59, 'ParticleScratch': 60,
               'AttachedPowerups': 61, 'VFNodes': 62}
# The DLL's install line for each rule, the byte marker the builder's DLL gate requires (like CHAR_SOUNDS_MARKER): the
# literal format string of each row's own install log line in XML2 Fix 1.9.0 (w3/integrated). The style manager (rules
# 35 r2 + 53), the effect pools (56 + 57) and the power pools (61 + 62, src/power_pools.cpp) are one owner each with one
# install line, so they share it; the UTF-16 key names (RELEASE_18_KEYS) still tell the rows apart. The key's name alone cannot certify a rule (an older DLL reads
# FightStyles to 32).
_STYLE_MANAGER_LINE = b'limits: style manager styles %d; events %d; size 0x%lX; %s: %s'
_EFFECT_POOLS_LINE = b'limits: %s installed {%u,0,0,0}; %zu ledger operands; native lazy constructor and teardown retained'
_POWER_POOLS_LINE = b'limits: %s 256 (allocation 0x%X): %s; %s'
WAVE3_MARKERS = {
    'FightStyles': _STYLE_MANAGER_LINE,
    'StyleEvents': _STYLE_MANAGER_LINE,
    'FightMoves': b'limits: FightMoves raised from 332 to %lu; descriptor published before MoveTriggers',
    'EffectTemplates': b'EffectFiles: %s; capacity %u',
    'PrimitiveDefs': _EFFECT_POOLS_LINE,
    'EffectVectors': _EFFECT_POOLS_LINE,
    'PrimitivesPerEffect': b'PrimitivesPerEffect: %s; capacity %u',
    'AttachedPowerups': _POWER_POOLS_LINE,
    'VFNodes': _POWER_POOLS_LINE,
    'ScriptPools': b'ScriptPools: rule 59 revision 1 installed {4096,0,0,0}; statements 4096, values 8192, compiled scripts 512',
    'ParticleScratch': b'ParticleScratch: rule 60 revision 1 installed {40,0,0,0}; eleven operations, clamp only',
}
WAVE3_MARKERS_ARE_PLACEHOLDERS = False


def wave3_limits(mode) -> dict:
    """[Limits] keys of the --limits-wave3 level `mode` ('off' / None -> {}; 'on' -> the nine rows; 'all' -> + the late
    rows)."""
    mode = (mode or 'off').lower()
    if mode == 'off':
        return {}
    if mode == 'on':
        return dict(LIMITS_WAVE3)
    if mode == 'all':
        return {**LIMITS_WAVE3, **LIMITS_WAVE3_LATE}
    raise ValueError(f'--limits-wave3 {mode!r}: choose from {LIMITS_WAVE3_MODES}')


def limits_in_use(mode=None) -> dict:
    """the [Limits] section a build asks the DLL for: LIMITS, with the wave-3 rows over it at level `mode`. The validators
    read their capacities from this (a key a build does not write is the game's own value)."""
    return {**LIMITS, **wave3_limits(mode)}

# xml2-fix 1.9.0 (limits wave 2, its docs/limits-wave2.md "Step 8") [Limits] SaveLayout=w2: the W2 native save layout
# (item definitions / instances / world slots / objectives 1024, enhancement and attached records 4096, 8 zone
# records, talent pools 256 with multiplier 200, 8191 zone-string names). One key selects the whole layout and every
# engine raise that goes with it; none of them is separately selectable. It is OPT-IN (builder option --save-layout w2,
# build record 'save_layout'): W2 is Legends Classic 0.4.2 and is in no candidate yet, so a default build writes no
# SaveLayout key and its ini is byte-identical to before. The DLL accepts the key only with [Save] Format=lc,
# [Limits] EntityCapacity=1 and ItemEnhancements absent or 4096 (W2 owns 4096; any other value is refused at
# start-up), so the builder writes the four keys together and refuses any key set that breaks the table
# (check_save_layout_keys); a DLL that does not recognize the key is refused too (check_save_layout_dll), never
# silently written to. An empty SaveLayout= is never written.
SAVE_LAYOUT_KEY = 'SaveLayout'
SAVE_LAYOUT_W2 = 'w2'
SAVE_LAYOUT_RETAIL = 'retail'                 # the builder option's default: no key, the configured baseline
SAVE_LAYOUTS = (SAVE_LAYOUT_RETAIL, SAVE_LAYOUT_W2)
W2_ITEM_ENHANCEMENTS = '4096'                 # the W2 layout's item enhancement records (limits-wave2 section 2, E3)


def limits_for(save_layout=None) -> dict:
    """[Limits] a build needs: LIMITS, plus under save_layout 'w2' the pair SaveLayout=w2 / ItemEnhancements=4096
    (EntityCapacity=1 is in LIMITS already; [Save] Format=lc is port_keys' / save_keys' job). Any other value
    ('retail', None) is the baseline: LIMITS unchanged."""
    limits = dict(LIMITS)
    if save_layout is None or save_layout == SAVE_LAYOUT_RETAIL:
        return limits
    if save_layout != SAVE_LAYOUT_W2:
        raise ValueError(f'unknown save layout {save_layout!r} (expected one of {", ".join(SAVE_LAYOUTS)})')
    out = {}
    for key, value in limits.items():
        out[key] = W2_ITEM_ENHANCEMENTS if key == 'ItemEnhancements' else value
        if key == 'EntityCapacity':
            out[SAVE_LAYOUT_KEY] = SAVE_LAYOUT_W2
    return out

# xml2-fix 1.3.1 [Game] GeometrySharingBlendIndices (SPEC 44, issue #11): XMen2.exe's geometry sharing reuses one
# skinned mesh for another when positions and weights match although their packed blend indices differ; XML1's
# enemies share outlines that way across skins and drew them with the wrong bones (large black spikes on the HAARP
# officer, the GRSO nullifier and flamethrower). '1' makes the fix compare the indices too. Off in xml2-fix unless
# set (stock XML2 is not known to need it), so every XML1 build asks for it.
GEOMETRY_SHARING_BLEND_INDICES = '1'

# xml2-fix 1.8.0-beta.2 [Engine] ModelPools (its docs/model-pools.md): every model the game shows takes a handle and
# components from fixed pools (handles 692, IGB 400, actors 32, particle clouds 40, ...); a full pool silently refuses
# the model - and the spawn that needs it (the beta 1 crash: a team-combo head the full IGB pool refused). x4 raises
# them all (handles 4096, IGB 2048, actors 128, clouds 128). Online it is gameplay-agreement rule 28 (ModelPools): a
# 1.8.0-beta.1 peer, which has no rule 28, and a beta.2 port build refuse each other at join by name.
MODEL_POOLS = 'x4'
# xml2-fix 1.9.0-beta.1 [Engine] ModelHandles (limits wave 1): the model handles and transforms past ModelPools'
# profile, sized for the 1024 IGB records above (8192; part of rule 28's values online).
MODEL_HANDLES = '8192'
# xml2-fix 1.8.0-beta.2 [Game] ComboPopupGuard: a team-combo popup that lacks a hero's head is hidden instead of
# crashing (XMen2.exe+0x1a6848). On by default in the DLL; written so the builder's DLL check (check_release_dll)
# refuses a 1.8.0-beta.1 DLL without it. Display only, no agreement rule.
COMBO_POPUP_GUARD = '1'

# xml2-fix 1.3.2 [Game] CharacterLadderPaths (SPEC 46, issue #32): the sewer and Arbiter ladder descents are driven by
# two generated native motion paths (ladder_motion), but XMen2.exe never schedules the generic path evaluator for
# characters. '1' makes the fix evaluate those two paths with the native movement timer; ordinary character
# movement is unchanged. Off in xml2-fix unless set, so every XML1 build asks for it.
CHARACTER_LADDER_PATHS = '1'

# xml2-fix 1.3.2 [Game] ObjectiveDescriptions (SPEC 47, issue #8): XML1's objectives carry an updatedescription, the
# journal text once the objective is complete, which XMen2.exe's parser ignores; the build keeps the attribute in the
# missions and '1' makes the fix show it in both journal renderers while the objective's completion bit is set (saved
# objective records unchanged). Off in xml2-fix unless set, so every XML1 build asks for it.
OBJECTIVE_DESCRIPTIONS = '1'

# xml2-fix 1.3.2 [Game] BreakRule (SPEC 63, issue #51's follow-up): XMen2.exe keeps an object's
# structure in 0..2 and caps a melee hit's level at 1, so the converted structure (x1schema.convert_physics: XML1's
# 2-9 -> 1) lets a plain punch break walls XML1 kept for powers. 'xml1' makes the fix compare XML1's hit level
# (authored level + Might + the damageLevel affecter) with the xml1structure the build's entity definitions carry.
# Off in xml2-fix unless set; a fix without the feature (before 1.3.2) ignores the key and the attribute, and objects
# break as they do without it. Written for every XML1 build.
BREAK_RULE = 'xml1'

# xml2-fix [Game] LiftRule (gameplay rule 38, owner decision 2026-10-25): XMen2.exe never lifts its heaviness 3, into
# which x1schema's rescale folds XML1's 4 (Might rank 3 lifts it) and 5 (never). 'xml1' makes the fix lift the
# objects that carry xml1heaviness (x1schema.XML1_HEAVINESS_ATTR) by XML1's rule; every other object and every
# heaviness byte stay the game's. A fix without the rule ignores the key and the attribute. Written for every XML1
# build.
LIFT_RULE = 'xml1'

# xml2-fix 1.9.0-beta.1 [Game] Xml1WallCling (gameplay rule 39, docs/xml1-cling.md): XML1's ch_clingwalldecide /
# ch_clingwallbackflip, the acrobat moveset's wall cling and back-flip (acrobatics 2). The converted moveset_acrobat
# carries both moves already (XML2 shipped the data with no handler, so they ran as %default%); 'xml1' gives them
# the first game's handlers. A fix without the rule ignores the key.
WALL_CLING = 'xml1'

# xml2-fix 1.9.0-beta.1 shared combat handlers (gameplay rule 42, docs/shared-handler-rules.md): seven callbacks every
# moveset shares - ice/lava skating, Nightcrawler's teleport landing, the popup / air spin decision and landing, the
# charge (Advanced Sentinel), Nightcrawler's buddy-teleport targets and Gambit's object charge - behave as XML1's.
# The fix applies them to the whole installation, so they belong to an XML1 build's profile. One mask online.
# xml2-fix 1.9.0-beta.1 shared handlers wave C (gameplay rule 46, docs/shared-handler-c-rules.md): the jump attack's and
# the flying charge's damage from values.xmlb's L3 row, Colossus's charge, Beast's bounce and the fastball contact, the
# idle/bored choice, the animation rate's scale and phase and Nightcrawler's teleport visibility behave as XML1's.
# Whole-installation, so an XML1 build's profile; one mask online. Phoenix's telekinesis and the guard decide are rule 46's
# bits 512 / 1024 (TK_GUARD below), written only with Xml1GrabCarry.
SHARED_HANDLERS_C = {'JumpAttackDamageRule': 'xml1', 'FlyChargeDamageRule': 'xml1', 'ColossusChargeRule': 'xml1',
                     'BeastBounceRule': 'xml1', 'FastballRule': 'xml1', 'IdleBoredRule': 'xml1', 'LocomotionScaleRule': 'xml1',
                     'AnimationPhaseRule': 'xml1', 'TeleportVisibilityRule': 'xml1'}
# xml2-fix 1.9.0-beta.1 rule 46 bits 512 / 1024 (beta8/tk-guard, docs/tk-guard.md): Phoenix's telekinesis (entry / update /
# input / cancel, XML1's candidate policy, damage and tk levels) and the guard decide (held use_button: allies, enemies and
# objects; the acrobat's wall lunge) behave as XML1's. Both need rule 45's installed grab lifecycle (the fix refuses them
# without it and closes online), so port_keys writes them only with Xml1GrabCarry=xml1; a rebuild without it drops them.
# Beta 8 (080h, owner decision): the telekinesis is in progress (beta 9), so TelekinesisRule is written only with
# --telekinesis xml1 (default off). Beta 8 (080i, Owen's hand test 10-26): with GuardDecideRule=xml1 a real Guard press
# (pad X / keyboard E) did nothing at all, so it is written only with --guard-decide xml1 (default off) and Guard is
# XML2's ch_guard_decide again (grabs and pickups through the grab talent characters adds). 0.5.0-beta.1 keeps it off
# (Owen's real-pad check of 082f, 10-28: GuardTrace showed native_grab=1 stunned=0 on every press - the 082d
# stunned-only rule refused the grab XML2's Guard makes and the refused press showed no block).
TELEKINESIS = {'TelekinesisRule': 'xml1'}
GUARD_DECIDE = {'GuardDecideRule': 'xml1'}
TK_GUARD = {**TELEKINESIS, **GUARD_DECIDE}
# xml2-fix 1.9.0-beta.1 [Game] Xml1FlyingCarry (beta 8 080h, docs/xml1-grab-carry.md): =0 keeps rule 45 revision 3
# without the flying carry (its five handlers and the descent admission 0x433e6c; rule values {1,23,0,0}); Juggernaut's
# grab, pickup/recovery, the charge collision, fix7 and XML1's flight upkeep stay. The flying carry is in progress
# (beta 9): written as 0 with Xml1GrabCarry=xml1 unless --flying-carry xml1 (the key absent = the DLL's default, on).
FLYING_CARRY_OFF = {'Xml1FlyingCarry': '0'}

# xml2-fix 1.9.0-beta.1 [Limits] ActorPools (E4 stage 1, gameplay rule 44, docs/actor-pools.md): the path, shadow and
# delayed-damage pools sized for 32 actors grow to 124. Written only with --actor-pools 124 until its live runs pass
# (beta 8 leaves it off: no S1-L1..L5 run yet).
ACTOR_POOLS = '124'

# xml2-fix [Limits] AnimEnums (gameplay rule 48, xml2-fix docs/anim-enums.md; SPEC 107): the animation enum table 210 ->
# 512 with XML1's 23 flying-carry / Juggernaut-grab enums at fixed IDs. Written with --anim-enums xml1 (the default
# since 0.4.1-beta.1; the build then also carries their clips, mappings and carry nodes; anim_enums.py).
ANIM_ENUMS = '512'
# Rule 49: the sound cache needs headroom once AnimEnums removes the 16-type animation cap.
CHAR_SOUNDS = '127'
MOTION_POOL = '22528'
RESIDENT_STATS = '320'
RESIDENT_STATS_MARKER = b'ResidentStats: rule 50 revision 1 installed {320,22,320,1}'
MOTION_POOL_MARKER = b'MotionPool: rule 51 revision 1 installed {22528,0,0,0}'
CHAR_SOUNDS_MARKER = b'CharSounds: rule 49 revision 1 installed {127,0,0,0}'

SHARED_HANDLERS = {'SkatingRule': 'xml1', 'TeleportLandingRule': 'xml1', 'PopupRule': 'xml1', 'PopupLandRule': 'xml1',
                   'ChargeRule': 'xml1', 'NightcrawlerRule': 'xml1', 'GambitRule': 'xml1'}

# xml2-fix [Game] PlacementCrush (SPEC 63.4, issue #79): XMen2.exe settles each object on the floor - at a zone's load
# and 0.5 s after any spawn in play (death drops, script props, debris) - and an object touching another there may "crush" it (a 1,000,000-damage hit; BreakRule=xml1 refuses most, but the hit's sound
# still plays): XML1's furniture authored overlapping (the dormitories' desk chair under a roll-top desk) gave two hit
# sounds from an empty room on entry. 'xml1' makes the fix refuse that touch while a settle runs; the first game has no settle at
# all. Other touches in play keep the game's own rule. A fix without the feature ignores the key.
PLACEMENT_CRUSH = 'xml1'

# XML1's ordinary impact against a non-physical target has zero damage.
# Requires the companion ObjectWorldImpact install (gameplay rule 17).
OBJECT_WORLD_IMPACT = 'xml1'

# xml2-fix [Game] DoubleHeal (SPEC 63.5, issue #82): XMen2.exe's restoreHealth / restoreEnergy (the packs' onactivate
# scripts) sometimes heal double and then play common/game/pickup_power_double, XML2's own darker recording; XML1's
# packs never double and its banks have no such sound. '0' makes the fix always take the single branch.
DOUBLE_HEAL = '0'

# xml2-fix [Game] RankCosts (SPEC 88, issue #35): X-Men Legends 1 charges a talent rank its <level cost> (2 for the
# 119 ranks that open a new form of a power; heroes.py keeps the attribute, V-H16 checks it) in the skills screen, its
# buyable/greyed test, the automatic spending, the respec and when levels are lost; XMen2.exe charges 1 for every rank.
# Off in xml2-fix unless set; a fix without the feature ignores the key (every rank costs 1). Co-op peers must agree
# (gameplay rule 5). Written for every XML1 build.
RANK_COSTS = '1'

# xml2-fix [Game] LevelSkillPoints (SPEC 88.1): X-Men Legends 1 gives 2 skill points for a level divisible by 5 and 1
# for any other (default.xbe 0xb1ca0; a level lost takes the same back); XMen2.exe gives 1 for every level. 'xml1' makes
# the fix give the first game's; a fix without the feature ignores the key. Gameplay rule 5 with RankCosts. Written for
# every XML1 build.
LEVEL_SKILL_POINTS = 'xml1'

# xml2-fix [Game] LevelStatPoints (SPEC 88.2): the same rule for the stat points on the port's scale - XML1's 1 a level
# (2 on a level divisible by 5) is 4 (8) here, as the heroes' stats are XML1's x STAT_SCALE (4) and XMen2.exe's 4 a
# level already is XML1's 1. 'xml1' makes the fix give 8 on every 5th level; a fix without the feature ignores the key.
LEVEL_STAT_POINTS = 'xml1'

# xml2-fix [Game] DeathRule (the 0.2.2 death threshold; xml2-fix docs/death-threshold.md, gameplay rule 9): XML1's
# damage function (default.xbe 0x92220) kills an entity whose health falls BELOW 1, XMen2.exe's (0x497e70) only at 0,
# so with XMen2.exe's float damage an enemy could sit alive on a fraction of a point, its death script and drops
# waiting for another hit. 'xml1' makes the fix draw XML1's line in the damage functions. Off in xml2-fix unless set;
# a fix without the feature ignores the key (entities die at 0, as before). Written for every XML1 build.
DEATH_RULE = 'xml1'

# xml2-fix [Game] NpcPowerRule (0.2.2 follow-up; xml2-fix docs/npc-power-rule.md; gameplay rule 16): XML1's power use
# and melee combos for computer-controlled characters. XMen2.exe never charges an AI character for its powers (the
# cost's AI test 0x4318e7 asks the controller, which says yes only after a queued command), re-runs the melee-range
# power decision every 0.3 s (0x518770) and has no energy test there; XML1 charges every NPC (default.xbe 0xcde90),
# decides every 2.0 s (0.5 s for a party hero) and needs half the energy (0xee260). Without it the NPC energy pool
# (SPEC 24.3, x1_npc_energy) never empties and XML1's enemies fire powers whenever aireusetime allows (SPEC 95).
# XMen2.exe also overrides the AI's combo level with npcstat `combolevel` (0 for XML1 entries: no combos) and skips the
# pause after a combo start; the rule restores XML1's levels, combos and pause too (no data: XML1's six combos are not
# among XMen2.exe's). Rule 16 revision 3 also restores XML1's AI visibility ray and query reservation/budget.
# Off in xml2-fix unless set; a fix without the feature ignores the key. Written for every XML1 build.
NPC_POWER_RULE = 'xml1'

# xml2-fix [Game] NpcSemiAuto + [NpcSemiAuto] Count / W1..Wn (XML2 Fix 1.8.0-beta.6, schema 3 rows since 1.8.0-beta.7;
# xml2-fix docs/npc-semi-auto.md; gameplay rule 16 revision 10): XML1's weapon brain for every gun NPC (the officer,
# MP5 and laser soldiers, nullifier / knockback officers with their warm-up, lightning and flamethrower commanders,
# the police pistol: one shot per recoil period or a continuous beam, no bursts or melee at range, the grenade held
# at full energy). XMen2.exe registers no ch_weapon_semi_auto handler, so its converted gunmen burst-fire and melee.
# The rows are the characters stage's source-derived contract (xml1build.semi_auto -> _build/semi_auto.json;
# `actor|recoil|range|burst|leader|warmup|flags`, 20 rows from the owner's XML1 data); fidelity is the goal, so every
# XML1 build with a contract writes them (like NpcPowerRule). No contract / no row = no keys (rule 16 stays
# {1,1,0,0}, the stock PC gunmen).
NPC_SEMI_AUTO = 'xml1'
NPC_SEMI_AUTO_MAX_ROWS = 64          # the native bound (xml2-fix npc_semi_auto; semi_auto.contract refuses more)

# XML1's stun flag lasts only while the accepted stun reaction owns it. The companion DLL's rule 18
# drops rejected party-hero stuns and clears interrupted stuns; NPC reactions and accepted durations stay native.
STUN_RULE = 'xml1'

# xml2-fix [Game] ForcedTeams (SPEC 19): '1' = the scripts of a --forced-teams seat build seat XML1's parties
# (xml2-fix forced_teams module), '0' = the functions exist but report off (team menu), 'off' = no key (nothing
# patched). Every xml2-fix call sits behind xml2fixFeature("forcedteams") (validate V14b), so with ForcedTeams=0, a
# missing key, an xml2-fix build without the module or no DLL at all, the same scripts open the team menu.
FORCED_TEAMS_VALUES = ('1', '0', 'off')

# the xml2-fix release a builder-made play build needs (every key above is in v1.2.0; v1.3.0: the SKILL pickup's
# addSkillPoints, the conversation hooks [Game] AutoAdvance / ReplyVoices / ReplyCursor - SPEC 32, 34; v1.3.1:
# [Limits] FightStyles - SPEC 43, [Game] GeometrySharingBlendIndices - SPEC 44; v1.3.2: [Game] CharacterLadderPaths -
# SPEC 46, [Game] ObjectiveDescriptions - SPEC 47, the STAT pickup's addStatPoints - SPEC 48,
# [Game] BreakRule - SPEC 63, [Limits] EffectCurves - SPEC 65, [Game] Xtract - SPEC 66; v1.4: [Save] Format and the LC save tables - SPEC 70, [Balance] - SPEC 69;
# v1.5: the 0.2.2 wave's [Game] keys - PlacementCrush, DoubleHeal, RankCosts, LevelSkillPoints, LevelStatPoints,
# Xml1Multipart, X1Leader, SoloMode, DeathRule, DangerRoomGate, RevivalCost, Xml1Turrets, PackAmount, DeathSwitchClear - and
# [Limits] ScriptFunctions; a 1.4 DLL silently ignores every one of them, so check_release_dll refuses it)
REQUIRED_XML2FIX = '1.10'
# The companion fix's prerelease a beta/rc builder needs (launcher-facing requires.xml2fix only): 0.3.0-beta.2 writes
# [Engine] ModelPools and [Game] ComboPopupGuard, first read by XML2 Fix 1.8.0-beta.2; 0.3.0-beta.3 writes [Online]
# TickRate, first read by 1.8.0-beta.3; 0.4.0-beta.5 writes [Game] ClassicHud / ClassicCodex (the classic look), first
# read by 1.8.0-beta.5; 0.4.0-beta.6 writes [Game] NpcSemiAuto / [NpcSemiAuto] (the officer's weapon brain, rule 16
# revision 10), first read by 1.8.0-beta.6, so its requirement is '>=1.8.0-beta.6' (SemVer: beta.6, beta.N > 6, every
# rc and the final 1.8.0 meet it; 1.8.0-beta.5 and older do not). 0.4.0-beta.7 writes schema 3 [NpcSemiAuto] rows (every
# gun family) and [Game] ClassicSpeakers, first read by 1.8.0-beta.7 (a beta.6 DLL refuses the schema 3 rows: weapon
# brain off, host/join closed), so its requirement is '>=1.8.0-beta.7'. 0.4.1 (beta 8) required 1.9 / beta.1. 0.5.0 writes
# the 0.4.2 line's keys by default ([Limits] SaveLayout=w2, [Game] Xml1Economy, the wave 3 limits, TelekinesisRule,
# GuardDecideRule and the flying carry), first read together by XML2 Fix 1.10.0-beta.1: '>=1.10.0-beta.1' / '>=1.10'.
REQUIRED_XML2FIX_PRERELEASE = 'beta.1'


def required_xml2fix(builder_version: str) -> str:
    """Launcher-facing requirement shared by the release manifest and generated build stamp.

    Beta/rc builders accept the companion fix's prereleases from REQUIRED_XML2FIX_PRERELEASE on
    as well as the final release. Keep the stable requirement's original spelling. DLL capability
    checks below remain independent of this SemVer metadata: beta fixes have the same numeric
    VERSIONINFO (check_release_dll tells them apart by the keys they read).
    """
    if builder_version == RI.PRIVATE_CANDIDATE.release or re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+-(?:beta|rc)\.[0-9]+', builder_version):
        parts = REQUIRED_XML2FIX.split('.')
        base = '.'.join(parts + ['0'] * (3 - len(parts)))
        return '>=' + base + '-' + (REQUIRED_XML2FIX_PRERELEASE or '0')
    return '>=' + REQUIRED_XML2FIX


# xml2-fix [Balance] (xml1build.balance; SPEC 69): the first game's combat numbers for a
# balance build - one whose styles carry the power-attack marker (report.json build.balance 'xml1'). HeroStatScale
# is heroes.STAT_SCALE, what the build multiplied XML1's hero stats by; NativeStatHeroes the two herostat entries
# heroes.rescale_x1_hero_stats leaves at XML1's numbers (stats beyond XML1's 1..10 hero scale). Every build of a
# release since 0.2.0 is a balance build, so lobbies never mix with the port's without [Balance] (GameVersion).
BALANCE_HERO_STAT_SCALE = '4'
BALANCE_NATIVE_STAT_HEROES = 'ProfXAstral,ProfXGladiator'

# xml2-fix [Game] PackAmount (0.2.2; port gameplay rule 13): XML1's health / energy packs restore a quarter of the
# maximum - default.xbe's restoreHealth / restoreEnergy (0x9bd50 / 0x9bcb0) turn the items' -1 into (int)(max * 0.25)
# (0x3c83b0) - where XMen2.exe's (0x4a2dd0 / 0x4a2c20) take 0.33. Both games' HEALTH_ITEM / ENERGY_ITEM call the same
# scripts with -1 and say "25%", so the amount is not data: the fix writes 0.25 into the two single-amount stores.
PACK_AMOUNT = 'xml1'

# xml2-fix [Game] X1Leader (issue #15; gameplay rule 7): XML1's stats `leader` bit - heroes don't flinch from a leader's
# projectile, and a leader's corpse follows the first game's drop rule (4 drops, a forced health / energy / Xtreme
# pick). XMen2.exe keys both to its own x3-variant flag; the fix treats the actors characters.py lists in
# Data/x1leader.txt (V54) the same way. Off in xml2-fix unless set (the sidecar alone does nothing); a fix without the
# feature ignores the key. Written for every XML1 build.
X1_LEADER = '1'

# [Online] FastTransfer=1: the saved-campaign transfer as data/zero-run records with a pool-bounded window (seconds
# instead of minutes; xml2-fix docs/online-campaign-transfer.md). A gameplay-agreement rule: every co-op PC must use
# it, and a peer without it is refused by name. Written for every port build.
FAST_TRANSFER = '1'

# [Online] ReceiveValidation=1: reject malformed stock network messages before their handlers run. This is local
# receive-side hardening: it changes no wire format and needs no gameplay-agreement rule, so older peers still
# interoperate. Written for every port build.
RECEIVE_VALIDATION = '1'

# [Online] JoinInProgress=1 (XML2 Fix 1.8, gameplay agreement rule 26): drop-in co-op - the host may start alone, a
# player joins a running game and is brought in at the next level change, solo story segments keep the other players
# watching, and the host keeps hosting when the last player leaves. Every co-op PC must have it (a peer without it is
# refused by name). Written for every port build (0.4.0: drop-in on by default).
JOIN_IN_PROGRESS = '1'

# [Online] TickRate=60 (XML2 Fix 1.8.0-beta.3, gameplay agreement rule 29): online sessions run at 60 frames a second
# like single-player instead of the game's own 30 (CClient::frame's online 1/30 s frame). Lockstep runs every PC's
# frames together, so every co-op PC must have the same rate: a 60 and a 30 PC refuse each other at join by name.
# '30' is the fallback for slow PCs (then everyone in that session sets 30). Written for every port build.
TICK_RATE = '60'

# [Game] OnlineConversations=lockstep (XML2 Fix 1.7, gameplay agreement rule 27 revision 1): online, a conversation line
# that goes on by itself does so |timeDelay| s of game time after it was drawn on every PC, and a chosen reply's voice is
# cut; single-player is unchanged. Absent = the 1.6.0 decision by this PC's voice end, which put co-op peers one random
# draw apart and dropped the session.
ONLINE_CONVERSATIONS = 'lockstep'

# [Online] Broker / BrokerPin: the project broker the launcher's "Host online" / "Join by code" use (0.4.0, the
# launcher <-> XML2 Fix contract: the BUILDER writes them as defaults, the launcher never writes or removes them).
# THIS IS THE ONE PLACE TO SET THEM. The deployed project broker uses pinned self-signed TLS; empty = neither key is
# written and neither is port-owned, so a tester's hand-set Broker/BrokerPin survives a rebuild. When deployed:
# PROJECT_BROKER = '<public DNS name or IPv4>[:port]' (port 10020 when omitted) and, for the self-signed TLS option,
# PROJECT_BROKER_PIN = the 64-hex SPKI SHA-256 from the deploy kit's secrets/broker/broker-spki-sha256.txt
# (leave the pin empty with a publicly trusted certificate).
PROJECT_BROKER = 'broker.aethyrion.org:10020'
PROJECT_BROKER_PIN = 'ac569104f671775703f3e36a8109519f4e219fb1e8bc68aaa77793cfb3dbad09'

# [Game] PersonalItemPicture=window (XML2 Fix 1.7.1): a bedroom item's picture is drawn as the first game's 256x128 picture
# window over the menu panels (SPEC 56), so the builder ships the first game's 512x256 pictures as they are. Absent = the
# engine stretches the picture over the whole screen (an oversized picture hiding the panels).
PERSONAL_ITEM_PICTURE = 'window'

# xml2-fix [Game] WorldBackfaces=xml1 + [WorldBackfaces] ZoneCount / Z1..Zn (XML2 Fix 1.8.0-beta.7, gameplay rule 30
# revision 2; xml2-fix docs/world-backfaces.md): XML1's one-sided level collision for movement in the XML1 levels ONLY
# (owner decision 2026-10-25). The list is the zones the zones stage converted (_build/zones_detail.json 'converted');
# the XML2-origin maps an install still carries (tutorial, XML2 act1-5, briefings, Danger Room, versus) keep XML2's
# two-sided collision. Without a list the key is not written at all (the DLL refuses the rule without one).
WORLD_BACKFACES = 'xml1'
WORLD_BACKFACES_MAX_ZONES = 512
_ZONE_PATH = re.compile(r'^[a-z0-9_.\-]+(/[a-z0-9_.\-]+)*$')

# every key the port may write (the builder drops the ones a build does not need); the launcher owns the rest
PORT_OWNED = {'Game': ('NewGameTeam', 'ResetUnlocks', 'SaveFolder', 'ForcedTeams', 'PostgameScript', 'WindowTitle',
                        'EndHeroUnlock', 'MainMenuItems', 'DangerRoomGate', 'ClassicMainBackdrop', 'ClassicMainPanelBounds', 'NewGamePlus', 'ReviewStats', 'Xtract', 'XtractionShop', 'RevivalCost', 'XPCurve',
                       'GeometrySharingBlendIndices', 'CharacterLadderPaths', 'ObjectiveDescriptions',
                       'BreakRule', 'LiftRule', 'Xml1GrabCarry', 'Xml1FlyingCarry', 'Xml1RogueDecide', 'Xml1Economy', 'Xml1WallCling', *SHARED_HANDLERS, *SHARED_HANDLERS_C, *TK_GUARD, 'PlacementCrush', 'ObjectWorldImpact', 'DoubleHeal', 'DeathRule', 'NpcPowerRule', 'StunRule', 'DangerRoomParty', 'DangerRoomHealthBars', 'ResistanceDisplay', 'BoxHarmOrigin', 'HarmSingleChain', 'HarmLoopStartup', 'ConfirmationRelease',
                       'OnlineConversations', 'PersonalItemPicture', 'ComboPopupGuard', 'ClassicHud', 'ClassicHudPilot', 'ClassicCodex', 'ClassicObjectives', 'NpcSemiAuto', 'ClassicSpeakers', 'WorldBackfaces',
                       'ExplosiveFirstHit', 'PackAmount', 'SoloMode', 'X1Leader', 'DeathSwitchClear', 'RankCosts', 'LevelSkillPoints', 'LevelStatPoints', 'Xml1Multipart',
                       'Xml1MasterMold', 'Xml1MoldStage', 'Xml1Turrets', 'Xml1LockOnEffects', 'Xml1LockOnAim', 'Xml1Bosses'),
              'Limits': ('ActorSlots', 'ResourceNames', 'ItemEnhancements', 'FightStyles', 'EffectCurves', 'MoveTriggers', 'EntityCapacity',
                         'ScriptFunctions', 'IGBCache', 'ActorPools', 'AnimEnums', 'CharSounds', 'MotionPool', 'ResidentStats',
                         *(k for k in LIMITS_WAVE3 if k != 'FightStyles'), *LIMITS_WAVE3_LATE, SAVE_LAYOUT_KEY),
              'Online': ('GameVersion', 'ContentFingerprint', 'FastTransfer', 'ReceiveValidation', 'JoinInProgress', 'TickRate'),
              'Save': ('Format',),
              'Engine': ('ModelPools', 'ModelHandles'),
              'Xml1Turrets': ('Count',) + tuple(f'T{i}' for i in range(1, 33)),
              'NpcSemiAuto': ('Count',) + tuple(f'W{i}' for i in range(1, NPC_SEMI_AUTO_MAX_ROWS + 1)),
              'WorldBackfaces': ('ZoneCount',) + tuple(f'Z{i}' for i in range(1, WORLD_BACKFACES_MAX_ZONES + 1))}


def broker_keys() -> dict:
    """[Online] Broker / BrokerPin defaults: {} until PROJECT_BROKER is set (see above); the pin only with a broker."""
    broker = PROJECT_BROKER.strip()
    if not broker:
        return {}
    keys = {'Broker': broker}
    pin = PROJECT_BROKER_PIN.strip().lower()
    if pin:
        if len(pin) != 64 or any(c not in '0123456789abcdef' for c in pin):
            raise ValueError('PROJECT_BROKER_PIN must be 64 hexadecimal characters (the SPKI SHA-256)')
        keys['BrokerPin'] = pin
    return keys


def port_owned() -> dict:
    """PORT_OWNED, and with the balance switch on (xml1build.balance) the [Balance] section too. With the switch
    off the port does not own that section at all: nothing of it is written or dropped. The broker keys are owned
    only once the project broker is set (broker_keys)."""
    owned = dict(PORT_OWNED)
    if broker_keys():
        owned['Online'] = PORT_OWNED['Online'] + ('Broker', 'BrokerPin')
    if BAL.enabled():
        owned['Balance'] = tuple(BAL.BALANCE_KEYS) + BAL.TUNING_KEYS
    return owned


# ------------------------------------------------------------------------------------------------ reading the build
def _xmlb_decode(data):
    import xmlb                                       # tools/xmlb.py (tools/ is on sys.path with this package)
    return xmlb.decode(data)


def _read_menu(out, parts):
    p = Path(out).joinpath(*parts)
    if not p.is_file():
        return None
    try:
        return _xmlb_decode(p.read_bytes())
    except (ValueError, OSError, IndexError):
        return None


def menu_items_for(root, eighth=False):
    """The MainMenuItems value when the menu tree `root` is the XML1 front end's main menu (a MAIN_MENU whose shown
    text items are buttonN: the first MAIN_MENU_MOUSE_SLOTS with a usecmd, then the one without, Quit; with `eighth`
    (a DLL that takes 8 names) a 7th usecmd item follows Quit), else None."""
    if root is None or root.get('type') != 'MAIN_MENU':
        return None
    shown = [it for it in root.iter('item') if it.get('text') and not it.get('type')
             and (it.get('hide') or '').lower() != 'true' and (it.get('enabled') or '').lower() != 'false'
             and (it.get('neverfocus') or '').lower() != 'true']
    if not shown or any(not re.fullmatch(r'button\d+', it.get('name') or '') for it in shown):
        return None
    mouse = [it.get('name') for it in shown if it.get('usecmd')][:MAIN_MENU_MOUSE_SLOTS]
    quit_ = [it.get('name') for it in shown if not it.get('usecmd')]
    if len(mouse) != MAIN_MENU_MOUSE_SLOTS or len(quit_) != 1:
        return None
    extra = [it.get('name') for it in shown if it.get('usecmd')][MAIN_MENU_MOUSE_SLOTS:MAIN_MENU_MOUSE_SLOTS + 1]
    return ','.join(mouse + quit_ + (extra if eighth else []))


def build_menu_items(out, eighth=False):
    """MainMenuItems when the build's UI/menus/main.XMLB is the XML1 front end's main menu (--frontend xml1), else
    None (--frontend xml2 keeps XML2's menu, whose names XMen2.exe already knows)."""
    return menu_items_for(_read_menu(out, MAIN_MENU_FILE), eighth)


def review_stats_for(root):
    """REVIEW_STATS when the menu tree `root` is a REVIEW_PATHS_MENU without the Stats tab's label (the XML1 front
    end's review menu), else None (XML2's menu, or no review menu)."""
    if root is None or root.get('type') != 'REVIEW_PATHS_MENU':
        return None
    names = {it.get('name') for it in root.iter('item')}
    return REVIEW_STATS if REVIEW_STATS_LABEL not in names and 'option01_text' in names else None


def build_review_stats(out):
    """REVIEW_STATS when the build's UI/menus/review.XMLB is the XML1 front end's (no Stats tab), else None."""
    return review_stats_for(_read_menu(out, REVIEW_MENU_FILE))


def build_record(out) -> dict | None:
    """the 'build' block of <out>/_build/report.json, or None when <out> is no build_xml1 / builder build."""
    p = Path(out).joinpath(*BUILD_REPORT)
    if not p.is_file():
        return None
    try:
        b = json.loads(p.read_text(encoding='utf-8')).get('build')
    except (OSError, ValueError, AttributeError):
        return {}
    return b if isinstance(b, dict) else {}


def build_xp_curve(out):
    """XP_CURVE when <out> is a build_xml1.py build (XML1's XP amounts) made for it (report.json build.xp_curve 'xml1';
    a build from before the option carried no key and XML1's objective XP: XP_CURVE too), else None."""
    b = build_record(out)
    if b is None:
        return None
    chosen = str(b.get('xp_curve') or XP_CURVE).lower()
    return XP_CURVE if chosen == XP_CURVE else None


def build_balance(out):
    """True when <out> is a balance build: made with xml1build.balance's switch on (report.json build.balance)."""
    b = build_record(out) or {}
    return BAL.enabled() and str(b.get(BAL.REPORT_KEY) or '').lower() == BAL.REPORT_ON


def balance_keys(out=None) -> dict:
    """the [Balance] keys of a balance build: the first game's numbers."""
    keys = dict(BAL.BALANCE_KEYS)
    keys.update(HeroStatScale=BALANCE_HERO_STAT_SCALE, NativeStatHeroes=BALANCE_NATIVE_STAT_HEROES)
    if out is not None:
        from . import melee_weapons as MW
        path = Path(out, 'Data', 'npcstat.engb')
        if path.is_file():
            value = MW.ini_value(_xmlb_decode(path.read_bytes()))
            if value:
                keys[MW.INI_KEY] = value
    return keys


def build_postgame(out):
    """POSTGAME_SCRIPT when the build wrote XML1's postgame script (an XML1 build), else None."""
    return POSTGAME_SCRIPT if Path(out, 'Scripts', *POSTGAME_SCRIPT.split('/')).with_suffix('.py').is_file() else None


def build_forced_teams(out):
    """'1' for a --forced-teams seat build (the default; a build without the report counts as one), None for menu."""
    b = build_record(out) or {}
    return '1' if str(b.get('forced_teams') or 'seat').lower() == 'seat' else None


def mold_stage_binding(layout, width=None):
    """Native-controller binding for the effective packed mission stage."""
    if not isinstance(layout, dict) or layout.get('kind') != 'pack':
        return None
    flag, first, stored = (layout.get(key) for key in ('gamevar', 'first_bit', 'nbits'))
    width = stored if width is None else width
    if not isinstance(flag, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,32}', flag):
        return None
    if any(type(value) is not int for value in (first, stored, width)):
        return None
    if not (1 <= width <= stored <= 32 and 1 <= first <= 33 - stored):
        return None
    return f'{flag}:{first}:{width}'


def build_lockon_effects(out):
    from .lockon_effects import keys
    return keys(out)


def build_mold_controller(out):
    """Only a builder-generated, supported script contract opts into the DLL."""
    try:
        data = json.loads(Path(out, '_build/scripts_detail.json').read_text(encoding='utf-8'))
        contract = data.get('mold_controller', {})
        revision = contract.get('revision')
        binding = mold_stage_binding(contract.get('stage')) if type(revision) is int and revision == 1 else None
    except (OSError, ValueError, AttributeError, TypeError):
        return {}
    return dict(Xml1MasterMold='1', Xml1MoldStage=binding) if binding else {}


# XML1 boss brains (xml2-fix [Game] Xml1Bosses, gameplay rule 40, the shared boss dispatcher): each boss the DLL can run,
# with the converted zones it binds to (any one suffices) and the instance names it binds by. A boss is listed only when the build carries
# that zone with every one of those names (a missing or renamed instance would leave its controller idle while rule 40
# says it is on).
BOSS_BINDINGS = (('dopples', ('Maps/astral/ast3/colosseum.XMLB',), ('evilwolverine', 'evilcolossus', 'eviljean', 'evilcyc')),
                 ('avalanche', ('Maps/mount/mount/mount2.XMLB', 'Maps/astral/ast3/astral3_4.XMLB'), ('avalanche',)),
                 ('pyro', ('Maps/astral/ast3/astral3_3.XMLB',), ('pyro',)),
                 ('mystique', ('Maps/nyc/alison/nyc1_1_2b.XMLB', 'Maps/mansion/dr_mag2/mag_nyc3.XMLB',
                              'Maps/astroid_m/visit1/asteroid2_1.XMLB'), ('mystique',)),
                 ('shadowking', ('Maps/astral/savepx/final_astral.XMLB',), ('shadowking', 'shadowking2')),
                 ('marrow', ('Maps/sewers/hub/sewers1_2_4.XMLB',), ('marrow',)),
                 ('magneto', ('Maps/astroid_m/visit1/asteroid2_1.XMLB',), ('magneto',)),
                 ('blob', ('Maps/nyc/alison/nyc1_1_3.XMLB', 'Maps/mansion/dr_mag2/mag_nyc4.XMLB',
                           'Maps/astral/ast3/astral3_5.XMLB'), ('blob',)))
BOSS_IMPLEMENTATIONS = {'marrow': 'native'}  # request agreement/signature verification, never a replacement tick
BOSS_SCRIPT_CONTRACTS = {'shadowking': ('astral/savepx/sk1pain', 'astral/savepx/dropshield'),
                         'magneto': tuple(f'asteroid_m/stage{i}' for i in range(2, 6))}


def boss_instance_names(root):
    """Shipped bosses are named spawns; waypoint names, references and substrings cannot bind an actor."""
    return {e.get('monster_name') for e in root.iter('entity')
            if e.get('classname', '').lower() == 'monsterspawnerent' and e.get('monster_name')}


def source_bosses(ctx):
    """Plan script substitutes from the same zone/name contract the finished-build INI checks."""
    cache_key = 'boss_controller_plan'
    if cache_key not in ctx.shared:
        selected = ctx.shared.get('selected_modules', getattr(getattr(ctx, 'args', None), 'only', None))
        if selected is not None and 'zones' not in selected:
            # A scripts-only rebuild may carry maps from a previous build, but must not assume new maps will appear.
            ctx.shared[cache_key] = frozenset(build_bosses(ctx.out, check_scripts=False).get('Xml1Bosses', '').split(',')) - {''}
            return ctx.shared[cache_key]
        zones_built = set(ctx.x1_zones())
        names = set()
        for name, zones, instances in BOSS_BINDINGS:
            for zone in zones:
                source = zone[5:-5].lower()
                if source not in zones_built:
                    continue
                root = None
                for ext in ('.eng', '.xml'):
                    try:
                        root = ctx.read_x1_xml(f'maps/{source}{ext}')
                    except KeyError:
                        continue
                    if root is not None:
                        break
                if root is not None and set(instances) <= boss_instance_names(root):
                    names.add(name)
                    break
        if selected is not None and 'scripts' not in selected and not boss_scripts_ready(ctx.out, 'magneto'):
            names.discard('magneto')
        ctx.shared[cache_key] = frozenset(names)
    return ctx.shared[cache_key]


def boss_scripts_ready(out, name):
    """Check generated shield scripts independently of maps for bounded partial rebuilds."""
    if name not in BOSS_SCRIPT_CONTRACTS:
        return True
    try:
        scripts = [Path(out, 'Scripts', script + '.py').read_text(encoding='latin-1')
                   for script in BOSS_SCRIPT_CONTRACTS[name]]
    except OSError:
        return False
    if any(re.search(r'\bsetInvulnerable\s*\(', text, re.I) for text in scripts):
        return False
    return name != 'magneto' or all(
        re.search(r'setPatternSequence\s*\(\s*[\'"]magneto[\'"]\s*,\s*[\'"]mag' + str(stage) + r'[\'"]\s*\)', text)
        for stage, text in zip(range(2, 6), scripts))


def build_bosses(out, *, check_scripts=True) -> dict:
    """{'Xml1Bosses': 'name,...'} for the bosses whose zone and instances the finished build carries; {} for none."""
    import xmlb
    names = []
    for name, zones, instances in BOSS_BINDINGS:
        if check_scripts and not boss_scripts_ready(out, name):
            continue
        for zone in zones:
            try:
                root = xmlb.decode(Path(out, zone).read_bytes())
            except (OSError, ValueError, IndexError, KeyError, RecursionError, struct.error):
                continue
            if set(instances) <= boss_instance_names(root):
                if name == 'magneto':
                    # A map-only rebuild can still carry SPEC 36's hard protection.
                    if any(re.search(r'setInvulnerable\s*\(', el.get('actscript', ''), re.I)
                           for el in root.iter('entity') if el.get('name', '').lower() == 'shieldup'):
                        continue
                names.append(name)
                break
    return {'Xml1Bosses': ','.join(names)} if names else {}


def build_turrets(out) -> dict:
    """{'Game': {'Xml1Turrets': '1'}, 'Xml1Turrets': {'Count': n, 'T1': ...}} from the builder's turret contract
    (xml1build.turrets -> _build/turrets.json); {} without a valid one (the turrets stay inert physents)."""
    from . import turrets as TU
    try:
        data = json.loads(Path(out, '_build/turrets.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if TU.validate_contract(data) or not data.get('placements'):
        return {}
    section = {'Count': str(len(data['placements']))}
    section.update({f'T{i}': line for i, line in enumerate(data['placements'], 1)})
    return {'Game': {'Xml1Turrets': '1'}, 'Xml1Turrets': section}


def build_semi_auto(out) -> dict:
    """{'Game': {'NpcPowerRule': 'xml1', 'NpcSemiAuto': 'xml1'}, 'NpcSemiAuto': {'Count': n, 'W1': ...}} from the
    characters stage's weapon-brain contract (xml1build.semi_auto -> _build/semi_auto.json); {} without a valid one
    with at least one row (the officers keep the stock PC weapon AI)."""
    from . import semi_auto as SA
    try:
        data = json.loads(Path(out, '_build', SA.CONTRACT_FILE).read_text(encoding='utf-8'))
        sections = SA.ini_sections(data)
    except (OSError, ValueError, AttributeError, TypeError):
        return {}
    sections['Game']['NpcSemiAuto'] = NPC_SEMI_AUTO
    return sections


def build_world_backfaces(out) -> dict:
    """{'ZoneCount': n, 'Z1': zone, ...}: the XML1 zones this build converted (sorted, lower case, '/' separated), the
    zones xml2-fix's WorldBackfaces applies to; {} without a usable list (no zones stage output, an empty or oversized
    list, or a path the DLL would refuse), and then the build writes no WorldBackfaces key."""
    try:
        data = json.loads(Path(out, '_build', 'zones_detail.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    names = data.get('converted') if isinstance(data, dict) else None
    if not isinstance(names, list):
        return {}
    zones = sorted({str(z).strip().replace('\\', '/').lower() for z in names if str(z).strip()})
    if not zones or len(zones) > WORLD_BACKFACES_MAX_ZONES or not all(len(z) < 64 and '..' not in z and _ZONE_PATH.match(z) for z in zones):
        return {}
    section = {'ZoneCount': str(len(zones))}
    section.update({f'Z{i}': z for i, z in enumerate(zones, 1)})
    return section


def game_keys(*, xml1_opening=True, save_folder=None, forced_teams='1', add_hero=False, join_hero=True, postgame=None,
              port_identity=False, main_menu_items=None, new_game_plus=None, review_stats=None, xtract=None,
              xp_curve=None) -> dict:
    """the [Game] keys, in the order tools/harness.py always wrote them (a dict: insertion order)."""
    game = {}
    if xml1_opening:
        # Course fallback defaults must name XML1 heroes; protected training
        # opponents must retain their target gauges without changing protection.
        game['DangerRoomParty'] = 'xml1'
        game['DangerRoomHealthBars'] = 'xml1'
        # Target subtitles must query the scoped damage modifiers used by the
        # converted original talents, rather than only the PC's resist_* rows.
        game['ResistanceDisplay'] = 'xml1'
        game['ClassicHud'] = 'xml1'
        game['ClassicCodex'] = '1'
        # The PDA's Objectives page as in the first game: visible objectives only, opening on the current one
        # (xml2-fix classic_objectives.cpp). Local presentation only, no agreement record.
        game['ClassicObjectives'] = '1'
        # XML1's speaker labels: a line the builder gave speakerlabel (scripts.SPEAKER_TOKEN_LABELS, the party Magma's
        # ex-%ALISON% lines) reads "Alison" with Magma's portrait and talk animation. Display only (an XML2 Fix that
        # does not know the key ignores it and the line reads "Magma"); it is in RELEASE_18_KEYS as 1.8.0-beta.7's
        # marker, because that DLL is also the first to read the schema 3 weapon-brain rows.
        game['ClassicSpeakers'] = '1'
        # [Game] WorldBackfaces (rule 30) is not a fixed key: port_keys writes it with the build's XML1 zone list.
        game['BoxHarmOrigin'] = 'xml1'
        game['HarmSingleChain'] = 'single'
        # Online, an auto-advancing conversation line goes on after the same game time on every PC (not when this PC's
        # voice ends): a line change draws from the shared random generator, so co-op dropped mid-conversation.
        # Gameplay agreement rule 27, requested only (XML2 Fix 1.7).
        game['OnlineConversations'] = ONLINE_CONVERSATIONS
        # The bedroom items' pictures are the first game's 512x256 art, drawn in its 256x128 window (SPEC 56).
        game['PersonalItemPicture'] = PERSONAL_ITEM_PICTURE
        game['ComboPopupGuard'] = COMBO_POPUP_GUARD
        # XML1's opening: startFirstMission seats Wolverine alone, resetgame unlocks nobody (xml2-fix new_game.cpp;
        # the build's New Game hook uses loadMapKeepTeam - build_xml1.py --newgame keepteam, the default)
        game.update(NewGameTeam='wolverine', ResetUnlocks='0')
        if save_folder:
            game['SaveFolder'] = save_folder
        game['GeometrySharingBlendIndices'] = GEOMETRY_SHARING_BLEND_INDICES
        game['CharacterLadderPaths'] = CHARACTER_LADDER_PATHS
        game['ObjectiveDescriptions'] = OBJECTIVE_DESCRIPTIONS
        game['BreakRule'] = BREAK_RULE
        game['LiftRule'] = LIFT_RULE
        game['Xml1WallCling'] = WALL_CLING
        game.update(SHARED_HANDLERS)
        game.update(SHARED_HANDLERS_C)
        game['PlacementCrush'] = PLACEMENT_CRUSH
        game['ObjectWorldImpact'] = OBJECT_WORLD_IMPACT
        game['DoubleHeal'] = DOUBLE_HEAL
        game['ExplosiveFirstHit'] = '1'
        game['RankCosts'] = RANK_COSTS
        game['LevelSkillPoints'] = LEVEL_SKILL_POINTS
        game['LevelStatPoints'] = LEVEL_STAT_POINTS
        # xml2-fix multipart.cpp: XML1's breakable parts (npcstat <Multipart> health / effects / linkToPower, kept
        # verbatim by characters.py; V52 checks them) - Juggernaut's helmet, the Sentinels' arms
        game['Xml1Multipart'] = '1'
        game['DeathRule'] = DEATH_RULE
        game['NpcPowerRule'] = NPC_POWER_RULE
        game['StunRule'] = STUN_RULE
        game['PackAmount'] = PACK_AMOUNT
        # XML1's solo mode (issue #5): setSoloMode in the solo boxes / bridge scripts acts only with this key
        game['SoloMode'] = '1'
        game['X1Leader'] = X1_LEADER
        game['DeathSwitchClear'] = '1'  # the hero handed a dead hero's controller stops its AI walk (XML1's hand-over)
    if forced_teams in ('0', '1'):
        game['ForcedTeams'] = forced_teams
    if add_hero:
        # xml2-fix addHero (the dormant 0x46c9f0) for the XML1 joins; experimental - T7 (team menu) stays the fallback
        game['AddHero'] = '1'
    if not join_hero:
        # xml2-fix joinHero (the joins' reload with the hero added, no team menu) is on with ForcedTeams=1 unless 0:
        # JoinHero=0 makes the joins fall back to the T7 team menu (SPEC 19.7)
        game['JoinHero'] = '0'
    if postgame:
        game['PostgameScript'] = postgame
    if port_identity:
        game.update(WindowTitle=PORT_WINDOW_TITLE, EndHeroUnlock=PORT_END_HERO_UNLOCK, ConfirmationRelease='1')
    if main_menu_items:
        game['MainMenuItems'] = main_menu_items
        game['DangerRoomGate'] = DANGER_ROOM_GATE_ITEM
        game['ClassicMainBackdrop'] = '1'
        game['ClassicMainPanelBounds'] = '1'
    if new_game_plus is not None:
        game['NewGamePlus'] = new_game_plus
    if review_stats is not None:
        game['ReviewStats'] = review_stats
    if xtract is not None:
        game['Xtract'] = xtract
        game['XtractionShop'] = '1'
        # xml2-fix [Game] RevivalCost (issue #63): the first game's 200 * G^2, G = min(5, highest roster level / 10 + 1)
        # (default.xbe 0xaf6b0 / 0x54150), not XMen2.exe's max(200, 2 * level^2); agreement rule 10 (revision 3, 1.8.0)
        game['RevivalCost'] = 'xml1'
    if xp_curve:
        game['XPCurve'] = xp_curve
    return game


def content_fingerprint(out):
    """the build's content fingerprint (64 hex; lcsave.lcfiles: SHA-256 over the sorted (path, SHA-1) of
    catalogue.lcc and every .lcbind - decision D5), or None when the build carries no save files (a build from
    before SPEC 70)."""
    try:
        from lcsave import lcfiles                # tools/lcsave (tools/ is on sys.path with this package)
    except ImportError:
        return None
    return lcfiles.content_fingerprint(str(out))


def online_keys(*, port_identity=False, balance=False, fingerprint=None) -> dict:
    """the port's [Online] keys: its own GameSpy game version (changes with the content version and the save /
    combat rules - decision D5; since 0.2.0 one value for every build, balance always on) and, for a build with
    the save tables, the content fingerprint a co-op peer must share (SPEC-new-save 6)."""
    if not port_identity:
        return {}
    keys = {'GameVersion': RI.game_version(), 'FastTransfer': FAST_TRANSFER, 'ReceiveValidation': RECEIVE_VALIDATION,
            'JoinInProgress': JOIN_IN_PROGRESS, 'TickRate': TICK_RATE}
    if fingerprint:
        keys['ContentFingerprint'] = fingerprint
    keys.update(broker_keys())
    return keys


def save_keys(*, port_identity=False) -> dict:
    """[Save] Format=lc: the LC save format (xml2-fix 1.4; SPEC 70), written for a port build."""
    return {'Format': SAVE_FORMAT} if port_identity else {}


def build_save_layout(out):
    """'w2' when <out> is a build made with --save-layout w2 (report.json build.save_layout), else None. Like the other
    content options this is read off the build's own record, never inferred from an existing ini: rebuilding without
    the option must drop the owned SaveLayout key."""
    chosen = str((build_record(out) or {}).get('save_layout') or '').strip().lower()
    return SAVE_LAYOUT_W2 if chosen == SAVE_LAYOUT_W2 else None


# xml2-fix 1.9.x (loot + Forge, DESIGN 2.2.1 / 7; its rule 52): [Game] Xml1Economy=1 turns the first game's item economy
# on (the sidecar Data/x1economy.txt the builder wrote with --loot xml1). OPT-IN like SaveLayout (builder option --loot
# xml1, build record 'loot'); the DLL accepts it only with [Limits] SaveLayout=w2. A DLL that does not carry the UTF-16
# key is refused (check_economy_dll), never silently written to: it would ignore the key and run the old economy
# against data built for the new one. A build without the option drops the key.
ECONOMY_KEY = 'Xml1Economy'
ECONOMY_VALUE = '1'


def build_loot(out):
    """{'Xml1Economy': '1'} when <out> is a build made with --loot xml1 (report.json build.loot), else {}. Read off the
    build's own record, never inferred from an existing ini: rebuilding without the option must drop the owned key."""
    chosen = str((build_record(out) or {}).get('loot') or '').strip().lower()
    return {ECONOMY_KEY: ECONOMY_VALUE} if chosen == 'xml1' else {}


def build_harm_loop_startup(out):
    """Opt-in startup adapter; online remains blocked pending rule assignment."""
    return {'HarmLoopStartup': 'xml1'} if (build_record(out) or {}).get('harm_loop_startup') == 'xml1' else {}


def port_keys(out, *, save_folder=PLAY_SAVE_FOLDER, eighth=True) -> dict:
    """{section: {key: value}} a play build in <out> needs (= harness.py install --no-pipe --limits for an xml2-fix
    that takes the 8th menu name). Read off the finished build: its menus, report.json and scripts."""
    postgame = build_postgame(out)
    menu = build_menu_items(out, eighth)
    game = game_keys(xml1_opening=True, save_folder=save_folder, forced_teams=build_forced_teams(out) or 'off',
                     postgame=postgame, port_identity=bool(postgame), main_menu_items=menu,
                     new_game_plus=NEW_GAME_PLUS if menu else None, review_stats=build_review_stats(out),
                     xtract=XTRACT if postgame else None, xp_curve=build_xp_curve(out))
    game.update(build_harm_loop_startup(out))
    # Same recorded content option that heroes uses. Never infer this from an
    # existing INI: rebuilding with the feature off must remove the owned key.
    record = build_record(out) or {}
    if record.get('grab_carry') == 'xml1':
        game['Xml1GrabCarry'] = 'xml1'
        if record.get('guard_decide') == 'xml1':
            game.update(GUARD_DECIDE)
        if record.get('telekinesis') == 'xml1':
            game.update(TELEKINESIS)
        if record.get('flying_carry') != 'xml1':
            game.update(FLYING_CARRY_OFF)
    if (build_record(out) or {}).get('rogue_decide') == 'xml1':
        game['Xml1RogueDecide'] = 'xml1'
    game.update(build_loot(out))
    turrets = build_turrets(out) if postgame else {}
    if postgame:
        game.update(build_mold_controller(out))
        game.update(build_bosses(out))
        game.update(build_lockon_effects(out))
        game.update(turrets.get('Game', {}))
    semi_auto = build_semi_auto(out) if game.get('NpcPowerRule') == NPC_POWER_RULE else {}
    game.update(semi_auto.get('Game', {}))
    # XML1's one-sided level collision for movement (xml2-fix [Game] WorldBackfaces=xml1, gameplay rule 30 revision 2,
    # 1.8.0-beta.7; G14): movement sweeps stop meeting the back faces of the level hull, as XML1's trace helper never
    # asks for them - in the build's converted XML1 zones only ([WorldBackfaces] ZoneCount / Z1..Zn); no list = no key
    # (never every zone). Heroes too: the release waits on a per-zone walk test.
    world_backfaces = build_world_backfaces(out)
    if world_backfaces:
        game['WorldBackfaces'] = WORLD_BACKFACES
    save_layout = build_save_layout(out)
    keys = {'Game': game, 'Limits': limits_for(save_layout), 'Engine': {'ModelPools': MODEL_POOLS, 'ModelHandles': MODEL_HANDLES}}
    if (build_record(out) or {}).get('actor_pools') == ACTOR_POOLS:   # recorded option only (OFF rebuild drops it)
        keys['Limits']['ActorPools'] = ACTOR_POOLS
    if (build_record(out) or {}).get('anim_enums') == 'xml1':     # recorded option only (OFF rebuild drops it)
        keys['Limits']['AnimEnums'] = ANIM_ENUMS
        keys['Limits']['CharSounds'] = CHAR_SOUNDS
        keys['Limits']['MotionPool'] = MOTION_POOL
        keys['Limits']['ResidentStats'] = RESIDENT_STATS
    # limits wave 3 (--limits-wave3): recorded option only, absent for the default OFF (so an OFF build's record and ini
    # are the ones a build made before the option wrote); an OFF rebuild drops the keys and FightStyles is 32 again
    keys['Limits'].update(wave3_limits((build_record(out) or {}).get('limits_wave3')))
    if world_backfaces:
        keys['WorldBackfaces'] = world_backfaces
    if turrets:
        keys['Xml1Turrets'] = turrets['Xml1Turrets']
    if semi_auto:
        keys['NpcSemiAuto'] = semi_auto['NpcSemiAuto']
    balance = build_balance(out)
    online = online_keys(port_identity=bool(postgame), balance=balance, fingerprint=content_fingerprint(out))
    if postgame and (Path(out) / 'Data/lcsave/catalogue.lcc').is_file():
        online['GameVersion'] = RI.manifest(out)['game_version']
    if online:
        keys['Online'] = online
    save = save_keys(port_identity=bool(postgame))
    if save:
        keys['Save'] = save
    if balance:
        keys['Balance'] = balance_keys(out)
    check_save_layout_keys(keys)          # SaveLayout=w2 on a build without the LC save identity is refused here
    check_economy_keys(keys)              # Xml1Economy without the W2 layout is refused here
    return keys


def dropped_keys(keys: dict) -> dict:
    """{section: [key, ...]}: the PORT_OWNED keys `keys` does not set (merge_ini's drop for a port write)."""
    out = {}
    for section, owned in port_owned().items():
        have = {k.lower() for k in keys.get(section, {})}
        gone = [k for k in owned if k.lower() not in have]
        if gone:
            out[section] = gone
    return out


# ------------------------------------------------------------------------------------------------ the ini file
def _decode(raw: bytes):
    """(text, encoding tag) keeping every byte: UTF-16 LE with a BOM (what WritePrivateProfileStringW keeps), else
    latin-1 (a byte-for-byte round trip of any 8-bit or UTF-8 file; the port's values are ASCII)."""
    if raw.startswith(b'\xff\xfe'):
        return raw[2:].decode('utf-16-le'), 'utf-16'
    return raw.decode('latin-1'), 'latin-1'


def _encode(text: str, enc: str) -> bytes:
    return b'\xff\xfe' + text.encode('utf-16-le') if enc == 'utf-16' else text.encode('latin-1')


def _section_name(line: str):
    s = line.strip()
    if s.startswith('[') and ']' in s:
        return s[1:s.index(']')].strip()
    return None


def _key_of(line: str):
    s = line.strip()
    if not s or s[0] in ';#[' or '=' not in s:
        return None
    return s.split('=', 1)[0].strip()


def parse_ini(text: str) -> dict:
    """{section: {key: value}} as GetPrivateProfileString sees it (the first section / key of a name wins; names keep
    their spelling, lookups should use lower())."""
    out, by_lower, cur = {}, {}, None
    for line in text.splitlines():
        name = _section_name(line)
        if name is not None:
            if name.lower() not in by_lower:
                by_lower[name.lower()] = out[name] = {}
            cur = by_lower[name.lower()]
            continue
        key = _key_of(line)
        if cur is not None and key is not None and key.lower() not in {k.lower() for k in cur}:
            cur[key] = line.split('=', 1)[1].strip()
    return out


def read_ini(path) -> dict:
    """parse_ini of a file ({} when it does not exist)."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return {}
    return parse_ini(_decode(raw)[0])


def merge_text(text: str, sections: dict, drop: dict | None = None, newline: str = '\r\n') -> str:
    """text with sections {section: {key: value}} set and drop {section: [key, ...]} removed (see merge_ini)."""
    lines = text.splitlines()
    ends_with_newline = text.endswith(('\n', '\r'))

    def find_section(name):
        return next((i for i, line in enumerate(lines) if (_section_name(line) or '').lower() == name.lower()), None)

    def section_end(start):
        return next((i for i in range(start + 1, len(lines)) if _section_name(lines[i]) is not None), len(lines))

    for section, keys in (drop or {}).items():
        start = find_section(section)
        if start is None:
            continue
        wanted = {k.lower() for k in keys}
        end = section_end(start)
        lines[start + 1:end] = [ln for ln in lines[start + 1:end] if (_key_of(ln) or '').lower() not in wanted]
    for section, keys in sections.items():
        if not keys:
            continue
        start = find_section(section)
        if start is None:
            if lines and lines[-1].strip():
                lines.append('')
            lines.append(f'[{section}]')
            lines += [f'{k}={v}' for k, v in keys.items()]
            continue
        for key, value in keys.items():
            end = section_end(start)
            index = next((i for i in range(start + 1, end) if (_key_of(lines[i]) or '').lower() == key.lower()), None)
            if index is None:
                insert = end
                while insert > start + 1 and not lines[insert - 1].strip():
                    insert -= 1
                lines.insert(insert, f'{key}={value}')
            else:
                lines[index] = f'{lines[index].split("=", 1)[0]}={value}'
    if not lines:
        return ''
    return newline.join(lines) + (newline if ends_with_newline or not text else '')


def merge_ini(path, sections: dict, drop: dict | None = None) -> bool:
    """Set exactly `sections` ({section: {key: value}}) in the ini file at `path` and remove `drop` ({section:
    [key, ...]}), with WritePrivateProfileString semantics (module docstring); creates the file (CRLF, ANSI) when
    missing. Returns True when the file changed."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raw = None
    text, enc = _decode(raw) if raw else ('', 'latin-1')
    newline = '\r\n' if (raw is None or b'\r\n' in raw or b'\r\x00\n\x00' in raw or not text) else '\n'
    merged = merge_text(text, sections, drop, newline)
    data = _encode(merged, enc)
    if raw is not None and data == raw:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'{path.name}.tmp{os.getpid()}')
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return True


class FixTooOld(ValueError):
    """The companion DLL in the output folder does not know keys the build writes (`missing`: '[Section] Key'
    names). The harness and build_xml1 stop on it; the xml1-builder CLI warns and writes the ini, because the
    launcher puts the latest fix into the folder right after a build (a Rebuild over a 0.2.1 folder still holds
    XML2 Fix 1.4.0 until then)."""

    def __init__(self, msg: str, missing: list):
        super().__init__(msg)
        self.missing = list(missing)


def check_move_trigger_dll(dll, keys: dict) -> None:
    """An existing DLL must recognize the raised key before full-trigger output is installed.
    Source-only builds may omit the DLL, then install the companion build through the harness."""
    if int(keys.get('Limits', {}).get('MoveTriggers', '19')) <= 19:
        return
    dll = Path(dll)
    if dll.is_file() and 'MoveTriggers'.encode('utf-16le') not in dll.read_bytes():
        raise FixTooOld('Full move triggers require the companion XML2 Fix DLL supporting [Limits] MoveTriggers; '
                        'the existing DLL does not recognize it', ['[Limits] MoveTriggers'])


def check_save_layout_keys(keys: dict) -> None:
    """[Limits] SaveLayout (limits-wave2 "Step 8" contract table): only the exact value w2, and only together with
    [Save] Format=lc and [Limits] EntityCapacity=1 (the W2 tokens are contiguous), with ItemEnhancements absent or
    4096 (the DLL refuses any other value at start-up and the build would not start). Raises ValueError for any other
    key set; a key set without SaveLayout always passes (the configured baseline)."""
    limits = keys.get('Limits', {})
    if SAVE_LAYOUT_KEY not in limits:
        return
    value = limits[SAVE_LAYOUT_KEY]
    if value != SAVE_LAYOUT_W2:
        raise ValueError(f'[Limits] SaveLayout must be {SAVE_LAYOUT_W2} (got {value!r}); '
                         'an empty or unknown value is never written')
    if keys.get('Save', {}).get('Format') != SAVE_FORMAT:
        raise ValueError('[Limits] SaveLayout=w2 requires [Save] Format=lc')
    if limits.get('EntityCapacity') != '1':
        raise ValueError('[Limits] SaveLayout=w2 requires [Limits] EntityCapacity=1 (the W2 tokens are contiguous)')
    enhancements = limits.get('ItemEnhancements')
    if enhancements is not None and enhancements != W2_ITEM_ENHANCEMENTS:
        raise ValueError(f'[Limits] SaveLayout=w2 owns ItemEnhancements={W2_ITEM_ENHANCEMENTS}; '
                         f'{enhancements!r} would be refused at start-up')


def check_save_layout_dll(dll, keys: dict) -> None:
    """[Limits] SaveLayout=w2 needs the companion DLL that reads it (XML2 Fix 1.9, limits wave 2 step 8): probed as
    check_entity_capacity_dll probes EntityCapacity, as the UTF-16 key name with its terminator (a longer key or a
    message that merely starts with it does not count). Also runs check_save_layout_keys. Source-only builds may omit
    the DLL."""
    check_save_layout_keys(keys)
    if SAVE_LAYOUT_KEY not in keys.get('Limits', {}):
        return
    dll = Path(dll)
    if dll.is_file() and (SAVE_LAYOUT_KEY + '\0').encode('utf-16le') not in dll.read_bytes():
        raise FixTooOld('The W2 save layout requires the companion XML2 Fix DLL supporting [Limits] SaveLayout; '
                        'the existing DLL does not recognize it', ['[Limits] SaveLayout'])


def check_economy_keys(keys: dict) -> None:
    """[Game] Xml1Economy (DESIGN 7): only the value 1, and only together with [Limits] SaveLayout=w2 (the DLL refuses
    it otherwise: rule 52 needs rule 47). A key set without the key always passes."""
    game = keys.get('Game', {})
    if ECONOMY_KEY not in game:
        return
    if game[ECONOMY_KEY] != ECONOMY_VALUE:
        raise ValueError(f'[Game] {ECONOMY_KEY} must be {ECONOMY_VALUE} (got {game[ECONOMY_KEY]!r})')
    if keys.get('Limits', {}).get(SAVE_LAYOUT_KEY) != SAVE_LAYOUT_W2:
        raise ValueError(f'[Game] {ECONOMY_KEY}=1 requires [Limits] {SAVE_LAYOUT_KEY}={SAVE_LAYOUT_W2}')


def check_economy_dll(dll, keys: dict) -> None:
    """[Game] Xml1Economy=1 needs the companion DLL that carries the key (loot step 3a): probed as the UTF-16 key name
    with its terminator (check_save_layout_dll's probe). Also runs check_economy_keys. Source-only builds may omit the
    DLL."""
    check_economy_keys(keys)
    if ECONOMY_KEY not in keys.get('Game', {}):
        return
    dll = Path(dll)
    if dll.is_file() and (ECONOMY_KEY + '\0').encode('utf-16le') not in dll.read_bytes():
        raise FixTooOld('The first-game item economy requires the companion XML2 Fix DLL supporting [Game] '
                        f'{ECONOMY_KEY}; the existing DLL does not recognize it', [f'[Game] {ECONOMY_KEY}'])


def check_entity_capacity_dll(dll, keys: dict) -> None:
    """[Limits] EntityCapacity=1 (SPEC 85: actor 32 / generic 768 / World 1024) needs the companion DLL that owns it
    and LC saves (the expanded native save layout exists only as LC files)."""
    if keys.get('Limits', {}).get('EntityCapacity', '0') != '1':
        return
    if keys.get('Save', {}).get('Format') != 'lc':
        raise ValueError('[Limits] EntityCapacity=1 requires [Save] Format=lc')
    dll = Path(dll)
    if dll.is_file() and 'EntityCapacity'.encode('utf-16le') not in dll.read_bytes():
        raise FixTooOld('The entity-capacity raise requires the companion XML2 Fix DLL supporting [Limits] EntityCapacity; '
                        'the existing DLL does not recognize it', ['[Limits] EntityCapacity'])


# The [Game] / [Limits] keys first read by XML2 Fix 1.5 (REQUIRED_XML2FIX): a 1.4 DLL ignores them without a word.
RELEASE_15_KEYS = {'Game': ('PlacementCrush', 'DoubleHeal', 'RankCosts', 'LevelSkillPoints', 'LevelStatPoints',
                            'Xml1Multipart', 'X1Leader', 'SoloMode', 'DeathRule', 'DangerRoomGate', 'RevivalCost',
                            'Xml1Turrets', 'PackAmount', 'DeathSwitchClear', 'NpcPowerRule'),
                   'Limits': ('ScriptFunctions',)}
# TestMode is an optional player preference; the builder never writes it by default.
RELEASE_16_KEYS = {**RELEASE_15_KEYS,
                   'Game': RELEASE_15_KEYS['Game'] + ('ObjectWorldImpact', 'StunRule', 'DangerRoomParty', 'DangerRoomHealthBars', 'BoxHarmOrigin', 'HarmSingleChain',
                                                     'Xml1LockOnEffects', 'Xml1LockOnAim', 'HarmLoopStartup'),
                   'Online': ('FastTransfer', 'ReceiveValidation', 'Broker', 'BrokerPin')}  # Broker/BrokerPin: 0.4.0, only when set

# XML2 Fix 1.7 adds the display-only adapter and the online conversation rule (27), 1.7.1 the personal-item picture window; earlier keys retain their release
# grouping.
RELEASE_17_KEYS = {**RELEASE_16_KEYS, 'Game': RELEASE_16_KEYS['Game'] + ('ResistanceDisplay', 'OnlineConversations', 'PersonalItemPicture')}

# XML2 Fix 1.8 (Legends Classic 0.4.0) adds online rooms (Broker / BrokerPin are read since then) and drop-in co-op.
RELEASE_18_KEYS = {**RELEASE_17_KEYS, 'Online': RELEASE_17_KEYS['Online'] + ('JoinInProgress',)}
# XML2 Fix 1.8.0-beta.2 (Legends Classic 0.3.0-beta.2): the bigger model pools (gameplay-agreement rule 28) and the
# team-combo popup guard. A 1.8.0-beta.1 DLL knows neither, so the builder refuses it (its VERSIONINFO is the same
# numeric 1.8.0.0; the key strings are what tells the two apart).
RELEASE_18_KEYS = {**RELEASE_18_KEYS, 'Game': RELEASE_18_KEYS['Game'] + ('ComboPopupGuard',), 'Engine': ('ModelPools',)}
# XML2 Fix 1.8.0-beta.3 (Legends Classic 0.3.0-beta.3): online at 60 frames a second (gameplay-agreement rule 29). A
# beta.2 DLL does not read [Online] TickRate, so the builder refuses it.
RELEASE_18_KEYS = {**RELEASE_18_KEYS, 'Online': RELEASE_18_KEYS['Online'] + ('TickRate',)}
# XML2 Fix 1.8.0-beta.5 (Legends Classic 0.4.0-beta.5): the classic look's presentation-only adapters, [Game]
# ClassicHud=xml1 (the HUD) and ClassicCodex=1 (Codex Details/Back). A beta.4 DLL reads neither, so the builder refuses
# it. These two are matched with their UTF-16 terminator: earlier DLLs carry longer keys with the same start
# (ClassicHudPilot, ClassicHudTrace), which must not pass for them.
EXACT_KEYS = {'Game': ('ClassicHud', 'ClassicCodex')}
RELEASE_18_KEYS = {**RELEASE_18_KEYS, 'Game': RELEASE_18_KEYS['Game'] + EXACT_KEYS['Game']}
# XML2 Fix 1.8.0-beta.6 (Legends Classic 0.4.0-beta.6): the original weapon brain, [Game] NpcSemiAuto=xml1 with its
# [NpcSemiAuto] rows (gameplay-agreement rule 16 revision 10). A beta.5 DLL reads neither and would run the officer's
# stock burst/melee AI while its rule 16 record says revision 4, so the builder refuses it.
RELEASE_18_KEYS = {**RELEASE_18_KEYS, 'Game': RELEASE_18_KEYS['Game'] + ('NpcSemiAuto',)}
# XML2 Fix 1.8.0-beta.7 (Legends Classic 0.4.0-beta.7): [Game] ClassicSpeakers (XML1's "Alison" label) and the schema 3
# weapon-brain rows. A beta.6 DLL ignores the label and refuses the rows (the gunmen keep the stock PC AI and the
# requested rule 16 is unverified), so the builder refuses it, naming the key every build writes with the rows.
RELEASE_18_KEYS = {**RELEASE_18_KEYS, 'Game': RELEASE_18_KEYS['Game'] + ('ClassicSpeakers', 'WorldBackfaces')}
# Rule 30 revision 2 (XML1 levels only) reads [WorldBackfaces] ZoneCount / Z1..Zn. The first, unscoped beta 7 build (a
# private candidate DLL) knows [Game] WorldBackfaces but not the list and would apply the rule to every zone, so the
# builder also requires the list's key by name.
RELEASE_18_KEYS = {**RELEASE_18_KEYS, 'WorldBackfaces': ('ZoneCount',)}
# XML2 Fix 1.9.0-beta.1 (Legends Classic 0.4.1-beta.1, the port's beta 8): [Game] Xml1Bosses (the shared boss dispatcher, rule 40). A beta.7
# DLL ignores it, so the dopples would fight with the stock AI while the build says otherwise; the builder refuses it.
RELEASE_18_KEYS = {**RELEASE_18_KEYS, 'Game': RELEASE_18_KEYS['Game'] + ('Xml1Bosses',)}
# XML2 Fix 1.9.0-beta.1 (Legends Classic 0.4.1-beta.1, the port's beta 8): [Game] ClassicObjectives (the PDA objective page lists the
# visible objectives and opens on the current one). A beta.7 DLL leaves the native page: a hole for every hidden
# objective and the first slot, often a finished mission, so the builder refuses it.
RELEASE_18_KEYS = {**RELEASE_18_KEYS, 'Game': RELEASE_18_KEYS['Game'] + ('ClassicObjectives',)}
# Byte markers for formats a key name cannot show. The schema 4 weapon rows (bullet trace time + accuracy) are read only
# by a DLL whose rule 16 detail digest says "NSA4"; an earlier beta 7 DLL knows [Game] NpcSemiAuto but refuses the wider
# rows and withdraws rule 16, so the builder refuses it, naming the rows.
RELEASE_MARKERS = {('Game', 'NpcSemiAuto'): (b'NSA4', '[NpcSemiAuto] schema 4 rows')}
# XML2 Fix 1.9.0-beta.1 (Legends Classic 0.4.1-beta.1, the port's beta 8): limits wave 1 ([Limits] IGBCache, [Engine]
# ModelHandles; rules 31-32), XML1's wall cling (39), lift rule (38), Rogue's decide (43), the shared handlers (42),
# the receive-side rounding and damage cap ([Balance] ReceiveRounding / DamageCap, 41) and the boss brains (40). A
# 1.8.0 DLL (beta 7 or the stable) ignores every one of them without a word, so the builder refuses it by name.
RELEASE_18_KEYS = {**RELEASE_18_KEYS,
                   'Game': RELEASE_18_KEYS['Game'] + ('LiftRule', 'Xml1WallCling', 'Xml1RogueDecide') + tuple(SHARED_HANDLERS),
                   'Limits': RELEASE_18_KEYS.get('Limits', ()) + ('IGBCache',),
                   'Engine': RELEASE_18_KEYS['Engine'] + ('ModelHandles',),
                   'Balance': RELEASE_18_KEYS.get('Balance', ()) + ('ReceiveRounding', 'DamageCap')}
# Rule 16 revision 14 (parity wave A's items 19-22 and the character bullet ray) changes no key: a 1.8.0 DLL runs
# NpcPowerRule=xml1 as revision 11. The 1.9.0 DLL's install log carries "NPR14" (xml2-fix src/npc_power.cpp), so the
# builder requires that marker wherever it writes the rule.
RELEASE_MARKERS[('Game', 'NpcPowerRule')] = (b'NPR14', '[Game] NpcPowerRule revision 14')
# Candidate rule 45 is opt-in. The key must exist in the companion DLL when
# requested; a pre-candidate DLL would silently ignore the restored ground rule.
RELEASE_18_KEYS = {**RELEASE_18_KEYS, 'Game': RELEASE_18_KEYS['Game'] + ('Xml1GrabCarry',)}
# XML2 Fix 1.9.0-beta.1 (the port's beta 8 candidate 080b): the nine shared-handler wave C keys (rule 46) and, when
# written (--actor-pools 124), [Limits] ActorPools (rule 44). A DLL before them ignores each without a word.
RELEASE_18_KEYS = {**RELEASE_18_KEYS, 'Game': RELEASE_18_KEYS['Game'] + tuple(SHARED_HANDLERS_C),
                   'Limits': RELEASE_18_KEYS['Limits'] + ('ActorPools',)}
# xml2-fix rule 48 (beta8/anim-enums): [Limits] AnimEnums, when written (--anim-enums xml1). The key's name is not enough:
# the build's mappings name the DLL's XML1 enums, so the DLL must also carry its marked table (anim_enums.DLL_MARKER)
# with exactly the builder's 23 names in ID order (check_anim_enums_dll); a DLL without it would leave the 23 mappings
# unresolved (dropped by the shared_anims parser) and every carry / victim move on enum 0's animation.
RELEASE_18_KEYS = {**RELEASE_18_KEYS, 'Limits': RELEASE_18_KEYS['Limits'] + ('AnimEnums', 'CharSounds', 'MotionPool', 'ResidentStats')}
# The CharSounds key alone cannot certify that the DLL registers the agreement rule.
RELEASE_MARKERS[('Limits', 'CharSounds')] = (CHAR_SOUNDS_MARKER, '[Limits] CharSounds (rule 49)')
RELEASE_MARKERS[('Limits', 'MotionPool')] = (MOTION_POOL_MARKER, '[Limits] MotionPool (rule 51)')
# xml2-fix 1.9.0-beta.1 rule 45 revision 3 (beta8/carry 063f2e8: the flying carry, fix7 admission, XML1's strict flight
# upkeep) keeps the key name of revision 2 (080b), whose DLL would run the build's XML1 `flying` node (anim_enums
# .XML1_FLIGHT_UPKEEP) with no flight cost at all. Its install line is the byte marker (xml2-fix src/xml1_grab_carry.cpp).
GRAB_CARRY_R3_MARKER = b'flying carry, fix7 and XML1 upkeep installed'
RELEASE_MARKERS[('Game', 'Xml1GrabCarry')] = (GRAB_CARRY_R3_MARKER, '[Game] Xml1GrabCarry revision 3')
# xml2-fix 1.9.0-beta.1 (beta 8 candidate 080d): rule 46's TelekinesisRule / GuardDecideRule (a DLL before them - 080c and
# older - ignores both keys without a word and runs PC's telekinesis and guard decide).
RELEASE_18_KEYS = {**RELEASE_18_KEYS, 'Game': RELEASE_18_KEYS['Game'] + tuple(TK_GUARD)}
# xml2-fix 1.9.0-beta.1 (beta 8 candidate 080e, beta8/fix2 c0505c8): TelekinesisRule resolves Phoenix's power1a / power1b
# through the PC sound manager's name lookup (slot 0x38); the 080d DLL called slot 0x34 (a PC bool query, ret 4) and
# crashed at the first telekinesis hold. The same release keeps an established flying carry node instead of re-entering
# it every frame (080d: the victim never followed). Neither changes a key or a rule revision, so the install lines
# (xml2-fix src/shared_handlers_c.cpp, src/xml1_grab_carry.cpp) are the byte markers.
TK_AUDIO_MARKER = b'telekinesis sounds resolve through PC audio slot 38'
CARRY_CHAIN_MARKER = b'flying carry keeps its established node (no self-chain)'
RELEASE_MARKERS[('Game', 'TelekinesisRule')] = (TK_AUDIO_MARKER, '[Game] TelekinesisRule (PC audio slot 38)')
# a second marker for a key that already has one (Xml1GrabCarry: revision 3 above)
EXTRA_MARKERS = [(('Game', 'Xml1GrabCarry'), CARRY_CHAIN_MARKER, '[Game] Xml1GrabCarry (no carry self-chain)')]
# xml2-fix 1.9.0-beta.1 (beta 8 candidate 080g, beta8/fix3 6f7df24): a telekinesis throw released with no velocity
# divided zero by zero (080e/080f); a tapped guard never left the guard decide (the policy ran in the entry slot); the
# Colossus charge evaluated its damage / knockback / range on the struck soldier (no damage); a thrown body's world
# impact never reached its receiver (PC gate 0x42C09E) and the carry pose read the synthetic bones (victim 30 units low).
# No key or rule revision changes, so the install lines (xml2-fix src/shared_handlers_c.cpp, src/xml1_grab_carry.cpp)
# are the byte markers.
TK_STILL_MARKER = b"a still telekinesis throw keeps the victim's facing (no zero divide)"
GUARD_TAP_MARKER = b'guard decide runs at input and exits after a tap'
COLOSSUS_CASTER_MARKER = b'Colossus charge evaluates its talents on the caster'
THROWN_IMPACT_MARKER = b'thrown bodies forward world impacts (42C09E); carry pose on animated bones'
# xml2-fix 1.9.0-beta.1 (beta 8 candidate 080h): [Game] Xml1FlyingCarry=0. A DLL before it (080g and older) ignores the key
# and installs the flying carry; the key's name and its install line are both required.
FLYING_CARRY_OFF_MARKER = b'flying carry off (Xml1FlyingCarry=0): no carry handlers, PC flight descent'
RELEASE_18_KEYS = {**RELEASE_18_KEYS, 'Game': RELEASE_18_KEYS['Game'] + tuple(FLYING_CARRY_OFF)}
RELEASE_MARKERS[('Game', 'Xml1FlyingCarry')] = (FLYING_CARRY_OFF_MARKER, '[Game] Xml1FlyingCarry (flying carry off)')
EXTRA_MARKERS += [(('Game', 'TelekinesisRule'), TK_STILL_MARKER, '[Game] TelekinesisRule (still throw)'),
                  (('Game', 'GuardDecideRule'), GUARD_TAP_MARKER, '[Game] GuardDecideRule (tap exit)'),
                  (('Game', 'ColossusChargeRule'), COLOSSUS_CASTER_MARKER, '[Game] ColossusChargeRule (caster talents)'),
                  (('Game', 'Xml1GrabCarry'), THROWN_IMPACT_MARKER, '[Game] Xml1GrabCarry (thrown impact, animated bones)')]
# xml2-fix beta 9 (beta9/beta9-moves ab76926, candidate 082b): the guard decide resolves at its entry 0x693004 (a real
# pad / keyboard press did nothing in beta 8), telekinesis throws are armed through native L2 (release gate 0x42E923) and
# flying-carry throws through the victim_throw registration 0x692378 (beta 8: 0 damage). No key, rule revision or install
# line changed, so the fix's own guard descriptions for those sites are the byte markers: a 1.9.0-beta.1 / beta.2 DLL
# would install the moves with beta 8's defects. Only a build with the option on writes TelekinesisRule /
# GuardDecideRule or leaves Xml1FlyingCarry out (beta 8's defaults keep all three off).
TK_ARMING_MARKER = b'TK final selector chooses native L2 amount'
GUARD_ENTRY_MARKER = b'entry-context chain resolver'
CARRY_THROW_MARKER = b'victim_throw execute registration'
EXTRA_MARKERS += [(('Game', 'TelekinesisRule'), TK_ARMING_MARKER, '[Game] TelekinesisRule (throw damage, beta 9)'),
                  (('Game', 'GuardDecideRule'), GUARD_ENTRY_MARKER, '[Game] GuardDecideRule (decided at entry, beta 9)')]
FLYING_CARRY_ON_NAME = '[Game] Xml1GrabCarry (flying carry on: throw damage, beta 9)'
# xml2-fix 0.4.2 candidate 082c: W2's boot crash (651011f: two shared ring / ratl pool helpers had been widened in place,
# MONEY1 never registered) and save crash (5420671: the restore map overran save_format's statics; the side-mission
# and mission-state blocks streamed at the old size, so every W2 save was refused) changed no key, rule revision or
# install line either. Their own guard descriptions are the markers: a SaveLayout=w2 build with an earlier W2 DLL
# (082a / 082b) crashes at boot or on the first save. Moves round 2 (ac7a3d9: carry admission 0x433E6A, carry entry at
# the hands, energy) is marked by its carry trace; without it the flying carry keeps 082b's live failures.
W2_BOOT_MARKER = b'shared instance ring pop'
W2_SAVE_MARKER = b'mission state stream size'
W2_LAYOUT_MARKERS = ((W2_BOOT_MARKER, '[Limits] SaveLayout=w2 (boot: shared pool helpers stay retail, 082c)'),
                     (W2_SAVE_MARKER, '[Limits] SaveLayout=w2 (saving: restore map and mission blocks at W2 size, 082c)'))
CARRY_ROUND2_MARKER = b'carry trace hands selectors'
FLYING_CARRY_R2_NAME = '[Game] Xml1GrabCarry (flying carry on: admission, hands, energy - moves round 2)'
# xml2-fix 0.4.2 candidate 082d (the 082c live round's fixes; no key, rule revision or install line changed, so string
# constants of the fixed code are the markers). Economy (40a535c): opening the Forge or the Healer crashed 082c's DLL in
# the shop digest (unguarded native name reads; the digest runs with the testers' [Test] InputPipe=1), so a --loot xml1
# build needs the contained digest. Moves (19104f7): the guard grabbed untouched enemies and telekinesis tried its
# acquisition once (no held retry; one tk_guard_bridges change, marked by its TKTrace line); the flying carry hovered
# over its target, attached a carried ally by its feet and threw with the wrong level value (marked by the carry's
# move-name attachment table).
ECONOMY_DIGEST_MARKER = b'action-capture'
ECONOMY_DIGEST_NAME = '[Game] Xml1Economy (shop digest fault containment, 082d)'
TK_GUARD_082D_MARKER = b'tk acquisition actor='
CARRY_082D_MARKER = b'airpickupidleally'
FLYING_CARRY_082D_NAME = '[Game] Xml1GrabCarry (flying carry on: descent, hand attach, L2 throw damage - 082d)'
MARKERS_082D = (ECONOMY_DIGEST_MARKER, TK_GUARD_082D_MARKER, CARRY_082D_MARKER)
# xml2-fix 0.4.2 candidate 082e (the 082d live round's moves fixes, a2af326; again no key, rule revision or install line
# changed). The guard took only the reaction bit as "stunned", so an enemy under a timed stun was never picked up, and
# telekinesis' victim callback could release a victim selected at the converted power1 start (one tk_guard_bridges
# change, marked by its GuardTrace line); the flying pickup's clearance probe collided with the selected character
# itself and suppressed the descent (marked by the carry's pre-pickup CarryTrace stage).
TK_GUARD_082E_MARKER = b'guard eligibility actor='
TK_GUARD_082E_NAME = '(082e: timed-stun guard pickup, TK ownership through power1)'
CARRY_082E_MARKER = b'descent-not-character'
FLYING_CARRY_082E_NAME = '[Game] Xml1GrabCarry (flying carry on: pickup clearance excludes the victim - 082e)'
MARKERS_082E = (TK_GUARD_082E_MARKER, CARRY_082E_MARKER)
# E12 (SPEC 108): a build whose own XMen2.exe is large-address-aware needs the fix's address-space module (the 2 GB guard
# block, and the two test readers that refused addresses above 0x7fffffff before it). Its start line is the marker; the
# check reads the build's exe beside the DLL (no exe yet, or --laa off: nothing to check).
ADDRESS_SPACE_MARKER = b'address space: laa %s; 2 GB guard %s'


def check_address_space_dll(dll, keys: dict) -> None:
    dll = Path(dll)
    exe = dll.parent / 'XMen2.exe'
    if not dll.is_file() or not exe.is_file():
        return
    from . import exe_flags
    try:
        if exe_flags.laa_state(exe.read_bytes()) != 'on':
            return
    except exe_flags.NotPE32:
        return
    if ADDRESS_SPACE_MARKER not in dll.read_bytes():
        raise FixTooOld("The build's XMen2.exe is large-address-aware; the existing DLL has no address-space guard",
                        ['XMen2.exe large-address-aware (address space guard)'])


# Limits wave 3: each row's key AND its rule's install line (WAVE3_MARKERS) are required of an existing DLL, by name. The
# key names go through RELEASE_18_KEYS (the UTF-16 key string); the rules through the markers. FightStyles is the one key
# an older DLL already reads, so its marker (rule 35 revision 2: the two-dword bitmaps) is required only above the
# 32 the earlier DLLs raise it to.
RELEASE_18_KEYS = {**RELEASE_18_KEYS, 'Limits': RELEASE_18_KEYS['Limits'] + tuple(
    k for k in (*LIMITS_WAVE3, *LIMITS_WAVE3_LATE) if k != 'FightStyles')}
# Optional player preference: even 0 needs a DLL that reads it; older DLLs leave routing on.
# Keep the terminating NUL so LatePadsTrace cannot stand in for LatePads.
RELEASE_18_KEYS = {**RELEASE_18_KEYS, 'Input': RELEASE_18_KEYS.get('Input', ()) + ('LatePads',)}
EXACT_KEYS = {**EXACT_KEYS, 'Input': EXACT_KEYS.get('Input', ()) + ('LatePads',)}
# xml2-fix 739cc0f (E4 stage 2 core, its docs/e4-core.md) [Limits] Actors=96: live actors / controllers / teams 32 -> 96,
# gameplay rule 44 revision 2, save feature 0x4 (a campaign written with it on cannot be loaded by a DLL without it).
# An opt-in tester / player preference like LatePads: the builder never writes it and it is not port-owned, so a
# rebuild keeps it, and a rebuild must not leave it without the prerequisites the DLL requires in the same startup
# transaction (otherwise Stage 2 refuses at start). The UTF-16 key (with its NUL: no longer key can stand in) and the
# conservative-marking core's telemetry name (fe3f621 never shipped; 739cc0f added stale_fold_retirements) are both
# required of the DLL.
ACTORS_KEY = 'Actors'
ACTORS_VALUE = '96'
ACTORS_PREREQUISITES = (('EntityCapacity', '1'), ('ActorPools', ACTOR_POOLS), ('AnimEnums', ANIM_ENUMS),
                        ('CharSounds', CHAR_SOUNDS), ('ResidentStats', RESIDENT_STATS), ('MotionPool', MOTION_POOL))
ACTORS_MARKER = b'stale_fold_retirements'
RELEASE_18_KEYS = {**RELEASE_18_KEYS, 'Limits': RELEASE_18_KEYS['Limits'] + (ACTORS_KEY,)}
EXACT_KEYS = {**EXACT_KEYS, 'Limits': EXACT_KEYS.get('Limits', ()) + (ACTORS_KEY,)}


def check_actors_keys(keys: dict) -> None:
    """[Limits] Actors (when present): only 96, and only with its six prerequisites at their exact values in the same
    ini (the DLL refuses Stage 2 otherwise and plays with 32 actors). ValueError names every problem."""
    limits = keys.get('Limits', {})
    if ACTORS_KEY not in limits:
        return
    value = str(limits[ACTORS_KEY]).strip()
    if value != ACTORS_VALUE:
        raise ValueError(f'[Limits] {ACTORS_KEY} must be {ACTORS_VALUE} (got {value!r}); remove the key to keep 32 actors')
    bad = [f'[Limits] {k}={v}' for k, v in ACTORS_PREREQUISITES if str(limits.get(k, '')).strip() != v]
    if bad:
        raise ValueError(f'[Limits] {ACTORS_KEY}={ACTORS_VALUE} needs ' + ', '.join(bad) + ' in the same xml2-fix.ini '
                         '(add them, or remove Actors to keep 32 actors)')
for _key in (*LIMITS_WAVE3, *LIMITS_WAVE3_LATE):
    if _key != 'FightStyles':
        RELEASE_MARKERS[('Limits', _key)] = (WAVE3_MARKERS[_key], f'[Limits] {_key} (rule {WAVE3_RULES[_key]})')
# (section, key) -> (highest value an earlier DLL reads, marker, name)
VALUE_MARKERS = {('Limits', 'FightStyles'): (32, WAVE3_MARKERS['FightStyles'], '[Limits] FightStyles (rule 35 revision 2)')}


def _int_or_zero(value) -> int:
    try:
        return int(str(value).strip())
    except ValueError:
        return 0


def check_release_dll(dll, keys: dict) -> None:
    """An existing companion DLL must know every required key the build writes (as check_entity_capacity_dll does
    for 1.4's): an older fix would run the build with those rules silently off. Source-only builds may omit the DLL."""
    dll = Path(dll)
    if not dll.is_file():
        return
    data = dll.read_bytes()
    missing = [f'[{section}] {key}' for section, names in RELEASE_18_KEYS.items() for key in names
               if key in keys.get(section, {}) and (key + ('\0' if key in EXACT_KEYS.get(section, ()) else '')).encode('utf-16le') not in data]
    missing += [name for (section, key), (marker, name) in RELEASE_MARKERS.items()
                if key in keys.get(section, {}) and marker not in data]
    missing += [name for (section, key), marker, name in EXTRA_MARKERS
                if key in keys.get(section, {}) and marker not in data]
    game = keys.get('Game', {})
    if 'Xml1GrabCarry' in game and 'Xml1FlyingCarry' not in game and CARRY_THROW_MARKER not in data:
        missing.append(FLYING_CARRY_ON_NAME)         # --flying-carry xml1 (the key left out = the DLL's flying carry on)
    if 'Xml1GrabCarry' in game and 'Xml1FlyingCarry' not in game and CARRY_ROUND2_MARKER not in data:
        missing.append(FLYING_CARRY_R2_NAME)
    if keys.get('Limits', {}).get('SaveLayout') == 'w2':
        missing += [name for marker, name in W2_LAYOUT_MARKERS if marker not in data]
    if 'Xml1GrabCarry' in game and 'Xml1FlyingCarry' not in game and CARRY_082D_MARKER not in data:
        missing.append(FLYING_CARRY_082D_NAME)
    missing += [f'[Game] {key} (082d: stunned-only ground grab, held telekinesis retry)' for key in ('TelekinesisRule', 'GuardDecideRule')
                if key in game and TK_GUARD_082D_MARKER not in data]
    if 'Xml1GrabCarry' in game and 'Xml1FlyingCarry' not in game and CARRY_082E_MARKER not in data:
        missing.append(FLYING_CARRY_082E_NAME)
    missing += [f'[Game] {key} {TK_GUARD_082E_NAME}' for key in ('TelekinesisRule', 'GuardDecideRule')
                if key in game and TK_GUARD_082E_MARKER not in data]
    if 'Xml1Economy' in game and ECONOMY_DIGEST_MARKER not in data:
        missing.append(ECONOMY_DIGEST_NAME)
    for (section, key), (stock, marker, name) in VALUE_MARKERS.items():
        value = keys.get(section, {}).get(key)
        if value is not None and _int_or_zero(value) > stock:
            if key.encode('utf-16le') not in data:
                missing.append(f'[{section}] {key}')
            if marker not in data:
                missing.append(name)
    if missing:
        raise FixTooOld(f'This build needs XML2 Fix {REQUIRED_XML2FIX} or later; the existing DLL does not recognize '
                        + ', '.join(missing), missing)


def check_anim_enums_dll(dll, keys: dict) -> None:
    """[Limits] AnimEnums needs the companion DLL's AnimEnums table: the marker block and the builder's built-in names
    (anim_enums.BUILTIN_ENUMS, IDs 0xD2..) in the same order. Source-only builds may omit the DLL."""
    if 'AnimEnums' not in keys.get('Limits', {}):
        return
    dll = Path(dll)
    if not dll.is_file():
        return
    from . import anim_enums as AE
    names = AE.dll_builtin_names(dll.read_bytes())
    if names is None:
        raise FixTooOld('[Limits] AnimEnums needs the XML2 Fix with the AnimEnums table (rule 48); the existing DLL '
                        'has none', ['[Limits] AnimEnums (AnimEnums table)'])
    if tuple(names) != AE.BUILTIN_ENUMS:
        raise FixTooOld(f'[Limits] AnimEnums: the AnimEnums table of the existing DLL ({len(names)} names) differs '
                        f'from the builder\'s {len(AE.BUILTIN_ENUMS)} XML1 enums', ['[Limits] AnimEnums (AnimEnums table)'])


def check_wave3_keys(keys: dict) -> None:
    """The wave-3 rows depend on each other (DESIGN section 2): primitives per effect beyond 10 spill into a side table
    sized from the effect-template count, so PrimitivesPerEffect needs EffectTemplates; a late row needs the nine. Raises
    ValueError for a key set no DLL can run."""
    limits = keys.get('Limits', {})
    if 'PrimitivesPerEffect' in limits and 'EffectTemplates' not in limits:
        raise ValueError('[Limits] PrimitivesPerEffect requires [Limits] EffectTemplates (its side table is indexed by '
                         'the effect definition slot)')
    late = [k for k in LIMITS_WAVE3_LATE if k in limits]
    absent = [k for k in LIMITS_WAVE3 if k != 'FightStyles' and k not in limits]
    if late and absent:
        raise ValueError(f'[Limits] {", ".join(late)} is written only with the nine wave-3 rows; missing {absent}')


def old_fix_keys(dll, keys: dict) -> list:
    """every key of `keys` the existing companion DLL does not know ('[Section] Key'; [] without a DLL). Raises
    ValueError for a key set no DLL can run (EntityCapacity without Format=lc)."""
    missing = []
    check_wave3_keys(keys)
    for check in (check_move_trigger_dll, check_entity_capacity_dll, check_save_layout_dll, check_economy_dll,
                  check_release_dll, check_anim_enums_dll, check_address_space_dll):
        try:
            check(dll, keys)
        except FixTooOld as exc:
            missing += [m for m in exc.missing if m not in missing]
    return missing


def write_port_keys(out, keys: dict | None = None, *, old_fix_ok: bool = False) -> dict:
    """merge the port's keys (default: port_keys(out)) into <out>/xml2-fix.ini, dropping the PORT_OWNED keys it does
    not need; the launcher's keys stay. Returns the keys written. An existing DLL that doesn't know every key raises
    FixTooOld (naming them all) unless `old_fix_ok` (the CLI's warning path: FixTooOld)."""
    keys = port_keys(out) if keys is None else keys
    # Validate the optional player preference as it will survive this merge, including mixed-case INIs.
    # It is not port-owned: neither emit a default nor drop a player's explicit 0 on a rebuild.
    ini = Path(out) / 'xml2-fix.ini'
    try:
        text = _decode(ini.read_bytes())[0]
    except FileNotFoundError:
        text = ''
    drop = dropped_keys(keys)
    actors = any(section.lower() == 'limits' and any(k.lower() == ACTORS_KEY.lower() for k in values)
                 for section, values in parse_ini(text).items())
    if actors:
        # the Actors preference brings the one prerequisite a build may not write (ActorPools: --actor-pools); a
        # player who set both keeps both. The others are checked, not kept (they come with the build's options).
        drop = {section: [k for k in names if not (section == 'Limits' and k == 'ActorPools')]
                for section, names in drop.items()}
    merged = parse_ini(merge_text(text, keys, drop))
    validation_keys = {section: dict(values) for section, values in keys.items()}
    for section, values in merged.items():
        if section.lower() == 'input':
            for key, value in values.items():
                if key.lower() == 'latepads':
                    validation_keys.setdefault('Input', {})['LatePads'] = value
        if section.lower() == 'limits' and actors:
            # the prerequisites as the rebuilt ini will carry them (the port's own keys or the player's); the DLL
            # check needs only Actors (a DLL that has it reads all six)
            canonical = {k.lower(): k for k in (ACTORS_KEY, *(name for name, _ in ACTORS_PREREQUISITES))}
            check_actors_keys({'Limits': {canonical[k.lower()]: v for k, v in values.items() if k.lower() in canonical}})
            validation_keys.setdefault('Limits', {})[ACTORS_KEY] = next(
                v for k, v in values.items() if k.lower() == ACTORS_KEY.lower())
    missing = old_fix_keys(Path(out) / 'dinput.dll', validation_keys)
    if SAVE_LAYOUT_KEY in keys.get('Limits', {}) and f'[Limits] {SAVE_LAYOUT_KEY}' in missing:
        # the warning path (old_fix_ok) writes the other keys for an older fix the launcher replaces right after the
        # build; SaveLayout is not one of them: an older DLL ignores it and the build would run on the baseline
        # layout while its record says W2
        raise FixTooOld('The W2 save layout requires the companion XML2 Fix DLL supporting [Limits] SaveLayout; '
                        'the existing DLL does not recognize it, so the key is not written', [f'[Limits] {SAVE_LAYOUT_KEY}'])
    if ECONOMY_KEY in keys.get('Game', {}) and f'[Game] {ECONOMY_KEY}' in missing:
        # not a warning either: an older DLL ignores the key and would run XML2's economy against the XML1 item table
        raise FixTooOld('The first-game item economy requires the companion XML2 Fix DLL supporting [Game] '
                        f'{ECONOMY_KEY}; the existing DLL does not recognize it, so the key is not written',
                        [f'[Game] {ECONOMY_KEY}'])
    if missing and not old_fix_ok:
        raise FixTooOld(f'This build needs XML2 Fix {REQUIRED_XML2FIX} or later; the existing DLL does not recognize '
                        + ', '.join(missing), missing)
    if keys.get('Save', {}).get('Format') == 'lc' and (Path(out) / 'Data/lcsave/catalogue.lcc').is_file():
        import json
        identity = RI.manifest(out)
        keys.setdefault('Online', {})['GameVersion'] = identity['game_version']
        archive = Path(out) / '_build' / 'lc-release-identity.json'
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text(json.dumps(identity, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    merge_ini(Path(out) / 'xml2-fix.ini', keys, drop)
    return keys

RELEASE_MARKERS[('Limits', 'ResidentStats')] = (RESIDENT_STATS_MARKER, '[Limits] ResidentStats (rule 50)')
RELEASE_MARKERS[('Limits', ACTORS_KEY)] = (ACTORS_MARKER, f'[Limits] {ACTORS_KEY} (rule 44 revision 2, E4 stage 2 core)')
