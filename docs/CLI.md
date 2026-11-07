# The `xml1-builder` program

The standalone builder, for people who don't use the Ultimate Legends launcher. Maintainers: [how to cut stable, beta
and rc releases](RELEASING.md).

## Requirements

- **X-Men Legends for the original Xbox**, your own disc made into a disc image: a full Redump-style `.iso` or an
  XISO both work ([how to image your own disc](DUMPING.md)). Compressed images (CCI / CSO) need decompressing first.
  The PlayStation 2 and GameCube versions are different games under the hood and aren't supported (the builder
  recognises them and says so).
- **X-Men Legends II: Rise of Apocalypse for PC**: installed, English, with the retail `XMen2.exe` (the builder checks
  it) and unmodified game files. Your install is only read, never changed.
- **[xml2-fix](https://github.com/ChronoRixun/xml2-fix)**: the in-memory engine fixes the port relies on (new-game
  party, forced parties, the first game's level curve and combat numbers, bigger zones, its own save format and
  folder, display options). The Ultimate Legends launcher installs it for you. Each builder needs a minimum version
  (0.6.0-beta.3 needs 1.11.0-beta.3, 0.6.0-beta.1 needs 1.11.0-beta.1, 0.5.0-beta.1 needs 1.10.0-beta.1, the stable 0.4.0 needs 1.8.0): see
  [versions that go together](COMPATIBILITY.md).
- **Windows 10 or 11, 64-bit.** The released builder is a Windows program. From source it is plain Python + numpy +
  Pillow, written to run on Linux too (its tests run there in CI; a full Linux build is untested so far).
- **Disk space**: about 8 GB while building with movies (the game ~4.6 GB + a build cache ~3.2 GB you can delete
  afterwards), about 6 GB without movies.
- **Time**: the first build converts every sound bank: about 6-8 minutes on a current 8-core PC. Rebuilds with the
  cache take 2-3 minutes.

## Install

Download `xml1-builder-<version>-win64.zip` from [Releases](https://github.com/ChronoRixun/legends-classic/releases)
(check it against `SHA256SUMS.txt`) and unzip it into a folder of its own (the zip has no top-level folder).

**Before Build or Rebuild**, create the output folder and copy `dinput.dll` from the matching
[xml2-fix release](https://github.com/ChronoRixun/xml2-fix/releases) into it - for 0.6.0-beta.3 that is
**XML2 Fix 1.11.0-beta.3** (a beta builder needs the matching beta fix, not the latest stable one). The default
co-op screens check this DLL while the build runs; updating the fix only in your X-Men Legends II folder is not
enough. Then run the builder from a command prompt:

```
xml1-builder info    --iso "D:\Images\X-Men Legends.iso" --xml2 "C:\Games\X-Men Legends II"
xml1-builder build   --iso "D:\Images\X-Men Legends.iso" --xml2 "C:\Games\X-Men Legends II" --out "C:\Games\X-Men Legends (Port)"
xml1-builder verify  --out "C:\Games\X-Men Legends (Port)"
xml1-builder clean   --out "C:\Games\X-Men Legends (Port)"
```

After the build succeeds, start `XMen2.exe` in the output folder. The builder writes the port's `xml2-fix.ini`
settings (`--no-ini` leaves the file alone and records the required keys in `_build\stamp.json`).

The release zip is not code-signed yet, so Windows SmartScreen or an antivirus may warn about it: compare the
SHA-256 with the release page, or build it yourself from source ([BUILDING.md](BUILDING.md)).

## Commands

| Command | Does |
|---|---|
| `info` | identifies the disc image and the XML2 install, estimates space and time, reports the state of an existing build. Options: `--iso`, `--xml2`, `--out`, `--cache`. Reads only. |
| `build` | makes, updates or resumes the build. Options: `--iso`, `--xml2`, `--out`, `--cache DIR` (default `%LOCALAPPDATA%\xml1-builder\cache`), `--movies` (the default) or `--no-movies` (-1.1 GB), `--keep-cache` (the default) or `--drop-cache`, `--jobs N` (sound-conversion workers, default every CPU), `--no-ini`, `--main-menu-layout classic\|widescreen` (widescreen is a retired name for classic), `--allow-unknown-exe` (testers: an `XMen2.exe` that is not a known retail build). |
| `verify` | checks a build against its record: up to date, needs a rebuild, damaged, incomplete; writes `_build\verify-report.json`. Options: `--out`, `--iso`, `--xml2`; `--deep` also re-checks every file inside the disc image. |
| `clean` | deletes exactly what the builder made - never your saves; mods only with `--mods`; `--dry-run` only counts. |

Options that work with every command: `--events jsonl|text` (`jsonl` prints JSON-lines events for the launcher),
`--log FILE`, `--quiet` and `--version`. `xml1-builder --help` lists them all, including the feature options added
since 0.4.2 (see the [CHANGELOG](../CHANGELOG.md)).

`build --classic-conversation off|xml1` selects the conversation background. The default is **off**,
which keeps the native PC model. `xml1` uses the blue background from your own XML1 Xbox disc;
the builder validates its scene and embedded images before replacing `UI/hud/convo_background.IGB`.
Unsupported or missing inputs fail the build with recovery instructions and leave the base model in place.
Rebuild with `--classic-conversation off` to restore the PC background.

This is an appearance setting that requires rebuilding, independent of the main menu, Classic HUD,
fonts and Remastered. Text, portraits, response selection, input and conversation timing keep their
existing behavior. There is no runtime INI switch. Launcher controls are a separate integration;
this builder option does not imply that a launcher setting has shipped. Direct-substitution visual
acceptance, including widescreen and Remastered coverage, remains pending.

## What the build does

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

Saves go to `Documents\Activision\X-Men Legends`, separate from X-Men Legends II's ([SAVES.md](SAVES.md)).

## First start

The first time the game starts, Windows 10 or 11 may ask to install **DirectPlay**, an old Windows component that
Windows' own compatibility list requests for X-Men Legends II. Either answer works: *Install this feature* (once, from
Windows Update) stops the question, and *Skip this installation* lets the game start without it.

## Steam Deck / Proton

These releases are Windows programs. Running them through Proton is a compatibility path, not a native Linux release
or a fully tested Deck configuration. With the launcher, use Ultimate Legends 0.2.1 or later: earlier launchers could
not unpack the builder there. For a direct Steam shortcut to the game, put the DLL beside the executable and, if the
fix is not loaded, try this in the shortcut's Launch Options:

```text
WINEDLLOVERRIDES="dinput=n,b" %command%
```

Check for `xml2-fix.log` in the game folder to confirm the DLL loaded. Keep the same Proton prefix when updating:
saves are under that prefix's Windows Documents folder (which may be redirected). See
[Proton's runtime configuration](https://github.com/ValveSoftware/Proton#runtime-config-options) for Steam Launch
Options. Controller and Discord behaviour under Proton has not been verified here.
