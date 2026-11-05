# Building from source

Everything here runs on your own PC with your own copies of the games. Nothing in this repository contains game
data, so every command that builds or tests the port reads your disc image and your X-Men Legends II install.

## Set-up

- **Python 3.14, 64-bit** (the version the release is frozen with and CI tests on) and the pinned numpy and Pillow:

  ```
  python -m pip install -r requirements.txt
  ```

- **Optional: the compiled sound kernel** (`tools/xml1build/lib/ima_kernel.c`, plain C loaded with ctypes). Without
  it the sound stages run on numpy, 6-8x slower (the first build then takes ~15 minutes instead of ~6). It needs MSVC
  on Windows (Visual Studio or the Build Tools with the C++ workload; found through vswhere) or `cc` elsewhere:

  ```
  python tools/build_sound_kernel.py            # -> build/native/ima_kernel-<platform>.dll|so, self-checked
  ```

  The pipeline uses the library only if it was built from the current `ima_kernel.c` and passes its self-check
  (byte-identical output to the numpy path); the build log says which codec ran (`sound codec: ...`).

- Optional for developer tools: `XML2_DIR` = your X-Men Legends II folder (the default of the developer tools'
  `--base`; the builder itself always takes `--xml2`).

## The builder from source

```
cd tools
python -m xml1builder info  --iso <your disc image> --xml2 <your XML2 folder>
python -m xml1builder build --iso <your disc image> --xml2 <your XML2 folder> --out <new folder> [--no-movies]
python -m xml1builder verify --out <new folder>
```

The same commands, options, events (`--events jsonl`, what the launcher reads) and exit codes as the released
`xml1-builder.exe`; see `python -m xml1builder --help` and `research/release/BUILDER_DESIGN.md` section 2. The cache
defaults to `%LOCALAPPDATA%\xml1-builder\cache` (`--cache DIR` elsewhere). The output folder must not overlap the
XML2 install, the disc image, the cache or this repository's `tools/` and `research/` folders (the builder refuses).

`--iso` also auto-detects an extracted Xbox install folder, including a recomp install. All consumed originals
must match the packaged World dump hashes; loose overlays are ignored. Output, cache and log files must stay
outside that source install. See [using an extracted install](DUMPING.md#already-play-the-recomp-point-the-builder-at-its-folder).

Maintainers can regenerate `tools/xml1builder/data/known_dump_files.json` from an owned image with
`python -m xml1builder.devdata folder-reference --iso <image>` (from `tools/`). The command first checks the
whole-image SHA-256 against a trusted value already recorded in `known_dumps.json`, then checks the existing
executable, archive-directory and disc-listing fingerprints. It writes only names, sizes and SHA-256 hashes.
An extracted folder or an unknown image cannot supply a new trusted reference.

## Tests

`--online-menus on` is the 0.6 release default with the XML1 front end. It enables the custom
online screens, native Host/Join skins and private Barlow fonts together. `--online-menus off` keeps the fallback. It
requires `--frontend xml1` and one companion DLL carrying the exact menu, input,
lobby, broker (`lc-online-broker/2`), native Host/admission (`lc-online-native/1`) and font capabilities; a release number or
separate DLLs do not suffice.
Place that DLL in the output folder before the frontend runs. A missing or
incompatible DLL refuses the build, including the old-fix warning path.

The installer writes `[Online] Menus=1` and `[Game] LegendsClassicFonts=1` only
for a recorded enabled build with complete resources and the exact asset
marker. Rebuilding with the option off restores the owned base's native lobby
menus and removes the generated online resources and both owned INI keys.
Play Online always retains the native `openmenu online` command as fallback.

Round 5 wires the custom screens to the DLL's broker bridge with constant
commands only: `lcOnlineIntent` 18 Refresh, 19 Open room, 20 Retry, 21 Public/Private,
22/23 page, 24..30 select Browse row 0..6 (a page authors `online_menus.BROWSE_ROWS` = 7 rows, so 24..30 are
used) and 31 Join selected (resolve only), each
valid only on its own screen (`online_menus.BROKER_SCOPE`, checked by the validator).
Every authored menu scene stays within the supplied DLL's probed capacity (175 retail, 512 with `menu-anchors/512`; the
retail playfield build `0x5882e0` overflows at 175, while the expanded push refuses above 512); the builder and `output_problems` refuse more.
Browse and the two lobby skins (round 15's cause scenes / notices / inline lobby scenes + the two backdrop models) fit
because their focus bars share one model item per plane (`SHARED_FOCUS_SCREENS`: `lc_focus` at -150, `lc_focus_300` at
-300, at the scene origin): each focusable item sets it to its own bar on focus (authored at the owner's absolute
position) and hides it on nofocus; XMen2.exe's setFocus (0x5aaf80) loses the old item before the new one gains. The
clipboard / unavailable notices Browse can never raise are not authored there (the DLL falls back to `lc_inline_error`).
The independent native menu item map also holds at most **175 items**: insertion `0x5af490` checks the
count at menu `+0x1608` against `0xaf` at `0x5af4af` (owned retail-image recheck,
companion `docs/online-menus.md`, "Native item-map budget and LAN list fixes"). The
`menu-anchors/512` capability does not raise it. Tree validation, final backdrop authoring
and `output_problems` check this item limit separately from scene anchors. Current owned
menus including backdrops use Browse **172**, host lobby **173**, join lobby **169** items.
The lobbies reuse the hero fallback DATA field for linked rate plus slow-peer warning;
Browse keeps seven rows with numeric occupancy and one build label per row.
LAN rows additionally require the companion `lc-fonts-list/1` private LISTBOX scale;
its centered focus art follows the native row-center positioning. Rebuild content with
the matching DLL; no release/content identity is assigned by this fix.
Every Browse row cell exists from the start with its row command and starts disabled;
the DLL binds text and enables rows. Hidden localized variants (`lc_broker_*`, the
`lc_host_private`/`lc_host_public` scenes, `lc_rowN_selected`) are selected by the
DLL; remote text only ever reaches DATA fields and `broker_error` is a diagnostic
label, never a command. Room opening and joining create or resolve the broker room
only: native campaign setup and admission into the native lobby are the next round.
The native Host/Join classes retain their own actions, rosters and
admission. No live room, RTT, build, campaign or hero data is invented. Copy and
Code tool captions currently list both supported keyboard/pad shortcuts because
the supplied DLL contract does not expose an authored device selector for those
special actions. Guest Back state is shown in the right action bar; its footer
X caption remains Ready / Unready. These presentation gaps and real-game input,
clipping and rendering acceptance remain open; the option is experimental.
The retained native LISTBOXes keep their original font styles: their row metric
and render methods bypass the private CText scale hooks. New cards and status
fields use Barlow. The temporary Kick picker therefore retains native lettering;
its layered backdrop, arrows and actual selection/mouse bounds need live checks.
Code cells use neutral frames because input API /1 publishes cell text but no
cursor scene selector. Done and Start use native enabled text/focus rather than
baking a disabled state into an immutable background.

The classic main menu is XML1's composition, which the game centres at every aspect (4:3 to
21:9) without any change to the file. `--main-menu-layout` keeps only `classic`; the 0.2.0j
`widescreen` value, which pushed the menu right of centre, is accepted as a retired name for
`classic`. English medium/big letters also affect other menus and dialogs sharing those
global font indices. The bright Cerebro backdrop requires a companion XML2 Fix build with
`[Game] ClassicMainBackdrop=1`; the builder writes that key for the classic main menu.

| What | Command | Needs |
|---|---|---|
| Unit tests (synthetic: disc images, bundles, the prepare stages on made-up inputs, the builder CLI on a stub pipeline, packaging) | `python tests/unit/run.py` (or `pytest tests/unit`) | nothing; CI runs them on Windows and Linux |
| Content guard | `python tools/check_no_game_content.py --self-test` and `--all` | nothing |
| Sound kernel self-check | `python tools/build_sound_kernel.py --check` | a built kernel |
| The pipeline's self-tests | `python -m xml1build.<module>_selftest --out <a build>` from `tools/` (characters, heroes, scripts, zones, skins, automaps, combat_events, npc_values, frontend, validate, sound) | a build + the games |
| Equivalence of two builds | `python tools/build_equiv.py <build A> <build B>` | two builds |

For the offline G3 saved-zone corpus, use
[`check_saved_zone_corpus.py`](saved-zone-corpus.md) with the native host and a
finished W2/economy build. It checks all 148 inputs, reporting 147 successful
loads separately from the hash-pinned synthetic capacity save's expected refusal.

Tests that need the games never run in CI: a public repository's workflows must not reach game files.
The [release checklist](RELEASE_CHECKLIST.md) makes the zones output self-test a required local gate
for every release candidate and gives its exact command (its build directory is positional).

## The developer build

`tools/build_xml1.py` is the pipeline's own entry point with every test and A/B option (`--start-zone`, `--tour`,
`--only`, `--frontend`, `--forced-teams`, ...; `--help` lists them, `tools/xml1build/SPEC.md` explains them). Point
it at a prepare cache made by the builder or by `tools/prepare_xml1.py`:

```
python tools/prepare_xml1.py --cache <cache> --iso <your disc image> --base <your XML2 folder>
python tools/build_xml1.py --sources prepared --cache <cache> --base <your XML2 folder> --out build/dev --no-movies
```

`--test-ini` also writes `.codegpt-game.json`, a small JSON launch manifest for game-automation tools.

## The in-game test harness

The tools that drive a running game (`campaign_walk.py`, `power_sweep.py`, `tour_runner.py`, `fixinput.py`,
`conv_probe.py`, `hero_xp.py`, ...) work on any build folder with xml2-fix's test pipe enabled:
`tools/harness.py install <build>` writes the `[Test]` keys into that build's `xml2-fix.ini` (never into your real
XML2 install). They run the game in a window and send input through the pipe, so they don't need the focus - but
they do start the game: run them when nobody is playing on that PC.

For experimental AI/pathfinding play and local failure reports, see [the autopilot guide](AUTOPILOT.md).
Its owned build, generated goal cache and run evidence must live outside Git.

## Freezing the exe

```
python -m pip install -r requirements-freeze.txt      # PyInstaller, pinned
python tools/build_sound_kernel.py                     # the release ships the kernel
python tools/freeze_builder.py --smoke                 # -> dist/xml1-builder/, the zip, xml1-builder.json, SHA256SUMS.txt
```

`freeze_builder.py` packages the research tables the builder reads (without game text), runs PyInstaller in
one-folder mode (no UPX), runs the content guard over the bundled data, zips the result with the launcher's release
manifest and, with `--smoke`, runs `tools/freeze_smoke.py` against it. CI does the same on every push
(`.github/workflows/release.yml`); a `v*` tag that matches `VERSION` in `tools/xml1builder/__init__.py` publishes the
release. Beta and rc tags match the numeric base and carry the suffix through the frozen
builder and manifest; see [RELEASING.md](RELEASING.md).

## Repository layout

| Path | What |
|---|---|
| `tools/xml1builder/` | the builder (`python -m xml1builder` from `tools/`; frozen into `xml1-builder.exe`) |
| `tools/xml1build/` | the conversion pipeline (zones, characters, heroes, scripts, front end, media, validator), the prepare stages (`prepare/`), shared format code (`lib/`) and the specifications `SPEC.md` / `SPEC_heroes.md` |
| `tools/` | format tools (disc image, bundles, binary XML, sound banks), the developer build `build_xml1.py`, the freeze scripts and the test harness that drives the game through xml2-fix |
| `tests/unit/` | synthetic tests (no game data); CI runs them on Windows and Linux |
| `research/` | the reverse-engineering and design notes behind every decision: file formats, engine behaviour, addresses, measurements ([research/README.md](../research/README.md)) |
| `docs/` | player guides - [CLI.md](CLI.md) (the standalone builder), [SAVES.md](SAVES.md), [ONLINE.md](ONLINE.md), [COMPATIBILITY.md](COMPATIBILITY.md) (versions and settings), [KNOWN-ISSUES.md](KNOWN-ISSUES.md), [ROADMAP.md](ROADMAP.md), [DUMPING.md](DUMPING.md) (imaging your own disc) - and developer notes: this file (from source, tests, freezing), [RELEASING.md](RELEASING.md) |
| `tools/check_no_game_content.py` | the guard that keeps game content out of this repository (pre-commit hook + CI) |

## Where to read next

- `tools/xml1build/SPEC.md` - what every pipeline module does and why (the engine facts behind it), section 27 for
  the prepare stages and the builder.
- `tools/xml1build/SPEC_heroes.md` - the hero conversion.
- `research/release/BUILDER_DESIGN.md` - the builder, packaging, launcher integration and the publishing rules.
- `research/` - the notes behind the decisions ([research/README.md](../research/README.md)).

The frontend stage also builds the classic HUD atlas and models for both
frontend modes and writes `[Game] ClassicHud=xml1` and `[Game] ClassicCodex=1`
(0.4.0-beta.5, the classic look). They need XML2 Fix 1.8.0-beta.5 or later; the
builder refuses an older DLL by name. See [the HUD contract](CLASSIC_HUD_PILOT.md)
for the off switch and acceptance limits.

The characters stage also derives the NPC weapon-brain contract from your XML1
npcstat, weapons and powerstyles (`_build/semi_auto.json`), and every XML1 build
writes `[Game] NpcSemiAuto=xml1` with its `[NpcSemiAuto]` rows (schema 4, every
gun NPC since 0.4.0-beta.7; gameplay rule 16 revision 11; SPEC 95.4). They need
XML2 Fix 1.8.0-beta.7 or later (beta 6 read only the officer's schema 2 row); the
builder refuses an older DLL by name.

Schema 4 requires the beta 7 bullet-trace follow-up DLL and a content rebuild
(SPEC 95.5). Earlier beta 7 DLLs refuse these wider rows; a DLL swap alone into
an old content build does not add the converted-bullet event markers.


### Co-op model resource lifetime

Static menu models must serialize a single scene information reference with
matching list count, capacity and reference-buffer length. Shortening the
logical list while retaining discarded pump/scene references leaks the model's
pixel graph in Alchemy on every reopen (060s). `menu_scene.static_model` rebuilds
the root information buffer; the unit test checks the complete serialized
reference set. The optional Win32 owned-runtime test in
[`tests/native`](../tests/native/README.md) loads/unloads each co-op skin resource
set repeatedly and asserts flat private memory and handle counts after warm-up.
It uses the player's copied runtime DLLs and generated output, never starts
XMen2.exe, and does not replace integration's full output build and live check.

The 060s lobby/Browse presentation fixes keep the lobby card words in native text items in front of the card models;
readiness, role and build labels must not be converted back into overlapping coplanar raster surfaces. These display
labels are disabled for native hit testing and keep explicit palette prefixes for their authored glyph colors. The X1
follow-up shares Browse Refresh's highlight with the rows to fit the native focus-event budget. The Party Invite hint has normal and navy
copies, selected by the companion DLL. Build these assets with the corresponding fix P DLL changes; unit contracts
cover the generated trees and layout, while final depth, keyboard/pad and mouse behavior still needs a rendered check.


The 060t online presentation follow-up requires the matching companion DLL for
accepted resolution overrides, stale-empty Browse, guest controller prompts and
PDA Party mouse focus. Code/Browse author one shared highlight and at most 75 native
focus records; a builder contract rejects overflow. Paging uses separate footer
cells and footer bars share a consistent shear. The integration build must regenerate
menu resources and the hit table together. Module unit tests cover authoring here;
full owned-input generation and live visual acceptance remain separate gates.

The Wave 3 self-test retains the original 080c witness counts. A build with the
exact authored private Guard node adds one shared FightMove and two resident
trigger events: moves 307, largest style 109, events 833. This is self-test
accounting only; capacities and the census counting rules are unchanged. Missing
Guard nodes retain historical expectations; malformed or altered Guard payloads
are refused instead of adjusting the expected totals from observed content.
## 060u presentation follow-up

Regenerate online menu resources and `Data/lc_online_hits.txt` with the matching
companion DLL. Browse's header is now the complete DATA count (`1 public game`
or `1 last known game`), with its own space before the stale badge. The empty
static `list_header` anchor remains for layout compatibility.

Code/Browse keep 40/41 focus records. Their shared-origin model names require
the companion's expanded, bounded frontend string arena; its native string
handles and scene-anchor layout stay compatible. The companion also clears the
shared focus model when Retry loses focus, hides or becomes disabled. Native
and synthetic authoring tests cover these contracts; integration still needs
owned-output regeneration and live rendering/input checks.
Release maintainers: [Guard default and acceptance switch](RELEASE_GUARD.md).

Optional native online presentation is authored by `online_native_skins.py`:
the online text editor, Other ways settings and all four policy/info modes,
Host/Join chooser, native LAN/IP browser and the PC Join-options intermediate
page. Original menu classes, actions, modes, policy content and list services
come from the player's definitions. Unsupported or additional unknown widgets
publish an empty optional capability marker and select the plain LC failure page.
Each variant requires its matching adapter marker in the companion DLL before
the builder advertises it. The installer/output validator checks the same
complete resource closure. This changes generated content; integration owns
the content/cache identity and must regenerate the front end before live checks.


LC never falls back to the GameSpy-era online pages. `online_fallback.py` always
writes a native-font LC message for `lc_online_entry` and failed/unsupported
online resources, even when online menus are off. Back and Escape return to Main
through a native cancel item. Only already-skinned host/join resources are kept;
all retained online variants drop GameSpy/sequel logo model records and their
references. The DLL must expose `lc-online-no-gamespy/1` for enabled online menus.
Regenerate the matching content; the maintainer assigns its new content/cache
identity. No release/content token is assigned by this behavior change.
