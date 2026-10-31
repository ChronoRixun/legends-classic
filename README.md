![Legends Classic](https://chronorixun.github.io/legends-classic-site/img/banner.png)
# Legends Classic

**Play X-Men Legends (2004) on PC, built from your own copies of the games.**

X-Men Legends came out on consoles only. Its sequel, X-Men Legends II: Rise of Apocalypse, came to PC on the same
engine. Legends Classic takes the first game from **your own Xbox disc** and rebuilds it to run on **your own PC copy
of X-Men Legends II**: the story, the zones, the heroes and their powers, the menus, the movies and the music of the
first game, on the second game's PC engine, with modern display options, controller support and saves of its own.

**You need both games:** your own X-Men Legends disc for the original Xbox, and your own copy of X-Men Legends II for
PC, installed. It is a builder, not a download: every file of the result is made on your computer from the two
copies you own. This project ships no game content - no game files, no parts of them, no modified executables - and
the builder makes no network connections.

How it differs from GTTeancum's [XML1-recomp](https://github.com/GTTeancum/XML1-recomp): that project runs the
original Xbox game natively on PC; Legends Classic runs the first game on the sequel's PC engine, which is what makes
online co-op with drop-in and the sequel's modding possible.

> **Current release: 0.5.0-beta.1** (beta: builder 0.5.0-beta.1, XML2 Fix 1.10.0-beta.1, Ultimate Legends 0.4.0 or
> later on its Beta channel) - the first game's items, shops and drops. Stable: 0.4.0 (XML2 Fix 1.8.0 or later).
> **Coming next: 0.6.0-beta.1** (not released yet): in-game online co-op (Host, Join by code, Browse, lobby and Party), and friends can join a game in progress at the host's next area (the host's DROP-IN setting turns it off per room); co-op checked on two real PCs. <!-- release round: update -->
> Updating? Update Ultimate Legends first, then **Rebuild**, then **Play**. Everyone in an online game needs the same build.
> Help and bug reports: the [community Discord](https://discord.gg/tFxwHtZv8k). Details: [CHANGELOG](CHANGELOG.md),
> [known issues](docs/KNOWN-ISSUES.md).

## What you need

| | |
|---|---|
| **X-Men Legends for the original Xbox** | your own disc, imaged as `.iso` or XISO ([how](docs/DUMPING.md)). PS2 and GameCube discs are different games and don't work. |
| **X-Men Legends II: Rise of Apocalypse for PC** | installed, English, unmodified. It is only read, never changed. |
| **Windows 10 or 11, 64-bit** | Steam Deck / Linux via Proton works as a compatibility path ([notes](docs/CLI.md#steam-deck--proton)). |
| **Disk space and time** | about 8 GB and 6-8 minutes for the first build; rebuilds take 2-3 minutes. |

The engine fix the port needs, [xml2-fix](https://github.com/ChronoRixun/xml2-fix), is installed for you by the
launcher. Full requirements: [docs/CLI.md](docs/CLI.md#requirements).

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

Prefer the command line, or on a Steam Deck? See the [builder guide](docs/CLI.md).

## Playing

- **Saves** live in `Documents\Activision\X-Men Legends`, separate from X-Men Legends II's. Saves from every earlier
  version carry over automatically on first start. 0.5 writes a bigger save format that 0.4.x cannot load, so back up
  the `SaveLC` folder before updating if you may want to go back. Details: [docs/SAVES.md](docs/SAVES.md).
- **Online co-op** for up to four players: host, share a code or list the game publicly; friends join by code or
  from the public list. No port forwarding. Friends can drop in to a game in progress at the host's next area
  (the host can turn drop-in off). In 0.6 all of it moves into the game's own Play Online screens; up to 0.5 you
  start it from Ultimate Legends. Full steps, privacy and limits: [docs/ONLINE.md](docs/ONLINE.md). <!-- release round: update -->
- **Settings and key bindings** are shared with X-Men Legends II (same registry key).

## What to expect

Verified on the developer's PC: the whole campaign from opening to credits, every hero with the first game's stats,
powers and level curve, the first game's front end, movies and layered music, and modern display modes
([details](CHANGELOG.md#verified-in-game)). Online co-op, drop-in and the display options are additions the first game
never had ([what is not fidelity](docs/KNOWN-ISSUES.md#additions-not-fidelity)).

Still open:

- **The first game's loot and shops** are in the 0.5 beta and still being checked ([#6](https://github.com/ChronoRixun/legends-classic/issues/6));
  the stable 0.4.0 uses X-Men Legends II's drops and shops.
- **Some fall kill zones** stay off until proven safe ([#22](https://github.com/ChronoRixun/legends-classic/issues/22)).
- **Enemies attack somewhat more often** than in the original ([#101](https://github.com/ChronoRixun/legends-classic/issues/101)).
- **Online** co-op (0.6) is certified on two PCs on a LAN; internet play through the relay is not verified yet. If the host
  leaves, the session ends (until co-op recovery in 0.8).

Everything open, with measurements: [docs/KNOWN-ISSUES.md](docs/KNOWN-ISSUES.md) and
[issues](https://github.com/ChronoRixun/legends-classic/issues).

## Roadmap

0.6: online co-op with drop-in (the next release). <!-- release round: update --> 0.7: an optional "Remastered" graphics toggle and save import from
the original Xbox game. 0.8: co-op recovery. Then the first game's loot and shops finished, and 1.0 after a full
hand-played run. [Full roadmap](docs/ROADMAP.md).

## Community, contributing and bug reports

- **Discord**: [discord.gg/tFxwHtZv8k](https://discord.gg/tFxwHtZv8k) - setup help, bug reports, co-op partners.
  The same rule as here: no game files, disc images or links to them.
- **Bug reports**: use the issue form. It asks for the builder version, `_build\verify-report.json` and the end of
  `_build\builder.log` (file names, sizes, hashes and error codes) - nothing from the games. Never attach the disc
  image, the build, saves or any game file.
- **Pull requests**: our code and our words only - see [CONTRIBUTING.md](CONTRIBUTING.md). A content guard runs on
  every commit (`pre-commit install`) and in CI; it rejects game files, decoded game data, game text, disassembly
  listings, personal data and large binaries.
- No links to disc images, ROMs or download sites, anywhere in the project.

Building from source, repository layout and the test harness: [docs/BUILDING.md](docs/BUILDING.md).

## Credits

X-Men Legends and X-Men Legends II were made by Raven Software (the PC version of X-Men Legends II with Beenox) and
published by Activision; this project exists because those games are worth playing. Engine fixes:
[xml2-fix](https://github.com/ChronoRixun/xml2-fix). Launcher: [Ultimate Legends](https://github.com/ChronoRixun/ultimate-legends).
Built with Python, numpy, Pillow and PyInstaller. Project: [ChronoRixun](https://github.com/ChronoRixun).

The reverse engineering, the pipeline and these notes were made by one person working with Claude (Opus 5.5 and
Fable 5.1) over a few days; the commit trailers and the research notes show that work as it happened. It is meant as
a showcase of what people and AI can do together on preservation work.

## License and disclaimer

[MIT](LICENSE) for this project's code and documentation.

Legends Classic is an unofficial, non-commercial fan project, not affiliated with or endorsed by Marvel, Disney,
Activision, Raven Software or Beenox. Marvel, X-Men, X-Men Legends and all related character names are trademarks of
Marvel; all other trademarks belong to their owners and are used only to say which games this project works with.
It contains and distributes no game content: you need your own copies of both games. Full text: [LEGAL.md](LEGAL.md).
