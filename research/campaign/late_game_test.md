# Late-game test: act 9, Asteroid M, the Master Mold finale, credits, postgame (2026-09-28 night)

First in-game run of the END of the XML1 campaign on XMen2.exe. Result: **the whole ending chain works** - Magneto's
defeat, the four Asteroid M zones, both Master Mold zones, Master Mold's death script, XML1's R501, XML1's credits (+ the
port block), xml2-fix `PostgameScript` -> r505 -> the XML1 main menu. Every act-9 mission start loads with XML1's forced
party. XPCurve=xml1 lands the objective XP exactly on XML1's table (31 -> 32 -> 33 -> 34). Three new bugs (credits `#`
overprint, black spikes on the elite Acolytes, and the XML2 Deadpool popup confirmed in game) and two already fixed
upstream but present in the tested build (New Game+ prompt after the win, difficulty prompt).

## Setup

- Build: `build/_late` = junctions to every subfolder of `build/_heroes` (Owen's play build, port b967f14, movies,
  `--frontend xml1`) + copies of its top-level files. `harness.py install build/_late --limits --dll
  scratchpad/dll/dinput_1c750e3.dll --pipe-name xml1-late --save-folder "X-Men Legends (late tests)"` -> windowed
  1280x720, ForcedTeams=1, PostgameScript=x1/menus/postgame, MainMenuItems, NewGamePlus=0 (not known to 1c750e3),
  XPCurve=xml1, [Limits]. Launched with `cmd /c start "" XMen2.exe` (pid 61780), driven only through pipe `xml1-late`.
- Driver: scratchpad `late/late.py` (fixinput + current_zone/conv_probe/hero_xp bound to build\_late's pid - the other
  agent's windows `_jh2`, `_jh2_b`, `_xml2stock` were running and were never read, driven or killed) and
  `late/walk_late.py` (tools/campaign_walk.py with the same pid binding, `--no-launch --restart-after 99`).
- Screenshots: the session's scratch folder `late\` (not kept)
  (below: `shots/NN_*.png`, `walk/shots/*.png`, `walk/campaign.md`, `xml2-fix_late.log` = the run's log).
- Cleanup: the game was closed with the menu's Quit (exit clean); the 22 junctions of `build/_late` (_build, Actors,
  Automaps, Conversations, Data, Dialogs, Docs, Effects, HUD, Maps, Models, MotionPaths, Movies, Packages, plugins,
  Scripts, Skybox, Sounds, Subtitles, Texs, Textures, UI) removed one by one with a non-recursive
  `[System.IO.Directory]::Delete(junction, $false)`; `build/_heroes` still has 21,391 files (counted before and after).
  `build/_late` keeps only its copied top-level files (exe, dlls, ini, log).

## Part 1 - act 9 mission starts (campaign_walk, 21:52-22:10)

`walk_late.py build/_late <scratch>/walk --from mansion8 --to asteroid_mm2 --zones --side-parent --no-launch`
(New Game from the XML1 main menu first; begin-body movies skipped by Enter). 0 crashes. Status ok 8, bounced 1,
party-mismatch 1 - both are the known briefing pattern of build/walk1 (the briefing's conversation starts the next
mission), not failures:

| mission | expected party | seated party | zone reached | status |
|---|---|---|---|---|
| mansion8 | magma | magma | mansion/man8/subbasement8 (+ hangar8, mansion8_1, mansion8_2) | ok |
| asteroid_briefing | magma | frost, iceman, storm, wolverine | briefing_3_9_8 -> asteroid1_1 (its conversation runs begin_asteroid_rock) | party-mismatch (expected) |
| start_astral3 | magma | magma | subbasement8b -> astral/savepx/astral2_1 (conversation starts astral3) | bounced (expected) |
| astral3 | team menu | magma (walk accepted the menu; a fresh New Game has few heroes) | astral2_1 (+ astral2_2, astral2_3) | ok |
| astral_sk (side) | profxgladiator | profxgladiator | final_astral; pushParty record 1 astral2_1/magma, popParty back to astral2_1/magma | ok, restored |
| asteroid_rock | frost, iceman, storm, wolverine | same | asteroid1_1 (+ asteroid1_2, asteroid2_1, asteroid2_2) | ok |
| asteroid_int | kept | frost, iceman, storm, wolverine | asteroid1_3 (+ 2_1, 2_2) | ok |
| asteroid_int2 | kept | same | asteroid2_3 (+ 2_1, 2_2) | ok |
| asteroid_mm | kept | same | mastermold/mastermold1 | ok |
| asteroid_mm2 | kept | same | mastermold/mastermold2 | ok |

Log (seat builds' functions): `seatParty("frost", "iceman", "storm", "wolverine") -> frost / iceman / storm / wolverine
(was magma / - / - / -)`, `pushParty("_ACTIVE_HERO_") -> pushsidemission 11009: record 1 of 2, astral/savepx/astral2_1
with magma`, `seatParty("profxgladiator", ...)`, `popParty("astral/savepx/astral2_3") -> restorelastzone 0 queued, back
to astral/savepx/astral2_1 with magma / - / - / - (record 1)`. XP after the walk: every hero 2,000,000 = level 26 (the
astral3 crystal objectives), ProfXAstral/ProfXGladiator 40 xpexempt - SPEC 23's expected value. The walk left the party
fighting Master Mold unattended; they died (the game-over dialog, Load Game / Main Menu,
`shots/10_asteroid1_3.png`) - a harness artefact; Main Menu -> the XML1 menu.

## Part 2 - the ending chain (22:10-23:03)

Fresh Begin Story (difficulty prompt, Normal), then `console runscript x1/missions/begin_asteroid_rock` (r302 skipped,
party seated) and `begin_asteroid_int`. Heroes were made invulnerable after each load (`setInvulnerable("_HERO1_".."4",
"TRUE")`, two pipe lines) so the scripted steps could not end in a game over.

| # | step | how | result | shots |
|---|---|---|---|---|
| 1 | Acts 1-8 + astral XP | scripted `awardXPToPlayable(8411600)` (levels.md 5: 5,411,600 + astral3 2,000,000 + astral_sk 1,000,000) | all 15 heroes 8,411,600 = **31** | 18 |
| 2 | asteroid1_3 -> asteroid2_1 | teleport `_ACTIVE_HERO_` to zone_link02 + E (played use) | "Command Center" loads, 4 heroes | 19-21 |
| 3 | control center objective | scripted `act("trigger_touch09", ...)` (touch trigger) | +2,500,000 -> 10,911,600 = **32** | 22 |
| 4 | meet Magneto | scripted `act("trigger_touch06", ...)` (touch trigger; its acttargets spawn Magneto, Mystique, acolytes) | 2_1_meet_magneto camera + conversation asteroidm/3_10_2 (voice, portraits) clicked through; boss bar "Magneto (40)" "Mental Resistant" | 23-25 |
| 5 | Magneto fight | ~10 s played (KP4/KP6), then scripted `killEntity("magneto")` | monster_deathscript **defeat_magneto ran**: magneto objective +3,500,000 -> 14,411,600 = **33**, conversation 3_10_2_5 | 26-27 |
| 6 | Lounge Deck A | teleport to exit_zone_2_1 + E (played use) | end2_1movie -> **r305** played -> asteroid2_2 (63 s) | 28-31 |
| 7 | Lounge Deck B | teleport to trigger_touch09 + E | enter_lastzone -> **r306** -> asteroid2_3; start2_3 camera shake + its conversation (no Magma in the party -> 3_10_3_2) | 32-36 |
| 8 | gravitron objective | scripted `act("trigger_touch15", ...)` | +5,000,000 -> 19,411,600 = **34** | 37 |
| 9 | Main Power Core | teleport to trigger_touch10 + E | enter_mastermold -> mastermold1, intro camera + drop-in Sentinels | 38-41 |
| 10 | mastermold1 -> 2 | a few s of combat, then scripted `act("end_spiders", ...)` x3 (its actcountact 3 = the three spider deaths) | begin_asteroid_mm2 -> **r503** -> mastermold2, "Master Mold (40)" | 42-46 |
| 11 | Master Mold's death | a few s of combat, then scripted `killEntity("mastermold")` | monster_deathscript **stage3death ran**: HUD off, MM breaks apart, 5 s, **R501** played in full | 47-50, 51_ending_sheet*.png |
| 12 | credits | not skipped | CREDITS_MENU `credits_end`: XML1's credits page by page, then the port block (X-Men Legends PC Port / Community project / Project ChronoRixun / Engine fixes xml2-fix) | 51_ending_sheet4/5 |
| 13 | win bookkeeping | Enter on a popup | **XML2's Deadpool-unlocked** popup (bug B1); settings.dat rewritten 22:47 (the win); no save file written (nothing had been saved in this session) | 51_ending_43 |
| 14 | postgame | none | xml2-fix PostgameScript -> Scripts/x1/menus/postgame.py -> **r505** "The Final Newscast" in full -> `mainMenuExit()` -> **the XML1 main menu** (menu/main_back) | 54_post_sheet*.png, 56 |
| 15 | after the win | Begin Story, Normal | XML2's New Game+ prompt (take the character statistics from a saved game) (bug B4, fixed upstream) | 57-58 |
| 16 | Review | menu | Cinematics: Asteroid M Blackbird, Sentinel Attack, Asteroid M Descent, Alison's Gravitron (r501), Mastermold (r503), Astral Titan, The Final Newscast (r505) all unlocked (15 of 35) | 60-62 |
| 17 | Quit | menu | process exits | 64-65 |

Log at startup (xml2-fix 1c750e3): `postgame: after the end credits (and the game's end-of-game save) the game runs
Scripts\x1\menus\postgame.py ([Game] PostgameScript) instead of loading XML2's act5/egypt/egypt6 - CREDITS_MENU's push
at 0x005B1CBF now points at "runscript x1/menus/postgame"`; `xp curve: X-Men Legends 1's levels ([Game] XPCurve=xml1)
...`. Nothing was logged between `killEntity("mastermold")` and the main menu (no error, no warning).

XP check (XML1 T1: 31 = 7,557,660, 32 = 10,357,460, 33 = 14,183,785, 34 = 19,410,055, 35 = 26,544,400): every value
above lands on XML1's level; the whole roster (bench included) got each award, as XML1's roster award does; the end of
act 9 at 34 matches levels.md section 5 (20.4M cumulative -> 34; this run skipped asteroid_rock's 1,000,000 gatherinfo
and end_goons_defeated's setXP 1,125,000 top-up). Magneto and Master Mold show level 40. Kill XP was not exercised.

## Bugs

**B1. XML2's Deadpool-unlocked popup after the credits** (seen, `shots/51_ending_43.png`).
Data/strings id 1194 (XML2's string, kept by the port), shown by the end credits' win step (CREDITS_MENU state 3, the
0x5b1d44 area that also unlocks Hard) before the save + PostgameScript step; the credits stop until Enter. Already on
the queue as "drop XML2's Deadpool line for the port" (HANDOFF overnight block, xml2-fix small items). Deadpool is no
port hero, so only the popup is visible. Fix in xml2-fix next to postgame.cpp (skip the popup / the unlock when
PostgameScript is set), or retext id 1194 in the port (less clean: an empty popup would remain).

**B2. Credit lines with `#N` are drawn overprinted** (`shots/51_30_crop.png`: "NYC Acolyte #1, Shadow" shows as a
garbled "Shadowlyte", "Soldier #4, NYC GRSO" as an overprinted "NYC GRSO", "Demon #1" and "Computer Voice #1" lose the
number). 21 of XML1's credit lines have `#`. Cause: XMen2.exe's menu text renderer (0x5ef2e0) reads `#NNN` as a code
(3000+N) (research/input/prompts.md section 2); `|c` is its literal escape. Fix: `frontend.credits_tree` (SPEC 21.4)
writes `#` as `|#` (and `~` / `|` the same way); V17 check "no bare `#` / `~` in credit texts". XML2's own credits have
no `#`.

**B3. The elite Acolytes render with huge black spike polygons** (asteroid2_1, the Magneto room; `shots/23_crop.png`,
`shots/25_crop.png`). Characters AcolyteEnergy_B (skin 18805, "Acolyte Elite") and AcolyteLeader_B (skin 18808,
"Acolyte Master Elite"), both on anim DB `48_acolyteenergy` (43 KB); the red/yellow bodies are fine, large flat black
triangles stick out of them (in the conversation camera too). Looks like skinned vertices bound to bones the skeleton
doesn't have (or a broken cape mesh) in the character conversion (characters.py / the skin +14000 path). Not checked:
whether the non-elite Acolytes (18801-18804) or the other _B skins (18806 Smash_B, 18807 Mental_B) show it; compare
18805 with XML1's 4805 in a model viewer. Magneto's cape and the heroes are fine.
*Follow-up 2026-09-29 (branch skin-fix, research/characters/skins.md, SPEC 25):* the skins are sound and unchanged
by the pipeline but for the rename; the byte-identical 18805 drew correctly in seven build/_skins sessions (this
path, the late path, a 17-zone session, a main-menu round trip, CPU skinning, r302, DLL 1c750e3). Not reproduced -
a runtime state of this session; validator V20 now checks every XML1 skin against its anim DB.

**B4. After a Normal win, Begin Story shows the difficulty prompt and then XML2's New Game+ prompt** ("Use default
statistics / Use saved game statistics", `shots/58_begin_after_win_normal.png`). Fixed upstream but not in the tested
build: port 1af3657 (Begin Story = `resetgame;runscript setDifficultyLevel(1)`, no prompt) + xml2-fix 723e592
(`[Game] NewGamePlus=0`); the harness already writes NewGamePlus=0, which DLL 1c750e3 ignores. Re-check on the rebuilt
play build: finish -> Begin Story must start nyc1_1_1 directly.

**B5 (cosmetic, faithfulness).** (a) The credits roll over XML2's credits backdrop (`UI/menus/credits_end`: igb
`x2m_credits`, image `textures/loading/credits01`, a collage of XML2's heroes); XML1 has its own credits menus
(`xml1_assets/packages/generated/maps/package/menus/credits_end.fb`, `credits.fb`). (b) Review > Stats lists Act 1-5
(XML2's acts); XML1 has 9.

**Harness note (not a port bug).** The window ran at 6-20 fps while three other game windows were up (`status`: "fps
6.0 ... 20.7"), and the movies played 3-6x slower than real time (R501, 110.9 s, took ~11.5 min; r503 49.5 s ~2.5 min;
r505 81 s ~15 min incl. a 2-min stall around the main-menu load when the pipe got no frame for 3 s). Audio wasn't
checked. Re-check movie speed at 60 fps. No subtitles were drawn under R501 (the subtitle option was not checked).

## Scripted vs played

- Played: New Game from the XML1 menu, the four "use" transitions (zone link, Lounge Deck A/B, Main Power Core - teleport
  next to them, then E), every conversation (clicked through), the mastermold1 intro, all movies (r305, r306, r503,
  R501, r505) and the credits in full, the popup, the return to the menu, Review, Quit.
- Scripted: mission starts (`console runscript x1/missions/begin_*`), the pre-act-9 XP (`awardXPToPlayable`),
  invulnerable heroes, the three touch triggers (`act(trigger_touch09/06/15)`), the spider count (`act(end_spiders)` x3),
  both boss deaths (`killEntity`) - the deathscripts themselves ran as the engine's own monster_deathscript.

## Still needs a human playthrough

1. The Magneto fight as designed: acolyte kills -> shield1remover / stage2 -> Sabretooth -> stage3 -> Mystique ->
   stage4/5, magneto_pain's 25% thresholds and `magshield`, the magneto_end_door; Magneto dying from damage.
2. The Master Mold fight: the three warp-core switches (core_on/off relays, 90 s), checkcore -> `shockshield_off`,
   mmpain's thirds (patterns mold2 / mold3, spawnsentinels), the catwalk breaking, Kincaid; death by damage -> stage3death.
3. mastermold1's Sentinel waves and the three spiders whose deaths act end_spiders.
4. asteroid1_1/1_2 content (gatherinfo, Mystique, end_goons_defeated's setXP top-up) and asteroid2_2's Havok run.
5. The end-of-game save (CREDITS_MENU state 4, `saveloadProcess(2)`) with a save slot in use: here no file was written;
   check what it does to Owen's slot and whether a post-game load works.
6. astral3 with a real 4-hero team menu (minheros 4) - the walk accepted Magma alone.
7. Kill XP along act 9 (XPCurve=xml1: half of each kill to every hero) - only objective XP was exercised.
8. Movie speed and subtitles at 60 fps; B1-B5 after their fixes.
