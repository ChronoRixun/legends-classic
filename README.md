# Legends Classic

**Play X-Men Legends (2004) on PC, built from your own copies of the games.**

X-Men Legends came out on consoles only. Its sequel, X-Men Legends II: Rise of Apocalypse, came to PC on the same
engine. Legends Classic takes the first game from **your own Xbox disc** and rebuilds it to run on **your own PC copy
of X-Men Legends II**: the story, the zones, the heroes and their powers, the menus, the movies and the music of the
first game, on the second game's PC engine, with modern display options, controller support and saves of its own.

It is a builder, not a download: every file of the result is made on your computer from the two copies you own.
This project ships no game content - no game files, no parts of them, no modified executables - and the builder
makes no network connections.

> **Status: public test builds (builder 0.2.4, XML2 Fix 1.7.0, launcher 0.3.2).** Every mission and the ending run
> in automated tests on the developer's PC (a full hand-played run is under way). The builder makes the game from
> your own disc image and X-Men Legends II install, and the [Ultimate Legends](https://github.com/ChronoRixun/ultimate-legends)
> launcher does it in a few clicks. 0.2.4 restores Toad's HAARP fight and enemy resistance text, and fixes co-op
> disconnects during conversations. Rebuild, then Play; both co-op PCs need 0.2.4 / XML2 Fix 1.7.0.
> Known bugs and what is next: [Status](#status), [CHANGELOG](CHANGELOG.md) and [Roadmap](#roadmap).
> Help and bug reports: the [community Discord](https://discord.gg/tFxwHtZv8k).

## What you need

| | |
|---|---|
| **X-Men Legends for the original Xbox** | your own disc, made into a disc image: a full Redump-style `.iso` or an XISO both work. [How to image your own disc](docs/DUMPING.md). The PlayStation 2 and GameCube versions are different games under the hood and aren't supported (the builder recognises them and says so); compressed images (CCI / CSO) need decompressing first. |
| **X-Men Legends II: Rise of Apocalypse for PC** | installed, English, with the retail `XMen2.exe` (the builder checks it) and unmodified game files. Your install is only read, never changed. |
| **[xml2-fix](https://github.com/ChronoRixun/xml2-fix) 1.7.0 or later** | the in-memory engine fixes the port relies on (new-game party, forced parties, the first game's level curve and combat numbers, bigger zones, its own save format and folder, display options). The Ultimate Legends launcher installs it for you. Each builder needs a minimum version: see [Versions that go together](#versions-that-go-together). |
| **Windows 10 or 11, 64-bit** | the released builder is a Windows program. From source it is plain Python + numpy, written to run on Linux too (its tests run there in CI; a full Linux build is untested so far). |
| **Disk space** | about 8 GB while building with movies (the game ~4.6 GB + a build cache ~3.2 GB you can delete afterwards), about 6 GB without movies. |
| **Time** | the first build converts every sound bank: about 6-8 minutes on a current 8-core PC. Rebuilds with the cache take 2-3 minutes. |

## Installing

### With the Ultimate Legends launcher (recommended)

[Ultimate Legends](https://github.com/ChronoRixun/ultimate-legends) (a portable zip, no install) downloads the
builder, runs it and installs xml2-fix for you. On a Steam Deck or another Linux PC under Proton, use launcher 0.2.1 or
later: earlier launchers could not unpack the builder there.

1. Set up **X-Men Legends II** in the launcher as usual (it installs xml2-fix).
2. Open **X-Men Legends - community port** in the library and choose **Set up**.
3. Pick your disc image and a destination folder. The launcher checks the image, shows the space and time the build
   needs, and lets you switch the movies and the build cache on or off.
4. **Build.** A checklist of stages with a progress bar; you can hide it, cancel it and resume later.
5. **Play.** The launcher installs xml2-fix into the new folder and sets its display defaults.

The game page then shows whether your build is up to date and offers a rebuild when a new builder changes the
game's content (never automatic). *Verify* checks every file; *Uninstall* removes exactly what the builder made -
your saves stay.

### Standalone: the `xml1-builder` release zip

Download `xml1-builder-<version>-win64.zip` from [Releases](https://github.com/ChronoRixun/legends-classic/releases)
(check it against `SHA256SUMS.txt`), unzip it into a folder of its own (the zip has no top-level folder) and run it
from a command prompt:

```
xml1-builder info    --iso "D:\Images\X-Men Legends.iso" --xml2 "C:\Games\X-Men Legends II"
xml1-builder build   --iso "D:\Images\X-Men Legends.iso" --xml2 "C:\Games\X-Men Legends II" --out "C:\Games\X-Men Legends (Port)"
xml1-builder verify  --out "C:\Games\X-Men Legends (Port)"
xml1-builder clean   --out "C:\Games\X-Men Legends (Port)"
```

| Command | Does |
|---|---|
| `info` | identifies the disc image and the XML2 install, estimates space and time, reports the state of an existing build. Options: `--iso`, `--xml2`, `--out`, `--cache`. Reads only. |
| `build` | makes, updates or resumes the build. Options: `--iso`, `--xml2`, `--out`, `--cache DIR` (default `%LOCALAPPDATA%\xml1-builder\cache`), `--movies` (the default) or `--no-movies` (-1.1 GB), `--keep-cache` (the default) or `--drop-cache`, `--jobs N` (sound-conversion workers, default every CPU), `--no-ini`, `--main-menu-layout classic\|widescreen` (widescreen is a retired name for classic), `--allow-unknown-exe` (testers: an `XMen2.exe` that is not a known retail build). |
| `verify` | checks a build against its record: up to date, needs a rebuild, damaged, incomplete; writes `_build\verify-report.json`. Options: `--out`, `--iso`, `--xml2`; `--deep` also re-checks every file inside the disc image. |
| `clean` | deletes exactly what the builder made - never your saves; mods only with `--mods`; `--dry-run` only counts. |

Options that work with every command: `--events jsonl|text` (`jsonl` prints JSON-lines events for the launcher), `--log FILE`, `--quiet` and `--version`. `xml1-builder --help` lists them all.

Then copy `dinput.dll` from the [latest xml2-fix release](https://github.com/ChronoRixun/xml2-fix/releases/latest)
(builder 0.2.4 needs 1.7.0 or later) into the output folder and start `XMen2.exe` there. The builder has already written the `xml2-fix.ini` settings the
port needs (`--no-ini` leaves the file alone; the keys are in `_build\stamp.json`).

The release zip is not code-signed yet, so Windows SmartScreen or an antivirus may warn about it: compare the
SHA-256 with the release page, or build it yourself from source ([docs/BUILDING.md](docs/BUILDING.md)).

### Steam Deck / Proton

These releases are Windows programs. Running them through Proton is a compatibility path, not a native
Linux release or a fully tested Deck configuration. For a direct Steam shortcut to the game, put the DLL
beside the executable and, if the fix is not loaded, try this in the shortcut's Launch Options:

```text
WINEDLLOVERRIDES="dinput=n,b" %command%
```

Check for `xml2-fix.log` in the game folder to confirm the DLL loaded. Keep the same Proton prefix when
updating: saves are under that prefix's Windows Documents folder (which may be redirected).
See [Proton's runtime configuration](https://github.com/ValveSoftware/Proton#runtime-config-options)
for Steam Launch Options. Controller and Discord behavior under Proton has not been verified here.

### First start

The first time the game starts, Windows 10 or 11 may ask to install **DirectPlay**, an old Windows component that
Windows' own compatibility list requests for X-Men Legends II. Either answer works: *Install this feature* (once, from
Windows Update) stops the question, and *Skip this installation* lets the game start without it.

### What the build does

1. **Checks your inputs.** The disc image must be X-Men Legends for Xbox (title id `4156001E`) and complete; XML2
   must be the retail PC build. Clear messages when something doesn't fit.
2. **Reads the disc image in place** - no copy of the whole disc: it opens the Xbox file system inside the image,
   streams the game's archives and keeps what the conversion needs in the cache.
3. **Prepares** what takes time: the scripts rewritten for XML2's script engine, every sound bank converted from the
   Xbox's audio format to the PC's, the layered music rebuilt. Cached, so it happens once per disc.
4. **Builds** a new game folder: XML2's install as the base (copied - your XML2 folder is never written to), then
   the first game's zones, characters, powers, scripts, menus, movies and sound converted on top.
5. **Validates** the result with the same checks the developer builds use, reads every file back, and writes a record
   of what it made (`_build\stamp.json`, `_build\manifest.json`).

Saves go to `Documents\Activision\X-Men Legends`, separate from X-Men Legends II's.

## Saves

Builder 0.2.0 moves the port to a save format of its own, once, so that later updates can add and change content
without turning older saves into broken ones.

- **Your saves come with you.** The first time the rebuilt game starts, XML2 Fix 1.4 converts every save it finds in
  `Documents\Activision\X-Men Legends\Save`, and the profile, once, into the new `SaveLC` folder beside it
  (`saveslot<N>.lcsave`, `profile.lcsave`). The old folder is never touched. Saves of every earlier builder carry over:
  heroes, levels, stats, talents, inventory, mission progress, unlocks, heard conversations and trivia answers.
  `SaveLC\legacy-import.txt` says what happened to each file. Where a zone changed between versions, only that zone's
  remembered state starts fresh (a notice says so), and a few conversations can play again.
- **Rebuild and update the fix together.** The format needs the rebuilt game *and* XML2 Fix 1.4.0 or later (1.5.0
  for builder 0.2.2): the launcher does both (Rebuild, then Play). The new DLL alone doesn't make the save tables the
  format checks at every start.
- **Builder 0.2.2 catches old saves up once.** The first time a save from an earlier builder is loaded, every hero
  gets the fifth-level points of the first game's rules (1 skill point and 4 stat points for each fifth level already
  passed) and has its automatic stat growth recomputed with the first game's tables, comic rewards kept. The next save
  records it, so it happens only once. Going back from 0.2.2 to 0.2.1 needs the copy of your saves made before the
  update: XML2 Fix 1.4.0 keeps a save 1.5.0 wrote as `.lcsave.newer` rather than overwrite it, and can refuse to save
  the profile.
- **No way back with new saves.** Builders before 0.2.0 can't read `.lcsave` files: going back to 0.1.12 plays the old
  `Save` folder as it was before the update, without later progress. Back up the whole
  `Documents\Activision\X-Men Legends` folder before updating if you want to keep that option (Documents may be
  redirected, for example to OneDrive).
- **Backups.** Every save keeps the one before it as `.lcsave.bak`, and a damaged save loads from it. A save made by a
  newer version is never overwritten by an older one: it is kept as `.lcsave.newer`.
- **A refused save or load keeps your file.** The game says why, and the save on disk stays as it was (so the latest
  progress was not saved). Keep the `SaveLC` folder as it is and report it with `xml2-fix.log` and
  `SaveLC\legacy-import.txt` (look them over first: they can contain folder paths).
- **Mods.** Cosmetic, UI and script mods work as before. A mod that replaces save-bound data (numbered objects, map
  placements, the items and talents a save refers to) is refused with its file name, because saves could not be read
  back correctly with it. Details: XML2 Fix's
  [save format](https://github.com/ChronoRixun/xml2-fix/blob/main/docs/save-format.md) and
  [save guards](https://github.com/ChronoRixun/xml2-fix/blob/main/docs/save-guards.md).
- **Co-op.** Everyone in an online game needs the same builder version, the same XML2 Fix and the same settings.
  The game compares the builds and their gameplay rules when a player joins and refuses a mismatch, with the reason
  on both PCs, instead of letting the two games drift apart.

## Status

Verified in game on the developer's PC (mostly by automated runs that drive the game through xml2-fix's test pipe):

- **The whole campaign, in automated runs**: the opening, every mission start (73) with the party the first game used
  (forced parties, flashbacks with their fixed heroes and costumes, heroes joining mid-level), the ending chain (the
  final bosses' defeats triggered by script), the credits and back to the main menu; a tour of every converted zone reachable from New Game, in one session
  without a crash. A full hand-played run is under way (act 1 so far).
- **The first game's heroes** with their own stats, powers (64 of 64 fire), unlock points and level curve (its
  45-level table, via xml2-fix), and its enemies with their own damage and energy values.
- **The first game's front end**: main menu (since 0.2.0 with its own Cerebro room, panels, fonts and colours, in a
  widescreen layout), Danger Room, Review (load screens, cinematics), credits.
- **Movies and music**, including the first game's layered music.
- **Display** (xml2-fix): borderless or windowed at your desktop's resolution, and since 0.2.2 exclusive fullscreen
  at a high-refresh desktop's own mode (2560x1440 at 180 Hz, with 8x anti-aliasing).
- **A clean Windows 11** (Windows Sandbox: no Python, nothing preinstalled): the released builder made the game from a
  disc image in about 6.5 minutes and verified every file; a new game there played from the intro through several
  zones. The files matched the developer's own builds one for one.

Fixed in later builders (the launcher offers the rebuild when the content version rises, or run
`xml1-builder build` again - see [CHANGELOG.md](CHANGELOG.md)):

- **0.2.4 (with XML2 Fix 1.7.0):** Toad's HAARP jets, armour and soldier waves (#105), the first game's
  colored resistance text beneath enemy health bars, and co-op conversations that stay in step.
  See the changelog for the remaining solo-segment limitation (#106).
- **0.2.3 (with XML2 Fix 1.6.0):** hazards, enemy combat timing, ice-tunnel crates, Danger Room health bars,
  Sentinel lock-on effects, fast co-op saved-campaign loads and Connect by IP / LAN search.
- **0.2.2 (with XML2 Fix 1.5.0):** the scan turrets (#4); the Xtraction services - Load, Danger Room, Healer and
  Forge - and the main menu's Danger Room locked until Phoenix joins (#63); two-point ranks and the first game's
  fifth-level points (#35) and stat growth, old saves caught up once; breakable parts and boss armour that comes off
  (#3); resistant enemies that aren't launched or knocked back; leaders (#15); solo mode (#5); death below 1 health;
  quarter packs and the first game's revival price; two fall volumes back (#22); the death hand-over; Professor X's
  seats (#54), the dormitory hit sounds (#79), the pack sound (#82); pads after *Defaults* (XML2 Fix #9), the mouse
  in cutscenes (#85), the Codex highlight (#97), exclusive fullscreen and 8x anti-aliasing (#84); 1024 script
  functions.
- **0.2.1:** builds made with the released builder no longer stop at the last step.
- **0.2.0 (with XML2 Fix 1.4.0):** the port's own save format, every old save carried over once; the first game's
  combat balance (enemy health and damage, hit chance, strength bonus, power attacks, gun damage rolls; enemy melee
  punches hurt again, #94, #14); the classic main menu; rooms that keep every prop, projectile and trigger (the engine's
  object limit raised from 224 to 768: the HAARP freeze gun, Magneto's arena); Master Mold's original fight with his
  shield, the cores and his attacks (#27); Mystique's gun sounds (#83), the soldiers' grenade choices (#36), Pyro's
  fire barrier softlock (#93), keycards without a model (#96), the equipment shop at Xtraction points after meeting
  Forge (#95), the bedroom pictures (#47), the power icons (#53, #73), the HAARP entry prompt (#77), floating and
  sinking props (#81); trivia answers in every act.
- **0.1.12:** ladder descents, completed objective descriptions, STAT attribute points, power/Might-only break rules,
  effect particles in busy areas, recommended mission teams, rank-1 power damage, Xtraction beacon glow, and removal
  of the sequel's Xtract world map and Blink Portal.
- **0.1.11:** Save is available at the twenty formerly restricted Xtraction points.
- **0.1.10:** older hero talent indices translate across the 0.1.8 changes.
- Earlier releases fixed power-wheel loss, NPC gun/projectile damage, conversation timing, skill pickups,
  Danger Room rewards, and several boss and mansion progression problems.

### What isn't there

Some of the first game's features rely on engine code X-Men Legends II doesn't have. Until they are recreated (most
need new engine hooks in xml2-fix), the port plays without them:

- **The first game's loot and shops.** Random drops are X-Men Legends II's, not the first game's equipment. The shops
  (the Healer's, and the one at Xtraction points once you have met Forge) are X-Men Legends II's: generated stock, its
  prices and its training services ([#6](https://github.com/ChronoRixun/legends-classic/issues/6)).
- **18 of the first game's fall volumes** stay off: several sit in water or in rooms followers can stray into, and
  need their own checks ([#22](https://github.com/ChronoRixun/legends-classic/issues/22)). The East Rooftops and a
  sewer walkway have theirs back since 0.2.2.

Recreated in 0.2.2: the scan turrets ([#4](https://github.com/ChronoRixun/legends-classic/issues/4)), breakable
enemy parts ([#3](https://github.com/ChronoRixun/legends-classic/issues/3)), solo mode
([#5](https://github.com/ChronoRixun/legends-classic/issues/5)), the Xtraction services and the Danger Room's story
lock ([#63](https://github.com/ChronoRixun/legends-classic/issues/63)) and the two-point ranks
([#35](https://github.com/ChronoRixun/legends-classic/issues/35)).

### Known limitations

- Key bindings and display settings are shared with X-Men Legends II (both read the same Windows registry key);
  saves are separate.
- **A keycard behind a door in HAARP:** since 0.2.2 the HAARP officers are no longer launched onto the key door, the
  way their keycards ended up behind it. The first game can itself push an officer through that door when the two
  overlap; if a keycard is ever out of reach, load your last save.
- Online play (*Play Online*) is X-Men Legends II's, through the [OpenSpy](https://openspy.net) servers; port games
  only list other port games. Joining, playing and saving for both players work in tests with two copies of the game
  on one PC; play between two PCs, and across the internet, gets a dedicated pass in 0.3.0. Reports of disconnects are
  welcome (say whether the game showed its lag warnings first). In co-op, *Load Saved Campaign* sends the host's save
  to the joining player since 0.2.3, in seconds; both PCs now need builder 0.2.4 with XML2 Fix 1.7.0. *Connect by IP* and the
  LAN search list and admit port games since 0.2.3 (before, two port builds could not see each other that way).
- **Solo story segments (#106):** co-op New Game starts with Wolverine alone; Magma's mansion tour also leaves
  the second online player without a hero. At a solo segment's next level load the joiner can be dropped. Use
  Load Saved Campaign and restart from a save after the segment. Planned for 0.3.0 with drop-in co-op.
- **Still open:** enemy powers and stun (#101), fall kill zones still switched off until proven safe (#22),
  cosmetic reports (#54), and the first game's loot and item shop (#6).
- Local co-op on controllers should work (it is X-Men Legends II's) but has had little testing.
- Open bugs and play-test notes: [issues](https://github.com/ChronoRixun/legends-classic/issues) and
  `research/campaign/late_game_test.md`.

### Versions that go together

A build records the xml2-fix version it needs (`_build\stamp.json`, `requires`). With an older fix the game may still
start, but the new keys do nothing: a 0.2.0 build without XML2 Fix 1.4 has no saves of its own format and none of the
combat, menu, capacity or Master Mold changes. From 0.2.2 a build that finds an older `dinput.dll` in its folder warns
and names the settings it doesn't know. The launcher installs the latest fix after each build and each time it starts
the game.

| Builder | Content version | Needs xml2-fix | Notes |
|---|---|---|---|
| 0.2.4 | 22 | 1.7.0 | Toad at HAARP (#105); colored enemy resistance text (`[Game] ResistanceDisplay=xml1`); co-op conversations (`[Game] OnlineConversations=lockstep`, rule 27); catalogue 7 / LC31; both PCs need this pair |
| 0.2.3 | 21 | 1.6.0 | hazard bounds and the opening fire's rhythm (`[Game] BoxHarmOrigin`, `HarmSingleChain`), floor-overlap crates (`ObjectWorldImpact`), two more fall volumes, the first game's gun-move priority, NpcPower revision 4, StunRule revision 2, visible Danger Room opponents with health bars and the original fallback party (`DangerRoomHealthBars`, `DangerRoomParty`), Sentinel scan effects and aiming, fast saved-campaign transfer (`[Online] FastTransfer`), received-message checks (`[Online] ReceiveValidation`); catalogue 7 / LC30; verified saved-zone prefix retention; co-op peers need 0.2.3 / 1.6.0 on both PCs |
| 0.2.2 | 19 | 1.5.0 | the first game's rank costs and level points (`[Game] RankCosts`, `LevelSkillPoints`, `LevelStatPoints`), breakable parts (`[Game] Xml1Multipart`), leaders (`[Game] X1Leader`), solo mode (`[Game] SoloMode`), death below 1 health (`[Game] DeathRule`), the Xtraction services and Danger Room gate (`[Game] DangerRoomGate`), the revival price (`[Game] RevivalCost`), scan turrets (`[Game] Xml1Turrets`), pack amounts (`[Game] PackAmount`), settling without crushes (`[Game] PlacementCrush`), no double heals (`[Game] DoubleHeal`), 1024 script functions (`[Limits] ScriptFunctions`), the death hand-over (`[Game] DeathSwitchClear`), enemy power use and combos (`[Game] NpcPowerRule`); co-op peers need 0.2.2 / 1.5.0 on both PCs |
| 0.2.0 - 0.2.1 | 18 | 1.4.0 | the LC save format (`[Save] Format=lc`), the first game's combat balance (`[Balance]`), the entity capacity raise (`[Limits] EntityCapacity`: 768 generic / 1024 World entities), triggers per move (`[Limits] MoveTriggers`), the Master Mold controller (`[Game] Xml1MasterMold`, `Xml1MoldStage`), explosions' first hit (`[Game] ExplosiveFirstHit`), the classic main menu (`[Game] ClassicMainBackdrop`, `ClassicMainPanelBounds`), popup answers (`[Game] ConfirmationRelease`), the Xtraction shop (`[Game] XtractionShop`), content fingerprint metadata (`[Online] ContentFingerprint`) and the shared gameplay agreement (co-op peers with different content or settings are refused, with the reason on both PCs) |
| 0.1.12 | 15 | 1.3.2 | ladder descents (`[Game] CharacterLadderPaths`), objective completion text (`[Game] ObjectiveDescriptions`), STAT pickups (`addStatPoints`), the first game's break rule (`[Game] BreakRule`), the effect curve pool (`[Limits] EffectCurves`), no Xtract world map (`[Game] Xtract`) |
| 0.1.8 - 0.1.11 | 11 - 14 | 1.3.1 | fighting-style registry (`[Limits] FightStyles`), enemy outlines (`[Game] GeometrySharingBlendIndices`) |
| 0.1.6 - 0.1.7 | 8 - 9 | 1.3.0 | conversation hooks, skill points, the item-enhancement pool |
| 0.1.0 - 0.1.5 | 2 - 7 | 1.2.0 | |

Launcher: any release runs every builder; on Proton (Steam Deck, Linux) 0.2.1 or later.

## Roadmap

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
| M4 | **Public test period**: fixes from playthroughs, release by release (0.1.x, then 0.2.x: the port's own save format, the first game's combat balance, hazards, co-op fixes) | now |
| M5 | **Complete**: the first game's mechanics this engine lacks (see [What isn't there](#what-isnt-there)) | under way: turrets, breakable parts, solo mode, Xtraction services and ranks done in 0.2.2 |
| M6 | **Classic look**: the first game's menus, fonts, colours and HUD (the main menu is done in 0.2.0) | planned |
| 1.0 | **Finished**: a full campaign played by hand on a release build with nothing blocking, checked on the Steam Deck, co-op checked on one PC and across the internet | goal |
| later | settings separate from X-Men Legends II's; compressed disc images | ideas |

What comes next, by version (plans move with what testing finds):

- **0.2.0** - the port's own save format (every old save carried over once), the first game's combat balance, its
  main menu, rooms that keep every object (the engine's entity capacity raised) and Master Mold's original fight
  ([#27](https://github.com/ChronoRixun/legends-classic/issues/27)); **0.2.1** fixed builds from the released builder.
- **0.2.2** - the scan turrets ([#4](https://github.com/ChronoRixun/legends-classic/issues/4)), the
  Xtraction services ([#63](https://github.com/ChronoRixun/legends-classic/issues/63)), the first game's skill ranks,
  level points and stat growth ([#35](https://github.com/ChronoRixun/legends-classic/issues/35)), breakable parts and
  boss armour ([#3](https://github.com/ChronoRixun/legends-classic/issues/3)), solo mode
  ([#5](https://github.com/ChronoRixun/legends-classic/issues/5)), leaders, exclusive fullscreen and the fixes in
  [CHANGELOG.md](CHANGELOG.md).
- **0.2.3** - the first game's fires, spikes and electricity hazards hurt again, at a steady rhythm
  ([#104](https://github.com/ChronoRixun/legends-classic/issues/104)); co-op *Load Saved Campaign* works again and
  takes seconds, and *Connect by IP* and the LAN search work between port builds; the falling crates
  ([#103](https://github.com/ChronoRixun/legends-classic/issues/103)), the Danger Room's robot health bars and
  cloaked opponents, the Sentinel flashback's lock-on effects, two more fall volumes
  ([#22](https://github.com/ChronoRixun/legends-classic/issues/22)) and more of the enemy-AI stun gap
  ([#101](https://github.com/ChronoRixun/legends-classic/issues/101)) - needs XML2 Fix 1.6.0.
- **0.2.4 - done:** Toad's HAARP fight ([#105](https://github.com/ChronoRixun/legends-classic/issues/105)),
  enemy resistance text, and co-op conversations that stay in step. Needs XML2 Fix 1.7.0.
- **0.3.0** - online by code, a public game browser, drop-in co-op and the solo story segments
  ([#106](https://github.com/ChronoRixun/legends-classic/issues/106)): host and join from Ultimate Legends,
  share a code or browse public games, join a running campaign at the next level change, and keep the second
  player connected through Wolverine's opening and Magma's mansion tour. A new encrypted network layer adapts
  to bad connections, with relay fallback for internet play without port forwarding.
- **0.4** - classic look: the rest of the menus (pause, characters, Review, shops, loading) and the HUD, made from
  your own disc's art.
- **0.5** - complete, part two: the first game's loot and shops
  ([#6](https://github.com/ChronoRixun/legends-classic/issues/6)) and others.
- **0.6** - graphics: an optional DXVK toggle, and an investigation into graphical engine upgrades.
- **0.6 to 0.7** - the online section and join screen overhaul: a modern lobby.
- **0.7 to 1.0** - more may come, spread between 0.7 and 1.0: whatever is still open from these lists, and whatever
  the playthroughs turn up next.

## Repository layout

| Path | What |
|---|---|
| `tools/xml1builder/` | the builder (`python -m xml1builder` from `tools/`; frozen into `xml1-builder.exe`) |
| `tools/xml1build/` | the conversion pipeline (zones, characters, heroes, scripts, front end, media, validator), the prepare stages (`prepare/`), shared format code (`lib/`) and the specifications `SPEC.md` / `SPEC_heroes.md` |
| `tools/` | format tools (disc image, bundles, binary XML, sound banks), the developer build `build_xml1.py`, the freeze scripts and the test harness that drives the game through xml2-fix |
| `tests/unit/` | synthetic tests (no game data); CI runs them on Windows and Linux |
| `research/` | the reverse-engineering and design notes behind every decision: file formats, engine behaviour, addresses, measurements ([research/README.md](research/README.md)) |
| `docs/` | [DUMPING.md](docs/DUMPING.md) (imaging your own disc), [BUILDING.md](docs/BUILDING.md) (from source, tests, freezing) |
| `tools/check_no_game_content.py` | the guard that keeps game content out of this repository (pre-commit hook + CI) |

## Building from source

Python 3.14 (64-bit) and numpy; a C compiler is optional (the fast sound encoder). In short:

```
python -m pip install -r requirements.txt
python tools/build_sound_kernel.py          # optional: MSVC or cc; without it the sound stages are 6-8x slower
cd tools
python -m xml1builder build --iso <your disc image> --xml2 <your XML2 folder> --out <new folder>
```

Tests, the developer build, the harness and freezing the exe: [docs/BUILDING.md](docs/BUILDING.md).

## Community, contributing and bug reports

- **Discord**: [discord.gg/tFxwHtZv8k](https://discord.gg/tFxwHtZv8k) - help with setting up, bug reports, finding people for
  co-op. The same rule as here: no game files, disc images or links to them.

- **Bug reports**: use the issue form. It asks for the builder version, `_build\verify-report.json` and the end of
  `_build\builder.log`: file names, sizes, hashes and error codes, nothing from the games. Never attach the disc
  image, the build, save files or any game file.
- **Pull requests**: our code and our words only - see [CONTRIBUTING.md](CONTRIBUTING.md). The content guard runs on
  every commit (`pre-commit install`) and in CI; it rejects game files, decoded game data, game text, disassembly
  listings, personal data and large binaries.
- No links to disc images, ROMs or download sites, anywhere in the project.

## Credits

X-Men Legends and X-Men Legends II were made by Raven Software (the PC version of X-Men Legends II with Beenox) and
published by Activision; this project exists because those games are worth playing. Engine fixes:
[xml2-fix](https://github.com/ChronoRixun/xml2-fix). Launcher: [Ultimate Legends](https://github.com/ChronoRixun/ultimate-legends).
Built with Python, numpy and PyInstaller. Project: [ChronoRixun](https://github.com/ChronoRixun).

The reverse engineering, the pipeline and these notes were made by one person working with Claude (Opus 5.5 and
Fable 5.1) over a few days; the commit trailers and the research notes show that work as it happened. It is meant as
a showcase of what people and AI can do together on preservation work.

## License and disclaimer

[MIT](LICENSE) for this project's code and documentation.

Legends Classic is an unofficial, non-commercial fan project, not affiliated with or endorsed by Marvel, Disney,
Activision, Raven Software or Beenox. Marvel, X-Men, X-Men Legends and all related character names are trademarks of
Marvel; all other trademarks belong to their owners and are used only to say which games this project works with.
It contains and distributes no game content: you need your own copies of both games. Full text: [LEGAL.md](LEGAL.md).


### 0.2.3 companion settings and player testing

| XML2 Fix setting | Builder default | Purpose |
|---|---|---|
| `[Game] ObjectWorldImpact` | `xml1` | XML1 landing-impact coefficient; rule 17 |
| `[Game] StunRule` | `xml1` | Original party stun playback/recovery; rule 18 revision 2 |
| `[Game] DangerRoomParty` | `xml1` | Original incomplete-course four-hero fallback; rule 19 |
| `[Game] Xml1LockOnEffects` | authored triple | Scan, surface and acquired-target visuals |
| `[Game] Xml1LockOnAim` | `1` | Animated-head targeting; rule 20 |
| `[Game] NpcPowerRule` | `xml1` | XML1 power decisions and combo timing; rule 16 revision 4 |
| `[TestMode] ForgeEverywhere` | off, unwritten | Forge at Xtraction points |
| `[TestMode] Hotkeys` | off, unwritten | F8 clears eligible enemies, F9 toggles party protection, F10 returns to the nearest safe authored start |

`[TestMode]` is optional and offline only: either switch blocks hosting and joining until both are off and the game restarts. F8 may skip script-referenced actors; F10 refuses an unsafe destination. See the companion [testing guide](https://github.com/ChronoRixun/xml2-fix/blob/main/docs/test-mode.md). Saves made with testing tools retain their gameplay effects.

Builder 0.2.3 / XML2 Fix 1.6 carries newly appended hazards through online saved-campaign transfer (co-op protocol 4; XML2 Fix 1.5 and older peers are refused).

### 0.2.3 settings (rules 21-24)

| [Game] key | XML1 builder | Agreement |
|---|---|---|
| BoxHarmOrigin | xml1 | 21 revision 1, requested only |
| DangerRoomHealthBars | xml1 | 22 revision 1, requested only |
| HarmSingleChain | single | 23 revision 1, requested only |

| [Online] key | Builder | Agreement |
|---|---|---|
| FastTransfer | 1 | 24 revision 1, requested only |

Absent, empty, off or xml2 omits a rule. Invalid or failed requested installs remain unverified. Both peers must match. HUD dirty-stat refresh/clamp timing parity remains unproved. Content 21, catalogue 7, lobby token LC30. The builder also writes `[Online] ReceiveValidation=1`.

### 0.2.4 settings (rule 27)

| [Game] key | XML1 builder | Agreement |
|---|---|---|
| OnlineConversations | lockstep | 27 revision 1, requested only |

Online, a conversation line that goes on by itself does so |timeDelay| seconds of game time after it appears, on every PC on the same frame, and a chosen reply's voice is cut; single-player is unchanged. Absent or `stock` keeps the 1.6.0 behaviour and omits the rule; an invalid value is unverified (online refused). Both peers must match.
