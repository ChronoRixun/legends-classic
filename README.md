# Legends Classic

**Play X-Men Legends (2004) on PC, built from your own copies of the games.**

X-Men Legends came out on consoles only. Its sequel, X-Men Legends II: Rise of Apocalypse, came to PC on the same
engine. Legends Classic takes the first game from **your own Xbox disc** and rebuilds it to run on **your own PC copy
of X-Men Legends II**: the story, the zones, the heroes and their powers, the menus, the movies and the music of the
first game, on the second game's PC engine, with modern display options, controller support and saves of its own.

It is a builder, not a download: every file of the result is made on your computer from the two copies you own.
This project ships no game content - no game files, no parts of them, no modified executables - and the builder
makes no network connections.

> **Status: first public test builds (builder 0.1.7, launcher 0.2.0).** Every mission and the ending run in automated
> tests on the developer's PC (a full hand-played run is under way), the builder (`xml1-builder`) makes that build
> from a disc image and an X-Men Legends II install in a few minutes, and the
> [Ultimate Legends](https://github.com/ChronoRixun/ultimate-legends) launcher does it in a few clicks. Known bugs
> and what is next: [Status](#status). Help and bug reports: the [community Discord](https://discord.gg/tFxwHtZv8k).

## What you need

| | |
|---|---|
| **X-Men Legends for the original Xbox** | your own disc, made into a disc image: a full Redump-style `.iso` or an XISO both work. [How to image your own disc](docs/DUMPING.md). The PlayStation 2 and GameCube versions are different games under the hood and aren't supported (the builder recognises them and says so); compressed images (CCI / CSO) need decompressing first. |
| **X-Men Legends II: Rise of Apocalypse for PC** | installed, English, with the retail `XMen2.exe` (the builder checks it) and unmodified game files. Your install is only read, never changed. |
| **[xml2-fix](https://github.com/ChronoRixun/xml2-fix) 1.2.0 or later** | the in-memory engine fixes the port relies on (new-game party, forced parties, the first game's level curve, bigger zones, its own save folder, display options). The Ultimate Legends launcher installs it for you. |
| **Windows 10 or 11, 64-bit** | the released builder is a Windows program. From source it is plain Python + numpy, written to run on Linux too (its tests run there in CI; a full Linux build is untested so far). |
| **Disk space** | about 8 GB while building with movies (the game ~4.6 GB + a build cache ~3.2 GB you can delete afterwards), about 6 GB without movies. |
| **Time** | the first build converts every sound bank: about 6-8 minutes on a current 8-core PC. Rebuilds with the cache take 2-3 minutes. |

## Installing

### With the Ultimate Legends launcher (recommended)

[Ultimate Legends](https://github.com/ChronoRixun/ultimate-legends) (0.1.0 or later; a portable zip, no install)
downloads the builder, runs it and installs xml2-fix for you:

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

Then copy `dinput.dll` from the [latest xml2-fix release](https://github.com/ChronoRixun/xml2-fix/releases/latest)
into the output folder and start `XMen2.exe` there. The builder has already written the `xml2-fix.ini` settings the
port needs (`--no-ini` leaves the file alone; the keys are in `_build\stamp.json`).

The release zip is not code-signed yet, so Windows SmartScreen or an antivirus may warn about it: compare the
SHA-256 with the release page, or build it yourself from source ([docs/BUILDING.md](docs/BUILDING.md)).

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

Fixed in later builders (the launcher offers the rebuild when the content version rises, or run
`xml1-builder build` again - see [CHANGELOG.md](CHANGELOG.md)):

- **Builder 0.1.7 (content version 9): Magneto's shield never held; Shadow King's first form sat on a pillar where
  hits never registered, and his fight could end unfinished after killing his images in the wrong order; arriving
  in the mansion after that mission dropped the hero out of the level; Emma Frost's introduction ended before her
  questions.** All fixed; the boss fights and the mansion arrival were checked by hand. Master Mold's warp-core
  shield is still missing (issue #27).
- **Builder 0.1.6 (content version 8, with XML2 Fix 1.3.0): conversations that advanced by themselves in the first
  game waited for Enter on every line; spoken replies were cut off; SKILL pickups gave XP instead of a skill point;
  most Danger Room reward items never loaded.** All four fixed, two of them through new engine hooks in the fix.
- **Builder 0.1.5 (content version 7): balance - a SKILL pickup levelled the whole roster, bosses could be stunned
  and knocked down like henchmen, and melee did X-Men Legends II's damage numbers instead of the first game's.** All
  three restored to the first game's behaviour (SPEC sections 30-33).
- **Builder 0.1.4 (content version 6): projectile and explosion damage from the first game's data read as zero** -
  freeze and knockback gun shots, grenades, incendiaries, missiles, and Magma's, Pyro's, Mystique's and the Shades'
  thrown attacks did no damage. They do now, with the first game's numbers; expect those fights to hurt.
- **Builder 0.1.3 (content version 5): with builder 0.1.2, in zones with gun soldiers the third and fourth heroes
  of the party had no power wheel** (holding the power key did nothing for them; the next zone restored it). A
  packaging slip in 0.1.2; fixed, and the builder now refuses to produce it.
- **Builder 0.1.2 (content version 4): the first game's gun soldiers fired blanks** - the GRSO rifles, lasers,
  lightning and nullifier guns, the HAARP soldiers and flamethrowers, the pistol thugs did no damage and showed no
  tracer, sound or flame (the flamethrower's flame was invisible). They now fire, hit and are drawn, with the first
  game's damage numbers; expect the HAARP exterior to be harder than it was.
- **Builder 0.1.1 (content version 3): a hero's powers vanished from the power wheel after loading a save in a few
  zones** (nyc1_1_3 and 1_1_2b for Cyclops, the two Danger Room flashback zones with him, the sewer hub zone where
  Gambit is met, nuke2_2 for Colossus, the Blackbird arbiter zone). Leaving the zone brought them back; nothing was
  lost.

Known limitations:

- Key bindings and display settings are shared with X-Men Legends II (both read the same Windows registry key);
  saves are separate.
- Online play (*Play Online*) is X-Men Legends II's, through the [OpenSpy](https://openspy.net) servers; port games
  only list other port games. Tested between two copies of the game against a test server, not yet over the internet.
- Local co-op on controllers should work (it is X-Men Legends II's) but has had little testing.
- Open bugs and play-test notes: [issues](https://github.com/ChronoRixun/legends-classic/issues) and
  `research/campaign/late_game_test.md`.

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
| M4 | **Public test period**: the fixes the play-throughs turn up (0.1.1: the power-wheel bug above; 0.1.2: the silent gun soldiers; 0.1.3: the missing power wheels; 0.1.4: zero-damage projectiles; 0.1.5: skill pickups, boss immunities, melee numbers; 0.1.6: conversations, skill points, Danger Room rewards; 0.1.7: Magneto and Shadow King, the Emma conversation, the mansion arrival), then a balance pass (melee versus powers against the first game's enemy values) | now |
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
