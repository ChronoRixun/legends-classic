# Legends Classic

**Play X-Men Legends (2004) on PC, built from your own copies of the games.**

X-Men Legends came out on consoles only. Its sequel, X-Men Legends II: Rise of Apocalypse, came to PC on the same
engine. Legends Classic takes the first game from **your own Xbox disc** and rebuilds it to run on **your own PC copy
of X-Men Legends II**: the story, the zones, the heroes and their powers, the menus, the movies and the music of the
first game, on the second game's PC engine, with modern display options, controller support and saves of its own.

It is a builder, not a download: every file of the result is made on your computer from the two copies you own.
This project ships no game content - no game files, no parts of them, no modified executables - and the builder
makes no network connections.

> **Status: public test builds.** Published versions: builder **0.1.12**, XML2 Fix **1.3.2** and launcher
> **0.3.0**. Builder **0.2.0** / XML2 Fix **1.4.0** are unreleased; their changes below describe the prepared
> release branches, not downloads already available. Automated campaign checks are not a complete manual
> playthrough. Help and bug reports: [community Discord](https://discord.gg/tFxwHtZv8k).

## What you need

| | |
|---|---|
| **X-Men Legends for the original Xbox** | your own disc, made into a disc image: a full Redump-style `.iso` or an XISO both work. [How to image your own disc](docs/DUMPING.md). The PlayStation 2 and GameCube versions are different games under the hood and aren't supported (the builder recognises them and says so); compressed images (CCI / CSO) need decompressing first. |
| **X-Men Legends II: Rise of Apocalypse for PC** | installed, English, with the retail `XMen2.exe` (the builder checks it) and unmodified game files. Your install is only read, never changed. |
| **[xml2-fix](https://github.com/ChronoRixun/xml2-fix) matching your builder** | the in-memory engine fixes the port relies on (new-game party, forced parties, the first game's level curve, bigger zones, its own save folder, display options). The Ultimate Legends launcher installs it for you. Each builder needs a minimum version: see [Versions that go together](#versions-that-go-together). |
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
| `info` | identifies the disc image and the XML2 install, estimates space and time, reports the state of an existing build. Reads only. |
| `build` | makes, updates or resumes the build. Options: `--no-movies` (-1.1 GB), `--cache DIR` (default `%LOCALAPPDATA%\xml1-builder\cache`), `--drop-cache`, `--jobs N`, `--no-ini`. |
| `verify` | checks a build against its record: up to date, needs a rebuild, damaged, incomplete; writes `_build\verify-report.json`. `--deep` also re-checks every file inside the disc image. |
| `clean` | deletes exactly what the builder made - never your saves; mods only with `--mods`; `--dry-run` only counts. |

Then copy `dinput.dll` from the [xml2-fix release](https://github.com/ChronoRixun/xml2-fix/releases)
that matches your builder (0.1.12 needs 1.3.2; unreleased 0.2.0 needs 1.4.0)
into the output folder and start `XMen2.exe` there. The builder has already written the `xml2-fix.ini` settings the
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

## Saves in builder 0.2.0 / XML2 Fix 1.4 (unreleased)

Update the builder, rebuild the port, and install XML2 Fix **1.4.0** into the rebuilt game's folder.
Updating the DLL alone does not create the required save catalogue and bindings. Back up the whole
`Documents\Activision\X-Men Legends` profile folder before updating (Documents can be redirected;
`[Game] SaveFolder` can choose another root).

The build sets `[Save] Format=lc`. On the first start, when the profile or save menu first reads files,
old campaigns and the profile are imported from `Save` into sibling `SaveLC`, once per file. Originals
are never modified. Campaigns become `saveslot<N>.lcsave`, the profile `profile.lcsave`; the import ledger
is `SaveLC\legacy-import.txt`. An occupied slot uses another free slot; with all ten occupied an import
waits. Import failures appear in the ledger, log and an in-game notice. Supported old saves retain their
heroes, stats, talents, inventory, progress and unlocks; earlier talent-number changes are translated.
Changed zone or conversation data can reset only its affected state, with notices. This is not a promise
that every custom save or future removal will remain compatible.

Overwriting keeps the previous intact file as `.lcsave.bak`. A missing or damaged primary can load from
that backup. An intact save requiring a newer reader is refused rather than replaced by an older backup.
Before replacing a newer writer/content/catalogue file, the fix protects it as `.lcsave.newer`, including
one found only in `.bak`. An identical protected copy is reused; conflicting or unreadable copies block
the write. Deliberate campaign Delete removes its primary and `.bak`, but retains `.newer`.

If a save/load is refused, preserve the slot and all backups, copy the whole `SaveLC` folder, and check
`xml2-fix.log` and the import ledger. Correct the version pair, rebuild damaged content, or remove the
unsupported mod named by the message, then restart. A refused save has not recorded the latest progress.
Pre-LC releases cannot read `.lcsave`; going back to an old build uses old originals without later progress.

Cosmetic, UI and script mods remain allowed within LC identity rules. Overrides of save-bound data,
numbered entities, map placements, unknown identities or unverifiable package references can refuse LC
activation or saving. This is not unrestricted campaign-mod support. Details are in XML2 Fix 1.4's `docs/save-format.md` and `docs/save-guards.md`.

For online co-op, all players need the **same builder/content, XML2 Fix and combat/mod settings**.
The current 0.2.0 source assigns lobby token **LC23** (content 16, catalogue 5). Matching tokens separate
lobby generations; they do not compare every content file or enforce a complete peer fingerprint check.
Ordinary synchronized saves and a client cold solo reload/resave passed private local tests in upstream
candidate reports. **A save after destroying some objects online can still be refused; the existing save
file is kept.** The witnessed case followed a disconnect; a companion fix is not in these release heads.
Cross-machine internet play and a full manual campaign remain unverified.

## Status

Verified in game on the developer's PC (mostly by automated runs that drive the game through xml2-fix's test pipe):

- **The whole campaign, in automated runs**: the opening, every mission start (73) with the party the first game used
  (forced parties, flashbacks with their fixed heroes and costumes, heroes joining mid-level), the ending chain (the
  final bosses' defeats triggered by script), the credits and back to the main menu; a 154-zone tour in one session
  without a crash. A full hand-played run is under way (act 1 so far).
- **The first game's heroes** with their own stats, powers (64 of 64 fire), unlock points and level curve (its
  45-level table, via xml2-fix), and its enemies with their own damage and energy values.
- **The first game's front end**: main menu, Danger Room, Review (load screens, cinematics), credits.
- **Movies and music**, including the first game's layered music.
- **Display** (xml2-fix): borderless or windowed at your desktop's resolution.
- **A clean Windows 11** (Windows Sandbox: no Python, nothing preinstalled): the released builder made the game from a
  disc image in about 6.5 minutes and verified every file; a new game there played from the intro through several
  zones. The files matched the developer's own builds one for one.

Recent published fixes (rebuild to receive changed content; see [CHANGELOG.md](CHANGELOG.md)):

- **0.1.12 / content 15:** ladder descents, completed objective descriptions, STAT attribute points,
  power/Might-only break rules, effect particles in busy areas, recommended mission teams, rank-1 power damage,
  Xtraction beacon glow, and removal of the sequel's Xtract world map and Blink Portal.
- **0.1.11 / content 14:** Save is available at the twenty formerly restricted Xtraction points.
- **0.1.10:** older hero talent indices translate across the 0.1.8 changes.
- Earlier releases fixed power-wheel loss, NPC gun/projectile damage, conversation timing, skill pickups,
  Danger Room rewards, and several boss and mansion progression problems.

Prepared for **0.2.0 / content 16**, requiring **XML2 Fix 1.4.0** (unreleased): the LC save format above,
first-game combat balance, permanent save identities and registry guards, numbered prop floor placement,
personal-item picture framing/text depth, complete power icons, confirmation-button release handling,
weapon bonuses and integer damage rolls. Mystique's long smash burst remains only partly sounded.

### What isn't there

Some of the first game's features rely on engine code X-Men Legends II doesn't have. Until they are recreated (most
need new engine hooks in xml2-fix), the port plays without them:

- **Solo mode in 18 zones.** The first game let you send the party away for bridge puzzles (from the first ice
  tunnel on), five Astral Plane zones and a nuclear-plant zone with moving platforms. X-Men Legends II turned that
  input into Regroup, so the party stays with you there. Whether that breaks any of those puzzles hasn't been
  checked in game yet ([#5](https://github.com/ChronoRixun/legends-classic/issues/5)).
- **Scan turrets** never aim or fire (12 turrets in 8 zones, starting with the HAARP tank's missiles)
  ([#4](https://github.com/ChronoRixun/legends-classic/issues/4)).
- **Breakable enemy parts**: Juggernaut's helmet never comes off and the Sentinels' arms can't be destroyed
  ([#3](https://github.com/ChronoRixun/legends-classic/issues/3)).
- **Master Mold's warp-core shield.** In the first game his shield drops when the warp cores are destroyed; nothing
  shoots the cores on this engine, so the port never raises the shield and the fight is won on damage alone
  ([#27](https://github.com/ChronoRixun/legends-classic/issues/27)).
- **The first game's loot and shops.** Random drops are X-Men Legends II's, not the first game's equipment. The Healer
  opens a shop, but it is X-Men Legends II's (generated stock, its prices and its training services); Forge's
  workshop is absent ([#6](https://github.com/ChronoRixun/legends-classic/issues/6)).
- **Xtraction services.** Save works at every point since 0.1.11; the sequel's Xtract world map is removed
  in 0.1.12. The first game's Load, Danger Room, Healer and Forge choices are still absent
  ([#95](https://github.com/ChronoRixun/legends-classic/issues/95)).
- **Difficulty.** Published 0.1.12 still differs from the first game's balance; 0.2.0 enables the prepared
  first-game combat rules ([#14](https://github.com/ChronoRixun/legends-classic/issues/14)).
- **Talent costs are X-Men Legends II's**: the first game's two-point Xtreme and Legend ranks cost one point
  ([#15](https://github.com/ChronoRixun/legends-classic/issues/15)).

### Known limitations

- Key bindings and display settings are shared with X-Men Legends II (both read the same Windows registry key);
  saves are separate.
- Online play (*Play Online*) is X-Men Legends II's, through the [OpenSpy](https://openspy.net) servers; port games
  only list other port games. Tested between two copies of the game against a test server, not yet over the internet.
- Local co-op on controllers should work (it is X-Men Legends II's) but has had little testing.
- Open bugs and play-test notes: [issues](https://github.com/ChronoRixun/legends-classic/issues) and
  `research/campaign/late_game_test.md`.

### Versions that go together

A build records the xml2-fix version it needs (`_build\stamp.json`, `requires`). Use the matching pair.
An older DLL can ignore required keys and produce incorrect behavior; it cannot provide LC saves.
The launcher installs published fixes, so it cannot supply unreleased 1.4.0 before publication.

| Builder | Content version | Needs xml2-fix | Notes |
|---|---|---|---|
| 0.2.0 (unreleased) | 18 | 1.4 | the LC save format (`[Save] Format=lc`), the first game's combat balance (`[Balance]`), the entity capacity raise (`[Limits] EntityCapacity`: 768 generic / 1024 World entities), the Master Mold controller (`[Game] Xml1MasterMold`, `Xml1MoldStage`), content fingerprint metadata (`[Online] ContentFingerprint`) and the shared gameplay agreement (co-op peers with different content or settings are refused, with the reason on both PCs); also the 1.3.2 group: ladder descents (`[Game] CharacterLadderPaths`), objective completion text (`[Game] ObjectiveDescriptions`), STAT pickups (`addStatPoints`), the first game's break rule (`[Game] BreakRule`) |
| 0.1.12 | 15 | 1.3.2 | ladder descents (`[Game] CharacterLadderPaths`), objective completion text (`[Game] ObjectiveDescriptions`), STAT pickups (`addStatPoints`), the first game's break rule (`[Game] BreakRule`), the effect curve pool (`[Limits] EffectCurves`), no Xtract world map (`[Game] Xtract`) |
| 0.1.8 - 0.1.11 | 11 - 14 | 1.3.1 | fighting-style registry (`[Limits] FightStyles`), enemy outlines (`[Game] GeometrySharingBlendIndices`) |
| 0.1.6 - 0.1.7 | 8 - 9 | 1.3.0 | conversation hooks, skill points, the item-enhancement pool |
| 0.1.0 - 0.1.5 | 2 - 7 | 1.2.0 | |

Launcher: published 0.3.0 supports this setup flow; builder unpacking under Proton needs 0.2.1 or later.
Main also has additional fixes that are not in the 0.3.0 tag; see its README.

## Roadmap

| | Milestone | State |
|---|---|---|
| M1 | Playable start to finish | done in automated runs; hand-played run under way |
| M2 | Faithful: the first game's front end, Danger Room, parties, level curve, enemy values | done, polishing |
| M3 | **Shippable** | done: builder 0.1.0 and launcher 0.1.0 released 2026-09-29 |
| | build everything from the disc image on the player's PC (the prepare stages) | done |
| | fast sound conversion (a compiled encoder; first build in minutes) | done |
| | the `xml1-builder` program (info / build / verify / clean, progress, cancel and resume) | done |
| | packaging and CI (frozen Windows build, synthetic tests, the content guard) | done |
| | the launcher's setup wizard and game page | done |
| | this public repository, the community Discord | done |
| | release testing on a clean PC (Windows Sandbox): the builder alone, and the launcher's one-click setup | done |
| M4 | **Public test period**: fixes from playthroughs through 0.1.12; 0.2.0 prepares new saves and first-game combat balance | now |
| later | settings separate from X-Men Legends II's; compressed disc images; online play across the internet tested | ideas |

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
