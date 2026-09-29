# XML1 port online co-op test (two windows, local OpenSpy) - 2026-09-28 21:45-23:25

Build `build/_jh2` (--no-movies, XML1 front end, latest joins) + a second window folder `build/_jh2_b` (junctions
to _jh2's folders, copies of the top-level files; removed afterwards, junction links only). DLL xml2-fix 1c750e3.
Both inis: `harness.py install --limits --pipe-name port-host|port-join --online-server <host-address> --log-network
--save-folder "X-Men Legends (online host|join)" --width 960 --height 540` + `[Online] LocalIP=<host-address>`.
Stack: openspy-local (qr / serverbrowsing / natneg on 127.0.0.1 and <host-address>).
Screenshots: scratchpad `online/*.png` (not committed); logs: scratchpad `online/*.log`. _jh2's own ini + DLL
(20c28cd) were put back afterwards.

## Summary

| # | Question | Result |
|---|----------|--------|
| 1 | Play Online from the XML1 front end | **No menu item** (7 XML1 items). `console openmenu online` reaches XML2's online screens, but hosting/joining then **crashes** unless a main-menu item was accepted first (below). With a menu accept first, the whole flow works. |
| 2 | Port New Game online | Works. Host = Wolverine alone in nyc1_1_1; **2P is in standby** (HUD shows only a "2P" tag, camera follows the party), host gets XML2's popup 161 (a limited-heroes mission: extra players wait on standby) No kick, no crash, no desync. (Plain XML2: 2P got Cyclops because XML2's start party has several heroes.) |
| 3 | Cyclops join online | Works. Online `Load Saved Campaign` of an nyc1_1_3 save, host walks into trigger_touch03: tut15 popup -> joinHero (pushsidemission + restorelastzone, run on both windows in the same ms) -> **both windows reload together**, 1P Wolverine + **2P Cyclops** (2P moves Cyclops, host sees it). Team Management then shows both "Editing..." (accept on both). |
| 4 | Forced-solo stretch with 2 players | Works. Real flow `missionComplete('nyc/alison/blackbird_brief1')` (blackbird briefing, r103, seatParty magma + loadMapKeepTeam mansion1a_1) run on both while paused: both follow the briefing, Magma alone in the office, **2P back to standby**, conversation in sync. Online load of a mansion1a_1 save: Magma alone, 2P standby, stable 7+ min. 4-hero flashback (loadjuggernaut: seatParty cyclops/beast/iceman/phoenix): **2P gets a hero again** (kept Cyclops; host got Beast). |
| 5 | Crashes | 4x the same crash, all from `openmenu online` on a fresh boot (details below). No crash in any running session. Session drops ("lost communication") when a scripted zone change ran on one side or unpaused (a test-harness artifact, below), and one unexplained drop. |

## 1. Play Online and the XML1 front end

- XMen2.exe opens the online menu from MAIN_MENU only for an item named `label_option09` (0x5c9857, `openmenu
  online`); the port's menu avoids that name (frontend.py EXE_MENU_FORBIDDEN) and has no online item. The online
  menus are still in the build (XML2's `UI/menus/online|host|join|campaign_lobby|game_options|games_list`, GameSpy
  art, Apocalypse backdrop) and work in the port.
- **Crash: fresh boot + `openmenu online` by console + Host/Post Game or Join.** 4 of 4 (host 21:49, 21:58, 22:00,
  23:24 without a pad; joiner 22:06). WER: libIGDisplay.dll +0x20ba, c0000005 read 0 =
  `igControllerManager::getController(i)` with the manager's controller list NULL. Caught with a debugger
  (scratchpad online/avcatch.py): host `0x5f1bc8` (setuphost console handler 0x5f1bb0) -> 0x609f50 -> `0x60a03b`
  -> `0x551770` -> `0x5517db` (controller-slot scan 0x5517b0, loop to [esi+0x30]); joiner: `0x607889` <- 0x610469
  <- 0x60dc3c. Not the pad (the 23:24 crash had none) and not [Limits] (21:58 without it). **Any main-menu accept
  first (Review then Esc) and the same host/join works every time** (host 22:04, joiner 22:07, and all later
  sessions). Stock XML2 through its own Play Online item never crashed. So the accept on a main-menu item sets up
  player 1's controller slot; the console shortcut skips it. A real menu item is therefore also the crash fix.
- **Cleanest way to add Play Online** (Owen's call on the position; XML2 had it last before Quit): a visible 8th
  item in the XML1 menu (XML1's IGB has button8/9 nodes, now hidden debug slots) with `usecmd="openmenu online"`.
  Keyboard/pad accept runs the same menu-accept path Review uses (verified indirectly: Review -> online works).
  Mouse: XMen2.exe's MAIN_MENU hit-test has 6 item slots (label_option04..09) + debug_text, all used by the 7
  XML1 items via [Game] MainMenuItems, so a mouse-clickable 8th item needs one more slot in xml2-fix (or the
  item takes the `label_option09` slot and Credits moves to usecmd-only). frontend.py / validate_frontend V-check
  would allow `openmenu online` as a usecmd (only `newgame` / `startgamedialog` are forbidden).
- XML2 online flow as seen in the port: Play Online (Input Name / LocalIP / Ready) -> Host Game / Join Game.
  Host: Game Options (Game Name, Difficulty, Game Type = Campaign / Load Saved Campaign, Max Players) -> Post
  Game -> lobby -> Start Game. Join: Game Type Any / Difficulty Any -> Search -> Games List -> Join -> lobby ->
  Ready. `Load Saved Campaign` lists the port's own saves ([Game] SaveFolder) and loads them online (nyc1_1_3,
  mansion1a_1, nyc1_1_5 saves all loaded fine). Screens: h05/h06 (options), s_h1 (lobby), g_h4..g_h9 (saved
  campaign), s_j0 (games list).

## 2. New Game online (Campaign)

- Host s_h2/h31/h32, joiner j31/j32: Wolverine alone for 1P, "2P" tag with no hero for the joiner, popup 161 on
  the host (h32). The joiner's keys do nothing visible; its camera follows Wolverine; both stayed in sync
  (hold W on the host moved Wolverine in both). XML2's own behaviour (2P waits on standby until a hero is free)
  is exactly XML1's co-op rule for POV stretches.

## 3. Cyclops join (nyc1_1_3) online

- Online load of "Game 1 - East Manhattan" (saved at nyc1_1_3 before the trigger): c_h1/c_j1 Wolverine + 2P
  standby -> host `hold W 1800` -> tut15 popup on the host (c_h2) -> Continue -> joinHero log line on the host
  -> reload on both -> c_h4/c_j4: HUD 1P Wolverine + 2P Cyclops on both screens; joiner `hold S` moved Cyclops,
  seen on the host. Team Management after the join: both players "Editing..." (t_h4/t_j3). NPC double not checked.
- joinHero ran on **both** windows in the same millisecond (22:35:49.463 joiner / .464 host, same log line):
  the trigger, the popup's Continue and the script run in each client's lockstep simulation, and xml2-fix's
  script functions do the same thing on both. That is why the scripted reload stays in sync - and why running
  a script on one window only (harness) desyncs (section 5).

## 4. Forced-solo stretches with a connected 2nd player

- Mansion (Magma alone, "Game 3 - man1a" loaded online): m_h7/m_j7 (identical), r_h2/r_j2: Magma 1P, 2P standby.
  Standby 2P can open the pause menu and Team Management (r_j4): only Magma, empty slots, no Add/Replace for the
  standby player; Enter -> "[Esc] Main Menu". Pause-menu Ready handshake works for both (r_h7/r_j7).
- nyc1_1_5 (Wolverine + Cyclops, 2P = Cyclops) -> `missionComplete('nyc/alison/blackbird_brief1')` on both
  (paused): "Mission accomplished" popup (p_h2/p_j2) -> blackbird briefing on both (p_h3/p_j3) -> both logs
  `seatParty("magma") (was wolverine / cyclops)` -> mansion1a_1: Magma alone, 2P standby, the 1_2_1_1
  conversation advanced by the host shows the same line on the joiner (p_h4/p_j5) -> play continues (p_h7/p_j7).
  One 30-second lag-warning banner (p_h6) - both windows ran at 10-25 fps (PC at 100% CPU).
- Juggernaut flashback from Magma-alone (loadjuggernaut, paused, both): q2_h1/q2_j4 - 4 heroes, **1P Beast,
  2P Cyclops** (2P kept the hero it had; the host's Magma left the party so it took the next free one) ->
  combat with Juggernaut in sync. The flashback's conversation was advanced separately on each window (the
  joiner stayed on line 1 until it pressed Enter itself), unlike the standby case where it mirrored the host.
  Note: pushParty ran while paused and logged `no entity by that name - nothing pushed` (the pause hides
  `_ACTIVE_HERO_`) - a harness artifact, the real flow runs it from a popup option.

## 5. Drops / desync (no crash in session)

- Scripted zone change on the host only (`loadMapKeepTeam` by pipe, 22:18): the host reloaded alone, both got
  "lost communication / dropped" - expected, the harness bypasses the engine's sync (s_h4/s_j4 era, logs
  host_desync1.log / join_desync1.log).
- Same script queued on both windows within 0.1 ms but **unpaused** (22:53 loadjuggernaut): both ran it, then
  "You have lost communication with one of the other player(s)" on the host (f_h0/f_j0). Queued on both **while
  paused** (23:09 missionComplete, 23:12 loadjuggernaut): no drop. Real campaign flow never needs this; it's how
  the harness should drive scripted checks online (scratchpad online/dual.py).
- One unexplained drop at 22:45:14, ~55 s into an online load of the mansion save, no input: both sides stopped
  sending in the same 100 ms (host "Player has been dropped", n_h0). The retry of the same save ran 7+ minutes
  clean (22:50-22:57). Under 100% CPU load; watch for it in a quieter run.

## Keeping port games and XML2 games apart (GameSpy version)

- Both games are `xmenlegpc` (hard-wired with its secret key) and report `gamever 1.30` (qr heartbeat, see
  servers.ps1). The Games List is not filtered by game (XML2 players would see port games and vice versa;
  a mismatched join would load port zones on an XML2 install).
- The version is the 5-byte string "1.30" at **0x6a49b0**, copied by value into the net structs at startup
  (0x604fbb, 0x607d00 join request, 0x6083ab, 0x612272, 0x6144a0). Test (scratchpad online/setver.py, memory only):
  - patched after online had been opened once: no effect (the join request still said 1.30, join accepted);
  - **patched right after process start (joiner "1.31", host "1.30"): Search -> "No Games Found" (master server
    list and the LAN broadcast reply both dropped), and Connect by IP <host-address> -> "No Games Found" too**
    (v_j5, v_j10). The engine already refuses mismatched versions.
- Recommendation: xml2-fix patches those 4 characters at DllMain, before the game runs, e.g. `[Online]
  GameVersion=X1.0` written by the port's installer/launcher (max 4 chars; keep a digit scheme so later port
  releases with different content can bump it). No OpenSpy change needed. Symmetric check (stock 1.30 client vs
  X1.0 host) not run, but the refusal is on version inequality, so it should hold.

## Recommendations

1. Add a real "Play Online" item to the XML1 main menu (fixes the fresh-boot crash as a side effect). Mouse needs
   one more MAIN_MENU slot in xml2-fix.
2. xml2-fix `[Online] GameVersion` (0x6a49b0 at startup) so port and XML2 lobbies never mix.
3. Solo POV stretches: keep them faithful - the engine's standby mode (popup 161, 2P spectates with the host's
   camera, rejoins with a hero as soon as the party grows) is XML1's own co-op rule and works online. Open:
   later in the campaign, with more heroes unlocked, check whether a standby player can pull a hero into a
   forced party through Team Management (with only Magma unlocked it couldn't); if so, lock team changes while a
   forced party is seated.
4. Party order online: a player keeps his hero if it is still in the new party, so XML1's lead hero can end up
   with 2P (jug_fb: Cyclops -> 2P). Harmless; worth knowing for conversation speaker checks.
5. Harness notes: tap at 80 ms is sometimes missed at <25 fps (use `tap KEY 110` or `hold KEY 150`); text
   entry (Connect by IP) needs WM_CHAR (scratchpad online/wmchar.py) since the pipe's `wm` is gone; before any
   online test, accept a main-menu item once (Review -> Esc) or the host/join crashes.
