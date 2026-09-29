# Forced parties online: can a player break them? (2026-09-29 06:20-07:13)

Question (port_online_test.md rec. 3, online_saves.md): during a forced stretch (Magma alone, Wolverine alone in
nyc1_1_1) can a player on standby (no hero) pull a hero into the party through Team Management or an Xtraction
Point's Change Team, and can a joiner choose Xtract / Change Team for the group? Also later, with more heroes unlocked.

## Answer

| # | Route | Before the fix | After (xml2-fix f06f2e2 + port 02d0e52) |
|---|---|---|---|
| 1 | Pause menu > Team Management, standby joiner, 9 heroes unlocked | **No.** The in-game team screen: party slots only, no roster, no Add/Replace for anyone (host or joiner) | unchanged |
| 2 | X-point > Change Team, opened by the host, standby joiner | **Yes.** The team menu opens for every player; the joiner's `[J] Replace` on an empty pad opens the roster and seats a hero: Wolverine alone -> **Wolverine + Gambit** | Change Team **greyed out**; Enter on it closes the menu, no team menu |
| 3 | Same menu, the host | **Yes.** The host replaced the forced Wolverine: -> **Iceman + Gambit** (same in single player) | greyed out |
| 4 | X-point opened by a joiner **with** a hero | The menu belongs to the joiner (the host's keys do nothing): **Change Team and Xtract for the whole group** (Xtract opened XML2's world map on both) | Change Team greyed out on both; Xtract / Save Game stay |
| 5 | Standby joiner opens an X-point itself | No: it has no hero to use it with | - |
| 6 | Free mission (control, after the fix) | - | Change Team enabled, the team menu opens |

All of it ran in sync on both windows (no desync from the team change). The break is not online-only: any player,
single player included, could swap a forced party at a **full** Xtraction Point inside a forced mission.

## Where it matters (static)

- XMen2.exe team menu modes (`[0x8b134c]`): bit 4 (roster pick) is set by `setblackbirdparms` (0x5f2674, which
  `extractionPointChange` 0x4a7020, `loadMapChooseTeam`, `blackbirdMenu` run) or by opening the menu outside a zone
  (0x5e3631); in a zone the pause menu's `opencharactersmenu` (0x5f1cd0) opens the party screen without the roster
  (0x5db690). Closing clears bits 4/8/0x10 (0x5e07dd). So route 1 can't add a hero, route 2 can.
- The pick (0x5e5280): an unlocked roster hero not in the party -> 0x5e3e90 into the player's slot; each connected
  player edits its own slot, a standby player gets an empty one.
- Standby popup 161 (0x59f58b) is automatic: players > party members for a while. XML2 has no "limited heroes" flag.
- XML1's X-points in XML1's forced zones:
  - `extractionPointLite('_OWNER_','false',...)` (weapon_x wx1_1/wx1_3/wx2_1/wx3_1/wx3_3, nyc_fb1/fb4, mag_nyc4,
    muir_in2, nyc1_1_2b, the mansion subbasements): the port keeps the first 4 arguments and XMen2.exe's Lite
    (0x4a6d80) adds Change Team only when its first flag is "TRUE" - **no Change Team there**. mastermold1/2 have
    'true' (asteroid_mm/mm2 are free missions; XML1 allowed it).
  - full `extractionPoint('_OWNER_')` (0x4a6b50 always adds Change Team) in zones of seated forced missions:
    **alison** (nyc1_1_3, nyc1_1_4; XML1 maxheros 2, REQUIRED Wolverine + Cyclops), **astral1** (astral1_1,
    astral1_2; 3 REQUIRED), **astral1b** (astral4_3; 2 REQUIRED), **asteroid_rock** (asteroid1_1; maxheros 4, REQUIRED
    Frost), **end_astral** (mansion_front5; Magma).
- XML1's own rule: its Xtraction team change kept REQUIRED heroes and maxheros (mission_plan.json: 49 missions).

## The fix

**xml2-fix f06f2e2** (branch display, local only; DLL scratchpad `dll/dinput_f06f2e2.dll`, md5 a221fe44...):
- With `[Game] ForcedTeams=1`, the DLL's copy of the script function table (the one forced_teams already registers)
  runs its own handlers for `extractionPoint` / `extractionPointLite` first: they read game flag `teamlock` bit 1
  (the script interface 0x4a1670 vt+0x54 = 0x4a0190, what `getGameFlag` uses) and write the Change Team option's
  `disabled` argument - `push 0` at 0x4a6ccd / 0x4a6fb8, the 6th argument of the dialog's addOption (vt+0x1c,
  0x5e97d0), the one the online Game Type menu uses to grey out Danger Room (0x5b93e4) - then run the game's handler.
- 9 new guards (110); ForcedTeams=0 or absent: the game's menu. Log: `forced teams: extractionPoint: the mission's
  party is fixed (game flag teamlock bit 1) - Change Team greyed out`.
- xml2_test **PASSED (0 failures)**: the decision, the table entries (175/176), the bytes, the table wrap.

**Port 02d0e52** (SPEC 19.8): seat builds set the flag at every mission start, right after its
`XML1 beginMission(m)` marker - 1 for the 46 seated forced missions, 0 for the rest (the `_onl` build: 77 lines with
1, 82 with 0, inlined copies included; the New Game hook gets alison's 1, a `--newgame chooseteam` hook 0) - and
before each seated side mission's `endSideMission` marker the caller's value (jug_fb / sent_fb / dr_mag1 /
wx_fb_start / muir2_reboot -> 1, astral_sk -> 0).

Why a game flag: it is part of the game's state - saved, streamed to joiners with the host's save, set by the same
scripts on every machine in lockstep - so every machine builds the same menu (the X-point dialog reads the owner's
net input on every machine; a per-machine switch could desync it).

Deviations / limits:
- asteroid_rock is locked whole at asteroid1_1 (XML1 let the player swap Iceman/Storm/Wolverine, Frost REQUIRED).
- Saves from before this change carry no flag: unlocked until the next mission start.
- Xtract (XML2's world map: act 1 lists XML2's "Genosha / Sanctuary") and the pause menu's Blink Portal still leave
  a forced mission for an XML2 town centre (zones section 15, pre-existing) - not part of this fix.

## Tests

Build `build/_onl` (main 59f7836 + the fix; `--no-movies --frontend xml1`), a junction copy `build/_onl_b` (removed
afterwards, junction links only), harness `--limits --pipe-name onl-host|onl-join --online-server <host-address>
--log-network --save-folder "X-Men Legends (onl host|join)"` + `[Online] LocalIP=<host-address>`, local OpenSpy
(started and stopped). Play Online from the XML1 main menu (no crash). Screenshots: scratchpad `onl/shots/*.png`,
logs `onl/logs/` (not committed). Checks: validator 0 errors, heroes_validate PASS, scripts_selftest T1-T7 PASS,
scripts_transform selftest 0 failures, xml2_test PASSED.

Before the fix (DLL 00b2646; host = online Load Saved Campaign "East Manhattan", nyc1_1_3 before the Cyclops join):

| step | result | shots |
|---|---|---|
| online load | 1P Wolverine, 2P standby on both | a_h13, a_j4 |
| 9 heroes unlocked on both (paused, same script) | - | - |
| joiner: pause > Team Management | team menu opens on **both** windows; party screen, hints Details/Accept (host also Kick Player); Enter on the empty pad = accept | b_j2, b_h2, b_j3 |
| host: Team Management, DOWN + Enter | cursor cycles the pads, Enter closes; no roster | b_h4, b_h5 |
| host teleported to the X-point, E | X-Jet Xtraction: Xtract / Change Team / Save Game on both | b_h8, b_j8 |
| host: Change Team | team menu, hints now include `[J] Replace` for both | b_h9, b_j9 |
| joiner J on the empty pad | roster (Beast, Gambit, Iceman, ...) | c_j1 |
| joiner J on Gambit | Wolverine + **Gambit** "Editing..." on both | c_j2, c_h2 |
| both accept | reload: **1P Wolverine + 2P Gambit** | c_h3, c_j3 |
| joiner's Gambit E at the X-point | menu owned by the joiner: host DOWN ignored, joiner DOWN moves it | c_j4, c_h5, c_j5 |
| joiner Change Team, host J > J | host replaces Wolverine with **Iceman** -> Iceman + Gambit on both | c_h6, c_h7, c_j7, c_h8 |
| joiner Xtract | XML2's World Map (act 1 Genosha / Sanctuary) on both; Esc back | c_h9, c_j9, c_h10 |

After the fix (DLL f06f2e2, rebuilt `_onl`):

| step | result | shots / log |
|---|---|---|
| online New Game (Campaign) | nyc1_1_1, Wolverine alone, popup 161; the hook set teamlock 1 | d_h4 |
| (scripted teleport while the host paused first -> "lost communication" before any X-point: harness artifact, see below) | each side continued alone | e_h3, e_j3 |
| host alone, E | **Change Team greyed**; log `extractionPoint: the mission's party is fixed ... greyed out` | f_h1 |
| cursor on it + Enter | the menu closes; no team menu, no reload | f_h2, f_h3 |
| Save Game | works (slot 1 = the locked save) | f_h4-f_h6 |
| online Load Saved Campaign of that save (streamed ~70 s) | 1P Wolverine, 2P standby | g_h6, g_j6 |
| host E | **greyed on both**; both DLLs log it (07:04:34.329 / .402) | h_h1, h_j1 |
| host Enter on it | closes on both, play continues in sync | h_h2, h_h3, h_j3 |
| host walks into trigger_touch03 | tut popup -> joinHero on both -> **1P Wolverine + 2P Cyclops** | i_h4, i_j5 |
| Cyclops teleported (joiner paused first), joiner E | menu owned by the joiner, **greyed on both** (logs 07:07:48.837 / .803) | k_j3, k_h3 |
| joiner Enter on it | closes on both; W + C unchanged | k_j4, k_j5, k_h5 |
| free mission `begin_haarp_int` started on both (console, paused) | teamlock 0; joiner's X-point menu: **Change Team enabled** (the two windows had desynced by then, see below) | l_j3 |
| single player: Load Game of the locked save | greyed (flag from the save) | m_h3 |
| single player: `begin_haarp_int`, X-point | **enabled**; Change Team opens the team menu (Replace) | m_h5, m_h6 |

Drops / desync (both harness-made, neither near the fix's code): a scripted `copyOriginAndAngles` sent to both while
only the host had paused (06:57: the joiner simulated frames the host didn't; "lost communication" ~30 s later, no
X-point handler had run), and a console mission start sent to both in a paused session (07:08: the host stayed at
the spawn while the joiner walked). Real play never does either; the teleport issued after the **joiner** paused
(07:07) stayed in sync, as in port_online_test.md. Harness rule: pause from the joiner, wait, then script both.

## Open

- The exact player-count rules of the team menu with 3-4 players (one standby player per empty slot) - not run.
- Xtract / Blink Portal to XML2 town centres from forced missions (pre-existing).
- asteroid_rock partial lock (above) - acceptable unless Owen wants XML1's exact REQUIRED/maxheros rule in the
  team menu (bigger: roster filtering in the team menu code).
