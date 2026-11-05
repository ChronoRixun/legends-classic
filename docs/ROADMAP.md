# Roadmap

| | Milestone | State |
|---|---|---|
| M1 | Playable start to finish | done in automated runs; hand-played run under way |
| M2 | Faithful: the first game's front end, Danger Room, parties, level curve, enemy values | done, polishing |
| M3 | **Shippable** | done: builder 0.1.0 released 2026-09-29 and launcher 0.1.0 released 2026-09-30 (UTC) |
| | build everything from the disc image on the player's PC (the prepare stages) | done |
| | fast sound conversion (a compiled encoder; first build in minutes) | done |
| | the `xml1-builder` program (info / build / verify / clean, progress, cancel and resume) | done |
| | packaging and CI (frozen Windows build, synthetic tests, the content guard) | done |
| | the launcher's setup wizard and game page | done |
| | this public repository, the community Discord | done |
| | release testing on a clean PC (Windows Sandbox): the builder alone, and the launcher's one-click setup | done |
| M4 | **Public test period**: fixes from playthroughs, release by release (0.1.x, then 0.2.x: the port's own save format, the first game's combat balance, hazards, co-op fixes; 0.4: online co-op and the classic look) | now |
| M5 | **Complete**: the first game's mechanics this engine lacks ([known issues](KNOWN-ISSUES.md#not-yet-recreated)) | under way: turrets, breakable parts, solo mode, Xtraction services and ranks done in 0.2.2; bosses, moves and grabs in beta 8 (0.4.1-beta.1); the first game's items, shops and drops in the 0.5 beta, still being checked |
| M6 | **Classic look**: the first game's menus, fonts, colours and HUD | done: the main menu in 0.2.0, the HUD, pause menu, character room, Review, Codex and the other screens in 0.4.0 |
| 1.0 | **Finished**: a full campaign played by hand on a release build with nothing blocking, checked on the Steam Deck, co-op checked on one PC and across the internet | goal |
| later | settings separate from X-Men Legends II's; compressed disc images | ideas |

## Next, by version

Plans move with what testing finds. What each released version added is in the [CHANGELOG](../CHANGELOG.md).

- **0.6 - in beta (0.6.0-beta.2):** online co-op in the game's own Play Online screens (Host, Join by code, Browse,
  the lobby and Party), and friends can join a game in progress at the host's next area (the host's DROP-IN setting
  turns it off per room). Beta.2: the session follows the host's frame rate, the rest of the online screens (LAN,
  Connect by IP, the keyboards, Game Options, the pause menu's player list) in the classic style with keyboard and
  controller, and fixes for Blob and the other first-game bosses, the 4-player host crash and the lost-newcomer
  pause. Still to verify: the relay, players on different home networks, three or four separate PCs, long sessions,
  joins over slow connections. Later 0.6 betas: **save import** from xemu and from XML1-recomp.
- **0.7** - an optional **"Remastered" graphics** toggle: DXVK, anti-aliasing, anisotropic filtering, resolution
  scaling and a centred HUD; off is the original look exactly.
- **0.8** - **co-op recovery**: area checkpoints, and rehosting after the host is lost.
- **0.9** - **moves and characters**: one pass over the heroes' moves, blocking and grabs, each compared with the
  original game (for example the held block, carrying, and Wolverine's ultimate at high levels).
- **Then** - whatever is still open from these lists or the playthroughs turn up. (The first game's items, shops and
  drops shipped in 0.5.0-beta.1, on by default; [#6](https://github.com/ChronoRixun/legends-classic/issues/6) stays
  open while they are checked against the original.)
- **1.0** - after a full hand-played run on a release build.
