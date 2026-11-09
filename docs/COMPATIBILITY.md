# Versions that go together

A build records the xml2-fix version it needs (`_build\stamp.json`, `requires`). With an older fix the game may still
start, but the new keys do nothing: a 0.2.0 build without XML2 Fix 1.4 has no saves of its own format and none of the
combat, menu, capacity or Master Mold changes. From 0.2.2 a build that finds an older `dinput.dll` in its folder warns
and names the settings it doesn't know; for some keys (the save layout, the economy, the raised limits) the builder
refuses an older DLL by name instead. The launcher installs the latest fix after each build and each time it starts
the game.

Co-op: every PC needs the same builder / fix pair and the same settings; a mismatch is refused with the reason on
both PCs.

| Builder | Content | Needs xml2-fix | Launcher | Adds |
|---|---|---|---|---|
| 0.6.0-beta.5 | 34 | 1.11.0-beta.4 | 0.5.0, Beta channel | Sewer progression, optional Nuke doors and rank gates; catalogue 8 / LC44; beta.1–4 and RC1–3 saves load; matching peers required |
| 0.6.0-beta.4 | 33 | 1.11.0-beta.4 | 0.5.0, Beta channel | Arbiter hatches/rescue, emitter lifetime, temporary control, loaded services and restart leave notice; catalogue 8 / LC43; beta.1/2/3 saves load; matching beta.4 peers required |
| 0.6.0-beta.3 | 32 | 1.11.0-beta.3 | 0.5.0, Beta channel (Classic conversation box offered for builder >=0.6.0-beta.3) | optional conversation background (default off); lost-newcomer notice, solo-host pause and Enter IP polish; occupied-seat restart barrier; catalogue 8 / LC42; beta.1 and beta.2 saves load; matching beta.3 online peers required |
| 0.6.0-beta.2 | 31 | 1.11.0-beta.2 | 0.4.0 or later, Beta channel (0.5.0-beta.4+ sends `--classic-conversation off`, accepted) | the classic online screens (Game Options, the name and IP keyboards with keyboard, controller and analog stick, Other ways, LAN host / join / list, Connect by IP, the pause player list); the host's frame rate for the whole session (rule 29 revision 2, `[Online] TickRate=60` the hosting ceiling); the first game's bosses leave impossible steps (rule 40 revisions; Blob attacks again); the 4-player host crash and the lost-newcomer pause fixed; catalogue 8 / LC41, 0.6.0-beta.1 saves load; a beta.1 game cannot join |
| 0.6.0-beta.1 | 30 | 1.11.0-beta.1 | 0.4.0 or later, Beta channel | the game's own Play Online screens and fonts (Host, Join by code, Browse, lobby, Party; `[Online] Menus=1`; `--online-menus off` keeps the original menus); joining a game in progress at the host's next area (`[Online] LateJoin=1`; the host's DROP-IN row turns it off per room; rule 26 revision 7; a player's own `LateJoin=0` survives a rebuild); the 0.5 defaults unchanged; Guard held back (`--guard-decide off`); catalogue 8 / LC40; the DLL must be in the output folder before Build; a 0.5 game cannot join |
| 0.5.0-beta.1 | 29 | 1.10.0-beta.1 | 0.4.0 or later, Beta channel | the 0.4.2 line as defaults: the first game's items, shops and drops (`--loot xml1`, `[Game] Xml1Economy=1` with `Data\x1economy.txt`, rule 52), the bigger save layout (`--save-layout w2`: `[Limits] SaveLayout=w2`, `ItemEnhancements=4096`), limits wave 3 (`--limits-wave3 all`: rules 35 revision 2 and 53-62), Phoenix's telekinesis (`--telekinesis xml1`) and the flying carry (`--flying-carry xml1`); late-connected controllers (`[Input] LatePads`); the first game's Guard held back (`--guard-decide off`); catalogue 8 / LC38; refuses beta 8 and 0.4.0 |
| 0.4.1-beta.1 | 28 | 1.9.0-beta.1 | Beta channel | beta 8: the first game's bosses (`[Game] Xml1Bosses`, rule 40), moves (rules 38, 39, 42, 43, 46), Juggernaut's grab (`Xml1GrabCarry=xml1` with `Xml1FlyingCarry=0`, rule 45 revision 3), damage rounding (rule 41), raised limits (IGB cache, model handles, character sounds, motion pool, resident stats, animation enums) and the large-address-aware exe, the save-compatibility ledger rows, the GRSO style names, the classic objectives page; telekinesis, the XML1 guard decide and the flying carry off (next beta); catalogue 7 / LC37; refuses 1.8.0 |
| 0.4.0 | 27 | 1.8.0 | 0.4.0 for Online | online codes, public browser, drop-in on, solo watchers; the classic look (`[Game] ClassicHud=xml1`, `ClassicCodex=1`); the officer's weapon brain and rule 16 revision 10 (`[Game] NpcSemiAuto=xml1`), no small-map frame; every gun NPC's weapon brain with the XML1 bullet trace timer (schema 4 rows), rule 16 revision 11, one-sided walls in the XML1 zones (`[Game] WorldBackfaces=xml1`, rule 30) and the "Alison" label (`[Game] ClassicSpeakers=1`); the first game's revival price (XML2 Fix 1.8.0, rule 10 revision 3); catalogue 7 / LC36; matching peers required |
| 0.2.5 | 23 | 1.7.1 | | the bedroom items' pictures in the first game's picture window (`[Game] PersonalItemPicture=window`, #54); heroes re-stunned by every stun hit (`[Game] StunRule=xml1`, rule 18 revision 3, #101); catalogue 7 / LC32; both PCs need this pair |
| 0.2.4 | 22 | 1.7.0 | | Toad at HAARP (#105); coloured enemy resistance text (`[Game] ResistanceDisplay=xml1`); co-op conversations (`[Game] OnlineConversations=lockstep`, rule 27); catalogue 7 / LC31; both PCs need this pair |
| 0.2.3 | 21 | 1.6.0 | | hazard bounds and the opening fire's rhythm (`[Game] BoxHarmOrigin`, `HarmSingleChain`), floor-overlap crates (`ObjectWorldImpact`), two more fall volumes, the first game's gun-move priority, NpcPower revision 4, StunRule revision 2, visible Danger Room opponents with health bars and the original fallback party (`DangerRoomHealthBars`, `DangerRoomParty`), Sentinel scan effects and aiming, fast saved-campaign transfer (`[Online] FastTransfer`), received-message checks (`[Online] ReceiveValidation`); catalogue 7 / LC30; verified saved-zone prefix retention; co-op peers need 0.2.3 / 1.6.0 on both PCs |
| 0.2.2 | 19 | 1.5.0 | | the first game's rank costs and level points, breakable parts, leaders, solo mode, death below 1 health, the Xtraction services and Danger Room gate, the revival price, scan turrets, pack amounts, settling without crushes, no double heals, 1024 script functions, the death hand-over, enemy power use and combos (`[Game] NpcPowerRule`); co-op peers need 0.2.2 / 1.5.0 on both PCs |
| 0.2.0 - 0.2.1 | 18 | 1.4.0 | | the LC save format, the first game's combat balance, the entity capacity raise (768 generic / 1024 World entities), triggers per move, the Master Mold controller, explosions' first hit, the classic main menu, popup answers, the Xtraction shop, content fingerprint metadata and the shared gameplay agreement (co-op peers with different content or settings are refused, with the reason on both PCs) |
| 0.1.12 | 15 | 1.3.2 | | ladder descents, objective completion text, STAT pickups (`addStatPoints`), the first game's break rule, the effect curve pool, no Xtract world map |
| 0.1.8 - 0.1.11 | 11 - 14 | 1.3.1 | | fighting-style registry, enemy outlines |
| 0.1.6 - 0.1.7 | 8 - 9 | 1.3.0 | | conversation hooks, skill points, the item-enhancement pool |
| 0.1.0 - 0.1.5 | 2 - 7 | 1.2.0 | | |

0.4.0 betas: betas 1-4 content 24 / LC33; beta 5 content 25 / LC34 (the classic look, needs XML2 Fix 1.8.0-beta.5);
beta 6 content 26 / LC35 (the officer's weapon brain, rule 16 revision 10, no small-map frame, needs 1.8.0-beta.6);
beta 7 content 27 (every gun NPC's weapon brain, rule 16 revision 11, `WorldBackfaces` rule 30, `ClassicSpeakers`,
needs 1.8.0-beta.7).

Launcher: **0.4.0 or later for online play from 0.4.0 on**; the betas come through its Beta channel. The builder
manifest still has `min_launcher=0.0.0`; older launchers can build and use normal Play but do not provide the Online
panel. On Proton (Steam Deck, Linux), archive support needs 0.2.1 or later; 0.4.0 online/Deck acceptance remains in
the launcher checklist.

## XML2 Fix settings the builder writes

The builder writes these to `xml2-fix.ini` (`--no-ini` leaves the file alone). "Rule" is the shared-gameplay
agreement entry co-op peers compare (XML2 Fix's
[gameplay agreement](https://github.com/ChronoRixun/xml2-fix/blob/main/docs/gameplay-agreement.md)); "requested only"
means an absent, empty, off or `xml2` value omits the rule, and an invalid or failed requested install is unverified
(online refused). Both peers must match. The complete, current list is the code that writes it,
`tools/xml1build/fix_ini.py`.

| Key | Builder value | Purpose | Rule |
|---|---|---|---|
| `[Save] Format` | `lc` | the port's save format | |
| `[Balance]` | the first game's numbers | the first game's combat balance | |
| `[Limits] EntityCapacity` | `1` | rooms keep every prop, projectile and trigger (768 generic / 1024 World entities) | 1 |
| `[Limits] MoveTriggers` | `64` | every authored holster / redraw event and a flash and sound per gun shot | |
| `[Limits] EffectCurves` | `3600` | effect animation curves for busy zones and a four-hero party | |
| `[Limits] FightStyles` | `32` (`64` with limits wave 3) | the fighting / power style registry | 35 revision 2 with wave 3 |
| `[Limits] ScriptFunctions` | `1024` | script function names | 14 |
| `[Limits] IGBCache`, `ResourceNames` | `1024`, `2048` | the model file cache and its name table (beta 8) | 31, 32 |
| `[Engine] ModelPools` | `x4` | model handle and component pools (1.8.0-beta.2) | 28 |
| `[Game] Xml1MasterMold`, `Xml1MoldStage` | `1`, the stage binding from your disc's script | Master Mold's original fight | 3 |
| `[Game] ExplosiveFirstHit` | `1` | explosions' first hit | 2 |
| `[Game] ClassicMainBackdrop`, `ClassicMainPanelBounds` | `1`, `1` | the classic main menu | |
| `[Game] ConfirmationRelease` | `1` | popup answers | |
| `[Game] XtractionShop` | `1` | the shop at Xtraction points after meeting Forge | |
| `[Game] CharacterLadderPaths`, `ObjectiveDescriptions`, `BreakRule`, `Xtract` | `1`, `1`, `xml1`, `0` | ladder descents, objective text, the break rule, no Xtract world map (0.1.12) | |
| `[Game] GeometrySharingBlendIndices` | `1` | enemy outlines (0.1.8) | |
| `[Game] RankCosts`, `LevelSkillPoints`, `LevelStatPoints` | `1`, `xml1`, `xml1` | the first game's ranks and level points | 5 revision 3 |
| `[Game] Xml1Multipart` | `1` | breakable parts and boss armour | 6 |
| `[Game] X1Leader` | `1` | leaders | 7 revision 2 |
| `[Game] SoloMode` | `1` | solo mode | 8 |
| `[Game] DeathRule` | `xml1` | death below 1 health | 9 |
| `[Game] DangerRoomGate` | `button3` | Xtraction services and the Danger Room's story lock | 10 |
| `[Game] RevivalCost` | `xml1` | the first game's revival price | 10 revision 3 |
| `[Game] Xml1Turrets` + `[Xml1Turrets]` | `1` + the placements from your disc | scan turrets | 4 revision 2 |
| `[Game] PackAmount` | `xml1` | quarter packs | 13 |
| `[Game] PlacementCrush` | `xml1` | settling without crushes | 11 |
| `[Game] DoubleHeal` | `0` | no double heals | 12 |
| `[Game] DeathSwitchClear` | `1` | the death hand-over | 15 |
| `[Game] NpcPowerRule` | `xml1` | XML1 power decisions, combo timing, reaction-spent combo steps, the brain running through locked moves (power re-checks made inside attacks and powers) and XML1's block rule | 16 revision 11 (XML2 Fix 1.8.0-beta.7; revision 10 in beta.6, 4 before; 14 from beta 8) |
| `[Game] NpcSemiAuto` + `[NpcSemiAuto]` | `xml1` + rows from your disc | XML1's weapon brain for every gun NPC (20 schema 4 rows since 0.4.0-beta.7; the HAARP officer only in beta 6), rows derived from your XML1 data | 16 revision 11 |
| `[Game] ObjectWorldImpact` | `xml1` | XML1 landing-impact coefficient | 17 |
| `[Game] StunRule` | `xml1` | original party stun playback / recovery and per-hit re-stun | 18 revision 3 |
| `[Game] DangerRoomParty` | `xml1` | original incomplete-course four-hero fallback | 19 |
| `[Game] Xml1LockOnEffects` | authored triple | scan, surface and acquired-target visuals | |
| `[Game] Xml1LockOnAim` | `1` | animated-head targeting | 20 |
| `[Game] BoxHarmOrigin` | `xml1` | hazard bounds | 21 revision 1, requested only |
| `[Game] DangerRoomHealthBars` | `xml1` | Danger Room opponents' health bars | 22 revision 1, requested only |
| `[Game] HarmSingleChain` | `single` | hazard rhythm | 23 revision 1, requested only |
| `[Online] FastTransfer` | `1` | fast saved-campaign transfer | 24 revision 1, requested only |
| `[Online] ReceiveValidation` | `1` | rejects malformed network messages before their handlers run (local only, no wire change) | |
| `[Online] JoinInProgress` | `1` | drop-in co-op (XML2 Fix 1.8): start alone, joiners come in at the next level change | 26 |
| `[Online] LateJoin` | `1` (0.6.0) | admits a player who joins after the host pressed Start, at the host's next area; the host's DROP-IN row turns it off per room, and a tester's own value survives a rebuild | 26 revision 7 (host's choice) |
| `[Online] TickRate` | `60` | online sessions at 60 frames a second (`30` for slow PCs: then everyone in the session sets 30) | 29 |
| `[Game] OnlineConversations` | `lockstep` | online, a conversation line that goes on by itself does so \|timeDelay\| seconds of game time after it appears, on every PC on the same frame, and a chosen reply's voice is cut; single-player is unchanged. Absent or `stock` keeps the 1.6.0 behaviour. | 27 revision 1, requested only |
| `[Game] PersonalItemPicture` | `window` | the bedroom items' pictures in the first game's 256x128 window (engine display only) | |
| `[Game] ResistanceDisplay` | `xml1` | coloured resistance text | |
| `[Game] ClassicHud` | `xml1` | the classic look | |
| `[Game] ClassicCodex` | `1` | the classic Codex | |
| `[Game] ClassicObjectives` | `1` | the pause menu's Objectives page as in the first game (beta 8; display only) | |
| `[Game] ClassicSpeakers` | `1` | XML1's "Alison" label on the party Magma's ex-`%ALISON%` lines (portrait and talk animation stay Magma's; display only; 0.4.0-beta.7, XML2 Fix 1.8.0-beta.7) | |
| `[Game] WorldBackfaces` + `[WorldBackfaces]` | `xml1` + the converted XML1 zones | XML1's one-sided level walls for movement, in the XML1 levels only (XML2-origin maps keep XML2's); 0.4.0-beta.7, XML2 Fix 1.8.0-beta.7 | 30 revision 2 |
| `[Game] LiftRule`, `Xml1WallCling` | `xml1`, `xml1` | the first game's lifts and wall cling (beta 8) | 38, 39 |
| `[Game] Xml1Bosses` | the bosses the DLL can run | the first game's boss brains (beta 8) | 40 |
| `[Game] Xml1Economy` | `1` (0.5) | the first game's item economy, with the `Data\x1economy.txt` sidecar | 52 |
| `[Online] ContentFingerprint` | the build's 64-hex save-file fingerprint | content fingerprint for the shared gameplay agreement | |

Builder 0.2.3 / XML2 Fix 1.6 carries newly appended hazards through online saved-campaign transfer (co-op protocol 4;
XML2 Fix 1.5 and older peers are refused). HUD dirty-stat refresh/clamp timing parity remains unproved.

## Test mode (optional, offline only)

| Key | Default | Purpose |
|---|---|---|
| `[TestMode] ForgeEverywhere` | off, unwritten | Forge at Xtraction points |
| `[TestMode] Hotkeys` | off, unwritten | F8 clears eligible enemies, F9 toggles party protection, F10 returns to the nearest safe authored start |

Either switch blocks hosting and joining until both are off and the game restarts. F8 may skip script-referenced
actors; F10 refuses an unsafe destination. Saves made with testing tools retain their gameplay effects. See the
companion [testing guide](https://github.com/ChronoRixun/xml2-fix/blob/main/docs/test-mode.md).
