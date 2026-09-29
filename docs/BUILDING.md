# Building from source

Everything here runs on your own PC with your own copies of the games. Nothing in this repository contains game
data, so every command that builds or tests the port reads your disc image and your X-Men Legends II install.

## Set-up

- **Python 3.14, 64-bit** (the version the release is frozen with and CI tests on) and the pinned numpy:

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

## Tests

| What | Command | Needs |
|---|---|---|
| Unit tests (synthetic: disc images, bundles, the prepare stages on made-up inputs, the builder CLI on a stub pipeline, packaging) | `python tests/unit/run.py` (or `pytest tests/unit`) | nothing; CI runs them on Windows and Linux |
| Content guard | `python tools/check_no_game_content.py --self-test` and `--all` | nothing |
| Sound kernel self-check | `python tools/build_sound_kernel.py --check` | a built kernel |
| The pipeline's self-tests | `python -m xml1build.<module>_selftest --out <a build>` from `tools/` (characters, heroes, scripts, zones, skins, automaps, combat_events, npc_values, frontend, validate, sound) | a build + the games |
| Equivalence of two builds | `python tools/build_equiv.py <build A> <build B>` | two builds |

Tests that need the games never run in CI: a public repository's workflows must not reach game files.

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
release.

## Where to read next

- `tools/xml1build/SPEC.md` - what every pipeline module does and why (the engine facts behind it), section 27 for
  the prepare stages and the builder.
- `tools/xml1build/SPEC_heroes.md` - the hero conversion.
- `research/release/BUILDER_DESIGN.md` - the builder, packaging, launcher integration and the publishing rules.
- `research/` - the notes behind the decisions ([research/README.md](../research/README.md)).
