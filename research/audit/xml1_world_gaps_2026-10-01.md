# XML1 world-side compatibility audit (2026-10-01)

Scope: scripts, zones and entities, conversations and dialogs, missions / objectives / zoneinfo, HUD and menus, items and
pickups, music and sound hooks, the rest of XML1's data tables. Combat, stats, power styles, talents, effects and AI are
the other half (Fable agent) and appear here only where a zone or item attribute leads into them.

Inputs: build/_w4 (content version 6, XMen2.exe there), its `_build/*.json` reports, XML1 sources (`xml1_loose`,
`xml1_assets`), XML2 retail (`<XML2 folder>`, read only), `research/scripts/xml2_text.asm` /
`xml1_text.asm`. Addresses are XMen2.exe VAs unless marked default.xbe. No game text is quoted; identifiers only.

## 1. Ranked findings

Impact: how much a player loses and how early. Effort: XS < 1 h, S = a day, M = a few days, L = a week or more.

| # | Impact | Where (first met) | Player-visible symptom | Evidence | Fix sketch | Effort |
|---|---|---|---|---|---|---|
| 1 | High | 151 conversations (939 lines) whose `startCondition` has `runwithoutuser`, plus 530 line/response flags in 51 more; mansion1a_1 / 1a_2 on the first mansion visit, then every mansion hub, Muir, astral, Weapon X, arbiter | XML1's hands-free tour and walk-and-talk lines and cutscene chains need Enter after every line; a line sits until the player presses Enter, long after its voice has finished | XMen2.exe has no `runwithoutuser` string; parser 0x458820 / 0x459860 never reads it. The update 0x45d1a0 advances only on accept, and `timeDelay` (+0x80 -> CS+0x239a8) is never read (conversation-speakers.md section 0). XML1 parses it (default.xbe 0x619a6 line flag, 0x62788 startCondition +0xf0). **In game (this audit):** the mansion1a_2 entry tour line and mansion1a_1's `1_2_24_5` (both flagged) held the same line_id for 20 s, voice done, until Enter | xml2-fix hook (the design in conversation-speakers.md section 9 item 1): read the flag at parse into spare bit 0x10 of node+0x7c (lines) and a spare startCondition byte; in 0x45d1a0 auto-accept when the line is flagged (or its startCondition is) and exactly one response is visible, once the voice handle has stopped or a builder-written `timeDelay` has elapsed. The builder writes `timeDelay` = voice length + pad on flagged lines so the hook has a fallback | M |
| 2 | High (balance) | `SKILL` pickups in haarp_ext03 (act 1), sewers3_1_3 (act 7), hive2_2_4 (act 8) | One skill-point pickup gives every roster hero 5,000 XP; on XML1's curve that is level 1 -> 9, or several levels at act 1 | Data/items `SKILL` onactivate = `awardXPToPlayable(5000)` (SPEC 11.3 / 23.1 stand-in, "XMen2.exe has no skill-point call"); XML1 item type `skill` = one free skill point for the picker. **In game (this audit):** `awardXPToPlayable(5000)` on a fresh profile: every roster hero read went level 1 -> 9, XP 0 -> 5000 (tools/hero_xp.py, XPCurve=xml1) | Interim, data only: `setXP('_ACTIVATOR_', n)` with n of about one XML1 level at the zone's expected level (haarp_ext03 ~1,000; sewers3_1_3 / hive2_2_4 from levels.md), picker only. Proper: an xml2-fix script function (like `seatParty`) that adds unspent power points to the actor's stats | XS / S |
| 3 | Medium-High | 245 voiced responses in converted conversations (XML2 retail: 6); mansion hubs first (Magma's spoken replies to Rogue, Iceman, Storm, Jean, Beast, Nightcrawler ...) | The hero's spoken reply is cut off at once; only the NPC's answer is heard | 0x45d5d0 -> 0x458700 starts the response voice and marks it pending; the next frame 0x45d242-0x45d27d stops it if still playing (audio vt+0x74), then advances. **In game (this audit):** `1_2_37` reply menu, Enter on a voiced reply: line 66 -> 67 within the key press (< 0.1 s), voice handle 0x11 -> 0x13 (0x12, the reply's voice, replaced before the first sample) | xml2-fix: in the pending branch at 0x45d242 return while vt+0x60 (voice playing) is true instead of stopping (conversation-speakers.md 9 item 2). Data-only alternative: move each reply's voice onto an inserted line before the child line; costs pool space (40 lines per file, largest XML1 file 27 lines + 31 responses) | S |
| 4 | Medium | 12 scan turrets in 8 zones: haarp_ext02 / 04 (tank missile turrets, act 1), hive1_1_1 (flame turret), arb2_2, arb2_3, arb3_2 (tripod MGs), wx1_3 | Turrets never aim or fire; they are destructible props that still gate progression | Remapped `scanturretent` -> `physent` (x1schema CLASS_REMAP_LOSSES: turretweapon, turnrate, turndelay, resetdelay, yaw/pitch/visextent, rotatesound unread); no "turret" string in XMen2.exe | Remap to XML2's own autonomous turret `sentryent` (registered 0x67ad25, parent physent; retail use: `ents_ironman iron_p5_turret`, `ents_phoenix p7_guardian` with `projectileent`), firing a projectile entity built from the turret weapon (as weapons.py does for the freeze / knockback guns), team enemy, no lifetime. Needs RE of sentryent's target and team selection and of how it treats `lifetime` | M-L |
| 5 | Medium | `enterSoloMode('_ACTIVATOR_')` triggers in 18 zones, first met in icetunnel1 / 2 (act 1), then sewers1_1_4, nyc3_2_2, sewers3_1_3, nuke1_2..2_2a, arb3_2..3_4, hive2_2_4, astral1_2 / 1_3 / 2_2 / 2_3 / 3_4 | XML1 parked the AI allies while the leader crossed (12 of the 18 zones have `powertriggerent reactpower="bridge"` puzzles; the 5 astral zones and nuke1_3 use moving platforms); in the port nothing stops the allies following the leader (consequence not yet seen in game) | Call removed by rewrite_scripts (DROP table); XML1 0x9eef0 -> 0x33a70 toggles solo on each non-activator hero. XML2 keeps a SOLO input (action registry id 0xa, 0x553be7) but repurposes it as Regroup (Data/strings 193 / 194); no script entry point | First an in-game look at one bridge (icetunnel1) with a 4-hero party to see whether the allies actually fall or block. If they do: an xml2-fix `enterSoloMode / exitSoloMode` pair (AI allies hold position; restore on zone change / exit), or data only: `moveHeroesToEnt` to a safe marker on bridge completion | M |
| 6 | Medium-Low | Every zone with random drops; the Xtraction menu | XML1's loot table (116 equipment items, 5 drop groups, `frequency`, 10 `grabbag` uniques) never drops; drops come from XML2's pool. XML1's item shop (99 items with `cost`) is absent, so money has no use | SPEC 11.3: only referenced XML1 items are added, "XML2's random-drop pool is unchanged"; SPEC 12.4 defers the Xtraction shop. `frontend.translate_equipment` already converts XML1 equipment (`activepowerup` -> `enhancement`) for the 19 Danger Room rewards | Run `translate_equipment` over all 116, map `group` 1-5 to `enemy_level` bands by act, carry `unique`; decide whether XML2's own random equipment stays in the pool. Shop: `shopMenu` exists (XML2 scripts call it); offer it from the XML1 Xtraction menu or the mansion | M |
| 7 | Low-Medium | 57 XML1 conversations whose reply menu is re-entered by `tagjump` with responses hidden by `disallowResponseOnVar` (mansion hubs, Muir, sewers hub, nuke puzzles) | Coming back to a hub menu, nothing is highlighted and Enter does nothing until Up/Down is pressed | 0x45b5f1-0x45b5fc stores `sel = visibleCount` (conversation-speakers.md 8 item 3); XML2 retail has the same pattern in 35 conversations, so this is an engine bug that XML1's hub-menu style hits far more often | xml2-fix one-instruction patch at 0x45b5fc (store count-1 or 0) | S |
| 8 | Low | Per-zone music in 9 campaign zones (arb2_2, arb2_3, sewers1_1_2, sewers1_1_4, sewers1_2_1, sewers1_2_3, sewers2_1_2, sewers2_1_3, subbasement8b) and 7 demo copies | The zone bank's default ambient / combat track plays instead of XML1's override (for example the Morlock or arbiter combat themes) | `ambientmusic` / `combatmusic` / `intromusic` are not XMen2.exe strings; zones defers them (`zones_detail.json music_overrides`) | media: build the zone's `_a` / `_c` bank from the override track, or give the zone the soundfile of a twin zone whose banks carry that track | S-M |
| 9 | Low | nuke1_1..1_4 (6 spawners, `monster_grenade="flashbang"`); every XML1 GRSO weapon's `grenade=` choice | Grenade-throwing soldiers throw the moveset's default grenade instead of the flashbang / incendiary their weapon or spawner names | The spawner forwards `monster_grenade` (0x4633b9) but the only reference to "grenade" (0x686bf4) is that forward list: no actor reader. XML1's `moveset_grenade` takes the entity from the weapon (weapons.eng `grenade=`) | Handed to the combat half: weapons.py could set the `grenade_projectile` trigger's `entity` per weapon variant, and zones could pick a variant per spawner override | S |
| 10 | Low | 39 objectives with `updatedescription`, 2 with `required="false"` | No XML1-specific completion text; XML1's two optional objectives are written `major="true"` like the required ones | mission_plan.py drops both ("XML1-only attrs (updatedescription, required) are dropped"); XML2's objective schema has neither | `required="false"` -> `major="false"`, if XML2's `major` means what the name suggests (check the HUD list). The completion text can only come from a script `display`-style call, and XML2's `display` is a stub (0x5aaff0) | XS |
| 11 | Low | mansion4_1, conversation `mansion/man4/2_5_10b` | The conversation ends early at the response whose `tagjump="2_5_10loop"` targets a tagIndex that is in another file | conversation-speakers.md 8 item 4; still unresolved in build/_w4 (the file has no tagIndex at all) | Copy the target line (and its subtree) from the conversation that holds `2_5_10loop` into 2_5_10b, or point the jump at the equivalent local line | XS |
| 12 | Low | `STAT` pickups in 5 zones (arb2_1, asteroid2_2, nuke2_2, nyc3_2_2, sewers3_1_3) | XML1's free stat point (player's choice) becomes a fixed body boost | Data/items `STAT` onactivate = `permanentStatBoost('_ACTIVATOR_','body')` | If the xml2-fix function of #2 is written, give it a stat-point twin; otherwise keep | XS (with #2) |
| 13 | Low | 3 popup dialogs with `debounce="0.75"` | XML1's input guard on those popups is gone; an Enter held from the previous screen can dismiss them at once | `debounce` is not an XMen2.exe string | Drop, or bump the dialog to open after a `waittimed` in its script | XS |

## 2. Details

### 2.1 runwithoutuser (finding 1)

Counts in the build (XML1-sourced conversations only): 151 conversations carry `startCondition runwithoutuser="true"`
(939 lines, 86 of them with `enableAI`, 44 one-line), and 51 more conversations carry the flag on 530 lines / responses.
By area: mansion/man1a 36, man3 25, muir2 16, man4 15, man5 9, man6 5, astral/ast1 4, dr_mag2 4, then 1-3 each in
man2, man7, man8, muir3, nuke, weapon_x (old, secret, wfb), jugrnt, mount, arbiter 1_7_7_*, nyc (alison, fb, riots),
sewers (healer, hub) and `common/enemies_around`.

The one-line `enableAI` conversations are XML1's walk-and-talk: a touch trigger runs a script that starts the line
while the tour continues (e.g. mansion1a_2 `trigger_touch09` -> `mansion/man1a/conv_1_2_12`, gated on the touring
flag). On XMen2.exe each becomes a dialog box with `[Enter] done` that waits for accept.

What XML1 did with the flag at run time was not traced (the startCondition byte +0xf0 written at default.xbe
0x627f8 has no direct `byte ptr [reg + 0xf0]` reader in the conversation code; it is probably copied into the running
conversation's state). The behaviour difference is established on the XML2 side only: XMen2.exe never auto-advances.

In-game run (build/_w4, harness pipe w4, windowed, about 90 s; scratchpad driver `conv_driver.py`, frames
`01_rwu_t6.png`, `04_resp_menu.png`): conversation-system probe (tools/conv_probe.py) every few seconds for 20 s after
the entry conversation of mansion1a_2 started: `active` true, the same `line_id`, voice handle unchanged; the first
Enter ended it.

Fix notes: the hook must leave reply menus alone (auto-accept only when one response is visible), keep the 1 s accept
lock-out (CS+0x21b5c) semantics, and not fire while a cutscene camera script is still moving (the `*_cam_start`
condition scripts run once at start, so this is safe). A `[Game]` key in xml2-fix.ini keeps XML2 retail unaffected
(XML2 has 7 flagged lines and 4 flagged responses of its own; they would start auto-advancing too).

### 2.2 SKILL pickup (finding 2)

XML1 `data/items.eng`: `SKILL` type `skill` ("free skill point"), `STAT` type `stat`, `XP` type `xp`. The XP pickup was
converted faithfully (SPEC 23.1: `setXP('_ACTIVATOR_', count)`, XP to the picker, 0x4a8660 -> 0x422350). SKILL kept
the roster-wide `awardXPToPlayable(5000)` stand-in in both XP modes. With `XPCurve=xml1`, XML1's level table is 830 XP at
level 5 and 6,880 at level 10 (research/heroes/levels.md section 4), so at haarp_ext03 the stand-in is worth several
levels to every hero, the bench included.

In-game run (scratchpad `xp_driver.py`): fresh profile, nyc1_1_1, `tools/hero_xp.py` before and after
`awardXPToPlayable(5000)`: every hero in the printed rows (Beast, Colossus, Cyclops, Frost, Gambit, Iceman, Jubilee,
Magma, Nightcrawler, Phoenix, Psylocke; the driver printed the first 12 rows only) went from level 1 / 0 XP to level 9 /
5,000 XP (ProfXAstral is xpexempt).

The skill-point field was not located (engine.md section 4 maps the CStats level / XP block at CStats+0x1c; the
unspent-points counter should sit near it, unverified); an xml2-fix function `addSkillPoints(actor, n)` registered the way the forced-team functions are (SPEC 19.1) is the
clean fix. Until then, a picker-only XP amount sized to one XML1 level at that point of the campaign is closer than
5,000 to every hero.

### 2.3 Voiced responses (finding 3)

245 voiced responses in the build's conversations; XML2 retail has 6 (Storm / Frost), which is why the cut never
showed in XML2. In XML1 the responses are mostly the player character speaking her choice in the mansion hubs.
In-game (scratchpad `conv_driver3.py`, frame `07_after_voiced_resp.png`): mansion1a_1, `startConversation` of
`1_2_37`, Enter through the opening line, then Enter on the first of four voiced replies: the probe's first sample
after the key press already shows the child line (66 -> 67) with voice handle 0x13 and no pending response. Voice
handles are allocated in sequence (the opening line had 0x11), so 0x12 was the reply's voice and lived less than the
key press (80 ms) plus one probe. The audio itself was not listened to.

### 2.4 Turrets (finding 4)

| zone | entities | XML1 weapon (data/weapons/weapons.eng) |
|---|---|---|
| haarp/ext/haarp_ext02, haarp_ext04 | 4 | `wp_tank_turret_haarp`: projectile, `missilelauncher_ents`, 3 per volley, range 900 |
| hive/h_ext/hive1_1_1 | 2 | `wp_tank_turret`: continuous flame, range 132 |
| arbiter/a_int/arb2_2, arb2_3, arb3_2 (+ demo arb3_2), weapon_x/wfb/wx1_3 | 6 | `wp_tripod_turret`: bullet, L4, range 600 |

They keep health, structure, deathscript and the fixed mount (SPEC 11.2, 12.3), so progression works; only the
threat is gone. XML2's `sentryent` is the nearest engine object (a physent child that spawns `projectileent` shots on
its own); the tracer / beam forms of weapons.py are style triggers on actors and do not apply to a non-actor. An
alternative that avoids sentryent RE: an invisible, invulnerable, immobile NPC (stats entry with the weapon variant
style, `nogravity`, `setNoClip`) spawned at the turret and removed by the turret's deathscript.

### 2.5 Solo mode (finding 5)

All 18 `trigger_solo` entities have the same form (`boxcollision`, `actontouch`, `actmatchteam`, `actleader="true"`,
`actinactivedelay="0.1"`). 12 of the zones hold 4-8 `powertriggerent reactpower="bridge"` puzzles (XMen2.exe parses
the type, 0x49a2dd, and names `tkbridge%d` / `icebridge%d` / `metalbridge%d`); the 5 astral zones (bridge platforms
moved by script) and nuke1_3 have none. Only the four astral bridge scripts call
`exitSoloMode`. XML1's toggle (default.xbe 0x33a70) walks the party and acts on every hero except the activator when
the party has more than one hero; what the others did (hold position, hide, or both) was not decompiled to the end.
XMen2.exe's SOLO action exists but its text calls it Regroup (string 193) and "call for help" (string 1126); no
script function reaches it. Whether XML2's ally AI makes the bridge puzzles worse (allies dropping into the gap,
blocking the bridge) needs an in-game look before any engine work.

### 2.6 Loot and shop (finding 6)

XML1 `items.eng`: 132 items; 116 equipment (`group` -1..5, `class` 0-2, `frequency`, `cost`, 48 `unique`, 10 `grabbag`),
3 money, health / energy packs, keycards, XTREME_PIP, and the XP / SKILL / STAT trio. The build's Data/items has 88
entries: XML2's 64 plus 24 referenced XML1 items (19 of them the Danger Room rewards). What XMen2.exe's random
drop actually rolls in an XML1 zone (XML2's named equipment, money, XML2's random enhancements) was not observed in
game.

### 2.7 Things noticed in passing

- A conversation line spoken by a hero who is neither in the party nor spawned in the zone drew a black portrait
  (the test party was Wolverine alone; Magma's reply menu in `1_2_37`). With forced parties on (ForcedTeams=1, Magma
  seated in the hubs) the campaign does not hit it; a `ForcedTeams=0` play would. The portrait needs the character's
  package loaded, which contradicts the "loaded whether or not in the zone" note in conversation-speakers.md table 0.
- 49 `script_ref_missing` and 12 `call_target_missing` zone problems are XML1 dead references (absent on both discs),
  including the `*_cam_start` condition scripts of several mansion conversations. The conversations still start
  (seen in game for `1_2_37`); only the camera move is missing, as on the Xbox.

## 3. Checked and found fine (or already handled)

- **Entity classes.** All 22 classnames in the converted zones are registered (`ent`, `actionent`, `gameent`, `physent`,
  `doorent`, `moverent`, `inventoryent`, `powertriggerent`, `affectableharment`, `projectileent`, `actor`, `tileent`,
  `playerstartent`, `waypointent`, `lightent`, `enabletargetent`, `monsterspawnerent`, `zonelinkent`, `waterent`,
  `cameramagnetent`, `scripttriggerent`, `worldent`). Hierarchy from the 0x461080 registrations: every class except `ent`
  / `worldent` derives from `actionent`, whose reader (0x41b930..0x41bf00) takes the whole `act*` family and the
  `act` / `spawn` prefix groups. So `actscript` on player starts, spawners, enable targets and harm entities is read.
- **Composed attribute names.** 0x467c20 builds `<prefix>script`, `soundloop`, `sound`, `soundradius`, `soundvolume`,
  `effect` for the prefixes `act`, `spawn` (actionent), `death`, `xdeath`, `pain` (0x498d9f..) and `deact` (0x4b356e).
  `xdeathscript`, `painscript`, `spawnsoundradius`, `deathsoundradius`, `actsound`, `acteffect`, `spawnsoundloop` are
  therefore read although they are not exe strings.
- **Spawner forwarding.** 0x463380..0x463850 forwards `monster_` + 60 actor attributes (team, aggression,
  guarddistance, aiforceranged, nopickup, acttargets, actondeath, fleedistance, willflee, aitype, randompickups, the
  prefix groups ...). Not forwarded: `monster_smartqnt` (1 spawner), `monster_startenabled` on an actionent (1).
  `grenade` is forwarded and never read (finding 9); `fleedistance` / `willflee` are read and unused (SPEC 12.5a).
- **World entity.** `gravity`, `astral`, `cold`, `startblack`, `nosave`, `level`, `act`, `zonescript`, `soundfile`,
  `skybox` are read by the world parse (0x4858fe..0x485a03; astral -> map vt+0x90, cold -> vt+0x9c). Whether anything
  reads `astral` / `cold` back was not traced (XML2 retail never sets them; cosmetic at most). XML2 ships XML1's
  `astralsky*` skyboxes and uses the attribute itself (genosha4).
- **Remaining XML1-only entity names** (not exe strings, not composed): `healthresist` (12 astral torches,
  nocollide, cannot be hit anyway), turret attributes (finding 4), music (finding 8), `loopfxtime` / `camerapos` /
  `deathstyle` (always empty), `qacttargets` / `healh` (XML1 typos, unread on the Xbox too).
- **Hint types.** Every XML1 `hinttype` / `setHintType` value (`objective`, `use`, `power`, `talk`, `usetoggle`,
  `objectivehide`, `importanttalk`) is an exe string (0x68774c..0x687798).
- **Puzzle reactions.** XML1 uses `extinguish` 105, `bridge` 85, `weld` 30, `charge` 6, `move` 2; all are parsed
  (0x49a236..0x49a331). Which converted hero moves trigger them is the combat half's question; worth one in-game puzzle
  check per type (weld has no XML2 retail user).
- **Scripts.** The lint is clean (0 problems, 14 allowlisted lines all in unreachable XML1 debug mission scripts).
  The dropped "legacy python" lines are only `def main` / `import` / `if __name__` (no `return` was ever dropped).
  `sound()` uses the same `PLAY_SOUND` form as XML2 retail; `screenFade` -> `cameraFade` keeps XML1's argument idiom
  (XML2 retail uses the same pairs); `display()` is a stub in both games (XML1 0x2123a0, XMen2 0x5aaff0); every
  `objective` / `getObjective` verb XML1 uses (`EOBJCMD_*`, `COMPLETE`, `COUNT`, `COUNT_GOAL`, `HIDDEN`) is an exe
  string; the XML1-only console commands (`beginmission`, `beginsidemission`, `endsidemission`, `changethememusic`,
  `optionscontroller`) are never named by data. Of the 31 XML1-only script functions, the unused ones (`getBody`,
  `getCount`, `levelUp`, `restartMission`, `soloModeCheck`, `displayHelp`, `magnetoBall`) need nothing;
  `setPowerStatus` (dr_mag1 tutorial), `xtremeConversationLight`, `removeFromGroup`, `setGroupLeader` (commented out in
  XML1) are dropped with little loss.
- **Conversation schema.** Element and attribute sets of all 983 built conversations equal XML2's apart from
  `runwithoutuser` (finding 1). Speaker tokens resolve (SPEC 12.1, V6).
- **Dialogs / popups.** Schema equals XML2's apart from `debounce` (finding 13); `hud="true"` and `scriptcancel` are
  read. Every controller token in XML1 tutorial texts (`$MENU_ACCEPT`, `$SMASH`, `$ATTACK`, `$GUARD`, `$MOVE`, `$POWER`,
  `$ALLY`, `$DPAD_UP`, `$SOLO`, `$TARGET_LOCK`, `$PAUSE`) is one XML2's own texts use.
- **Missions and objectives.** The installed Data/missions files have XML2's schema; `count` and `xp` carried.
- **Zone precache.** Every precache type in the converted zones (conversation, script, model, sound, fx, dialog,
  motionpath, effect, xml_resident, texture, fightstyle, subtitle, xml, actoranimdb) is one XML2 retail zones use.
- **World tables.** `item_ents` / `common_ents`: same names in both games, XML2's definitions win; differences are
  pickup sounds / effect paths only. Health and energy packs map to XML2's `potion` items with the same
  `restoreHealth` / `restoreEnergy(-1)` calls. Keycards and `XTREME_PIP` resolve.
- **Already handled elsewhere** (not re-audited): weapons (SPEC 29), automaps (26), Danger Room / Review / codex /
  trivia / credits (21), Xtraction network and town centres (12.4, 15), act on zone entry (12.7), mission animations
  (12.5), spawn loops (12.5a), extents (17), same-name NPCs (18), forced parties (19), unlock points (20), zone-package
  hero styles (28), entity value codes (29.2).

## 4. Not established

- XML1's runtime handling of `runWithoutUser` (no reader of the startCondition byte found; behaviour inferred from the
  name and from the tour design).
- What XML1's solo mode did to the other heroes, and whether XML2's ally AI actually breaks the bridge puzzles.
- What XMen2.exe's random drops produce in XML1 zones.
- How `sentryent` picks targets and team, and whether it honours a `lifetime` of -1.
- Whether anything reads the world `astral` / `cold` flags back.

## 5. In-game runs made for this audit

build/_w4 with the harness already installed (pipe `w4`, save folder "X-Men Legends (w4 tests)", windowed), launched
by `tools/gamedbg.py`, killed with `current_zone.kill_build` after each run; no other game process from build/_w4 was
running. Four short runs (about 1-3 min each): two for finding 1 / 3 (the first never left the menu: the Enter presses
came during loading), one for finding 3, one for finding 2. Drivers and frames are in the session scratchpad
(`audit/conv_driver*.py`, `audit/xp_driver.py`, `audit/game/*.png`). The game appends to `build/_w4/xml2-fix.log` as on
every run; nothing else in the repository was touched.
