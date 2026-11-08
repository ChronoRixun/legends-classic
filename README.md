![Legends Classic](https://legends.aethyrion.org/img/banner.png)
# Legends Classic

**Play X-Men Legends (2004) on PC, built from your own copies of the games.**

**Website:** [legends.aethyrion.org](https://legends.aethyrion.org) - screenshots, what you need, and how to start.

X-Men Legends came out on consoles only. Its sequel, X-Men Legends II: Rise of Apocalypse, came to PC on the same
engine. Legends Classic takes the first game from **your own Xbox disc** and rebuilds it to run on **your own PC copy
of X-Men Legends II**: the story, the zones, the heroes and their powers, the menus, the movies and the music of the
first game, on the second game's PC engine, with modern display options, controller support and saves of its own.

**You need both games:** your own X-Men Legends disc for the original Xbox, and your own copy of X-Men Legends II for
PC, installed. It is a builder, not a download: every file of the result is made on your computer from the two
copies you own. This project ships no game content - no game files, no parts of them, no modified executables - and
the builder makes no network connections.

Unlike [XML1-recomp](https://github.com/GTTeancum/XML1-recomp), which runs the original Xbox game natively, Legends
Classic runs the first game on the sequel's PC engine - which is what makes online co-op and the sequel's mods possible.

> **Current beta: 0.6.0-beta.4**, paired with XML2 Fix 1.11.0-beta.4 on Ultimate Legends' Beta channel.
> Beta.4 fixes Arbiter progression hatches and crew rescue, destroyed pylon cleanup, temporary control effects,
> loaded-save Healer/Forge availability and the lost-newcomer restart notice.
> Update both parts, **Rebuild**, then **Play**. beta.1, beta.2 and beta.3 saves load; online builds must match.
> Previous beta: 0.6.0-beta.3. Stable: 0.4.0. See [CHANGELOG](CHANGELOG.md) and [known issues](docs/KNOWN-ISSUES.md).

## What you need

| | |
|---|---|
| **X-Men Legends for the original Xbox** | your own disc, imaged as `.iso` or XISO ([how](docs/DUMPING.md)). PS2 and GameCube discs are different games and don't work. |
| **X-Men Legends II: Rise of Apocalypse for PC** | installed, English, unmodified. It is only read, never changed. |
| **Windows 10 or 11, 64-bit** | Steam Deck / Linux via Proton works as a compatibility path ([notes](docs/CLI.md#steam-deck--proton)). |
| **Disk space and time** | about 8 GB and 6-8 minutes for the first build; rebuilds take 2-3 minutes. |

The launcher installs the engine fix the port needs, [xml2-fix](https://github.com/ChronoRixun/xml2-fix), for you.
Full requirements: [docs/CLI.md](docs/CLI.md#requirements).

## Installing

[Ultimate Legends](https://github.com/ChronoRixun/ultimate-legends) (a portable zip, no install) does everything:
it downloads the builder, runs it and installs the engine fix.

1. Set up **X-Men Legends II** in the launcher as usual (it installs xml2-fix).
2. Open **X-Men Legends - community port** in the library and choose **Set up**.
3. Pick your disc image and a destination folder. The launcher checks the image, shows the space and time the build
   needs, and lets you switch the movies and the build cache on or off.
4. **Build** (6-8 minutes): a checklist of stages with a progress bar; you can hide it, cancel it and resume later.
5. **Play.** The launcher installs xml2-fix into the new folder and sets its display defaults.

The launcher tells you when a new builder needs a rebuild (never automatic), can **Verify** every file, and
**Uninstall** removes exactly what it made - your saves stay.

Prefer the command line, or on a Steam Deck? See the [builder guide](docs/CLI.md). Without the launcher, copy the
matching XML2 Fix `dinput.dll` into the output folder **before** you build: the default co-op screens need it.
The standalone builder's `--iso` also accepts an extracted X-Men Legends install folder, including a compatible
XML1-recomp install; the original files are checked, and saves and loose mods are not brought across
([dumping guide](docs/DUMPING.md)).

## Playing

- **Saves** live in `Documents\Activision\X-Men Legends`, separate from X-Men Legends II's, and earlier saves carry
  over. 0.4.x cannot load the bigger 0.5/0.6 saves, so back up `SaveLC` before updating ([docs/SAVES.md](docs/SAVES.md)).
- **Online co-op** for up to four players, from the game's own **Play Online** screen: **Host** a public or private
  room, **Join by code** or **Browse** public games, get ready in the lobby, and manage the group from **Party**.
  Friends can join a game in progress at the host's next area. Steps, privacy and limits: [docs/ONLINE.md](docs/ONLINE.md).
- **Settings and key bindings** are shared with X-Men Legends II (same registry key).

## What to expect

Verified on the developer's PC: the whole campaign from opening to credits, every hero with the first game's stats,
powers and level curve, its front end, movies and layered music, and modern display modes ([details](CHANGELOG.md#verified-in-game)).
Online co-op and the display options are additions the first game never had ([what is not fidelity](docs/KNOWN-ISSUES.md#additions-not-fidelity)).

Still open (everything, with measurements: [docs/KNOWN-ISSUES.md](docs/KNOWN-ISSUES.md) and [issues](https://github.com/ChronoRixun/legends-classic/issues)):

- **The first game's items, shops and drops** shipped in 0.5.0-beta.1 and are on by default; they are still being
  checked against the original ([#6](https://github.com/ChronoRixun/legends-classic/issues/6)). Stable 0.4.0 uses X-Men Legends II's.
- **Some fall kill zones** stay off until proven safe ([#22](https://github.com/ChronoRixun/legends-classic/issues/22)).
- **Enemies attack somewhat more often** than in the original ([#101](https://github.com/ChronoRixun/legends-classic/issues/101)).
- **Online** co-op is a beta. Co-op was tested on one PC and on two PCs at home, with two, three and four players,
  including fights. Not verified yet: playing through the relay (networks where a direct connection fails), four
  players on four separate PCs, long sessions, and joins over slow connections. If the host leaves, the session
  ends (until co-op recovery in 0.8).

## Roadmap

0.6 (this beta): online co-op in the game's own screens, with joining a game in progress; beta.2 adds the shared
frame rate and the rest of the online screens; a later 0.6 beta adds save import from xemu and XML1-recomp. 0.7: an
optional "Remastered" graphics toggle. 0.8: co-op recovery. 0.9: moves and characters tuned against the original.
1.0 after a full hand-played run. [Full roadmap](docs/ROADMAP.md).

## Community, contributing and bug reports

- **Website**: [legends.aethyrion.org](https://legends.aethyrion.org).
- **Discord**: [discord.gg/tFxwHtZv8k](https://discord.gg/tFxwHtZv8k) - setup help, bug reports, co-op partners.
- **Bug reports**: use the issue form (builder version, `_build\verify-report.json`, the end of `_build\builder.log`).
  Never attach the disc image, the build, saves or any game file, and no links to disc images or ROMs anywhere.
- **Pull requests**: our code and our words only - see [CONTRIBUTING.md](CONTRIBUTING.md). A content guard runs on
  every commit and in CI and rejects game files, decoded game data, game text and personal data.

Building from source, repository layout and the test harness: [docs/BUILDING.md](docs/BUILDING.md).

## Credits

X-Men Legends and X-Men Legends II were made by Raven Software (the PC version of X-Men Legends II with Beenox) and
published by Activision; this project exists because those games are worth playing. Engine fixes:
[xml2-fix](https://github.com/ChronoRixun/xml2-fix). Launcher: [Ultimate Legends](https://github.com/ChronoRixun/ultimate-legends).
Built with Python, numpy, Pillow and PyInstaller. Project: [ChronoRixun](https://github.com/ChronoRixun).

The reverse engineering, the pipeline and these notes were made by one person working with AI; the commit trailers and the research notes show that work as it happened.

## License and disclaimer

[MIT](LICENSE) for this project's code and documentation.

Legends Classic is an unofficial, non-commercial fan project, not affiliated with or endorsed by Marvel, Disney,
Activision, Raven Software or Beenox. Marvel, X-Men, X-Men Legends and all related character names are trademarks of
Marvel; all other trademarks belong to their owners and are used only to say which games this project works with.
It contains and distributes no game content: you need your own copies of both games. Full text: [LEGAL.md](LEGAL.md).
