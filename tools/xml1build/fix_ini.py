"""xml1build.fix_ini - the port's keys in xml2-fix.ini (BUILDER_DESIGN.md 3.5).

The xml2-fix DLL (dinput.dll) reads <game>/xml2-fix.ini. Two writers share that file and neither removes the other's
keys:

  the port (this module)  the content requirements of a build - [Game] NewGameTeam / ResetUnlocks / SaveFolder /
                          ForcedTeams / PostgameScript / WindowTitle / EndHeroUnlock / MainMenuItems / NewGamePlus /
                          ReviewStats / Xtract / XPCurve / GeometrySharingBlendIndices / CharacterLadderPaths /
                          ObjectiveDescriptions / BreakRule, [Limits]
                          ActorSlots / ResourceNames / ItemEnhancements / FightStyles / EffectCurves, [Online] GameVersion /
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
LIMITS = {'ActorSlots': '127', 'ResourceNames': '1024', 'ItemEnhancements': '512', 'FightStyles': '32',
          'EffectCurves': '3600', 'MoveTriggers': '64', 'EntityCapacity': '1', 'ScriptFunctions': '1024'}

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
REQUIRED_XML2FIX = '1.8'
# The companion fix's prerelease a beta/rc builder needs (launcher-facing requires.xml2fix only): 0.3.0-beta.2 writes
# [Engine] ModelPools and [Game] ComboPopupGuard, first read by XML2 Fix 1.8.0-beta.2; 0.3.0-beta.3 writes [Online]
# TickRate, first read by 1.8.0-beta.3; 0.4.0-beta.5 writes [Game] ClassicHud / ClassicCodex (the classic look), first
# read by 1.8.0-beta.5, so its requirement is '>=1.8.0-beta.5' (SemVer: beta.5, beta.N > 5, every rc and the final
# 1.8.0 meet it; 1.8.0-beta.4 and older do not).
REQUIRED_XML2FIX_PRERELEASE = 'beta.5'


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

# every key the port may write (the builder drops the ones a build does not need); the launcher owns the rest
PORT_OWNED = {'Game': ('NewGameTeam', 'ResetUnlocks', 'SaveFolder', 'ForcedTeams', 'PostgameScript', 'WindowTitle',
                        'EndHeroUnlock', 'MainMenuItems', 'DangerRoomGate', 'ClassicMainBackdrop', 'ClassicMainPanelBounds', 'NewGamePlus', 'ReviewStats', 'Xtract', 'XtractionShop', 'RevivalCost', 'XPCurve',
                       'GeometrySharingBlendIndices', 'CharacterLadderPaths', 'ObjectiveDescriptions',
                       'BreakRule', 'PlacementCrush', 'ObjectWorldImpact', 'DoubleHeal', 'DeathRule', 'NpcPowerRule', 'StunRule', 'DangerRoomParty', 'DangerRoomHealthBars', 'ResistanceDisplay', 'BoxHarmOrigin', 'HarmSingleChain', 'HarmLoopStartup', 'ConfirmationRelease',
                       'OnlineConversations', 'PersonalItemPicture', 'ComboPopupGuard', 'ClassicHud', 'ClassicHudPilot', 'ClassicCodex',
                       'ExplosiveFirstHit', 'PackAmount', 'SoloMode', 'X1Leader', 'DeathSwitchClear', 'RankCosts', 'LevelSkillPoints', 'LevelStatPoints', 'Xml1Multipart',
                       'Xml1MasterMold', 'Xml1MoldStage', 'Xml1Turrets', 'Xml1LockOnEffects', 'Xml1LockOnAim'),
              'Limits': ('ActorSlots', 'ResourceNames', 'ItemEnhancements', 'FightStyles', 'EffectCurves', 'MoveTriggers', 'EntityCapacity',
                         'ScriptFunctions'),
              'Online': ('GameVersion', 'ContentFingerprint', 'FastTransfer', 'ReceiveValidation', 'JoinInProgress', 'TickRate'),
              'Save': ('Format',),
              'Engine': ('ModelPools',),
              'Xml1Turrets': ('Count',) + tuple(f'T{i}' for i in range(1, 33))}


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
        # xml2-fix [Game] RevivalCost (issue #63): a fallen hero costs the first game's 200 * (highest roster level)^2
        # (default.xbe 0xaf6b0 / 0x54cb0), not XMen2.exe's max(200, 2 * level^2); shared gameplay agreement rule 10
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
    turrets = build_turrets(out) if postgame else {}
    if postgame:
        game.update(build_mold_controller(out))
        game.update(build_lockon_effects(out))
        game.update(turrets.get('Game', {}))
    keys = {'Game': game, 'Limits': dict(LIMITS), 'Engine': {'ModelPools': MODEL_POOLS}}
    if turrets:
        keys['Xml1Turrets'] = turrets['Xml1Turrets']
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


def check_release_dll(dll, keys: dict) -> None:
    """An existing companion DLL must know every required key the build writes (as check_entity_capacity_dll does
    for 1.4's): an older fix would run the build with those rules silently off. Source-only builds may omit the DLL."""
    dll = Path(dll)
    if not dll.is_file():
        return
    data = dll.read_bytes()
    missing = [f'[{section}] {key}' for section, names in RELEASE_18_KEYS.items() for key in names
               if key in keys.get(section, {}) and (key + ('\0' if key in EXACT_KEYS.get(section, ()) else '')).encode('utf-16le') not in data]
    if missing:
        raise FixTooOld(f'This build needs XML2 Fix {REQUIRED_XML2FIX} or later; the existing DLL does not recognize '
                        + ', '.join(missing), missing)


def old_fix_keys(dll, keys: dict) -> list:
    """every key of `keys` the existing companion DLL does not know ('[Section] Key'; [] without a DLL). Raises
    ValueError for a key set no DLL can run (EntityCapacity without Format=lc)."""
    missing = []
    for check in (check_move_trigger_dll, check_entity_capacity_dll, check_release_dll):
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
    missing = old_fix_keys(Path(out) / 'dinput.dll', keys)
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
    merge_ini(Path(out) / 'xml2-fix.ini', keys, dropped_keys(keys))
    return keys
